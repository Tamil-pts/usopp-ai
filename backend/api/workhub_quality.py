"""Project-local engineering quality controls and administrator procedure settings."""
from urllib.parse import quote
from fastapi import APIRouter,Depends,Request,Response,HTTPException
from fastapi.responses import FileResponse
from backend.api.workhub import personal_account
from backend.core.workhub_quality import store,service,documents,configuration,packages,checks
from backend.core.workhub_intelligence import jobs

router=APIRouter(dependencies=[Depends(personal_account)],tags=['Engineering quality and closure'])
PREFIX='/api/workhub/projects/{pid}/quality'
def actor(request):store.personal(request.state.user);return request.state.user

@router.get('/api/admin/settings/engineering-quality')
def settings(request:Request):
    result=configuration.get(actor(request))
    with store.hub.db() as db:result['logos']=[dict(r) for r in db.execute("SELECT id,name FROM files WHERE size<2097152 AND (lower(name) LIKE '%.png' OR lower(name) LIKE '%.jpg' OR lower(name) LIKE '%.jpeg') ORDER BY created_at DESC LIMIT 200")]
    return result
@router.put('/api/admin/settings/engineering-quality')
def save_settings(request:Request,payload:dict):return configuration.save(actor(request),payload)

@router.get(PREFIX)
def overview(pid:str,request:Request):return service.overview(actor(request),pid)
@router.post(PREFIX+'/drafts')
def manual_draft(pid:str,request:Request,payload:dict):
    from backend.core.workhub_quality.authoring import create
    return create(actor(request),pid,payload)
@router.post(PREFIX+'/prepare-from-frd')
def prepare_from_frd(pid:str,request:Request):
    from backend.core.workhub_quality.authoring import prepare_related
    return prepare_related(actor(request),pid)
@router.get(PREFIX+'/trace/{requirement_id}')
def engineering_trace(pid:str,requirement_id:str,request:Request):
    from backend.core.workhub_quality.authoring import trace
    return trace(actor(request),pid,requirement_id)
@router.put(PREFIX+'/context')
def context(pid:str,request:Request,payload:dict):return service.context(actor(request),pid,payload)
@router.post(PREFIX+'/procedure')
def procedure(pid:str,request:Request,payload:dict):return service.rebaseline_policy(actor(request),pid,payload)
@router.post(PREFIX+'/generate')
def generate(pid:str,request:Request,payload:dict):
    user=actor(request);store.initialize();stage=payload.get('stage')
    if stage not in store.STAGES:raise HTTPException(400,'Choose a quality document stage.')
    if 'brief' in payload:payload={**payload,'brief':store.text(payload['brief'],12000)}
    with store.hub.db() as db:
        store.project(db,pid,user,True)
        d=db.execute('SELECT * FROM qc_documents WHERE project_id=? AND stage=?',(pid,stage)).fetchone()
        if d:
            r=store.revision(db,d['id'],store.native(db,dict(d))['current_revision'])
            if r['status'] in {'draft','correction_required'} and (r['version']>1 or r['confirmed_at']):raise HTTPException(409,'This draft already contains saved edits. Keep editing it, use the FRD assistant for proposed changes, or create a new revision before preparing another draft.')
            if r['status'] not in {'draft','correction_required'} and not str(payload.get('reason','')).strip():raise HTTPException(400,'Record the reason for a new controlled revision.')
    return jobs.enqueue(user,pid,'q_generate',payload)
@router.post(PREFIX+'/explain')
def explain(pid:str,request:Request):
    user=actor(request);store.initialize()
    with store.hub.db() as db:
        p=store.project(db,pid,user);r=checks.report(db,p,True)
    return {'answer':('The project has '+str(len(r['blockers']))+' unresolved quality condition(s). ' if r['blockers'] else 'The configured closure checks are satisfied. ')+
      'Prepared documents require human confirmation. Tool completion is not proof of physical test execution.\n'+ '\n'.join('- '+b['title'] for b in r['blockers'])+
      ('\nApproved dispositions: '+str(len(r['dispositions'])) if r['dispositions'] else ''),'source':'Current WorkHub quality records','baseline':r['baseline']}
