"""Shared WorkHub projects. Existing personal engineering workspaces stay private."""
from __future__ import annotations
import csv
import io
import json
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter,HTTPException,Request,Query,Depends,File,UploadFile
from fastapi.responses import FileResponse,Response,StreamingResponse,RedirectResponse
from starlette.concurrency import run_in_threadpool
from backend.core.workhub import store,identity,timestamp,text,encode
from backend.core import workhub_files as files
from backend.core import workhub_notifications as extensions
from backend.core import workhub_portfolio as portfolio
from backend.core import workhub_workspace as workspace

def personal_account(request:Request):
    if request.state.user.get('isDemo'):raise HTTPException(403,'Sign in with a personal account to open shared company projects.')
router=APIRouter(prefix='/api/workhub',tags=['WorkHub projects'],dependencies=[Depends(personal_account)])
def actor(request):return request.state.user

@router.get('/projects/{key}/delivery-readiness')
def delivery_readiness(key:str,request:Request):
    from backend.core.workhub_quality import store as quality
    from backend.core.workhub_delivery import readiness
    quality.initialize()
    with store.db() as db:return readiness(db,quality.project(db,key,actor(request),True))

@router.get('/overview')
def overview(request:Request):
    from backend.core.workhub_quality import store as quality
    quality.initialize()
    value=store.overview()
    with store.db() as db:
        from backend.core.workhub_billing import approved_hours
        billing=approved_hours(db)
        # Count current submitted reports once. Independent private documents
        # have their own register and must not leak through company KPI counts.
        value['summary']['pending_reviews']=db.execute("SELECT count(*) FROM pi_documents d JOIN pi_revisions r ON r.id=d.current_revision JOIN items p ON p.id=d.project_id AND p.type='project' WHERE r.status='review'").fetchone()[0]
        # Only expose the two portfolio fields; the remaining controlled context stays in project details.
        contexts={}
        for row in db.execute("SELECT q.project_id,q.context FROM qc_projects q JOIN items p ON p.id=q.project_id WHERE p.type='project'"):
            try:
                context=json.loads(row['context'])
            except (TypeError,ValueError):
                continue
            if isinstance(context,dict):contexts[row['project_id']]=context
        open_issues={row[0]:row[1] for row in db.execute("SELECT project_id,count(*) FROM issues WHERE status='open' GROUP BY project_id")}
        approvals={row[0]:row[1] for row in db.execute("SELECT project_id,count(*) FROM items WHERE stage IN ('quality','release_approval','ready_release') GROUP BY project_id")}
        for item in value['items']:
            if item['type']=='project':
                context=contexts.get(item['id'],{})
                item['customer']=context.get('customer','')
                item['customer_project_reference']=context.get('customer_project_reference','')
                item['open_issue_count']=open_issues.get(item['id'],0)
                item['workflow_approval_count']=approvals.get(item['id'],0)
                item['billing_hours']=billing.get(item['id'],0)
                from backend.core.workhub_custom_fields import read
                item['custom_fields']=read(db,item['id'])

    return {**value,'storage':files.storage_usage()}

def portfolio_filters(role:str='',department:str='',team:str='',manager:int|None=None,status:str='',
                      from_date:str=Query('',alias='from'),to_date:str=Query('',alias='to'),project_id:str=''):
    return dict(role=role,department=department,team=team,manager=manager,status=status,
                from_date=from_date,to_date=to_date,project_id=project_id)

@router.get('/portfolio')
def portfolio_dashboard(request:Request,page:int=Query(1,ge=1),page_size:int=Query(15,ge=1,le=50),filters:dict=Depends(portfolio_filters)):
    return portfolio.dashboard(actor(request),page=page,page_size=page_size,**filters)

@router.get('/portfolio/approvals')
def portfolio_approvals(request:Request,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50),documents_only:bool=False,filters:dict=Depends(portfolio_filters)):
    return portfolio.approval_queue(actor(request),page=page,page_size=page_size,documents_only=documents_only,**filters)

@router.get('/portfolio/rules')
def portfolio_rules(request:Request,project_id:str=''):
    return portfolio.get_rules(actor(request),project_id)

