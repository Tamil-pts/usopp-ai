"""Persistent private direct messages. Attachments are available to participants only."""
from contextlib import contextmanager
from pathlib import Path
import json
import re
import sqlite3
import threading
import time
import uuid
from fastapi import APIRouter,Request,HTTPException,UploadFile,File,Form,Query,Depends
from fastapi.responses import FileResponse
from backend.core.runtime import BASE
from backend.core import accounts

def actor(request:Request):
    who=getattr(request.state,'user',None)
    if not who:raise HTTPException(401,'Sign in to use team chat.')
    if who.get('isDemo'):raise HTTPException(403,'Team chat requires a personal account.')
    return who

router=APIRouter(prefix='/api/team-chat',tags=['Team chat'],dependencies=[Depends(actor)])
ALLOWED={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp',
         '.zip':'application/zip','.webm':'video/webm','.mp4':'video/mp4','.mp3':'audio/mpeg','.wav':'audio/wav','.pdf':'application/pdf','.csv':'text/csv','.txt':'text/plain','.log':'text/plain',
         '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         '.xls':'application/vnd.ms-excel','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
         '.doc':'application/msword','.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation'}

class ChatStore:
    def __init__(self,root):self.root=Path(root);self.lock=threading.RLock()
    @contextmanager
    def db(self):
        self.root.mkdir(parents=True,exist_ok=True)
        with self.lock:
            db=sqlite3.connect(self.root/'messages.sqlite3',timeout=10);db.row_factory=sqlite3.Row
            try:
                db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA journal_mode=WAL')
                db.executescript('''CREATE TABLE IF NOT EXISTS threads(id TEXT PRIMARY KEY,a INTEGER NOT NULL,b INTEGER NOT NULL,created REAL NOT NULL,a_identity TEXT NOT NULL,b_identity TEXT NOT NULL,UNIQUE(a,b,a_identity,b_identity));
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,thread TEXT NOT NULL REFERENCES threads(id),sender INTEGER NOT NULL,body TEXT NOT NULL,created REAL NOT NULL,client_id TEXT NOT NULL,UNIQUE(sender,client_id));
                CREATE INDEX IF NOT EXISTS message_thread ON messages(thread,id);
                CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY,message INTEGER NOT NULL REFERENCES messages(id),name TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS reads(thread TEXT NOT NULL REFERENCES threads(id),user INTEGER NOT NULL,last_id INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(thread,user));''')
                db.executescript('''CREATE TABLE IF NOT EXISTS chat_groups(thread TEXT PRIMARY KEY REFERENCES threads(id),name TEXT NOT NULL,owner INTEGER NOT NULL,team_id TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS group_members(thread TEXT NOT NULL REFERENCES threads(id),user INTEGER NOT NULL,identity TEXT NOT NULL,PRIMARY KEY(thread,user));
                CREATE TABLE IF NOT EXISTS message_links(message INTEGER PRIMARY KEY REFERENCES messages(id),project TEXT NOT NULL,item TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS meetings(id TEXT PRIMARY KEY,thread TEXT NOT NULL REFERENCES threads(id),host INTEGER NOT NULL,host_identity TEXT NOT NULL,title TEXT NOT NULL,start REAL NOT NULL,end REAL NOT NULL,timezone TEXT NOT NULL,agenda TEXT NOT NULL,status TEXT NOT NULL,project TEXT NOT NULL,item TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS meeting_rsvp(meeting TEXT NOT NULL REFERENCES meetings(id),user INTEGER NOT NULL,identity TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(meeting,user));
                CREATE TABLE IF NOT EXISTS meeting_attendance(meeting TEXT NOT NULL REFERENCES meetings(id),user INTEGER NOT NULL,identity TEXT NOT NULL,joined REAL NOT NULL,PRIMARY KEY(meeting,user));
                CREATE TABLE IF NOT EXISTS meeting_recordings(meeting TEXT NOT NULL REFERENCES meetings(id),attachment TEXT NOT NULL REFERENCES attachments(id),PRIMARY KEY(meeting,attachment));''')
                db.executescript('''CREATE TABLE IF NOT EXISTS chat_components(message INTEGER PRIMARY KEY REFERENCES messages(id),kind TEXT NOT NULL,content TEXT NOT NULL,version INTEGER NOT NULL,updated REAL NOT NULL,editor INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS chat_component_history(message INTEGER NOT NULL REFERENCES messages(id),version INTEGER NOT NULL,editor INTEGER NOT NULL,editor_identity TEXT NOT NULL,editor_name TEXT NOT NULL,content TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(message,version));''')
                db.execute('CREATE INDEX IF NOT EXISTS component_editor_time ON chat_component_history(editor,created)')
                yield db;db.commit()
            except Exception:db.rollback();raise
            finally:db.close()
    def thread(self,db,key,user,sync=True):
        group=db.execute('SELECT * FROM chat_groups WHERE thread=?',(key,)).fetchone()
        if group:
            if sync:sync_groups(db)
            member=db.execute('SELECT * FROM group_members WHERE thread=? AND user=?',(key,user)).fetchone();account=people().get(user)
            if not member or not account or not account['active'] or not account['approved'] or member['identity']!=stamp(account):raise HTTPException(404,'Conversation not found.')
            return db.execute('SELECT * FROM threads WHERE id=?',(key,)).fetchone()
        row=db.execute('SELECT * FROM threads WHERE id=? AND (a=? OR b=?)',(key,user,user)).fetchone()
        account=people().get(user)
        if not row or not account or row['a_identity' if row['a']==user else 'b_identity']!=stamp(account):raise HTTPException(404,'Conversation not found.')
        return row
    def message(self,db,row):
        item=dict(row);link=db.execute('SELECT project,item FROM message_links WHERE message=?',(row['id'],)).fetchone();item['work_link']=dict(link) if link else None;item['attachments']=[dict(a) for a in db.execute('SELECT id,name,mime,size FROM attachments WHERE message=?',(row['id'],))]
        component=db.execute('SELECT * FROM chat_components WHERE message=?',(row['id'],)).fetchone()
        item['component']={**dict(component),'content':json.loads(component['content'])} if component else None
        return item

