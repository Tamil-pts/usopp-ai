"""Authenticated WorkHub Performance & Capability and Contribution Passport."""
from fastapi import APIRouter,Depends,Request,UploadFile,File,Query,HTTPException
from fastapi.responses import FileResponse,JSONResponse
from backend.api.workhub import personal_account
from backend.core.workhub_growth import store,performance,passport,files

router=APIRouter(prefix='/api/workhub/growth',tags=['WorkHub performance and knowledge'],dependencies=[Depends(personal_account)])


@router.get('/metadata')
def metadata(request:Request):return store.metadata(request.state.user)


@router.get('/performance/{person_id}')
def profile(person_id:int,request:Request,days:int=90,project_id:str|None=None):return performance.profile(request.state.user,person_id,days,project_id)


@router.get('/team')
def team(request:Request,days:int=90,project_id:str|None=None):return performance.team(request.state.user,days,project_id)


@router.get('/events/{event_id}')
def event(event_id:str,request:Request):return performance.event_detail(request.state.user,event_id)


@router.get('/events')
def events(request:Request,person_id:int,days:int=90,project_id:str|None=None,kind:str='all',page:int=1):
    return performance.history(request.state.user,person_id,days,project_id,kind,page)


@router.get('/events/{event_id}/result')
def source_result(event_id:str,request:Request):
    return JSONResponse(performance.source_result(request.state.user,event_id),headers={'Cache-Control':'private, no-store','Content-Disposition':'attachment; filename="engineering-result.json"','X-Content-Type-Options':'nosniff'})


@router.post('/evidence')
def save_evidence(payload:dict,request:Request):return performance.manual_save(request.state.user,payload)


@router.get('/evidence/{key}')
def evidence(key:str,request:Request):return performance.manual_detail(request.state.user,key)


@router.put('/evidence/{key}')
def update_evidence(key:str,payload:dict,request:Request):return performance.manual_save(request.state.user,payload,key)


@router.post('/evidence/{key}/review')
def review_evidence(key:str,payload:dict,request:Request):return performance.manual_review(request.state.user,key,payload)


@router.get('/workspace')
def workspace(request:Request):return passport.workspace(request.state.user)


@router.get('/library')
def library(request:Request,q:str='',category:str='',project_id:str='',author_id:int|None=None,page:int=1):return passport.search(request.state.user,q,category,project_id,author_id,page)


@router.post('/articles')
def create_article(payload:dict,request:Request):return passport.save(request.state.user,payload)


@router.get('/articles/{key}')
def article(key:str,request:Request,revision_id:str|None=None):return passport.detail(request.state.user,key,revision_id)


@router.put('/articles/{key}')
def edit_article(key:str,payload:dict,request:Request):return passport.save(request.state.user,payload,key)


@router.post('/articles/{key}/review')
def review_article(key:str,payload:dict,request:Request):return passport.review(request.state.user,key,payload)


@router.post('/articles/{key}/polish')
def polish(key:str,payload:dict,request:Request):return passport.polish(request.state.user,key,payload)


@router.post('/assistant')
def assistant(payload:dict,request:Request):return passport.assistant(request.state.user,payload)


@router.post('/files/{kind}/{key}')
async def upload(kind:str,key:str,request:Request,file:UploadFile=File(...)):
    if kind not in {'article','evidence'}:raise HTTPException(400,'Choose a contribution or evidence record.')
    return await files.upload(request.state.user,kind,key,file)


@router.get('/files/{file_id}')
def download(file_id:str,request:Request):
    value,path=files.download(request.state.user,file_id)
    return FileResponse(path,filename=value['name'],media_type='application/octet-stream',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
