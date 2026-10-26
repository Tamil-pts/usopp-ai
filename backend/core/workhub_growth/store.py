"""Additive records and access rules in the existing WorkHub database."""
import json
import math
import threading
from fastapi import HTTPException
from backend.core.workhub import store as hub,identity,timestamp,text,encode,day

LOCK=threading.RLock();READY=set()
CAPABILITIES={'problem_solving':'Problem-solving','work_quality':'Work quality','execution':'Execution','ownership':'Ownership','knowledge_sharing':'Knowledge sharing'}
CATEGORIES={
    'troubleshooting':'Error Resolution & Troubleshooting',
    'project_knowledge':'Project Knowledge Sharing',
    'solutions':'Technical Solutions & Improvements',
    'research':'Research & Learning',
    'best_practices':'Best Practices & Reusable Methods'}
ACTIVITIES=['PLC / automation','Electrical / circuit design','Documentation','Research','Design / CAD','Testing / validation','General engineering']


def initialize():
    key=str(hub.root.resolve())
    if key in READY:return
    with LOCK:
        if key in READY:return
        with hub.db(True) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS pc_events(id TEXT PRIMARY KEY,source_type TEXT NOT NULL,source_id TEXT NOT NULL,
              project_id TEXT,task_id TEXT,actor_id INTEGER,subject_id INTEGER,event_type TEXT NOT NULL,title TEXT NOT NULL,
              occurred_at TEXT NOT NULL,verification TEXT NOT NULL DEFAULT 'recorded',data TEXT NOT NULL,updated_at TEXT NOT NULL,
              UNIQUE(source_type,source_id));
            CREATE INDEX IF NOT EXISTS pc_person_events ON pc_events(subject_id,occurred_at);
            CREATE INDEX IF NOT EXISTS pc_project_events ON pc_events(project_id,occurred_at);
            CREATE TABLE IF NOT EXISTS pc_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pc_manual(id TEXT PRIMARY KEY,author_id INTEGER NOT NULL,project_id TEXT,task_id TEXT,
              current_revision TEXT,approved_revision TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pc_manual_revisions(id TEXT PRIMARY KEY,evidence_id TEXT NOT NULL,number INTEGER NOT NULL,
              content TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',reviewer_id INTEGER,created_at TEXT NOT NULL,
              reviewed_at TEXT,comment TEXT NOT NULL DEFAULT '',reviewed_by INTEGER,verified_capabilities TEXT NOT NULL DEFAULT '[]',
              UNIQUE(evidence_id,number));
            CREATE INDEX IF NOT EXISTS pc_manual_author ON pc_manual(author_id,updated_at);
            CREATE TABLE IF NOT EXISTS cp_articles(id TEXT PRIMARY KEY,author_id INTEGER NOT NULL,project_id TEXT,task_id TEXT,
              current_revision TEXT,approved_revision TEXT,published_revision TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS cp_article_author ON cp_articles(author_id,updated_at);
            CREATE TABLE IF NOT EXISTS cp_revisions(id TEXT PRIMARY KEY,article_id TEXT NOT NULL,number INTEGER NOT NULL,
              title TEXT NOT NULL,category TEXT NOT NULL,keywords TEXT NOT NULL,answers TEXT NOT NULL,body TEXT NOT NULL,
              file_ids TEXT NOT NULL DEFAULT '[]',status TEXT NOT NULL DEFAULT 'draft',reviewer_id INTEGER,created_at TEXT NOT NULL,
              reviewed_at TEXT,reviewed_by INTEGER,review_comment TEXT NOT NULL DEFAULT '',published_at TEXT,published_by INTEGER,
              verified_capabilities TEXT NOT NULL DEFAULT '[]',UNIQUE(article_id,number));
            CREATE INDEX IF NOT EXISTS cp_review_queue ON cp_revisions(status,reviewer_id);
            CREATE TABLE IF NOT EXISTS cp_actions(id TEXT PRIMARY KEY,object_type TEXT NOT NULL,object_id TEXT NOT NULL,
              revision_id TEXT,actor_id INTEGER NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cp_files(id TEXT PRIMARY KEY,object_type TEXT NOT NULL,object_id TEXT NOT NULL,
              uploaded_by INTEGER NOT NULL,name TEXT NOT NULL,sha256 TEXT NOT NULL,size INTEGER NOT NULL,created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS cp_file_object ON cp_files(object_type,object_id);
            CREATE TABLE IF NOT EXISTS cp_notification_targets(notification_id TEXT PRIMARY KEY,object_type TEXT NOT NULL,
              object_id TEXT NOT NULL,revision_id TEXT);
            CREATE TABLE IF NOT EXISTS cp_search(article_id TEXT PRIMARY KEY,revision_id TEXT NOT NULL,title TEXT NOT NULL,
              category TEXT NOT NULL,keywords TEXT NOT NULL,body TEXT NOT NULL);
            ''')
            try:
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS cp_search_fts USING fts5(article_id UNINDEXED,revision_id UNINDEXED,title,keywords,body,tokenize='unicode61')")
                db.execute("INSERT OR REPLACE INTO pc_state VALUES('fts','1')")
            except Exception:db.execute("INSERT OR REPLACE INTO pc_state VALUES('fts','0')")
        READY.add(key)


def personal(user):
    hub.actor(user)
    if not user.get('active',True) or not user.get('approved',True):raise HTTPException(403,'Use an enabled personal account.')


def managed_projects(db,user):
    personal(user)
    query="SELECT id FROM items WHERE type='project'"
    return {r[0] for r in db.execute(query) } if user['role']=='admin' else {r[0] for r in db.execute(query+' AND (created_by=? OR owner_id=?)',(user['id'],user['id']))}


def scope(db,user,person_id):
    personal(user)
    if person_id==user['id'] or user['role']=='admin':return None
    projects=managed_projects(db,user)
    if not projects:raise HTTPException(403,'You can view your own performance. Team profiles require project management responsibility.')
    permitted=db.execute('SELECT 1 FROM items WHERE project_id IN ('+','.join('?' for _ in projects)+') AND ? IN (created_by,owner_id,quality_id,approver_id,release_id) LIMIT 1',(*projects,person_id)).fetchone()
    if not permitted:raise HTTPException(403,'This engineer is outside your managed projects.')
    return projects


def project_link(db,user,project_id=None,task_id=None,contribute=False):
    personal(user)
    if task_id and not project_id:raise HTTPException(400,'Select the project for this task.')
    if not project_id:return None,None
    item=hub.contribute(db,project_id,user) if contribute else hub.item(db,project_id)
    if item['type']!='project':raise HTTPException(400,'Choose a WorkHub project.')
    if task_id:
        task=hub.item(db,task_id)
        if task['type']!='task' or task['project_id']!=project_id:raise HTTPException(400,'Choose a task in the selected project.')
    return project_id,task_id or None


def reviewers(db,project_id=None,author_id=None):
    users=hub.users();allowed={u['id'] for u in users if u['active']}
    from backend.core import accounts
    managers={u['id'] for u in accounts.store.list_users() if u.get('active') and u.get('approved') and not u.get('isDemo') and u['role']=='admin'}
    if project_id:
        project=hub.item(db,project_id)
        managers.update(project[field] for field in ('created_by','owner_id','quality_id','approver_id','release_id'))
    else:
        for row in db.execute("SELECT created_by,owner_id FROM items WHERE type='project'"):managers.update(row)
    return [u for u in users if u['id'] in allowed&managers and u['id']!=author_id]


def review_user(db,project_id,author_id,value):
    value=hub.user_id(value)
    if value not in {u['id'] for u in reviewers(db,project_id,author_id)}:raise HTTPException(403,'Choose an independent project reviewer, project manager or Admin.')
    return value


def capabilities(value):
    if not isinstance(value,list) or any(not isinstance(k,str) or k not in CAPABILITIES for k in value):raise HTTPException(400,'Choose supported engineering capabilities.')
    return list(dict.fromkeys(value))


def bounded(value,limit=512*1024):
    try:raw=json.dumps(value,ensure_ascii=False,allow_nan=False)
    except (ValueError,TypeError):raise HTTPException(400,'Use valid structured content.')
    if len(raw.encode())>limit:raise HTTPException(413,'Split this submission into smaller evidence records.')
    return raw


def object_row(db,kind,key):
    table='cp_articles' if kind=='article' else 'pc_manual' if kind=='evidence' else ''
    if not table or not isinstance(key,str):raise HTTPException(404,'Record not found.')
    row=db.execute('SELECT * FROM '+table+' WHERE id=?',(key,)).fetchone()
    if not row:raise HTTPException(404,'Record not found.')
    return dict(row)


def revision(db,kind,key,object_id):
    table,field=('cp_revisions','article_id') if kind=='article' else ('pc_manual_revisions','evidence_id')
    row=db.execute('SELECT * FROM '+table+' WHERE id=? AND '+field+'=?',(key,object_id)).fetchone()
    if not row:raise HTTPException(404,'Revision not found for this record.')
    value=dict(row)
    for field in ('answers','keywords','file_ids','verified_capabilities','content'):
        if field in value:value[field]=json.loads(value[field])
    return value


def can_read(db,user,kind,row):
    personal(user)
    if user['role']=='admin' or row['author_id']==user['id']:return True
    table,field=('cp_revisions','article_id') if kind=='article' else ('pc_manual_revisions','evidence_id')
    if db.execute('SELECT 1 FROM '+table+' WHERE '+field+'=? AND reviewer_id=? AND status!=?',(row['id'],user['id'],'draft')).fetchone():return True
    if kind=='article' and row.get('published_revision'):return True
    if kind=='evidence' and row['project_id'] in managed_projects(db,user):return True
    return False


def require_read(db,user,kind,row):
    if not can_read(db,user,kind,row):raise HTTPException(403,'This draft or evidence record is private to its author and authorized reviewers.')


def author(user,row):
    personal(user)
    if row['author_id']!=user['id']:raise HTTPException(403,'Only the author can edit and submit a new revision.')


def action(db,user,kind,key,rev,verb,detail=None):
    db.execute('INSERT INTO cp_actions VALUES(?,?,?,?,?,?,?,?)',(identity(),kind,key,rev,user['id'],verb,bounded(detail or {}),timestamp()))


def notify(db,user,row,recipients,title,body):
    before=db.execute('SELECT COALESCE(MAX(rowid),0) FROM notifications').fetchone()[0]
    if row.get('project_id'):
        hub.notify(db,hub.item(db,row['project_id']),user['id'],recipients,title,body)
    else:
        enabled={u['id'] for u in hub.users() if u['active']}
        for recipient in set(recipients)&enabled:
            db.execute('INSERT INTO notifications VALUES(?,?,?,?,?,?,?,?,NULL)',(identity(),recipient,user['id'],'','',title[:240],body[:3000],timestamp()))
    kind='article' if 'published_revision' in row else 'evidence'
    for record in db.execute('SELECT id FROM notifications WHERE rowid>?',(before,)):
        db.execute('INSERT INTO cp_notification_targets VALUES(?,?,?,?)',(record['id'],kind,row['id'],row['current_revision']))


def notification_targets(value):
    with hub.db() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='cp_notification_targets'").fetchone():return value
        for row in value.get('items',[]):
            target=db.execute('SELECT object_type,object_id,revision_id FROM cp_notification_targets WHERE notification_id=?',(row['id'],)).fetchone()
            if target:row['growth_target']=dict(target)
    return value


def owned_files(db,user,kind,object_id,ids):
    if not isinstance(ids,list) or len(ids)>30 or any(not isinstance(key,str) for key in ids):raise HTTPException(400,'Attach up to 30 files.')
    for key in ids:
        if not db.execute('SELECT 1 FROM cp_files WHERE id=? AND object_type=? AND object_id=?',(key,kind,object_id)).fetchone():raise HTTPException(400,'Choose attachments uploaded to this record.')
    return list(dict.fromkeys(ids))


def metadata(user):
    initialize();personal(user)
    from backend.core import accounts
    users=hub.users();admins={u['id'] for u in accounts.store.list_users() if u.get('active') and u.get('approved') and u['role']=='admin' and not u.get('isDemo')}
    with hub.db() as db:
        raw=[dict(r) for r in db.execute("SELECT * FROM items WHERE type='project' ORDER BY title")]
        contributor_ids={}
        for r in db.execute('SELECT project_id,created_by,owner_id,quality_id,approver_id,release_id FROM items'):
            contributor_ids.setdefault(r['project_id'],set()).update(r[k] for k in ('created_by','owner_id','quality_id','approver_id','release_id'))
        projects=[{'id':r['id'],'title':r['title'],'kind':r['kind'],'can_contribute':user['role']=='admin' or user['id'] in contributor_ids.get(r['id'],set())} for r in raw]
        tasks=[{'id':r['id'],'project_id':r['project_id'],'title':r['title']} for r in db.execute("SELECT id,project_id,title FROM items WHERE type='task' ORDER BY title")]
        managed=managed_projects(db,user);reviewer_map={};general=set(admins)
        for r in raw:
            eligible=admins|{r[k] for k in ('created_by','owner_id','quality_id','approver_id','release_id')}
            reviewer_map[r['id']]=[u for u in users if u['active'] and u['id']!=user['id'] and u['id'] in eligible]
            general.update((r['created_by'],r['owner_id']))
        return {'user_id':user['id'],'categories':CATEGORIES,'capabilities':CAPABILITIES,'activities':ACTIVITIES,
                'users':users,'projects':projects,'tasks':tasks,'managed_projects':sorted(managed),'is_manager':user['role']=='admin' or bool(managed),
                'reviewers':reviewer_map,'general_reviewers':[u for u in users if u['active'] and u['id']!=user['id'] and u['id'] in general]}
