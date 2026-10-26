"""Resumable bounded uploads and content-addressed WorkHub project revisions."""
from __future__ import annotations
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import queue
import re
import shutil
import threading
import time
import zipfile
from fastapi import HTTPException
from .workhub import store, identity, timestamp, text, encode

CHUNK=8*1024*1024
MAX_FILE=int(os.getenv('USOPP_WORKHUB_MAX_FILE_BYTES',str(4*1024**3)))
MAX_STORAGE=int(os.getenv('USOPP_WORKHUB_STORAGE_BYTES',str(100*1024**3)))
UPLOAD_LOCKS=[threading.RLock() for _ in range(64)]
BLOB_LOCK=threading.RLock()

def upload_lock(key):return UPLOAD_LOCKS[int(hashlib.sha256(str(key).encode()).hexdigest()[:4],16)%len(UPLOAD_LOCKS)]
def relative_name(value):
    name=text(value,500,True).replace('\\','/')
    parts=PurePosixPath(name)
    if parts.is_absolute() or any(part in {'','..','.'} or ':' in part or any(ord(c)<32 for c in part) for part in name.split('/')):
        raise HTTPException(400,'Choose a normal relative file name without parent paths.')
    return name
def part_path(key):
    if not re.fullmatch('[0-9a-f]{32}',str(key)):raise HTTPException(404,'Upload not found.')
    folder=store.root/'uploads';folder.mkdir(exist_ok=True)
    return folder/(key+'.part')
def blob_path(digest):
    if not re.fullmatch('[0-9a-f]{64}',str(digest)):raise HTTPException(400,'Invalid stored file identity.')
    return store.root/'blobs'/digest[:2]/digest
def cleanup_uploads():
    with store.db() as db:
        stale=db.execute("SELECT id FROM uploads WHERE status='uploading' AND updated<?",(time.time()-7*86400,)).fetchall()
    for row in stale:
        with upload_lock(row['id']),store.db(True) as db:
            current=db.execute('SELECT status,updated FROM uploads WHERE id=?',(row['id'],)).fetchone()
            if current and current['status']=='uploading' and current['updated']<time.time()-7*86400:
                part_path(row['id']).unlink(missing_ok=True)
                db.execute("UPDATE uploads SET status='expired' WHERE id=?",(row['id'],))
def begin(user,project,payload):
    store.actor(user);name=relative_name(payload.get('name',''));size=payload.get('size')
    if type(size) is not int or size<0 or size>MAX_FILE:raise HTTPException(413,f'Each file must be at most {MAX_FILE//1024**2} MB.')
    with store.db(True) as db:
        store.contribute(db,project,user)
        physical=db.execute('SELECT COALESCE(SUM(size),0) FROM (SELECT MAX(size) AS size FROM files GROUP BY sha256)').fetchone()[0]
        reserved=db.execute("SELECT COALESCE(SUM(size),0) FROM uploads WHERE status='uploading'").fetchone()[0]
        if physical+reserved+size>MAX_STORAGE:raise HTTPException(413,'WorkHub storage quota reached. Ask Admin to review stored revisions.')
        if size>shutil.disk_usage(store.root).free-256*1024**2:raise HTTPException(413,'The server does not have enough free disk space for this file.')
        key=identity();now=time.time();part_path(key).touch(exist_ok=False)
        db.execute('INSERT INTO uploads(id,project_id,owner_id,name,size,created,updated) VALUES(?,?,?,?,?,?,?)',(key,project,user['id'],name,size,now,now))
        return {'id':key,'received':0,'size':size,'chunkBytes':CHUNK}
def get_upload(user,key):
    with store.db() as db:row=db.execute('SELECT * FROM uploads WHERE id=? AND owner_id=?',(key,user['id'])).fetchone()
    if not row:raise HTTPException(404,'Upload not found for this account.')
    return dict(row)
