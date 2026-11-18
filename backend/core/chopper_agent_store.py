"""Private agent diagnostics and reviewed examples; separate from approved PLC rules."""
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
import re
import sqlite3
import uuid
from backend.core.runtime import BASE

DATABASE=BASE/'chopper_agent.sqlite3'
DEFAULTS={'webEnabled':False,'webDomains':['www.br-automation.com','help.br-automation.com','docs.python.org','www.sqlite.org','docs.langchain.com'],
          'profiles':[],'roles':{'planner':'local','researcher':'local','reviewer':'local'}}


def owner(user):
    if not user or not isinstance(user.get('id'),int):raise PermissionError('Sign in to use the Chopper agent.')
    return str(user['id'])+':'+str(user.get('createdAt',''))


@contextmanager
def connect():
    DATABASE.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DATABASE,timeout=10) as db:
        db.row_factory=sqlite3.Row
        db.executescript('''CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,created TEXT NOT NULL,value TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS runs_owner ON runs(owner,created DESC);
        CREATE TABLE IF NOT EXISTS examples(id TEXT PRIMARY KEY,owner TEXT NOT NULL,run_id TEXT NOT NULL,
          status TEXT NOT NULL,value TEXT NOT NULL,reviewer TEXT,review_note TEXT);''')
        yield db


def settings():
    with connect() as db:row=db.execute('SELECT value FROM settings WHERE id=1').fetchone()
    return {**DEFAULTS,**(json.loads(row['value']) if row else {})}


def save_settings(user,payload):
    if user.get('role')!='admin':raise PermissionError('Only an administrator can configure agent connections.')
    from backend.core.chopper_agent_models import validate_profiles
    profiles=validate_profiles(payload.get('profiles',[]))
    roles=payload.get('roles',{})
    if not isinstance(roles,dict):raise ValueError('Agent roles must be an object.')
    ids={'local',*[p['id'] for p in profiles]}
    if any(roles.get(role,'local') not in ids for role in ('planner','researcher','reviewer')):raise ValueError('Choose a configured model profile for each role.')
    domains=payload.get('webDomains',DEFAULTS['webDomains'])
    if not isinstance(domains,list) or len(domains)>30 or any(not isinstance(d,str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,250})\.[a-z]{2,24}',d) or '..' in d for d in domains):
        raise ValueError('Enter up to 30 exact public domain names; wildcards and local addresses are not allowed.')
    value={'profiles':profiles,'roles':{role:roles.get(role,'local') for role in ('planner','researcher','reviewer')},
           'webEnabled':payload.get('webEnabled') is True,'webDomains':list(dict.fromkeys(domains))}
    with connect() as db:db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(value),))
    return value


def save_run(user,value):
    key=uuid.uuid4().hex
    value={**value,'id':key,'createdAt':datetime.now(timezone.utc).isoformat()}
    with connect() as db:db.execute('INSERT INTO runs VALUES(?,?,?,?)',(key,owner(user),value['createdAt'],json.dumps(value,ensure_ascii=False,allow_nan=False)))
    return value


def run(user,key):
    with connect() as db:row=db.execute('SELECT value FROM runs WHERE id=? AND owner=?',(str(key),owner(user))).fetchone()
    if not row:raise PermissionError('This agent run is unavailable for this account.')
    return json.loads(row['value'])


def history(user):
    with connect() as db:rows=db.execute('SELECT id,created,value FROM runs WHERE owner=? ORDER BY created DESC LIMIT 30',(owner(user),)).fetchall()
    return [{'id':r['id'],'createdAt':r['created'],'question':json.loads(r['value']).get('question',''),
             'status':json.loads(r['value']).get('status'),'mode':json.loads(r['value']).get('mode')} for r in rows]


def propose(user,key,note):
    value=run(user,key)
    if value.get('mode')!='evidence' or value.get('status')!='evidence_ready':raise ValueError('Only a completed evidence run can be submitted for example review.')
    if not str(note).strip() or len(str(note))>2000:raise ValueError('Describe the reviewed lesson in up to 2,000 characters.')
    example={'question':value['question'],'note':str(note),'runId':key,
             'facts':value.get('facts',[]),'sources':value.get('sources',[]),
             'evidenceDigest':hashlib.sha256(json.dumps(value.get('facts'),sort_keys=True).encode()).hexdigest()}
    eid=uuid.uuid4().hex
    with connect() as db:db.execute('INSERT INTO examples VALUES(?,?,?,?,?,?,?)',(eid,owner(user),key,'pending',json.dumps(example),None,None))
    return {'id':eid,'status':'pending','weightsChanged':False}


def examples(user):
    with connect() as db:
        rows=db.execute('SELECT * FROM examples WHERE owner=? OR ?=1 ORDER BY rowid DESC LIMIT 100',(owner(user),int(user.get('role')=='admin'))).fetchall()
    return [{'id':r['id'],'status':r['status'],'reviewer':r['reviewer'],'reviewNote':r['review_note'],**json.loads(r['value'])} for r in rows]


def review(user,key,approve,note):
    if user.get('role')!='admin':raise PermissionError('An independent administrator must review this example.')
    if not str(note).strip() or len(str(note))>2000:raise ValueError('Record a review reason in up to 2,000 characters.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM examples WHERE id=?',(str(key),)).fetchone()
        if not row:raise ValueError('Review example not found.')
        if row['owner']==owner(user):raise PermissionError('The example author cannot approve their own example.')
        if row['status']!='pending':raise ValueError('This example already has a review decision.')
        db.execute('UPDATE examples SET status=?,reviewer=?,review_note=? WHERE id=?',('approved' if approve else 'rejected',owner(user),str(note),key))
    return {'id':key,'status':'approved' if approve else 'rejected','weightsChanged':False}


def lessons(user):
    with connect() as db:rows=db.execute("SELECT value FROM examples WHERE owner=? AND status='approved' ORDER BY rowid DESC LIMIT 5",(owner(user),)).fetchall()
    return [json.loads(row['value']) for row in rows]
