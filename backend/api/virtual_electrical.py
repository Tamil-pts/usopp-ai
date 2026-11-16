"""Account-bound native electrical circuits, imports and local simulation."""
from contextvars import copy_context
from pathlib import Path
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid

from fastapi import APIRouter,File,HTTPException,UploadFile
from fastapi.responses import FileResponse,Response
from starlette.background import BackgroundTask
from backend.core.runtime import WORK
from backend.core.run_history import current_user
from backend.core import virtual_electrical as engine
from backend.core.access import claim_resource

router=APIRouter(prefix='/api/virtual-electrical',tags=['Virtual electrical workspace'])
SLOTS=threading.BoundedSemaphore(2)

@router.post('/control/simulate')
def simulate_industrial_control(payload:dict):
    user()
    from backend.electrical.control import simulate
    return simulate(payload)


@router.get('/library')
def library():
    user()
    from backend.core.electrical_library import LIBRARY
    from backend.core.electrical_simulation import executable
    return {'components':LIBRARY,'solverAvailable':bool(executable()),'engine':'ngspice','schemaVersion':2}


@router.post('/projects/native')
def native_project(payload:dict):
    from backend.core.electrical_library import example
    kind=payload.get('example','blank')
    if kind not in {'blank','divider','rc','starter'}:raise HTTPException(400,'Choose a supported circuit example.')
    document=example(kind) if kind!='blank' else {'schemaVersion':2,'version':1,'name':'New circuit','elements':[],'sources':[],'issues':[],'imported':False,'sourceSha256':None,'modelNotice':'Native component model; no physical controller connection.'}
    key,folder=begin(str(payload.get('name') or document['name']),{'kind':'native'})
    try:
        engine.write(folder/'circuit.json',document)
        engine.write(folder/'drawing.json',{'pages':[],'references':[],'sourceSha256':None,'pageCount':0})
        engine.write(folder/'layout.json',{'version':1,'mode':'custom','positions':[]})
        engine.write(folder/'status.json',{'status':'ready','phase':'Native circuit ready','pageCount':0})
    finally:SLOTS.release()
    return {'id':key,'status':'ready'}


def user():
    who=current_user.get()
    if not who:raise HTTPException(401,'Sign in to open an electrical workspace.')
    if who.get('role')!='admin' and 'edesign' not in who.get('workspaceModules',['edesign']):raise HTTPException(403,'Electrical drawing access is disabled for this account.')
    return who


def opened(key,ready=True):
    who=user()
    if not re.fullmatch(r'electrical_[a-f0-9]{32}',key):raise HTTPException(404,'Electrical workspace not found.')
    folder=WORK/key;path=folder/'workspace.json'
    if not path.is_file():raise HTTPException(404,'Electrical workspace not found.')
    data=engine.read(path)
    if data['ownerId']!=who['id']:raise HTTPException(403,'This electrical workspace belongs to another account.')
    state=engine.read(folder/'status.json')
    if state['status']=='analyzing' and state.get('processId')!=os.getpid():state={**state,'status':'failed','error':'Analysis was interrupted by a server restart. Import the drawing again.'}
    if ready and state['status']!='ready':raise HTTPException(409,state.get('error') or 'Drawing analysis is not complete.')
    return folder,data,state


def begin(name,source=None):
    who=user()
    if not SLOTS.acquire(blocking=False):raise HTTPException(429,'Two electrical drawings are being prepared. Wait for one to finish.')
    key='electrical_'+uuid.uuid4().hex;folder=WORK/key
    try:
        folder.mkdir();claim_resource(folder)
        engine.write(folder/'workspace.json',{'id':key,'ownerId':who['id'],'name':name[:180],'created':time.time(),'source':source})
        engine.write(folder/'status.json',{'status':'analyzing','processId':os.getpid(),'phase':'Opening drawing','current':0,'total':0})
    except Exception:SLOTS.release();raise
    return key,folder


def worker(folder):
    def progress(phase,current,total):engine.write(folder/'status.json',{'status':'analyzing','processId':os.getpid(),'phase':phase,'current':current,'total':total})
    try:
        meta=engine.read(folder/'workspace.json')
        if (meta.get('source') or {}).get('mode')=='industrial':
            from backend.electrical.reconstruction import build
            model=build(folder,progress);data={'pageCount':len(model['pages'])}
        else:data=engine.decode(folder,progress)
        engine.write(folder/'status.json',{'status':'ready','phase':'Native circuit objects ready','pageCount':data['pageCount']})
    except Exception as error:engine.write(folder/'status.json',{'status':'failed','error':str(error)[:350]})
    finally:SLOTS.release()


def start(folder):
    context=copy_context();threading.Thread(target=context.run,args=(worker,folder),daemon=True,name='electrical-drawing').start()


