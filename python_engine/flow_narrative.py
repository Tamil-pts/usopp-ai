"""Connect verified working steps into prose without executing PLC code."""
from __future__ import annotations

import re


def words(items):
    values = [str(item) for item in items if item]
    return ', '.join(values[:-1]) + ' and ' + values[-1] if len(values) > 1 else ''.join(values)


def unwrapped(value):
    value = value.strip()
    while value.startswith('(') and value.endswith(')'):
        depth, quote, balanced = 0, '', True
        for index, char in enumerate(value):
            if quote:
                if char == quote and (index == 0 or value[index - 1] != '$'): quote = ''
            elif char in "'\"": quote = char
            elif char == '(': depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0 and index < len(value) - 1:
                    balanced = False
                    break
        if not balanced or depth: break
        value = value[1:-1].strip()
    return value


def split_operator(value, operator):
    depth, quote = 0, ''
    for index, char in enumerate(value):
        if quote:
            if char == quote and (index == 0 or value[index - 1] != '$'): quote = ''
            continue
        if char in "'\"": quote = char
        elif char in '([': depth += 1
        elif char in ')]': depth -= 1
        elif depth == 0 and value[index:index + len(operator)].upper() == operator:
            before, after = value[index - 1:index], value[index + len(operator):index + len(operator) + 1]
            if not before or not after or not (before.isalnum() or before == '_') and not (after.isalnum() or after == '_'):
                return value[:index].strip(), value[index + len(operator):].strip()
    return None


def condition(value, explanations=()):
    value = unwrapped(value)
    constant_contact = re.fullmatch(r'(TRUE|FALSE) is (TRUE|FALSE)', value, re.I)
    if constant_contact: return 'TRUE' if constant_contact[1].upper() == constant_contact[2].upper() else 'FALSE'
    for operator, joiner in [('OR', 'or'), ('XOR', 'or, but not both'), ('AND', 'and')]:
        parts = split_operator(value, operator)
        if parts:
            rendered = [condition(part, explanations) for part in parts]
            if operator == 'XOR': return f'exactly one of ({rendered[0]}) or ({rendered[1]}) is true'
            # Preserve the scope of an OR expression inside an AND expression.
            if operator == 'AND':
                rendered = [f'({text})' if split_operator(unwrapped(part), 'OR') else text for part, text in zip(parts, rendered)]
            return f'{rendered[0]} {joiner} {rendered[1]}'
    if re.match(r'^NOT\b', value, re.I):
        inner = condition(value[3:].strip(), explanations)
        if re.fullmatch(r'[\w.\[\]]+ is TRUE', inner): return inner[:-4] + 'FALSE'
        return 'it is not the case that (' + inner + ')'
    comparison = re.fullmatch(r'(.+?)\s*(>=|<=|<>|!=|=|>|<)\s*(.+)', value)
    if comparison:
        left, operator, right = [part.strip() for part in comparison.groups()]
        status = re.fullmatch(r'(\w+)\.status', left, re.I)
        if status and operator == '=':
            meanings = [item for info in explanations if info['instance'].casefold() == status[1].casefold()
                        for item in info.get('statuses', []) if right.casefold() in {item['name'].casefold(), item['value']}]
            if meanings:
                name = meanings[0]['name'].upper()
                if name == 'ERR_OK': return f'{status[1]} reports success (status {right})'
                if name == 'ERR_FUB_BUSY': return f'{status[1]} is still processing ({right})'
        names = {'>=': 'reaches or exceeds', '<=': 'is less than or equal to', '<>': 'does not equal',
                 '!=': 'does not equal', '=': 'equals', '>': 'is greater than', '<': 'is less than'}
        return f'{left} {names[operator]} {right}'
    if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[[^\]]+\])*', value):
        return value + ' is TRUE' if value.upper() not in {'TRUE', 'FALSE'} else value.upper()
    return value


