"""PLC MatchView entry point using the existing immutable, account-owned file store."""
from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from backend.api.document_comparison import private
from backend.core import document_comparison as core, document_pdf_comparison as pdf, plc_pdf_comparison as plc

router=APIRouter(prefix='/api/local/compare/plc-pdf',tags=['PLC PDF comparison'],dependencies=[Depends(private)])

@router.post('/uploads')
def upload(request:Request,file:UploadFile=File(...)):
    try:
        if not (file.filename or '').lower().endswith('.pdf'):core.fail('Choose a PLC program PDF.',400)
        return core.upload(request.state.user,file.filename,file.file.read(core.MAX_BYTES+1))
    finally:file.file.close()

@router.post('/run')
def run(payload:dict,request:Request):
    return core.run(request.state.user,{**payload,'plc_networks':True})

@router.get('/results/{key}')
def result(key:str,request:Request,status:str='differences',offset:int=0,limit:int=100):
    return core.page(request.state.user,key,status,offset,limit)

@router.get('/results/{key}/networks/{row_id}/{side}.png')
def network(key:str,row_id:int,side:str,request:Request,overlay:bool=False,highlight:bool=False):
    return Response(plc.network_image(request.state.user,key,row_id,side,overlay,highlight),media_type='image/png')

@router.get('/results/{key}/export.csv')
def csv(key:str,request:Request,status:str='differences'):
    return Response(core.export_csv(request.state.user,key,status),media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition':f'attachment; filename="plc-networks-{key[:8]}.csv"'})

@router.get('/results/{key}/report.{format}')
def report(key:str,format:str,request:Request,status:str='differences',project_name:str='',project_id:str='',department:str='',base:str='',description:str='',approved_by:str='',objective_scope:str='',developed:str='',reviewed_by:str=''):
    if format not in {'html','pdf','docx'}:core.fail('Choose PDF, HTML or Word.',400)
    media={'html':'text/html; charset=utf-8','pdf':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
    headers={'Content-Disposition':f'attachment; filename="plc-networks-{key[:8]}.{format}"'}
    if format=='html':headers['Content-Security-Policy']="default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    metadata={'project_name':project_name,'project_id':project_id,'department':department,'base':base,'description':description,'approved_by':approved_by,'objective_scope':objective_scope,'developed':developed,'reviewed_by':reviewed_by}
    return Response(plc.export_report(request.state.user,key,format,status,metadata),media_type=media[format],headers=headers)

@router.get('/results/{key}/highlighted-{side}.pdf')
def highlighted(key:str,side:str,request:Request,status:str='differences'):
    return Response(pdf.annotated_pdf(request.state.user,key,side,status),media_type='application/pdf',
        headers={'Content-Disposition':f'attachment; filename="plc-{key[:8]}-{side}-highlighted.pdf"'})
