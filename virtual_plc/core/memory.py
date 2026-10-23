"""Typed, bounded PLC memory. A force takes precedence over cyclic writes."""
from __future__ import annotations

from copy import deepcopy
import math
import re

from .compiler import IEC_BLOCKS, literal, iec_string
from .libraries import BLOCK_INPUTS, BLOCK_OUTPUTS, block_member, block_field_type

MAX_VARIABLES = 50_000
MAX_ARRAY_ELEMENTS = 65_536
MAX_MEMORY_ELEMENTS = 300_000
MAX_STRING_LENGTH = 4096
INTEGER_TYPES = {"SINT": (-128, 127), "USINT": (0, 255), "BYTE": (0, 255),
                 "INT": (-32768, 32767), "UINT": (0, 65535), "WORD": (0, 65535),
                 "DINT": (-2147483648, 2147483647), "UDINT": (0, 4294967295), "DWORD": (0, 4294967295),
                 "LINT": (-9223372036854775808, 9223372036854775807),
                 "ULINT": (0, 18446744073709551615), "LWORD": (0, 18446744073709551615)}
INTEGER_TYPES.update(DATE_AND_TIME=(0,4294967295),DT=(0,4294967295))


class MemoryErrorPLC(ValueError):
    pass


def global_scope(scope: str | None) -> bool:
    return str(scope or "").lower() in {"", "global", "@global", "var_global"}


