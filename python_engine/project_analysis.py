"""Bounded, source-backed task analysis. No PLC execution or model training."""
from pathlib import Path
import re

SPELLINGS = {
    'machien': 'machine', 'machiens': 'machines', 'fuction': 'function',
    'fuctions': 'functions', 'funtion': 'function', 'communction': 'communication',
    'communcation': 'communication', 'commnication': 'communication',
    'communiction': 'communication', 'communciation': 'communication',
    'comunication': 'communication', 'improvent': 'improvement',
    'improvents': 'improvements', 'suggection': 'suggestion',
    'suggesion': 'suggestion', 'suggetion': 'suggestion',
    'projrct': 'project', 'projrcts': 'projects', 'alram': 'alarm',
    'parametre': 'parameter', 'parametr': 'parameter', 'timout': 'timeout',
    'laddee': 'ladder', 'laddder': 'ladder', 'logci': 'logic',
}


def normalize_question(question):
    # Correct known ordinary words only. Preserve identifiers, paths and quoted text.
    value = str(question)
    protected = r"'[^'\n]*'|\"[^\"\n]*\"|[\w./\\-]+\.(?:st|ld|ab|c|var|typ|page)\b|[A-Za-z_]\w*_[\w.]+"
    def ordinary(text):
        text = re.sub(r'\b[A-Za-z]+\b', lambda m: SPELLINGS.get(m.group().casefold(), m.group()), text)
        return re.sub(r'\bRS[ -]?(232|422|485)\b', r'RS\1', text, flags=re.I)
    parts, end = [], 0
    for match in re.finditer(protected, value, re.I):
        parts.extend([ordinary(value[end:match.start()]), match.group()]); end = match.end()
    return ''.join(parts) + ordinary(value[end:])


def question_intent(question):
    text = normalize_question(question)
    communication = bool(re.search(r'\b(?:communications?|protocols?|RS(?:232|422|485)|serial|modbus|TCP|UDP|ping|ethernet|CANopen|POWERLINK|profibus)\b|\b(?:Tcp(?:Open|Close|Server|Client|Send|Recv|Ioctl)|Udp(?:Open|Close|Send|Recv)|IcmpPing|FRM_\w+|MBMOpen|MBMaster|MBSlave)\w*', text, re.I))
    improvement = bool(re.search(r'\b(?:improv\w*|suggest\w*|optimi[sz]\w*|review|bugs?|risk\w*)\b', text, re.I))
    machine = bool(re.search(r'machine.*(?:function|operat|work)|(?:function|operat).*machine|operating sequence|(?:understand|explain).*project|project.*(?:function|overview)', text, re.I))
    return {'kind': 'communication review' if communication and improvement else 'communication' if communication else 'improvement review' if improvement else 'machine functions' if machine else 'source lookup',
            'communication': communication, 'improvement': improvement, 'machine': machine,
            'normalizedQuestion': text}


def _mask(text, strings=False):
    # Lexical masking keeps line and character positions; comments cannot create calls.
    pattern = r"'(?:(?:'')|[^'])*'|\"(?:\\.|[^\"\\])*\"|\(\*.*?\*\)|/\*.*?\*/|//[^\n]*"
    def replace(match):
        value = match.group()
        if not strings and value[:1] in {'"', "'"}: return value
        return ''.join('\n' if char == '\n' else ' ' for char in value)
    return re.sub(pattern, replace, text, flags=re.S)


def collect_file(file, text, category, ownership):
    """Keep literal calls, assignments, branch headers and serial setting evidence."""
    if Path(file).suffix.casefold() == '.ld': return []
    if category not in {'Logic', 'Hardware / I/O', 'Configuration', 'Declarations'}: return []
    clean, code = _mask(text), _mask(text, strings=True)
    records = []
    def add(kind, match, **fields):
        line = text.count('\n', 0, match.start()) + 1
        records.append({'kind': kind, 'file': file, 'category': category, 'ownership': ownership,
                        'eventLine': line, **fields})
    if category == 'Logic' and Path(file).suffix.casefold() in {'.st', '.ab', '.src', '.c'}:
        pattern = r'\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\('
        ignored = {'if', 'elsif', 'while', 'for', 'switch', 'sizeof', 'adr', 'address', 'return'}
        for match in list(re.finditer(pattern, code))[:1000]:
            if match.group(1).casefold() in ignored: continue
            if Path(file).suffix.casefold() == '.c':
                prefix = code[code.rfind('\n', 0, match.start())+1:match.start()]
                # Prototypes/definitions in C are not executable calls.
                if re.fullmatch(r'\s*(?:(?:extern|static|inline|const|unsigned|signed|long|short)\s+)*[A-Za-z_]\w*\s*\*?\s+', prefix): continue
            target = re.match(r'\s*&\s*([A-Za-z_]\w*)', code[match.end():match.end()+100]) if Path(file).suffix.casefold() == '.c' else None
            add('call', match, name=match.group(1), instance=target.group(1) if target else match.group(1))
        assignment = r'\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]\n]+\])*)\s*(?::=|=(?!=))\s*([^;\n]+)'
        for match in list(re.finditer(assignment, clean))[:2000]:
            # Avoid C/AB comparisons and named arguments becoming assignments.
            prefix = code[max(0, match.start()-1):match.start()]
            if prefix in {'<', '>', '!', '='}: continue
            add('assignment', match, name=match.group(1), value=match.group(2).strip()[:400])
        for match in list(re.finditer(r'\b(?:IF|ELSIF|CASE|WHILE)\s+[^\n]{1,240}|\bif\s*\([^\n]{1,240}', code))[:600]:
            add('branch', match, expression=match.group().strip())
    # Configuration markers only establish literal presence until linked to a call.
    for match in list(re.finditer(r'\bRS[- ]?(?:232|422|485)\b|/(?:BD|PA|DB|SB|PHY)\s*=\s*[^\s\x22\x27;]+', clean, re.I))[:100]:
        add('serial setting', match, value=match.group())
    return records


