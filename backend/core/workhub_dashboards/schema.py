"""The shared allowlist for manual editing, Chopper proposals and data queries.

No user expressions, SQL, JavaScript, HTML or arbitrary ECharts options are accepted.
"""
import json
import math
import re
from datetime import date
from fastapi import HTTPException

WIDGETS = {
    'kpi':'KPI card','scorecard':'Scorecard','gauge':'Gauge','progress':'Progress indicator',
    'bar':'Bar chart','stacked_bar':'Stacked bars','line':'Line chart','area':'Area chart',
    'pie':'Pie chart','donut':'Donut chart','scatter':'Scatter chart','combo':'Combo chart',
    'heatmap':'Heatmap','histogram':'Histogram','treemap':'Treemap','funnel':'Funnel','radar':'Radar chart',
    'table':'Table','pivot':'Pivot table','matrix':'Matrix','gantt':'Gantt chart','roadmap':'Roadmap',
    'calendar':'Calendar','text':'Text','documents':'Document links'}
COLS={'desktop':12,'tablet':8,'mobile':4}
AGGS=['count','distinct','sum','avg','min','max']
COMMON={'id':('Record ID','string'),'title':('Title','string'),'project_id':('Project ID','string'),
        'project':('Project','string'),'engineer_id':('Engineer ID','string'),'engineer':('Engineer','string'),
        'date':('Recorded date','date')}

def source(title, description, fields, default_dimension, default_metric='id', default_aggregation='count'):
    return {'title':title,'description':description,'fields':{
        key:{'id':key,'label':label,'type':kind,'aggregations':AGGS if kind=='number' else ['count','distinct']}
        for key,(label,kind) in {**COMMON,**fields}.items()},'default_dimension':default_dimension,
        'default_metric':default_metric,'default_aggregation':default_aggregation}

SOURCES={
 'projects':source('Projects','Existing WorkHub project completion calculations; all enabled personal accounts.',
   {'status':('Stage','string'),'work_type':('Work type','string'),'progress':('Project completion (%)','number'),
    'development_progress':('Development completion (%)','number'),'start':('Planned start','date'),'end':('Due date','date'),
    'hours':('Planned hours','number'),'health':('Health','string')},'status'),
 'tasks':source('Tasks','Workflow steps with their recorded phase and completion.',
   {'status':('Stage','string'),'phase':('Work phase','string'),'work_type':('Work type','string'),
    'progress':('Task completion (%)','number'),'completed':('Development completed (0/1)','number'),
    'released':('Released (0/1)','number'),'start':('Planned start','date'),'end':('Due date','date'),
    'hours':('Planned hours','number')},'engineer'),
 'assignments':source('Assignments','One record per assigned work item and workflow role.',
   {'status':('Stage','string'),'role':('Assigned role','string'),'item_type':('Work item type','string')},'engineer'),
 'milestones':source('Milestones','Explicit milestone tasks, with their saved dates.',
   {'status':('Stage','string'),'progress':('Completion (%)','number'),'start':('Planned start','date'),'end':('Due date','date')},'project'),
 'approvals':source('Approvals','Pending quality/release decisions and recorded review decisions, with their status.',
   {'status':('Decision status','string'),'decision':('Decision type','string'),'item_type':('Work item type','string')},'status'),
 'activity':source('Engineering activity','Your activity, or activity in projects you manage. Admin can view all. Counts are activity, not performance.',
   {'event':('Activity type','string'),'verification':('Verification','string'),'tool':('Engineering tool','string')},'date'),
 'validation':source('Validation results','Existing runs visible to you. Private archives stay private. Run counts and iterations are activity only.',
   {'status':('Run status','string'),'tool':('Engineering tool','string'),'iteration':('Recorded iteration','number'),
    'score':('Recorded validation score','number'),'score_field':('Recorded score field','string')},'tool'),
 'contributions':source('Reviewed contributions','Reviewed work from the existing 365-day performance profile, within your authorized scope.',
   {'activity':('Contribution type','string'),'reviewer':('Reviewer','string')},'engineer'),
 'capabilities':source('Capabilities','Existing 365-day capability profile. Counts of reviewed work are not capability scores. Project/date filters require Reviewed contributions.',
   {'capability':('Capability','string'),'assessment':('Existing assessment','string'),
    'reviewed_records':('Supporting reviewed records','number'),'projects_count':('Supporting projects','number')},'capability','reviewed_records','sum'),
 'knowledge':source('Knowledge articles','Published revisions only. Private drafts and submitted revisions are excluded.',
   {'category':('Category','string'),'revision':('Published revision','number')},'category'),
 'documents':source('Project documents','Project attachments and approved document revisions. Draft document content is excluded.',
   {'kind':('Document type','string'),'size':('File size (bytes)','number'),'revision':('Approved revision','number')},'kind')}

