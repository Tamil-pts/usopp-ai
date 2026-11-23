"""Chopper Command Layer — MatchView (project comparison) action.

Slots required:
  base_path  — local FS path to the BASE (reference) project
  new_path   — local FS path to the DEVELOPED project
Slots optional:
  base_hmi   — HMI sub-folder path for base project (usually left empty)
  new_hmi    — HMI sub-folder path for developed project (usually left empty)

The user is shown which project is base and which is developed on the plan
card, with a 'Swap' option before confirming, because reversing the direction
changes what shows as 'added' vs 'removed'.

This module registers itself in the action registry when imported.
"""
from __future__ import annotations

import re
import time

from backend.core.chopper_actions.registry import (
    ActionEntry, SlotDef, SlotKind, register,
)

_PATTERNS = [
    re.compile(
        r'\b(?:run|start|do|execute|launch|compare|diff)\b.{0,60}'
        r'\b(?:matchview|match.?view|comparison|compare)\b',
        re.I,
    ),
    re.compile(
        r'\bcompare\b.{0,80}\b(?:project|plc|version|base|developed|new|both|two|folder|files?)\b',
        re.I,
    ),
    re.compile(
        r'\b(?:project[s]?|folders?|files?)\b.{0,80}\b(?:compare|comparison|diff|summary)\b',
        re.I,
    ),
    re.compile(
        r'\bcompare\b.{0,60}\b(?:both|two|them|projects?|results?|folders?)\b',
        re.I,
    ),
    re.compile(
        r'\b(?:matchview|match.?view)\b',
        re.I,
    ),
    re.compile(
        r'\b(?:diff|differences?)\b.{0,40}\b(?:between|of|projects?|folders?)\b',
        re.I,
    ),
    re.compile(
        r'\bcompare\b',
        re.I,
    ),
]

_SLOTS = [
    SlotDef(
        key='base_path',
        kind=SlotKind.PROJECT,
        label='Base (reference) project',
        prompt='Which project is the BASE (reference / original)? '
               'Paste the full folder path or click Attach Project.',
    ),
    SlotDef(
        key='new_path',
        kind=SlotKind.PROJECT,
        label='Developed project',
        prompt='Which project is the DEVELOPED version? '
               'Paste the full folder path or click Attach Project.',
    ),
    SlotDef(
        key='base_hmi',
        kind=SlotKind.TEXT,
        label='Base HMI folder (optional)',
        prompt='Is there a separate HMI folder for the base project? '
               'Paste the path or type "skip".',
        optional=True,
    ),
    SlotDef(
        key='new_hmi',
        kind=SlotKind.TEXT,
        label='Developed HMI folder (optional)',
        prompt='Is there a separate HMI folder for the developed project? '
               'Paste the path or type "skip".',
        optional=True,
    ),
]


# ---------------------------------------------------------------------------
# Run — starts the compare worker thread, polls until done
# ---------------------------------------------------------------------------

_POLL_INTERVAL = 2.0    # seconds between status polls
_POLL_TIMEOUT  = 1800.0  # 30 minutes max


def _run(slots: dict, user: dict) -> dict:
    from backend.core.chopper_actions.plan_security import validate_project_path
    from backend.core.runtime import COMPARE_JOBS, COMPARE_JOBS_LOCK, WORK
    from backend.api.comparison import _compare_session, _compare_worker
    import threading
    from contextvars import copy_context

    base_root = validate_project_path(slots['base_path'])
    new_root  = validate_project_path(slots['new_path'])

    base_hmi = str(slots.get('base_hmi') or '').strip()
    new_hmi  = str(slots.get('new_hmi')  or '').strip()
    if base_hmi.lower() in {'skip', 'none', ''}:
        base_hmi = ''
    if new_hmi.lower() in {'skip', 'none', ''}:
        new_hmi = ''

    sid, work = _compare_session()
    with COMPARE_JOBS_LOCK:
        COMPARE_JOBS[sid] = {
            'status': 'starting', 'phase': 'starting',
            'percent': 0, 'current': 0, 'total': 0,
            'baseFile': '', 'newFile': '', 'logs': [],
        }

    threading.Thread(
        target=copy_context().run,
        args=(_compare_worker, sid, work, base_root, new_root,
              base_root.name, new_root.name, base_hmi, new_hmi),
        daemon=True,
    ).start()

    # Poll until complete or timeout
    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL)
        with COMPARE_JOBS_LOCK:
            job = COMPARE_JOBS.get(sid, {})
        status = job.get('status')
        if status == 'complete':
            return job['result']
        if status == 'error':
            from fastapi import HTTPException
            raise HTTPException(500, job.get('error', 'Comparison failed.'))

    from fastapi import HTTPException
    raise HTTPException(504, 'Comparison timed out. The projects may be very large.')


# ---------------------------------------------------------------------------
# Summarize — computed from result dict, never from the model
# ---------------------------------------------------------------------------

_TOP_N_CHANGED = 10


def _summarize(result: dict) -> dict:
    summary = result.get('summary') or {}
    added    = int(summary.get('added', 0))
    removed  = int(summary.get('removed', 0))
    modified = int(summary.get('modified', 0))
    unchanged = int(summary.get('unchanged', 0))

    # Per-category breakdown from diffs list
    by_category: dict[str, int] = {}
    top_changed: list[dict] = []

    for entry in (result.get('diffs') or []):
        cat = str(entry.get('category') or 'other')
        status = str(entry.get('status') or '')
        if status in {'added', 'removed', 'modified'}:
            by_category[cat] = by_category.get(cat, 0) + 1
            if len(top_changed) < _TOP_N_CHANGED:
                top_changed.append({
                    'path':     entry.get('path', ''),
                    'category': cat,
                    'status':   status,
                })

    sid = result.get('sessionId', '')

    return {
        'type':       'action-summary',
        'actionId':   'matchview',
        'baseName':   result.get('baseName', ''),
        'newName':    result.get('newName', ''),
        'summary':    {'added': added, 'removed': removed, 'modified': modified, 'unchanged': unchanged},
        'byCategory': by_category,
        'topChanged': top_changed,
        'sessionId':  sid,
        'deepLink':   {'page': 'compare', 'sessionId': sid},
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register(ActionEntry(
    id='matchview',
    title='MatchView Comparison',
    window='matchview',
    patterns=_PATTERNS,
    slots=_SLOTS,
    permissions=['matchview'],
    run=_run,
    summarize=_summarize,
    description='Compare a base and a developed Automation Studio project side by side.',
))
