"""Deterministic Virtual PLC interpreter, independent of the validation engine.

Only compiled instructions execute. It never opens a PLC connection, writes a
project file, evaluates Python, or invokes code from the imported project.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from functools import reduce
import math
import re
import time

from .compiler import BUILTINS, IEC_BLOCKS, STATEFUL_CALLS, Parser, compile_ladder, compile_source, literal, walk_ir
from .libraries import BLOCK_INPUTS, BLOCK_OUTPUTS, LibraryError, block_member, builtin, execute_block
from .vendor import CALLS as VENDOR_CALLS, FILE_BLOCKS, VendorRuntime, call_name, register_types
from .cpu import CALLS as CPU_CALLS, BLOCKS as CPU_BLOCKS, CPURuntime, register_types as register_cpu_types
from .vendor_services import CALLS as SERVICE_CALLS, BLOCKS as SERVICE_BLOCKS, ServiceRuntime, register_types as register_service_types
from .memory import INTEGER_TYPES, MemoryErrorPLC, PLCMemory, global_scope

MAX_INSTRUCTIONS_PER_SCAN = 1_000_000
MAX_LOOP_ITERATIONS = 65_536
MAX_CALL_DEPTH = 24
MAX_CALL_FRAME_ELEMENTS = 50_000
MAX_TRACE = 3000
MAX_SIGNAL_HISTORY = 256
MAX_TOTAL_SIGNAL_HISTORY = 10_000
MAX_EDGE_STATES = 50_000


def _preview(value, depth=0, budget=None):
    """Bound archival event payloads independently of the full PLC memory."""
    if budget is None: budget = [128]
    budget[0] -= 1
    if budget[0] < 0: return "<trace element limit>"
    if depth > 4:
        return "<nested value omitted from trace>"
    if isinstance(value, dict):
        result = {}
        for key, child in list(value.items())[:32]:
            if budget[0] <= 0:
                result["__traceTruncated"] = True
                break
            if not str(key).startswith("_"):
                result[str(key)] = _preview(child, depth+1, budget)
        if len(value) > 32: result["__traceTruncated"] = True
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for child in value[:32]:
            if budget[0] <= 0:
                result.append("<trace element limit>")
                break
            result.append(_preview(child, depth+1, budget))
        if len(value) > 32: result.append("<remaining elements omitted from trace>")
        return result
    return value[:512] + "<trace truncated>" if isinstance(value, str) and len(value) > 512 else value


class RuntimeErrorPLC(ValueError):
    pass


class ReturnPLC(Exception):
    def __init__(self, value=None):
        self.value = value


class ExitPLC(Exception):
    pass


class JumpPLC(Exception):
    def __init__(self, label):
        self.label = label


def _diagnostic(code, message, source="", line=1, severity="error", **extra):
    return {"severity": severity, "code": code, "message": str(message)[:2000], "source": source, "line": int(line or 1), **extra}


class VirtualRuntime:
    def __init__(self, project: dict):
        self.project = deepcopy(project)
        self.symbol_case_sensitive = project.get("symbolCaseSensitive") is True
        self.status, self.time_ms, self.scan_count, self.speed = "stopped", 0, 0, 1.0
        self.trace = deque(maxlen=MAX_TRACE)
        self.diagnostics = []
        self.units, self.callables, self.enum_constants, self.actions = {}, {}, {}, {}
        self.tasks, self.initializers, self.exits = [], [], []
        self.breakpoints = set()
        self._sequence, self._budget, self._call_depth = 0, 0, 0
        self._pending, self._pending_instruction, self._skip_breakpoint = None, None, False
        self._initialized, self._context = False, {}
        self._task_timing_interrupted = False
        self.signal_history = {}
        self._edge_memory = {}
        self._signal_history_count = 0
        self.vendor = VendorRuntime(self)
        self.cpu = CPURuntime(self)
        self.services = ServiceRuntime(self)
        self._requested_reset = None
        self._access_bindings={}
        self._load()

    def symbol_key(self, value):
        return str(value) if self.symbol_case_sensitive else str(value).casefold()

    def _load(self):
        from .io_bindings import connect_io
        connect_io(self.project.setdefault('hardware', {}), self.project.get('variables', []), self.project.get('tasks', []))
        programs = list(self.project.get("programs", [])) + list(self.project.get("functions", []))
        # .fun files describe callable interfaces. Their formals and internal
        # parameters are not independent PLC memory allocations. Real instances
        # and called frames still undergo their normal type/dependency checks.
        variables = deepcopy([v for v in self.project.get("variables", [])
                              if not str(v.get('source', '')).lower().endswith('.fun')])
        types = deepcopy(self.project.get("types", {}))
        register_types(types, case_sensitive=self.symbol_case_sensitive)
        register_cpu_types(types, case_sensitive=self.symbol_case_sensitive)
        register_service_types(types, case_sensitive=self.symbol_case_sensitive)
        self.diagnostics.extend(deepcopy(self.project.get("diagnostics", [])))
        declarations_by_unit = {}
        for index, program in enumerate(programs):
            identifier = str(program.get("id") or program.get("name") or "program-" + str(index))
            if identifier in self.units:
                if self.units[identifier].get("source") == program.get("source", identifier) and self.units[identifier].get("code", "") == program.get("code", ""):
                    continue  # adapters expose functions as a subset of programs
                self.diagnostics.append(_diagnostic("DUPLICATE_PROGRAM", "Duplicate executable identity: " + identifier))
                continue
            source = program.get("source", identifier)
            language = program.get("language", "st").lower().lstrip(".")
            compiled = compile_ladder(program.get("networks", program.get("code", "")), source, source_text=program.get("code", "")) if language == "ld" else compile_source(program.get("code", ""), language, source)
            interface = program.get("interface")
            if isinstance(interface, dict) and interface.get("declaration"):
                parsed_interface = compile_source(interface["declaration"], "st", interface.get("source", source))
                compiled["diagnostics"].extend(parsed_interface["diagnostics"])
                existing = {(item.get("scope", "").casefold(), self.symbol_key(item["name"])) for item in compiled["declarations"]}
                compiled["declarations"].extend(item for item in parsed_interface["declarations"]
                                                if (item.get("scope", "").casefold(), self.symbol_key(item["name"])) not in existing)
                for body in compiled['sections']:
                    header=next((s for s in parsed_interface['sections'] if self.symbol_key(s['name'])==self.symbol_key(body['name'])),None)
                    if header and not body.get('returnType'):body['returnType']=header.get('returnType')
            unit = {**program, "id": identifier, "scope": program.get("scope") or program.get("name") or identifier,
                    "compiled": compiled, "sections": compiled["sections"], "source": source}
            self.units[identifier] = unit
            declarations_by_unit[identifier] = compiled.get("declarations", [])
            for section in compiled["sections"]:
                section["unitId"] = identifier
                if section['kind']=='action':
                    self.actions.setdefault((unit['scope'].casefold(),self.symbol_key(section['name'])),[]).append(section)
                if section["kind"] in {"function", "function_block"}:
                    key = self.symbol_key(section.get("callName", section["name"]))
                    self.callables.setdefault(key, []).append(section)
                    if section["kind"] == "function_block":
                        fields = [{"name": declaration["name"], "type": declaration["type"]}
                                  for declaration in compiled.get("declarations", [])
                                  if self.symbol_key(declaration.get("scope", "")) == self.symbol_key(section["name"])]
                        types.setdefault(section["name"], {"kind": "struct", "fields": fields, "functionBlock": True})
            # Some parsers supply body-only functions with a separate interface.
            if program.get("kind", "").lower() in {"function", "functionblock", "function_block"} and not any(
                    section["kind"] in {"function", "function_block"} for section in compiled["sections"]):
                for section in compiled["sections"]:
                    section["name"] = program.get("name", identifier)
                    section["kind"] = "function" if program["kind"].lower() == "function" else "function_block"
                    section["returnType"] = program.get("returnType")
                    self.callables.setdefault(self.symbol_key(section["name"]), []).append(section)
                    for declaration in program.get("interface", []) if isinstance(program.get("interface"), list) else []:
                        declarations_by_unit[identifier].append({**declaration, "scope": section["name"],
                            "mode": declaration.get("mode", "VAR_INPUT")})
        known = {(str(item.get("scope") or "@global").casefold(), self.symbol_key(item["name"])) for item in variables}
        for identifier, declarations in declarations_by_unit.items():
            unit = self.units[identifier]
            callable_names = {self.symbol_key(section["name"]) for section in unit["sections"] if section["kind"] in {"function", "function_block"}}
            for declaration in declarations:
                if str(declaration.get('source', '')).lower().endswith('.fun') and declaration.get('mode') != 'VAR_GLOBAL':
                    continue
                if self.symbol_key(declaration.get("scope", "")) in callable_names:
                    continue
                scope = "@global" if declaration.get("mode") == "VAR_GLOBAL" else unit["scope"]
                key = (scope.casefold(), self.symbol_key(declaration["name"]))
                if key not in known:
                    item = {**declaration, "scope": scope, "id": scope + "::" + declaration["name"]}
                    expression = declaration.get("initialExpression")
                    if expression:
                        if expression.get("op") != "literal":
                            self.diagnostics.append(_diagnostic("INITIALIZER_EXPRESSION", "Only literal variable initializers are executable", unit["source"], declaration.get("line")))
                        else:
                            item["initial"] = expression["value"]
                            item['initialDecoded'] = True
                    variables.append(item)
                    known.add(key)
        try:
            self.memory = PLCMemory(variables, types, strict=False, case_sensitive=self.symbol_case_sensitive)
            self.diagnostics.extend(self.memory.diagnostics)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self.memory = PLCMemory([], {}, case_sensitive=self.symbol_case_sensitive)
            self.diagnostics.append(_diagnostic("MEMORY_TYPE", str(error)))
        self.simulation_profile=None
        if self.project.get('simulationProfile'):
            from .profiles import apply_profile
            try:self.simulation_profile=apply_profile(self,self.project['simulationProfile'])
            except ValueError as error:self.diagnostics.append(_diagnostic('SIMULATION_PROFILE',str(error)))
        for reference in self.project.get("references", []):
            for identity in self.memory.names.get(self.symbol_key(reference.get("name", "")), []):
                record = self.memory.records[identity]
                if reference.get("scope") == record["scope"] or global_scope(record["scope"]):
                    references = record.setdefault("references", [])
                    if len(references) < 50:
                        references.append({key: value for key, value in reference.items() if key != "name"})
        for typename, specification in self.memory.types.items():
            if isinstance(specification, dict) and specification.get("kind", "").lower() == "enum":
                for name, value in self.memory.enum_values(specification).items():
                    if self.symbol_key(name) in self.enum_constants and self.enum_constants[self.symbol_key(name)] != value:
                        self.enum_constants[self.symbol_key(name)] = None
                    else:
                        self.enum_constants[self.symbol_key(name)] = value
                    self.enum_constants[typename + "#" + self.symbol_key(name)] = value
        for index, task in enumerate(self.project.get("tasks", [])):
            if task.get("enabled", True) is False:
                continue
            if (task.get("assignments") == [] and not task.get("programs")
                    and not task.get("initializationPrograms") and not task.get("exitPrograms")):
                self.diagnostics.append(_diagnostic("TASK_EMPTY", "Unused task class has no program assignments: " + task.get("name", str(index)), severity="info", excluded=True))
                continue
            task = deepcopy(task)
            from .lifecycle import schedule_entries,unit_phases
            schedule_entries(task,{identity:unit_phases(unit) for identity,unit in self.units.items()})
            task.setdefault("id", task.get("name", "task-" + str(index)))
            task.setdefault("name", task["id"])
            task.setdefault("priority", index)
            task["executionCount"], task["lastExecutionMs"], task["lastWallDurationMs"] = 0, None, None
            interval = task.get("intervalMs")
            if str(task.get("kind", "cyclic")).lower() not in {"cyclic", "periodic"}:
                self.diagnostics.append(_diagnostic("TASK_KIND", "Event/interrupt task execution is unsupported: " + task["name"]))
            if not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval < .1:
                self.diagnostics.append(_diagnostic("TASK_INTERVAL", "Task cycle time is unresolved or below 100 microseconds: " + task["name"]))
                task["intervalMs"] = None
            else:
                task["nextDueMs"] = float(interval)
            if not task.get("programs"):
                self.diagnostics.append(_diagnostic("TASK_PROGRAMS", "No active programs resolved for task: " + task["name"]))
            self.tasks.append(task)
        self.tasks.sort(key=lambda task: (task.get("priority", 0), str(task["id"])))
        active = set()
        for task in self.tasks:
            for identifier in task.get("programs", []):
                if identifier not in self.units:
                    self.diagnostics.append(_diagnostic("TASK_UNRESOLVED_PROGRAM", "Task references unknown program: " + str(identifier)))
                else:
                    active.add(identifier)
                    if self.units[identifier]["sections"] and all(section["kind"] in {"function", "function_block"} for section in self.units[identifier]["sections"]):
                        self.diagnostics.append(_diagnostic("TASK_NON_PROGRAM", "A function/FB cannot be a cyclic program assignment: " + str(identifier), self.units[identifier]["source"]))
            self.initializers.extend(task.get("initializationPrograms", []))
            self.exits.extend(task.get("exitPrograms", []))
        active_scopes = {self.units[key]["scope"] for key in active}
        for identifier, unit in self.units.items():
            if unit["scope"] in active_scopes:
                if unit.get("entry") == "init": self.initializers.append(identifier)
                if unit.get("entry") == "exit": self.exits.append(identifier)
        self.initializers = list(dict.fromkeys(self.initializers + self.project.get("initializationPrograms", [])))
        self.exits = list(dict.fromkeys(self.exits + self.project.get("exitPrograms", [])))
        for identifier in self.initializers + self.exits:
            if identifier not in self.units:
                self.diagnostics.append(_diagnostic("LIFECYCLE_PROGRAM", "Unresolved lifecycle program: " + str(identifier)))
            else:
                active.add(identifier)
        if not self.tasks:
            self.diagnostics.append(_diagnostic("TASK_CONFIGURATION", "No active cyclic task configuration was resolved; execution is unavailable."))
        visited = set()
        for identifier in list(active):
            self._validate_unit(identifier, visited)
        for identifier, unit in self.units.items():
            if identifier not in visited:
                for diagnostic in unit["compiled"]["diagnostics"]:
                    self.diagnostics.append({**diagnostic, "severity": "warning", "excluded": True,
                                             "message": "Inactive source: " + diagnostic["message"]})
        self.active_units = visited
        self.execution_order = list(dict.fromkeys(self.initializers + [identity for task in self.tasks for identity in task.get("programs", [])] + self.exits))
        self.run_allowed = not any(diagnostic.get("severity") == "error" for diagnostic in self.diagnostics)
        if self.project.get("compatibility", {}).get("runAllowed") is False:
            self.run_allowed = False
            self.diagnostics.append(_diagnostic("PROJECT_INCOMPATIBLE", "Project analysis reported unresolved active dependencies."))
        self.diagnostic_count = len(self.diagnostics)
        if len(self.diagnostics) > 2000:
            self.diagnostics = ([item for item in self.diagnostics if item.get("severity") == "error"] +
                                [item for item in self.diagnostics if item.get("severity") != "error"])[:2000]
        self.quantum_ms = min((float(task["intervalMs"]) for task in self.tasks if task.get("intervalMs")), default=10.0)
        # Microsecond integer GCD preserves configured task phase/order without
        # inventing execution timing for different cyclic classes.
        intervals = [max(100, round(float(task["intervalMs"])*1000)) for task in self.tasks if task.get("intervalMs")]
        if intervals:
            self.quantum_ms = reduce(math.gcd, intervals)/1000.0
        self._event("loaded", f"Loaded {len(self.units)} executable resources; " + ("ready" if self.run_allowed else "execution blocked"))

    def _validate_unit(self, identifier, visited):
        if identifier in visited:
            return
        visited.add(identifier)
        unit = self.units[identifier]
        self.diagnostics.extend(deepcopy(unit["compiled"]["diagnostics"]))
        if not unit["sections"] and not unit["compiled"]["diagnostics"]:
            self.diagnostics.append(_diagnostic("EMPTY_ACTIVE_PROGRAM", "Active program has no executable section", unit["source"]))
        for section in unit["sections"]:
            formals={self.symbol_key(d['name']):d for d in unit['compiled'].get('declarations',[]) if self.symbol_key(d.get('scope',''))==self.symbol_key(section['name'])}
            for statement in walk_ir(section.get('instructions',[])):
                if statement.get('op')!='reference_statement':continue
                ref=statement.get('expression',{})
                if ref.get('op')!='ref' or ref.get('path'):continue
                name=ref['name']
                try:spec=self.memory.spec(formals[self.symbol_key(name)]['type'] if self.symbol_key(name) in formals else self.memory.resolve(name,unit['scope'])['type'])
                except ValueError:spec={}
                if spec.get('kind')=='block' or spec.get('functionBlock') or spec.get('cpuBlock') or spec.get('serviceBlock') or spec.get('libraryBlock') or (unit['scope'].casefold(),self.symbol_key(name)) in self.actions:
                    statement['op']='call';statement['expression']={**ref,'op':'call','args':[]}
            local = {self.symbol_key(item["name"]): item for item in unit["compiled"].get("declarations", [])
                     if self.symbol_key(item.get("scope", "")) == self.symbol_key(section["name"])}
            if section.get("returnType"):
                local[self.symbol_key(section["name"])] = {"name": section["name"], "type": section["returnType"]}
            for node in walk_ir(section.get("instructions", [])):
                if node["op"] == "ref":
                    name = node["name"]
                    if self.symbol_key(name) in self.enum_constants:
                        if self.enum_constants[self.symbol_key(name)] is None:
                            self.diagnostics.append(_diagnostic("ENUM_AMBIGUOUS", "Ambiguous enumeration member requires a type qualifier: " + name,
                                                                 unit["source"], node.get("line", section.get("line"))))
                        continue
                    try:
                        if self.symbol_key(name) in local:
                            specification = self.memory.spec(local[self.symbol_key(name)]["type"])
                        else:
                            record = self.memory.resolve(name, unit["scope"])
                            if record.get("ambiguous"):
                                raise MemoryErrorPLC("Conflicting declarations make variable ambiguous: " + name)
                            specification = record["_spec"]
                        if specification.get("kind") == "unresolved":
                            raise MemoryErrorPLC("Active variable has unresolved type: " + name + ": " + specification.get("message", ""))
                        self.memory.reference_spec(node, unit["scope"], specification)
                    except (ValueError, KeyError, TypeError) as error:
                        self.diagnostics.append(_diagnostic("UNRESOLVED_SYMBOL", str(error), unit["source"], node.get("line", section.get("line")), program=unit.get("name", identifier)))
                elif node["op"] == "call":
                    # Statement wrapper uses expression; expression node owns name.
                    if "name" not in node:
                        continue
                    self._validate_call(node, unit, local, visited, section)
                elif node["op"] == "ladder":
                    for cell in node["network"].get("cells", []):
                        if cell.get("kind") in {"contact", "coil"}:
                            try:
                                reference = cell["expression"]
                                specification = {"kind": "scalar", "type": "BOOL"} if reference.get("op") == "literal" else self.memory.reference_spec(reference, unit["scope"])
                                if specification.get("kind") != "scalar" or specification.get("type") != "BOOL":
                                    raise MemoryErrorPLC("Ladder contact/coil requires BOOL: " + cell["name"])
                                for index_reference in walk_ir(reference):
                                    if index_reference is not reference and index_reference.get("op") == "ref":
                                        self.memory.reference_spec(index_reference, unit["scope"])
                            except ValueError as error:
                                self.diagnostics.append(_diagnostic("LADDER_SYMBOL", str(error), unit["source"], cell.get("sourceLine", node["line"])))
                    if node.get('plan'):
                        from .ladder_dataflow import validate_plan
                        validate_plan(self,node,unit,local,visited,section)
                    block = node.get("block")
                    if block:
                        try:
                            specification = self.memory.reference_spec({"name": block["instance"], "path": []}, unit["scope"])
                            if specification.get("kind") != "block" or specification.get("type") != block["type"]:
                                raise MemoryErrorPLC("Ladder block instance/type differs: " + block["instance"] + ": expected " + block["type"])
                        except ValueError as error:
                            self.diagnostics.append(_diagnostic("LADDER_BLOCK_INSTANCE", str(error), unit["source"], block["line"]))

    def _validate_call(self, node, unit, local, visited, section=None):
        if node.get('instance'):
            ref=node['instance']
            try:
                typename=self._reference_type(ref,unit['scope'],local=local)
                self._validate_call({k:v for k,v in node.items() if k!='instance'},unit,{**local,self.symbol_key(node['name']):{'type':typename}},visited,section)
            except ValueError as error:self.diagnostics.append(_diagnostic('CALL_INSTANCE',str(error),unit['source'],node.get('line')))
            return
        if unit.get('language')=='c':self._c_block_call(node,unit['scope'],local=local)
        name = node["name"]
        upper = name.upper()
        actions=self.actions.get((unit['scope'].casefold(),self.symbol_key(name)),[])
        if actions:
            if len(actions)!=1 or node['args']:
                self.diagnostics.append(_diagnostic('ACTION_INTERFACE','An ACTION requires one same-program definition and no arguments: '+name,unit['source'],node.get('line')))
            else:self._validate_unit(actions[0]['unitId'],visited)
            return
        vendor_name = call_name(upper)
        if vendor_name in VENDOR_CALLS:
            low, high = VENDOR_CALLS[vendor_name]
            if not low <= len(node['args']) <= high or any(arg.get('name') or arg.get('output') for arg in node['args']):
                self.diagnostics.append(_diagnostic('LIBRARY_INTERFACE', name + ' requires ' + str(low) + ' positional inputs', unit['source'], node.get('line')))
            if vendor_name in {'ADR', 'SIZEOF'} and len(node['args']) == 1:
                argument = node['args'][0]['value']
                if argument.get('op') not in {'ref', 'literal'} or (argument.get('op') == 'literal' and not isinstance(argument.get('value'), str)):
                    self.diagnostics.append(_diagnostic('VIRTUAL_POINTER', name + ' requires a declared value or string literal', unit['source'], node.get('line')))
                try:
                    name_key = self.symbol_key(argument.get('name', ''))
                    if name_key in local:
                        spec = self.memory.reference_spec(argument, unit['scope'], self.memory.spec(local[name_key]['type']))
                    else:
                        spec = self.vendor.specification(argument, unit['scope'])
                    self.vendor.size(spec)
                except (ValueError, KeyError, TypeError) as error:
                    self.diagnostics.append(_diagnostic('VIRTUAL_POINTER_LAYOUT', str(error), unit['source'], node.get('line')))
            return
        if upper in CPU_CALLS:
            low,high=CPU_CALLS[upper]
            if not low<=len(node['args'])<=high or any(a.get('name') or a.get('output') for a in node['args']):
                self.diagnostics.append(_diagnostic('CPU_INTERFACE',name+' requires positional inputs',unit['source'],node.get('line')))
            return
        if upper in SERVICE_CALLS:
            low,high=SERVICE_CALLS[upper]
            if not low<=len(node['args'])<=high or any(a.get('name') or a.get('output') for a in node['args']):
                self.diagnostics.append(_diagnostic('SERVICE_INTERFACE',name+' requires positional inputs',unit['source'],node.get('line')))
            return
        if upper in STATEFUL_CALLS:
            if len(node["args"]) != 1 or any(arg.get("name") or arg.get("output") for arg in node["args"]):
                self.diagnostics.append(_diagnostic("EDGE_INTERFACE", upper + " requires one positional BOOL input", unit["source"], node.get("line")))
            # B&R hidden state inside user functions / FBs needs instance and
            # recursion semantics beyond program-local edge storage. Do not
            # silently share that memory between independently called instances.
            return
        if upper in BUILTINS or re.fullmatch(r"(?:BOOL|S?INT|USINT|UINT|DINT|UDINT|REAL|LREAL|TIME|DT|DATE_AND_TIME|BYTE|WORD|DWORD)_TO_(?:BOOL|S?INT|USINT|UINT|DINT|UDINT|REAL|LREAL|TIME|BYTE|WORD|DWORD|STRING)", upper):
            if upper in {"ROL", "ROR"}:
                self.diagnostics.append(_diagnostic("LIBRARY_WIDTH", "Rotate requires a typed width and is unsupported", unit["source"], node.get("line")))
            if any(arg.get("name") or arg.get("output") for arg in node["args"]):
                self.diagnostics.append(_diagnostic("BUILTIN_INTERFACE", "Builtin functions currently require positional input arguments", unit["source"], node.get("line")))
            return
        try:
            typename = local[self.symbol_key(name)]["type"] if self.symbol_key(name) in local else self.memory.resolve(name, unit["scope"])["type"]
            spec = self.memory.spec(typename)
        except (ValueError, KeyError):
            typename, spec = None, None
        if typename is not None and node.get('expectedType') and self.symbol_key(typename) != self.symbol_key(node['expectedType']):
            self.diagnostics.append(_diagnostic('FUB_TYPE', f'{name} FUB {node["expectedType"]} differs from its declared type {typename}.', unit['source'], node.get('line')))
        if spec and spec.get('serviceBlock') in SERVICE_BLOCKS:
            kind=spec['serviceBlock'];inputs,outputs=SERVICE_BLOCKS[kind];seen=set()
            for arg in node['args']:
                key=arg.get('name');allowed=outputs if arg.get('output') else inputs
                if key not in allowed or key in seen or (arg.get('output') and arg['value'].get('op')!='ref'):
                    self.diagnostics.append(_diagnostic('SERVICE_INTERFACE','Invalid '+kind+' argument: '+str(key),unit['source'],node.get('line')))
                seen.add(key)
            return
        if spec and spec.get('cpuBlock') in CPU_BLOCKS:
            kind=spec['cpuBlock'];inputs,outputs=CPU_BLOCKS[kind];seen=set()
            if self.symbol_key(name) in local and kind.startswith('Cfg'):
                self.diagnostics.append(_diagnostic('CPU_FRAME','Asynchronous CPU configuration blocks need declared program instances.',unit['source'],node.get('line')))
            for arg in node['args']:
                key=arg.get('name');allowed=outputs if arg.get('output') else inputs
                if key not in allowed or key in seen or (arg.get('output') and arg['value'].get('op')!='ref'):
                    self.diagnostics.append(_diagnostic('CPU_INTERFACE','Invalid '+kind+' argument: '+str(key),unit['source'],node.get('line')))
                seen.add(key)
            return
        if spec and spec.get('libraryBlock') in FILE_BLOCKS:
            if self.symbol_key(name) in local:
                self.diagnostics.append(_diagnostic('VIRTUAL_FILEIO_FRAME', 'FileIO instances in callable-local frames are unsupported', unit['source'], node.get('line')))
            inputs, outputs = FILE_BLOCKS[spec['libraryBlock']]
            seen = set()
            for arg in node['args']:
                key = str(arg.get('name', '')).casefold()
                allowed = outputs if arg.get('output') else inputs
                if key not in {name.casefold() for name in allowed} or key in seen or (arg.get('output') and arg['value'].get('op') != 'ref'):
                    self.diagnostics.append(_diagnostic('LIBRARY_INTERFACE', 'Invalid ' + spec['libraryBlock'] + ' argument: ' + str(arg.get('name')), unit['source'], node.get('line')))
                seen.add(key)
            return
        if spec and spec.get("kind") == "block":
            kind = spec["type"]
            seen = set()
            for arg in node["args"]:
                canonical = block_member(kind, arg.get("name", ""))
                if (arg.get("name") is None or canonical not in (BLOCK_OUTPUTS[kind] if arg.get("output") else BLOCK_INPUTS[kind])
                        or canonical in seen or (arg.get("output") and arg["value"].get("op") != "ref")):
                    self.diagnostics.append(_diagnostic("BLOCK_INTERFACE", f"Unsupported {kind} argument: {arg.get('name')}", unit["source"], node.get("line")))
                seen.add(canonical)
            return
        callable_name = self.symbol_key(str(typename or name))
        choices = self.callables.get(callable_name, []) or self.callables.get(self.symbol_key(name), [])
        if len(choices) != 1:
            self.diagnostics.append(_diagnostic("UNSUPPORTED_CALL", "Unresolved or ambiguous function/library call: " + name,
                                                 unit["source"], node.get("line")))
            return
        target = choices[0]
        declarations = [item for item in self.units[target["unitId"]]["compiled"]["declarations"]
                        if self.symbol_key(item.get("scope", "")) == self.symbol_key(target["name"])]
        inputs = [item for item in declarations if item.get("mode") in {"VAR_INPUT", "VAR_IN_OUT"}]
        names, positional = set(), 0
        for arg in node["args"]:
            declaration = next((item for item in declarations if self.symbol_key(item["name"]) == self.symbol_key(str(arg.get("name", "")))), None) if arg.get("name") else inputs[positional] if positional < len(inputs) else None
            if not arg.get("name"): positional += 1
            invalid = not declaration
            if declaration:
                mode = declaration.get("mode")
                invalid = (self.symbol_key(declaration["name"]) in names or
                           (arg.get("output") and (mode not in {"VAR_OUTPUT", "VAR_IN_OUT"} or arg["value"].get("op") != "ref")) or
                           (not arg.get("output") and mode not in {"VAR_INPUT", "VAR_IN_OUT"}) or
                           (mode == "VAR_IN_OUT" and arg["value"].get("op") != "ref"))
                names.add(self.symbol_key(declaration["name"]))
            if invalid:
                self.diagnostics.append(_diagnostic("CALL_INTERFACE", "Unknown, duplicate, excess or incorrectly mapped argument to " + name,
                                                     unit["source"], node.get("line")))
        if target["kind"] == "function":
            for declaration in inputs:
                if self.symbol_key(declaration["name"]) not in names and not declaration.get("initialExpression"):
                    self.diagnostics.append(_diagnostic("FUNCTION_INPUT", "Missing required input " + declaration["name"] + " to " + name,
                                                         unit["source"], node.get("line")))
        self._validate_unit(target["unitId"], visited)

    def _event(self, kind, message, node=None, **extra):
        self._sequence += 1
        self.trace.append({"sequence": self._sequence, "timeMs": self.time_ms, "kind": kind, "message": str(message)[:2000],
                           "task": self._context.get("task"), "program": self._context.get("program"),
                           "source": (node or {}).get("source", self._context.get("source", "")),
                           "line": (node or {}).get("line", 0), **{key: _preview(value) for key, value in extra.items()}})

    def _consume(self):
        self._budget -= 1
        if self._budget < 0:
            raise RuntimeErrorPLC("Per-scan instruction budget exceeded; simulation halted")

    def _pointer_reference(self, reference, scope, frame=None):
        """Resolve a typed C dereference within allocated virtual memory only."""
        if not reference.get('path'):return None
        name=self.symbol_key(reference['name'])
        if frame and name in frame['values']:
            value,spec=frame['values'][name],frame['specs'][name]
        else:
            record=self.memory.resolve(reference['name'],scope)
            value,spec=record['value'],record['_spec']
        address=None
        for segment in reference['path']:
            if spec.get('pointsTo') and ('index' in segment or segment.get('dereference')):
                if address is not None:value=self.vendor.decode(self.vendor.read(address,self.vendor.size(spec)),spec)
                index=0 if segment.get('dereference') else self._eval(segment['index'],scope,frame)
                if type(index) is not int or type(value) is not int:raise RuntimeErrorPLC('Pointer index and address must be integers')
                spec=self.memory.spec(spec['pointsTo'])
                address=value+index*self.vendor.size(spec)
                self.vendor.region(address,self.vendor.size(spec))
            elif address is None:
                value,spec=self.memory.member(value,spec,[segment],lambda e:self._eval(e,scope,frame))
            elif 'member' in segment:
                offset,spec=self.vendor.field_offset(spec,segment['member']);address+=offset
            elif 'index' in segment:
                low,count,nested=self.vendor.array(spec);index=self._eval(segment['index'],scope,frame)
                if type(index) is not int or not low<=index<low+count:raise RuntimeErrorPLC('Pointer array member index is out of bounds')
                address+=(index-low)*self.vendor.size(nested);spec=nested
            else:raise RuntimeErrorPLC('Unsupported pointer path')
        return (address,spec) if address is not None else None

    def _read(self, reference, scope, frame=None):
        alias=self._access_bindings.get(((frame or {}).get('instance_path',scope),self.symbol_key(reference['name'])))
        if alias is not None:
            spec=self.vendor.specification(reference,scope,frame)
            if reference.get('path'):raise RuntimeErrorPLC('ACCESS aggregate member alias requires an explicit pointer')
            return self.vendor.decode(self.vendor.read(alias,self.vendor.size(spec)),spec)
        if self.symbol_key(reference["name"]) in self.enum_constants and not reference.get("path"):
            value = self.enum_constants[self.symbol_key(reference["name"])]
            if value is None: raise RuntimeErrorPLC("Ambiguous enumeration member: " + reference["name"])
            return value
        pointer=self._pointer_reference(reference,scope,frame)
        if pointer:return self.vendor.decode(self.vendor.read(pointer[0],self.vendor.size(pointer[1])),pointer[1])
        name = self.symbol_key(reference["name"])
        if frame and name in frame["values"]:
            return self.memory.member(frame["values"][name], frame["specs"][name], reference.get("path", []),
                                      lambda expression: self._eval(expression, scope, frame))[0]
        return self.memory.read(reference, scope, lambda expression: self._eval(expression, scope, frame))

    def _write(self, reference, value, scope, frame=None, force=False):
        alias=self._access_bindings.get(((frame or {}).get('instance_path',scope),self.symbol_key(reference['name'])))
        if alias is not None:
            spec=self.vendor.specification(reference,scope,frame)
            if reference.get('path'):raise RuntimeErrorPLC('ACCESS aggregate member alias requires an explicit pointer')
            self.vendor.write(alias,self.vendor.encode(self.memory.coerce(value,spec),spec));return
        if reference.get('path') and 'bit' in reference['path'][-1]:
            parent={**reference,'path':reference['path'][:-1]};bit=reference['path'][-1]['bit']
            self.memory.reference_spec(reference,scope,frame['specs'].get(self.symbol_key(reference['name'])) if frame else None)
            current=int(self._read(parent,scope,frame));converted=current|(1<<bit) if self.memory.coerce(value,{'kind':'scalar','type':'BOOL'}) else current&~(1<<bit)
            spec=self.vendor.specification(parent,scope,frame);bounds=INTEGER_TYPES[spec['type']]
            if converted>bounds[1]:converted-=bounds[1]-bounds[0]+1
            return self._write(parent,converted,scope,frame,force)
        pointer=self._pointer_reference(reference,scope,frame)
        if pointer:
            self.vendor.write(pointer[0],self.vendor.encode(self.memory.coerce(value,pointer[1]),pointer[1]));return
        name = self.symbol_key(reference["name"])
        if frame and name in frame["values"]:
            path = reference.get("path", [])
            _, specification = self.memory.member(frame["values"][name], frame["specs"][name], path,
                                                   lambda expression: self._eval(expression, scope, frame))
            converted = self.memory.coerce(value, specification)
            if path:
                parent, parent_spec = self.memory.member(frame["values"][name], frame["specs"][name], path[:-1], lambda expression: self._eval(expression, scope, frame))
                final = path[-1]
                if "member" in final:
                    requested = block_member(parent_spec["type"], final["member"]) if parent_spec.get("kind") == "block" else final["member"]
                    key = next(key for key in parent if self.symbol_key(key) == self.symbol_key(requested))
                    parent[key] = converted
                else:
                    bounds = parent_spec["bounds"]
                    low = bounds[0][0] if isinstance(bounds[0], (list, tuple)) else bounds[0]
                    parent[int(self._eval(final["index"], scope, frame))-int(low)] = converted
            else:
                frame["values"][name] = converted
            return
        change = self.memory.write(reference, value, scope, lambda expression: self._eval(expression, scope, frame), self.time_ms, force)
        if change:
            self._event("variable", change["name"] + " changed", changes=[change])
            history = self.signal_history.setdefault(change["id"], deque(maxlen=MAX_SIGNAL_HISTORY))
            if len(history) < MAX_SIGNAL_HISTORY: self._signal_history_count += 1
            history.append({"timeMs": self.time_ms, "value": _preview(change["value"])})
            while self._signal_history_count > MAX_TOTAL_SIGNAL_HISTORY:
                oldest_id = next(iter(self.signal_history))
                oldest = self.signal_history[oldest_id]
                oldest.popleft()
                self._signal_history_count -= 1
                if not oldest: self.signal_history.pop(oldest_id)

    def _eval(self, expression, scope, frame=None):
        self._consume()
        operation = expression["op"]
        if operation == "literal": return expression["value"]
        if operation == "ref": return self._read(expression, scope, frame)
        if operation == "call": return self._call(expression, scope, frame)
        if operation=='conditional':return self._eval(expression['yes'] if self._eval(expression['condition'],scope,frame) else expression['no'],scope,frame)
        if operation=='sizeof_type':return self.vendor.size(self.memory.spec(expression['type']+'*'*expression.get('pointers',0)))
        if operation=='cast':
            child=expression['value'];typename=expression['type']+'*'*expression.get('pointers',0)
            spec=self.memory.spec(typename)
            if child.get('op')=='ref' and (spec.get('pointsTo') or typename.upper() in {'UDINT','DWORD'}):
                original=self.vendor.specification(child,scope,frame)
                value=self.vendor.address(child,scope,frame) if original.get('kind') in {'string','array'} else self._eval(child,scope,frame)
            else:value=self._eval(child,scope,frame)
            kind=spec.get('type','').upper()
            if kind in INTEGER_TYPES:
                if not isinstance(value,(bool,int,float)) or not math.isfinite(value):raise RuntimeErrorPLC('C integer cast requires a finite number')
                low,high=INTEGER_TYPES[kind];modulus=high-low+1;converted=int(value)%modulus
                return converted-modulus if low<0 and converted>high else converted
            return self.memory.coerce(value,spec)
        if operation == "unary":
            value = self._eval(expression["value"], scope, frame)
            operator = expression["operator"]
            if operator in {"NOT", "!"}:
                if isinstance(value, bool) or operator == "!": return not value
                child = expression["value"]
                if child.get("op") == "ref":
                    local = frame and frame["specs"].get(self.symbol_key(child["name"]))
                    spec = self.memory.reference_spec(child, scope, local)
                    bounds = INTEGER_TYPES.get(spec.get("type", "").upper())
                    if bounds:
                        low, high = bounds
                        modulus = high - low + 1
                        result = ~int(value) & (modulus - 1)
                        return result - modulus if low < 0 and result > high else result
                return ~int(value)
            if operator == "~": return ~int(value)
            if operator == "+": return +value
            return -value
        if operation == "binary":
            operator = expression["operator"]
            left = self._eval(expression["left"], scope, frame)
            # C short circuit semantics are explicit; IEC operators evaluate both sides.
            if operator == "&&" and not left: return False
            if operator == "||" and left: return True
            right = self._eval(expression["right"], scope, frame)
            if operator in {"=", "=="}: return left == right
            if operator in {"<>", "!="}: return left != right
            if operator == "<": return left < right
            if operator == ">": return left > right
            if operator == "<=": return left <= right
            if operator == ">=": return left >= right
            if operator in {"AND", "&"}: return left & right
            if operator in {"OR", "|"}: return left | right
            if operator in {"XOR", "^"}: return left ^ right
            if operator == "&&": return bool(left and right)
            if operator == "||": return bool(left or right)
            if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                raise RuntimeErrorPLC("Arithmetic operands must be numeric; string operations require a supported string library")
            if operator == "+": return left + right
            if operator == "-": return left - right
            if operator == "*": return left * right
            if operator == "/":
                if not right: raise RuntimeErrorPLC("Division by zero")
                return math.trunc(left/right) if isinstance(left, int) and isinstance(right, int) else left/right
            if operator in {"MOD", "%"}:
                if not right: raise RuntimeErrorPLC("Division by zero")
                return left-math.trunc(left/right)*right
            if operator == "**":
                if abs(right) > 128 or abs(left) > 1e12: raise RuntimeErrorPLC("Exponentiation operand limit exceeded")
                result = left ** right
                if isinstance(result, complex) or not math.isfinite(result): raise RuntimeErrorPLC("Non-finite exponentiation")
                return result
            if operator in {"<<", ">>"}:
                if not 0 <= right <= 63: raise RuntimeErrorPLC("Shift exceeds 0..63 bit bound")
                return int(left) << int(right) if operator == "<<" else int(left) >> int(right)
        raise RuntimeErrorPLC("Unsupported IR expression: " + operation)

    def _call(self, expression, scope, frame=None):
        self._call_depth += 1
        if self._call_depth > MAX_CALL_DEPTH:
            self._call_depth -= 1
            raise RuntimeErrorPLC("Function call depth limit exceeded")
        try:
            return self._call_inner(expression, scope, frame)
        finally:
            self._call_depth -= 1

    def _reference_type(self,ref,scope,frame=None,local=None):
        key=self.symbol_key(ref['name'])
        typename=(local or {}).get(key,{}).get('type')
        if not typename:typename=frame['types'][key] if frame and key in frame['types'] else self.memory.resolve(ref['name'],scope)['type']
        spec=self.memory.spec(typename)
        for part in ref.get('path',[]):
            if 'member' in part:
                field=next((f for f in self.memory.fields(spec) if self.symbol_key(f['name'])==self.symbol_key(part['member'])),None)
                if not field:raise MemoryErrorPLC('Unknown nested FB member: '+part['member'])
                typename=field['type'];spec=self.memory.spec(typename)
            elif 'index' in part:
                _,_,spec=self.vendor.array(spec);typename=spec.get('type') or next((k for k,v in self.memory.types.items() if v==spec),None)
            else:raise MemoryErrorPLC('Unsupported FB instance path')
        return typename

    def _c_block_call(self,expression,scope,frame=None,local=None):
        """C library ABI Type(&instance) maps to the same declared virtual FB."""
        args=expression.get('args',[])
        if len(args)!=1:return
        pointer=args[0].get('value',{})
        if pointer.get('op')!='call' or pointer.get('name','').upper()!='ADR' or len(pointer.get('args',[]))!=1:return
        ref=pointer['args'][0]['value']
        if ref.get('op')!='ref' or ref.get('path'):return
        try:
            expected=self.memory.spec(expression['name']);key=self.symbol_key(ref['name'])
            typename=(local or {}).get(key,{}).get('type')
            if not typename:typename=frame['types'][key] if frame and key in frame['types'] else self.memory.resolve(ref['name'],scope)['type']
            actual=self.memory.spec(typename)
            for marker in ('serviceBlock','cpuBlock','libraryBlock'):
                if expected.get(marker) and expected[marker]==actual.get(marker):
                    expression.update(name=ref['name'],args=[]);return
        except ValueError:return

    def _call_inner(self, expression, scope, frame):
        if expression.get('instance'):
            ref=expression['instance'];name=expression['name'];key=self.symbol_key(name)
            typename=self._reference_type(ref,scope,frame);spec=self.memory.spec(typename)
            nested={'values':{key:self._read(ref,scope,frame)},'specs':{key:spec},'types':{key:typename},'instance_path':(frame or {}).get('instance_path',scope)+'::'+repr(ref),'backing':{'reference':ref,'scope':scope,'frame':frame,'whole':True},'active':True}
            result=self._call_inner({k:v for k,v in expression.items() if k!='instance'},scope,nested)
            self._write(ref,nested['values'][key],scope,frame);return result
        if self.units.get(self._context.get('unitId'),{}).get('language')=='c':self._c_block_call(expression,scope,frame)
        name, args = expression["name"], expression["args"]
        upper = name.upper()
        actions=self.actions.get((scope.casefold(),self.symbol_key(name)),[])
        if actions:
            if len(actions)!=1 or args:raise RuntimeErrorPLC('Invalid ACTION invocation: '+name)
            action=actions[0]
            for _ in self._execute_section(action['instructions'],scope,frame):pass
            return None
        if call_name(upper) in VENDOR_CALLS:
            language = self.units.get(self._context.get('unitId'), {}).get('language', 'st')
            return self.vendor.call(upper, args, scope, frame, language)
        if upper in CPU_CALLS:return self.cpu.call(upper,args,scope,frame)
        if upper in SERVICE_CALLS:return self.services.call(upper,args,scope,frame)
        if upper in STATEFUL_CALLS:
            if len(args) != 1 or any(arg.get("name") or arg.get("output") for arg in args):
                raise RuntimeErrorPLC(upper + " requires one positional BOOL input in a program section")
            value = self._eval(args[0]["value"], scope, frame)
            if value not in (True, False, 0, 1):
                raise RuntimeErrorPLC(upper + " input must be BOOL")
            key = (self._context.get("unitId"), expression.get("source", self._context.get("source", "")), (frame or {}).get('instance_path',scope),
                   expression.get("site"), upper)
            if key not in self._edge_memory and len(self._edge_memory) >= MAX_EDGE_STATES:
                raise RuntimeErrorPLC("Edge operator state limit exceeded")
            previous = self._edge_memory.get(key, False)
            current = bool(value)
            self._edge_memory[key] = current
            return current and not previous if upper == "EDGEPOS" else previous and not current
        if upper in BUILTINS or "_TO_" in upper:
            if any(arg.get("output") for arg in args):
                raise RuntimeErrorPLC("Builtin functions do not expose mapped outputs")
            return builtin(name, [self._eval(arg["value"], scope, frame) for arg in args])
        if frame and self.symbol_key(name) in frame["values"]:
            value = frame["values"][self.symbol_key(name)]
            typename = frame["types"][self.symbol_key(name)]
        else:
            try:
                typename = self.memory.resolve(name, scope)["type"]
                value = self._read({"op": "ref", "name": name, "path": []}, scope, frame)
            except MemoryErrorPLC:typename, value = None, None
        block_spec = self.memory.spec(typename) if typename else None
        if block_spec and block_spec.get('serviceBlock') in SERVICE_BLOCKS:
            kind=block_spec['serviceBlock'];block=deepcopy(value)
            for arg in args:
                if not arg.get('output'):
                    member=arg['name']
                    spec=self.memory.reference_spec({'name':name,'path':[{'member':member}]},scope,block_spec)
                    block[member]=self.memory.coerce(self._eval(arg['value'],scope,frame),spec)
            if frame and self.symbol_key(name) in frame['values']:key=frame.get('instance_path',scope)+'::'+name
            else:
                record=self.memory.resolve(name,scope);key=record['id']
                if record.get('forced'):return block.get('status')
            result=self.services.block(kind,key,block)
            self._write({'op':'ref','name':name,'path':[]},result,scope,frame)
            for arg in args:
                if arg.get('output'):self._write(arg['value'],result[arg['name']],scope,frame)
            self._event('virtual-service',name+' ('+kind+')',expression)
            return result.get('status',0)
        if block_spec and block_spec.get('cpuBlock') in CPU_BLOCKS:
            kind=block_spec['cpuBlock'];block=deepcopy(value)
            for arg in args:
                if not arg.get('output'):
                    member=arg['name']
                    spec=self.memory.reference_spec({'name':name,'path':[{'member':member}]},scope,block_spec)
                    block[member]=self.memory.coerce(self._eval(arg['value'],scope,frame),spec)
            if frame and self.symbol_key(name) in frame['values']:key=frame.get('instance_path',scope)+'::'+name
            else:
                record=self.memory.resolve(name,scope);key=record['id']
                if record.get('forced'):return block.get('status')
            result=self.cpu.block(kind,key,block)
            self._write({'op':'ref','name':name,'path':[]},result,scope,frame)
            for arg in args:
                if arg.get('output'):self._write(arg['value'],result[arg['name']],scope,frame)
            self._event('virtual-cpu',name+' ('+kind+')',expression)
            return result.get('status',0)
        if block_spec and block_spec.get('libraryBlock') in FILE_BLOCKS:
            kind = block_spec['libraryBlock']
            block = deepcopy(value)
            fields = {key.casefold(): key for key in block}
            for arg in args:
                if not arg.get('output'):
                    field = fields[str(arg.get('name', '')).casefold()]
                    field_spec = self.memory.reference_spec({'name': name, 'path': [{'member': field}]}, scope)
                    block[field] = self.memory.coerce(self._eval(arg['value'], scope, frame), field_spec)
            record = self.memory.resolve(name, scope)
            if record.get('forced'): return block.get('status')
            result = self.vendor.file_block(kind, record['id'], block)
            self._write({'op': 'ref', 'name': name, 'path': []}, result, scope, frame)
            for arg in args:
                if arg.get('output'):
                    self._write(arg['value'], result[fields[str(arg['name']).casefold()]], scope, frame)
            self._event('virtual-fileio', name + ': status ' + str(result['status']), expression)
            return result['status']
        if block_spec and block_spec.get("kind") == "block":
            kind = block_spec["type"]
            inputs = {arg["name"].upper(): self._eval(arg["value"], scope, frame) for arg in args if not arg.get("output") and arg.get("name")}
            # Work on a copy so failed execution does not partially corrupt an instance.
            block = deepcopy(value)
            outputs = execute_block(kind, block, inputs, self.time_ms)
            self._write({"op": "ref", "name": name, "path": []}, block, scope, frame)
            for arg in args:
                if arg.get("output"):
                    self._write(arg["value"], outputs[arg["name"].upper()], scope, frame)
            self._event("function-block", name + " (" + kind + ")", expression, outputs=outputs)
            return outputs.get("Q")
        choices = self.callables.get(self.symbol_key(str(typename or name)), []) or self.callables.get(self.symbol_key(name), [])
        if len(choices) != 1:
            raise RuntimeErrorPLC("Unsupported call: " + name)
        section = choices[0]
        unit = self.units[section["unitId"]]
        declarations = [item for item in unit["compiled"].get("declarations", [])
                        if self.symbol_key(item.get("scope", "")) == self.symbol_key(section["name"])]
        values, specs, type_names = {}, {}, {}
        frame_budget = [MAX_CALL_FRAME_ELEMENTS]
        for declaration in declarations:
            key = self.symbol_key(declaration["name"])
            spec = self.memory.spec(declaration["type"])
            type_names[key], specs[key] = declaration["type"], spec
            stored = next((item for field, item in value.items() if self.symbol_key(field) == key), None) if section["kind"] == "function_block" and isinstance(value, dict) else None
            initial = declaration.get("initialExpression")
            default = self.memory.default(spec, budget=frame_budget)
            values[key] = deepcopy(stored) if stored is not None else self.memory.coerce(initial["value"], spec) if initial and initial.get("op") == "literal" else default
        if section.get("returnType"):
            key = self.symbol_key(section["name"])
            type_names[key], specs[key] = section["returnType"], self.memory.spec(section["returnType"])
            values[key] = self.memory.default(specs[key], budget=frame_budget)
        instance_path=(frame or {}).get('instance_path',scope)+'::'+name if frame else self.memory.resolve(name,scope)['id'] if section['kind']=='function_block' else unit['scope']
        call_frame = {"values": values, "specs": specs, "types": type_names,'instance_path':instance_path,'active':True}
        if section['kind']=='function_block':call_frame['backing']={'reference':{'op':'ref','name':name,'path':[]},'scope':scope,'frame':frame}
        inputs = [item for item in declarations if item.get("mode") in {"VAR_INPUT", "VAR_IN_OUT"}]
        positional = 0
        bindings = []
        for arg in args:
            if arg.get("name"):
                declaration = next((item for item in declarations if self.symbol_key(item["name"]) == self.symbol_key(arg["name"])), None)
            else:
                declaration = inputs[positional] if positional < len(inputs) else None
                positional += 1
            if not declaration:
                raise RuntimeErrorPLC("Unknown/excess argument to " + name + ": " + str(arg.get("name")))
            key = self.symbol_key(declaration["name"])
            if arg.get("output"):
                if declaration.get("mode") not in {"VAR_OUTPUT", "VAR_IN_OUT"} or arg["value"].get("op") != "ref":
                    raise RuntimeErrorPLC("Invalid output binding for " + name)
                bindings.append((arg["value"], key))
            else:
                if declaration.get("mode") not in {"VAR_INPUT", "VAR_IN_OUT"}:
                    raise RuntimeErrorPLC("Argument is not a declared input: " + declaration["name"])
                values[key] = self.memory.coerce(self._eval(arg["value"], scope, frame), specs[key])
                if declaration.get("mode") == "VAR_IN_OUT":
                    if arg["value"].get("op") != "ref": raise RuntimeErrorPLC("VAR_IN_OUT requires a variable")
                    bindings.append((arg["value"], key))
        returned = None
        try:
            for _ in self._execute_section(section["instructions"], unit["scope"], call_frame):
                pass
        except ReturnPLC as result:
            returned = result.value
        if section["kind"] == "function_block":
            stored = {declaration["name"]: values[self.symbol_key(declaration["name"])] for declaration in declarations
                      if declaration.get("mode") != "VAR_TEMP"}
            self._write({"op": "ref", "name": name, "path": []}, stored, scope, frame)
        for reference, key in bindings:
            self._write(reference, values[key], scope, frame)
        call_frame['active']=False
        if returned is not None:
            return self.memory.coerce(returned, self.memory.spec(section["returnType"])) if section.get("returnType") else returned
        return values.get(self.symbol_key(section["name"]))

    def _assign_source(self, target, value, scope, frame=None, expression=None):
        """Apply PLC assignment storage rules, then use the shared checked writer.

        B&R integer assignment stores the destination-width bit pattern (for
        example SINT 200 becomes -56). Keep this separate from external input
        writes, which must reject out-of-range user values.
        """
        spec = self.vendor.specification(target, scope, frame)
        if (spec.get('type') == 'UDINT' and isinstance(value, str)
                and (expression or {}).get('op') == 'literal'):
            value = self.vendor.address(expression, scope, frame)
        if spec.get('kind') == 'string' and isinstance(value, str):
            value = value[:spec.get('length', 80)]
        bounds = INTEGER_TYPES.get(spec.get('type', ''))
        unit=self.units.get(self._context.get('unitId'),{})
        if bounds and type(value) is float and unit.get('language')=='c':
            # C assignment converts a finite floating value to an integer by
            # truncating toward zero. External HMI/input writes stay strict.
            if not math.isfinite(value) or not bounds[0] <= math.trunc(value) <= bounds[1]:
                raise RuntimeErrorPLC('C floating-to-integer assignment exceeds the destination range')
            value=math.trunc(value)
        if bounds and isinstance(value, (int, bool)):
            low, high = bounds
            value = (int(value) - low) % (high - low + 1) + low
        self._write(target, value, scope, frame)

    def _execute_section(self,instructions,scope,frame=None):
        labels={self.symbol_key(n['name']):i for i,n in enumerate(instructions) if n.get('op')=='label'}
        pc=0
        while pc<len(instructions):
            location=instructions[pc]
            try:
                for location in self._execute([instructions[pc]],scope,frame):
                    yield location
                pc+=1
            except JumpPLC as jump:
                label=self.symbol_key(jump.label)
                if label not in labels:raise RuntimeErrorPLC('Unresolved section label: '+jump.label)
                pc=labels[label]
            except (ValueError, ArithmeticError, TypeError, KeyError, IndexError, RecursionError) as error:
                # Actions and source functions execute atomically inside a call.
                # Their yielded instruction never reaches tick(), which still
                # holds the calling statement. Carry the deepest location on
                # this exception before its section unwinds to the caller.
                if not hasattr(error, '_plc_fault_location'):
                    error._plc_fault_location = {key: location[key] for key in ('source', 'line') if key in location}
                raise

    def _execute(self, instructions, scope, frame=None):
        for node in instructions:
            self._consume()
            yield node  # breakpoint boundary before the instruction executes
            operation = node["op"]
            self._event("instruction", operation, node)
            if operation == "assign":
                self._assign_source(node['target'], self._eval(node['value'], scope, frame),
                                    scope, frame, expression=node['value'])
            elif operation == "call":
                self._eval(node["expression"], scope, frame)
            elif operation=='reference_statement':
                self._eval(node['expression'],scope,frame)
            elif operation=='label':
                pass
            elif operation=='goto':
                raise JumpPLC(node['label'])
            elif operation=='access':
                address=self._eval(node['value'],scope,frame);spec=self.vendor.specification(node['target'],scope,frame)
                self.vendor.region(address,self.vendor.size(spec))
                self._access_bindings[((frame or {}).get('instance_path',scope),self.symbol_key(node['target']['name']))]=address
            elif operation == "if":
                body = node.get("else", [])
                for branch in node["cases"]:
                    if self._eval(branch["condition"], scope, frame):
                        body = branch["body"]
                        break
                yield from self._execute(body, scope, frame)
            elif operation == "case":
                selected = self._eval(node["value"], scope, frame)
                body = node.get("else", [])
                for branch in node["cases"]:
                    matches = False
                    for label in branch["labels"]:
                        first = self._eval(label["first"], scope, frame)
                        last = self._eval(label["last"], scope, frame) if label.get("last") else first
                        if first <= selected <= last:
                            matches = True
                            break
                    if matches:
                        body = branch["body"]
                        break
                yield from self._execute(body, scope, frame)
            elif operation=='switch':
                selected=self._eval(node['value'],scope,frame);matched=False
                try:
                    for branch in node['cases']:
                        if matched or any(selected==self._eval(label,scope,frame) for label in branch['labels']):
                            matched=True;yield from self._execute(branch['body'],scope,frame)
                    yield from self._execute(node.get('default',[]),scope,frame)
                except ExitPLC:pass
            elif operation in {"for", "while", "repeat"}:
                count = 0
                if operation == "for":
                    value = self._eval(node["start"], scope, frame)
                    end = self._eval(node["end"], scope, frame)
                    step = self._eval(node["step"], scope, frame)
                    if not step or any(not isinstance(item, (int, float)) or item != int(item) for item in (value, end, step)):
                        raise RuntimeErrorPLC("FOR bounds/step must be integral and step cannot be zero")
                    self._write(node["target"], value, scope, frame)
                while True:
                    if operation == "for":
                        value = self._read(node["target"], scope, frame)
                        if (step > 0 and value > end) or (step < 0 and value < end): break
                    elif operation == "while" and not self._eval(node["condition"], scope, frame):
                        break
                    if count >= MAX_LOOP_ITERATIONS:
                        raise RuntimeErrorPLC("Loop iteration limit exceeded; simulation halted")
                    count += 1
                    self._consume()
                    try:
                        yield from self._execute(node["body"], scope, frame)
                    except ExitPLC:
                        break
                    if operation == "for":
                        next_value=self._read(node["target"], scope, frame)+step
                        if node.get('basicLoop') and ((step>0 and next_value>end) or (step<0 and next_value<end)):break
                        self._write(node["target"], next_value, scope, frame)
                    elif operation == "repeat" and self._eval(node["condition"], scope, frame):
                        break
            elif operation == "sequence":
                yield from self._execute(node["body"], scope, frame)
            elif operation == "exit":
                raise ExitPLC()
            elif operation == "return":
                raise ReturnPLC(self._eval(node["value"], scope, frame) if node.get("value") else None)
            elif operation == "ladder":
                self._ladder(node, scope)
            elif operation=='ladder_program':
                from .ladder_dataflow import execute_program
                yield from execute_program(self,node,scope)
            else:
                raise RuntimeErrorPLC("Unsupported instruction: " + operation)

    def _ladder(self, node, scope):
        if node.get('plan'):
            from .ladder_dataflow import execute_network
            return execute_network(self,node,scope)
        network = node["network"]
        cells = network.get("cells", [])
        # Model each wire boundary as an electrical junction. Branch edges join
        # right boundaries in the existing B&R parser; series cells connect them.
        parents = {}
        def find(key):
            parents.setdefault(key, key)
            if parents[key] != key: parents[key] = find(parents[key])
            return parents[key]
        def union(left, right):
            parents[find(right)] = find(left)
        by_id = {cell["id"]: cell for cell in cells}
        def right(cell): return (cell["row"], cell["column"] + cell.get("span", 1))
        def left(cell): return (cell["row"], cell["column"])
        for cell in cells:
            find(left(cell)); find(right(cell))
            if cell.get("kind") == "line": union(left(cell), right(cell))
        for edge in network.get("connections", []):
            if edge.get("kind") == "branch":
                union(right(by_id[edge["from"]]), right(by_id[edge["to"]]))
        powered = {find((cell["row"], 0)) for cell in cells if cell["column"] == 0 and cell.get("kind") != "empty" and cell.get("position") != "header"}
        contacts = [cell for cell in cells if cell.get("kind") == "contact"]
        coils = [cell for cell in cells if cell.get("kind") == "coil"]
        block = node.get("block")
        graph = {}

        def contact_edges(selected):
            for cell in selected:
                self._consume()
                value = bool(self._eval(cell["expression"], scope))
                kind = cell.get("type", "").upper()
                if kind in {"TRANSITION", "POSITIVE TRANSITION", "NEGATIVE TRANSITION"}:
                    key = (self._context.get("unitId"), node["source"], node.get("line"),
                           node.get("networkNumber"), scope, "ladder-contact", cell["id"])
                    if key not in self._edge_memory and len(self._edge_memory) >= MAX_EDGE_STATES:
                        raise RuntimeErrorPLC("Edge operator state limit exceeded")
                    previous = self._edge_memory.get(key, False)
                    self._edge_memory[key] = value
                    value = value!=previous if kind=='TRANSITION' else value and not previous if kind == "POSITIVE TRANSITION" else previous and not value
                elif kind in {"CLOSED", "NEGATED", "NC"}:
                    value = not value
                if value:
                    graph.setdefault(find(left(cell)), []).append(find(right(cell)))

        def propagate():
            queue, visited = deque(powered), set()
            while queue:
                self._consume()
                junction = queue.popleft()
                if junction in visited:
                    continue
                visited.add(junction)
                for destination in graph.get(junction, []):
                    if destination not in powered:
                        powered.add(destination)
                    if destination not in visited:
                        queue.append(destination)

        contact_edges(cell for cell in contacts if not block or cell["column"] < block["column"])
        propagate()
        if block:
            args = [{"name": item["pin"], "output": False,
                     "value": item["expression"] if "expression" in item else {"op": "literal", "value": find(left(by_id[item["wire"]])) in powered}}
                    for item in block["inputs"]]
            args.extend({"name": item["pin"], "output": True, "value": item["target"]} for item in block["outputs"])
            value = self._call({"op": "call", "name": block["instance"], "args": args, "source": node["source"], "line": block["line"]}, scope)
            if value:
                powered.update(find(right(by_id[identifier])) for identifier in block["booleanOutputs"])
            contact_edges(cell for cell in contacts if cell["column"] >= block["column"]+2)
            propagate()
        for coil in coils:
            self._consume()
            value = find(left(coil)) in powered
            reference = coil["expression"]
            kind = coil.get("type", "").upper()
            if kind == 'RETURN':
                if value: raise ReturnPLC()
                continue
            if kind == "SET":
                if value: self._write(reference, True, scope)
            elif kind == "RESET":
                if value: self._write(reference, False, scope)
            else:
                self._write(reference, not value if kind in {"CLOSED", "NEGATED", "NC"} else value, scope)

    def _program(self, identifier, entry="cyclic"):
        from .lifecycle import section_phase
        unit = self.units[identifier]
        previous = self._context.copy()
        self._context.update(unitId=identifier, program=unit.get("name", identifier), source=unit["source"])
        try:
            for section in unit["sections"]:
                name = section["name"].upper()
                kind = section["kind"]
                if kind in {"function", "function_block", "action"}: continue
                if section_phase(section,unit.get('entry','cyclic')) != entry:continue
                try:
                    yield from self._execute_section(section["instructions"], unit["scope"])
                except ReturnPLC:
                    pass
        finally:
            self._context = previous

    def _scan(self):
        self.cpu.publish_io()
        if not self._initialized:
            for identifier in self.initializers:
                yield from self._program(identifier, "init")
            # Embedded _INIT sections in a combined source also execute once.
            for identifier in self.execution_order:
                if identifier not in self.initializers:
                    yield from self._program(identifier, "init")
            self._initialized = True
        self.time_ms = round(self.time_ms + self.quantum_ms, 9)
        for task in self.tasks:
            if task.get("intervalMs") is None or self.time_ms + 1e-7 < task["nextDueMs"]: continue
            self._context = {"task": task["name"]}
            started = time.perf_counter()
            self._task_timing_interrupted = False
            self._event("task-start", task["name"])
            for identifier in task.get("programs", []):
                yield from self._program(identifier)
            task["executionCount"] += 1
            task["lastExecutionMs"] = self.time_ms
            task["lastWallDurationMs"] = None if self._task_timing_interrupted else round((time.perf_counter()-started)*1000, 5)
            task["nextDueMs"] = round(task["nextDueMs"]+task["intervalMs"], 9)
            self._event("task-end", task["name"], wallDurationMs=task["lastWallDurationMs"])
        self._context = {}
        self.scan_count += 1

    def _fault(self, error, node=None):
        self.status = "faulted"
        self._pending = None
        self._pending_instruction = None
        location = getattr(error, '_plc_fault_location', None) or node or {}
        diagnostic = _diagnostic("RUNTIME_FAULT", str(error), location.get("source", self._context.get("source", "")),
                                 location.get("line", 0))
        self.diagnostics.append(diagnostic)
        # Runtime errors remain bounded even after repeated explicit retries.
        self.diagnostics = self.diagnostics[-2000:]
        self._event("error", str(error), location)

    def request_reset(self,mode):
        if mode not in (1,2,17,18,32,64):raise RuntimeErrorPLC('Unsupported SYSreset mode')
        self._requested_reset=mode
        self._requested_reset_origin=next((dict(row) for row in reversed(self.trace) if row.get('kind')=='instruction'),dict(self._context))

    def tick(self, single_instruction=False):
        if not self.run_allowed:
            raise RuntimeErrorPLC("Execution blocked: review compatibility diagnostics")
        if self.status != "running" and not single_instruction:
            return None
        if self._pending is None:
            self._budget = MAX_INSTRUCTIONS_PER_SCAN
            self._pending = self._scan()
        current = self._pending_instruction
        self._pending_instruction = None
        try:
            while True:
                if current is None:
                    current = next(self._pending)
                key = (current.get("source", ""), int(current.get("line", 0)))
                if key in self.breakpoints and not self._skip_breakpoint:
                    self._pending_instruction = current
                    self.status = "paused"
                    self._task_timing_interrupted = True
                    self._skip_breakpoint = True
                    self._event("breakpoint", "Paused before source instruction", current)
                    break
                self._skip_breakpoint = False
                # Resuming advances the generator past this instruction. A
                # second boundary is retained when executing an instruction step.
                current = next(self._pending)
                if single_instruction:
                    self._pending_instruction = current
                    self.status = "paused"
                    self._task_timing_interrupted = True
                    break
        except StopIteration:
            self._pending = None
            self._pending_instruction = None
            if single_instruction: self.status = "paused"
            if self._requested_reset is not None:
                mode,self._requested_reset=self._requested_reset,None
                origin=getattr(self,'_requested_reset_origin',{})
                self._event('source-control',f'PLC source requested SYSreset mode {mode}',origin,resetMode=mode)
                if mode in (17,18):self.command('cold-reset' if mode==18 else 'reset')
                elif mode in (32,64):self.command('stop')
                else:
                    self.command('cold-reset' if mode==2 else 'reset');self.command('run')
        except (ValueError, ArithmeticError, TypeError, KeyError, IndexError, ExitPLC, RecursionError) as error:
            self._fault(error, current)
        return None

    def command(self, action: str, speed=None, return_snapshot=True):
        action = str(action).lower()
        if speed is not None:
            if not isinstance(speed, (int, float)) or not math.isfinite(speed) or not .1 <= speed <= 10:
                raise RuntimeErrorPLC("Simulation speed must be 0.1..10")
            self.speed = float(speed)
        if action in {"run", "scan", "step"} and not self.run_allowed:
            raise RuntimeErrorPLC("Execution blocked: review compatibility diagnostics")
        if action == "run":
            if self.status == "faulted": raise RuntimeErrorPLC("Reset the fault before restarting")
            self.status = "running"
        elif action == "pause":
            self.status = "paused"
            if self._pending is not None: self._task_timing_interrupted = True
        elif action == "stop":
            self.status = "stopped"
            self._pending = self._pending_instruction = None
            self._skip_breakpoint = False
            if self._initialized and self.run_allowed:
                self._budget = MAX_INSTRUCTIONS_PER_SCAN
                try:
                    for identifier in self.exits:
                        for _ in self._program(identifier, "exit"): pass
                    for identifier in self.execution_order:
                        if identifier not in self.exits:
                            for _ in self._program(identifier, "exit"): pass
                except (ValueError, ArithmeticError, TypeError, KeyError, IndexError, ExitPLC) as error:
                    self._fault(error)
        elif action in {"reset", "cold-reset"}:
            self.memory.reset(cold=action == "cold-reset")
            self.vendor.reset(cold=action == 'cold-reset')
            self.services.reset(cold=action=='cold-reset')
            self._access_bindings.clear()
            if hasattr(self,'_ladder_values'):self._ladder_values.clear()
            self.status, self.time_ms, self.scan_count = "stopped", 0, 0
            self.cpu.reset()
            self._initialized = False
            self._requested_reset=None
            self._pending = self._pending_instruction = None
            self._skip_breakpoint = False
            for task in self.tasks:
                task["executionCount"], task["lastExecutionMs"], task["lastWallDurationMs"] = 0, None, None
                if task.get("intervalMs"): task["nextDueMs"] = float(task["intervalMs"])
            self.signal_history.clear()
            self._signal_history_count = 0
            self._edge_memory.clear()
        elif action == "scan":
            if self.status == "faulted": raise RuntimeErrorPLC("Reset the fault before scanning")
            self.status = "running"
            self.tick()
            if self.status == "running": self.status = "paused"
        elif action == "step":
            if self.status == "faulted": raise RuntimeErrorPLC("Reset the fault before stepping")
            self.status = "paused"
            self.tick(single_instruction=True)
        else:
            raise RuntimeErrorPLC("Unknown simulation command: " + action)
        self._event("control", action)
        return self.snapshot() if return_snapshot else None

    def value_reference(self, name_or_id, scope=None):
        try:
            record = self.memory.resolve(name_or_id, scope)
            return record, {"op": "ref", "name": record["id"], "path": []}
        except MemoryErrorPLC:
            # HMI datasource addresses may select a structure field or literal
            # array element. This is an lvalue parser, never an expression/call.
            address = str(name_or_id)
            explicit_scope, separator, binding = address.rpartition("::")
            if not separator and ':' in address:
                explicit_scope, separator, binding = address.rpartition(':')
            if not separator:
                binding = address
            if not re.fullmatch(r'[A-Za-z_]\w*(?:(?:\.[A-Za-z_]\w*)|(?:\[\s*-?\d+(?:\s*,\s*-?\d+)*\s*\]))+', binding):
                raise
            parser = Parser(binding, "Virtual interface binding")
            reference = parser.expression()
            if reference.get("op") != "ref" or parser.up != "<EOF>":
                raise RuntimeErrorPLC("Select a variable, structure member or array element")
            record = self.memory.resolve(explicit_scope + "::" + reference["name"] if separator else reference["name"], scope)
            reference["name"] = record["id"]
            for segment in reference.get("path", []):
                index = segment.get("index", {})
                if index.get("op") == "unary" and index.get("operator") == "-" and index.get("value", {}).get("op") == "literal":
                    segment["index"] = {"op": "literal", "value": -index["value"]["value"]}
            self.memory.reference_spec(reference, record["scope"])
            return record, reference

    def get_value(self, name_or_id, scope=None):
        record, reference = self.value_reference(name_or_id, scope)
        budget = self._budget
        try:
            self._budget = 1000
            return deepcopy(self._read(reference, record["scope"]))
        finally:
            self._budget = budget

    def set_value(self, name_or_id, value, force=False, scope=None, return_snapshot=True):
        record, reference = self.value_reference(name_or_id, scope)
        if force and reference.get("path"):
            raise RuntimeErrorPLC("Forcing individual array/structure members is not supported; force the whole variable instead")
        budget = self._budget
        try:
            self._budget = 1000
            self._write(reference, value, record["scope"], force=bool(force))
        finally:
            self._budget = budget
        self._event("force" if force else "input", record["name"] + (" forced" if force else " set"))
        return self.snapshot() if return_snapshot else None

    def release_force(self, name_or_id, scope=None):
        self.memory.release(name_or_id, scope)
        self._event("force-released", str(name_or_id))
        return self.snapshot()

    def set_breakpoint(self, source, line, enabled=True, return_snapshot=True):
        key = (str(source), int(line))
        if key[1] < 1: raise RuntimeErrorPLC("Breakpoint line must be positive")
        if enabled: self.breakpoints.add(key)
        else: self.breakpoints.discard(key)
        return self.snapshot() if return_snapshot else None

    def snapshot(self, compact=False, watchlist=(), state_only=False):
        variables = [] if state_only else self.memory.snapshot(compact=compact, watchlist=watchlist)
        for variable in variables:
            if isinstance(variable.get("value"), dict):
                variable["value"] = {key: value for key, value in variable["value"].items() if not key.startswith("_")}
            if isinstance(variable.get("previous"), dict):
                variable["previous"] = {key: value for key, value in variable["previous"].items() if not key.startswith("_")}
        signals = []
        configured = self.project.get("signals", self.project.get("io", self.project.get("hardware", {}).get("channels", [])))
        if isinstance(configured, dict): configured = configured.get("signals", configured.get("channels", []))
        for signal in ([] if state_only else configured):
            target = signal.get("variableId", signal.get("variable", signal.get("name")))
            try:
                record, reference = self.value_reference(target, signal.get("scope"))
                raw, _ = self.memory.member(record['value'], record['_spec'], reference.get('path', []), lambda index:index['value'])
            except (ValueError, AttributeError):
                signals.append({**signal, "value": None, "timestamp": self.time_ms, "quality": "unresolved"})
                continue
            signals.append({**signal, "id": signal.get("id", record["id"]), "name": signal.get("name", record["name"]),
                            "dataType": record["type"], "direction": signal.get("direction", "unknown"),
                            "value": deepcopy(raw), "timestamp": record["lastUpdate"],
                            "quality": "forced" if record["forced"] else "simulated", "forced": record["forced"],
                            "history": list(self.signal_history.get(record["id"], []))})
        errors = sum(item.get("severity") == "error" for item in self.diagnostics)
        memory = {key: deepcopy(row['value']) for key,row in self.memory.records.items() if row.get('retain')} if state_only else {item['id']: item['value'] for item in variables}
        return {"status": self.status, "timeMs": self.time_ms, "scanCount": self.scan_count, "speed": self.speed,
                'virtualFileIO': self.vendor.summary(),
                "quantumMs": self.quantum_ms, "memory": memory,
                "variables": variables, "tasks": deepcopy(self.tasks), "signals": signals, "trace": list(self.trace)[-200 if state_only else -500:] if compact or state_only else list(self.trace),
                "cpuServices": self.cpu.summary(),
                "virtualServices": self.services.summary(),
                "simulationProfile":self.simulation_profile,
                'performance': getattr(self, 'performance', {}), 'retentionOnly': state_only,
                "diagnostics": deepcopy(self.diagnostics), "breakpoints": [{"source": source, "line": line} for source, line in sorted(self.breakpoints)],
                "diagnosticCount": max(self.diagnostic_count, len(self.diagnostics)), "diagnosticsTruncated": self.diagnostic_count > len(self.diagnostics),
                "compatibility": {"runAllowed": self.run_allowed, "status": "supported" if self.run_allowed else "blocked",
                                  "supported": len(self.active_units) if self.run_allowed else 0, "blocked": errors,
                                  "limitations": ["Simulation executes a supported IEC subset, not the B&R runtime.",
                                                  "Breakpoints/step pause at task instruction boundaries; function calls are atomic.",
                                                  "No physical PLC communication or native C execution."]}}
