"""Independent document collections, using the existing revisions and approvals."""
import json
from fastapi import HTTPException
from .workhub import store as hub,identity,timestamp,text,encode

def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS wh_document_numbers(document_id TEXT PRIMARY KEY,number TEXT NOT NULL UNIQUE,numbering_snapshot TEXT NOT NULL)')
    db.execute('''CREATE TABLE IF NOT EXISTS wh_document_spaces(
      id TEXT PRIMARY KEY,title TEXT NOT NULL,owner_id INTEGER NOT NULL,reviewer_id INTEGER,
      linked_project_id TEXT,library INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    if 'request_id' not in {r[1] for r in db.execute('PRAGMA table_info(wh_document_spaces)')}:db.execute("ALTER TABLE wh_document_spaces ADD COLUMN request_id TEXT NOT NULL DEFAULT ''")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS document_space_request ON wh_document_spaces(owner_id,request_id) WHERE request_id!=''")
    db.execute('CREATE INDEX IF NOT EXISTS document_space_owner ON wh_document_spaces(owner_id,updated_at)')
    db.execute('CREATE INDEX IF NOT EXISTS document_space_project ON wh_document_spaces(linked_project_id)')

def find(db,key):
    row=db.execute('SELECT * FROM wh_document_spaces WHERE id=?',(key,)).fetchone()
    if not row:return None
    r=dict(row)
    # A scope adapter lets existing document services retain their contracts.
    # No project or task is created and portfolio calculations never count it.
    return {'id':key,'project_id':key,'type':'document_space','title':r['title'],'kind':'Documentation',
      'description':'','created_by':r['owner_id'],'owner_id':r['owner_id'],
      'quality_id':r['reviewer_id'] or r['owner_id'],'approver_id':r['reviewer_id'] or r['owner_id'],
      'release_id':r['reviewer_id'] or r['owner_id'],'stage':'development','due_date':'','start_date':'',
      'baseline_due':'','completed_at':None,'created_at':r['created_at'],'updated_at':r['updated_at'],
      'version':r['version'],'dependencies':'[]','supporting_ids':'[]','project_number':'','milestone':False,
      'is_document_space':True,'library':bool(r['library']),'linked_project_id':r['linked_project_id'],
      'reviewer_id':r['reviewer_id']}

def authorize(db,scope,user,write=False,allow_library=False):
    hub.actor(user)
    member=user['role']=='admin' or user['id'] in {scope['owner_id'],scope['reviewer_id']}
    if not member and (write or not scope['library'] or not allow_library):raise HTTPException(403,'This document is private to its author and reviewer.')
    if scope['linked_project_id']:
        # Sharing a document does not grant access to a linked project.
        if not member:hub.contribute(db,scope['linked_project_id'],user)
    return scope

def create(user,payload):
    from .workhub_quality import store,authoring
    store.initialize();hub.actor(user)
    key=identity();now=timestamp();title=text(payload.get('title') or 'Engineering document',180,True)
    linked=payload.get('linked_project_id') or None
    request_id=text(payload.get('request_id') or '',80)
    with hub.db(True) as db:
        prior=db.execute('SELECT id FROM wh_document_spaces WHERE owner_id=? AND request_id=?',(user['id'],request_id)).fetchone() if request_id else None
        if prior:
            key=prior[0]
        else:
            if linked:hub.contribute(db,linked,user)
            db.execute('INSERT INTO wh_document_spaces(id,title,owner_id,linked_project_id,created_at,updated_at,request_id) VALUES(?,?,?,?,?,?,?)',(key,title,user['id'],linked,now,now,request_id))
        p=find(db,key);state=store.ensure_project(db,p,user)
        if linked:
            source=db.execute('SELECT context FROM qc_projects WHERE project_id=?',(linked,)).fetchone()
            if source:db.execute('UPDATE qc_projects SET context=? WHERE project_id=?',(source[0],key))
        store.audit(db,user,key,'independent_document_created',{'linked_project_id':linked})
    result=authoring.create(user,key,payload)
    return {**result,'scope_id':key,'independent':True}

def details(user,key):
    from .workhub_quality import store
    store.initialize()
    with hub.db() as db:
        p=find(db,key)
        if not p:raise HTTPException(404,'Document workspace not found.')
        authorize(db,p,user)
        native=db.execute('SELECT id FROM pi_documents WHERE project_id=? AND kind=\'mom\' ORDER BY created_at LIMIT 1',(key,)).fetchone()
        return {'project':hub.public(p),'tasks':[],'phases':[],'sprints':[],'files':[dict(r) for r in db.execute('SELECT * FROM files WHERE project_id=? ORDER BY created_at DESC',(key,))],
                'initial_document':'native:'+native[0] if native else 'frd','project_context':store.policy_row(db,p)['context'],'can_manage':user['role']=='admin' or user['id']==p['owner_id']}

def update(user,key,payload):
    from .workhub_quality import store
    store.initialize()
    with hub.db(True) as db:
        p=find(db,key)
        if not p:raise HTTPException(404,'Document workspace not found.')
        authorize(db,p,user,True);hub.manage(p,user)
        if payload.get('version')!=p['version']:raise HTTPException(409,'Document settings changed. Reload before saving.')
        reviewer=payload.get('reviewer_id',p['reviewer_id']) or None
        if reviewer:hub.user_id(reviewer)
        library=payload.get('library',p['library'])
        if type(library) is not bool:raise HTTPException(400,'Choose whether to add the approved document to the library.')
        if library and not db.execute("SELECT 1 FROM pi_documents WHERE project_id=? AND approved_revision IS NOT NULL",(key,)).fetchone():raise HTTPException(409,'Approve a revision before sharing it in the library.')
        db.execute('UPDATE wh_document_spaces SET reviewer_id=?,library=?,version=version+1,updated_at=? WHERE id=?',(reviewer,int(library),timestamp(),key))
        store.audit(db,user,key,'document_access_updated',{'reviewer_id':reviewer,'library':library})
    return details(user,key)