store=ChatStore(BASE/'.usopp_chat')

def people():
    return {u['id']:{**{k:u[k] for k in ('id','username','designation','active','approved','avatarUrl')},'createdAt':u.get('createdAt',0)} for u in accounts.store.list_users() if not u.get('isDemo')}

def stamp(account):return str(account.get('createdAt',0))

def team_directory():
    from backend.core import workhub_organization as org
    from datetime import datetime
    org.initialize()
    known=people()
    def current(row):
        # A reused numeric account ID must not inherit an old team assignment.
        try:return row['user_id'] in known and datetime.fromisoformat(row['updated_at']).timestamp()>=float(known[row['user_id']]['createdAt'])
        except (TypeError,ValueError):return False
    with org.hub.db() as db:
        return [{'id':r['id'],'name':r['name'],'users':[m['user_id'] for m in db.execute('SELECT m.user_id,p.updated_at FROM wh_org_members m JOIN wh_org_profiles p ON p.user_id=m.user_id WHERE team_id=?',(r['id'],)) if current(m)]} for r in db.execute("SELECT * FROM wh_org_units WHERE kind='team' AND active=1")]

def sync_groups(db):
    known=people();teams=team_directory();active={t['id'] for t in teams}
    for row in db.execute('SELECT thread,team_id FROM chat_groups WHERE team_id IS NOT NULL'):
        if row['team_id'] not in active:db.execute('DELETE FROM group_members WHERE thread=?',(row['thread'],))
    for team in teams:
        group=db.execute('SELECT thread FROM chat_groups WHERE team_id=?',(team['id'],)).fetchone()
        key=group['thread'] if group else uuid.uuid4().hex
        if not group:
            db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',(key,-1,-1,time.time(),key,key))
            db.execute('INSERT INTO chat_groups VALUES(?,?,?,?)',(key,team['name'],0,team['id']))
        db.execute('UPDATE chat_groups SET name=? WHERE thread=?',(team['name'],key))
        db.execute('DELETE FROM group_members WHERE thread=?',(key,))
        for user in team['users']:
            if user in known and known[user]['active'] and known[user]['approved']:db.execute('INSERT INTO group_members VALUES(?,?,?)',(key,user,stamp(known[user])))