def duration(value):
    match = re.fullmatch(r'(?:T|TIME)#(\d+(?:\.\d+)?)(MS|S|M|H)', value, re.I)
    if not match: return value
    units = {'MS': 'millisecond', 'S': 'second', 'M': 'minute', 'H': 'hour'}
    amount = 'one' if match[1] == '1' else match[1]
    return amount + ' ' + units[match[2].upper()] + ('' if match[1] == '1' else 's')


def input_text(parameter, explanations=()):
    name, value = parameter['name'], parameter['value']
    address = re.fullmatch(r'ADR\s*\((.*)\)', value, re.I)
    if address: return f'{name} receives the address of {address[1].strip()}'
    if name.upper() == 'PT': return f'PT is set to {duration(value)}'
    if parameter.get('dataType', '').upper() == 'BOOL':
        predicate = condition(value, explanations)
        return f'{name} is set to {predicate}' if predicate.upper() in {'TRUE', 'FALSE', '0', '1'} else f'{name} is TRUE when {predicate}'
    if re.fullmatch(r'\d+', value) and re.search(r'10[- ]ms steps', parameter.get('description', ''), re.I):
        return f'{name} is set to {value}, which represents {int(value) * 10} milliseconds'
    if re.fullmatch(r'\d+', value) and re.search(r'number of bytes', parameter.get('description', ''), re.I):
        return f'{name} is set to {value} bytes'
    return f'{name} is set to {value}'


def call_words(info, explanations=()):
    name, instance = info['name'], info['instance']
    inputs = [param for param in info.get('parameters', []) if param['direction'] in {'IN', 'IN_OUT'} and 'value' in param]
    documented_timer = name.upper() == 'TON' and any(ref['file'].startswith('br_help/') for ref in info.get('references', []))
    if documented_timer:
        preset = next((param['value'] for param in inputs if param['name'].upper() == 'PT'), None)
        text = f'runs the on-delay timer {instance}' + (f' with a preset of {duration(preset)}' if preset else '') + '.'
        supplied = [param for param in inputs if param['name'].upper() != 'PT']
        if supplied: text += ' ' + words(input_text(param, explanations) for param in supplied) + '.'
        text += f' While IN remains TRUE, the timer accumulates elapsed time; when the preset is reached, {instance}.Q becomes TRUE.'
        return text
    if info['kind'].startswith('Project '):
        text = f'calls the project {info["kind"][8:].lower()} {name}' + (f' through instance {instance}' if instance != name else '') + '.'
    else:
        purpose = re.split(r'(?<=[.!?])\s+', info.get('purpose', ''), maxsplit=1)[0].rstrip('.')
        verb = re.match(r'^(?:The \w+\(\) function block is used to |This function block can be used to )(.+)', purpose, re.I)
        text = f'calls {instance}' + (f' ({name})' if instance != name else '') + '.'
        if purpose:
            if verb: text += ' Its documented purpose is to ' + verb[1] + '.'
            elif re.match(r'^(?:The |This )', purpose): text += ' ' + purpose + '.'
            else:
                subject = 'This operator' if info['kind'] in {'Type conversion', 'Language operator'} else 'This function'
                purpose = re.sub(r'^Return\b', 'Returns', purpose)
                purpose = re.sub(r'^Convert\b', 'Converts', purpose)
                text += ' ' + subject + ' ' + purpose[:1].lower() + purpose[1:] + '.'
    if inputs: text += ' For this call, ' + words(input_text(param, explanations) for param in inputs) + '.'
    return text


