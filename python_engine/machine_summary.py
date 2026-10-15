"""Readable machine overviews assembled from the current project's source index."""
from pathlib import Path
import re

from python_engine.project_analysis import _mask, _symbols, block_family


SUMMARY_SYSTEM = '''For a broad machine-function or project-summary question, use this order:
1. Project summary: project name, machine purpose (label inference), PLC, selected configuration and HMI object.
2. Main functions: short plain-English descriptions of source-supported subsystems.
3. How the machine works: connected sentences about the actual retained operations and branch conditions in this project. Do not turn concurrent task order into a simulated sequence.
4. Communication present: a compact table of actual called interfaces, literal ports/devices/settings and source citations. Separate configured code from a working live connection.
5. Review points: only supported observations or supplied review candidates. Do not invent faults to fill this section. If no complete defect review was supplied, say so briefly.
6. Review limits: one short sentence identifying source coverage and any missing live/compile evidence.
Use projectMachineSummary as a source-located outline, not a substitute for its cited excerpts. Derive subsystem labels and machine purpose from the actual operations, calls and bindings in this project. Routine titles are source names, not verified functional classifications. Do not copy a predefined drawframe, motor, doffing, fault or reporting list into an unrelated project. Do not turn these functions into validation requirements or PASS/FAIL verdicts. Inferred subsystem roles are not proof of complete control flow. Cite each functional paragraph/table row with supplied [S#] IDs. Keep the answer around 250-450 words. Avoid raw assignment dumps, repeated inventory lists and generic unsupported-source wording. Never reuse another project's machine type, ports, settings or findings. Never display 'PLC source logic' as a heading.'''


# Routine names below are read from the current selected configuration. They are
# display labels only: executable operations provide every behavior claim.

def _human_name(value):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return re.sub(r"[_/]+", " ", value).strip() or "Source routine"


def _task_for(file, tasks):
    path = "/" + file.casefold()
    candidates = []
    for task in tasks:
        source = re.sub(r"\.prg$", "", task.get("source", ""), flags=re.I).replace(".", "/")
        if source and "/" + source.casefold() + "/" in path:
            candidates.append((len(source), task, source))
    return max(candidates, key=lambda item: item[0])[1:] if candidates else (None, "")


def _operation_rank(record, mapped_outputs):
    name = record.get("name", "")
    root = name.split("[", 1)[0].casefold()
    value = record.get("value", "")
    score = 20 if root in mapped_outputs else 0
    score += 5 if record.get("kind") == "coil" else 0
    score += 3 if len(record.get("reads", [])) > 1 else 0
    score += 3 if re.search(r"[*/+-]", value) else 0
    score += 2 if record.get("guards") else 0
    score -= 5 if "." in name else 0  # Individual block pins are support details.
    score -= 3 if re.fullmatch(r"(?:0|1|TRUE|FALSE)", value, re.I) else 0
    score -= 8 if re.search(r"(?:INIT|EXIT)", record.get("section", ""), re.I) else 0
    return (-score, record["file"], record.get("eventLine", 1))


def _operation_sentence(record, with_guards):
    name = record["name"]
    if record["kind"] == "coil":
        verb = {"set": "latches", "reset": "resets", "open": "drives"}.get(record.get("coilType"), "updates")
        action = f"{verb} {name} according to its connected rung"
        if record.get("complexTopology"):
            action += "; the full series/parallel connections need the rung view"
    else:
        value = record.get("value", "")
        reads = list(dict.fromkeys(record.get("reads", [])))
        if re.fullmatch(r"(?:TRUE|FALSE|[-+]?\d+(?:\.\d+)?)", value, re.I):
            action = f"sets {name} to {value}"
        elif re.fullmatch(r"[A-Za-z_]\w*(?:\.\w+|\[[^]]+\])*", value):
            action = f"copies {value} into {name}"
        elif reads:
            action = f"calculates {name} using " + ", ".join(reads[:4])
            if len(reads) > 4:
                action += " and other source operands"
        else:
            action = f"updates {name} with its source expression"
    guards = record.get("guards", []) if with_guards else []
    section = record.get('section', '').upper()
    phase = 'During initialization, ' if 'INIT' in section else 'During the exit section, ' if 'EXIT' in section else ''
    if guards and len(" AND ".join(guards)) <= 180:
        from python_engine.flow_narrative import condition
        rendered = [condition(guard) for guard in guards]
        if len(rendered) > 1:
            rendered = ['(' + text + ')' if re.search(r'\bor\b', text) else text for text in rendered]
        return phase + ("when " if phase else "When ") + " and ".join(rendered) + ", it " + action + "."
    prefix = "Under the source branch conditions, it " if record.get('guards') else "The routine "
    if record.get("guardCoverage") == "unresolved":
        prefix = "The source contains an operation that "
    return phase + (prefix[:1].lower() + prefix[1:] if phase else prefix) + action + "."


