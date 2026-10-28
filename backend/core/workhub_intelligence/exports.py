"""Queued exports alongside compatible existing direct-download APIs."""
from . import store,documents,reliability
from .cache import compute,_file_hash
from backend.core.workhub import store as hub,timestamp
from backend.core.workhub_files import file_record
from fastapi import HTTPException


def source(db,pid,kind,payload,user):
    p=store.project(db,pid,user)
    # Enqueue holds the existing write transaction. Freeze legacy approvals before
    # computing their job fingerprint, including any original approved PDF bytes.
    if db.in_transaction:
        if kind=='q_export':
            from backend.core.workhub_quality import store as qc
            doc=qc.control(db,pid,payload.get('control_id'))
            rev=qc.revision(db,doc['id'],payload.get('revision_id') or qc.native(db,doc)['current_revision'])
        else:
            doc=store.document(db,payload.get('document_id'),pid)
            from backend.core.workhub_quality.store import guard_native
            guard_native(db,doc['id'])
            rev=store.revision(db,payload.get('revision_id') or doc['current_revision'],doc['id'])
        from backend.core.workhub_quality.pdf_templates import freeze,APPROVED
        if rev['status'] in APPROVED:freeze(db,p,doc,{**rev,'_legacy_capture':True},user,controlled=kind=='q_export')
    return _source(db,pid,kind,payload)


def _source(db,pid,kind,payload):
    """Internal snapshot helper; entrypoints authorize the project before calling."""
    if kind=='q_export':
        from backend.core.workhub_quality import store as qc,packages
        doc=qc.control(db,pid,payload.get('control_id'))
        rev=qc.revision(db,doc['id'],payload.get('revision_id') or qc.native(db,doc)['current_revision'])
        p=hub.item(db,pid)
        from backend.core.workhub_quality.pdf_templates import signature as pdf_signature
        signature={'pdf_layout':pdf_signature(db,p,doc,rev),'control_id':doc['id'],'revision_id':rev['id'],'version':rev['version'],'hash':rev['content_hash'],
                   'status':rev['status'],'baseline':packages.export_signature(db,p)}
        return doc,rev,signature
    doc=store.document(db,payload.get('document_id'),pid)
    from backend.core.workhub_quality.store import guard_native
    guard_native(db,doc['id'])
    rev=store.revision(db,payload.get('revision_id') or doc['current_revision'],doc['id'])
    from backend.core.workhub_quality.pdf_templates import signature as pdf_signature
    return doc,rev,{'pdf_layout':pdf_signature(db,hub.item(db,pid),doc,rev,False),'document_id':doc['id'],'title':doc['title'],'revision_id':rev['id'],'status':rev['status'],'hash':reliability.digest(rev['content'])}


def process(job,user):
    pid=job.row['project_id'];payload=job.row['payload'];kind=job.row['kind'];format=payload.get('format','pdf')
    if format not in {'pdf','docx','json','svg'}:raise ValueError('Choose a supported document export format.')
    with hub.db() as db:doc,rev,signature=source(db,pid,kind,payload,user)
    cache_key=reliability.digest({'processor':'export-v2','source':signature,'format':format})
    def render():
        job.progress(25,'Preparing the selected document revision')
        if kind=='q_export':
            from backend.core.workhub_quality.packages import export_document
            data,mime,name=export_document(user,pid,doc['id'],rev['id'],format,record_download=False)
        else:
            data,mime=documents.export_document(doc,rev,format,user=user);name=doc['kind']+'-r'+str(rev['number'])+'.'+format
        job.check()
        with hub.db() as db:
            if source(db,pid,kind,payload,user)[2]!=signature:raise reliability.SourceChanged('The document changed during export. Prepare the current revision again.')
        file=documents.generated_file(user,pid,'export-'+name,data,read_access=True)
        return {'file_id':file['id'],'sha256':file['sha256'],'filename':name,'media_type':mime}
    value,_=compute(pid,cache_key,'export-v1',render,job.check)
    file,path=file_record(value['file_id'],pid)
    if _file_hash(path)!=value['sha256']:raise ValueError('Export integrity verification failed. The source revision remains available.')
    job.progress(95,'Export verified and stored')
    return {**value,'document_id':doc.get('document_id',doc['id']),'revision_id':rev['id'],
            'download_url':'/api/workhub/projects/'+pid+'/intelligence/jobs/'+job.row['id']+'/download'}


def download(user,pid,key):
    from . import jobs
    value=jobs.get_job(user,pid,key)
    if value['kind'] not in {'export','q_export'} or value['status']!='completed':raise HTTPException(409,'This export is not complete.')
    with hub.db(True) as db:
        row=db.execute('SELECT payload FROM pi_jobs WHERE id=? AND project_id=?',(key,pid)).fetchone()
        import json
        payload=json.loads(row['payload'])
        source(db,pid,value['kind'],payload,user)  # Recheck current permissions.
        if value['kind']=='q_export':
            from backend.core.workhub_quality import store as qc
            qc.audit(db,user,pid,'document_downloaded',{'job_id':key,'format':payload.get('format','pdf')},payload.get('control_id'),value['result'].get('revision_id'))
    result=value['result'];file,path=file_record(result['file_id'],pid)
    if _file_hash(path)!=result['sha256']:raise HTTPException(409,'Export integrity verification failed.')
    return result,path