@router.put('/portfolio/rules')
def update_portfolio_rules(request:Request,payload:dict):
    return portfolio.save_rules(actor(request),payload)

@router.post('/projects')
def create(request:Request,payload:dict):return workspace.create(actor(request),payload)

@router.post('/requirements-preview')
async def requirements_preview(file:UploadFile=File(...)):
    from backend.api.assist_attachments import preview,MAX_FILE
    try:
        content=await file.read(MAX_FILE+1)
        if len(content)>MAX_FILE:raise HTTPException(413,'Choose a file smaller than 20 MB.')
        value=await run_in_threadpool(preview,file.filename or 'Attachment',content)
        if not value['readable']:raise HTTPException(422,value['notice'] or 'No readable text found.')
        lines=[line.strip() for line in value['text'].splitlines() if line.strip()]
        return {'lines':lines[:200],'notice':value.get('notice',''),'truncated':len(lines)>200}
    finally:await file.close()

@router.get('/project-templates')
def project_templates(request:Request):
    from backend.core.workhub_project_templates import list_templates
    return list_templates(actor(request))

@router.post('/project-templates')
def save_project_template(request:Request,payload:dict):
    from backend.core.workhub_project_templates import save
    return save(actor(request),payload)

@router.get('/project-numbering')
def project_numbering(request:Request):return workspace.numbering_preview()

@router.get('/workflow/catalog')
def workflow_catalog(request:Request):
    from backend.core.workhub_workflow import catalog
    return catalog(actor(request))

@router.get('/projects/{project}/tracking')
def project_tracking(project:str,request:Request,event_page:int=Query(1,ge=1,le=1000000)):
    from backend.core.workhub_workflow import tracking
    return tracking(actor(request),project,event_page)

@router.post('/projects/{project}/workflow')
def apply_workflow(project:str,request:Request,payload:dict):
    from backend.core.workhub_workflow import apply
    return apply(actor(request),project,payload)

@router.get('/projects/{project}')
def project_detail(project:str,request:Request):return workspace.details(actor(request),project)

@router.delete('/projects/{project}')
def delete_project(project:str,request:Request,payload:dict):
    from backend.core.workhub_deletion import delete
    return delete(actor(request),project,payload)

@router.get('/documents')
def common_documents(request:Request,search:str='',kind:str='',status:str='',project_id:str='',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50),library_only:bool=False):
    return workspace.document_register(actor(request),search,kind,status,project_id,page,page_size,library_only)

@router.get('/inbox')
def personal_inbox(request:Request,page:int=Query(1,ge=1),kind:str=Query('',pattern='^(|workflow|document|time|correction)$')):
    from backend.core.workhub_inbox import inbox
    return inbox(actor(request),page,kind)

@router.post('/documents/{document_id}/delete')
def delete_document(document_id:str,request:Request,payload:dict):
    from backend.core.workhub_document_actions import delete
    return delete(actor(request),document_id,payload)

@router.post('/document-spaces')
def create_independent_document(request:Request,payload:dict):
    from backend.core.workhub_document_spaces import create
    return create(actor(request),payload)

@router.get('/items/{item}/approval-documents')
def workflow_approval_documents(item:str,request:Request,offset:int=Query(0,ge=0)):
    from backend.core.workhub_approval_documents import overview
    return overview(actor(request),item,offset)

@router.put('/items/{item}/approval-documents')
def attach_workflow_documents(item:str,request:Request,payload:dict):
    from backend.core.workhub_approval_documents import save
    return save(actor(request),item,payload)

@router.get('/documents/{document_id}/library-preview')
def preview_library_document(document_id:str,request:Request):
    from backend.core.workhub_quality import store as quality,pdf_templates
    from backend.core.workhub_document_spaces import authorize
    quality.initialize();user=actor(request)
    with store.db() as db:
        d=db.execute('SELECT * FROM pi_documents WHERE id=?',(document_id,)).fetchone()
        if not d or not d['approved_revision']:raise HTTPException(404,'Approved library document not found.')
        p=store.item(db,d['project_id'])
        if not p.get('is_document_space'):raise HTTPException(404,'Independent library document not found.')
        authorize(db,p,user,allow_library=True)
        if not p['library']:raise HTTPException(403,'This document has not been shared in the library.')
        control=db.execute('SELECT * FROM qc_documents WHERE document_id=?',(document_id,)).fetchone()
        doc=dict(control) if control else dict(d);rev={'id':d['approved_revision']}
    raw=pdf_templates.export(user,p['id'],doc,rev,controlled=bool(control),library_read=True)
    return Response(raw,media_type='application/pdf',headers={'Cache-Control':'private, no-store','Content-Disposition':'inline'})

