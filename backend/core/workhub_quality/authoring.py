"""Manual/guided drafting, authorized reuse and record-backed engineering trace."""
from copy import deepcopy
import json
from fastapi import HTTPException
from . import store, documents, configuration, checks
from .store import hub, pi, text

SECTIONS={
 'frd':['Existing machine behavior','Proposed machine behavior','PLC & HMI functions','Alarms & interlocks','Open clarifications'],
 'corrections':['Existing behavior','Observed problem','Expected behavior','Required correction','Assigned engineer','Modified PLC/HMI references','Before evidence','After evidence','Impact analysis','Implementation notes','Verification results','Review and closure'],
 'test':['Validation objective','Test environment','Validation scope','Reference documents','Findings and deviations'],
 'fat':['Test scope','Prerequisites','Test environment','Deviations','Authorized sign-off'],
 'quality':['FRD revision verification','Correction note disposition','Test report review','FAT evidence verification','Outstanding issues','Reviewer comments'],
 'closure':['Completion summary','Final deliverables','Document revisions','Handover information','Open issues','Closure remarks','Approval fields'],
}

def blank(stage):
    if stage not in SECTIONS:raise HTTPException(400,'Choose a controlled document type.')
    return {'summary':'','purpose':'','scope':'','acceptance_summary':'','requirements':[],'changes':[],'cases':[],
            'sources':[],'file_ids':[],'sections':[{'heading':h,'text':''} for h in SECTIONS[stage]]}

def library_access(db,pid,user):
    p=hub.item(db,pid)
    if p.get('is_document_space'):
        from backend.core.workhub_document_spaces import authorize
        return authorize(db,p,user,allow_library=True)
    return hub.contribute(db,pid,user)

def prepare_related(user,pid):
    """Reuse saved requirements; never record execution results or approval."""
    store.initialize();results=[]
    with hub.db() as db:
        p=store.project(db,pid,user,True)
        frd=store.control(db,pid,'frd');native=store.native(db,frd);rid=native['current_revision']
        revision=store.revision(db,frd['id'],rid);content=pi.revision(db,rid,frd['document_id'])['content']
        requirements=[r for r in content.get('requirements',[]) if r.get('change')!='removed_proposed']
        if not requirements:raise HTTPException(400,'Add the FRD requirements first.')
        existing={r['stage']:dict(r) for r in db.execute('SELECT * FROM qc_documents WHERE project_id=?',(pid,))}
    source='FRD-'+rid
    for stage in ('test','fat','closure'):
        if stage in existing:
            results.append({'stage':stage,'control_id':existing[stage]['id'],'existing':True});continue
        draft=blank(stage);draft.update(summary=content.get('summary') or content.get('purpose') or p['title'],purpose=content.get('purpose',''),scope=content.get('scope',''))
        draft['sources']=[{'id':source,'type':'frd_revision','label':frd['number']+' / '+revision['label'],'text':'Source SHA-256 '+revision['content_hash'],'revision_id':rid,'sha256':revision['content_hash']}]
        if stage in {'test','fat'}:
            draft['cases']=[{'id':('TC-' if stage=='test' else 'FAT-')+str(i+1).zfill(3),
                'objective':r.get('title') or r['id'],'procedure':'Verify the following requirement under the authorized test conditions: '+(r.get('description') or r.get('title') or r['id']),
                'expected_result':r.get('expected_behavior') or r.get('acceptance_criteria') or '',
                'acceptance_criteria':r.get('acceptance_criteria') or '', 'requirement_ids':[r['id']],'source_ids':[source],'mandatory':r.get('mandatory',True)} for i,r in enumerate(requirements)]
            values={'Validation objective':content.get('purpose') or content.get('summary',''),'Validation scope':content.get('scope',''),
                    'Reference documents':frd['number']+' / '+revision['label'],'Test scope':content.get('scope',''),
                    'Prerequisites':'Review the current FRD '+frd['number']+' / '+revision['label']+' and confirm the test setup before execution.'}
            draft['sections']=[{**s,'text':values.get(s['heading'],'')} for s in draft['sections']]
            draft['file_ids']=content.get('file_ids',[])
            draft['field_files']={}
            for case,requirement in zip(draft['cases'],requirements):
                for target,original in [('objective','title'),('procedure','description'),('expected_result','expected_behavior' if requirement.get('expected_behavior') else 'acceptance_criteria'),('acceptance_criteria','acceptance_criteria')]:
                    linked=content.get('field_files',{}).get('requirement/'+requirement['id']+'/'+original,[])
                    if linked:draft['field_files']['case/'+case['id']+'/'+target]=linked
        else:
            draft['sections']=[{'heading':'Completion summary','text':content.get('scope') or p['title']},
                {'heading':'Final deliverables','text':'FRD, Validation Test Report and FAT for '+p['title']},
                {'heading':'Open issues','text':'Testing, document review, approvals and handover remain to be confirmed.'},
                {'heading':'Handover information','text':''},{'heading':'Closure remarks','text':''}]
        result=documents.draft(user,pid,stage,draft,'Prepared from saved FRD '+revision['label'],generated_by='frd-derived:'+rid+':'+revision['content_hash']+':'+stage,frd_revision=rid)
        results.append({'stage':stage,**result,'existing':False})
    notice='Drafts are ready to edit. Actual test results and authorized review are still required.'
    return {'documents':results,'notice':notice,'notices':[notice]}


