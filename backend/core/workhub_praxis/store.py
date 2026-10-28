import json
import math
import threading
from fastapi import HTTPException
from backend.core import workhub_organization as org
from backend.core.workhub import store as hub,identity,timestamp,text,encode,day

LOCK=threading.RLock();READY=set()
LEVELS=['Awareness','Basic','Proficient','Advanced','Expert']


def initialize():
    org.initialize();key=str(hub.root.resolve())
    if key in READY:return
    with LOCK:
        if key in READY:return
        with hub.db(True) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS px_configuration(version INTEGER PRIMARY KEY,content TEXT NOT NULL,author_id INTEGER NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS px_assessments(
              id TEXT PRIMARY KEY,subject_id INTEGER NOT NULL,period_id TEXT NOT NULL,template_id TEXT NOT NULL,
              reviewer_id INTEGER NOT NULL,created_by INTEGER NOT NULL,current_revision TEXT,approved_revision TEXT,
              status TEXT NOT NULL DEFAULT 'draft',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS px_assessment_period ON px_assessments(subject_id,period_id,template_id);
            CREATE TABLE IF NOT EXISTS px_revisions(
              id TEXT PRIMARY KEY,assessment_id TEXT NOT NULL,number INTEGER NOT NULL,content TEXT NOT NULL,
              methodology TEXT NOT NULL,author_id INTEGER NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS px_reviews(
              id TEXT PRIMARY KEY,assessment_id TEXT NOT NULL,revision_id TEXT NOT NULL,action TEXT NOT NULL,
              actor_id INTEGER NOT NULL,comment TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS px_development(
              id TEXT PRIMARY KEY,subject_id INTEGER NOT NULL,competency_id TEXT NOT NULL,title TEXT NOT NULL,
              description TEXT NOT NULL,target_level INTEGER,due_date TEXT NOT NULL,status TEXT NOT NULL,
              project_id TEXT,task_id TEXT,version INTEGER NOT NULL,created_by INTEGER NOT NULL,updated_at TEXT NOT NULL);
            ''')
        READY.add(key)


def number(value,low,high,label,integer=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high or integer and type(value)is not int:
        raise HTTPException(400,label+' is outside its allowed range.')
    return value


def configuration(db):
    row=db.execute('SELECT * FROM px_configuration ORDER BY version DESC LIMIT 1').fetchone()
    return {'version':row['version'],'content':json.loads(row['content'])} if row else {'version':0,'content':{'competencies':[],'templates':[],'periods':[],'levels':LEVELS}}


def authorize(db,user,subject):
    org.personal(user);org.person(subject,False)
    if subject not in org.managed_people(db,user):raise HTTPException(403,'This confidential Competency Hub profile is outside your reporting or team responsibilities.')


def manager(db,user):
    org.personal(user)
    if user['role']!='admin' and not (org.managed_people(db,user)-{user['id']}):raise HTTPException(403,'Competency Hub configuration requires Admin or an assigned team administrator.')


def audit(db,user,assessment,revision,action,comment=''):
    db.execute('INSERT INTO px_reviews VALUES(?,?,?,?,?,?,?)',(identity(),assessment,revision,action,user['id'],text(comment,4000),timestamp()))


def save_configuration(user,payload):
    initialize()
    with hub.db(True) as db:
        manager(db,user);previous=configuration(db)
        if payload.get('version')!=previous['version']:raise HTTPException(409,'Competency Hub configuration changed. Refresh before saving.')
        content=payload.get('content')
        if not isinstance(content,dict):raise HTTPException(400,'Provide the Competency Hub configuration.')
        value={'levels':LEVELS,'competencies':[],'templates':[],'periods':[]};seen=set()
        for kind in ('competencies','templates','periods'):
            rows=content.get(kind,[])
            if not isinstance(rows,list) or len(rows)>500:raise HTTPException(400,'Too many configuration records.')
            for raw in rows:
                if not isinstance(raw,dict):raise HTTPException(400,'Use structured configuration records.')
                key=text(raw.get('id') or identity(),80,True)
                if key in seen:raise HTTPException(400,'Configuration identifiers must be unique.')
                seen.add(key)
                row={'id':key,'name':text(raw.get('name',''),160,True),'active':raw.get('active',True)}
                if type(row['active'])is not bool:raise HTTPException(400,'Choose active or archived.')
                if kind=='periods':
                    row.update(start=day(raw.get('start')),end=day(raw.get('end')))
                    if not row['start'] or not row['end'] or row['end']<row['start']:raise HTTPException(400,'An assessment period needs valid start and finish dates.')
                else:
                    row.update(department_id=raw.get('department_id') or '',description=text(raw.get('description',''),4000))
                    org.unit(db,row['department_id'],'department',include_archived=not row['active'])
                if kind=='competencies':
                    row.update(category=text(raw.get('category',''),120,True),criteria=text(raw.get('criteria',''),4000,True),review_frequency_days=number(raw.get('review_frequency_days',90),7,730,'Review frequency',True))
                if kind=='templates':
                    row.update(role_id=raw.get('role_id') or '',method=raw.get('method','weighted_mean'),competencies=[],performance=[])
                    role=org.unit(db,row['role_id'],'role',False,include_archived=not row['active'])
                    if role['department_id'] and role['department_id']!=row['department_id']:raise HTTPException(400,'Choose a professional role within the model department.')
                    if not isinstance(row['method'],str) or row['method'] not in {'weighted_mean','weighted_geometric','minimum'}:raise HTTPException(400,'Choose a supported performance calculation.')
                    for field in ('competencies','performance'):
                        entries=raw.get(field,[])
                        if not isinstance(entries,list) or len(entries)>100:raise HTTPException(400,'A role model supports up to 100 dimensions.')
                        ids=set()
                        for entry in entries:
                            if not isinstance(entry,dict):raise HTTPException(400,'Provide a structured measurement dimension.')
                            eid=text(entry.get('id') or identity(),80,True)
                            if eid in ids:raise HTTPException(400,'A model dimension is duplicated.')
                            ids.add(eid)
                            item={'id':eid,'weight':number(entry.get('weight',1),0.01,1000,'Measurement weight')}
                            if field=='competencies':item.update(competency_id=text(entry.get('competency_id',''),80,True),required_level=number(entry.get('required_level',3),1,5,'Required proficiency',True))
                            else:item.update(name=text(entry.get('name',''),160,True),criteria=text(entry.get('criteria',''),4000,True),source=text(entry.get('source','reviewer'),80,True))
                            row[field].append(item)
                value[kind].append(row)
        competencies={c['id']:c for c in value['competencies']}
        for model in value['templates']:
            bindings=[b['competency_id'] for b in model['competencies']]
            if len(bindings)!=len(set(bindings)):raise HTTPException(400,'Each competency may occur only once in a role model.')
            for binding in model['competencies']:
                c=competencies.get(binding['competency_id'])
                if not c:raise HTTPException(400,'A role model refers to a missing competency.')
                if c['department_id'] and model['department_id']!=c['department_id']:raise HTTPException(400,'Keep role competencies within their department or use a shared competency.')
        # Preserve definitions that historical assessment snapshots reference.
        for kind in ('competencies','templates','periods'):
            old={r['id']:r for r in previous['content'][kind]};new={r['id']:r for r in value[kind]}
            if not old.keys()<=new.keys():raise HTTPException(409,'Archive configuration records instead of deleting their history.')
        if user['role']!='admin':
            departments={org.profile(db,uid)['department_id'] for uid in org.managed_people(db,user)-{user['id']}}-{''}
            if value['periods']!=previous['content']['periods']:raise HTTPException(403,'Only Admin can configure company assessment periods.')
            for kind in ('competencies','templates'):
                old={r['id']:r for r in previous['content'][kind]}
                for row in value[kind]:
                    if row!=old.get(row['id']) and (row['department_id'] not in departments or old.get(row['id'],row)['department_id'] not in departments):raise HTTPException(403,'Configure only your managed departments.')
        revision=previous['version']+1
        db.execute('INSERT INTO px_configuration VALUES(?,?,?,?)',(revision,encode(value),user['id'],timestamp()))
        return {'version':revision,'content':value}
