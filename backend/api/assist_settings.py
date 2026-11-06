from fastapi import APIRouter,HTTPException,Request
from backend.core.assist_model import public_configuration,save_configuration,check_model,ModelBusyError

router=APIRouter(tags=['Chopper model'])

@router.get('/api/assist/model/retrieval')
def retrieval_status(request:Request):
    admin(request)
    from backend.core.semantic_runtime import status
    return status()

@router.post('/api/assist/model/retrieval')
def retrieval_settings(payload:dict,request:Request):
    admin(request)
    from backend.core.semantic_runtime import save_settings
    try:return save_settings(payload)
    except ValueError as error:raise HTTPException(400,str(error)) from None

@router.post('/api/assist/model/retrieval/install')
def install_retrieval(request:Request):
    admin(request)
    from backend.core.semantic_runtime import begin_install
    return begin_install()

@router.get('/api/assist/model/status')
def public_status():
    from backend.core.assist_model import configuration
    from backend.core.local_model_runtime import status
    from backend.core.cpu_model import model_path
    from pathlib import Path
    cfg=configuration();state=status()
    safe={key:state.get(key) for key in ('running','ready','runtimeAvailable','modelName','contextLimit','ramMB','responseSeconds','fallbackReason','failed')}
    return {**safe,'provider':cfg['provider'],'modelName':safe['modelName'] or Path(str(cfg.get('modelPath') or cfg.get('model') or '')).stem,
            'contextLimit':safe['contextLimit'] or cfg.get('contextSize',4096),'installed':Path(str(cfg.get('modelPath') or '')).is_file(),
            'primaryInstalled':model_path('primary').is_file(),'fallbackInstalled':model_path('fallback').is_file()}

@router.post('/api/assist/model/cpu/select')
def select_cpu(payload:dict,request:Request):
    admin(request)
    from backend.core.cpu_model import model_path
    from backend.core.assist_model import configuration
    target=model_path(payload.get('modelId','primary'))
    if not target.is_file():raise HTTPException(409,'Install this model before selecting it.')
    cfg=configuration()
    result=save_configuration({**cfg,'provider':'embedded','modelPath':str(target),'contextSize':4096,'maxTokens':768,'autoStart':True})
    return result

@router.get('/api/assist/model/cpu')
def cpu_status(request:Request):
    admin(request)
    from backend.core.cpu_model import status
    return status()

@router.post('/api/assist/model/cpu/install')
def install_cpu(request:Request,payload:dict=None):
    admin(request)
    from backend.core.cpu_model import begin_install
    return begin_install((payload or {}).get('modelId','primary'))

def admin(request):
    if request.state.user.get('role')!='admin': raise HTTPException(403,'Only an administrator can view or change the shared Chopper model connection.')

@router.get('/api/assist/model')
def model_settings(request:Request):
    admin(request)
    return public_configuration()

@router.post('/api/assist/model')
def save_model(payload:dict,request:Request):
    admin(request);return save_configuration(payload)

@router.post('/api/assist/model/check')
def check(request:Request):
    admin(request)
    try: return check_model()
    except ModelBusyError as error:raise HTTPException(409,str(error))
    except Exception as error:
        # Do not expose request headers, credentials or upstream response bodies.
        raise HTTPException(502,f'Model connection failed ({type(error).__name__}). Check that the service is running and its URL/model are correct.')

@router.get('/api/assist/model/runtime')
def runtime_status(request:Request):
    admin(request)
    from backend.core.local_model_runtime import status
    return status()

@router.post('/api/assist/model/runtime/{action}')
def runtime_action(action:str,request:Request):
    admin(request)
    from backend.core.local_model_runtime import start,stop,restart
    from backend.core.assist_model import configuration
    if action=='stop':return stop()
    if action not in ('start','restart'):raise HTTPException(400,'Choose start, restart or stop')
    cfg=configuration()
    if cfg['provider']!='embedded':raise HTTPException(409,'Save Chopper local model mode first.')
    return restart(cfg) if action=='restart' else start(cfg)

@router.get('/api/assist/tools')
def tools():
    return {'mode':'local-tools','tools':[
        {'name':'decode_collected_log','location':'AI Assistant / Chat attachments','description':'Map uploaded or pasted log buffers to workbook groups, tags, types and offsets; identify rejected requests and incomplete payloads.'},
        {'name':'search_project','endpoint':'/api/assist','description':'Find source evidence in the selected B&R project.'},
        {'name':'configure_rule','endpoint':'/api/assist/rule-config','description':'Create a reviewable validation rule.'},
        {'name':'read_project_source','endpoint':'/api/validation/source/read','description':'Open source in an existing validation session.'},
        {'name':'save_project_source','endpoint':'/api/validation/source/save','description':'Engineer saves text with backup and a file-version check.'}
    ]}
