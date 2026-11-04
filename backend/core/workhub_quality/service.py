"""Project document register, contextual actions, dispositions and human approvals."""
import json
from datetime import date
from fastapi import HTTPException
from . import store,configuration,documents,checks
from .store import hub,pi,identity,timestamp,text
from backend.core.workhub_intelligence import jobs as intelligence_jobs

def overview(user,pid):
    store.initialize()
    with hub.db(True) as db:
        p=store.project(db,pid,user);can_edit=True
        try:hub.contribute(db,pid,user)
        except HTTPException:can_edit=False
        if can_edit:
            store.ensure_project(db,p,user);documents.adopt_existing(db,p,user)
        report=checks.report(db,p,True);state=store.policy_row(db,p);register=[]
        for d in report['documents']:
            register.append({**d,'title':pi.document(db,d['document_id'],pid)['title'],'file_location':'/api/workhub/projects/'+pid+'/quality/documents/'+d['id']+'/export/pdf'})
        stage_states=[]
        frd=next((d for d in register if d['stage']=='frd'),None)
        for stage,title in store.STAGES.items():
            d=next((d for d in register if d['stage']==stage),None);complete=bool(d and d['current']);label=d['revision']['status'] if d and d['revision'] else 'Required' if stage in state['policy']['required_stages'] else 'Optional'
            if d and stage=='quality' and complete and not report['quality_approved']:complete=False;label='Review again - baseline changed'
            if d and stage in {'test','fat'} and complete and frd and d['revision']['frd_revision_id']!=frd['approved_revision']:complete=False;label='Outdated FRD baseline'
            if stage=='closure' and complete and p['stage']!='released':complete=False;label='Approved - awaiting project release'
            stage_states.append({'id':stage,'title':title,'required':stage in state['policy']['required_stages'],'document':d,'complete':complete,'display_status':label})
        from .branding import choices
        from backend.core.workhub_delivery import readiness
        return {'project':hub.public(p),'context':{**state['context'],**report['context']},'branding_choices':choices(db),'context_version':state['version'],'can_edit':can_edit,
          'stages':stage_states,'delivery':readiness(db,p),'can_manage':user['role']=='admin' or user['id'] in {p['owner_id'],p['created_by']},
          'register':register,'report':report,'users':hub.users(),
          'clarifications':[{**dict(r),'options':json.loads(r['options']),'source_refs':json.loads(r['source_refs'])} for r in db.execute('SELECT * FROM pi_clarifications WHERE project_id=? ORDER BY updated_at DESC LIMIT 500',(pid,))],
          'files':[dict(r) for r in db.execute('SELECT * FROM files WHERE project_id=? ORDER BY created_at DESC',(pid,))],
          'quality_tasks':[dict(r) for r in db.execute("SELECT id,title,owner_id,stage,version FROM items WHERE project_id=? AND type='task' AND work_phase='quality' ORDER BY created_at",(pid,))],
          'reference_documents':[dict(r) for r in db.execute('SELECT id,title,kind,current_revision,approved_revision FROM pi_documents WHERE project_id=? AND NOT EXISTS(SELECT 1 FROM qc_documents q WHERE q.document_id=pi_documents.id)',(pid,))],
          'jobs':intelligence_jobs.list_jobs(user,pid,50,kinds='quality')['jobs'],
          'packages':[dict(r) for r in db.execute('SELECT id,audience,number,baseline,sha256,created_by,created_at,final FROM qc_packages WHERE project_id=? ORDER BY created_at DESC',(pid,))],
          'waivers':[dict(r) for r in db.execute('SELECT * FROM qc_waivers WHERE project_id=? ORDER BY requested_at DESC',(pid,))],
          'audit':[{**dict(r),'detail':json.loads(r['detail'])} for r in db.execute('SELECT * FROM qc_audit WHERE project_id=? ORDER BY id DESC LIMIT 200',(pid,))]}

