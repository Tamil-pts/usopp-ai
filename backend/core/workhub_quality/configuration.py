"""Versioned procedures, templates and atomic company numbering."""
from copy import deepcopy
from datetime import datetime,timezone
from string import Formatter
from zoneinfo import ZoneInfo
import json
import re
from fastapi import HTTPException
from . import store
from .store import hub,timestamp,text

DEFAULT={
 'project_prefix':'',
 'company':'PTPL','department':'ES','team':'PLC','separator':'-',
 'pattern':'{COMPANY}{SEP}{DEPARTMENT}{SEP}{TEAM}{SEP}{DOCTYPE}{SEP}{YEAR}{SEP}{SEQ}',
 'sequence_scope':'doctype_year','sequence_start':1,'sequence_width':3,'revision_pattern':'R{REV}','revision_width':2,'timezone':'UTC',
 'branding':{'name':'PTPL','subtitle':'Engineering Services / PLC','accent':'#0b6472','logo_file_id':None},
 'codes':{'frd':'FRD','corrections':'CN','test':'TR','fat':'FAT','quality':'QA','closure':'PC'},
 'default_profile':{'required_stages':list(store.STAGES),'independent_review':True,'allow_waivers':True,
     'require_customer_acceptance':True,'require_test_evidence':True,'required_project_fields':['customer','machine','scope'],
     'procedure':'Engineering verification and approved disposition are required before closure.'},
 'project_profiles':{},
 'templates':{key:{'version':'1','title':title,'sections':[], 'fat_items':[]} for key,title in store.STAGES.items()}}

def admin(user):
    store.personal(user)
    if user['role']!='admin':raise HTTPException(403,'Only Admin can change company document controls or generate date-range ISO packs.')
def current(db):
    row=db.execute('SELECT * FROM qc_settings WHERE id=1').fetchone()
    return {'version':row['version'],'configuration':json.loads(row['configuration']),'updated_at':row['updated_at']} if row else {'version':0,'configuration':deepcopy(DEFAULT),'updated_at':None}
def profile(config,kind):return deepcopy(config['project_profiles'].get(kind,config['default_profile']))

def _pattern(value,fields,required):
    value=text(value,240,True)
    try:
        found=[]
        for literal,field,spec,conversion in Formatter().parse(value):
            if field is not None:
                if field not in fields or spec or conversion:raise ValueError()
                found.append(field)
            if any(c in literal for c in '\r\n\x00<>'):raise ValueError()
    except ValueError:raise HTTPException(400,'Numbering patterns support plain allowlisted tokens only.') from None
    if required not in found:raise HTTPException(400,'The pattern must include {'+required+'}.')
    return value
def _profile(value):
    if not isinstance(value,dict):raise HTTPException(400,'Provide a structured project quality procedure.')
    stages=value.get('required_stages',list(store.STAGES))
    if not isinstance(stages,list) or any(s not in store.STAGES for s in stages):raise HTTPException(400,'Choose supported workflow stages.')
    stages=list(dict.fromkeys([*stages,'quality','closure']))
    fields=value.get('required_project_fields',[])
    if not isinstance(fields,list) or any(s not in {'customer','machine','scope'} for s in fields):raise HTTPException(400,'Choose customer, machine or scope as required project context.')
    result={'required_stages':stages,'required_project_fields':list(dict.fromkeys(fields)),'procedure':text(value.get('procedure',''),4000)}
    for key in ('independent_review','allow_waivers','require_customer_acceptance','require_test_evidence'):
        if type(value.get(key,True)) is not bool:raise HTTPException(400,'Use true or false procedure options.')
        result[key]=value.get(key,True)
    from backend.core.workhub_workflow import validate_steps,validate_rules
    result['workflow_steps']=validate_steps(value.get('workflow_steps',[]))
    result['validation_rules']=validate_rules(value.get('validation_rules',[]))
    return result

