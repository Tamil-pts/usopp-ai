from fastapi import APIRouter,Depends,File,Request,Response,UploadFile
from fastapi.responses import FileResponse
from backend.api.document_comparison import private
from backend.core import spreadsheet_analysis as core,document_comparison as store

router=APIRouter(prefix='/api/assist/datasets',tags=['Spreadsheet analysis'],dependencies=[Depends(private)])

@router.post('/uploads')
def upload(request:Request,file:UploadFile=File(...)):
    try:return core.upload(request.state.user,file.filename,file.file.read(20*1024**2+1))
    finally:file.file.close()

@router.post('/analyze')
def analyze(request:Request,payload:dict):return core.analyze(request.state.user,payload)

@router.post('/rows')
def rows(request:Request,payload:dict):return core.preview_rows(request.state.user,payload)

@router.get('/{key}/source')
def source(key:str,request:Request):
    path,info=store.source(request.state.user,key)
    return FileResponse(path,filename=info['name'],headers={'Cache-Control':'private, no-store'})

@router.post('/export/{format}')
def export(format:str,request:Request,payload:dict):
    if format not in {'csv','xlsx','json'}:store.fail('Choose CSV, XLSX or JSON.',400)
    media={'csv':'text/csv; charset=utf-8','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','json':'application/json'}
    return Response(core.export(request.state.user,payload,format),media_type=media[format],headers={'Content-Disposition':f'attachment; filename="Chopper_worksheet.{format}"'})