def create(user,pid,payload):
    """Create once; opening a template never overwrites an existing draft."""
    store.initialize();stage=payload.get('stage')
    if stage=='mom':return create_mom(user,pid,payload)
    content=blank(stage)
    with hub.db(True) as db:
        p=store.project(db,pid,user,True)
        if p['stage']=='released':raise HTTPException(409,'Reopen this project before creating documents.')
        store.ensure_project(db,p,user);documents.adopt_existing(db,p,user)
        existing=db.execute('SELECT * FROM qc_documents WHERE project_id=? AND stage=?',(pid,stage)).fetchone()
        if existing:
            if payload.get('library_revision_id'):raise HTTPException(409,'This project already has this document. Create a controlled revision before importing different source text.')
            if payload.get('file_ids'):
                doc=dict(existing);rev=store.revision(db,doc['id'],store.native(db,doc)['current_revision'])
                content=pi.revision(db,rev['id'],doc['document_id'])['content']
                content['file_ids']=list(dict.fromkeys(content.get('file_ids',[])+documents.file_ids(db,pid,payload['file_ids'])))
                documents._save(db,user,p,doc,rev,documents.clean_content(db,pid,stage,content),rev['version'])
            return {'control_id':existing['id'],'revision_id':store.native(db,dict(existing))['current_revision'],'existing':True}
        source_id=payload.get('library_revision_id');provenance=None
        if source_id:
            row=db.execute('SELECT d.*,r.id AS source_revision FROM qc_documents d JOIN qc_revisions r ON r.control_id=d.id WHERE r.id=? AND d.stage=? AND r.status IN (\'approved\',\'released\')',(source_id,stage)).fetchone()
            if not row:raise HTTPException(404,'Choose an approved revision of this document type.')
            source=dict(row);library_access(db,source['project_id'],user)
            rev=store.revision(db,source['id'],source_id);original=pi.revision(db,source_id,source['document_id'])['content']
            content=deepcopy(original)
            for section in content.get('sections',[]):
                if section.get('heading') in {'Before evidence','After evidence','Verification results','Review and closure','Authorized sign-off','Reviewer comments','Approval fields','Completion summary','Handover information','Closure remarks'}:section['text']=''
            source_ref='LIBRARY-'+source_id
            # Copy editable text and a revision reference, never signatures, files or executions.
            for key in ('file_ids','sources'):content[key]=[]
            content['sources']=[{'id':source_ref,'type':'library_reference','label':source['number']+' / '+rev['label'],'text':'Approved library source SHA-256 '+rev['content_hash']+'. Reused text requires project-specific review.'}]
            for key in ('requirements','changes','cases'):
                for row in content.get(key,[]):
                    for field in ('execution','outcome','native_run_id'):row.pop(field,None)
                    row['source_ids']=[source_ref]
                    if key!='requirements':row['requirement_ids']=[]
            if content.get('flowchart'):
                content['flowchart']['sources']=content['sources'];content['flowchart'].pop('reviewed_requirements_hash',None)
                for node in content['flowchart'].get('nodes',[]):node.setdefault('data',{})['source_ids']=[source_ref]
            provenance={'project_id':source['project_id'],'document_id':source['document_id'],'revision_id':source_id,'sha256':rev['content_hash']}
        elif payload.get('from_project') is True:
            state=store.policy_row(db,p);content['summary']=p.get('description') or ''
            if stage=='frd':content['scope']=state['context'].get('scope') or p.get('description') or ''
        content=documents.clean_content(db,pid,stage,content)
        content['file_ids']=documents.file_ids(db,pid,payload.get('file_ids',[]))
        doc=documents.create_control(db,p,user,stage,initial_content=content)
        rid=store.native(db,doc)['current_revision']
        frd=db.execute("SELECT n.approved_revision FROM qc_documents q JOIN pi_documents n ON n.id=q.document_id WHERE q.project_id=? AND q.stage='frd'",(pid,)).fetchone()
        baseline=checks.baseline(db,p,stage=='closure') if stage in {'quality','closure'} else None
        db.execute('UPDATE qc_revisions SET frd_revision_id=?,baseline=?,reason=? WHERE id=?',(frd[0] if frd else None,baseline,'Reused approved library text' if source_id else 'Manual structured template',rid))
        store.audit(db,user,pid,'library_draft_created' if source_id else 'manual_draft_created',provenance or {'from_project':payload.get('from_project') is True},doc['id'],rid)
        return {'control_id':doc['id'],'revision_id':rid,'existing':False}


