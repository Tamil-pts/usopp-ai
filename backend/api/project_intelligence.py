from fastapi import APIRouter,HTTPException,Request
from backend.core import project_intelligence as intelligence
from backend.core.runtime import _local_path,locate_root
from python_engine.machine_function_engine import analyze as analyze_machine_functions
from backend.core.project_retrieval import retrieve_page

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
        return retrieve_page(index,str(payload.get('question') or '')[:4000],characters=18000,
                              offset=payload.get('offset',0),limit=payload.get('limit',14))
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


@router.get('/api/assist/projects/{key}/relationships')
def relationship_page(key:str,request:Request,kind:str='',q:str='',file:str='',offset:int=0,limit:int=100):
    try:
        index=intelligence.opened(key,owner(request))
        return index.relationships(kind,q,file,offset,limit)
    except (ValueError,PermissionError) as error:raise HTTPException(404,str(error))


@router.get('/api/assist/projects/{key}/machine-analysis/{collection}')
def machine_analysis_page(key:str,collection:str,request:Request,q:str='',offset:int=0,limit:int=100):
    allowed={'functions','stateMachines','signalWrites','callGraph','timers','hmiLinks','hardwareLinks','evidence','dataDependencies','ladderNetworks'}
    if collection not in allowed:raise HTTPException(400,'Unknown engineering collection.')
    try:
        index=intelligence.opened(key,owner(request))
        rows=analyze_machine_functions(index).get(collection,[])
        if q:
            import json
            rows=[row for row in rows if q[:200].casefold() in json.dumps(row).casefold()]
        offset=max(0,offset);limit=max(1,min(500,limit));total=len(rows)
        return {'items':rows[offset:offset+limit],'total':total,'offset':offset,'nextOffset':offset+limit if offset+limit<total else None}
    except (ValueError,PermissionError) as error:raise HTTPException(404,str(error))


@router.get('/api/assist/projects/{key}/source')
def project_source(key:str,request:Request,path:str,line:int=1,context:int=2):
    try:
        index=intelligence.opened(key,owner(request))
        return index.source_excerpt(path,line,context)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(404,str(error))


def foundation(key,request):
    from backend.core.engineering_foundation import model
    return model(key,request.state.user)


@router.post('/api/assist/projects/{key}/engineering-model/build')
def build_foundation(key:str,request:Request):
    from backend.core.engineering_foundation import build_model
    try:return build_model(key,request.state.user)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))


@router.get('/api/assist/projects/{key}/engineering-model')
def foundation_structure(key:str,request:Request):
    try:return foundation(key,request).structure()
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))


@router.get('/api/assist/projects/{key}/engineering-model/blocks')
def foundation_blocks(key:str,request:Request,kind:str='',file:str='',q:str='',offset:int=0,limit:int=100):
    try:return foundation(key,request).blocks(kind,file,q,offset,limit)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))


@router.get('/api/assist/projects/{key}/engineering-model/blocks/{block_id}')
def foundation_block(key:str,block_id:str,request:Request,include_ir:bool=False):
    try:return foundation(key,request).block(block_id,include_ir)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))


@router.get('/api/assist/projects/{key}/engineering-model/relationships')
def foundation_relations(key:str,request:Request,block_id:str='',kind:str='',offset:int=0,limit:int=100):
    try:return foundation(key,request).relations(block_id,kind,offset,limit)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))


@router.get('/api/assist/projects/{key}/engineering-model/validate')
def foundation_validation(key:str,request:Request,offset:int=0,limit:int=100):
    try:return foundation(key,request).validate(offset,limit)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))


@router.get('/api/assist/projects/{key}/engineering-model/execution')
def foundation_execution(key:str,request:Request,task_id:str='',limit:int=200):
    try:return foundation(key,request).execution_flow(task_id,limit)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))


@router.get('/api/assist/projects/{key}/engineering-model/trace')
def foundation_trace(key:str,request:Request,signal:str,scope:str='',limit:int=100):
    try:return foundation(key,request).trace_signal(signal,scope,limit)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))


@router.get('/api/assist/projects/{key}/engineering-model/tokens')
def foundation_tokens(key:str,request:Request,file:str,offset:int=0,limit:int=100):
    try:return foundation(key,request).tokens(file,offset,limit)
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))


@router.post('/api/assist/projects/{key}/engineering-model/investigate')
def foundation_investigate(key:str,payload:dict,request:Request):
    from backend.core.engineering_harness import investigate
    try:return investigate(key,payload.get('question',''),request.state.user,bool(payload.get('useModel',True)),payload.get('maxPasses',2))
    except (ValueError,PermissionError,OSError) as error:raise HTTPException(409,str(error))