def get_document(user,pid,key,rid=None):
    store.initialize()
    with hub.db() as db:
        p=store.project(db,pid,user);doc=store.control(db,pid,key);native=store.native(db,doc)
        rev=store.revision(db,doc['id'],rid or native['current_revision'])
        from .authoring import readiness
        from backend.core.workhub_signoff import history
        can_delete=rev['id']==native['current_revision'] and p['stage']!='released' and rev['status']!='archived' and (user['role']=='admin' or user['id'] in {p['owner_id'],p['created_by'],native['created_by'],rev['owner_id']})
        return {'document':{**doc,'title':native['title']},'revision':store.detail(db,doc,rev),'can_delete':can_delete,'readiness':readiness(db,store.project(db,pid,user),doc,rev),
          'sign_offs':history(db,rev['id']),
          'approved_revision':store.detail(db,doc,store.revision(db,doc['id'],native['approved_revision'])) if native['approved_revision'] else None,
          'revisions':[dict(r) for r in db.execute('SELECT id,number,label,status,reason,owner_id,confirmed_by,confirmed_at,reviewer_id,approver_id,approved_by,approved_at,released_by,released_at,customer_safe,created_at FROM qc_revisions WHERE control_id=? ORDER BY number DESC',(doc['id'],))]}

def context(user,pid,payload):
    store.initialize()
    with hub.db(True) as db:
        p=store.project(db,pid,user,True);state=store.ensure_project(db,p,user)
        if payload.get('version')!=state['version']:raise HTTPException(409,'Project context changed. Reload before saving.')
        from .branding import link_context
        values=link_context(db,{**state['context'],**{k:text(payload.get(k,state['context'].get(k,'')) or '',8000 if k=='scope' else 180) for k in ('customer','machine','scope')}},payload)
        if 'fat_applicable' in payload:
            hub.manage(p,user)
            if type(payload['fat_applicable']) is not bool:raise HTTPException(400,'Choose whether FAT applies to this project.')
            values['fat_applicable']=payload['fat_applicable']
            values['fat_reason']=text(payload.get('fat_reason',''),2000,True)
        if p['stage']=='released':raise HTTPException(409,'Closed project context is historical. Reopen the project to revise it.')
        db.execute('UPDATE qc_projects SET context=?,version=version+1,updated_at=? WHERE project_id=?',(store.bounded(values),timestamp(),pid))
        store.audit(db,user,pid,'project_context_updated',{'before':state['context'],'after':values})
    return {'saved':True}

def rebaseline_policy(user,pid,payload):
    store.initialize()
    with hub.db(True) as db:
        p=store.project(db,pid,user,True);hub.manage(p,user);state=store.ensure_project(db,p,user)
        if p['stage']=='released':raise HTTPException(409,'Reopen this project before adopting a new procedure.')
        reason=text(payload.get('reason',''),2000,True);setting=configuration.current(db)
        policy=configuration.profile(setting['configuration'],p['kind'])
        if p['type']=='project' and policy.get('workflow_steps'):
            from backend.core.workhub_workflow import schema
            schema(db)
            linked={r[0] for r in db.execute('SELECT step_id FROM wh_workflow_steps WHERE project_id=?',(pid,))}
            if p['stage'] not in {'todo','development','blocked'} and any(s['id'] not in linked for s in policy['workflow_steps']):raise HTTPException(409,'Return the project to development before adopting a procedure with new work steps.')
        db.execute('UPDATE qc_projects SET policy=?,policy_version=?,project_type=?,version=version+1,updated_at=? WHERE project_id=?',
          (store.bounded(policy),setting['version'],p['kind'],timestamp(),pid))
        if p['type']=='project':
            from backend.core.workhub_workflow import create_steps
            create_steps(db,p,user)
        store.audit(db,user,pid,'procedure_rebaselined',{'previous_version':state['policy_version'],'version':setting['version'],'reason':reason})
    return {'saved':True}

