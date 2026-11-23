"""Chopper Command Layer — action registry, router and built-in actions.

All new code lives here. The only change to existing files is a single
early-return hook added to backend/api/assist.py::_assist() after the
existing log_diagnostics and report_analysis hooks.

Feature flag: USOPP_CHOPPER_ACTIONS=1  (admin-only by default; see permissions.py).
"""
