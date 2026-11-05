"""Owner-scoped, durable MatchView report preparation."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from backend.core.report_cover import ReportCover
from backend.core.run_history import current_user, write_json
from backend.core.runtime import EXPORTS, log

router = APIRouter(tags=['Project Comparison'])
ROOT = EXPORTS / 'compare'
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='matchview-report')
ACTIVE: dict[str, dict] = {}
MEDIA = {'html':'text/html', 'pdf':'application/pdf', 'docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'json':'application/json'}


class ExportRequest(BaseModel):
    cover: ReportCover
    formats: list[Literal['html','pdf','docx','json']] = Field(default_factory=lambda:['html','pdf'], min_length=1, max_length=4)
    skipLayoutProperties: bool = False
    categories: list[Literal['logic','screen','config','hardware']] = Field(default_factory=lambda:['logic','screen','config','hardware'], max_length=4)
    statuses: list[Literal['modified','added','removed','unchanged']] = Field(default_factory=lambda:['modified','added','removed'], min_length=1, max_length=4)
    includeKnowledge: bool = True
    screenControlNames: bool = True
    screenLayerViews: list[Literal['visible','all']] = Field(default_factory=lambda:['visible','all'],min_length=1,max_length=2)


def owner():
    user = current_user.get() or {}
    identity = user.get('id') or user.get('username')
    if not identity:
        raise HTTPException(401, 'Sign in to prepare reports.')
    return str(identity)


def manifest_path(job_id):
    if not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise HTTPException(404, 'Report not found.')
    return ROOT / job_id / 'manifest.json'


def load_job(job_id, identity):
    with LOCK:
        job = ACTIVE.get(job_id)
        if job is None:
            try:
                job = json.loads(manifest_path(job_id).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                raise HTTPException(404, 'Report not found.')
            if job.get('status') in {'queued','running'}:
                job['status'] = 'interrupted'
                job['stage'] = 'Report preparation was interrupted by a server restart. Prepare another report.'
                for item in job['reports'].values():
                    if item['status'] != 'ready':
                        item.update(status='error', error='Preparation interrupted. Please retry.')
        if job.get('owner') != identity and (current_user.get() or {}).get('role') != 'admin':
            raise HTTPException(404, 'Report not found.')
        return job


def public_job(job):
    with LOCK:
        elapsed = time.time() - job['started'] if job.get('status') in {'queued','running'} else job.get('elapsedSeconds', 0)
        reports = {fmt:{k:v for k,v in item.items() if k != 'path'} for fmt,item in job['reports'].items()}
        return {k:v for k,v in job.items() if k not in {'owner','started','fingerprint','reports'}} | {'reports':reports, 'elapsedSeconds':round(elapsed,1)}


def persist(job):
    write_json(manifest_path(job['id']), job)


def prepare(job_id):
    from backend.api.comparison import _export_comparison
    from backend.core.compare_screen_preview import preview_progress
    def stage(message):
        with LOCK:
            ACTIVE[job_id]['stage'] = message
    token = preview_progress.set(stage)
    try:
        with LOCK:
            job = ACTIVE[job_id]
            job.update(status='running', stage='Preparing comparison reports')
            persist(job)
        for fmt in job['formats']:
            with LOCK:
                job['stage'] = f'Preparing {fmt.upper()} report'
                job['reports'][fmt]['status'] = 'running'
                persist(job)
            started = time.time()
            try:
                response = _export_comparison(job['sessionId'], fmt, job['cover'], skip_layout_properties=job['skipLayoutProperties'], selection={key:job[key] for key in ('categories','statuses','includeKnowledge','screenControlNames','screenLayerViews')})
                artifact = Path(response.path).resolve()
                relative = artifact.relative_to(ROOT.resolve())
                with LOCK:
                    job['reports'][fmt].update(status='ready', path=relative.as_posix(), filename=artifact.name,
                        downloadUrl=f'/api/local/compare/reports/download/{job_id}/{fmt}', elapsedSeconds=round(time.time()-started,2))
            except Exception as error:
                log.exception('COMPARE_BACKGROUND_EXPORT_ERROR job=%s format=%s',job_id,fmt)
                message = str(error.detail) if isinstance(error,HTTPException) else str(error)
                with LOCK:
                    job['reports'][fmt].update(status='error', error=message)
            with LOCK:
                persist(job)
        with LOCK:
            failed = sum(item['status']=='error' for item in job['reports'].values())
            job.update(status='complete' if not failed else 'partial' if failed<len(job['formats']) else 'error',
                stage='Reports ready' if not failed else 'Some reports could not be prepared', elapsedSeconds=round(time.time()-job['started'],2))
            persist(job)
    finally:
        preview_progress.reset(token)
        with LOCK:
            ACTIVE.pop(job_id,None)


@router.post('/api/local/compare/reports/start/{sid}')
@router.post('/api/local/compare/export/start/{sid}', include_in_schema=False)
def start_export(sid:str, request:ExportRequest):
    from backend.api.comparison import _comparison_result_for_export
    if not re.fullmatch(r'[A-Za-z0-9_-]+',sid):
        raise HTTPException(400, 'Invalid comparison session.')
    identity = owner()
    options = request.model_dump(mode='json')
    options['formats'] = sorted(set(options['formats']))
    from python_engine.ladder_model import RENDER_VERSION
    fingerprint = hashlib.sha256(json.dumps({'schema':11, 'ladderRenderVersion':RENDER_VERSION, 'owner':identity, 'sessionId':sid, **options},sort_keys=True).encode()).hexdigest()
    ROOT.mkdir(parents=True,exist_ok=True)
    with LOCK:
        for path in ROOT.glob('*/manifest.json'):
            try:
                saved = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError,OSError):
                continue
            if saved.get('fingerprint') != fingerprint:
                continue
            job = load_job(saved['id'],identity)
            if job['status'] in {'queued','running'} or (job['status']=='complete' and all((ROOT/item['path']).is_file() for item in job['reports'].values())):
                return public_job(job)
        if sum(j['owner']==identity for j in ACTIVE.values()) >= 2:
            raise HTTPException(429, 'Two reports are already preparing. Download them or wait before starting another.')
        _comparison_result_for_export(sid)
        job_id = uuid4().hex
        job = {'id':job_id, 'owner':identity, 'fingerprint':fingerprint, 'sessionId':sid, **options,
            'status':'queued', 'stage':'Waiting to prepare reports', 'started':time.time(), 'createdAt':datetime.now(timezone.utc).isoformat(),
            'reports':{fmt:{'status':'queued'} for fmt in options['formats']}}
        ACTIVE[job_id] = job
        persist(job)
        try:
            POOL.submit(copy_context().run, prepare, job_id)
        except Exception:
            ACTIVE.pop(job_id,None)
            job.update(status='error',stage='Could not start report preparation')
            persist(job)
            raise
        return public_job(job)


@router.get('/api/local/compare/reports/status/{job_id}')
@router.get('/api/local/compare/export/status/{job_id}', include_in_schema=False)
def export_status(job_id:str):
    return public_job(load_job(job_id,owner()))


@router.get('/api/local/compare/reports/download/{job_id}/{fmt}')
@router.get('/api/local/compare/export/download/{job_id}/{fmt}', include_in_schema=False)
def download_export(job_id:str,fmt:str):
    job = load_job(job_id,owner())
    item = job['reports'].get(fmt)
    if not item or item['status']!='ready':
        raise HTTPException(409, 'This report is not ready yet.')
    path = (ROOT/item['path']).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise HTTPException(404, 'The prepared report was removed. Prepare another report.')
    return FileResponse(path,filename=item['filename'],media_type=MEDIA[fmt])