def action_words(item, explanations=()):
    text = item['text'].strip().rstrip('.')
    guarded = re.match(r'^When (.+): (.+)$', text)
    if guarded: return f'when {condition(guarded[1], explanations)}, it {action_words({**item, "text": guarded[2]}, explanations)}'
    assignment = re.fullmatch(r'Set (.+) to (.+)', text)
    if assignment:
        target, expression = assignment.groups()
        increment = re.fullmatch(re.escape(target) + r'\s*([+-])\s*1', expression)
        if increment: return f'{"increments" if increment[1] == "+" else "decrements"} {target} by one'
        conversion = re.fullmatch(r'(\w+)\s*\(\s*(\w+)\s*/\s*3600\s*\)', expression)
        if conversion and 'HOUR' in target.upper() and 'SEC' in conversion[2].upper():
            return f'divides {conversion[2]} by 3600 to obtain hours, applies the {conversion[1]} conversion and stores the result in {target}'
        outer_call = re.match(r'(\w+)\s*\(', expression)
        if outer_call:
            info = next((info for info in explanations if info['name'].casefold() == outer_call[1].casefold() and info['line'] == item['line']), None)
            if info:
                return call_words(info, explanations) + f' The returned result is stored in {target}'
        return f'sets {target} to {"zero" if expression == "0" else expression}'
    if text.startswith('Convert '):
        return 'converts ' + text[8:].replace('; store ', ' and stores ')
    if text.startswith('Continue to '): return 'continues to ' + text[12:]
    if text.startswith('Build '): return 'builds ' + text[6:]
    if text.startswith('Split '): return 'splits ' + text[6:]
    receives = re.fullmatch(r'(.+) receives (.+)', text)
    if receives: return f'supplies {receives[2]} to {receives[1]}'
    drive = re.fullmatch(r'Drive (.+) TRUE when (.+); FALSE otherwise', text)
    if drive: return f'sets {drive[1]} to TRUE when {condition(drive[2], explanations)} and to FALSE otherwise'
    coil = re.match(r'^(Set|Latch|Reset) (\S+) (TRUE|FALSE)(.*)$', text)
    if coil: return f'{ {"Set": "sets", "Latch": "latches", "Reset": "resets"}[coil[1]]} {coil[2]} to {coil[3]}{coil[4]}'
    for verb, conjugated in [('Evaluate', 'evaluates'), ('Latch', 'latches'), ('Reset', 'resets'),
                             ('Drive', 'drives'), ('Apply', 'applies'), ('Repeat', 'repeats'), ('Execute', 'executes')]:
        if text.startswith(verb + ' '): return conjugated + text[len(verb):]
    return text[:1].lower() + text[1:]


def outcome_words(outcome, explanations=()):
    guards = outcome.get('when', [])
    actions = [action_words(item, explanations) for item in outcome.get('actions', [])]
    when = words(condition(guard, explanations) for guard in guards)
    return (f'When {when}, the routine ' if when else 'The routine ') + (words(actions) if actions else 'makes no assignment in this branch') + '.'


def paragraph(step, position, count):
    if step.get('disabled'): return 'This rung is commented out and does not take part in the active routine.'
    explanations = step.get('explanations', [])
    primary = next((info for info in explanations if info['instance'] == step.get('call', {}).get('instance')), None)
    transition = 'First' if position == 0 else 'Finally' if position == count - 1 else 'Next'
    parts = []
    for outcome in step.get('inputConditions', []): parts.append(outcome_words(outcome, explanations))
    for item in step['actions']:
        is_call_fact = primary and item['line'] == primary['line'] and item['text'].startswith((primary['instance'] + ':', 'Call ', 'Evaluate '))
        clause = call_words(primary, explanations) if is_call_fact else action_words(item, explanations) + '.'
        parts.append('The routine ' + clause)
    if not parts and not step['outcomes']:
        parts.append('The routine checks whether ' + words(condition(guard, explanations) for guard in step['when']) + '.' if step['when'] else 'The routine evaluates this rung.')
    elif parts and step['when']:
        guard = words(condition(value, explanations) for value in step['when'])
        parts[0] = f'When {guard}, ' + parts[0][:1].lower() + parts[0][1:]
    for index, outcome in enumerate(step['outcomes']):
        if index and len(outcome.get('when', [])) == 1 and unwrapped(outcome['when'][0]).upper().startswith('NOT '):
            previous = step['outcomes'][index - 1].get('when', [])
            inner = unwrapped(unwrapped(outcome['when'][0])[4:])
            if len(previous) == 1 and inner == unwrapped(previous[0]):
                parts.append('Otherwise, the routine ' + words(action_words(item, explanations) for item in outcome['actions']) + '.')
                continue
        outcome_text = outcome_words(outcome, explanations)
        parts.append('Within this branch, ' + outcome_text[:1].lower() + outcome_text[1:] if primary and step['when'] else outcome_text)
    if primary:
        parts.extend(value for value in primary.get('behavior', []) if value.startswith('In this routine,'))
        if primary['name'].upper() == 'TON' and step['when']:
            parts.append('If the surrounding condition is false, this timer call is skipped and does not update its stored outputs in that invocation.')
    return transition + ', ' + ' '.join(parts)[:1].lower() + ' '.join(parts)[1:]


