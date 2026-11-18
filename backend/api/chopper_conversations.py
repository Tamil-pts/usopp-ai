"""Private project conversation snapshots and review-only answer feedback."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.api.document_comparison import private
from backend.core.runtime import WORK
from backend.core.project_intelligence import opened

router=APIRouter(prefix='/api/assist/conversations',tags=['Chopper conversations'],dependencies=[Depends(private)])

def owner(user):return str(user['id'])+':'+str(user.get('createdAt',''))

@contextmanager
def database():
    folder=WORK/'chopper-conversations';folder.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(folder/'conversations.sqlite3',timeout=10)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS conversations(owner TEXT,project TEXT,value TEXT,updated TEXT,PRIMARY KEY(owner,project))')
        db.execute('CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,owner TEXT,project TEXT,value TEXT,status TEXT,created TEXT)')
        yield db
        db.commit()
    finally:db.close()

def access(user,project):
    try:return opened(project,user['id'])
    except (ValueError,PermissionError,FileNotFoundError):raise HTTPException(404,'Project conversation is unavailable.') from None

def checked_messages(messages,project):
    """Validate display shapes, without treating a saved snapshot as evidence."""
    def records(value):
        if not isinstance(value,list) or len(value)>10000 or any(not isinstance(v,dict) for v in value):
            raise HTTPException(400,'Invalid conversation records. Start a new chat.')
        return value
    for message in messages:
        if message.get('machineAnalysisProjectId') not in (None,project):raise HTTPException(400,'Conversation source belongs to another project.')
        for field in ('source','modelNotice'):
            if message.get(field) is not None and not isinstance(message[field],str):raise HTTPException(400,'Invalid conversation text.')
        if message.get('evidence') is not None:records(message['evidence'])
        machine=message.get('machineAnalysis')
        if machine is None:continue
        if not isinstance(machine,dict):raise HTTPException(400,'Invalid conversation analysis.')
        for field in ('project','coverage','taskExecution','detailCounts'):
            if field in machine and not isinstance(machine[field],dict):raise HTTPException(400,'Invalid conversation analysis fields.')
        for field in ('stateMachines','functions','callGraph','timers','edgeAndCounterBlocks','alarmCandidates','interlockCandidates','multipleWriters','retainedVariables','typeDefinitions','dataDependencies','hmiLinks','hardwareLinks','ladderNetworks','evidence','axes','writerTrace','signalWrites'):
            if field in machine:records(machine[field])
        for sequence in machine.get('stateMachines',[]):
            for transition in records(sequence.get('transitions',[])):
                conditions=transition.get('conditions',[])
                if not isinstance(conditions,list) or any(not isinstance(c,str) for c in conditions):raise HTTPException(400,'Invalid conversation conditions.')
                records(transition.get('actions',[]))
        for alarm in machine.get('alarmCandidates',[]):records(alarm.get('writers',[]))
    return [{key:value for key,value in m.items() if key in {'role','text','source','machineAnalysis','machineAnalysisProjectId','evidence','modelNotice'}} for m in messages]

@router.get('/feedback')
def feedback_list(request:Request):
    user=request.state.user
    with database() as db:
        rows=db.execute('SELECT id,project,value,status,created FROM feedback WHERE owner=? ORDER BY created DESC LIMIT 100',(owner(user),)).fetchall()
    return {'items':[{'id':r[0],'project':r[1],**json.loads(r[2]),'status':r[3],'created':r[4]} for r in rows],
            'notice':'Feedback is pending review. It never changes validation verdicts, approved knowledge or model weights.'}

@router.post('/feedback')
def feedback(payload:dict,request:Request):
    user=request.state.user;project=str(payload.get('projectId',''));access(user,project)
    vote=payload.get('vote');correction=str(payload.get('correction','')).strip()
    if vote not in ('useful','not_useful','correction') or len(correction)>8000:raise HTTPException(400,'Choose a feedback action and keep corrections within 8,000 characters.')
    if vote=='correction' and not correction:raise HTTPException(400,'Enter the correction for review.')
    value={'vote':vote,'correction':correction,'question':str(payload.get('question',''))[:12000],
           'answer':str(payload.get('answer',''))[:24000],'trainingEligible':False}
    key=uuid.uuid4().hex
    with database() as db:db.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?)',(key,owner(user),project,json.dumps(value), 'pending',datetime.now(timezone.utc).isoformat()))
    return {'id':key,'status':'pending','trainingEligible':False}

@router.get('/{project}')
def get_conversation(project:str,request:Request):
    user=request.state.user;access(user,project)
    with database() as db:row=db.execute('SELECT value,updated FROM conversations WHERE owner=? AND project=?',(owner(user),project)).fetchone()
    return {'messages':json.loads(row[0]) if row else [],'updated':row[1] if row else None,'snapshot':True}

@router.post('/{project}')
def save_conversation(project:str,payload:dict,request:Request):
    user=request.state.user;access(user,project)
    messages=payload.get('messages')
    if not isinstance(messages,list) or len(messages)>50 or any(not isinstance(m,dict) or m.get('role') not in ('user','assist') or not isinstance(m.get('text'),str) for m in messages):raise HTTPException(400,'Save up to 50 chat messages.')
    messages=checked_messages(messages,project)
    # This is untrusted history, not engineering evidence or an approved answer.
    encoded=json.dumps(messages,ensure_ascii=False,allow_nan=False)
    if len(encoded.encode('utf8'))>2*1024*1024:raise HTTPException(413,'Conversation exceeds the 2 MiB snapshot limit. Start a new conversation.')
    with database() as db:db.execute('INSERT OR REPLACE INTO conversations VALUES(?,?,?,?)',(owner(user),project,encoded,datetime.now(timezone.utc).isoformat()))
    return {'saved':True,'snapshot':True}
