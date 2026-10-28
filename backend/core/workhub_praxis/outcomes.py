"""Explainable work indices from project/task outcomes and workflow feedback.

Legacy assessment revisions remain intact. These analytics never sign off work,
infer a passing test from a completed run, or count unlinked tests for a project.
"""
from copy import deepcopy
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import json,math
from fastapi import HTTPException
from . import store,service
from .store import hub,org,identity,timestamp,text,encode

DEFAULTS={'performance_weights':{'delivery':35,'quality':45,'response':20},
          'competency_weights':{'quality':30,'problem_solving':35,'ownership':20,'knowledge':15},
          'response_hours':48,'sharing_target':2,'required_level':4}
NAMES={'delivery':'Delivery reliability','quality':'Work quality','response':'Response and follow-through',
       'problem_solving':'Problem solving','ownership':'Correction ownership','knowledge':'Knowledge sharing'}
QUESTIONS={'quality':{'none':100,'minor':75,'major':40},'problem_solving':{'independent':100,'supported':70,'escalated':40},'response':{'prompt':100,'follow_up':70,'repeated_follow_up':40}}

def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS px_work_feedback(id TEXT PRIMARY KEY,item_id TEXT NOT NULL,item_version INTEGER NOT NULL,phase TEXT NOT NULL,subject_id INTEGER NOT NULL,reviewer_id INTEGER NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(item_id,item_version,phase))')
    db.execute('CREATE TABLE IF NOT EXISTS px_work_configuration(version INTEGER PRIMARY KEY,content TEXT NOT NULL,actor_id INTEGER NOT NULL,created_at TEXT NOT NULL)')

def configuration(db):
    schema(db);r=db.execute('SELECT * FROM px_work_configuration ORDER BY version DESC LIMIT 1').fetchone()
    return {'version':r['version'] if r else 0,'content':json.loads(r['content']) if r else deepcopy(DEFAULTS)}

def settings(user,payload=None):
    store.initialize();org.personal(user)
    with hub.db(True) as db:
        old=configuration(db)
        if payload is None:return old
        if user['role']!='admin':raise HTTPException(403,'Only Admin can change shared work scoring rules.')
        if payload.get('version')!=old['version']:raise HTTPException(409,'The scoring rules changed. Reload before saving.')
        c=payload.get('content',{});result={}
        for field in ('performance_weights','competency_weights'):
            raw=c.get(field,{})
            if not isinstance(raw,dict) or set(raw)!=set(DEFAULTS[field]):raise HTTPException(400,'Keep each configured work dimension.')
            result[field]={k:store.number(v,0,100,'Dimension weight') for k,v in raw.items()}
            if not sum(result[field].values()):raise HTTPException(400,'Give at least one dimension a positive weight.')
        for key,low,high in [('response_hours',1,720),('sharing_target',1,100),('required_level',1,5)]:result[key]=store.number(c.get(key,DEFAULTS[key]),low,high,key,True)
        db.execute('INSERT INTO px_work_configuration VALUES(?,?,?,?)',(old['version']+1,encode(result),user['id'],timestamp()))
        return configuration(db)

def clean_feedback(raw):
    if not isinstance(raw,dict):raise HTTPException(400,'Provide structured work feedback.')
    result={}
    for key,choices in QUESTIONS.items():
        value=raw.get(key) or None
        if value is not None and (not isinstance(value,str) or value not in choices):raise HTTPException(400,'Choose an available work feedback answer.')
        result[key]=value
    for key in ('errors_corrected','troubleshooting_cases','solutions_shared','colleagues_helped'):
        result[key]=None if raw.get(key) in (None,'') else store.number(raw[key],0,10000,key,True)
    result['comment']=text(raw.get('comment',''),2000)
    return result

def record(db,user,item,phase,raw):
    if raw is None:return None
    if phase not in {'quality_pass','approve_release','release'}:raise HTTPException(400,'Work feedback belongs to approval or completion.')
    value=clean_feedback(raw)
    if not any(v is not None and v!='' for v in value.values()):return None
    schema(db)
    # Attribution is captured at the workflow action, never supplied by a client.
    dev=db.execute("SELECT actor_id FROM events WHERE item_id=? AND event='complete_development' ORDER BY id DESC LIMIT 1",(item['id'],)).fetchone()
    subject=dev['actor_id'] if dev else item['owner_id'];key=identity()
    db.execute('INSERT INTO px_work_feedback VALUES(?,?,?,?,?,?,?,?)',(key,item['id'],item['version']+1,phase,subject,user['id'],encode(value),timestamp()))
    return key

