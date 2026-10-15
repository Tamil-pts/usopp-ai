"""Read-only, source-backed function flows for IEC text and XML ladder logic."""
from __future__ import annotations

import html
import re
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

SUPPORTED_EXTENSIONS = {'.st', '.ab', '.src', '.ld'}
STRING_PATTERN = r"'(?:\$[^\r\n]|''|[^'$\r\n])*'|\"(?:\$[^\r\n]|\"\"|[^\"$\r\n])*\""
TOKEN = re.compile(STRING_PATTERN + r'|[A-Za-z_]\w*|:=|=>|\r?\n|[^\s]', re.I)
BASIC_TOKEN = re.compile(r"ELSE[ \t]+IF\b|" + TOKEN.pattern, re.I)
STRINGS = re.compile(STRING_PATTERN)
IDENTIFIER = re.compile(r'\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\s*\[[^\]\n]+\])?')
KEYWORDS = set('IF THEN ELSE ELSIF ELSEIF END_IF ENDIF CASE OF END_CASE FOR TO BY DO END_FOR WHILE END_WHILE LOOP ENDLOOP REPEAT UNTIL END_REPEAT PROGRAM END_PROGRAM FUNCTION END_FUNCTION FUNCTION_BLOCK END_FUNCTION_BLOCK VAR END_VAR TYPE END_TYPE TRUE FALSE AND OR NOT XOR MOD FUB EXIT EXITIF RETURN BOOL USINT UINT UDINT INT DINT REAL LREAL STRING TIME BYTE WORD DWORD ADR SIZEOF'.split())
CLOSE = {'END_IF', 'ENDIF', 'END_CASE', 'END_FOR', 'END_WHILE', 'ENDLOOP', 'END_REPEAT'}
NOTICE = ('Shows source order within one program or function call. Cyclic programs repeat on later scans. '
          'This static view does not simulate live values or expand library internals.')


def _mask_comments(text: str, basic: bool) -> str:
    """Retain positions and quoted strings when masking source comments."""
    chars = list(text)
    i = 0
    quote = ''
    while i < len(text):
        if quote:
            if text[i] == '$' and i + 1 < len(text):
                i += 2
                continue
            if text[i] == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = ''
            i += 1
            continue
        if text[i] in "'\"":
            quote = text[i]
            i += 1
            continue
        end = None
        if text.startswith('(*', i):
            closing = text.find('*)', i + 2)
            end = len(text) if closing < 0 else closing + 2
        elif text.startswith('//', i) or basic and text[i] == ';':
            closing = text.find('\n', i)
            end = len(text) if closing < 0 else closing
        if end is not None:
            for j in range(i, end):
                if chars[j] not in '\r\n':
                    chars[j] = ' '
            i = end
        else:
            i += 1
    return ''.join(chars)


