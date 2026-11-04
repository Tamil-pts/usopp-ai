"""Additive schema and bounded operational telemetry, in the existing database."""
from collections import defaultdict, deque
import hashlib
import json
import shutil
import threading
import time
from backend.core.workhub import store as hub

LATENCIES = defaultdict(lambda: deque(maxlen=256))
LOCK = threading.Lock()


def migrate(db):
    columns = {r[1] for r in db.execute('PRAGMA table_info(pi_jobs)')}
    additions = {'fingerprint': "TEXT NOT NULL DEFAULT ''", 'input_snapshot': "TEXT NOT NULL DEFAULT '{}'",
                 'lane': "TEXT NOT NULL DEFAULT 'document'", 'started_at': 'REAL', 'finished_at': 'REAL',
                 'next_attempt': 'REAL NOT NULL DEFAULT 0', 'max_attempts': 'INTEGER NOT NULL DEFAULT 3',
                 'error_code': "TEXT NOT NULL DEFAULT ''", 'retryable': 'INTEGER NOT NULL DEFAULT 1',
                 'duration_ms': 'INTEGER NOT NULL DEFAULT 0', 'peak_memory_bytes': 'INTEGER NOT NULL DEFAULT 0'}
    for name, definition in additions.items():
        if name not in columns: db.execute('ALTER TABLE pi_jobs ADD COLUMN '+name+' '+definition)
    db.executescript('''
    CREATE INDEX IF NOT EXISTS pi_jobs_fingerprint ON pi_jobs(project_id,kind,fingerprint,status);
    CREATE INDEX IF NOT EXISTS pi_jobs_dispatch ON pi_jobs(status,next_attempt,created_at,id);
    CREATE INDEX IF NOT EXISTS pi_jobs_project_page ON pi_jobs(project_id,created_at DESC,id DESC);
    CREATE INDEX IF NOT EXISTS pi_jobs_project_pending ON pi_jobs(project_id,status);
    CREATE INDEX IF NOT EXISTS pi_revision_generated ON pi_revisions(generated_by,document_id);
    CREATE INDEX IF NOT EXISTS pi_clarification_status ON pi_clarifications(project_id,status,updated_at);
    CREATE INDEX IF NOT EXISTS wh_event_project_type ON events(project_id,event,id);
    CREATE INDEX IF NOT EXISTS wh_updates_project ON updates(project_id,created_at);
    CREATE INDEX IF NOT EXISTS wh_issues_project ON issues(project_id,status,created_at);
    CREATE INDEX IF NOT EXISTS wh_file_hash ON files(sha256,size);
    CREATE TABLE IF NOT EXISTS pi_cache(project_id TEXT NOT NULL,cache_key TEXT NOT NULL,processor TEXT NOT NULL,
      state TEXT NOT NULL,owner TEXT,expires REAL NOT NULL DEFAULT 0,output BLOB,sha256 TEXT,
      input_bytes INTEGER NOT NULL DEFAULT 0,output_bytes INTEGER NOT NULL DEFAULT 0,
      duration_ms INTEGER NOT NULL DEFAULT 0,hits INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,updated REAL NOT NULL,
      PRIMARY KEY(project_id,cache_key));
    CREATE INDEX IF NOT EXISTS pi_cache_state ON pi_cache(state,expires);
    CREATE TABLE IF NOT EXISTS pi_inference(id TEXT PRIMARY KEY,job_id TEXT,state TEXT NOT NULL,created REAL NOT NULL,
      started REAL,expires REAL NOT NULL,owner TEXT NOT NULL DEFAULT '');
    CREATE INDEX IF NOT EXISTS pi_inference_queue ON pi_inference(state,created,id);
    CREATE TABLE IF NOT EXISTS pi_worker_health(id TEXT PRIMARY KEY,heartbeat REAL NOT NULL,job_id TEXT,
      failures INTEGER NOT NULL DEFAULT 0,peak_memory_bytes INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS pi_job_outputs(job_id TEXT NOT NULL,slot TEXT NOT NULL,file_id TEXT NOT NULL,
      PRIMARY KEY(job_id,slot));
    CREATE TABLE IF NOT EXISTS pi_job_packages(job_id TEXT NOT NULL,slot TEXT NOT NULL,package_id TEXT NOT NULL,
      PRIMARY KEY(job_id,slot));
    ''')
    if 'owner' not in {r[1] for r in db.execute('PRAGMA table_info(pi_inference)')}:db.execute("ALTER TABLE pi_inference ADD COLUMN owner TEXT NOT NULL DEFAULT ''")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def snapshot(db, pid, kind, payload):
    """Revision identities, never confidential text. Exclude generated pack blobs."""
    value = {}
    if kind=='diagram_assist':
        p=hub.item(db,pid)
        # Queue input identities include the exact editable revision and FRD link.
        from . import store
        doc=store.document(db,payload.get('document_id'),pid)
        revision=store.revision(db,doc['current_revision'],doc['id'])
        linked=db.execute('SELECT current_revision FROM pi_documents WHERE id=?',(p.get('linked_document_id'),)).fetchone()
        source=db.execute('SELECT content FROM pi_revisions WHERE id=? AND document_id=?',(p.get('linked_revision_id'),p.get('linked_document_id'))).fetchone()
        return {'diagram':{'revision_id':revision['id'],'content_hash':digest(revision['content']),
                           'linked_document_id':p.get('linked_document_id'),'linked_revision_id':p.get('linked_revision_id'),
                           'source_current_revision':linked[0] if linked else None,'source_hash':digest(json.loads(source[0])) if source else None}}
    if kind in {'export','q_export'}:
        from .exports import _source
        return {'export':_source(db,pid,kind,payload)[2]}
    ids = payload.get('file_ids') or []
    if ids:
        value['files'] = [dict(db.execute('SELECT id,sha256,size FROM files WHERE id=? AND project_id=?', (key,pid)).fetchone()) for key in ids]
    if payload.get('meeting_id'):
        row = db.execute('SELECT id,file_id,transcript_version FROM pi_meetings WHERE id=? AND project_id=?', (payload['meeting_id'],pid)).fetchone()
        if row: value['meeting'] = dict(row)
    if kind in {'frd','flowchart','plan','document_answer','clarifications','q_generate','q_answer','q_frd_assist'}:
        rows = [dict(r) for r in db.execute("SELECT id,kind,current_revision,approved_revision FROM pi_documents WHERE project_id=? AND kind IN ('mom','source','frd') ORDER BY id LIMIT 501", (pid,))]
        if len(rows)>500:
            from fastapi import HTTPException
            raise HTTPException(413,'Narrow the project source scope before automatic generation (maximum 500 reference documents).')
        selected = payload.get('document_ids') or ([payload['document_id']] if payload.get('document_id') else [])
        if selected: rows = [r for r in rows if r['id'] in selected or payload.get('compare_frd') and r['kind']=='frd']
        controlled=bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_revisions'").fetchone())
        versions={r['id']:r['version'] for r in db.execute('SELECT r.id,r.version FROM qc_revisions r JOIN qc_documents d ON d.id=r.control_id WHERE d.project_id=?',(pid,))} if controlled else {}
        for r in rows:
            r['edit_version']=versions.get(r['current_revision'],0)
        value['documents'] = rows
        value['answers'] = [dict(r) for r in db.execute("SELECT id,answer,status,file_id FROM pi_clarifications WHERE project_id=? AND status='confirmed' ORDER BY id", (pid,))]
        if kind == 'q_generate':
            p=hub.item(db,pid)
            value['project_brief']={key:p.get(key) for key in ('title','description','kind')}
            generated = bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_generated_files'").fetchone())
            sql = 'SELECT id,sha256,size FROM files f WHERE project_id=?'
            if generated: sql += ' AND NOT EXISTS(SELECT 1 FROM qc_generated_files g WHERE g.file_id=f.id)'
            value['files'] = [dict(r) for r in db.execute(sql+' ORDER BY id', (pid,))]
    if kind in {'q_generate','q_answer','q_package','q_frd_assist'} and db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_revisions'").fetchone():
        dependencies={'frd':set(),'corrections':{'frd'},'test':{'frd','corrections'},'fat':{'frd','corrections','test'},
                      'quality':{'frd','corrections','test','fat'},'closure':{'frd','corrections','test','fat','quality'}}
        stages=dependencies.get(payload.get('stage'),set()) if kind=='q_generate' else None
        value['quality_revisions']=[dict(r) for r in db.execute('SELECT q.stage,r.id,r.version,r.content_hash,r.status FROM qc_documents q JOIN pi_documents d ON d.id=q.document_id JOIN qc_revisions r ON r.id=d.current_revision WHERE q.project_id=? ORDER BY q.stage',(pid,)) if stages is None or r['stage'] in stages]
        # These are the native records actually read by quality preparation.
        value['activity']={table:[dict(r) for r in db.execute(sql,(pid,))] for table,sql in (
            ('runs','SELECT run_id,status,completed_at,summary FROM engineering_runs WHERE project_id=? ORDER BY run_id'),
            ('issues','SELECT id,status,updated_at FROM issues WHERE project_id=? ORDER BY id'),
            ('executions','SELECT id,revision_id,outcome,recorded_at FROM qc_executions WHERE project_id=? ORDER BY id'))}
        if kind=='q_generate' and payload.get('stage')=='frd':value.pop('activity',None)
        elif kind=='q_generate' and payload.get('stage') in {'corrections','test','fat'}:value['activity'].pop('executions',None)
    if kind=='q_iso' and db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_packages'").fetchone():
        ids=payload.get('project_ids',[])
        sql="SELECT id,project_id,number,sha256 FROM qc_packages WHERE audience='internal'";params=[]
        if ids:sql+=' AND project_id IN ('+','.join('?' for _ in ids)+')';params.extend(ids)
        if payload.get('from'):sql+=' AND created_at>=?';params.append(payload['from'])
        if payload.get('to'):sql+=' AND substr(created_at,1,10)<=?';params.append(payload['to'])
        value['packages']=[dict(r) for r in db.execute(sql+' ORDER BY id LIMIT 501',params)]
    return value


