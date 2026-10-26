"""Fictional FRD training material and private practice records.

These tables never create WorkHub projects, production approvals, deliveries or
document sequence entries. Only the owner can open or change a practice copy.
"""
from copy import deepcopy
import json
from fastapi import HTTPException
from . import store,branding,pdf_templates,documents
from .store import hub,identity,timestamp

TITLE='Sample Project — Ring Frame Motor Trip Alarm Modification'
NOTICE='FICTIONAL TRAINING EXAMPLE. No real customer project, physical test result, signature or approval is represented.'
READY=set()


def example():
    statements=[
        ('Engineer A (fictional)','The training PLC shall detect TRAIN_MOTOR_TRIP and latch TRAIN_TRIP_ALARM.','The training PLC shall detect TRAIN_MOTOR_TRIP and latch TRAIN_TRIP_ALARM.'),
        ('Engineer B (fictional)','Motor trip வந்தால் HMI alarm காட்ட வேண்டும்.','The HMI shall display the motor-trip alarm while it is active.'),
        ('Engineer A (fictional)','TRAIN_RESET_REQUEST shall clear the alarm only after trip feedback is clear and reviewed reset conditions are satisfied.','TRAIN_RESET_REQUEST shall clear the alarm only after trip feedback is clear and reviewed reset conditions are satisfied.'),
        ('Engineer B (fictional)','Record alarm activation and clearance where the reviewed history system supports it.','Record alarm activation and clearance where the reviewed history system supports it.'),
        ('Engineer A (fictional)','Confirm power-cycle retention and the motor-running reset permissive before approval. Owners and deadlines are not yet assigned.','Confirm power-cycle retention and the motor-running reset permissive before approval. Owners and deadlines are not yet assigned.')]
    segments=[{'id':'S'+str(i+1),'start':i*12,'end':i*12+10,'speaker':speaker,'text':original,'original_text':original,'english':english,'uncertain':False} for i,(speaker,original,english) in enumerate(statements)]
    sources=[{'id':s['id'],'label':'Fictional meeting / '+s['id'],'text':s['english'],'start':s['start'],'end':s['end'],'type':'training_transcript'} for s in segments]
    reqs=[
      {'id':'FR-001','title':'Motor trip detection','description':statements[0][1],'trigger':'TRAIN_MOTOR_TRIP active','expected_behavior':'Latch TRAIN_TRIP_ALARM','acceptance_criteria':'The alarm registers for a verified training trip input.','source_ids':['S1']},
      {'id':'FR-002','title':'HMI alarm indication','description':statements[1][2],'trigger':'Training alarm active','expected_behavior':'Display the corresponding HMI alarm indication.','acceptance_criteria':'The HMI indication follows the reviewed alarm state.','source_ids':['S2']},
      {'id':'FR-003','title':'Controlled manual alarm reset','description':statements[2][1],'trigger':'TRAIN_RESET_REQUEST','expected_behavior':'Keep the alarm latched while the trip remains active.','acceptance_criteria':'An active trip prevents clearing; trip-clear reset follows the confirmed engineering conditions.','source_ids':['S3','S5']},
      {'id':'FR-004','title':'Alarm history','description':statements[3][1],'trigger':'Alarm activation or clearance','expected_behavior':'Record events where the reviewed history system supports it.','acceptance_criteria':'Recorded events can be retrieved when history is in scope.','source_ids':['S4']}]
    reqs=[{**r,'subsystem':'Ring Frame training PLC / HMI','mandatory':True,'change':'new'} for r in reqs]
    nodes=[('monitor','start','Monitor training trip input',['FR-001'],['TRAIN_MOTOR_TRIP'],0,0),
      ('trip','decision','Trip detected?',['FR-001'],['TRAIN_MOTOR_TRIP'],310,0),
      ('latch','alarm','Latch alarm; display on HMI',['FR-001','FR-002'],['TRAIN_TRIP_ALARM'],620,0),
      ('reset','interlock','Trip clear AND reset requested under reviewed conditions?',['FR-003'],['TRAIN_RESET_REQUEST'],620,170),
      ('clear','process','Clear alarm and record event where supported',['FR-003','FR-004'],[],930,170)]
    flow={'nodes':[{'id':i,'position':{'x':x,'y':y},'data':{'kind':kind,'label':label,'requirement_ids':refs,'plc_references':tags,'source_ids':list({s for r in reqs if r['id'] in refs for s in r['source_ids']})}} for i,kind,label,refs,tags,x,y in nodes],
      'edges':[{'id':i,'source':a,'target':b,'label':label} for i,a,b,label in [('e1','monitor','trip',''),('e2','trip','monitor','No'),('e3','trip','latch','Yes'),('e4','latch','reset',''),('e5','reset','reset','No — keep alarm latched'),('e6','reset','clear','Yes')]],
      'sources':sources,'notice':'Fictional illustrative sequence. Reset permissives and retention require engineering review.'}
    cases=[{'id':'FAT-'+str(i+1).zfill(3),'requirement_ids':refs,'objective':objective,'procedure':action,'expected_result':expected,'acceptance_criteria':expected,'outcome':'not_run','execution':None} for i,(refs,objective,action,expected) in enumerate([
      (['FR-001'],'Trip detection','Apply the fictional training trip input.','The training alarm registers.'),
      (['FR-002'],'HMI indication','Activate the training alarm.','The HMI shows the reviewed alarm state.'),
      (['FR-003'],'Reset interlock','Request reset while the trip remains active.','The alarm remains latched.'),
      (['FR-003'],'Permitted reset','Clear the trip and use the reviewed reset conditions.','The alarm clears only when those conditions are met.'),
      (['FR-004'],'History','Activate and clear a training alarm when history is in scope.','The history system records the events.')])]
    return {'schema_version':1,'title':TITLE,'notice':NOTICE,'sample_version':'1','project':{'title':TITLE,'number':'SAMPLE-RF-001','customer':'Imaginary Textile Training Ltd. (fictional)','machine':'Ring Frame training system','department':'ES','team':'PLC','scope':'Illustrative trip alarm, HMI indication, controlled reset and optional history. Existing machine safety is outside this training example.'},
      'transcript':{'segments':segments,'notice':'Manually authored training transcript and interpretation; no speech-recognition accuracy is implied.'},
      'mom':{'meeting_subject':'Fictional motor-trip alarm discussion','meeting_date':None,'participants':['Engineer A (fictional)','Engineer B (fictional)'],
        'discussion_summary':[{'text':'Review trip detection, HMI indication, reset interlocks and optional event history.','source_ids':['S1','S2','S3','S4']}],
        'decisions':[{'text':statements[2][1],'source_ids':['S3']}],'engineering_requirements':[{'text':s['text'],'source_ids':[s['id']]} for s in sources[:4]],
        'actions':[{'text':'Clarify retention and reset permissives.','responsible':None,'target_date':None,'source_ids':['S5']}],
        'clarifications':[{'question':statements[4][1],'source_ids':['S5']}],'sources':sources,'status':'training_example'},
      'frd':{'purpose':'Illustrate a traceable motor-trip alarm modification using fictional training signals.','scope':'Training PLC alarm and HMI feedback only. Confirm actual safety and reset behavior separately.',
        'acceptance_summary':'Execute the linked FAT cases only after the open conditions are reviewed. All sample cases remain Not Tested.',
        'requirements':reqs,'sources':sources,'flowchart':flow,'sections':[{'heading':'Operating sequence','text':'See the editable linked flowchart.'},{'heading':'PLC / HMI behavior','text':'See FR-001 through FR-004.'},{'heading':'Open clarifications','text':statements[4][1]}]},
      'fat':{'cases':cases},'history':[{'revision':'R00','status':'Fictional draft','reason':'Built-in training material; not an engineering approval.'}]}