def _statements(text: str, basic: bool) -> list[dict]:
    clean = _mask_comments(text, basic)
    newlines = [match.start() for match in re.finditer('\n', clean)]
    rows = []
    start = None
    depth = 0
    end = 0

    def flush(stop):
        nonlocal start
        if start is not None:
            code = clean[start:stop].strip().rstrip(';').strip()
            if code:
                compact = re.sub(STRINGS.pattern + r'|\s+', lambda match: ' ' if match.group().isspace() else match.group(), code)
                rows.append({'code': compact,
                             'line': bisect_right(newlines, start) + 1,
                             'endLine': bisect_right(newlines, max(start, stop - 1)) + 1})
        start = None

    for token in (BASIC_TOKEN if basic else TOKEN).finditer(clean):
        value = token.group()
        upper = value.upper()
        end = token.end()
        if value in {'\n', '\r\n'}:
            if start is not None and not depth:
                pending = clean[start:token.start()].strip().upper()
                header = bool(re.match(r'^(IF|ELSIF|ELSEIF|ELSE\s+IF|CASE|FOR|WHILE|LOOP)\b', pending))
                if pending.startswith(('PROGRAM ', 'FUNCTION ', 'FUNCTION_BLOCK ', 'UNTIL ')) or basic and not header:
                    flush(token.start())
            continue
        if not depth and (upper in CLOSE | {'ELSE', 'END_PROGRAM', 'END_FUNCTION', 'END_FUNCTION_BLOCK', 'REPEAT', 'END_VAR', 'END_TYPE', 'TYPE'} or re.fullmatch(r'VAR(?:_[A-Z]+)?', upper)):
            flush(token.start())
            start = token.start()
            flush(end)
            continue
        if not depth and upper in {'IF', 'ELSIF', 'ELSEIF', 'ELSE IF', 'CASE', 'FOR', 'WHILE', 'LOOP', 'UNTIL', 'PROGRAM', 'FUNCTION', 'FUNCTION_BLOCK'}:
            flush(token.start())
        if start is None:
            start = token.start()
        if value in {'(', '['}:
            depth += 1
        elif value in {')', ']'}:
            depth = max(0, depth - 1)
        if not depth and (value == ';' or upper in {'THEN', 'DO', 'OF'}):
            flush(end)
        elif not depth and value == ':' and re.fullmatch(r'[\w\s,#.\-]+:', clean[start:end].strip()):
            flush(end)
    flush(end)
    return rows


def _names(code: str) -> list[str]:
    clean = STRINGS.sub(' ', code)
    clean = re.sub(r'\b(?:T|TIME|LTIME)#[\w.]+', ' ', clean, flags=re.I)
    # Named FB parameters are not standalone project variables.
    clean = re.sub(r'\b[A-Za-z_]\w*\s*(?::=|=>)', ' ', clean)
    calls = {m.group(1).casefold() for m in re.finditer(r'\b([A-Za-z_]\w*)\s*\(', clean)}
    names = []
    for match in IDENTIFIER.finditer(clean):
        value = match.group().strip()
        if value.upper() in KEYWORDS or value.casefold() in calls:
            continue
        if value not in names:
            names.append(value)
        if '[' in value:
            for index_name in re.findall(r'\b[A-Za-z_]\w*\b', value.split('[', 1)[1]):
                if index_name.upper() not in KEYWORDS and index_name not in names:
                    names.append(index_name)
    return names


