from fastapi import APIRouter,HTTPException,Request
from backend.core import project_intelligence as intelligence
from backend.core.runtime import _local_path,locate_root
from python_engine.machine_function_engine import analyze as analyze_machine_functions

router=APIRouter(tags=['Chopper Project Intelligence'])


def owner(request):return request.state.user['id']


@router.post('/api/assist/projects/index')
def index_project(payload:dict,request:Request):
    try:
        project=locate_root(_local_path(str(payload.get('projectPath') or ''),True,True))
        return intelligence.start(project,owner(request),payload.get('mode','refresh'))
    except (ValueError,PermissionError) as error:raise HTTPException(400,str(error))


@router.get('/api/assist/projects/{key}')
def index_status(key:str,request:Request):
    try:return intelligence.status(intelligence.opened(key,owner(request)),owner(request))
    except (ValueError,PermissionError) as error:raise HTTPException(404,str(error))


@router.post('/api/assist/projects/{key}/cancel')
def cancel_index(key:str,request:Request):
    try:return intelligence.cancel(key,owner(request))
    except (ValueError,PermissionError) as error:raise HTTPException(404,str(error))


@router.post('/api/assist/projects/{key}/retrieve')
def retrieve(key:str,payload:dict,request:Request):
    try:
        index=intelligence.opened(key,owner(request))
        return index.retrieve(str(payload.get('question') or '')[:4000],characters=18000)
    except (ValueError,PermissionError) as error:raise HTTPException(404,str(error))


@router.get('/api/assist/projects/{key}/symbols')
def search_symbols(key:str,request:Request,q:str='',limit:int=50):
    try:
        index=intelligence.opened(key,owner(request))
        return {'query':q[:100],'symbols':index.search_symbols(q,limit)}
    except (ValueError,PermissionError) as error:raise HTTPException(404,str(error))


@router.get('/api/assist/projects/{key}/machine-analysis')
def machine_analysis(key:str,request:Request):
    try:
        index=intelligence.opened(key,owner(request))
        return analyze_machine_functions(index)
    except (ValueError,PermissionError) as error:raise HTTPException(404,str(error))


@router.get('/api/assist/projects/{key}/source')
def project_source(key:str,request:Request,path:str,line:int=1,context:int=2):
    try:
        index=intelligence.opened(key,owner(request))
        return index.source_excerpt(path,line,context)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(404,str(error))
