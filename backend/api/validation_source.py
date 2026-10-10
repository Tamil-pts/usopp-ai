"""Read/save source files in the project recorded by a validation session."""
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from backend.core.runtime import WORK, VALIDATION_LOCK

router=APIRouter(tags=['Validation source editor'])
SOURCE_EXTENSIONS={'.st','.src','.ab','.var','.typ','.c','.h','.txt','.fun','.ld','.page','.pages','.txtgrp','.algrp','.tpr','.hw','.hwl','.iom','.sw','.set','.pgp','.per'}
MAX_SOURCE_BYTES=5*1024*1024

def source_path(payload):
    sid=str(payload.get('session_id',''))
    if not re.fullmatch(r'[A-Za-z0-9_-]+',sid): raise HTTPException(400,'Invalid validation session.')
    from backend.core.access import require_session
    require_session(sid)
    work=WORK/sid
    try:
        manifest=json.loads((work/'inputs.json').read_text(encoding='utf-8'))
        root=Path(manifest['project']).resolve(strict=True)
    except (OSError,ValueError,KeyError):
        raise HTTPException(404,'Validation session not found. Run validation again.')
    relative=Path(str(payload.get('path','')).replace('\\','/'))
    if relative.is_absolute() or '..' in relative.parts: raise HTTPException(400,'Use a project-relative source path.')
    try: path=(root/relative).resolve(strict=True)
    except OSError: raise HTTPException(404,'Source file no longer exists.')
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
        raise HTTPException(400,'Only supported project source files can be opened.')
    if any(part.casefold() in {'temp','as','binaries','diagnosis','.git'} for part in path.relative_to(root).parts[:-1]):
        raise HTTPException(400,'Generated project folders cannot be edited here.')
    if path.stat().st_size>MAX_SOURCE_BYTES: raise HTTPException(413,'Source editor supports files up to 5 MB.')
    return work,root,path

def decode_source(raw):
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        encoding='utf-16' if raw.startswith(b'\xff\xfe') else 'utf-16-be'
        return (raw.decode(encoding).lstrip('\ufeff'),encoding,raw.startswith(b'\xfe\xff'))
    encoding='utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'
    try: return raw.decode(encoding),encoding,False
    except UnicodeDecodeError: return raw.decode('cp1252'),'cp1252',False

@router.post('/api/validation/source/read')
def read_source(payload:dict):
    _,root,path=source_path(payload)
    raw=path.read_bytes()
    wrapped=path.suffix.casefold() in {'.src','.pgp'} and raw.startswith(b'B&R') and b'\x00' in raw
    if wrapped:
        # Container bytes are not a text encoding; decode its text records with
        # the same policy used by the validation engine.
        content=raw.decode('utf-8',errors='ignore')
        encoding='AS 2.7 source view'
    else:
        try: content,encoding,_=decode_source(raw)
        except UnicodeError: raise HTTPException(400,'This source encoding is not supported for editing.')
    read_only=False
    note=''
    from backend.core.run_history import SNAPSHOTS
    if root.is_relative_to(SNAPSHOTS.resolve()):
        read_only=True
        note='Archived source from this run is read-only. Use Reuse in WorkHub to create an editable project copy.'
    if '\x00' in content:
        if path.suffix.casefold() in {'.src','.pgp'} and raw.startswith(b'B&R'):
            # Match the validator's UTF-8-ignore splitlines numbering. Preserve
            # line positions, but hide container control bytes from the viewer.
            content='\n'.join(''.join(c for c in line if c=='\t' or c.isprintable()) for line in raw.decode('utf-8',errors='ignore').splitlines())
            read_only=True
            note='AS 2.7 binary source container: decoded source view only. Edit the original in Automation Studio to preserve its container records.'
        else: raise HTTPException(400,'This binary file does not contain a supported AS 2.7 source view.')
    return {'path':path.relative_to(root).as_posix(),'projectPath':str(root),'content':content,
            'encoding':encoding,'etag':hashlib.sha256(raw).hexdigest(),'readOnly':read_only,'note':note}

@router.post('/api/validation/source/save')
def save_source(payload:dict):
    if str(payload.get('session_id','')).startswith('history_'):
        raise HTTPException(403,'Archived source is read-only. Reuse the stored project before editing.')
    from backend.core.jobs import project_job
    work,root,path=source_path(payload)
    from backend.core.run_history import SNAPSHOTS
    if root.resolve().is_relative_to(SNAPSHOTS.resolve()):
        raise HTTPException(403,'Archived source is read-only. Reuse the stored project before editing.')
    guard=project_job(root,editing=True)
    guard.__enter__()
    temporary=None
    try:
        raw=path.read_bytes()
        if b'\x00' in raw and raw.startswith(b'B&R') and path.suffix.casefold() in {'.src','.pgp'}:
            raise HTTPException(400,'AS 2.7 source containers are view-only here. Save changes in Automation Studio.')
        if payload.get('etag')!=hashlib.sha256(raw).hexdigest():
            raise HTTPException(409,'The file changed since it was opened. Reload it before saving.')
        content=payload.get('content')
        if not isinstance(content,str) or len(content)>MAX_SOURCE_BYTES or '\x00' in content:
            raise HTTPException(400,'Invalid source text or file exceeds the editor size limit.')
        original,encoding,big_endian_bom=decode_source(raw)
        newline='\r\n' if '\r\n' in original else '\r' if '\r' in original else '\n'
        try:
            updated=content.replace('\r\n','\n').replace('\r','\n').replace('\n',newline).encode(encoding)
        except UnicodeError: raise HTTPException(400,f'Text cannot be saved using the original {encoding} encoding.')
        if big_endian_bom: updated=b'\xfe\xff'+updated
        if len(updated)>MAX_SOURCE_BYTES: raise HTTPException(413,'Source exceeds 5 MB.')
        backup_dir=work/'source_backups'
        backup_dir.mkdir(exist_ok=True)
        backup=backup_dir/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+path.name+'.bak')
        backup.write_bytes(raw)
        fd,name=tempfile.mkstemp(prefix='.usopp-edit-',suffix='.tmp',dir=path.parent)
        temporary=Path(name)
        with os.fdopen(fd,'wb') as stream: stream.write(updated)
        shutil.copymode(path,temporary)
        if path.read_bytes()!=raw: raise HTTPException(409,'The source changed during save. Reload it before saving.')
        os.replace(temporary,path)
        with (work/'source_edits.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'time':datetime.now().isoformat(),'path':path.relative_to(root).as_posix(),'backup':backup.name})+'\n')
        return {'path':path.relative_to(root).as_posix(),'etag':hashlib.sha256(updated).hexdigest(),
                'backup':str(backup),'message':'File saved with backup. Run validation again to update results.'}
    finally:
        if temporary and temporary.exists(): temporary.unlink()
        guard.__exit__(None,None,None)
