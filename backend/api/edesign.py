"""Persistent circuit PDF reviews. Source drawings are immutable; markups are separate."""
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
import hashlib
import json
import math
import re
import shutil
import sqlite3
import time
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from backend.core import accounts
from backend.core import edesign_history as history
from backend.core.access import claim_resource
from backend.core.run_history import current_user
from backend.core.runtime import WORK
from python_engine.circuit_compare import PDFIUM_LOCK

router = APIRouter(prefix='/api/e-design', tags=['e-design review'])
MAX_BYTES = 75 * 1024 * 1024


def user():
    value = current_user.get()
    if not value: raise HTTPException(401, 'Sign in to review drawings.')
    return value


@contextmanager
def database(folder):
    connection = sqlite3.connect(str(folder / 'review.sqlite3'), timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        # Serialize first-open migrations when list/open requests overlap.
        connection.execute('BEGIN IMMEDIATE')
        history.migrate(connection)
        connection.commit()
        with connection: yield connection
    finally: connection.close()


def workspace(sid, write=False, manage=False):
    if not re.fullmatch(r'edesign_[a-f0-9]{32}', sid): raise HTTPException(404, 'Review not found.')
    folder = WORK / sid
    manifest = folder / 'review.json'
    if not manifest.is_file(): raise HTTPException(404, 'Review not found.')
    meta = json.loads(manifest.read_text(encoding='utf-8'))
    who = user()
    access = 'owner' if who['id'] == meta['ownerId'] or who.get('role') == 'admin' else ''
    if not access:
        with database(folder) as db:
            row = db.execute('SELECT access FROM members WHERE user_id=?', (who['id'],)).fetchone()
        access = row['access'] if row else ''
    if not access or (write and access == 'view') or (manage and access != 'owner'):
        raise HTTPException(403, 'This drawing review is not shared with the required access.')
    return folder, meta, access


def public_mark(row):
    return history.public(row)


class Markup(BaseModel):
    page: int = Field(ge=1)
    kind: Literal['modify', 'add', 'remove', 'comment'] = 'modify'
    shape: Literal['rectangle', 'cloud', 'arrow', 'note'] = 'rectangle'
    box: list[float] = Field(min_length=4, max_length=4)
    body: str = Field(min_length=1, max_length=6000)
    status: Literal['open', 'resolved'] = 'open'
    reverseX: bool = False
    reverseY: bool = False
    version: int = Field(default=0, ge=0)

    @model_validator(mode='after')
    def geometry(self):
        if not self.body.strip(): raise ValueError('Enter a correction comment.')
        x0, y0, x1, y1 = self.box
        if not all(math.isfinite(n) and 0 <= n <= 1 for n in self.box) or x1-x0 < .001 or y1-y0 < .001:
            raise ValueError('Select an area inside the drawing.')
        self.body = self.body.strip()
        return self


def create_review(folder, sid, name, who):
    from pypdf import PdfReader
    import pypdfium2 as pdfium
    reader = PdfReader(folder / 'source.pdf')
    if reader.is_encrypted: raise ValueError('Upload an unlocked PDF.')
    if not 1 <= len(reader.pages) <= 150: raise ValueError('Use a drawing set with 1–150 pages.')
    from python_engine.edesign_pdf import read_review,review_background
    imported=read_review(folder/'source.pdf')
    review_background(folder/'source.pdf',folder/'background.pdf')
    # PDFium returns displayed dimensions, including rotation/crop, matching previews.
    with PDFIUM_LOCK:
        with pdfium.PdfDocument(str(folder / 'source.pdf')) as doc:
            pages = [{'number': i+1, 'width': doc.get_page_size(i)[0], 'height': doc.get_page_size(i)[1]} for i in range(len(doc))]
    with database(folder) as db:
        db.executescript('''
            CREATE TABLE marks (id TEXT PRIMARY KEY, page INTEGER NOT NULL, kind TEXT NOT NULL,
                shape TEXT NOT NULL, box TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL,
                author_id INTEGER NOT NULL, author TEXT NOT NULL, created REAL NOT NULL,
                updated REAL NOT NULL, version INTEGER NOT NULL, reverse_x INTEGER NOT NULL, reverse_y INTEGER NOT NULL);
            CREATE TABLE members (user_id INTEGER PRIMARY KEY, access TEXT NOT NULL);
            CREATE TABLE events (id INTEGER PRIMARY KEY, at REAL NOT NULL, actor INTEGER NOT NULL,
                action TEXT NOT NULL, mark_id TEXT, snapshot TEXT NOT NULL);
        ''')
        history.migrate(db)
        incoming=[]
        for mark in imported['marks']:
            payload=Markup(**mark)
            incoming.append({**payload.model_dump(),'id':mark['id'],'author':mark['author'],'author_id':who['id'],'deleted':False})
        if incoming:
            history.change(db,incoming,who,'import PDF comments','PDF file / reported authors')
            for mark in imported['marks']:history.retain_portable(db,mark)
    meta = {'id': sid, 'name': name, 'ownerId': who['id'], 'owner': who['username'], 'created': time.time(),
            'pages': pages, 'sourceHash': hashlib.sha256((folder / 'source.pdf').read_bytes()).hexdigest()}
    envelope=imported['envelope']
    if re.fullmatch(r'edesign_[a-f0-9]{32}',str(envelope.get('reviewId',''))):
        meta.update(lineageId=envelope['reviewId'],originSourceHash=envelope.get('sourceHash',''))
    meta['importedComments']=len(imported['marks'])
    if imported['skipped']:meta['importNotice']=f'{imported["skipped"]} unsupported annotations remain in the original PDF.'
    (folder / 'review.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    claim_resource(folder, who)
    return meta


@router.post('')
async def upload(file: UploadFile = File(...)):
    who = user()
    sid = 'edesign_' + uuid.uuid4().hex
    folder = WORK / sid
    folder.mkdir(parents=True)
    try:
        size = 0
        with (folder / 'source.pdf').open('wb') as stream:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES: raise HTTPException(413, 'The PDF must be 75 MB or smaller.')
                stream.write(chunk)
        with (folder / 'source.pdf').open('rb') as stream:
            if not stream.read(5).startswith(b'%PDF-'): raise HTTPException(400, 'Upload a PDF drawing.')
        name = re.split(r'[/\\]', file.filename or 'Drawing.pdf')[-1][:200]
        meta = await run_in_threadpool(create_review, folder, sid, name, who)
        return read(sid)
    except Exception as error:
        # Only this request's generated workspace may be cleaned up on failure.
        if folder.resolve().parent == WORK.resolve() and folder.name == sid:
            shutil.rmtree(folder)
        if isinstance(error, HTTPException): raise
        raise HTTPException(400, 'The PDF could not be opened. Use an unlocked, valid PDF with up to 150 pages.') from error
    finally: await file.close()


@router.get('')
def reviews():
    user()
    values = []
    for manifest in WORK.glob('edesign_*/review.json'):
        try:
            folder, meta, access = workspace(manifest.parent.name)
            with database(folder) as db:
                counts = dict(db.execute('SELECT status,count(*) FROM marks WHERE deleted=0 GROUP BY status').fetchall())
            values.append({**meta, 'access': access, 'open': counts.get('open', 0), 'resolved': counts.get('resolved', 0)})
        except HTTPException as error:
            if error.status_code not in (403, 404): raise
    return {'reviews': sorted(values, key=lambda v: v['created'], reverse=True)}


@router.get('/people')
def people():
    user()
    return {'people': [{'id': u['id'], 'username': u['username'], 'designation': u['designation']}
                       for u in accounts.store.list_users() if u['active'] and u['approved']]}


@router.get('/{sid}')
def read(sid: str):
    folder, meta, access = workspace(sid)
    with database(folder) as db:
        marks = [public_mark(row) for row in db.execute('SELECT * FROM marks WHERE deleted=0 ORDER BY page,created')]
        members = [dict(row) for row in db.execute('SELECT * FROM members')] if access == 'owner' else []
        commands=history.stacks(db,user())
    return {**meta, 'access': access, 'marks': marks, 'members': members, 'commands':commands}


@router.get('/{sid}/original')
def original(sid: str):
    folder, meta, _ = workspace(sid)
    return FileResponse(folder / 'source.pdf', media_type='application/pdf', filename=meta['name'])


@router.get('/{sid}/page/{number}')
def preview(sid: str, number: int):
    folder, meta, _ = workspace(sid)
    if not 1 <= number <= len(meta['pages']): raise HTTPException(404, 'Page not found.')
    image = folder / f'page-{number}.png'
    with PDFIUM_LOCK:
        if not image.exists():
            import pypdfium2 as pdfium
            with pdfium.PdfDocument(str(folder / ('background.pdf' if (folder/'background.pdf').exists() else 'source.pdf'))) as doc:
                page = doc[number-1]
                try:
                    bitmap = page.render(scale=min(2000/page.get_width(), 2600/page.get_height()),draw_annots=True)
                    try: bitmap.to_pil().convert('RGB').save(image)
                    finally: bitmap.close()
                finally: page.close()
    return FileResponse(image, media_type='image/png')


@router.post('/{sid}/marks')
def add_mark(sid: str, payload: Markup):
    folder, meta, _ = workspace(sid, write=True)
    if payload.page > len(meta['pages']): raise HTTPException(400, 'Page not found.')
    if payload.version != 0: raise HTTPException(400, 'New markups must start at version zero.')
    who, mark_id, now = user(), uuid.uuid4().hex, time.time()
    with database(folder) as db:
        db.execute('BEGIN IMMEDIATE')
        values,command=history.change(db,[{**payload.model_dump(),'id':mark_id,'author':who['username'],'author_id':who['id'],'created':now,'deleted':False}],who,'create')
        return {**values[mark_id],'commandId':command,'commands':history.stacks(db,who)}


def editable_mark(db, mark_id, access):
    row = db.execute('SELECT * FROM marks WHERE id=?', (mark_id,)).fetchone()
    if not row or row['deleted']: raise HTTPException(404, 'Correction not found.')
    # Shared review access explicitly permits editing comments; view-only access
    # is rejected by workspace(write=True). Each editor is retained in history.
    return row


@router.put('/{sid}/marks/{mark_id}')
def update_mark(sid: str, mark_id: str, payload: Markup):
    folder, meta, access = workspace(sid, write=True)
    if payload.page > len(meta['pages']): raise HTTPException(400, 'Page not found.')
    with database(folder) as db:
        db.execute('BEGIN IMMEDIATE')
        old = editable_mark(db, mark_id, access)
        if old['version'] != payload.version: raise HTTPException(409, 'This correction changed in another window. Refresh comments before editing.')
        action=('resolve' if payload.status=='resolved' else 'reopen') if old['status']!=payload.status else 'update'
        values,command=history.change(db,[{**public_mark(old),**payload.model_dump()}],user(),action)
        return {**values[mark_id],'commandId':command,'commands':history.stacks(db,user())}


@router.delete('/{sid}/marks/{mark_id}')
def delete_mark(sid: str, mark_id: str, version: int):
    folder, _, access = workspace(sid, write=True)
    with database(folder) as db:
        db.execute('BEGIN IMMEDIATE')
        old = editable_mark(db, mark_id, access)
        if old['version'] != version: raise HTTPException(409, 'This correction changed. Refresh comments first.')
        history.change(db,[{**public_mark(old),'deleted':True}],user(),'delete')
        commands=history.stacks(db,user())
    return {'removed':mark_id,'commands':commands}


@router.get('/{sid}/marks/{mark_id}/history')
def comment_history(sid:str,mark_id:str):
    folder,_,_=workspace(sid)
    with database(folder) as db:
        if not history.current(db,mark_id):raise HTTPException(404,'Correction not found.')
        return {'revisions':history.history(db,mark_id)}


class HistoryAction(BaseModel):
    commandId:int


@router.post('/{sid}/history/{direction}')
def undo_redo(sid:str,direction:Literal['undo','redo'],payload:HistoryAction):
    folder,_,_=workspace(sid,write=True)
    with database(folder) as db:
        db.execute('BEGIN IMMEDIATE')
        history.travel(db,user(),direction,payload.commandId)
    return read(sid)


class Restore(BaseModel):
    revision:int=Field(ge=1)
    version:int=Field(ge=1)


@router.post('/{sid}/marks/{mark_id}/restore')
def restore(sid:str,mark_id:str,payload:Restore):
    folder,_,_=workspace(sid,write=True)
    with database(folder) as db:
        db.execute('BEGIN IMMEDIATE')
        current=history.current(db,mark_id)
        if not current:raise HTTPException(404,'Correction not found.')
        if current['version']!=payload.version:raise HTTPException(409,'The comment changed. Refresh before restoring.')
        row=db.execute('SELECT snapshot FROM revisions WHERE mark_id=? AND version=?',(mark_id,payload.revision)).fetchone()
        if not row:raise HTTPException(404,'Revision not found.')
        history.change(db,[{**json.loads(row['snapshot']),'deleted':False}],user(),f'restore revision {payload.revision}')
    return read(sid)


class Share(BaseModel):
    userId: int
    access: Literal['review', 'view', 'remove'] = 'review'


@router.post('/{sid}/share')
def share(sid: str, payload: Share):
    folder, meta, _ = workspace(sid, manage=True)
    candidates = {u['id']: u for u in accounts.store.list_users() if u['active'] and u['approved']}
    if payload.userId not in candidates or payload.userId == meta['ownerId']:
        raise HTTPException(400, 'Select another enabled account.')
    with database(folder) as db:
        if payload.access == 'remove': db.execute('DELETE FROM members WHERE user_id=?',(payload.userId,))
        else: db.execute('INSERT OR REPLACE INTO members VALUES (?,?)',(payload.userId,payload.access))
        db.execute('INSERT INTO events(at,actor,action,snapshot) VALUES (?,?,?,?)',
                   (time.time(),user()['id'],'share',payload.model_dump_json()))
    return {'shared':True}


def import_feedback(folder,meta,path,who):
    from python_engine.edesign_pdf import read_review
    parsed=read_review(path);envelope=parsed['envelope']
    if (envelope.get('reviewId')!=meta.get('lineageId',meta['id']) or
        envelope.get('sourceHash')!=meta.get('originSourceHash',meta['sourceHash']) or
        parsed['pages']!=len(meta['pages'])):
        raise HTTPException(400,'This feedback PDF is not from this drawing review. Upload it as a separate review instead.')
    if not parsed['marks'] and envelope.get('marks'):
        raise HTTPException(400,'This PDF has no editable review comments. Import the saved review PDF, not a flattened or printed copy.')
    changes=[];unchanged=0
    with database(folder) as db:
        db.execute('BEGIN IMMEDIATE')
        for item in parsed['marks']:
            payload=Markup(**item)
            existing=history.current(db,item['id'])
            incoming=payload.model_dump()
            if existing:
                baseline=item['baseline'];expected=baseline.get('snapshot',{})
                equal=lambda a,b:all(a.get(k)==b.get(k) for k in history.FIELDS)
                if equal(incoming,existing):unchanged+=1;continue
                # A stale, unchanged PDF must not revert newer server comments.
                if equal(incoming,expected):unchanged+=1;continue
                if existing['deleted'] or not equal(existing,expected):
                    raise HTTPException(409,'A returned comment conflicts with a newer local revision. No comments were imported; review the returned PDF separately.')
                incoming={**existing,**incoming}
            else:incoming={**incoming,'author':item['author'],'author_id':who['id'],'deleted':False}
            incoming['id']=item['id'];changes.append(incoming)
        if changes:history.change(db,changes,who,'import feedback','Returned PDF / reported reviewer comments')
        for item in parsed['marks']:history.retain_portable(db,item,keep_base=False)
    return {'updated':len(changes),'unchanged':unchanged,'unmatched':len(envelope.get('marks',[]))-len([m for m in parsed['marks'] if m.get('reportedVersion')])}


@router.post('/{sid}/import')
async def import_pdf(sid:str,file:UploadFile=File(...)):
    folder,meta,_=workspace(sid,write=True)
    target=folder/f'feedback-{uuid.uuid4().hex}.pdf'
    try:
        size=0
        with target.open('wb') as stream:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>MAX_BYTES:raise HTTPException(413,'The feedback PDF must be 75 MB or smaller.')
                stream.write(chunk)
        result=await run_in_threadpool(import_feedback,folder,meta,target,user())
        return {**read(sid),'importSummary':result}
    except HTTPException:raise
    except (ValueError,KeyError,TypeError) as error:raise HTTPException(400,'The PDF comments or revision data could not be imported.') from error
    finally:target.unlink(missing_ok=True);await file.close()


@router.get('/{sid}/export/{format}')
def export(sid: str, format: Literal['pdf','report','docx','csv','html']):
    folder, meta, _ = workspace(sid)
    with database(folder) as db:
        marks = [public_mark(row) for row in db.execute('SELECT * FROM marks WHERE deleted=0 ORDER BY page,created')]
        for mark in marks:mark['history']=history.portable_history(db,mark['id'])
        for mark in marks:
            baseline=db.execute('SELECT version,snapshot FROM portable_bases WHERE mark_id=?',(mark['id'],)).fetchone()
            if baseline:mark['baseline']={'version':baseline['version'],'snapshot':json.loads(baseline['snapshot'])}
    from python_engine.edesign_export import export_review
    extension='pdf' if format=='report' else format
    target = folder / f'export-{uuid.uuid4().hex}.{extension}'
    try:
        if format=='html':
            with PDFIUM_LOCK:export_review(folder / 'source.pdf', meta, marks, target, format)
        else:export_review(folder / 'source.pdf', meta, marks, target, format)
    except ValueError as error:
        target.unlink(missing_ok=True)
        raise HTTPException(400,str(error)) from error
    except Exception:
        target.unlink(missing_ok=True)
        raise
    types = {'pdf':'application/pdf','report':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','csv':'text/csv','html':'text/html; charset=utf-8'}
    return FileResponse(target, media_type=types[format], filename=f'{Path(meta["name"]).stem}-review.{extension}',
                        background=BackgroundTask(target.unlink, missing_ok=True))