def append(user,key,offset,content):
    with upload_lock(key):
        row=get_upload(user,key)
        if row['status']!='uploading':raise HTTPException(409,'This upload is no longer accepting chunks.')
        if not content or len(content)>CHUNK or type(offset) is not int:raise HTTPException(400,'Provide a nonempty chunk of at most 8 MB.')
        if offset<0 or offset+len(content)>row['size']:raise HTTPException(400,'Chunk exceeds the declared file size.')
        path=part_path(key)
        with path.open('r+b') as output:
            # A crash between writing and committing the offset leaves a tail to retry.
            output.truncate(row['received'])
            if offset!=row['received']:
                if offset+len(content)<=row['received']:
                    output.seek(offset)
                    if output.read(len(content))==content:return {'received':row['received']}
                raise HTTPException(409,'Upload offset changed. Resume from the current received offset.')
            output.seek(offset);output.write(content);output.flush();os.fsync(output.fileno())
        with store.db(True) as db:db.execute('UPDATE uploads SET received=?,updated=? WHERE id=?',(offset+len(content),time.time(),key))
        return {'received':offset+len(content)}
def finish(user,key):
    with upload_lock(key):
        row=get_upload(user,key)
        if row['status']=='completed':
            with store.db() as db:return dict(db.execute('SELECT * FROM files WHERE id=?',(row['file_id'],)).fetchone())
        if row['status']!='uploading' or row['received']!=row['size']:raise HTTPException(409,'Finish uploading every chunk first.')
        path=part_path(key)
        with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
        dest=blob_path(digest);dest.parent.mkdir(parents=True,exist_ok=True)
        # Keep the resumable part until its database record commits. Hard links
        # avoid a second physical copy on the normal NTFS/ext4 storage volume.
        with BLOB_LOCK:
            if not dest.exists():
                try:os.link(path,dest)
                except OSError:
                    staging=dest.with_suffix('.pending')
                    try:
                        shutil.copyfile(path,staging);os.replace(staging,dest)
                    finally:staging.unlink(missing_ok=True)
            file_id=identity()
            with store.db(True) as db:
                store.contribute(db,row['project_id'],user)
                db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?)',(file_id,row['project_id'],user['id'],row['name'],digest,row['size'],timestamp()))
                db.execute("UPDATE uploads SET status='completed',file_id=?,updated=? WHERE id=?",(file_id,time.time(),key))
                record=dict(db.execute('SELECT * FROM files WHERE id=?',(file_id,)).fetchone())
            path.unlink(missing_ok=True)
            return record
def cancel(user,key):
    with upload_lock(key):
        row=get_upload(user,key)
        if row['status']=='uploading':
            part_path(key).unlink(missing_ok=True)
            with store.db(True) as db:db.execute("UPDATE uploads SET status='cancelled' WHERE id=?",(key,))
        return {'status':'cancelled'}
def file_record(key,project=None):
    with store.db() as db:row=db.execute('SELECT * FROM files WHERE id=?',(key,)).fetchone()
    if not row or project and row['project_id']!=project:raise HTTPException(404,'Project file not found.')
    path=blob_path(row['sha256'])
    if not path.is_file():raise HTTPException(404,'The stored project file is unavailable.')
    return dict(row),path