def members(db,key):
    known=people()
    return [public_person(known[r['user']]) for r in db.execute('SELECT * FROM group_members WHERE thread=?',(key,)) if r['user'] in known and r['identity']==stamp(known[r['user']]) and known[r['user']]['active'] and known[r['user']]['approved']]

def work_link(user,project,item=''):
    if user.get('role')!='admin' and 'workhub' not in user.get('workspaceModules',[]):raise HTTPException(403,'WorkHub access is required.')
    from backend.core.workhub import store as hub
    with hub.db() as db:
        hub.contribute(db,project,user)
        if item:
            task=hub.item(db,item)
            if task['type']!='task' or task['project_id']!=project:raise HTTPException(400,'Choose a task inside this project.')

@router.post('/groups')
def create_group(request:Request,payload:dict):
    own=actor(request)['id'];known=people();name=payload.get('name','');ids=payload.get('user_ids',[])
    if not isinstance(name,str) or '\x00' in name or not 1<=len(name.strip())<=100 or not isinstance(ids,list) or len(ids)>100:raise HTTPException(400,'Enter a group name and up to 100 members.')
    if any(type(u) is not int or u not in known or not known[u]['active'] or not known[u]['approved'] for u in ids) or own not in known:raise HTTPException(400,'Choose active approved members.')
    key=uuid.uuid4().hex
    with store.db() as db:
        db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',(key,-1,-1,time.time(),key,key));db.execute('INSERT INTO chat_groups VALUES(?,?,?,NULL)',(key,name.strip(),own))
        for user in set(ids+[own]):db.execute('INSERT INTO group_members VALUES(?,?,?)',(key,user,stamp(known[user])))
    return {'id':key}

@router.get('/work-options')
def work_options(request:Request):
    user=actor(request)
    from backend.core.workhub import store as hub
    output=[]
    if user.get('role')!='admin' and 'workhub' not in user.get('workspaceModules',[]):return {'projects':[]}
    with hub.db() as db:
        for project in db.execute("SELECT * FROM items WHERE type='project' ORDER BY title"):
            try:hub.contribute(db,project['id'],user)
            except HTTPException:continue
            output.append({'id':project['id'],'title':project['title'],'tasks':[{'id':r['id'],'title':r['title']} for r in db.execute("SELECT id,title FROM items WHERE project_id=? AND type='task' ORDER BY title",(project['id'],))]})
    return {'projects':output}

@router.post('/threads/{key}/messages/{message_id}/work-item')
def message_work(key:str,message_id:int,request:Request,payload:dict):
    user=actor(request)
    with store.db() as db:
        store.thread(db,key,user['id']);message=db.execute('SELECT * FROM messages WHERE id=? AND thread=?',(message_id,key)).fetchone()
        if not message:raise HTTPException(404,'Message not found.')
    if user.get('role')!='admin' and 'workhub' not in user.get('workspaceModules',[]):raise HTTPException(403,'WorkHub access is required.')
    kind=payload.get('kind');project=payload.get('project_id')
    if kind not in {'project','task'} or kind=='task' and not project:raise HTTPException(400,'Choose project or task and its parent project.')
    from backend.core.workhub import store as hub
    result=hub.create(user,{'title':payload.get('title',''),'description':message['body']},project_id=project if kind=='task' else None)
    return {'project':result['project_id'],'item':result['id']}

def public_person(account):return {k:v for k,v in account.items() if k!='createdAt'}

@router.get('/users')
def users(request:Request):
    own=actor(request)['id'];return {'users':[public_person(u) for u in people().values() if u['id']!=own and u['active'] and u['approved']]}

