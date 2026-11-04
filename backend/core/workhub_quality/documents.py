"""Immutable approved revisions, autosaved drafts and authenticated test execution."""
from copy import deepcopy
import json
import re
from datetime import datetime,timezone
from fastapi import HTTPException
from . import store,configuration
from .store import hub,pi,identity,timestamp,text
ANY_CURRENT=object()

def requirements_hash(requirements):
    return store.digest([{k:r.get(k) for k in ('id','title','description','trigger','expected_behavior','subsystem','acceptance_criteria','mandatory')} for r in requirements])

def _list(value,limit=2000):
    if not isinstance(value,list) or len(value)>limit:raise HTTPException(400,'Use a bounded list of structured document items.')
    return value
def file_ids(db,pid,values):
    ids=_list(values,100)
    for key in ids:
        if not isinstance(key,str) or not db.execute('SELECT 1 FROM files WHERE id=? AND project_id=?',(key,pid)).fetchone():raise HTTPException(400,'Choose existing files in this project.')
    return list(dict.fromkeys(ids))

def clean_content(db,pid,stage,content):
    if not isinstance(content,dict):raise HTTPException(400,'Provide structured document content.')
    store.bounded(content);result={'summary':text(content.get('summary',''),12000),
      'file_ids':file_ids(db,pid,content.get('file_ids',[])),'requirements':[],'changes':[],'cases':[],
      'sections':[],'sources':[],'missing':[],'flowchart':None,
      'applicability':content.get('applicability','applicable'),'na_reason':text(content.get('na_reason',''),2000)}
    if 'document_info' in content:
        from backend.core.workhub_document_information import clean
        result['document_info']=clean(content['document_info'])
    from backend.core.workhub_document_information import links
    linked=links(db,pid)
    if linked is not None:result['document_links']=linked
    if stage=='frd':
        for k in ('purpose','background','expected_outcome','scope','acceptance_summary'):result[k]=text(content.get(k) or '',12000)
        criteria=content.get('acceptance_items')
        # The text field remains compatible with older forms and drafting tools.
        # New forms update the checklist and its summary together.
        if isinstance(criteria,list) and 'acceptance_summary' in content and result['acceptance_summary']!='\n'.join(str(c.get('text','')) for c in criteria if isinstance(c,dict)):
            criteria=None
        if criteria is None:criteria=[{'id':'AC-'+str(i+1).zfill(3),'text':v,'confirmed':False} for i,v in enumerate(result['acceptance_summary'].splitlines()) if v.strip()]
        result['acceptance_items']=[];seen_criteria=set()
        for i,item in enumerate(_list(criteria,200)):
            if not isinstance(item,dict):raise HTTPException(400,'Provide structured acceptance criteria.')
            key=item.get('id') or 'AC-'+str(i+1).zfill(3)
            if not isinstance(key,str) or not re.fullmatch(r'AC-\d{3,6}',key) or key in seen_criteria:raise HTTPException(400,'Acceptance criteria need unique AC-001 style IDs.')
            if type(item.get('confirmed',False)) is not bool:raise HTTPException(400,'Choose whether the acceptance criterion wording is confirmed.')
            seen_criteria.add(key);result['acceptance_items'].append({'id':key,'text':text(item.get('text') or '',8000),'confirmed':item.get('confirmed',False)})
        if criteria is not None:result['acceptance_summary']='\n'.join(item['text'] for item in result['acceptance_items'])
    if stage in {'test','fat'}:
        from .report_templates import clean
        result=clean(db,pid,content,result);result['report_type']=stage
    if result['applicability'] not in {'applicable','not_applicable'} or result['applicability']=='not_applicable' and stage!='corrections':raise HTTPException(400,'Only Correction Notes can be marked Not Applicable. Use a formal disposition for other exceptions.')
    for raw in _list(content.get('sources',[]),4000):
        if not isinstance(raw,dict) or not isinstance(raw.get('id'),str):raise HTTPException(400,'Sources need stable source IDs.')
        # Links are built by the server, never taken from model-provided URLs.
        source={key:raw.get(key) for key in ('id','type','file_id','document_id','revision_id','run_id','issue_id','event_id','label','text','page','sha256','meeting_id','transcript_version','segment_id','upstream_sources','filename','start','end','paragraph','sheet','cell') if raw.get(key) is not None}
        if source.get('file_id'):
            file_ids(db,pid,[source['file_id']]);source['sha256']=db.execute('SELECT sha256 FROM files WHERE id=?',(source['file_id'],)).fetchone()[0]
        if source.get('meeting_id'):pi.meeting(db,source['meeting_id'],pid)
        if source.get('document_id'):
            pi.document(db,source['document_id'],pid)
            if source.get('revision_id'):pi.revision(db,source['revision_id'],source['document_id'])
        if source.get('run_id') and not db.execute('SELECT 1 FROM engineering_runs WHERE project_id=? AND run_id=?',(pid,source['run_id'])).fetchone():raise HTTPException(400,'Use validation runs shared with this project.')
        source['text']=text(str(source.get('text','')),40000);source['label']=text(str(source.get('label',source['id'])),300)
        result['sources'].append(source)
    known={s['id'] for s in result['sources']}
    def refs(raw):
        ids=_list(raw.get('source_ids',[]),200)
        if any(not isinstance(key,str) or key not in known for key in ids):raise HTTPException(400,'A document item references an unavailable source. Regenerate or correct the reference.')
        return list(dict.fromkeys(ids))
    def requirement_ids(raw):
        ids=_list(raw.get('requirement_ids',[]),2000)
        if any(not isinstance(key,str) or not re.fullmatch('(?:FR|REQ)-\\d{3,6}',key) for key in ids):raise HTTPException(400,'Use requirement IDs from the approved FRD.')
        return list(dict.fromkeys(ids))
    if stage=='frd':
        seen=set()
        for r in _list(content.get('requirements',[])):
            if not isinstance(r,dict) or not re.fullmatch('(?:FR|REQ)-\\d{3,6}',str(r.get('id',''))) or r['id'] in seen:raise HTTPException(400,'Requirements need unique REQ-001 or FR-001 style IDs.')
            seen.add(r['id']);result['requirements'].append({'id':r['id'],**{k:text(r.get(k) or '',8000) for k in ('title','description','trigger','expected_behavior','subsystem','acceptance_criteria')},
              'source_ids':refs(r),'mandatory':bool(r.get('mandatory',True)),'category':text(r.get('category') or '',200),'source_label':text(r.get('source_label') or '',240),'priority':r.get('priority') if r.get('priority') in {'low','medium','high','urgent'} else 'medium',
              'status':r.get('status') if r.get('status') in {'open','in_review','confirmed'} else 'open',
              'change':r.get('change') if r.get('change') in {'new','modified','confirmed','removed_proposed','unresolved','unchanged'} else 'new'})
    for r in _list(content.get('changes',[])):
        if not isinstance(r,dict):raise HTTPException(400,'Provide structured correction notes.')
        result['changes'].append({'id':text(r.get('id',''),80,True),'summary':text(r.get('summary',''),8000,True),**{k:text(r.get(k) or '',8000) for k in ('existing_behavior','expected_behavior','plc_references','impact','before_evidence','after_evidence','verification')},'source_ids':refs(r),'requirement_ids':requirement_ids(r)})
    seen=set()
    for r in _list(content.get('cases',[])):
        if not isinstance(r,dict):raise HTTPException(400,'Provide structured test cases.')
        key=text(r.get('id',''),80,True)
        if key in seen:raise HTTPException(400,'Test case IDs must be unique.')
        seen.add(key);native=r.get('native_run_id') or None
        if native and not db.execute('SELECT 1 FROM engineering_runs WHERE project_id=? AND run_id=?',(pid,native)).fetchone():raise HTTPException(400,'A native result must belong to this project.')
        result['cases'].append({'id':key,**{k:text(r.get(k) or '',8000) for k in ('objective','procedure','expected_result','acceptance_criteria')},
          'requirement_ids':requirement_ids(r),'source_ids':refs(r),'mandatory':bool(r.get('mandatory',True)),'native_run_id':native})
    from .field_attachments import section_id,normalize
    section_ids=set()
    for i,r in enumerate(_list(content.get('sections',[]),40)):
        if not isinstance(r,dict):raise HTTPException(400,'Provide a heading and text for each template section.')
        key=section_id(r.get('id'),i)
        if key in section_ids:raise HTTPException(400,'Document sections need unique identifiers.')
        section_ids.add(key)
        result['sections'].append({'id':key,'heading':text(r.get('heading',''),180,True),'text':text(r.get('text',''),12000)})
    for r in _list(content.get('missing',[]),500):result['missing'].append(text(str(r),1000,True))
    if content.get('flowchart'):
        flow=deepcopy(content['flowchart']);pi.validate_content('flowchart',flow);result['flowchart']=flow
        if stage=='frd':
            ids={r['id'] for r in result['requirements']}
            for n in flow.get('nodes',[]):
                links=n.get('data',{}).get('requirement_ids',[])
                if not isinstance(links,list) or any(v not in ids for v in links):raise HTTPException(400,'Flowchart nodes must reference requirements retained in this FRD revision.')
            flow['requirements_hash']=requirements_hash(result['requirements'])
            flow['needs_review']=flow.get('reviewed_requirements_hash')!=flow['requirements_hash']
    result=normalize(db,pid,content,result)
    if content.get('studio'):
        from backend.core.workhub_studio.bindings import synchronize
        from backend.core.workhub_studio.store import validate_media
        result=synchronize({**result,'studio':content['studio']});validate_media(db,pid,result)
    return result

