"""Turn parsed PLC statements into visible, numbered working steps.

The syntax tree remains the evidence. Steps describe operations and retain their
guards; arrows indicate source progression, never a simulated machine timeline.
"""
from __future__ import annotations

import re


CONFIG_CALLS = {
    'cfggetipaddr': ('read', 'Read the current IP address'),
    'cfggetsubnetmask': ('read', 'Read the subnet mask'),
    'cfggetdefaultgateway': ('read', 'Read the default gateway'),
    'cfgsetipaddr': ('write', 'Apply the new IP address'),
    'cfgsetsubnetmask': ('write', 'Apply the new subnet mask'),
    'cfgsetdefaultgateway': ('write', 'Apply the new default gateway'),
}
ASSIGNMENT = re.compile(r'^([A-Za-z_]\w*(?:\.\w+|\[[^\]]+\])*)\s*(?::=|=(?!=))\s*(.+)$')
CALL = re.compile(r'^([A-Za-z_]\w*)\s+(?:FUB\s+)([A-Za-z_]\w*)\s*\(', re.I)
DIRECT_CALL = re.compile(r'^([A-Za-z_]\w*)\s*\(', re.I)


def operation(row):
    if row.get('resolvedCall'):
        return row['resolvedCall']
    match = CALL.match(row['code'])
    if match:
        return {'instance': match[1], 'name': match[2], 'line': row['line']}
    match = DIRECT_CALL.match(row['code'])
    if match and row.get('kind') == 'call':
        return {'instance': match[1], 'name': match[1], 'line': row['line']}
    return None


def title_for(call):
    return CONFIG_CALLS.get(call['name'].casefold(), ('', f'Call {call["instance"]}'))[1]


def branch_guard(node, index):
    branch = node['branches'][index]
    if node['kind'] == 'case':
        return (f'{node["condition"]} matches {branch["label"]}' if branch['label'] != 'ELSE'
                else f'Other CASE values of {node["condition"]}')
    earlier = [b['condition'] for b in node['branches'][:index] if b.get('condition')]
    parts = [f'NOT ({condition})' for condition in earlier]
    if branch.get('condition'):
        parts.append(branch['condition'])
    return ' AND '.join(f'({part})' for part in parts) if len(parts) > 1 else (parts[0] if parts else 'Otherwise')


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get('children', []))
        for branch in node.get('branches', []):
            yield from walk(branch['nodes'])


def records(nodes, guards=(), guard_lines=()):
    for index, node in enumerate(nodes):
        if node['kind'] == 'action':
            for row_index, row in enumerate(node['statements']):
                yield {'row': row, 'node': node, 'nodes': nodes, 'index': index,
                       'rowIndex': row_index, 'guards': list(guards), 'guardLines': list(guard_lines)}
        for branch_index, branch in enumerate(node.get('branches', [])):
            yield from records(branch['nodes'], (*guards, branch_guard(node, branch_index)), (*guard_lines, branch['line']))
        yield from records(node.get('children', []), (*guards, node['condition']) if node['kind'] == 'loop' else guards,
                           (*guard_lines, node['line']) if node['kind'] == 'loop' else guard_lines)


def fact(text, line, end_line=None):
    return {'text': text, 'line': line, 'endLine': end_line or line}


def statement_facts(rows):
    """Compress string construction; retain all other direct assignments."""
    facts = []
    builders = [r for r in rows if re.search(r'\b(?:itoa|strcat)\s*\(', r['code'], re.I)]
    built = False
    # Only call this a dotted address when the source actually appends a dot.
    dotted = any(re.search(r'''\bstrcat\s*\(.*ADR\s*\(\s*["']\.["']\s*\)''', r['code'], re.I) for r in builders)
    arrays = list(dict.fromkeys(re.findall(r'\bitoa\s*\(\s*([A-Za-z_]\w*)\[\d+\]', ' '.join(r['code'] for r in builders), re.I)))
    for row in rows:
        if row in builders and dotted and len(arrays) == 1:
            if not built:
                buffer = re.search(r'\bitoa\s*\([^,]+,\s*ADR\s*\((\w+)\)', builders[0]['code'], re.I)
                facts.append(fact(f'Build dotted text {"in " + buffer[1] if buffer else ""} from {arrays[0]} using itoa and strcat.',
                                  builders[0]['line'], builders[-1]['endLine']))
                built = True
            continue
        match = ASSIGNMENT.match(row['code'])
        if match:
            destination, expression = match.groups()
            hours = re.fullmatch(r'(\w*HOUR\w*)\s*\*\s*60\s*\*\s*60', expression, re.I)
            text = (f'Convert {hours[1]} from hours to seconds; store the result in {destination}.' if hours
                    else f'Set {destination} to {expression}.')
            facts.append(fact(text, row['line'], row['endLine']))
        else:
            call = operation(row)
            facts.append(fact(f'Call {call["instance"]} ({call["name"]}).' if call else f'Execute {row["code"]}.', row['line'], row['endLine']))
    compact = []
    for item in facts:
        match = re.fullmatch(r'Set (.+) to (0|1|TRUE|FALSE)\.', item['text'])
        previous = re.fullmatch(r'Set (.+) to (0|1|TRUE|FALSE)\.', compact[-1]['text']) if compact else None
        if match and previous and match[2] == previous[2]:
            compact[-1]['text'] = f'Set {previous[1]}, {match[1]} to {match[2]}.'
            compact[-1]['endLine'] = item['endLine']
        else:
            compact.append(item)
    return compact


