"""B&R Ladder wire/dataflow scheduling, without executing source XML or Python.

Geometry is the same logical-column/OR-junction model used by MatchView.
Every function and FB executes once after its wired inputs have been evaluated.
An unwired FB input retains its declared instance member; functions require inputs.
"""
from __future__ import annotations

import re
from functools import reduce

STANDARD_FUNCTIONS = {
    "ADD", "SUB", "MUL", "DIV", "MOD", "AND", "OR", "XOR", "NOT",
    "EQ", "NE", "LT", "LE", "GT", "GE", "MOVE", "LIMIT", "SEL", "MUX",
    "MIN", "MAX", "ABS", "SQRT", "SIN", "COS", "TAN", "EXP", "LN", "LOG",
    "TRUNC", "ROUND", "SHL", "SHR", "BIT_SET", "BIT_CLR", "BIT_TST",
}
COMPARISONS = {"EQ": "=", "NE": "<>", "LT": "<", "LE": "<=", "GT": ">", "GE": ">="}
COIL_TYPES = {"", "NORMAL", "OPEN", "CLOSED", "NEGATED", "SET", "RESET", "NC", "NO", "JUMP", "RETURN"}
CONTACT_TYPES = {"", "NORMAL", "OPEN", "CLOSED", "NEGATED", "NC", "NO", "TRANSITION", "POSITIVE TRANSITION", "NEGATIVE TRANSITION"}