def validate(value):
    store.bounded(value,1024*1024)
    if not isinstance(value,dict):raise HTTPException(400,'Provide company document settings.')
    clean=deepcopy(DEFAULT)
    prefix=text(value.get('project_prefix',''),60)
    if prefix and not re.fullmatch(r'[A-Za-z0-9_. -]+',prefix):raise HTTPException(400,'Use letters, digits and simple separators for the project prefix.')
    clean['project_prefix']=prefix
    for field in ('company','department','team'):
        val=text(value.get(field,clean[field]),24,True)
        if not re.fullmatch(r'[A-Za-z0-9_]{1,24}',val):raise HTTPException(400,'Use letters, digits or underscores for company numbering codes.')
        clean[field]=val
    separator=value.get('separator','-')
    if not isinstance(separator,str) or len(separator)>3 or any(c not in '-_./ ' for c in separator):raise HTTPException(400,'Use a separator of up to three punctuation or space characters.')
    clean['separator']=separator
    clean['pattern']=_pattern(value.get('pattern',clean['pattern']),{'COMPANY','DEPARTMENT','TEAM','DOCTYPE','YEAR','SEQ','SEP'},'SEQ')
    clean['revision_pattern']=_pattern(value.get('revision_pattern','R{REV}'),{'REV'},'REV')
    for field,lo,hi in [('sequence_start',1,999999999),('sequence_width',1,10),('revision_width',1,6)]:
        val=value.get(field,clean[field])
        if type(val) is not int or not lo<=val<=hi:raise HTTPException(400,'Sequence/revision widths and start must be valid whole numbers.')
        clean[field]=val
    scope=value.get('sequence_scope','doctype_year')
    if scope not in {'doctype_year','doctype','global_year','global'}:raise HTTPException(400,'Choose a supported atomic sequence scope.')
    clean['sequence_scope']=scope
    try:ZoneInfo(value.get('timezone','UTC'))
    except (KeyError,TypeError,ValueError):raise HTTPException(400,'Use a valid company timezone.') from None
    clean['timezone']=value.get('timezone','UTC')
    codes=value.get('codes',clean['codes'])
    for stage in store.STAGES:
        code=codes.get(stage) if isinstance(codes,dict) else None
        if not isinstance(code,str) or not re.fullmatch('[A-Za-z0-9_]{1,20}',code):raise HTTPException(400,'Provide a short document code for every stage.')
        clean['codes'][stage]=code
    brand=value.get('branding',clean['branding'])
    if not isinstance(brand,dict) or not re.fullmatch('#[a-fA-F0-9]{6}',str(brand.get('accent','#0b6472'))):raise HTTPException(400,'Use a valid company branding color.')
    clean['branding']={'name':text(brand.get('name',clean['company']),180,True),'subtitle':text(brand.get('subtitle',''),240),'accent':brand.get('accent','#0b6472'),'logo_file_id':brand.get('logo_file_id') or None}
    if clean['branding']['logo_file_id']:
        from backend.core.workhub_files import file_record
        row,path=file_record(clean['branding']['logo_file_id'])
        if path.stat().st_size>2*1024*1024 or not row['name'].lower().endswith(('.png','.jpg','.jpeg')):raise HTTPException(400,'Use a saved PNG/JPEG company logo below 2 MiB.')
    clean['default_profile']=_profile(value.get('default_profile',clean['default_profile']))
    profiles=value.get('project_profiles',{})
    if not isinstance(profiles,dict) or len(profiles)>100:raise HTTPException(400,'Configure up to 100 project-type procedures.')
    clean['project_profiles']={text(k,50,True):_profile(v) for k,v in profiles.items()}
    templates=value.get('templates',clean['templates'])
    if not isinstance(templates,dict):raise HTTPException(400,'Provide document templates by stage.')
    for stage in store.STAGES:
        t=templates.get(stage,DEFAULT['templates'][stage]);sections=t.get('sections',[]);fat=t.get('fat_items',[])
        if not isinstance(sections,list) or len(sections)>40 or not isinstance(fat,list) or len(fat)>500:raise HTTPException(400,'Use up to 40 headings and 500 FAT template items.')
        entries=[]
        for item in fat:
            if not isinstance(item,dict):raise HTTPException(400,'Provide structured FAT template items.')
            entries.append({key:text(item.get(key,''),4000,key=='objective') for key in ('objective','procedure','expected_result','acceptance_criteria')}|{'mandatory':bool(item.get('mandatory',True))})
        clean['templates'][stage]={'version':text(t.get('version','1'),40,True),'title':text(t.get('title',store.STAGES[stage]),240,True),
          'sections':[text(s,180,True) for s in sections],'fat_items':entries}
    return clean

def get(user):
    admin(user);store.initialize()
    with hub.db() as db:return current(db)
def save(user,payload):
    admin(user);store.initialize();config=validate(payload.get('configuration'))
    with hub.db(True) as db:
        old=current(db)
        if payload.get('version')!=old['version']:raise HTTPException(409,'Company controls changed. Reload before saving.')
        version=old['version']+1
        db.execute('INSERT INTO qc_settings VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,configuration=excluded.configuration,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
                   (version,store.bounded(config),user['id'],timestamp()))
        store.audit(db,user,None,'company_controls_updated',{'version':version,'configuration':config})
        return current(db)

def allocate(db,stage,setting):
    """Caller holds WorkHub BEGIN IMMEDIATE. Number uniqueness spans all configurations."""
    config=setting['configuration'];year=datetime.now(ZoneInfo(config['timezone'])).year;code=config['codes'][stage]
    mode=config['sequence_scope'];scope=('doctype:'+code if mode.startswith('doctype') else 'global')+(':'+str(year) if mode.endswith('year') else '')
    for _ in range(10000):
        r=db.execute('SELECT last_value FROM qc_sequences WHERE scope=?',(scope,)).fetchone();n=r[0]+1 if r else config['sequence_start']
        db.execute('INSERT INTO qc_sequences VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET last_value=excluded.last_value',(scope,n))
        value=config['pattern'].format(COMPANY=config['company'],DEPARTMENT=config['department'],TEAM=config['team'],DOCTYPE=code,YEAR=year,SEQ=str(n).zfill(config['sequence_width']),SEP=config['separator'])
        if not db.execute('SELECT 1 FROM qc_documents WHERE number=?',(value,)).fetchone() and not db.execute('SELECT 1 FROM wh_document_numbers WHERE number=?',(value,)).fetchone():return value
    raise HTTPException(409,'The number pattern repeatedly collides with issued numbers. Include year/type or change the sequence rule.')

def revision_label(config,number):return config['revision_pattern'].format(REV=str(number).zfill(config['revision_width']))
