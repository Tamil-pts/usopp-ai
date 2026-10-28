"""Organization and project resource planning in the existing WorkHub."""
from fastapi import APIRouter,Depends,Request
from backend.api.workhub import personal_account
from backend.core import workhub_organization as org,workhub_resources as resources

router=APIRouter(prefix='/api/workhub',tags=['WorkHub teams and resources'],dependencies=[Depends(personal_account)])

@router.get('/testing-projects')
def testing_projects(request:Request):
    from backend.core.workhub_tool_context import options
    return options(request.state.user)

@router.get('/organization')
def organization(request:Request):return org.directory(request.state.user)

@router.post('/organization/units')
def create_unit(request:Request,payload:dict):return org.save_unit(request.state.user,payload)

@router.put('/organization/units/{key}')
def edit_unit(key:str,request:Request,payload:dict):return org.save_unit(request.state.user,payload,key)

@router.put('/organization/profiles/{user_id}')
def profile(user_id:int,request:Request,payload:dict):return org.save_profile(request.state.user,user_id,payload)

@router.get('/resources')
def planning(request:Request,from_date:str='',to_date:str='',project_id:str='',team_id:str='',department_id:str='',status:str=''):
    return resources.snapshot(request.state.user,from_date,to_date,project_id,team_id,department_id,status)