def create_control(db,p,user,stage,existing=None,initial_content=None,generated_by=None):
    from .branding import numbering
    setting=numbering(db,p,configuration.current(db));config=setting['configuration'];now=timestamp();key=identity()
    if not existing:
        kind='frd' if stage=='frd' else 'note'
        title='Test Report' if stage=='test' and p.get('document_type')=='test_report' else config['templates'][stage]['title']
        doc,rev=pi.create_document(db,user,p['id'],kind,title,initial_content if initial_content is not None else {'requirements':[],'sources':[]} if stage=='frd' else {},generated_by=generated_by,quality_control=True)
    else:doc=existing;rev=None
    is_template=db.execute("SELECT 1 FROM ds_template_drafts WHERE scope_id=?",(p['id'],)).fetchone()
    number='TEMPLATE-'+key[:20].upper() if is_template else configuration.allocate(db,stage,setting)
    db.execute('INSERT INTO qc_documents VALUES(?,?,?,?,?,?,?,?)',(key,p['id'],stage,doc['id'],number,setting['version'],store.bounded(config),now))
    result=store.control(db,p['id'],key)
    store.audit(db,user,p['id'],'document_registered',{'document_number':number,'native_document_id':doc['id'],'stage':stage},key)
    # Import existing native identities and actual decisions. No new approval is invented.
    for raw in db.execute('SELECT * FROM pi_revisions WHERE document_id=? ORDER BY number',(doc['id'],)).fetchall():
        r=dict(raw);approved=bool(r['reviewed_by'] and r['reviewed_at'] and r['status']=='approved')
        status='approved' if approved else 'correction_required' if r['status']=='changes_requested' else 'draft'
        content=json.loads(r['content']);h=store.digest(content)
        _insert_revision(db,result,r,user,config,status,'Existing Project Intelligence revision' if existing else 'Initial draft',h)
        if existing and r['status']=='review':
            db.execute("UPDATE pi_revisions SET status='draft' WHERE id=?",(r['id'],))
            store.audit(db,user,p['id'],'existing_pending_review_requires_controlled_confirmation',{'previous_reviewer_id':r['reviewer_id']},key,r['id'])
        if approved:
            db.execute('UPDATE qc_revisions SET confirmed_by=?,confirmed_at=?,confirmed_hash=?,reviewed_by=?,reviewed_at=?,approved_by=?,approved_at=?,reviewer_id=?,approver_id=? WHERE id=?',
               (r['reviewed_by'],r['reviewed_at'],h,r['reviewed_by'],r['reviewed_at'],r['reviewed_by'],r['reviewed_at'],r['reviewer_id'],r['reviewer_id'],r['id']))
            store.audit(db,user,p['id'],'existing_approval_adopted',{'source_reviewed_by':r['reviewed_by'],'source_reviewed_at':r['reviewed_at']},key,r['id'])
    return result