def create_mom(user,pid,payload):
    with hub.db(True) as db:
        p=store.project(db,pid,user,True)
        if p['stage']=='released':raise HTTPException(409,'Reopen the project before creating documents.')
        request_id=text(payload.get('request_id',''),80,True)
        content={'project_name':p['title'],'meeting_subject':'','meeting_date':None,'participants':[],
                 'discussion_summary':[],'decisions':[],'engineering_requirements':[],'actions':[],'clarifications':[],'sources':[]}
        if payload.get('library_revision_id'):
            raw=db.execute("SELECT r.*,d.project_id,d.kind,d.title FROM pi_revisions r JOIN pi_documents d ON d.id=r.document_id WHERE r.id=? AND r.status='approved' AND d.kind='mom'",(payload['library_revision_id'],)).fetchone()
            if not raw:raise HTTPException(404,'Choose an approved MOM revision.')
            library_access(db,raw['project_id'],user);content=json.loads(raw['content'])
            content.update(project_name=p['title'],meeting_date=None,participants=[],sources=[])
            for name in ('discussion_summary','decisions','engineering_requirements','actions','clarifications'):
                for row in content.get(name,[]):
                    row['source_ids']=[]
                    if name=='actions':row.update(responsible=None,target_date=None)
            content['sources']=[{'id':'LIBRARY-'+raw['id'],'label':raw['title']+' / revision '+str(raw['number']),'text':'Reused source wording requires review for this meeting. Source SHA-256 '+store.digest(json.loads(raw['content']))}]
        files=documents.file_ids(db,pid,payload.get('file_ids',[]))
        pi.validate_content('mom',content)
        doc,rev=pi.create_document(db,user,pid,'mom','Minutes of Meeting',content,file_id=files[0] if files else None,generated_by='manual:'+str(user['id'])+':'+request_id)
        if not db.execute('SELECT 1 FROM wh_document_numbers WHERE document_id=?',(doc['id'],)).fetchone():
            from .branding import numbering
            setting=numbering(db,p,configuration.current(db));setting['configuration']['codes']['mom']='MOM'
            number=configuration.allocate(db,'mom',setting)
            db.execute('INSERT INTO wh_document_numbers VALUES(?,?,?)',(doc['id'],number,store.bounded(setting['configuration'])))
        if files and rev['status']=='draft':
            old=pi.revision(db,rev['id'],doc['id'])['content'];old['file_ids']=list(dict.fromkeys(old.get('file_ids',[])+files))
            db.execute('UPDATE pi_revisions SET file_id=COALESCE(file_id,?),content=? WHERE id=?',(files[0],store.bounded(old),rev['id']))
        return {'document_id':doc['id'],'revision_id':rev['id'],'existing':False}