@router.get('/projects')
def projects():
    who=user();rows=[]
    for path in WORK.glob('electrical_*/workspace.json'):
        data=engine.read(path)
        if data['ownerId']!=who['id']:continue
        state=engine.read(path.parent/'status.json')
        if state['status']=='analyzing' and state.get('processId')!=os.getpid():state={**state,'status':'failed','error':'Analysis was interrupted. Import the drawing again.'}
        rows.append({**data,**state})
    return {'projects':sorted(rows,key=lambda p:p['created'],reverse=True)}


@router.get('/sources')
def sources():
    user()
    from backend.api.edesign import reviews
    return {'drawings':[{'reviewId':r['id'],'name':r['name'],'pages':len(r['pages'])} for r in reviews()['reviews']]}


@router.post('/projects/from-review')
def from_review(payload:dict):
    user()
    from backend.api.edesign import workspace
    source,meta,_=workspace(str(payload.get('reviewId','')))
    key,folder=begin(meta['name'],{'reviewId':meta['id']})
    try:shutil.copyfile(source/'source.pdf',folder/'source.pdf');start(folder)
    except Exception:
        engine.write(folder/'status.json',{'status':'failed','error':'The source drawing could not be copied.'})
        SLOTS.release();raise
    return {'id':key,'status':'analyzing'}


@router.post('/projects')
async def upload(file:UploadFile=File(...),mode:str='electronics'):
    if mode not in {'electronics','industrial'}:raise HTTPException(400,'Choose Electronics or Industrial import mode.')
    key,folder=begin(Path((file.filename or 'Circuit.pdf').replace('\\','/')).name,{'mode':mode})
    try:
        size=0
        with (folder/'source.pdf').open('wb') as stream:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>75*1024*1024:raise HTTPException(413,'Use a PDF up to 75 MB.')
                stream.write(chunk)
        with (folder/'source.pdf').open('rb') as stream:
            if stream.read(5)!=b'%PDF-':raise HTTPException(400,'Choose a valid electrical drawing PDF.')
        start(folder)
    except Exception:
        engine.write(folder/'status.json',{'status':'failed','error':'The PDF upload did not finish. Choose a valid PDF up to 75 MB.'})
        SLOTS.release();raise
    finally:await file.close()
    return {'id':key,'status':'analyzing'}


@router.get('/projects/{key}')
def project(key:str):
    folder,meta,state=opened(key,False)
    if state['status']!='ready':return {**meta,**state}
    return {**meta,**state,**engine.read(folder/'drawing.json'),'layout':engine.read(folder/'layout.json')}


@router.put('/projects/{key}/layout')
def save_layout(key:str,payload:dict):return engine.update_layout(opened(key)[0],payload)


@router.get('/projects/{key}/scene/{number}')
def scene(key:str,number:int):
    folder,_,state=opened(key)
    if not 1<=number<=state['pageCount']:raise HTTPException(404,'Drawing page not found.')
    return engine.read(folder/f'scene-drawing-{number}.json')


@router.get('/projects/{key}/page/{number}')
def page(key:str,number:int,thumbnail:bool=False):
    folder,_,state=opened(key)
    if not 1<=number<=state['pageCount']:raise HTTPException(404,'Drawing page not found.')
    small=folder/f'thumb-{number}.png'
    return FileResponse(small if thumbnail and small.is_file() else folder/f'drawing-{number}.png',media_type='image/png')


@router.get('/projects/{key}/original')
def original(key:str):
    folder,meta,_=opened(key,False)
    if not (folder/'source.pdf').is_file():raise HTTPException(404,'This circuit was created natively and has no source PDF.')
    return FileResponse(folder/'source.pdf',media_type='application/pdf',filename=meta['name'])


@router.get('/projects/{key}/export')
def export(key:str):
    folder,_,_=opened(key)
    if not (folder/'source.pdf').is_file():raise HTTPException(409,'Use native SVG or circuit JSON export for this circuit.')
    handle=tempfile.NamedTemporaryFile(prefix='electrical-layout-',suffix='.pdf',delete=False);handle.close();path=Path(handle.name)
    try:engine.export_pdf(folder,path)
    except Exception:path.unlink(missing_ok=True);raise
    return FileResponse(path,media_type='application/pdf',filename='Unified_electrical_circuit.pdf',background=BackgroundTask(path.unlink,missing_ok=True))


@router.get('/projects/{key}/circuit')
def circuit(key:str):
    from backend.core.electrical_native import build
    return build(opened(key)[0])


@router.put('/projects/{key}/circuit')
def save_circuit(key:str,payload:dict):
    from backend.core.electrical_native import save
    return save(opened(key)[0],payload)


