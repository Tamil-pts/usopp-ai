"""Reviewable FRD proposals in the existing controlled document, never approvals."""
from copy import deepcopy
import json
from fastapi import HTTPException
from . import store,documents
from .store import hub,pi
from backend.core.workhub_intelligence.local_ai import llm_json,configured,ServiceUnavailable

ACTIONS={'analyze','rewrite','clarify','flowchart'}
FIELDS=('title','description','trigger','expected_behavior','subsystem','acceptance_criteria')


def request(user,pid,key,payload):
    from backend.core.workhub_intelligence import jobs
    store.initialize();store.bounded(payload)
    action=payload.get('action','analyze')
    if action not in ACTIONS:raise HTTPException(400,'Choose a supported FRD assistance action.')
    with hub.db() as db:
        store.project(db,pid,user,True);d=store.control(db,pid,key);r=store.revision(db,d['id'],payload.get('revision_id'))
        if d['stage']!='frd':raise HTTPException(400,'Use the embedded assistant in the FRD.')
        if payload.get('version')!=r['version']:raise HTTPException(409,'Save or reload the FRD before asking Chopper.')
        selected=payload.get('requirement_ids',[]);content=pi.revision(db,r['id'],d['document_id'])['content']
        known={r['id'] for r in content.get('requirements',[])}
        if not isinstance(selected,list) or len(selected)>2000 or any(s not in known for s in selected):raise HTTPException(400,'Select requirements from this FRD revision.')
    return jobs.enqueue(user,pid,'q_frd_assist',{'control_id':d['id'],'document_id':d['document_id'],'revision_id':r['id'],'base_hash':r['content_hash'],
        'requirement_ids':selected,'action':action,'question':store.text(payload.get('question',''),4000)})


