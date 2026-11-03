"""Delivery handoffs over existing tasks, revisions, documents and audit records."""
import json
from fastapi import HTTPException
from .workhub import store as hub, DONE_DEVELOPMENT
from .workhub_quality import store,checks
from .workhub_approval_documents import attached


def deliverables(db,p):
    row=db.execute("SELECT d.id,d.current_revision,d.approved_revision FROM pi_documents d JOIN qc_documents q ON q.document_id=d.id WHERE q.project_id=? AND q.stage='frd'",(p['id'],)).fetchone()
    if not row:return []
    revision=row['approved_revision'] or row['current_revision']
    if not revision:return []
    content=store.pi.revision(db,revision,row['id'])['content'];value=content.get('deliverables') or '\n'.join(s.get('text','') for s in content.get('sections',[]) if s.get('heading','').strip().casefold() in {'deliverables','required deliverables','final deliverables'})
    if isinstance(value,str):return [s.strip(' -•\t') for s in value.splitlines() if s.strip()][:100]
    if isinstance(value,list):return [str(s.get('title') or s.get('name') or '') if isinstance(s,dict) else str(s) for s in value][:100]
    return []


def readiness(db,p):
    state=store.policy_row(db,p)
    tasks=[dict(r) for r in db.execute("SELECT id,title,stage FROM items WHERE project_id=? AND type='task' AND work_phase='development' ORDER BY created_at",(p['id'],))]
    reports=[d for d in attached(db,p['id']) if d['type'] in {'test','test_report'}]
    history=[dict(r) for r in db.execute("""SELECT a.id,a.action,a.revision_id,a.actor_id,a.detail,a.created_at,r.label,r.status
      FROM qc_audit a JOIN qc_documents d ON d.id=a.control_id LEFT JOIN qc_revisions r ON r.id=a.revision_id
      WHERE a.project_id=? AND d.stage='test' AND a.action IN ('draft_prepared','submitted_for_approval','document_approve','document_reject','document_request_corrections','controlled_revision_created','new_revision','revision_created','revision_created_from_source','test_execution_recorded','verified_execution_reused')
      ORDER BY a.id DESC LIMIT 100""",(p['id'],))]
    for row in history:row['detail']=json.loads(row['detail'])
    return {'project_id':p['id'],'version':p['version'],'development_tasks':tasks,
      'development_complete':all(t['stage'] in DONE_DEVELOPMENT for t in tasks),
      'required_deliverables':deliverables(db,p),'validation_reports':reports,'validation_history':history,
      'fat_applicable':'fat' in state['policy']['required_stages'],'fat_reason':state['context'].get('fat_reason',''),
      'files':[dict(r) for r in db.execute('SELECT id,name FROM files WHERE project_id=? ORDER BY created_at DESC',(p['id'],))],
      'closure_checks':['final_deliverables','handover','required_acceptance']}


def validation_report(db,p):
    reports=[d for d in attached(db,p['id']) if d['type'] in {'test','test_report'}]
    if not reports:raise HTTPException(409,'Select the saved Validation Test Report for this submission.')
    if any(d['stale'] for d in reports):raise HTTPException(409,'The selected Validation Test Report changed. Select its current saved revision and request revalidation.')
    return reports


def guard(db,p,action,payload):
    if p['type']!='project':return
    if action in {'complete_development','submit_quality'}:
        required=deliverables(db,p)
        if required:
            if payload.get('deliverables_complete') is not True:raise HTTPException(409,'Confirm completion of the required development deliverables.')
            ids=payload.get('deliverable_file_ids',[])
            if not isinstance(ids,list) or not ids or len(ids)>100 or any(not isinstance(i,str) or not db.execute('SELECT 1 FROM files WHERE id=? AND project_id=?',(i,p['id'])).fetchone() for i in ids):
                raise HTTPException(409,'Link saved project evidence for the completed development deliverables.')
    if action=='submit_quality':validation_report(db,p)
    if action in {'quality_pass','approve_release','release'}:
        reports=validation_report(db,p)
        if any(d['status'] not in {'approved','released'} for d in reports):raise HTTPException(409,'The selected Validation Test Report revision requires independent approval.')
        if action=='approve_release':
            value=checks.report(db,p)
            if value['blockers']:raise HTTPException(409,'Release prerequisites: '+'; '.join(b['title'] for b in value['blockers'][:8]))
            if not value['quality_approved']:raise HTTPException(409,'Approve the current Quality Review before release approval.')
    if action=='release':
        flags=payload.get('closure_checks',{})
        if not isinstance(flags,dict) or not all(flags.get(k) is True for k in ('final_deliverables','handover','required_acceptance')):
            raise HTTPException(409,'Verify final deliverables, handover and required acceptance before closing this project.')