def loop_facts(node):
    all_rows = [r['row'] for r in records([node])]
    code = ' '.join(n.get('condition', '') for n in walk([node])) + ' ' + ' '.join(r['code'] for r in all_rows)
    converted = [r for r in all_rows if ASSIGNMENT.match(r['code']) and re.search(r'\batoi\s*\(', r['code'], re.I)]
    separator = re.search(r'(\w+)\[[^\]]+\]\s*=\s*46\b', code)
    end_marker = re.search(r'(\w+)\[[^\]]+\]\s*=\s*0\b', code)
    if converted and separator and end_marker and separator[1].casefold() == end_marker[1].casefold():
        targets = ', '.join(ASSIGNMENT.match(r['code'])[1] for r in converted)
        # Original source remains available beside the summary, including exits.
        item = fact(f'Split {separator[1]} at a dot (byte 46) or end marker (byte 0); convert the extracted text with atoi and store it in {targets}.',
                    converted[0]['line'], converted[-1]['endLine'])
        item['sourceLines'] = [n['line'] for n in walk([node]) if re.search(re.escape(separator[1]) + r'\[[^\]]+\]\s*=\s*(?:0|46)\b', n.get('condition', ''))]
        return [item]
    result = [fact(f'Repeat {node["condition"]}' + (f'; stop at {node["until"]}.' if node.get('until') else '.'), node['line'], node['endLine'])]
    result.extend(actions_for(node.get('children', [])))
    return result


def first_operation(nodes):
    return next((operation(record['row']) for record in records(nodes) if operation(record['row'])), None)


def actions_for(nodes, prefix=''):
    result = []
    for node in nodes:
        if node['kind'] == 'action':
            for item in statement_facts(node['statements']):
                result.append({**item, 'text': prefix + item['text']})
        elif node['kind'] == 'loop':
            result.extend({**item, 'text': prefix + item['text']} for item in loop_facts(node))
        elif node.get('branches'):
            for index, branch in enumerate(node['branches']):
                result.extend(actions_for(branch['nodes'], prefix + f'When {branch_guard(node, index)}: '))
        elif node['kind'] == 'exit':
            result.append(fact(prefix + node['code'] + '.', node['line'], node['endLine']))
        else:
            result.extend(actions_for(node.get('children', []), prefix))
    return result


def outcomes_for(nodes, prefix=()):
    outcomes = []
    for node in nodes:
        if not node.get('branches'):
            continue
        for index, branch in enumerate(node['branches']):
            guards = (*prefix, branch_guard(node, index))
            next_record = next((record for record in records(branch['nodes']) if operation(record['row'])), None)
            next_call = operation(next_record['row']) if next_record else None
            if next_call:
                outcomes.append({'when': [*guards, *next_record['guards']], 'actions': [fact(f'Continue to {title_for(next_call).lower()} through {next_call["instance"]}.', next_call['line'])], 'line': branch['line']})
                continue
            # Preserve e.g. gateway status 29009, then the nested status 0 / ELSE.
            nested = [n for n in branch['nodes'] if n.get('branches')]
            direct = [n for n in branch['nodes'] if not n.get('branches')]
            if direct:
                outcomes.append({'when': list(guards), 'actions': actions_for(direct), 'line': branch['line']})
            if nested:
                outcomes.extend(outcomes_for(nested, guards))
            if not branch['nodes']:
                outcomes.append({'when': list(guards), 'actions': [], 'line': branch['line']})
    return outcomes