@router.get('/threads')
def threads(request:Request):
    own=actor(request)['id'];names=people();items=[]
    with store.db() as db:
        sync_groups(db)
        for t in list(db.execute('SELECT * FROM threads WHERE a=? OR b=? OR EXISTS(SELECT 1 FROM group_members gm WHERE gm.thread=threads.id AND gm.user=?)',(own,own,own))):
            group=db.execute('SELECT * FROM chat_groups WHERE thread=?',(t['id'],)).fetchone()
            if group:
                try:store.thread(db,t['id'],own,sync=False)
                except HTTPException:continue
            else:
                if own not in names or t['a_identity' if t['a']==own else 'b_identity']!=stamp(names[own]):continue
            last=db.execute('SELECT * FROM messages WHERE thread=? ORDER BY id DESC LIMIT 1',(t['id'],)).fetchone()
            read=db.execute('SELECT last_id FROM reads WHERE thread=? AND user=?',(t['id'],own)).fetchone()
            unread=db.execute('SELECT COUNT(*) FROM messages WHERE thread=? AND sender!=? AND id>?',(t['id'],own,read['last_id'] if read else 0)).fetchone()[0]
            peer=names.get(t['b'] if t['a']==own else t['a'],{'id':0,'username':'Unavailable user','active':False})
            if t['b_identity' if t['a']==own else 'a_identity']!=stamp(peer):peer={'id':0,'username':'Unavailable user','active':False}
            if group:peer={'id':0,'username':group['name'],'active':True}
            items.append({'kind':'team' if group and group['team_id'] else 'group' if group else 'direct','members':members(db,t['id']) if group else [],**{k:t[k] for k in ('id','a','b','created')},'peer':public_person(peer),'last':store.message(db,last) if last else None,'unread':unread})
    items.sort(key=lambda t:t['last']['id'] if t['last'] else 0,reverse=True)
    return {'threads':items,'unread':sum(t['unread'] for t in items)}

