"""Resolve explicit B&R task-qualified global I/O aliases to declarations."""
import re


def connect_io(hardware, variables, tasks):
    globals_by_name = {v['name']: v for v in variables if v.get('scope') == '@global'}
    identities = {v['id']: v for v in variables}
    task_names = {str(t.get('name')) for t in tasks}
    for channel in hardware.get('channels', []):
        original = channel.get('variable', '')
        address = original
        alias = re.match(r'^(Cyclic#\d+)\.(?:::)?(.+)$', original)
        if alias and alias[1] in task_names:
            address = alias[2]
        root = re.split(r'[.\[]', address, 1)[0]
        record = identities.get(address) or identities.get(root) or globals_by_name.get(root)
        if record:
            suffix = address[len(root):] if root in (record['name'], record['id']) else ''
            channel.update(variableId=record['id']+suffix, type=record['type'], quality='not-running')
            if original != address:
                channel['bindingEvidence'] = {'original': original, 'declaration': record.get('source'),
                                              'line': record.get('line'), 'rule': 'Task-qualified global I/O alias'}
        else:
            channel.pop('variableId', None)
            channel['quality'] = 'unresolved-variable'
    hardware['bindingAdapterVersion'] = 1
    return hardware
