"""Apply report choices before loading expensive HMI/ladder details."""
from pathlib import PurePosixPath

DEFAULT_SELECTION = {'categories': ['logic', 'screen', 'config', 'hardware'],
                     'statuses': ['modified', 'added', 'removed'], 'includeKnowledge': True}


def select_report(result, selection=None):
    selection = {**DEFAULT_SELECTION, **(selection or {})}
    categories, statuses = set(selection['categories']), set(selection['statuses'])
    entries = list(result.get('diffs') or [])
    if 'unchanged' in statuses:
        for key in ('same_logic_files', 'same_screen_files', 'same_project_files'):
            entries.extend(result.get(key) or [])
    seen, selected = set(), []
    for original in entries:
        path = str(original.get('path') or '').replace('\\', '/')
        if PurePosixPath(path).suffix.casefold() in {'.pkg', '.prg'} or path in seen:
            continue
        seen.add(path)
        if original.get('category') not in categories or original.get('status') not in statuses:
            continue
        selected.append({**original, 'report_include_same': original.get('status') == 'unchanged'})
    summary = {key: sum(entry.get('status') == key for entry in selected)
               for key in ('modified', 'added', 'removed', 'unchanged')}
    return {**result, 'comparisonSummary': result.get('comparisonSummary', result.get('summary', {})),
            'summary': summary, 'reportSelection': selection, 'diffs': selected,
            'same_logic_files': [], 'same_screen_files': [], 'same_project_files': []}