@router.post('/projects/{key}/simulate')
def simulate(key:str,payload:dict):
    from backend.core.electrical_native import build
    from backend.core.electrical_simulation import solve
    folder,_,_=opened(key);document=build(folder)
    if payload.get('version')!=document['version']:raise HTTPException(409,'Save or reopen the current circuit before simulating.')
    previous=engine.read(folder/'simulation.json') if (folder/'simulation.json').exists() and not payload.get('reset') else None
    result=solve(document,payload,previous)
    if build(folder)['version']!=document['version']:return {'status':'blocked','issues':['Circuit changed during simulation. Run again with the saved version.'],'issueCount':1}
    if result['status']=='complete':engine.write(folder/'simulation.json',result)
    return result


@router.get('/projects/{key}/circuit/export')
def export_circuit(key:str,format:str='svg'):
    from backend.core.electrical_native import build,svg
    data=build(opened(key)[0])
    if format=='svg':return Response(svg(data),media_type='image/svg+xml',headers={'Content-Disposition':'attachment; filename="Circuit.svg"'})
    if format=='json':return Response(json.dumps(data,ensure_ascii=False),media_type='application/json',headers={'Content-Disposition':'attachment; filename="Circuit.json"'})
    raise HTTPException(400,'Choose SVG or circuit JSON.')

@router.get('/projects/{key}/reconstruction')
def reconstruction_model(key:str):
    from backend.electrical.reconstruction import load
    return load(opened(key)[0])

@router.get('/projects/{key}/reconstruction/pages/{number}')
def reconstruction_page(key:str,number:int):
    from backend.electrical.reconstruction import load
    folder,_,_=opened(key);model=load(folder)
    if not 1<=number<=len(model['pages']):raise HTTPException(404,'Source page not found.')
    return engine.read(folder/model['pages'][number-1]['geometry_file'])

@router.post('/projects/{key}/reconstruction/review')
def reconstruction_review(key:str,payload:dict):
    from backend.electrical.reconstruction import review
    return review(opened(key)[0],payload,user())

@router.post('/projects/{key}/reconstruction/review-page')
def reconstruction_review_page(key:str,payload:dict):
    from backend.electrical.reconstruction import review_page
    return review_page(opened(key)[0],payload,user())

@router.get('/projects/{key}/reconstruction/pages/{number}/graphical')
def reconstruction_graphical(key:str,number:int):
    from backend.electrical.reconstruction import load
    folder,_,_=opened(key);model=load(folder)
    if not 1<=number<=len(model['pages']):raise HTTPException(404,'Source page not found.')
    path=folder/f'electrical-graphical-{number}.json'
    if not path.exists():raise HTTPException(409,'Reimport this source to extract independent vector paths.')
    return engine.read(path)

@router.post('/projects/{key}/reconstruction/validate-scope')
def reconstruction_scope(key:str,payload:dict):
    from backend.electrical.reconstruction import load,validate
    model=load(opened(key)[0]);pages=payload.get('pages')
    if not isinstance(pages,list) or not pages or any(type(p) is not int or not 1<=p<=len(model['pages']) for p in pages):raise HTTPException(400,'Select valid source pages for the simulation scope.')
    return validate(model,pages=pages)

@router.get('/projects/{key}/reconstruction/validate')
def reconstruction_validate(key:str,page:int|None=None):
    from backend.electrical.reconstruction import load,validate
    model=load(opened(key)[0])
    if page is not None and not 1<=page<=len(model['pages']):raise HTTPException(404,'Source page not found.')
    return validate(model,page)

@router.post('/projects/{key}/reconstruction/compile')
def reconstruction_compile(key:str,payload:dict):
    from backend.electrical.reconstruction import load,validate
    model=load(opened(key)[0]);page=payload.get('page')
    if type(page) is not int or not 1<=page<=len(model['pages']):raise HTTPException(400,'Choose a source page to compile.')
    result=validate(model,page)
    if result['status']!='verified':raise HTTPException(409,{'message':'Resolve and verify all connections on the selected page first.','validation':result})
    return {'kind':'continuity_only','source_sha256':model['source']['sha256'],'revision':model['revision'],'page':page,'connections':[c for c in model['connections'] if c['source']['page']==page],'simulation_ready':False,'notice':'Verified pin assignments only. No supply, relay, motor or machine behavior inferred.'}

@router.get('/projects/{key}/reconstruction/pages/{number}/preview')
def reconstruction_preview(key:str,number:int):
    from backend.electrical.reconstruction import load
    import io
    import pypdfium2 as pdfium
    folder,_,_=opened(key);model=load(folder)
    if not 1<=number<=len(model['pages']):raise HTTPException(404,'Source page not found.')
    pdf=pdfium.PdfDocument(str(folder/'source.pdf'))
    try:
        page=pdf[number-1]
        try:
            width,height=page.get_size();bitmap=page.render(scale=min(2,1800/max(width,height)))
            try:
                image=bitmap.to_pil();stream=io.BytesIO();image.save(stream,format='PNG')
            finally:bitmap.close()
        finally:page.close()
    finally:pdf.close()
    return Response(stream.getvalue(),media_type='image/png',headers={'Cache-Control':'private, no-store'})