def _insert_revision(db,doc,r,user,config,status,reason,h,frd_revision=None,baseline=None):
    template=config['templates'][doc['stage']]
    db.execute('INSERT INTO qc_revisions(id,control_id,number,label,status,reason,owner_id,template_version,template_snapshot,frd_revision_id,content_hash,baseline,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
      (r['id'],doc['id'],r['number'],configuration.revision_label(config,r['number']),status,reason,r['created_by'],template['version'],store.bounded(template),frd_revision,h,baseline,r['created_at']))
    db.execute('INSERT INTO qc_draft_history VALUES(?,?,?,?,?,?,?)',(identity(),r['id'],1,r['content'] if isinstance(r['content'],str) else store.bounded(r['content']),h,user['id'],timestamp()))

def adopt_existing(db,p,user):
    if db.execute("SELECT 1 FROM qc_documents WHERE project_id=? AND stage='frd'",(p['id'],)).fetchone():return
    existing=db.execute("SELECT * FROM pi_documents WHERE project_id=? AND kind='frd' ORDER BY created_at LIMIT 1",(p['id'],)).fetchone()
    if existing:create_control(db,p,user,'frd',dict(existing))

def draft(user,pid,stage,content,reason='',generated_by=None,expected_current=ANY_CURRENT,frd_revision=None,baseline=None):
    store.initialize()
    if stage not in store.STAGES:raise HTTPException(400,'Choose a supported engineering stage.')
    with hub.db(True) as db:
        p=store.project(db,pid,user,True);store.ensure_project(db,p,user);adopt_existing(db,p,user)
        if p['stage']=='released':raise HTTPException(409,'Reopen the project before preparing new controlled documents.')
        clean=clean_content(db,pid,stage,content)
        row=db.execute('SELECT * FROM qc_documents WHERE project_id=? AND stage=?',(pid,stage)).fetchone()
        if not row:
            if expected_current is not ANY_CURRENT and expected_current is not None:raise HTTPException(409,'The source revision changed during preparation.')
            doc=create_control(db,p,user,stage,initial_content=clean,generated_by=generated_by)
            rid=store.native(db,doc)['current_revision']
            db.execute('UPDATE qc_revisions SET frd_revision_id=?,baseline=?,reason=? WHERE id=?',(frd_revision,baseline,reason or 'Prepared from existing project records',rid))
            store.audit(db,user,pid,'draft_prepared',{'generated_by':generated_by,'source_count':len(clean['sources'])},doc['id'],rid)
            return {'control_id':doc['id'],'revision_id':rid}
        doc=dict(row)
        native=store.native(db,doc)
        if generated_by:
            old=db.execute('SELECT id FROM pi_revisions WHERE document_id=? AND generated_by=?',(doc['document_id'],generated_by)).fetchone()
            if old:return {'control_id':doc['id'],'revision_id':old['id']}
        if expected_current is not ANY_CURRENT and native['current_revision']!=expected_current:raise HTTPException(409,'This document changed while preparation was running. Keep the newer work and generate again.')
        current=store.revision(db,doc['id'],native['current_revision']) if native['current_revision'] else None
        setting=configuration.current(db);config=setting['configuration']
        if current and current['status'] in {'draft','correction_required'} and not generated_by:
            return _save(db,user,p,doc,current,clean,current['version'])
        if current and current['status'] in {'approved','released','superseded','archived','rejected','in_review'} and not reason.strip():raise HTTPException(400,'Record the reason for preparing a controlled new revision.')
        # Do not silently replace an in-progress engineer draft with generated text.
        if current and current['status'] in {'draft','correction_required'} and generated_by:
            old_content=pi.revision(db,current['id'],doc['document_id'])['content']
            if not generated_by.startswith('revision:') and (current['version']>1 or current['confirmed_at']):raise HTTPException(409,'A reviewed or edited draft already exists. Keep it, or explicitly create a new revision before generating.')
        _,rev=pi.create_document(db,user,pid,'frd' if stage=='frd' else 'note',config['templates'][stage]['title'],clean,
            document_id=doc['document_id'],expected_revision=native['current_revision'],generated_by=generated_by,quality_control=True)
        h=store.digest(clean);_insert_revision(db,doc,rev,user,config,'draft',text(reason or 'Prepared from existing project records',2000,True),h,frd_revision,baseline)
        store.audit(db,user,pid,'draft_prepared',{'generated_by':generated_by,'source_count':len(clean['sources']),'reason':reason},doc['id'],rev['id'])
        return {'control_id':doc['id'],'revision_id':rev['id']}

