"""Chopper Command Layer — stateless action router.

Entry point: reply_if_action(payload) -> dict | None

Returns None  → not a command phrase; existing Chopper path runs unchanged.
Returns dict  → one of three card types:
  {'type': 'action-question', ...}  — asking the user to fill a slot
  {'type': 'action-plan',     ...}  — plan summary, asks user to Confirm / Cancel
  {'type': 'action-summary',  ...}  — result of a confirmed and completed action
  {'type': 'action-error',    ...}  — permission denied or slot validation error

State travels in payload['_actionState']; it is signed by the server.
The client must echo _actionState back unchanged on subsequent messages.

Plan security:
  - Every plan is HMAC-SHA256 signed over (user_id, action_id, slots, expiry).
  - Plans expire after 15 minutes.
  - Each plan can be run exactly once (used-plan cache).
  - Project/metadata paths are re-validated server-side at run time.

Routing is entirely regex-based — the small language model is NOT consulted
for dispatch decisions.
"""
from __future__ import annotations

import os
from typing import Any

from backend.core.runtime import log


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_user() -> dict:
    try:
        from backend.core.run_history import current_user
        return current_user.get() or {}
    except Exception:
        return {}


def _user_id(user: dict) -> str:
    return str(user.get('id') or user.get('username') or 'anonymous')


def _departments() -> list[str]:
    """Return the department list from admin config (excluding 'All')."""
    try:
        from backend.api.admin_settings import read_config
        cfg = read_config()
        return [d for d in (cfg.get('departments') or []) if d.casefold() != 'all']
    except Exception:
        return []


def _error_card(message: str, action_id: str = '') -> dict:
    return {'type': 'action-error', 'actionId': action_id, 'message': message}


# ---------------------------------------------------------------------------
# State extraction
# ---------------------------------------------------------------------------

def _get_state(payload: dict) -> dict:
    state = payload.get('_actionState')
    return state if isinstance(state, dict) else {}


# ---------------------------------------------------------------------------
# Question phrase guard
# ---------------------------------------------------------------------------

# Phrases that look like commands but are actually questions.
# If the message matches any of these, we return None (old Chopper handles it).
_QUESTION_PREFIXES = (
    'what', 'how', 'why', 'when', 'where', 'which', 'who', 'can you explain',
    'explain', 'tell me', 'show me', 'describe', 'is there', 'does',
    'are there', 'do i', 'should i', 'could you', 'would you',
)


def _looks_like_question(text: str) -> bool:
    low = text.strip().lower()
    for prefix in _QUESTION_PREFIXES:
        if low.startswith(prefix):
            return True
    if low.endswith('?'):
        return True
    return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def reply_if_action(payload: dict) -> dict | None:  # noqa: C901
    """Route a Chopper payload to the command layer.

    Returns None when the message is a question or no command pattern matches.
    Returns a card dict when an action is detected or in progress.
    """
    # Feature flag — checked first; if explicitly disabled ('0'), hand back to old Chopper.
    if os.environ.get('USOPP_CHOPPER_ACTIONS') == '0':
        return None

    question = str(payload.get('question') or '').strip()
    if not question:
        return None

    user = _current_user()
    uid  = _user_id(user)
    state = _get_state(payload)

    # --- Check for confirmation / cancellation / swap of an in-progress plan -------
    q_lower = question.lower()
    if state.get('phase') == 'confirm':
        if q_lower in {'yes', 'confirm', 'proceed', 'ok', 'go', 'run it', 'do it', 'execute'}:
            return _execute_confirmed_plan(state, user, uid)
        if q_lower in {'no', 'cancel', 'stop', 'abort', 'back', 'never mind'}:
            return {'type': 'action-cancelled', 'message': 'Action cancelled. What else can I help you with?'}
        if q_lower in {'swap', 'reverse', 'invert', 'switch'} and state.get('actionId') == 'matchview':
            slots = dict(state.get('slots') or {})
            slots['base_path'], slots['new_path'] = slots.get('new_path', ''), slots.get('base_path', '')
            state['slots'] = slots
            return _rebuild_plan_card(state, user, uid, notice='Swapped Base and Developed projects.')
        # Ambiguous — re-show the plan card and ask again
        return _rebuild_plan_card(state, user, uid, notice='Please reply with Confirm or Cancel.')

    # --- Check if we are mid-flow filling slots --------------------------------
    if state.get('phase') == 'collecting' and state.get('actionId'):
        return _continue_collection(state, user, uid, question, payload)

    # --- Fresh message — question guard first ---------------------------------
    if _looks_like_question(question):
        return None

    # --- Pattern matching -----------------------------------------------------
    from backend.core.chopper_actions.registry import match_action
    entry = match_action(question)
    if entry is None:
        return None

    # --- Permission check -----------------------------------------------------
    from backend.core.chopper_actions.permissions import user_has_permission, module_permitted
    if not user_has_permission(user):
        return None   # silently fall through to old Chopper

    for mod in entry.permissions:
        if not module_permitted(user, mod):
            return _error_card(
                f'Your account does not have access to the {mod} module. '
                f'Ask an administrator to enable it.',
                entry.id,
            )

    # --- Start slot collection ------------------------------------------------
    return _start_collection(entry, user, uid, question, payload)


