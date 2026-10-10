from __future__ import annotations
from contextvars import copy_context
from backend.core.run_history import begin_run, record_run
import re
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from backend.core.runtime import (
    BASE,
    COMPARE_ENGINE,
    COMPARE_JOBS,
    COMPARE_JOBS_LOCK,
    EXPORTS,
    List,
    MAX_PROJECT_FILES,
    Optional,
    Path,
    WORK,
    WORKSPACE,
    datetime,
    engine_command,
    engine_creation_flags,
    json,
    locate_root,
    log,
    os,
    safe_name,
    shutil,
    subprocess,
    sys,
    tempfile,
    threading,
    time,
)

from backend.core.runtime import _local_path, _local_session, stage_project

router = APIRouter(tags=['Project Comparison'])
COMPARE_LOG_DIR=BASE/'logs'/'compare'
COMPARE_WORK_DIR=WORK/'compare'
COMPARE_EXPORT_DIR=EXPORTS/'compare'
COMPARE_LOG_DIR.mkdir(parents=True,exist_ok=True)
COMPARE_WORK_DIR.mkdir(parents=True,exist_ok=True)
COMPARE_EXPORT_DIR.mkdir(parents=True,exist_ok=True)

def _compare_session():
    sid=f'{os.getpid()}_{next(tempfile._get_candidate_names())}'
    work=COMPARE_WORK_DIR/sid
    work.mkdir(parents=True,exist_ok=True)
    from backend.core.access import claim_resource
    claim_resource(work)
    return sid,work

def _compare_worker(sid:str, work:Path, base:Path, new:Path, base_name:str, new_name:str, base_hmi:str='', new_hmi:str=''):
    from backend.core.jobs import projects_job
    identity={'sessionId':sid,'projectName':base_name+' vs '+new_name,'baseName':base_name,'newName':new_name}
    begin_run('compare',identity,new)
    with projects_job([locate_root(base),locate_root(new)]):
        return _compare_project(sid,work,base,new,base_name,new_name,base_hmi,new_hmi,identity)

def _compare_project(sid,work,base,new,base_name,new_name,base_hmi,new_hmi,identity):
    out=work/'compare_results.json'
    started=time.time()
    job={'status':'running','phase':'starting','percent':0,'current':0,'total':0,'baseFile':'','newFile':'','logs':[], 'startedAt':datetime.now().isoformat()}
    with COMPARE_JOBS_LOCK: COMPARE_JOBS[sid]=job
    compare_log=COMPARE_LOG_DIR/f'compare_{sid}.log'
    try:
        log.info('LOCAL_COMPARE_START session=%s base=%s new=%s',sid,base,new)
        args=engine_command(COMPARE_ENGINE,'--base',str(locate_root(base)),'--new',str(locate_root(new)),'--output',str(out))
        if base_hmi: args += ['--base-hmi',base_hmi]
        if new_hmi: args += ['--new-hmi',new_hmi]
        proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONUTF8':'1'},cwd=str(BASE),bufsize=1,creationflags=engine_creation_flags())
        assert proc.stdout is not None
        for raw in proc.stdout:
            line=raw.strip()
            if not line: continue
            with compare_log.open('a',encoding='utf-8') as stream: stream.write(line+'\n')
            try: msg=json.loads(line)
            except Exception: msg={'event':'log','message':line}
            with COMPARE_JOBS_LOCK:
                j=COMPARE_JOBS.get(sid,job)
                if msg.get('event')=='progress':
                    j.update({'phase':'comparing','percent':msg.get('percent',0),'current':msg.get('current',0),'total':msg.get('total',0),'baseFile':msg.get('base_path',''),'newFile':msg.get('new_path','')})
                    textmsg=f"[{msg.get('percent',0):>5}%] {msg.get('category','').upper():8} | BASE: {msg.get('base_path','-')} | NEW: {msg.get('new_path','-')}"
                else:
                    textmsg=msg.get('message') or line
                    if msg.get('event')=='phase': j['phase']=msg.get('phase','working')
                    if msg.get('event')=='complete': j['percent']=100; j['phase']='complete'
                j['logs']=(j.get('logs') or [])+ [textmsg]
                j['logs']=j['logs'][-300:]
        rc=proc.wait()
        if rc!=0: raise RuntimeError(f'Compare engine exited with code {rc}')
        if not out.exists(): raise RuntimeError('Compare engine finished but no result file was created.')
        data=json.loads(out.read_text(encoding='utf-8'))
        projects=data.get('projects') or {}
        detected_base=(projects.get('base') or {}).get('project_name')
        detected_new=(projects.get('developed') or {}).get('project_name')
        data.update({'baseName':detected_base or base_name,'newName':detected_new or new_name,'localMode':work.is_relative_to(COMPARE_WORK_DIR),'sessionId':sid,**{key:identity[key] for key in ('testId','historyId','machineDepartment','runKind')}})
        data['projectName']=data['baseName']+' vs '+data['newName']
        record_run('compare',data,new)
        with out.open('w',encoding='utf-8') as stream:
            json.dump(data,stream,ensure_ascii=False,separators=(',',':'))
        with COMPARE_JOBS_LOCK:
            j=COMPARE_JOBS[sid]; j.update({'status':'complete','phase':'complete','percent':100,'result':data,'elapsedSeconds':round(time.time()-started,2)})
        log.info('LOCAL_COMPARE_SUCCESS session=%s elapsed=%.2fs modified=%s added=%s removed=%s',sid,time.time()-started,data.get('summary',{}).get('modified',0),data.get('summary',{}).get('added',0),data.get('summary',{}).get('removed',0))
    except Exception as e:
        log.exception('LOCAL_COMPARE_ERROR session=%s',sid)
        record_run('compare',{**identity,'runStatus':'failed','error':str(e)},new)
        with COMPARE_JOBS_LOCK:
            j=COMPARE_JOBS.get(sid,job); j.update({'status':'error','phase':'error','error':str(e),'elapsedSeconds':round(time.time()-started,2)})
            j['logs']=(j.get('logs') or [])+[f'ERROR: {e}']; j['logs']=j['logs'][-300:]
