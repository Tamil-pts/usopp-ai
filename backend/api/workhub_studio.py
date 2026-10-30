"""Document Studio reuses WorkHub's project, revision and review authorities."""
from urllib.parse import quote
from pathlib import Path
from fastapi import APIRouter,Depends,Request,Response
from fastapi.responses import HTMLResponse,FileResponse
from backend.api.workhub import personal_account
from backend.core.workhub_studio import service,store,quality,compare,connections,reviews,library,builder,exporting

def private_response(response:Response):response.headers['Cache-Control']='private, no-store'
router=APIRouter(tags=['WorkHub Document Studio'],dependencies=[Depends(personal_account),Depends(private_response)])
BASE='/api/workhub/projects/{pid}/studio/documents/{did}'

@router.get(BASE)
def get(pid:str,did:str,request:Request,revision_id:str|None=None):return service.get(request.state.user,pid,did,revision_id)
@router.put(BASE)
def save(pid:str,did:str,payload:dict,request:Request):return service.save(request.state.user,pid,did,payload)
@router.post(BASE+'/preview')
def preview(pid:str,did:str,payload:dict,request:Request):return HTMLResponse(exporting.preview(request.state.user,pid,did,payload),headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
@router.post(BASE+'/quality-check')
def preflight(pid:str,did:str,payload:dict,request:Request):return quality.preflight(request.state.user,pid,did,payload)
@router.post(BASE+'/locks')
def lock(pid:str,did:str,payload:dict,request:Request):return service.lock(request.state.user,pid,did,payload)
@router.post(BASE+'/revision')
def revision(pid:str,did:str,payload:dict,request:Request):return service.revision(request.state.user,pid,did,payload)
@router.get(BASE+'/compare')
def comparison(pid:str,did:str,left:str,right:str,request:Request):return compare.compare(request.state.user,pid,did,left,right)
@router.get(BASE+'/connections')
def graph(pid:str,did:str,request:Request):return connections.graph(request.state.user,pid,did)
@router.post(BASE+'/connections')
def link(pid:str,did:str,payload:dict,request:Request):return connections.add(request.state.user,pid,did,payload)
@router.post(BASE+'/connections/{key}/remove')
def unlink(pid:str,did:str,key:str,payload:dict,request:Request):return connections.remove(request.state.user,pid,did,key,payload)
@router.get(BASE+'/comments')
def comments(pid:str,did:str,request:Request):return reviews.list_comments(request.state.user,pid,did)
@router.post(BASE+'/comments')
def comment(pid:str,did:str,payload:dict,request:Request):return reviews.add(request.state.user,pid,did,payload)
@router.post(BASE+'/comments/{key}')
def respond(pid:str,did:str,key:str,payload:dict,request:Request):return reviews.update(request.state.user,pid,did,key,payload)
@router.get('/api/workhub/studio/template-drafts')
def template_drafts(request:Request):return library.template_drafts(request.state.user)
@router.post('/api/workhub/studio/template-drafts')
def create_template_draft(payload:dict,request:Request):return library.create_template_draft(request.state.user,payload)

@router.get('/api/workhub/studio/templates')
def templates(request:Request):return library.templates(request.state.user)
@router.post(BASE+'/templates')
def save_template(pid:str,did:str,payload:dict,request:Request):return library.save_template(request.state.user,pid,did,payload)
@router.post('/api/workhub/studio/templates/{key}/lock')
def lock_template(key:str,payload:dict,request:Request):return library.lock_template(request.state.user,key,payload)
@router.post(BASE+'/templates/{key}/apply')
def apply_template(pid:str,did:str,key:str,payload:dict,request:Request):return library.apply_template(request.state.user,pid,did,key,payload)
@router.get('/api/workhub/studio/library')
def snippets(request:Request,q:str=''):return library.snippets(request.state.user,q)
@router.post(BASE+'/library')
def save_snippet(pid:str,did:str,payload:dict,request:Request):return library.save_snippet(request.state.user,pid,did,payload)
@router.post(BASE+'/library/{key}/insert')
def insert_snippet(pid:str,did:str,key:str,payload:dict,request:Request):return library.insert_snippet(request.state.user,pid,did,key,payload)
@router.post(BASE+'/build/guided')
def guided(pid:str,did:str,payload:dict,request:Request):return builder.guided(request.state.user,pid,did,payload)
@router.post(BASE+'/build/chopper')
def chopper(pid:str,did:str,payload:dict,request:Request):return builder.queue(request.state.user,pid,did,payload)
@router.post(BASE+'/build/{job_id}/apply')
def apply_proposal(pid:str,did:str,job_id:str,payload:dict,request:Request):return builder.apply(request.state.user,pid,did,job_id,payload)
@router.get(BASE+'/export/{format}')
def export(pid:str,did:str,format:str,request:Request,revision_id:str|None=None):
    raw,mime,name=exporting.export(request.state.user,pid,did,revision_id,format)
    return Response(raw,media_type=mime,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(name,safe=''),'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
@router.post(BASE+'/workflow')
def workflow(pid:str,did:str,payload:dict,request:Request):
    store.initialize();user=request.state.user
    with store.hub.db() as db:p,doc,rev,control=store.document(db,user,pid,did,payload.get('revision_id'))
    if control:
        from backend.core.workhub_quality.service import action
        action(user,pid,control['id'],payload)
    else:store.pi.review(user,pid,did,payload)
    return service.get(user,pid,did)
