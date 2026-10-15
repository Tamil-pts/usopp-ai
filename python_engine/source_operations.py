"""Compact, project-derived operations for engineering overviews.

Names identify source objects; they never select a predefined machine function.
Text guards come from the IEC parser. Complex ladder paths remain separate.
"""
from pathlib import Path
import re

from python_engine.function_flow import _text_flow, _names
from python_engine.project_analysis import _mask
from python_engine.working_sequence import ASSIGNMENT, records


def collect_operations(file, text, category, ownership, networks=()):
    if category not in {'Logic', 'Ladder'} or ownership == 'disabled task':
        return []
    base = {'file': file, 'category': category, 'ownership': ownership}
    result = []
    suffix = Path(file).suffix.casefold()
    if networks:
        offsets = [match.start() for match in re.finditer(r'<network\s', text)]
        for network in networks:
            if network.get('commented'):
                continue
            cells = network['diagram']['cells']
            contacts = [cell for cell in cells if cell['kind'] == 'contact']
            coils = [cell for cell in cells if cell['kind'] == 'coil']
            simple = (network['diagram']['rows'] == 1 and len(coils) == 1 and
                      all(cell['kind'] in {'line', 'contact', 'coil'} and not cell['or'] for cell in cells) and
                      all(cell['type'] in {'open', 'closed'} for cell in contacts))
            guards = [' AND '.join(f"{cell['name']} is {'TRUE' if cell['type'] == 'open' else 'FALSE'}"
                                   for cell in contacts)] if simple and contacts else []
            line = text.count('\n', 0, offsets[network['index'] - 1]) + 1
            for cell in coils:
                result.append({**base, 'kind': 'coil', 'name': cell['name'], 'coilType': cell['type'],
                               'reads': list(dict.fromkeys(c['name'] for c in contacts)), 'writes': [cell['name']],
                               'guards': guards, 'guardLines': [], 'section': '_CYCLIC',
                               'eventLine': line, 'network': network['index'], 'complexTopology': not simple})
        return result
    if suffix not in {'.st', '.ab', '.src'}:
        # C needs its own control-flow parser. Literal C calls remain available in
        # analysisRecords; do not run IEC syntax rules over C branches.
        return []
    basic = suffix == '.ab' or bool(re.search(r'\b(?:ENDIF|ENDLOOP|FUB)\b', _mask(text), re.I))
    parts, _, _, notices = _text_flow(text, file, basic)
    # An incomplete parse cannot establish nested branch relationships.
    trusted_guards = not notices
    for part in parts:
        for record in records(part['nodes']):
            row = record['row']
            assignment = ASSIGNMENT.match(row['code'])
            if not assignment:
                continue
            target, expression = assignment.groups()
            calls = set(re.findall(r'\b([A-Za-z_]\w*)\s*\(', expression))
            result.append({**base, 'kind': 'assignment', 'name': target, 'value': expression,
                           'reads': [name for name in _names(expression) if name not in calls], 'writes': [target], 'section': part['name'],
                           'guards': record['guards'] if trusted_guards else [],
                           'guardLines': record['guardLines'] if trusted_guards else [],
                           'guardCoverage': 'parsed' if trusted_guards else 'unresolved',
                           'eventLine': row['line'], 'endLine': row['endLine']})
    return result
