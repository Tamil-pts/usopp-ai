"""AI Assist's private uploaded-file comparison API."""
from fastapi import APIRouter,Depends,File,Request,Response,UploadFile
from backend.core import document_comparison as comparison


def private(response:Response):response.headers['Cache-Control']='private, no-store'


router=APIRouter(prefix='/api/assist/document-comparisons',tags=['Document comparison'],dependencies=[Depends(private)])


@router.post('/uploads')
def upload(request:Request,file:UploadFile=File(...)):
    content=file.file.read(comparison.MAX_BYTES+1)
    try:return comparison.upload(request.state.user,file.filename,content)
    finally:file.file.close()


@router.get('/uploads/{key}/columns')
def columns(key:str,request:Request,sheet:str,header_row:int=1):return comparison.columns(request.state.user,key,sheet,header_row)


@router.post('/run')
def run(payload:dict,request:Request):return comparison.run(request.state.user,payload)


@router.get('/results/{key}')
def result(key:str,request:Request,status:str='differences',offset:int=0,limit:int=100):return comparison.page(request.state.user,key,status,offset,limit)


@router.post('/results/{key}/query')
def query(key:str,payload:dict,request:Request):
    return comparison.page(request.state.user,key,payload.get('status','differences'),comparison.number(payload.get('offset',0)),comparison.number(payload.get('limit',100)),payload.get('column_filters'),payload.get('sort'))


@router.post('/results/{key}/values')
def values(key:str,payload:dict,request:Request):return comparison.column_values(request.state.user,key,payload)


@router.get('/results/{key}/export.csv')
def export(key:str,request:Request,status:str='differences'):
    return Response(comparison.export_csv(request.state.user,key,status),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="document-comparison-{key[:8]}.csv"','Cache-Control':'private, no-store'})


@router.post('/results/{key}/export.csv')
def export_view(key:str,payload:dict,request:Request):
    return Response(comparison.export_csv(request.state.user,key,payload.get('status','differences'),payload.get('column_filters'),payload.get('sort')),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="document-comparison-{key[:8]}.csv"','Cache-Control':'private, no-store'})
