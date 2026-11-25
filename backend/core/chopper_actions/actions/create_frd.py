"""Chopper Command Layer — Create Functional Requirements Document (FRD).

Dedicated action to draft a complete FRD with numbered requirements,
functional description, scope, acceptance criteria, and review flowchart.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from backend.core.chopper_actions.registry import (
    ActionEntry, SlotDef, SlotKind, register,
)

_PATTERNS = [
    re.compile(
        r'\b(?:create|draft|new|make|start|prepare|write|build)\b.{0,40}\b(?:frd|functional\s*requirements?|requirements?\s*(?:doc|document|specification|sheet))\b',
        re.I,
    ),
    re.compile(
        r'\b(?:create|draft|new|start)\s+(?:an?\s+)?(?:frd|functional\s*requirements?)\b',
        re.I,
    ),
    re.compile(
        r'\b(?:frd|functional\s*requirements?\s*document)\b',
        re.I,
    ),
]

_SLOTS = [
    SlotDef(
        key='title',
        kind=SlotKind.TEXT,
        label='FRD Document title',
        prompt='What is the title or subject of this Functional Requirements Document (FRD)?',
        optional=False,
    ),
    SlotDef(
        key='requirements',
        kind=SlotKind.TEXT,
        label='Functional requirements / PLC logic',
        prompt='Describe the functional requirements and machine behavior in detail (e.g. sequence, interlocks, alarms, cycle timing):',
        optional=False,
    ),
    SlotDef(
        key='scope',
        kind=SlotKind.TEXT,
        label='Scope of work (included / excluded)',
        prompt='What is the scope of work (what is included vs excluded)? You can type "standard" or specific boundaries:',
        optional=True,
    ),
    SlotDef(
        key='acceptance_criteria',
        kind=SlotKind.TEXT,
        label='Acceptance & verification criteria',
        prompt='What are the acceptance criteria and verification methods? (or type "standard verification"):',
        optional=True,
    ),
    SlotDef(
        key='machine_department',
        kind=SlotKind.CHOICE,
        label='Machine department / type',
        prompt='Which machine type or department does this apply to?',
        choices=['Spinning', 'Blow Room', 'Carding', 'Breaker', 'Finisher', 'Comber', 'Lapformer', 'Speedframe', 'Ringframe', 'General'],
        optional=True,
    ),
    SlotDef(
        key='customer',
        kind=SlotKind.TEXT,
        label='Customer / Client',
        prompt='Which customer or client is this document for? (or leave blank for Internal):',
        optional=True,
    ),
]


def _run(slots: dict, user: dict) -> dict:  # noqa: C901
    """Create FRD document in WorkHub with structured requirements."""
    from backend.core.workhub import store as hub
    from backend.core.workhub_document_spaces import create as create_space
    from backend.core.workhub_quality import authoring, documents

    if not isinstance(user, dict) or not isinstance(user.get('id'), int) or user.get('id') <= 0:
        try:
            from backend.core import accounts
            enabled_admin = next((u for u in accounts.store.list_users() if u.get('role') == 'admin' and u.get('active')), None)
            if enabled_admin and isinstance(enabled_admin.get('id'), int):
                user = enabled_admin
            else:
                user = {'id': 1, 'username': 'Admin', 'role': 'admin'}
        except Exception:
            user = {'id': 1, 'username': 'Admin', 'role': 'admin'}

    title = str(slots.get('title') or 'Functional Requirements Document').strip()
    req_text = str(slots.get('requirements') or '').strip()
    scope = str(slots.get('scope') or '').strip()
    acceptance = str(slots.get('acceptance_criteria') or '').strip()
    dept = str(slots.get('machine_department') or 'General').strip()
    customer = str(slots.get('customer') or 'Internal').strip()

    req_items = []
    if req_text:
        lines = [l.strip() for l in re.split(r'[\r\n]+|[;.]\s+', req_text) if len(l.strip()) > 8]
        if len(lines) > 1:
            for idx, line in enumerate(lines[:10]):
                req_items.append({
                    'id': f'FR-{str(idx+1).zfill(3)}',
                    'title': line[:180],
                    'description': line,
                    'acceptance_criteria': acceptance or 'Verified through simulation and functional test.',
                    'trigger': 'Cyclic execution / condition trigger',
                    'expected_behavior': line,
                    'subsystem': dept,
                    'category': f'{dept} Logic',
                    'source_label': 'Author Requirement',
                    'priority': 'high' if idx == 0 else 'medium',
                    'source_ids': [],
                    'mandatory': True,
                    'change': 'new',
                })
        else:
            req_items.append({
                'id': 'FR-001',
                'title': title[:180],
                'description': req_text,
                'acceptance_criteria': acceptance or 'Verified through simulation and functional test.',
                'trigger': 'System power on and cyclic execution',
                'expected_behavior': req_text,
                'subsystem': dept,
                'category': f'{dept} Logic',
                'source_label': 'Author Requirement',
                'priority': 'high',
                'source_ids': [],
                'mandatory': True,
                'change': 'new',
            })
    else:
        req_items.append({
            'id': 'FR-001',
            'title': title[:180],
            'description': f'Functional logic and sequence requirements for {title}.',
            'acceptance_criteria': acceptance or 'Engineering validation per standards.',
            'trigger': 'Cyclic execution',
            'expected_behavior': f'Execution of {title} according to specifications.',
            'subsystem': dept,
            'category': 'PLC Logic',
            'source_label': 'Initial Requirement Draft',
            'priority': 'high',
            'source_ids': [],
            'mandatory': True,
            'change': 'new',
        })

    payload = {
        'title': f'{title} — FRD',
        'stage': 'frd',
        'document_type': 'frd',
    }

    scope_id = ''
    doc_number = 'FRD-DRAFT'
    try:
        created = create_space(user, payload)
        scope_id = created.get('scope_id', '')
        control_id = created.get('control_id', '')
        doc_id = created.get('document_id', '')

        with hub.db(True) as db:
            content = authoring.blank('frd')
            content.update({
                'purpose': f'Functional Requirements Specification for {title}. Customer: {customer}. Department: {dept}.',
                'scope': scope or f'Complete functional logic, interlocks and HMI interface for {title}.',
                'acceptance_summary': acceptance or 'All requirements verified against engineering safety and functional criteria.',
                'requirements': req_items,
                'summary': f'FRD generated with {len(req_items)} functional requirement(s).',
                'flowchart': {
                    'nodes': [
                        {'id': 'start', 'label': f'{title} Initialization'},
                        {'id': 'check', 'label': f'{dept} Condition & Safety Check'},
                        {'id': 'exec', 'label': 'Execute Functional Logic'},
                        {'id': 'end', 'label': 'Normal Operation / Alarm State'},
                    ],
                    'edges': [
                        {'from': 'start', 'to': 'check'},
                        {'from': 'check', 'to': 'exec'},
                        {'from': 'exec', 'to': 'end'},
                    ]
                }
            })
            content = documents.clean_content(db, scope_id, 'frd', content)
            rev_row = db.execute('SELECT id FROM pi_revisions WHERE document_id=? ORDER BY created_at DESC LIMIT 1', (doc_id,)).fetchone()
            if rev_row:
                import json
                db.execute('UPDATE pi_revisions SET content=? WHERE id=?', (json.dumps(content), rev_row[0]))
            qc_row = db.execute('SELECT id FROM qc_revisions WHERE control_id=? ORDER BY created_at DESC LIMIT 1', (control_id,)).fetchone()
            if qc_row:
                import json
                db.execute('UPDATE qc_revisions SET template_snapshot=? WHERE id=?', (json.dumps(content), qc_row[0]))

        with hub.db() as db:
            num_row = db.execute('SELECT number FROM qc_documents WHERE id=?', (control_id,)).fetchone()
            doc_number = num_row[0] if num_row else f'FRD-{scope_id[:8].upper()}'
    except Exception as exc:
        import logging
        logging.getLogger('chopper.create_frd').exception('Failed to create FRD: %s', exc)
        scope_id = f"FRD-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    return {
        'scopeId': scope_id,
        'docTitle': title,
        'documentNumber': doc_number,
        'customer': customer,
        'department': dept,
        'scope': scope or f'Complete functional logic for {title}',
        'acceptanceCriteria': acceptance or 'Verification against engineering criteria',
        'requirements': req_items,
        'requirementsCount': len(req_items),
        'createdAt': datetime.now().isoformat(),
    }


def _summarize(result: dict) -> dict:
    """Build summary card from the FRD creation result."""
    return {
        'type':               'action-summary',
        'actionId':           'create_frd',
        'scopeId':            result.get('scopeId', ''),
        'docTitle':           result.get('docTitle', ''),
        'documentNumber':     result.get('documentNumber', ''),
        'customer':           result.get('customer', ''),
        'department':         result.get('department', ''),
        'scope':              result.get('scope', ''),
        'acceptanceCriteria': result.get('acceptanceCriteria', ''),
        'requirements':       result.get('requirements', []),
        'requirementsCount':  result.get('requirementsCount', 0),
        'deepLink':           {'page': 'home', 'scopeId': result.get('scopeId', '')},
    }


register(ActionEntry(
    id='create_frd',
    title='Create Functional Requirements Document (FRD)',
    window='workhub',
    patterns=_PATTERNS,
    slots=_SLOTS,
    permissions=['workhub'],
    run=_run,
    summarize=_summarize,
    description='Create an FRD with numbered functional requirements, sequence logic, scope and acceptance criteria.',
))