def _save(db,user,p,doc,rev,content,version):
    store.editable(db,doc,rev,user,version)
    from backend.core.workhub_studio.store import guard
    guard(db,user,rev['id'],pi.revision(db,rev['id'],doc['document_id'])['content'],content)
    h=store.digest(content)
    if h==rev['content_hash']:return {'control_id':doc['id'],'revision_id':rev['id'],'version':rev['version'],'content_hash':h}
    db.execute('UPDATE pi_revisions SET content=? WHERE id=?',(store.bounded(content),rev['id']))
    db.execute('UPDATE qc_revisions SET version=version+1,content_hash=?,confirmed_by=NULL,confirmed_at=NULL,confirmed_hash=NULL WHERE id=?',(h,rev['id']))
    db.execute('UPDATE pi_documents SET updated_at=? WHERE id=?',(timestamp(),doc['document_id']))
    db.execute('INSERT INTO qc_draft_history VALUES(?,?,?,?,?,?,?)',(identity(),rev['id'],rev['version']+1,store.bounded(content),h,user['id'],timestamp()))
    store.audit(db,user,p['id'],'draft_modified',{'before_hash':rev['content_hash'],'after_hash':h,'version':rev['version']+1},doc['id'],rev['id'])
    from .authoring import readiness
    return {'control_id':doc['id'],'revision_id':rev['id'],'version':rev['version']+1,'content_hash':h,'readiness':readiness(db,p,doc,store.revision(db,doc['id'],rev['id']))}