def _discover_functions(index, add, communication_files=()):
    tasks = index.get("tasks", [])
    active = [record for record in index.get("operationRecords", [])
              if record.get("ownership") == "active task"]
    operations = active or [record for record in index.get("operationRecords", [])
                            if record.get("ownership") != "disabled task"]
    mapped_outputs = set()
    for chunk in index.get("chunks", []):
        if chunk.get("category") == "Hardware / I/O":
            mapped_outputs.update(match.group(1).split(".")[-1].casefold()
                                  for match in re.finditer(r"([A-Za-z_][\w.#]*)\s+AT\s+%Q", _mask(chunk["text"]), re.I))
    groups = {}
    for record in operations:
        task, source = _task_for(record["file"], tasks)
        if task and not task.get("enabled", True):
            continue
        key = source or str(Path(record["file"]).parent)
        group = groups.setdefault(key, {"records": [], "task": task, "source": source})
        group["records"].append(record)
    def group_rank(pair):
        import math
        records = pair[1]['records']
        best = min(records, key=lambda record: _operation_rank(record, mapped_outputs))
        mapped = {name.casefold() for record in records for name in record.get('writes', [])
                  if name.casefold() in mapped_outputs}
        score = -_operation_rank(best, mapped_outputs)[0] + min(12, len(mapped) * 2) + math.log2(len(records) + 1)
        if all(record['file'] in communication_files for record in records):
            score -= 20  # The communication table already covers this routine.
        return (-score, pair[0])
    ranked = sorted(groups.items(), key=group_rank)
    # Start with different source areas so a large package cannot consume the
    # entire overview. No area is assigned a machine-specific interpretation.
    first, later, areas = [], [], set()
    for key, group in ranked:
        source = group["source"] or key.removeprefix("Logical/")
        area = source.split("/", 1)[0]
        (later if area in areas else first).append((key, group))
        areas.add(area)
    ordered = first + later
    mapped_groups = [(key, group) for key, group in ordered if any(record['name'].casefold() in mapped_outputs for record in group['records'])]
    other_groups = [(key, group) for key, group in ordered if (key, group) not in mapped_groups]
    # Include calculations/internal state as well as physical output writers.
    ordered = mapped_groups[:6] + other_groups[:4] + mapped_groups[6:] + other_groups[4:]
    functions = []
    for key, group in ordered:
        chosen = sorted(group["records"], key=lambda record: _operation_rank(record, mapped_outputs))
        record = next((item for item in chosen if not re.search(r"(?:INIT|EXIT)", item.get("section", ""), re.I)), chosen[0])
        ref = add(record)
        if not ref:
            continue
        refs = [ref]
        with_guards = len(record.get('guards', [])) <= 4 and len(' AND '.join(record.get('guards', []))) <= 180
        for line in dict.fromkeys(record.get("guardLines", []) if with_guards else []):
            guard_ref = add({**record, "eventLine": line})
            if guard_ref:
                refs.append(guard_ref)
            else:
                with_guards = False
        task = group["task"]
        source = group["source"] or str(Path(record["file"]).parent).removeprefix("Logical/")
        title = _human_name(source.split("/")[-1])
        functions.append({"key": key, "title": title, "routine": source,
                          "description": _operation_sentence(record, with_guards),
                          "ownership": record["ownership"], "references": refs,
                          "outputs": record.get("writes", []), "inputs": record.get("reads", []),
                          "operationCount": len(group["records"]),
                          "task": task.get("name") if task else None,
                          "section": record.get("section", ""),
                          "meaning": "Representative executable operation; title is the source routine name, not a complete subsystem classification."})
        if len(functions) >= 10:
            break
    return functions, len(groups)


