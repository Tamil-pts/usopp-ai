from fastapi import APIRouter,Depends,Request,Body,HTTPException,UploadFile,File
from fastapi.responses import Response
from backend.api.workhub import personal_account
from backend.core.workhub_quality import training
from backend.core.workhub_intelligence.local_ai import ServiceUnavailable,ModelOutputError

router=APIRouter(prefix='/api/workhub/training/frd',tags=['WorkHub FRD training'],dependencies=[Depends(personal_account)])
@router.get('')
def sample(request:Request):return {'sample':training.example(),'copies':training.list_copies(request.state.user)}
@router.post('/copies')
def create(request:Request):return training.create(request.state.user)
@router.get('/copies/{key}')
def get(key:str,request:Request):return training.get(request.state.user,key)
@router.post('/copies/{key}/assets')
def upload(key:str,request:Request,file:UploadFile=File(...)):
    return training.upload(request.state.user,key,file.filename or 'practice.txt',file.file.read(10*1024*1024+1))
@router.get('/copies/{key}/assets/{asset_id}')
def asset(key:str,asset_id:str,request:Request):
    from urllib.parse import quote
    row=training.asset(request.state.user,key,asset_id)
    return Response(row['content'],media_type=row['mime'],headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['name'],safe=''),'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
@router.put('/copies/{key}')
def save(key:str,request:Request,payload:dict=Body(...)):return training.save(request.state.user,key,payload)
@router.post('/copies/{key}/assist')
def assist(key:str,request:Request,payload:dict=Body(...)):
    try:return training.assist(request.state.user,key,payload)
    except ServiceUnavailable as e:raise HTTPException(503,str(e)) from None
    except ModelOutputError as e:raise HTTPException(422,str(e)) from None
@router.post('/copies/{key}/apply')
def apply(key:str,request:Request,payload:dict=Body(...)):return training.apply(request.state.user,key,payload)
@router.get('/pdf')
def sample_pdf(request:Request,kind:str='frd'):return Response(training.pdf(request.state.user,kind=kind),media_type='application/pdf',headers={'Cache-Control':'private, no-store','Content-Disposition':'inline; filename="sample-document.pdf"'})
@router.get('/copies/{key}/pdf')
def practice_pdf(key:str,request:Request,kind:str='frd'):return Response(training.pdf(request.state.user,key,kind),media_type='application/pdf',headers={'Cache-Control':'private, no-store','Content-Disposition':'inline; filename="practice-document.pdf"'})
