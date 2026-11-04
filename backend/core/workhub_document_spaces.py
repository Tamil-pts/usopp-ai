"""Independent document collections, using the existing revisions and approvals."""
import json
from fastapi import HTTPException
from .workhub import store as hub,identity,timestamp,text,encode

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS wh_workflow_documents(
      project_id TEXT NOT NULL,item_id TEXT NOT NULL,document_id TEXT NOT NULL,revision_id TEXT NOT NULL,
      snapshot TEXT NOT NULL,attached_by INTEGER NOT NULL,attached_at TEXT NOT NULL,
      PRIMARY KEY(item_id,document_id))''')
    db.execute('CREATE INDEX IF NOT EXISTS workflow_document_scope ON wh_workflow_documents(project_id,document_id)')
    db.execute('CREATE TABLE IF NOT EXISTS wh_document_numbers(document_id TEXT PRIMARY KEY,number TEXT NOT NULL UNIQUE,numbering_snapshot TEXT NOT NULL)')
    db.execute('''CREATE TABLE IF NOT EXISTS wh_document_spaces(
      id TEXT PRIMARY KEY,title TEXT NOT NULL,owner_id INTEGER NOT NULL,reviewer_id INTEGER,
      linked_project_id TEXT,library INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    if 'request_id' not in {r[1] for r in db.execute('PRAGMA table_info(wh_document_spaces)')}:db.execute("ALTER TABLE wh_document_spaces ADD COLUMN request_id TEXT NOT NULL DEFAULT ''")
    if 'document_type' not in {r[1] for r in db.execute('PRAGMA table_info(wh_document_spaces)')}:
        db.execute("ALTER TABLE wh_document_spaces ADD COLUMN document_type TEXT NOT NULL DEFAULT ''")
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if {'qc_documents','pi_documents'}<=tables:
            db.execute("UPDATE wh_document_spaces SET document_type=COALESCE((SELECT stage FROM qc_documents WHERE project_id=wh_document_spaces.id ORDER BY created_at LIMIT 1),(SELECT kind FROM pi_documents WHERE project_id=wh_document_spaces.id ORDER BY created_at LIMIT 1),'')")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS document_space_request ON wh_document_spaces(owner_id,request_id) WHERE request_id!=''")
    db.execute('CREATE INDEX IF NOT EXISTS document_space_owner ON wh_document_spaces(owner_id,updated_at)')
    db.execute('CREATE INDEX IF NOT EXISTS document_space_project ON wh_document_spaces(linked_project_id)')
    for column in ('linked_document_id','linked_revision_id'):
        if column not in {r[1] for r in db.execute('PRAGMA table_info(wh_document_spaces)')}:
            db.execute('ALTER TABLE wh_document_spaces ADD COLUMN '+column+' TEXT')

def find(db,key):
    row=db.execute('SELECT * FROM wh_document_spaces WHERE id=?',(key,)).fetchone()
    if not row:return None
    r=dict(row)
    linked=db.execute('SELECT title,project_number FROM items WHERE id=?',(r['linked_project_id'],)).fetchone() if r['linked_project_id'] else None
    # A scope adapter lets existing document services retain their contracts.
    # No project or task is created and portfolio calculations never count it.
    return {'id':key,'project_id':key,'type':'document_space','title':r['title'],'kind':'Documentation',
      'description':'','created_by':r['owner_id'],'owner_id':r['owner_id'],
      'quality_id':r['reviewer_id'] or r['owner_id'],'approver_id':r['reviewer_id'] or r['owner_id'],
      'release_id':r['reviewer_id'] or r['owner_id'],'stage':'development','due_date':'','start_date':'',
      'baseline_due':'','completed_at':None,'created_at':r['created_at'],'updated_at':r['updated_at'],
      'version':r['version'],'dependencies':'[]','supporting_ids':'[]','project_number':'','milestone':False,
      'is_document_space':True,'library':bool(r['library']),'linked_project_id':r['linked_project_id'],
      'reviewer_id':r['reviewer_id'],'document_type':r['document_type'],
      'linked_document_id':r['linked_document_id'],'linked_revision_id':r['linked_revision_id'],
      'linked_project_name':linked['title'] if linked else '', 'linked_project_number':linked['project_number'] if linked else ''}

def authorize(db,scope,user,write=False,allow_library=False):
    hub.actor(user)
    member=user['role']=='admin' or user['id'] in {scope['owner_id'],scope['reviewer_id']}
    if not member and not write and scope['linked_project_id']:
        shared=db.execute('''SELECT 1 FROM wh_workflow_documents a JOIN pi_documents d ON d.id=a.document_id
          WHERE a.project_id=? AND d.project_id=? LIMIT 1''',(scope['linked_project_id'],scope['id'])).fetchone()
        if shared:
            hub.contribute(db,scope['linked_project_id'],user)
            return scope
    if not member and (write or not scope['library'] or not allow_library):raise HTTPException(403,'This document is private to its author and reviewer.')
    if scope['linked_project_id']:
        # Sharing a document does not grant access to a linked project.
        if not member:hub.contribute(db,scope['linked_project_id'],user)
    return scope

def create(user,payload):
    from .workhub_quality import store,authoring
    store.initialize();hub.actor(user)
    key=identity();now=timestamp();title=text(payload.get('title') or 'Engineering document',180,True)
    document_type=payload.get('document_type') or payload.get('stage')
    expected_stage='test' if document_type=='test_report' else document_type
    if expected_stage not in {'mom','flowchart','mindmap',*store.STAGES} or payload.get('stage')!=expected_stage:
        raise HTTPException(400,'Choose a supported document type and its structured template.')
    linked=payload.get('linked_project_id') or None
    request_id=text(payload.get('request_id') or '',80)
    with hub.db(True) as db:
        prior=db.execute('SELECT id FROM wh_document_spaces WHERE owner_id=? AND request_id=?',(user['id'],request_id)).fetchone() if request_id else None
        if prior:
            key=prior[0]
            prior_space=find(db,key)
            if prior_space['document_type']!=document_type or prior_space['linked_project_id']!=linked:
                raise HTTPException(409,'This creation request already belongs to a different document. Open that document or start a new request.')
        else:
            if linked:hub.contribute(db,linked,user)
            db.execute('INSERT INTO wh_document_spaces(id,title,owner_id,linked_project_id,created_at,updated_at,request_id,document_type) VALUES(?,?,?,?,?,?,?,?)',(key,title,user['id'],linked,now,now,request_id,document_type))
            if payload.get('linked_document_id'):
                linked_doc,linked_rev=frd_link(db,payload['linked_document_id'],user)
                db.execute('UPDATE wh_document_spaces SET linked_document_id=?,linked_revision_id=? WHERE id=?',(linked_doc['id'],linked_rev['id'],key))
        p=find(db,key);state=store.ensure_project(db,p,user)
        if linked:
            source=db.execute('SELECT context FROM qc_projects WHERE project_id=?',(linked,)).fetchone()
            if source:db.execute('UPDATE qc_projects SET context=? WHERE project_id=?',(source[0],key))
        store.audit(db,user,key,'independent_document_created',{'linked_project_id':linked})
        if document_type in {'flowchart','mindmap'}:
            from .workhub_diagrams import create
            return create(db,user,p,document_type,payload.get('diagram_template'))
    result=authoring.create(user,key,payload)
    if not result.get('existing'):
        with hub.db(True) as db:
            document_id=result.get('document_id')
            if result.get('control_id'):
                controlled=db.execute('SELECT document_id FROM qc_documents WHERE id=?',(result['control_id'],)).fetchone()
                document_id=controlled[0]
            if document_id:db.execute('UPDATE pi_documents SET title=? WHERE id=?',(title,document_id))
    return {**result,'scope_id':key,'independent':True}

def details(user,key):
    from .workhub_quality import store
    store.initialize()
    with hub.db() as db:
        p=find(db,key)
        if not p:raise HTTPException(404,'Document workspace not found.')
        authorize(db,p,user)
        stage='test' if p['document_type']=='test_report' else p['document_type']
        kind='flowchart' if stage=='mindmap' else stage
        document=db.execute('''SELECT d.id,d.kind,q.stage,COALESCE(q.number,n.number) AS number
            FROM pi_documents d LEFT JOIN qc_documents q ON q.document_id=d.id
            LEFT JOIN wh_document_numbers n ON n.document_id=d.id
            WHERE d.project_id=? AND (q.stage=? OR d.kind=?) ORDER BY d.created_at LIMIT 1''',(key,stage,kind)).fetchone()
        initial='native:'+document['id'] if document and document['kind'] in {'mom','flowchart'} else document['stage'] if document and document['stage'] else 'frd'
        return {'project':hub.public(p),'tasks':[],'phases':[],'sprints':[],'files':[dict(r) for r in db.execute('SELECT * FROM files WHERE project_id=? ORDER BY created_at DESC',(key,))],
                'initial_document':initial,'document_number':document['number'] if document else None,'project_context':store.policy_row(db,p)['context'],'can_manage':user['role']=='admin' or user['id']==p['owner_id']}

def update(user,key,payload):
    from .workhub_quality import store
    store.initialize()
    with hub.db(True) as db:
        p=find(db,key)
        if not p:raise HTTPException(404,'Document workspace not found.')
        authorize(db,p,user,True);hub.manage(p,user)
        if payload.get('version')!=p['version']:raise HTTPException(409,'Document settings changed. Reload before saving.')
        reviewer=payload.get('reviewer_id',p['reviewer_id']) or None
        if reviewer!=p['reviewer_id'] and db.execute("SELECT 1 FROM pi_documents d JOIN pi_revisions r ON r.id=d.current_revision WHERE d.project_id=? AND r.status IN ('review','in_review')",(key,)).fetchone():raise HTTPException(409,'Finish the pending review before changing its reviewer.')
        if reviewer:
            hub.user_id(reviewer)
            if reviewer==p['owner_id']:raise HTTPException(400,'Choose a reviewer other than the document author.')
        linked=payload.get('linked_project_id',p['linked_project_id']) or None
        linked_document=payload.get('linked_document_id',p.get('linked_document_id')) or None
        link_changed=linked!=p['linked_project_id'] or linked_document!=p.get('linked_document_id')
        if link_changed:
            state=db.execute('SELECT r.status FROM pi_documents d JOIN pi_revisions r ON r.id=d.current_revision WHERE d.project_id=?',(key,)).fetchone()
            if state and state[0] not in {'draft','changes_requested','correction_required'}:raise HTTPException(409,'Create an editable revision before changing document links.')
            if linked:hub.contribute(db,linked,user)
            doc,rev=frd_link(db,linked_document,user) if linked_document else (None,None)
            if doc and doc['project_id']==key:raise HTTPException(400,'A document cannot link to itself.')
            db.execute('UPDATE wh_document_spaces SET linked_project_id=?,linked_document_id=?,linked_revision_id=? WHERE id=?',(linked,linked_document,rev['id'] if rev else None,key))
            from .workhub_document_information import snapshot
            from .workhub_diagrams import fill_information
            changed_scope=find(db,key)
            fill_information(db,user,changed_scope,snapshot(db,changed_scope) if payload.get('autofill') is True else None)
        library=payload.get('library',p['library'])
        if type(library) is not bool:raise HTTPException(400,'Choose whether to add the approved document to the library.')
        if library and not db.execute("SELECT 1 FROM pi_documents WHERE project_id=? AND approved_revision IS NOT NULL",(key,)).fetchone():raise HTTPException(409,'Approve a revision before sharing it in the library.')
        db.execute('UPDATE wh_document_spaces SET reviewer_id=?,library=?,version=version+1,updated_at=? WHERE id=?',(reviewer,int(library),timestamp(),key))
        store.audit(db,user,key,'document_access_updated',{'reviewer_id':reviewer,'library':library})
    return details(user,key)


def frd_link(db,key,user):
    from .workhub_intelligence import store as pi
    row=db.execute("SELECT * FROM pi_documents WHERE id=? AND kind='frd'",(key,)).fetchone()
    if not row:raise HTTPException(404,'Choose an accessible FRD document.')
    doc=dict(row);hub.contribute(db,doc['project_id'],user)
    return doc,pi.revision(db,doc['current_revision'],doc['id'])
