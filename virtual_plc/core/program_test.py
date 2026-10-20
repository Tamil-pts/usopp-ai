"""An explicit, separate program test, with dependencies still checked normally."""
from copy import deepcopy
import math


def program_model(model, identity, parent_id, interval_ms=None):
    program = next((p for p in model.get('programs', []) if p['id'] == identity), None)
    if not program or program.get('kind') != 'program' or program.get('entry') != 'cyclic':
        raise ValueError('Select a cyclic PLC program from this project.')
    assigned = next((t for t in model.get('tasks', []) if identity in t.get('programs', [])), None)
    interval = interval_ms if interval_ms is not None else (assigned or {}).get('intervalMs')
    if type(interval) not in {int, float} or not math.isfinite(interval) or not .1 <= interval <= 60000:
        raise ValueError('Specify a program-test interval between 0.1 and 60000 ms.')
    selected = deepcopy(model)
    selected['tasks'] = [{'id': 'program-test', 'name': 'Program test', 'kind': 'cyclic', 'intervalMs': interval,
                          'priority': 1, 'enabled': True, 'programs': [identity], 'source': program['source']}]
    # The selected program's lifecycle sections are picked by its normal scope
    # in VirtualRuntime. No full-project lifecycle task is retained here.
    selected['initializationPrograms'] = []
    selected['exitPrograms'] = []
    task_findings = {'program-unresolved', 'task-interval-unresolved', 'tasks-unresolved'}
    excluded = [d for d in selected.get('diagnostics', []) if d.get('code') in task_findings]
    selected['diagnostics'] = [d for d in selected.get('diagnostics', []) if d.get('code') not in task_findings]
    selected.pop('compatibility', None)
    selected['executionScope'] = {'mode': 'program-test', 'parentProjectId': parent_id, 'programId': identity,
                                  'intervalMs': interval, 'excludedTaskCount': len(model.get('tasks', [])),
                                  'excludedTaskFindings': excluded, 'completeMachineExecution': False,
                                  'notice': 'Only the selected program, its lifecycle and called dependencies execute. Other machine tasks are excluded from this separate test.'}
    selected['name'] = model.get('name', 'PLC') + ' - program test: ' + program.get('name', identity)
    return selected
