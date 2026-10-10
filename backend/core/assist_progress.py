"""Per-request Chopper progress, propagated into the background context."""
from contextvars import ContextVar

reporter = ContextVar('chopper_progress', default=None)


def report(stage, current=None, total=None):
    callback = reporter.get()
    if callback:
        callback(stage, current, total)
