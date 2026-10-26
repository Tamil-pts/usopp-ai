"""Durable run records and project snapshots, independent of browser/cache state."""
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import threading
import uuid
from backend.core.runtime import WORK, EXPORTS, log
from python_engine.project_paths import IGNORED_PROJECT_DIRS

current_user = ContextVar('history_user', default=None)
LOCK = threading.RLock()
SERVER_ID = uuid.uuid4().hex
RUN_LOCKS = {}
RECORDS = EXPORTS/'history'
SNAPSHOTS = WORK/'history'
IGNORED = IGNORED_PROJECT_DIRS

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)

def copy_project(source, destination):
    source=Path(source).resolve()
    destination=Path(destination).resolve()
    if destination.is_relative_to(source):
        raise ValueError('A project snapshot cannot be stored inside its source project.')
    shutil.copytree(source,destination,ignore=lambda folder,names:[name for name in names if name.casefold() in IGNORED or (Path(folder)/name).is_symlink()])

SESSION_RESULTS = {'validation':'validation_results.json','metadata':'generated_metadata.json',
                   'rules':'rule_results.json','compare':'compare_results.json','datainspect':'datainspect_results.json',
                   'data-model':'data_model_results.json'}

def archive_database(record, result):
    # JSON/file archives remain recoverable even when the database is unavailable.
    try:
        from backend.core.persistent_store import archive_run
        archive_run(record, result)
    except Exception:
        log.exception('RUN_HISTORY_DATABASE_ERROR run=%s; file archive retained', record['id'])

def sync_workhub(record,data,root=None,new=False):
    # Existing private archives are not published merely by exporting a report.
    if new and data.get('workhubCapture') is False:return
    if not new and not record.get('workhubAutoCapture'):return
    if record.get('kind') not in {'validation','metadata','datainspect','compare','rules'}:return
    if not record.get('user') or record['user'].get('isDemo'):return
    record['workhubAutoCapture']=True
    try:
        from .workhub_runs import synchronize
        link=synchronize(record,data,root);record.update(link,workhubSyncPending=False);data.update(link,workhubSyncPending=False)
    except Exception:
        record['workhubSyncPending']=True;data['workhubSyncPending']=True
        log.exception('WORKHUB_RUN_CAPTURE_ERROR run=%s; original engineering archive retained',record['id'])

def begin_run(kind, data, root=None):
    from backend.core.identifiers import identify_result
    from backend.core.access import claim_resource
    identify_result(data, kind)
    run_id = data.get('historyId') or uuid.uuid4().hex
    data['historyId'] = run_id
    folder = RECORDS/run_id
    claim_resource(folder)
    record = {'id':run_id,'kind':kind,'projectName':data.get('projectName') or (Path(root).name if root else 'DataInspect'),
              'testId':data['testId'],'machineDepartment':data['machineDepartment'],
              'createdAt':datetime.now(timezone.utc).isoformat(),'user':current_user.get(),
              'sessionId':data.get('sessionId'),'status':'running','summary':{},
              'projectPath':str(root or ''),'snapshotPath':'','metadataPath':'','snapshotError':''}
    record['serverId']=SERVER_ID
    data.update(runOwner=record['user'],createdAt=record['createdAt'])
    sync_workhub(record,data,root,new=True)
    write_json(folder/'result.json', data)
    write_json(folder/'record.json', record)
    archive_database(record, data)
    return record

def run_lock(run_id):
    with LOCK: return RUN_LOCKS.setdefault(run_id, threading.RLock())

def record_run(kind, data, root=None, metadata_path=None):
    data.setdefault('historyId',uuid.uuid4().hex)
    with run_lock(data['historyId']):
        return _record_run(kind,data,root,metadata_path)

