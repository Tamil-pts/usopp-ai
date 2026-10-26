"""Cookie-free ONLYOFFICE callbacks. Every access requires a scoped signature."""
from fastapi import APIRouter,Request
from fastapi.responses import FileResponse
from backend.core.workhub_intelligence import office

router=APIRouter(prefix='/api/workhub/intelligence/office',tags=['Local office integration'])


@router.get('/files/{session_id}')
def source(session_id:str,token:str):
    row,path=office.original(session_id,token)
    return FileResponse(path,filename=row['name'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.post('/callback/{session_id}')
def callback(session_id:str,token:str,payload:dict,request:Request):return office.callback(session_id,token,payload,request.headers.get('authorization',''))
