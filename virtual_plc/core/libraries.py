"""Explicit, deterministic IEC library implementations (no external I/O)."""
from __future__ import annotations

import math


class LibraryError(ValueError):
    pass


def builtin(name: str, args: list):
    name = name.upper()
    if "_TO_" in name:
        name = name.rsplit("_TO_", 1)[1]
    if name.startswith("TO_"):
        name = name[3:]
    arity = {"ABS": (1, 1), "SQRT": (1, 1), "SIN": (1, 1), "COS": (1, 1), "TAN": (1, 1),
             "EXP": (1, 1), "LN": (1, 1), "LOG": (1, 1), "TRUNC": (1, 1), "ROUND": (1, 1),
             "LIMIT": (3, 3), "SEL": (3, 3), "MUX": (2, 64), "MIN": (1, 64), "MAX": (1, 64),
             "SHL": (2, 2), "SHR": (2, 2), "ROL": (2, 2), "ROR": (2, 2),
             "BIT_SET": (2, 2), "BIT_CLR": (2, 2), "BIT_TST": (2, 2), "MOD": (2, 2), "MOVE": (1, 1),'LEN':(1,1),'CONCAT':(2,2)}
    integers = {"BYTE", "WORD", "DWORD", "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT"}
    if name in integers | {"BOOL", "REAL", "LREAL", "TIME", "STRING"}:
        if len(args) != 1:
            raise LibraryError(name + " requires one argument")
        if name == "BOOL":
            if not isinstance(args[0], (int, float)) or not math.isfinite(args[0]):
                raise LibraryError("BOOL conversion requires a finite numeric or Boolean input")
            return bool(args[0])
        if name == "STRING":
            if isinstance(args[0], bool): return "TRUE" if args[0] else "FALSE"
            return str(args[0])[:4096]
        return int(round(args[0])) if name in integers and isinstance(args[0], float) else int(args[0]) if name in integers else float(args[0])
    if name not in arity or not arity[name][0] <= len(args) <= arity[name][1]:
        raise LibraryError("Unsupported call or argument count: " + name)
    if name == "ABS": return abs(args[0])
    if name=='LEN':
        if not isinstance(args[0],str):raise LibraryError('LEN requires STRING')
        return len(args[0])
    if name=='CONCAT':
        if not all(isinstance(v,str) for v in args) or len(args[0])+len(args[1])>4096:raise LibraryError('CONCAT requires bounded STRING inputs')
        return ''.join(args)
    if name == "MIN": return min(args)
    if name == "MAX": return max(args)
    if name == "LIMIT": return max(args[0], min(args[1], args[2]))
    if name == "SEL": return args[2] if args[0] else args[1]
    if name == "MUX":
        index = int(args[0])
        if not 0 <= index < len(args)-1:
            raise LibraryError("MUX selector outside input range")
        return args[index+1]
    if name == "MOVE": return args[0]
    if name == "TRUNC": return math.trunc(args[0])
    if name == "ROUND": return round(args[0])
    if name == "MOD":
        if not args[1]: raise LibraryError("Division by zero")
        return args[0] - math.trunc(args[0]/args[1])*args[1]
    if name in {"SHL", "SHR", "ROL", "ROR", "BIT_SET", "BIT_CLR", "BIT_TST"}:
        value, shift = int(args[0]), int(args[1])
        if not 0 <= shift < 64:
            raise LibraryError("Bit/shift position must be 0..63")
        if name == "SHL": return value << shift
        if name == "SHR": return value >> shift
        # Width-dependent rotate semantics require a typed argument; unsupported
        # until the IR carries that width. Never guess DWORD for a BYTE input.
        if name in {"ROL", "ROR"}:
            raise LibraryError("Rotate requires an explicit typed operand width; unsupported")
        if name == "BIT_SET": return value | (1 << shift)
        if name == "BIT_CLR": return value & ~(1 << shift)
        return bool(value & (1 << shift))
    funcs = {"SQRT": math.sqrt, "SIN": math.sin, "COS": math.cos, "TAN": math.tan,
             "EXP": math.exp, "LN": math.log, "LOG": math.log10}
    return funcs[name](args[0])


BLOCK_INPUTS = {"TON": {"IN", "PT"}, "TON_10MS": {"IN", "PT"}, "TOF": {"IN", "PT"}, "TP": {"IN", "PT"},
                "CTU": {"CU", "R", "PV"}, "CTD": {"CD", "LD", "PV"},
                "R_TRIG": {"CLK"}, "F_TRIG": {"CLK"}}