def initialize():
    store.initialize()
    key=str(hub.root.resolve())
    if key in READY:return
    with hub.db(True) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS wh_training_workspaces(id TEXT PRIMARY KEY,owner_id INTEGER NOT NULL,
          version INTEGER NOT NULL,data TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS wh_training_owner ON wh_training_workspaces(owner_id,updated_at);
        CREATE TABLE IF NOT EXISTS wh_training_history(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,version INTEGER NOT NULL,
          data TEXT NOT NULL,actor_id INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(workspace_id,version));
        CREATE TABLE IF NOT EXISTS wh_training_proposals(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,base_version INTEGER NOT NULL,
          data TEXT NOT NULL,created_at TEXT NOT NULL);''')
    READY.add(key)


def owned(db,user,key):
    store.personal(user)
    row=db.execute('SELECT * FROM wh_training_workspaces WHERE id=? AND owner_id=?',(key,user['id'])).fetchone()
    if not row:raise HTTPException(404,'This private practice copy was not found.')
    history=[{'version':r['version'],'status':json.loads(r['data']).get('practice_status','draft'),'actor_id':r['actor_id'],'created_at':r['created_at']} for r in db.execute('SELECT version,data,actor_id,created_at FROM wh_training_history WHERE workspace_id=? ORDER BY version DESC LIMIT 100',(key,))]
    return {**dict(row),'data':json.loads(row['data']),'revision_history':history}


def list_copies(user):
    initialize();store.personal(user)
    with hub.db() as db:return [dict(r) for r in db.execute('SELECT id,version,status,created_at,updated_at FROM wh_training_workspaces WHERE owner_id=? ORDER BY updated_at DESC LIMIT 30',(user['id'],))]


def create(user):
    initialize();store.personal(user)
    with hub.db(True) as db:
        if db.execute('SELECT count(*) FROM wh_training_workspaces WHERE owner_id=?',(user['id'],)).fetchone()[0]>=30:raise HTTPException(409,'Reuse an existing practice copy (limit 30).')
        key=identity();value=example();value['project']['number']='PRACTICE-'+key[:8].upper();now=timestamp();raw=store.bounded(value)
        db.execute('INSERT INTO wh_training_workspaces VALUES(?,?,?,?,?,?,?)',(key,user['id'],1,raw,'draft',now,now))
        db.execute('INSERT INTO wh_training_history VALUES(?,?,?,?,?,?)',(identity(),key,1,raw,user['id'],now))
        return owned(db,user,key)


def get(user,key):
    initialize()
    with hub.db() as db:return owned(db,user,key)


def save(user,key,payload):
    initialize()
    with hub.db(True) as db:
        row=owned(db,user,key)
        if type(payload.get('version')) is not int or payload['version']!=row['version']:raise HTTPException(409,'This practice copy changed. Reload before saving.')
        value=deepcopy(row['data'])
        for field in ['frd','mom','transcript']:
            if field in payload:
                if not isinstance(payload[field],dict):raise HTTPException(400,'Use structured training content.')
                value[field]=payload[field]
        store.bounded(value,2*1024*1024);store.pi.validate_content('frd',value['frd'])
        known_sources={s['id'] for s in value['frd'].get('sources',[])}
        for r in value['frd']['requirements']:
            refs=r.get('source_ids',[])
            if not isinstance(refs,list) or any(not isinstance(ref,str) or ref not in known_sources for ref in refs):raise HTTPException(400,'Use source references from this practice FRD.')
        if value['frd'].get('flowchart'):
            store.pi.validate_content('flowchart',value['frd']['flowchart'])
            ids={r['id'] for r in value['frd']['requirements']}
            if any(ref not in ids for n in value['frd']['flowchart']['nodes'] for ref in n.get('data',{}).get('requirement_ids',[])):raise HTTPException(400,'Link diagram nodes to requirements in this practice FRD.')
        status='training_review' if payload.get('submit_for_review') is True else 'draft'
        value['practice_status']=status
        raw=store.bounded(value,2*1024*1024);now=timestamp();version=row['version']+1
        db.execute('UPDATE wh_training_workspaces SET data=?,version=?,status=?,updated_at=? WHERE id=?',(raw,version,status,now,key))
        db.execute('INSERT INTO wh_training_history VALUES(?,?,?,?,?,?)',(identity(),key,version,raw,user['id'],now))
        return owned(db,user,key)


def assist(user,key,payload):
    from backend.core.workhub_intelligence.local_ai import llm_json
    from backend.core.workhub_intelligence.processing import unsupported_values,layout_graph
    row=get(user,key)
    if payload.get('version')!=row['version']:raise HTTPException(409,'Save or reload the practice copy before asking Chopper.')
    content=row['data']['frd'];known={r['id'] for r in content['requirements']};action=payload.get('action','analyze')
    if action not in {'analyze','clarify','rewrite','flowchart'}:raise HTTPException(400,'Choose a supported FRD assistance action.')
    sources=[{'id':r['id'],'text':json.dumps(r,ensure_ascii=False)} for r in content['requirements']]
    result=llm_json('This is fictional FRD training, not a real machine project. Return {"answer":"...","source_ids":["FR-001"],"requirement_updates":[],"clarifications":[],"flowchart":null}. '
      'For rewrite, requirement_updates contain existing id,title,description,trigger,expected_behavior,acceptance_criteria,source_ids. '
      'For flowchart, return nodes with id,position:{x:0,y:0},data:{kind:"process",label:"...",requirement_ids:["FR-001"],source_ids:["FR-001"]} and edges with id,source,target,label. '
      'Use only the supplied training sources. Preserve unknown reset/retention conditions as clarification questions. Never invent numbers, tags, results, names or approvals.',
      {'action':action,'question':store.text(payload.get('question',''),3000),'sources':sources})
    refs=result.get('source_ids',[])
    if not isinstance(refs,list) or not refs or any(r not in known for r in refs):raise HTTPException(422,'Chopper did not return valid training source references.')
    for update in result.get('requirement_updates',[]):
        if not isinstance(update,dict) or update.get('id') not in known:raise HTTPException(422,'A proposed update is outside this training FRD.')
        source=' '.join(s['text'] for s in sources if s['id'] in refs)
        if unsupported_values(source,' '.join(str(update.get(k) or '') for k in ['description','trigger','expected_behavior','acceptance_criteria'])):raise HTTPException(422,'A proposal introduced an unsupported technical value or PLC tag.')
    flow=result.get('flowchart')
    if flow:
        flow['nodes']=layout_graph(flow.get('nodes',[]),flow.get('edges',[]));store.pi.validate_content('flowchart',flow)
        if any(ref not in known for n in flow['nodes'] for ref in n.get('data',{}).get('requirement_ids',[])):raise HTTPException(422,'A flowchart proposal references unknown training requirements.')
    with hub.db(True) as db:
        current=owned(db,user,key)
        if current['version']!=row['version']:raise HTTPException(409,'The practice copy changed during the proposal. Ask again.')
        proposal=identity();db.execute('INSERT INTO wh_training_proposals VALUES(?,?,?,?,?)',(proposal,key,row['version'],store.bounded(result),timestamp()))
    return {'id':proposal,'base_version':row['version'],'proposal':result,'notice':'Private Chopper proposal. Review before applying; no real project is changed.'}


def apply(user,key,payload):
    initialize()
    with hub.db() as db:
        row=owned(db,user,key);proposal=db.execute('SELECT * FROM wh_training_proposals WHERE id=? AND workspace_id=?',(payload.get('proposal_id'),key)).fetchone()
        if not proposal or proposal['base_version']!=row['version']:raise HTTPException(409,'This proposal is stale. Ask Chopper again.')
        if payload.get('reviewed') is not True:raise HTTPException(400,'Review the proposal before applying it.')
        result=json.loads(proposal['data']);content=deepcopy(row['data']['frd'])
        if payload.get('flowchart') and result.get('flowchart'):content['flowchart']=result['flowchart']
        if payload.get('updates'):
            for update in result.get('requirement_updates',[]):
                for r in content['requirements']:
                    if r['id']==update['id']:
                        for field in ['title','description','trigger','expected_behavior','acceptance_criteria']:
                            if field in update:r[field]=store.text(update[field] or '',8000)
    return save(user,key,{'version':row['version'],'frd':content})


def pdf(user,key=None):
    initialize();store.personal(user);row=get(user,key) if key else None;data=row['data'] if row else example()
    with hub.db() as db:
        layout=branding.template(db,'frd',{})['data'];value=pdf_templates.preview(db,layout)
    value.update(title='Functional Requirements Document — Training',project_name=data['project']['title'],project_number=data['project']['number'],
        number='PRACTICE-FRD-'+key[:8].upper() if key else 'PTPL-ES-PLC-FRD-SAMPLE-001',revision='R'+str(row['version'] if row else 0).zfill(2),approved=False)
    value['customer']={'name':data['project']['customer'],'address':'Fictional training customer only','logo_data':''}
    value['metadata']=[['Project',data['project']['title']],['Project number',data['project']['number']],['Customer',data['project']['customer']],['Machine / System',data['project']['machine']],
        ['Status',NOTICE],['Prepared by',user['username']+' (practice)' if row else 'Fictional training authors'],['Reviewed by','Not approved'],['Approved by','Not approved']]
    value['sections']=pdf_templates.blocks({**data['frd'],'cases':data['fat']['cases']})
    history=[['Practice '+str(r['version']),r['status'],r['created_at']] for r in reversed(row['revision_history'])] if row else [[r['revision'],r['status'],r['reason']] for r in data['history']]
    value['sections']+=[{'key':'details','title':'Revision history','text':'Training history only; no production approvals.','columns':['Revision','Status','Recorded'],
        'rows':history,'svg':''}]
    return pdf_templates.render(value)[0]