def _text_flow(text: str, source_file: str, basic: bool) -> tuple[list, list, list, list]:
    sections = []
    variables = defaultdict(lambda: {'reads': set(), 'writes': set()})
    calls = []
    notices = []
    stack = []
    counter = 0
    section = {'name': Path(source_file).stem, 'nodes': []}
    sections.append(section)
    declaration = False

    def target():
        return stack[-1]['target'] if stack else section['nodes']

    def node(kind, row, **extra):
        nonlocal counter
        counter += 1
        result = {'id': f'n{counter}', 'kind': kind, **row, **extra}
        target().append(result)
        return result

    def reads(code, line):
        for name in _names(code):
            variables[name]['reads'].add(line)

    for row in _statements(text, basic):
        code, line = row['code'], row['line']
        upper = code.upper()
        if re.match(r'^(VAR\w*|TYPE)\b', upper):
            declaration = True
        if declaration:
            if upper in {'END_VAR', 'END_TYPE'}:
                declaration = False
            continue
        if re.match(r'^(PROGRAM|FUNCTION|FUNCTION_BLOCK)\s+', upper):
            if stack:
                notices.append(f'Unclosed control structure before line {line}; inspect this source.')
            stack = []
            section = {'name': code.split(None, 1)[1], 'nodes': []}
            sections.append(section)
            continue
        if upper in {'END_PROGRAM', 'END_FUNCTION', 'END_FUNCTION_BLOCK'}:
            if stack:
                notices.append(f'Unclosed control structure at line {line}; inspect this source.')
            stack = []
            continue
        if upper in CLOSE:
            expected = 'condition' if upper in {'END_IF', 'ENDIF'} else 'case' if upper == 'END_CASE' else 'loop'
            if not stack or stack[-1]['node']['kind'] != expected:
                notices.append(f'Unmatched {code} at line {line}; no branch relationship was guessed.')
                continue
            stack.pop()['node']['endLine'] = row['endLine']
            continue
        if re.match(r'^(ELSIF|ELSEIF|ELSE\s+IF)\b', upper) or upper == 'ELSE':
            if not stack or stack[-1]['node']['kind'] not in {'condition', 'case'}:
                notices.append(f'Unmatched branch at line {line}.')
                continue
            condition = re.sub(r'^(ELSIF|ELSEIF|ELSE\s+IF)\s*|\s*THEN$', '', code, flags=re.I) if upper != 'ELSE' else ''
            branch = {'label': 'ELSE IF' if condition else 'ELSE', 'condition': condition, 'line': line, 'nodes': []}
            stack[-1]['node']['branches'].append(branch)
            stack[-1]['target'] = branch['nodes']
            reads(condition, line)
            continue
        if re.match(r'^IF\b', upper):
            condition = re.sub(r'^IF\s*|\s*THEN$', '', code, flags=re.I)
            branch = {'label': 'TRUE', 'condition': condition, 'line': line, 'nodes': []}
            current = node('condition', row, label='Check condition', condition=condition, branches=[branch])
            stack.append({'node': current, 'target': branch['nodes']})
            reads(condition, line)
            continue
        if re.match(r'^CASE\b', upper):
            expression = re.sub(r'^CASE\s*|\s*OF$', '', code, flags=re.I)
            current = node('case', row, label='Select case', condition=expression, branches=[])
            stack.append({'node': current, 'target': current.setdefault('children', [])})
            reads(expression, line)
            continue
        if code.endswith(':') and stack and stack[-1]['node']['kind'] == 'case':
            branch = {'label': code[:-1], 'condition': '', 'line': line, 'nodes': []}
            stack[-1]['node']['branches'].append(branch)
            stack[-1]['target'] = branch['nodes']
            continue
        if re.match(r'^(FOR|WHILE|LOOP|REPEAT)\b', upper):
            current = node('loop', row, label='Repeat loop', condition=code, children=[])
            stack.append({'node': current, 'target': current['children']})
            iterator=re.match(r'^(FOR|LOOP)\s+([A-Za-z_]\w*)\s*(?::=|=)\s*(.+)$', code, re.I)
            if iterator:
                variables[iterator.group(2)]['writes'].add(line)
                reads(iterator.group(3), line)
            else:
                reads(code, line)
            continue
        if upper.startswith('UNTIL ') and stack and stack[-1]['node']['kind'] == 'loop':
            stack[-1]['node']['until'] = code
            reads(code, line)
            continue
        if re.match(r'^(EXITIF|EXIT|RETURN)\b', upper):
            node('exit', row, label='Exit / return', condition=code)
            reads(code, line)
            continue

        assignment = re.match(r'^([A-Za-z_]\w*(?:\.\w+|\[[^\]]+\])*)\s*(?::=|=(?!=))\s*(.+)$', code)
        call = re.match(r'^([A-Za-z_]\w*)\s+FUB\s+([A-Za-z_]\w*)\s*\(', code, re.I)
        call_names = list(dict.fromkeys(re.findall(r'\b([A-Za-z_]\w*)\s*\(', STRINGS.sub(' ', code))))
        if assignment:
            destination, expression = assignment.groups()
            variables[destination]['writes'].add(line)
            reads(expression, line)
            if '[' in destination:
                reads(destination.split('[', 1)[1], line)
        else:
            reads(code, line)
        statement = {**row, 'kind': 'assignment' if assignment else 'call' if call or call_names else 'source'}
        for name in call_names:
            calls.append({'name': name, 'instance': call.group(1) if call and call.group(2) == name else name,
                          'line': line, 'code': code})
        if target() and target()[-1]['kind'] == 'action':
            target()[-1]['statements'].append(statement)
            target()[-1]['endLine'] = row['endLine']
        else:
            node('action', row, label='Assignments and calls', statements=[statement])
    if stack:
        notices.append('Source ended with an unclosed control structure; inspect the displayed source.')
    sections = [part for part in sections if part['nodes']] or [section]
    variable_rows = _variable_rows(variables)
    return sections, variable_rows, calls, notices


