"""Native document facade for the page editor and its permission-aware tools."""
from copy import deepcopy
import json
from fastapi import HTTPException
from . import store,bindings,schema
from .store import hub,quality,pi,identity,timestamp,text

def fields(db,p,doc,rev,control):
    from backend.core.workhub_quality import branding
    state=quality.policy_row(db,p);header=quality.source_header(db,p,state);org=branding.organization(db,state['context'])
    users={u['id']:u['username'] for u in hub.users()}
    number=control['number'] if control else next((r[0] for r in db.execute('SELECT number FROM wh_document_numbers WHERE document_id=?',(doc['id'],))),doc['id'])
    kind=control['stage'] if control else doc['kind']
    return {'project_name':header['project_name'],'project_number':header.get('project_number') or '',
      'customer':header.get('customer') or '', 'machine':header.get('machine') or '',
      'document_number':number,'document_title':branding.KINDS.get(kind,doc['title']),
      'revision':rev.get('label') or 'Rev '+str(max(0,rev['number']-1)).zfill(2),'status':rev['status'],
      'prepared_by':users.get(rev.get('owner_id',rev.get('created_by')),'Not recorded'),
      'reviewed_by':users.get(rev.get('reviewed_by'),'Pending'), 'approved_by':users.get(rev.get('approved_by',rev.get('reviewed_by') if rev['status'] in store.APPROVED else None),'Pending'),
      'approval_date':rev.get('approved_at',rev.get('reviewed_at')) or '', 'company':org['data']['name'],
      'department':org['data'].get('department',''),'date':rev['created_at'][:10],'page':'{page}','pages':'{pages}','section_title':''}

def can_edit(db,user,p,doc,rev,control):
    try:store.editable(db,user,p['id'],doc['id'],rev['id']);return True
    except HTTPException:return False

def get(user,pid,did,rid=None):
    store.initialize()
    with hub.db() as db:
        p,doc,rev,control=store.document(db,user,pid,did,rid)
        content=deepcopy(rev['content']);kind=control['stage'] if control else doc['kind']
        normalized=bindings.synchronize(content);layout=bindings.layout(normalized,kind);f=fields(db,p,doc,rev,control)
        revisions=[dict(r) for r in db.execute('SELECT id,number,status,created_by,created_at,reviewed_by,reviewed_at FROM pi_revisions WHERE document_id=? ORDER BY number DESC',(did,))]
        files=[dict(r) for r in db.execute('SELECT id,name,size,sha256 FROM files WHERE project_id=? ORDER BY created_at DESC LIMIT 500',(pid,))]
        try:pi.project(db,pid,user,write=True);can_comment=True
        except HTTPException:can_comment=False
        meetings=[{'id':r['id'],'title':r['subject'],'status':r['status']} for r in db.execute('SELECT id,subject,status FROM pi_meetings WHERE project_id=? ORDER BY created_at DESC LIMIT 200',(pid,))]
        reserved={key:sorted(store.reserved_ids(db,did,key)) for key in bindings.TABLES}
        from .quality import inspect
        return {'document':{**doc,'kind':kind,'control_id':control['id'] if control else None,'number':f['document_number']},
          'revision':{**rev,'content':normalized,'etag':bindings.digest(rev['content'])},'layout':layout,'fields':f,
          'editable':can_edit(db,user,p,doc,rev,control),'can_comment':can_comment,'project':hub.public(p),'meetings':meetings,'reserved_ids':reserved,'user_id':user['id'],'is_admin':user['role']=='admin',
          'revisions':revisions,'locks':store.locks(db,rev['id']),'tables':{k:[{'field':a,'label':b} for a,b in v] for k,v in bindings.TABLES.items()},
          'native_tables':{key:bindings.native_table(content,key) for key in bindings.TABLES},'files':files,
          'users':[{'id':u['id'],'username':u['username']} for u in hub.users() if u.get('active',True)],
          'comments':[dict(r) for r in db.execute('SELECT * FROM ds_comments WHERE document_id=? ORDER BY created_at',(did,))],
          'quality':inspect(db,p,doc,rev,control,content),
          'legacy_approved':rev['status'] in store.APPROVED and not content.get('studio')}

