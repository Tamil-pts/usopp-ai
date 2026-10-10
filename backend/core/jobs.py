"""Bound concurrent engines while keeping reads and source saves per project."""
import os
import threading
from contextlib import contextmanager, ExitStack
from pathlib import Path
from fastapi import HTTPException

MAX_PARALLEL_TESTS = max(1, int(os.getenv('USOPP_MAX_PARALLEL_TESTS', '5')))
SLOTS = threading.BoundedSemaphore(MAX_PARALLEL_TESTS)
GUARD = threading.RLock()
PROJECTS = {}
ACTIVE = {}

def project_lock(root):
    key = os.path.normcase(str(Path(root).resolve()))
    with GUARD:
        return PROJECTS.setdefault(key, threading.RLock())

@contextmanager
def projects_job(roots, editing=False):
    keys = sorted(set(os.path.normcase(str(Path(root).resolve())) for root in roots))
    with GUARD:
        for key in keys: ACTIVE[key] = ACTIVE.get(key, 0) + 1
    try:
        with ExitStack() as stack:
            for key in keys:
                lock = project_lock(key)
                if not lock.acquire(blocking=not editing):
                    raise HTTPException(409, 'This project is being processed. Wait before saving its source.')
                stack.callback(lock.release)
            if editing: yield
            else:
                with SLOTS: yield
    finally:
        with GUARD:
            for key in keys:
                ACTIVE[key] -= 1
                if not ACTIVE[key]: del ACTIVE[key]

def project_job(root, editing=False):
    return projects_job([root], editing)

@contextmanager
def workspace_cleanup(path):
    """Prevent deletion of a source directory used by a queued or active test."""
    root = Path(path).resolve()
    with GUARD:
        busy = any(Path(key).is_relative_to(root) for key in ACTIVE)
        yield not busy