@router.post(PREFIX+'/packages')
def prepare_packages(pid:str,request:Request,payload:dict):return jobs.enqueue(actor(request),pid,'q_package',payload)
@router.post(PREFIX+'/ask')
def ask_quality(pid:str,request:Request,payload:dict):
    stage=payload.get('stage','quality')
    if stage not in store.STAGES:raise HTTPException(400,'Choose a quality document stage.')
    question=store.text(payload.get('question',''),4000,True)
    return jobs.enqueue(actor(request),pid,'q_answer',{'stage':stage,'question':question})
@router.post(PREFIX+'/iso-pack')
def iso(pid:str,request:Request,payload:dict):
    user=actor(request);configuration.admin(user);return jobs.enqueue(user,pid,'q_iso',payload)
@router.get(PREFIX+'/packages/{key}/download')
def download_package(pid:str,key:str,request:Request):
    row,path=packages.package_download(actor(request),pid,key);return FileResponse(path,filename=row['name'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
@router.get(PREFIX+'/documents/{key}')
def document(pid:str,key:str,request:Request,revision_id:str|None=None):return service.get_document(actor(request),pid,key,revision_id)
@router.post(PREFIX+'/documents/{key}/flowchart/confirm')
def confirm_flowchart(pid:str,key:str,request:Request,payload:dict):return documents.confirm_flowchart(actor(request),pid,key,payload)
@router.put(PREFIX+'/documents/{key}')
def save(pid:str,key:str,request:Request,payload:dict):return documents.save(actor(request),pid,key,payload)
@router.post(PREFIX+'/documents/{key}/revision')
def revision(pid:str,key:str,request:Request,payload:dict):return service.new_revision(actor(request),pid,key,payload)

@router.post(PREFIX+'/documents/{key}/assist')
def frd_assist(pid:str,key:str,request:Request,payload:dict):
    from backend.core.workhub_quality import frd_assistant
    return frd_assistant.request(actor(request),pid,key,payload)

@router.post(PREFIX+'/documents/{key}/assist/{job_id}/apply')
def apply_frd_assist(pid:str,key:str,job_id:str,request:Request,payload:dict):
    from backend.core.workhub_quality import frd_assistant
    return frd_assistant.apply(actor(request),pid,key,job_id,payload)
@router.post(PREFIX+'/documents/{key}/action')
def action(pid:str,key:str,request:Request,payload:dict):return service.action(actor(request),pid,key,payload)
@router.post(PREFIX+'/documents/{key}/execution')
def execution(pid:str,key:str,request:Request,payload:dict):return documents.execute(actor(request),pid,key,payload)
@router.post(PREFIX+'/documents/{key}/acceptance')
def acceptance(pid:str,key:str,request:Request,payload:dict):return documents.acceptance(actor(request),pid,key,payload)
@router.get(PREFIX+'/documents/{key}/export/{format}')
def export(pid:str,key:str,format:str,request:Request,revision_id:str|None=None):
    raw,mime,name=packages.export_document(actor(request),pid,key,revision_id,format)
    return Response(raw,media_type=mime,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(name,safe=''),'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
@router.post(PREFIX+'/waivers')
def waiver(pid:str,request:Request,payload:dict):return service.waive(actor(request),pid,payload)
@router.post(PREFIX+'/waivers/{key}')
def decide(pid:str,key:str,request:Request,payload:dict):return service.waive(actor(request),pid,payload,key)
@router.post(PREFIX+'/flowchart')
def flowchart(pid:str,request:Request):
    user=actor(request);store.initialize()
    with store.hub.db() as db:d=store.control(db,pid,'frd')
    return jobs.enqueue(user,pid,'flowchart',{'document_ids':[d['document_id']],'flow_kind':'functional'})