def block_family(name):
    name = name.casefold().split('.')[-1]
    if re.match(r'tcp(?:open|close|server|client|connect|send|recv|ioctl)', name): return 'TCP / Ethernet'
    if re.match(r'udp(?:open|close|send|recv|ioctl)', name): return 'UDP / Ethernet'
    if name.startswith('icmpping'): return 'ICMP ping / Ethernet'
    if name.startswith(('mbtcp', 'mb_tcp')): return 'Modbus TCP'
    if re.match(r'mb(?:mopen|mclose|master|mcmd|sopen|sclose|slave)', name): return 'Modbus serial (RTU/ASCII mode needs tracing)'
    if re.match(r'frm_(?:x?open|close|read|write|rbuf|gbuf|ioctl)', name): return 'Serial frames / DVFrame'
    if name.startswith(('canopen', 'arcan', 'can_', 'ascans')): return 'CAN API (protocol needs tracing)'
    return None


def _symbols(symbol_map, record):
    name = record.get('instance', record.get('name', '')).split('.')[-1].casefold()
    candidates = symbol_map.get(name, [])
    local = [s for s in candidates if Path(s['file']).parent == Path(record['file']).parent]
    # Never borrow a same-named instance from a different task.
    return local if local else [s for s in candidates if Path(s['file']).stem.casefold() in {'global', 'variables'} and Path(s['file']).parent.as_posix().casefold() in {'logical', '.'}]


def _evidence(record, index):
    if 'excerpt' in record:
        return {k: record[k] for k in ('file', 'line', 'category', 'ownership', 'excerpt', 'network', 'enabled') if k in record} | {'behaviour': record.get('behaviour', [])}
    line = record['eventLine']
    chunks = [c for c in index['chunks'] if c['file'] == record['file'] and not c.get('network') and c['line'] <= line < c['line'] + len(c['text'].splitlines())]
    if not chunks: return None
    chunk = max(chunks, key=lambda c: c['line'])
    lines = chunk['text'].splitlines(); start = max(0, line - chunk['line'] - 8)
    excerpt = '\n'.join(lines[start:start + 25])
    while len(excerpt) > 3200 and '\n' in excerpt: excerpt = excerpt.rsplit('\n', 1)[0]
    if line >= chunk['line'] + start + len(excerpt.splitlines()): return None
    return {k: record[k] for k in ('file', 'category', 'ownership')} | {'line': chunk['line'] + start, 'excerpt': excerpt[:3200], 'behaviour': []}


