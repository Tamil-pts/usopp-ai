"""Project Intelligence API, using the existing WorkHub account and access rules."""
import json
from urllib.parse import quote
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import Response,FileResponse
from backend.api.workhub import personal_account
from backend.core.workhub import store as hub,text,identity,timestamp
from backend.core.workhub_intelligence import store,operations,jobs,documents
from backend.core.workhub_intelligence.local_ai import capabilities,ServiceUnavailable

router=APIRouter(prefix='/api/workhub/projects/{project_id}/intelligence',tags=['WorkHub Project Intelligence'],dependencies=[Depends(personal_account)])


@router.get('')
def overview(project_id:str,request:Request):return {**store.overview(request.state.user,project_id),'services':capabilities()}


@router.post('/meetings')
def create_meeting(project_id:str,payload:dict,request:Request):return operations.create_meeting(request.state.user,project_id,payload)


@router.get('/meetings/{meeting_id}')
def meeting(project_id:str,meeting_id:str,request:Request,version:int|None=None):return operations.get_meeting(request.state.user,project_id,meeting_id,version)


@router.get('/meetings/{meeting_id}/media')
def media(project_id:str,meeting_id:str,request:Request):
    value=operations.get_meeting(request.state.user,project_id,meeting_id)
    from backend.core.workhub_files import file_record
    import mimetypes
    record,path=file_record(value['file_id'],project_id)
    return FileResponse(path,media_type=mimetypes.guess_type(record['name'])[0] or 'application/octet-stream',headers={'Content-Disposition':'inline','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.put('/meetings/{meeting_id}/transcript')
def transcript(project_id:str,meeting_id:str,payload:dict,request:Request):return operations.edit_transcript(request.state.user,project_id,meeting_id,payload)


@router.get('/meetings/{meeting_id}/transcript/export')
def transcript_export(project_id:str,meeting_id:str,request:Request,format:str='vtt',version:int|None=None):
    value=operations.get_meeting(request.state.user,project_id,meeting_id,version)
    if format=='json':return Response(json.dumps(value,ensure_ascii=False),media_type='application/json',headers={'Content-Disposition':'attachment; filename="meeting-transcript.json"'})
    def timecode(seconds):
        ms=round(float(seconds or 0)*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'
    rows=['WEBVTT','']
    for segment in value['transcript'].get('segments',[]):
        if segment.get('start') is None:continue
        end=segment.get('end') if segment.get('end') is not None else segment['start']+1
        rows.extend([segment['id'],timecode(segment['start'])+' --> '+timecode(end),segment['text'],''])
    return Response('\n'.join(rows),media_type='text/vtt',headers={'Content-Disposition':'attachment; filename="meeting-transcript.vtt"'})


@router.post('/meetings/{meeting_id}/transcript/confirm')
def confirm_transcript(project_id:str,meeting_id:str,payload:dict,request:Request):
    return operations.confirm_transcript(request.state.user,project_id,meeting_id,payload)


@router.post('/jobs')
def queue(project_id:str,payload:dict,request:Request):return jobs.enqueue(request.state.user,project_id,payload.get('kind'),payload.get('payload',{}))


@router.get('/jobs')
def job_statuses(project_id:str,request:Request,limit:int=50,cursor:str|None=None):return jobs.list_jobs(request.state.user,project_id,limit,cursor)


@router.get('/jobs/{job_id}')
def job_status(project_id:str,job_id:str,request:Request):return jobs.get_job(request.state.user,project_id,job_id)


@router.get('/jobs/{job_id}/download')
def download_job(project_id:str,job_id:str,request:Request):
    from backend.core.workhub_intelligence.exports import download
    result,path=download(request.state.user,project_id,job_id)
    return FileResponse(path,media_type=result['media_type'],filename=result['filename'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.post('/jobs/{job_id}/cancel')
def cancel(project_id:str,job_id:str,request:Request):return jobs.cancel(request.state.user,project_id,job_id)


@router.post('/jobs/{job_id}/retry')
def retry(project_id:str,job_id:str,request:Request):return jobs.retry(request.state.user,project_id,job_id)


@router.post('/documents')
def create_document(project_id:str,payload:dict,request:Request):return store.save_document(request.state.user,project_id,payload)


@router.get('/documents/{document_id}')
def document(project_id:str,document_id:str,request:Request,revision_id:str|None=None):
    value=store.get_document(request.state.user,project_id,document_id)
    if revision_id:
        with hub.db() as db:value['selected_revision']=store.revision(db,revision_id,document_id)
    return value


@router.put('/documents/{document_id}')
def update_document(project_id:str,document_id:str,payload:dict,request:Request):return store.save_document(request.state.user,project_id,payload,document_id)


@router.put('/documents/{document_id}/text')
def update_text(project_id:str,document_id:str,payload:dict,request:Request):return operations.save_text(request.state.user,project_id,document_id,payload)


@router.post('/documents/{document_id}/review')
def review(project_id:str,document_id:str,payload:dict,request:Request):
    result=store.review(request.state.user,project_id,document_id,payload)
    if payload.get('action')=='approve' and result['document']['kind']=='mom':
        # The reviewer can be any named enabled personal user. Use the original
        # contributor to queue derivation if the reviewer is not a contributor.
        from backend.core import accounts
        creator=next((u for u in accounts.store.list_users() if u['id']==result['revision']['created_by'] and u.get('active') and u.get('approved')),None)
        if creator:
            try:
                from backend.core.workhub_quality.store import guard_native
                with hub.db() as db:
                    controlled=bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_documents'").fetchone() and db.execute("SELECT 1 FROM qc_documents WHERE project_id=? AND stage='frd'",(project_id,)).fetchone())
                result['frd_job']=jobs.enqueue(creator,project_id,'q_generate' if controlled else 'frd',{'stage':'frd','reason':'Updated approved MOM '+result['revision']['id']} if controlled else {'document_ids':[document_id],'approved_mom_revision':result['revision']['id']})
            except HTTPException:result['notice']='MOM approved. A current project contributor can generate the FRD proposal.'
    return result


@router.post('/documents/{document_id}/apply-plan')
def apply_plan(project_id:str,document_id:str,payload:dict,request:Request):return operations.apply_plan(request.state.user,project_id,document_id,payload)


@router.post('/documents/{document_id}/annotations')
def annotate(project_id:str,document_id:str,payload:dict,request:Request):return operations.annotate(request.state.user,project_id,document_id,payload)


@router.get('/documents/{document_id}/export/{format}')
def export(project_id:str,document_id:str,format:str,request:Request,revision_id:str|None=None,page_id:str|None=None):
    store.initialize()
    with hub.db() as db:
        store.project(db,project_id,request.state.user);doc=store.document(db,document_id,project_id);revision=store.revision(db,revision_id or doc['current_revision'],document_id)
    from backend.core.workhub_quality.store import guard_native
    with hub.db() as db:guard_native(db,document_id)
    if page_id is not None:
        if doc['kind']!='flowchart' or format not in {'svg','pdf'}:raise HTTPException(400,'Page export supports drawing SVG and PDF.')
        from backend.core.workhub_drawing import svg_pages
        content=revision['content']
        pages=svg_pages(content)
        ids=[p['id'] for p in content.get('workspace',{}).get('pages',[{'id':'page-1'}])]
        if page_id!='all':
            if page_id not in ids:raise HTTPException(404,'Drawing page not found in this revision.')
            pages=[pages[ids.index(page_id)]]
        if format=='svg':
            if len(pages)!=1:raise HTTPException(400,'Choose one page for SVG export.')
            data,mime=pages[0][1].encode(),'image/svg+xml'
        else:
            if any('\u0b80'<=c<='\u0bff' for _,source in pages for c in source):raise HTTPException(503,'Tamil drawing PDF needs the configured local font/document renderer. SVG and PNG retain the labels.')
            import io
            from reportlab.pdfgen.canvas import Canvas
            from reportlab.graphics import renderPDF
            from svglib.svglib import svg2rlg
            stream=io.BytesIO();pdf=Canvas(stream);pdf.setTitle(doc['title'])
            for _,source in pages:
                drawing=svg2rlg(io.BytesIO(source.encode()));pdf.setPageSize((drawing.width,drawing.height));renderPDF.draw(drawing,pdf,0,0);pdf.showPage()
            pdf.save();data,mime=stream.getvalue(),'application/pdf'
    else:
        try:data,mime=documents.export_document(doc,revision,format,user=request.state.user)
        except ServiceUnavailable as error:raise HTTPException(503,str(error))
        except ValueError as error:raise HTTPException(400,str(error))
    from backend.core.workhub_document_filename import filename
    name=filename(doc,revision,format)
    return Response(data,media_type=mime,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(name,safe=''),'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.get('/documents/{document_id}/content')
def content(project_id:str,document_id:str,request:Request,revision_id:str|None=None):
    store.initialize()
    with hub.db() as db:
        store.project(db,project_id,request.state.user);doc=store.document(db,document_id,project_id);rev=store.revision(db,revision_id or doc['current_revision'],document_id)
    from backend.core.workhub_quality.store import guard_native
    with hub.db() as db:guard_native(db,document_id)
    from backend.core.workhub_files import file_record
    if not rev['file_id']:raise HTTPException(404,'This generated document has no original file. Use Export.')
    row,path=file_record(rev['file_id'],project_id)
    import mimetypes
    return FileResponse(path,media_type=mimetypes.guess_type(row['name'])[0] or 'application/octet-stream',headers={'Content-Disposition':'inline','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.post('/clarifications')
def clarification(project_id:str,payload:dict,request:Request):
    store.initialize()
    with hub.db(True) as db:
        store.project(db,project_id,request.state.user,write=True)
        store.add_clarification(db,project_id,payload.get('question',''),payload.get('options'),payload.get('source_refs'))
    return {'saved':True}


@router.put('/clarifications/{clarification_id}')
def answer(project_id:str,clarification_id:str,payload:dict,request:Request):return store.answer(request.state.user,project_id,clarification_id,payload)


@router.put('/preferences')
def preferences(project_id:str,payload:dict,request:Request):return operations.preferences(request.state.user,project_id,payload)


@router.post('/documents/{document_id}/office')
def office(project_id:str,document_id:str,request:Request,payload:dict):
    from backend.core.workhub_intelligence.office import editor_config
    try:return editor_config(request.state.user,project_id,document_id,payload)
    except ServiceUnavailable as error:raise HTTPException(503,str(error))


@router.put('/roadmap/{phase}')
def roadmap(project_id:str,phase:str,payload:dict,request:Request):
    store.initialize()
    if phase not in {'development','quality','release'}:raise HTTPException(400,'Choose an existing WorkHub phase.')
    with hub.db(True) as db:
        project=store.project(db,project_id,request.state.user,manage=True)
        row=db.execute('SELECT * FROM project_phases WHERE project_id=? AND phase=?',(project_id,phase)).fetchone()
        if not row or payload.get('version')!=row['version']:raise HTTPException(409,'This roadmap phase changed. Refresh before editing.')
        if project['stage']=='released':raise HTTPException(409,'Reopen the project before changing the roadmap.')
        if 'owner_id' in payload:
            role={'development':'owner_id','quality':'quality_id','release':'release_id'}[phase]
            hub.edit(request.state.user,project_id,{role:payload['owner_id'],'version':project['version']},transaction=db)
        title=text(payload.get('title',row['title']),180,True)
        db.execute('UPDATE project_phases SET title=?,version=version+1 WHERE id=?',(title,row['id']))
        hub.event(db,project,request.state.user,'intelligence_roadmap_updated',{'phase':phase,'title':title})
    return {'saved':True}