def new_revision(user,pid,key,payload):
    store.initialize()
    with hub.db() as db:
        p=store.project(db,pid,user,True);doc=store.control(db,pid,key);current=store.native(db,doc)['current_revision'];rev=store.revision(db,doc['id'],current)
        if payload.get('revision_id')!=current:raise HTTPException(409,'Reload the current revision before creating its successor.')
        content=pi.revision(db,current,doc['document_id'])['content']
    result=documents.draft(user,pid,doc['stage'],content,text(payload.get('reason',''),2000,True),generated_by='revision:'+identity(),expected_current=current,frd_revision=rev['frd_revision_id'],baseline=rev['baseline'])
    with hub.db(True) as db:
        ex=store.executions(db,current)
        for case in content.get('cases',[]):
            old=ex.get(case['id'])
            if old and old['specification_hash']==store.case_hash(case,rev['frd_revision_id']):
                db.execute('INSERT OR REPLACE INTO qc_execution_reuse VALUES(?,?,?)',(result['revision_id'],case['id'],old['id']))
                store.audit(db,user,pid,'verified_execution_reused',{'original_execution_id':old['id'],'case_id':case['id']},doc['id'],result['revision_id'])
    return result

def _confirm(db,user,p,doc,rev):
    store.editable(db,doc,rev,user,rev['version']);content=pi.revision(db,rev['id'],doc['document_id'])['content']
    from backend.core.workhub_studio.quality import assert_ready
    assert_ready(db,p,doc,{**rev,'content':content},doc)
    if doc['stage']=='frd':
        if any(r.get('change') in {'removed_proposed','unresolved'} for r in content.get('requirements',[])):raise HTTPException(400,'Resolve unclear requirement proposals and explicitly review proposed removals before confirming the FRD.')
        if not content.get('requirements'):raise HTTPException(400,'Extract or enter the actual requirements before confirming this FRD.')
        if any(not r.get('title') or not r.get('acceptance_criteria') for r in content['requirements']):raise HTTPException(400,'Confirm each requirement title and acceptance criterion. Missing technical values must be clarified, not invented.')
    if doc['stage']=='frd' and content.get('flowchart') and content['flowchart'].get('needs_review',True):
        raise HTTPException(409,'Review the flowchart against the current requirements before confirming this FRD.')
    if doc['stage']=='corrections' and content.get('applicability')=='not_applicable':
        if not content.get('na_reason'):raise HTTPException(400,'Record why Correction Notes are Not Applicable.')
        if content.get('changes') or db.execute('SELECT 1 FROM issues WHERE project_id=? LIMIT 1',(p['id'],)).fetchone():raise HTTPException(409,'Recorded corrections or issues exist. Summarize them rather than marking Correction Notes Not Applicable.')
        if any(checks.recorded_corrections(dict(r)) for r in db.execute('SELECT summary FROM engineering_runs WHERE project_id=?',(p['id'],))):raise HTTPException(409,'Recorded comparisons or findings contain corrections. Review and summarize them before approval.')
    if doc['stage'] in {'test','fat'}:
        for source in content.get('sources',[]):
            if source.get('type')=='frd_revision' and source.get('sha256'):
                original=db.execute('SELECT content_hash FROM qc_revisions WHERE id=?',(source.get('revision_id'),)).fetchone()
                if not original or original[0]!=source['sha256']:raise HTTPException(409,'The source FRD content changed. Prepare and review an updated test draft.')
        frd=db.execute("SELECT p.approved_revision,p.id FROM qc_documents q JOIN pi_documents p ON p.id=q.document_id WHERE q.project_id=? AND q.stage='frd'",(p['id'],)).fetchone()
        approved=frd['approved_revision'] if frd else None
        if approved and approved!=rev['frd_revision_id']:raise HTTPException(409,'The FRD baseline changed. Prepare tests from its current approved revision.')
        known={r['id'] for r in pi.revision(db,approved,frd['id'])['content'].get('requirements',[])} if approved else set()
        for case in content.get('cases',[]):
            if any(rid not in known for rid in case.get('requirement_ids',[])):raise HTTPException(400,'Link only requirements in the approved FRD.')
            if not all(case.get(k) for k in ('objective','procedure','expected_result','acceptance_criteria')):raise HTTPException(400,'Verify each test objective, procedure, expected result and acceptance criterion before confirmation.')
    if doc['stage'] in {'quality','closure'} and p.get('is_document_space'):
        if not content.get('summary') and not any(s.get('text','').strip() for s in content.get('sections',[])):raise HTTPException(400,'Complete the document content before confirming it.')
    if doc['stage'] in {'quality','closure'} and not p.get('is_document_space'):
        value=checks.report(db,p,doc['stage']=='closure')
        blockers=[b for b in value['blockers'] if b['code']!='approval:closure']
        if blockers:raise HTTPException(409,'Resolve or formally disposition: '+'; '.join(b['title'] for b in blockers[:5]))
        required=checks.baseline(db,p,doc['stage']=='closure')
        if rev['baseline']!=required:raise HTTPException(409,'The prepared review uses an outdated project baseline. Generate a new review draft.')
    now=timestamp();db.execute('UPDATE qc_revisions SET confirmed_by=?,confirmed_at=?,confirmed_hash=?,version=version+1 WHERE id=?',(user['id'],now,rev['content_hash'],rev['id']))
    store.audit(db,user,p['id'],'draft_reviewed_and_confirmed',{'content_hash':rev['content_hash'],'source_links_verified':True},doc['id'],rev['id'])

