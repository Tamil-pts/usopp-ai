import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from backend.core.access import claim_resource
from backend.core import run_history
from backend.core.runtime import WORK, _local_session

router=APIRouter(prefix='/api/history',tags=['Run history'])

def allowed(record, request):
    user=request.state.user
    if user.get('role')!='admin' and (record.get('user') or {}).get('id')!=user['id']:
        raise HTTPException(403,'You can view only your own test results.')
    # Restore ownership for pre-update records that already captured an account.
    owner=record.get('user')
    if owner and owner.get('id'):
        folders=[run_history.RECORDS/record['id'],run_history.SNAPSHOTS/record['id']]
        sid=str(record.get('sessionId') or '')
        if __import__('re').fullmatch(r'[A-Za-z0-9_-]+',sid): folders.extend([WORK/sid,WORK/'compare'/sid])
        for folder in folders:
            if folder.is_dir(): claim_resource(folder,owner)

def load(run_id):
    try:
        if run_id.startswith('legacy_'): return run_history.legacy_result(run_id)
        record=run_history.read_record(run_id)
        try: result=json.loads((run_history.RECORDS/run_id/'result.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):
            from backend.core.persistent_store import archived_run
            archived=archived_run(run_id)
            if not archived: raise FileNotFoundError('History result not found.')
            result=archived[1]
        return record,result
    except (OSError,ValueError): raise HTTPException(404,'History record was not found.')

@router.get('')
def history(request:Request):
    user=request.state.user
    rows=run_history.list_records()
    if user['role']!='admin': rows=[row for row in rows if (row.get('user') or {}).get('id')==user['id']]
    return {'runs':rows,'scope':'all' if user['role']=='admin' else 'own'}

@router.get('/{run_id}')
def result(run_id:str,request:Request):
    record,data=load(run_id)
    allowed(record,request)
    data['historyId']=run_id
    if data.get('workbookPath') and record.get('user'):
        from backend.core.runtime import EXPORTS
        workbook=Path(data['workbookPath']).resolve()
        if workbook.is_file() and workbook.is_relative_to((EXPORTS/'metadata').resolve()): claim_resource(workbook,record['user'])
    if record.get('status')=='interrupted': data.update(runStatus='interrupted',error=record.get('error',''))
    downloads=data.get('historyDownloads',[])
    if downloads:
        if record['kind']=='metadata':
            data['workbookPath']=str(run_history.RECORDS/run_id/'files'/downloads[0]['name'])
            data['downloadExcelUrl']=downloads[0]['url']
        data['snapshotError']=record.get('snapshotError','')
        if record['kind']=='rules': data['reportDownloads']=[item['url'] for item in downloads]
        elif record['kind']=='validation': data['downloadExcelUrl']=downloads[0]['url']
    if record.get('snapshotPath') and Path(record['snapshotPath']).is_dir():
        # A separate read-only session displays the exact archived source, even
        # if the working project has changed or its upload cache was cleared.
        sid='history_'+run_id
        work=WORK/sid
        claim_resource(work,record.get('user') or request.state.user)
        generated=data.get('workbookPath','') if record['kind']=='metadata' else ''
        run_history.write_json(work/'inputs.json',{'project':record['snapshotPath'],'uploaded':record.get('metadataPath',''),'generated':generated})
        data.update(sessionId=sid,projectPath=record['snapshotPath'],historyId=run_id)
        if record['kind']=='rules':
            run_history.write_json(work/'rule_results.json',data)
            if data.get('ruleConfiguration'): run_history.write_json(work/'rules.json',data['ruleConfiguration'])
        if record['kind']=='compare': run_history.write_json(work/'compare_results.json',data)
    return {'record':record,'result':data}

@router.get('/{run_id}/download/{filename}')
def download(run_id:str,filename:str,request:Request):
    record,_=load(run_id)
    allowed(record,request)
    if Path(filename).name!=filename or '\\' in filename or filename not in record.get('artifacts',[]):
        raise HTTPException(404,'Archived download was not found.')
    path=run_history.RECORDS/run_id/'files'/filename
    if not path.is_file(): raise HTTPException(404,'Archived file was not found.')
    return FileResponse(path,filename=filename)

@router.get('/{run_id}/json')
def download_json(run_id:str,request:Request):
    record,data=load(run_id)
    allowed(record,request)
    if record.get('legacy'):
        from fastapi.responses import JSONResponse
        return JSONResponse(data,headers={'Content-Disposition':f'attachment; filename="{record.get("testId") or record["sessionId"]}_result.json"'})
    return FileResponse(run_history.RECORDS/run_id/'result.json',media_type='application/json',filename=f'{record["testId"]}_result.json')

@router.post('/{run_id}/reuse')
def reuse(run_id:str,request:Request):
    record,data=load(run_id)
    allowed(record,request)
    source=Path(record.get('snapshotPath') or record.get('projectPath') or '__missing__')
    if not source.is_dir(): raise HTTPException(409,'Stored project files are unavailable. Upload the project again to rerun it; its previous result is still available.')
    sid,work=_local_session()
    destination=work/'source'
    run_history.copy_project(source,destination)
    return {'projectName':data.get('newName') if record['kind']=='compare' else record['projectName'],'projectPath':str(destination),
            'metadataPath':record.get('metadataPath',''),'sessionId':sid}
