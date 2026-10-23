from __future__ import annotations
import os, json, shutil, tempfile, subprocess, sys, re, logging, traceback, threading, time, csv, io
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import requests
from python_engine.project_paths import IGNORED_PROJECT_DIRS
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

FROZEN=bool(getattr(sys,'frozen',False))
RESOURCE_ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2])).resolve()
if FROZEN:
    _local_app_data=Path(os.getenv('LOCALAPPDATA') or (Path.home()/'AppData'/'Local'))
    BASE=Path(os.getenv('USOPP_DATA_ROOT') or (_local_app_data/'uSOPp.ai')).resolve()
    BASE.mkdir(parents=True,exist_ok=True)
else:
    BASE=Path(os.getenv('USOPP_DATA_ROOT') or RESOURCE_ROOT).resolve()
    BASE.mkdir(parents=True,exist_ok=True)
VERSION=json.loads((RESOURCE_ROOT/'package.json').read_text(encoding='utf-8'))['version']

def _seed_resource_tree(name:str):
    """Copy bundled editable defaults to the per-user data directory once."""
    if BASE == RESOURCE_ROOT:
        return
    source=RESOURCE_ROOT/name
    target=BASE/name
    if not source.exists():
        return
    for item in source.rglob('*'):
        relative=item.relative_to(source)
        destination=target/relative
        if item.is_dir():
            destination.mkdir(parents=True,exist_ok=True)
        elif not destination.exists():
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(item,destination)

for _resource_name in ('knowledge','rules'):
    _seed_resource_tree(_resource_name)
LOG_DIR=BASE/'logs'; LOG_DIR.mkdir(exist_ok=True)
LOG_FILE=LOG_DIR/f'usopp_backend_{datetime.now():%Y%m%d}.log'
_log_handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8')]
if sys.stdout is not None:
    _log_handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', handlers=_log_handlers)
log=logging.getLogger('usopp')
ENGINE=RESOURCE_ROOT/'python_engine'/'packet_validation_report_uSOPp_v1.71_final.py'
RULE_ENGINE=RESOURCE_ROOT/'python_engine'/'rule_engine_v4_30.py'
COMPARE_ENGINE=RESOURCE_ROOT/'python_engine'/'compare.py'
DEFAULT_RULES=BASE/'rules'/'engineering_rules_v4.30.json'
KNOWLEDGE=BASE/'knowledge'; MASTER=KNOWLEDGE/'master'; PROJECT_KB=KNOWLEDGE/'projects'; MASTER.mkdir(parents=True,exist_ok=True); PROJECT_KB.mkdir(parents=True,exist_ok=True)
MASTER_PARAM_FILE=MASTER/'parameter_mappings.json'
if not MASTER_PARAM_FILE.exists(): MASTER_PARAM_FILE.write_text(json.dumps({'version':'1.0','mappings':[]},indent=2),encoding='utf-8')

def project_kb_file(project_name:str)->Path:
    key=safe_name(project_name or 'unnamed_project') or 'unnamed_project'
    folder=PROJECT_KB/key
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'parameter_mappings.json'
    if not path.exists(): path.write_text(json.dumps({'version':'1.0','project':project_name,'mappings':[]},ensure_ascii=False,indent=2),encoding='utf-8')
    return path
CACHE_TTL_SECONDS=600
WORK=BASE/'.usopp_workspaces'; WORK.mkdir(exist_ok=True)
EXPORTS=BASE/'.usopp_exports'; (EXPORTS/'metadata').mkdir(parents=True,exist_ok=True)

# Backward-compatible alias used by the comparison workflow.
WORKSPACE=WORK
MAX_PROJECT_FILES=800000
VALIDATION_LOCK=threading.Lock()
COMPARE_JOBS={}
COMPARE_JOBS_LOCK=threading.Lock()
log.info('uSOPP_BACKEND_IMPORT_OK version=%s python=%s pid=%s cwd=%s', VERSION, sys.executable, os.getpid(), os.getcwd())
log.info('CONFIG MAX_PROJECT_FILES=%d ENGINE=%s RULE_ENGINE=%s MASTER_KB=%s reports=retained', MAX_PROJECT_FILES, ENGINE, RULE_ENGINE, MASTER_PARAM_FILE)

