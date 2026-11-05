"""AI Assist's private uploaded-file comparison API."""
from fastapi import APIRouter,Depends,File,Request,Response,UploadFile
from backend.core import document_comparison as comparison
from backend.core import document_pdf_comparison as pdf_comparison


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


@router.get('/results/{key}/pdf-pairs/{pair_id}')
def pdf_pair(key:str,pair_id:int,request:Request):
    return pdf_comparison.pair_detail(request.state.user,key,pair_id)


@router.get('/results/{key}/pdf-pages/{side}/{page}.png')
def pdf_page(key:str,side:str,page:int,request:Request):
    return Response(pdf_comparison.page_image(request.state.user,key,side,page),media_type='image/png')


@router.get('/results/{key}/highlighted-{side}.pdf')
def highlighted_pdf(key:str,side:str,request:Request):
    return Response(pdf_comparison.annotated_pdf(request.state.user,key,side),media_type='application/pdf',
                    headers={'Content-Disposition':f'attachment; filename="comparison-{key[:8]}-{side}-highlighted.pdf"'})


@router.get('/results/{key}/report.html')
def pdf_report(key:str,request:Request):
    return Response(pdf_comparison.export_html(request.state.user,key),media_type='text/html; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="comparison-{key[:8]}-report.html"',
                             'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'"})


@router.get('/results/{key}/report.pdf')
def pdf_comparison_report(key:str,request:Request):
    return Response(pdf_comparison.export_pdf(request.state.user,key),media_type='application/pdf',
                    headers={'Content-Disposition':f'attachment; filename="comparison-{key[:8]}-report.pdf"'})
