from fastapi import APIRouter,Depends,Request,Response,HTTPException
from backend.api.document_comparison import private
from backend.core import spreadsheet_bi as core
router=APIRouter(prefix='/api/assist/datasets/bi',tags=['Chopper worksheet BI'],dependencies=[Depends(private)])
def invoke(operation,*args,bounded=False):
    if bounded and not core.SLOTS.acquire(blocking=False):raise HTTPException(429,'Worksheet analytics is busy. Retry shortly.')
    try:return operation(*args)
    except (ValueError,TypeError,KeyError) as error:raise HTTPException(400,str(error)[:350]) from None
    finally:
        if bounded:core.SLOTS.release()
@router.post('/start')
def start(payload:dict,request:Request):return invoke(core.start,request.state.user,payload)
@router.get('/jobs/{key}')
def job(key:str,request:Request):return invoke(core.job,request.state.user,key)
@router.post('/question')
def question(payload:dict,request:Request):return invoke(core.answer,request.state.user,payload,bounded=True)
@router.post('/dashboards')
def save(payload:dict,request:Request):return invoke(core.save,request.state.user,payload,bounded=True)
@router.get('/dashboards')
def saved(request:Request):return {'dashboards':invoke(core.saved,request.state.user)}
@router.get('/dashboards/{key}')
def open_saved(key:str,request:Request):return invoke(core.saved,request.state.user,key)
@router.post('/export/{format}')
def export(format:str,payload:dict,request:Request):
    from backend.core.spreadsheet_bi_export import export as render
    data=invoke(render,request.state.user,payload,format,bounded=True)
    return Response(data,media_type='application/pdf' if format=='pdf' else 'text/html; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="Chopper_dashboard.{format}"'})
@router.post('/summary')
def summary(payload:dict,request:Request):return invoke(core.summarize,request.state.user,payload,bounded=True)
