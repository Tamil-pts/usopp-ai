from __future__ import annotations
import argparse, json, re, sys
try:
    from python_engine.hmi_requirements import parse_requirements, control_candidates, compare_control
except ModuleNotFoundError:
    from hmi_requirements import parse_requirements, control_candidates, compare_control
try:
    from python_engine.rule_evidence import enrich_result, expected_logic, LOGIC_KINDS
except ModuleNotFoundError:
    from rule_evidence import enrich_result, expected_logic, LOGIC_KINDS
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
try: from python_engine.project_paths import project_files
except ModuleNotFoundError: from project_paths import project_files
try: from python_engine.source_resolution import matching_sources
except ModuleNotFoundError: from source_resolution import matching_sources

STATUS = {"PASS":"pass", "FAIL":"fail", "NOT FOUND":"not_found"}


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def all_files(root: Path, suffix: str | None = None):
    for p in project_files(root):
        if p.is_file() and (suffix is None or p.suffix.lower() == suffix.lower()):
            yield p


def find_file_equiv(root: Path, names: list[str], suffix: str | None = None):
    targets = {n.lower() for n in names}
    for p in all_files(root, suffix):
        if p.name.lower() in targets:
            return p
    return None


def packet_source_files(root: Path, requested: str = "mms_nw_rCyclic.st"):
    """Resolve the packet source name used by AS 4.x and legacy AS 2.7."""
    names = {Path(requested).name.lower()}
    known = {"mms_nw_rcyclic.st", "cyclic.st", "mms_nw_r.st", "mms_nw_r.src"}
    if names & known:
        names.update(known)
    matches=[]
    packet_request=bool(names & known)
    candidates=matching_sources(root,requested,list(all_files(root)))
    for p in candidates:
        if packet_request and p.name.lower() in {"cyclic.st", "mms_nw_r.st"} and p.parent.name.casefold()!="mms_nw_r":
            continue
        if packet_request and p.name.lower()=="mms_nw_r.st" and not re.search(r"\bCASE\s+nw_group_code\s+OF\b",read_text(p),re.I):
            continue
        matches.append(p)
    return matches


def result(rule_id, name, status, expected, actual, evidence=None, recommendations=None, source_files=None):
    return {
        "id": rule_id, "name": name, "status": status,
        "expected": expected, "actual": actual,
        "evidence": evidence or [],
        "recommendations": recommendations or [],
        "sourceFiles": source_files or [],
    }


def checkpoint_1(root, rule):
    p = next(iter(packet_source_files(root, rule.get("subroutine", "mms_nw_rCyclic.st"))), None)
    if not p:
        return result(rule["id"], rule["name"], "NOT FOUND", rule["expected"], "mms_nw_rCyclic.st not found", recommendations=["Locate the packet cyclic subroutine or configure the rule with the equivalent source file."])
    text = read_text(p)
    checks = {
        "alarm_default": bool(re.search(r"Alarm_EN_Delay\s*:=\s*250", text, re.I)),
        "alarm_condition": bool(re.search(r"Alarm_EN_Delay[^\n;]*<=\s*30", text, re.I) or re.search(r"IF\s+Alarm_EN_Delay\s*<=\s*30", text, re.I)),
        "hmi_default": bool(re.search(r"HMI_read_recv_timeout_time\s*:=\s*250", text, re.I)),
        "hmi_condition": bool(re.search(r"HMI_read_recv_timeout_time[^\n;]*<=\s*30", text, re.I) or re.search(r"IF\s+HMI_read_recv_timeout_time\s*<=\s*30", text, re.I)),
        "final_calc": bool(re.search(r"read_recv_timeout_time\s*:=\s*HMI_read_recv_timeout_time\s*\*\s*1000", text, re.I)),
    }
    ok = all(checks.values())
    evidence = [f"{k}: {'FOUND' if v else 'MISSING'}" for k,v in checks.items()]
    return result(rule["id"], rule["name"], "PASS" if ok else "FAIL", rule["expected"], "All timeout requirements detected." if ok else "One or more timeout requirements are missing.", evidence, ["Review mms_nw_rCyclic.st and restore the missing comparison/default/multiplication logic."] if not ok else [], [str(p.relative_to(root))])


def checkpoint_2(root, rule):
    p = next(iter(packet_source_files(root, rule.get("subroutine", "mms_nw_rCyclic.st"))), None)
    if not p:
        return result(rule["id"], rule["name"], "NOT FOUND", rule["expected"], "mms_nw_rCyclic.st not found")
    text = read_text(p)
    found = []
    for m in re.finditer(r"(?:nw_rcv_buffer|rtc_nw_rcv_buffer)\s*\[\s*(\d+)\s*\]", text, re.I):
        found.append(int(m.group(1)))
    assignments = []
    pat = re.compile(r"rtc_nw_rcv_buffer\s*\[\s*(\d+)\s*\]\s*:=\s*nw_rcv_buffer\s*\[\s*(\d+)\s*\]", re.I)
    for m in pat.finditer(text): assignments.append((int(m.group(1)), int(m.group(2))))
    expected = list(range(9,28))
    pairs = {d:s for d,s in assignments}
    missing = [i for i in expected if i not in pairs]
    wrong = [i for i in expected if i in pairs and pairs[i] != i]
    ok = len(assignments) >= 19 and not missing and not wrong
    return result(rule["id"], rule["name"], "PASS" if ok else "FAIL", rule["expected"], f"Found {len(assignments)} RTC byte assignments." if assignments else "No RTC byte assignments found.", [f"Destination/source pairs: {assignments[:25]}", f"Missing indexes: {missing or 'none'}", f"Wrong source indexes: {wrong or 'none'}"], ["Add the missing 9–27 assignments from nw_rcv_buffer to rtc_nw_rcv_buffer."] if not ok else [], [str(p.relative_to(root))])


def parse_case_branches(text: str):
    m = re.search(r"CASE\s+nw_group_code\s+OF(.*?)(?:END_CASE)", text, re.I | re.S)
    if not m: return {}
    body = m.group(1)
    starts = list(re.finditer(r"(?:^|\n)\s*([0-9]+(?:\s*,\s*[0-9]+)*)\s*:\s*", body))
    branches = {}
    for i, s in enumerate(starts):
        end = starts[i+1].start() if i+1 < len(starts) else len(body)
        segment = body[s.end():end]
        for code in re.split(r"\s*,\s*", s.group(1)):
            branches[int(code)] = segment
    return branches


def checkpoint_3(root, rule):
    target = rule.get("variable", "Blow_room_product_code")
    requested = rule.get("subroutine", "mms_nw_rCyclic.st")
    files = packet_source_files(root, requested)
    size = str(rule.get("size", 2))
    branches = {}
    source = None
    for p in files:
        t = read_text(p)
        b = parse_case_branches(t)
        if b:
            branches.update({(k,p):v for k,v in b.items()})
            source = p
    if not branches:
        return result(rule["id"], rule["name"], "NOT FOUND", rule["expected"], "CASE nw_group_code OF not found", recommendations=["Confirm the packet response CASE is present and uses nw_group_code."])
    rows=[]
    failures=[]
    for (gc,p),seg in branches.items():
        if gc == 11: continue
        mem = re.search(r"memcpy\s*\(.*?ADR\s*\(\s*([^\)]+)\s*\).*?ADR\s*\(\s*([^\)]+)\s*\).*?,\s*(\d+)\s*\)\s*;", seg, re.I|re.S)
        first = mem.group(2).strip() if mem else None
        first_size = mem.group(3) if mem else None
        inc_ok = bool(re.search(r"memcpy\s*\(.*?%s.*?\b%s\b.*?\)\s*;\s*nw_i\s*:=\s*nw_i\s*\+\s*2\s*;" % (re.escape(target), re.escape(size)), seg, re.I|re.S))
        ok = bool(mem and target.lower() in (first or '').lower() and first_size == size and inc_ok)
        rows.append({"groupCode":gc,"file":str(p.relative_to(root)),"firstVariable":first,"size":first_size,"increment2":inc_ok,"status":"PASS" if ok else "FAIL"})
        if not ok: failures.append(gc)
    status = "PASS" if rows and not failures else "FAIL"
    return result(rule["id"], rule["name"], status, rule["expected"], f"Checked {len(rows)} Group Code branches (excluding 11).", rows, [f"Fix first response memcpy and nw_i increment for Group Codes: {failures}"] if failures else [], [str(source.relative_to(root))] if source else [])


def checkpoint_4(root, rule):
    all_names = [p for p in all_files(root)]
    lower_paths = [str(p.relative_to(root)).lower().replace('\\','/') for p in all_names]
    rtc_names = ["mms_rtc.fun","cyclic.st","init.st","iec.prg","mms_rtc_auto.var","gvarmms_rtc.var","gvarmms_rtc.typ"]
    rtc_hits = {n: any((n in x) for x in lower_paths) for n in rtc_names}
    rtc_ok = rtc_hits["mms_rtc.fun"] and sum(1 for v in rtc_hits.values() if v) >= 4
    ping_logic = [x for x in lower_paths if any(k in Path(x).name.lower() for k in ["icmp_ping.st","icmp_ping.var","icmp_ping","icmpping","ping.st","ping.var"]) and not x.endswith('.page')]
    ping_ok = bool(ping_logic)
    page_candidates = [p for p in all_names if p.suffix.lower()=='.page' and any(k in p.name.lower() for k in ["mms_ip_ping","mms_ping","mms_ip_ping","mms_ping"])]
    if not page_candidates:
        page_candidates = [p for p in all_names if p.suffix.lower()=='.page' and 'ping' in p.name.lower()]
    page_evidence=[]
    page_ok=False
    for p in page_candidates:
        t=read_text(p).lower()
        controls = {
            "ip_address": 'ip address' in t or 'ip_address' in t or 'ipaddress' in t,
            "start_ping": 'start ping' in t or 'start_ping' in t,
            "status": 'ping status' in t or 'ping_status' in t or 'status' in t and 'ping' in t,
            "binding": 'icmp_ping' in t or 'icmpping' in t,
        }
        page_evidence.append({"page":str(p.relative_to(root)),**controls})
        if sum(controls.values()) >= 3 and controls['binding']: page_ok=True
    overall = rtc_ok and ping_ok and page_ok
    status = "PASS" if overall else ("NOT FOUND" if not rtc_ok and not ping_ok and not page_candidates else "FAIL")
    return result(rule["id"], rule["name"], status, rule["expected"], "RTC, Ping logic and Ping HMI were detected." if overall else "One or more RTC/Ping requirements are incomplete.", [{"rtcFiles":rtc_hits},{"pingLogic":ping_logic},{"pingPages":page_evidence}], ["Add/restore the missing RTC files, Ping implementation, or Ping HMI controls/bindings."] if not overall else [], [str(p.relative_to(root)) for p in page_candidates[:10]])