def _ladder_flow(text, source_file):
    from python_engine.compare import _ladder_networks
    networks = _ladder_networks(text, source_file=source_file)
    positions = [match.start() for match in re.finditer(r'<network\b', text, re.I)]
    nodes, calls = [], []
    variables = defaultdict(lambda: {'reads': set(), 'writes': set()})
    for index, network in enumerate(networks):
        line = text.count('\n', 0, positions[index]) + 1 if index < len(positions) else 1
        closing = text.find('</network>', positions[index]) if index < len(positions) else -1
        end_line = text.count('\n', 0, closing) + 1 if closing >= 0 else line
        conditions, actions = [], []
        seen_blocks = set()
        disabled = network['commented']
        for cell in network['diagram']['cells']:
            kind, name, cell_type = cell['kind'], cell['name'], cell['type']
            if kind == 'contact':
                conditions.append(f'{name} [{cell_type}]')
                if not disabled:
                    for variable in _names(name):
                        variables[variable]['reads'].add(line)
            elif kind == 'coil':
                verb = {'set': 'Latch TRUE', 'reset': 'Reset FALSE', 'open': 'Assign rung result'}.get(cell_type, cell_type or 'Coil')
                actions.append(f'{verb}: {name}')
                if not disabled:
                    variables[name]['writes'].add(line)
            elif kind in {'function', 'functionblock'} and cell.get('blockId') not in seen_blocks:
                seen_blocks.add(cell.get('blockId'))
                calls.append({'name': cell_type, 'instance': cell.get('instance') or name or cell_type,
                              'line': line, 'code': f'{cell.get("instance") or name} [{cell_type}]', 'disabled': disabled,
                              'blockId': cell.get('blockId')})
            elif kind == 'analog' and name and not disabled:
                for variable in _names(name):
                    variables[variable]['writes' if cell_type == 'output' else 'reads'].add(line)
        nodes.append({'id': f'rung{index + 1}', 'kind': 'network', 'label': f'Network {index + 1}',
                      'line': line, 'endLine': end_line, 'code': network['comment'] or network['label'],
                      'conditions': conditions, 'actions': actions, 'disabled': disabled,
                      'parallel': any(link['kind'] == 'branch' for link in network['diagram']['connections']),
                      'network': {key: value for key, value in network.items() if not key.startswith('_')}})
    variable_rows = _variable_rows(variables)
    notices = [] if networks else ['This legacy ladder encoding has no XML network model. Export its source from Automation Studio to view rung topology.']
    return [{'name': Path(source_file).stem, 'nodes': nodes}], variable_rows, calls, notices


def _variable_rows(variables):
    combined={}
    for name,value in variables.items():
        key=re.sub(r'\s+','',name).casefold()
        entry=combined.setdefault(key,{'name':name,'reads':set(),'writes':set()})
        entry['reads'].update(value['reads'])
        entry['writes'].update(value['writes'])
    return [{'name':value['name'],'reads':sorted(value['reads']),'writes':sorted(value['writes'])}
            for _,value in sorted(combined.items())]


