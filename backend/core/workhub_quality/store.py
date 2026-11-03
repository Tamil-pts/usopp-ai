"""Additive controls around existing Project Intelligence documents and WorkHub files."""
import hashlib
import json
import re
import threading
from datetime import datetime,timezone
from fastapi import HTTPException
from backend.core.workhub import store as hub,identity,timestamp,text,encode
from backend.core.workhub_growth.store import personal
from backend.core.workhub_intelligence import store as pi

STAGES={'frd':'FRD','corrections':'Correction Notes','test':'Test Report','fat':'FAT','quality':'Quality Approval','closure':'Project Closure'}
STATUSES={'draft','in_review','correction_required','approved','released','superseded','rejected','archived'}
LOCK=threading.RLock();READY=set()

def bounded(value,limit=8*1024*1024):
    try:raw=json.dumps(value,ensure_ascii=False,allow_nan=False)
    except (ValueError,TypeError):raise HTTPException(400,'Provide valid structured content with finite numbers.') from None
    if len(raw.encode())>limit:raise HTTPException(413,'Split this document into smaller controlled documents.')
    return raw
def digest(value):return hashlib.sha256(bounded(value).encode()).hexdigest()
def initialize():
    pi.initialize();key=str(hub.root.resolve())
    if key in READY:return
    with LOCK:
        if key in READY:return
        with hub.db(True) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS qc_settings(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,configuration TEXT NOT NULL,updated_by INTEGER,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS qc_sequences(scope TEXT PRIMARY KEY,last_value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS qc_projects(project_id TEXT PRIMARY KEY,policy TEXT NOT NULL,policy_version INTEGER NOT NULL,project_type TEXT NOT NULL,
              context TEXT NOT NULL DEFAULT '{}',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS qc_documents(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,stage TEXT NOT NULL,document_id TEXT NOT NULL UNIQUE,
              number TEXT NOT NULL UNIQUE,numbering_version INTEGER NOT NULL,numbering_snapshot TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(project_id,stage));
            CREATE TABLE IF NOT EXISTS qc_revisions(id TEXT PRIMARY KEY,control_id TEXT NOT NULL,number INTEGER NOT NULL,label TEXT NOT NULL,
              status TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,reason TEXT NOT NULL,owner_id INTEGER NOT NULL,
              template_version TEXT NOT NULL,template_snapshot TEXT NOT NULL,frd_revision_id TEXT,content_hash TEXT NOT NULL,
              confirmed_by INTEGER,confirmed_at TEXT,confirmed_hash TEXT,reviewer_id INTEGER,approver_id INTEGER,reviewed_by INTEGER,reviewed_at TEXT,
              approved_by INTEGER,approved_at TEXT,released_by INTEGER,released_at TEXT,customer_safe INTEGER NOT NULL DEFAULT 0,
              customer_authorized_by INTEGER,customer_authorized_at TEXT,baseline TEXT,created_at TEXT NOT NULL,
              UNIQUE(control_id,number));
            CREATE INDEX IF NOT EXISTS qc_revision_control ON qc_revisions(control_id,number);
            CREATE TABLE IF NOT EXISTS qc_draft_history(id TEXT PRIMARY KEY,revision_id TEXT NOT NULL,version INTEGER NOT NULL,
              content TEXT NOT NULL,content_hash TEXT NOT NULL,actor_id INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(revision_id,version));
            CREATE TABLE IF NOT EXISTS qc_executions(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,revision_id TEXT NOT NULL,case_id TEXT NOT NULL,
              specification_hash TEXT NOT NULL,outcome TEXT NOT NULL,actual TEXT NOT NULL,observations TEXT NOT NULL,
              file_ids TEXT NOT NULL,executed_by INTEGER NOT NULL,executed_at TEXT NOT NULL,recorded_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS qc_case_execution ON qc_executions(revision_id,case_id,recorded_at);
            CREATE TABLE IF NOT EXISTS qc_execution_reuse(revision_id TEXT NOT NULL,case_id TEXT NOT NULL,execution_id TEXT NOT NULL,PRIMARY KEY(revision_id,case_id));
            CREATE TABLE IF NOT EXISTS qc_customer_files(revision_id TEXT NOT NULL,file_id TEXT NOT NULL,authorized_by INTEGER NOT NULL,authorized_at TEXT NOT NULL,PRIMARY KEY(revision_id,file_id));
            CREATE TABLE IF NOT EXISTS qc_generated_files(file_id TEXT PRIMARY KEY,purpose TEXT NOT NULL,job_id TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS qc_acceptances(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,revision_id TEXT NOT NULL,status TEXT NOT NULL,
              customer TEXT NOT NULL,representative TEXT NOT NULL,accepted_at TEXT NOT NULL,file_ids TEXT NOT NULL,remarks TEXT NOT NULL,
              recorded_by INTEGER NOT NULL,recorded_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS qc_waivers(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,code TEXT NOT NULL,basis TEXT NOT NULL,
              reason TEXT NOT NULL,disposition TEXT NOT NULL,status TEXT NOT NULL,requested_by INTEGER NOT NULL,requested_at TEXT NOT NULL,
              approved_by INTEGER,approved_at TEXT,expires_at TEXT,comment TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS qc_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT,control_id TEXT,revision_id TEXT,
              actor_id INTEGER NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS qc_audit_project ON qc_audit(project_id,id);
            CREATE TABLE IF NOT EXISTS qc_packages(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,audience TEXT NOT NULL,number INTEGER NOT NULL,
              baseline TEXT NOT NULL,manifest TEXT NOT NULL,file_id TEXT NOT NULL,sha256 TEXT NOT NULL,created_by INTEGER NOT NULL,
              created_at TEXT NOT NULL,final INTEGER NOT NULL DEFAULT 0,UNIQUE(project_id,audience,number));
            CREATE INDEX IF NOT EXISTS qc_package_scope ON qc_packages(project_id,audience,created_at);
            CREATE INDEX IF NOT EXISTS qc_generated_job ON qc_generated_files(job_id,purpose);
            CREATE INDEX IF NOT EXISTS qc_execution_project ON qc_executions(project_id,revision_id,recorded_at);
            ''')
        with hub.db(True) as db:
            from .branding import schema
            schema(db)
        READY.add(key)

def audit(db,user,project_id,action,detail=None,control=None,revision=None):
    db.execute('INSERT INTO qc_audit(project_id,control_id,revision_id,actor_id,action,detail,created_at) VALUES(?,?,?,?,?,?,?)',
      (project_id,control,revision,user['id'],action,bounded(detail or {}),timestamp()))

def project(db,key,user,write=False):
    personal(user);return pi.project(db,key,user,write=write)

def control(db,project_id,key):
    row=db.execute('SELECT * FROM qc_documents WHERE project_id=? AND (id=? OR stage=?)',(project_id,key,key)).fetchone()
    if not row:raise HTTPException(404,'Create or adopt this project document first.')
    return dict(row)
def revision(db,control_id,key):
    row=db.execute('SELECT * FROM qc_revisions WHERE id=? AND control_id=?',(key,control_id)).fetchone()
    if not row:raise HTTPException(404,'Controlled revision not found in this document.')
    return dict(row)
def native(db,doc):return pi.document(db,doc['document_id'],doc['project_id'])
def editable(db,doc,rev,user,version=None):
    p=project(db,doc['project_id'],user,write=True)
    if p['stage']=='released':raise HTTPException(409,'Reopen the project through its existing workflow before preparing a new revision.')
    if native(db,doc)['current_revision']!=rev['id'] or rev['status'] not in {'draft','correction_required'}:
        raise HTTPException(409,'This revision is read-only. Prepare a controlled new revision with a reason.')
    if version is not None and (type(version) is not int or version!=rev['version']):
        raise HTTPException(409,'This document changed. Reload before saving or acting.')
    return p

def guard_native(db,document_id):
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_documents'").fetchone() and db.execute('SELECT 1 FROM qc_documents WHERE document_id=?',(document_id,)).fetchone():
        raise HTTPException(409,'This is a controlled engineering document. Use Quality & Closure to edit, review or export its numbered revision.')

def policy_row(db,p):
    from .configuration import current,profile
    row=db.execute('SELECT * FROM qc_projects WHERE project_id=?',(p['id'],)).fetchone()
    if row:
        state={**dict(row),'policy':json.loads(row['policy']),'context':json.loads(row['context'])}
        applicable=state['context'].get('fat_applicable')
        if applicable is False:state['policy']['required_stages']=[s for s in state['policy']['required_stages'] if s!='fat']
        elif applicable is True and 'fat' not in state['policy']['required_stages']:state['policy']['required_stages'].append('fat')
        return state
    setting=current(db)
    return {'project_id':p['id'],'policy':profile(setting['configuration'],p['kind']),'policy_version':setting['version'],
      'project_type':p['kind'],'context':{},'version':0,'created_at':None,'updated_at':None}

def ensure_project(db,p,user):
    state=policy_row(db,p)
    if state['version']:return state
    now=timestamp()
    db.execute('INSERT INTO qc_projects VALUES(?,?,?,?,?,?,?,?)',(p['id'],bounded(state['policy']),state['policy_version'],p['kind'],'{}',1,now,now))
    audit(db,user,p['id'],'quality_control_started',{'policy_version':state['policy_version'],'project_type':p['kind']})
    return policy_row(db,p)

def source_header(db,p,state):
    users={u['id']:u['username'] for u in hub.users()};context=state['context']
    from .branding import record,organization
    customer=record(db,'customer',context['customer_id'])['data'] if context.get('customer_id') else {}
    org=organization(db,context)
    return {'project_id':p['id'],'project_name':p['title'],'project_number':p.get('project_number') or None,'project_type':p['kind'],
      'customer':customer.get('name') or p.get('customer') or context.get('customer') or None,'customer_details':customer,
      'organization':{'id':org['id'],'version':org['version'],'name':org['data']['name']},
      'machine':p.get('machine') or context.get('machine') or None,
      'scope':context.get('scope') or p.get('description') or None,
      'owner':users.get(p['owner_id']),'owner_id':p['owner_id'],
      'team':[{'id':uid,'name':users.get(uid),'roles':roles} for uid,roles in team(db,p).items()],
      'created_at':p['created_at'],'due_date':p['due_date'],'stage':p['stage'],'completed_at':p.get('completed_at')}
def team(db,p):
    roles={}
    for uid in json.loads(p.get('supporting_ids','[]')):roles.setdefault(uid,set()).add('Supporting engineer')
    for r in db.execute('SELECT owner_id,quality_id,approver_id,release_id FROM items WHERE project_id=?',(p['id'],)):
        for field,label in [('owner_id','Development'),('quality_id','Quality reviewer'),('approver_id','Release approver'),('release_id','Release owner')]:
            if r[field] is not None:roles.setdefault(r[field],set()).add(label)
    return {uid:sorted(labels) for uid,labels in roles.items()}

def case_hash(case,frd_revision):
    return digest({'case':{k:v for k,v in case.items() if k not in {'execution','proposed_outcome','source_result','outcome','waived'}},'frd_revision':frd_revision})

def executions(db,revision_id):
    latest={}
    for row in db.execute('SELECT e.* FROM qc_execution_reuse u JOIN qc_executions e ON e.id=u.execution_id WHERE u.revision_id=?',(revision_id,)):
        r=dict(row);r['file_ids']=json.loads(r['file_ids']);r['reused_from_revision']=r['revision_id'];latest[r['case_id']]=r
    for row in db.execute('SELECT * FROM qc_executions WHERE revision_id=? ORDER BY rowid',(revision_id,)):
        r=dict(row);r['file_ids']=json.loads(r['file_ids']);latest[r['case_id']]=r
    return latest

def detail(db,doc,rev):
    p=pi.revision(db,rev['id'],doc['document_id']);value={**rev,'content':p['content'],'file_id':p['file_id']}
    ex=executions(db,rev['id'])
    for case in value['content'].get('cases',[]):
        result=ex.get(case['id']);case['execution']=result if result and result['specification_hash']==case_hash(case,rev['frd_revision_id']) else None
        case['outcome']=case['execution']['outcome'] if case['execution'] else 'not_run'
        if case.get('native_run_id'):
            run=db.execute('SELECT * FROM engineering_runs WHERE project_id=? AND run_id=?',(doc['project_id'],case['native_run_id'])).fetchone()
            if run:
                from .checks import native_outcome
                source=dict(run);case['source_result']={'run_id':source['run_id'],'kind':source['kind'],'status':source['status'],'outcome':native_outcome(source),'summary':json.loads(source['summary'])}
                if not case['execution'] and rev['confirmed_at'] and rev['confirmed_hash']==rev['content_hash']:case['outcome']=native_outcome(source)
    value['execution_history']=[{**dict(r),'file_ids':json.loads(r['file_ids'])} for r in db.execute('SELECT * FROM qc_executions WHERE revision_id=? ORDER BY rowid DESC',(rev['id'],))]
    acceptance=db.execute('SELECT * FROM qc_acceptances WHERE revision_id=? ORDER BY rowid DESC LIMIT 1',(rev['id'],)).fetchone()
    value['acceptance']={**dict(acceptance),'file_ids':json.loads(acceptance['file_ids'])} if acceptance else None
    value['confirmed']=bool(rev['confirmed_at'] and rev['confirmed_hash']==rev['content_hash'])
    value['customer_file_ids']=[r[0] for r in db.execute('SELECT file_id FROM qc_customer_files WHERE revision_id=?',(rev['id'],))]
    return value