def _source_evidence(root: Path, path: Path, text: str, pos: int, check: str, excerpt: str | None = None, line_number: int | None = None):
    """Create stable source evidence that the UI and Assist can cite."""
    line = line_number or _line_number(text, max(0, pos))
    lines = text.splitlines()
    shown = excerpt if excerpt is not None else (lines[line - 1].strip() if line <= len(lines) else "")
    return {
        "check": check,
        "file": str(path.relative_to(root)),
        "line": line,
        "excerpt": shown[:500],
    }


def _find_pattern_evidence(root: Path, files: list[Path], pattern: str, check: str, flags=re.I | re.S):
    for path in files:
        text = read_text(path)
        clean = _strip_plc_comments(text)
        match = re.search(pattern, clean, flags)
        if match:
            return _source_evidence(root, path, text, match.start(), check, match.group(0), _line_number(clean, match.start()))
    return None


def _configured_source_files(root: Path, rule: dict[str, Any]):
    requested = rule.get("subroutine", "mms_nw_rCyclic.st")
    return packet_source_files(root, requested)


def _condition_assignment_checkpoint(root: Path, rule: dict[str, Any]):
    files = _configured_source_files(root, rule)
    variable = str(rule.get("variable") or "")
    comparison = str(rule.get("comparison") or "<=")
    threshold = str(rule.get("threshold") if rule.get("threshold") is not None else 30)
    assigned = str(rule.get("assignedValue") if rule.get("assignedValue") is not None else 250)
    if not files:
        return result(rule["id"], rule["name"], "NOT FOUND", rule["expected"],
                      f"{rule.get('subroutine', 'mms_nw_rCyclic.st')} was not found.",
                      recommendations=["Locate the packet cyclic source or configure its equivalent filename."])
    alternatives=expected_logic(rule)
    if alternatives:
        for path in files:
            text=read_text(path); clean=_strip_plc_comments(text)
            segment=clean; start=0
            if rule.get('groupCode') is not None:
                branch=_branch_with_location(text,int(rule['groupCode']))
                if not branch: continue
                segment,start=branch
            for index,alternative in enumerate(alternatives):
                hit=_logic_match(segment,alternative)
                if hit:
                    line=_line_number(clean,start+hit[0])
                    evidence=_source_evidence(root,path,text,0,f'accepted condition logic {index+1}',alternative,line)
                    return result(rule['id'],rule['name'],'PASS',rule['expected'],
                                  f'Complete accepted condition logic alternative {index+1} was found.',[evidence],[],
                                  sorted({str(source.relative_to(root)) for source in files}))
        evidence=[{'check':'accepted condition logic','status':'MISSING','expected':alternatives,
                   'actual':'None of the complete accepted condition blocks was found.'}]
        return result(rule['id'],rule['name'],'FAIL',rule['expected'],
                      f'None of the {len(alternatives)} complete accepted condition logic blocks was found.',evidence,
                      ['Review the IF condition, assignment and END_IF in the configured PLC source.'],
                      sorted({str(source.relative_to(root)) for source in files}))
    operator = re.escape(comparison)
    pattern = (rf"IF\s*\(?\s*{re.escape(variable)}\s*{operator}\s*{re.escape(threshold)}\s*\)?\s*THEN"
               rf".*?{re.escape(variable)}\s*:=\s*{re.escape(assigned)}\s*;.*?END_IF")
    hit = _find_pattern_evidence(root, files, pattern, "condition and default assignment")
    status = "PASS" if hit else "FAIL"
    evidence = [hit] if hit else []
    if not hit:
        observed_pattern=rf"IF[^\r\n]*{re.escape(variable)}[^\r\n]*THEN.*?{re.escape(variable)}\s*:=\s*[^;]+;.*?END_IF"
        observed=_find_pattern_evidence(root,files,observed_pattern,"observed non-matching logic")
        if observed: evidence.append(observed)
        evidence.append({
            "check": "condition and default assignment",
            "status": "MISSING",
            "variable": variable,
            "expectedCondition": f"{variable} {comparison} {threshold}",
            "expectedAssignment": f"{variable} := {assigned}",
        })
    return result(rule["id"], rule["name"], status, rule["expected"],
                  "Required condition and assignment were found." if hit else "Required condition or assignment is missing.",
                  evidence,
                  [f"Add the required {variable} condition and assignment in the packet cyclic source."] if not hit else [],
                  sorted({str(p.relative_to(root)) for p in files}))


def _indexed_assignment_checkpoint(root: Path, rule: dict[str, Any]):
    files = _configured_source_files(root, rule)
    destination = str(rule.get("destination") or "rtc_nw_rcv_buffer")
    source = str(rule.get("source") or "nw_rcv_buffer")
    start = int(rule.get("startIndex", 9)); end = int(rule.get("endIndex", 27))
    if not files:
        return result(rule["id"], rule["name"], "NOT FOUND", rule["expected"], "Packet cyclic source was not found.")
    found: dict[int, dict[str, Any]] = {}
    wrong = []
    pattern = re.compile(rf"{re.escape(destination)}\s*\[\s*(\d+)\s*\]\s*:=\s*{re.escape(source)}\s*\[\s*(\d+)\s*\]\s*;", re.I)
    for path in files:
        text = read_text(path); clean = _strip_plc_comments(text)
        for match in pattern.finditer(clean):
            dest_index, source_index = int(match.group(1)), int(match.group(2))
            if start <= dest_index <= end:
                item = _source_evidence(root, path, text, match.start(), f"index {dest_index}", match.group(0), _line_number(clean, match.start()))
                item["sourceIndex"] = source_index
                found[dest_index] = item
                if source_index != dest_index:
                    wrong.append({"destinationIndex": dest_index, "sourceIndex": source_index, "file": item["file"], "line": item["line"]})
    missing = [index for index in range(start, end + 1) if index not in found]
    ok = not missing and not wrong
    evidence = [found[index] for index in sorted(found)]
    if missing: evidence.append({"check": "continuous index range", "status": "MISSING", "indexes": missing})
    if wrong: evidence.append({"check": "matching source/destination indexes", "status": "INCORRECT", "indexes": wrong})
    return result(rule["id"], rule["name"], "PASS" if ok else "FAIL", rule["expected"],
                  f"Found {len(found)} of {end - start + 1} required RTC assignments.", evidence,
                  [f"Restore the missing or incorrect {destination}[{start}..{end}] assignments."] if not ok else [],
                  sorted({item["file"] for item in found.values()}))


def _branch_with_location(text: str, group_code: int):
    clean = _strip_plc_comments(text)
    case = re.search(r"CASE\s+nw_group_code\s+OF(.*?)(?:END_CASE)", clean, re.I | re.S)
    if not case:
        return None
    body = case.group(1)
    starts = list(re.finditer(r"(?:^|\n)\s*([0-9]+(?:\s*,\s*[0-9]+)*)\s*:\s*", body))
    for index, start_match in enumerate(starts):
        codes = {int(value) for value in re.split(r"\s*,\s*", start_match.group(1))}
        if group_code not in codes:
            continue
        segment_end = starts[index + 1].start() if index + 1 < len(starts) else len(body)
        absolute_start = case.start(1) + start_match.end()
        return clean[absolute_start:case.start(1) + segment_end], absolute_start
    return None


def _machine_status_checkpoint(root: Path, rule: dict[str, Any]):
    variable = str(rule.get("variable") or "MMS_MACHINE_STATUS")
    size = int(rule.get("size", 4)); group_code = int(rule.get("groupCode", 20))
    packet_files = _configured_source_files(root, rule)
    packet_evidence = None
    for path in packet_files:
        text = read_text(path); branch = _branch_with_location(text, group_code)
        if not branch: continue
        segment, start_pos = branch
        match = re.search(rf"memcpy\s*\(.*?ADR\s*\(\s*{re.escape(variable)}\s*\)\s*,\s*{size}\s*\)\s*;\s*nw_i\s*:=\s*nw_i\s*\+\s*{size}\s*;", segment, re.I | re.S)
        if match:
            absolute=start_pos+match.start()
            packet_evidence = _source_evidence(root, path, text, absolute, f"Group {group_code} packet mapping", match.group(0), _line_number(_strip_plc_comments(text), absolute))
            break
    logic_files = [p for p in all_files(root) if p.suffix.lower() in {'.st', '.src'}]
    logic_pattern = (rf"IF\s*\(?\s*MACHINE_RUNTIME\.START\s*\)?\s*THEN\s*{re.escape(variable)}\s*:=\s*1\s*;"
                     rf".*?ELSE\s*{re.escape(variable)}\s*:=\s*0\s*;.*?END_IF")
    logic_evidence = _find_pattern_evidence(root, logic_files, logic_pattern, "machine runtime status assignment")
    declaration_files = [p for p in all_files(root) if p.suffix.lower() in {'.var', '.typ', '.st', '.src', '.c'}]
    declaration_pattern = rf"\b{re.escape(variable)}\b[^;\r\n]*:\s*(DINT|REAL)\b"
    declaration_evidence = _find_pattern_evidence(root, declaration_files, declaration_pattern, "DINT or REAL declaration", re.I)
    evidence = [item for item in (packet_evidence, logic_evidence, declaration_evidence) if item]
    if not packet_evidence:
        observed_packet=_find_pattern_evidence(root,packet_files,rf"memcpy\s*\(.*?ADR\s*\(\s*{re.escape(variable)}\s*\)\s*,\s*\d+\s*\)\s*;\s*nw_i\s*:=\s*nw_i\s*\+\s*\d+\s*;","observed machine-status packet mapping")
        if observed_packet: evidence.append(observed_packet)
    if not logic_evidence:
        observed_logic=_find_pattern_evidence(root,logic_files,rf"IF[^\r\n]*\.START[^\r\n]*THEN\s*{re.escape(variable)}\s*:=\s*\d+\s*;","observed machine-status assignment")
        if observed_logic: evidence.append(observed_logic)
    if not declaration_evidence:
        observed_declaration=_find_pattern_evidence(root,declaration_files,rf"\b{re.escape(variable)}\b[^;\r\n]*:\s*([A-Za-z_][A-Za-z0-9_]*)\b","observed machine-status declaration",re.I)
        if observed_declaration: evidence.append(observed_declaration)
    missing = []
    if not packet_evidence: missing.append(f"Group {group_code} memcpy({variable}, {size}) and nw_i increment")
    if not logic_evidence: missing.append("MACHINE_RUNTIME.START assignment logic")
    if not declaration_evidence: missing.append(f"{variable} DINT or REAL declaration")
    if missing: evidence.append({"check": "required components", "status": "MISSING", "items": missing})
    return result(rule["id"], rule["name"], "PASS" if not missing else "FAIL", rule["expected"],
                  "Packet mapping, runtime assignment, and declaration use the same PLC variable." if not missing else "One or more machine-status requirements are missing.",
                  evidence, ["Restore the missing machine-status mapping, assignment, or declaration using one consistent PLC variable."] if missing else [],
                  sorted({item["file"] for item in evidence if isinstance(item, dict) and item.get("file")}))


