from fastapi import APIRouter,Depends,Request,Query
from fastapi.responses import Response
from backend.api.workhub import personal_account
from backend.core.workhub_praxis import store,service,reports,insights,outcomes

def private_response(response:Response):response.headers['Cache-Control']='private, no-store'

router=APIRouter(prefix='/api/workhub/praxis',tags=['Competency Hub'],dependencies=[Depends(personal_account),Depends(private_response)])

@router.get('/work-configuration')
def work_configuration(request:Request):return outcomes.settings(request.state.user)

@router.put('/work-configuration')
def save_work_configuration(request:Request,payload:dict):return outcomes.settings(request.state.user,payload)

@router.get('/work-profiles/{subject}')
def work_profile(subject:int,request:Request,period_id:str='',project_id:str=''):return outcomes.profile(request.state.user,subject,period_id,project_id)

@router.get('/work-team')
def work_team(request:Request,period_id:str='',department_id:str='',team_id:str='',role_id:str='',employee_id:int|None=None,project_id:str=''):
    return outcomes.team(request.state.user,period_id,department_id,team_id,role_id,employee_id,project_id)

@router.get('/insights')
def insight_layout(request:Request):return insights.layout(request.state.user)

@router.put('/insights')
def save_insights(request:Request,payload:dict):return insights.save(request.state.user,payload)

@router.get('/activity/{subject}')
def activity(subject:int,request:Request):
    store.initialize()
    with store.hub.db() as db:store.authorize(db,request.state.user,subject)
    return insights.work_activity(request.state.user,subject)

@router.get('/metadata')
def metadata(request:Request):return service.metadata(request.state.user)

@router.put('/configuration')
def configure(request:Request,payload:dict):return store.save_configuration(request.state.user,payload)

@router.get('/profiles/{subject}')
def profile(subject:int,request:Request,period_id:str=''):return service.profile(request.state.user,subject,period_id)

@router.get('/team')
def team(request:Request,period_id:str='',department_id:str='',team_id:str='',role_id:str='',employee_id:int|None=None,project_id:str=''):
    return service.team(request.state.user,period_id,department_id,team_id,role_id,employee_id,project_id)

@router.post('/assessments')
def create_assessment(request:Request,payload:dict):return service.save_assessment(request.state.user,payload)

@router.get('/assessments/{key}')
def assessment(key:str,request:Request):return service.assessment(request.state.user,key)

@router.put('/assessments/{key}')
def edit_assessment(key:str,request:Request,payload:dict):return service.save_assessment(request.state.user,payload,key)

@router.post('/assessments/{key}/review')
def review(key:str,request:Request,payload:dict):return service.review(request.state.user,key,payload)

@router.post('/development')
def create_goal(request:Request,payload:dict):return service.save_development(request.state.user,payload)

@router.put('/development/{key}')
def edit_goal(key:str,request:Request,payload:dict):return service.save_development(request.state.user,payload,key)

@router.get('/reports/{kind}/{format}')
def export(kind:str,format:str,request:Request,subject:int=0,period_id:str='',department_id:str='',team_id:str='',role_id:str='',employee_id:int|None=None,project_id:str='',source:str='assessments'):
    from fastapi import HTTPException
    if format not in {'pdf','xlsx'}:raise HTTPException(400,'Choose PDF or Excel.')
    value=reports.data(request.state.user,kind,subject or request.state.user['id'],period_id,department_id,team_id,role_id,employee_id,project_id,work_based=source=='work')
    content=reports.pdf(value) if format=='pdf' else reports.excel(value)
    mime='application/pdf' if format=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return Response(content,media_type=mime,headers={'Content-Disposition':f'attachment; filename="Competency Hub-{kind}.{format}"','Cache-Control':'private, no-store'})