def _record_run(kind, data, root=None, metadata_path=None):
    from backend.core.identifiers import identify_result
    identify_result(data,kind)
    if kind=='rules':
        reports=[]
        for index,name in enumerate(data.get('moduleReports') or [],1):
            source=WORK/str(data.get('sessionId') or '')/str(name)
            if source.is_file() and source.parent==WORK/str(data.get('sessionId') or ''):
                target=source if source.name.startswith(data['testId']+'_') else source.with_name(f'{data["testId"]}_LogicScan_{index}{source.suffix}')
                if source != target: source.rename(target)
                reports.append(target.name)
        data['moduleReports']=reports
        data['reportDownloads']=[f'/api/download/{data["sessionId"]}/{name}' for name in reports]
    from backend.core.access import claim_resource
    run_id=data.get('historyId') or uuid.uuid4().hex
    folder=RECORDS/run_id
    claim_resource(folder)
    old=json.loads((folder/'record.json').read_text(encoding='utf-8')) if (folder/'record.json').is_file() else {}
    record={**old,'id':run_id,'kind':kind,'projectName':data.get('projectName') or (Path(root).name if root else 'DataInspect'),
            'testId':data['testId'],'machineDepartment':data['machineDepartment'],
            'createdAt':old.get('createdAt') or datetime.now(timezone.utc).isoformat(),'user':old.get('user') or current_user.get(),
            'completedAt':datetime.now(timezone.utc).isoformat(), 'status':data.get('runStatus') or 'completed',
            'sessionId':data.get('sessionId'),'summary':data.get('summary') or data.get('counts') or {},
            'projectPath':str(root or old.get('projectPath') or ''),'snapshotPath':old.get('snapshotPath',''),
            'metadataPath':old.get('metadataPath',''),'snapshotError':old.get('snapshotError',''), 'error':data.get('error','')}
    data.update(runOwner=record['user'],createdAt=record['createdAt'],completedAt=record['completedAt'])
    try:
        if root and not record['snapshotPath']:
            snapshot=SNAPSHOTS/run_id/'project'
            claim_resource(snapshot.parent, record['user'])
            snapshot.parent.mkdir(parents=True,exist_ok=True)
            copy_project(root,snapshot)
            record['snapshotPath']=str(snapshot)
    except (OSError,ValueError) as error:
        record['snapshotError']=str(error)
        log.exception('RUN_HISTORY_SNAPSHOT_ERROR run=%s',run_id)
    if metadata_path and Path(metadata_path).is_file():
        target=folder/('input_metadata'+Path(metadata_path).suffix)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(metadata_path,target)
        record['metadataPath']=str(target)
    data['historyId']=run_id
    # Keep downloads with the archived result; working caches can be removed.
    artifacts=folder/'files'
    saved=old.get('artifacts',[])
    candidates=[]
    if data.get('workbookPath'): candidates.append(Path(data['workbookPath']))
    sid=str(data.get('sessionId') or '')
    session_folder=WORK/sid
    if kind=='compare' and not (session_folder/'compare_results.json').is_file(): session_folder=WORK/'compare'/sid
    if kind=='rules' and (session_folder/'rules.json').is_file():
        data['ruleConfiguration']=json.loads((session_folder/'rules.json').read_text(encoding='utf-8'))
        data.setdefault('pipelineRunId',data['ruleConfiguration'].get('pipelineRunId'))
    if kind=='compare' and (session_folder/'hmi_details').is_dir():
        try: shutil.copytree(session_folder/'hmi_details',folder/'hmi_details',dirs_exist_ok=True)
        except OSError as error:
            record['snapshotError']=f'Comparison details archive: {error}'
            log.exception('RUN_HISTORY_DETAILS_ERROR run=%s',run_id)
    if session_folder.is_dir():
        if not data.get('workbookPath'): candidates.extend(path for path in session_folder.glob('*.xlsx') if path.name!='uploaded_metadata.xlsx')
        candidates.extend(session_folder/name for name in data.get('moduleReports',[]) if Path(name).name==name)
    for source in candidates:
        if source.is_file():
            artifacts.mkdir(parents=True,exist_ok=True)
            destination=artifacts/source.name
            if source.resolve()!=destination.resolve(): shutil.copy2(source,destination)
            if source.name not in saved: saved.append(source.name)
    record['artifacts']=saved
    data['historyDownloads']=[{'name':name,'url':f'/api/history/{run_id}/download/{name}'} for name in saved]
    sync_workhub(record,data,root,new=not bool(old))
    write_json(folder/'result.json',data)
    session_file=session_folder/SESSION_RESULTS[kind]
    if session_file.is_file(): write_json(session_file,data)
    write_json(folder/'record.json',record)
    archive_database(record, data)
    return record

def add_run_artifact(run_id, source):
    """Retain each prepared report version with its original test."""
    from backend.core.access import require_resource
    source=Path(source)
    folder=RECORDS/run_id
    require_resource(folder)
    with run_lock(run_id):
        record=read_record(run_id)
        name=f'{source.stem}_{source.parent.name[:8]}{source.suffix}'
        destination=folder/'files'/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        record['artifacts']=list(dict.fromkeys([*record.get('artifacts',[]),name]))
        result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        result['historyDownloads']=[{'name':item,'url':f'/api/history/{run_id}/download/{item}'} for item in record['artifacts']]
        sync_workhub(record,result)
        write_json(folder/'result.json',result)
        write_json(folder/'record.json',record)
        archive_database(record, result)
        return name

