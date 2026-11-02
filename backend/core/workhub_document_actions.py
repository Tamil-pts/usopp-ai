"""Document deletion deactivates its current record while retaining revision/audit evidence."""
from fastapi import HTTPException
from .workhub import store as hub,timestamp,text
from .workhub_quality import store


def delete(user,key,payload):
    store.initialize()
    with hub.db(True) as db:
        raw=db.execute('''SELECT d.*,r.created_by AS revision_owner,r.status AS native_status,q.id AS control_id,
            c.version AS revision_version,c.status AS controlled_status,c.owner_id AS controlled_owner
            FROM pi_documents d JOIN pi_revisions r ON r.id=d.current_revision
            LEFT JOIN qc_documents q ON q.document_id=d.id LEFT JOIN qc_revisions c ON c.id=r.id WHERE d.id=?''',(key,)).fetchone()
        if not raw:raise HTTPException(404,'Document not found.')
        doc=dict(raw);p=store.project(db,doc['project_id'],user,True)
        if user['role']!='admin' and user['id'] not in {p['owner_id'],p['created_by'],doc['created_by'],doc['controlled_owner'] or doc['revision_owner']}:raise HTTPException(403,'Only the document author, project owner or Admin can delete this document.')
        if p['stage']=='released':raise HTTPException(409,'Reopen the project before deleting one of its documents.')
        if payload.get('revision_id')!=doc['current_revision']:raise HTTPException(409,'The document changed. Reload before deleting it.')
        if doc['control_id'] and payload.get('version')!=doc['revision_version']:raise HTTPException(409,'The document revision changed. Reload before deleting it.')
        reason=text(payload.get('reason',''),2000,True)
        if (doc['controlled_status'] or doc['native_status'])=='archived':return {'deleted':True,'document_id':key,'already_deleted':True}
        now=timestamp()
        # Clear the active approved pointer. Exact historical revisions and their
        # frozen PDFs remain available through authenticated revision history.
        db.execute("UPDATE pi_revisions SET status='archived' WHERE id=?",(doc['current_revision'],))
        db.execute('UPDATE pi_documents SET approved_revision=NULL,updated_at=? WHERE id=?',(now,key))
        if doc['control_id']:db.execute("UPDATE qc_revisions SET status='archived',customer_safe=0,version=version+1 WHERE id=?",(doc['current_revision'],))
        detail={'document_id':key,'revision_id':doc['current_revision'],'title':doc['title'],'previous_status':doc['controlled_status'] or doc['native_status'],'reason':reason}
        store.audit(db,user,p['id'],'document_deleted',detail,doc['control_id'],doc['current_revision'])
        hub.event(db,p,user,'document_deleted',detail)
    return {'deleted':True,'document_id':key,'history_retained':True}