def analyze(index, question, fallback_evidence, characters=15000, limit=20):
    intent = question_intent(question)
    records = index.get('analysisRecords', [])
    symbol_map = {}
    for symbol in index.get('symbols', []): symbol_map.setdefault(symbol['name'].casefold(), []).append(symbol)
    calls, settings = [], [r for r in records if r['kind'] == 'serial setting']
    for record in records:
        if record['kind'] != 'call': continue
        resolved = _symbols(symbol_map, record)
        types = list(dict.fromkeys(re.match(r'\w+', s['declaration']).group() for s in resolved if re.match(r'\w+', s['declaration'])))
        family = block_family(record['name']) or next((block_family(t) for t in types if block_family(t)), None)
        if family:
            calls.append({**record, 'blockTypes': types, 'family': family, 'declarations': resolved[:2]})
    # Ladder blocks have explicit types, so declarations are unnecessary for presence.
    for record in index.get('ladderCalls', []):
        family = block_family(record['blockType'])
        if family and record.get('enabled', True): calls.append({**record, 'family': family, 'blockTypes': [record['blockType']], 'declarations': []})
    query = intent['normalizedQuestion']
    query_tokens = set(re.findall(r'[A-Za-z_]\w*', query.casefold()))
    file_focus = re.search(r'\b([\w.-]+\.(?:st|ab|c|ld))\b', query, re.I)
    focus = re.search(r'\b(RS485|RS232|RS422|modbus|TCP|UDP|ping|serial)\b', query, re.I)
    def rank(call):
        exact = call.get('instance', call['name']).casefold() in query_tokens or call['name'].casefold() in query_tokens
        named_file = bool(file_focus and Path(call['file']).name.casefold() == file_focus.group(1).casefold())
        focused = not focus or (focus.group().casefold() in (call['family']+' '+call['name']).casefold())
        if focus and focus.group().upper().startswith('RS'): focused = 'serial' in call['family'].casefold()
        return (not exact, not named_file, not focused, call['ownership'] != 'active task', call['file'], call['eventLine'])
    unique = {}; calls = sorted(calls, key=rank)
    for call in calls: unique.setdefault((call['file'], call.get('instance', call['name']), call['family']), call)
    calls = list(unique.values())
    chosen, seen = [], set()
    def include(record):
        nonlocal characters
        event = record.get('eventLine', record.get('line', 0))
        if not record.get('network') and any(e['file'] == record['file'] and not e.get('network') and e['line'] <= event < e['line'] + len(e['excerpt'].splitlines()) for e in chosen): return True
        item = _evidence(record, index)
        if not item: return False
        key = (item['file'], item['line'], item.get('network'))
        if key in seen: return True
        if len(chosen) >= limit or len(item['excerpt']) > characters: return False
        chosen.append(item); seen.add(key); characters -= len(item['excerpt']); return True
    communication = []
    if intent['communication']:
        for call in calls[:8]:
            if not include(call): continue
            typed = []
            for symbol in call['declarations']:
                if include({**symbol, 'eventLine': symbol['line'], 'category': 'Declarations', 'ownership': 'declaration; scope matched to call'}):
                    typed.append(re.match(r'\w+', symbol['declaration']).group())
            if call['declarations'] and not typed:
                # Presence based on an unresolved instance cannot prove a protocol.
                continue
            trace = []
            trace_name = call.get('instance', call['name'])
            names = {trace_name.casefold()}
            related = [r for r in records if r['file'] == call['file'] and r['kind'] in {'assignment', 'branch'} and
                       (trace_name.casefold()+'.' in (r.get('name', '')+' '+r.get('expression', '')).casefold() or
                        (call.get('network') is None and abs(r['eventLine']-call['eventLine']) < 12))]
            related.sort(key=lambda r: (r['kind'] != 'branch', abs(r['eventLine']-call['eventLine'])))
            for record in related[:6]:
                names.update(n.casefold() for n in re.findall(r'\b[A-Za-z_]\w*\b', record.get('value', '')))
                if include(record): trace.append({k: record[k] for k in ('kind', 'file', 'eventLine', 'name', 'value', 'expression') if k in record})
            # Initialization/ADR settings can live in a sibling Init file.
            peers = [r for r in records if Path(r['file']).parent == Path(call['file']).parent and
                     r['kind'] == 'assignment' and r.get('name', '').casefold() in names]
            for record in peers[:4]:
                if include(record): trace.append({k: record[k] for k in ('kind', 'file', 'eventLine', 'name', 'value') if k in record})
            communication.append({k: call[k] for k in ('file', 'eventLine', 'name', 'family', 'ownership')} | {'blockTypes': typed or call['blockTypes'], 'typeSources': [{'file': s['file'], 'line': s['line']} for s in call['declarations']], 'trace': trace})
        for setting in settings[:6]: include(setting)
    for item in fallback_evidence:
        include({**item, 'eventLine': item['line']})
    # Details cite only evidence actually retained. Full counts are coverage metadata.
    review = []
    if intent['improvement']:
        for item in chosen[:6]:
            excerpt = _mask(item['excerpt'])
            topics = []
            if re.search(r'\b(?:Step|State)\b', excerpt, re.I): topics.append('Review state transitions, busy/error branches and recovery paths in the complete state machine.')
            if re.search(r'timeout|TON|retry|ping_try', excerpt, re.I): topics.append('Check timeout units, retry limits and reset behavior against the selected library contract.')
            if re.search(r'\bADR\s*\(|memcpy|brsmemcpy|pData|datalen|recvlen', excerpt, re.I): topics.append('Review buffer length, pointer lifetime and received-length checks before decoding.')
            if re.search(r'DO_|MOTOR|MC_ON|MC_OFF|interlock', excerpt, re.I): topics.append('Trace stop/fault interlocks and output reset behavior across all writers before proposing a change.')
            if topics: review.append({'file': item['file'], 'line': item['line'], 'suggestions': topics[:2], 'kind': 'review candidate; not a proven defect'})
    functions = []
    if intent['machine']:
        for item in chosen:
            if item['category'] not in {'Logic', 'Ladder'}: continue
            actions = [r for r in records if r['file'] == item['file'] and r['kind'] == 'assignment' and
                       item['line'] <= r['eventLine'] < item['line'] + len(item['excerpt'].splitlines())]
            branch = [r for r in records if r['file'] == item['file'] and r['kind'] == 'branch' and
                      item['line'] <= r['eventLine'] < item['line'] + len(item['excerpt'].splitlines())]
            functions.append({'file': item['file'], 'line': item['line'], 'ownership': item['ownership'],
                              'actions': [{'line': r['eventLine'], 'target': r['name'], 'value': r['value']} for r in actions[:5]],
                              'branchHeaders': [{'line': r['eventLine'], 'expression': r['expression']} for r in branch[:3]],
                              'meaning': 'Literal actions and branch headers; assignment guards must be traced in complete source.'})
    return {'intent': intent['kind'], 'normalizedQuestion': query, 'communications': communication, 'machineFunctions': functions,
            'communicationCallSites': len(unique), 'serialSettingSites': len(settings), 'reviewCandidates': review,
            'sourceFingerprint': index['fingerprint'], 'coverage': 'Bounded static traces. Serial settings are literal markers until linked to a block/device; RS485 is a physical interface, not a protocol. No live execution, wiring, complete control-flow proof or automatic source edits.'}, chosen