def compile_plan(model, source, parse_expression):
    """Return serializable operations with explicit dependencies and pin bindings."""
    cells = model.get("cells", [])
    by_id = {cell["id"]: cell for cell in cells}
    parents = {}
    def find(key):
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = find(parents[key])
        return parents[key]
    def union(a, b):
        parents[find(b)] = find(a)
    def left(cell): return (cell["row"], cell["column"])
    def right(cell): return (cell["row"], cell["column"] + cell.get("span", 1))
    for cell in cells:
        find(left(cell)); find(right(cell))
        if cell["kind"] == "line": union(left(cell), right(cell))
    for edge in model.get("connections", []):
        if edge["kind"] == "branch":
            union(right(by_id[edge["from"]]), right(by_id[edge["to"]]))
    roots = {root: str(index) for index, root in enumerate(sorted({find(key) for key in parents}))}
    def junction(key): return roots[find(key)]
    rail = {junction(left(cell)) for cell in cells if cell["column"] == 0
            and cell["kind"] in {"line", "contact", "coil"}}
    groups = {}
    for cell in cells:
        kind = cell["kind"]
        if kind not in {"empty", "line", "contact", "coil", "analog", "function", "functionblock"}:
            raise ValueError("Unsupported Ladder element: " + kind)
        if kind in {"function", "functionblock"}:
            if not cell.get("blockId") or not cell.get("type"):
                raise ValueError("Function/FB lacks a resolved type or segment owner")
            groups.setdefault(cell["blockId"], []).append(cell)
    operations, producers = {}, {}
    def produce(j, opid, pin=None):
        producers.setdefault(j, []).append({"operation": opid, "pin": pin})
    for cell in cells:
        kind = cell["kind"]
        if kind == "analog":
            if cell.get("type", "").lower() not in {"input", "output"}:
                raise ValueError("Unsupported analog connector type: " + cell.get("type", ""))
            expression = parse_expression(cell.get("name", ""), source, target=cell["type"].lower() == "output")
            if cell["type"].lower() == "input":
                operations[cell["id"]] = {"kind": "value", "expression": expression, "line": cell.get("sourceLine", 1)}
                produce(junction(right(cell)), cell["id"])
            else:
                operations[cell["id"]] = {"kind": "output", "target": expression, "wire": junction(left(cell)), "line": cell.get("sourceLine", 1)}
        elif kind == "contact":
            typ = cell.get("type", "").upper()
            if typ not in CONTACT_TYPES: raise ValueError("Unsupported contact type: " + typ)
            expression = parse_expression(cell.get("name", ""), source)
            if expression.get("op") not in {"ref", "literal"} or (expression.get("op") == "literal" and not isinstance(expression.get("value"), bool)):
                raise ValueError("Ladder contact requires a BOOL binding or literal")
            cell["expression"] = expression
            operations[cell["id"]] = {"kind": "contact", "expression": expression, "type": typ,
                                      "wire": junction(left(cell)), "line": cell.get("sourceLine", 1)}
            produce(junction(right(cell)), cell["id"])
        elif kind == "coil":
            typ = cell.get("type", "").upper()
            if typ not in COIL_TYPES: raise ValueError("Unsupported coil type: " + typ)
            if typ == "JUMP":
                if not re.fullmatch(r"[A-Za-z_]\w*", cell.get("name", "")): raise ValueError("Invalid jump label")
                expression = None
            elif typ == "RETURN": expression = None
            else: expression = parse_expression(cell.get("name", ""), source, target=True)
            cell["expression"] = expression or {"op": "literal", "value": False}
            operations[cell["id"]] = {"kind": "coil", "type": typ, "target": expression,
                                      "label": cell.get("name", ""), "wire": junction(left(cell)), "line": cell.get("sourceLine", 1)}
    for identifier, members in groups.items():
        body = [cell for cell in members if cell.get("position") != "header"]
        if not body or not any(c.get("inputs") or c.get("outputs") for c in body): raise ValueError("Function/FB has no executable pin rows")
        kinds = {cell["kind"] for cell in members}; types = {cell["type"].upper() for cell in members}
        if len(kinds) != 1 or len(types) != 1: raise ValueError("Inconsistent function/FB segments")
        kind, typename = next(iter(kinds)), next(iter(types))
        names = {cell.get("instance") or cell.get("name") for cell in members} - {"", None}
        if kind == "functionblock" and len(names) != 1: raise ValueError("Function block requires one instance declaration")
        operation = {"kind": kind, "type": typename, "typeName": members[0]["type"], "name": next(iter(names)) if names else members[0]["type"],
                     "inputs": [], "outputs": [], "line": min(cell.get("sourceLine", 1) for cell in members)}
        used_inputs, used_outputs = set(), set()
        for cell in body:
            if len(cell.get("inputs", [])) > 1 or len(cell.get("outputs", [])) > 1:
                raise ValueError("Multiple pins on one row have no separate wire geometry")
            for pin in cell.get("inputs", []):
                # Extensible IEC operators may encode subsequent input names as empty.
                if pin and pin.upper() in used_inputs: raise ValueError("Duplicate input pin " + pin)
                used_inputs.add(pin.upper())
                j = junction(left(cell))
                connected = bool(producers.get(j)) or j in rail
                if connected: operation["inputs"].append({"pin": pin, "wire": j, "cell": cell["id"]})
            for pin in cell.get("outputs", []):
                if pin.upper() in used_outputs: raise ValueError("Duplicate output pin " + pin)
                used_outputs.add(pin.upper())
                operation["outputs"].append({"pin": pin, "wire": junction(right(cell)), "cell": cell["id"]})
        operations[identifier] = operation
        for output in operation["outputs"]: produce(output["wire"], identifier, output["pin"])
    # Inputs can be driven by groups that occur later in XML order. Connect after
    # all producers are registered; unwired FB members retain their stored value.
    for identifier, members in groups.items():
        operation = operations[identifier]
        operation["inputs"] = []
        for cell in members:
            if cell.get("position") == "header": continue
            for pin in cell.get("inputs", []):
                j = junction(left(cell)); connected = bool(producers.get(j)) or j in rail
                if connected: operation["inputs"].append({"pin": pin, "wire": j, "cell": cell["id"]})
                elif operation["kind"] == "function": raise ValueError("Function input has no wire: " + operation["type"] + "." + pin)
    # Topological order includes every contact (edge state) and FB (state update),
    # even when its output is currently false or unused.
    for operation in operations.values():
        if operation["kind"] == "output" and not producers.get(operation["wire"]):
            raise ValueError("Analog output has no data source")
        for item in operation.get("inputs", []):
            drivers = producers.get(item["wire"], [])
            if len(drivers) == 1:
                driver = operations[drivers[0]["operation"]]
                if driver["kind"] == "value": item["expression"] = driver["expression"]
    order, visiting, done = [], set(), set()
    def visit(identifier):
        if identifier in done: return
        if identifier in visiting: raise ValueError("Cyclic Ladder dataflow requires an explicit stored variable")
        visiting.add(identifier); operation = operations[identifier]
        wires = [operation["wire"]] if "wire" in operation else [item["wire"] for item in operation.get("inputs", [])]
        for j in wires:
            for value in producers.get(j, []): visit(value["operation"])
        visiting.remove(identifier); done.add(identifier); order.append(identifier)
    for identifier in sorted(operations, key=lambda key: (by_id[key]["column"], by_id[key]["row"], key)):
        visit(identifier)
    return {"version": 1, "operations": operations, "order": order, "producers": producers, "rail": sorted(rail)}


class LadderJump(Exception):
    def __init__(self, label): self.label = label


def execute_program(runtime, node, scope):
    """Preserve network order and bounded forward/backward IEC jump semantics."""
    body, labels, index = node["body"], node["labels"], 0
    while index < len(body):
        runtime._consume()
        try:
            yield from runtime._execute([body[index]], scope)
        except LadderJump as jump:
            index = labels[jump.label.casefold()]
        else: index += 1


