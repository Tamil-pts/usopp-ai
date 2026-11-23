"""Chopper Command Layer — append-only audit log.

One JSON-lines file per day at BASE/logs/chopper_actions_YYYYMMDD.log.
Each record is a single JSON object.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime

from backend.core.runtime import BASE, log

_AUDIT_DIR = BASE / 'logs'
_AUDIT_LOCK = threading.Lock()


def write_audit(
    *,
    user_id: str,
    action_id: str,
    input_summary: dict,
    result_id: str,
    status: str = 'ok',
    error: str = '',
) -> None:
    """Append one audit record (JSON line) to today's chopper_actions log.

    *input_summary* must NOT contain raw project text or file contents.
    It should contain only paths, counts and identifiers.
    """
    record = {
        'ts': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'user': str(user_id),
        'action': str(action_id),
        'input': input_summary,
        'result_id': str(result_id),
        'status': str(status),
    }
    if error:
        record['error'] = str(error)
    line = json.dumps(record, ensure_ascii=False, separators=(',', ':'))
    today = datetime.utcnow().strftime('%Y%m%d')
    path = _AUDIT_DIR / f'chopper_actions_{today}.log'
    try:
        with _AUDIT_LOCK:
            _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as f:
                f.write(line + '\n')
    except OSError as exc:
        log.error('CHOPPER_ACTIONS_AUDIT_WRITE_ERROR %s', exc)
