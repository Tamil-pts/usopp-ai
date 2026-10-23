"""Shared validation/generation execution for local and uploaded project inputs."""
from __future__ import annotations
import json
import shutil
import time
from typing import Optional, List
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from backend.core.project_info import MAX_SETTINGS_BYTES, local_project_details, read_active_configuration
from backend.core.runtime import (
    BASE, ENGINE, EXPORTS, VERSION, WORK, MAX_PROJECT_FILES, VALIDATION_LOCK,
    _local_path, _local_metadata_path, _local_session, find_json, locate_root,
    append_project_upload, finish_project_upload, log, project_kb_file,
    run_engine, safe_name, stage_project, start_project_upload,
)

router = APIRouter(tags=['Validation & Metadata'])

def _bool_metadata_mode(value) -> str:
    mode=str(value or 'BOOL').strip().upper()
    if mode not in {'BOOL','USINT'}:
        raise HTTPException(400,'BOOL metadata mode must be BOOL or USINT.')
    return mode

@router.post('/api/project-upload/start')
def project_upload_start(payload:dict):
    return start_project_upload(
        str(payload.get('project_name') or ''),
        int(payload.get('total_files') or 0),
    )

@router.post('/api/project-upload/chunk')
async def project_upload_chunk(
    session_id:str=Form(...),
    project_files:List[UploadFile]=File(...),
):
    return await append_project_upload(session_id,project_files)

@router.post('/api/project-upload/finish')
def project_upload_finish(payload:dict):
    return finish_project_upload(str(payload.get('session_id') or ''))

@router.post('/api/local/project/details')
def project_details(payload:dict):
    root=locate_root(_local_path(payload.get('project_path',''),True,True))
    return local_project_details(root)

@router.post('/api/project/last-user')
async def uploaded_project_settings(settings_file:UploadFile=File(...)):
    name=(settings_file.filename or '').replace('\\','/')
    if name.rsplit('/',1)[-1].casefold()!='lastuser.set':
        raise HTTPException(400,'Select the project LastUser.set file.')
    return read_active_configuration(await settings_file.read(MAX_SETTINGS_BYTES+1),name)

def _execute(sid, root, project_name, metadata_path=None, generate=False, local=False, machine_department='All', bool_metadata_mode='BOOL'):
    from backend.core.jobs import project_job
    with project_job(locate_root(root)):
        return _execute_project(sid,root,project_name,metadata_path,generate,local,machine_department,bool_metadata_mode)

def _execute_project(sid, root, project_name, metadata_path=None, generate=False, local=False, machine_department='All', bool_metadata_mode='BOOL'):
    root=locate_root(root)
    name=project_name.strip() or root.name
    bool_metadata_mode=_bool_metadata_mode(bool_metadata_mode)
    work=WORK/sid
    from backend.core.run_history import begin_run,record_run
    data={'sessionId':sid,'projectName':name,'machineDepartment':machine_department}
    begin_run('metadata' if generate else 'validation',data,root)
    identity=dict(data)
    try:
        from backend.core.identifiers import run_identity
        test_id=data['testId']
        kind='Generated_Metadata' if generate else 'Validation_Report'
        out=work/f'{test_id}_{kind}.xlsx'
        json_name='generated_metadata.json' if generate else 'validation_results.json'
        args=[str(ENGINE),'--project',str(root),'--output-excel',str(out),
              '--output-json',str(work/json_name),'--project-kb',str(project_kb_file(name))]
        args += ['--machine-department',str(machine_department or 'All')]
        args += ['--bool-metadata-mode',bool_metadata_mode]
        if generate: args.append('--generate-metadata')
        elif metadata_path: args += ['--metadata',str(metadata_path)]
        started=time.perf_counter()
        run_engine(args,BASE)
        data={**find_json(work,json_name),**identity}
        manifest={'project':str(root),'uploaded':str(metadata_path or ''),'machineDepartment':machine_department,'boolMetadataMode':bool_metadata_mode}
        download=f'/api/download/{sid}/{out.name}'
        if generate:
            target=EXPORTS/'metadata'/f'{test_id}_Generated_Metadata_{sid}.xlsx'
            shutil.copy2(out,target)
            from backend.core.access import claim_resource
            claim_resource(target)
            manifest['generated']=str(target)
            data['workbookPath']=str(target)
            data['generationSeconds']=round(time.perf_counter()-started,2)
            download=f'/api/metadata/view/download/{sid}/{target.name}'
        else: data['metadataPath']=str(metadata_path or '')
        (work/'inputs.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        data.update(sessionId=sid,version=VERSION,engineVersion='1.71',projectName=name,projectPath=str(root),
                    localMode=local,downloadExcelUrl=download,machineDepartment=machine_department,boolMetadataMode=bool_metadata_mode,testId=test_id)
        from backend.core.run_history import record_run
        record_run('metadata' if generate else 'validation',data,root,metadata_path)
        return data
    except HTTPException: raise
    except Exception as exc:
        log.exception('VALIDATION_WORKFLOW_ERROR session=%s',sid)
        failed={**identity,'runStatus':'failed','error':str(exc)}
        record_run('metadata' if generate else 'validation',failed,root,metadata_path)
        raise HTTPException(500,str(exc)) from exc