def _ratio(a,b):return round(100*a/b,1) if b else None
def _mean(values):
    numbers=[v for v in values if v is not None]
    return round(sum(numbers)/len(numbers),1) if numbers else None
def _weighted(values,weights):
    usable=[(values.get(k),w) for k,w in weights.items() if values.get(k) is not None and w>0]
    return round(sum(v*w for v,w in usable)/sum(w for _,w in usable),1) if usable else None
def _date(raw):
    try:return datetime.fromisoformat(str(raw).replace('Z','+00:00')).replace(tzinfo=timezone.utc) if len(str(raw))<=10 else datetime.fromisoformat(str(raw).replace('Z','+00:00'))
    except (ValueError,TypeError):return None
def _day(raw):
    value=_date(raw)
    return value.astimezone(ZoneInfo('Asia/Kolkata')).date().isoformat() if value else str(raw)[:10]

def profile(user,subject,period_id='',project_id=''):
    base=service.profile(user,subject,period_id);store.initialize()
    from backend.core.workhub_growth import collector,store as growth
    growth.initialize();collector.collect()
    period=base.get('period') or {'id':'recent','name':'Last 90 days','start':(datetime.now(timezone.utc)-timedelta(days=90)).date().isoformat(),'end':datetime.now(timezone.utc).date().isoformat()}
    start=period.get('start','');end=period.get('end','9999-12-31')
    def in_period(at):return start<=_day(at)<=end
    with hub.db(True) as db:
        config=configuration(db);cfg=config['content']
        samples={r['id'] for r in db.execute('SELECT id FROM items WHERE is_sample=1')}
        projects={r['id'] for r in db.execute("SELECT id FROM items WHERE type='project'")}
        include=lambda pid:pid==project_id and pid in projects if project_id else pid is None or pid in projects and pid not in samples
        assigned=[dict(r) for r in db.execute('SELECT * FROM items WHERE owner_id=?',(subject,)) if include(r['project_id'])]
        all_events=[dict(r) for r in db.execute('SELECT e.*,i.title,i.type,i.owner_id,i.due_date,i.baseline_due,i.stage AS current_stage,i.completed_at FROM events e JOIN items i ON i.id=e.item_id WHERE e.item_id IN (SELECT item_id FROM events WHERE actor_id=? AND event=?) ORDER BY e.id',(subject,'complete_development')) if include(r['project_id'])]
        grouped=defaultdict(list)
        for e in all_events:grouped[e['item_id']].append(e)
        records=[];on_time=[];accepted=[];response=[];references=[]
        for key,events in grouped.items():
            developer=None;requests=[];rework=0;completion=None;quality=None;release=None
            for e in events:
                if e['event']=='complete_development':
                    developer=e['actor_id'];completion=e
                    if requests and developer==subject:
                        a=_date(requests[-1]['created_at']);b=_date(e['created_at'])
                        if a and b and in_period(e['created_at']):response.append(100 if (b-a).total_seconds()<=cfg['response_hours']*3600 else 0)
                    requests=[]
                elif e['event']=='request_changes':
                    if developer==subject and in_period(e['created_at']):rework+=1
                    requests.append(e)
                elif e['event']=='quality_pass' and developer==subject and in_period(e['created_at']):quality=e
                elif e['event']=='release' and developer==subject and in_period(e['created_at']):release=e
            if not completion or completion['actor_id']!=subject or not in_period(completion['created_at']):continue
            reference={'kind':completion['type'],'id':key,'title':completion['title'],'project_id':completion['project_id'],'task_id':key if completion['type']=='task' else None}
            references.append(reference)
            if quality or release:accepted.append(100/(1+rework))
            # Prefer a preserved planned date. Never borrow today's due date
            # for a reopened historical completion cycle.
            detail=json.loads(completion['detail']);due=detail.get('baseline_due') or detail.get('due_date')
            if not due and release and completion['current_stage']=='released':due=completion['baseline_due'] or completion['due_date']
            timely=(100 if _day(completion['created_at'])<=due[:10] else 0) if due else None
            if due:on_time.append(timely)
            records.append({'id':key,'title':completion['title'],'project_id':completion['project_id'],'type':completion['type'],'completed_at':completion['created_at'],'reviewed_at':(quality or release or completion)['created_at'],'reviewer_id':(quality or release)['actor_id'] if quality or release else None,'review_comment':json.loads((quality or release or completion)['detail']).get('comment',''),'due':due,'delivery_score':timely,'accepted':bool(quality or release),'correction_cycles':rework,'reference':reference})
        raw_feedback=[dict(r) for r in db.execute('SELECT f.*,i.project_id,i.title FROM px_work_feedback f JOIN items i ON i.id=f.item_id WHERE f.subject_id=? ORDER BY f.created_at',(subject,)) if in_period(r['created_at']) and include(r['project_id'])]
        # Quality and completion can describe the same delivered work. The
        # latest entered answer for each question wins; counts are not summed
        # repeatedly across approval and release.
        feedback={}
        for f in raw_feedback:
            content=json.loads(f['content']);old=feedback.setdefault(f['item_id'],{'answers':{},'record':f})
            for k,v in content.items():
                if v is not None and v!='':old['answers'][k]=v
            old['record']=f
        answers=[v['answers'] for v in feedback.values()]
        counts={k:sum(a.get(k) or 0 for a in answers) for k in ('errors_corrected','troubleshooting_cases','solutions_shared','colleagues_helped')}
        issues=[dict(r) for r in db.execute('SELECT * FROM issues WHERE owner_id=?',(subject,)) if in_period(r['updated_at']) and include(r['project_id'])]
        published=sum(include(r['project_id']) for r in db.execute('SELECT a.id,a.project_id FROM cp_articles a JOIN cp_revisions r ON r.id=a.published_revision WHERE a.author_id=? AND substr(r.published_at,1,10)>=? AND substr(r.published_at,1,10)<=?',(subject,start,end)))
        runs=[dict(r) for r in db.execute("SELECT * FROM pc_events WHERE source_type='run' AND subject_id=? AND project_id IS NOT NULL ORDER BY occurred_at",(subject,)) if in_period(r['occurred_at']) and include(r['project_id'])]
        sources=[];user_names={u['id']:u['username'] for u in hub.users()}
        for v in feedback.values():
            f=v['record'];sources.append({'item_id':f['item_id'],'project_id':f['project_id'],'title':f['title'],'reviewer_id':f['reviewer_id'],'reviewer_name':user_names.get(f['reviewer_id'],'Former user'),'at':f['created_at'],'answers':v['answers']})
    latest={}
    for row in runs:
        data=json.loads(row['data']);summary=data.get('summary') or {};key=(row['project_id'],data.get('kind'),str(summary.get('target') or data.get('target_id') or ''))
        latest[key]=data
    validation_scores=[]
    for data in latest.values():
        scores=[r['value'] for r in data.get('recorded_scores',[]) if type(r.get('value')) in (int,float) and math.isfinite(r['value']) and 0<=r['value']<=100]
        if scores:validation_scores.append(sum(scores)/len(scores))
    q=[QUESTIONS['quality'][a['quality']] for a in answers if a.get('quality')]
    measured={'delivery':_mean(on_time),'quality':_mean([_mean(accepted),_mean(q),_mean(validation_scores)]),
              'response':_mean([_mean(response),_mean([QUESTIONS['response'][a['response']] for a in answers if a.get('response')])]),
              'problem_solving':_mean([QUESTIONS['problem_solving'][a['problem_solving']] for a in answers if a.get('problem_solving')]),
              'ownership':_ratio(sum(r['status']=='resolved' for r in issues),len(issues)),
              'knowledge':min(100,100*(published+counts['solutions_shared'])/cfg['sharing_target']) if published or any('solutions_shared' in a for a in answers) else None}
    performance_index=_weighted(measured,cfg['performance_weights']);competency_index=_weighted(measured,cfg['competency_weights'])
    notes={'delivery':f'{len(on_time)} completed deliveries with a known planned date.', 'quality':f'{len(accepted)} approved work outcomes; {len(q)} reviewer correction answers; {len(validation_scores)} latest recorded validation scores. A completed test without a score is not treated as a pass.',
           'response':f'{len(response)} measured correction responses; target {cfg["response_hours"]} elapsed hours.',
           'problem_solving':'Reviewer answers at project/task approval: independent 100, supported 70, escalated 40.',
           'ownership':f'{sum(r["status"]=="resolved" for r in issues)} of {len(issues)} assigned issues resolved.',
           'knowledge':f'{published} published contributions and {counts["solutions_shared"]} reviewer-confirmed shared solutions; target {cfg["sharing_target"]}.'}
    dimensions=[{'id':k,'name':NAMES[k],'source':k,'value':v,'weight':cfg['performance_weights'].get(k,cfg['competency_weights'].get(k,0)),'criteria':notes[k],'note':notes[k],'not_applicable':False,'references':references[:25]} for k,v in measured.items()]
    competencies=[{'id':d['id'],'name':d['name'],'category':'Project and task capability','description':d['criteria'],'criteria':d['criteria'],'current':None if d['value'] is None else round(1+4*d['value']/100,1),'required':cfg['required_level'],'gap':None if d['value'] is None else round(max(0,cfg['required_level']-(1+4*d['value']/100)),1),'weight':cfg['competency_weights'].get(d['id'],0),'note':d['note'],'references':d['references'],'review_frequency_days':90} for d in dimensions if d['id'] in cfg['competency_weights']]
    native_review=max((r for r in records if r['reviewer_id']),key=lambda r:r['reviewed_at'],default=None)
    history=[]
    for row in records:
        a=feedback.get(row['id'],{}).get('answers',{});values={'delivery':row['delivery_score'],'quality':_mean([100/(1+row['correction_cycles']) if row['accepted'] else None,QUESTIONS['quality'].get(a.get('quality'))]),'response':QUESTIONS['response'].get(a.get('response')),'problem_solving':QUESTIONS['problem_solving'].get(a.get('problem_solving'))}
        history.append({'revision_id':row['id'],'at':feedback.get(row['id'],{}).get('record',{}).get('created_at',row['reviewed_at']),'period':{'name':row['title']},'title':row['title'],'performance_index':_weighted(values,cfg['performance_weights']),'competency_index':_weighted(values,cfg['competency_weights']),'competencies':[],'performance':[],'comment':'Work outcome at its recorded review/completion; calculated with the displayed rules.'})
    history.sort(key=lambda h:h['at'])
    return {**base,'sample_preview':project_id in samples,'sample_projects_excluded':len(samples) if not project_id else 0,'legacy_approved_revision':base['approved_revision'],'approved_revision':None,'assessments':[], 'period':period,'model':{'name':'Project and task outcomes','method':'weighted_mean'},
            'performance_index':performance_index,'competency_index':competency_index,'performance_status':'Calculated from work' if performance_index is not None else 'Waiting for completed work','competency_status':'Calculated from work' if competency_index is not None else 'Waiting for completed work',
            'development':[],'development_progress':_ratio(sum(r['stage'] in {'development_completed','quality','release_approval','ready_release','released'} for r in assigned),len(assigned)),'performance':dimensions,'competencies':competencies,'competencies_assessed':sum(d['current'] is not None for d in competencies),'competencies_required':len(competencies),
            'review':({'reviewer_name':sources[-1]['reviewer_name'],'at':sources[-1]['at'],'comment':sources[-1]['answers'].get('comment','')} if sources else {'reviewer_name':user_names.get(native_review['reviewer_id'],'Former user'),'at':native_review['reviewed_at'],'comment':native_review['review_comment']} if native_review else None),'history':history,'work_based':True,'work_records':records,'work_feedback':sources,'work_counts':{**counts,'published_contributions':published,'validation_runs':len(runs),'completed_work':len(records),'accepted_work':len(accepted),'quality_cycles':sum(r['correction_cycles'] for r in records),'issues_resolved':sum(r['status']=='resolved' for r in issues)},
            'validation_activity':[{'tool':json.loads(r['data']).get('tool',r['event_type']),'at':r['occurred_at'],'project_id':r['project_id'],'data':json.loads(r['data'])} for r in runs],
            'scoring_configuration':config,'methodology':{'performance':'Available delivery, quality and response dimensions, weighted separately.','competency':'Available quality, problem solving, issue ownership and sharing dimensions, weighted separately. Work capability level = 1 + 4 × score / 100.','missing':'Missing dimensions are excluded and coverage is shown; they are never invented or scored as zero. No separate assessment is required.'}}

def team(user,period_id='',department_id='',team_id='',role_id='',employee_id=None,project_id=''):
    # Reuse the existing managed-team and reporting-relationship authorization.
    allowed=service.team(user,period_id,department_id,team_id,role_id,employee_id,project_id)
    people=[profile(user,p['person']['id'],period_id,project_id) for p in allowed['people']]
    return {**allowed,'people':people,'assessed':sum(p['competency_index'] is not None for p in people),'work_based':True}