# ---------------------------------------------------------------------------
# Slot collection state machine
# ---------------------------------------------------------------------------

def _start_collection(entry: 'ActionEntry', user: dict, uid: str, question: str, payload: dict | None = None) -> dict:  # type: ignore[name-defined]
    """Begin collecting slots for a freshly matched action."""
    slots: dict[str, str] = {}
    payload = payload or {}
    context = payload.get('context') if isinstance(payload.get('context'), dict) else {}

    # Extract attached projects/files if any
    attached_projects: list[str] = []
    raw_attachments = payload.get('attachments') or context.get('attachments') or []
    if isinstance(raw_attachments, list):
        for att in raw_attachments:
            if isinstance(att, dict) and att.get('projectPath'):
                attached_projects.append(str(att['projectPath']))

    ctx_project = str(context.get('projectPath') or '').strip()

    if entry.id == 'matchview':
        if len(attached_projects) >= 2:
            slots['base_path'] = attached_projects[0]
            slots['new_path'] = attached_projects[1]
        elif len(attached_projects) == 1 and ctx_project and ctx_project != attached_projects[0]:
            slots['base_path'] = ctx_project
            slots['new_path'] = attached_projects[0]
    elif entry.id == 'bytecheck':
        if attached_projects:
            slots['project_path'] = attached_projects[0]
        elif ctx_project:
            slots['project_path'] = ctx_project

    # Pre-fill CHOICE slots with department list metadata
    for slot in entry.slots:
        if slot.kind == 'choice' and slot.key == 'machine_department':
            slot.choices = _departments()

    # Find the first unfilled required slot
    next_slot = _next_required_slot(entry, slots)
    if next_slot is None:
        # All required slots pre-filled (unusual on first message)
        return _build_plan_card(entry, slots, uid)

    new_state = {
        'phase':    'collecting',
        'actionId': entry.id,
        'slots':    slots,
        'fillSlot': next_slot.key,
    }
    return _question_card(next_slot, entry, new_state, uid)