def _instruction_flow(text,source_file):
    nodes=[]
    variables=defaultdict(lambda:{'reads':set(),'writes':set()})
    calls=[]
    group=[]
    def flush():
        if group:
            nodes.append({'id':f'il{len(nodes)+1}','kind':'action','label':f'Instruction group {len(nodes)+1}',
                          'line':group[0]['line'],'endLine':group[-1]['line'],'code':'', 'statements':list(group)})
            group.clear()
    for line,code in enumerate(_mask_comments(text,False).splitlines(),1):
        code=code.strip()
        if not code:
            flush()
            continue
        group.append({'code':code,'line':line,'endLine':line,'kind':'instruction'})
        instruction=re.match(r'([A-Za-z]+)\s+(.+)',code)
        if instruction:
            op,operand=instruction.groups()
            for name in _names(operand):
                variables[name]['writes' if op.upper() in {'ST','STN','S','R'} else 'reads'].add(line)
            if op.upper() in {'CAL','CALC','CALCN'}:
                calls.append({'name':operand,'instance':operand,'line':line,'code':code})
    flush()
    return [{'name':Path(source_file).stem,'nodes':nodes}],_variable_rows(variables),calls,[
        'Legacy ladder is available as instruction text. Instruction order is shown; rung geometry and jump conditions require the original ladder view.']


def build_function_flow(text: str, source_file: str) -> dict:
    suffix = Path(source_file).suffix.casefold()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError('Function flow supports .st, .ab, .src and .ld implementation files.')
    basic = suffix == '.ab' or bool(re.search(r'\b(?:ENDIF|ENDLOOP|FUB)\b', _mask_comments(text, False), re.I))
    language = 'Automation Basic' if basic else 'Structured Text'
    il_source=bool(re.search(r'^\s*LDN?\s+\S',_mask_comments(text,False),re.I|re.M)) and not re.search(r'<networks\b',text,re.I)
    if suffix in {'.src','.ld'} and il_source:
        language='Instruction List (legacy ladder source)'
        sections,variables,calls,notices=_instruction_flow(text,source_file)
    elif suffix == '.ld':
        language = 'Ladder'
        sections, variables, calls, notices = _ladder_flow(text, source_file)
    else:
        sections, variables, calls, notices = _text_flow(text, source_file, basic)
    from python_engine.working_sequence import build_working_sequence
    for section in sections:
        section['sequences'] = build_working_sequence(section)
    flow = {'schemaVersion': 2, 'sourceFile': source_file, 'language': language,
            'notice': NOTICE, 'sections': sections, 'variables': variables, 'calls': calls,
            'notices': notices, 'sourceLines': text.splitlines()}
    from python_engine.flow_narrative import add_flow_narrative
    return add_flow_narrative(flow)


