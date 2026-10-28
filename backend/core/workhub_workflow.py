"""Project procedures, ordinary task plans and record-backed transition checks."""
from datetime import date, timedelta
import json
import math
import re
from fastapi import HTTPException
from .workhub import store as hub, DONE_DEVELOPMENT, NEXT_OWNER, identity, timestamp, text
from .workhub_quality import store

PHASES={'development':'Development','quality':'Quality review','release':'Handover'}
ROLES={'development':'owner_id','quality':'quality_id','release':'release_id'}
ACTIONS={'start':'Start project','complete_development':'Complete development','submit_quality':'Submit for quality review',
         'quality_pass':'Pass quality review','approve_release':'Approve release','release':'Close project'}
CONDITIONS={'document_approved':'Approved document','project_field':'Required project detail',
            'no_open_issues':'No unresolved issues','milestones_complete':'Milestones completed',
            'phase_complete':'Phase tasks completed','validation_pass':'Saved engineering check passed',
            'tests_passed':'Required test cases passed'}
DOCUMENTS={**store.STAGES,'mom':'Minutes of Meeting','flowchart':'Functional Flowchart'}
FIELDS={'customer':'Customer','machine':'Machine','scope':'Scope','start_date':'Start date','due_date':'Target date'}
TOOLS={'validation':'ByteMap','metadata':'Metadata','datainspect':'DataInspect','compare':'MatchView','rules':'LogicScan'}


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS wh_workflow_steps(project_id TEXT NOT NULL,step_id TEXT NOT NULL,
      task_id TEXT NOT NULL UNIQUE,profile_version INTEGER NOT NULL,PRIMARY KEY(project_id,step_id))''')
    db.execute('CREATE INDEX IF NOT EXISTS workflow_project_tasks ON wh_workflow_steps(project_id,task_id)')


def identifier(value):
    value=text(value,64,True)
    if not re.fullmatch(r'[A-Za-z0-9_-]+',value):raise HTTPException(400,'Use letters, numbers, underscores or dashes for a step or rule ID.')
    return value


def validate_steps(value):
    if not isinstance(value,list) or len(value)>100:raise HTTPException(400,'A workflow supports up to 100 steps.')
    clean=[];known={};last_phase=-1
    for raw in value:
        if not isinstance(raw,dict):raise HTTPException(400,'Provide structured workflow steps.')
        key=identifier(raw.get('id'));phase=raw.get('phase','development')
        if key in known or phase not in PHASES:raise HTTPException(400,'Use unique step IDs and supported delivery phases.')
        phase_index=list(PHASES).index(phase)
        if phase_index<last_phase:raise HTTPException(400,'Order development steps before quality review and handover steps.')
        last_phase=phase_index
        days=raw.get('days',1);hours=raw.get('planned_hours',0);milestone=raw.get('milestone',False)
        if type(days) is not int or not 1<=days<=3650:raise HTTPException(400,'Use a step duration between 1 and 3650 days.')
        if type(hours) not in (int,float) or not math.isfinite(hours) or not 0<=hours<=100000:raise HTTPException(400,'Use a finite step estimate between 0 and 100000 hours.')
        if type(milestone) is not bool:raise HTTPException(400,'Choose whether the step is a milestone.')
        dependencies=raw.get('depends_on',[])
        if not isinstance(dependencies,list) or len(dependencies)>100 or any(not isinstance(d,str) or d not in known for d in dependencies):raise HTTPException(400,'A step can depend only on earlier steps in this workflow.')
        clean.append({'id':key,'title':text(raw.get('title',''),180,True),'description':text(raw.get('description',''),4000),
                      'phase':phase,'days':days,'planned_hours':hours,'milestone':milestone,'depends_on':list(dict.fromkeys(dependencies))})
        known[key]=phase
    return clean


def validate_rules(value):
    if not isinstance(value,list) or len(value)>100:raise HTTPException(400,'A procedure supports up to 100 validation rules.')
    clean=[];known=set()
    for raw in value:
        if not isinstance(raw,dict):raise HTTPException(400,'Provide structured project validation rules.')
        key=identifier(raw.get('id'));condition=raw.get('condition');action=raw.get('action');severity=raw.get('severity','block')
        if key in known or condition not in CONDITIONS or action not in ACTIONS or severity not in {'block','warning'}:raise HTTPException(400,'Choose unique rule IDs, a supported check, a workflow action and a severity.')
        known.add(key);parameter=raw.get('parameter','')
        allowed=DOCUMENTS if condition=='document_approved' else FIELDS if condition=='project_field' else PHASES if condition in {'phase_complete','milestones_complete'} else TOOLS if condition=='validation_pass' else {'test':'Validation Test Report','fat':'FAT'} if condition=='tests_passed' else {'':''}
        if not isinstance(parameter,str) or parameter not in allowed:raise HTTPException(400,'Choose a supported value for the project validation rule.')
        if condition=='document_approved' and (parameter=='quality' and action not in {'approve_release','release'} or parameter=='closure' and action!='release'):raise HTTPException(400,'Require quality approval at release approval or closure, and closure approval at project closure, to avoid a circular approval.')
        if condition in {'phase_complete','milestones_complete'} and (parameter=='quality' and action not in {'quality_pass','approve_release','release'} or parameter=='release' and action!='release'):raise HTTPException(400,'Check quality work at quality completion, and handover work at project closure.')
        enabled=raw.get('enabled',True)
        if type(enabled) is not bool:raise HTTPException(400,'Choose whether the rule is enabled.')
        clean.append({'id':key,'name':text(raw.get('name',''),180,True),'condition':condition,'parameter':parameter,'action':action,'severity':severity,'enabled':enabled})
    return clean


def catalog(user):
    from .workhub_quality import configuration
    store.personal(user);store.initialize()
    with hub.db() as db:
        current=configuration.current(db);config=current['configuration']
        return {'version':current['version'],'templates':[{'id':'','name':'Default workflow','steps':len(config['default_profile'].get('workflow_steps',[])),'rules':len(config['default_profile'].get('validation_rules',[]))}]+
                [{'id':k,'name':k,'steps':len(v.get('workflow_steps',[])),'rules':len(v.get('validation_rules',[]))} for k,v in config['project_profiles'].items()],
                'phases':PHASES,'actions':ACTIONS,'conditions':CONDITIONS,'documents':DOCUMENTS,'fields':FIELDS,'tools':TOOLS}


def create_steps(db,p,user):
    """Create missing tasks once. Existing assignments, schedules and results survive."""
    schema(db);state=store.ensure_project(db,p,user);steps=state['policy'].get('workflow_steps',[])
    existing={r['step_id']:r['task_id'] for r in db.execute('SELECT * FROM wh_workflow_steps WHERE project_id=?',(p['id'],))}
    tasks={r['id']:dict(r) for r in db.execute("SELECT * FROM items WHERE project_id=? AND type='task'",(p['id'],))}
    today=date.today();base=date.fromisoformat(p['start_date']) if p.get('start_date') else today
    ends={key:date.fromisoformat(tasks[task]['due_date']) if tasks[task].get('due_date') else base for key,task in existing.items() if task in tasks}
    created=[];cursor=base
    for step in steps:
        if step['id'] in existing:
            if existing[step['id']] not in tasks:raise HTTPException(409,'A linked workflow task is missing. Restore or repair its link before applying the procedure.')
            continue
        start=max([base,*[ends[k]+timedelta(days=1) for k in step['depends_on']]]) if step['depends_on'] else base
        due=start+timedelta(days=step['days']-1)
        if step['milestone']:start=due
        task=hub.create(user,{'title':step['title'],'description':step['description'],'work_phase':step['phase'],
             'owner_id':p[ROLES[step['phase']]],'start_date':start.isoformat(),'due_date':due.isoformat(),
             'planned_hours':step['planned_hours'],'milestone':step['milestone'],'dependencies':[existing[k] for k in step['depends_on']]},p['id'],transaction=db)
        db.execute('INSERT INTO wh_workflow_steps VALUES(?,?,?,?)',(p['id'],step['id'],task['id'],state['policy_version']))
        existing[step['id']]=task['id'];ends[step['id']]=due;cursor=max(cursor,due);created.append(task['id'])
    if created:
        for phase in PHASES:
            bounds=db.execute("SELECT min(start_date),max(due_date) FROM items WHERE project_id=? AND type='task' AND work_phase=? AND start_date!='' AND due_date!=''",(p['id'],phase)).fetchone()
            if bounds[0]:
                db.execute('INSERT OR IGNORE INTO project_phases(id,project_id,phase,title,start_date,due_date,baseline_due) VALUES(?,?,?,?,?,?,?)',(identity(),p['id'],phase,PHASES[phase],bounds[0],bounds[1],bounds[1]))
                db.execute("UPDATE project_phases SET start_date=?,due_date=?,baseline_due=?,version=version+1 WHERE project_id=? AND phase=? AND start_date='' AND due_date=''",(bounds[0],bounds[1],bounds[1],p['id'],phase))
        if not p.get('start_date'):db.execute('UPDATE items SET start_date=? WHERE id=?',(base.isoformat(),p['id']))
        if not p.get('due_date'):db.execute('UPDATE items SET due_date=?,baseline_due=? WHERE id=?',(cursor.isoformat(),cursor.isoformat(),p['id']))
        db.execute('UPDATE items SET version=version+1,updated_at=? WHERE id=?',(timestamp(),p['id']))
        hub.event(db,p,user,'workflow_steps_created',{'tasks':created,'procedure_version':state['policy_version']})
    return created


def apply(user,pid,payload):
    from .workhub_quality import configuration
    store.initialize()
    with hub.db(True) as db:
        p=hub.contribute(db,pid,user);hub.manage(p,user,db)
        if p['type']!='project' or p['stage'] not in {'todo','development','blocked'}:raise HTTPException(409,'Apply a workflow during project planning or development.')
        if type(payload.get('version')) is not int or payload['version']!=p['version']:raise HTTPException(409,'The project changed. Reload its tracking view.')
        current=configuration.current(db)
        if payload.get('settings_version')!=current['version']:raise HTTPException(409,'Workflow settings changed. Reload the available workflows.')
        kind=payload.get('template_id') or p['kind'];reason=text(payload.get('reason',''),2000,True)
        if payload.get('template_id') and kind not in current['configuration']['project_profiles']:raise HTTPException(404,'Choose a configured workflow.')
        store.ensure_project(db,p,user);policy=configuration.profile(current['configuration'],kind)
        db.execute('UPDATE qc_projects SET policy=?,policy_version=?,project_type=?,version=version+1,updated_at=? WHERE project_id=?',
                   (store.bounded(policy),current['version'],kind,timestamp(),pid))
        db.execute('UPDATE items SET kind=?,version=version+1,updated_at=? WHERE id=?',(kind,timestamp(),pid))
        p=hub.item(db,pid);created=create_steps(db,p,user)
        store.audit(db,user,pid,'project_workflow_adopted',{'version':current['version'],'template':kind,'reason':reason,'created_tasks':created})
        hub.event(db,p,user,'project_workflow_adopted',{'template':kind,'reason':reason,'version':current['version']})
    return tracking(user,pid)


def evaluate(db,p,action=None):
    if p['type']!='project':return []
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_projects'").fetchone():return []
    if not db.execute('SELECT 1 FROM qc_projects WHERE project_id=?',(p['id'],)).fetchone():return []
    state=store.policy_row(db,p);rules=[r for r in state['policy'].get('validation_rules',[]) if r.get('enabled',True) and (action is None or r['action']==action)]
    if not rules:return []
    tasks=[dict(r) for r in db.execute("SELECT * FROM items WHERE project_id=? AND type='task' LIMIT 10001",(p['id'],))]
    if len(tasks)>10000:raise HTTPException(422,'This workflow exceeds the project tracking record limit.')
    open_issues=db.execute("SELECT count(*) FROM issues WHERE project_id=? AND status='open'",(p['id'],)).fetchone()[0]
    documents={r['stage']:dict(r) for r in db.execute('SELECT q.*,n.approved_revision,n.current_revision FROM qc_documents q JOIN pi_documents n ON n.id=q.document_id WHERE q.project_id=?',(p['id'],))}
    results=[];facts={}
    for rule in rules:
        condition=rule['condition'];parameter=rule['parameter'];passed=False;detail=''
        if (condition,parameter) in facts:
            passed,detail=facts[(condition,parameter)]
            results.append({**rule,'passed':passed,'detail':detail,'action_label':ACTIONS[rule['action']]});continue
        if condition=='document_approved':
            if parameter in {'mom','flowchart'}:
                passed=bool(db.execute('SELECT 1 FROM pi_documents WHERE project_id=? AND kind=? AND approved_revision IS NOT NULL AND current_revision=approved_revision',(p['id'],parameter)).fetchone())
                if parameter=='flowchart' and not passed and documents.get('frd') and documents['frd']['approved_revision'] and documents['frd']['current_revision']==documents['frd']['approved_revision']:
                    content=store.pi.revision(db,documents['frd']['approved_revision'],documents['frd']['document_id'])['content']
                    flow=content.get('flowchart');passed=bool(flow and not flow.get('needs_review',True))
            else:
                d=documents.get(parameter);passed=bool(d and d['approved_revision'] and d['current_revision']==d['approved_revision'])
            detail=DOCUMENTS[parameter]+(' is approved.' if passed else ' needs an approved current revision.')
        elif condition=='project_field':
            value=p.get(parameter) if parameter in {'start_date','due_date'} else state['context'].get(parameter) or (p.get('description') if parameter=='scope' else '')
            passed=bool(value);detail=FIELDS[parameter]+(' is recorded.' if passed else ' has not been recorded.')
        elif condition=='no_open_issues':passed=open_issues==0;detail=str(open_issues)+' unresolved issue(s).'
        elif condition in {'milestones_complete','phase_complete'}:
            selected=[t for t in tasks if t['work_phase']==parameter and (condition!='milestones_complete' or t['milestone'])]
            complete=sum(t['stage'] in DONE_DEVELOPMENT for t in selected);passed=bool(selected) and complete==len(selected)
            detail=str(complete)+' / '+str(len(selected))+' '+('milestones' if condition=='milestones_complete' else PHASES[parameter]+' tasks')+' completed.'
        elif condition=='validation_pass':
            from .workhub_quality.checks import native_outcome
            latest={}
            rows=db.execute('SELECT * FROM engineering_runs WHERE project_id=? AND kind=? ORDER BY iteration LIMIT 10001',(p['id'],parameter)).fetchall()
            if len(rows)>10000:raise HTTPException(422,'Narrow the saved engineering checks before evaluating this workflow.')
            for row in rows:
                row=dict(row);summary=json.loads(row['summary']);target=summary.get('target') or summary.get('configuration') or ''
                latest[(row['source_name'],store.bounded(target))]=row
            passed=bool(latest) and all(native_outcome(row)=='pass' for row in latest.values())
            detail='Latest saved '+TOOLS[parameter]+(' checks passed for all '+str(len(latest))+' source/target group(s).' if passed else ' checks need recorded passes for every source and target. A completed run alone is insufficient.')
        elif condition=='tests_passed':
            d=documents.get(parameter);cases=[];executions={}
            if d and d['current_revision']:
                cases=store.pi.revision(db,d['current_revision'],d['document_id'])['content'].get('cases',[])
                revision=store.revision(db,d['id'],d['current_revision']);executions=store.executions(db,d['current_revision'])
            required=[c for c in cases if c.get('mandatory',True)]
            passed=bool(required) and all(c['id'] in executions and executions[c['id']]['outcome']=='pass' and executions[c['id']]['specification_hash']==store.case_hash(c,revision['frd_revision_id']) for c in required)
            detail=('All required '+DOCUMENTS[parameter]+' cases passed.' if passed else DOCUMENTS[parameter]+' has missing, changed or non-passing required test results.')
        facts[(condition,parameter)]=(passed,detail)
        results.append({**rule,'passed':passed,'detail':detail,'action_label':ACTIONS[rule['action']]})
    return results


def guard(db,p,user,action):
    if p['type']!='project':return
    checks=evaluate(db,p,action);failed=[r for r in checks if not r['passed'] and r['severity']=='block']
    if failed:raise HTTPException(409,'Project workflow: '+'; '.join(r['name']+': '+r['detail'] for r in failed[:6]))
    warnings=[r for r in checks if not r['passed'] and r['severity']=='warning']
    if warnings:hub.event(db,p,user,'workflow_warnings',{'action':action,'rules':warnings})


def tracking(user,pid,event_page=1):
    from . import workhub_portfolio as portfolio
    from .workhub_quality import configuration
    store.initialize()
    with hub.db() as db:
        p=hub.contribute(db,pid,user)
        if p['type']!='project':raise HTTPException(400,'Open a project to view its delivery tracking.')
        tasks=[dict(r) for r in db.execute("SELECT * FROM items WHERE project_id=? AND type='task' ORDER BY start_date,due_date,created_at LIMIT 10001",(pid,))]
        issues=[dict(r) for r in db.execute('SELECT * FROM issues WHERE project_id=? ORDER BY created_at DESC LIMIT 10001',(pid,))]
        if len(tasks)>10000 or len(issues)>10000:raise HTTPException(422,'Narrow this project plan before loading its tracking view.')
        phase_schedule=[dict(r) for r in db.execute('SELECT * FROM project_phases WHERE project_id=?',(pid,))]
        state=store.policy_row(db,p);latest=configuration.current(db);assessment=portfolio.calculate(p,tasks,issues,portfolio.policy(db,pid),phase_schedule=phase_schedule)
        events=[dict(r) for r in db.execute('SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT 30 OFFSET ?',(pid,(event_page-1)*30))]
        for row in events:row['detail']=json.loads(row['detail'])
        documents=[dict(r) for r in db.execute('SELECT d.id,d.title,d.kind,r.status,r.number AS revision,d.updated_at FROM pi_documents d LEFT JOIN pi_revisions r ON r.id=d.current_revision WHERE d.project_id=? ORDER BY d.updated_at DESC LIMIT 100',(pid,))]
        return {'project':hub.public(p),'assessment':assessment,'procedure':{'name':state['project_type'],'version':state['policy_version'],'settings_version':latest['version'],'steps':state['policy'].get('workflow_steps',[]),'can_update':latest['version']!=state['policy_version']},
                'tasks':[hub.public(t) for t in tasks],'checks':evaluate(db,p),'issues':issues,'documents':documents,'events':events,
                'event_page':event_page,'event_total':db.execute('SELECT count(*) FROM events WHERE project_id=?',(pid,)).fetchone()[0],
                'responsible_id':p[NEXT_OWNER[p['stage']]],'can_manage':user['role']=='admin' or user['id'] in {p['created_by'],p['owner_id']},
                'schedule_warning':'The task plan extends beyond the project target date. Review the schedule.' if p['due_date'] and any(t['due_date']>p['due_date'] for t in tasks) else '',
                'phases':[{'id':phase,'name':label,'total':sum(t['work_phase']==phase for t in tasks),'completed':sum(t['work_phase']==phase and t['stage'] in DONE_DEVELOPMENT for t in tasks)} for phase,label in PHASES.items()]}