def _continue_collection(state: dict, user: dict, uid: str, answer: str, payload: dict) -> dict:
    from backend.core.chopper_actions.registry import get_action
    entry = get_action(state.get('actionId', ''))
    if entry is None:
        return None  # type: ignore[return-value]

    slots: dict = dict(state.get('slots') or {})
    fill_key = str(state.get('fillSlot') or '')
    slot_def = next((s for s in entry.slots if s.key == fill_key), None)

    if slot_def is None:
        return _error_card('Internal error: unknown slot. Please start again.', entry.id)

    # Accept / validate the answer
    answer = answer.strip()
    if answer.lower() in {'skip', ''} and slot_def.optional:
        slots[fill_key] = ''
    elif slot_def.kind == 'choice':
        # Validate department choice
        normalized = _match_choice(answer, slot_def.choices)
        if normalized is None:
            return _question_card(
                slot_def, entry,
                {**state, 'slots': slots},
                uid,
                notice=f'"{answer}" is not in the list. Choose one of: {", ".join(slot_def.choices[:8])}.',
            )
        slots[fill_key] = normalized
    elif slot_def.kind in {'project', 'metadata'}:
        # Validate path eagerly so errors surface before the plan card
        try:
            if slot_def.kind == 'project':
                from backend.core.chopper_actions.plan_security import validate_project_path
                validate_project_path(answer)
            else:
                from backend.core.chopper_actions.plan_security import validate_metadata_path
                validate_metadata_path(answer)
            slots[fill_key] = answer
        except Exception as exc:
            notice = str(getattr(exc, 'detail', exc))
            return _question_card(
                slot_def, entry,
                {**state, 'slots': slots},
                uid,
                notice=notice,
            )
    else:
        slots[fill_key] = answer

    # Find the next unfilled required slot
    next_slot = _next_required_slot(entry, slots)
    if next_slot is not None:
        new_state = {**state, 'slots': slots, 'fillSlot': next_slot.key}
        return _question_card(next_slot, entry, new_state, uid)

    # All required slots filled — show plan card
    return _build_plan_card(entry, slots, uid)


def _next_required_slot(entry: 'ActionEntry', slots: dict) -> 'SlotDef | None':  # type: ignore[name-defined]
    for slot in entry.slots:
        if not slot.optional and not slots.get(slot.key):
            return slot
    return None


def _match_choice(answer: str, choices: list[str]) -> str | None:
    lower = answer.strip().casefold()
    for c in choices:
        if c.casefold() == lower:
            return c
    for c in choices:
        if c.casefold().startswith(lower):
            return c
    return None


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------

def _question_card(slot_def: 'SlotDef', entry: 'ActionEntry', state: dict, uid: str, notice: str = '') -> dict:  # type: ignore[name-defined]
    return {
        'type':        'action-question',
        'actionId':    entry.id,
        'actionTitle': entry.title,
        'slot':        slot_def.key,
        'slotKind':    slot_def.kind,
        'label':       slot_def.label,
        'question':    slot_def.prompt,
        'choices':     slot_def.choices,
        'optional':    slot_def.optional,
        'notice':      notice,
        '_actionState': state,
        'source':      'chopper-action',
        'model':       None,
        'evidence':    [],
    }


def _build_plan_card(entry: 'ActionEntry', slots: dict, uid: str) -> dict:
    from backend.core.chopper_actions.plan_security import sign_plan, plan_hash as make_hash

    sig, expiry = sign_plan(uid, entry.id, slots)
    p_hash = make_hash(uid, entry.id, slots, expiry)

    # Human-readable slot summary (do NOT include raw paths in model context)
    slot_summary = []
    for slot_def in entry.slots:
        val = slots.get(slot_def.key) or ''
        if val:
            slot_summary.append({'label': slot_def.label, 'value': val})

    state = {
        'phase':     'confirm',
        'actionId':  entry.id,
        'slots':     slots,
        'signature': sig,
        'expiry':    expiry,
        'planHash':  p_hash,
    }

    return {
        'type':        'action-plan',
        'actionId':    entry.id,
        'actionTitle': entry.title,
        'description': entry.description,
        'slotSummary': slot_summary,
        'expiresIn':   '15 minutes',
        '_actionState': state,
        'source':      'chopper-action',
        'model':       None,
        'evidence':    [],
        'answer':      _plan_text(entry.title, slot_summary),
    }


def _rebuild_plan_card(state: dict, user: dict, uid: str, notice: str = '') -> dict:
    from backend.core.chopper_actions.registry import get_action
    entry = get_action(state.get('actionId', ''))
    if entry is None:
        return _error_card('Plan not found. Please start again.')
    card = _build_plan_card(entry, state.get('slots', {}), uid)
    if notice:
        card['notice'] = notice
    return card


def _plan_text(title: str, slot_summary: list[dict]) -> str:
    lines = [f'**{title} — Action Plan**', '']
    for item in slot_summary:
        lines.append(f'- **{item["label"]}:** {item["value"]}')
    lines += ['', 'Reply **Confirm** to run, or **Cancel** to stop.']
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Plan execution
# ---------------------------------------------------------------------------

