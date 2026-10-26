"""Shared WorkHub projects. Existing personal engineering workspaces stay private."""
from __future__ import annotations
import csv
import io
import json
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter,HTTPException,Request,Query,Depends
from fastapi.responses import FileResponse,Response,StreamingResponse,RedirectResponse
from starlette.concurrency import run_in_threadpool
from backend.core.workhub import store,identity,timestamp,text,encode
from backend.core import workhub_files as files
from backend.core import workhub_notifications as extensions

def personal_account(request:Request):
    if request.state.user.get('isDemo'):raise HTTPException(403,'Sign in with a personal account to open shared company projects.')
router=APIRouter(prefix='/api/workhub',tags=['WorkHub projects'],dependencies=[Depends(personal_account)])
def actor(request):return request.state.user

@router.get('/overview')
def overview(request:Request):return {**store.overview(),'storage':files.storage_usage()}

@router.post('/projects')
def create(request:Request,payload:dict):return store.create(actor(request),payload)

@router.get('/projects/{project}')
def project_detail(project:str,request:Request):return store.detail(project)

@router.post('/projects/{project}/tasks')
def create_task(project:str,request:Request,payload:dict):return store.create(actor(request),payload,project)

@router.put('/projects/{project}/schedule')
def schedule(project:str,request:Request,payload:dict):
    from backend.core.workhub_planning import schedule as save_schedule
    return save_schedule(store,actor(request),project,payload)

@router.post('/projects/{project}/sprints')
def create_sprint(project:str,request:Request,payload:dict):
    from backend.core.workhub_planning import save_sprint
    return save_sprint(store,actor(request),project,payload)

@router.put('/projects/{project}/sprints/{sprint}')
def update_sprint(project:str,sprint:str,request:Request,payload:dict):
    from backend.core.workhub_planning import save_sprint
    return save_sprint(store,actor(request),project,payload,sprint)

@router.put('/items/{item}')
def edit_item(item:str,request:Request,payload:dict):return store.edit(actor(request),item,payload)

@router.post('/items/{item}/transition')
def transition(item:str,request:Request,payload:dict):
    user=actor(request);result=store.transition(user,item,payload)
    if result['type']=='project' and result['stage']=='released':
        from backend.core.workhub_intelligence import jobs
        jobs.enqueue(user,item,'q_package',{'closure_version':result['version']})
    return result

@router.post('/items/{item}/updates')
def add_update(item:str,request:Request,payload:dict):return store.add_update(actor(request),item,payload)

@router.post('/updates/{update}/review')
def review_time(update:str,request:Request,payload:dict):return store.time_review(actor(request),update,payload)

@router.post('/updates/{update}/resubmit')
def resubmit_time(update:str,request:Request,payload:dict):return store.resubmit_time(actor(request),update,payload)

@router.get('/time-entries')
def time_entries(request:Request):
    with store.db() as db:return {'items':[dict(row) for row in db.execute('SELECT * FROM updates WHERE minutes>0 ORDER BY created_at DESC LIMIT 1000')]}

@router.get('/activity')
def activity(request:Request):
    with store.db() as db:return {'items':[dict(row) for row in db.execute('SELECT u.*,i.title AS item_title,e.iteration,e.kind AS tool_kind,e.status AS run_status FROM updates u JOIN items i ON i.id=u.item_id LEFT JOIN engineering_runs e ON e.update_id=u.id ORDER BY u.created_at DESC LIMIT 300')]}

@router.post('/projects/{project}/issues')
def create_issue(project:str,request:Request,payload:dict):
    user=actor(request);store.actor(user)
    with store.db(True) as db:
        item=store.item(db,payload.get('item_id') or project)
        if item['project_id']!=project:raise HTTPException(400,'Choose a task from this project.')
        key=identity();now=timestamp();title=text(payload.get('title',''),2000,True);owner=store.user_id(payload.get('owner_id',item['owner_id']))
        db.execute('INSERT INTO issues VALUES(?,?,?,?,?,?,?,?,?)',(key,project,item['id'],title,owner,user['id'],'open',now,now))
        store.event(db,item,user,'issue_created',{'issue_id':key,'title':title,'owner_id':owner})
        store.notify(db,item,user['id'],[owner],'Issue assigned: '+item['title'],title)
        return {'id':key}

