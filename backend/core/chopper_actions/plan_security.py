"""Chopper Command Layer — HMAC plan signing, used-plan cache, slot validation.

Security model (all enforced server-side):
  1. The server signs every plan card with HMAC-SHA256 over a canonical
     representation of: user_id | action_id | slots | expiry_epoch.
  2. At run time the signature is re-verified before any side effect.
  3. A used-plan cache (in-memory, keyed by plan_hash until expiry) ensures
     a confirmed plan can run exactly once.
  4. Project-path slots are re-validated via _local_path so the server never
     trusts a path the client sent — the same check ByteMap and MatchView use.
  5. Plans expire after PLAN_TTL_SECONDS (900 s = 15 min).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from pathlib import Path

from backend.core.runtime import BASE, log

# ---------------------------------------------------------------------------
# Server secret — derived from a stable file, never from the client.
# If the file doesn't exist, it is created once with os.urandom.
# ---------------------------------------------------------------------------

_SECRET_FILE = BASE / '.usopp_chopper2' / 'plan_signing_key.bin'
_SECRET_LOCK = threading.Lock()


def _server_secret() -> bytes:
    with _SECRET_LOCK:
        try:
            return _SECRET_FILE.read_bytes()
        except FileNotFoundError:
            secret = os.urandom(32)
            _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SECRET_FILE.write_bytes(secret)
            return secret
        except OSError as exc:
            log.error('CHOPPER_ACTIONS_SECRET_READ_ERROR %s', exc)
            raise


# ---------------------------------------------------------------------------
# Plan TTL
# ---------------------------------------------------------------------------

PLAN_TTL_SECONDS = 900  # 15 minutes


# ---------------------------------------------------------------------------
# Used-plan cache — in-memory, pruned lazily on every write.
# Key: plan_hash (hex string)  Value: expiry epoch float
# ---------------------------------------------------------------------------

_USED_PLANS: dict[str, float] = {}
_USED_PLANS_LOCK = threading.Lock()


def _prune_used_plans() -> None:
    now = time.time()
    with _USED_PLANS_LOCK:
        expired = [h for h, exp in _USED_PLANS.items() if now > exp]
        for h in expired:
            del _USED_PLANS[h]


def _mark_used(plan_hash: str, expiry: float) -> None:
    _prune_used_plans()
    with _USED_PLANS_LOCK:
        _USED_PLANS[plan_hash] = expiry


def _is_used(plan_hash: str) -> bool:
    with _USED_PLANS_LOCK:
        return plan_hash in _USED_PLANS


# ---------------------------------------------------------------------------
# Canonical representation for signing
# ---------------------------------------------------------------------------

def _canonical(user_id: str, action_id: str, slots: dict, expiry: int) -> bytes:
    """Deterministic UTF-8 bytes over the fields that must not be tampered with."""
    obj = {
        'u': str(user_id),
        'a': str(action_id),
        's': {str(k): str(v) for k, v in sorted(slots.items())},
        'e': int(expiry),
    }
    return json.dumps(obj, ensure_ascii=True, separators=(',', ':')).encode('utf-8')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sign_plan(user_id: str, action_id: str, slots: dict) -> tuple[str, int]:
    """Sign a plan and return (hex_signature, expiry_epoch_int)."""
    expiry = int(time.time()) + PLAN_TTL_SECONDS
    msg = _canonical(user_id, action_id, slots, expiry)
    sig = hmac.new(_server_secret(), msg, hashlib.sha256).hexdigest()
    return sig, expiry


def verify_plan(
    user_id: str,
    action_id: str,
    slots: dict,
    expiry: int,
    signature: str,
    plan_hash: str,
) -> str | None:
    """Verify a plan submitted by the client.

    Returns None on success.
    Returns a human-readable error string on failure (do NOT expose internal
    details to the client; log them server-side instead).
    """
    # 1. Expired?
    if int(time.time()) > expiry:
        return 'This action plan has expired. Please start again.'

    # 2. Already used?
    if _is_used(plan_hash):
        return 'This action plan has already been used. Please start again.'

    # 3. HMAC match?
    msg = _canonical(user_id, action_id, slots, expiry)
    expected = hmac.new(_server_secret(), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(signature)):
        log.warning(
            'CHOPPER_ACTIONS_PLAN_TAMPER user=%s action=%s', user_id, action_id
        )
        return 'Action plan signature is invalid. Please start again.'

    return None


def consume_plan(plan_hash: str, expiry: int) -> None:
    """Mark a plan as used so it cannot be replayed."""
    _mark_used(plan_hash, float(expiry))


def plan_hash(user_id: str, action_id: str, slots: dict, expiry: int) -> str:
    """Stable hex identifier for a plan (used as the cache key)."""
    msg = _canonical(user_id, action_id, slots, expiry)
    return hashlib.sha256(msg).hexdigest()


# ---------------------------------------------------------------------------
# Slot path validation — always call this at run time, never trust the client.
# ---------------------------------------------------------------------------

def validate_project_path(raw: str) -> Path:
    """Re-validate a project path using the same check ByteMap uses.

    Raises HTTPException (400 / 403 / 404) on failure — identical to the
    _local_path guard already in backend.core.runtime.
    """
    from backend.core.runtime import _local_path, locate_root
    return locate_root(_local_path(raw, must_exist=True, directory=True))


def validate_metadata_path(raw: str) -> Path | None:
    """Validate an optional metadata xlsx path.  Returns None if raw is empty."""
    if not raw or not str(raw).strip():
        return None
    from backend.core.runtime import _local_path
    p = _local_path(raw, must_exist=True, directory=False)
    if p.suffix.lower() not in {'.xlsx', '.xls'}:
        from fastapi import HTTPException
        raise HTTPException(400, 'Metadata must be an .xlsx or .xls file.')
    return p