@router.post('/api/local/compare/start')
def local_compare_start(payload:dict):
    sid,work=_compare_session()
    try:
        base=_local_path(payload.get('base_path',''),True,True); new=_local_path(payload.get('new_path',''),True,True)
        base_name=str(payload.get('base_name') or base.name); new_name=str(payload.get('new_name') or new.name)
        with COMPARE_JOBS_LOCK: COMPARE_JOBS[sid]={'status':'starting','phase':'starting','percent':0,'current':0,'total':0,'baseFile':'','newFile':'','logs':[]}
        threading.Thread(target=copy_context().run,args=(_compare_worker,sid,work,base,new,base_name,new_name,str(payload.get('base_hmi') or ''),str(payload.get('new_hmi') or '')),daemon=True).start()
        return JSONResponse({'status':'started','sessionId':sid,'baseName':base_name,'newName':new_name})
    except HTTPException: raise
    except Exception as e:
        log.exception('LOCAL_COMPARE_START_ERROR session=%s',sid); raise HTTPException(500,str(e))

@router.post('/api/local/compare/project-info')
def local_compare_project_info(payload:dict):
    from python_engine.compare import project_identity
    root=locate_root(_local_path(payload.get('project_path',''),True,True))
    return JSONResponse(project_identity(root,str(payload.get('selected_hmi') or '')))
@router.get('/api/local/compare/status/{sid}')
def local_compare_status(sid:str):
    with COMPARE_JOBS_LOCK: job=COMPARE_JOBS.get(sid)
    if not job: raise HTTPException(404,'Comparison session not found or already cleared.')
    return JSONResponse(job)
@router.post('/api/local/compare')
def local_compare(payload:dict):
    sid,work=_compare_session()
    base=_local_path(payload.get('base_path',''),True,True); new=_local_path(payload.get('new_path',''),True,True)
    _compare_worker(sid,work,base,new,str(payload.get('base_name') or base.name),str(payload.get('new_name') or new.name),str(payload.get('base_hmi') or ''),str(payload.get('new_hmi') or ''))
    job=COMPARE_JOBS[sid]
    if job['status']=='error': raise HTTPException(500,job['error'])
    return JSONResponse(job['result'])
def _comparison_result_for_export(sid:str):
    from backend.core.access import require_session
    require_session(sid)
    if not re.fullmatch(r'[A-Za-z0-9_-]+',sid): raise HTTPException(400,'Invalid comparison session')
    with COMPARE_JOBS_LOCK: job=COMPARE_JOBS.get(sid)
    if job and job.get('result'):
        work=COMPARE_WORK_DIR/sid
        return job['result'],work if work.exists() else WORK/sid
    work=COMPARE_WORK_DIR/sid; path=work/'compare_results.json'
    if not path.exists():
        work=WORK/sid; path=work/'compare_results.json'
    if path.exists():
        if sid.startswith('history_'):
            from backend.core.run_history import RECORDS
            return json.loads(path.read_text(encoding='utf-8')),RECORDS/sid.removeprefix('history_')
        return json.loads(path.read_text(encoding='utf-8')),work
    raise HTTPException(404,'Comparison result not found. Run the comparison again.')
