from fastapi import APIRouter,HTTPException,Request
from backend.core.assist_model import public_configuration,save_configuration,check_model

router=APIRouter(tags=['Chopper model'])

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
    from backend.core.local_model_runtime import start,stop
    from backend.core.assist_model import configuration
    if action=='stop':return stop()
    if action!='start':raise HTTPException(400,'Choose start or stop')
    cfg=configuration()
    if cfg['provider']!='embedded':raise HTTPException(409,'Save Chopper local model mode first.')
    return start(cfg)

@router.get('/api/assist/tools')
def tools():
    return {'mode':'local-tools','tools':[
        {'name':'decode_collected_log','location':'AI Assistant / Chat attachments','description':'Map uploaded or pasted log buffers to workbook groups, tags, types and offsets; identify rejected requests and incomplete payloads.'},
        {'name':'search_project','endpoint':'/api/assist','description':'Find source evidence in the selected B&R project.'},
        {'name':'configure_rule','endpoint':'/api/assist/rule-config','description':'Create a reviewable validation rule.'},
        {'name':'read_project_source','endpoint':'/api/validation/source/read','description':'Open source in an existing validation session.'},
        {'name':'save_project_source','endpoint':'/api/validation/source/save','description':'Engineer saves text with backup and a file-version check.'}
    ]}
