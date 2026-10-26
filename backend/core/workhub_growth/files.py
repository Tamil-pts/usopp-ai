"""Private, bounded contribution/evidence attachments in the central data volume."""
import hashlib
import os
from pathlib import Path
import re
import tempfile
from fastapi import HTTPException
from . import store
from .store import hub,identity,timestamp,text

MAX_FILE=max(1,int(os.getenv('USOPP_PASSPORT_MAX_FILE_BYTES',str(100*1024**2))))
MAX_STORAGE=max(MAX_FILE,int(os.getenv('USOPP_PASSPORT_STORAGE_BYTES',str(10*1024**3))))


def root():
    folder=hub.root/'contributions';folder.mkdir(parents=True,exist_ok=True);return folder


def temporary(user,kind,key,name):
    store.initialize();store.personal(user)
    with hub.db() as db:store.author(user,store.object_row(db,kind,key))
    name=text(Path(str(name or 'attachment').replace('\\','/')).name,180,True)
    if name in {'.','..'} or any(ord(c)<32 for c in name):raise HTTPException(400,'Choose a normal attachment filename.')
    fd,path=tempfile.mkstemp(prefix='upload-',suffix='.part',dir=root());os.close(fd)
    return name,Path(path)


def finish(user,kind,key,name,path,size,digest):
    with hub.db(True) as db:
        store.author(user,store.object_row(db,kind,key))
        exists=db.execute('SELECT 1 FROM cp_files WHERE sha256=?',(digest,)).fetchone()
        used=db.execute('SELECT COALESCE(SUM(size),0) FROM (SELECT MAX(size) AS size FROM cp_files GROUP BY sha256)').fetchone()[0]
        if not exists and used+size>MAX_STORAGE:raise HTTPException(413,'The contribution attachment storage quota is full.')
        target=root()/'blobs'/digest[:2]/digest;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():os.replace(path,target)
        key_file=identity();db.execute('INSERT INTO cp_files VALUES(?,?,?,?,?,?,?,?)',(key_file,kind,key,user['id'],name,digest,size,timestamp()))
        store.action(db,user,kind,key,None,'attachment_uploaded',{'file_id':key_file,'name':name,'size':size})
        return {'id':key_file,'name':name,'size':size}


async def upload(user,kind,key,file):
    name,path=temporary(user,kind,key,file.filename);size=0;digest=hashlib.sha256()
    try:
        with path.open('wb') as out:
            while True:
                chunk=await file.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>MAX_FILE:raise HTTPException(413,'Contribution attachments must be at most '+str(MAX_FILE//1024**2)+' MiB. Link the existing project evidence for larger engineering files.')
                digest.update(chunk);out.write(chunk)
        if not size:raise HTTPException(400,'Choose a nonempty attachment.')
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(finish,user,kind,key,name,path,size,digest.hexdigest())
    finally:path.unlink(missing_ok=True);await file.close()


def download(user,key):
    store.initialize();store.personal(user)
    with hub.db() as db:
        row=db.execute('SELECT * FROM cp_files WHERE id=?',(key,)).fetchone()
        if not row:raise HTTPException(404,'Attachment not found.')
        value=dict(row);obj=store.object_row(db,value['object_type'],value['object_id']);store.require_read(db,user,value['object_type'],obj)
        allowed=user['role']=='admin' or user['id']==obj['author_id']
        if not allowed:
            table,column=('cp_revisions','article_id') if value['object_type']=='article' else ('pc_manual_revisions','evidence_id')
            for item in db.execute('SELECT id FROM '+table+' WHERE '+column+'=?',(obj['id'],)):
                rev=store.revision(db,value['object_type'],item['id'],obj['id'])
                ids=rev['file_ids'] if value['object_type']=='article' else rev['content'].get('file_ids',[])
                eligible=rev['reviewer_id']==user['id'] and rev['status']!='draft'
                if value['object_type']=='article':eligible=eligible or rev['status']=='published' and bool(rev.get('published_at'))
                else:eligible=eligible or rev['status']=='approved' and obj['project_id'] in store.managed_projects(db,user)
                if eligible and key in ids:allowed=True;break
        if not allowed:raise HTTPException(403,'This attachment is not part of a revision available to you.')
    if not re.fullmatch('[a-f0-9]{64}',value['sha256']):raise HTTPException(404,'Attachment is unavailable.')
    path=root()/'blobs'/value['sha256'][:2]/value['sha256']
    if not path.is_file():raise HTTPException(404,'Attachment is unavailable on this server.')
    return value,path