@router.put('/issues/{issue}')
def update_issue(issue:str,request:Request,payload:dict):
    user=actor(request);store.actor(user)
    with store.db(True) as db:
        row=db.execute('SELECT * FROM issues WHERE id=?',(issue,)).fetchone()
        if not row:raise HTTPException(404,'Issue not found.')
        item=store.item(db,row['item_id'])
        if user['id'] not in {row['owner_id'],row['created_by'],item['created_by']} and user['role']!='admin':raise HTTPException(403,'Only the issue owner or project manager can update this issue.')
        status=payload.get('status')
        if status not in {'open','resolved'}:raise HTTPException(400,'Choose Open or Resolved.')
        db.execute('UPDATE issues SET status=?,updated_at=? WHERE id=?',(status,timestamp(),issue))
        store.event(db,item,user,'issue_'+status,{'issue_id':issue});return {'status':status}

@router.post('/projects/{project}/uploads')
def start_upload(project:str,request:Request,payload:dict):return files.begin(actor(request),project,payload)

@router.get('/uploads/{upload}')
def upload_state(upload:str,request:Request):return files.get_upload(actor(request),upload)

@router.put('/uploads/{upload}')
async def upload_chunk(upload:str,request:Request,offset:int=Query(...,ge=0)):
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>files.CHUNK:raise HTTPException(413,'Send file chunks of at most 8 MB.')
    return await run_in_threadpool(files.append,actor(request),upload,offset,bytes(content))

@router.post('/uploads/{upload}/finish')
def finish_upload(upload:str,request:Request):return files.finish(actor(request),upload)

@router.delete('/uploads/{upload}')
def cancel_upload(upload:str,request:Request):return files.cancel(actor(request),upload)

