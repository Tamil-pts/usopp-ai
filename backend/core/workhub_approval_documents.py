"""Revision-specific document attachments for existing workflow decisions."""
import json
from fastapi import HTTPException
from .workhub import store as hub, timestamp, encode
from .workhub_quality import store

APPROVED={'approved','released'}


def editable(db,item,user,review=False):
    project=hub.item(db,item['project_id'])
    if review and item['stage'] in {'quality','release_approval','ready_release'}:
        from .workhub import NEXT_OWNER
        return project['stage']!='released' and item[NEXT_OWNER[item['stage']]]==user['id']
    if project['stage']=='released' or item['stage'] not in {'todo','development','development_completed','blocked'}:return False
    return user['role']=='admin' or user['id'] in {item['created_by'],item['owner_id'],project['created_by'],project['owner_id']}


def document(db,key,revision=None):
    raw=db.execute('''SELECT d.*,q.id AS control_id,q.stage,q.number AS controlled_number,
      s.linked_project_id,s.document_type FROM pi_documents d LEFT JOIN qc_documents q ON q.document_id=d.id
      LEFT JOIN wh_document_spaces s ON s.id=d.project_id WHERE d.id=?''',(key,)).fetchone()
    if not raw:raise HTTPException(404,'An attached document is no longer available.')
    d=dict(raw);rid=revision or d['current_revision']
    raw=db.execute('''SELECT r.id,r.number,r.status,r.content,c.label,c.status AS controlled_status,c.content_hash
      FROM pi_revisions r LEFT JOIN qc_revisions c ON c.id=r.id WHERE r.id=? AND r.document_id=?''',(rid,key)).fetchone()
    if not raw:raise HTTPException(404,'An attached document revision is no longer available.')
    r=dict(raw);kind=d['stage'] or d['kind']
    if kind=='test' and d['document_type']=='test_report':kind='test_report'
    numbered=db.execute('SELECT number FROM wh_document_numbers WHERE document_id=?',(key,)).fetchone()
    return {'document_id':key,'revision_id':rid,'scope_id':d['project_id'],'title':d['title'],'type':kind,
      'number':d['controlled_number'] or (numbered[0] if numbered else 'Native '+key[:8].upper()),
      'revision':r['label'] or 'R'+str(r['number']),'status':r['controlled_status'] or r['status'],
      'current_revision':d['current_revision'],'stale':rid!=d['current_revision'],'content_hash':r['content_hash'] or store.digest(json.loads(r['content'])),
      'control_id':d['control_id'],'linked_project_id':d['linked_project_id'],
      'pdf_url':'/api/workhub/projects/'+d['project_id']+('/quality/documents/'+d['control_id'] if d['control_id'] else '/intelligence/documents/'+key)+'/export/pdf?revision_id='+rid}


def attached(db,item_id):
    rows=[]
    for raw in db.execute('SELECT * FROM wh_workflow_documents WHERE item_id=? ORDER BY attached_at,document_id',(item_id,)):
        saved=json.loads(raw['snapshot'])
        try:current=document(db,raw['document_id'],raw['revision_id'])
        except HTTPException:current={**saved,'status':'unavailable','stale':True}
        rows.append({**current,'attached_by':raw['attached_by'],'attached_at':raw['attached_at']})
    return rows


def overview(user,key,offset=0):
    store.initialize()
    with hub.db() as db:
        item=hub.item(db,key);hub.contribute(db,item['project_id'],user)
        if item['type'] not in {'project','task'}:raise HTTPException(400,'Choose a project or workflow step.')
        # All candidates are project documents or explicitly linked document workspaces.
        keys=[r[0] for r in db.execute('''SELECT d.id FROM pi_documents d LEFT JOIN wh_document_spaces s ON s.id=d.project_id
          WHERE d.project_id=? OR s.linked_project_id=? ORDER BY d.updated_at DESC,d.id''',(item['project_id'],item['project_id']))]
        visible=[]
        for doc_id in keys:
            d=document(db,doc_id)
            if d['scope_id']!=item['project_id']:
                from .workhub_document_spaces import authorize
                try:authorize(db,hub.item(db,d['scope_id']),user)
                except HTTPException:continue
            visible.append(d)
        related=[]
        if item['type']=='project':
            for task in db.execute("SELECT id,title,work_phase FROM items WHERE project_id=? AND type='task' ORDER BY created_at",(key,)):
                related.extend({**d,'item_id':task['id'],'step_title':task['title'],'work_phase':task['work_phase']} for d in attached(db,task['id']))
        from .workhub_signoff import history
        return {'item':hub.public(item),'selected':attached(db,key),'related':related,'items':visible[offset:offset+50],'sign_offs':history(db,key),
          'total':len(visible),'offset':offset,'limit':50,'can_attach':editable(db,item,user),
          'can_select_review_documents':editable(db,item,user,review=True)}


