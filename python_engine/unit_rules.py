"""Configurable unit labels for generated metadata; no value conversion."""
import hashlib
import json
from pathlib import Path
import re

DEFAULT_RULES = {'version': '1.0', 'enabled': True, 'mappings': [
    {'id': 'minutes', 'keyword': 'minutes', 'unit': 'Mins', 'match': 'word', 'machine_department': 'All', 'enabled': True},
    {'id': 'minute', 'keyword': 'minute', 'unit': 'Mins', 'match': 'word', 'machine_department': 'All', 'enabled': True},
    {'id': 'seconds', 'keyword': 'seconds', 'unit': 'Sec', 'match': 'word', 'machine_department': 'All', 'enabled': True},
    {'id': 'second', 'keyword': 'second', 'unit': 'Sec', 'match': 'word', 'machine_department': 'All', 'enabled': True},
]}


def validate_unit_rules(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('enabled'), bool):
        raise ValueError('Unit rules need an enabled flag.')
    rows = payload.get('mappings')
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError('Configure at most 200 unit rules.')
    clean, seen = [], set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'Unit rule {index} must be an object.')
        fields = {}
        for key, limit in [('id', 80), ('keyword', 100), ('unit', 32), ('machine_department', 64)]:
            value = row.get(key, 'All' if key == 'machine_department' else '')
            if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
                raise ValueError(f'Unit rule {index}: {key} is required (maximum {limit} characters).')
            fields[key] = value.strip()
        if fields['id'] in seen:
            raise ValueError('Unit rule IDs must be unique.')
        if fields['unit'].startswith('='):
            raise ValueError('Unit labels must be text, not spreadsheet formulas.')
        seen.add(fields['id'])
        if row.get('match') not in {'word', 'contains', 'exact'} or not isinstance(row.get('enabled'), bool):
            raise ValueError(f'Unit rule {index}: choose a match mode and enabled flag.')
        clean.append({**fields, 'match': row['match'], 'enabled': row['enabled']})
    return {'version': '1.0', 'enabled': payload['enabled'], 'mappings': clean}


def load_unit_rules(path: Path):
    raw = path.read_bytes() if path.is_file() else json.dumps(DEFAULT_RULES, sort_keys=True).encode('utf-8')
    return validate_unit_rules(json.loads(raw.decode('utf-8-sig'))), hashlib.sha256(raw).hexdigest()


def _words(value):
    value = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(value))
    return re.sub(r'[^\w%]+|_', ' ', value.casefold()).strip()


def resolve_unit(config, parameter, department='All', existing=None):
    explicit = str(existing or '').strip()
    if explicit.casefold() not in {'', '<null>', 'null', 'none', 'nan'}:
        return {'unit': explicit, 'source': 'Explicit parameter mapping', 'ruleId': None}
    if config['enabled']:
        name, machine = _words(parameter), str(department or 'All').strip().casefold()
        rows = [row for row in config['mappings'] if row['enabled'] and
                row['machine_department'].casefold() in {'all', machine}]
        # Department-specific rules take priority; table order resolves other matches.
        rows.sort(key=lambda row: row['machine_department'].casefold() == 'all')
        for row in rows:
            keyword = _words(row['keyword'])
            matches = (name == keyword if row['match'] == 'exact' else keyword in name
                       if row['match'] == 'contains' else
                       bool(re.search(r'(?<!\w)' + re.escape(keyword) + r'(?!\w)', name)))
            if keyword and matches:
                return {'unit': row['unit'], 'source': 'Unit rule: ' + row['keyword'], 'ruleId': row['id']}
    return {'unit': '<null>', 'source': 'No unit configured', 'ruleId': None}