@router.post('/threads')
def create_thread(request:Request,payload:dict):
    own=actor(request)['id'];peer=payload.get('user_id');known=people()
    if own not in known:raise HTTPException(401,'This account is no longer available.')
    if type(peer) is not int or peer==own or peer not in known or not known[peer]['active'] or not known[peer]['approved']:raise HTTPException(400,'Choose an active approved user.')
    a,b=sorted([own,peer])
    with store.db() as db:
        db.execute('INSERT OR IGNORE INTO threads VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,a,b,time.time(),stamp(known[a]),stamp(known[b])))
        row=db.execute('SELECT * FROM threads WHERE a=? AND b=? AND a_identity=? AND b_identity=?',(a,b,stamp(known[a]),stamp(known[b]))).fetchone()
        return {k:row[k] for k in ('id','a','b','created')}

@router.get('/threads/{key}/messages')
def messages(key:str,request:Request,before:int|None=None,limit:int=Query(50,ge=1,le=100)):
    own=actor(request)['id']
    with store.db() as db:
        t=store.thread(db,key,own)
        rows=list(db.execute('SELECT * FROM messages WHERE thread=? AND id<? ORDER BY id DESC LIMIT ?',(key,before if before is not None else 9223372036854775807,limit+1)))
        more=len(rows)>limit;rows=rows[:limit]
        other=db.execute('SELECT last_id FROM reads WHERE thread=? AND user!=?',(key,own)).fetchone()
        return {'messages':[store.message(db,r) for r in reversed(rows)],'has_more':more,'peer_read_id':other['last_id'] if other else 0}

@router.post('/threads/{key}/read')
def mark_read(key:str,request:Request,payload:dict):
    own=actor(request)['id'];last=payload.get('last_id')
    if type(last) is not int or last<0:raise HTTPException(400,'Invalid message cursor.')
    with store.db() as db:
        store.thread(db,key,own)
        if last and not db.execute('SELECT 1 FROM messages WHERE thread=? AND id=?',(key,last)).fetchone():raise HTTPException(400,'Message is outside this conversation.')
        db.execute('INSERT INTO reads VALUES(?,?,?) ON CONFLICT(thread,user) DO UPDATE SET last_id=MAX(last_id,excluded.last_id)',(key,own,last))
    return {'ok':True}

@router.post('/threads/{key}/messages')
def send(key:str,request:Request,body:str=Form(''),client_id:str=Form(...),files:list[UploadFile]=File(default=[]),project_id:str=Form(''),item_id:str=Form('')):
    own=actor(request)['id'];body=body.strip()
    if len(body)>8000 or '\x00' in body or not re.fullmatch(r'[a-zA-Z0-9-]{8,80}',client_id) or len(files)>3 or not body and not files:raise HTTPException(400,'Write up to 8,000 characters or attach up to 3 files.')
    saved=[];folder=store.root/'files';total=0
    try:
        with store.db() as db:
            t=store.thread(db,key,own);peer=t['b'] if t['a']==own else t['a'];known=people()
            group=db.execute('SELECT 1 FROM chat_groups WHERE thread=?',(key,)).fetchone()
            if not group and (peer not in known or not known[peer]['active'] or not known[peer]['approved'] or t['b_identity' if t['a']==own else 'a_identity']!=stamp(known[peer])):raise HTTPException(409,'This user is no longer available for new messages.')
            if project_id:work_link(actor(request),project_id,item_id)
            elif item_id:raise HTTPException(400,'Select the project for this task.')
            existing=db.execute('SELECT * FROM messages WHERE sender=? AND client_id=?',(own,client_id)).fetchone()
            if existing:
                if existing['thread']!=key:raise HTTPException(409,'Message retry belongs to another conversation.')
                return store.message(db,existing)
            for upload in files:
                name=re.sub(r'[\x00-\x1f\x7f]','',str(upload.filename or 'file').replace('\\','/').rsplit('/',1)[-1])[:180];suffix=Path(name).suffix.lower()
                if suffix not in ALLOWED:raise HTTPException(400,'Use ZIP, PNG, JPG, WebP, PDF, Office, audio/video, CSV or text files. Executable, HTML and SVG uploads are not accepted.')
                folder.mkdir(exist_ok=True);identity=uuid.uuid4().hex;path=folder/identity;size=0;saved.append((path,identity,name,ALLOWED[suffix],0))
                with path.open('xb') as output:
                    while chunk:=upload.file.read(262144):
                        size+=len(chunk);total+=len(chunk)
                        if total>20*1024*1024:raise HTTPException(413,'Attachments must total 20 MB or less.')
                        output.write(chunk)
                if not size:raise HTTPException(400,'Empty files are not accepted.')
                if suffix=='.zip':
                    import zipfile
                    if not zipfile.is_zipfile(path):raise HTTPException(400,'The ZIP archive is invalid. Archives are shared without extraction.')
                if ALLOWED[suffix].startswith('image/'):
                    from PIL import Image
                    try:
                        with Image.open(path) as image:
                            if image.format not in {'PNG','JPEG','WEBP'} or image.width*image.height>25_000_000:raise ValueError()
                            actual={'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}[image.format];image.verify()
                    except Exception:raise HTTPException(400,'The image is invalid or too large to preview.') from None
                    mime=actual
                else:mime=ALLOWED[suffix]
                saved[-1]=(path,identity,name,mime,size)
            now=time.time()
            if db.execute('SELECT COUNT(*) FROM messages WHERE sender=? AND created>?',(own,now-60)).fetchone()[0]>=60:raise HTTPException(429,'Message limit reached. Try again in a minute.')
            cursor=db.execute('INSERT INTO messages(thread,sender,body,created,client_id) VALUES(?,?,?,?,?)',(key,own,body,now,client_id));message=cursor.lastrowid
            for _,identity,name,mime,size in saved:db.execute('INSERT INTO attachments VALUES(?,?,?,?,?)',(identity,message,name,mime,size))
            if project_id:db.execute('INSERT INTO message_links VALUES(?,?,?)',(message,project_id,item_id))
            result=store.message(db,db.execute('SELECT * FROM messages WHERE id=?',(message,)).fetchone())
        return result
    except Exception:
        for path,*_ in saved:path.unlink(missing_ok=True)
        raise
    finally:
        for upload in files:upload.file.close()

@router.get('/files/{identity}')
def attachment(identity:str,request:Request,preview:bool=False):
    own=actor(request)['id']
    with store.db() as db:
        row=db.execute('SELECT a.*,m.thread FROM attachments a JOIN messages m ON m.id=a.message WHERE a.id=?',(identity,)).fetchone()
        if not row:raise HTTPException(404,'File not found.')
        store.thread(db,row['thread'],own)
    path=store.root/'files'/row['id']
    if not path.is_file():raise HTTPException(404,'File no longer available.')
    inline=preview and row['mime'].startswith('image/')
    return FileResponse(path,media_type=row['mime'] if inline else 'application/octet-stream',filename=row['name'],content_disposition_type='inline' if inline else 'attachment',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
