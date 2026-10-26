"""Durable SQLite queue with bounded, isolated job execution."""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from fastapi import HTTPException
from backend.core.workhub import store as hub,identity,timestamp,encode
from . import store,reliability
from .resources import setting,admission,kill_owned_tree,tree_rss

STOP=threading.Event();THREAD=None;GUARD=threading.Lock()
LEASE_SECONDS=90
KINDS={'meeting','transcribe','frd','flowchart','plan','extract','ocr','pdf','convert','document_answer','clarifications','q_generate','q_package','q_iso','q_answer','q_frd_assist','export','q_export'}
WORKER_ID=socket.gethostname()+':'+str(os.getpid())+':'+uuid.uuid4().hex


def lane(kind):return 'speech' if kind in {'meeting','transcribe'} else 'pdf' if kind in {'pdf','ocr','convert','q_package','q_iso','export','q_export'} else 'document'


def enqueue(user,project_id,kind,payload):
    store.initialize()
    if kind in {'export','q_export'}:
        from backend.core.workhub_quality.store import initialize
        initialize()
    if kind not in KINDS:raise HTTPException(400,'Choose a supported Project Intelligence operation.')
    if not isinstance(payload,dict):raise HTTPException(400,'Provide structured processing options.')
    store._bounded(payload);raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    reason=admission(lane(kind))
    if reason:raise HTTPException(503,reason+'. Original documents remain available.',headers={'Retry-After':'15'})
    with hub.db(True) as db:
        item=store.project(db,project_id,user,write=kind not in {'export','q_export'})
        if payload.get('meeting_id'):store.meeting(db,payload['meeting_id'],project_id)
        if kind=='meeting' and payload.get('phase')!='transcribe':
            from .reliability import digest
            meeting=store.meeting(db,payload.get('meeting_id'),project_id)
            review=db.execute('SELECT transcript_hash FROM pi_transcript_reviews WHERE meeting_id=? AND version=?',(meeting['id'],meeting['transcript_version'])).fetchone()
            if not review or review['transcript_hash']!=digest(json.loads(meeting['transcript'])):
                raise HTTPException(409,'Transcribe/import the meeting, then review and confirm its current transcript before generating the MOM.')
        if payload.get('document_id'):store.document(db,payload['document_id'],project_id)
        if payload.get('revision_id') and kind!='q_export':
            row=db.execute('SELECT r.document_id FROM pi_revisions r JOIN pi_documents d ON d.id=r.document_id WHERE r.id=? AND d.project_id=?',(payload['revision_id'],project_id)).fetchone()
            if not row or payload.get('document_id')!=row['document_id']:raise HTTPException(400,'Select a revision of the specified project document.')
        for field,limit in (('document_ids',100),('file_ids',20),('project_ids',100)):
            if field not in payload:continue
            ids=payload[field]
            if not isinstance(ids,list) or len(ids)>limit or any(not isinstance(key,str) for key in ids):raise HTTPException(400,'Choose a bounded list of project references.')
            for key in ids:
                if field=='document_ids':store.document(db,key,project_id)
                elif field=='file_ids':
                    if not db.execute('SELECT 1 FROM files WHERE id=? AND project_id=?',(key,project_id)).fetchone():raise HTTPException(404,'Choose a file in this project.')
                else:store.project(db,key,user)
        if kind=='q_iso' and user.get('role')!='admin':raise HTTPException(403,'ISO audit preparation requires an administrator.')
        if kind in {'export','q_export'}:
            from .exports import source
            source(db,project_id,kind,payload,user)
        inputs=reliability.snapshot(db,project_id,kind,payload);fingerprint=reliability.digest({'kind':kind,'payload':payload,'inputs':inputs})
        previous=db.execute("SELECT id,status FROM pi_jobs WHERE project_id=? AND kind=? AND fingerprint=? AND status IN ('queued','running','completed') ORDER BY created_at DESC LIMIT 1",(project_id,kind,fingerprint)).fetchone()
        if previous:return dict(previous)
        # A generated document changes its own current revision. That output must
        # not turn a repeated HTTP submission into a second draft/number.
        for previous in db.execute("SELECT * FROM pi_jobs WHERE project_id=? AND kind=? AND payload=? AND status='completed' ORDER BY created_at DESC LIMIT 10",(project_id,kind,raw)):
            output=_output_document(db,dict(previous))
            if output and not reliability.source_changed(db,dict(previous),output):return {'id':previous['id'],'status':'completed'}
        pending=db.execute("SELECT COUNT(*) FROM pi_jobs WHERE status IN ('queued','running')").fetchone()[0]
        count=db.execute("SELECT COUNT(*) FROM pi_jobs WHERE project_id=? AND status IN ('queued','running')",(project_id,)).fetchone()[0]
        if pending>=setting('MAX_PENDING',100) or count>=setting('MAX_PROJECT_PENDING',20):raise HTTPException(429,'Document processing is busy. Retry after existing jobs finish.',headers={'Retry-After':'15'})
        key=identity();now=timestamp()
        db.execute('INSERT INTO pi_jobs(id,project_id,kind,payload,created_by,created_at,updated_at,fingerprint,input_snapshot,lane,max_attempts) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (key,project_id,kind,raw,user['id'],now,now,fingerprint,encode(inputs),lane(kind),setting('JOB_MAX_ATTEMPTS',3,1,10)))
        hub.event(db,item,user,'intelligence_job_queued',{'job_id':key,'kind':kind})
    try:
        client=redis_client()
        if client:client.lpush('usopp:project-intelligence:wakeup',key);client.ltrim('usopp:project-intelligence:wakeup',0,1000)
    except Exception:pass
    start();return {'id':key,'status':'queued'}


def redis_client():
    url=os.getenv('USOPP_PI_REDIS_URL','')
    if not url:return None
    from .local_ai import local_url
    local_url(url,schemes={'redis','rediss'})
    import redis
    return redis.Redis.from_url(url,socket_connect_timeout=2,socket_timeout=3)


def _can_control(db,row,user):
    try:
        store.project(db,row['project_id'],user,write=row['kind'] not in {'export','q_export'})
        if row['created_by']!=user['id']:store.project(db,row['project_id'],user,manage=True)
        return True
    except HTTPException:return False


def _output_document(db,row):
    result=row['result'] if isinstance(row.get('result'),dict) else json.loads(row.get('result') or '{}')
    if row['kind']=='q_generate' and result.get('control_id'):
        control=db.execute('SELECT document_id FROM qc_documents WHERE id=? AND project_id=?',(result['control_id'],row['project_id'])).fetchone()
        return control['document_id'] if control else None
    if row['kind'] in {'meeting','frd','flowchart','plan','extract','ocr','pdf','convert','q_generate'}:
        committed=db.execute('SELECT d.id FROM pi_revisions r JOIN pi_documents d ON d.id=r.document_id WHERE r.generated_by=? AND d.project_id=? LIMIT 1',(row['id'],row['project_id'])).fetchone()
        return committed['id'] if committed else result.get('document_id')
    return None


def public(db,row,user,allowed=None,contributor=None):
    value=dict(row);value.pop('payload',None);value.pop('input_snapshot',None);value.pop('lease_owner',None)
    value['result']=json.loads(value['result']) if isinstance(value.get('result'),str) else value.get('result',{})
    if allowed is None:allowed=_can_control(db,row,user)
    if contributor is None:
        try:store.project(db,row['project_id'],user,write=True);contributor=True
        except HTTPException:contributor=False
    exhausted=row['attempts']>=row['max_attempts']
    value['can_retry']=bool((allowed if row['kind'] in {'export','q_export'} else contributor) and row['status'] in {'failed','cancelled','blocked'} and row['retryable'] and not exhausted)
    value['can_cancel']=bool(allowed and row['status'] in {'queued','running'} and not row['cancel_requested'])
    value['retry_reason']='Attempt limit reached. Review the failure and start a new preparation.' if exhausted else '' if row['retryable'] else 'Sources or processing options need correction. Start a new preparation.'
    value['display_status']='Processing' if row['status'] in {'queued','running'} else 'Failed' if row['status']=='blocked' else row['status'].capitalize()
    return value


def list_jobs(user,pid,limit=50,cursor=None,kinds=None):
    store.initialize();limit=min(100,max(1,int(limit)))
    with hub.db() as db:
        store.project(db,pid,user)
        query='SELECT * FROM pi_jobs WHERE project_id=?';params=[pid]
        if kinds=='quality':query+=" AND kind LIKE 'q_%'"
        if cursor:
            row=db.execute('SELECT created_at,id FROM pi_jobs WHERE id=? AND project_id=?',(cursor,pid)).fetchone()
            if not row:raise HTTPException(400,'The jobs cursor is not in this project.')
            query+=' AND (created_at,id)<(?,?)';params.extend(row)
        rows=db.execute(query+' ORDER BY created_at DESC,id DESC LIMIT ?',(*params,limit+1)).fetchall()
        # Resolve project control once, rather than re-reading assignments per row.
        contributor=False;manager=user.get('role')=='admin'
        try:store.project(db,pid,user,write=True);contributor=True
        except HTTPException:pass
        try:store.project(db,pid,user,manage=True);manager=True
        except HTTPException:pass
        result=[public(db,r,user,(contributor or r['kind'] in {'export','q_export'}) and (manager or r['created_by']==user['id']),contributor) for r in rows[:limit]]
    return {'jobs':result,'next_cursor':rows[limit-1]['id'] if len(rows)>limit else None}


def get_job(user,pid,key):
    store.initialize()
    with hub.db() as db:
        store.project(db,pid,user);row=db.execute('SELECT * FROM pi_jobs WHERE id=? AND project_id=?',(key,pid)).fetchone()
        if not row:raise HTTPException(404,'Choose a job in this project.')
        value=public(db,row,user)
        if row['status']=='completed':value['source_changed']=reliability.source_changed(db,dict(row),_output_document(db,dict(row)))
        return value


def cancel(user,project_id,key):
    store.initialize()
    with hub.db(True) as db:
        store.project(db,project_id,user);row=db.execute('SELECT * FROM pi_jobs WHERE id=? AND project_id=?',(key,project_id)).fetchone()
        if not row:raise HTTPException(404,'Choose a job in this project.')
        if not _can_control(db,row,user):raise HTTPException(403,'Only the submitter or project manager can cancel this job.')
        if row['status'] in {'queued','running'}:
            db.execute("UPDATE pi_jobs SET cancel_requested=1,stage=CASE WHEN status='queued' THEN 'Cancelled' ELSE stage END,finished_at=CASE WHEN status='queued' THEN ? ELSE finished_at END,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END,updated_at=? WHERE id=?",(time.time(),timestamp(),key))
            return {'id':key,'status':'cancelling' if row['status']=='running' else 'cancelled'}
        return {'id':key,'status':row['status']}


def retry(user,project_id,key):
    store.initialize()
    with hub.db(True) as db:
        store.project(db,project_id,user);row=db.execute('SELECT * FROM pi_jobs WHERE id=? AND project_id=?',(key,project_id)).fetchone()
        if not row:raise HTTPException(404,'Choose a job in this project.')
        if not public(db,row,user)['can_retry']:raise HTTPException(409,'This job cannot be retried. Review its status or prepare a new job after correcting the inputs.')
        if reliability.source_changed(db,dict(row),_output_document(db,dict(row))) and row['kind'] not in {'meeting','transcribe'}:raise HTTPException(409,'Source revisions changed. Start a new preparation with current sources.')
        if db.execute("SELECT COUNT(*) FROM pi_jobs WHERE status IN ('queued','running')").fetchone()[0]>=setting('MAX_PENDING',100):raise HTTPException(429,'The processing queue is full.',headers={'Retry-After':'15'})
        db.execute("UPDATE pi_jobs SET status='queued',cancel_requested=0,error='',error_code='',stage='Queued again',lease_owner=NULL,lease_until=0,next_attempt=0,finished_at=NULL,created_by=?,updated_at=? WHERE id=?",(user['id'],timestamp(),key))
        hub.event(db,hub.item(db,project_id),user,'intelligence_job_retried',{'job_id':key,'attempts':row['attempts'],'original_submitter':row['created_by']})
    start();return {'id':key,'status':'queued'}


class Job:
    def __init__(self,row,lease):
        self.row=dict(row);self.lease=lease;self._next_access_check=0
        if isinstance(self.row['payload'],str):self.row['payload']=json.loads(self.row['payload'])
    def check(self):
        with hub.db() as db:row=db.execute('SELECT cancel_requested,lease_owner,status,lease_until FROM pi_jobs WHERE id=?',(self.row['id'],)).fetchone()
        if not row or row['cancel_requested'] or row['lease_owner']!=self.lease or row['status']!='running' or row['lease_until']<time.time():raise InterruptedError('Processing cancelled or worker lease expired.')
        if time.monotonic()>=self._next_access_check:
            from backend.core import accounts
            user=next((u for u in accounts.store.list_users() if u['id']==self.row['created_by'] and u.get('active') and u.get('approved') and not u.get('isDemo')),None)
            if not user:raise PermissionError('The submitting account is no longer enabled.')
            if self.row['kind']=='q_iso' and user.get('role')!='admin':raise PermissionError('ISO preparation requires current administrator authorization.')
            with hub.db() as db:store.project(db,self.row['project_id'],user,write=self.row['kind'] not in {'export','q_export'})
            self._next_access_check=time.monotonic()+2
    def progress(self,percent,stage):
        self.check()
        with hub.db(True) as db:db.execute('UPDATE pi_jobs SET progress=MAX(progress,?),stage=?,updated_at=? WHERE id=? AND lease_owner=?',
                                         (min(99,max(0,int(percent))),str(stage)[:200],timestamp(),self.row['id'],self.lease))


def claim(kinds=None):
    store.initialize();lease=socket.gethostname()+':'+str(os.getpid())+':'+uuid.uuid4().hex;now=time.time()
    reason=admission()
    if reason:
        with hub.db(True) as db:db.execute("UPDATE pi_jobs SET stage=?,updated_at=? WHERE status='queued' AND stage<>?",(reason,timestamp(),reason))
        return None
    with hub.db(True) as db:
        db.execute("UPDATE pi_jobs SET status='cancelled',finished_at=?,stage='Cancelled',lease_until=0 WHERE status='running' AND lease_until<? AND cancel_requested=1",(now,now))
        db.execute("UPDATE pi_jobs SET status='failed',retryable=0,error_code='attempt_limit',error='The worker recovery limit was reached. Review worker health before preparing again.',finished_at=?,stage='Failed',lease_until=0 WHERE status IN ('queued','running') AND attempts>=max_attempts AND lease_until<?",(now,now))
        active=db.execute("SELECT COUNT(*) FROM pi_jobs WHERE status='running' AND lease_until>?",(now,)).fetchone()[0]
        if active>=setting('WORKER_CONCURRENCY',1,1,8):return None
        query="SELECT * FROM pi_jobs WHERE cancel_requested=0 AND attempts<max_attempts AND next_attempt<=? AND (status='queued' OR (status='running' AND lease_until<?))";params=[now,now]
        if kinds:query+=' AND kind IN ('+','.join('?' for _ in kinds)+')';params.extend(sorted(kinds))
        rows=db.execute(query+' ORDER BY created_at,id LIMIT 20',params).fetchall()
        for row in rows:
            this_lane=lane(row['kind']);active_lane=db.execute("SELECT COUNT(*) FROM pi_jobs WHERE lane=? AND status='running' AND lease_until>?",(this_lane,now)).fetchone()[0]
            if active_lane>=setting(this_lane.upper()+'_CONCURRENCY',1,1,8):continue
            db.execute("UPDATE pi_jobs SET status='running',attempts=attempts+1,lease_owner=?,lease_until=?,started_at=?,finished_at=NULL,updated_at=?,stage='Starting local processing',lane=? WHERE id=?",(lease,now+LEASE_SECONDS,now,timestamp(),this_lane,row['id']))
            return Job(db.execute('SELECT * FROM pi_jobs WHERE id=?',(row['id'],)).fetchone(),lease)
    return None


def finish(job,status,result=None,error='',code='',retryable=True,peak=0):
    now=time.time();elapsed=max(0,int((now-(job.row.get('started_at') or now))*1000))
    with hub.db(True) as db:
        row=db.execute("SELECT cancel_requested FROM pi_jobs WHERE id=? AND lease_owner=? AND status='running'",(job.row['id'],job.lease)).fetchone()
        if not row:return
        if row['cancel_requested'] and status=='completed':status='cancelled'
        db.execute("UPDATE pi_jobs SET status=?,progress=CASE WHEN ?='completed' THEN 100 ELSE progress END,stage=?,error=?,error_code=?,retryable=?,result=?,lease_until=0,finished_at=?,duration_ms=duration_ms+?,peak_memory_bytes=MAX(peak_memory_bytes,?),updated_at=? WHERE id=? AND lease_owner=?",
                   (status,status,'Completed' if status=='completed' else 'Waiting for local service' if status=='blocked' else status.capitalize(),str(error)[:1200],code,int(retryable),encode(result or {}),now,elapsed,peak,timestamp(),job.row['id'],job.lease))


def execute(job,stop=None):
    from .cache import workspace,clean_temporary
    from backend.core.runtime import RESOURCE_ROOT
    stop=stop or STOP;process=None;peak=0;start_time=time.monotonic();last_heartbeat=0
    deadline=setting('SPEECH_TIMEOUT' if job.row['kind'] in {'meeting','transcribe'} else 'JOB_TIMEOUT',3600 if job.row['kind'] in {'meeting','transcribe'} else 1800,1,86400)
    try:
        with workspace(job) as folder:
            env={**os.environ,'USOPP_DATA_ROOT':str(hub.root.parent),'USOPP_PI_CHILD':'1','USOPP_PI_WORKER_MODE':'external',
                 'TMPDIR':str(folder),'TMP':str(folder),'TEMP':str(folder),'OMP_NUM_THREADS':str(setting('NATIVE_THREADS',2,1,32)),
                 'OPENBLAS_NUM_THREADS':str(setting('NATIVE_THREADS',2,1,32))}
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
            command=[sys.executable,'--workhub-job',job.row['id'],job.lease] if getattr(sys,'frozen',False) else [sys.executable,'-m','backend.core.workhub_intelligence.job_runner',job.row['id'],job.lease]
            process=subprocess.Popen(command,
                                     cwd=str(RESOURCE_ROOT),env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
            while process.poll() is None:
                if stop.is_set():
                    kill_owned_tree(process)
                    with hub.db(True) as db:db.execute("UPDATE pi_jobs SET status='queued',stage='Recovering after worker restart',lease_until=0,next_attempt=?,updated_at=? WHERE id=? AND lease_owner=? AND status='running'",(time.time()+2,timestamp(),job.row['id'],job.lease))
                    return
                job.check()
                if time.monotonic()-start_time>deadline:raise TimeoutError('Processing exceeded its time limit. Completed checkpoints can be reused on retry.')
                peak=max(peak,tree_rss(process))
                if peak>setting('JOB_MAX_MEMORY_MB',2048)*1024*1024:raise MemoryError('Processing reached its memory budget. Reduce the document or audit scope before preparing again.')
                import shutil
                if shutil.disk_usage(hub.root).free<setting('DISK_RESERVE_MB',512,0)*1024*1024:raise OSError('Processing paused because disk capacity reached its reserve. Free space before retrying.')
                if time.monotonic()-last_heartbeat>=10:
                    with hub.db(True) as db:
                        db.execute("UPDATE pi_jobs SET lease_until=?,peak_memory_bytes=MAX(peak_memory_bytes,?) WHERE id=? AND lease_owner=? AND status='running'",(time.time()+LEASE_SECONDS,peak,job.row['id'],job.lease))
                        db.execute('UPDATE pi_worker_health SET heartbeat=?,job_id=?,peak_memory_bytes=MAX(peak_memory_bytes,?) WHERE id=?',(time.time(),job.row['id'],peak,WORKER_ID))
                    last_heartbeat=time.monotonic()
                stop.wait(.25)
            with hub.db() as db:row=db.execute('SELECT status FROM pi_jobs WHERE id=?',(job.row['id'],)).fetchone()
            if row and row['status']=='running':
                if job.row['attempts']<job.row['max_attempts']:
                    with hub.db(True) as db:db.execute("UPDATE pi_jobs SET status='queued',error_code='worker_exit',stage='Recovering interrupted processing',lease_until=0,next_attempt=?,updated_at=? WHERE id=? AND lease_owner=?",(time.time()+min(60,2**job.row['attempts']),timestamp(),job.row['id'],job.lease))
                else:finish(job,'failed',error='The worker exited before committing a result. Review worker health.',code='worker_exit',retryable=False,peak=peak)
    except InterruptedError as error:
        if process:kill_owned_tree(process)
        finish(job,'cancelled',error=str(error),code='cancelled',peak=peak)
    except Exception as error:
        if process:kill_owned_tree(process)
        finish(job,'failed',error=str(error),code='timeout' if isinstance(error,TimeoutError) else 'memory_limit' if isinstance(error,MemoryError) else 'worker_error',retryable=not isinstance(error,MemoryError),peak=peak)
    finally:
        if process and process.poll() is None:kill_owned_tree(process)
        with hub.db(True) as db:
            db.execute('UPDATE pi_inference SET expires=MIN(expires,?) WHERE job_id=? AND owner=?',(time.time()+30,job.row['id'],job.lease))
            row=db.execute('SELECT error_code FROM pi_jobs WHERE id=?',(job.row['id'],)).fetchone()
            db.execute('UPDATE pi_worker_health SET failures=failures+?,peak_memory_bytes=MAX(peak_memory_bytes,?) WHERE id=?',(int(bool(row and row['error_code'] in {'worker_exit','worker_error','timeout','memory_limit'})),peak,WORKER_ID))
        clean_temporary(job)


def run(stop=None,kinds=None):
    stop=stop or STOP;store.initialize()
    from .cache import clean_temporary
    clean_temporary();last_cleanup=time.monotonic()
    while not stop.is_set():
        try:
            with hub.db(True) as db:db.execute('INSERT INTO pi_worker_health(id,heartbeat) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat,job_id=NULL',(WORKER_ID,time.time()))
            job=claim(kinds)
            if job:execute(job,stop);continue
            if time.monotonic()-last_cleanup>3600:clean_temporary();last_cleanup=time.monotonic()
        except Exception:
            from backend.core.runtime import log
            log.exception('PROJECT_INTELLIGENCE_WORKER_ERROR')
            with hub.db(True) as db:db.execute('UPDATE pi_worker_health SET failures=failures+1 WHERE id=?',(WORKER_ID,))
        try:
            client=redis_client()
            if client:client.brpop('usopp:project-intelligence:wakeup',timeout=2)
            else:stop.wait(1)
        except Exception:stop.wait(2)


def start():
    global THREAD
    if os.getenv('USOPP_PI_WORKER_MODE','embedded').lower()!='embedded':return
    with GUARD:
        if THREAD and THREAD.is_alive():return
        STOP.clear();THREAD=threading.Thread(target=run,name='project-intelligence-worker',daemon=True);THREAD.start()


def shutdown():
    STOP.set()
    if THREAD and THREAD is not threading.current_thread():THREAD.join(timeout=8)