for _source,_label in {'projects':'Project owner','tasks':'Task assignee','assignments':'Assigned engineer','milestones':'Milestone assignee','approvals':'Decision reviewer','activity':'Attributed engineer','validation':'Run author','contributions':'Contribution author','capabilities':'Engineer','knowledge':'Article author','documents':'Document author / uploader'}.items():
    SOURCES[_source]['fields']['engineer']['label']=_label

def fail(message):raise HTTPException(400,message)
def string(value, limit=180):
    if not isinstance(value,str) or len(value)>limit:fail('Use text with at most '+str(limit)+' characters.')
    return value.strip()
def number(value,low,high):
    if type(value) not in (float,int) or not math.isfinite(value) or not low<=value<=high:fail('Numeric setting is outside its supported range.')
    return value
def integer(value,low,high):
    if type(value) is not int:fail('Use whole numbers for grid coordinates and limits.')
    return int(number(value,low,high))
def choice(value,options):
    if not isinstance(value,str) or value not in options:fail('Choose a supported setting: '+', '.join(options))
    return value
def bounded(value,limit=512*1024):
    try:raw=json.dumps(value,allow_nan=False,ensure_ascii=False)
    except (TypeError,ValueError):fail('Use finite numbers and valid JSON settings.')
    if len(raw.encode())>limit:raise HTTPException(413,'Dashboard configuration is too large.')
    return raw
def obj(value):
    if not isinstance(value,dict):fail('Provide a structured configuration.')
    return value
def array(value,limit):
    if not isinstance(value,list) or len(value)>limit:fail('Too many configuration entries.')
    return value
def iso(value):
    if value in ('',None):return ''
    try:return date.fromisoformat(value).isoformat()
    except (TypeError,ValueError):fail('Use an ISO date (YYYY-MM-DD).')
