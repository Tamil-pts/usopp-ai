"""Optional report filtering; original comparison and screen geometry stay intact."""
from copy import deepcopy

SKIPPED_PROPERTIES = {'width', 'top', 'left', 'alignmentvertical', 'alignmenthorizontal'}


def filter_screen_properties(result):
    output = {**result, 'diffs': []}
    for original in result.get('diffs', []):
        if original.get('category') != 'screen' or not original.get('parsed_screen'):
            output['diffs'].append(original)
            continue
        entry = deepcopy(original)
        parsed = entry['parsed_screen']
        def properties(values):
            return {key:value for key,value in (values or {}).items() if key.casefold() not in SKIPPED_PROPERTIES}
        def changes(values):
            return [change for change in values or [] if str(change.get('prop', '')).casefold() not in SKIPPED_PROPERTIES]
        for control in parsed.get('controls', []):
            before = control.get('changes', [])
            control['changes'] = changes(before)
            if control.get('status') == 'modified' and before and not control['changes']:
                control['status'] = 'unchanged'
            for side in ('base', 'new'):
                if control.get(side): control[side]['properties'] = properties(control[side].get('properties'))
        parsed['changes'] = [{**change, 'changes': changes(change['changes'])} if 'changes' in change else change
                             for change in parsed.get('changes', [])]
        parsed['changes'] = [change for change in parsed['changes'] if
                             not (change.get('type') == 'control_modified' and not change.get('changes'))]
        for field in ('base_page_properties', 'new_page_properties'):
            parsed[field] = properties(parsed.get(field))
        statuses = {control['name']:control['status'] for control in parsed.get('controls', [])}
        for layout in (parsed.get('layouts') or {}).values():
            for layer in (layout or {}).get('layers', []):
                for control in layer.get('controls', []):
                    control['status'] = statuses.get(control.get('id'), statuses.get(control.get('name'),control.get('status')))
        output['diffs'].append(entry)
    output['skippedHmiProperties'] = sorted(SKIPPED_PROPERTIES)
    return output