class PLCMemory:
    def __init__(self, variables: list[dict], types: dict | None = None, strict: bool = True, case_sensitive: bool = False):
        if len(variables) > MAX_VARIABLES:
            raise MemoryErrorPLC(f"PLC variable limit exceeded ({MAX_VARIABLES})")
        self.case_sensitive = case_sensitive
        self.types = {self.symbol_key(key): value for key, value in (types or {}).items()}
        self._spec_cache={}
        self.records: dict[str, dict] = {}
        self.identities: dict[str, str] = {}
        self.names: dict[str, list[str]] = {}
        self._resolution_cache = {}
        self.element_count = 0
        self._allocating = False
        self.strict, self.diagnostics = strict, []
        for item in variables:
            try:
                self.add(item)
            except (ValueError, KeyError, TypeError) as error:
                if strict: raise
                self.diagnostics.append({"severity": "error", "code": "MEMORY_DECLARATION", "message": str(error),
                                         "source": item.get("source", ""), "line": item.get("line", 1)})

    def symbol_key(self, value):
        """B&R identifiers preserve case; generic IEC workspaces retain their dialect."""
        return str(value) if self.case_sensitive else str(value).casefold()

    def spec(self, typename, depth: int = 0):
        if isinstance(typename,dict):return typename
        name=str(typename or '').strip()
        if name not in self._spec_cache:self._spec_cache[name]=self._spec_impl(name,depth)
        return self._spec_cache[name]

    def _spec_impl(self, typename, depth: int = 0):
        if depth > 30:
            raise MemoryErrorPLC("Recursive IEC type definition")
        if isinstance(typename, dict):
            return typename
        name = str(typename or "").strip()
        reference=re.fullmatch(r'(?i)REFERENCE\s+TO\s+(.+)',name)
        if reference:return {**self.spec(reference[1],depth+1),'referenceTo':reference[1]}
        c_alias={'plcbit':'BOOL','plcstring':'USINT','plcdt':'DATE_AND_TIME'}
        if name in c_alias:return self.spec(c_alias[name],depth+1)
        if name.endswith('*'):
            return {'kind':'scalar','type':'UDINT','pointsTo':name[:-1].strip()}
        alias = self.types.get(self.symbol_key(name))
        if alias is not None:
            if isinstance(alias, str):
                return self.spec(alias, depth+1)
            if alias.get("kind", "").lower() in {"alias", "scalar"}:
                return self.spec(alias.get("type", alias.get("baseType", alias.get("base", ""))), depth+1)
            return alias
        array = re.fullmatch(r"(?is)ARRAY\s*\[(.*?)\]\s*OF\s*(.+)", name)
        if array:
            bounds = []
            for dimension in array.group(1).split(","):
                match = re.fullmatch(r"\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*", dimension)
                if not match:
                    raise MemoryErrorPLC("Only resolved constant array bounds are executable: " + name)
                bounds.append([int(match[1]), int(match[2])])
            return {"kind": "array", "bounds": bounds, "elementType": array.group(2).strip()}
        string = re.fullmatch(r"(?i)(W?STRING)(?:\s*[\[(]\s*(\d+)\s*[\])])?", name)
        if string:
            return {"kind": "string", "length": min(int(string[2] or 80), MAX_STRING_LENGTH)}
        upper = name.upper().replace(" ", "")
        if upper in INTEGER_TYPES or upper in {"BOOL", "REAL", "LREAL", "TIME", "LTIME"}:
            return {"kind": "scalar", "type": upper}
        if upper in IEC_BLOCKS:
            return {"kind": "block", "type": upper}
        if name.endswith('_typ') and self.symbol_key(name[:-4]) in self.types:
            return self.spec(name[:-4],depth+1)
        # User FB interfaces are registered as a struct by the runtime.
        raise MemoryErrorPLC("Unsupported or unresolved IEC type: " + name)

    def default(self, spec, depth: int = 0, budget=None):
        if depth > 30:
            raise MemoryErrorPLC("Memory type nesting limit exceeded")
        if budget is None: budget = [MAX_MEMORY_ELEMENTS]
        budget[0] -= 1
        if budget[0] < 0:
            raise MemoryErrorPLC("Transient PLC memory element limit exceeded")
        if self._allocating:
            self.element_count += 1
            if self.element_count > MAX_MEMORY_ELEMENTS:
                raise MemoryErrorPLC("PLC memory element limit exceeded")
        kind = spec.get("kind", "").lower()
        if kind == "array":
            bounds = spec.get("bounds", [])
            if bounds and isinstance(bounds[0], (int, float)):
                bounds = [bounds]
            if not bounds:
                raise MemoryErrorPLC("Array bounds are not resolved")
            low, high = map(int, bounds[0])
            count = high-low+1
            if not 0 <= count <= MAX_ARRAY_ELEMENTS:
                raise MemoryErrorPLC("Array element limit or invalid bounds")
            nested = {**spec, "bounds": bounds[1:]} if len(bounds) > 1 else self.spec(spec.get("elementType", spec.get("element", "")))
            return [self.default(nested, depth+1, budget) for _ in range(count)]
        if kind == "struct":
            result = {}
            for field in self.fields(spec):
                field_spec = self.spec(field["type"])
                field_default = self.default(field_spec, depth+1, budget)
                result[field["name"]] = self.coerce(field["initial"], field_spec, depth+1) if field.get("initial") is not None else field_default
            return result
        if kind == "enum":
            values = self.enum_values(spec)
            return next(iter(values.values()), 0)
        if kind == "string":
            return ""
        if kind == "block":
            return {"IN": False, "PT": 0.0, "Q": False, "ET": 0.0, "CU": False, "CD": False,
                    "R": False, "LD": False, "PV": 0, "CV": 0, "CLK": False, "_state": {}}
        if kind == "scalar":
            return False if spec.get("type") == "BOOL" else 0.0 if spec.get("type") in {"REAL", "LREAL", "TIME", "LTIME"} else 0
        raise MemoryErrorPLC("Unsupported type specification: " + str(spec))

    @staticmethod
    def fields(spec):
        fields = spec.get("fields", [])
        return [{"name": key, "type": value} if isinstance(value, str) else {"name": key, **value}
                for key, value in fields.items()] if isinstance(fields, dict) else fields

    @staticmethod
    def enum_values(spec):
        values = spec.get("values", {})
        if isinstance(values, dict):
            return {str(key): int(value) for key, value in values.items()}
        return {item["name"] if isinstance(item, dict) else str(item):
                int(item.get("value", i)) if isinstance(item, dict) else i for i, item in enumerate(values)}

    def coerce(self, value, spec, depth: int = 0):
        if depth > 30:
            raise MemoryErrorPLC("Memory type nesting limit exceeded")
        if value is None:
            return self.default(spec, depth)
        kind = spec.get("kind", "").lower()
        # AS exports a zeroed FB instance as := (0). This is aggregate zero
        # initialization, not an expression or a scalar assigned to a block.
        if kind in {'block','struct','array'} and isinstance(value,str) and re.fullmatch(r'\(\s*0\s*\)',value):
            return self.default(spec,depth)
        if isinstance(value, str) and kind not in {"string"}:
            if kind == "enum":
                matching = {self.symbol_key(key): val for key, val in self.enum_values(spec).items()}
                if self.symbol_key(value) in matching:
                    value = matching[self.symbol_key(value)]
                else:
                    value = literal(value)
            elif value.strip().startswith("[") and kind == "array":
                # JSON arrays only: no expression evaluation during initialization.
                import json
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    repetition = re.fullmatch(r'\[\s*(\d+)\s*\(\s*(.*?)\s*\)\s*\]', value, re.S)
                    if not repetition or int(repetition[1]) > MAX_ARRAY_ELEMENTS:
                        raise MemoryErrorPLC('Unsupported IEC array initializer') from None
                    value = [literal(repetition[2]) for _ in range(int(repetition[1]))]
            else:
                value = literal(value)
        if kind == "scalar":
            typename = spec["type"]
            if typename == "BOOL":
                if value not in (False, True, 0, 1):
                    raise MemoryErrorPLC("BOOL requires TRUE/FALSE or 0/1")
                return bool(value)
            if typename in INTEGER_TYPES:
                if isinstance(value, bool):
                    value = int(value)
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value):
                    raise MemoryErrorPLC(typename + " requires a finite integral value")
                low, high = INTEGER_TYPES[typename]
                if not low <= int(value) <= high:
                    raise MemoryErrorPLC(typename + " value is out of range")
                return int(value)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise MemoryErrorPLC(typename + " requires a finite number")
            if typename in {"TIME", "LTIME"} and value < 0:
                raise MemoryErrorPLC("TIME duration cannot be negative")
            return float(value)
        if kind == "enum":
            if value not in self.enum_values(spec).values():
                raise MemoryErrorPLC("Value is outside declared enumeration")
            return int(value)
        if kind == "string":
            if not isinstance(value, str) or len(value) > spec.get("length", 80):
                raise MemoryErrorPLC("STRING value exceeds declared length or is not text")
            return value
        if kind == "array":
            bounds = spec.get("bounds", [])
            if bounds and isinstance(bounds[0], (int, float)):
                bounds = [bounds]
            if not bounds or not isinstance(value, list) or len(value) != int(bounds[0][1])-int(bounds[0][0])+1:
                raise MemoryErrorPLC("Array initial value must match declared bounds")
            nested = {**spec, "bounds": bounds[1:]} if len(bounds) > 1 else self.spec(spec.get("elementType", spec.get("element", "")))
            return [self.coerce(item, nested, depth+1) for item in value]
        if kind in {"struct", "block"}:
            if not isinstance(value, dict):
                raise MemoryErrorPLC("Structure requires a field mapping")
            default = self.default(spec, depth)
            if kind == "block":
                if set(value) - set(default):
                    raise MemoryErrorPLC("Unknown IEC function block field")
                for key, child in value.items():
                    if key == "_state":
                        if not isinstance(child, dict) or set(child) - {"previous", "start"}:
                            raise MemoryErrorPLC("Unsupported IEC internal state")
                        if any(not isinstance(part, (int, float, bool)) or not math.isfinite(part) for part in child.values()):
                            raise MemoryErrorPLC("Invalid IEC state value")
                        default[key] = deepcopy(child)
                    else:
                        field_type = block_field_type(spec["type"], key)
                        default[key] = self.coerce(child, self.spec(field_type), depth+1)
            else:
                fields = {self.symbol_key(field["name"]): field for field in self.fields(spec)}
                for key, child in value.items():
                    if self.symbol_key(key) not in fields:
                        raise MemoryErrorPLC("Unknown structure field: " + key)
                    field = fields[self.symbol_key(key)]
                    default[field["name"]] = self.coerce(child, self.spec(field["type"]), depth+1)
            return default
        raise MemoryErrorPLC("Unsupported value type")

    def add(self, item: dict):
        if len(self.records) >= MAX_VARIABLES:
            raise MemoryErrorPLC("PLC variable limit exceeded")
        name, scope = str(item["name"]), str(item.get("scope") or "@global")
        identifier = str(item.get("id") or scope + "::" + name)
        if identifier in self.records:
            raise MemoryErrorPLC("Duplicate variable identity: " + identifier)
        if any(self.records[key]["scope"].casefold() == scope.casefold() for key in self.names.get(self.symbol_key(name), [])):
            raise MemoryErrorPLC("Duplicate variable declaration: " + scope + "::" + name)
        try:
            spec = self.spec(item.get("type", item.get("datatype")))
            self._allocating = True
            try:
                default = self.default(spec)
            finally:
                self._allocating = False
            initial_value = item.get('initial')
            if spec.get('kind') == 'string' and isinstance(initial_value, str) and not item.get('initialDecoded'):
                initial_value = iec_string(initial_value)
            initial = self.coerce(initial_value, spec) if initial_value is not None else default
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            if self.strict: raise
            spec, initial = {"kind": "unresolved", "message": str(error)}, None
            self.diagnostics.append({"severity": "warning", "code": "MEMORY_UNRESOLVED_TYPE", "message": str(error),
                                     "source": item.get("source", ""), "line": item.get("line", 1), "variable": name,
                                     "detail": "The declaration is visible but cannot execute. An active reference blocks simulation."})
        record = {**deepcopy(item), "id": identifier, "name": name, "scope": scope,
                  "type": item.get("type", item.get("datatype")), "value": initial, "previous": deepcopy(initial),
                  "lastUpdate": 0, "forced": False, "quality": "unresolved" if spec.get("kind") == "unresolved" else "simulated",
                  "_forcedValue": None, "_spec": spec, "_initial": deepcopy(initial)}
        self._resolution_cache.clear()
        self.records[identifier] = record
        self.identities[self.symbol_key(identifier)] = identifier
        self.names.setdefault(self.symbol_key(name), []).append(identifier)
        return record

    def resolve(self, name: str, scope: str | None = None):
        key=(name,scope)
        cached=self._resolution_cache.get(key)
        if cached is not None:return cached
        record=self._resolve_uncached(name,scope)
        if len(self._resolution_cache)>=100000:self._resolution_cache.clear()
        self._resolution_cache[key]=record
        return record

    def _resolve_uncached(self, name: str, scope: str | None = None):
        identity = self.identities.get(self.symbol_key(name))
        if identity is not None:
            return self.records[identity]
        explicit_scope = '::' in str(name)
        if explicit_scope:
            scope, name = str(name).rsplit('::', 1)
        candidates = [self.records[key] for key in self.names.get(self.symbol_key(name), [])]
        scoped = [item for item in candidates if scope is not None and item["scope"].casefold() == scope.casefold()]
        if scoped:
            return scoped[0]
        if explicit_scope:
            raise MemoryErrorPLC('Unresolved scoped variable: ' + scope + '::' + name)
        globals_ = [item for item in candidates if global_scope(item["scope"])]
        if len(globals_) == 1:
            return globals_[0]
        if scope is None and len(candidates) == 1:
            return candidates[0]
        raise MemoryErrorPLC(("Ambiguous" if candidates else "Unresolved") + " variable: " + name + (" in " + scope if scope else ""))

    def member(self, value, spec, path: list, evaluate):
        for segment in path:
            if 'bit' in segment:
                bounds=INTEGER_TYPES.get(spec.get('type',''))
                bit=segment['bit']
                if not bounds or not 0<=bit<(bounds[1]-bounds[0]+1).bit_length()-1:raise MemoryErrorPLC('Bit index exceeds declared integer width')
                value=bool(int(value)&(1<<bit));spec={'kind':'scalar','type':'BOOL'}
            elif "member" in segment:
                requested = segment["member"]
                if spec.get("kind") == "block":
                    requested = block_member(spec["type"], requested)
                    if requested not in BLOCK_INPUTS[spec["type"]] | BLOCK_OUTPUTS[spec["type"]]:
                        raise MemoryErrorPLC("Unknown block member: " + requested)
                keys = {self.symbol_key(key): key for key in value} if isinstance(value, dict) else {}
                if self.symbol_key(requested) not in keys or requested.startswith("_"):
                    raise MemoryErrorPLC("Unresolved structure/member: " + requested)
                key = keys[self.symbol_key(requested)]
                value = value[key]
                if spec.get("kind") == "struct":
                    field = next(field for field in self.fields(spec) if self.symbol_key(field["name"]) == self.symbol_key(requested))
                    spec = self.spec(field["type"])
                elif spec.get("kind") == "block":
                    spec = self.spec(block_field_type(spec["type"], key))
                else:
                    raise MemoryErrorPLC("Member access on non-structure")
            else:
                if spec.get("kind") != "array":
                    raise MemoryErrorPLC("Array access on non-array")
                raw_index = evaluate(segment["index"])
                if isinstance(raw_index, bool) or not isinstance(raw_index, (int, float)) or raw_index != int(raw_index):
                    raise MemoryErrorPLC("Array index must be integral")
                bounds = spec["bounds"]
                if bounds and isinstance(bounds[0], (int, float)):
                    bounds = [bounds]
                low, high = map(int, bounds[0])
                if not low <= int(raw_index) <= high:
                    raise MemoryErrorPLC(f"Array index {raw_index} outside [{low}..{high}]")
                value = value[int(raw_index)-low]
                spec = {**spec, "bounds": bounds[1:]} if len(bounds) > 1 else self.spec(spec.get("elementType", spec.get("element", "")))
        return value, spec

    def reference_spec(self, reference, scope=None, specification=None):
        """Resolve the declared leaf type without reading/evaluating PLC values.

        Ladder contacts and ST references must use the same member/array rules.
        Dynamic indexes are checked at execution time; literal indexes can also
        be rejected before Run, without accidentally executing an expression.
        """
        if specification is None:
            record = self.resolve(reference["name"], scope)
            if record.get("ambiguous"):
                raise MemoryErrorPLC("Conflicting declarations make variable ambiguous: " + reference["name"])
            specification = record["_spec"]
        for segment in reference.get("path", []):
            if specification.get("kind") == "unresolved":
                raise MemoryErrorPLC("Active variable has unresolved type: " + reference["name"] + ": " + specification.get("message", ""))
            if 'bit' in segment:
                bounds=INTEGER_TYPES.get(specification.get('type',''));bit=segment['bit']
                if not bounds or not 0<=bit<(bounds[1]-bounds[0]+1).bit_length()-1:raise MemoryErrorPLC('Bit index exceeds declared integer width')
                specification={'kind':'scalar','type':'BOOL'}
            elif segment.get('dereference'):
                if not specification.get('pointsTo'):raise MemoryErrorPLC('Dereference requires a declared pointer')
                specification=self.spec(specification['pointsTo'])
            elif 'index' in segment and specification.get('pointsTo'):
                specification=self.spec(specification['pointsTo'])
            elif "member" in segment:
                requested = self.symbol_key(segment["member"])
                if specification.get("kind") == "block":
                    requested = block_member(specification["type"], requested)
                    if requested not in BLOCK_INPUTS[specification["type"]] | BLOCK_OUTPUTS[specification["type"]]:
                        raise MemoryErrorPLC("Unknown block member: " + requested)
                    specification = self.spec(block_field_type(specification["type"], requested))
                elif specification.get("kind") == "struct":
                    field = next((field for field in self.fields(specification) if self.symbol_key(field["name"]) == requested), None)
                    if field is None:
                        raise MemoryErrorPLC("Unknown structure member: " + requested)
                    specification = self.spec(field["type"])
                else:
                    raise MemoryErrorPLC("Member access requires a structure/block")
            elif "index" in segment:
                if specification.get("kind") != "array":
                    raise MemoryErrorPLC("Array index requires an array")
                bounds = specification["bounds"]
                if bounds and isinstance(bounds[0], (int, float)):
                    bounds = [bounds]
                index = segment["index"]
                if index.get("op") == "literal":
                    value = index["value"]
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
                        raise MemoryErrorPLC("Array index must be integral")
                    if not int(bounds[0][0]) <= value <= int(bounds[0][1]):
                        raise MemoryErrorPLC(f"Array index {value} outside [{bounds[0][0]}..{bounds[0][1]}]")
                specification = {**specification, "bounds": bounds[1:]} if len(bounds) > 1 else self.spec(specification.get("elementType", specification.get("element", "")))
            else:
                raise MemoryErrorPLC("Unrecognized variable path segment")
        if specification.get("kind") == "unresolved":
            raise MemoryErrorPLC("Active variable has unresolved type: " + reference["name"] + ": " + specification.get("message", ""))
        return specification

    def read(self, reference, scope, evaluate):
        record = self.resolve(reference["name"], scope)
        if record.get("ambiguous"):
            raise MemoryErrorPLC("Conflicting declarations make variable ambiguous: " + record["name"])
        value = record["_forcedValue"] if record["forced"] else record["value"]
        return self.member(value, record["_spec"], reference.get("path", []), evaluate)[0]

    def write(self, reference, value, scope, evaluate, time_ms: float, force: bool = False):
        record = self.resolve(reference["name"], scope)
        if record.get("ambiguous"):
            raise MemoryErrorPLC("Conflicting declarations make variable ambiguous: " + record["name"])
        path = reference.get("path", [])
        if record["forced"] and not force:
            return None
        if record.get("constant") or record.get("mode") == "VAR_CONSTANT":
            raise MemoryErrorPLC("Cannot write a constant: " + record["name"])
        current, spec = self.member(record["value"], record["_spec"], path, evaluate)
        converted = self.coerce(value, spec)
        if current==converted and not force:return None
        previous = deepcopy(record["value"])
        if path:
            parent, parent_spec = self.member(record["value"], record["_spec"], path[:-1], evaluate)
            final = path[-1]
            if "member" in final:
                requested = block_member(parent_spec["type"], final["member"]) if parent_spec.get("kind") == "block" else final["member"]
                key = next(key for key in parent if self.symbol_key(key) == self.symbol_key(requested))
                parent[key] = converted
            else:
                bounds = parent_spec["bounds"]
                low = bounds[0][0] if isinstance(bounds[0], (list, tuple)) else bounds[0]
                parent[int(evaluate(final["index"]))-int(low)] = converted
        else:
            record["value"] = converted
        if force:
            record["forced"] = True
            record["_forcedValue"] = deepcopy(record["value"])
        if previous != record["value"]:
            record["previous"] = previous
            record["lastUpdate"] = time_ms
            return {"id": record["id"], "name": record["name"], "previous": previous, "value": deepcopy(record["value"])}
        return None

    def release(self, name, scope=None):
        record = self.resolve(name, scope)
        record["forced"] = False
        record["_forcedValue"] = None

    def reset(self, cold=False):
        for record in self.records.values():
            if cold or not record.get("retain", False):
                record["value"] = deepcopy(record["_initial"])
            record["previous"] = deepcopy(record["value"])
            record["forced"] = False
            record["_forcedValue"] = None
            record["lastUpdate"] = 0

    def snapshot(self, compact=False, watchlist=()):
        if compact:
            from .preview import value_preview
            watched = set(watchlist)
            result = []
            for index, item in enumerate(self.records.values()):
                if index >= 1000 and item['id'] not in watched and item['name'] not in watched:
                    continue
                row = {key: item[key] for key in ('id','name','scope','type','source','line','constant','forced','retain','lastUpdate','ambiguous') if key in item}
                for field in ('value','previous'):
                    row[field], complete = value_preview(item.get(field))
                    if not complete: row['valueTruncated'] = True
                result.append(row)
            return result
        return [{key: deepcopy(value) for key, value in item.items() if not key.startswith("_")}
                for item in self.records.values()]