def flow_html(flow: dict, title: str = '', show_source: bool = True) -> str:
    """Portable working-sequence poster with source or ladder alongside each step."""
    esc = lambda value: html.escape(str(value or ''))
    def facts(items):
        return '<ul>' + ''.join(f'<li>{esc(item["text"])} <small>L{item["line"]}' + (f'–{item["endLine"]}' if item['endLine'] != item['line'] else '') + '</small></li>' for item in items) + '</ul>' if items else ''

    def source(step):
        if step.get('network'):
            from python_engine.ladder_model import render_svg
            return '<div class="rung">' + render_svg(step['network']) + '</div>'
        lines = list(range(step['line'], min(step['endLine'], step['line'] + 13) + 1))
        lines = sorted(set(lines + step['evidenceLines']))
        last, result = 0, []
        for line in lines:
            if not 0 < line <= len(flow['sourceLines']):
                continue
            if last and line > last + 1:
                result.append('<span class="gap">…</span>')
            result.append(f'<span><i>{line}</i> {esc(flow["sourceLines"][line - 1])}</span>')
            last = line
        return '<pre class="snippet">' + ''.join(result) + '</pre>'

    def explanation_html(explanation, link_steps=False):
        if not explanation: return ''
        paragraphs = []
        for item in explanation['paragraphs']:
            label = f'{item["sequenceTitle"]} · Step {item["number"]}'
            link = f'<a href="#flow-step-{esc(item["stepId"])}">{esc(label)}</a>' if link_steps else esc(label)
            paragraphs.append(f'<p>{esc(item["text"])}<br><small>{link} · {esc(item["sourceFile"])}:L{item["line"]}–L{item["endLine"]}</small></p>')
        return '<section class="narrative"><h3>How this subroutine works</h3><p>' + esc(explanation['intro']) + '</p>' + ''.join(paragraphs) + ''.join(f'<p class="note">{esc(note)}</p>' for note in explanation['notes']) + '</section>'

    def call_details(info):
        parameters = ''.join(f'<tr><td>{esc(param["direction"])} {esc(param["name"])}<br><small>{esc(param["dataType"])}</small></td><td>' +
                             (f'<code>{esc(param["value"])}</code><br>' if 'value' in param else '') + esc(param['description']) + '</td></tr>' for param in info['parameters'])
        statuses = ''.join(f'<p><b>{esc(status["name"])} · {esc(status["value"])}</b><br>{esc(status["description"])}</p>' for status in info['statuses'])
        nested = ''
        for sequence in info.get('sequences', []):
            steps = ''.join(f'<article class="outcome"><h4>{step["number"]}. {esc(step["title"])}</h4><p>{esc(" AND ".join(step["when"]))}</p>{facts(step["actions"])}' +
                            ''.join(f'<p><b>When</b> {esc(" AND ".join(outcome["when"]))}</p>{facts(outcome["actions"])}' for outcome in step['outcomes']) +
                            ''.join(call_details(child) for child in step.get('explanations', [])) + '</article>' for step in sequence['steps'])
            nested += f'<details open><summary>Inside {esc(info["name"])} · {esc(sequence["program"])}</summary>{explanation_html(sequence.get("workingExplanation"))}{steps}</details>'
        refs = ''.join(f'<p>{esc(ref["title"])}<br><small>{esc(ref["file"])}</small></p>' for ref in info['references'])
        return f'<section><h4>{esc(info["instance"])} / {esc(info["name"])}</h4><small>{esc(info["kind"])}</small><p>{esc(info["purpose"])}</p><ul>' + ''.join(f'<li>{esc(value)}</li>' for value in info['behavior']) + '</ul>' + (f'<table>{parameters}</table>' if parameters else '') + (f'<details><summary>Documented status codes</summary>{statuses}</details>' if statuses else '') + nested + (f'<details><summary>Explanation references</summary>{refs}</details>' if refs else '') + ''.join(f'<p class="note">{esc(note)}</p>' for note in info['notes'] if not note.startswith('Behavior from the supplied')) + '</section>'

    def poster(lane):
        rows = []
        for step in lane['steps']:
            guards = ''.join(f'<code>{esc(guard)}</code>' for guard in step['when']) or ('Follow the contacts and branches in this rung.' if step.get('network') else 'At this source position')
            def outcome_cards(items):
                return ''.join(f'<div class="outcome"><b>When</b> {" AND ".join(esc(g) for g in outcome["when"])}{facts(outcome["actions"])}</div>' for outcome in items)
            outcomes = outcome_cards(step['outcomes'])
            inputs = outcome_cards(step.get('inputConditions', []))
            settings = ''.join(f'<tr><td>{esc(s["name"])}</td><td><code>{esc(s["value"])}</code></td></tr>' for s in step.get('settings', []))
            path = ''.join(f'<div class="pathBox">{esc(value)}</div>' + ('<div class="arrow">↓</div>' if index < len(step.get('dataPath', [])) - 1 else '') for index, value in enumerate(step.get('dataPath', [])))
            call = step.get('call')
            block = f'<h4>Function block</h4><code>{esc(call["instance"])}</code><p>{esc(call["name"])}</p>' if call else ''
            details = (f'<h4>Data path</h4>{path}' if path else '') + block + (f'<h4>Configured inputs</h4><table>{settings}</table>' if settings else '')
            if step.get('explanations'):
                details = (f'<h4>Data path</h4>{path}' if path else '') + ''.join(call_details(info) for info in step['explanations'])
            if not details:
                names = [v for v in flow['variables'] if any(step['line'] <= line <= step['endLine'] for line in v['reads'] + v['writes'])]
                details = '<h4>Variables in this step</h4>' + ''.join(f'<p><code>{esc(v["name"])}</code></p>' for v in names[:12])
            disabled = '<p class="note">Commented network — inactive</p>' if step.get('disabled') else ''
            source_column = f'<section class="source"><h4>Step {step["number"]} · Source evidence</h4>{source(step)}</section>' if show_source else ''
            rows.append(f'<div class="posterRow" id="flow-step-{esc(step["id"])}">{source_column}<section class="step {esc(step["kind"])}"><header><span class="number">{step["number"]}</span><h3>{esc(step["title"])}</h3></header>{disabled}<div class="trigger"><b>Trigger</b>{guards}</div>{inputs}{facts(step["actions"])}{outcomes}<small>Reference: {esc(flow["sourceFile"])}:L{step["line"]}–L{step["endLine"]}</small></section><aside>{details}</aside></div>')
        source_heading = '<b>PLC source / ladder logic</b>' if show_source else ''
        return f'<section class="lane"><h2>{esc(lane["title"])} <small>· Step by step</small></h2><p>{esc(lane["caption"])}</p><div class="columnHeads">{source_heading}<b>Working sequence</b><b>Functions / blocks explained</b></div>' + '<div class="connector">↓</div>'.join(rows) + f'<p class="note">{esc(lane["arrowNote"])}</p></section>'

    body = ''.join(f'<h2 class="program">{esc(section["name"])}</h2>' + explanation_html(section.get('workingExplanation'), True) + ''.join(poster(lane) for lane in section['sequences']) for section in flow['sections'])
    rows = ''.join(f'<tr><td><code>{esc(row["name"])}</code></td><td>{esc(", ".join(map(str,row["reads"])))}</td><td>{esc(", ".join(map(str,row["writes"])))}</td></tr>' for row in flow['variables'])
    calls = ''.join(f'<li><code>{esc(call["instance"])} / {esc(call["name"])}</code> — L{call["line"]}</li>' for call in flow['calls'])
    complete_source = f'<details><summary>Complete source</summary><pre>{esc(chr(10).join(f"{i+1:4}  {line}" for i,line in enumerate(flow["sourceLines"])))}</pre></details>' if show_source else ''
    layout_override = '' if show_source else '<style>.columnHeads,.posterRow{grid-template-columns:minmax(0,1.1fr) minmax(0,1fr)}@media(max-width:1000px){.posterRow{grid-template-columns:1fr}}</style>'
    narrative_style = '<style>.narrative{background:white;border:1px solid #ccdae2;border-left:4px solid #09896a;border-radius:10px;padding:20px;margin:18px 0}.narrative h3{margin-bottom:14px}.narrative p{line-height:1.85;overflow-wrap:anywhere}.narrative p small{display:block;margin-top:6px}.narrative a{color:#157a63}</style>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title or flow['sourceFile'])} — Function flow</title>