def execute_network(runtime, node, scope):
    from .runtime import RuntimeErrorPLC, ReturnPLC, MAX_EDGE_STATES
    plan = node["plan"]; results = {}
    def signal(j):
        values = [results[item["operation"]][item["pin"]] if item.get("pin") is not None else results[item["operation"]]
                  for item in plan["producers"].get(j, [])]
        if j in plan["rail"]: values.append(True)
        if not values: return False
        if len(values) == 1: return values[0]
        if not all(isinstance(value, bool) for value in values):
            raise RuntimeErrorPLC("Multiple non-Boolean drivers on Ladder wire")
        return any(values)
    for identifier in plan["order"]:
        runtime._consume(); operation = plan["operations"][identifier]; kind = operation["kind"]
        if kind == "value": results[identifier] = runtime._eval(operation["expression"], scope)
        elif kind == "contact":
            value = bool(runtime._eval(operation["expression"], scope)); typ = operation["type"]
            if typ in {"TRANSITION", "POSITIVE TRANSITION", "NEGATIVE TRANSITION"}:
                key = (runtime._context.get("unitId"), node["source"], node.get("line"), node.get("networkNumber"), scope, "ladder-contact", identifier)
                if key not in runtime._edge_memory and len(runtime._edge_memory) >= MAX_EDGE_STATES: raise RuntimeErrorPLC("Edge operator state limit exceeded")
                previous = runtime._edge_memory.get(key, False); runtime._edge_memory[key] = value
                value = value!=previous if typ=='TRANSITION' else value and not previous if typ == "POSITIVE TRANSITION" else previous and not value
            elif typ in {"CLOSED", "NEGATED", "NC"}: value = not value
            results[identifier] = bool(signal(operation["wire"])) and value
        elif kind in {"function", "functionblock"}:
            arguments = [{"name": item["pin"] or None, "output": False,
                          "value": item.get("expression") or {"op": "literal", "value": signal(item["wire"])}} for item in operation["inputs"]]
            if kind == "function":
                wrapper=operation['type'] in STANDARD_FUNCTIONS or '_TO_' in operation['type']
                enable=next((a for a in arguments if str(a.get('name','')).upper()=='EN'),None) if wrapper else None
                key=(node['source'],node.get('networkNumber'),scope,identifier)
                saved=getattr(runtime,'_ladder_values',{})
                if enable and not bool(runtime._eval(enable['value'],scope)):
                    result=saved.get(key,False if operation['type'] in COMPARISONS else 0)
                else:
                    result=_function(runtime,operation,[a for a in arguments if a is not enable],scope,node,plan)
                    if enable:
                        if not hasattr(runtime,'_ladder_values'):runtime._ladder_values={}
                        runtime._ladder_values[key]=result
                results[identifier]={item['pin']:(bool(runtime._eval(enable['value'],scope)) if item['pin'].upper()=='ENO' and enable else result) for item in operation['outputs']}
            else:
                # Call the same declared instance and implementations as ST/AB.
                runtime._call({"op": "call", "name": operation["name"], "expectedType": operation["typeName"], "args": arguments,
                               "source": node["source"], "line": operation["line"]}, scope)
                results[identifier] = {item["pin"]: runtime._eval({"op": "ref", "name": operation["name"], "path": [{"member": item["pin"]}]}, scope)
                                       for item in operation["outputs"]}
        elif kind == "output": runtime._assign_source(operation["target"], signal(operation["wire"]), scope)
        elif kind == "coil":
            value = bool(signal(operation["wire"])); typ = operation["type"]
            if typ == "JUMP":
                if value: raise LadderJump(operation["label"])
            elif typ == "RETURN":
                if value: raise ReturnPLC()
            elif typ == "SET":
                if value: runtime._write(operation["target"], True, scope)
            elif typ == "RESET":
                if value: runtime._write(operation["target"], False, scope)
            else: runtime._write(operation["target"], not value if typ in {"CLOSED", "NEGATED", "NC"} else value, scope)


