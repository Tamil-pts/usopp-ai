"""Durable project intelligence records; WorkHub owns accounts, tasks and files."""
from contextlib import nullcontext
import hashlib
import json
import math
import re
import threading
from fastapi import HTTPException
from backend.core.workhub import store as hub,identity,timestamp,text,encode,day

LOCK=threading.RLock()
READY=set()
KINDS={'mom','frd','flowchart','plan','source','note'}
LANGUAGES={'auto','en','ta'}


def initialize():
    key=str(hub.root.resolve())
    if key in READY:return
    with LOCK,hub.db(True) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS pi_meetings(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,subject TEXT NOT NULL,
          meeting_date TEXT NOT NULL DEFAULT '',language TEXT NOT NULL DEFAULT 'auto',participants TEXT NOT NULL DEFAULT '[]',
          file_id TEXT,status TEXT NOT NULL DEFAULT 'saved',duration REAL,transcript TEXT NOT NULL DEFAULT '{}',
          transcript_version INTEGER NOT NULL DEFAULT 0,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS pi_meeting_project ON pi_meetings(project_id,created_at);
        CREATE TABLE IF NOT EXISTS pi_transcript_reviews(meeting_id TEXT NOT NULL,version INTEGER NOT NULL,
          transcript_hash TEXT NOT NULL,reviewed_by INTEGER NOT NULL,reviewed_at TEXT NOT NULL,PRIMARY KEY(meeting_id,version));
        CREATE TABLE IF NOT EXISTS pi_documents(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,kind TEXT NOT NULL,title TEXT NOT NULL,
          meeting_id TEXT,current_revision TEXT,approved_revision TEXT,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,UNIQUE(project_id,kind,meeting_id));
        CREATE INDEX IF NOT EXISTS pi_document_project ON pi_documents(project_id,updated_at);
        CREATE TABLE IF NOT EXISTS pi_revisions(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,number INTEGER NOT NULL,
          content TEXT NOT NULL,file_id TEXT,status TEXT NOT NULL DEFAULT 'draft',reviewer_id INTEGER,created_by INTEGER NOT NULL,
          created_at TEXT NOT NULL,reviewed_at TEXT,review_comment TEXT NOT NULL DEFAULT '',reviewed_by INTEGER,
          generated_by TEXT,base_approved TEXT,applied_at TEXT,UNIQUE(document_id,number),UNIQUE(document_id,generated_by));
        CREATE TABLE IF NOT EXISTS pi_clarifications(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,question TEXT NOT NULL,
          fingerprint TEXT NOT NULL,options TEXT NOT NULL DEFAULT '[]',source_refs TEXT NOT NULL DEFAULT '[]',
          answer TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'open',file_id TEXT,answered_by INTEGER,
          updated_at TEXT NOT NULL,UNIQUE(project_id,fingerprint));
        CREATE TABLE IF NOT EXISTS pi_jobs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued',progress INTEGER NOT NULL DEFAULT 0,stage TEXT NOT NULL DEFAULT 'Queued',
          error TEXT NOT NULL DEFAULT '',result TEXT NOT NULL DEFAULT '{}',created_by INTEGER NOT NULL,created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,lease_owner TEXT,lease_until REAL NOT NULL DEFAULT 0,cancel_requested INTEGER NOT NULL DEFAULT 0,
          attempts INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS pi_jobs_queue ON pi_jobs(status,lease_until,created_at);
        CREATE INDEX IF NOT EXISTS pi_jobs_project ON pi_jobs(project_id,created_at);
        CREATE TABLE IF NOT EXISTS pi_task_links(document_id TEXT NOT NULL,proposal_key TEXT NOT NULL,task_id TEXT NOT NULL,
          PRIMARY KEY(document_id,proposal_key));
        CREATE TABLE IF NOT EXISTS pi_annotations(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,revision_id TEXT NOT NULL,
          page INTEGER NOT NULL,body TEXT NOT NULL,x REAL,y REAL,author_id INTEGER NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pi_preferences(project_id TEXT PRIMARY KEY,terminology TEXT NOT NULL DEFAULT '[]',
          templates TEXT NOT NULL DEFAULT '[]',updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pi_transcript_history(meeting_id TEXT NOT NULL,version INTEGER NOT NULL,transcript TEXT NOT NULL,
          changed_by INTEGER NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(meeting_id,version));
        ''')
        from .reliability import migrate
        migrate(db)
    READY.add(key)


def project(db,key,user,write=False,manage=False):
    hub.actor(user)
    value=hub.contribute(db,key,user) if write else hub.item(db,key)
    if value.get('is_document_space'):
        from backend.core.workhub_document_spaces import authorize
        authorize(db,value,user,write)
    elif value['type']!='project':raise HTTPException(400,'Choose a WorkHub project.')
    if manage:hub.manage(value,user,db)
    return value


def meeting(db,key,project_id):
    row=db.execute('SELECT * FROM pi_meetings WHERE id=? AND project_id=?',(key,project_id)).fetchone()
    if not row:raise HTTPException(404,'This meeting is not in the selected project.')
    return dict(row)


def document(db,key,project_id):
    row=db.execute('SELECT * FROM pi_documents WHERE id=? AND project_id=?',(key,project_id)).fetchone()
    if not row:raise HTTPException(404,'This document is not in the selected project.')
    result=dict(row)
    numbered=db.execute('SELECT number FROM wh_document_numbers WHERE document_id=?',(key,)).fetchone()
    if numbered:result['number']=numbered[0]
    return result


def revision(db,key,document_id):
    row=db.execute('SELECT * FROM pi_revisions WHERE id=? AND document_id=?',(key,document_id)).fetchone()
    if not row:raise HTTPException(404,'This document revision is unavailable.')
    return {**dict(row),'content':json.loads(row['content'])}


def _bounded(value):
    try:raw=json.dumps(value,ensure_ascii=False,allow_nan=False)
    except (ValueError,TypeError):raise HTTPException(400,'Use JSON content with finite numbers.')
    if len(raw.encode())>8*1024*1024:raise HTTPException(413,'Document content exceeds 8 MiB. Split it into smaller project documents.')
    return raw


def create_document(db,user,project_id,kind,title,content,file_id=None,meeting_id=None,generated_by=None,document_id=None,expected_revision=None,quality_control=False):
    # Recover a committed result before creating a new document identity/number.
    if generated_by:
        previous=db.execute('SELECT r.id,r.document_id FROM pi_revisions r JOIN pi_documents d ON d.id=r.document_id WHERE r.generated_by=? AND d.project_id=?',(generated_by,project_id)).fetchone()
        if previous:return document(db,previous['document_id'],project_id),revision(db,previous['id'],previous['document_id'])
        from .reliability import guard_generation
        guard_generation(db,generated_by,document_id)
    if kind not in KINDS:raise HTTPException(400,'Choose a supported document type.')
    if file_id:
        from backend.core.workhub_files import file_record
        file_record(file_id,project_id)
    if meeting_id:meeting(db,meeting_id,project_id)
    if document_id:
        doc=document(db,document_id,project_id)
        if doc['kind']!=kind:raise HTTPException(400,'Create this revision in a document of the same type.')
        if expected_revision!=doc['current_revision']:raise HTTPException(409,'This document changed. Refresh before saving a new revision.')
    else:
        # One MOM per meeting and one FRD/plan per project. Source documents and
        # flowcharts have independent identities and can have many siblings.
        singleton=kind in {'frd','plan'} or kind=='mom' and meeting_id is not None
        row=db.execute('SELECT * FROM pi_documents WHERE project_id=? AND kind=? AND meeting_id IS ?',(project_id,kind,meeting_id)).fetchone() if singleton else None
        if row:doc=dict(row)
        else:
            now=timestamp();doc={'id':identity(),'project_id':project_id,'kind':kind,'title':text(title,240,True),'meeting_id':meeting_id,'current_revision':None,'approved_revision':None}
            db.execute('INSERT INTO pi_documents(id,project_id,kind,title,meeting_id,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                       (doc['id'],project_id,kind,doc['title'],meeting_id,user['id'],now,now))
    if not quality_control:
        from backend.core.workhub_quality.store import guard_native
        guard_native(db,doc['id'])
    if generated_by:
        previous=db.execute('SELECT id FROM pi_revisions WHERE document_id=? AND generated_by=?',(doc['id'],generated_by)).fetchone()
        if previous:return doc,revision(db,previous['id'],doc['id'])
    from backend.core.workhub_studio import bindings as studio_bindings,store as studio_store
    parent_revision=doc.get('current_revision')
    parent_content=revision(db,parent_revision,doc['id'])['content'] if parent_revision else None
    if parent_content and parent_content.get('studio') and not content.get('studio'):content={**content,'studio':parent_content['studio']}
    if content.get('studio'):
        content=studio_bindings.synchronize(content);studio_store.validate_media(db,project_id,content)
    if parent_revision:studio_store.guard(db,user,parent_revision,parent_content,content)
    number=db.execute('SELECT COALESCE(MAX(number),0)+1 FROM pi_revisions WHERE document_id=?',(doc['id'],)).fetchone()[0]
    key=identity();now=timestamp()
    db.execute('INSERT INTO pi_revisions(id,document_id,number,content,file_id,created_by,created_at,generated_by,base_approved) VALUES(?,?,?,?,?,?,?,?,?)',
               (key,doc['id'],number,_bounded(content),file_id,user['id'],now,generated_by,doc.get('approved_revision')))
    studio_store.inherit(db,parent_revision,key)
    db.execute('UPDATE pi_documents SET current_revision=?,updated_at=? WHERE id=?',(key,now,doc['id']))
    item=hub.item(db,project_id);hub.event(db,item,user,'intelligence_revision_created',{'document_id':doc['id'],'revision_id':key,'number':number,'kind':kind,'title':doc['title']})
    doc.update(current_revision=key)
    return doc,revision(db,key,doc['id'])


def save_document(user,project_id,payload,document_id=None):
    initialize()
    with hub.db(True) as db:
        scope=project(db,project_id,user,write=True)
        if scope.get('document_type') in {'flowchart','mindmap'} and user['role']!='admin' and user['id']!=scope['owner_id']:raise HTTPException(403,'Only the diagram author can edit it; the reviewer records review decisions.')
        kind=document(db,document_id,project_id)['kind'] if document_id else payload.get('kind','note')
        existing=revision(db,document(db,document_id,project_id)['current_revision'],document_id) if document_id else {}
        content=payload.get('content',{})
        if not isinstance(content,dict):raise HTTPException(400,'Provide structured document content.')
        if scope.get('is_document_space'):
            from backend.core.workhub_document_information import links
            content={**content,'document_links':links(db,project_id)}
        validate_content(kind,content)
        if document_id and kind=='mom' and (content.get('meeting_subject') or '').strip():
            db.execute('UPDATE pi_documents SET title=? WHERE id=?',(text(content['meeting_subject'],240,True),document_id))
        doc,rev=create_document(db,user,project_id,kind,payload.get('title') or kind.upper(),content,
                               payload.get('file_id',existing.get('file_id')),payload.get('meeting_id'),document_id=document_id,expected_revision=payload.get('version'))
        return {'document':doc,'revision':rev}


def validate_content(kind,value):
    _bounded(value)
    if 'document_info' in value:
        from backend.core.workhub_document_information import clean
        clean(value['document_info'])
    if not isinstance(value.get('sources',[]),list) or any(not isinstance(s,dict) or not isinstance(s.get('id'),str) for s in value.get('sources',[])):raise HTTPException(400,'Use structured source references with source IDs.')
    if kind=='mom':
        for field in ('discussion_summary','decisions','engineering_requirements','actions','clarifications','next_meeting_items'):
            entries=value.get(field,[])
            if not isinstance(entries,list) or len(entries)>2000 or any(not isinstance(entry,dict) for entry in entries):raise HTTPException(400,'Use structured MOM section items.')
        people=value.get('participants',[])
        if not isinstance(people,list) or len(people)>100 or any(not isinstance(person,str) for person in people):raise HTTPException(400,'Provide known participant names as a list.')
        for field in ('meeting_subject','meeting_mode','location','agenda','meeting_objective','meeting_start_time','meeting_end_time'):
            if field in value:text(value[field] or '',12000 if field in {'agenda','meeting_objective'} else 500)
        details=value.get('participant_details',[])
        if not isinstance(details,list) or len(details)>100 or any(not isinstance(p,dict) for p in details):raise HTTPException(400,'Use up to 100 structured participant rows.')
        for person in details:
            for field in ('name','role','organization'):text(person.get(field,'') or '',500)
            if person.get('attendance','Not confirmed') not in {'Present','Absent','Invited','Not confirmed'}:raise HTTPException(400,'Choose a recorded attendance status.')
        types=value.get('meeting_types',[])
        if not isinstance(types,list) or len(types)>4 or any(t not in {'Project Review','Requirement','Issue / Resolution','Others'} for t in types):raise HTTPException(400,'Choose a supported meeting type.')
        next_meeting=value.get('next_meeting',{})
        if not isinstance(next_meeting,dict):raise HTTPException(400,'Provide structured next meeting details.')
        for field in ('date','time','mode'):text(next_meeting.get(field,'') or '',500)
    if kind=='flowchart':
        nodes=value.get('nodes',[]);edges=value.get('edges',[])
        if not isinstance(nodes,list) or not isinstance(edges,list) or len(nodes)>500 or len(edges)>1500:raise HTTPException(400,'Use up to 500 nodes and 1,500 connections.')
        ids=set()
        for node in nodes:
            if not isinstance(node,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',str(node.get('id',''))) or node['id'] in ids:raise HTTPException(400,'Diagram node IDs must be unique.')
            ids.add(node['id']);position=node.get('position',{})
            if not isinstance(position,dict) or not isinstance(node.get('data',{}),dict):raise HTTPException(400,'Provide a position and structured data for every diagram node.')
            if any(type(position.get(k)) not in (int,float) or not math.isfinite(position[k]) or abs(position[k])>100000 for k in ('x','y')):raise HTTPException(400,'Use finite diagram positions.')
            text(str(node.get('data',{}).get('label','')),2000)
            data=node.get('data',{})
            if data.get('kind','process') not in {'start','process','decision','end','alarm','interlock','io','topic','subtopic','document','subprocess','note'}:raise HTTPException(400,'Choose a supported engineering node type.')
            for dimension in ('width','height'):
                if dimension in node and (type(node[dimension]) not in (int,float) or not math.isfinite(node[dimension]) or not 60<=node[dimension]<=1200):raise HTTPException(400,'Use node dimensions from 60 to 1200 pixels.')
            if data.get('color') and not re.fullmatch(r'#[0-9a-fA-F]{6}',str(data['color'])):raise HTTPException(400,'Choose a valid node color.')
            refs=data.get('plc_references',[])
            if not isinstance(refs,list) or len(refs)>100 or any(not isinstance(v,str) or len(v)>180 for v in refs):raise HTTPException(400,'Use up to 100 short PLC I/O references per node.')
        for edge in edges:
            if not isinstance(edge,dict) or edge.get('source') not in ids or edge.get('target') not in ids:raise HTTPException(400,'Connect existing diagram nodes.')
            text(edge.get('label') or '',2000)
        edge_ids=[edge.get('id') for edge in edges]
        if any(not isinstance(key,str) or not key for key in edge_ids) or len(set(edge_ids))!=len(edge_ids):raise HTTPException(400,'Diagram connection IDs must be unique.')
        from backend.core.workhub_drawing import validate as validate_drawing
        validate_drawing(value)
    if kind=='frd':
        requirements=value.get('requirements',[])
        if not isinstance(requirements,list) or len(requirements)>2000:raise HTTPException(400,'Use up to 2,000 requirements per document.')
        ids=[r.get('id') for r in requirements if isinstance(r,dict)]
        if len(ids)!=len(requirements) or any(not re.fullmatch(r'(?:FR|REQ)-\d{3,6}',str(i or '')) for i in ids) or len(set(ids))!=len(ids):raise HTTPException(400,'Every requirement needs a unique REQ-001 or FR-001 style ID.')
        for requirement in requirements:
            for field in ('title','description','trigger','expected_behavior','subsystem','acceptance_criteria'):
                item=requirement.get(field)
                if item is not None and not isinstance(item,str):raise HTTPException(400,'Requirement descriptions, conditions and criteria must be text or unconfirmed.')
    if kind=='plan':
        tasks=value.get('tasks',[])
        if not isinstance(tasks,list) or len(tasks)>200:raise HTTPException(400,'Use up to 200 proposed tasks.')
        ids=set()
        for task in tasks:
            key=task.get('id') if isinstance(task,dict) else None
            if not isinstance(key,str) or not key or key in ids:raise HTTPException(400,'Proposed task IDs must be unique.')
            ids.add(key);text(task.get('title',''),180,True)
            for field in ('start_date','due_date'):
                if task.get(field):day(task[field])
            if task.get('start_date') and task.get('due_date') and task['due_date']<task['start_date']:raise HTTPException(400,'Task finish must follow its start.')
        for task in tasks:
            if not isinstance(task.get('dependencies',[]),list) or any(k not in ids or k==task['id'] for k in task.get('dependencies',[])):raise HTTPException(400,'Choose dependencies in this proposal.')
            if task.get('phase','development') not in {'development','quality','release'}:raise HTTPException(400,'Choose development, quality or release for the activity.')
            hours=task.get('planned_hours') or 0
            if type(hours) not in (int,float) or not math.isfinite(hours) or not 0<=hours<=100000:raise HTTPException(400,'Use a finite estimate between 0 and 100,000 hours.')
            if task.get('milestone') and (not task.get('start_date') or task.get('start_date')!=task.get('due_date')):raise HTTPException(400,'A milestone needs a matching start and finish date.')
            if task.get('owner_id') is not None:hub.user_id(task['owner_id'])
        graph={task['id']:task.get('dependencies',[]) for task in tasks};visited=set()
        def visit(key,path):
            if key in path:raise HTTPException(400,'Proposed dependencies cannot form a cycle.')
            if len(path)>150:raise HTTPException(400,'Use dependency chains up to 150 activities.')
            if key in visited:return
            for parent in graph[key]:visit(parent,path|{key})
            visited.add(key)
        for key in graph:visit(key,set())


def overview(user,key):
    initialize()
    with hub.db() as db:
        item=project(db,key,user)
        meetings=[]
        for row in db.execute('SELECT id,subject,meeting_date,language,participants,file_id,status,duration,transcript_version,created_by,created_at,updated_at FROM pi_meetings WHERE project_id=? ORDER BY created_at DESC LIMIT 200',(key,)):
            meetings.append({**dict(row),'participants':json.loads(row['participants'])})
        documents=[]
        fields=('id','number','file_id','status','reviewer_id','created_by','created_at','reviewed_at','applied_at')
        sql='SELECT d.*,'+','.join('r.'+f+' AS rev_'+f for f in fields)+" FROM pi_documents d LEFT JOIN pi_revisions r ON r.id=d.current_revision WHERE d.project_id=? AND COALESCE(r.status,'')!='archived' ORDER BY d.updated_at DESC LIMIT 500"
        for row in db.execute(sql,(key,)):
            value=dict(row);current={f:value.pop('rev_'+f) for f in fields}
            documents.append({**value,'revision':current if current['id'] else {}})
        from .jobs import list_jobs
        jobs=list_jobs(user,key,100)['jobs']
        clarifications=[{**dict(row),'options':json.loads(row['options']),'source_refs':json.loads(row['source_refs'])} for row in db.execute('SELECT * FROM pi_clarifications WHERE project_id=? ORDER BY updated_at DESC LIMIT 500',(key,))]
        pref=db.execute('SELECT * FROM pi_preferences WHERE project_id=?',(key,)).fetchone()
        preferences={'terminology':json.loads(pref['terminology']),'templates':json.loads(pref['templates'])} if pref else {'terminology':['PLC','HMI','servo','VFD','Modbus','OPC UA'],'templates':['Requirement finalization','Electrical design','PLC programming','HMI development','Communication integration','Internal testing','FAT','Site commissioning','Project handover']}
        approved=[]
        for doc in documents:
            if doc['kind']=='frd' and doc['approved_revision']:approved=revision(db,doc['approved_revision'],doc['id'])['content'].get('requirements',[])
        return {'project_id':key,'meetings':meetings,'documents':documents,'jobs':jobs,'clarifications':clarifications,'preferences':preferences,
                'approved_requirements':[{'id':r['id'],'title':r.get('title','')} for r in approved if r.get('change')!='removed_proposed'],
                'summary':{'approved_requirements':sum(r.get('change')!='removed_proposed' for r in approved),
                           'pending_reviews':sum(d['revision'].get('status')=='review' for d in documents),
                           'open_clarifications':sum(c['status'] in {'open','ask_later','not_decided'} for c in clarifications)}}


def get_document(user,key,doc_id):
    initialize()
    with hub.db() as db:
        p=project(db,key,user);doc=document(db,doc_id,key)
        revisions=[]
        for row in db.execute('SELECT * FROM pi_revisions WHERE document_id=? ORDER BY number DESC LIMIT 100',(doc_id,)):
            value=dict(row);raw=value.pop('content')
            if row['id']==doc['current_revision']:value['content']=json.loads(raw)
            revisions.append(value)
        annotations=[dict(row) for row in db.execute('SELECT * FROM pi_annotations WHERE document_id=? ORDER BY created_at',(doc_id,))]
        from backend.core.workhub_signoff import history
        current=next((r for r in revisions if r['id']==doc['current_revision']),{})
        can_delete=p['stage']!='released' and current.get('status')!='archived' and (user['role']=='admin' or user['id'] in {p['owner_id'],p['created_by'],doc['created_by'],current.get('created_by')})
        can_edit=False
        if p['stage']!='released' and current.get('status') not in {'archived','review','in_review'}:
            try:project(db,key,user,write=True);can_edit=True
            except HTTPException as error:
                if error.status_code not in {403,404}:raise
        if p.get('document_type') in {'flowchart','mindmap'} and user['role']!='admin' and user['id']!=p['owner_id']:can_edit=False
        return {'document':doc,'revisions':revisions,'annotations':annotations,'can_edit':can_edit,'can_delete':can_delete,'sign_offs':[stamp for rev in revisions for stamp in history(db,rev['id'])]}


def review(user,key,doc_id,payload):
    initialize()
    from backend.core.workhub_quality.store import initialize as initialize_quality
    initialize_quality()
    with hub.db(True) as db:
        item=project(db,key,user);doc=document(db,doc_id,key)
        from backend.core.workhub_quality.store import guard_native
        guard_native(db,doc_id)
        rev=revision(db,payload.get('revision_id'),doc_id)
        action=payload.get('action');comment=text(payload.get('comment',''),4000)
        if action=='submit':
            project(db,key,user,write=True)
            if doc['current_revision']!=rev['id'] or rev['status'] not in {'draft','changes_requested'}:raise HTTPException(409,'Submit the latest editable revision.')
            if doc['kind']=='flowchart' and not rev['content'].get('nodes'):raise HTTPException(400,'Add diagram content before submitting it.')
            from backend.core.workhub_studio.quality import assert_ready
            assert_ready(db,item,doc,rev)
            reviewer=hub.user_id(payload.get('reviewer_id',item['quality_id']))
            if item.get('is_document_space') and (not item.get('reviewer_id') or reviewer!=item['reviewer_id'] or reviewer==rev['created_by']):raise HTTPException(400,'Choose an independent reviewer in document settings before submitting.')
            db.execute("UPDATE pi_revisions SET status='review',reviewer_id=? WHERE id=?",(reviewer,rev['id']))
            hub.notify(db,item,user['id'],[reviewer],'Document review: '+doc['title'],f'Review revision {rev["number"]} in Project Intelligence.')
        elif action in {'approve','request_changes','reject'}:
            if rev['status']!='review' or rev['reviewer_id']!=user['id']:raise HTTPException(403,'The assigned document reviewer must record this decision.')
            if doc['current_revision']!=rev['id']:raise HTTPException(409,'A newer document revision exists. Review the latest revision.')
            if action!='approve' and not comment.strip():raise HTTPException(400,'Describe the requested corrections or rejection.')
            from backend.core.workhub_signoff import record as sign
            stamp=sign(db,user,payload,project_id=key,subject_id=rev['id'],subject_type='document_revision',
                decision=action,role='Document reviewer',basis={'document_id':doc_id,'revision_id':rev['id'],'revision':rev['number'],'content_hash':__import__('hashlib').sha256(_bounded(rev['content']).encode()).hexdigest()})
            if action=='approve':
                if rev['base_approved']!=doc['approved_revision']:raise HTTPException(409,'The approved baseline changed. Refresh and prepare a new revision.')
                validate_content(doc['kind'],rev['content'])
                from backend.core.workhub_studio.quality import assert_ready
                assert_ready(db,item,doc,rev)
                if doc['kind']=='frd' and not rev['content'].get('requirements'):raise HTTPException(400,'Add requirements before approving the FRD.')
                if doc['kind']=='plan' and not rev['content'].get('tasks'):raise HTTPException(400,'Add activities before approving the plan.')
                db.execute('UPDATE pi_documents SET approved_revision=?,updated_at=? WHERE id=?',(rev['id'],timestamp(),doc_id))
            db.execute('UPDATE pi_revisions SET status=?,reviewed_at=?,review_comment=?,reviewed_by=? WHERE id=?',
                       ('approved' if action=='approve' else 'rejected' if action=='reject' else 'changes_requested',timestamp(),comment,user['id'],rev['id']))
            if action=='approve':
                from backend.core.workhub_quality.pdf_templates import freeze
                freeze(db,item,doc,revision(db,rev['id'],doc_id),user,controlled=False)
                from backend.core.workhub_studio.exporting import freeze as freeze_studio
                freeze_studio(db,item,doc,revision(db,rev['id'],doc_id),user)
            hub.notify(db,item,user['id'],[rev['created_by']],('Document approved: ' if action=='approve' else 'Document changes requested: ')+doc['title'],comment or 'The assigned reviewer approved this recorded revision.')
        else:raise HTTPException(400,'Choose submit, approve, reject or request changes.')
        hub.event(db,item,user,'intelligence_document_'+action,{'document_id':doc_id,'revision_id':rev['id'],'comment':comment,'sign_off':stamp if action in {'approve','request_changes','reject'} else None})
        return {'document':doc,'revision':revision(db,rev['id'],doc_id)}


def add_clarification(db,key,question,options=None,source_refs=None):
    question=text(question,1000,True);fingerprint=hashlib.sha256(' '.join(re.sub(r'[^\w\s]','',question.casefold()).split()).encode()).hexdigest()
    if not isinstance(options or [],list) or not isinstance(source_refs or [],list):raise HTTPException(400,'Provide question choices and source references as lists.')
    db.execute('INSERT OR IGNORE INTO pi_clarifications(id,project_id,question,fingerprint,options,source_refs,updated_at) VALUES(?,?,?,?,?,?,?)',
               (identity(),key,question,fingerprint,encode((options or [])[:8]),encode(source_refs or []),timestamp()))


def answer(user,key,clarification_id,payload):
    initialize()
    with hub.db(True) as db:
        item=project(db,key,user,write=True)
        row=db.execute('SELECT * FROM pi_clarifications WHERE id=? AND project_id=?',(clarification_id,key)).fetchone()
        if not row:raise HTTPException(404,'Choose a clarification in this project.')
        status=payload.get('status','confirmed')
        if status not in {'confirmed','not_decided','ask_later'}:raise HTTPException(400,'Choose an answer, Not decided or Ask later.')
        value=text(payload.get('answer',''),4000,status=='confirmed')
        if payload.get('file_id'):
            from backend.core.workhub_files import file_record
            file_record(payload['file_id'],key)
        db.execute('UPDATE pi_clarifications SET answer=?,status=?,file_id=?,answered_by=?,updated_at=? WHERE id=?',
                   (value,status,payload.get('file_id'),user['id'],timestamp(),clarification_id))
        hub.event(db,item,user,'intelligence_clarification_answered',{'clarification_id':clarification_id,'answer':value,'status':status})
        return {'status':status}