def source_changed(db, row, output_document=None):
    expected = json.loads(row.get('input_snapshot') or '{}')
    if not expected: return False  # Historical jobs keep their existing behavior.
    payload = row['payload'] if isinstance(row['payload'],dict) else json.loads(row['payload'])
    actual = snapshot(db,row['project_id'],row['kind'],payload)
    # The job's own derived draft/transcript is an output, not a changed input.
    for values in (expected,actual):
        if row['kind'] in {'meeting','transcribe'}: values.pop('meeting',None)  # These jobs check transcript CAS themselves.
        if output_document and 'documents' in values: values['documents'] = [r for r in values['documents'] if r['id']!=output_document]
        if output_document and 'quality_revisions' in values:
            target=db.execute('SELECT stage FROM qc_documents WHERE document_id=?',(output_document,)).fetchone()
            if target:values['quality_revisions']=[r for r in values['quality_revisions'] if r['stage']!=target['stage']]
    return digest(expected)!=digest(actual)


def guard_generation(db, job_id, output_document=None):
    if not job_id: return
    row = db.execute('SELECT * FROM pi_jobs WHERE id=?', (job_id,)).fetchone()
    if row and source_changed(db,dict(row),output_document):
        raise SourceChanged('Source revisions changed during preparation. Start a new job using the current sources; the original revisions are retained.')