# FastAPI currently asks Starlette Request.form() to use its default 1000-file
# parser limit. Browser folder uploads from Automation Studio can contain
# several thousand files, so raise that parser limit for this application.
# This is intentionally local to this process and requires no admin access.
_ORIGINAL_GET_FORM = Request._get_form
async def _usopp_get_form(self, *, max_files=1000, max_fields=1000, max_part_size=1024*1024):
    # Automation Studio workspaces can contain hundreds of thousands of files.
    # Raise Starlette's parser limits for this local application.
    if max_files == 1000:
        max_files = MAX_PROJECT_FILES
    if max_fields == 1000:
        max_fields = MAX_PROJECT_FILES
    # Keep a generous part-size limit for metadata and project files.
    max_part_size = max(max_part_size, 100 * 1024 * 1024)
    return await _ORIGINAL_GET_FORM(
        self,
        max_files=max_files,
        max_fields=max_fields,
        max_part_size=max_part_size
    )
Request._get_form = _usopp_get_form

def safe_name(s:str)->str:
    return ''.join(c if c.isalnum() or c in '_-' else '_' for c in (s or 'AutomationStudioProject'))[:100]
def locate_root(folder:Path)->Path:
    folder=folder.resolve()
    if folder.is_file() and folder.suffix.lower()=='.apj': folder=folder.parent
    if folder.name.lower()=='logical': folder=folder.parent
    def project_root(path):
        names={item.name.casefold() for item in path.iterdir()}
        return 'logical' in names or any(name.endswith('.apj') for name in names) or ('pgm' in names and (path.name.casefold().endswith('.pgp') or 'cpu.txt' in names))
    if project_root(folder): return folder
    candidates=[]
    ignored={'node_modules','.git','.venv','binaries','temp','as','diagnosis','.usopp_workspaces'}
    for current, dirs, files in os.walk(folder):
        path=Path(current)
        dirs[:]=[d for d in dirs if d.casefold() not in ignored and not (path/d).is_symlink()]
        if project_root(path):
            candidates.append(path); dirs[:]=[]
        elif len(path.relative_to(folder).parts)>=4: dirs[:]=[]
    if len(candidates)==1: return candidates[0]
    if len(candidates)>1:
        raise HTTPException(400,'Multiple PLC projects found. Select one project root: '+', '.join(str(p) for p in candidates[:5]))
    raise HTTPException(400,'Select the Automation Studio project root containing Logical or an .apj file.')
def _project_upload_workspace(sid:str)->tuple[Path,Path,Path]:
    if not re.fullmatch(r'[A-Za-z0-9_-]+',str(sid or '')):
        raise HTTPException(400,'Invalid project upload session.')
    work=(WORK/sid).resolve()
    from backend.core.access import require_session
    require_session(sid)
    if WORK.resolve() not in work.parents or not work.is_dir():
        raise HTTPException(404,'Project upload session was not found. Select the folder again.')
    state_path=work/'project_upload.json'
    extract=work/'source'
    if not state_path.is_file() or not extract.is_dir():
        raise HTTPException(404,'Project upload session was not found. Select the folder again.')
    return work,extract,state_path

