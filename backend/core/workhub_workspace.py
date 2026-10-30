"""Missing project metadata and a common register over existing documents.

Project identity stays in items; customer/machine/scope stay in qc_projects.
Numbering uses the existing transactional qc_sequences and company prefixes.
"""
import json
import re
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from backend.core.workhub import store as hub, text, timestamp, encode

FIELDS={'project_number','priority','assignment_state','assigned_at','supporting_ids','responsibility','assignment_remarks','exception_status','exception_reason'}
CONTEXT={'customer','customer_project_reference','machine','scope','project_requirements','acceptance_criteria','additional_information','base_reference','developed_reference','customer_id','organization_id'}


def migrate(db):
    from .workhub_document_spaces import schema
    schema(db)
    db.execute('CREATE TABLE IF NOT EXISTS ds_template_drafts(scope_id TEXT PRIMARY KEY,document_id TEXT NOT NULL,kind TEXT NOT NULL,name TEXT NOT NULL,owner_id INTEGER NOT NULL,created_at TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS wh_closed_schedule(project_id TEXT PRIMARY KEY,due_date TEXT NOT NULL)')
    columns={r[1] for r in db.execute('PRAGMA table_info(items)')}
    for name,default in [('project_number',''),('priority','normal'),('assignment_state','assigned'),('assigned_at',''),('supporting_ids','[]'),('responsibility',''),('assignment_remarks',''),('exception_status',''),('exception_reason','')]:
        if name not in columns:db.execute('ALTER TABLE items ADD COLUMN '+name+" TEXT NOT NULL DEFAULT '"+default+"'")
    if 'is_sample' not in columns:db.execute('ALTER TABLE items ADD COLUMN is_sample INTEGER NOT NULL DEFAULT 0')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS workspace_project_number ON items(project_number) WHERE type='project' AND project_number!=''")


def lifecycle(p):
    exception=p.get('exception_status')
    if exception=='on_hold':return 'On Hold'
    if exception=='cancelled':return 'Cancelled'
    if p['stage']=='blocked':return 'Blocked'
    if p['stage']=='released':return 'Completed'
    if p.get('assignment_state')=='unassigned':return 'Created'
    if p['stage']=='todo':return 'Assigned'
    if p['stage']=='ready_release':return 'Closure'
    if p['stage'] in {'quality','release_approval'}:return 'Quality Review'
    return 'In Progress'


def allocate(db):
    from .workhub_quality.configuration import current
    c=current(db)['configuration'];year=datetime.now(ZoneInfo(c['timezone'])).year
    scope='project:'+':'.join([c['company'],c['department'],c['team'],str(year)])
    if c.get('project_prefix'):scope+=':'+c['project_prefix']
    for _ in range(10000):
        row=db.execute('SELECT last_value FROM qc_sequences WHERE scope=?',(scope,)).fetchone()
        n=row[0]+1 if row else c['sequence_start']
        db.execute('INSERT INTO qc_sequences VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET last_value=excluded.last_value',(scope,n))
        value=c['pattern'].format(COMPANY=c['company'],DEPARTMENT=c['department'],TEAM=c['team'],DOCTYPE='PRJ',YEAR=year,SEQ=str(n).zfill(c['sequence_width']),SEP=c['separator'])
        if c.get('project_prefix'):value=c['separator'].join([c['project_prefix'],str(year),str(n).zfill(c['sequence_width'])])
        if not db.execute('SELECT 1 FROM items WHERE project_number=?',(value,)).fetchone():return value
    raise HTTPException(409,'Project numbering needs administrator review.')


def numbering_preview():
    from .workhub_quality import store,configuration
    store.initialize()
    with hub.db() as db:
        c=configuration.current(db)['configuration'];year=datetime.now(ZoneInfo(c['timezone'])).year
        prefix=c.get('project_prefix','');scope='project:'+':'.join([c['company'],c['department'],c['team'],str(year)])+(':'+prefix if prefix else '')
        r=db.execute('SELECT last_value FROM qc_sequences WHERE scope=?',(scope,)).fetchone();n=r[0]+1 if r else c['sequence_start']
        for _ in range(10000):
            value=c['separator'].join([prefix,str(year),str(n).zfill(c['sequence_width'])]) if prefix else c['pattern'].format(COMPANY=c['company'],DEPARTMENT=c['department'],TEAM=c['team'],DOCTYPE='PRJ',YEAR=year,SEQ=str(n).zfill(c['sequence_width']),SEP=c['separator'])
            if not db.execute('SELECT 1 FROM items WHERE project_number=?',(value,)).fetchone():break
            n+=1
        return {'prefix':prefix,'separator':c['separator'],'preview':value,'note':'Preview only. The final automatic number is reserved when the project is created.'}


