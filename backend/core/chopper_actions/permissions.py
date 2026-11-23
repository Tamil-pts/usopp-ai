"""Chopper Command Layer — pilot-user permission check.

Admins always have access.
A configurable 'pilot_users' list (usernames or roles) can be managed in
Admin Settings → Chopper Actions. Do not hard-code names here.

Config file: BASE / '.usopp_chopper2' / 'chopper_actions_config.json'
Schema:
  {
    "version": "1.0",
    "pilot_users":  ["alice", "bob"],       // exact usernames
    "pilot_roles":  ["lead_engineer"]       // role strings
  }
"""
from __future__ import annotations

import json
import os

from backend.core.runtime import BASE

_CONFIG_PATH = BASE / '.usopp_chopper2' / 'chopper_actions_config.json'
_DEFAULT: dict = {'version': '1.0', 'pilot_users': [], 'pilot_roles': []}


def _read_config() -> dict:
    try:
        value = json.loads(_CONFIG_PATH.read_text(encoding='utf-8'))
        if isinstance(value, dict):
            return value
    except (OSError, ValueError):
        pass
    return _DEFAULT


def save_config(payload: dict) -> dict:
    """Persist pilot user/role lists. Called from admin_settings endpoint."""
    pilot_users = [str(u).strip() for u in (payload.get('pilot_users') or []) if str(u).strip()]
    pilot_roles = [str(r).strip() for r in (payload.get('pilot_roles') or []) if str(r).strip()]
    cfg = {'version': '1.0', 'pilot_users': pilot_users, 'pilot_roles': pilot_roles}
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
    return cfg


def read_config() -> dict:
    return _read_config()


def user_has_permission(user: dict | None) -> bool:
    """Return True if *user* is allowed to use Chopper actions.

    Admins always pass. When pilot_users / pilot_roles are unconfigured (the default),
    all users are permitted. If an admin configures a pilot list, only admins and
    listed users/roles pass.
    """
    if os.environ.get('USOPP_CHOPPER_ACTIONS') == '0':
        return False
    user = user or {}
    role = str(user.get('role') or '')
    if role == 'admin':
        return True
    cfg = _read_config()
    pilot_users = {str(u).strip().casefold() for u in (cfg.get('pilot_users') or [])}
    pilot_roles = {str(r).strip().casefold() for r in (cfg.get('pilot_roles') or [])}
    # Default-open: if no pilot restrictions are configured, allow all users
    if not pilot_users and not pilot_roles:
        return True
    username = str(user.get('username') or user.get('id') or '')
    return (
        username.casefold() in pilot_users
        or role.casefold() in pilot_roles
    )


def module_permitted(user: dict, module_id: str) -> bool:
    """Check the user has the required workspace module enabled."""
    from_modules = user.get('workspaceModules')
    if from_modules is None:
        return True  # all modules visible (admin or default)
    return module_id in from_modules