def _execute_confirmed_plan(state: dict, user: dict, uid: str) -> dict:
    from backend.core.chopper_actions.plan_security import verify_plan, consume_plan
    from backend.core.chopper_actions.registry import get_action
    from backend.core.chopper_actions.audit import write_audit

    action_id = str(state.get('actionId') or '')
    slots     = state.get('slots') or {}
    expiry    = int(state.get('expiry') or 0)
    signature = str(state.get('signature') or '')
    p_hash    = str(state.get('planHash') or '')

    entry = get_action(action_id)
    if entry is None:
        return _error_card('The action is no longer registered. Please start again.')

    # Verify plan security
    err = verify_plan(uid, action_id, slots, expiry, signature, p_hash)
    if err:
        return _error_card(err, action_id)

    # Permission re-check at run time
    from backend.core.chopper_actions.permissions import user_has_permission, module_permitted
    if not user_has_permission(user):
        return _error_card('You do not have permission to run Chopper actions.', action_id)
    for mod in entry.permissions:
        if not module_permitted(user, mod):
            return _error_card(f'Module {mod} is not enabled for your account.', action_id)

    # Mark plan as used BEFORE running (prevents double-submit)
    consume_plan(p_hash, expiry)

    # Execute
    try:
        result = entry.run(slots, user)
        summary = entry.summarize(result)
        write_audit(
            user_id=uid,
            action_id=action_id,
            input_summary={k: (v[:120] if isinstance(v, str) else v) for k, v in slots.items()},
            result_id=str(result.get('sessionId') or ''),
            status='ok',
        )
        summary['answer'] = _result_text(summary)
        summary['source'] = 'chopper-action'
        summary['model']  = None
        summary['evidence'] = []
        return summary
    except Exception as exc:
        log.exception('CHOPPER_ACTION_RUN_ERROR action=%s user=%s', action_id, uid)
        write_audit(
            user_id=uid,
            action_id=action_id,
            input_summary={k: (v[:120] if isinstance(v, str) else v) for k, v in slots.items()},
            result_id='',
            status='error',
            error=str(exc),
        )
        detail = getattr(exc, 'detail', str(exc))
        return _error_card(f'The action failed: {detail}', action_id)


def _result_text(summary: dict) -> str:
    if summary.get('actionId') == 'bytecheck':
        c = summary.get('counts') or {}
        lines = [
            f'**ByteMap Validation complete** — {summary.get("projectName", "")} '
            f'({summary.get("department", "")})',
            '',
            f'✅ Pass: {c.get("pass", 0)}  '
            f'❌ Fail: {c.get("fail", 0)}  '
            f'⚠️ Warning: {c.get("warning", 0)}  '
            f'Groups: {c.get("groups", 0)}',
        ]
        if summary.get('topFails'):
            lines += ['', '**Top fails:**']
            for issue in summary['topFails']:
                loc = f' `{issue["location"]}`' if issue.get('location') else ''
                lines.append(f'- {issue["parameter"]}: {issue["message"]}{loc}')
        lines += ['', 'Click **View details** to open ByteMap.']
        return '\n'.join(lines)

    if summary.get('actionId') == 'matchview':
        s = summary.get('summary') or {}
        lines = [
            f'**MatchView Comparison complete** — '
            f'{summary.get("baseName", "")} → {summary.get("newName", "")}',
            '',
            f'Added: {s.get("added", 0)}  |  '
            f'Removed: {s.get("removed", 0)}  |  '
            f'Modified: {s.get("modified", 0)}  |  '
            f'Unchanged: {s.get("unchanged", 0)}',
        ]
        by_cat = summary.get('byCategory') or {}
        if by_cat:
            lines += ['', '**By category:**']
            for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]):
                lines.append(f'- {cat}: {count} change(s)')
        if summary.get('topChanged'):
            lines += ['', '**Top changed files:**']
            for item in summary['topChanged'][:5]:
                lines.append(f'- `{item["path"]}` ({item["status"]})')
        lines += ['', 'Click **View details** to open MatchView.']
        return '\n'.join(lines)

    return 'Action complete.'