@router.get('/api/local/compare/detail/{sid}/{detail_id}')
def local_compare_detail(sid:str,detail_id:str):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',sid) or not re.fullmatch(r'[a-f0-9]{64}',detail_id):
        raise HTTPException(400,'Invalid comparison detail')
    for work in (COMPARE_WORK_DIR/sid,WORK/sid):
        path=work/'hmi_details'/f'{detail_id}.json'
        if path.is_file(): return FileResponse(path,media_type='application/json')
    if sid.startswith('history_'):
        _,work=_comparison_result_for_export(sid)
        path=work/'hmi_details'/f'{detail_id}.json'
        if path.is_file(): return FileResponse(path,media_type='application/json')
    raise HTTPException(404,'Comparison details were cleared. Run the comparison again.')


def _ladder_detail(result:dict, work:Path, path:str):
    """Load new lazy diagrams or rebuild an older saved file from its own sources."""
    import hashlib
    from python_engine.compare import parse_ladder_diff
    from python_engine.ladder_model import declaration_symbols
    entries=[entry for key in ('diffs','same_logic_files','same_project_files')
             for entry in result.get(key,[])]
    entry=next((entry for entry in entries if entry.get('path')==path),None)
    if entry is None or Path(path).suffix.casefold()!='.ld':
        raise HTTPException(404,'Ladder file is not in this comparison.')
    if any((control.get('base') or {}).get('diagram') or (control.get('new') or {}).get('diagram')
           for control in (entry.get('parsed_ladder') or {}).get('controls',[])):
        return entry['parsed_ladder']
    detail_id=hashlib.sha256(('ladder:' + path).encode('utf-8')).hexdigest()
    cached=work/'hmi_details'/f'{detail_id}.json'
    if cached.is_file():return json.loads(cached.read_text(encoding='utf-8'))
    def saved_sources(record):
        detail_id=record.get('project_detail_id','')
        if re.fullmatch(r'[a-f0-9]{64}',detail_id):
            detail=work/'hmi_details'/f'{detail_id}.json'
            if detail.is_file():return {**record,**json.loads(detail.read_text(encoding='utf-8'))}
        return record
    entry=saved_sources(entry)
    if not any(entry.get(key) for key in ('base_source','new_source')):
        raise HTTPException(404,'Ladder source was not saved. Run the comparison again to generate diagrams.')
    sources={side:{} for side in ('base','new')}
    for variable in entries:
        variable_path=variable.get('path','')
        if Path(variable_path).suffix.casefold()!='.var':continue
        variable=saved_sources(variable)
        for side in sources:
            text=variable.get(f'{side}_source')
            if text is not None:sources[side][variable_path]=text
    parsed=parse_ladder_diff(entry.get('base_source',''),entry.get('new_source',''),
        declaration_symbols(sources['base'],path,read_text=lambda text:text),
        declaration_symbols(sources['new'],path,read_text=lambda text:text),path)
    cached.parent.mkdir(parents=True,exist_ok=True)
    # Atomic replacement also permits simultaneous report/UI requests.
    from uuid import uuid4
    temporary=cached.with_suffix('.'+uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(parsed,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    temporary.replace(cached)
    return parsed


@router.get('/api/local/compare/ladder/{sid}')
def local_compare_ladder(sid:str,path:str):
    result,work=_comparison_result_for_export(sid)
    return JSONResponse(_ladder_detail(result,work,path))


def _hydrate_screen_details(result:dict,work:Path,include_same:bool=False):
    # Export gets its own copy, never inflate the object used by status polling.
    result={**result,'diffs':[dict(entry) for entry in result.get('diffs',[])]}
    groups=[result['diffs']]
    if include_same:
        result['same_screen_files']=[dict(entry) for entry in result.get('same_screen_files',[])]
        groups.append(result['same_screen_files'])
    for entries in groups:
        for entry in entries:
            detail_id=entry.get('screen_detail_id','')
            if not re.fullmatch(r'[a-f0-9]{64}',detail_id): continue
            path=work/'hmi_details'/f'{detail_id}.json'
            if not path.is_file(): raise HTTPException(404,'Comparison details were cleared. Run the comparison again.')
            entry['parsed_screen']=json.loads(path.read_text(encoding='utf-8'))
            if not include_same: entry['parsed_screen'].pop('layouts',None)
    return result

@router.get('/api/local/compare/export/{sid}/{fmt}')
def local_compare_export(sid:str,fmt:str,skip_layout_properties:bool=False):
    return _export_comparison(sid,fmt,skip_layout_properties=skip_layout_properties)


from backend.core.report_cover import ReportCover

@router.post('/api/local/compare/export/{sid}/{fmt}')
def comparison_report_with_cover(sid:str,fmt:str,cover:ReportCover,skip_layout_properties:bool=False):
    if fmt not in ('html','pdf'): raise HTTPException(400,'Cover pages are supported for HTML and PDF reports')
    return _export_comparison(sid,fmt,cover.model_dump(mode='json'),skip_layout_properties=skip_layout_properties)


def _export_comparison(sid:str,fmt:str,cover:dict|None=None,skip_layout_properties:bool=False,selection:dict|None=None):
    from backend.core.compare_exports import export_docx,export_html,export_pdf,export_data,_changed_diffs
    result,work=_comparison_result_for_export(sid)
    saved_result=result
    result=dict(result)
    if fmt not in ('html','pdf','docx','json'): raise HTTPException(400,'Supported formats: html, pdf, docx, json')
    if cover: result={**result,'reportCover':cover}
    base=safe_name(result.get('baseName','Base')); developed=safe_name(result.get('newName','Developed'))
    from backend.core.identifiers import identify_result, filename_part
    identify_result(result,'compare')
    stem=f'{filename_part(result["testId"])}_MatchView'
    from uuid import uuid4
    folder=COMPARE_EXPORT_DIR/uuid4().hex
    folder.mkdir(parents=True,exist_ok=True)
    from backend.core.access import claim_resource
    claim_resource(folder)
    export_path=folder/f'{stem}.{fmt}'
    from backend.core.compare_report_selection import select_report
    result=select_report(result,selection)
    for entry in result['diffs']:
        detail_id=entry.get('project_detail_id','')
        if re.fullmatch(r'[a-f0-9]{64}',detail_id):
            detail_path=work/'hmi_details'/f'{detail_id}.json'
            if not detail_path.is_file():raise HTTPException(404,'Comparison details were cleared. Run the comparison again.')
            entry.update(json.loads(detail_path.read_text(encoding='utf-8')))
        if str(entry.get('path','')).casefold().endswith('.ld'):
            entry['parsed_ladder']=_ladder_detail(saved_result,work,entry['path'])
    result=_hydrate_screen_details(result,work,include_same=True)
    if skip_layout_properties:
        from backend.core.hmi_difference_filter import filter_screen_properties
        result=filter_screen_properties(result)
    result['diffs']=_changed_diffs(result)
    result['summary']={status:sum(entry.get('status')==status for entry in result['diffs']) for status in ('modified','added','removed','unchanged')}
    exported_entries=result['diffs']
    result['summary']={state:sum(entry.get('status')==state for entry in exported_entries) for state in ('added','removed','modified','unchanged')}
    from backend.core.runtime import RESOURCE_ROOT
    logo=RESOURCE_ROOT/'src'/'usopp_logo.png'
    from backend.core.compare_screen_preview import preview_cache
    cache_token=preview_cache.set(work/'hmi_preview_cache')
    try:
        if fmt=='json':
            path=export_path
            with path.open('w',encoding='utf-8') as stream:
                json.dump(export_data(result),stream,ensure_ascii=False,separators=(',',':'))
            media='application/json'
        elif fmt=='html':
            path=export_path; export_html(result,path,logo); media='text/html'
        elif fmt=='pdf':
            path=export_path; export_pdf(result,path,logo); media='application/pdf'
        else:
            path=export_path; export_docx(result,path,logo); media='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    except Exception as error:
        log.exception('COMPARE_EXPORT_ERROR session=%s format=%s',sid,fmt)
        raise HTTPException(500,f'{fmt.upper()} export failed: {error}')
    finally:
        preview_cache.reset(cache_token)
    if result.get('historyId'):
        from backend.core.run_history import add_run_artifact
        add_run_artifact(result['historyId'],path)
    return FileResponse(path,filename=path.name,media_type=media)

@router.post('/api/compare')
async def compare_projects(
    base_files:Optional[List[UploadFile]]=File(None,max_files=MAX_PROJECT_FILES),
    new_files:Optional[List[UploadFile]]=File(None,max_files=MAX_PROJECT_FILES),
    base_name:str=Form(''),new_name:str=Form(''),base_hmi:str=Form(''),new_hmi:str=Form('')):
    if not base_files or not new_files:
        raise HTTPException(400,'Select both project folders using the same input method.')
    sid,base=await stage_project(base_files,base_name)
    _,new=await stage_project(new_files,new_name)
    work=WORK/sid
    from starlette.concurrency import run_in_threadpool
    await run_in_threadpool(_compare_worker,sid,work,base,new,base_name or base.name,new_name or new.name,base_hmi,new_hmi)
    job=COMPARE_JOBS[sid]
    if job['status']=='error': raise HTTPException(500,job['error'])
    job['result']['localMode']=False
    return job['result']
