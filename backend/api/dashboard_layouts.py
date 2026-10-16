"""Shared workbook starters and private layout copies in the knowledge folder."""
import hashlib
import json
import re
import threading
from datetime import datetime,timezone
from uuid import uuid4
from fastapi import APIRouter,HTTPException,Request
from backend.core.runtime import KNOWLEDGE
from backend.core.run_history import write_json

router=APIRouter(prefix='/api/nami/dashboard-layouts',tags=['Dashboard knowledge layouts'])
LOCK=threading.RLock()


def root():return KNOWLEDGE/'dashboard_layouts'


def personal(user):
    identity=str(user['id'])
    # 128-bit account key also leaves room for atomic filenames on Windows.
    return root()/'users'/hashlib.sha256(identity.encode()).hexdigest()[:32]


def remove_user(user_id):
    folder=personal({'id':user_id})
    if folder.is_symlink() or not folder.resolve().is_relative_to((root()/'users').resolve()):return
    with LOCK:
        for path in folder.glob('*.json'):
            if path.is_file() and not path.is_symlink():path.unlink()


def catalog():
    path=root()/'catalog.json'
    return json.loads(path.read_text(encoding='utf-8')).get('templates',[]) if path.is_file() else []


@router.get('')
def list_layouts(request:Request):
    saved=[]
    for path in personal(request.state.user).glob('*.json'):
        if path.is_symlink():continue
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            saved.append({key:data[key] for key in ('id','name','savedAt','dashboardCount')})
        except (ValueError,KeyError,OSError):continue
    return {'accountId':request.state.user['id'],'templates':catalog(),'saved':sorted(saved,key=lambda row:row['savedAt'],reverse=True)}


@router.get('/starter/{layout_id}')
def starter(layout_id:str):
    item=next((item for item in catalog() if item.get('id')==layout_id),None)
    if not item:raise HTTPException(404,'Starter layout not found.')
    path=(root()/item['file']).resolve()
    if not path.is_relative_to(root().resolve()) or path.is_symlink():raise HTTPException(400,'Invalid layout location.')
    from backend.core.data_model_rules import load_rules,apply_starter
    config,revision=load_rules(KNOWLEDGE/'master/data_model_rules.json')
    return {**apply_starter(json.loads(path.read_text(encoding='utf-8')),config),'mappingRulesRevision':revision}


def saved_file(request,layout_id):
    if not re.fullmatch(r'[a-f0-9]{32}',layout_id):raise HTTPException(404,'Saved layout not found.')
    path=personal(request.state.user)/(layout_id+'.json')
    if not path.is_file() or path.is_symlink():raise HTTPException(404,'Saved layout not found.')
    return path


@router.get('/saved/{layout_id}')
def get_saved(request:Request,layout_id:str):
    return {'accountId':request.state.user['id'],**json.loads(saved_file(request,layout_id).read_text(encoding='utf-8'))}


@router.post('/saved')
async def save_layout(request:Request):
    # Check length while streaming, before parsing user-controlled JSON.
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>16*1024*1024:raise HTTPException(413,'A layout transfer must be smaller than 16 MB.')
    try:
        payload=json.loads(content);layout=payload['layout']
        if payload.get('accountId')!=request.state.user['id']:raise HTTPException(409,'The account changed. Reload before saving.')
        name=payload.get('name','').strip()
        if not name or len(name)>80:raise ValueError('Use a layout name of 1-80 characters.')
        if layout.get('schemaVersion')!=2 or not isinstance(layout.get('dashboards'),list) or not 1<=len(layout['dashboards'])<=20:raise ValueError('Invalid dashboard library.')
        if len(json.dumps(layout,separators=(',',':'),ensure_ascii=False).encode())>8*1024*1024:raise ValueError('Keep dashboard configuration below 8 MB.')
        for board in layout['dashboards']:
            if not isinstance(board.get('cards'),list) or len(board['cards'])>32 or board.get('mode') not in ('live','report'):raise ValueError('Invalid dashboard.')
            for card in board['cards']:
                values=[card]+card.get('series',[])
                if len(values)>12:raise ValueError('A widget supports 12 parameters.')
                for value in values:
                    if not isinstance(value.get('inputs'),list) or len(value['inputs'])>12 or value.get('kind')=='direct' and len(value['inputs'])!=1:raise ValueError('Invalid widget inputs.')
                    if len(str(value.get('expression','')))>400:raise ValueError('Formula is too long.')
        record={'id':uuid4().hex,'name':name,'savedAt':datetime.now(timezone.utc).isoformat(),
                'dashboardCount':len(layout['dashboards']),'layout':layout}
        with LOCK:
            folder=personal(request.state.user)
            if len(list(folder.glob('*.json')))>=100:raise HTTPException(400,'Keep at most 100 knowledge layout copies. Remove an older copy first.')
            write_json(folder/(record['id']+'.json'),record)
        return {'accountId':request.state.user['id'],'id':record['id'],
                'location':f'knowledge/dashboard_layouts/users/{folder.name}/{record["id"]}.json'}
    except (ValueError,KeyError,TypeError,AttributeError) as error:raise HTTPException(400,str(error))


@router.delete('/saved/{layout_id}')
def remove_saved(request:Request,layout_id:str):
    with LOCK:saved_file(request,layout_id).unlink()
    return {'accountId':request.state.user['id'],'removed':layout_id}