def save(user,pid,did,payload):
    store.initialize()
    with hub.db(True) as db:
        p,doc,rev,control=store.editable(db,user,pid,did,payload.get('revision_id'),payload.get('version'))
        if payload.get('etag')!=bindings.digest(rev['content']):raise HTTPException(409,'This document changed. Reload the saved revision before applying your edits.')
        content=deepcopy(payload.get('content'))
        if not isinstance(content,dict):schema.fail('Provide the structured document content.')
        content['studio']=schema.normalize(payload.get('layout',content.get('studio')))
        content=bindings.synchronize(content);store.validate_media(db,pid,content)
        if not control:
            from backend.core.workhub_quality.field_attachments import normalize as normalize_files
            content=normalize_files(db,pid,content,content)
        for row in content.get('cases',[]):row.pop('execution',None)
        store.guard(db,user,rev['id'],pi.revision(db,rev['id'],did)['content'],content)
        store.reserve_ids(db,did,rev['content'],content)
        if control:
            from backend.core.workhub_quality.documents import clean_content,_save
            clean=clean_content(db,pid,control['stage'],content);_save(db,user,p,control,rev,clean,payload.get('version'))
            rid=rev['id']
        else:
            pi.validate_content(doc['kind'],content)
            _,new=pi.create_document(db,user,pid,doc['kind'],doc['title'],content,file_id=rev.get('file_id'),meeting_id=doc.get('meeting_id'),document_id=did,expected_revision=rev['id'])
            rid=new['id']
        store.audit(db,user,pid,did,rid,'studio_saved',{'previous_revision':rev['id'],'content_hash':bindings.digest(content)})
    return get(user,pid,did,rid)

def lock(user,pid,did,payload):
    store.initialize()
    with hub.db(True) as db:
        p,doc,rev,control=store.editable(db,user,pid,did,payload.get('revision_id'),payload.get('version'))
        element=schema.key(payload.get('element_id'));kind=schema.choice(payload.get('kind'),{'content','layout','template'})
        if not rev['content'].get('studio') and (element!='document' or kind!='content'):raise HTTPException(409,'Save the page layout before protecting its elements.')
        layout=bindings.layout(rev['content'],control['stage'] if control else doc['kind'])
        if element not in {'document','header','footer','page','template_id'} and not any(b['id']==element for b in layout['blocks']):raise HTTPException(404,'This document element no longer exists.')
        previous=db.execute('SELECT * FROM ds_locks WHERE revision_id=? AND element_id=? AND kind=?',(rev['id'],element,kind)).fetchone()
        enable=schema.boolean(payload.get('locked'))
        if previous and previous['locked_by']!=user['id'] and user['role']!='admin':raise HTTPException(403,'Only the user who placed this lock or Admin can unlock it.')
        reason=text(payload.get('reason',''),1000,True)
        if enable:db.execute('INSERT OR REPLACE INTO ds_locks VALUES(?,?,?,?,?,?)',(rev['id'],element,kind,user['id'],reason,timestamp()))
        else:db.execute('DELETE FROM ds_locks WHERE revision_id=? AND element_id=? AND kind=?',(rev['id'],element,kind))
        store.audit(db,user,pid,did,rev['id'],'element_locked' if enable else 'element_unlocked',{'element_id':element,'kind':kind,'reason':reason})
    return get(user,pid,did,rev['id'])

def revision(user,pid,did,payload):
    store.initialize()
    with hub.db() as db:
        p,doc,rev,control=store.document(db,user,pid,did,write=True)
        if payload.get('revision_id')!=doc['current_revision']:raise HTTPException(409,'Prepare a revision from the current saved document.')
        reason=text(payload.get('reason',''),2000,True)
    if control:
        from backend.core.workhub_quality.service import new_revision
        result=new_revision(user,pid,control['id'],{'revision_id':rev['id'],'reason':reason});rid=result['revision_id']
    else:
        if rev['status'] not in {'approved','changes_requested'}:raise HTTPException(409,'Finish the current review or edit its draft before preparing another revision.')
        with hub.db(True) as db:
            _,new=pi.create_document(db,user,pid,doc['kind'],doc['title'],rev['content'],file_id=rev.get('file_id'),meeting_id=doc.get('meeting_id'),document_id=did,expected_revision=rev['id'])
            rid=new['id'];store.audit(db,user,pid,did,rid,'studio_revision_prepared',{'reason':reason,'parent_revision':rev['id']})
    return get(user,pid,did,rid)