def _product_code_checkpoint(root: Path, rule: dict[str, Any]):
    variable = str(rule.get("variable") or "Blow_room_product_code")
    size = int(rule.get("size", 2)); excluded = {int(x) for x in rule.get("excludeGroupCodes", [11])}
    files = _configured_source_files(root, rule)
    rows=[]; failures=[]; sources=set()
    for path in files:
        text = read_text(path); clean = _strip_plc_comments(text)
        branches = parse_case_branches(clean)
        for code, segment in sorted(branches.items()):
            if code in excluded: continue
            first = re.search(r"memcpy\s*\(.*?ADR\s*\(\s*([^\)]+)\s*\).*?ADR\s*\(\s*([^\)]+)\s*\).*?,\s*(\d+)\s*\)\s*;", segment, re.I | re.S)
            first_variable = first.group(2).strip() if first else None
            first_size = int(first.group(3)) if first else None
            increment = bool(first and re.search(rf"{re.escape(first.group(0))}\s*nw_i\s*:=\s*nw_i\s*\+\s*{size}\s*;", segment, re.I | re.S))
            ok = bool(first and variable.casefold() in (first_variable or '').casefold() and first_size == size and increment)
            row={"groupCode":code,"file":str(path.relative_to(root)),"firstVariable":first_variable,"size":first_size,"increment":size if increment else None,"status":"PASS" if ok else "FAIL"}
            rows.append(row); sources.add(row["file"])
            if not ok: failures.append(code)
    status = "PASS" if rows and not failures else ("NOT FOUND" if not rows else "FAIL")
    return result(rule["id"], rule["name"], status, rule["expected"],
                  f"Checked {len(rows)} active Group Code branches; {len(failures)} failed.", rows,
                  [f"Correct the first Product Code mapping in Group Codes: {sorted(set(failures))}"] if failures else [], sorted(sources))


def _logic_match(text: str, expected: str):
    """Match complete IEC tokens, preserving string contents and source offsets."""
    if re.match(r'\s*<[A-Za-z!?]', expected):
        # XML values and URLs are literal; PLC comment stripping would truncate
        # http:// values, and case folding would silently accept different labels.
        xml_tokens = r'"[^"]*"|\x27[^\x27]*\x27|[A-Za-z_][\w:.-]*|[^\s]'
        clean_xml = re.sub(r'<!--.*?-->', lambda m: ' ' * len(m.group()), text, flags=re.S)
        clean_expected = re.sub(r'<!--.*?-->', '', expected, flags=re.S)
        source = list(re.finditer(xml_tokens, clean_xml))
        wanted = re.findall(xml_tokens, clean_expected)
        values = [token.group() for token in source]
        if not wanted: return None
        for index in range(len(values)-len(wanted)+1):
            if values[index:index+len(wanted)] == wanted:
                return source[index].start(), source[index+len(wanted)-1].end()
        return None
    token_pattern = r"'(?:[^']|'')*'|[A-Za-z_]\w*|\d+(?:\.\d+)?|:=|<=|>=|<>|\S"
    # Preserve character offsets so evidence excerpts point to the original source.
    clean_source = re.sub(r"\(\*.*?\*\)", lambda m: re.sub(r"[^\r\n]", " ", m.group()), text, flags=re.S)
    clean_source = re.sub(r"//[^\r\n]*", lambda m: " " * len(m.group()), clean_source)
    source = list(re.finditer(token_pattern, clean_source))
    wanted = [m.group(0) for m in re.finditer(token_pattern, _strip_plc_comments(expected))]
    def canonical(value):
        return value if value.startswith("'") else value.casefold()
    values = [canonical(m.group(0)) for m in source]
    wanted = [canonical(value) for value in wanted]
    if not wanted: return None
    for index in range(len(values)-len(wanted)+1):
        if values[index:index+len(wanted)] == wanted:
            return source[index].start(), source[index+len(wanted)-1].end()

    # A configured IF may intentionally describe only the condition and the
    # required statements. Allow other project statements (including nested IF
    # blocks) inside that same outer IF, while still requiring the configured
    # statements in order and as complete token sequences.
    trailing = len(wanted) - 1 if wanted and wanted[-1] == ';' else len(wanted)
    if len(wanted) < 4 or wanted[0] != 'if' or wanted[trailing-1] != 'end_if':
        return None
    try:
        expected_then = wanted.index('then', 1, trailing-1)
    except ValueError:
        return None
    expected_body = wanted[expected_then+1:trailing-1]
    # Keep this relaxed form unambiguous. A configured nested IF must still use
    # the existing complete-token match above.
    if any(token in {'if','elsif','else','end_if'} for token in expected_body):
        return None
    statements=[]
    cursor=0
    for index,token in enumerate(expected_body):
        if token == ';':
            statement=expected_body[cursor:index+1]
            if statement: statements.append(statement)
            cursor=index+1
    if expected_body[cursor:]:
        statements.append(expected_body[cursor:])
    if not statements:
        return None

    expected_condition=wanted[1:expected_then]
    for opening in range(len(values)):
        if values[opening] != 'if':
            continue
        try:
            source_then=values.index('then',opening+1)
        except ValueError:
            break
        if values[opening+1:source_then] != expected_condition:
            continue
        depth=1;closing=None
        for index in range(source_then+1,len(values)):
            if values[index] == 'if': depth += 1
            elif values[index] == 'end_if':
                depth -= 1
                if depth == 0:
                    closing=index
                    break
        if closing is None:
            continue
        search_from=source_then+1
        matched=True
        for statement in statements:
            location=None
            for index in range(search_from,closing-len(statement)+1):
                if values[index:index+len(statement)] == statement:
                    location=index
                    break
            if location is None:
                matched=False
                break
            search_from=location+len(statement)
        if matched:
            return source[opening].start(), source[closing].end()
    return None


def _configured_rule_paths(root: Path, rule: dict[str, Any]):
    requested=rule.get('sourceFiles') or ([rule.get('subroutine') or rule.get('sourceFile')] if rule.get('subroutine') or rule.get('sourceFile') else [])
    if isinstance(requested,str): requested=re.split(r'[\r\n,;]+',requested)
    requested=[str(value).replace('\\','/').strip().casefold() for value in requested if str(value).strip()] if isinstance(requested,list) else []
    if not requested: return []
    names={Path(value).name for value in requested}
    if names & {'mms_nw_rcyclic.st','mms_nw_r.src'}: names.update({'mms_nw_rcyclic.st','mms_nw_r.src'})
    found=[]
    for path in all_files(root):
        if path.suffix.casefold() not in {'.st','.src','.ab','.ld','.fun','.c'}: continue
        relative=path.relative_to(root).as_posix().casefold()
        if any((relative==value or relative.endswith('/'+value)) if '/' in value else path.name.casefold()==value or (value in {'mms_nw_rcyclic.st','mms_nw_r.src'} and path.name.casefold() in names) for value in requested):
            found.append(path)
    return found


def _cross_function_logic_checks(root: Path, rule: dict[str, Any], exclude_paths=()):
    """Check required logic snippets in one or more other PLC subroutines."""
    checks=rule.get('crossFunctionChecks') or []
    if not isinstance(checks,list) or not checks:
        return [],[]
    source_suffixes={'.st','.src','.ab','.ld','.fun','.c','.var','.typ','.page','.pages','.xml',
                     '.txtgrp','.algrp','.layer','.tpr','.hwl','.iom','.sw','.hw','.set','.osl',
                     '.apj','.gdm','.cfg','.pkg','.lby','.vcvk'}
    excluded={Path(path).resolve() for path in exclude_paths if path}
    ignored_dirs={'temp','as','binaries','diagnosis','.git','.svn','archive','archives','backup','backups'}
    all_logic=[path for path in all_files(root) if path.suffix.casefold() in source_suffixes and not any(part.casefold() in ignored_dirs for part in path.relative_to(root).parts[:-1])]
    source_cache={}
    def source_text(path):
        if path not in source_cache: source_cache[path]=read_text(path)
        return source_cache[path]
    evidence=[]; failures=[]
    for index,check in enumerate(checks):
        if not isinstance(check,dict):
            label=f'Cross-function check {index+1}'
            failures.append(label)
            evidence.append({'crossFunctionIndex':index,'check':label,'status':'MISSING','expected':'Configured PLC logic','actual':'Check configuration must be an object.'})
            continue
        label=str(check.get('name') or f'Cross-function check {index+1}').strip()
        alternatives=expected_logic(check)
        requested=check.get('sourceFiles') or ([check.get('subroutine') or check.get('sourceFile')] if check.get('subroutine') or check.get('sourceFile') else [])
        if isinstance(requested,str): requested=re.split(r'[\r\n,;]+',requested)
        requested=[str(value).replace('\\','/').strip().casefold() for value in requested if str(value).strip()] if isinstance(requested,list) else []
        search_all=bool(check.get('searchAllSubroutines'))
        if search_all:
            candidates=[path for path in all_logic if path.resolve() not in excluded]
        elif requested:
            candidates=[]
            for path in all_logic:
                # An explicit reference may check another control in the main HMI file.
                relative=path.relative_to(root).as_posix().casefold()
                if any((relative==name or relative.endswith('/'+name)) if '/' in name else path.name.casefold()==name for name in requested):
                    candidates.append(path)
        else:
            candidates=[]
        matched=None
        if alternatives:
            for path in candidates:
                text=source_text(path)
                clean=_strip_plc_comments(text) if path.suffix.casefold() in {'.st','.src','.ab','.ld','.fun','.c','.var','.typ'} else text
                segment=clean; start=0
                if check.get('groupCode') is not None:
                    try: branch=_branch_with_location(text,int(check['groupCode']))
                    except (TypeError,ValueError): branch=None
                    if not branch: continue
                    segment,start=branch
                match_source=_strip_plc_comments(segment) if path.suffix.casefold() in {'.st','.src','.ab','.ld','.fun','.c','.var','.typ'} else segment
                for alternative_index,alternative in enumerate(alternatives):
                    hit=_logic_match(segment,alternative)
                    if not hit: continue
                    line=_line_number(clean,start+hit[0])
                    actual_logic=match_source[hit[0]:hit[1]]
                    matched=_source_evidence(root,path,text,0,f'{label} · accepted logic {alternative_index+1}',actual_logic,line)
                    matched.update({'crossFunctionIndex':index,'status':'PASS','name':label,'expected':alternative,'actual':'Configured source found in the related file.','matchedLogic':actual_logic})
                    break
                if matched: break
        if matched:
            evidence.append(matched)
        else:
            failures.append(label)
            if not alternatives:
                actual='No accepted logic block is configured for this cross-function check.'
            elif not candidates:
                actual='No related project file matched the configured search scope.'
            else:
                actual='None of the accepted logic blocks was found in the configured other subroutines.'
            evidence.append({'crossFunctionIndex':index,'check':label,'name':label,'status':'MISSING','expected':alternatives,'actual':actual,'searchedFiles':[path.relative_to(root).as_posix() for path in candidates]})
    if rule.get('crossFunctionMode','all') == 'any' and any(row.get('status') == 'PASS' for row in evidence):
        for row in evidence:
            if row.get('status') != 'PASS':
                row.update(alternativeStatus=row.get('status'),status='NOT_REQUIRED',
                           notRequiredReason='Another complete OR cross reference passed; this alternative is not required.')
        failures=[]
    return evidence,failures