async def _write_project_files(extract:Path, project_files:List[UploadFile], start_index:int=0, total_files:Optional[int]=None)->int:
    base_path=extract.resolve()
    for idx,f in enumerate(project_files):
        name=f.filename or ''
        normalized=name.replace('\\','/')
        rel=Path(normalized)
        if not normalized or rel.is_absolute() or rel.drive or normalized.startswith('/') or '..' in rel.parts:
            log.error('PROJECT_FILE_REJECTED index=%d/%d filename=%r normalized=%r reason=unsafe_path',start_index+idx+1,total_files or len(project_files),name,normalized)
            raise HTTPException(400,f'Unsafe folder upload path: {name}')
        if any(part.casefold() in IGNORED_PROJECT_DIRS for part in rel.parts[:-1]):
            completed=start_index+idx+1
            if completed%100==0 or idx+1==len(project_files):
                log.info('PROJECT_UPLOAD_PROGRESS %d/%d skipped_generated=%s',completed,total_files or len(project_files),str(rel))
            continue
        target=(extract/rel).resolve()
        if target!=base_path and base_path not in target.parents:
            log.error('PROJECT_FILE_REJECTED index=%d/%d filename=%r normalized=%r reason=outside_workspace',start_index+idx+1,total_files or len(project_files),name,normalized)
            raise HTTPException(400,f'Unsafe folder upload path: {name}')
        data=await f.read()
        # Python accepts extended Windows paths without changing machine policy.
        disk_target=Path('\\\\?\\'+str(target)) if os.name=='nt' and not str(target).startswith('\\\\') else target
        disk_target.parent.mkdir(parents=True,exist_ok=True); disk_target.write_bytes(data)
        completed=start_index+idx+1
        if len(project_files)<=10 or completed%100==0 or idx+1==len(project_files):
            log.info('PROJECT_UPLOAD_PROGRESS %d/%d file=%s bytes=%d',completed,total_files or len(project_files),str(rel),len(data))
    return len(project_files)

def clear_temporary_workspaces()->dict:
    """Clear only this user's inactive staged sources; retain saved results."""
    root=WORK.resolve(); removed=0; failed=[]
    for child in list(root.iterdir()):
        if child.name in {'history','data_models','chopper_knowledge','compare'}:
            continue
        try:
            from backend.core.access import owns_resource
            from backend.core.jobs import workspace_cleanup
            if not owns_resource(child): continue
            resolved=child.resolve()
            if root not in resolved.parents:
                failed.append(child.name); continue
            # Download routes still serve reports from their session directory.
            # Clear only staged source trees; retain report/session artifacts.
            if child.is_dir():
                if child.name.startswith('chopper_report_'):
                    shutil.rmtree(resolved)
                    removed += 1
                    continue
                upload=child/'project_upload.json'
                if upload.is_file() and not json.loads(upload.read_text(encoding='utf-8')).get('complete'): continue
                with workspace_cleanup(child) as available:
                    if not available: continue
                    for name in ('source', 'extract'):
                        staged = child / name
                        if staged.is_dir() and root in staged.resolve().parents:
                            shutil.rmtree(staged)
                    if not any(child.iterdir()): child.rmdir()
            else:
                continue
            removed+=1
        except (OSError,ValueError):
            failed.append(child.name)
    return {'removed':removed,'failed':failed}

