from pathlib import Path
import json
from fastapi import APIRouter,File,Form,HTTPException,UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from starlette.concurrency import run_in_threadpool
from backend.core.runtime import RESOURCE_ROOT,WORK,KNOWLEDGE
from backend.core.run_history import current_user,write_json
from backend.core.data_models import parse_model,validate_model,machine_key,database_json

router=APIRouter(tags=['DataInspect data models'])


def user_folder():
    import hashlib
    user=current_user.get() or {}
    identity=user.get('id') or user.get('username')
    if not identity:raise HTTPException(401,'Sign in to view data models.')
    folder=WORK/'data_models'/hashlib.sha256(str(identity).encode()).hexdigest()
    from backend.core.access import claim_resource
    claim_resource(folder)
    return folder


def models():
    bundled=RESOURCE_ROOT/'knowledge/data_models/catalog.json'
    items=json.loads(bundled.read_text(encoding='utf-8')).get('models',[]) if bundled.is_file() else []
    from backend.core.data_model_rules import load_rules,apply_model
    config,revision=load_rules(KNOWLEDGE/'master/data_model_rules.json')
    items=[{**apply_model(model,config),'mappingRulesRevision':revision} for model in items]
    saved=user_folder()
    for path in saved.glob('*.json'):
        try:
            item=json.loads(path.read_text(encoding='utf-8'))
            if isinstance(item,dict) and item.get('id') and isinstance(item.get('parameters'),list):
                items.append({**apply_model(item,config),'mappingRulesRevision':revision})
        except (ValueError,OSError):continue
    return list({item['id']:item for item in items}.values())


def model_for(model_id):
    model=next((model for model in models() if model['id']==model_id),None)
    if not model:
        legacy=RESOURCE_ROOT/'knowledge/data_models/legacy_catalog.json'
        if legacy.is_file():
            model=next((item for item in json.loads(legacy.read_text(encoding='utf-8')).get('models',[]) if item['id']==model_id),None)
    if not model:raise HTTPException(404,'Data model not found.')
    return model


@router.get('/api/nami/data-models')
def list_models(machine:str='',include_parameters:bool=False,fixed_only:bool=False):
    items=models()
    if machine:items=[model for model in items if machine_key(model.get('machine',''))==machine_key(machine)]
    if fixed_only:items=[model for model in items if model.get('fixed') is True]
    if include_parameters:return items
    return [{key:model[key] for key in ('id','source','service','serviceName','machine')}|{'parameterCount':len(model['parameters']),'warningCount':len(model['warnings']),'fixed':model.get('fixed',False),'sourceRelativePath':model.get('sourceRelativePath','')} for model in items]


@router.get('/api/nami/data-models/{model_id}')
def get_model(model_id:str):return model_for(model_id)


@router.get('/api/nami/data-models/{model_id}/download')
def download_model(model_id:str):
    model=model_for(model_id)
    target=user_folder()/'downloads'/(model['id']+'.json');write_json(target,database_json(model))
    return FileResponse(target,media_type='application/json',filename=model['service']+'_'+Path(model['source']).stem+'.json')


@router.post('/api/nami/data-models/import')
async def import_model(file:UploadFile=File(...),service:str=Form(''),machine:str=Form('')):
    content=await file.read(20*1024*1024+1)
    if len(content)>20*1024*1024:raise HTTPException(400,'Data model file exceeds 20 MB.')
    try:model=await run_in_threadpool(parse_model,content,Path((file.filename or '').replace('\\','/')).name,service,machine)
    except Exception as error:raise HTTPException(400,str(error))
    await run_in_threadpool(write_json,user_folder()/(model['id']+'.json'),model)
    from backend.core.data_model_rules import load_rules,apply_model
    config,revision=load_rules(KNOWLEDGE/'master/data_model_rules.json')
    return {**apply_model(model,config),'mappingRulesRevision':revision}


class ValidationRequest(BaseModel):
    metadata:list[dict]=Field(max_length=30000)


@router.post('/api/nami/data-models/{model_id}/validate')
def check_model(model_id:str,request:ValidationRequest):
    model=model_for(model_id)
    result=validate_model(model,request.metadata)
    result.update(projectName=f'{model["machine"]} / {model["service"]} / {model["source"]}',machineDepartment=model['machine'])
    from backend.core.runtime import _local_session
    from backend.core.run_history import record_run
    result['sessionId']=_local_session()[0]
    result['metadata']=request.metadata
    record_run('data-model',result)
    return result