def _lot_name_checkpoint(root: Path, rule: dict[str, Any]):
    import xml.etree.ElementTree as ET
    group_code=int(rule.get('groupCode',140))
    alternatives=expected_logic(rule)
    if not alternatives:
        alternatives=[
            'memcpy(ADR(nw_snd_buffer[nw_i]),ADR(PMS_Lotname_Shift[0]),20); stringlength:=strlen(ADR(PMS_Lotname_Shift[0])); memset(ADR(nw_snd_buffer[nw_i+stringlength]),0,50-stringlength); nw_i:=nw_i+50;',
            'memcpy(ADR(nw_snd_buffer[nw_i]),ADR(PMS_Lot_Name_Temp),50); stringlength:=strlen(ADR(PMS_Lotname_Shift[0])); memset(ADR(nw_snd_buffer[nw_i+stringlength]),0,50-stringlength); nw_i:=nw_i+50;',
        ]
    evidence=[]; packet_hits=[]
    packet_sources=_configured_source_files(root,rule)
    for path in packet_sources:
        text=read_text(path); branch=_branch_with_location(text,group_code)
        if not branch: continue
        segment,start=branch
        for index,alternative in enumerate(alternatives):
            hit=_logic_match(segment,alternative)
            variable=re.search(r'memcpy\s*\(\s*ADR\s*\(\s*nw_snd_buffer\s*\[\s*nw_i\s*\]\s*\)\s*,\s*ADR\s*\(\s*([\w.]+(?:\s*\[\s*\d+\s*\])?)\s*\)',alternative,re.I)
            if not hit or not variable: continue
            line=_line_number(_strip_plc_comments(text),start+hit[0])
            item=_source_evidence(root,path,text,0,f'Group {group_code} accepted alternative {index+1}',alternative,line)
            item['packetVariable']=re.sub(r'\s+','',variable.group(1)); packet_hits.append(item); evidence.append(item)
    prefix=str(rule.get('pagePrefix') or 'Process').casefold()
    pages=[p for p in all_files(root) if p.suffix.lower() in {'.page','.pages'} and p.stem.casefold().startswith(prefix)]
    cross_evidence,cross_failures=_cross_function_logic_checks(root,rule,packet_sources)
    evidence.extend(cross_evidence)
    variable_flows=[]
    for item in cross_evidence:
        if item.get('status')!='PASS': continue
        for flow in re.finditer(r'([A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*(?:\s*\[\s*\d+\s*\])?)\s*:=\s*([A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*(?:\s*\[\s*\d+\s*\])?)\s*;',str(item.get('matchedLogic') or ''),re.I):
            variable_flows.append((re.sub(r'\s+','',flow.group(1)).casefold(),re.sub(r'\s+','',flow.group(2)).casefold()))
    target_results={}; matches=[]
    def tag(node): return node.tag.split('}')[-1]
    def normalized_variable(value):
        value=re.sub(r'\s+','',value).casefold()
        # A string array's first element and its root address refer to the same buffer.
        return re.sub(r'\[0\]$','',value)
    for path in pages:
        relative=path.relative_to(root)
        parts=relative.parts; logical=next((i for i,x in enumerate(parts) if x.casefold()=='logical'),-1)
        target=parts[logical+1] if logical>=0 and len(parts)>logical+1 else str(relative.parent)
        target_results.setdefault(target,False)
        text=read_text(path)
        try: page=ET.fromstring(text)
        except ET.ParseError as error:
            evidence.append({'check':'HMI XML','file':str(relative),'status':'FAIL','actual':str(error)}); continue
        label=str(rule.get('label') or 'LOT NAME').casefold()
        label_ok=any(tag(node)=='Text' and str(node.get('Value') or node.text or '').strip().casefold()==label for node in page.iter())
        for control in page.iter():
            if tag(control)!='Control': continue
            name=control.get('Name','')
            if not name.strip().casefold().startswith(str(rule.get('controlNamePrefix') or 'String').casefold()): continue
            props={node.get('Name'):node.get('Value','') for node in control if tag(node)=='Property'}
            datapoint=props.get('ValueDatapoint','')
            binding=re.search(r'Variable\[(.*)\]$',datapoint,re.I)
            bound=normalized_variable(binding.group(1)) if binding else ''
            def same_variable(left,right):
                left=normalized_variable(left); right=normalized_variable(right)
                return bool(left and right and (left==right or left.endswith('.'+right) or right.endswith('.'+left)))
            def linked(packet_variable):
                packet=normalized_variable(packet_variable)
                # Follow assignments backwards from the packet source. For example,
                # Shift[0] := Lot_Name_Temp means an HMI bound to Lot_Name_Temp feeds
                # the value that the packet reads from Shift[0]. Multiple configured
                # cross-function checks may describe a multi-step assignment chain.
                pending=[packet]; visited=[]
                while pending:
                    current=pending.pop()
                    if same_variable(bound,current): return True
                    if any(same_variable(current,prior) for prior in visited): continue
                    visited.append(current)
                    pending.extend(source for destination,source in variable_flows
                                   if same_variable(destination,current)
                                   and not any(same_variable(source,prior) for prior in visited))
                return False
            same=next((hit for hit in packet_hits if bound and linked(hit['packetVariable'])),None)
            expected_props={} if rule.get('explicitHmiProperties') else {'Input':'True','InputTouchpad':rule.get('inputTouchpad') or 'Source[local].TouchPad[AlphaPadQVGA]'}
            expected_props.update(rule.get('requiredProperties') or {})
            property_details=compare_control(control,{'properties':expected_props})
            checks={'label':label_ok,'sameVariable':bool(same),**{key:value['status']=='PASS' for key,value in property_details.items()}}
            position=text.find('Name="'+name+'"')
            item=_source_evidence(root,path,text,max(0,position),'Lot Name control')
            item.update({'control':name,'target':target,'datapoint':datapoint,'properties':checks,'propertyComparisons':property_details,'status':'PASS' if all(checks.values()) else 'FAIL'})
            evidence.append(item)
            if all(checks.values()): target_results[target]=True;matches.append(item)
    missing=[]
    if not packet_hits: missing.append(f'Group {group_code}: neither complete ST alternative found')
    if cross_failures: missing.append('Cross-function logic missing: '+', '.join(cross_failures))
    if not pages: missing.append(f'No {rule.get("pagePrefix") or "Process"}* HMI page found')
    missing.extend('No matching String control in HMI target '+target for target,ok in target_results.items() if not ok)
    if rule.get('hmiControlChecks'):
        structured=_hmi_property_checkpoint(root,rule,pages)
        evidence.extend(structured['evidence'])
        if structured['status']!='PASS':missing.append(structured['actual'])
    if rule.get('variable') and rule.get('allowedDatatypes'):
        declaration_rule={**rule,'kind':'exact_logic_declaration'}
        declaration=_exact_logic_declaration(root,declaration_rule)
        evidence.extend(declaration['evidence'])
        if declaration['status']!='PASS': missing.append(declaration['actual'])
    output=result(rule['id'],rule['name'],'FAIL' if missing else 'PASS',rule['expected'],
                  '; '.join(missing) if missing else 'Accepted Group Code logic and matching String input found in each HMI target.',
                  evidence,['Review the missing logic or the properties of the same String control.'] if missing else [],
                  sorted({item['file'] for item in evidence if item.get('file')}))
    output['crossFunctionLogicChecks']=cross_evidence
    return output


def _hmi_page_structure_checkpoint(root: Path, rule: dict[str, Any]):
    accepted={str(x).casefold() for x in rule.get("acceptedPageNames", ["MMS_CONFIG.page", "MMS_CONFIG.pages"])}
    logic_alternatives=expected_logic(rule)
    candidates=[p for p in all_files(root) if p.name.casefold() in accepted]
    if not candidates:
        return result(rule["id"],rule["name"],"NOT FOUND",rule["expected"],"MMS_CONFIG page was not found.",
                      evidence=[{"check":"page presence","status":"MISSING","acceptedNames":sorted(accepted)}],
                      recommendations=["Add the MMS_CONFIG HMI page or configure its accepted filename."])
    evidence=[]; complete=False
    for path in candidates:
        text=read_text(path)
        properties={name:bool(re.search(re.escape(name),text,re.I)) for name in ("IndexDatapoint","LockingDatapoint","TextGroup")}
        objects={
            "text": bool(re.search(r"<(?:Text|TextLayer)\b",text,re.I)),
            "numeric": bool(re.search(r"(?:Numeric|Number|ClassId\s*=\s*[\"']0x[0-9A-F]+)",text,re.I)),
            "control": bool(re.search(r"<Control\b",text,re.I)),
            "hotspot": bool(re.search(r"Hot\s*Spot|HotSpot",text,re.I)),
        }
        logic_hit=next(((index,alternative,_logic_match(text,alternative)) for index,alternative in enumerate(logic_alternatives)
                        if _logic_match(text,alternative)),None)
        logic_ok=not logic_alternatives or logic_hit is not None
        ok=all(properties.values()) and all(objects.values()) and logic_ok
        complete=complete or ok
        row={"check":"MMS_CONFIG page structure","file":str(path.relative_to(root)),"properties":properties,"objects":objects,"status":"PASS" if ok else "FAIL"}
        if logic_alternatives:
            row.update({"logicStatus":"PASS" if logic_ok else "MISSING",
                        "expectedLogic":logic_alternatives,
                        "matchedAlternative":logic_hit[0]+1 if logic_hit else None,
                        "actualLogic":logic_hit[1] if logic_hit else "None of the accepted HMI logic blocks was found."})
        evidence.append(row)
    return result(rule["id"],rule["name"],"PASS" if complete else "FAIL",rule["expected"],
                  "MMS_CONFIG page and required objects/properties were found." if complete else "MMS_CONFIG exists but required objects or properties are missing.",
                  evidence,["Restore the missing Text, Numeric, Control, HotSpot, IndexDatapoint, LockingDatapoint, or TextGroup configuration."] if not complete else [],
                  [str(p.relative_to(root)) for p in candidates])