def prepare_summary(index, fallback_evidence=(), characters=14000):
    """Return a project-specific outline and bounded evidence for model/fallback use."""
    evidence, references = [], {}
    chunks_by_file = {}
    for chunk in index.get('chunks', []):
        chunks_by_file.setdefault(chunk['file'], []).append(chunk)

    def add(record):
        nonlocal characters
        line = record.get('eventLine', record.get('line', 1))
        file = record['file']
        if (file, line) in references: return references[file, line]
        for item in evidence:
            end = item['line'] + (1 if item.get('network') else len(item['excerpt'].splitlines()))
            if item['file'] == file and item['line'] <= line < end:
                ref = {'file': file, 'line': line}
                references[file, line] = ref
                return ref
        candidates = [c for c in chunks_by_file.get(file, [])
                      if c['line'] <= line < c['line'] + (1 if c.get('network') else len(c['text'].splitlines()))]
        if not candidates: return None
        chunk = max(candidates, key=lambda c: c['line'])
        item = {k: chunk[k] for k in ('file', 'line', 'category', 'ownership', 'network', 'enabled') if k in chunk}
        if chunk.get('network'):
            diagram = '\n'.join(chunk['text'].splitlines()[2:])
            match = re.search(record.get('summarySignal', re.escape(record.get('name', '')) or r'Coil:|Function block:'), diagram, re.I)
            offset = match.start() if match else 0
            excerpt = (chunk['text'] if len(chunk['text']) <= 3200 else
                       chunk['text'].splitlines()[0] + '\nPartial decoded network: ' + diagram[max(0, offset - 200):offset + 550])
        else:
            lines = chunk['text'].splitlines()
            start = max(0, line - chunk['line'] - 3)
            excerpt = '\n'.join(lines[start:line - chunk['line'] + 6])
            item['line'] += start
        if not excerpt or len(excerpt) > characters or len(evidence) >= 48: return None
        item.update(excerpt=excerpt, behaviour=[])
        evidence.append(item)
        characters -= len(excerpt)
        ref = {'file': file, 'line': line}
        references[file, line] = ref
        return ref

    identity_refs = []
    for item in index.get('inventory', []):
        if Path(item['file']).suffix.casefold() == '.apj' or Path(item['file']).name.casefold() == 'cpu.sw':
            ref = add({**item, 'eventLine': 1})
            if ref: identity_refs.append(ref)

    records = [r for r in index.get('analysisRecords', []) if r.get('ownership') != 'disabled task']
    records_by_file = {}
    for record in records: records_by_file.setdefault(record['file'], []).append(record)
    symbol_map = {}
    for symbol in index.get('symbols', []): symbol_map.setdefault(symbol['name'].casefold(), []).append(symbol)
    communications, seen = [], set()
    for record in records:
        if record['kind'] != 'call': continue
        typed = _symbols(symbol_map, record)
        if record.get('bare') and not any(block_family(s['declaration'].split()[0]) for s in typed if s.get('declaration')):
            continue
        family = block_family(record['name']) or next((block_family(s['declaration'].split()[0]) for s in typed if s.get('declaration') and block_family(s['declaration'].split()[0])), None)
        if not family or (record['file'], family) in seen: continue
        seen.add((record['file'], family))
        file_records = records_by_file[record['file']]
        settings = []
        refs = []
        if 'TCP' in family or 'UDP' in family:
            ports = []
            for assignment in file_records:
                if assignment['kind'] != 'assignment' or not re.search(r'\.port$', assignment['name'], re.I) or not re.fullmatch(r'\d+', assignment['value']):
                    continue
                owner = assignment['name'].rsplit('.', 1)[0]
                declared = _symbols(symbol_map, {**record, 'name': owner, 'instance': owner})
                port_family = block_family(owner) or next((block_family(symbol['declaration'].split()[0]) for symbol in declared if symbol.get('declaration') and block_family(symbol['declaration'].split()[0])), None)
                if port_family == family:
                    ports.append(assignment)
            for port in ports[:2]:
                ref = add(port)
                if ref: settings.append('port ' + port['value']); refs.append(ref)
        if 'Serial' in family or 'serial' in family:
            modes = [r for r in file_records if r['kind'] == 'assignment' and '/PHY' in r.get('value', '').upper()]
            for mode in modes[:1]:
                values = re.findall(r'/(BD|PA|DB|SB|PHY)\s*=\s*([^\s\x22\x27;)]+)', mode['value'], re.I)
                ref = add(mode)
                if ref: settings.extend(k.upper() + '=' + v for k, v in values); refs.append(ref)
        ref = add(record)
        if not ref: continue
        refs.insert(0, ref)
        if typed:
            type_ref = add(typed[0])
            if not type_ref: continue
            refs.append(type_ref)
        if refs:
            communications.append({'title': family, 'settings': ', '.join(dict.fromkeys(settings)) or 'Endpoint/settings need further tracing',
                                   'routine': Path(record['file']).parent.name, 'file': record['file'], 'ownership': record['ownership'], 'references': refs})

    functions, discovered_routines = _discover_functions(index, add, {item['file'] for item in communications})

    # Fallback for formats with literal-call coverage but no IEC/ladder decoder.
    # Calls prove a referenced operation; filenames never supply its behavior.
    if not functions:
        for record in records:
            if record["kind"] != "call" or record.get("bare"):
                continue
            ref = add(record)
            if ref:
                functions.append({"key": record["file"], "title": _human_name(Path(record["file"]).parent.name),
                                  "routine": str(Path(record["file"]).parent),
                                  "description": f"Contains a call to {record['name']}; its conditions and effect need the full routine trace.",
                                  "ownership": record["ownership"], "references": [ref],
                                  "inputs": [], "outputs": []})
            if len(functions) >= 6:
                break
    purpose = "This overview is derived from the selected project's executable operations. The physical machine type needs source or engineering confirmation."
    purpose_refs = []
    # Preserve configuration and at least representative communication evidence
    # when a small model's context budget drops later excerpts.
    priority_groups = [identity_refs,
                       [r for function in functions[:3] for r in function['references']],
                       [r for item in communications if 'port ' in item['settings'] for r in item['references']],
                       [r for function in functions[3:] for r in function['references']],
                       [r for item in communications for r in item['references']]]
    def priority(item):
        return next((rank for rank, refs in enumerate(priority_groups)
                     if any(item['file'] == ref['file'] and item['line'] <= ref['line'] < item['line'] + (1 if item.get('network') else len(item['excerpt'].splitlines())) for ref in refs)), len(priority_groups))
    evidence.sort(key=priority)
    for number, item in enumerate(evidence, 1): item['sourceId'] = f'S{number}'
    return {'identity': index['identity'], 'identityReferences': identity_refs,
            'configuredTasks': len(index.get('tasks', [])),
            'enabledTasks': sum(t.get('enabled', True) for t in index.get('tasks', [])),
            'binaryTasksWithoutSource': sum(t.get('enabled', True) and not t.get('source') for t in index.get('tasks', [])),
            'purpose': purpose, 'purposeReferences': purpose_refs, 'functions': functions,
            'communications': communications, 'reviewPoints': [], 'notices': index.get('notices', []),
            'discoveredRoutineCount': discovered_routines, 'summaryMethod': 'project executable operations; no predefined machine-function catalog',
            'coverage': 'Representative source operations from the selected project/configuration; no live PLC connection, complete machine simulation or Automation Studio build result.'}, evidence


