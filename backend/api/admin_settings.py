"""Administrator-managed shared machine/department configuration."""
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from backend.core.runtime import KNOWLEDGE

router = APIRouter(prefix='/api/admin/settings', tags=['Admin settings'])
CONFIG = KNOWLEDGE / 'master' / 'machine_departments.json'
DEFAULT = {
    'version': '1.0',
    'departments': ['All', 'Blow Room', 'Carding', 'Breaker', 'Finisher', 'Comber', 'Lapformer', 'Speedframe', 'Ringframe', 'RAP', 'Auto Winder'],
    'prefixes': [
        {'prefix': 'LDF', 'department': 'Finisher'}, {'prefix': 'LDB', 'department': 'Breaker'},
        {'prefix': 'LH', 'department': 'Lapformer'}, {'prefix': 'LF', 'department': 'Speedframe'},
        {'prefix': 'LC', 'department': 'Carding'}, {'prefix': 'BL', 'department': 'Blow Room'},
        {'prefix': 'LR', 'department': 'Ringframe'},
    ],
}


def read_config():
    try:
        value = json.loads(CONFIG.read_text(encoding='utf-8'))
        if isinstance(value, dict) and isinstance(value.get('departments'), list) and isinstance(value.get('prefixes'), list):
            return value
    except (OSError, ValueError):
        pass
    return DEFAULT


def require_admin(request: Request):
    if getattr(request.state, 'user', {}).get('role') != 'admin':
        raise HTTPException(403, 'Only an administrator can change shared machine / department settings.')


@router.get('/workhub-health')
def workhub_health(request:Request):
    require_admin(request)
    from backend.core.workhub_intelligence.reliability import health
    return health()


@router.get('/machine-departments')
def get_machine_departments():
    return read_config()


@router.put('/machine-departments')
def save_machine_departments(request: Request, payload: dict):
    require_admin(request)
    departments = payload.get('departments')
    prefixes = payload.get('prefixes')
    if not isinstance(departments, list) or not isinstance(prefixes, list):
        raise HTTPException(400, 'Supply department names and .apj prefixes.')
    clean_departments = []
    for item in departments:
        name = str(item or '').strip()
        if not name or len(name) > 80:
            raise HTTPException(400, 'Department names must contain 1 to 80 characters.')
        if name.casefold() not in {value.casefold() for value in clean_departments}:
            clean_departments.append(name)
    if not clean_departments or clean_departments[0].casefold() != 'all':
        raise HTTPException(400, 'The first department must be All.')
    clean_prefixes = []
    seen = set()
    for row in prefixes:
        if not isinstance(row, dict):
            raise HTTPException(400, 'Each prefix mapping needs a prefix and department.')
        prefix = str(row.get('prefix') or '').strip().upper()
        department = str(row.get('department') or '').strip()
        if not re.fullmatch(r'[A-Z0-9_-]{1,16}', prefix):
            raise HTTPException(400, 'Prefixes can contain 1 to 16 letters, numbers, underscores or hyphens.')
        if department.casefold() not in {value.casefold() for value in clean_departments if value.casefold() != 'all'}:
            raise HTTPException(400, f'Choose a configured department for prefix {prefix}.')
        if prefix in seen:
            raise HTTPException(400, f'Prefix {prefix} occurs more than once.')
        seen.add(prefix)
        clean_prefixes.append({'prefix': prefix, 'department': department})
    clean_prefixes.sort(key=lambda item: (-len(item['prefix']), item['prefix']))
    result = {'version': '1.0', 'departments': clean_departments, 'prefixes': clean_prefixes}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result