def call_step(record):
    row, node = record['row'], record['node']
    call = operation(row)
    preceding_call = max((index for index, item in enumerate(node['statements'][:record['rowIndex']]) if operation(item)), default=-1)
    before = node['statements'][preceding_call + 1:record['rowIndex']]
    next_call_index = next((index for index in range(record['rowIndex'] + 1, len(node['statements'])) if operation(node['statements'][index])), len(node['statements']))
    trailing = node['statements'][record['rowIndex'] + 1:next_call_index]
    settings, preparation = [], []
    for item in before:
        match = ASSIGNMENT.match(item['code'])
        if match and match[1].casefold().startswith(call['instance'].casefold() + '.'):
            settings.append({'name': match[1].split('.', 1)[1], 'value': match[2], 'line': item['line']})
        else:
            preparation.append(item)
    # Inline named inputs are evidence too, e.g. timer(IN := run, PT := T#3S).
    if not CALL.match(row['code']):
        depth, quote, start, arguments = 0, '', row['code'].find('(') + 1, []
        for index in range(start, len(row['code'])):
            char = row['code'][index]
            if quote:
                if char == quote and (index == 0 or row['code'][index - 1] != '$'):
                    quote = ''
            elif char in "'\"":
                quote = char
            elif char in '([':
                depth += 1
            elif char in ')]':
                if not depth:
                    arguments.append(row['code'][start:index])
                    break
                depth -= 1
            elif char == ',' and not depth:
                arguments.append(row['code'][start:index])
                start = index + 1
        for argument in arguments:
            match = re.match(r'\s*(\w+)\s*:=\s*(.+)', argument)
            if match:
                settings.append({'name': match[1], 'value': match[2].strip(), 'line': row['line']})
    after = record['nodes'][record['index'] + 1:] if next_call_index == len(node['statements']) else []
    status_nodes = []
    for child in after:
        if child['kind'] in {'condition', 'case'} and re.search(r'\b' + re.escape(call['instance']) + r'\.', child.get('condition', ''), re.I):
            status_nodes.append(child)
        else:
            break
    kind = CONFIG_CALLS.get(call['name'].casefold(), ('operation', ''))[0]
    is_timer = call['name'].upper() in {'TON', 'TOF', 'TP'}
    if is_timer:
        kind = 'support'
    step = {'id': node['id'] + '-' + str(row['line']), 'title': title_for(call) if not is_timer else f'Run {call["instance"]}',
            'kind': kind, 'when': record['guards'], 'actions': statement_facts(preparation) + [fact(f'Call {call["instance"]} ({call["name"]}).', row['line'])] + statement_facts(trailing),
            'outcomes': outcomes_for(status_nodes), 'call': call, 'settings': settings,
            'guardLines': record['guardLines'], 'line': before[0]['line'] if before else row['line'],
            'endLine': max([trailing[-1]['endLine'] if trailing else row['endLine']] + [n['endLine'] for n in status_nodes])}
    # Keep preparation and completion evidence without swallowing the next setter.
    next_calls = [operation(r['row']) for n in status_nodes for r in records([n]) if operation(r['row'])]
    if next_calls:
        step['endLine'] = row['endLine']
    device = next((s['value'] for s in settings if s['name'].casefold() == 'pdevice'), '')
    endpoint = re.fullmatch(r'''ADR\s*\(\s*(["'])(.*?)\1\s*\)''', device, re.I)
    buffer = next((s['value'] for s in settings if s['name'].casefold() in {'pipaddr', 'psubnetmask', 'pgateway'}), '')
    decoded = [ASSIGNMENT.match(r['row']['code'])[1] for n in status_nodes for r in records([n])
               if ASSIGNMENT.match(r['row']['code']) and re.search(r'\batoi\s*\(', r['row']['code'], re.I)]
    built_arrays = list(dict.fromkeys(re.findall(r'\bitoa\s*\(\s*(\w+)\[', ' '.join(r['code'] for r in preparation), re.I)))
    if endpoint and buffer:
        buffer_match = re.fullmatch(r'ADR\s*\(\s*(\w+)\s*\)', buffer, re.I)
        values = [endpoint[2], buffer_match[1] if buffer_match else buffer]
        if kind == 'read' and decoded:
            values.extend(dict.fromkeys(decoded))
        elif kind == 'write':
            values = built_arrays + list(reversed(values))
        step['dataPath'] = values
    if is_timer:
        previous = record['nodes'][:record['index']]
        input_node = next((n for n in reversed(previous) if any(re.match(re.escape(call['instance']) + r'\.IN\s*(?::=|=)', r['row']['code'], re.I) for r in records([n]))), None)
        if input_node:
            step['inputConditions'] = outcomes_for([input_node])
            step['line'] = input_node['line']
        step['actions'] = statement_facts(preparation) + [fact(f'Call {call["instance"]} ({call["name"]})' +
                           (' with ' + ', '.join(f'{s["name"]} = {s["value"]}' for s in settings) if settings else '') + '.', row['line'])] + statement_facts(trailing)
    return step