@router.get('/document-spaces/{space}')
def independent_document(space:str,request:Request):
    from backend.core.workhub_document_spaces import details
    return details(actor(request),space)

@router.put('/document-spaces/{space}')
def update_independent_document(space:str,request:Request,payload:dict):
    from backend.core.workhub_document_spaces import update
    return update(actor(request),space,payload)

@router.get('/project-options')
def project_options(request:Request):
    from backend.core.workhub_quality import store as quality,branding
    quality.initialize()
    with store.db() as db:return branding.choices(db)

@router.post('/projects/{project}/condition')
def project_condition(project:str,request:Request,payload:dict):return workspace.exception(actor(request),project,payload)

@router.post('/projects/{project}/tasks')
def create_task(project:str,request:Request,payload:dict):return store.create(actor(request),payload,project)

@router.put('/projects/{project}/schedule')
def schedule(project:str,request:Request,payload:dict):
    from backend.core.workhub_planning import schedule as save_schedule
    return save_schedule(store,actor(request),project,payload)

@router.put('/projects/{project}/planning-method')
def planning_method(project:str,request:Request,payload:dict):
    from backend.core.workhub_planning import change_method
    return change_method(store,actor(request),project,payload)

@router.post('/projects/{project}/sprints')
def create_sprint(project:str,request:Request,payload:dict):
    from backend.core.workhub_planning import save_sprint
    return save_sprint(store,actor(request),project,payload)

@router.put('/projects/{project}/sprints/{sprint}')
def update_sprint(project:str,sprint:str,request:Request,payload:dict):
    from backend.core.workhub_planning import save_sprint
    return save_sprint(store,actor(request),project,payload,sprint)

@router.put('/items/{item}')
def edit_item(item:str,request:Request,payload:dict):return workspace.edit(actor(request),item,payload)

@router.post('/items/{item}/transition')
def transition(item:str,request:Request,payload:dict):
    user=actor(request);workspace.guard_transition(user,item);result=store.transition(user,item,payload)
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
        store.contribute(db,project,user)
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

@router.get('/project-exports')
def project_export_catalog(request:Request,role:str=''):
    from backend.core.workhub_project_exports import catalog
    return catalog(actor(request),role)

@router.post('/project-exports')
def project_export(request:Request,payload:dict):
    from backend.core.workhub_project_exports import export
    return export(actor(request),payload)

@router.post('/project-exports/views')
def project_export_view(request:Request,payload:dict):
    from backend.core.workhub_project_exports import save_view
    return save_view(actor(request),payload)

@router.delete('/project-exports/views/{view_id}')
def delete_project_export_view(view_id:str,request:Request):
    from backend.core.workhub_project_exports import delete_view
    return delete_view(actor(request),view_id)

@router.get('/reports/{format}')
def report(format:str,request:Request):
    overview=store.overview();items=overview['items']
    from backend.core.workhub_billing import approved_hours
    with store.db() as db:billing=approved_hours(db)
    for item in items:
        if item['type']=='project':item['billing_hours']=billing.get(item['id'],0)
    users={row['id']:row['username'] for row in overview['users']}
    headers=['Project / task','Type','Assignee','Stage','Planned start','Baseline due','Current due','Actual start','Released at','Work completion %','Billing hours (approved time)']
    values=[[row['title'],row['kind'],users.get(row['current_user_id'],'Account unavailable'),row['stage_label'],row['start_date'],row['baseline_due'],row['due_date'],row['started_at'] or '',row['completed_at'] or '',row.get('progress',''),round(row['billing_hours'],2) if row['type']=='project' else ''] for row in items]
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