BLOCK_OUTPUTS = {"TON": {"Q", "ET"}, "TON_10MS": {"Q", "ET"}, "TOF": {"Q", "ET"}, "TP": {"Q", "ET"},
                 "CTU": {"Q", "CV"}, "CTD": {"Q", "CV"}, "R_TRIG": {"Q"}, "F_TRIG": {"Q"}}


def block_member(kind: str, name: str) -> str:
    """Resolve B&R standard.fun counter input names to one stored field.

    The supplied standard library declares CTU.RESET and CTD.LOAD. Keep the
    existing IEC R/LD spelling usable without creating two independent inputs.
    """
    kind, name = str(kind).upper(), str(name).upper()
    return {"CTU": {"RESET": "R"}, "CTD": {"LOAD": "LD"}}.get(kind, {}).get(name, name)


def block_field_type(kind, key):
    if key in {'IN', 'Q', 'CU', 'CD', 'R', 'LD', 'CLK'}: return 'BOOL'
    if key in {'PT', 'ET'}: return 'UDINT' if kind == 'TON_10MS' else 'TIME'
    return 'DINT'


def execute_block(kind: str, block: dict, inputs: dict, now_ms: float):
    kind = kind.upper()
    if kind not in BLOCK_INPUTS:
        raise LibraryError("Unsupported function block: " + kind)
    normalized = {}
    for name, value in inputs.items():
        canonical = block_member(kind, name)
        if canonical in normalized:
            raise LibraryError("Duplicate " + kind + " input after alias resolution: " + canonical)
        normalized[canonical] = value
    inputs = normalized
    if set(inputs) - BLOCK_INPUTS[kind]:
        raise LibraryError("Unsupported " + kind + " inputs: " + ", ".join(sorted(set(inputs)-BLOCK_INPUTS[kind])))
    for name, value in inputs.items():
        if name in {"PT", "PV"}:
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise LibraryError(kind + " " + name + " must be a finite non-negative number")
            if name == "PV" and value != int(value):
                raise LibraryError("Counter preset must be integral")
            if kind == 'TON_10MS' and name == 'PT' and (value != int(value) or value > 4294967295):
                raise LibraryError('TON_10ms preset must be a UDINT count of 10 ms intervals')
            block[name] = value
        else:
            if value not in (True, False, 0, 1):
                raise LibraryError(kind + " " + name + " must be BOOL")
            block[name] = bool(value)
    state = block.setdefault("_state", {})
    if kind in {"R_TRIG", "F_TRIG"}:
        current = bool(block["CLK"])
        previous = state.get("previous", False if kind == "R_TRIG" else True)
        block["Q"] = current and not previous if kind == "R_TRIG" else not current and previous
        state["previous"] = current
    elif kind in {"CTU", "CTD"}:
        signal = bool(block["CU" if kind == "CTU" else "CD"])
        rising = signal and not state.get("previous", False)
        if kind == "CTU":
            if block["R"]:
                block["CV"] = 0
            elif rising:
                block["CV"] = min(32767, int(block["CV"])+1)
            block["Q"] = block["CV"] >= block["PV"]
        else:
            if block["LD"]:
                block["CV"] = min(32767, int(block["PV"]))
            elif rising:
                block["CV"] = max(0, int(block["CV"])-1)
            block["Q"] = block["CV"] <= 0
        state["previous"] = signal
    else:
        signal, preset = bool(block["IN"]), float(block["PT"])
        previous = state.get("previous", False)
        if kind in {"TON", 'TON_10MS'}:
            if signal:
                state.setdefault("start", now_ms)
                elapsed = max(0, now_ms-state['start'])
                block['ET'] = min(preset, math.floor(elapsed/10) if kind == 'TON_10MS' else elapsed)
                block["Q"] = block["ET"] >= preset
            else:
                state.pop("start", None)
                block["ET"], block["Q"] = 0.0, False
        elif kind == "TOF":
            if signal:
                state.pop("start", None)
                block["ET"], block["Q"] = 0.0, True
            else:
                if previous:
                    state["start"] = now_ms
                if "start" in state:
                    block["ET"] = min(preset, max(0, now_ms-state["start"]))
                    block["Q"] = block["ET"] < preset
                else:
                    block["ET"], block["Q"] = 0.0, False
        elif kind == "TP":
            if signal and not previous and "start" not in state:
                state["start"] = now_ms
            if "start" in state:
                block["ET"] = min(preset, max(0, now_ms-state["start"]))
                block["Q"] = block["ET"] < preset
                if not block["Q"]:
                    state.pop("start", None)
            else:
                block["Q"] = False
                if not signal:
                    block["ET"] = 0.0
        state["previous"] = signal
    return {name: block[name] for name in BLOCK_OUTPUTS[kind]}
