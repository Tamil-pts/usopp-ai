from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, HTTPException
from fastapi.responses import FileResponse
from backend.core import presentation_studio as core, visual_content as visual, presentation_exports as renderer
from backend.api.document_comparison import private

router=APIRouter(prefix='/api/assist/presentations',tags=['Chopper Presentation Studio'],dependencies=[Depends(private)])

@router.get('/catalog')
def catalog(request:Request):
    core.home(request.state.user)
    return {'fonts':visual.FONTS,'palettes':visual.PALETTES,
            'notice':'Fonts depend on the viewing computer; fonts are not downloaded or embedded. PDF/PNG use available server fonts with standard fallbacks; unsupported characters block export. Review the exported slides.'}

@router.post('/sources')
def source(request:Request,file:UploadFile=File(...)):
    try:return core.upload(request.state.user,file.filename or 'Source',file.file.read(20*1024**2+1))
    finally:file.file.close()

@router.get('/sources/{key}/original')
def original(key:str,request:Request):
    import json
    path=core.path_for(request.state.user,key)
    if not (path/'source.json').is_file():raise HTTPException(404,'Source not found for this account.')
    info=json.loads((path/'source.json').read_text(encoding='utf-8'))
    return FileResponse(path/'original',filename=info['name'],media_type='application/octet-stream',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.post('/generate')
def generate(request:Request,payload:dict):return core.generate(request.state.user,payload)

@router.get('')
def listing(request:Request):
    home=core.home(request.state.user);rows=[]
    for file in home.glob('*/record.json'):
        import json
        row=json.loads(file.read_text(encoding='utf-8'))
        rows.append({'id':row['id'],'title':row['deck']['title'],'revision':row['revision'],'modified':file.stat().st_mtime})
    return {'items':sorted(rows,key=lambda r:r['modified'],reverse=True)}

@router.get('/{key}')
def get(key:str,request:Request):return core.load(request.state.user,key)

@router.post('/{key}')
def save(key:str,request:Request,payload:dict):return core.save(request.state.user,key,payload)

@router.get('/{key}/export/{kind}')
def export(key:str,kind:str,request:Request,revision:int):
    value=core.load(request.state.user,key)
    if revision!=value['revision']:raise HTTPException(409,'The saved deck has changed. Reopen it before exporting.')
    if kind not in {'pptx','pdf','svg','png','json'}:raise HTTPException(400,'Choose PPTX, PDF, SVG, PNG or editable JSON.')
    if kind=='json':
        import json
        content=json.dumps(value,ensure_ascii=False).encode();media='application/json';suffix='json'
    else:
        content=renderer.export(value['deck'],kind)
        media={'pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation','pdf':'application/pdf','svg':'application/zip','png':'application/zip'}[kind]
        suffix='zip' if kind in {'png','svg'} else kind
    return Response(content,media_type=media,headers={'Content-Disposition':f'attachment; filename="Chopper_Presentation_{key[:8]}_R{revision}.{suffix}"','Cache-Control':'private, no-store'})
