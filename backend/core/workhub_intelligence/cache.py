"""Project-scoped, integrity-checked reusable processing outputs in SQLite.

The immutable source blob hash and processor/options version form the identity.
Leases serialize simultaneous misses. A killed worker leaves a recoverable lease,
not a partially published extraction. Cached content is never served by a public URL.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
import uuid
import zlib
from functools import lru_cache
from importlib.metadata import version,PackageNotFoundError
from backend.core.workhub import store as hub
from .resources import CURRENT_JOB, setting
from .reliability import digest

MAX_OUTPUT = 24*1024*1024


@lru_cache(maxsize=8)
def library_version(extension):
    package={'.pdf':'pypdf','.docx':'python-docx','.xlsx':'openpyxl'}.get(extension,'Pillow')
    try:return version(package)
    except PackageNotFoundError:return 'unavailable'


def compute(pid, key, processor, factory, check=lambda: None):
    from . import store
    store.initialize(); owner=uuid.uuid4().hex; began=time.monotonic(); stop=threading.Event()
    while True:
        check(); now=time.time()
        with hub.db(True) as db:
            row=db.execute('SELECT * FROM pi_cache WHERE project_id=? AND cache_key=?',(pid,key)).fetchone()
            if row and row['state']=='ready':
                try:
                    raw=_unpack(row['output'])
                    if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Cache integrity check failed')
                    value=json.loads(raw)
                except (ValueError,TypeError,zlib.error):
                    db.execute('DELETE FROM pi_cache WHERE project_id=? AND cache_key=?',(pid,key))
                else:
                    db.execute('UPDATE pi_cache SET hits=hits+1,updated=? WHERE project_id=? AND cache_key=?',(now,pid,key))
                    return value, True
            elif row and row['expires']>now:
                pass
            else:
                from .local_ai import ServiceUnavailable
                used=db.execute('SELECT COALESCE(SUM(output_bytes),0) FROM pi_cache').fetchone()[0]
                if used >= setting('CACHE_MAX_MB',1024)*1024*1024:
                    # Do not evict originals or approved revisions. Full cache can
                    # be bypassed safely; durable document results still persist.
                    break
                db.execute('INSERT INTO pi_cache(project_id,cache_key,processor,state,owner,expires,created,updated) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(project_id,cache_key) DO UPDATE SET state=excluded.state,owner=excluded.owner,expires=excluded.expires,updated=excluded.updated',
                           (pid,key,processor,'processing',owner,now+90,now,now))
                break
        if time.monotonic()-began>setting('CACHE_WAIT_SECONDS',120,1,3600):
            from .local_ai import ServiceUnavailable
            raise ServiceUnavailable('This source revision is being processed by another worker. Retry when it finishes.')
        stop.wait(.2)
    def renew():
        while not stop.wait(20):
            try:
                check()
                with hub.db(True) as db:db.execute('UPDATE pi_cache SET expires=? WHERE project_id=? AND cache_key=? AND owner=?',(time.time()+90,pid,key,owner))
            except Exception:return
    heartbeat=threading.Thread(target=renew,daemon=True,name='workhub-cache-lease');heartbeat.start()
    try:
        value=factory();check();raw=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
        if len(raw)<=MAX_OUTPUT:
            output=zlib.compress(raw,level=3)
            with hub.db(True) as db:
                used=db.execute('SELECT COALESCE(SUM(output_bytes),0) FROM pi_cache').fetchone()[0]
                if used+len(output)<=setting('CACHE_MAX_MB',1024)*1024*1024:
                    db.execute("UPDATE pi_cache SET state='ready',output=?,sha256=?,output_bytes=?,input_bytes=?,duration_ms=?,expires=0,updated=? WHERE project_id=? AND cache_key=? AND owner=?",
                               (output,hashlib.sha256(raw).hexdigest(),len(output),len(raw),int((time.monotonic()-began)*1000),time.time(),pid,key,owner))
                else:db.execute('DELETE FROM pi_cache WHERE project_id=? AND cache_key=? AND owner=?',(pid,key,owner))
        else:
            with hub.db(True) as db:db.execute('DELETE FROM pi_cache WHERE project_id=? AND cache_key=? AND owner=?',(pid,key,owner))
        return value, False
    except BaseException:
        with hub.db(True) as db:db.execute('DELETE FROM pi_cache WHERE project_id=? AND cache_key=? AND owner=?',(pid,key,owner))
        raise
    finally:
        stop.set();heartbeat.join(timeout=1)


def _unpack(data):
    decoder=zlib.decompressobj();raw=decoder.decompress(data,MAX_OUTPUT+1)
    if len(raw)>MAX_OUTPUT or not decoder.eof or decoder.unused_data:raise ValueError('Invalid cache payload')
    return raw


def extraction(file_id,pid,extractor,check=lambda:None):
    from backend.core.workhub_files import file_record
    row,path=file_record(file_id,pid)  # Recheck project scope even on a cache hit.
    from .documents import MAX_DOCUMENT
    if row['size']>MAX_DOCUMENT:raise ValueError('This document exceeds the processing file-size limit.')
    extension=Path(row['name']).suffix.lower()
    options={'format':extension,'library':library_version(extension),'ocr_languages':os.getenv('USOPP_PI_OCR_LANGUAGES','eng+tam')}
    # Canonical source IDs are rebound only within the same project and same bytes.
    key=digest({'sha256':row['sha256'],'processor':'extract-v2','options':options})
    if _file_hash(path)!=row['sha256'] or path.stat().st_size!=row['size']:raise ValueError('The stored source file failed integrity verification. Restore it from the original.')
    def factory():
        value=extractor(file_id,pid,check)
        for s in value['sources']:
            s['fingerprint']=hashlib.sha256(json.dumps({k:v for k,v in s.items() if k not in {'id','file_id','filename'}},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return value
    value,hit=compute(pid,key,'extract-v2',factory,check)
    old=value['original_file_id']; value['original_file_id']=file_id
    for source in value['sources']:
        source['file_id']=file_id
        source['filename']=row['name']
        if source['id'].startswith(old+':'):source['id']=file_id+source['id'][len(old):]
    value['processing']={'cache_hit':hit,'source_sha256':row['sha256'],'processor':'extract-v2',
                         'incremental':'Unchanged file revisions reuse complete extraction; changed files retain stable chunk fingerprints for downstream reuse.'}
    return value


def _file_hash(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


@contextmanager
def workspace(job):
    """All child-owned temporary outputs stay outside the immutable blob store."""
    root=(hub.root/'processing-tmp').resolve();root.mkdir(parents=True,exist_ok=True)
    path=root/(job.row['id']+'-'+hashlib.sha256(job.lease.encode()).hexdigest()[:16]);path.mkdir(exist_ok=True)
    yield path
    # Supervisor performs cleanup after the child exits, including failed/killed jobs.


def clean_temporary(job=None):
    root=(hub.root/'processing-tmp').resolve()
    if not root.exists():return
    now=time.time()
    with hub.db() as db:
        active={r['id'] for r in db.execute("SELECT id FROM pi_jobs WHERE status='running' AND lease_until>?",(now,))}
    for path in root.iterdir():
        if not path.is_dir() or path.is_symlink() or path.resolve().parent!=root:continue
        key=path.name.split('-',1)[0]
        if key in active:continue
        try:
            if job and key==job.row['id'] or now-path.stat().st_mtime>86400:
                shutil.rmtree(path)  # Only disposable processing-tmp/<job>-<lease>.
        except FileNotFoundError:pass  # Another worker already cleaned the orphan.
        except OSError:
            from backend.core.runtime import log
            log.warning('WORKHUB_TEMP_CLEANUP_DEFERRED job=%s',key)