def revision(user,project,payload):
    with store.db(True) as db:
        item=store.contribute(db,project,user);store.manage(item,user)
        if item['stage'] not in {'todo','development','blocked'}:raise HTTPException(409,'Request changes or reopen development before adding a new project revision.')
        values=payload.get('file_ids',[])
        if not isinstance(values,list) or not values or len(values)>50000:raise HTTPException(400,'Select 1..50,000 files for a revision.')
        available={row['id']:dict(row) for row in db.execute('SELECT * FROM files WHERE project_id=?',(project,))}
        selected={};base=payload.get('base_revision')
        if base:
            if not isinstance(base,str):raise HTTPException(400,'Choose a saved base revision.')
            latest=db.execute('SELECT * FROM revisions WHERE project_id=? ORDER BY created_at DESC LIMIT 1',(project,)).fetchone()
            if not latest or latest['id']!=base:raise HTTPException(409,'A newer project revision was saved. Reopen the upload dialog before merging unchanged files.')
            import json
            for key in json.loads(latest['file_ids']):
                if key not in available:raise HTTPException(409,'A base revision file is unavailable.')
                selected[available[key]['name'].casefold()]=available[key]
        for key in values:
            if not isinstance(key,str):raise HTTPException(400,'Choose stored project files.')
            row=available.get(key)
            if not row:raise HTTPException(400,'Choose files from this project.')
            selected[row['name'].casefold()]=row
        if len(selected)>50000:raise HTTPException(400,'Each revision supports at most 50,000 file paths.')
        total=sum(row['size'] for row in selected.values())
        count=db.execute('SELECT COUNT(*) FROM revisions WHERE project_id=?',(project,)).fetchone()[0]
        key=identity();label=text(payload.get('label') or f'V{count+1}',100,True);now=timestamp()
        db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)',(key,project,label,encode([row['id'] for row in selected.values()]),user['id'],now,text(payload.get('description',''),4000)))
        db.execute('UPDATE items SET updated_at=?,version=version+1 WHERE id=?',(now,project))
        store.event(db,item,user,'revision_uploaded',{'revision_id':key,'label':label,'files':len(selected),'bytes':total})
        return {'id':key,'label':label,'file_count':len(selected),'bytes':total}
def revision_files(key):
    import json
    with store.db() as db:
        row=db.execute('SELECT * FROM revisions WHERE id=?',(key,)).fetchone()
        if not row:raise HTTPException(404,'Revision not found.')
        available={entry['id']:dict(entry) for entry in db.execute('SELECT * FROM files WHERE project_id=?',(row['project_id'],))}
    files=[]
    for file_id in json.loads(row['file_ids']):
        entry=available.get(file_id)
        if not entry:raise HTTPException(404,'A revision file is unavailable.')
        path=blob_path(entry['sha256'])
        if not path.is_file():raise HTTPException(404,'A stored revision file is unavailable.')
        files.append((entry,path))
    return dict(row),files
def stream_revision(files):
    """ZIP64 stream using a bounded queue; no 2 GB server-side download copy."""
    output=queue.Queue(maxsize=4);stop=threading.Event()
    def emit(value):
        while not stop.is_set():
            try:output.put(value,timeout=.2);return
            except queue.Full:pass
        raise BrokenPipeError('Download closed.')
    class Sink:
        def __init__(self):self.offset=0
        def write(self,data):
            self.offset+=len(data)
            if data:emit(bytes(data))
            return len(data)
        def tell(self):return self.offset
        def flush(self):pass
        def seekable(self):return False
    def produce():
        try:
            with zipfile.ZipFile(Sink(),'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
                for row,path in files:
                    with archive.open(relative_name(row['name']),'w',force_zip64=True) as target,path.open('rb') as source:
                        while block:=source.read(1024*1024):target.write(block)
            emit(None)
        except BrokenPipeError:pass
        except Exception as error:emit(error)
    thread=threading.Thread(target=produce,daemon=True,name='workhub-download');thread.start()
    try:
        while True:
            try:block=output.get(timeout=1)
            except queue.Empty:
                if not thread.is_alive():raise OSError('Revision download interrupted.')
                continue
            if block is None:break
            if isinstance(block,Exception):raise block
            yield block
    finally:stop.set();thread.join(timeout=1)
def storage_usage():
    with store.db() as db:
        logical=db.execute('SELECT COALESCE(SUM(size),0) FROM files').fetchone()[0]
        revisions=db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0]
        physical=db.execute('SELECT COALESCE(SUM(size),0) FROM (SELECT MAX(size) AS size FROM files GROUP BY sha256)').fetchone()[0]
    return {'storedBytes':physical,'logicalBytes':logical,'savedBytes':max(0,logical-physical),'quotaBytes':MAX_STORAGE,'maxFileBytes':MAX_FILE,'revisionCount':revisions,'chunkBytes':CHUNK}