class SourceChanged(ValueError):
    pass


def record_latency(route, milliseconds, failed=False):
    # Route templates, not URLs, keep both cardinality and project identifiers bounded.
    if not route.startswith('/api/workhub') and route!='/api/health': return
    with LOCK:
        if route not in LATENCIES and len(LATENCIES)>=100: return
        LATENCIES[route].append((milliseconds,bool(failed)))


def health():
    from . import store
    from .resources import memory
    store.initialize(); now=time.time(); disk=shutil.disk_usage(hub.root)
    with hub.db() as db:
        queues=[dict(r) for r in db.execute('SELECT lane,status,COUNT(*) AS count FROM pi_jobs GROUP BY lane,status')]
        durations=[dict(r) for r in db.execute("SELECT kind,COUNT(*) AS samples,AVG(duration_ms) AS mean_ms,MAX(duration_ms) AS max_ms,MAX(peak_memory_bytes) AS peak_memory_bytes FROM (SELECT * FROM pi_jobs WHERE finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1000) GROUP BY kind")]
        workers=[{**dict(r),'healthy':now-r['heartbeat']<45} for r in db.execute('SELECT * FROM pi_worker_health ORDER BY heartbeat DESC LIMIT 20')]
        inference=[dict(r) for r in db.execute('SELECT state,COUNT(*) AS count FROM pi_inference WHERE expires>? GROUP BY state',(now,))]
        cache=dict(db.execute('SELECT COUNT(*) AS entries,COALESCE(SUM(hits),0) AS hits,COALESCE(SUM(output_bytes),0) AS bytes FROM pi_cache').fetchone())
    with LOCK:
        latency=[]
        for route,values in LATENCIES.items():
            ordered=sorted(v[0] for v in values)
            latency.append({'route':route,'samples':len(values),'p95_ms':round(ordered[min(len(ordered)-1,int(.95*len(ordered)))],2),'errors':sum(v[1] for v in values)})
    from backend.core import local_model_runtime
    from .resources import tree_rss
    owned_model=local_model_runtime.PROCESS
    model_memory=tree_rss(owned_model) if owned_model and owned_model.poll() is None else None
    return {'queues':queues,'processing':durations,'workers':workers,'inference':inference,'memory':memory(),
            'ai_memory':{'owned_model_rss_bytes':model_memory,'scope':'Owned local model process; remote model service memory is managed by its Docker limit.'},
            'disk':{'free_bytes':disk.free,'total_bytes':disk.total},'cache':cache,'api_latency':latency,
            'latency_scope':'Bounded samples in this API process since startup; processing metrics are persistent.'}