def retained_summary(summary, evidence):
    """Do not send outline claims whose supporting excerpts were dropped from the prompt."""
    def retained(ref):
        return any(e['file'] == ref['file'] and e['line'] <= ref['line'] < e['line'] + (1 if e.get('network') else len(e['excerpt'].splitlines())) for e in evidence)
    result = {**summary}
    for key in ('functions', 'communications', 'reviewPoints'):
        result[key] = [{k: v for k, v in item.items() if k != 'meaning'} for item in summary.get(key, []) if all(retained(r) for r in item['references'])]
    if summary['purposeReferences'] and not all(retained(r) for r in summary['purposeReferences']):
        result.update(purpose='The supplied excerpts do not establish the machine type.', purposeReferences=[])
    result['identityReferences'] = [r for r in summary['identityReferences'] if retained(r)]
    return result


def summary_answer(summary, evidence):
    def cite(refs):
        ids = []
        for ref in refs:
            item = next((e for e in evidence if e['file'] == ref['file'] and e['line'] <= ref['line'] < e['line'] + (1 if e.get('network') else len(e['excerpt'].splitlines()))), None)
            if item and item['sourceId'] not in ids: ids.append(item['sourceId'])
        return ' '.join('[' + sid + ']' for sid in ids)
    identity = summary['identity']
    lines = [f"## Project summary — {identity.get('project_name') or 'Selected project'}", '',
             summary['purpose'] + ' ' + cite(summary['purposeReferences']), '',
             f"- PLC: {identity.get('plc_type') or 'unresolved'}.",
             f"- Automation Studio: {identity.get('automation_studio_version') or 'unresolved'}.",
             f"- Selected configuration: {identity.get('active_configuration') or 'unresolved'}.",
             f"- HMI visualization object: {identity.get('active_hmi') or 'unresolved'}."]
    if summary['configuredTasks']:
        lines.append(f"- Tasks: {summary['configuredTasks']} configured; {summary['enabledTasks']} enabled. {cite(summary['identityReferences'])}")
    lines.extend(['', '### Main functions', ''])
    for item in summary['functions']:
        scope = '' if item['ownership'] == 'active task' else ' Task ownership is unconfirmed.'
        lines.append(f"- **{item['title']}:** {item['description']}{scope} {cite(item['references'])}")
    if not summary['functions']: lines.append('No source-supported functional overview was retained. A focused routine review is needed.')
    lines.extend(['', '### How the machine works', ''])
    if summary['functions']:
        sentences = []
        for item in summary['functions'][:4]:
            sentences.append(f"In {item['title']}, " + item['description'][:1].lower() + item['description'][1:] + ' ' + cite(item['references']))
        sentences.append('These are source-supported operations across separate routines; their listing order does not establish a machine timeline.')
        lines.append(' '.join(sentences))
    else:
        lines.append('The retained actions do not establish an operating sequence. Start/stop conditions and transitions need a focused source trace.')
    lines.extend(['', '### Communication present', ''])
    if summary['communications']:
        lines.extend(['| Interface / routine | Source-defined settings | Evidence |', '| --- | --- | --- |'])
        for item in summary['communications']:
            scope = '' if item['ownership'] == 'active task' else ' (ownership unconfirmed)'
            lines.append(f"| {item['title']} / {item['routine']}{scope} | {item['settings']} | {cite(item['references'])} |")
    else:
        lines.append('No recognized communication calls were retained; this does not establish that communication is absent.')
    lines.extend(['', '### Review points', '', 'A complete defect review was not performed for this overview. Ask about a specific function, fault or communication path for a detailed trace.'])
    if summary['binaryTasksWithoutSource']:
        lines.append(f"{summary['binaryTasksWithoutSource']} enabled task entry/entries have no source reference; their behavior is not explained here.")
    lines.extend(['', '### Review limits', '', summary['coverage']])
    if summary.get('discoveredRoutineCount', 0) > len(summary['functions']):
        lines.append(f"This overview shows {len(summary['functions'])} of {summary['discoveredRoutineCount']} routines with decoded operations; ask about a named routine for its complete trace.")
    lines.extend(summary['notices'])
    return '\n'.join(lines)
