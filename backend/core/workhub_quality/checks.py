"""Traceability and closure gates; no validator is invoked or its results rewritten."""
import json
from datetime import datetime,timezone
from fastapi import HTTPException
from . import store
from .store import hub,pi

def baseline(db,p,include_quality=False):
    state=store.policy_row(db,p)
    docs=[]
    for d in db.execute('SELECT * FROM qc_documents WHERE project_id=? ORDER BY stage',(p['id'],)):
        if d['stage']=='closure' or d['stage']=='quality' and not include_quality:continue
        native=pi.document(db,d['document_id'],p['id'])
        current=store.revision(db,d['id'],native['current_revision']) if native['current_revision'] else None
        docs.append({'id':d['id'],'current':native['current_revision'],'approved':native['approved_revision'],
            'content_hash':current['content_hash'] if current else None})
    return store.digest({'project':{k:p.get(k) for k in ('id','title','kind','description','customer','machine','due_date','owner_id','quality_id','approver_id','release_id')},
      'policy':state['policy'],'context':state['context'],'documents':docs,
      'executions':[dict(r) for r in db.execute('SELECT * FROM qc_executions WHERE project_id=? ORDER BY id',(p['id'],))],
      'execution_reuse':[dict(r) for r in db.execute('SELECT u.* FROM qc_execution_reuse u JOIN qc_revisions r ON r.id=u.revision_id JOIN qc_documents d ON d.id=r.control_id WHERE d.project_id=? ORDER BY u.revision_id,u.case_id',(p['id'],))],
      'acceptances':[dict(r) for r in db.execute('SELECT * FROM qc_acceptances WHERE project_id=? ORDER BY id',(p['id'],))],
      'source_files':[dict(r) for r in db.execute('SELECT id,sha256,size FROM files f WHERE project_id=? AND NOT EXISTS(SELECT 1 FROM qc_generated_files g WHERE g.file_id=f.id) ORDER BY id',(p['id'],))],
      'engineering_steps':[dict(r) for r in db.execute("SELECT id,title,owner_id,work_phase,stage,dependencies,planned_hours FROM items WHERE project_id=? AND type='task' AND work_phase!='release' ORDER BY id",(p['id'],))],
      'runs':[dict(r) for r in db.execute('SELECT run_id,status,summary,completed_at FROM engineering_runs WHERE project_id=? ORDER BY run_id',(p['id'],))],
      'issues':[dict(r) for r in db.execute('SELECT * FROM issues WHERE project_id=? ORDER BY id',(p['id'],))],
      'waivers':[dict(r) for r in db.execute("SELECT id,code,basis,status,approved_by,approved_at,expires_at,reason,disposition FROM qc_waivers WHERE project_id=? AND status='approved' ORDER BY id",(p['id'],))],
      'updates':[dict(r) for r in db.execute('SELECT id,body,file_ids,run_ids FROM updates WHERE project_id=? ORDER BY id',(p['id'],))],
      'changes':[dict(r) for r in db.execute("SELECT id,event,detail FROM events WHERE project_id=? AND event IN ('reopen','plan_updated','file_uploaded','issue_resolved','issue_reopened') ORDER BY id",(p['id'],))]})

def native_outcome(run):
    status=run.get('status');summary=run.get('summary') or {}
    if isinstance(summary,str):
        try:summary=json.loads(summary)
        except ValueError:summary={}
    if status in {'failed','error','interrupted','cancelled'}:return 'fail'
    if status=='running':return 'not_run'
    explicit=str(summary.get('status','')).casefold()
    if explicit in {'pass','passed','success'}:return 'pass'
    if explicit in {'fail','failed','error'}:return 'fail'
    # Only unambiguous native count pairs establish a pass. A completion state or score does not.
    for total_key,failed_key in [('total','failed'),('totalChecks','failedChecks'),('checks_total','checks_failed')]:
        total,failed=summary.get(total_key),summary.get(failed_key)
        if type(total) is int and total>0 and type(failed) is int:
            return 'fail' if failed>0 else 'pass' if status=='completed' and failed==0 else 'recorded'
    return 'recorded'

def recorded_corrections(run):
    summary=run.get('summary') or {}
    if isinstance(summary,str):
        try:summary=json.loads(summary)
        except ValueError:return False
    keys={'added','removed','modified','differences','changed','mismatches','failed','errors','changes','findings'}
    for key,value in summary.items():
        if key not in keys:continue
        if type(value) in (int,float) and value>0 or isinstance(value,list) and value:return True
        if isinstance(value,dict) and any(type(v) in (int,float) and v>0 or isinstance(v,list) and v for v in value.values()):return True
    return False