@router.post('/api/local/validate')
def local_validate(payload:dict):
    root=_local_path(payload.get('project_path',''),True,True)
    sid,work=_local_session()
    meta=_local_metadata_path(work,payload.get('metadata_path',''))
    return _execute(sid,root,str(payload.get('project_name') or ''),meta,local=True,machine_department=payload.get('machine_department','All'),bool_metadata_mode=payload.get('bool_metadata_mode','BOOL'))

@router.post('/api/local/generate-metadata')
def local_generate_metadata(payload:dict):
    root=_local_path(payload.get('project_path',''),True,True)
    sid,_=_local_session()
    return _execute(sid,root,str(payload.get('project_name') or ''),generate=True,local=True,machine_department=payload.get('machine_department','All'),bool_metadata_mode=payload.get('bool_metadata_mode','BOOL'))

async def store_metadata(file:UploadFile,work):
    suffix=file.filename.rsplit('.',1)[-1].lower() if file.filename else ''
    if suffix not in {'xlsx','xls'}: raise HTTPException(400,'Metadata must be an .xlsx or .xls workbook.')
    path=work/f'uploaded_metadata.{suffix}'
    path.write_bytes(await file.read())
    return path

@router.post('/api/metadata/upload')
async def upload_metadata(metadata:UploadFile=File(...)):
    sid,work=_local_session()
    path=await store_metadata(metadata,work)
    (work/'inputs.json').write_text(json.dumps({'uploaded':str(path)}),encoding='utf-8')
    return {'sessionId':sid,'path':str(path),'fileName':metadata.filename}

@router.post('/api/validate')
async def validate(project_files:Optional[List[UploadFile]]=File(None),
                   metadata:Optional[UploadFile]=File(None),project_name:str=Form(''),metadata_path:str=Form(''),bool_metadata_mode:str=Form('BOOL')):
    sid,root=await stage_project(project_files,project_name)
    work=WORK/sid
    meta=await store_metadata(metadata,work) if metadata and metadata.filename else _local_metadata_path(work,metadata_path)
    return await run_in_threadpool(_execute,sid,root,project_name,meta,False,False,'All',bool_metadata_mode)

@router.post('/api/generate-metadata')
async def generate_metadata(project_files:Optional[List[UploadFile]]=File(None),project_name:str=Form(''),bool_metadata_mode:str=Form('BOOL')):
    sid,root=await stage_project(project_files,project_name)
    return await run_in_threadpool(_execute,sid,root,project_name,None,True,False,'All',bool_metadata_mode)