def start_project_upload(project_name:str,total_files:int)->dict:
    if total_files<1:
        raise HTTPException(400,'Select the complete B&R project folder.')
    if total_files>MAX_PROJECT_FILES:
        raise HTTPException(400,f'Project folder contains {total_files} files; maximum supported is {MAX_PROJECT_FILES}.')
    sid=f'{os.getpid()}_{next(tempfile._get_candidate_names())}'
    work=WORK/sid; work.mkdir(parents=True,exist_ok=False); (work/'source').mkdir()
    from backend.core.access import claim_resource
    claim_resource(work)
    state={'projectName':str(project_name or 'UploadedProject'),'expectedFiles':total_files,'receivedFiles':0,'receivedBytes':0,'complete':False}
    (work/'project_upload.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    log.info('PROJECT_CHUNK_UPLOAD_START session=%s project_name=%r files=%d',sid,state['projectName'],total_files)
    return {'sessionId':sid,'totalFiles':total_files}

async def append_project_upload(sid:str,project_files:Optional[List[UploadFile]])->dict:
    if not project_files:
        raise HTTPException(400,'Project upload chunk is empty.')
    _,extract,state_path=_project_upload_workspace(sid)
    state=json.loads(state_path.read_text(encoding='utf-8'))
    if state.get('complete'):
        raise HTTPException(409,'Project upload is already complete.')
    received=int(state.get('receivedFiles') or 0)
    expected=int(state.get('expectedFiles') or 0)
    if received+len(project_files)>expected:
        raise HTTPException(400,'Project upload contains more files than selected.')
    added=await _write_project_files(extract,project_files,received,expected)
    state['receivedFiles']=received+added
    state['receivedBytes']=int(state.get('receivedBytes') or 0)+sum(int(getattr(item,'size',0) or 0) for item in project_files)
    state_path.write_text(json.dumps(state,indent=2),encoding='utf-8')
    return {'sessionId':sid,'receivedFiles':state['receivedFiles'],'totalFiles':expected}

def finish_project_upload(sid:str)->dict:
    _,extract,state_path=_project_upload_workspace(sid)
    state=json.loads(state_path.read_text(encoding='utf-8'))
    received=int(state.get('receivedFiles') or 0); expected=int(state.get('expectedFiles') or 0)
    if received!=expected:
        raise HTTPException(400,f'Project upload is incomplete: received {received} of {expected} files.')
    root=locate_root(extract)
    state.update(complete=True,projectRoot=str(root))
    state_path.write_text(json.dumps(state,indent=2),encoding='utf-8')
    log.info('PROJECT_CHUNK_UPLOAD_COMPLETE session=%s files=%d root=%s',sid,received,root)
    return {'sessionId':sid,'projectPath':str(root),'projectName':state.get('projectName') or root.name,'uploadedFiles':received}

async def stage_project(project_files: Optional[List[UploadFile]], project_name: str)->tuple[str,Path]:
    # Compatibility path for small uploads and existing API clients.
    if not project_files:
        raise HTTPException(400,'Select the complete B&R project folder.')
    if not project_name:
        project_name=project_files[0].filename.replace('\\','/').split('/')[0] if project_files[0].filename else 'UploadedProject'
    log.info('PROJECT_STAGE_START project_name=%r folder_files=%d max_allowed=%d', project_name, len(project_files), MAX_PROJECT_FILES)
    if len(project_files)>MAX_PROJECT_FILES:
        log.error('PROJECT_STAGE_REJECTED folder_files=%d max_allowed=%d', len(project_files), MAX_PROJECT_FILES)
        raise HTTPException(400,f'Project folder contains {len(project_files)} files; maximum supported is {MAX_PROJECT_FILES}.')
    sid=f'{os.getpid()}_{next(tempfile._get_candidate_names())}'
    work=WORK/sid; work.mkdir(parents=True,exist_ok=True); extract=work/'source'; extract.mkdir()
    from backend.core.access import claim_resource
    claim_resource(work)
    await _write_project_files(extract,project_files,0,len(project_files))
    log.info('PROJECT_UPLOAD_COMPLETE files=%d workspace=%s',len(project_files),sid)
    root=locate_root(extract)
    log.info('PROJECT_READY session=%s root=%s',sid,root)
    return sid,root
def run_engine(args:list[str], cwd:Path):
    command=engine_command(Path(args[0]),*args[1:])
    log.info('ENGINE_START cwd=%s cmd=%s', cwd, ' '.join(map(str,command)))
    started=time.perf_counter()
    p=subprocess.run(command,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600,env={**os.environ,'PYTHONUTF8':'1','USOPP_DATA_ROOT':str(BASE)},creationflags=engine_creation_flags())
    if p.stdout: log.info('ENGINE_STDOUT %s', p.stdout[-20000:])
    if p.stderr: log.warning('ENGINE_STDERR %s', p.stderr[-20000:])
    log.info('ENGINE_END returncode=%s seconds=%.3f', p.returncode, time.perf_counter()-started)
    if p.returncode!=0: raise RuntimeError((p.stderr or p.stdout or 'Engine failed').strip()[-12000:])
    return p

def engine_command(script:Path,*args)->list[str]:
    """Run an engine with Python in development or through the packaged EXE."""
    if FROZEN:
        return [sys.executable,'--usopp-engine',script.name,*map(str,args)]
    # Container releases contain adjacent bytecode, compiled with their runtime.
    if not script.is_file() and script.suffix == '.py':
        script = script.with_suffix('.pyc')
    return [sys.executable,str(script),*map(str,args)]

def engine_creation_flags()->int:
    return int(getattr(subprocess,'CREATE_NO_WINDOW',0)) if FROZEN and os.name=='nt' else 0
def find_json(work:Path,name:str)->dict:
    p=work/name
    if not p.exists(): raise RuntimeError(f'Expected output not found: {name}')
    return json.loads(p.read_text(encoding='utf-8'))
def _local_path(raw:str, must_exist:bool=True, directory:bool=False)->Path:
    if not raw or not str(raw).strip():
        raise HTTPException(400,'Local path is required.')
    value=str(raw).strip().strip('"').strip("'").strip()
    if 'fakepath' in value.lower():
        raise HTTPException(400,'Browser fake paths cannot be opened. Paste the full path from File Explorer or use Browse This PC.')
    if value.lower().startswith('file:'):
        from urllib.parse import urlparse, unquote
        uri=urlparse(value); value=unquote(uri.path)
        if uri.netloc: value='//'+uri.netloc+value
        elif os.name=='nt' and re.match(r'^/[A-Za-z]:',value): value=value[1:]
    try:
        p=Path(os.path.expandvars(os.path.expanduser(value)))
        if not p.is_absolute(): p=BASE/p
        p=p.resolve()
    except Exception: raise HTTPException(400,'Invalid local path.')
    if must_exist and not p.exists(): raise HTTPException(404,f'Local path not found: {p}')
    if directory and p.is_file() and p.suffix.lower()=='.apj': p=p.parent
    if directory and p.exists() and not p.is_dir(): raise HTTPException(400,'Selected local path is not a folder.')
    from backend.core.access import require_resource
    require_resource(p)
    return p
def _local_roots():
    if os.name=='nt':
        return [Path(f'{chr(c)}:\\') for c in range(ord('A'),ord('Z')+1) if Path(f'{chr(c)}:\\').exists()]
    return [Path('/')]
def _local_entries(path:Path, include_files:bool=False, file_exts=None):
    entries=[]
    file_exts=set(file_exts or {'.xlsx','.xls'})
    try:
        for child in path.iterdir():
            try:
                if child.is_symlink():
                    continue
                if child.is_dir():
                    entries.append({'name':child.name,'path':str(child),'has_children':True})
                elif include_files and child.is_file() and child.suffix.lower() in file_exts:
                    entries.append({'name':child.name,'path':str(child),'has_children':False,'is_file':True})
            except (PermissionError,OSError):
                continue
    except (PermissionError,OSError) as e:
        raise HTTPException(403,f'Cannot browse this folder: {path}')
    entries.sort(key=lambda x:(x.get('is_file',False),x['name'].lower()))
    return entries
def _local_session():
    sid=f'{os.getpid()}_{next(tempfile._get_candidate_names())}'
    work=WORK/sid; work.mkdir(parents=True,exist_ok=True)
    from backend.core.access import claim_resource
    claim_resource(work)
    return sid,work
def _local_metadata_path(work:Path, raw:str):
    if not raw: return None
    p=_local_path(raw,True,False)
    if not p.is_file(): raise HTTPException(400,'Select a metadata file, not a folder.')
    if p.suffix.lower() not in {'.xlsx','.xls'}: raise HTTPException(400,'Metadata must be an .xlsx or .xls workbook.')
    return p