def ordinary_step(node):
    if node['kind'] == 'network':
        return ladder_step(node)
    assignments = [ASSIGNMENT.match(r['row']['code']) for r in records([node])]
    targets = list(dict.fromkeys(m[1].split('[', 1)[0] for m in assignments if m))
    title = f'Update {", ".join(targets[:3])}' if targets else node.get('label') or 'Execute source instructions'
    return {'id': node['id'], 'title': title, 'kind': 'logic', 'when': [node['condition']] if node['kind'] in {'condition', 'loop'} else [],
            'line': node['line'], 'endLine': node['endLine'], 'actions': actions_for([node]) if node['kind'] != 'condition' else [],
            'outcomes': outcomes_for([node]) if node['kind'] == 'condition' else []}


def ladder_step(node):
    """Explain connected series paths, keeping parallel wiring in the diagram."""
    network = node['network']
    cells = network['diagram']['cells']
    by_id = {c['id']: c for c in cells}
    incoming = {}
    for edge in network['diagram']['connections']:
        if edge['kind'] == 'series':
            incoming.setdefault(edge['to'], []).append(edge['from'])
    contacts = [c for c in cells if c['kind'] == 'contact']
    coils = [c for c in cells if c['kind'] == 'coil']
    blocks = {}
    for cell in cells:
        if cell['kind'] in {'function', 'functionblock'}:
            blocks.setdefault(cell['blockId'], []).append(cell)

    def contact_text(cell):
        return {'open': f'{cell["name"]} is TRUE', 'closed': f'{cell["name"]} is FALSE',
                'positive transition': f'Rising edge of {cell["name"]}',
                'negative transition': f'Falling edge of {cell["name"]}'}.get(cell['type'], f'{cell["name"]} [{cell["type"]}]')

    def path_guard(target):
        if node.get('parallel'):
            return ''
        parts, current, visited = [], target, set()
        while incoming.get(current['id']):
            parents = incoming[current['id']]
            if len(parents) != 1 or parents[0] in visited:
                return ''
            visited.add(parents[0])
            current = by_id[parents[0]]
            if current['kind'] == 'contact' and current['name'].upper() != 'TRUE':
                parts.insert(0, contact_text(current))
            elif current['kind'] in {'function', 'functionblock'}:
                parts.insert(0, f'{current.get("instance") or current["type"]} output is TRUE')
            elif current['kind'] not in {'line', 'contact'}:
                return ''
        return ' AND '.join(parts)

    actions, coil_actions, conditions, settings = [], [], [], []
    for coil in coils:
        guard = path_guard(coil)
        if guard and len(coils) == 1 and not blocks:
            conditions.append(guard)
        verb = {'set': f'Latch {coil["name"]} TRUE when its rung conducts.',
                'reset': f'Reset {coil["name"]} FALSE when its rung conducts.',
                'open': f'Set {coil["name"]} TRUE when its rung conducts; FALSE otherwise.'}.get(coil['type'], f'Apply {coil["type"]} coil to {coil["name"]}.')
        coil_actions.append(fact((f'When {guard}: ' if guard and (len(coils) > 1 or blocks) else '') + verb, node['line']))
    call = None
    for block_cells in blocks.values():
        block = block_cells[0]
        instance = block.get('instance') or block['type']
        if len(blocks) == 1:
            call = {'instance': instance, 'name': block['type'], 'line': node['line']}
        actions.append(fact(f'Evaluate {instance} ({block["type"]}) using its connected inputs.', node['line']))
        for cell in block_cells:
            if cell.get('inputs'):
                for parent_id in incoming.get(cell['id'], []):
                    parent = by_id[parent_id]
                    if parent['kind'] == 'analog':
                        for pin in cell['inputs']:
                            actions.append(fact(f'{instance}.{pin} receives {parent["name"]}.', node['line']))
                            if len(blocks) == 1:
                                settings.append({'name': pin, 'value': parent['name'], 'line': node['line']})
                if 'IN' in cell['inputs']:
                    guard = path_guard(cell)
                    if guard:
                        actions.append(fact(f'Drive {instance}.IN TRUE when {guard}; FALSE otherwise.', node['line']))
                        if len(blocks) == 1:
                            settings.append({'name': 'IN', 'value': guard, 'line': node['line']})
    if node.get('parallel'):
        actions.insert(0, fact('Evaluate the parallel paths shown in the rung diagram.', node['line']))
        actions.extend(fact(contact_text(c) + '.', node['line']) for c in contacts)
    actions.extend(coil_actions)
    targets = [c['name'] for c in coils]
    inferred_title = (f'Update {", ".join(targets)}' if targets else f'Run {call["instance"]}' if call else node['label'])
    return {'id': node['id'], 'title': network.get('comment') or inferred_title, 'kind': 'rung', 'when': conditions,
            'line': node['line'], 'endLine': node['endLine'], 'actions': actions, 'outcomes': [],
            'network': network, 'disabled': node.get('disabled', False), 'settings': settings, **({'call': call} if call else {})}


