"""Deterministic, source-linked PLC function and sequence analysis for Chopper.

This engine reads the owner's existing project index and reuses the IEC and
ladder parsers. It never executes PLC code or infers a live machine timeline.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath

from python_engine.compare import _ladder_networks, decode_project_text
from python_engine.function_flow import _ladder_flow, _mask_comments, _names, _text_flow
from python_engine.project_analysis import _mask
from python_engine.source_operations import collect_operations
from python_engine.working_sequence import ASSIGNMENT, branch_guard, records, walk


SCHEMA = 3
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_CODE_FILES = 800
MAX_EVIDENCE = 3000
STATE_SELECTOR = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
STATE_NAMES = re.compile(r"(?:step|state|sequence|seq|phase)", re.I)
ALARM_NAMES = re.compile(r"(?:alarm|fault|trip|error|warning)", re.I)
TIMER_TYPES = {"ton", "tof", "tp"}
EDGE_TYPES = {"r_trig", "f_trig", "ctu", "ctd", "ctud"}


def _decode(path: Path, raw: bytes) -> str:
    if path.suffix.casefold() in {".src", ".ld"}:
        return decode_project_text(path, raw)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _normal(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _active_task_for(path: str, tasks: list[dict], active_configuration: str):
    normalized = "/" + path.casefold().replace("\\", "/")
    owners = []
    disabled = []
    other_configuration = []
    configuration_unresolved = []
    for task in tasks:
        source = str(task.get("source") or "").removesuffix(".prg").replace(".", "/").strip("/")
        if not source:
            continue
        marker = "/" + source.casefold() + "/"
        if marker not in normalized:
            continue
        configuration = str(task.get("configuration") or "")
        if not active_configuration:
            configuration_unresolved.append((len(source), task))
            continue
        if not task.get("enabled"):
            if configuration.casefold() == active_configuration.casefold():
                disabled.append((len(source), task))
            else:
                other_configuration.append((len(source), task))
        elif configuration.casefold() == active_configuration.casefold():
            owners.append((len(source), task))
        else:
            other_configuration.append((len(source), task))
    if owners:
        return max(owners, key=lambda value: value[0])[1], "active task"
    if disabled:
        return max(disabled, key=lambda value: value[0])[1], "disabled task"
    if other_configuration:
        return max(other_configuration, key=lambda value: value[0])[1], "other configuration task"
    if configuration_unresolved:
        task = max(configuration_unresolved, key=lambda value: value[0])[1]
        return task, "task assignment found; active configuration unresolved"
    return None, "shared / task ownership unconfirmed"


def _configuration_for_path(path: str):
    parts = PurePosixPath(str(path).replace("\\", "/")).parts
    return parts[1] if len(parts) > 1 and parts[0].casefold() == "physical" else None


def _hmi_folder_for_path(path: str):
    parts = PurePosixPath(str(path).replace("\\", "/")).parts
    return parts[1] if len(parts) > 1 and parts[0].casefold() == "logical" else None


class _Evidence:
    def __init__(self, root: Path):
        self.root = root
        self.lines = {}
        self.items = []
        self.by_source = {}
        self.notices = []

    def add(self, file: str, line: int, end_line: int | None = None, kind="source", ownership="active task"):
        line = max(1, int(line or 1))
        key = (file, line, kind)
        if key in self.by_source:
            return self.by_source[key]
        if len(self.items) >= MAX_EVIDENCE:
            return None
        try:
            resolved = (self.root / file).resolve()
            if not resolved.is_relative_to(self.root) or resolved.is_symlink():
                raise ValueError("Source is outside the indexed project.")
            if file not in self.lines:
                if resolved.stat().st_size > MAX_SOURCE_BYTES:
                    raise ValueError("Source exceeds the analysis size limit.")
                self.lines[file] = _decode(resolved, resolved.read_bytes()).splitlines()
            lines = self.lines[file]
            first = max(1, line - 2)
            last = min(len(lines), max(line + 2, int(end_line or line)))
            if last - first > 8:
                last = first + 8
            excerpt = "\n".join(f"{number}: {lines[number - 1]}" for number in range(first, last + 1))
            item_id = f"E{len(self.items) + 1:03d}"
            item = {"id": item_id, "type": kind, "file": file, "line": line,
                    "endLine": min(int(end_line or line), max(line, len(lines))),
                    "ownership": ownership, "status": "verified from source", "excerpt": excerpt}
            self.items.append(item)
            self.by_source[key] = item_id
            return item_id
        except (OSError, ValueError) as error:
            note = f"{file}:{line} could not be read for evidence ({error})."
            if note not in self.notices:
                self.notices.append(note)
            return None


def _machine_transitions(file, task, ownership, sections, parser_notices, evidence):
    machines = []
    for section in sections:
        for case in walk(section.get("nodes", [])):
            selector = str(case.get("condition") or "").strip().strip("() ")
            if case.get("kind") != "case" or not STATE_SELECTOR.fullmatch(selector):
                continue
            transitions = []
            labels = []
            for branch_index, branch in enumerate(case.get("branches", [])):
                label = str(branch.get("label") or "").strip()
                if label:
                    labels.append(label)
                outer_guard = branch_guard(case, branch_index)
                nested_records = list(records(branch.get("nodes", []), (outer_guard,), (branch.get("line", case.get("line", 1)),)))
                branch_transitions = []
                for record in nested_records:
                    row = record["row"]
                    match = ASSIGNMENT.match(row.get("code", ""))
                    if not match or _normal(match.group(1)) != _normal(selector):
                        continue
                    target = match.group(2).strip()
                    refs = []
                    condition_refs = []
                    assignment_refs = []
                    condition_lines = list(dict.fromkeys(record.get("guardLines", []) or [branch.get("line", case.get("line", 1))]))
                    for ref_line in list(dict.fromkeys([*condition_lines, row.get("line", 1)])):
                        ref = evidence.add(file, ref_line, kind="state transition", ownership=ownership)
                        if ref:
                            refs.append(ref)
                            (assignment_refs if ref_line == row.get("line", 1) else condition_refs).append(ref)
                    nested = [guard for guard in record.get("guards", []) if guard != outer_guard]
                    branch_transitions.append({"from": label or "Unlabelled branch", "to": target,
                                               "conditions": [outer_guard, *nested], "line": row.get("line", 1),
                                               "evidence": list(dict.fromkeys(refs)),
                                               "conditionEvidence": list(dict.fromkeys(condition_refs)),
                                               "assignmentEvidence": list(dict.fromkeys(assignment_refs)),
                                               "_guardPath": list(record.get("guards", [])),
                                               "status": "source-parsed assignment; live transition not established" if not parser_notices else "parsed fact; surrounding control flow needs review"})
                branch_records = [record for record in nested_records if record.get("row", {}).get("code", "").strip()]
                for transition in branch_transitions:
                    wanted = transition.pop("_guardPath")
                    actions = []
                    for record in branch_records:
                        row = record["row"]
                        code = row.get("code", "").strip()
                        assignment = ASSIGNMENT.match(code)
                        if assignment and _normal(assignment.group(1)) == _normal(selector):
                            continue
                        guard_path = record.get("guards", [])
                        if len(guard_path) <= len(wanted) and all(_normal(left) == _normal(right) for left, right in zip(guard_path, wanted)):
                            action_ref = evidence.add(file, row.get("line", 1), row.get("endLine"), kind="transition action", ownership=ownership)
                            actions.append({"code": code, "line": row.get("line", 1), "evidence": [action_ref] if action_ref else []})
                    transition["actions"] = actions[:24]
                    transition["evidence"] = list(dict.fromkeys([*transition["evidence"], *(ref for action in transition["actions"] for ref in action["evidence"])]))
                    transitions.append(transition)
            if not transitions:
                continue
            if STATE_NAMES.search(selector) or len(labels) >= 2:
                machine_id = f"{Path(file).stem}:{selector}:{case.get('line', 1)}"
                state_labels = list(dict.fromkeys([*labels, *(item["to"] for item in transitions)]))
                machines.append({"id": machine_id, "name": selector, "routine": section.get("name") or Path(file).stem,
                                 "file": file, "task": task.get("name") if task else None,
                                 "ownership": ownership, "line": case.get("line", 1),
                                 "states": state_labels, "transitions": transitions,
                                 "status": "CASE transitions parsed; whether this selector represents a machine state is unconfirmed" if not parser_notices else "partial; parser notices affect branch completeness",
                                 "notices": parser_notices[:4]})
    return machines


def _retained_declarations(file, text):
    """Return declarations inside explicit IEC RETAIN variable blocks."""
    clean = _mask(text)
    retained = []
    declaration = re.compile(r"(?im)^\s*([A-Za-z_]\w*)\s*(?:AT\s+[^:;]+)?\s*:\s*([^;\n]+);?")
    for block in re.finditer(r"(?ims)^\s*VAR(?:_GLOBAL|_INPUT|_OUTPUT|_IN_OUT|_TEMP)?\s+RETAIN\b(.*?)^\s*END_VAR\b", clean):
        for match in declaration.finditer(block.group(1)):
            line = text.count("\n", 0, block.start(1) + match.start(1)) + 1
            retained.append({"name": match.group(1), "datatype": match.group(2).strip(), "file": file, "line": line,
                             "status": "RETAIN declared in source; runtime persistence and initialization were not simulated"})
    return retained


def _source_call_targets(calls, symbols, file, task, ownership, evidence):
    result = []
    for call in calls:
        name = str(call.get("name") or "").split(".")[-1]
        candidates = symbols.get(name.casefold(), [])
        implementations = [symbol for symbol in candidates if symbol.get("kind") in {"function", "function_block", "program"}]
        status = "resolved to local declaration" if len(implementations) == 1 else "ambiguous local declaration" if len(implementations) > 1 else "library, external, or unresolved"
        ref = evidence.add(file, call.get("line", 1), kind="function call", ownership=ownership)
        result.append({"caller": Path(file).stem, "file": file, "callee": name, "instance": call.get("instance") or name,
                       "line": call.get("line", 1), "task": task.get("name") if task else None,
                       "ownership": ownership, "resolution": status,
                       "targetFiles": list(dict.fromkeys(symbol.get("file") for symbol in implementations))[:6],
                       "evidence": [ref] if ref else []})
    return result


def _read_schedule(index, tasks, evidence):
    schedule = []
    seen = set()
    recognized = {"period", "cycle", "cycletime", "priority", "interval", "executionperiod", "taskperiod", "schedule"}
    for task in sorted(tasks, key=lambda item: (item.get("file", "").casefold(), item.get("line", 0))):
        file = task.get("file")
        if not file or file in seen:
            continue
        seen.add(file)
        try:
            path = (index.root / file).resolve()
            if not path.is_relative_to(index.root) or path.stat().st_size > MAX_SOURCE_BYTES:
                continue
            tree = ET.fromstring(path.read_bytes())
            for node in tree.iter():
                if node.tag.rsplit("}", 1)[-1].casefold() != "task":
                    continue
                attrs = {key: value for key, value in node.attrib.items() if key.casefold() in recognized}
                matching = next((item for item in tasks if item.get("name", "").casefold() == node.get("Name", "").casefold() and item.get("file") == file), None)
                if matching:
                    ref = evidence.add(file, matching.get("line", 1), kind="task configuration", ownership="active configuration")
                    schedule.append({"name": matching.get("name"), "source": matching.get("source"),
                                     "configuration": matching.get("configuration"), "enabled": bool(matching.get("enabled")),
                                     "declarationOrder": len(schedule) + 1, "configuredTiming": attrs,
                                     "timingEvidence": [ref] if ref else []})
        except (ET.ParseError, OSError, ValueError):
            continue
    return schedule


def _fingerprint(index, db):
    rows = [tuple(row) for row in db.execute("SELECT path,size,mtime,sha,status FROM files ORDER BY path")]
    details = json.dumps([SCHEMA, index.root.as_posix(), rows], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(details.encode("utf-8")).hexdigest()


def analyze(index):
    """Build or return the cached evidence model for an indexed B&R project."""
    from backend.core.project_intelligence import connection, metadata

    with connection(index.path) as db:
        fingerprint = _fingerprint(index, db)
        cached = metadata(db, "machine_function_analysis") or {}
        if cached.get("fingerprint") == fingerprint:
            return cached["result"]
        state = metadata(db, "state") or {}
        identity = metadata(db, "identity") or {}
        active_configuration = str(identity.get("activeConfiguration") or "")
        task_rows = [dict(row) for row in db.execute("SELECT name,source,file,line,enabled,configuration FROM tasks ORDER BY file,line")]
        declarations = defaultdict(list)
        for row in db.execute("SELECT name,display,kind,datatype,file,line,scope FROM symbols ORDER BY name,file,line"):
            declarations[row["name"].casefold()].append(dict(row))
        files = [dict(row) for row in db.execute("SELECT path,size,category,status FROM files WHERE status='indexed' ORDER BY path")]
        io_edges = [dict(row) for row in db.execute("SELECT a,b,file,line,detail FROM edges WHERE kind='io-binding' ORDER BY file,line LIMIT 1200")]
        hmi_edges = [dict(row) for row in db.execute("SELECT a,b,file,line,detail FROM edges WHERE kind='hmi-binding' ORDER BY file,line LIMIT 1200")]
        dependency_edges = [dict(row) for row in db.execute("SELECT a,b,file,line,scope,detail FROM edges WHERE kind='depends-on' ORDER BY file,line LIMIT 12000")]
        failed = [dict(row) for row in db.execute("SELECT path,error FROM files WHERE status='failed' ORDER BY path LIMIT 100")]
        c_paths = [row["path"] for row in files if row["category"] == "Logic" and Path(row["path"]).suffix.casefold() == ".c"]
        c_refs = defaultdict(list)
        if c_paths:
            placeholders = ",".join("?" for _ in c_paths)
            for row in db.execute(f"SELECT name,file,line,kind FROM refs WHERE file IN ({placeholders}) AND kind IN ('call','write','read','use') ORDER BY file,line", c_paths):
                c_refs[row["file"]].append(dict(row))

    evidence = _Evidence(index.root)
    output_addresses = {}
    hardware_links = []
    for edge in io_edges:
        detail = str(edge.get("detail") or "")
        address = re.search(r"\bAT\s+(%[IQ][A-Z]?[^;\s]*)", detail, re.I)
        if address:
            configuration = _configuration_for_path(edge["file"])
            selected = bool(active_configuration and configuration and configuration.casefold() == active_configuration.casefold())
            ownership = "active configuration" if selected else "other configuration" if active_configuration and configuration else "configuration ownership unresolved"
            ref = evidence.add(edge["file"], edge["line"], kind="hardware mapping", ownership=ownership)
            mapping = {"variable": edge["a"], "address": address.group(1), "file": edge["file"], "line": edge["line"],
                       "configuration": configuration, "ownership": ownership, "evidence": [ref] if ref else []}
            hardware_links.append(mapping)
            if selected:
                output_addresses.setdefault(_normal(edge.get("a")), []).append(mapping)

    indexed_executable = [row for row in files if Path(row["path"]).suffix.casefold() in {".st", ".ab", ".src", ".ld", ".c", ".fun"}
                          and row["category"] in {"Logic", "Ladder"}]
    ownership_rank = {"active task": 0, "task assignment found; active configuration unresolved": 1,
                      "shared / task ownership unconfirmed": 2, "other configuration task": 3, "disabled task": 4}
    ranked_files = sorted(indexed_executable, key=lambda row: (ownership_rank.get(_active_task_for(row["path"], task_rows, active_configuration)[1], 2), row["path"].casefold()))
    disabled_source_file_count = sum(1 for row in indexed_executable if _active_task_for(row["path"], task_rows, active_configuration)[1] in {"disabled task", "other configuration task"})
    analyzable_files = [row for row in ranked_files if _active_task_for(row["path"], task_rows, active_configuration)[1] not in {"disabled task", "other configuration task"}]
    code_files = analyzable_files[:MAX_CODE_FILES]
    notices = []
    notices.append("Static source analysis does not prove live machine operation, functional safety, or commissioning behavior.")
    if len(analyzable_files) > MAX_CODE_FILES:
        notices.append(f"Only the first {MAX_CODE_FILES} executable files were analyzed; full coverage is incomplete.")
    if disabled_source_file_count:
        notices.append(f"{disabled_source_file_count} disabled-task or non-active-configuration source files were excluded from active sequence analysis.")
    if not active_configuration:
        notices.append("Active PLC configuration is unresolved; task ownership cannot be confirmed.")
    parsed_count = 0
    parse_failures = []
    language_counts = defaultdict(int)
    functions = []
    ladder_networks = []
    calls = []
    state_machines = []
    timer_signals = {}
    edge_signals = {}
    alarm_signals = {}
    writers = defaultdict(list)
    retained_variables = []
    interlocks = []
    file_owner = {}

    for file_row in code_files:
        file = file_row["path"]
        task, ownership = _active_task_for(file, task_rows, active_configuration)
        file_owner[file] = {"task": task, "ownership": ownership}
        if ownership == "disabled task":
            continue
        try:
            path = (index.root / file).resolve()
            if not path.is_relative_to(index.root) or path.is_symlink():
                raise ValueError("Source resolves outside the indexed project.")
            if path.stat().st_size > MAX_SOURCE_BYTES:
                raise ValueError("Source exceeds the 8 MB analysis limit.")
            text = _decode(path, path.read_bytes()).replace("\x00", "")
            if not text.strip():
                continue
            suffix = path.suffix.casefold()
            if suffix in {".st", ".ab", ".src", ".fun"}:
                masked = _mask(text)
                basic = suffix == ".ab" or bool(re.search(r"\b(?:ENDIF|ENDLOOP|FUB)\b", masked, re.I))
                sections, variable_rows, parsed_calls, parser_notices = _text_flow(text, file, basic)
                language = "Automation Basic" if basic else "IEC function source" if suffix == ".fun" else "Structured Text"
                language_counts[language] += 1
                parsed_count += 1
                parsed_writes = []
                parsed_reads = []
                for section in sections:
                    for record in records(section.get("nodes", [])):
                        row = record["row"]
                        match = ASSIGNMENT.match(row.get("code", ""))
                        if not match:
                            continue
                        name, expression = match.groups()
                        alarm_entry = None
                        if ALARM_NAMES.search(name):
                            alarm_entry = alarm_signals.setdefault(_normal(name), {"name": name, "writers": [], "readers": [], "status": "name-based alarm/fault candidate"})
                        timer_property = bool(re.match(r"^[A-Za-z_]\w*\.(?:PT|IN)\s*$", name, re.I))
                        important_assignment = _normal(name) in output_addresses or (alarm_entry is not None and not alarm_entry["writers"]) or timer_property
                        ref = evidence.add(file, row.get("line", 1), row.get("endLine"), kind="alarm/output/timer assignment", ownership=ownership) if important_assignment else None
                        entry = {"name": name, "value": expression, "file": file, "line": row.get("line", 1),
                                 "task": task.get("name") if task else None, "ownership": ownership,
                                 "guards": record.get("guards", []) if not parser_notices else [],
                                 "guardCoverage": "parsed" if not parser_notices else "unresolved due to parser notices",
                                 "evidence": [ref] if ref else []}
                        parsed_writes.append(entry)
                        writers[_normal(name)].append(entry)
                        for read in _names(expression):
                            parsed_reads.append(read)
                        if alarm_entry is not None:
                            alarm_entry["writers"].append(entry)
                        if _normal(name).endswith((".pt", ".in", ".et", ".q", ".reset", ".ack")):
                            instance, _, prop = name.rpartition(".")
                            if instance and prop.casefold() in {"pt", "in"}:
                                timer_signals.setdefault(_normal(instance), {"instance": instance, "settings": [], "type": None, "evidence": []})["settings"].append({"name": prop, "value": expression, "line": row.get("line", 1), "file": file, "evidence": [ref] if ref else []})
                        if _normal(name) in output_addresses:
                            interlocks.append({"output": name, "physical": output_addresses[_normal(name)], "conditions": entry["guards"],
                                               "guardCoverage": entry["guardCoverage"], "file": file, "line": entry["line"], "evidence": entry["evidence"]})
                for variable in variable_rows:
                    if ALARM_NAMES.search(variable["name"]):
                        alarm_signals.setdefault(_normal(variable["name"]), {"name": variable["name"], "writers": [], "readers": [], "status": "name-based alarm/fault candidate"})["readers"].append({"file": file, "reads": variable["reads"][:20], "writes": variable["writes"][:20]})
                for call in parsed_calls:
                    name = str(call.get("name") or "").casefold()
                    instance = str(call.get("instance") or call.get("name") or "")
                    candidates = declarations.get(instance.casefold(), [])
                    datatype = next((row.get("datatype") for row in candidates if row.get("kind") == "variable" and row.get("datatype")), "")
                    block_type = str(datatype or name).split(".")[-1].casefold()
                    if block_type in TIMER_TYPES:
                        ref = evidence.add(file, call.get("line", 1), kind="timer block call", ownership=ownership)
                        entry = timer_signals.setdefault(_normal(instance), {"instance": instance, "settings": [], "type": block_type.upper(), "evidence": []})
                        if ref:
                            entry["evidence"].append(ref)
                    elif block_type in EDGE_TYPES:
                        ref = evidence.add(file, call.get("line", 1), kind="edge/counter block call", ownership=ownership)
                        entry = edge_signals.setdefault(_normal(instance), {"instance": instance, "type": block_type.upper(), "file": file,
                                                                              "line": call.get("line", 1), "evidence": []})
                        if ref:
                            entry["evidence"].append(ref)
                calls.extend(_source_call_targets(parsed_calls, declarations, file, task, ownership, evidence))
                state_machines.extend(_machine_transitions(file, task, ownership, sections, parser_notices, evidence))
                if parser_notices:
                    parse_failures.append({"file": file, "notices": list(dict.fromkeys(parser_notices))[:6], "ownership": ownership})
                function_ref = evidence.add(file, parsed_writes[0]["line"] if parsed_writes else (sections[0].get("nodes", [{}])[0].get("line", 1) if sections and sections[0].get("nodes") else 1), kind="routine evidence", ownership=ownership)
                functions.append({"name": Path(file).stem, "file": file, "language": language,
                                  "task": task.get("name") if task else None, "ownership": ownership,
                                  "operations": len(parsed_writes), "calls": len(parsed_calls),
                                  "inputs": list(dict.fromkeys(parsed_reads))[:32],
                                  "outputs": list(dict.fromkeys(item["name"] for item in parsed_writes))[:32],
                                  "evidence": list(dict.fromkeys([function_ref, *(ref for item in parsed_writes for ref in item["evidence"])]))[:40],
                                  "parserNotices": list(dict.fromkeys(parser_notices))[:6]})
            elif suffix == ".ld":
                networks = _ladder_networks(text, source_file=file)
                network_offsets = [match.start() for match in re.finditer(r"<network\s", text, re.I)]
                for network in networks:
                    network_number = network.get("index", 0)
                    line = text.count("\n", 0, network_offsets[network_number - 1]) + 1 if 0 < network_number <= len(network_offsets) else 1
                    elements = [{key: element.get(key) for key in ("kind", "name", "type", "position", "row", "column", "branch", "pins")} for element in network.get("elements", [])]
                    network_ref = evidence.add(file, line, kind="ladder network topology", ownership=ownership) if not network.get("commented") else None
                    ladder_networks.append({"file": file, "line": line, "network": network_number,
                                            "task": task.get("name") if task else None, "ownership": ownership,
                                            "label": network.get("label"), "comment": network.get("comment"),
                                            "commented": network.get("commented"), "rows": network.get("rows"),
                                            "summary": network.get("summary"), "layout": network.get("layout"),
                                            "elements": elements,
                                            "status": "commented; not executable" if network.get("commented") else "topology preserved; complex branch conditions are not flattened",
                                            "evidence": [network_ref] if network_ref else []})
                sections, variable_rows, parsed_calls, parser_notices = _ladder_flow(text, file)
                operations = collect_operations(file, text, "Ladder", ownership, networks)
                language_counts["Ladder XML"] += 1
                parsed_count += 1
                parsed_writes = []
                for operation in operations:
                    needs_evidence = _normal(operation["name"]) in output_addresses or ALARM_NAMES.search(operation["name"])
                    ref = evidence.add(file, operation.get("eventLine", 1), kind="ladder output", ownership=ownership) if needs_evidence else None
                    entry = {"name": operation["name"], "value": operation.get("coilType"), "file": file,
                             "line": operation.get("eventLine", 1), "task": task.get("name") if task else None,
                             "ownership": ownership, "guards": operation.get("guards", []),
                             "guardCoverage": "parsed" if not operation.get("complexTopology") else "complex rung; retain diagram topology",
                             "evidence": [ref] if ref else [], "network": operation.get("network")}
                    parsed_writes.append(entry)
                    writers[_normal(operation["name"])].append(entry)
                    if ALARM_NAMES.search(operation["name"]):
                        alarm_signals.setdefault(_normal(operation["name"]), {"name": operation["name"], "writers": [], "readers": [], "status": "name-based alarm/fault candidate"})["writers"].append(entry)
                    if _normal(operation["name"]) in output_addresses:
                        interlocks.append({"output": operation["name"], "physical": output_addresses[_normal(operation["name"])],
                                           "conditions": operation.get("guards", []), "guardCoverage": entry["guardCoverage"],
                                           "file": file, "line": entry["line"], "evidence": entry["evidence"]})
                calls.extend(_source_call_targets(parsed_calls, declarations, file, task, ownership, evidence))
                function_ref = evidence.add(file, parsed_writes[0]["line"] if parsed_writes else (sections[0].get("nodes", [{}])[0].get("line", 1) if sections and sections[0].get("nodes") else 1), kind="routine evidence", ownership=ownership)
                functions.append({"name": Path(file).stem, "file": file, "language": "Ladder XML",
                                  "task": task.get("name") if task else None, "ownership": ownership,
                                  "operations": len(parsed_writes), "calls": len(parsed_calls),
                                  "inputs": list(dict.fromkeys(value for node in sections[0].get("nodes", []) for value in node.get("conditions", [])))[:32] if sections else [],
                                  "outputs": list(dict.fromkeys(item["name"] for item in parsed_writes))[:32],
                                  "evidence": list(dict.fromkeys([function_ref, *(ref for item in parsed_writes for ref in item["evidence"])]))[:40],
                                  "parserNotices": parser_notices[:6]})
            elif suffix == ".c":
                # C is inventoried and linked through the existing reference index,
                # but its branches are deliberately not parsed as IEC control flow.
                language_counts["C (control flow unresolved)"] += 1
                calls_in_file = c_refs.get(file, [])
                parsed_calls = [{"name": row["name"], "instance": row["name"], "line": row["line"]} for row in calls_in_file if row["kind"] == "call"]
                calls.extend(_source_call_targets(parsed_calls, declarations, file, task, ownership, evidence))
                functions.append({"name": Path(file).stem, "file": file, "language": "C", "task": task.get("name") if task else None,
                                  "ownership": ownership, "operations": 0, "calls": len(parsed_calls), "inputs": [], "outputs": [],
                                  "evidence": [], "parserNotices": ["C call/reference index only; C control flow and write/return semantics are unresolved."]})
        except (OSError, ValueError, ET.ParseError, IndexError, KeyError, TypeError) as error:
            parse_failures.append({"file": file, "notices": [str(error)[:240]], "ownership": ownership})

    calls_by_file = defaultdict(list)
    for call in calls:
        if call.get("resolution") == "resolved to local declaration":
            calls_by_file[call["file"]].append(call)
    reachable_by_task = defaultdict(set)
    pending = deque()
    visited = set()
    for file, owner_info in file_owner.items():
        if owner_info.get("ownership") == "active task":
            task_name = (owner_info.get("task") or {}).get("name") or "active task"
            reachable_by_task[file].add(task_name)
            pending.append((file, task_name))
    while pending:
        caller_file, task_name = pending.popleft()
        marker = (caller_file, task_name)
        if marker in visited:
            continue
        visited.add(marker)
        for call in calls_by_file.get(caller_file, []):
            for target_file in call.get("targetFiles", []):
                if task_name not in reachable_by_task[target_file]:
                    reachable_by_task[target_file].add(task_name)
                    pending.append((target_file, task_name))
    def add_reachability(item):
        tasks = sorted(reachable_by_task.get(item.get("file", ""), set()), key=str.casefold)
        item["reachableFromTasks"] = tasks
        if tasks and item.get("ownership") != "active task":
            item["reachabilityStatus"] = "Potentially reachable through resolved local calls; call guards, invocation and task scheduling were not executed."
    for collection in (functions, state_machines, ladder_networks, calls, interlocks, alarm_signals.values()):
        for item in collection:
            add_reachability(item)

    timer_type_by_name = {}
    for items in declarations.values():
        for item in items:
            if item.get("kind") == "variable" and str(item.get("datatype") or "").strip().casefold() in TIMER_TYPES | EDGE_TYPES:
                timer_type_by_name.setdefault(item["name"].casefold(), item["datatype"].strip().upper())
    for key, timer in timer_signals.items():
        if not timer.get("type"):
            timer["type"] = timer_type_by_name.get(timer["instance"].casefold())
        timer["status"] = "block instance and source calls found; internal runtime behavior not simulated" if timer.get("type") else "timer-like name; block type not resolved"

    for key, edge in edge_signals.items():
        if not edge.get("type"):
            edge["type"] = timer_type_by_name.get(edge["instance"].casefold())

    for file_row in files:
        file = file_row["path"]
        if Path(file).suffix.casefold() not in {".var", ".st", ".ab", ".src", ".fun"}:
            continue
        try:
            path = (index.root / file).resolve()
            if not path.is_relative_to(index.root) or path.is_symlink() or path.stat().st_size > MAX_SOURCE_BYTES:
                continue
            text = _decode(path, path.read_bytes()).replace("\x00", "")
            for item in _retained_declarations(file, text):
                item["evidence"] = [evidence.add(file, item["line"], kind="retained state declaration", ownership="declaration scope")]
                item["evidence"] = [ref for ref in item["evidence"] if ref]
                retained_variables.append(item)
        except (OSError, ValueError):
            continue

    shared_writes = []
    for key, locations in writers.items():
        distinct = {(item["file"], item.get("task"), item.get("line")) for item in locations}
        if len(distinct) > 1:
            routines = {(item["file"], item.get("task")) for item in locations}
            status = "multiple source writers across routines/tasks; scheduling and last-write behavior not simulated" if len(routines) > 1 else "multiple writes in one routine/task; cyclic branch order and final value depend on execution conditions"
            shared_writes.append({"signal": locations[0]["name"], "writerCount": len(distinct), "writers": locations[:16], "status": status})

    hmi_links = []
    selected_hmi = str(identity.get("screenFolder") or "")
    for number, edge in enumerate(hmi_edges):
        hmi_folder = _hmi_folder_for_path(edge["file"])
        selected = bool(selected_hmi and hmi_folder and hmi_folder.casefold() == selected_hmi.casefold())
        ownership = "selected HMI project" if selected else "other HMI project" if selected_hmi and hmi_folder else "HMI project unresolved"
        ref = evidence.add(edge["file"], edge["line"], kind="HMI binding", ownership=ownership) if number < 100 else None
        hmi_links.append({"control": edge["a"], "signal": edge["b"], "file": edge["file"], "line": edge["line"],
                          "detail": edge["detail"], "hmiProject": hmi_folder, "ownership": ownership,
                          "status": "binding belongs to selected HMI project" if selected else "not linked to the selected HMI target",
                          "evidence": [ref] if ref else []})
    type_definitions = [symbol for rows in declarations.values() for symbol in rows if symbol.get("kind") == "data_type"]

    dependencies = []
    active_paths = {file for file, owner in file_owner.items() if owner["ownership"] == "active task"}
    reachable_paths = set(reachable_by_task) - active_paths
    for number, edge in enumerate(dependency_edges):
        if edge["file"] not in active_paths | reachable_paths:
            continue
        direct = edge["file"] in active_paths
        ownership = "active task" if direct else "reachable through resolved local calls"
        key = evidence.add(edge["file"], edge["line"], kind="data dependency", ownership=ownership) if number < 160 else None
        dependencies.append({"output": edge["a"], "input": edge["b"], "file": edge["file"], "line": edge["line"],
                             "scope": edge["scope"], "ownership": ownership,
                             "reachableFromTasks": sorted(reachable_by_task.get(edge["file"], set()), key=str.casefold),
                             "evidence": [key] if key else []})

    schedule = _read_schedule(index, task_rows, evidence)
    active_tasks = [item for item in schedule if item.get("configuration", "").casefold() == active_configuration.casefold() and item.get("enabled")]
    if not active_configuration:
        notices.append("Active PLC configuration is unresolved; task ownership cannot be confirmed.")
    if selected_hmi and not any(item["ownership"] == "selected HMI project" for item in hmi_links):
        notices.append("No indexed HMI bindings were found under the selected visualization project.")
    if not selected_hmi and hmi_links:
        notices.append("Visualization target is unresolved; HMI bindings are kept separate by project folder and are not linked to an active target.")
    if state.get("failedFilesCount"):
        notices.append(f"{state['failedFilesCount']} indexed source files failed; behavior in those files is unresolved.")
    if state.get("analysisNotices"):
        notices.append("The project index reported bounded extraction or parser notices; review relevant source before treating paths as complete.")
    if any(item.get("ownership") == "shared / task ownership unconfirmed" for item in functions):
        notices.append("Some routines have no active task assignment; they are shown as shared context, not proven active execution.")
    if any(item.get("parserNotices") for item in functions):
        notices.append("Some Structured Text, Automation Basic or ladder sections have parser notices; affected branch coverage is incomplete.")
    if any(item.get("language") == "C" for item in functions):
        notices.append("C source has call/reference indexing only; control flow and write ordering need a C-aware parser.")
    if not any(task.get("configuredTiming") for task in schedule):
        notices.append("The selected CPU task configuration does not expose cycle period or priority attributes; task declaration order is not a proven runtime order.")
    if len(evidence.items) >= MAX_EVIDENCE:
        notices.append("Evidence excerpts are bounded; open the cited source lines for additional surrounding logic.")
    if len(ladder_networks) > 5000:
        notices.append("Ladder topology output is bounded to the first 5000 networks; additional networks are indexed but omitted from this model.")

    result = {"schemaVersion": SCHEMA, "project": {"name": index.root.name,
              "automationStudioVersion": identity.get("automationStudioVersion"),
              "activeConfiguration": active_configuration or None, "plcType": identity.get("plcType"),
              "hmiProject": identity.get("screenFolder"), "hmiPanelType": identity.get("screenType")},
              "analysisMode": "deterministic static analysis", "executionSimulated": False,
              "coverage": {"indexReady": bool(state.get("ready")), "indexedFiles": len(files),
                           "failedIndexedFiles": len(failed), "executableSourceFiles": len(indexed_executable),
                           "parsedSourceFiles": parsed_count, "codeFilesAnalyzed": len(code_files),
                           "excludedDisabledOrOtherConfigurationFiles": disabled_source_file_count,
                           "activeTaskCount": len(active_tasks), "taskCount": len(schedule),
                           "activeStateGroupCount": sum(1 for item in state_machines if item.get("ownership") == "active task"),
                           "reachableStateGroupCount": sum(1 for item in state_machines if item.get("ownership") != "active task" and item.get("reachableFromTasks")),
                           "reachableRoutineFileCount": len(reachable_paths),
                           "stateTransitionCount": sum(len(item.get("transitions", [])) for item in state_machines),
                           "callReferenceCount": len(calls), "timerCount": len(timer_signals),
                           "alarmCandidateCount": len(alarm_signals), "multipleWriterSignalCount": len(shared_writes),
                           "retainedVariableCount": len(retained_variables), "ladderNetworkCount": len(ladder_networks),
                           "typeDefinitionCount": len(type_definitions),
                           "hmiBindingCount": len(hmi_links),
                           "selectedHmiBindingCount": sum(1 for item in hmi_links if item["ownership"] == "selected HMI project"),
                           "hardwareMappingCount": len(hardware_links),
                           "activeHardwareMappingCount": sum(1 for item in hardware_links if item["ownership"] == "active configuration"),
                           "dataDependencyCount": len(dependencies),
                           "languageFiles": dict(language_counts), "failedFiles": failed[:30],
                           "parsingIssues": parse_failures[:100], "notices": list(dict.fromkeys(notices + evidence.notices))[:100]},
              "taskExecution": {"tasks": schedule,
                                "orderingMeaning": "Rows preserve CPU configuration declaration order only. This does not establish scheduler priority, task period, preemption, or observed runtime order."},
              "stateMachines": state_machines[:300], "functions": functions[:400],
              "callGraph": calls[:3000], "timers": list(timer_signals.values())[:500],
              "edgeAndCounterBlocks": list(edge_signals.values())[:300],
              "alarmCandidates": list(alarm_signals.values())[:500],
              "interlockCandidates": interlocks[:1200], "multipleWriters": shared_writes[:800],
              "retainedVariables": retained_variables[:2000],
              "typeDefinitions": sorted(type_definitions, key=lambda item: (item.get("file", "").casefold(), item.get("line", 0)))[:5000],
              "dataDependencies": dependencies[:12000], "hmiLinks": hmi_links[:1200],
              "hardwareLinks": hardware_links[:1200], "ladderNetworks": ladder_networks[:5000], "evidence": evidence.items}
    with connection(index.path) as db:
        metadata(db, "machine_function_analysis", {"fingerprint": fingerprint, "result": result})
        db.commit()
    return result


def compact_for_chat(result):
    """Small deterministic facts for the LLM; detailed evidence stays in the UI."""
    coverage = result.get("coverage", {})
    task_execution = result.get("taskExecution", {})
    return {"project": result.get("project"),
            "coverage": {key: coverage.get(key) for key in ("indexReady", "indexedFiles", "failedIndexedFiles", "executableSourceFiles", "parsedSourceFiles", "codeFilesAnalyzed", "excludedDisabledOrOtherConfigurationFiles", "activeTaskCount", "taskCount", "activeStateGroupCount", "reachableStateGroupCount", "reachableRoutineFileCount", "stateTransitionCount", "callReferenceCount", "timerCount", "alarmCandidateCount", "multipleWriterSignalCount", "retainedVariableCount", "typeDefinitionCount", "ladderNetworkCount", "hmiBindingCount", "selectedHmiBindingCount", "hardwareMappingCount", "activeHardwareMappingCount", "dataDependencyCount", "languageFiles", "notices")},
            "taskExecution": {"orderingMeaning": task_execution.get("orderingMeaning"),
                              "tasks": [{key: task.get(key) for key in ("name", "source", "configuration", "enabled", "declarationOrder", "configuredTiming")} for task in task_execution.get("tasks", [])[:30]]},
            "stateMachineGroupCount": len(result.get("stateMachines", [])),
            "unresolvedOwnershipGroupCount": sum(1 for item in result.get("stateMachines", []) if item.get("ownership") != "active task"),
            "stateMachines": [{key: item.get(key) for key in ("id", "name", "routine", "file", "task", "ownership", "line", "states", "status")}
                              | {"transitionCount": len(item.get("transitions", []))}
                              for item in result.get("stateMachines", []) if item.get("ownership") == "active task"][:24],
            "reachableStateMachines": [{key: item.get(key) for key in ("id", "name", "routine", "file", "task", "ownership", "reachableFromTasks", "reachabilityStatus", "line", "states", "status")}
                                        | {"transitionCount": len(item.get("transitions", []))}
                                        for item in result.get("stateMachines", []) if item.get("ownership") != "active task" and item.get("reachableFromTasks")][:24],
            "functions": [{key: item.get(key) for key in ("name", "file", "language", "task", "ownership", "operations", "calls", "inputs", "outputs", "parserNotices")}
                          | {key: item.get(key) for key in ("reachableFromTasks", "reachabilityStatus")}
                          for item in result.get("functions", [])[:30]],
            "callGraph": [{key: item.get(key) for key in ("caller", "file", "callee", "instance", "line", "task", "ownership", "resolution", "targetFiles", "reachableFromTasks", "reachabilityStatus", "evidence")}
                          for item in result.get("callGraph", []) if item.get("ownership") == "active task" or item.get("reachableFromTasks")][:60],
            "timers": [{key: item.get(key) for key in ("instance", "type", "settings", "status")} for item in result.get("timers", [])[:30]],
            "edgeAndCounterBlocks": [{key: item.get(key) for key in ("instance", "type", "file", "line")} for item in result.get("edgeAndCounterBlocks", [])[:20]],
            "alarmCandidates": [{"name": item.get("name"), "status": item.get("status"),
                                 "writers": [{key: writer.get(key) for key in ("file", "line", "task", "guards")} for writer in item.get("writers", [])[:3]]}
                                for item in result.get("alarmCandidates", [])[:30]],
            "interlockCandidates": [{key: item.get(key) for key in ("output", "conditions", "guardCoverage", "file", "line")} for item in result.get("interlockCandidates", [])[:20]],
            "ladderNetworks": [{key: item.get(key) for key in ("file", "line", "network", "task", "ownership", "label", "comment", "commented", "rows", "summary", "layout", "status", "elements", "evidence")} for item in result.get("ladderNetworks", [])[:30]],
            "multipleWriters": [{"signal": item.get("signal"), "writerCount": item.get("writerCount"), "status": item.get("status"),
                                 "writers": [{key: writer.get(key) for key in ("file", "line", "task", "guards")} for writer in item.get("writers", [])[:4]]}
                                for item in result.get("multipleWriters", [])[:20]],
            "retainedVariables": [{key: item.get(key) for key in ("name", "datatype", "file", "line", "status")} for item in result.get("retainedVariables", [])[:40]],
            "typeDefinitions": [{key: item.get(key) for key in ("name", "display", "datatype", "file", "line", "scope")} for item in result.get("typeDefinitions", [])[:40]],
            "totalTransitionCount": sum(len(item.get("transitions", [])) for item in result.get("stateMachines", [])),
            "unresolvedCallCount": sum(1 for item in result.get("callGraph", []) if item.get("resolution") == "library, external, or unresolved"),
            "notices": coverage.get("notices", [])[:30]}

