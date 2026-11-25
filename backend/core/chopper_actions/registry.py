"""Chopper Command Layer — action registry.

Each action is described by an ActionEntry. Actions are registered at
import time; the router looks them up by pattern matching.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Any


# ---------------------------------------------------------------------------
# Data types for slot definitions
# ---------------------------------------------------------------------------

class SlotKind:
    PROJECT  = 'project'      # local FS path to an Automation Studio project
    METADATA = 'metadata'     # local FS path to a metadata .xlsx file
    CHOICE   = 'choice'       # one value from a fixed list (e.g. machine_department)
    TEXT     = 'text'         # free-form short string


@dataclass
class SlotDef:
    key:      str
    kind:     str              # SlotKind constant
    label:    str              # shown to the user
    prompt:   str              # question text
    choices:  list[str] = field(default_factory=list)   # for CHOICE slots
    optional: bool = False


# ---------------------------------------------------------------------------
# ActionEntry
# ---------------------------------------------------------------------------

@dataclass
class ActionEntry:
    id:            str
    title:         str
    window:        str                   # module id the user needs: 'bytemap' | 'matchview'
    patterns:      list[re.Pattern]      # regex patterns that identify a command phrase
    slots:         list[SlotDef]         # ordered slot definitions
    permissions:   list[str]            # required workspace module ids
    run:           Callable              # (slots: dict, user: dict) -> result dict
    summarize:     Callable              # (result: dict) -> chat-card dict (computed, never LLM)
    description:   str = ''


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, ActionEntry] = {}


def register(entry: ActionEntry) -> None:
    _REGISTRY[entry.id] = entry


def all_actions() -> list[ActionEntry]:
    return list(_REGISTRY.values())


def get_action(action_id: str) -> ActionEntry | None:
    return _REGISTRY.get(action_id)


def match_action(text: str) -> ActionEntry | None:
    """Return the first registered action whose pattern matches *text*.

    Returns None when no pattern matches — the caller (router) will fall
    through to the existing Chopper question path unchanged.
    """
    lower = text.lower()
    for entry in _REGISTRY.values():
        if any(p.search(lower) for p in entry.patterns):
            return entry
    return None


# ---------------------------------------------------------------------------
# Lazy registration — importing this package registers all built-in actions.
# Actions import here so the registry is populated on first package import.
# ---------------------------------------------------------------------------

def _register_builtin_actions() -> None:
    from backend.core.chopper_actions.actions import bytecheck             # noqa: F401 — registers itself
    from backend.core.chopper_actions.actions import matchview             # noqa: F401 — registers itself
    from backend.core.chopper_actions.actions import project_pack          # noqa: F401 — registers itself
    from backend.core.chopper_actions.actions import create_frd            # noqa: F401 — registers itself
    from backend.core.chopper_actions.actions import create_mom            # noqa: F401 — registers itself
    from backend.core.chopper_actions.actions import create_quality_report # noqa: F401 — registers itself


_register_builtin_actions()