def _docs(db,p):
    result={}
    for row in db.execute('SELECT * FROM qc_documents WHERE project_id=?',(p['id'],)):
        doc=dict(row);native=store.native(db,doc)
        current=store.revision(db,doc['id'],native['current_revision']) if native['current_revision'] else None
        approved=store.revision(db,doc['id'],native['approved_revision']) if native['approved_revision'] else None
        result[doc['stage']]={**doc,'current_revision':native['current_revision'],'approved_revision':native['approved_revision'],
            'revision':current,'approved':approved,'current':bool(current and approved and current['id']==approved['id'] and approved['status'] in {'approved','released'})}
    return result

def report(db,p,closure=False):
    state=store.policy_row(db,p);policy=state['policy'];docs=_docs(db,p);blockers=[];waivers=[]
    def add(code,title,basis,waivable=True):
        fingerprint=store.digest(basis)
        matches=db.execute("SELECT * FROM qc_waivers WHERE project_id=? AND code=? AND basis=? AND status='approved' ORDER BY approved_at DESC",(p['id'],code,fingerprint)).fetchall()
        waiver=next((dict(w) for w in matches if not w['expires_at'] or w['expires_at']>=datetime.now(timezone.utc).date().isoformat()),None)
        value={'code':code,'title':title,'basis':fingerprint,'waivable':waivable and policy['allow_waivers'],'waiver':waiver}
        (waivers if waiver else blockers).append(value)
        return bool(waiver)
    header=store.source_header(db,p,state)
    for field in policy['required_project_fields']:
        if not header.get(field):add('context:'+field,'Missing '+field,{'field':field,'value':None})
    for stage in policy['required_stages']:
        if stage in {'quality','closure'}:continue
        d=docs.get(stage)
        if not d:add('document:'+stage,'Missing '+store.STAGES[stage],None);continue
        if not d['current']:add('document:'+stage,store.STAGES[stage]+' is missing a current approved revision',{'current':d['current_revision'],'approved':d['approved_revision'],'status':d['revision']['status'] if d['revision'] else None})
        if d['revision']:
            generation=db.execute('SELECT j.* FROM pi_jobs j JOIN pi_revisions r ON r.generated_by=j.id WHERE r.id=? AND j.project_id=?',(d['revision']['id'],p['id'])).fetchone()
            if generation:
                from backend.core.workhub_intelligence.reliability import source_changed
                if source_changed(db,dict(generation),d['document_id']):add('sources:'+stage,store.STAGES[stage]+' sources changed after preparation; review a fresh draft',{'revision':d['revision']['id'],'job_id':generation['id']},False)
    frd=docs.get('frd');frd_id=frd['approved_revision'] if frd and frd['current'] else None
    requirements=pi.revision(db,frd_id,frd['document_id'])['content'].get('requirements',[]) if frd_id else []
    if 'frd' in policy['required_stages'] and frd_id and not requirements:add('requirements:empty','The approved FRD has no requirements',frd_id)
    for r in requirements:
        if r.get('mandatory',True) and not r.get('acceptance_criteria'):add('requirement:'+r['id']+':criteria','Acceptance criteria missing for '+r['id'],{'frd':frd_id,'requirement':r})
    runs={r['run_id']:dict(r) for r in db.execute('SELECT * FROM engineering_runs WHERE project_id=?',(p['id'],))}
    statuses={};coverage=[]
    for stage in ('test','fat'):
        d=docs.get(stage);cases=[]
        if d and d['revision']:
            rev=store.detail(db,d,d['revision']);cases=rev['content'].get('cases',[])
            if stage in policy['required_stages'] and frd_id and rev['frd_revision_id']!=frd_id:add('baseline:'+stage,store.STAGES[stage]+' refers to an outdated FRD revision',{'frd':frd_id,'document_frd':rev['frd_revision_id'],'revision':rev['id']})
            if stage in policy['required_stages'] and not cases:add('cases:'+stage,store.STAGES[stage]+' has no test cases',rev['id'])
            for c in cases:
                ex=c.get('execution');run=runs.get(c.get('native_run_id'));outcome=ex['outcome'] if ex else native_outcome(run) if run and rev['confirmed'] else 'not_run'
                c['outcome']=outcome;c['waived']=False
                if stage in policy['required_stages'] and c.get('mandatory',True) and outcome!='pass':
                    c['waived']=add('case:'+stage+':'+c['id'],store.STAGES[stage]+' / '+c['id']+': '+outcome,{'revision':rev['id'],'case':store.case_hash(c,rev['frd_revision_id']),'execution':ex,'run':run})
            if stage=='fat' and policy['require_customer_acceptance'] and stage in policy['required_stages']:
                a=rev['acceptance']
                if not a or a['status']!='accepted':add('fat:customer_acceptance','Customer acceptance is missing or not unconditional',{'revision':rev['id'],'acceptance':a})
        statuses[stage]={'total':len(cases),'passed':sum(c['outcome']=='pass' for c in cases),'failed':sum(c['outcome']=='fail' for c in cases),'waived':sum(c.get('waived',False) for c in cases),'cases':cases}
        if stage not in policy['required_stages']:continue
        for r in requirements:
            linked=[c for c in cases if r['id'] in c.get('requirement_ids',[])]
            satisfied=bool(d and d['current'] and linked and any(c['outcome']=='pass' or c.get('waived') for c in linked) and all(c['outcome']=='pass' or c.get('waived') or not c.get('mandatory',True) for c in linked))
            waived=False
            if r.get('mandatory',True) and not satisfied:waived=add('requirement:'+r['id']+':'+stage,r['id']+' has no verified '+store.STAGES[stage]+' coverage',{'frd':frd_id,'requirement':r,'revision':d['current_revision'] if d else None,'cases':[{k:c.get(k) for k in ('id','requirement_ids','outcome','execution','waived')} for c in linked]})
            coverage.append({'requirement_id':r['id'],'title':r.get('title'),'stage':stage,'case_ids':[c['id'] for c in linked],'covered':satisfied,'waived':waived})
    latest={}
    for r in sorted(runs.values(),key=lambda r:(r.get('iteration') or 0,r['created_at'])):
        summary=json.loads(r['summary']);target=summary.get('target') or summary.get('configuration') or ''
        latest[(r['kind'],r.get('source_name') or '',store.bounded(target))]=r
    for r in latest.values():
        if native_outcome(r) in {'fail','not_run'}:add('validation:'+r['run_id'],'Current native validation requires disposition: '+r['kind']+' / '+r['status'],r,r['status']!='running')
    issues=[dict(r) for r in db.execute("SELECT * FROM issues WHERE project_id=? AND status='open'",(p['id'],))]
    for r in issues:add('issue:'+r['id'],'Unresolved issue: '+r['title'],r)
    quality=docs.get('quality');current_basis=baseline(db,p)
    quality_valid=bool(quality and quality['current'] and quality['approved']['baseline']==current_basis and not blockers)
    if closure:
        if not quality_valid:add('approval:quality','Current authorized quality approval is required',{'quality':quality['approved_revision'] if quality else None,'baseline':current_basis},False)
        c=docs.get('closure')
        if not c or not c['current'] or c['approved']['baseline']!=baseline(db,p,True):add('approval:closure','Current authorized closure approval is required',{'closure':c['approved_revision'] if c else None,'baseline':baseline(db,p,True)},False)
    return {'project_id':p['id'],'policy':policy,'policy_version':state['policy_version'],'context':header,
      'documents':list(docs.values()),'requirements':requirements,'traceability':coverage,'tests':statuses['test'],'fat':statuses['fat'],
      'open_issues':issues,'validation_runs':[{'run_id':r['run_id'],'kind':r['kind'],'status':r['status'],'outcome':native_outcome(r),'summary':json.loads(r['summary'])} for r in runs.values()],
      'blockers':blockers,'dispositions':waivers,'ready_for_quality':not blockers,'quality_approved':quality_valid,'baseline':current_basis,
      'closure_baseline':baseline(db,p,True),'ready_for_closure':not blockers if closure else False}

def guard_closure(db,p,user):
    value=report(db,p,True)
    if value['blockers']:raise HTTPException(409,'Quality & Closure: '+ '; '.join(r['title'] for r in value['blockers'][:6]))
    return value

def issue_dispositioned(db,row):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_waivers'").fetchone():return False
    state=db.execute('SELECT policy FROM qc_projects WHERE project_id=?',(row['project_id'],)).fetchone()
    if state and not json.loads(state['policy']).get('allow_waivers'):return False
    return bool(db.execute("SELECT 1 FROM qc_waivers WHERE project_id=? AND code=? AND basis=? AND status='approved' AND (expires_at IS NULL OR expires_at>=?)",
      (row['project_id'],'issue:'+row['id'],store.digest(dict(row)),datetime.now(timezone.utc).date().isoformat())).fetchone())