def _normalized_logic(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def _checklist_source_files(root: Path, configured: str) -> list[Path]:
    value=(configured or '').replace('\\','/').casefold()
    if value in {'mms_nw_rcyclic.st','mms_nw_r/cyclic.st'}:
        return packet_source_files(root,'mms_nw_rCyclic.st')
    if value=='mms_pms/cyclic.st':
        return [p for p in all_files(root) if p.name.casefold()=='cyclic.st' and p.parent.name.casefold()=='mms_pms']
    if value=='global declaration files':
        return [p for p in all_files(root) if p.suffix.casefold() in {'.var','.typ','.c'}]
    name=Path(value).name
    return [p for p in all_files(root) if p.name.casefold()==name]


def _group_code_exact_logic(root: Path, rule: dict[str, Any]):
    """Every selected CASE branch must contain one complete accepted block."""
    files=_configured_rule_paths(root,rule)
    mode=str(rule.get('groupCodeMode') or 'all')
    configured={int(value) for value in rule.get('groupCodes') or []}
    branches=[(path,branch) for path in files for branch in _parse_case_group_branches(read_text(path))]
    groups=configured if mode=='selected' else {branch['groupCode'] for _,branch in branches}-(configured if mode=='exclude' else set())
    alternatives=expected_logic(rule)
    evidence=[]
    for group in sorted(groups):
        selected=[(path,branch) for path,branch in branches if branch['groupCode']==group]
        if not selected:
            evidence.append({'groupCode':group,'status':'MISSING','check':'Group Code presence','expected':alternatives})
        for path,branch in selected:
            matched=next(((index,hit) for index,block in enumerate(alternatives) if (hit:=_logic_match(branch['segment'],block))),None)
            evidence.append({'groupCode':group,'file':path.relative_to(root).as_posix(),'line':branch['line'],
                             'check':'Complete accepted source block','status':'PASS' if matched else 'FAIL',
                             'expectedLogic':alternatives,'matchedAlternative':matched[0]+1 if matched else None,
                             'actualLogic':branch['segment'][matched[1][0]:matched[1][1]] if matched else branch['segment']})
    failures=sum(item['status']!='PASS' for item in evidence)
    return result(rule['id'],rule['name'],'PASS' if evidence and not failures else 'FAIL' if evidence else 'NOT FOUND',rule.get('expected',''),
                  f'Checked {len(evidence)} branches in {len(groups)} Group Codes; {failures} failed.',evidence,
                  ['Restore one complete accepted block in each failed Group Code.'] if failures else [],
                  sorted({path.relative_to(root).as_posix() for path in files}))


def _checklist_packet_signatures(root: Path, rule: dict[str, Any]):
    files=_checklist_source_files(root,str(rule.get('sourceFile') or 'mms_nw_rCyclic.st'))
    mode=str(rule.get('groupCodeMode') or 'selected').casefold()
    configured_groups=[int(value) for value in rule.get('groupCodes') or []]
    if mode in {'all','exclude'}:
        discovered=set()
        for path in files:
            discovered.update(item['groupCode'] for item in _parse_case_group_branches(read_text(path)))
        excluded=set(configured_groups) if mode=='exclude' else set()
        groups=sorted(discovered-excluded)
    else:
        groups=configured_groups
    required=rule.get('requiredParameters') or []
    if not files:
        return result(rule['id'],rule['name'],'NOT FOUND',rule.get('expected',''),
                      f"Configured source file {rule.get('sourceFile')} was not found.",
                      recommendations=['Confirm the checklist source file before enabling this rule.'])
    evidence=[]; failures=[]; sources=set(); found_branches=0
    for group_code in groups:
        branch_found=False
        for path in files:
            text=read_text(path)
            branches=[item for item in _parse_case_group_branches(text) if item['groupCode']==group_code]
            if not branches: continue
            branch_found=True; found_branches+=1; sources.add(str(path.relative_to(root)))
            branch=branches[0]
            actual=_extract_memcpy_parameters(branch['segment'],branch['originalSegment'],branch['line'])
            for expected in required:
                target=_normalized_logic(str(expected.get('parameter') or ''))
                match=next((item for item in actual if _normalized_logic(item.get('parameter',''))==target),None)
                expected_size=int(expected.get('size') or 0)
                expected_increment=expected.get('increment')
                ok=bool(match and match.get('memcpySize')==expected_size and
                        (expected_increment is None or match.get('incrementValue')==int(expected_increment)))
                line=branch['line']
                if match:
                    pos=branch['originalSegment'].casefold().find(str(match.get('parameter','')).casefold())
                    if pos>=0: line+=branch['originalSegment'].count('\n',0,pos)
                item={
                    'check':f"Group {group_code} parameter",
                    'groupCode':group_code,
                    'parameter':expected.get('parameter'),
                    'expectedSize':expected_size,
                    'actualSize':match.get('memcpySize') if match else None,
                    'expectedIncrement':expected_increment,
                    'actualIncrement':match.get('incrementValue') if match else None,
                    'file':str(path.relative_to(root)),
                    'line':line,
                    'status':'PASS' if ok else 'FAIL',
                }
                evidence.append(item)
                if not ok: failures.append({'groupCode':group_code,'parameter':expected.get('parameter')})
            break
        if not branch_found:
            failures.append({'groupCode':group_code,'parameter':'Group branch'})
            evidence.append({'check':f'Group {group_code} branch','groupCode':group_code,'status':'NOT FOUND'})
    status='PASS' if groups and not failures else ('NOT FOUND' if not found_branches else 'FAIL')
    return result(rule['id'],rule['name'],status,rule.get('expected',''),
                  f"Checked {len(required)} required parameter signatures across {len(groups)} Group Code(s); {len(failures)} mismatch(es).",
                  evidence,
                  ['Review the failed parameter, memcpy size, cursor increment, or missing Group Code before approving this checklist rule.'] if failures else [],
                  sorted(sources))


def _checklist_source_signatures(root: Path, rule: dict[str, Any]):
    files=_checklist_source_files(root,str(rule.get('sourceFile') or ''))
    snippets=[str(value) for value in rule.get('requiredSnippets') or []]
    declarations=rule.get('requiredDeclarations') or []
    if not files:
        return result(rule['id'],rule['name'],'NOT FOUND',rule.get('expected',''),
                      f"Configured source file {rule.get('sourceFile')} was not found.")
    evidence=[]; missing=[]; sources=set()
    for snippet in snippets:
        hit=None
        for path in files:
            text=read_text(path); normalized=_normalized_logic(_strip_plc_comments(text)); target=_normalized_logic(snippet)
            if target and target in normalized:
                compact_line=re.sub(r'\s+',' ',snippet).strip()
                first_token=re.split(r'\s*:=|\s+',compact_line,1)[0]
                match=re.search(re.escape(first_token),text,re.I)
                hit={'check':'source statement','snippet':compact_line[:500],'file':str(path.relative_to(root)),'line':_line_number(text,match.start()) if match else 1,'status':'PASS'}
                sources.add(hit['file']); break
        if hit: evidence.append(hit)
        else:
            missing.append(snippet)
            evidence.append({'check':'source statement','snippet':re.sub(r'\s+',' ',snippet).strip()[:500],'status':'NOT FOUND'})
    for declaration in declarations:
        variable=str(declaration.get('variable') or ''); datatype=str(declaration.get('datatype') or '')
        lower=int(declaration.get('lowerBound',0)); upper=int(declaration.get('upperBound',0)); hit=None
        pattern=rf"\b{re.escape(variable)}\b(?:\s+AT\s+%[A-Z]+\d*)?\s*:\s*ARRAY\s*\[\s*{lower}\s*\.\.\s*{upper}\s*\]\s*OF\s*{re.escape(datatype)}\b"
        for path in files:
            text=read_text(path); match=re.search(pattern,text,re.I)
            if match:
                hit={'check':'array declaration','variable':variable,'datatype':datatype,'bounds':f'{lower}..{upper}','file':str(path.relative_to(root)),'line':_line_number(text,match.start()),'status':'PASS'}
                sources.add(hit['file']); break
        if hit: evidence.append(hit)
        else:
            missing.append(f'{variable} ARRAY[{lower}..{upper}] OF {datatype}')
            evidence.append({'check':'array declaration','variable':variable,'datatype':datatype,'bounds':f'{lower}..{upper}','status':'NOT FOUND'})
    requirement_count=len(snippets)+len(declarations)
    status='PASS' if requirement_count and not missing else ('NOT FOUND' if not requirement_count else 'FAIL')
    return result(rule['id'],rule['name'],status,rule.get('expected',''),
                  f"Found {requirement_count-len(missing)} of {requirement_count} required source statements/declarations.",evidence,
                  ['Confirm the source file and missing executable statements or declarations before approving this checklist rule.'] if missing or not requirement_count else [],sorted(sources))


# ---------------------------------------------------------------------------
# Configurable rule modules
# ---------------------------------------------------------------------------

def _strip_plc_comments(text: str) -> str:
    """Remove IEC/B&R comments while preserving line positions."""
    text = re.sub(r"\(\*.*?\*\)", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"//[^\r\n]*", "", text)
    return text


def _line_number(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _clean_identifier(expr: str) -> str:
    expr = re.sub(r"\s+", " ", expr or "").strip()
    expr = re.sub(r"^\(\*.*?\*\)\s*", "", expr, flags=re.S)
    return expr


def _extract_comment_before(original: str, pos: int) -> str:
    """Return the closest trailing/preceding (* ... *) comment for an item."""
    prefix = original[max(0, pos - 350):pos]
    comments = list(re.finditer(r"\(\*\s*(.*?)\s*\*\)", prefix, re.S))
    if comments:
        return re.sub(r"\s+", " ", comments[-1].group(1)).strip()
    return "No Description"


def _parse_case_group_branches(original: str):
    """Discover active CASE nw_group_code branches while preserving source lines."""
    clean = _strip_plc_comments(original)
    clean_lines = clean.splitlines()
    original_lines = original.splitlines()
    out = []
    i = 0
    while i < len(clean_lines):
        if not re.search(r"\bCASE\s+nw_group_code\s+OF\b", clean_lines[i], re.I):
            i += 1
            continue
        case_start = i
        i += 1
        labels = []
        while i < len(clean_lines):
            line = clean_lines[i]
            if re.search(r"\bEND_CASE\b", line, re.I):
                break
            m = re.match(r"^\s*([0-9]+(?:\s*,\s*[0-9]+)*)\s*:\s*", line)
            if m:
                labels.append((i, [int(x.strip()) for x in m.group(1).split(",")], m.end()))
            i += 1
        end_case = i
        for idx, (line_no, codes, content_start) in enumerate(labels):
            next_line = labels[idx + 1][0] if idx + 1 < len(labels) else end_case
            # Preserve the label line through the line before the next label.
            original_segment = "\n".join(original_lines[line_no:next_line])
            original_label = original_lines[line_no] if line_no < len(original_lines) else ""
            dm = re.search(r":\s*\(\*\s*(.*?)\s*\*\)", original_label, re.S)
            desc = re.sub(r"\s+", " ", dm.group(1)).strip() if dm else "No Description"
            # Strip the label itself for clean-code processing.
            clean_segment = "\n".join(clean_lines[line_no:next_line])
            clean_segment = re.sub(r"^\s*[0-9]+(?:\s*,\s*[0-9]+)*\s*:\s*", "", clean_segment, count=1)
            for code in codes:
                out.append({
                    "groupCode": code,
                    "description": desc,
                    "segment": clean_segment,
                    "originalSegment": original_segment,
                    "line": line_no + 1,
                    "caseStart": case_start + 1,
                })
        i += 1
    return out

def _find_numeric_assignment(text: str, index: int):
    pat = re.compile(
        rf"\bnw_snd_buffer\s*\[\s*{index}\s*\]\s*:=\s*([^;]+);",
        re.I
    )
    m = pat.search(text)
    if not m:
        return None, None
    expr = m.group(1).strip()
    # Handle simple numeric assignments and common conversion wrappers.
    nums = re.fullmatch(r"(?:USINT_TO_UINT|UINT_TO_USINT|DINT_TO_USINT|INT_TO_USINT)?\s*\(?\s*(\d+)\s*\)?", expr, re.I)
    if nums:
        return int(nums.group(1)), expr
    return None, expr


def _datatype_size(datatype: str, declared_size=None):
    dt = (datatype or "").upper().replace(" ", "")
    if dt.startswith("ARRAY"):
        m = re.search(r"OF(.+)$", dt)
        dt = m.group(1) if m else dt
    sizes = {
        "BOOL": 1, "USINT": 1, "SINT": 1, "BYTE": 1, "CHAR": 1,
        "UINT": 2, "INT": 2, "WORD": 2,
        "UDINT": 4, "DINT": 4, "DWORD": 4, "REAL": 4,
        "ULINT": 8, "LINT": 8, "LWORD": 8, "LREAL": 8,
    }
    if dt.startswith("STRING"):
        m = re.search(r"STRING\((\d+)\)", dt)
        return (int(m.group(1)) if m else 1)
    return sizes.get(dt, declared_size)


def _load_symbol_types(root: Path):
    """Best-effort project symbol/type extraction for rule validation."""
    variables, types = {}, {}
    # Prefer the existing packet engine because it already knows the project
    # symbol formats. Never make the rule engine depend on its implementation.
    try:
        import importlib.util
        p = root
        # Search the local application engine only when available.
        here = Path(__file__).resolve().parent
        packet = here / "packet_validation_report_uSOPp_v1.71_final.py"
        if not packet.exists():
            packet = packet.with_suffix('.pyc')
        if packet.exists():
            spec = importlib.util.spec_from_file_location("_usopp_packet_engine", packet)
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)
            if hasattr(mod, "parse_symbol_files"):
                variables, types = mod.parse_symbol_files(root)
    except Exception:
        pass

    # Small fallback parser for .var/.typ when the packet engine is unavailable.
    for p in all_files(root, ".var"):
        t = read_text(p)
        for m in re.finditer(r"\b([A-Za-z_]\w*)\s*(?:AT\s+%[A-Z]+\d*)?\s*:\s*([A-Za-z_]\w*(?:\s*\(\s*\d+\s*\))?)\s*;", t, re.I):
            variables.setdefault(m.group(1), m.group(2).replace(" ", ""))
    return variables, types


def _extract_memcpy_parameters(segment: str, original: str, base_line: int = 1):
    """Extract memcpy destination, source parameter, size and local offset."""
    rows = []
    pat = re.compile(
        r"\bmemcpy\s*\(\s*ADR\s*\(\s*([^\)]+?)\s*\)\s*,\s*ADR\s*\(\s*([^\)]+?)\s*\)\s*,\s*(\d+)\s*\)\s*;",
        re.I | re.S
    )
    running = 0
    for seq, m in enumerate(pat.finditer(segment), 1):
        dest = _clean_identifier(m.group(1))
        source = _clean_identifier(m.group(2))
        size = int(m.group(3))
        # Source description from the original source near the memcpy close.
        absolute_hint = max(0, min(len(original) - 1, m.start()))
        desc = _extract_comment_before(original, absolute_hint)
        # If no comment was adjacent, inspect immediately after memcpy.
        after = original[absolute_hint:absolute_hint + 250]
        cm = re.search(r";\s*\(\*\s*(.*?)\s*\*\)", after, re.S)
        if cm:
            desc = re.sub(r"\s+", " ", cm.group(1)).strip()
        # Cursor increment immediately after this memcpy.
        tail = segment[m.end():m.end() + 500]
        inc = re.search(r"\bnw_i\s*:=\s*nw_i\s*\+\s*(\d+)\s*;", tail, re.I)
        inc_value = int(inc.group(1)) if inc else None
        rows.append({
            "sequence": seq,
            "parameter": source,
            "description": desc or "No Description",
            "memcpySize": size,
            "runningOffset": running,
            "expectedOffset": running,
            "incrementValue": inc_value,
            "offsetStatus": "PASS" if inc_value == size else ("FAIL" if inc_value is not None else "NOT FOUND"),
            "destination": dest,
        })
        running += size
    return rows


def common_group_packet_validate(root: Path, rule: dict[str, Any], output_excel: Path | None = None):
    """
    Generic SC-COMMON-PACKET implementation.

    Discovery is limited to the configured AS 4.x or AS 2.7 packet source.
    Group numbers, parameter names and packet sizes are never hard-coded.
    """
    target_name = str(rule.get("subroutine", "mms_nw_rCyclic.st"))
    files = packet_source_files(root, target_name)
    if not files:
        return result(
            rule["id"], rule.get("name", "Common Group Code Packet Validation"),
            "NOT FOUND", rule.get("expected", "Active Group Codes shall be validated."),
            f"{target_name} not found.",
            recommendations=[f"Add or configure the packet cyclic source file {target_name}."]
        )

    variables, types = _load_symbol_types(root)
    group_rows, parameter_rows, error_rows = [], [], []
    discovered = 0
    skipped = 0

    for p in files:
        original = read_text(p)
        branches = _parse_case_group_branches(original)
        for b in branches:
            segment = b["segment"]
            original_segment = b.get("originalSegment", segment)
            # Empty/no-memcpy branches are incomplete for this packet rule and
            # are explicitly skipped rather than reported as false failures.
            params = _extract_memcpy_parameters(original_segment, original_segment, b["line"])
            if not params:
                skipped += 1
                continue
            discovered += 1

            b3, b3expr = _find_numeric_assignment(original_segment, 3)
            b4, b4expr = _find_numeric_assignment(original_segment, 4)
            configured = (b3 * 256 + b4) if b3 is not None and b4 is not None else None
            calculated = sum(x["memcpySize"] for x in params)

            group_status = "PASS"
            if configured is None:
                group_status = "FAIL"
                error_rows.append({
                    "Group Code": b["groupCode"], "Parameter": "",
                    "Description": b["description"], "Validation Type": "Packet Size",
                    "Expected": "Numeric nw_snd_buffer[3] and nw_snd_buffer[4]",
                    "Actual": f"[3]={b3expr or 'not found'}, [4]={b4expr or 'not found'}"
                })
            elif configured != calculated:
                group_status = "FAIL"
                error_rows.append({
                    "Group Code": b["groupCode"], "Parameter": "",
                    "Description": b["description"], "Validation Type": "Packet Size",
                    "Expected": calculated, "Actual": configured
                })

            for row in params:
                declared = variables.get(row["parameter"])
                if declared is None:
                    # Some projects expose the type through a symbol type map.
                    declared = types.get(row["parameter"])
                row["dataType"] = str(declared or "NOT FOUND")
                expected_size = _datatype_size(row["dataType"])
                row["expectedDataTypeSize"] = expected_size
                if expected_size is None:
                    dtype_status = "NOT FOUND"
                else:
                    dtype_status = "PASS" if expected_size == row["memcpySize"] else "FAIL"
                if dtype_status == "FAIL":
                    group_status = "FAIL"
                    error_rows.append({
                        "Group Code": b["groupCode"], "Parameter": row["parameter"],
                        "Description": row["description"], "Validation Type": "Data Type",
                        "Expected": f"{row['dataType']} = {expected_size} bytes",
                        "Actual": f"memcpy = {row['memcpySize']} bytes"
                    })
                elif dtype_status == "NOT FOUND":
                    # Missing symbol information is not silently treated as a pass.
                    group_status = "FAIL"
                    error_rows.append({
                        "Group Code": b["groupCode"], "Parameter": row["parameter"],
                        "Description": row["description"], "Validation Type": "Data Type",
                        "Expected": "Resolvable PLC datatype",
                        "Actual": "Datatype not found in project symbols"
                    })

                offset_status = row["offsetStatus"]
                if offset_status != "PASS":
                    group_status = "FAIL"
                    error_rows.append({
                        "Group Code": b["groupCode"], "Parameter": row["parameter"],
                        "Description": row["description"], "Validation Type": "Offset",
                        "Expected": row["memcpySize"], "Actual": row["incrementValue"] if row["incrementValue"] is not None else "Not found"
                    })

                parameter_rows.append({
                    "Group Code": b["groupCode"],
                    "Sequence": row["sequence"],
                    "Parameter": row["parameter"],
                    "Description": row["description"],
                    "Data Type": row["dataType"],
                    "memcpy Size": row["memcpySize"],
                    "Running Offset": row["runningOffset"],
                    "Expected Offset": row["expectedOffset"],
                    "Status": "PASS" if dtype_status == "PASS" and offset_status == "PASS" else "FAIL",
                    "Source File": str(p.relative_to(root)),
                    "Line": b["line"],
                })

            group_rows.append({
                "Group Code": b["groupCode"],
                "Description": b["description"],
                "Configured Bytes": configured if configured is not None else "",
                "Calculated Bytes": calculated,
                "nw_snd_buffer[3]": b3 if b3 is not None else "",
                "nw_snd_buffer[4]": b4 if b4 is not None else "",
                "Total Parameters": len(params),
                "Status": group_status,
                "Source File": str(p.relative_to(root)),
                "Line": b["line"],
            })

    if not group_rows:
        status = "NOT FOUND"
        actual = f"No complete active Group Code branches with memcpy() were found in {target_name}."
    else:
        status = "PASS" if all(x["Status"] == "PASS" for x in group_rows) else "FAIL"
        actual = f"Validated {len(group_rows)} active Group Code branches; skipped {skipped} incomplete branches."

    excel_path = None
    if output_excel:
        excel_path = Path(output_excel)
        _write_common_packet_excel(excel_path, root.name, group_rows, parameter_rows, error_rows)

    r = result(
        rule["id"], rule.get("name", "Common Group Code Packet Validation"), status,
        rule.get("expected", "Every active Group Code in mms_nw_rCyclic.st shall be validated."),
        actual,
        evidence={
            "groups": group_rows,
            "parameters": parameter_rows,
            "errors": error_rows,
            "discoveredGroups": len(group_rows),
            "skippedIncomplete": skipped,
        },
        recommendations=["Review Validation Errors and correct the packet size, datatype or nw_i increment." ] if error_rows else [],
        source_files=[str(p.relative_to(root)) for p in files]
    )
    r["reportStatus"] = "Packet Validation Report Generated Successfully" if excel_path else "Report generation not requested"
    r["reportWorkbook"] = excel_path.name if excel_path else None
    return r


def _write_common_packet_excel(path: Path, project_name: str, groups, parameters, errors):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    from openpyxl.utils import get_column_letter

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "GroupCode Summary"
    headers = ["Group Code","Description","Configured Bytes","Calculated Bytes",
               "nw_snd_buffer[3]","nw_snd_buffer[4]","Total Parameters","Status"]
    ws.append(headers)
    for row in groups:
        ws.append([row.get(h, "") for h in headers])

    ws2 = wb.create_sheet("Parameter Validation")
    headers2 = ["Group Code","Sequence","Parameter","Description","Data Type",
                "memcpy Size","Running Offset","Expected Offset","Status"]
    ws2.append(headers2)
    for row in parameters:
        ws2.append([row.get(h, "") for h in headers2])

    ws3 = wb.create_sheet("Validation Errors")
    headers3 = ["Group Code","Parameter","Description","Validation Type","Expected","Actual"]
    ws3.append(headers3)
    for row in errors:
        ws3.append([row.get(h, "") for h in headers3])

    for sheet in (ws, ws2, ws3):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        for col in range(1, sheet.max_column + 1):
            max_len = max([len(str(sheet.cell(r, col).value or "")) for r in range(1, min(sheet.max_row, 200) + 1)] + [10])
            sheet.column_dimensions[get_column_letter(col)].width = min(max_len + 2, 50)

    wb.save(path)


def evaluate_rule_modules(root: Path, rules: list[dict[str, Any]], output_dir: Path, pipeline_mode: str='sequential'):
    """Evaluate rules and generate per-module artifacts without changing legacy checkpoints."""
    out = []
    module_reports = []
    output_dir.mkdir(parents=True, exist_ok=True)
    def evaluate_one(index_rule):
        index,r=index_rule
        try:
            if r.get('needsLogicConfiguration') or r.get('needsRuleConfiguration') or (r.get('kind') in LOGIC_KINDS and not expected_logic(r)):
                missing=result(r['id'],r.get('name',r['id']),'NOT FOUND',r.get('expected',''),
                               'This draft has skipped required configuration. Complete the missing fields in Assist / Teach before testing or enabling it.')
                return enrich_result(root,r,missing,sys.modules[__name__]),None
            if r.get("kind") == "common_group_packet":
                suffix=f"_{index+1}_{_safe_report_name(str(r.get('id') or 'rule'))}"
                workbook = output_dir / f"{_safe_report_name(root.name)}{suffix}.xlsx"
                x = common_group_packet_validate(root, r, workbook)
                report=str(workbook.name)
            else:
                x = None
                report=None
            if x is not None:
                evaluated=enrich_result(root,r,x,sys.modules[__name__])
            else:
                # Legacy evaluator remains the source of truth for all existing kinds.
                evaluated=enrich_result(root,r,evaluate_legacy_one(root, r),sys.modules[__name__])
            if r.get('kind')!='lot_name_packet_hmi' and r.get('crossFunctionChecks'):
                cross_evidence,cross_failures=_cross_function_logic_checks(root,r,_configured_rule_paths(root,r))
                evaluated['crossFunctionLogicChecks']=cross_evidence
                evaluated['sourceFiles']=sorted(set(evaluated.get('sourceFiles') or [])|{item['file'] for item in cross_evidence if item.get('file')}|{name for item in cross_evidence for name in item.get('searchedFiles',[])})
                if cross_failures:
                    if evaluated.get('status')=='PASS': evaluated['status']='FAIL'
                    evaluated['actual']=(str(evaluated.get('actual') or '').rstrip('.')+'; ' if evaluated.get('actual') else '')+'Cross-function logic not found: '+', '.join(cross_failures)+'.'
                    evaluated['recommendations']=list(dict.fromkeys([*(evaluated.get('recommendations') or []),'Add or correct the configured logic in each linked PLC subroutine.']))
                    evaluated['failureReasons']=[evaluated['actual'],*evaluated.get('recommendations',[])]
            return evaluated,report
        except Exception as e:
            return result(r.get("id","R-ERR"), r.get("name","Rule"), "FAIL",
                          r.get("expected",""), f"Rule evaluation error: {e}",
                          recommendations=["Review the rule configuration and source project."]),None
    indexed=list(enumerate(rules))
    if pipeline_mode=='parallel' and len(indexed)>1:
        with ThreadPoolExecutor(max_workers=min(8,len(indexed)),thread_name_prefix='rule-check') as pool:
            evaluated=list(pool.map(evaluate_one,indexed))
    else:
        evaluated=[evaluate_one(item) for item in indexed]
    for item,report in evaluated:
        out.append(item)
        if report: module_reports.append(report)
    return out, module_reports


def _safe_report_name(name: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "_", name or "AutomationStudioProject").strip(" .")
    return (value or "AutomationStudioProject")[:150]



def _hmi_property_checkpoint(root,rule,paths=None):
    if paths is None:
        requested=rule.get('sourceFiles') or [rule.get('subroutine') or rule.get('sourceFile') or '']
        paths=[p for p in all_files(root) if p.suffix.casefold() in {'.page','.pages','.layer','.tpr','.xml'} and any(p.relative_to(root).as_posix().casefold()==str(name).replace('\\','/').casefold() if '/' in str(name).replace('\\','/') else p.name.casefold()==str(name).casefold() for name in requested)]
    requirements=rule.get('hmiControlChecks') or parse_requirements(rule.get('exactLogic',''))
    evidence=[];failures=[]
    # A matching control in one visualization cannot cover a missing control in another.
    targets={}
    for path in paths:
        parts=path.relative_to(root).parts
        target=parts[1] if len(parts)>2 and parts[0].casefold()=='logical' else str(path.parent.relative_to(root))
        targets.setdefault(target,[]).append(path)
    for target,files in targets.items():
        for index,requirement in enumerate(requirements):
            candidates=[]
            for path in files:
                try:
                    for control,checks in control_candidates(read_text(path),requirement):
                        candidates.append({'check':f'HMI control {index+1}','file':path.relative_to(root).as_posix(),'target':target,'control':control.get('Name'),
                                           'propertyComparisons':checks,'status':'PASS' if all(c['status']=='PASS' for c in checks.values()) else 'FAIL'})
                except Exception as error:candidates.append({'check':'HMI XML','file':str(path),'status':'FAIL','actual':str(error)})
            passed=next((row for row in candidates if row['status']=='PASS'),None)
            evidence.extend([passed] if passed else candidates or [{'check':requirement.get('name'),'target':target,'status':'NOT FOUND','expected':requirement}])
            if not passed:failures.append(f"{target}: {requirement.get('name') or 'control'} properties did not match")
    return result(rule['id'],rule['name'],'PASS' if paths and not failures else 'FAIL',rule.get('expected',''),('; '.join(failures) or 'Configured HMI control properties matched.') if paths else 'Configured HMI file not found.',evidence,
                  ['Review each expected/actual property on the same control.'] if failures else [],[str(path.relative_to(root)) for path in paths])


def evaluate_legacy_one(root: Path, rule: dict[str, Any]):
    if rule.get('kind')=='module_serial_mapping':
        try: from python_engine.module_serial_mapping import evaluate
        except ModuleNotFoundError: from module_serial_mapping import evaluate
        return evaluate(root,rule,sys.modules[__name__])
    if rule.get('kind')=='structured_requirements':
        try: from python_engine.structured_requirements import evaluate
        except ModuleNotFoundError: from structured_requirements import evaluate
        return evaluate(root,rule,sys.modules[__name__])
    if rule.get('kind')=='structured_checks':
        try: from python_engine.structured_rule_checks import evaluate
        except ModuleNotFoundError: from structured_rule_checks import evaluate
        return evaluate(root,rule,sys.modules[__name__])
    if rule.get('kind')!='group_code_exact_logic' and rule.get('groupCodeMode') in {'selected','all','exclude'}:
        mode=rule['groupCodeMode'];configured={int(x) for x in rule.get('groupCodes') or []}
        codes=configured if mode=='selected' else {b['groupCode'] for p in _configured_rule_paths(root,rule) for b in _parse_case_group_branches(read_text(p))}-(configured if mode=='exclude' else set())
        checks=[]
        for code in sorted(codes):
            scoped={k:v for k,v in rule.items() if k not in {'groupCodes','groupCodeMode'}};scoped['groupCode']=code
            checked=evaluate_legacy_one(root,scoped)
            for item in checked.get('evidence',[]):item.setdefault('groupCode',code)
            checks.append(checked)
        return result(rule['id'],rule['name'],'PASS' if checks and all(c['status']=='PASS' for c in checks) else 'FAIL',rule.get('expected',''),
                      '; '.join(f"Group {code}: {check['status']} - {check['actual']}" for code,check in zip(sorted(codes),checks)) or 'No selected Group Codes found.',
                      [item for check in checks for item in check.get('evidence',[])],[],sorted({file for check in checks for file in check.get('sourceFiles',[])}))
    if rule.get('kind')=='hmi_control_properties':return _hmi_property_checkpoint(root,rule)
    if rule.get('kind')=='checkpoint_1': return checkpoint_1(root,rule)
    if rule.get('kind')=='checkpoint_2': return checkpoint_2(root,rule)
    if rule.get('kind')=='checkpoint_3': return checkpoint_3(root,rule)
    if rule.get('kind')=='checkpoint_4': return checkpoint_4(root,rule)
    if rule.get('kind')=='condition_assignment': return _condition_assignment_checkpoint(root,rule)
    if rule.get('kind')=='indexed_assignment_range': return _indexed_assignment_checkpoint(root,rule)
    if rule.get('kind')=='machine_status_packet': return _machine_status_checkpoint(root,rule)
    if rule.get('kind')=='product_code_all_groups': return _product_code_checkpoint(root,rule)
    if rule.get('kind')=='lot_name_packet_hmi': return _lot_name_checkpoint(root,rule)
    if rule.get('kind')=='hmi_page_structure': return _hmi_page_structure_checkpoint(root,rule)
    if rule.get('kind')=='checklist_packet_signatures': return _checklist_packet_signatures(root,rule)
    if rule.get('kind')=='group_code_exact_logic': return _group_code_exact_logic(root,rule)
    if rule.get('kind')=='checklist_source_signatures': return _checklist_source_signatures(root,rule)
    if rule.get('kind') in {'exact_logic_declaration','cross_domain_traceability'}: return _exact_logic_declaration(root,rule)
    return generic_rule(root,rule)


def _exact_logic_declaration(root: Path, rule: dict[str, Any]):
    """Validate configured PLC source, declarations, and optional HMI tag bindings."""
    requested=str(rule.get('subroutine') or '').strip()
    exact=str(rule.get('exactLogic') or '').strip()
    variable=str(rule.get('variable') or '').strip()
    allowed=[str(value).strip().upper() for value in (rule.get('allowedDatatypes') or []) if str(value).strip()]
    candidates=[]
    requested_files=[str(x).replace('\\','/').strip() for x in (rule.get('sourceFiles') or []) if str(x).strip()]
    if requested and not requested_files: requested_files=[requested.replace('\\','/')]
    requested_names={Path(x).name.casefold() for x in requested_files}
    if requested_names & {'mms_nw_rcyclic.st','mms_nw_r.src'}:
        requested_names.update({'mms_nw_rcyclic.st','mms_nw_r.src'})
    for path in all_files(root):
        relative=str(path.relative_to(root)).replace('\\','/')
        if requested_files and not any(relative.casefold()==x.casefold() if '/' in x else path.name.casefold()==x.casefold() or (x.casefold() in {'mms_nw_rcyclic.st','mms_nw_r.src'} and path.name.casefold() in {'mms_nw_rcyclic.st','mms_nw_r.src'}) for x in requested_files):
            continue
        if path.suffix.casefold() in {'.st','.ab','.src','.c','.ld','.var','.typ','.page','.pages','.layer','.txtgrp','.algrp','.tpr','.hwl','.iom','.sw','.hw','.set','.osl','.apj','.gdm','.xml','.cfg','.pkg','.lby','.vcvk'}:
            candidates.append(path)
    if not candidates:
        return result(rule['id'],rule.get('name',rule['id']),'NOT FOUND',rule.get('expected',''),
                      f"Configured subroutine was not found: {requested or 'not supplied'}.",
                      recommendations=['Select the correct source subroutine before enabling this rule.'])
    logic_hit=None
    alternatives=expected_logic(rule)
    for path in candidates:
        text=read_text(path); clean=_strip_plc_comments(text) if path.suffix.casefold() in {'.st','.ab','.src','.c','.ld','.var','.typ'} else text
        if rule.get('groupCode') is not None:
            branch=_branch_with_location(text,int(rule['groupCode']))
            if not branch: continue
            segment,start=branch
        else: segment,start=clean,0
        for index,alternative in enumerate(alternatives):
            hit=_logic_match(segment,alternative)
            if hit:
                line=_line_number(clean,start+hit[0])
                logic_hit=_source_evidence(root,path,text,0,f'accepted ST alternative {index+1}',alternative[:500],line)
                break
        if logic_hit: break
    declaration_hit=None; observed_type=''
    if variable and allowed:
        declaration_files=[path for path in all_files(root) if path.suffix.casefold() in {'.var','.typ','.st','.src','.c','.txt'}]
        types='|'.join(re.escape(value) for value in allowed)
        patterns=[
            rf'\b{re.escape(variable)}\b(?:\s+AT\s+%[A-Z]+\w*|\s+%[A-Z]+\w*)?\s*:\s*({types})\b',
            rf'\b({types})\b[^;\r\n]*\b{re.escape(variable)}\b',
        ]
        for path in declaration_files:
            text=read_text(path)
            match=next((match for pattern in patterns if (match:=re.search(pattern,text,re.I))),None)
            if match:
                observed_type=match.group(1).upper()
                declaration_hit=_source_evidence(root,path,text,match.start(),f'{variable} declaration',match.group(0))
                break
    logic_ok=bool(logic_hit)
    declaration_ok=bool(declaration_hit) if variable and allowed else True
    cross_checks=[]
    if rule.get('kind')=='cross_domain_traceability':
        logic_candidates=[p for p in candidates if p.suffix.casefold() in {'.st','.ab','.src','.c','.ld','.var','.typ'}]
        configured_logic=[x for x in requested_files if Path(x).suffix.casefold() in {'.st','.ab','.src','.c','.ld','.var','.typ'}]
        for configured in configured_logic if variable else []:
            matches=[p for p in logic_candidates if p.name.casefold()==Path(configured).name.casefold() or str(p.relative_to(root)).replace('\\','/').casefold().endswith(configured.casefold())]
            found=False
            for path in matches:
                text=read_text(path); match=re.search(rf'\b{re.escape(variable)}\b',text,re.I) if variable else None
                if match:
                    found=True; cross_checks.append(_source_evidence(root,path,text,match.start(),'PLC tag present in configured source',variable))
            if not found:
                cross_checks.append({'file':configured,'check':'PLC tag present in configured source','status':'MISSING','expected':variable,'actual':'File not found or tag not declared/used'})
        hmi_pages=rule.get('crossDomainHmiPages') or []
        for configured in hmi_pages:
            configured=str(configured).replace('\\','/').casefold()
            page_matches=[p for p in all_files(root) if p.suffix.casefold() in {'.page','.pages'} and (p.name.casefold()==Path(configured).name or str(p.relative_to(root)).replace('\\','/').casefold().endswith(configured))]
            found=False
            for page in page_matches:
                text=read_text(page)
                # Match the declared tag token even when the page wraps it in a datapoint path.
                match=re.search(rf'\b{re.escape(variable)}\b',text,re.I) if variable else None
                if match:
                    found=True; cross_checks.append(_source_evidence(root,page,text,match.start(),'PLC tag bound on configured HMI page',variable))
            if not found:
                cross_checks.append({'file':configured,'check':'PLC tag bound on configured HMI page','status':'MISSING','expected':variable,'actual':'No matching datapoint found'})
    cross_ok=all(x.get('status')!='MISSING' for x in cross_checks)
    status='PASS' if logic_ok and declaration_ok and cross_ok else 'FAIL'
    missing=[]
    if not logic_ok: missing.append('configured expected logic/source pattern')
    if not declaration_ok: missing.append(f"{variable} datatype ({' or '.join(allowed)})")
    if not cross_ok: missing.append('PLC tag on one or more configured HMI pages')
    evidence=[item for item in (logic_hit,declaration_hit) if item]+cross_checks
    actual='Configured source, declaration and cross-domain checks were found.' if not missing else 'Missing: '+', '.join(missing)+'.'
    sources=sorted({str(item.get('file')) for item in evidence if item.get('file')} | {str(path.relative_to(root)) for path in candidates})
    return result(rule['id'],rule.get('name',rule['id']),status,rule.get('expected',''),actual,evidence,
                  ['Restore the configured logic or correct the PLC variable declaration datatype.'] if missing else [],sources)


def generic_rule(root, rule):
    kind=rule.get('kind','file_presence')
    if kind=='file_presence':
        names=rule.get('names',[]); hits=[]
        for p in all_files(root):
            if p.name.lower() in {n.lower() for n in names}: hits.append(str(p.relative_to(root)))
        ok=bool(hits)
        return result(rule['id'],rule['name'],'PASS' if ok else 'NOT FOUND',rule.get('expected','Required files shall exist.'),f'{len(hits)} matching files found.',hits,[rule.get('recommendation','Add the required implementation files.')] if not ok else [],hits)
    if kind=='source_regex':
        matches=[]
        pattern=rule.get('pattern','')
        for p in all_files(root, rule.get('suffix')):
            if re.search(pattern,read_text(p),re.I|re.M): matches.append(str(p.relative_to(root)))
        ok=bool(matches)
        return result(rule['id'],rule['name'],'PASS' if ok else 'FAIL',rule.get('expected','Configured source pattern shall exist.'),f'{len(matches)} matching source files.',matches,[rule.get('recommendation','Review the PLC source implementation.')] if not ok else [],matches)
    return result(rule['id'],rule['name'],'NOT FOUND',rule.get('expected',''),f'Unsupported rule kind: {kind}',recommendations=['Ask Assist to configure the rule using a supported rule kind.'])


def evaluate(root: Path, rules: list[dict[str,Any]], output_dir: Path | None = None, pipeline_mode: str='sequential'):
    output_dir = Path(output_dir or root)
    mode='parallel' if str(pipeline_mode).casefold()=='parallel' else 'sequential'
    out, module_reports = evaluate_rule_modules(root, rules, output_dir,mode)
    counts={"pass":sum(x['status']=='PASS' for x in out),
            "fail":sum(x['status']=='FAIL' for x in out),
            "not_found":sum(x['status']=='NOT FOUND' for x in out)}
    return {"version":"4.52","ruleCount":len(out),"pipelineMode":mode,"counts":counts,
            "results":out,"moduleReports":module_reports}


def evaluate_branched_pipeline(root, config, output_dir):
    """Run independent branches concurrently and stages within each branch in order."""
    stages=config.get('pipelineStages',[])
    lookup={r['id']:r for r in config.get('rules',[])}
    branches={}
    identities=set()
    if not isinstance(stages,list) or not stages: raise ValueError('Branch pipeline requires stages.')
    for ordinal,stage in enumerate(stages):
        if not isinstance(stage,dict): raise ValueError('Invalid pipeline stage.')
        sid=stage.get('id'); branch=stage.get('branch',1); ids=stage.get('ruleIds')
        if not isinstance(sid,str) or not sid or sid in identities or type(branch) is not int or not 1<=branch<=100:
            raise ValueError('Stages require unique IDs and a branch between 1 and 100.')
        identities.add(sid)
        if not isinstance(ids,list) or not ids or any(not isinstance(rid,str) or rid not in lookup for rid in ids):
            raise ValueError('Each stage needs known rule IDs.')
        branches.setdefault(branch,[]).append((ordinal,stage))
    def run_branch(job):
        branch,entries=job
        results=[];reports=[]
        for ordinal,stage in entries:
            folder=output_dir/f'pipeline_stage_{ordinal+1}'
            data=evaluate(root,[lookup[rid] for rid in stage['ruleIds']],folder,'sequential')
            for item in data['results']:
                item.update({'pipelineStageId':stage['id'],'pipelineStageName':stage.get('label',''),'pipelineBranch':branch})
                results.append(item)
            for name in data.get('moduleReports',[]):
                source=folder/name
                destination=output_dir/f'stage_{ordinal+1}_{source.name}'
                source.replace(destination)
                reports.append(destination.name)
        return results,reports
    output_dir.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=min(8,len(branches)),thread_name_prefix='pipeline-branch') as pool:
        finished=list(pool.map(run_branch, sorted(branches.items())))
    results=[r for rows,_ in finished for r in rows]
    counts={'pass':sum(r['status']=='PASS' for r in results),'fail':sum(r['status']=='FAIL' for r in results),'not_found':sum(r['status']=='NOT FOUND' for r in results)}
    return {'version':'4.57','pipelineMode':'branches','ruleCount':len(results),'counts':counts,'results':results,'moduleReports':[r for _,reports in finished for r in reports]}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project',required=True)
    ap.add_argument('--rules',required=True)
    ap.add_argument('--output-json',required=True)
    ap.add_argument('--output-dir',required=False,default='')
    a=ap.parse_args()
    root=Path(a.project).resolve()
    config=json.loads(Path(a.rules).read_text(encoding='utf-8'))
    pipeline_mode=config.get('pipelineMode','sequential') if isinstance(config,dict) else 'sequential'
    rules = config.get('rules',config) if isinstance(config,dict) else config
    output_dir=Path(a.output_dir).resolve() if a.output_dir else Path(a.output_json).resolve().parent
    if pipeline_mode=='graph':
        try:
            from python_engine.pipeline_graph import evaluate_graph
        except ModuleNotFoundError:
            from pipeline_graph import evaluate_graph
        data=evaluate_graph(root,config,output_dir,evaluate)
    else:
        data=evaluate_branched_pipeline(root,config,output_dir) if pipeline_mode=='branches' else evaluate(root,rules,output_dir,pipeline_mode)
    Path(a.output_json).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(data))

if __name__=='__main__':
    main()