def action(user,pid,key,payload):
    store.initialize();queue_packages=False;bridge_quality=False
    if payload.get('action')=='approve' and payload.get('work_feedback') is not None:
        from backend.core.workhub_praxis.outcomes import clean_feedback
        clean_feedback(payload['work_feedback'])
    if type(payload.get('version')) is not int:raise HTTPException(400,'Include the current revision version.')
    with hub.db(True) as db:
        p=store.project(db,pid,user,True);doc=store.control(db,pid,key);rev=store.revision(db,doc['id'],payload.get('revision_id'));native=store.native(db,doc)
        if rev['version']!=payload['version']:raise HTTPException(409,'This revision changed. Reload before acting.')
        action=payload.get('action');comment=text(payload.get('comment',''),4000)
        policy=store.policy_row(db,p)['policy'];now=timestamp()
        if action=='confirm':_confirm(db,user,p,doc,rev)
        elif action=='submit':
            store.editable(db,doc,rev,user,payload['version'])
            from backend.core.workhub_studio.quality import assert_ready
            assert_ready(db,p,doc,{**rev,'content':pi.revision(db,rev['id'],doc['document_id'])['content']},doc)
            if not rev['confirmed_at'] or rev['confirmed_hash']!=rev['content_hash']:raise HTTPException(409,'Review & Confirm this saved draft before submission.')
            reviewer=p['release_id'] if doc['stage']=='closure' else p['quality_id'];hub.user_id(reviewer)
            if policy['independent_review'] and reviewer==rev['owner_id']:raise HTTPException(403,'The procedure requires a reviewer other than the document author. Use the existing project assignment controls.')
            db.execute("UPDATE qc_revisions SET status='in_review',reviewer_id=?,approver_id=?,version=version+1 WHERE id=?",(reviewer,reviewer,rev['id']))
            db.execute("UPDATE pi_revisions SET status='review',reviewer_id=? WHERE id=?",(reviewer,rev['id']))
            store.audit(db,user,pid,'submitted_for_approval',{'reviewer_id':reviewer},doc['id'],rev['id'])
        elif action in {'approve','reject','request_corrections'}:
            reviewer=p['release_id'] if doc['stage']=='closure' else p['quality_id']
            if rev['status']!='in_review' or user['id']!=rev['reviewer_id'] or user['id']!=reviewer:raise HTTPException(403,'Only the currently assigned reviewer can decide this submitted revision.')
            if native['current_revision']!=rev['id']:raise HTTPException(409,'Review the current revision.')
            if action!='approve' and not comment:raise HTTPException(400,'Describe the rejection or requested corrections.')
            from backend.core.workhub_signoff import record as record_signoff
            stamp=record_signoff(db,user,payload,project_id=pid,subject_id=rev['id'],subject_type='document_revision',
                decision='request_changes' if action=='request_corrections' else action,
                role='Closure approver' if doc['stage']=='closure' else 'Document reviewer',
                basis={'document_id':doc['document_id'],'control_id':key,'revision_id':rev['id'],'version':rev['version'],'content_hash':rev['content_hash']})
            if action=='approve':
                if policy['independent_review'] and rev['owner_id']==user['id']:raise HTTPException(403,'Independent review is required.')
                if not rev['confirmed_at'] or rev['confirmed_hash']!=rev['content_hash']:raise HTTPException(409,'The document has no current human confirmation.')
                from backend.core.workhub_studio.quality import assert_ready
                assert_ready(db,p,doc,{**rev,'content':pi.revision(db,rev['id'],doc['document_id'])['content']},doc)
                if doc['stage'] in {'quality','closure'} and not p.get('is_document_space'):
                    if doc['stage']=='quality':
                        from backend.core.workhub_delivery import guard as guard_delivery
                        guard_delivery(db,p,'quality_pass',{})
                        from backend.core.workhub_workflow import guard
                        guard(db,p,user,'quality_pass')
                        from backend.core.workhub_approval_documents import guard as guard_documents
                        guard_documents(db,p,'quality_pass',exclude_document=doc['document_id'])
                    value=checks.report(db,p,doc['stage']=='closure');blockers=[b for b in value['blockers'] if b['code']!='approval:closure']
                    if blockers or rev['baseline']!=checks.baseline(db,p,doc['stage']=='closure'):raise HTTPException(409,'Quality conditions changed after preparation. Review a fresh draft.')
                    required=['documents','requirements','tests','issues','approvals']+(['fat'] if 'fat' in policy['required_stages'] else [])
                    if not isinstance(payload.get('checklist'),dict) or not all(payload['checklist'].get(k) is True for k in required):raise HTTPException(400,'Confirm the six applicable review checks before approval.')
                    if doc['stage']=='quality' and p['stage']=='quality':
                        from backend.core.workhub import DONE_DEVELOPMENT
                        tasks=[dict(r) for r in db.execute("SELECT * FROM items WHERE project_id=? AND type='task' AND work_phase='quality' ORDER BY created_at",(pid,)) if r['stage'] not in DONE_DEVELOPMENT]
                        if tasks:
                            if payload.get('complete_review_tasks') is not True:raise HTTPException(409,'Complete the planned quality tasks, or explicitly confirm completion of your own review tasks with this approval.')
                            if any(t['owner_id']!=user['id'] for t in tasks):raise HTTPException(409,'Another engineer has unfinished quality work. They must complete it before this approval.')
                            versions=payload.get('quality_task_versions')
                            if not isinstance(versions,dict) or any(versions.get(t['id'])!=t['version'] for t in tasks):raise HTTPException(409,'The planned review tasks changed. Refresh before confirming completion.')
                            before=rev['baseline'];completed=[]
                            for task in tasks:
                                row=hub.item(db,task['id'])
                                if row['stage']=='todo':
                                    hub.transition(user,row['id'],{'version':row['version'],'action':'start','comment':'Started as part of the explicitly confirmed quality review.'},transaction=db)
                                    row=hub.item(db,row['id'])
                                if row['stage']!='development':raise HTTPException(409,'Resolve the review task status before completing it with this approval.')
                                hub.transition(user,row['id'],{'version':row['version'],'action':'complete_development','comment':'Completed by the assigned reviewer with quality approval.'},transaction=db)
                                completed.append(row['id'])
                            # Only the explicitly confirmed task state changes here.
                            # Engineering text, results and the reviewed hash stay intact.
                            basis=checks.baseline(db,p)
                            db.execute('UPDATE qc_revisions SET baseline=? WHERE id=?',(basis,rev['id']))
                            rev['baseline']=basis
                            store.audit(db,user,pid,'review_tasks_completed_with_approval',{'task_ids':completed,'previous_baseline':before,'baseline':basis},doc['id'],rev['id'])
                if native['approved_revision'] and native['approved_revision']!=rev['id']:
                    db.execute("UPDATE qc_revisions SET status='superseded' WHERE id=? AND status IN ('approved','released')",(native['approved_revision'],))
                    store.audit(db,user,pid,'revision_superseded',{'successor':rev['id']},doc['id'],native['approved_revision'])
                db.execute('UPDATE pi_documents SET approved_revision=?,updated_at=? WHERE id=?',(rev['id'],now,doc['document_id']))
                db.execute("UPDATE qc_revisions SET status='approved',reviewed_by=?,reviewed_at=?,approved_by=?,approved_at=?,version=version+1 WHERE id=?",(user['id'],now,user['id'],now,rev['id']))
                db.execute("UPDATE pi_revisions SET status='approved',reviewed_by=?,reviewed_at=?,review_comment=? WHERE id=?",(user['id'],now,comment,rev['id']))
                from .pdf_templates import freeze
                freeze(db,p,doc,store.revision(db,doc['id'],rev['id']),user)
                from backend.core.workhub_studio.exporting import freeze as freeze_studio
                freeze_studio(db,p,doc,store.revision(db,doc['id'],rev['id']),user,doc)
                hub.event(db,p,user,'intelligence_document_approve',{'document_id':doc['document_id'],'revision_id':rev['id'],'kind':doc['stage'],'comment':comment})
                queue_packages=doc['stage'] in {'quality','closure'} and not p.get('is_document_space');bridge_quality=doc['stage']=='quality' and p['stage']=='quality' and not p.get('is_document_space')
            else:
                status='rejected' if action=='reject' else 'correction_required'
                db.execute('UPDATE qc_revisions SET status=?,reviewed_by=?,reviewed_at=?,confirmed_by=NULL,confirmed_at=NULL,confirmed_hash=NULL,version=version+1 WHERE id=?',(status,user['id'],now,rev['id']))
                db.execute('UPDATE pi_revisions SET status=?,reviewed_by=?,reviewed_at=?,review_comment=? WHERE id=?',('changes_requested',user['id'],now,comment,rev['id']))
            store.audit(db,user,pid,'document_'+action,{'comment':comment,'checklist':payload.get('checklist') or {},'sign_off':stamp},doc['id'],rev['id'])
        elif action in {'release','archive','customer_authorize','customer_revoke'}:
            allowed=p['release_id'] if action=='release' else p['approver_id']
            if user['id']!=allowed and user['role']!='admin':raise HTTPException(403,'This action requires the assigned release authority or Admin.')
            if not comment:raise HTTPException(400,'Record the reason for this controlled action.')
            if action.startswith('customer_'):
                if rev['status'] not in {'approved','released'}:raise HTTPException(409,'Only reviewed approved revisions can be authorized for a customer package.')
                db.execute('UPDATE qc_revisions SET customer_safe=?,customer_authorized_by=?,customer_authorized_at=?,version=version+1 WHERE id=?',(int(action=='customer_authorize'),user['id'],now,rev['id']))
                ids=documents.file_ids(db,pid,payload.get('customer_file_ids',[])) if action=='customer_authorize' else []
                detail=store.detail(db,doc,rev);allowed=set(detail['content'].get('file_ids',[]))
                for c in detail['content'].get('cases',[]):allowed.update((c.get('execution') or {}).get('file_ids',[]))
                allowed.update((detail.get('acceptance') or {}).get('file_ids',[]))
                if any(i not in allowed for i in ids):raise HTTPException(400,'Authorize only attachments linked to this approved revision or its actual test/acceptance records.')
                if any(db.execute("SELECT 1 FROM files WHERE id=? AND (name LIKE 'QC-ISO-%' OR name LIKE 'QC-INTERNAL-%')",(i,)).fetchone() for i in ids):raise HTTPException(403,'Internal audit and ISO packs cannot be included as customer attachments.')
                db.execute('DELETE FROM qc_customer_files WHERE revision_id=?',(rev['id'],))
                db.executemany('INSERT INTO qc_customer_files VALUES(?,?,?,?)',[(rev['id'],i,user['id'],now) for i in ids])
            else:
                if action=='release' and (rev['status']!='approved' or native['approved_revision']!=rev['id']):raise HTTPException(409,'Release the latest approved revision.')
                db.execute('UPDATE qc_revisions SET status=?,released_by=?,released_at=?,version=version+1 WHERE id=?',('released' if action=='release' else 'archived',user['id'],now,rev['id']))
                if action=='archive' and native['approved_revision']==rev['id']:db.execute('UPDATE pi_documents SET approved_revision=NULL WHERE id=?',(doc['document_id'],))
            store.audit(db,user,pid,action,{'reason':comment},doc['id'],rev['id'])
        else:raise HTTPException(400,'Choose a supported controlled document action.')
    notices=[]
    if action=='confirm' and doc['stage']=='frd' and not p.get('is_document_space'):
        from .authoring import prepare_related
        related=prepare_related(user,pid)
        notices.append(related['notice'])
    if bridge_quality:
        try:hub.transition(user,pid,{'action':'quality_pass','version':p['version'],'comment':'Quality & Closure approved: '+doc['number'],'work_feedback':payload.get('work_feedback')})
        except HTTPException as exc:notices.append('Document quality approval is recorded. Existing project workflow still requires: '+str(exc.detail))
    if queue_packages:
        from backend.core.workhub_intelligence import jobs
        jobs.enqueue(user,pid,'q_package',{})
        if doc['stage']=='quality':
            try:jobs.enqueue(user,pid,'q_generate',{'stage':'closure','reason':'Closure preparation after authorized quality approval'})
            except HTTPException as exc:notices.append(str(exc.detail))
    return {'saved':True,'notices':notices}