def local_answer(index, analysis, evidence, base_answer):
    if analysis['intent'] == 'machine functions':
        lines = [base_answer, '\nAdditional literal control actions (trace branch guards before interpreting the sequence):']
        for function in analysis.get('machineFunctions', [])[:8]:
            if not function['actions']: continue
            lines.append(f"{function['file']} ({function['ownership']})")
            lines.extend(f"- Line {a['line']}: {a['target']} := {a['value']}" for a in function['actions'][:3])
        return '\n'.join(lines)
    if analysis['intent'] not in {'communication', 'communication review', 'improvement review'}: return base_answer
    lines = [f"Project: {index['identity'].get('project_name', 'Uploaded project')}",
             f"Active configuration: {index['identity'].get('active_configuration') or 'unresolved / legacy'}", '']
    def cite(file, line):
        match = next((e for e in evidence if e['file'] == file and e['line'] <= line < e['line'] + len(e['excerpt'].splitlines())), None)
        return f"[{match['sourceId']}] {file}:{line}" if match and match.get('sourceId') else f'{file}:{line}'
    if analysis['intent'].startswith('communication'):
        lines.append('Communication code found:' if analysis['communications'] else 'No recognized communication calls were retained in this search. This does not prove the project has no communication.')
        for call in analysis['communications']:
            lines.append(f"- {call['family']}: {call['name']} ({call['ownership']}). {cite(call['file'], call['eventLine'])}")
            if call['blockTypes']: lines.append('  Declared/explicit block type: ' + ', '.join(call['blockTypes']))
            for record in call['trace'][:5]:
                fact = f"{record['name']} := {record['value']}" if record['kind'] == 'assignment' else record['expression']
                lines.append(f"  Source trace: {fact}. {cite(record['file'], record['eventLine'])}")
        if re.search(r'RS(?:485|232|422)|serial|modbus', analysis['normalizedQuestion'], re.I):
            serial = [e for e in evidence if re.search(r'RS[- ]?(?:485|232|422)|/PHY\s*=', _mask(e['excerpt']), re.I)]
            if serial:
                lines.append('\nPhysical-interface / mode markers (link to the actual device before concluding RS485 use):')
                for item in serial[:3]: lines.append('- ' + cite(item['file'], item['line']))
            else: lines.append('\nSerial physical configuration was not established by the retained evidence. Serial/Modbus calls alone do not prove RS485; trace the device and mode string and check hardware/wiring.')
        config = [e for e in evidence if e['category'] in {'Configuration', 'Hardware / I/O'}]
        if config:
            lines.append('\nRelated configuration excerpts (configuration alone does not prove live connectivity):')
            for item in config[:3]: lines.append('- ' + cite(item['file'], item['line']))
    if analysis['reviewCandidates']:
        lines.append('\nImprovement candidates for engineer review:')
        for review in analysis['reviewCandidates']:
            lines.append('- ' + ' '.join(review['suggestions']) + ' ' + cite(review['file'], review['line']))
    elif analysis['intent'] == 'improvement review': lines.extend(['No automatic defect finding was established from these excerpts.', base_answer])
    lines.extend(['', analysis['coverage'], *index.get('notices', [])])
    return '\n'.join(lines)
