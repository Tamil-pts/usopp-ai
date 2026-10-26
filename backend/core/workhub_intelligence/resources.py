"""Small, shared resource budgets for the existing WorkHub workers."""
from contextlib import contextmanager
import contextvars
import os
from pathlib import Path
import shutil
import threading
import time
import uuid
import psutil
from backend.core.workhub import store as hub, timestamp

CURRENT_JOB = contextvars.ContextVar('workhub_job', default=None)
MIB = 1024 * 1024


def setting(name, default, minimum=1, maximum=100000):
    try:
        return min(maximum, max(minimum, int(os.getenv('USOPP_PI_'+name, str(default)))))
    except ValueError:
        return default


def memory():
    host = psutil.virtual_memory()
    available, total, used = host.available, host.total, host.used
    # cgroup v2 and v1 limits, when the server runs in Docker.
    for limit_path, usage_path in (('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory.current'),
                                   ('/sys/fs/cgroup/memory/memory.limit_in_bytes', '/sys/fs/cgroup/memory/memory.usage_in_bytes')):
        try:
            limit = int(Path(limit_path).read_text().strip()); usage = int(Path(usage_path).read_text().strip())
            if 0 < limit < total:
                total, used, available = limit, usage, min(available, max(0, limit-usage))
                break
        except (OSError, ValueError):
            continue
    return {'total_bytes': total, 'available_bytes': available, 'used_bytes': used}


def admission(lane='document'):
    reserve = setting('MEMORY_RESERVE_MB', 256, 0)*MIB
    needed = setting('AI_REQUEST_MEMORY_MB' if lane == 'inference' else 'JOB_MEMORY_MB', 256, 0)*MIB
    if memory()['available_bytes'] < reserve+needed:
        return 'Waiting for available memory'
    if shutil.disk_usage(hub.root).free < setting('DISK_RESERVE_MB', 512, 0)*MIB:
        return 'Waiting for free disk capacity'
    return None


@contextmanager
def inference_slot(check=lambda: None,request_timeout=None):
    """Persistent FIFO admission shared by Qwen requests across app/worker processes.

    Only lease IDs and numeric telemetry are stored here, never prompts or tokens.
    Requests already admitted keep their reservation until their HTTP call ends.
    """
    from . import store
    from .local_ai import ServiceUnavailable
    store.initialize()
    key = uuid.uuid4().hex; job = CURRENT_JOB.get(); now = time.time()
    wait_seconds = setting('AI_QUEUE_TIMEOUT', 120, 1, 3600)
    request_seconds = min(3600,max(1,int(request_timeout))) if request_timeout else setting('LLM_TIMEOUT', 240, 1, 3600)
    with hub.db(True) as db:
        db.execute('DELETE FROM pi_inference WHERE expires<?', (now,))
        db.execute("UPDATE pi_inference SET expires=MIN(expires,?) WHERE job_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM pi_jobs j WHERE j.id=pi_inference.job_id AND j.status='running' AND j.lease_owner=pi_inference.owner AND j.lease_until>?)",(now+30,now))
        if db.execute('SELECT COUNT(*) FROM pi_inference').fetchone()[0] >= setting('AI_MAX_PENDING', 32):
            raise ServiceUnavailable('The local inference queue is full. Retry when existing requests finish.')
        db.execute('INSERT INTO pi_inference(id,job_id,state,created,expires,owner) VALUES(?,?,?,?,?,?)',
                   (key, job.row['id'] if job else None, 'waiting', now, now+wait_seconds+10,job.lease if job else ''))
    stop = threading.Event(); heartbeat = None; failed=False; acquired=False
    try:
        deadline = now+wait_seconds
        while True:
            check(); now = time.time()
            if now >= deadline:
                raise ServiceUnavailable('The local model is busy or waiting for memory. Retry this saved job later.')
            reason = admission('inference')
            with hub.db(True) as db:
                db.execute('DELETE FROM pi_inference WHERE expires<?', (now,))
                first = db.execute("SELECT id FROM pi_inference WHERE state='waiting' ORDER BY created,id LIMIT 1").fetchone()
                active = db.execute("SELECT COUNT(*) FROM pi_inference WHERE state='running'").fetchone()[0]
                if not reason and first and first['id'] == key and active < setting('AI_CONCURRENCY', 1, 1, 8):
                    db.execute("UPDATE pi_inference SET state='running',started=?,expires=? WHERE id=?", (now, now+request_seconds+30, key))
                    acquired=True
                    break
            stop.wait(.25)
        def renew():
            while not stop.wait(10):
                try:
                    check()
                    with hub.db(True) as db:
                        db.execute('UPDATE pi_inference SET expires=? WHERE id=?', (time.time()+request_seconds+30, key))
                except Exception:
                    return
        heartbeat = threading.Thread(target=renew, daemon=True, name='workhub-inference-lease'); heartbeat.start()
        yield
    except BaseException:
        failed=True;raise
    finally:
        stop.set()
        if heartbeat: heartbeat.join(timeout=1)
        with hub.db(True) as db:
            # A remote model may still be unwinding a timed-out request. Keep a
            # short reservation instead of immediately admitting another request.
            if failed and acquired:db.execute('UPDATE pi_inference SET expires=? WHERE id=?',(time.time()+30,key))
            else:db.execute('DELETE FROM pi_inference WHERE id=?', (key,))


def kill_owned_tree(process):
    """Stop only the child started by this supervisor, including native converters."""
    try:
        parent = psutil.Process(process.pid)
        descendants = parent.children(recursive=True)
        # Freeze the root first so it cannot fork while descendants are collected.
        try: parent.suspend()
        except psutil.Error: pass
        descendants = list({p.pid: p for p in descendants+parent.children(recursive=True)}.values())
        for child in descendants:
            try:child.suspend()
            except psutil.Error:pass
        descendants = list({p.pid: p for p in descendants+parent.children(recursive=True)}.values())
        for child in reversed(descendants):
            try: child.kill()
            except psutil.Error: pass
        parent.kill()
        psutil.wait_procs(descendants+[parent], timeout=3)
    except psutil.NoSuchProcess:
        pass


def tree_rss(process):
    try:
        root = psutil.Process(process.pid)
        return sum(p.memory_info().rss for p in [root]+root.children(recursive=True) if p.is_running())
    except psutil.Error:
        return 0