def process(job,user):
    from backend.core.workhub_intelligence.processing import confirmed_answers,layout_graph
    payload=job.row['payload'];pid=job.row['project_id'];store.initialize()
    with hub.db() as db:
        p=store.project(db,pid,user,True);d=store.control(db,pid,payload['control_id']);r=store.revision(db,d['id'],payload['revision_id'])
        if r['content_hash']!=payload['base_hash']:raise ValueError('The FRD changed before Chopper read it. Ask again using the saved revision.')
        content=pi.revision(db,r['id'],d['document_id'])['content'];requirements=content.get('requirements',[])
        selected=[v for v in requirements if not payload['requirement_ids'] or v['id'] in payload['requirement_ids']]
        header=store.source_header(db,p,store.policy_row(db,p))
        approved_id=store.native(db,d)['approved_revision'];approved=pi.revision(db,approved_id,d['document_id'])['content'].get('requirements',[]) if approved_id else []
    selected_ids={v['id'] for v in selected}
    sources=[{'id':'frd:'+r['id']+':'+v['id'],'type':'requirement','document_id':d['document_id'],'revision_id':r['id'],
        'label':v['id'],'text':'\n'.join(str(v.get(k) or '') for k in ('title','description','trigger','expected_behavior','acceptance_criteria'))} for v in selected]
    selected_refs={sid for v in selected for sid in v.get('source_ids',[])}
    sources+=[s for s in content.get('sources',[]) if s['id'] in selected_refs]
    if payload['action']=='flowchart':
        sources+=(content.get('flowchart') or {}).get('sources',[])
        sources+=[{'id':'frd:'+r['id']+':'+v['id'],'type':'requirement','document_id':d['document_id'],'revision_id':r['id'],'label':v['id'],'text':'\n'.join(str(v.get(k) or '') for k in ('title','description','trigger','expected_behavior','acceptance_criteria'))} for v in requirements if v['id'] not in selected_ids]
    sources=list({s['id']:s for s in sources}.values())
    answers=confirmed_answers(pid)
    for a in answers:sources.append({'id':a['id'],'type':'confirmed_clarification','label':a['question'],'text':a['answer'],**({'file_id':a['file_id']} if a.get('file_id') else {})})
    source_map={s['id']:s for s in sources};selected_ids={v['id'] for v in selected};job.progress(25,'Reading selected FRD requirements and confirmed project decisions')
    updates=[];questions=[];flow=None;mode='Recorded requirement checks'
    if configured():
        result=llm_json('Help review an FRD. Action: '+payload['action']+'. Return {"answer":"...","source_ids":["known id"],'
            '"requirement_updates":[{"id":"existing FR id","title":"...","description":"...","trigger":"...","expected_behavior":"...","subsystem":"...","acceptance_criteria":"...","source_ids":["known id"]}],'
            '"clarification_questions":[{"question":"...","options":["...","Not decided"],"requirement_ids":["existing id"],"source_ids":["known id"]}],'
            '"flowchart":{"nodes":[{"id":"n1","data":{"label":"...","kind":"start|process|decision|end|alarm|interlock|io","plc_references":[],"requirement_ids":["existing id"],"source_ids":["known id"]}}],"edges":[{"id":"e1","source":"n1","target":"n2","label":"Yes"}]}}. '
            'Only populate flowchart for the flowchart action. Update an existing diagram conservatively when supplied; retain unrelated steps. '
            'Every proposal must cite sources. Do not invent numeric values, reset conditions, interlocks, safety behavior or acceptance tolerances. '
            'Unknown behavior stays a clarification. Never create results, signatures or approvals. Do not repeat confirmed clarification questions. '
            'Only modify selected existing requirements. Changes remain draft proposals requiring a human Apply action.',
            {'question':payload['question'],'project':header,'selected_requirements':selected,'approved_requirements':[v for v in approved if v['id'] in selected_ids],
                'existing_flowchart':content.get('flowchart'),'confirmed_decisions':answers,'sources':sources},job.check)
        answer=store.text(result.get('answer',''),12000,True);mode='Private local Chopper'
        def refs(value):
            ids=value.get('source_ids',[])
            if not isinstance(ids,list) or not ids or any(not isinstance(s,str) or s not in source_map for s in ids):raise ValueError('A Chopper proposal omitted a valid source. Retry or edit the controlled draft manually.')
            return list(dict.fromkeys(ids))
        cited=refs(result)
        for u in documents._list(result.get('requirement_updates',[]),2000):
            if not isinstance(u,dict) or u.get('id') not in selected_ids:raise ValueError('Chopper proposed a requirement outside the selection.')
            from backend.core.workhub_intelligence.processing import unsupported_values
            cited_update=refs(u)
            if unsupported_values(' '.join(source_map[s]['text'] for s in cited_update),' '.join(str(u.get(k) or '') for k in FIELDS)):
                raise ValueError('Chopper introduced a technical value or PLC tag absent from the cited sources. Clarify the source before applying a proposal.')
            updates.append({'id':u['id'],**{k:store.text(u.get(k) or '',8000) for k in FIELDS},'source_ids':refs(u)})
        for q in documents._list(result.get('clarification_questions',[]),100):
            if not isinstance(q,dict):raise ValueError('Use structured clarification questions.')
            ids=q.get('requirement_ids',[])
            if not isinstance(ids,list) or any(s not in selected_ids for s in ids):raise ValueError('Clarification requirements must belong to the selection.')
            questions.append({'question':store.text(q.get('question',''),1000,True),'options':[store.text(v,500) for v in documents._list(q.get('options',[]),8)],'requirement_ids':ids,'source_ids':refs(q)})
        if payload['action']=='flowchart':
            f=result.get('flowchart')
            if not isinstance(f,dict):raise ValueError('Chopper did not return a structured editable flowchart.')
            nodes=[]
            for n in documents._list(f.get('nodes',[]),500):
                data=n.get('data',{});ids=data.get('requirement_ids',[])
                if not isinstance(ids,list) or any(s not in {v['id'] for v in requirements} for s in ids):raise ValueError('A diagram node references an unavailable FRD requirement.')
                if data.get('kind') not in {'start','process','decision','end','alarm','interlock','io'}:raise ValueError('Use supported engineering node types.')
                source_ids=refs(data);tags=documents._list(data.get('plc_references',[]),100)
                if any(not isinstance(t,str) or len(t)>180 for t in tags):raise ValueError('Use bounded PLC references.')
                from backend.core.workhub_intelligence.processing import unsupported_values
                if unsupported_values(' '.join(source_map[s]['text'] for s in source_ids),str(data.get('label',''))+' '+' '.join(tags)):raise ValueError('A diagram proposal introduced an unsupported technical value or PLC tag.')
                nodes.append({'id':store.text(n.get('id',''),80,True),'data':{'label':store.text(data.get('label',''),2000,True),'kind':data['kind'],'requirement_ids':ids,'source_ids':source_ids,'plc_references':tags}})
            edges=[{'id':store.text(e.get('id',''),80,True),'source':store.text(e.get('source',''),80,True),'target':store.text(e.get('target',''),80,True),'label':store.text(e.get('label',''),500)} for e in documents._list(f.get('edges',[]),1500)]
            if not nodes:raise ValueError('A flowchart proposal needs nodes.')
            flow={'nodes':layout_graph(nodes,edges),'edges':edges,'sources':sources,'notice':'Engineering proposal linked to this FRD. Human review is required; this is not validated PLC logic.'}
            pi.validate_content('flowchart',flow)
    else:
        if payload['action']=='flowchart':raise ServiceUnavailable('Start the existing private Chopper model to propose a functional sequence, or use Add blank flowchart. No machine logic is inferred from requirement titles.')
        for v in selected:
            for field in ('trigger','expected_behavior','acceptance_criteria'):
                if not v.get(field):questions.append({'question':v['id']+': confirm '+field.replace('_',' ')+'.','options':['Not decided'],'requirement_ids':[v['id']],'source_ids':['frd:'+r['id']+':'+v['id']]})
        answer='No private model is configured. These are checks of recorded fields only. '+str(len(questions))+' missing requirement detail(s) need engineering clarification. No technical behavior or criteria were invented.';cited=[s['id'] for s in sources]
    job.check()
    return {'control_id':d['id'],'revision_id':r['id'],'base_hash':r['content_hash'],'action':payload['action'],'answer':answer,'mode':mode,
        'requirement_updates':updates,'clarification_questions':questions,'flowchart':flow,'sources':sources,'source_ids':cited,'requires_review':True}