def read_record(run_id):
    if not __import__('re').fullmatch(r'[a-f0-9]{32}',run_id):
        raise ValueError('Invalid history ID.')
    try:
        record=json.loads((RECORDS/run_id/'record.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):
        from backend.core.persistent_store import archived_run
        archived=archived_run(run_id)
        if not archived: raise FileNotFoundError('History record not found.')
        record=archived[0]
    if record.get('status')=='running' and record.get('serverId')!=SERVER_ID:
        record.update(status='interrupted',error='Server restarted before this test completed. Run a new test.')
    return record

def list_records():
    with LOCK:
        from backend.core.persistent_store import archived_records, archive_run
        try: indexed={row['id']:row for row in archived_records()}
        except Exception:
            log.exception('RUN_HISTORY_DATABASE_READ_ERROR; using file archives')
            indexed={}
        records=[]
        if RECORDS.exists():
            for path in RECORDS.glob('*/record.json'):
                try:
                    row=json.loads(path.read_text(encoding='utf-8'))
                    if row['id'] not in indexed:
                        # Adopt earlier file history without changing owners or IDs.
                        try:
                            result=json.loads((path.parent/'result.json').read_text(encoding='utf-8'))
                            archive_run(row,result,only_missing=True)
                        except Exception: log.exception('RUN_HISTORY_DATABASE_IMPORT_ERROR run=%s',row['id'])
                    indexed[row['id']]=row
                except (OSError,ValueError,KeyError): continue
        for row in indexed.values():
            if row.get('status')=='running' and row.get('serverId')!=SERVER_ID:
                row.update(status='interrupted',error='Server restarted before this test completed. Run a new test.')
            row['projectAvailable']=bool(row.get('snapshotPath') and Path(row['snapshotPath']).is_dir())
            records.append(row)
        # Pre-history runs can still be opened, but user identity was not captured.
        known={(row.get('sessionId'),row.get('kind')) for row in records}
        folders=list(WORK.iterdir())
        if (WORK/'compare').is_dir(): folders.extend((WORK/'compare').iterdir())
        for folder in folders:
            if not folder.is_dir() or folder.name in {'history','compare','data_models','chopper_knowledge'} or folder.name.startswith('history_'): continue
            for name,kind in [('validation_results.json','validation'),('generated_metadata.json','metadata'),('rule_results.json','rules'),('compare_results.json','compare')]:
                if (folder.name,kind) in known: continue
                path=folder/name
                if not path.is_file(): continue
                try:
                    data=json.loads(path.read_text(encoding='utf-8'))
                    manifest=json.loads((folder/'inputs.json').read_text(encoding='utf-8')) if (folder/'inputs.json').is_file() else {'project':data.get('projectPath','')}
                    row={'id':'legacy_'+kind+'_'+folder.name,'sessionId':folder.name,'kind':kind,'projectName':data.get('projectName') or Path(manifest.get('project','')).name or folder.name,
                         'testId':data.get('testId',''),'machineDepartment':data.get('machineDepartment','All'),'status':'completed',
                         'createdAt':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),'user':None,'legacy':True,
                         'projectPath':manifest.get('project',''),'summary':data.get('summary') or data.get('counts') or {},
                         'projectAvailable':bool(manifest.get('project')) and Path(manifest['project']).is_dir()}
                    records.append(row)
                except (OSError,ValueError): continue
        return sorted(records,key=lambda row:row['createdAt'],reverse=True)

def legacy_result(run_id):
    record=next((row for row in list_records() if row['id']==run_id or (row.get('legacy') and 'legacy_'+row['sessionId']==run_id)),None)
    if record is None: raise FileNotFoundError('History record not found.')
    folder=WORK/record['sessionId']
    if not folder.is_dir(): folder=WORK/'compare'/record['sessionId']
    name={'validation':'validation_results.json','metadata':'generated_metadata.json','rules':'rule_results.json','compare':'compare_results.json'}[record['kind']]
    data=json.loads((folder/name).read_text(encoding='utf-8'))
    data.update(sessionId=record['sessionId'],projectName=record['projectName'],projectPath=record['projectPath'])
    workbook=next(folder.glob('*.xlsx'),None)
    if workbook: data['downloadExcelUrl']=f'/api/download/{folder.name}/{workbook.name}'
    return record,data