def build_working_sequence(section):
    operations = [record for record in records(section['nodes']) if operation(record['row'])]
    steps = [call_step(record) for record in operations]
    timer_instances = [s['call']['instance'].casefold() for s in steps if s['kind'] == 'support']
    for node in section['nodes']:
        if first_operation([node]):
            continue
        rows = [r['row'] for r in records([node])]
        condition = node.get('condition', '').casefold()
        timer_only = bool(rows) and all((m := ASSIGNMENT.match(r['code'])) and
                                       (any(m[1].casefold().startswith(name + '.') for name in timer_instances) or
                                        any(name + '.q' in condition for name in timer_instances)) for r in rows)
        if timer_only:
            continue
        steps.append(ordinary_step(node))
    # Keep assignments in alternate branches around a call, e.g. IF run THEN
    # block(); ELSE output := FALSE; END_IF. These are separate guarded steps.
    covered = [(s['line'], s['endLine']) for s in steps]
    remaining = {}
    for record in records(section['nodes']):
        row = record['row']
        if not any(start <= row['line'] <= end for start, end in covered):
            entry = remaining.setdefault(record['node']['id'], {'record': record, 'rows': []})
            entry['rows'].append(row)
    for entry in remaining.values():
        record, rows = entry['record'], entry['rows']
        step = ordinary_step({**record['node'], 'statements': rows})
        step.update(when=record['guards'], guardLines=record['guardLines'], line=rows[0]['line'], endLine=rows[-1]['endLine'])
        steps.append(step)
    steps.sort(key=lambda s: (s['line'], s['id']))
    specialized = any(s['kind'] in {'read', 'write'} for s in steps)
    lanes = []
    definitions = [('read', 'Read addresses', 'Follow the read request flags and each returned status.'),
                   ('write', 'Apply addresses', 'Follow the write request and the status checks shown on each step.'),
                   ('other', 'Checks every scan', 'Preparation and status indicators run at their own source positions.')]
    if not specialized:
        definitions = [('all', 'Working sequence', 'Follow the source conditions and the resulting actions, step by step.')]
    for key, title, caption in definitions:
        values = [s for s in steps if key == 'all' or s['kind'] == key or key == 'other' and s['kind'] not in {'read', 'write'}]
        if not values:
            continue
        for index, step in enumerate(values):
            step['number'] = index + 1
            # Variable evidence belongs to the selected step, rather than to a guessed physical I/O list.
            step_facts = step['actions'] + [f for o in step['outcomes'] + step.get('inputConditions', []) for f in o['actions']]
            step['evidenceLines'] = sorted(set([step['line'], step['endLine']] + step.get('guardLines', []) +
                                              [o['line'] for o in step['outcomes'] + step.get('inputConditions', [])] +
                                              [line for f in step_facts for line in list(range(f['line'], f['endLine'] + 1)) + f.get('sourceLines', [])]))
        lanes.append({'id': key, 'title': title, 'caption': caption, 'steps': values,
                      'arrowNote': 'Source order; proceed only when the next step\'s conditions are met.'})
    return lanes
