from fastapi import APIRouter,Request,HTTPException
from backend.core import data_simulator as simulator

router=APIRouter(prefix='/api/nami/data-simulator',tags=['Metadata data simulator'])

def owner(request,data=None):
    user=request.state.user
    if user.get('isDemo'):raise HTTPException(403,'A personal account is required to run a virtual PLC.')
    if data is not None and data.get('accountId')!=user['id']:raise HTTPException(409,'The account changed. Reload DataInspect.')
    return user['id']

@router.get('/{target_id}')
def status(request:Request,target_id:str):
    return simulator.status(request.state.user['id'],target_id)

@router.post('/preview')
def preview(request:Request,data:dict):
    owner(request,data)
    try:
        config=simulator.validate(data);generator=simulator.Generator(config)
        return {'rows':[{'key':simulator.key(row),'parameter':row['parameter'],'groupCode':row['groupCode'],'tagCode':row['tagCode'],
                'dataType':row['dataType'],'units':row.get('units'),'value':generator.value(row,0)[0],'behavior':generator.value(row,0)[1]} for row in config['metadata']]}
    except (ValueError,TypeError,OverflowError) as error:raise HTTPException(400,str(error))

@router.post('/start')
def start(request:Request,data:dict):
    user_id=owner(request,data)
    try:return simulator.start(user_id,data)
    except (ValueError,TypeError,OverflowError) as error:raise HTTPException(400,str(error))

@router.post('/configure')
def configure(request:Request,data:dict):
    try:return simulator.configure(owner(request,data),data)
    except (ValueError,TypeError,OverflowError) as error:raise HTTPException(400,str(error))

@router.post('/{target_id}/stop')
def stop(request:Request,target_id:str,data:dict):
    return simulator.stop(owner(request,data),target_id)