def _function(runtime, operation, arguments, scope, node, plan):
    from .runtime import RuntimeErrorPLC
    name = operation["type"]; values = [runtime._eval(argument["value"], scope) for argument in arguments]
    if name in COMPARISONS:
        if len(values) < 2: raise RuntimeErrorPLC(name + " requires at least two inputs")
        if name == "NE": return all(values[i] != values[j] for i in range(len(values)) for j in range(i+1, len(values)))
        return all(runtime._eval({"op": "binary", "operator": COMPARISONS[name], "left": {"op": "literal", "value": a}, "right": {"op": "literal", "value": b}}, scope)
                   for a, b in zip(values, values[1:]))
    if name == "NOT":
        if len(arguments) != 1: raise RuntimeErrorPLC("NOT requires one input")
        return runtime._eval({"op": "unary", "operator": "NOT", "value": arguments[0]["value"]}, scope)
    operators = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "AND": "AND", "OR": "OR", "XOR": "XOR"}
    if name in operators:
        if len(values) < 2: raise RuntimeErrorPLC(name + " requires at least two inputs")
        return reduce(lambda a,b: runtime._eval({"op": "binary", "operator": operators[name], "left": {"op": "literal", "value": a}, "right": {"op": "literal", "value": b}}, scope), values)
    # ADR and SIZEOF require the original declared expression, not its value.
    if name in {"ADR", "SIZEOF"}:
        for argument, item in zip(arguments, operation["inputs"]):
            sources = plan["producers"].get(item["wire"], [])
            if len(sources) != 1: raise RuntimeErrorPLC(name + " needs one declared input")
            original = plan["operations"][sources[0]["operation"]]
            if original["kind"] != "value": raise RuntimeErrorPLC(name + " needs a declared value or literal")
            argument["value"] = original["expression"]
    positional = name in STANDARD_FUNCTIONS or "_TO_" in name or name in {"ADR", "SIZEOF"}
    if positional:
        for argument in arguments: argument["name"] = None
    return runtime._call({"op": "call", "name": operation["typeName"], "args": arguments, "source": node["source"], "line": operation["line"]}, scope)


def validate_plan(runtime, node, unit, local, visited, section):
    """Use ordinary callable validation; compiler-owned graph operators are explicit."""
    from .compiler import walk_ir
    from .runtime import _diagnostic
    from .libraries import BLOCK_INPUTS, BLOCK_OUTPUTS, block_member
    plan = node["plan"]
    for wire,drivers in plan['producers'].items():
        if len({(d['operation'],d.get('pin')) for d in drivers})<2:continue
        for driver in drivers:
            producer=plan['operations'][driver['operation']]
            if producer['kind']!='value':continue
            expression=producer['expression']
            try:
                spec=runtime.memory.reference_spec(expression,unit['scope']) if expression.get('op')=='ref' else {'type':'BOOL' if isinstance(expression.get('value'),bool) else 'non-BOOL'}
                if spec.get('type')!='BOOL':
                    runtime.diagnostics.append(_diagnostic('LADDER_SIGNAL_TYPE','Parallel wire combines a scalar data value with another driver.',node['source'],producer['line']))
            except ValueError:pass
    for operation in plan["operations"].values():
        kind = operation["kind"]
        if kind not in {"function", "functionblock"}: continue
        typename = operation["type"]
        args = []
        for item in operation["inputs"]:
            sources = plan["producers"].get(item["wire"], [])
            original = plan["operations"][sources[0]["operation"]] if len(sources) == 1 else None
            expression = original["expression"] if original and original["kind"] == "value" else {"op": "literal", "value": False}
            args.append({"name": item["pin"] or None, "output": False, "value": expression})
        if kind == "function":
            if typename in STANDARD_FUNCTIONS:
                count = len([a for a in args if str(a.get('name','')).upper()!='EN'])
                low, high = (2, 64) if typename in set(COMPARISONS) | {"ADD", "SUB", "MUL", "DIV", "AND", "OR", "XOR"} else (1, 64) if typename in {"MIN", "MAX"} else (3, 3) if typename in {"LIMIT", "SEL"} else (2, 64) if typename == "MUX" else (1, 1) if typename in {"NOT", "MOVE", "ABS", "SQRT", "SIN", "COS", "TAN", "EXP", "LN", "LOG", "TRUNC", "ROUND"} else (2, 2)
                if not low <= count <= high:
                    runtime.diagnostics.append(_diagnostic("LADDER_FUNCTION_INTERFACE", typename + " input count is invalid", node["source"], operation["line"]))
                continue
            if "_TO_" in typename or typename in {"ADR", "SIZEOF"}:
                for arg in args: arg["name"] = None
            call = {"op": "call", "name": operation["typeName"], "args": args, "line": operation["line"]}
        else:
            for item in operation["outputs"]:
                try:
                    runtime.memory.reference_spec({"op": "ref", "name": operation["name"], "path": [{"member": item["pin"]}]}, unit["scope"])
                except ValueError as error:
                    runtime.diagnostics.append(_diagnostic("LADDER_BLOCK_INTERFACE", str(error), node["source"], operation["line"]))
            if typename in BLOCK_INPUTS:
                for item in operation["outputs"]:
                    if block_member(typename, item["pin"]) not in BLOCK_OUTPUTS[typename]:
                        runtime.diagnostics.append(_diagnostic("LADDER_BLOCK_INTERFACE", "Unknown " + typename + " output " + item["pin"], node["source"], operation["line"]))
            call = {"op": "call", "name": operation["name"], "expectedType": operation["typeName"], "args": args, "line": operation["line"]}
        runtime._validate_call(call, unit, local, visited, section)
