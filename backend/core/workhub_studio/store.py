"""Additive Studio metadata. Native revisions and approvals remain authoritative."""
import json,threading
from fastapi import HTTPException
from backend.core.workhub import store as hub,identity,timestamp,text
from backend.core.workhub_quality import store as quality
from backend.core.workhub_intelligence import store as pi
from . import bindings,schema

LOCK=threading.RLock();READY=set()
APPROVED={'approved','released','superseded','archived'}

def initialize():
    quality.initialize();key=str(hub.root.resolve())
    if key in READY:return
    with LOCK:
        if key in READY:return
        with hub.db(True) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS ds_locks(revision_id TEXT NOT NULL,element_id TEXT NOT NULL,kind TEXT NOT NULL,locked_by INTEGER NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(revision_id,element_id,kind));
            CREATE TABLE IF NOT EXISTS ds_comments(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,revision_id TEXT NOT NULL,block_id TEXT NOT NULL,cell_id TEXT NOT NULL,start_offset INTEGER NOT NULL,end_offset INTEGER NOT NULL,quote TEXT NOT NULL,source_hash TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,assignee_id INTEGER,due_date TEXT NOT NULL,status TEXT NOT NULL,version INTEGER NOT NULL,author_id INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,resolved_by INTEGER,resolved_at TEXT);
            CREATE INDEX IF NOT EXISTS ds_comment_document ON ds_comments(document_id,status,created_at);
            CREATE TABLE IF NOT EXISTS ds_comment_events(id TEXT PRIMARY KEY,comment_id TEXT NOT NULL,actor_id INTEGER NOT NULL,action TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ds_templates(id TEXT NOT NULL,version INTEGER NOT NULL,name TEXT NOT NULL,kind TEXT NOT NULL,layout TEXT NOT NULL,owner_id INTEGER NOT NULL,shared INTEGER NOT NULL,locked INTEGER NOT NULL,active INTEGER NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(id,version));
            CREATE TABLE IF NOT EXISTS ds_library(id TEXT PRIMARY KEY,title TEXT NOT NULL,kind TEXT NOT NULL,project_id TEXT NOT NULL,document_id TEXT NOT NULL,revision_id TEXT NOT NULL,source_hash TEXT NOT NULL,blocks TEXT NOT NULL,owner_id INTEGER NOT NULL,shared INTEGER NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ds_export_context(revision_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_hash TEXT NOT NULL,context TEXT NOT NULL,context_hash TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ds_exports(revision_id TEXT NOT NULL,format TEXT NOT NULL,data BLOB NOT NULL,sha256 TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(revision_id,format));
            CREATE TABLE IF NOT EXISTS ds_audit(id TEXT PRIMARY KEY,project_id TEXT,document_id TEXT,revision_id TEXT,actor_id INTEGER NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ds_reserved_ids(document_id TEXT NOT NULL,binding TEXT NOT NULL,item_id TEXT NOT NULL,PRIMARY KEY(document_id,binding,item_id));
            CREATE TABLE IF NOT EXISTS ds_links(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,revision_id TEXT NOT NULL,block_id TEXT NOT NULL,requirement_id TEXT NOT NULL,source_document_id TEXT NOT NULL,source_revision_id TEXT NOT NULL,source_hash TEXT NOT NULL,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(revision_id,block_id,requirement_id,source_document_id));
            ''')
        READY.add(key)

def exists(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='ds_locks'").fetchone())

def reserved_ids(db,did,binding):
    result={str(row['id']) for r in db.execute('SELECT content FROM pi_revisions WHERE document_id=?',(did,)) for row in (json.loads(r['content']).get(binding) or []) if isinstance(row,dict) and row.get('id')}
    result.update(r['item_id'] for r in db.execute('SELECT item_id FROM ds_reserved_ids WHERE document_id=? AND binding=?',(did,binding)))
    return result

def reserve_ids(db,did,*contents):
    for content in contents:
        db.executemany('INSERT OR IGNORE INTO ds_reserved_ids VALUES(?,?,?)',[(did,binding,str(row['id'])) for binding in bindings.TABLES for row in (content.get(binding) or []) if isinstance(row,dict) and row.get('id')])
def audit(db,user,pid,did,rid,action,detail=None):
    db.execute('INSERT INTO ds_audit VALUES(?,?,?,?,?,?,?,?)',(identity(),pid,did,rid,user['id'],action,quality.bounded(detail or {}),timestamp()))

def document(db,user,pid,did,rid=None,write=False):
    p=pi.project(db,pid,user,write=write);doc=pi.document(db,did,pid);native=pi.revision(db,rid or doc['current_revision'],did)
    raw=db.execute('SELECT * FROM qc_documents WHERE document_id=?',(did,)).fetchone()
    control=dict(raw) if raw else None
    revision=quality.detail(db,control,quality.revision(db,control['id'],native['id'])) if control else native
    return p,doc,revision,control

def editable(db,user,pid,did,rid=None,version=None):
    p,doc,rev,control=document(db,user,pid,did,rid,True)
    if p['stage']=='released' or doc['current_revision']!=rev['id']:raise HTTPException(409,'Edit the current draft; prepare a new revision for approved content.')
    if control:quality.editable(db,control,rev,user,version if version is not None else rev['version'])
    elif rev['status'] not in {'draft','changes_requested'}:raise HTTPException(409,'This native revision is protected by its existing review workflow. Prepare a new revision to edit it.')
    return p,doc,rev,control

def locks(db,rid):return [dict(r) for r in db.execute('SELECT * FROM ds_locks WHERE revision_id=?',(rid,))] if exists(db) else []

def _layout(content):return content.get('studio') or {}
def _element(content,element):
    value=_layout(content)
    if element=='document':return value
    if element in {'header','footer','page','template_id'}:return value.get(element)
    return next((b for b in value.get('blocks',[]) if b['id']==element),None)


def _content_shape(value):
    if isinstance(value,list):return [_content_shape(v) for v in value]
    if not isinstance(value,dict):return value
    omitted={'style','color','source_hash','widths','header_background','border_color','border_width','line_color','line_width','background','x','y','width','height','row','col','rowspan','colspan','rows','columns','header_rows','font_size','font','bold','italic','underline','color','align','padding','keep_together','space_before','space_after','line_height','inherit_font','inherit_color','highlight'}
    return {k:_content_shape(v) for k,v in value.items() if k not in omitted}


def _layout_shape(value):
    if isinstance(value,list):return [_layout_shape(v) for v in value]
    if not isinstance(value,dict):return value
    omitted={'text','field','label','title','caption','alt','name','role','date','file_id','source_ids','source_hash','binding','checked','values','labels'}
    result={k:_layout_shape(v) for k,v in value.items() if k not in omitted and k!='runs'}
    if 'runs' in value:
        # Text edits may split a run without changing its formatting.
        result['run_formats']=sorted({json.dumps({k:v for k,v in r.items() if k not in {'text','field'}},sort_keys=True) for r in value['runs']})
    return result

def guard(db,user,revision_id,old,new):
    """All save APIs enforce the same locks, including the legacy forms."""
    for lock in locks(db,revision_id):
        element=lock['element_id'];a=_element(old,element);b=_element(new,element)
        if element=='document' and lock['kind']=='content':
            before={k:v for k,v in old.items() if k!='studio'};after={k:v for k,v in new.items() if k!='studio'}
            if before!=after:raise HTTPException(423,'Document content is locked. An authorized user must unlock it before editing.')
            a=_content_shape({**{k:(a or {}).get(k) for k in ('header','footer')},'blocks':[{'id':v['id'],'data':v['data'],'type':v['type']} for v in (a or {}).get('blocks',[])]});b=_content_shape({**{k:(b or {}).get(k) for k in ('header','footer')},'blocks':[{'id':v['id'],'data':v['data'],'type':v['type']} for v in (b or {}).get('blocks',[])]})
        elif lock['kind']=='content' and isinstance(a,dict) and 'data' in a:
            if a.get('type')=='native_text':
                binding=a['data']['binding']
                if bindings.text_value(old,binding)!=bindings.text_value(new,binding):raise HTTPException(423,'This native document field is content locked.')
            elif a.get('type')=='native_table' and old.get(a['data']['binding'])!=new.get(a['data']['binding']):raise HTTPException(423,'This native document table is content locked.')
            a=_content_shape({'data':a.get('data'),'type':a.get('type')});b=_content_shape({'data':b.get('data'),'type':b.get('type')}) if b else None
        elif lock['kind']=='layout':
            if element not in {'document','header','footer','page','template_id'}:
                old_order=[v['id'] for v in _layout(old).get('blocks',[])];new_order=[v['id'] for v in _layout(new).get('blocks',[])]
                if element not in new_order or old_order.index(element)!=new_order.index(element):raise HTTPException(423,'This element position is layout locked.')
            a=_layout_shape(a);b=_layout_shape(b)
        elif lock['kind']=='template':a=_layout(old).get('template_id');b=_layout(new).get('template_id')
        if a!=b:raise HTTPException(423,'The '+lock['kind']+' of '+element+' is locked. Unlock it before editing; lock changes are audited.')

def inherit(db,parent,revision):
    if not parent or not exists(db):return
    db.execute('INSERT OR IGNORE INTO ds_locks SELECT ?,element_id,kind,locked_by,reason,created_at FROM ds_locks WHERE revision_id=?',(revision,parent))
    db.execute('INSERT OR IGNORE INTO ds_links SELECT lower(hex(randomblob(16))),document_id,?,block_id,requirement_id,source_document_id,source_revision_id,source_hash,created_by,created_at FROM ds_links WHERE revision_id=?',(revision,parent))

def validate_media(db,pid,content):
    studio=content.get('studio')
    if not studio:return
    ids=set()
    for b in studio['blocks']:
        if b['type'] in {'image','signature','approval'} and b['data'].get('file_id'):ids.add(b['data']['file_id'])
        if b['type']=='section_break':
            for part in ('header','footer'):
                for variant in b['data'][part]['variants'].values():ids.update(v['file_id'] for v in variant['items'] if v['type']=='logo' and v.get('source')=='file' and v.get('file_id'))
    for part in ('header','footer'):
        for variant in studio[part]['variants'].values():ids.update(v['file_id'] for v in variant['items'] if v['type']=='logo' and v.get('source')=='file' and v.get('file_id'))
    from backend.core.workhub_files import file_record
    from PIL import Image
    for key in ids:
        row,path=file_record(key,pid)
        if row['size']>10*1024*1024:raise HTTPException(413,'Use document images up to 10 MiB. The original file remains available.')
        try:
            with Image.open(path) as im:
                if im.format not in {'PNG','JPEG','WEBP'} or im.width*im.height>24000000:raise ValueError()
                im.verify()
        except Exception:raise HTTPException(400,'Insert a valid PNG, JPEG or WebP image.') from None
    content['file_ids']=list(dict.fromkeys([*content.get('file_ids',[]),*sorted(ids)]))