def waive(user,pid,payload,key=None):
    store.initialize()
    with hub.db(True) as db:
        p=store.project(db,pid,user,True);value=checks.report(db,p,True);policy=value['policy'];now=timestamp()
        if not policy['allow_waivers']:raise HTTPException(403,'This procedure does not allow deviations or waivers.')
        if not key:
            blocker=next((r for r in value['blockers'] if r['code']==payload.get('code') and r['basis']==payload.get('basis')),None)
            if not blocker or not blocker['waivable']:raise HTTPException(409,'Choose a current waivable quality finding.')
            expiry=payload.get('expires_at') or None
            if expiry:
                try:date.fromisoformat(expiry)
                except (ValueError,TypeError):raise HTTPException(400,'Choose an ISO expiry date.') from None
                if expiry<date.today().isoformat():raise HTTPException(400,'Waiver expiry cannot be in the past.')
            key=identity();db.execute('INSERT INTO qc_waivers(id,project_id,code,basis,reason,disposition,status,requested_by,requested_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
              (key,pid,blocker['code'],blocker['basis'],text(payload.get('reason',''),4000,True),text(payload.get('disposition',''),4000,True),'submitted',user['id'],now,expiry))
            store.audit(db,user,pid,'deviation_requested',{'waiver_id':key,'code':blocker['code']})
        else:
            row=db.execute('SELECT * FROM qc_waivers WHERE id=? AND project_id=?',(key,pid)).fetchone()
            if not row or row['status']!='submitted':raise HTTPException(409,'This deviation is no longer pending.')
            if user['id']!=p['approver_id']:raise HTTPException(403,'The assigned release approver must decide deviations.')
            if policy['independent_review'] and row['requested_by']==user['id']:raise HTTPException(403,'A deviation requires independent approval.')
            if payload.get('action') not in {'approve','reject'}:raise HTTPException(400,'Approve or reject the deviation.')
            if payload['action']=='approve' and not any(r['code']==row['code'] and r['basis']==row['basis'] for r in value['blockers']):raise HTTPException(409,'This finding changed. Request a deviation against the current finding.')
            comment=text(payload.get('comment',''),4000,True)
            db.execute('UPDATE qc_waivers SET status=?,approved_by=?,approved_at=?,comment=? WHERE id=?',('approved' if payload['action']=='approve' else 'rejected',user['id'],now,comment,key))
            store.audit(db,user,pid,'deviation_'+payload['action'],{'waiver_id':key,'comment':comment})
    return {'id':key}