def save(user,pid,key,payload):
    store.initialize()
    with hub.db(True) as db:
        doc=store.control(db,pid,key);rev=store.revision(db,doc['id'],payload.get('revision_id'));p=store.editable(db,doc,rev,user,payload.get('version'))
        if type(payload.get('version')) is not int:raise HTTPException(400,'Include the current draft version.')
        return _save(db,user,p,doc,rev,clean_content(db,pid,doc['stage'],payload.get('content')),payload['version'])

def confirm_flowchart(user,pid,key,payload):
    store.initialize()
    if type(payload.get('version')) is not int:raise HTTPException(400,'Include the current draft version.')
    with hub.db(True) as db:
        doc=store.control(db,pid,key);rev=store.revision(db,doc['id'],payload.get('revision_id'));p=store.editable(db,doc,rev,user,payload.get('version'))
        content=pi.revision(db,rev['id'],doc['document_id'])['content']
        if doc['stage']!='frd' or not (content.get('flowchart') or {}).get('nodes'):raise HTTPException(400,'Save an FRD flowchart with nodes before reviewing it.')
        if payload.get('confirmed') is not True:raise HTTPException(400,'Confirm the diagram matches its linked requirements.')
        content['flowchart']['reviewed_requirements_hash']=requirements_hash(content['requirements'])
        result=_save(db,user,p,doc,rev,clean_content(db,pid,'frd',content),payload['version'])
        store.audit(db,user,pid,'flowchart_reviewed',{'requirements_hash':content['flowchart']['reviewed_requirements_hash']},doc['id'],rev['id'])
        return result