<style>body{{font:14px/1.5 system-ui;background:#edf3f5;color:#16313b;margin:0;padding:24px}}main{{max-width:1600px;margin:auto}}.hero{{background:#153f60;color:white;padding:26px;border-radius:16px}}h1{{margin:0 0 8px;font-size:30px}}h2{{margin:0 0 6px}}h3{{font-size:17px;margin:0}}h4{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin:0 0 12px}}small{{font-size:11px;color:#536f7e}}.hero small{{color:#c5e5ef}}.program{{margin:24px 0}}.lane{{margin:26px 0;background:white;border:1px solid #ccdae2;border-radius:14px;padding:18px}}.columnHeads,.posterRow{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr) minmax(180px,.7fr);gap:16px}}.columnHeads{{background:#184f75;color:white;padding:12px;border-radius:8px;margin:20px 0}}.posterRow{{align-items:stretch}}.source,aside{{min-width:0;background:#f4f8fb;border:1px solid #d2dfe8;padding:14px;border-radius:10px}}.step{{background:#edf9f4;border:1px solid #aed7c6;border-left:5px solid #0b9673;border-radius:10px;padding:16px;min-width:0}}.step.write{{background:#f4f1fd;border-color:#c6b7e8;border-left-color:#7658b1}}.step.support{{background:#fff8e7;border-color:#ead79a;border-left-color:#cb931b}}.step header{{display:flex;gap:12px;align-items:center;margin-bottom:14px}}.number{{display:grid;place-items:center;flex:0 0 34px;height:34px;border-radius:50%;background:#09896a;color:white;font-weight:750;font-size:20px}}.write .number{{background:#7658b1}}.support .number{{background:#b77d0a}}.trigger{{border-bottom:1px solid #cbded9;padding-bottom:12px;margin-bottom:12px}}.trigger b{{display:block;color:#36675e;font-size:11px;text-transform:uppercase}}.trigger code{{display:block;margin-top:5px}}.outcome{{margin:12px 0;padding:10px 12px;border-radius:8px;background:#ffffffb8;border:1px solid #d4e3de;font-size:12px;overflow-wrap:anywhere}}.outcome>b{{color:#157a63}}ul{{padding-left:20px;margin:9px 0}}li{{margin:7px 0;overflow-wrap:anywhere}}code{{font:12px/1.6 Consolas,monospace;overflow-wrap:anywhere}}.snippet{{font:11px/1.6 Consolas,monospace;overflow:auto;max-height:440px;margin:0}}.snippet span{{display:block;white-space:pre-wrap;overflow-wrap:anywhere}}.snippet i{{display:inline-block;font-style:normal;color:#718e9e;width:26px}}.gap{{color:#8298a3}}.pathBox{{background:white;border:1px solid #9bc0d6;padding:12px;text-align:center;border-radius:8px;font:13px Consolas,monospace;overflow-wrap:anywhere}}.arrow,.connector{{color:#2576a0;text-align:center;font-size:26px}}.connector{{width:43%;margin-left:34%;padding:6px}}aside h4{{margin-top:15px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:7px;text-align:left;vertical-align:top;border-bottom:1px solid #dce5e8;font-size:12px}}.note{{background:#e8f2f8;padding:12px;border-radius:8px;color:#40637a}}summary{{cursor:pointer;font-weight:650;padding:12px}}details{{margin-top:16px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.rung{{overflow:auto}}.rung svg{{max-width:100%;height:auto}}@media(max-width:1000px){{.posterRow{{grid-template-columns:1fr}}.columnHeads{{display:none}}.source{{order:2}}.step{{order:1}}aside{{order:3}}.connector{{width:100%;margin:0}}}}@media print{{body{{padding:0}}.posterRow{{break-inside:avoid}}.snippet{{max-height:none}}.hero{{print-color-adjust:exact}}}}</style>
{narrative_style}{layout_override}<main><header class="hero"><h1>{esc(title or Path(flow['sourceFile']).stem)} — Working sequence</h1><small>{esc(flow['language'])} · {esc(flow['sourceFile'])} · {esc(flow.get('lineBasis','Source file'))}</small></header><p class="note">{esc(flow['notice'])}</p>{body}<details><summary>All variables and source lines ({len(flow['variables'])})</summary><table><tr><th>Variable</th><th>Read at lines</th><th>Written at lines</th></tr>{rows}</table></details><details><summary>All function calls ({len(flow['calls'])})</summary><ul>{calls}</ul></details>{complete_source}{''.join(f'<p class="note">{esc(n)}</p>' for n in flow['notices'])}</main></html>'''