def apply(db,p,user,payload,creating=False):
    from .workhub_quality import store,branding
    values={}
    if creating or 'project_number' in payload:
        number=text(payload.get('project_number',''),120)
        if creating and number:
            from .workhub_quality.configuration import current
            c=current(db)['configuration'];prefix=c.get('project_prefix','');join=c['separator']
            if prefix and not number.startswith(prefix+join):number=text(prefix+join+number,120)
        if number and not re.fullmatch(r'[A-Za-z0-9_./ -]+',number):raise HTTPException(400,'Use letters, digits and simple separators for the project number.')
        if p.get('project_number') and number!=p['project_number'] and p['stage']!='todo':raise HTTPException(409,'Project numbers are fixed after work starts.')
        values['project_number']=number or allocate(db)
    if creating or 'priority' in payload:
        priority=payload.get('priority','normal')
        if priority not in {'low','normal','high','urgent'}:raise HTTPException(400,'Choose a supported priority.')
        values['priority']=priority
    if creating:
        mode=payload.get('assignment_mode','now')
        if mode not in {'now','later'}:raise HTTPException(400,'Choose whether to assign the engineer now or later.')
        values.update(assignment_state='unassigned' if mode=='later' else 'assigned',assigned_at='' if mode=='later' else timestamp())
    elif 'owner_id' in payload and (p.get('assignment_state')=='unassigned' or payload['owner_id']!=p['owner_id']):
        values.update(assignment_state='assigned',assigned_at=timestamp())
    for key in ['responsibility','assignment_remarks']:
        if key in payload:values[key]=text(payload[key],2000)
    if 'supporting_ids' in payload:
        ids=payload['supporting_ids']
        if not isinstance(ids,list) or len(ids)>100:raise HTTPException(400,'Choose up to 100 supporting engineers.')
        values['supporting_ids']=encode(list(dict.fromkeys(hub.user_id(uid) for uid in ids)))
    if p['stage']=='released' and (values or CONTEXT.intersection(payload)) and not creating:
        raise HTTPException(409,'Reopen the project through its controlled workflow before revising project metadata.')
    if CONTEXT.intersection(payload):
        state=store.ensure_project(db,p,user);context=dict(state['context'])
        for key in ['customer','customer_project_reference','machine','scope','project_requirements','acceptance_criteria','additional_information','base_reference','developed_reference']:
            if key in payload:context[key]=text(payload[key] or '',8000 if key in {'scope','project_requirements','acceptance_criteria','additional_information','base_reference','developed_reference'} else 180)
        context=branding.link_context(db,context,payload)
        db.execute('UPDATE qc_projects SET context=?,version=version+1,updated_at=? WHERE project_id=?',(store.bounded(context),timestamp(),p['id']))
        store.audit(db,user,p['id'],'project_context_updated',{'fields':sorted(CONTEXT.intersection(payload))})
    if values:
        try:db.execute('UPDATE items SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),p['id']))
        except sqlite3.IntegrityError:raise HTTPException(409,'This project number already exists. Choose another number.') from None
        hub.event(db,p,user,'project_registered' if creating else 'project_assignment_updated',values)
        old_support=set(json.loads(p.get('supporting_ids','[]')))
        new_support=set(json.loads(values.get('supporting_ids','[]')))-old_support
        if new_support:hub.notify(db,p,user['id'],new_support,'Project team assignment: '+p['title'],'You are assigned as a supporting engineer. Open the project to view its tasks and documents.')
        if not creating and p.get('assignment_state')=='unassigned' and values.get('assignment_state')=='assigned':
            hub.notify(db,p,user['id'],[payload.get('owner_id',p['owner_id'])],'Project assigned: '+p['title'],'You are the responsible engineer. Open My Work to begin.')
    return bool(values or CONTEXT.intersection(payload))


def create(user,payload):
    from .workhub_quality import store
    store.initialize()
    if 'is_sample' in payload and (type(payload['is_sample']) is not bool or user.get('role')!='admin'):
        raise HTTPException(403,'Only Admin can mark demonstration projects.')
    if payload.get('workspace_schema')==2:
        for field in ('title','description','kind','due_date'):
            if not str(payload.get(field) or '').strip():raise HTTPException(400,'Complete the project '+field.replace('_',' ')+'.')
        if not (payload.get('customer_id') or str(payload.get('customer') or '').strip()):raise HTTPException(400,'Choose or enter the customer.')
    if payload.get('workspace_schema')==3 and not str(payload.get('title') or '').strip():raise HTTPException(400,'Enter a project name.')
    with hub.db(True) as db:
        value=hub.create(user,payload,transaction=db)
        apply(db,hub.item(db,value['id']),user,payload,True)
        if payload.get('is_sample'):
            db.execute('UPDATE items SET is_sample=1 WHERE id=?',(value['id'],))
        if payload.get('prepare_frd') is True:
            from .workhub_quality import authoring,documents
            p=hub.item(db,value['id']);content=authoring.blank('frd')
            content.update(purpose=text(payload.get('description',''),12000),scope=text(payload.get('scope',''),12000),acceptance_summary=text(payload.get('acceptance_criteria',''),12000))
            rows=payload.get('requirement_items',[])
            if not isinstance(rows,list) or len(rows)>200:raise HTTPException(400,'Provide up to 200 project requirements.')
            for index,row in enumerate(rows):
                if not isinstance(row,dict):raise HTTPException(400,'Provide structured requirements.')
                description=text(row.get('description',''),8000,True)
                content['requirements'].append({'id':'FR-'+str(index+1).zfill(3),'title':description[:180], 'description':description,'acceptance_criteria':'','trigger':'','expected_behavior':'','subsystem':text(row.get('category',''),200), 'category':text(row.get('category',''),200),'source_label':text(row.get('source_label',''),240),'priority':row.get('priority','medium'),'source_ids':[],'mandatory':True,'change':'new'})
            if not rows and payload.get('project_requirements'):
                description=text(payload['project_requirements'],8000,True)
                content['requirements'].append({'id':'FR-001','title':description[:180],'description':description,'acceptance_criteria':'','source_ids':[],'mandatory':True,'change':'new'})
            for key,heading in [('base_reference','Base reference'),('developed_reference','Developed reference'),('additional_information','Additional information')]:
                if payload.get(key):content['sections'].append({'heading':heading,'text':text(payload[key],12000)})
            if payload.get('flowchart'):
                if not isinstance(payload['flowchart'],dict):raise HTTPException(400,'Provide a structured flowchart.')
                content['flowchart']={**payload['flowchart'],'needs_review':True}
            content=documents.clean_content(db,p['id'],'frd',content)
            documents.create_control(db,p,user,'frd',initial_content=content)
        from .workhub_workflow import create_steps,validate_steps
        if 'workflow_steps' in payload:
            from .workhub_quality import configuration
            steps=validate_steps(payload['workflow_steps'])
            if not steps:raise HTTPException(400,'Add at least one workflow step.')
            assignments=payload.get('workflow_assignees',{})
            if not isinstance(assignments,dict) or set(assignments)-{step['id'] for step in steps}:raise HTTPException(400,'Choose assignees for valid workflow steps.')
            assignments={key:hub.user_id(uid) for key,uid in assignments.items()}
            template=payload.get('workflow_template','')
            if not isinstance(template,str):raise HTTPException(400,'Choose a configured workflow template.')
            current=configuration.current(db)
            if template and template not in current['configuration']['project_profiles']:raise HTTPException(400,'Choose a configured workflow template.')
            p=hub.item(db,value['id']);state=store.ensure_project(db,p,user)
            policy=configuration.profile(current['configuration'],template) if template else configuration.profile(current['configuration'],'')
            policy['workflow_steps']=steps
            db.execute('UPDATE qc_projects SET policy=?,policy_version=?,project_type=?,version=version+1,updated_at=? WHERE project_id=?',
                       (store.bounded(policy),current['version'],template or p['kind'],timestamp(),p['id']))
            store.audit(db,user,p['id'],'project_workflow_configured',{'template':template,'step_count':len(steps)})
            create_steps(db,p,user,assignments)
        else:
            create_steps(db,hub.item(db,value['id']),user)
        return hub.public(hub.item(db,value['id']))


def edit(user,key,payload):
    from .workhub_quality import store
    store.initialize()
    with hub.db(True) as db:
        p=hub.item(db,key)
        base={k:v for k,v in payload.items() if k not in FIELDS|CONTEXT}
        value=hub.edit(user,key,base,transaction=db)
        if p['type']=='project' and apply(db,p,user,payload):
            db.execute('UPDATE items SET version=version+1,updated_at=? WHERE id=?',(timestamp(),key))
        return hub.public(hub.item(db,key))


def guard_transition(user,key):
    with hub.db() as db:
        row=hub.item(db,key);p=hub.item(db,row['project_id'])
        if p.get('exception_status') in {'on_hold','cancelled'}:raise HTTPException(409,'Resume or reopen the project condition before advancing its workflow.')
        if p.get('assignment_state')=='unassigned':raise HTTPException(409,'Assign a responsible engineer before starting project work.')


def exception(user,key,payload):
    hub.actor(user)
    with hub.db(True) as db:
        p=hub.item(db,key);hub.manage(p,user,db)
        if p['type']!='project' or p['stage']=='released':raise HTTPException(409,'Use controlled reopening for a completed project.')
        if payload.get('version')!=p['version']:raise HTTPException(409,'The project changed. Refresh before acting.')
        value=payload.get('condition','');reason=text(payload.get('reason',''),4000,True)
        if value not in {'','on_hold','cancelled'}:raise HTTPException(400,'Choose On Hold, Cancelled or Resume.')
        if p['exception_status']=='cancelled' and value=='on_hold':raise HTTPException(409,'Resume the cancelled project with a reason before placing it on hold.')
        db.execute('UPDATE items SET exception_status=?,exception_reason=?,version=version+1,updated_at=? WHERE id=?',(value,reason,timestamp(),key))
        hub.event(db,p,user,'project_'+(value or 'resumed'),{'reason':reason,'previous':p['exception_status']})
        hub.notify(db,p,user['id'],[p['owner_id'],p['quality_id'],p['approver_id'],p['release_id']],p['title']+': '+(value.replace('_',' ') or 'resumed'),reason)
        return hub.public(hub.item(db,key))


def details(user,key):
    from . import workhub_portfolio as portfolio
    from .workhub_quality import store
    store.initialize()
    with hub.db() as db:
        p=hub.item(db,key)
        if p.get('is_document_space'):
            from .workhub_document_spaces import details as document_details
            return document_details(user,key)
    value=hub.detail(key)
    with hub.db() as db:
        p=value['project'];state=store.policy_row(db,p)
        assessed=portfolio.calculate(p,value['tasks'],value['issues'],portfolio.policy(db,key),phase_schedule=value['phases'])
        quality=db.execute("SELECT r.status FROM qc_documents d JOIN pi_documents n ON n.id=d.document_id JOIN qc_revisions r ON r.id=n.current_revision WHERE d.project_id=? AND d.stage='quality'",(key,)).fetchone()
        p.update(project_status=lifecycle(p),portfolio_progress=assessed['progress'],portfolio_health=assessed['health'],health_reasons=assessed['reasons'],
                 progress_basis=assessed['progress_basis'],quality_status=quality[0] if quality else 'Workflow review' if p['stage'] in {'quality','release_approval','ready_release'} else 'Not submitted')
        value['project_context']=state['context']
        value['pending_approvals']=db.execute("SELECT COUNT(*) FROM items WHERE project_id=? AND stage IN ('quality','release_approval','ready_release')",(key,)).fetchone()[0]
    return value


def document_register(user,search='',kind='',status='',project_id='',page=1,page_size=20,library_only=False):
    from . import workhub_portfolio as portfolio
    from .workhub_quality import store
    store.initialize();hub.actor(user)
    with hub.db() as db:
        db.execute('BEGIN')
        _,_,predicate,args=portfolio.scope(db,user,'management' if user['role']=='admin' else 'engineer')
        query="""SELECT d.id,d.project_id,COALESCE(p.title,lp.title,'Independent document') AS project,COALESCE(p.project_number,lp.project_number,'') AS project_number,
                 s.linked_project_id,s.library,s.owner_id AS space_owner,s.reviewer_id AS space_reviewer,CASE WHEN s.id IS NULL THEN 0 ELSE 1 END AS independent,d.kind,d.title,d.updated_at,d.current_revision,
                 r.number AS revision,r.status,r.created_by AS owner_id,q.id AS control_id,COALESCE(q.number,dn.number) AS document_number,q.stage,
                 cr.label AS revision_label,cr.status AS controlled_status,cr.owner_id AS controlled_owner
                 FROM pi_documents d LEFT JOIN items p ON p.id=d.project_id LEFT JOIN wh_document_spaces s ON s.id=d.project_id
                 LEFT JOIN items lp ON lp.id=s.linked_project_id JOIN pi_revisions r ON r.id=d.current_revision
                 LEFT JOIN qc_documents q ON q.document_id=d.id LEFT JOIN qc_revisions cr ON cr.id=r.id
                 LEFT JOIN wh_document_numbers dn ON dn.document_id=d.id
                 WHERE NOT EXISTS (SELECT 1 FROM ds_template_drafts td WHERE td.scope_id=d.project_id) AND ((p.type='project' AND """+predicate+") OR (s.id IS NOT NULL AND (? OR s.owner_id=? OR s.reviewer_id=? OR (s.library=1 AND s.linked_project_id IS NULL AND COALESCE(cr.status,r.status) IN ('approved','released')))))"
        params=[*args,user['role']=='admin',user['id'],user['id']]
        if project_id:query+=' AND (p.id=? OR s.linked_project_id=?)';params.extend([project_id,project_id])
        if kind:query+=' AND COALESCE(q.stage,d.kind)=?';params.append(kind)
        if status:query+=' AND COALESCE(cr.status,r.status)=?';params.append(status)
        if library_only:query+=" AND COALESCE(cr.status,r.status) IN ('approved','released') AND (s.library=1 OR p.id IS NOT NULL)"
        if search:
            query+=' AND (d.title LIKE ? ESCAPE \'\\\' OR p.title LIKE ? ESCAPE \'\\\' OR p.project_number LIKE ? ESCAPE \'\\\' OR q.number LIKE ? ESCAPE \'\\\')'
            term='%'+text(search,180).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%';params.extend([term]*4)
        total=db.execute('SELECT COUNT(*) FROM ('+query+')',params).fetchone()[0]
        rows=[dict(r) for r in db.execute(query+' ORDER BY d.updated_at DESC,d.id LIMIT ? OFFSET ?',(*params,page_size,(page-1)*page_size))]
        people={u['id']:u['username'] for u in hub.users()}
        for r in rows:
            r['status']=r['controlled_status'] or r['status'];r['owner']=people.get(r['controlled_owner'] or r['owner_id'])
            r['type']=r['stage'] or r['kind'];r['section']='meetings' if r['type'] in {'mom','frd','flowchart'} else 'quality' if r['type'] in {'fat','quality','closure'} else 'overview' if r['type']=='plan' else 'documents'
            r['document_number']=r['document_number'] or 'Native '+r['id'][:8].upper()
            r['pdf_url']='/api/workhub/projects/'+r['project_id']+('/quality/documents/'+r['control_id']+'/export/pdf' if r['control_id'] else '/intelligence/documents/'+r['id']+'/export/pdf')+'?revision_id='+r['current_revision']
            r['api_url']='/api/workhub/projects/'+r['project_id']+('/quality/documents/'+r['control_id'] if r['control_id'] else '/intelligence/documents/'+r['id'])
            r['library_preview_only']=bool(r['independent'] and user['role']!='admin' and user['id'] not in {r['space_owner'],r['space_reviewer']})
            if r['library_preview_only']:r['pdf_url']='/api/workhub/documents/'+r['id']+'/library-preview'
        return {'items':rows,'total':total,'page':page,'page_size':page_size,
                'types':[{'id':k,'label':v} for k,v in {'mom':'Minutes of Meeting','frd':'FRD','flowchart':'Functional Flowchart',**store.STAGES,'source':'Source document','note':'Engineering note','plan':'Planning proposal'}.items()]}
