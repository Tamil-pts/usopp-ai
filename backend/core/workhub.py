"""Shared engineering projects, explicit workflow decisions and durable evidence."""
from __future__ import annotations

from contextlib import contextmanager,nullcontext,closing
from datetime import datetime, date, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from fastapi import HTTPException
from backend.core.runtime import BASE
from backend.core import accounts

ROOT=BASE/'.usopp_workhub'
STAGES={'todo':'To do','development':'Development','development_completed':'Development completed','quality':'Quality check',
        'release_approval':'Release approval','ready_release':'Ready for release','released':'Released / Closed','blocked':'Blocked'}
KINDS=['B&R PLC','Siemens PLC','Other PLC','Electrical / CAD','Documentation','General']
NEXT_OWNER={'todo':'owner_id','development':'owner_id','development_completed':'owner_id','quality':'quality_id',
            'release_approval':'approver_id','ready_release':'release_id','released':'owner_id','blocked':'owner_id'}
DONE_DEVELOPMENT={'development_completed','quality','release_approval','ready_release','released'}

def identity():return uuid.uuid4().hex
def timestamp():return datetime.now(timezone.utc).isoformat()
def encode(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def text(value,limit=4000,required=False):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value:raise HTTPException(400,'Enter valid text within the field limit.')
    value=value.strip()
    if required and not value:raise HTTPException(400,'Enter a name or description.')
    return value
def day(value):
    value=text(value or '',10)
    if value:
        try:date.fromisoformat(value)
        except ValueError:raise HTTPException(400,'Choose a valid date.') from None
    return value

class WorkHub:
    def __init__(self,root=ROOT):self.root=Path(root);self.ready=False;self.lock=threading.RLock()
    def initialize(self):
        with self.lock:
            if self.ready:return
            self.root.mkdir(parents=True,exist_ok=True)
            with closing(sqlite3.connect(str(self.root/'projects.sqlite3'))) as db,db:
                db.execute('PRAGMA journal_mode=WAL')
                db.executescript('''
                CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,parent_id TEXT,
                  type TEXT NOT NULL,title TEXT NOT NULL,kind TEXT NOT NULL,description TEXT NOT NULL,
                  created_by INTEGER NOT NULL,owner_id INTEGER NOT NULL,quality_id INTEGER NOT NULL,
                  approver_id INTEGER NOT NULL,release_id INTEGER NOT NULL,stage TEXT NOT NULL DEFAULT 'todo',
                  due_date TEXT NOT NULL DEFAULT '',start_date TEXT NOT NULL DEFAULT '',baseline_due TEXT NOT NULL DEFAULT '',
                  planned_hours REAL NOT NULL DEFAULT 0,started_at TEXT,completed_at TEXT,review_revision TEXT,
                  resume_stage TEXT,dependencies TEXT NOT NULL DEFAULT '[]',version INTEGER NOT NULL DEFAULT 1,
                  created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS project_items ON items(project_id,type);
                CREATE TABLE IF NOT EXISTS updates(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,item_id TEXT NOT NULL,
                  author_id INTEGER NOT NULL,body TEXT NOT NULL,work_date TEXT NOT NULL,minutes INTEGER NOT NULL DEFAULT 0,
                  file_ids TEXT NOT NULL,run_ids TEXT NOT NULL,created_at TEXT NOT NULL,reviewer_id INTEGER,
                  time_status TEXT NOT NULL DEFAULT 'none',review_comment TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS update_context(update_id TEXT PRIMARY KEY,work_status TEXT NOT NULL,request_kind TEXT NOT NULL,mention_ids TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS update_requests(notification_id TEXT PRIMARY KEY,update_id TEXT NOT NULL,resolved_at TEXT);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id TEXT NOT NULL,
                  item_id TEXT NOT NULL,actor_id INTEGER NOT NULL,event TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,recipient_id INTEGER NOT NULL,
                  sender_id INTEGER NOT NULL,project_id TEXT NOT NULL,item_id TEXT NOT NULL,title TEXT NOT NULL,
                  body TEXT NOT NULL,created_at TEXT NOT NULL,read_at TEXT);
                CREATE INDEX IF NOT EXISTS user_notifications ON notifications(recipient_id,created_at);
                CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,notification_id TEXT NOT NULL,
                  channel TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
                  next_attempt REAL NOT NULL DEFAULT 0,detail TEXT NOT NULL DEFAULT '',updated_at TEXT);
                CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,uploaded_by INTEGER NOT NULL,
                  name TEXT NOT NULL,sha256 TEXT NOT NULL,size INTEGER NOT NULL,created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS file_project ON files(project_id);
                CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,owner_id INTEGER NOT NULL,
                  name TEXT NOT NULL,size INTEGER NOT NULL,received INTEGER NOT NULL DEFAULT 0,
                  status TEXT NOT NULL DEFAULT 'uploading',file_id TEXT,created REAL NOT NULL,updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,label TEXT NOT NULL,
                  file_ids TEXT NOT NULL,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,description TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS issues(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,item_id TEXT NOT NULL,
                  title TEXT NOT NULL,owner_id INTEGER NOT NULL,created_by INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'open',
                  created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS preferences(user_id INTEGER PRIMARY KEY,contact_email TEXT NOT NULL DEFAULT '',
                  email_enabled INTEGER NOT NULL DEFAULT 0,teams_secret TEXT NOT NULL DEFAULT '',
                  teams_enabled INTEGER NOT NULL DEFAULT 0,mail_cache TEXT NOT NULL DEFAULT '',mail_address TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY,user_id INTEGER NOT NULL,
                  flow TEXT NOT NULL,expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS reminders(item_id TEXT NOT NULL,day TEXT NOT NULL,PRIMARY KEY(item_id,day));
                CREATE TABLE IF NOT EXISTS engineering_sources(owner_id INTEGER NOT NULL,source_key TEXT NOT NULL,
                  project_id TEXT NOT NULL,PRIMARY KEY(owner_id,source_key,project_id));
                CREATE TABLE IF NOT EXISTS engineering_runs(run_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
                  update_id TEXT NOT NULL,iteration INTEGER NOT NULL,kind TEXT NOT NULL,test_id TEXT NOT NULL,
                  author_id INTEGER NOT NULL,status TEXT NOT NULL,summary TEXT NOT NULL,source_name TEXT NOT NULL,
                  created_at TEXT NOT NULL,completed_at TEXT,UNIQUE(project_id,iteration));
                CREATE INDEX IF NOT EXISTS engineering_project ON engineering_runs(project_id,iteration);
                CREATE TABLE IF NOT EXISTS project_phases(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,phase TEXT NOT NULL,
                  title TEXT NOT NULL,start_date TEXT NOT NULL DEFAULT '',due_date TEXT NOT NULL DEFAULT '',
                  baseline_due TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,UNIQUE(project_id,phase));
                CREATE TABLE IF NOT EXISTS sprints(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,title TEXT NOT NULL,
                  goal TEXT NOT NULL DEFAULT '',owner_id INTEGER NOT NULL,start_date TEXT NOT NULL,due_date TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'planned',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS project_sprints ON sprints(project_id,start_date);
                ''')
                if 'review_run_id' not in {row[1] for row in db.execute('PRAGMA table_info(items)')}:
                    db.execute('ALTER TABLE items ADD COLUMN review_run_id TEXT')
                if 'milestone' not in {row[1] for row in db.execute('PRAGMA table_info(items)')}:
                    db.execute('ALTER TABLE items ADD COLUMN milestone INTEGER NOT NULL DEFAULT 0')
                item_columns={row[1] for row in db.execute('PRAGMA table_info(items)')}
                for name,definition in (('methodology',"TEXT NOT NULL DEFAULT 'custom'"),('work_phase',"TEXT NOT NULL DEFAULT 'development'"),('sprint_id',"TEXT NOT NULL DEFAULT ''")):
                    if name not in item_columns:db.execute('ALTER TABLE items ADD COLUMN '+name+' '+definition)
                from .workhub_workspace import migrate as workspace_metadata
                workspace_metadata(db)
                columns={row[1] for row in db.execute('PRAGMA table_info(preferences)')}
                for name,definition in (('teams_chat_url',"TEXT NOT NULL DEFAULT ''"),('teams_mode',"TEXT NOT NULL DEFAULT 'chat'")):
                    if name not in columns:db.execute('ALTER TABLE preferences ADD COLUMN '+name+' '+definition)
                db.execute("UPDATE outbox SET status='manual',detail='Share using the Teams chat link; no automatic message was sent.' WHERE channel='teams' AND status IN ('pending','failed','waiting_connection') AND notification_id IN (SELECT n.id FROM notifications n LEFT JOIN preferences p ON p.user_id=n.recipient_id WHERE COALESCE(p.teams_mode,'chat')='chat')")
                db.execute("UPDATE outbox SET status='disabled',detail='The sender has not enabled automatic email.' WHERE channel='email' AND status IN ('pending','failed','waiting_connection') AND notification_id IN (SELECT n.id FROM notifications n LEFT JOIN preferences p ON p.user_id=n.sender_id WHERE COALESCE(p.email_enabled,0)=0)")
            self.ready=True
    @contextmanager
    def db(self,write=False):
        self.initialize()
        db=sqlite3.connect(str(self.root/'projects.sqlite3'),timeout=30);db.row_factory=sqlite3.Row
        try:
            if write:db.execute('BEGIN IMMEDIATE')
            yield db
            if write:db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()
    def users(self):
        return [{'id':u['id'],'username':u['username'],'designation':u['designation'],'avatarUrl':u.get('avatarUrl'),'active':bool(u.get('active'))}
                for u in accounts.store.list_users() if u.get('approved') and not u.get('isDemo')]
    def user_id(self,value):
        if type(value) is not int or value not in {u['id'] for u in self.users() if u['active']}:raise HTTPException(400,'Choose an enabled user by name.')
        return value
    def actor(self,user):
        if not user or user.get('isDemo'):raise HTTPException(403,'Use a personal account to create or change shared projects.')
    def item(self,db,key):
        if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{32}',key):raise HTTPException(404,'Project or task not found.')
        row=db.execute('SELECT * FROM items WHERE id=?',(key,)).fetchone()
        if not row:
            from .workhub_document_spaces import find
            scope=find(db,key)
            if scope:return scope
            raise HTTPException(404,'Project or task not found.')
        return dict(row)
    def manage(self,item,user,db=None):
        self.actor(user)
        managers={item['created_by'],item['owner_id']}
        if db is not None and item['type']=='task':
            project=self.item(db,item['project_id']);managers.update({project['created_by'],project['owner_id']})
        if user['role']!='admin' and user['id'] not in managers:
            raise HTTPException(403,'Only the project creator, assigned owner or Admin can change its plan.')
    def contribute(self,db,key,user):
        self.actor(user);project=self.item(db,key)
        if project.get('is_document_space'):
            from .workhub_document_spaces import authorize
            return authorize(db,project,user,True)
        if project['type']!='project':raise HTTPException(400,'Choose a project.')
        if user['role']!='admin' and not db.execute('SELECT 1 FROM items WHERE project_id=? AND (? IN (created_by,owner_id,quality_id,approver_id,release_id) OR EXISTS(SELECT 1 FROM json_each(supporting_ids) WHERE value=?)) LIMIT 1',(key,user['id'],user['id'])).fetchone():
            raise HTTPException(403,'Ask the project owner to assign you before uploading project files.')
        return project
    def event(self,db,item,user,event,detail):
        detail={**detail,'actor_name':user.get('username','')}
        db.execute('INSERT INTO events(project_id,item_id,actor_id,event,detail,created_at) VALUES(?,?,?,?,?,?)',
                   (item['project_id'],item['id'],user['id'],event,encode(detail),timestamp()))
    def notify(self,db,item,sender,recipients,title,body):
        for recipient in set(recipients):
            if recipient not in {u['id'] for u in self.users() if u['active']}:continue
            key=identity();now=timestamp()
            db.execute('INSERT INTO notifications VALUES(?,?,?,?,?,?,?,?,NULL)',
                       (key,recipient,sender,item['project_id'],item['id'],title[:240],body[:3000],now))
            for channel in ('email','teams'):
                preference=db.execute('SELECT teams_mode FROM preferences WHERE user_id=?',(recipient,)).fetchone() if channel=='teams' else None
                status='manual' if channel=='teams' and (not preference or preference['teams_mode']=='chat') else 'pending'
                db.execute('INSERT INTO outbox(id,notification_id,channel,status) VALUES(?,?,?,?)',(identity(),key,channel,status))
    def public(self,item):
        row=dict(item);row['dependencies']=json.loads(row.get('dependencies','[]'))
        row['milestone']=bool(row.get('milestone',False))
        row['progress']=100 if row['stage'] in DONE_DEVELOPMENT else 0
        if row['type']=='project':
            row['progress']={'development_completed':33,'quality':33,'release_approval':67,'ready_release':83,'released':100}.get(row['stage'],0)
        row['stage_label']=STAGES[row['stage']];row['current_user_id']=row[NEXT_OWNER[row['stage']]]
        row['health']='Delayed' if row['due_date'] and row['due_date']<date.today().isoformat() and row['stage']!='released' else 'At risk' if row['stage']=='blocked' else 'On track'
        return row
    def completion(self,project,tasks):
        from .workhub_planning import completion
        return completion(project,tasks)
    def create(self,user,payload,project_id=None,transaction=None):
        self.actor(user);now=timestamp();key=identity()
        with (nullcontext(transaction) if transaction is not None else self.db(True)) as db:
            parent=self.item(db,project_id) if project_id else None
            if parent and parent['type']!='project':raise HTTPException(400,'Create tasks inside a project.')
            if parent:self.manage(parent,user)
            from .workhub_planning import phase,initialize_plan
            work_phase=phase(payload.get('work_phase','development'))
            if parent and (parent['stage']=='released' or (work_phase=='development' and parent['stage'] not in {'todo','development','blocked'})):raise HTTPException(409,'Continue project development before adding development work.')
            default_owner=parent[{'development':'owner_id','quality':'quality_id','release':'release_id'}[work_phase]] if parent else user['id']
            owner=self.user_id(payload.get('owner_id',default_owner))
            quality=self.user_id(payload.get('quality_id',parent['quality_id'] if parent else user['id']))
            approver=self.user_id(payload.get('approver_id',parent['approver_id'] if parent else user['id']))
            release=self.user_id(payload.get('release_id',parent['release_id'] if parent else owner))
            kind=text(payload.get('kind',parent['kind'] if parent else 'General'),50)
            kind=text(kind,50,True)
            title=text(payload.get('title',''),180,True);due=day(payload.get('due_date',parent['due_date'] if parent else ''));start=day(payload.get('start_date',''))
            if due and start and due<start:raise HTTPException(400,'Due date must follow the planned start.')
            milestone=payload.get('milestone',False)
            if type(milestone) is not bool:raise HTTPException(400,'Choose whether this step is a milestone.')
            if milestone and (not parent or not start or due!=start):raise HTTPException(400,'A milestone needs one matching start and finish date inside a project.')
            parent_id=payload.get('parent_id') or None
            if parent_id and (not parent or self.item(db,parent_id)['project_id']!=project_id):raise HTTPException(400,'Choose a parent in this project.')
            if parent_id and self.item(db,parent_id)['stage'] not in {'todo','development','blocked'}:raise HTTPException(409,'Reopen the parent task before adding subtasks.')
            planned=payload.get('planned_hours',0)
            if type(planned) not in (int,float) or not 0<=planned<=100000:raise HTTPException(400,'Enter a valid estimate.')
            dependencies=payload.get('dependencies',[])
            if not isinstance(dependencies,list) or len(dependencies)>100:raise HTTPException(400,'Use at most 100 dependencies.')
            for dep in dependencies:
                related=self.item(db,dep)
                if not parent or related['project_id']!=project_id or related['type']!='task':raise HTTPException(400,'Choose other tasks in this project.')
            db.execute('''INSERT INTO items(id,project_id,parent_id,type,title,kind,description,created_by,
              owner_id,quality_id,approver_id,release_id,due_date,start_date,baseline_due,planned_hours,dependencies,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(key,project_id or key,parent_id,'task' if parent else 'project',title,kind,
              text(payload.get('description','')),user['id'],owner,quality,approver,release,due,start,due,planned,encode(list(dict.fromkeys(dependencies))),now,now))
            sprint_id=payload.get('sprint_id') or ''
            if not isinstance(sprint_id,str):raise HTTPException(400,'Choose a sprint in this project.')
            if sprint_id:
                sprint=db.execute('SELECT * FROM sprints WHERE id=? AND project_id=?',(sprint_id,project_id)).fetchone()
                if not parent or work_phase!='development' or not sprint or sprint['status']=='closed':raise HTTPException(400,'Choose an open development sprint in this project.')
            db.execute('UPDATE items SET milestone=?,work_phase=?,sprint_id=? WHERE id=?',(int(milestone),work_phase,sprint_id,key))
            item=self.item(db,key);self.event(db,item,user,'created',{'title':title,'owner':owner})
            if not parent:initialize_plan(self,db,item,user,payload)
            if not parent and payload.get('assignment_mode')=='later':
                self.notify(db,item,user['id'],[user['id']],'Project needs an engineer: '+title,'The project is registered and awaits assignment.')
            else:self.notify(db,item,user['id'],[owner],'Work assigned: '+title,'You are assigned development. Open the task to start or add an update.')
            return self.public(self.item(db,key))
    def overview(self):
        with self.db() as db:
            items=[self.public(row) for row in db.execute('SELECT * FROM items ORDER BY created_at DESC')]
            tasks_by_project={}
            for row in items:
                if row['type']=='task':tasks_by_project.setdefault(row['project_id'],[]).append(row)
            updates={row[0]:row[1] for row in db.execute('SELECT project_id,MAX(created_at) FROM updates GROUP BY project_id')}
            latest_runs={row['project_id']:dict(row) for row in db.execute('SELECT e.* FROM engineering_runs e JOIN (SELECT project_id,MAX(iteration) AS iteration FROM engineering_runs GROUP BY project_id) latest ON latest.project_id=e.project_id AND latest.iteration=e.iteration')}
            for project in items:
                if project['type']!='project':continue
                tasks=tasks_by_project.get(project['id'],[])
                project.update(self.completion(project,tasks))
                project['latest_update']=updates.get(project['id'])
            for item in items:
                latest=latest_runs.get(item['project_id'])
                item['iteration_count']=latest['iteration'] if latest else 0
                item['latest_iteration']={**dict(latest),'summary':json.loads(latest['summary'])} if latest else None
            kinds=list(dict.fromkeys([*KINDS,*[row[0] for row in db.execute("SELECT DISTINCT kind FROM items WHERE kind!='' ORDER BY kind COLLATE NOCASE")]]))
            return {'items':items,'users':self.users(),'stages':STAGES,'kinds':kinds,
                    'summary':{'projects':sum(row['type']=='project' for row in items),'active':sum(row['type']=='project' and row['stage']!='released' for row in items),
                               'blocked':sum(row['stage']=='blocked' for row in items),'overdue':sum(row['health']=='Delayed' for row in items)}}
    def detail(self,key):
        with self.db() as db:
            project=self.item(db,key)
            if project['type']!='project':raise HTTPException(400,'Choose a project.')
            def rows(table,limit=500):return [dict(row) for row in db.execute(f'SELECT * FROM {table} WHERE project_id=? ORDER BY created_at DESC LIMIT ?',(key,limit))]
            updates=rows('updates')
            for row in updates:
                row['file_ids']=json.loads(row['file_ids']);row['run_ids']=json.loads(row['run_ids'])
            revisions=rows('revisions')
            for row in revisions:row['file_ids']=json.loads(row['file_ids'])
            events=rows('events')
            for row in events:row['detail']=json.loads(row['detail'])
            iterations=[{**dict(row),'summary':json.loads(row['summary'])} for row in db.execute('SELECT * FROM engineering_runs WHERE project_id=? ORDER BY iteration DESC LIMIT 500',(key,))]
            by_update={row['update_id']:row for row in iterations}
            for row in updates:row['iteration']=by_update.get(row['id'])
            tasks=[self.public(row) for row in db.execute("SELECT * FROM items WHERE project_id=? AND type='task' ORDER BY created_at",(key,))]
            from .workhub_planning import phases,sprints
            return {'project':{**self.public(project),**self.completion(project,tasks)},'tasks':tasks,'phases':phases(self,db,project,tasks),'sprints':sprints(db,project,tasks),
                    'updates':updates,'iterations':iterations,'revisions':revisions,'files':rows('files',50000),'events':events,'issues':rows('issues')}
    def edit(self,user,key,payload,transaction=None):
        with (nullcontext(transaction) if transaction is not None else self.db(True)) as db:
            item=self.item(db,key);self.manage(item,user,db)
            if payload.get('version')!=item['version']:raise HTTPException(409,'This work changed. Refresh before saving.')
            role_fields={'owner_id','quality_id','approver_id','release_id'}
            metadata_fields=role_fields|{'kind','version'}
            if item['stage'] not in {'todo','development','blocked'} and not set(payload).issubset(metadata_fields):raise HTTPException(409,'Request changes or reopen the work before changing its plan. Assignees and work type can still be changed.')
            if item['type']=='task':
                parent=self.item(db,item['project_id']);allowed={'todo','development','blocked'}|({'quality'} if item['work_phase']=='quality' else {'release_approval','ready_release'} if item['work_phase']=='release' else set())
                future_plan=item['stage']=='todo' and item['work_phase'] in {'quality','release'} and parent['stage']!='released'
                if parent['stage'] not in allowed and not future_plan and not set(payload).issubset(metadata_fields):raise HTTPException(409,'Continue the corresponding project phase before changing this workflow step.')
            changed={}
            if 'kind' in payload:
                changed['kind']=text(payload['kind'],50,True)
            from .workhub_planning import method,phase
            if 'methodology' in payload and item['type']=='project':changed['methodology']=method(payload['methodology'])
            if 'work_phase' in payload and item['type']=='task':
                selected_phase=phase(payload['work_phase'])
                if selected_phase!=item['work_phase'] and item['stage']!='todo':raise HTTPException(409,'Change the phase before starting this step.')
                if selected_phase=='development' and parent['stage'] not in {'todo','development','blocked'}:raise HTTPException(409,'Continue project development before moving this step into development.')
                changed['work_phase']=selected_phase
            if 'sprint_id' in payload and item['type']=='task':
                sprint_id=payload['sprint_id'] or ''
                if not isinstance(sprint_id,str):raise HTTPException(400,'Choose a sprint in this project.')
                previous=db.execute('SELECT status FROM sprints WHERE id=?',(item['sprint_id'],)).fetchone() if item['sprint_id'] else None
                if previous and previous['status']=='closed' and sprint_id!=item['sprint_id']:raise HTTPException(409,'Reopen the sprint before moving its work.')
                if sprint_id:
                    sprint=db.execute('SELECT * FROM sprints WHERE id=? AND project_id=?',(sprint_id,item['project_id'])).fetchone()
                    if not sprint or sprint['status']=='closed' or changed.get('work_phase',item['work_phase'])!='development':raise HTTPException(400,'Choose an open development sprint in this project.')
                changed['sprint_id']=sprint_id
            for field in ('title','description'):
                if field in payload:changed[field]=text(payload[field],180 if field=='title' else 4000,field=='title')
            for field in ('owner_id','quality_id','approver_id','release_id'):
                if field in payload:changed[field]=self.user_id(payload[field])
            for field in ('due_date','start_date'):
                if field in payload:changed[field]=day(payload[field])
            start=changed.get('start_date',item['start_date']);due=changed.get('due_date',item['due_date'])
            if start and due and due<start:raise HTTPException(400,'Due date must follow the planned start.')
            if 'milestone' in payload:
                if type(payload['milestone']) is not bool:raise HTTPException(400,'Choose whether this step is a milestone.')
                changed['milestone']=int(payload['milestone'])
            if changed.get('milestone',item.get('milestone',0)) and (item['type']!='task' or not start or due!=start):
                raise HTTPException(400,'A milestone needs one matching start and finish date inside a project.')
            if 'planned_hours' in payload:
                val=payload['planned_hours']
                if type(val) not in (int,float) or not 0<=val<=100000:raise HTTPException(400,'Enter a valid estimate.')
                changed['planned_hours']=val
            if 'dependencies' in payload:
                dependencies=payload['dependencies']
                if not isinstance(dependencies,list) or len(dependencies)>100:raise HTTPException(400,'Use at most 100 dependencies.')
                graph={row['id']:json.loads(row['dependencies']) for row in db.execute('SELECT id,dependencies FROM items WHERE project_id=?',(item['project_id'],))}
                for dep in dependencies:
                    if not isinstance(dep,str) or dep not in graph or dep in {key,item['project_id']}:raise HTTPException(400,'Choose other tasks in the same project.')
                graph[key]=dependencies
                visited=set()
                def visit(node,path):
                    if node in path:raise HTTPException(400,'Task dependencies cannot form a cycle.')
                    if len(path)>150:raise HTTPException(400,'Use dependency chains of at most 150 tasks.')
                    if node in visited:return
                    for dep in graph[node]:visit(dep,path|{node})
                    visited.add(node)
                visit(key,set());changed['dependencies']=encode(list(dict.fromkeys(dependencies)))
            if not changed:return self.public(item)
            changed.update(updated_at=timestamp(),version=item['version']+1)
            db.execute('UPDATE items SET '+','.join(field+'=?' for field in changed)+' WHERE id=?',(*changed.values(),key))
            if 'quality_id' in changed and changed['quality_id']!=item['quality_id']:
                db.execute("UPDATE updates SET reviewer_id=? WHERE item_id=? AND time_status='submitted'",(changed['quality_id'],key))
            self.event(db,item,user,'plan_updated',changed)
            for field in role_fields:
                if field in changed and changed[field]!=item[field]:
                    from .workhub_planning import reassign_phase_steps
                    reassign_phase_steps(self,db,item,user,field,changed[field])
                    self.notify(db,item,user['id'],[changed[field]],'Work reassigned: '+item['title'],('The current workflow stage is assigned to you.' if field==NEXT_OWNER[item['stage']] else 'You have been assigned '+{'owner_id':'development','quality_id':'quality review','approver_id':'release approval','release_id':'release'}[field]+'.'))
            return self.public(self.item(db,key))
    def transition(self,user,key,payload,transaction=None):
        from .workhub_quality.store import initialize as initialize_quality
        from .workhub_quality.checks import guard_closure,issue_dispositioned
        initialize_quality()
        self.actor(user)
        with (nullcontext(transaction) if transaction is not None else self.db(True)) as db:
            item=self.item(db,key);action=payload.get('action');comment=text(payload.get('comment',''))
            project=self.item(db,item['project_id'])
            if project.get('exception_status') in {'on_hold','cancelled'}:raise HTTPException(409,'Resume the project condition before advancing its workflow.')
            if project.get('assignment_state')=='unassigned':raise HTTPException(409,'Assign a responsible engineer before starting project work.')
            if payload.get('version')!=item['version']:raise HTTPException(409,'This work changed. Refresh before acting.')
            stage=item['stage'];responsible=item[NEXT_OWNER[stage]]
            if user['id']!=responsible:raise HTTPException(403,'This action belongs to the user assigned to the current stage.')
            transitions={'start':({'todo'},'development'),'complete_development':({'development'},'development_completed'),
                         'continue_development':({'development_completed'},'development'),'submit_quality':({'development_completed'},'quality'),
                         'quality_pass':({'quality'},'release_approval'),'approve_release':({'release_approval'},'ready_release'),
                         'release':({'ready_release'},'released'),'request_changes':({'quality','release_approval','ready_release'},'development'),
                         'reject':({'quality','release_approval','ready_release'},'development'),
                         'block':({'development'},'blocked'),'resume':({'blocked'},'development'),'reopen':({'released'},'development')}
            if action not in transitions or stage not in transitions[action][0]:raise HTTPException(409,'This action is unavailable at the current stage.')
            target=transitions[action][1]
            from .workhub_approval_documents import attach as attach_documents, guard as guard_documents
            if 'approval_documents' in payload:
                if action not in {'submit_quality','quality_pass','approve_release','release','request_changes','reject'}:raise HTTPException(400,'Choose a workflow submission or review action.')
                attach_documents(db,item,user,payload['approval_documents'],review=action!='submit_quality')
            checked_documents=guard_documents(db,item,action)
            from .workhub_delivery import guard as guard_delivery
            if action=='submit_quality':
                from .workhub_approval_documents import attached
                checked_documents=attached(db,key)
            if item['type']=='project' and action=='reopen':db.execute('DELETE FROM wh_closed_schedule WHERE project_id=?',(key,))
            if item['type']=='project':
                from .workhub_workflow import guard
                guard(db,item,user,action)
                if action=='quality_pass' and db.execute("SELECT 1 FROM qc_documents WHERE project_id=? AND stage='frd'",(key,)).fetchone():
                    from .workhub_quality.checks import report
                    findings=report(db,item)['blockers']
                    if findings:raise HTTPException(409,'Review the Validation Report and FAT before quality approval: '+'; '.join(r['title'] for r in findings[:6]))
            if item['type']=='task' and target=='development' and item.get('work_phase') in {'quality','release'}:
                parent=self.item(db,item['project_id'])
                expected='quality' if item['work_phase']=='quality' else 'ready_release'
                if parent['stage']!=expected:raise HTTPException(409,'Open the corresponding project review or release phase before continuing this task.')
            if action in {'request_changes','reject','block','reopen'} and not comment:raise HTTPException(400,'Add a short reason.')
            if action=='start':
                if item['type']=='task':
                    parent=self.item(db,item['project_id'])
                    if item['work_phase']=='quality' and parent['stage']!='quality':raise HTTPException(409,'Submit the project for quality check before starting its quality work.')
                    if item['work_phase']=='release' and parent['stage']!='ready_release':raise HTTPException(409,'Approve the project release before starting release delivery work.')
                    if item.get('sprint_id'):
                        sprint=db.execute('SELECT status FROM sprints WHERE id=?',(item['sprint_id'],)).fetchone()
                        if not sprint or sprint['status']!='active':raise HTTPException(409,'Start the assigned sprint before starting its work.')
                for dep in json.loads(item['dependencies']):
                    if self.item(db,dep)['stage'] not in DONE_DEVELOPMENT:raise HTTPException(409,'Complete development on the preceding workflow steps before starting this step.')
            children=[dict(row) for row in db.execute("SELECT * FROM items WHERE parent_id=? OR (project_id=? AND type='task' AND ?='project')",(key,key,item['type']))]
            development_children=[row for row in children if item['type']!='project' or row.get('work_phase','development')=='development']
            if action in {'complete_development','submit_quality'} and any(row['stage'] not in DONE_DEVELOPMENT for row in development_children):raise HTTPException(409,'Complete the development steps before completing or submitting development. Quality and release steps remain separate.')
            if action=='quality_pass' and item['type']=='project' and any(row['work_phase']=='quality' and row['stage'] not in DONE_DEVELOPMENT for row in children):raise HTTPException(409,'Complete the planned quality checks before passing project quality.')
            if action in {'complete_development','submit_quality'} and item['type']=='project' and db.execute("SELECT 1 FROM engineering_runs WHERE project_id=? AND status='running' LIMIT 1",(key,)).fetchone():raise HTTPException(409,'Wait for the project engineering runs to finish before completing development.')
            if action in {'quality_pass','approve_release','release'} and db.execute("SELECT 1 FROM engineering_runs WHERE project_id=? AND status='running' LIMIT 1",(item['project_id'],)).fetchone():raise HTTPException(409,'Wait for the active engineering check to finish before approving or releasing this work.')
            if action=='release' and any(row['stage'] not in {'development_completed','released'} for row in children):raise HTTPException(409,'Complete the workflow steps and finish any separately requested step reviews before closing this work.')
            if action=='release' and item['type']=='project' and any(not issue_dispositioned(db,row) for row in db.execute("SELECT * FROM issues WHERE project_id=? AND status='open'",(key,))):
                raise HTTPException(409,'Resolve the project and workflow steps\' open issues before releasing this project.')
            if action in {'quality_pass','approve_release','release'} and any(not issue_dispositioned(db,row) for row in db.execute("SELECT * FROM issues WHERE item_id=? AND status='open'",(key,))):raise HTTPException(409,'Resolve this work item\'s open issues before approving it.')
            if action=='release' and item['type']=='project':guard_closure(db,item,user)
            revision=item['review_revision'];review_run=item.get('review_run_id')
            if action=='submit_quality':
                from .workhub_planning import reassign_phase_steps
                for field in ('quality_id','approver_id','release_id'):
                    owner=self.user_id(payload.get(field,item[field]))
                    reassign_phase_steps(self,db,item,user,field,owner)
                    item[field]=owner
                db.execute('UPDATE items SET quality_id=?,approver_id=?,release_id=? WHERE id=?',(item['quality_id'],item['approver_id'],item['release_id'],key))
                db.execute("UPDATE updates SET reviewer_id=? WHERE item_id=? AND time_status='submitted'",(item['quality_id'],key))
                latest=db.execute('SELECT id FROM revisions WHERE project_id=? ORDER BY created_at DESC LIMIT 1',(item['project_id'],)).fetchone()
                revision=latest[0] if latest else None
                if payload.get('revision_id')!=revision:raise HTTPException(409,'The latest project revision changed. Open this action again and review its submitted revision.')
                latest_run=db.execute('SELECT run_id FROM engineering_runs WHERE project_id=? ORDER BY iteration DESC LIMIT 1',(item['project_id'],)).fetchone()
                review_run=latest_run[0] if latest_run else None
            if target=='development':revision=None;review_run=None
            checked_run=db.execute('SELECT run_id FROM engineering_runs WHERE project_id=? ORDER BY iteration DESC LIMIT 1',(item['project_id'],)).fetchone() if action in {'quality_pass','approve_release','release'} else None
            now=timestamp();started=item['started_at'] or (now if action=='start' else None)
            db.execute('UPDATE items SET stage=?,started_at=?,completed_at=?,review_revision=?,review_run_id=?,updated_at=?,version=version+1 WHERE id=?',
                       (target,started,now if target=='released' else None,revision,review_run,now,key))
            if item['type']=='task' and target=='development' and item.get('work_phase','development')=='development':
                project=self.item(db,item['project_id'])
                if project['stage'] not in {'development','blocked'}:
                    db.execute("UPDATE items SET stage='development',started_at=COALESCE(started_at,?),completed_at=NULL,review_revision=NULL,review_run_id=NULL,updated_at=?,version=version+1 WHERE id=?",(now,now,project['id']))
                    self.event(db,project,user,'step_development_resumed',{'from':project['stage'],'to':'development','step_id':key,'step_title':item['title']})
                    self.notify(db,project,user['id'],[project['owner_id'],project['created_by']],'Development: '+project['title'],'Work resumed on '+item['title']+'. Previous review decisions remain in the history.')
            from .workhub_praxis.outcomes import record as record_work_feedback
            feedback_id=record_work_feedback(db,user,item,action,payload.get('work_feedback')) if payload.get('work_feedback') is not None else None
            from .workhub_signoff import record as record_signoff
            stamp=record_signoff(db,user,payload,project_id=item['project_id'],subject_id=key,subject_type='workflow',
                decision='approve' if action in {'quality_pass','approve_release','release'} else action,
                role={'quality':'Quality reviewer','release_approval':'Release approver','ready_release':'Release owner'}.get(stage,'Workflow owner'),
                basis={'item_id':key,'version':item['version'],'stage':stage,'action':action,'revision_id':revision,'run_id':review_run,'closure_checks':payload.get('closure_checks',{}),'deliverable_file_ids':payload.get('deliverable_file_ids',[])},documents=checked_documents)
            # Validate authenticated sign-off evidence before delivery gates; this
            # entire transition (including any stamp) rolls back on rejection.
            guard_delivery(db,item,action,payload)
            self.event(db,item,user,action,{'from':stage,'to':target,'comment':comment,'revision_id':revision,'run_id':review_run,'owner_id':item['owner_id'],'due_date':item.get('due_date'),'baseline_due':item.get('baseline_due'),'work_feedback_id':feedback_id,
                       'checked_run_id':checked_run[0] if checked_run else None,'approval_documents':checked_documents,'sign_off':stamp,
                       'reviewers':{field:item[field] for field in ('quality_id','approver_id','release_id')},
                       'deliverables_complete':payload.get('deliverables_complete'),
                       'deliverable_file_ids':payload.get('deliverable_file_ids',[]),'closure_checks':payload.get('closure_checks',{})})
            if action in {'request_changes','reject'}:
                db.execute('INSERT INTO issues VALUES(?,?,?,?,?,?,?,?,?)',(identity(),item['project_id'],key,comment,item['owner_id'],user['id'],'open',now,now))
            new=self.item(db,key);recipients=[new[NEXT_OWNER[target]],item['created_by'],item['owner_id']]
            self.notify(db,new,user['id'],recipients,STAGES[target]+': '+item['title'],comment or 'The workflow is ready for its next action.')
            return self.public(new)
    def add_update(self,user,key,payload):
        self.actor(user)
        with self.db(True) as db:
            item=self.item(db,key);self.contribute(db,item['project_id'],user);body=text(payload.get('body',''),8000,True)
            files=payload.get('file_ids',[])
            if not isinstance(files,list) or len(files)>100:raise HTTPException(400,'Attach at most 100 evidence files to one update.')
            for file_id in files:
                if not isinstance(file_id,str) or not db.execute('SELECT 1 FROM files WHERE id=? AND project_id=?',(file_id,item['project_id'])).fetchone():raise HTTPException(400,'Choose attachments from this project.')
            minutes=payload.get('minutes',0)
            if type(minutes) is not int or not 0<=minutes<=1440:raise HTTPException(400,'Enter working minutes in 0..1440.')
            work_date=day(payload.get('work_date') or date.today().isoformat())
            if work_date>date.today().isoformat():raise HTTPException(400,'Daily work entries cannot be in the future.')
            run_ids=payload.get('run_ids',[])
            if not isinstance(run_ids,list) or len(run_ids)>20:raise HTTPException(400,'Link at most 20 engineering results.')
            from backend.core import run_history
            valid_runs=[];selected_runs=[]
            for run_id in run_ids:
                try:record=run_history.read_record(str(run_id))
                except (OSError,ValueError):raise HTTPException(400,'Saved result not found.') from None
                if user['role']!='admin' and (record.get('user') or {}).get('id')!=user['id']:raise HTTPException(403,'You can share only your own saved results.')
                valid_runs.append({'id':record['id'],'kind':record['kind'],'testId':record.get('testId',''),'projectName':record.get('projectName','')})
                selected_runs.append(record)
            work_status=payload.get('work_status','');request_kind=payload.get('request_kind','progress')
            if work_status not in {'','not_started','in_progress','blocked','completed'} or request_kind not in {'progress','guidance','support','review_request'}:
                raise HTTPException(400,'Choose a valid work status and update purpose.')
            mentions=payload.get('mention_ids',[])
            active={u['id'] for u in self.users() if u['active']}
            if not isinstance(mentions,list) or len(mentions)>30 or any(type(v) is not int or v not in active for v in mentions):
                raise HTTPException(400,'Mention up to 30 active approved users.')
            mentions=sorted(set(mentions))
            if request_kind!='progress' and not mentions:raise HTTPException(400,'Choose a person for your support or review request.')
            key_update=identity();now=timestamp()
            db.execute('INSERT INTO updates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(key_update,item['project_id'],key,user['id'],body,work_date,minutes,encode(files),encode(valid_runs),now,item['quality_id'],'submitted' if minutes else 'none',''))
            db.execute('INSERT INTO update_context VALUES(?,?,?,?)',(key_update,work_status,request_kind,encode(mentions)))
            from .workhub_runs import link_saved
            for record in selected_runs:link_saved(db,user,item['project_id'],record,key_update)
            db.execute('UPDATE items SET updated_at=? WHERE id IN (?,?)',(now,key,item['project_id']))
            self.event(db,item,user,'daily_update',{'update_id':key_update,'minutes':minutes,'work_date':work_date})
            recipients=[item['created_by'],*mentions]
            recipients.extend(u['id'] for u in self.users() if re.search(r'@'+re.escape(u['username'])+r'(?!\w)',body,re.I))
            if request_kind!='progress':recipients=[i for i in recipients if i not in mentions]
            self.notify(db,item,user['id'],recipients,'Work update: '+item['title'],body[:1000])
            # Action requests are in-app records, independently resolvable by each recipient.
            if request_kind!='progress':
                for recipient in mentions:
                    notification=identity()
                    db.execute('INSERT INTO notifications VALUES(?,?,?,?,?,?,?,?,NULL)',(notification,recipient,user['id'],item['project_id'],item['id'],request_kind.replace('_',' ').title()+': '+item['title'],body[:3000],now))
                    db.execute('INSERT INTO update_requests VALUES(?,?,NULL)',(notification,key_update))
            if minutes:self.notify(db,item,user['id'],[item['quality_id']],'Time entry awaiting review: '+item['title'],f'{minutes} minutes recorded for {work_date}.')
            return {'id':key_update,'status':'saved'}
    def time_review(self,user,key,payload):
        self.actor(user)
        with self.db(True) as db:
            row=db.execute('SELECT * FROM updates WHERE id=?',(key,)).fetchone()
            if not row:raise HTTPException(404,'Time entry not found.')
            if row['reviewer_id']!=user['id']:raise HTTPException(403,'This time entry belongs to the selected reviewer.')
            if row['time_status']!='submitted':raise HTTPException(409,'This entry has already been reviewed.')
            status=payload.get('status');comment=text(payload.get('comment',''))
            if status not in {'approved','changes_requested'}:raise HTTPException(400,'Approve or request changes.')
            if status=='changes_requested' and not comment:raise HTTPException(400,'Add a short reason.')
            db.execute('UPDATE updates SET time_status=?,review_comment=? WHERE id=?',(status,comment,key))
            item=self.item(db,row['item_id']);self.event(db,item,user,'time_'+status,{'update_id':key,'comment':comment})
            self.notify(db,item,user['id'],[row['author_id']],'Time entry '+status.replace('_',' '),comment or row['body'][:500])
            return {'status':status}
    def resubmit_time(self,user,key,payload):
        self.actor(user)
        with self.db(True) as db:
            row=db.execute('SELECT * FROM updates WHERE id=?',(key,)).fetchone()
            if not row:raise HTTPException(404,'Time entry not found.')
            if row['author_id']!=user['id']:raise HTTPException(403,'Only the author can correct this time entry.')
            if row['time_status']!='changes_requested':raise HTTPException(409,'Only a returned time entry can be resubmitted.')
            minutes=payload.get('minutes');work_date=day(payload.get('work_date'));comment=text(payload.get('comment',''),4000,True)
            if type(minutes) is not int or not 1<=minutes<=1440:raise HTTPException(400,'Enter working minutes in 1..1440.')
            if not work_date or work_date>date.today().isoformat():raise HTTPException(400,'Choose today or an earlier work date.')
            item=self.item(db,row['item_id']);reviewer=self.user_id(item['quality_id'])
            db.execute("UPDATE updates SET minutes=?,work_date=?,reviewer_id=?,time_status='submitted',review_comment='' WHERE id=?",(minutes,work_date,reviewer,key))
            self.event(db,item,user,'time_resubmitted',{'update_id':key,'previous_minutes':row['minutes'],'minutes':minutes,'previous_work_date':row['work_date'],'work_date':work_date,'comment':comment})
            self.notify(db,item,user['id'],[reviewer],'Corrected time entry: '+item['title'],comment)
            return {'status':'submitted'}
    def notifications(self,user):
        with self.db() as db:
            rows=[dict(row) for row in db.execute('SELECT * FROM notifications WHERE recipient_id=? ORDER BY created_at DESC LIMIT 150',(user['id'],))]
            for row in rows:row['deliveries']=[dict(delivery) for delivery in db.execute('SELECT channel,status,detail FROM outbox WHERE notification_id=?',(row['id'],))]
            return {'items':rows,'unread':db.execute('SELECT COUNT(*) FROM notifications WHERE recipient_id=? AND read_at IS NULL',(user['id'],)).fetchone()[0]}

store=WorkHub()