@router.get('/files/{file}/download')
def download_file(file:str,request:Request):
    row,path=files.file_record(file)
    from backend.core.workhub_quality.packages import file_access
    with store.db(True) as db:file_access(db,actor(request),row)
    return FileResponse(path,filename=Path(row['name']).name,media_type='application/octet-stream',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.post('/projects/{project}/revisions')
def add_revision(project:str,request:Request,payload:dict):return files.revision(actor(request),project,payload)

@router.get('/revisions/{revision}/download')
def download_revision(revision:str,request:Request):
    row,entries=files.revision_files(revision)
    if len(entries)==1:
        record,path=entries[0]
        return FileResponse(path,filename=Path(record['name']).name,media_type='application/octet-stream',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
    filename='Project_'+row['label']+'.zip'
    return StreamingResponse(files.stream_revision(entries),media_type='application/zip',headers={'Cache-Control':'private, no-store','Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename,safe='')})

@router.get('/revisions/{revision}/manifest')
def revision_manifest(revision:str,request:Request):
    with store.db() as db:
        row=db.execute('SELECT * FROM revisions WHERE id=?',(revision,)).fetchone()
        if not row:raise HTTPException(404,'Revision not found.')
        available={entry['id']:dict(entry) for entry in db.execute('SELECT id,name,size,sha256 FROM files WHERE project_id=?',(row['project_id'],))}
        result={**dict(row),'files':[available[key] for key in json.loads(row['file_ids']) if key in available]}
        result.pop('file_ids',None)
    return Response(json.dumps(result,ensure_ascii=False),media_type='application/json',headers={'Content-Disposition':'attachment; filename="WorkHub_revision_files.json"','Cache-Control':'private, no-store'})

@router.post('/items/{item}/prepare-update')
def prepare_update(item:str,request:Request,payload:dict):
    store.actor(actor(request))
    from backend.core.workhub_evidence import prepare
    return prepare(actor(request),item,payload)

@router.get('/notifications')
def notifications(request:Request):
    from backend.core.workhub_growth.store import notification_targets
    return notification_targets(store.notifications(actor(request)))

@router.get('/items/{item}/share')
def share_item(item:str,request:Request):return extensions.prepare_share(actor(request),item,str(request.base_url))

@router.get('/notifications/{notification}/share')
def share_notification(notification:str,request:Request):
    with store.db() as db:row=db.execute('SELECT item_id FROM notifications WHERE id=? AND recipient_id=?',(notification,actor(request)['id'])).fetchone()
    if not row:raise HTTPException(404,'Notification not found.')
    return extensions.prepare_share(actor(request),row['item_id'],str(request.base_url),notification)

@router.post('/notifications/read')
def read_notifications(request:Request,payload:dict):
    with store.db(True) as db:
        if payload.get('all') is True:db.execute('UPDATE notifications SET read_at=? WHERE recipient_id=? AND read_at IS NULL',(timestamp(),actor(request)['id']))
        else:db.execute('UPDATE notifications SET read_at=? WHERE id=? AND recipient_id=?',(timestamp(),payload.get('id'),actor(request)['id']))
    return store.notifications(actor(request))

@router.post('/notifications/{notification}/retry')
def retry(notification:str,request:Request):
    with store.db(True) as db:
        if not db.execute('SELECT 1 FROM notifications WHERE id=? AND recipient_id=?',(notification,actor(request)['id'])).fetchone():raise HTTPException(404,'Notification not found.')
        db.execute("UPDATE outbox SET status='pending',next_attempt=0,attempts=0 WHERE notification_id=? AND status IN ('failed','waiting_connection')",(notification,))
    return {'status':'queued'}

@router.get('/connections')
def connections(request:Request):return extensions.own_settings(actor(request))

@router.put('/connections')
def save_connections(request:Request,payload:dict):return extensions.save_settings(actor(request),payload)

@router.put('/connections/company')
def company_connections(request:Request,payload:dict):return extensions.save_config(actor(request),payload)

@router.get('/connections/microsoft/start')
def microsoft_start(request:Request):return RedirectResponse(extensions.connect(actor(request)),status_code=303)

@router.get('/connections/microsoft/callback')
def microsoft_callback(request:Request):
    extensions.callback(actor(request),dict(request.query_params))
    return RedirectResponse('/?workhubConnections=connected',status_code=303)

@router.delete('/connections/microsoft')
def microsoft_disconnect(request:Request):return extensions.disconnect(actor(request))

@router.get('/projects/{project}/shared-results/{run_id}')
def shared_result(project:str,run_id:str,request:Request):
    from backend.core import run_history
    with store.db() as db:
        store.item(db,project)
        shared=any(any(run['id']==run_id for run in json.loads(row['run_ids'])) for row in db.execute('SELECT run_ids FROM updates WHERE project_id=?',(project,)))
    if not shared:raise HTTPException(404,'This result was not shared with the project.')
    try:record=run_history.read_record(run_id)
    except (ValueError,OSError):raise HTTPException(404,'Saved result not found.') from None
    prefix='/api/workhub/projects/'+project+'/shared-results/'+run_id
    downloads=[{'name':Path(name).name,'url':prefix+'/download/'+quote(Path(name).name,safe='')} for name in record.get('artifacts',[])]
    if (run_history.RECORDS/run_id/'result.json').is_file():downloads.append({'name':'Recorded result JSON','url':prefix+'/evidence'})
    if record.get('snapshotPath') and Path(record['snapshotPath']).is_dir():downloads.append({'name':'Uploaded project snapshot ZIP','url':prefix+'/source'})
    return {'id':run_id,'kind':record['kind'],'projectName':record.get('projectName',''),'testId':record.get('testId',''),
            'status':record.get('status'),'summary':record.get('summary') or {},'files':downloads}

@router.get('/projects/{project}/shared-results/{run_id}/evidence')
def shared_evidence(project:str,run_id:str,request:Request):
    record=shared_result(project,run_id,request)
    from backend.core import run_history
    path=run_history.RECORDS/run_id/'result.json'
    if not path.is_file():raise HTTPException(404,'Saved run evidence is unavailable.')
    return FileResponse(path,filename=(record.get('testId') or run_id)+'_result.json',media_type='application/json',headers={'Cache-Control':'private, no-store'})

@router.get('/projects/{project}/shared-results/{run_id}/source')
def shared_source(project:str,run_id:str,request:Request):
    shared_result(project,run_id,request)
    from backend.core import run_history
    record=run_history.read_record(run_id);source=record.get('snapshotPath')
    if not source or not Path(source).is_dir():raise HTTPException(404,'The project snapshot is unavailable.')
    root=Path(source).resolve();entries=[]
    for path in root.rglob('*'):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):continue
        entries.append(({'name':files.relative_name(path.relative_to(root).as_posix())},path))
    return StreamingResponse(files.stream_revision(entries),media_type='application/zip',headers={'Cache-Control':'private, no-store','Content-Disposition':"attachment; filename*=UTF-8''"+quote((record.get('testId') or run_id)+'_project.zip',safe='')})

@router.get('/projects/{project}/shared-results/{run_id}/download/{name}')
def shared_download(project:str,run_id:str,name:str,request:Request):
    record=shared_result(project,run_id,request)
    if name!=Path(name).name or '\\' in name or name not in {row['name'] for row in record['files']}:raise HTTPException(404,'Shared result file not found.')
    from backend.core import run_history
    path=run_history.RECORDS/run_id/'files'/name
    if not path.is_file():raise HTTPException(404,'Shared result file is unavailable.')
    return FileResponse(path,filename=name,headers={'Cache-Control':'private, no-store'})

@router.get('/reports/{format}')
def report(format:str,request:Request):
    overview=store.overview();items=overview['items']
    users={row['id']:row['username'] for row in overview['users']}
    headers=['Project / task','Type','Assignee','Stage','Planned start','Baseline due','Current due','Actual start','Released at','Work completion %']
    values=[[row['title'],row['kind'],users.get(row['current_user_id'],'Account unavailable'),row['stage_label'],row['start_date'],row['baseline_due'],row['due_date'],row['started_at'] or '',row['completed_at'] or '',row.get('progress','')] for row in items]
    if format=='csv':
        stream=io.StringIO();writer=csv.writer(stream);writer.writerow(headers)
        writer.writerows([["'"+str(value) if str(value).startswith(('=','+','-','@')) else value for value in row] for row in values])
        return Response('\ufeff'+stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="WorkHub_projects.csv"'})
    if format=='json':return Response(json.dumps({'generatedAt':timestamp(),'projects':overview,'timeEntries':time_entries(request)},ensure_ascii=False),media_type='application/json',headers={'Content-Disposition':'attachment; filename="WorkHub_evidence.json"'})
    if format=='pdf':
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4,landscape
        from xml.sax.saxutils import escape
        result=io.BytesIO();styles=getSampleStyleSheet();rows=[[Paragraph(escape(str(value)),styles['BodyText']) for value in row] for row in [['Project / task','Assignee','Stage','Due','Completion'],*[[row[0],row[2],row[3],row[6],str(row[9])+'%'] for row in values[:1000]]]]
        table=LongTable(rows,repeatRows=1,colWidths=[260,130,140,100,80]);table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f3f4')),('GRID',(0,0),(-1,-1),.3,colors.lightgrey),('VALIGN',(0,0),(-1,-1),'TOP')]))
        SimpleDocTemplate(result,pagesize=landscape(A4),leftMargin=24,rightMargin=24).build([Paragraph('WorkHub project portfolio',styles['Title']),Spacer(1,12),table])
        return Response(result.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="WorkHub_projects.pdf"'})
    raise HTTPException(400,'Choose csv, pdf or json.')
