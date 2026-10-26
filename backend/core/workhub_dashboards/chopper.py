"""Chopper's dashboard actions produce drafts, never executable code or queries."""
import copy
import os
import re
from fastapi import HTTPException
from backend.core.workhub import identity
from . import schema

def fresh(kind,source,title=None,dimension=None,metric='id',aggregation='count'):
    return schema.widget({'id':identity(),'type':kind,'title':title or schema.WIDGETS[kind],
      'query':{'source':source,'dimensions':[{'field':dimension,'grain':'day' if dimension=='date' else 'value'}] if dimension else [],
        'metrics':[{'field':metric,'aggregation':aggregation}]}})

def add(config,widget):
    config['widgets'].append(widget)
    for key,cols in schema.COLS.items():
        rows=config['layouts'][key]
        rows.append({'i':widget['id'],'x':0,'y':max([r['y']+r['h'] for r in rows] or [0]),'w':min(6,cols),'h':5})

def proposal(user,payload):
    from backend.core.workhub_growth.store import personal
    personal(user);schema.bounded(payload)
    config=schema.dashboard(payload.get('configuration',{}));before=copy.deepcopy(config)
    prompt=schema.string(payload.get('prompt',''),4000)
    if not prompt:schema.fail('Describe the dashboard change you need.')
    text=prompt.lower();selected=payload.get('selected_id');target=next((w for w in config['widgets'] if w['id']==selected),None)
    if not target:
        matches=[w for w in config['widgets'] if w['title'].casefold() in text]
        target=matches[0] if len(matches)==1 else None
    kinds={'stacked bar':'stacked_bar','scorecard':'scorecard','heatmap':'heatmap','histogram':'histogram',
      'treemap':'treemap','roadmap':'roadmap','calendar':'calendar','progress indicator':'progress','gantt':'gantt',
      'donut':'donut','doughnut':'donut','scatter':'scatter','funnel':'funnel','radar':'radar','combo':'combo',
      'line':'line','area':'area','pie':'pie','bar':'bar','gauge':'gauge','pivot':'pivot','matrix':'matrix','table':'table','kpi':'kpi'}
    kind=next((value for term,value in kinds.items() if re.search(r'\b'+re.escape(term)+r'\b',text)),None)
    explanation='';mode='local structured action'
    if re.search(r'\b(change|convert|switch|make|resize|larger|smaller|bigger|wider|taller)\b',text) and ('widget' in text or target):
        if not target:raise HTTPException(422,'Select the widget to change in Edit mode, then ask Chopper again.')
        if kind:
            target['type']=kind;explanation='Changed the selected widget visualization.'
        else:
            delta=-1 if any(k in text for k in ('smaller','narrower','shorter')) else 1
            for key,cols in schema.COLS.items():
                r=next(r for r in config['layouts'][key] if r['i']==target['id'])
                r['w']=max(1,min(cols,r['w']+2*delta));r['x']=min(r['x'],cols-r['w']);r['h']=max(2,min(30,r['h']+delta))
            explanation='Resized the selected widget across desktop, tablet and mobile layouts.'
    elif ('project' in text and 'progress' in text and 'dashboard' in text):
        config['name']='Project progress'
        add(config,fresh('kpi','projects','Projects'))
        add(config,fresh('bar','projects','Project completion','title','progress','avg'))
        add(config,fresh('donut','projects','Projects by stage','status'))
        w=fresh('table','tasks','Upcoming project work');w['columns']=['title','project','engineer','status','end'];add(config,w)
        explanation='Added project count, recorded completion, stages and task details. No records or results were invented.'
    elif kind or any(w in text for w in ('dashboard','widget','chart','roadmap')):
        source=next((value for terms,value in [(['validation','iteration'],'validation'),(['approval'],'approvals'),
            (['knowledge','article'],'knowledge'),(['capabilit'],'capabilities'),(['contribution','reviewed'],'contributions'),
            (['milestone'],'milestones'),(['document'],'documents'),(['assignment'],'assignments'),(['task'],'tasks'),
            (['activity'],'activity'),(['project'],'projects')] if any(term in text for term in terms)),'projects')
        kind=kind or ('progress' if 'progress' in text else 'bar')
        definition=schema.SOURCES[source];fields=definition['fields']
        dimension='engineer' if re.search(r'by (engineer|person|assignee|owner)',text) else 'status' if 'by status' in text else 'project' if 'by project' in text else definition['default_dimension']
        metric=definition['default_metric'];agg=definition['default_aggregation']
        if source=='projects' and 'progress' in text:metric='progress';agg='avg';dimension='title'
        if source=='tasks' and 'completed' in text:metric='completed';agg='sum'
        if kind=='heatmap':dimensions=[{'field':'date','grain':'day'},{'field':'tool' if source in {'validation','activity'} else 'engineer','grain':'value'}]
        else:dimensions=[{'field':dimension,'grain':'day' if dimension=='date' else 'value'}] if dimension in fields else []
        w=fresh(kind,source,prompt[:120],metric=metric,aggregation=agg);w['query']['dimensions']=dimensions
        if 'pending' in text and 'status' in fields:w['query']['filters']=[{'field':'status','op':'eq','value':'pending'}]
        if 'completed' in text and source=='tasks':w['query']['filters']=[{'field':'completed','op':'eq','value':1}]
        if kind in {'scatter','histogram'}:
            nums=[k for k,f in fields.items() if f['type']=='number']
            if not nums:raise HTTPException(422,'This source has no numeric fields for that chart. Choose another source or visualization.')
            w['query']['metrics']=[{'field':k,'aggregation':'avg'} for k in nums[:2]]
        add(config,w);explanation='Added a configurable widget using authorized '+definition['title'].lower()+' records.'
    else:
        # Optional private local model only. Configuration/registry only, no company record values.
        if not __import__('backend.core.workhub_intelligence.local_ai',fromlist=['configured']).configured():raise HTTPException(422,'Describe a chart and source, or select a widget to change. For example: Add a bar chart of completed tasks by engineer.')
        from backend.core.workhub_intelligence.local_ai import llm_json,ServiceUnavailable
        try:
            result=llm_json('Return {"configuration": <complete dashboard>, "explanation": "short description"}. Use only the supplied registry and schema. Preserve unrelated widgets. No code, expressions, SQL, URLs, fabricated results or ECharts options. Changes are a draft requiring user review.',
               {'request':prompt,'configuration':config,'selected_id':selected,'registry':schema.registry()})
            config=schema.dashboard(result.get('configuration'));explanation=schema.string(result.get('explanation','Proposed dashboard changes.'),600);mode='private local model'
        except ServiceUnavailable:raise HTTPException(503,'The private Chopper model is unavailable. Use the widget library or a supported structured dashboard request.') from None
    config=schema.dashboard(config)
    if config==before:raise HTTPException(422,'No dashboard change was identified. Describe the widget or layout change.')
    return {'configuration':config,'explanation':explanation,'mode':mode,'requires_review':True,
      'notice':'Review and apply this draft in the builder. Save persists it. All widgets remain manually editable.'}