def readiness(db,p,doc,rev):
    c=pi.revision(db,rev['id'],doc['document_id'])['content'];issues=[];stage=doc['stage']
    if rev['status'] in {'approved','released','superseded','archived'}:
        return {'state':'Approved','issues':['This exact revision is read-only. Status: '+rev['status'].replace('_',' ')]}
    if rev['status'] in {'correction_required','rejected'}:
        comment=pi.revision(db,rev['id'],doc['document_id']).get('review_comment')
        issues.append(comment or 'Address the recorded reviewer feedback before resubmitting.')
    if stage=='frd':
        if not c.get('requirements'):issues.append('Add functional requirements.')
        for r in c.get('requirements',[]):
            if not r.get('title') or not r.get('acceptance_criteria'):issues.append(r['id']+': enter a title and acceptance criterion.')
            if r.get('change') in {'unresolved','removed_proposed'}:issues.append(r['id']+': resolve the proposal before review.')
        if c.get('flowchart') and c['flowchart'].get('needs_review',True):issues.append('Review the flowchart against the saved requirements.')
    if stage in {'test','fat'}:
        for source in c.get('sources',[]):
            if source.get('type')=='frd_revision' and source.get('sha256'):
                original=db.execute('SELECT content_hash FROM qc_revisions WHERE id=?',(source.get('revision_id'),)).fetchone()
                if not original or original[0]!=source['sha256']:issues.append('The source FRD content changed. Prepare a new revision and review the test coverage.')
        if not c.get('cases'):issues.append('Add test cases with procedures and expected results.')
        for case in c.get('cases',[]):
            if not all(case.get(k) for k in ('objective','procedure','expected_result','acceptance_criteria')):issues.append(case['id']+': complete the procedure and acceptance details.')
        frd=db.execute("SELECT n.approved_revision FROM qc_documents d JOIN pi_documents n ON n.id=d.document_id WHERE d.project_id=? AND d.stage='frd'",(p['id'],)).fetchone()
        if frd and frd[0]!=rev['frd_revision_id']:issues.append('The approved FRD changed. Prepare a revision against its current baseline.')
    if stage=='corrections' and not c.get('changes') and c.get('applicability')!='not_applicable':issues.append('Describe corrections or record why they are not applicable.')
    if stage=='corrections' and c.get('applicability')=='not_applicable' and not c.get('na_reason'):issues.append('Explain why corrections are not applicable.')
    if stage in {'quality','closure'}:
        issues.extend(b['title'] for b in checks.report(db,p,stage=='closure')['blockers'] if b['code']!='approval:closure')
        if rev['baseline']!=checks.baseline(db,p,stage=='closure'):issues.append('Project records changed after this review draft was prepared.')
    issues=list(dict.fromkeys(issues))
    state='Returned' if rev['status'] in {'correction_required','rejected'} else 'Missing Information' if issues else 'Ready for Review' if rev['status']=='in_review' or rev['confirmed_at'] and rev['confirmed_hash']==rev['content_hash'] else 'Draft'
    if not issues:issues=['Awaiting the assigned reviewer.' if rev['status']=='in_review' else 'Review and confirm the saved content before submitting for approval.']
    return {'state':state,'issues':issues}


def trace(user,pid,requirement_id):
    store.initialize()
    with hub.db() as db:
        hub.contribute(db,pid,user);items=[];requirement=None
        for raw in db.execute('SELECT * FROM qc_documents WHERE project_id=? ORDER BY stage',(pid,)):
            d=dict(raw);rid=store.native(db,d)['current_revision']
            if not rid:continue
            rev=store.detail(db,d,store.revision(db,d['id'],rid));c=rev['content']
            if d['stage']=='frd':requirement=next((r for r in c.get('requirements',[]) if r['id']==requirement_id),None)
            for kind in ('changes','cases'):
                for row in c.get(kind,[]):
                    if requirement_id in row.get('requirement_ids',[]):
                        items.append({'stage':d['stage'],'document_number':d['number'],'control_id':d['id'],'revision_id':rid,'revision':rev['label'],'status':rev['status'],'item':row,'source_references':[s for s in c.get('sources',[]) if s['id'] in row.get('source_ids',[])]})
        if not requirement:raise HTTPException(404,'Requirement not found in this project FRD.')
        return {'requirement':requirement,'links':items,'notice':'Only explicit saved requirement links are shown. Missing links do not prove the work was performed.'}
