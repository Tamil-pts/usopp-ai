"""Reusable project creation presets, independent of approval workflows."""
import json
from fastapi import HTTPException
from .workhub import store as hub,identity,timestamp,text
from .workhub_quality import store as quality
from .workhub_workflow import validate_steps

DEFAULT_STEPS=[
 {'id':'requirements','title':'Requirements & Planning','description':'FRD, MOM, technical study and planning','phase':'development','days':1,'planned_hours':0,'milestone':True,'depends_on':[]},
 {'id':'development','title':'Development','description':'PLC, HMI, electrical or design','phase':'development','days':1,'planned_hours':0,'milestone':True,'depends_on':['requirements']},
 {'id':'validation','title':'Testing & Validation','description':'Test plan and validation report','phase':'quality','days':1,'planned_hours':0,'milestone':True,'depends_on':['development']},
 {'id':'approval','title':'FAT & Approval','description':'FAT documents and customer approval','phase':'quality','days':1,'planned_hours':0,'milestone':True,'depends_on':['validation']},
 {'id':'closure','title':'Closure','description':'Closure report and final delivery','phase':'release','days':1,'planned_hours':0,'milestone':True,'depends_on':['approval']},
]
def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS wh_project_templates(id TEXT PRIMARY KEY,name TEXT NOT NULL,owner_id INTEGER NOT NULL,shared INTEGER NOT NULL,content TEXT NOT NULL,version INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)')

def list_templates(user):
    hub.actor(user);quality.initialize()
    with hub.db(True) as db:
        schema(db);rows=[dict(r) for r in db.execute('SELECT * FROM wh_project_templates WHERE owner_id=? OR shared=1 OR ? ORDER BY name COLLATE NOCASE',(user['id'],user['role']=='admin'))]
        for row in rows:row['content']=json.loads(row['content']);row['shared']=bool(row['shared'])
    return {'items':[{'id':'default','name':'Default project template','shared':True,'version':1,'content':{'kind':'General','steps':DEFAULT_STEPS}}]+rows}

def save(user,payload):
    hub.actor(user);quality.initialize();name=text(payload.get('name',''),180,True)
    content=payload.get('content')
    if not isinstance(content,dict):raise HTTPException(400,'Provide project template details.')
    steps=validate_steps(content.get('steps',[]))
    if not steps:raise HTTPException(400,'A project template needs at least one workflow step.')
    assignees=content.get('assignees',{})
    if not isinstance(assignees,dict) or set(assignees)-{s['id'] for s in steps}:raise HTTPException(400,'Choose valid workflow assignees.')
    clean={'kind':text(content.get('kind','General'),50,True),'steps':steps,'assignees':{k:hub.user_id(v) for k,v in assignees.items()}}
    for key in ('objective','requirements','acceptance','additional','base_reference','developed_reference'):clean[key]=text(content.get(key,'') or '',8000)
    rows=content.get('requirement_items',[]);criteria=content.get('acceptance_items',[])
    if not isinstance(rows,list) or len(rows)>200 or not isinstance(criteria,list) or len(criteria)>200:raise HTTPException(400,'Use up to 200 requirement and acceptance rows.')
    clean['requirement_items']=[]
    for row in rows:
        if not isinstance(row,dict):raise HTTPException(400,'Provide structured requirement rows.')
        clean['requirement_items'].append({'description':text(row.get('description','') or '',8000),'category':text(row.get('category','') or '',200),'source_label':text(row.get('source_label','') or '',240),'priority':row.get('priority') if row.get('priority') in {'low','medium','high','urgent'} else 'medium'})
    clean['acceptance_items']=[text(v,8000) for v in criteria]
    flow=content.get('flowchart')
    if flow:
        if not isinstance(flow,dict):raise HTTPException(400,'Provide a structured flowchart.')
        from .workhub_intelligence import store as intelligence
        intelligence.validate_content('flowchart',flow);clean['flowchart']=flow
    shared=payload.get('shared',False)
    if type(shared) is not bool:raise HTTPException(400,'Choose whether to share the template.')
    key=identity();now=timestamp()
    with hub.db(True) as db:
        schema(db);db.execute('INSERT INTO wh_project_templates VALUES(?,?,?,?,?,1,?,?)',(key,name,user['id'],int(shared),quality.bounded(clean),now,now))
    return {'id':key,'name':name,'version':1}