def reset_notes(steps):
    notes = []
    for index, step in enumerate(steps):
        if not any(re.search(r'\b\w*RESET\w*\b', guard, re.I) for guard in step['when']): continue
        resets = [match[1] for outcome in step['outcomes'] for item in outcome['actions']
                  if (match := re.fullmatch(r'Set (\w+) to 0\.', item['text']))]
        for counter in resets:
            for earlier in steps[:index]:
                if not any(re.search(r'\b' + re.escape(counter) + r'\b', guard) for guard in earlier['when']): continue
                outputs = {match[1] for outcome in earlier['outcomes'] for item in outcome['actions']
                           if (match := re.fullmatch(r'Set (\w+) to (?:0|1|TRUE|FALSE)\.', item['text']))}
                for output in sorted(outputs):
                    later_writes = [item for later in steps[index:] for item in later['actions'] + [item for outcome in later['outcomes'] for item in outcome['actions']]
                                    if re.match(r'Set ' + re.escape(output) + r'\b', item['text'])]
                    if not later_writes:
                        notes.append(f'The {output} check occurs before the reset clears {counter}. It uses the counter value at that earlier position; the reset does not rerun the check within the same invocation.')
    return notes


def add_flow_narrative(flow):
    for section in flow['sections']:
        collected = [(lane, step) for lane in section['sequences'] for step in lane['steps']]
        ordered = sorted(collected, key=lambda value: (value[1]['line'], value[1]['id']))
        name = section['name'].split(':', 1)[0].strip()
        interface = [item for item in flow.get('routineInterface', []) if item.get('scope', name).casefold() == name.casefold()]
        inputs = [item['name'] for item in interface if item['direction'] in {'INPUT', 'IN_OUT'}]
        outputs = [item['name'] for item in interface if item['direction'] in {'OUTPUT', 'IN_OUT'}]
        intro = f'{name} reads {words(inputs)}' if inputs else f'{name} evaluates the conditions and actions below'
        if outputs: intro += f' and updates {words(outputs)}'
        intro += '. The explanation follows the order in which the routine checks its source instructions.'
        paragraphs = [{'stepId': step['id'], 'sequenceId': lane['id'], 'number': step['number'], 'sequenceTitle': lane['title'],
                       'title': step['title'], 'text': paragraph(step, index, len(ordered)), 'sourceFile': flow['sourceFile'],
                       'line': step['line'], 'endLine': step['endLine']} for index, (lane, step) in enumerate(ordered)]
        note = ('This initialization section runs when the program is initialized.' if name.upper() == '_INIT' else
                'The cyclic section checks these conditions again on subsequent task cycles.' if name.upper() == '_CYCLIC' else
                'These conditions are evaluated again whenever this routine is called.')
        section['workingExplanation'] = {'intro': intro, 'paragraphs': paragraphs, 'notes': [note, *reset_notes([step for _, step in ordered])]}
        for lane in section['sequences']:
            lane['workingExplanation'] = {'intro': intro, 'paragraphs': [item for item in paragraphs if item['sequenceId'] == lane['id']], 'notes': [note]}
    return flow