def apply(user,pid,key,job_id,payload):
    store.initialize()
    if any(type(payload.get(k,False)) is not bool for k in ('updates','flowchart','questions')) or not any(payload.get(k,False) for k in ('updates','flowchart','questions')):raise HTTPException(400,'Explicitly choose reviewed wording, a flowchart or clarification questions to apply.')
    with hub.db(True) as db:
        p=store.project(db,pid,user,True);d=store.control(db,pid,key);r=store.revision(db,d['id'],payload.get('revision_id'))
        store.editable(db,d,r,user,payload.get('version'))
        if type(payload.get('version')) is not int:raise HTTPException(400,'Include the current draft version.')
        job=db.execute("SELECT * FROM pi_jobs WHERE id=? AND project_id=? AND kind='q_frd_assist' AND status='completed'",(job_id,pid)).fetchone()
        if not job:raise HTTPException(404,'Choose a completed FRD assistant draft from this project.')
        proposal=json.loads(job['result'])
        if d['stage']!='frd' or proposal.get('control_id')!=d['id'] or proposal.get('revision_id')!=r['id'] or proposal.get('base_hash')!=r['content_hash']:raise HTTPException(409,'The FRD changed after this proposal. Ask Chopper again to preserve the latest engineering work.')
        content=deepcopy(pi.revision(db,r['id'],d['document_id'])['content'])
        source_map={s['id']:s for s in content.get('sources',[])}
        for s in proposal['sources']:source_map[s['id']]=s
        content['sources']=list(source_map.values())
        updates={v['id']:v for v in proposal['requirement_updates']}
        if payload.get('updates'):content['requirements']=[{**v,**updates[v['id']],'change':'modified'} if v['id'] in updates else v for v in content.get('requirements',[])]
        if payload.get('flowchart'):
            if not proposal.get('flowchart'):raise HTTPException(400,'This proposal has no flowchart.')
            content['flowchart']=proposal['flowchart']
        if payload.get('questions'):
            for q in proposal['clarification_questions']:pi.add_clarification(db,pid,q['question'],q['options'],q['source_ids'])
        result=documents._save(db,user,p,d,r,documents.clean_content(db,pid,'frd',content),payload['version'])
        store.audit(db,user,pid,'frd_assistant_draft_applied',{'job_id':job_id,'updates':bool(payload.get('updates')),'flowchart':bool(payload.get('flowchart')),'questions':bool(payload.get('questions'))},d['id'],r['id'])
        return result
