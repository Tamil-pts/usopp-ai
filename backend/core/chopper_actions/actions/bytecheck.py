"""Chopper Command Layer — ByteCheck (ByteMap validation) action.

Slots required:
  project_path      — local FS path to an Automation Studio project
  machine_department — chosen by the user from the ByteMap department list
Slots optional:
  metadata_path     — local FS path to a metadata .xlsx workbook

This module registers itself in the action registry when imported.
"""
from __future__ import annotations

import re

from backend.core.chopper_actions.registry import (
    ActionEntry, SlotDef, SlotKind, register,
)


# ---------------------------------------------------------------------------
# Command patterns — must NOT match question phrases.
# A phrase matches only if it contains a command verb (run/validate/check/…)
# AND a target noun (project/plc/validation/bytemap/bytecheck).
# ---------------------------------------------------------------------------

_PATTERNS = [
    re.compile(
        r'\b(?:run|start|do|execute|launch|perform)\b.{0,60}'
        r'\b(?:bytecheck|bytemap|byte.?map|byte.?check|validation|validate)\b',
        re.I,
    ),
    re.compile(
        r'\b(?:validate|check|verify)\b.{0,60}'
        r'\b(?:project|plc|this|the|folder|files?)\b',
        re.I,
    ),
    re.compile(
        r'\b(?:bytecheck|byte.?check)\b',
        re.I,
    ),
    re.compile(
        r'\b(?:bytemap|byte.?map)\b',
        re.I,
    ),
    re.compile(
        r'\brun\s+(?:a\s+)?(?:validation|validate)\b',
        re.I,
    ),
    re.compile(
        r'\bvalidate\b',
        re.I,
    ),
]

_SLOTS = [
    SlotDef(
        key='project_path',
        kind=SlotKind.PROJECT,
        label='Project folder',
        prompt='Which Automation Studio project do you want to validate? '
               'Paste the full path or click Attach Project.',
    ),
    SlotDef(
        key='machine_department',
        kind=SlotKind.CHOICE,
        label='Machine / department',
        prompt='Which machine department should I use for the validation rule set?',
        choices=[],   # filled dynamically from admin config at plan-build time
    ),
    SlotDef(
        key='metadata_path',
        kind=SlotKind.METADATA,
        label='Metadata workbook (optional)',
        prompt='Do you want to include a metadata workbook? '
               'Paste the full path or skip.',
        optional=True,
    ),
]


# ---------------------------------------------------------------------------
# Run — calls the existing _execute_project, never duplicates engine logic
# ---------------------------------------------------------------------------

def _run(slots: dict, user: dict) -> dict:
    """Execute a ByteMap validation and return the raw engine result dict.

    Path slots are re-validated here (server-side, not trusting the client).
    """
    from backend.core.chopper_actions.plan_security import (
        validate_project_path, validate_metadata_path,
    )
    from backend.core.runtime import _local_session
    from backend.api.validation import _execute

    root = validate_project_path(slots['project_path'])
    meta = validate_metadata_path(slots.get('metadata_path') or '')
    department = str(slots.get('machine_department') or '').strip()
    if not department or department.casefold() == 'all':
        from fastapi import HTTPException
        raise HTTPException(400, 'Select a specific machine department before running validation.')

    sid, _ = _local_session()
    result = _execute(
        sid=sid,
        root=root,
        project_name=root.name,
        metadata_path=meta,
        generate=False,
        local=True,
        machine_department=department,
        bool_metadata_mode='BOOL',
    )
    return result


# ---------------------------------------------------------------------------
# Summarize — computed from the result dict, never from the model
# ---------------------------------------------------------------------------

def _summarize(result: dict) -> dict:
    """Build a compact chat-card dict from the validation result.

    All values come from the result dict.  No model inference is used.
    """
    counts = result.get('counts') or {}
    fail    = int(counts.get('fail', 0))
    warning = int(counts.get('warning', 0))
    passed  = int(counts.get('pass', 0))
    error   = int(counts.get('error', 0))
    groups  = int(counts.get('groups', 0))

    # Collect top fails and warnings with file:line references
    top_fails:    list[dict] = []
    top_warnings: list[dict] = []

    for group in (result.get('results') or []):
        for issue in (group.get('issues') or []):
            sev = str(issue.get('severity') or '').upper()
            entry = {
                'severity':  sev,
                'parameter': issue.get('parameter', ''),
                'message':   issue.get('message', ''),
                'location':  (
                    f"{issue['file']}:{issue['line']}"
                    if issue.get('file') and issue.get('line')
                    else issue.get('file') or ''
                ),
                'groupCode': group.get('group_code', ''),
            }
            if sev == 'FAIL' and len(top_fails) < 5:
                top_fails.append(entry)
            elif sev in {'WARNING', 'WARN'} and len(top_warnings) < 3:
                top_warnings.append(entry)

    sid = result.get('sessionId', '')
    project_name = result.get('projectName', '')
    department   = result.get('machineDepartment', '')

    return {
        'type':        'action-summary',
        'actionId':    'bytecheck',
        'projectName': project_name,
        'department':  department,
        'counts':      {'fail': fail, 'warning': warning, 'pass': passed, 'error': error, 'groups': groups},
        'topFails':    top_fails,
        'topWarnings': top_warnings,
        'sessionId':   sid,
        'deepLink':    {'page': 'validation', 'sessionId': sid},
        'score':       result.get('score'),
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register(ActionEntry(
    id='bytecheck',
    title='ByteMap Validation',
    window='bytemap',
    patterns=_PATTERNS,
    slots=_SLOTS,
    permissions=['bytemap'],
    run=_run,
    summarize=_summarize,
    description='Validate an Automation Studio project against the configured rule set.',
))