def execute(user,pid,key,payload):
    store.initialize()
    if type(payload.get('version')) is not int:raise HTTPException(400,'Include the current revision version.')
    with hub.db(True) as db:
        doc=store.control(db,pid,key);rev=store.revision(db,doc['id'],payload.get('revision_id'));p=store.editable(db,doc,rev,user,payload.get('version'))
        if doc['stage'] not in {'test','fat'}:raise HTTPException(400,'Record executions in the Test Report or FAT.')
        content=pi.revision(db,rev['id'],doc['document_id'])['content'];case=next((r for r in content.get('cases',[]) if r['id']==payload.get('case_id')),None)
        if not case:raise HTTPException(404,'Choose a test case in this revision.')
        outcome=payload.get('outcome')
        if outcome not in {'pass','fail','blocked','not_run','not_applicable'}:raise HTTPException(400,'Choose an actual execution outcome.')
        actual=text(payload.get('actual',''),8000,outcome in {'pass','fail'});observations=text(payload.get('observations',''),8000,outcome in {'blocked','not_applicable'})
        ids=file_ids(db,pid,payload.get('file_ids',[]));policy=store.policy_row(db,p)['policy']
        if outcome=='pass' and policy['require_test_evidence'] and not ids and not case.get('native_run_id'):raise HTTPException(400,'Attach existing test evidence or link the native validation record before recording a pass.')
        actual_time=payload.get('executed_at') or ''
        if actual_time:
            try:
                when=datetime.fromisoformat(actual_time.replace('Z','+00:00'))
                if when.tzinfo is None:when=when.replace(tzinfo=timezone.utc)
                if when>datetime.now(timezone.utc):raise ValueError()
                actual_time=when.isoformat()
            except (TypeError,ValueError):raise HTTPException(400,'Use an actual execution date/time that is not in the future.') from None
        key_exec=identity();now=timestamp()
        db.execute('INSERT INTO qc_executions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(key_exec,pid,rev['id'],case['id'],store.case_hash(case,rev['frd_revision_id']),outcome,actual,observations,store.bounded(ids),user['id'],actual_time,now))
        db.execute('UPDATE qc_revisions SET confirmed_by=NULL,confirmed_at=NULL,confirmed_hash=NULL,version=version+1 WHERE id=?',(rev['id'],))
        store.audit(db,user,pid,'test_execution_recorded',{'execution_id':key_exec,'case_id':case['id'],'outcome':outcome},doc['id'],rev['id'])
        return {'execution_id':key_exec,'version':rev['version']+1}

def acceptance(user,pid,key,payload):
    store.initialize()
    if type(payload.get('version')) is not int:raise HTTPException(400,'Include the current revision version.')
    with hub.db(True) as db:
        doc=store.control(db,pid,key);rev=store.revision(db,doc['id'],payload.get('revision_id'));store.editable(db,doc,rev,user,payload.get('version'))
        if doc['stage']!='fat':raise HTTPException(400,'Record customer acceptance against FAT.')
        status=payload.get('status')
        if status not in {'accepted','conditional','rejected'}:raise HTTPException(400,'Choose the recorded customer decision.')
        ids=file_ids(db,pid,payload.get('file_ids',[]))
        if not ids:raise HTTPException(400,'Link the actual customer acceptance record. No signature is generated by this app.')
        accepted=text(payload.get('accepted_at',''),40,True)
        try:
            when=datetime.fromisoformat(accepted.replace('Z','+00:00'))
            if when.tzinfo is None:when=when.replace(tzinfo=timezone.utc)
            if when>datetime.now(timezone.utc):raise ValueError()
        except ValueError:raise HTTPException(400,'Use the actual acceptance date, which cannot be in the future.') from None
        key_accept=identity();now=timestamp()
        db.execute('INSERT INTO qc_acceptances VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key_accept,pid,rev['id'],status,text(payload.get('customer',''),180,True),text(payload.get('representative',''),180,True),when.isoformat(),store.bounded(ids),text(payload.get('remarks',''),8000,status!='accepted'),user['id'],now))
        db.execute('UPDATE qc_revisions SET confirmed_by=NULL,confirmed_at=NULL,confirmed_hash=NULL,version=version+1 WHERE id=?',(rev['id'],))
        store.audit(db,user,pid,'customer_acceptance_recorded',{'acceptance_id':key_accept,'status':status},doc['id'],rev['id'])
        return {'id':key_accept,'version':rev['version']+1}
