"""Authenticated declarative WorkHub dashboard endpoints."""
from fastapi import APIRouter,Depends,Request,Response
from backend.api.workhub import personal_account
from backend.core.workhub_dashboards import schema,store,data,chopper,templates
from backend.core.workhub_growth.store import personal

def private_response(response:Response):response.headers['Cache-Control']='private, no-store'
router=APIRouter(prefix='/api/workhub/dashboards',dependencies=[Depends(personal_account),Depends(private_response)])
def actor(request):
    user=request.state.user;personal(user);return user

@router.get('/registry')
def registry(request:Request):actor(request);return schema.registry()

@router.get('/templates')
def dashboard_templates(request:Request):actor(request);return templates.catalog()

@router.post('/templates/{key}')
def use_template(request:Request,key:str,payload:dict):return store.from_template(actor(request),key,payload)

@router.post('/query')
def query(request:Request,payload:dict):return data.execute(actor(request),payload)

@router.post('/validate')
def validate(request:Request,payload:dict):
    actor(request);return {'configuration':schema.dashboard(payload.get('configuration',{}))}

@router.post('/propose')
def propose(request:Request,payload:dict):return chopper.proposal(actor(request),payload)

@router.get('')
def listing(request:Request):return store.listing(actor(request))

@router.post('')
def create(request:Request,payload:dict):return store.save(actor(request),payload)

@router.get('/{key}')
def get(request:Request,key:str):return store.get(actor(request),key)

@router.put('/{key}')
def update(request:Request,key:str,payload:dict):return store.save(actor(request),payload,key)

@router.post('/{key}/duplicate')
def duplicate(request:Request,key:str,payload:dict):return store.duplicate(actor(request),key,payload)

@router.put('/{key}/sharing')
def sharing(request:Request,key:str,payload:dict):return store.share(actor(request),key,payload)

@router.delete('/{key}')
def delete(request:Request,key:str,version:int):return store.delete(actor(request),key,version)
