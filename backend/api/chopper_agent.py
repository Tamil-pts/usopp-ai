"""Account-bound additive agent endpoints; no write tools or approval bypass."""
from fastapi import APIRouter,HTTPException,Request,Depends
from backend.core import chopper_agent as agent,chopper_agent_store as store,chopper_agent_eval as evaluation
def authorized(request:Request):
    user=getattr(request.state,'user',None)
    if not user or user.get('isDemo') or user.get('role')!='admin' and 'assistant' not in user.get('workspaceModules',[]):
        raise HTTPException(403,'The validated agent requires an authorized personal Chopper account.')

router=APIRouter(prefix='/api/assist/agent',tags=['Chopper validated agent'],dependencies=[Depends(authorized)])


def call(operation,*args):
    try:return operation(*args)
    except PermissionError as error:raise HTTPException(403,str(error)) from None
    except (ValueError,KeyError,TypeError) as error:raise HTTPException(400,str(error)[:300]) from None


@router.get('/status')
def status(request:Request):
    from backend.core.assist_model import public_configuration
    cfg=store.settings();user=request.state.user
    return {'settings':cfg,'model':public_configuration(),'evaluation':evaluation.status(),
            'canConfigure':user.get('role')=='admin','history':store.history(user),
            'capabilities':{'hybridRag':True,'readOnlyWorksheetSQL':True,'webRetrieval':cfg['webEnabled'],
                            'modelRoles':['planner','researcher','reviewer'],'automaticWeightTraining':False,'writeTools':False}}


@router.put('/settings')
def settings(payload:dict,request:Request):return call(store.save_settings,request.state.user,payload)


@router.post('/evaluate')
def evaluate(request:Request):
    if request.state.user.get('role')!='admin':raise HTTPException(403,'An administrator must run the installation safety evaluation.')
    return evaluation.evaluate()


@router.post('/runs')
def run(payload:dict,request:Request):
    call(evaluation.require_current)
    return call(agent.run,request.state.user,payload)


@router.get('/runs/{key}')
def get_run(key:str,request:Request):return call(store.run,request.state.user,key)


@router.post('/queries')
def query(payload:dict,request:Request):
    call(evaluation.require_current)
    return call(agent.prepare_query,request.state.user,payload)


@router.post('/queries/{key}/execute')
def execute(key:str,request:Request):
    call(evaluation.require_current)
    return call(agent.execute_query,request.state.user,key)


@router.get('/examples')
def examples(request:Request):return {'examples':store.examples(request.state.user)}


@router.post('/runs/{key}/examples')
def propose(key:str,payload:dict,request:Request):return call(store.propose,request.state.user,key,payload.get('note',''))


@router.post('/examples/{key}/review')
def review(key:str,payload:dict,request:Request):
    if not isinstance(payload.get('approve'),bool):raise HTTPException(400,'Choose approve or reject explicitly.')
    return call(store.review,request.state.user,key,payload['approve'],payload.get('note',''))