def attach(db,item,user,selection,review=False):
    if item['type'] not in {'project','task'}:raise HTTPException(400,'Choose a project or workflow step.')
    if not editable(db,item,user,review):raise HTTPException(403,'Choose documents during development or as the currently assigned reviewer.')
    if not isinstance(selection,list) or len(selection)>200:raise HTTPException(400,'Attach up to 200 document revisions to a workflow step.')
    chosen=[];seen=set()
    for ref in selection:
        if not isinstance(ref,dict) or not isinstance(ref.get('document_id'),str) or not isinstance(ref.get('revision_id'),str):raise HTTPException(400,'Choose a document and its exact revision.')
        d=document(db,ref['document_id'],ref['revision_id'])
        if d['document_id'] in seen:raise HTTPException(400,'Select each document once per workflow step.')
        if item['project_id'] not in {d['scope_id'],d['linked_project_id']}:raise HTTPException(400,'Only documents belonging or linked to this project can be attached.')
        if d['scope_id']!=item['project_id']:
            from .workhub_document_spaces import authorize
            # Attaching a private workspace shares it with this project's team;
            # only its author, reviewer or Admin may grant that access.
            shared=db.execute('SELECT 1 FROM wh_workflow_documents WHERE project_id=? AND document_id=? LIMIT 1',(item['project_id'],d['document_id'])).fetchone()
            authorize(db,hub.item(db,d['scope_id']),user,write=not bool(shared))
        if d['stale']:raise HTTPException(409,'A selected document has a newer revision. Reload and select its current revision.')
        if d['status'] in {'archived','superseded','rejected'}:raise HTTPException(409,'Choose an active document revision for workflow review.')
        chosen.append(d);seen.add(d['document_id'])
    if review and item['stage'] in {'quality','release_approval','ready_release'}:
        required={(d['document_id'],d['revision_id']) for d in attached(db,item['id'])}
        if not required.issubset({(d['document_id'],d['revision_id']) for d in chosen}):raise HTTPException(409,'Keep the submitted evidence during review. Request changes to remove or replace a submitted revision.')
    db.execute('DELETE FROM wh_workflow_documents WHERE item_id=?',(item['id'],))
    now=timestamp()
    db.executemany('INSERT INTO wh_workflow_documents VALUES(?,?,?,?,?,?,?)',[(item['project_id'],item['id'],d['document_id'],d['revision_id'],encode(d),user['id'],now) for d in chosen])
    hub.event(db,item,user,'workflow_documents_attached',{'documents':chosen})
    return chosen


def save(user,key,payload):
    store.initialize()
    with hub.db(True) as db:
        item=hub.item(db,key);hub.contribute(db,item['project_id'],user)
        if type(payload.get('version')) is not int or payload['version']!=item['version']:raise HTTPException(409,'This workflow step changed. Reload before attaching documents.')
        attach(db,item,user,payload.get('documents'),review=payload.get('review_selection') is True)
        db.execute('UPDATE items SET version=version+1,updated_at=? WHERE id=?',(timestamp(),key))
    return overview(user,key)


def guard(db,item,action,exclude_document=None):
    if action not in {'quality_pass','approve_release','release'}:return []
    if item['type']=='project':
        keys=[r[0] for r in db.execute('''SELECT DISTINCT a.item_id FROM wh_workflow_documents a JOIN items i ON i.id=a.item_id
          WHERE a.project_id=? AND (?='release' OR i.type='project' OR i.work_phase!='release')''',(item['id'],action))]
    else:keys=[item['id']]
    failures=[];checked=[]
    for key in keys:
        for d in attached(db,key):
            if d['document_id']==exclude_document:continue
            checked.append({**d,'item_id':key})
            if d['stale'] or d['status'] not in APPROVED:failures.append(d['number']+' / '+d['revision']+(': newer revision requires review' if d['stale'] else ': '+d['status'].replace('_',' ')))
    if failures:raise HTTPException(409,'Approve the attached workflow documents before this decision: '+'; '.join(failures[:8]))
    return checked