def color(value):
    if not isinstance(value,str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',value):fail('Use a six-digit hex color.')
    return value

def global_filters(value):
    v=obj(value or {})
    result={'project_id':string(v.get('project_id',''),64),'engineer_id':string(str(v.get('engineer_id','')),32),
            'from':iso(v.get('from')),'to':iso(v.get('to'))}
    if result['from'] and result['to'] and result['from']>result['to']:fail('The end date must follow the start date.')
    return result

def query(value):
    v=obj(value);key=choice(v.get('source','projects'),SOURCES);fields=SOURCES[key]['fields']
    dimensions=[]
    for entry in array(v.get('dimensions',[]),2):
        entry=obj(entry);field=choice(entry.get('field'),fields)
        grain=choice(entry.get('grain','value'),['value','day','week','month','year'])
        if grain!='value' and fields[field]['type']!='date':fail('Date grouping requires a date field.')
        dimensions.append({'field':field,'grain':grain})
    metrics=[]
    for entry in array(v.get('metrics',[{'field':'id','aggregation':'count'}]),4):
        entry=obj(entry);field=choice(entry.get('field'),fields);agg=choice(entry.get('aggregation','count'),fields[field]['aggregations'])
        metrics.append({'field':field,'aggregation':agg})
    if not metrics:fail('Select at least one metric.')
    filters=[]
    for entry in array(v.get('filters',[]),20):
        entry=obj(entry);field=choice(entry.get('field'),fields);op=choice(entry.get('op','eq'),['eq','ne','in','contains','gte','lte','is_set'])
        raw=entry.get('value','')
        values=array(raw,50) if op=='in' else [raw]
        converted=[]
        for val in values:
            if op=='is_set':converted.append(bool(val))
            elif fields[field]['type']=='number':converted.append(number(val,-1e15,1e15))
            elif fields[field]['type']=='date':converted.append(iso(val))
            else:converted.append(string(str(val),300))
        filters.append({'field':field,'op':op,'value':converted if op=='in' else converted[0]})
    return {'source':key,'dimensions':dimensions,'metrics':metrics,'filters':filters,
            'global':global_filters(v.get('global')),'limit':integer(v.get('limit',100),1,500),
            'sort':choice(v.get('sort','dimension'),['dimension','value_asc','value_desc']),
            'mode':choice(v.get('mode','aggregate'),['aggregate','records','histogram']),
            'bin_count':integer(v.get('bin_count',10),2,50)}

def widget(value):
    v=obj(value);key=string(v.get('id',''),64)
    if not re.fullmatch('[a-zA-Z0-9_-]{1,64}',key):fail('Use a valid widget ID.')
    kind=choice(v.get('type'),WIDGETS);q=query(v.get('query',{}));a=obj(v.get('appearance',{}))
    columns=[choice(k,SOURCES[q['source']]['fields']) for k in array(v.get('columns',[]),16)]
    palette=[color(k) for k in array(a.get('colors',['#16a394','#4269d0','#a383e3','#e8aa48','#d2657e']),12)]
    if not palette:fail('Choose at least one chart color.')
    return {'id':key,'type':kind,'title':string(v.get('title',WIDGETS[kind])), 'query':q,'columns':columns,
      'text':string(v.get('text',''),12000),
      'appearance':{'colors':palette,'legend':bool(a.get('legend',True)),'axes':bool(a.get('axes',True)),
        'horizontal':bool(a.get('horizontal',False)),'smooth':bool(a.get('smooth',False)),
        'series_types':[choice(k,['bar','line']) for k in array(a.get('series_types',[]),4)],
        'secondary_axis':bool(a.get('secondary_axis',False)),
        'format':choice(a.get('format','number'),['number','percent','hours','bytes']),
        'decimals':integer(a.get('decimals',0),0,4),'min':number(a.get('min',0),-1e12,1e12),
        'max':number(a.get('max',100),-1e12,1e12),'bins':integer(a.get('bins',10),2,50),
        'x_label':string(a.get('x_label',''),80),'y_label':string(a.get('y_label',''),80)}}

def overlaps(a,b):return a['x']<b['x']+b['w'] and b['x']<a['x']+a['w'] and a['y']<b['y']+b['h'] and b['y']<a['y']+a['h']
def layout(value,ids,cols):
    result=[];seen=set()
    for raw in array(value,60):
        v=obj(raw);key=choice(v.get('i'),ids)
        if key in seen:fail('Each widget must have one position per responsive layout.')
        seen.add(key);w=integer(v.get('w'),1,cols);h=integer(v.get('h'),2,30)
        row={'i':key,'x':integer(v.get('x'),0,cols-w),'y':integer(v.get('y'),0,2000),'w':w,'h':h}
        # Keep a requested free position; move down only when it collides.
        while any(overlaps(row,other) for other in result):
            row['y']=max(other['y']+other['h'] for other in result if overlaps(row,other))
        if row['y']+h>2100:fail('Layout exceeds the supported canvas height.')
        result.append(row)
    for key in ids:
        if key not in seen:result.append({'i':key,'x':0,'y':max([r['y']+r['h'] for r in result] or [0]),'w':min(6,cols),'h':5})
    return result

def dashboard(value):
    v=obj(value);bounded(v);widgets=[widget(w) for w in array(v.get('widgets',[]),60)];ids=[w['id'] for w in widgets]
    if len(set(ids))!=len(ids):fail('Widget IDs must be unique.')
    layouts=obj(v.get('layouts',{}));a=obj(v.get('appearance',{}))
    return {'schema_version':1,'name':string(v.get('name','My dashboard'),120) or 'My dashboard',
       'widgets':widgets,'layouts':{key:layout(layouts.get(key,[]),ids,cols) for key,cols in COLS.items()},
       'filters':global_filters(v.get('filters')),
       'appearance':{'theme':choice(a.get('theme','inherit'),['inherit','light','dark']),
         'background':choice(a.get('background','plain'),['plain','grid','tinted']),
         'density':choice(a.get('density','comfortable'),['comfortable','compact']),
         'accent':color(a.get('accent','#16a394'))}}

def registry():
    return {'sources':SOURCES,'widgets':WIDGETS,'columns':COLS,'schema_version':1,
      'limits':{'widgets':60,'result_rows':500,'dimensions':2,'metrics':4},
      'note':'Sharing a dashboard shares its configuration. Data is re-authorized for each viewer.'}
