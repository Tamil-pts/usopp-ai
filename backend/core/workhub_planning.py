"""Project phase schedules, reusable planning methods and sprint delivery."""
from datetime import date, timedelta
from fastapi import HTTPException
from .workhub import identity, timestamp, text, day, encode, DONE_DEVELOPMENT

PHASES=('development','quality','release')
METHODS=('custom','waterfall','agile','sprint')
LABELS={'development':'Development','quality':'Quality check','release':'Release'}

def method(value):
    if value not in METHODS:raise HTTPException(400,'Choose Custom, Waterfall, Agile or Sprint planning.')
    return value

def phase(value):
    if value not in PHASES:raise HTTPException(400,'Choose Development, Quality or Release.')
    return value

def bounds(payload,required=False):
    start=day(payload.get('start_date',''));finish=day(payload.get('due_date',''))
    if required and (not start or not finish):raise HTTPException(400,'Choose a start and finish date.')
    if start and finish and start>finish:raise HTTPException(400,'Finish must be on or after the start.')
    return start,finish

def phase_progress(project,tasks):
    parents={row['parent_id'] for row in tasks if row['parent_id']}
    leaves=[row for row in tasks if row['id'] not in parents]
    stage=project['stage'];result={}
    for code in PHASES:
        work=[row for row in leaves if row.get('work_phase','development')==code]
        weight=sum(row['planned_hours'] or 1 for row in work)
        finished=sum(row['planned_hours'] or 1 for row in work if row['stage'] in DONE_DEVELOPMENT)
        if code=='development':
            result[code]=100 if stage in DONE_DEVELOPMENT else round(100*finished/weight) if weight else 0
        else:
            gates=1 if code=='quality' else 2
            passed=int(stage in {'release_approval','ready_release','released'}) if code=='quality' else int(stage in {'ready_release','released'})+int(stage=='released')
            result[code]=100 if stage=='released' else round(100*(finished+passed)/(weight+gates))
    return result

def completion(project,tasks):
    parents={row['parent_id'] for row in tasks if row['parent_id']}
    leaves=[row for row in tasks if row['id'] not in parents]
    values=phase_progress(project,tasks)
    return {'task_count':len(tasks),'leaf_task_count':len(leaves),'completed_tasks':sum(row['stage'] in DONE_DEVELOPMENT for row in leaves),
            'progress':100 if project['stage']=='released' else min(99,round(sum(values.values())/3)),
            'development_progress':values['development'],'phase_progress':values}

def reassign_phase_steps(store,db,project,user,field,owner):
    code={'owner_id':'development','quality_id':'quality','release_id':'release'}.get(field)
    if project['type']!='project' or not code or owner==project[field]:return
    # Preserve individual assignments and completed work; move only inherited, unstarted work.
    for raw in db.execute("SELECT * FROM items WHERE project_id=? AND type='task' AND work_phase=? AND stage='todo' AND owner_id=?",(project['id'],code,project[field])).fetchall():
        row=dict(raw)
        db.execute('UPDATE items SET owner_id=?,updated_at=?,version=version+1 WHERE id=?',(owner,timestamp(),row['id']))
        store.event(db,row,user,'phase_assignment_updated',{'owner_id':owner,'phase':code})
        store.notify(db,row,user['id'],[owner],'Work assigned: '+row['title'],'You are responsible for this planned '+LABELS[code].lower()+' step.')

def phases(store,db,project,tasks):
    saved={row['phase']:dict(row) for row in db.execute('SELECT * FROM project_phases WHERE project_id=?',(project['id'],))}
    progress=phase_progress(project,tasks);result=[]
    for code in PHASES:
        row=saved.get(code,{'id':'phase_'+code,'project_id':project['id'],'phase':code,'title':LABELS[code],'start_date':'','due_date':'','baseline_due':'','version':0})
        owner=project['owner_id'] if code=='development' else project['quality_id'] if code=='quality' else project['approver_id'] if project['stage']=='release_approval' else project['release_id']
        active=project['stage'] in ({'todo','development','development_completed','blocked'} if code=='development' else {'quality'} if code=='quality' else {'release_approval','ready_release'})
        result.append({**row,'type':'phase','owner_id':owner,'current_user_id':owner,'created_by':project['created_by'],
                       'stage':'released' if project['stage']=='released' else 'development_completed' if progress[code]==100 else 'development' if active else 'todo',
                       'stage_label':'Complete' if progress[code]==100 else 'Active' if active else 'Planned','progress':progress[code],'dependencies':[],
                       'created_at':project['created_at'],'plan_locked':project['stage']=='released'})
    return result

def sprints(db,project,tasks):
    result=[]
    for raw in db.execute('SELECT * FROM sprints WHERE project_id=? ORDER BY start_date,created_at',(project['id'],)):
        row=dict(raw);work=[task for task in tasks if task.get('sprint_id')==row['id']]
        parents={task['parent_id'] for task in work if task['parent_id']};leaves=[task for task in work if task['id'] not in parents]
        total=sum(task['planned_hours'] or 1 for task in leaves)
        progress=round(100*sum(task['planned_hours'] or 1 for task in leaves if task['stage'] in DONE_DEVELOPMENT)/total) if total else 0
        result.append({**row,'type':'sprint','stage':'development_completed' if row['status']=='closed' else 'development' if row['status']=='active' else 'todo',
                       'stage_label':row['status'].capitalize(),'progress':progress,'task_count':len(work),'completed_tasks':sum(task['stage'] in DONE_DEVELOPMENT for task in work),
                       'current_user_id':row['owner_id'],'created_by':project['created_by'],'dependencies':[],'baseline_due':row['due_date'],
                       'plan_locked':row['status']=='closed' or project['stage']=='released'})
    return result

def initialize_plan(store,db,project,user,payload):
    selected=method(payload.get('methodology','custom'))
    db.execute('UPDATE items SET methodology=? WHERE id=?',(selected,project['id']))
    plan=payload.get('phase_plan',[])
    if not isinstance(plan,list) or len(plan)>3:raise HTTPException(400,'Plan at most three delivery phases.')
    seen=set();records={}
    for entry in plan:
        if not isinstance(entry,dict):raise HTTPException(400,'Choose valid phase dates.')
        code=phase(entry.get('phase'))
        if code in seen:raise HTTPException(400,'Each delivery phase must appear once.')
        seen.add(code);start,finish=bounds(entry)
        row={'id':identity(),'phase':code,'title':text(entry.get('title',LABELS[code]),180,True),'start_date':start,'due_date':finish}
        db.execute('INSERT INTO project_phases(id,project_id,phase,title,start_date,due_date,baseline_due) VALUES(?,?,?,?,?,?,?)',
                   (row['id'],project['id'],code,row['title'],start,finish,finish));records[code]=row
    sprint_plan=payload.get('sprints',[])
    if not isinstance(sprint_plan,list) or len(sprint_plan)>24:raise HTTPException(400,'Create at most 24 initial sprints.')
    if sprint_plan and selected not in {'agile','sprint'}:raise HTTPException(400,'Choose Agile or Sprint planning to create sprints.')
    previous=None;dev_end=[]
    generate_tasks=payload.get('generate_plan_tasks',True)
    if type(generate_tasks) is not bool:raise HTTPException(400,'Choose whether to create planning template tasks.')
    for index,entry in enumerate(sprint_plan):
        if not isinstance(entry,dict):raise HTTPException(400,'Choose valid sprint dates.')
        start,finish=bounds(entry,True)
        if (date.fromisoformat(finish)-date.fromisoformat(start)).days>90:raise HTTPException(400,'A sprint can span at most 91 calendar days.')
        sprint_id=identity();name=text(entry.get('title','Sprint '+str(index+1)),120,True)
        db.execute('INSERT INTO sprints(id,project_id,title,goal,owner_id,start_date,due_date,status,created_at) VALUES(?,?,?,?,?,?,?,\'planned\',?)',
                   (sprint_id,project['id'],name,text(entry.get('goal',''),2000),project['owner_id'],start,finish,timestamp()))
        if selected in {'agile','sprint'} and generate_tasks:
            first=date.fromisoformat(start);last=date.fromisoformat(finish);days=(last-first).days
            planning_end=first;build_start=min(first+timedelta(days=1),last);build_end=max(build_start,last-timedelta(days=1))
            steps=[('Planning',first,planning_end),('Implementation',build_start,build_end),('Sprint review',last,last)]
            previous=None
            for title,a,b in steps:
                previous=insert_step(store,db,project,user,name+' / '+title,'development',a.isoformat(),b.isoformat(),[previous] if previous else [],sprint_id)
            dev_end.append(previous)
    if selected=='waterfall' and 'development' in records and generate_tasks:
        row=records['development'];dev_end=[insert_step(store,db,project,user,'Development','development',row['start_date'],row['due_date'])]
    if selected!='custom' and generate_tasks:
        quality=records.get('quality',{});release=records.get('release',{})
        quality_id=insert_step(store,db,project,user,'Quality checks','quality',quality.get('start_date',''),quality.get('due_date',''),dev_end)
        insert_step(store,db,project,user,'Release and handover','release',release.get('start_date',''),release.get('due_date',''),[quality_id])
    store.event(db,project,user,'plan_created',{'methodology':selected,'phases':list(seen),'sprints':len(sprint_plan)})

def insert_step(store,db,project,user,title,code,start,finish,dependencies=None,sprint_id=''):
    key=identity();now=timestamp();owner=project['owner_id'] if code=='development' else project['quality_id'] if code=='quality' else project['release_id']
    db.execute('''INSERT INTO items(id,project_id,type,title,kind,description,created_by,owner_id,quality_id,approver_id,release_id,
                  due_date,start_date,baseline_due,dependencies,created_at,updated_at,work_phase,sprint_id)
                  VALUES(?,?,'task',?,?,'',?,?,?,?,?,?,?,?,?,?,?,?,?)''',
               (key,project['id'],title,project['kind'],user['id'],owner,project['quality_id'],project['approver_id'],project['release_id'],finish,start,finish,encode(dependencies or []),now,now,code,sprint_id))
    store.event(db,{**project,'id':key},user,'template_step_created',{'title':title,'phase':code,'sprint_id':sprint_id})
    return key

def schedule(store,user,project_id,payload):
    store.actor(user)
    with store.db(True) as db:
        project=store.item(db,project_id)
        if project['type']!='project':raise HTTPException(400,'Choose a project.')
        entries=payload.get('items',[])
        if not isinstance(entries,list) or not 1<=len(entries)<=100:raise HTTPException(400,'Choose 1 to 100 schedule rows.')
        touched=set()
        for entry in entries:
            if not isinstance(entry,dict):raise HTTPException(400,'Choose a valid schedule row.')
            kind=entry.get('type');key=entry.get('id');token=(kind,key)
            if token in touched:raise HTTPException(400,'Change each schedule row once.')
            touched.add(token);start,finish=bounds(entry,True);changes={'start_date':start,'due_date':finish}
            if kind=='phase':
                code=phase(entry.get('phase'));current=db.execute('SELECT * FROM project_phases WHERE project_id=? AND phase=?',(project_id,code)).fetchone()
                owner=project['owner_id'] if code=='development' else project['quality_id'] if code=='quality' else project['approver_id'] if project['stage']=='release_approval' else project['release_id']
                if user['id'] not in {owner,project['created_by'],project['owner_id']} and user['role']!='admin':raise HTTPException(403,'Only the phase assignee or project manager can schedule this phase.')
                expected=current['version'] if current else 0
                if entry.get('version')!=expected:raise HTTPException(409,'This phase changed. Refresh the project plan.')
                title=text(entry.get('title',current['title'] if current else LABELS[code]),180,True)
                if current:db.execute('UPDATE project_phases SET title=?,start_date=?,due_date=?,version=version+1 WHERE id=?',(title,start,finish,current['id']))
                else:db.execute('INSERT INTO project_phases(id,project_id,phase,title,start_date,due_date,baseline_due) VALUES(?,?,?,?,?,?,?)',(identity(),project_id,code,title,start,finish,finish))
                changes.update(phase=code,title=title)
                changes.update(previous_start_date=current['start_date'] if current else '',previous_due_date=current['due_date'] if current else '')
            elif kind=='sprint':
                row=db.execute('SELECT * FROM sprints WHERE id=? AND project_id=?',(key,project_id)).fetchone()
                if not row:raise HTTPException(404,'Sprint not found.')
                if row['owner_id']!=user['id']:store.manage(project,user,db)
                if entry.get('version')!=row['version']:raise HTTPException(409,'Refresh this sprint before changing its planned dates.')
                if (date.fromisoformat(finish)-date.fromisoformat(start)).days>90:raise HTTPException(400,'A sprint can span at most 91 calendar days.')
                db.execute('UPDATE sprints SET start_date=?,due_date=?,version=version+1 WHERE id=?',(start,finish,key))
                changes.update(previous_start_date=row['start_date'],previous_due_date=row['due_date'])
            elif kind in {'project','task'}:
                row=store.item(db,key)
                if row['project_id']!=project_id or row['type']!=kind:raise HTTPException(400,'Choose work in this project.')
                store.manage(row,user,db)
                if entry.get('version')!=row['version']:raise HTTPException(409,'This work changed. Refresh the plan before moving it.')
                if row.get('milestone') and start!=finish:raise HTTPException(400,'A milestone uses one date.')
                if kind=='project' and project['stage']=='released':
                    db.execute('INSERT OR IGNORE INTO wh_closed_schedule VALUES(?,?)',(project_id,row['due_date']))
                db.execute('UPDATE items SET start_date=?,due_date=?,version=version+1,updated_at=? WHERE id=?',(start,finish,timestamp(),key))
                changes.update(previous_start_date=row['start_date'],previous_due_date=row['due_date'])
            else:raise HTTPException(400,'Choose a project, phase, sprint or task row.')
            store.event(db,project,user,'schedule_updated',{**changes,'row_type':kind,'row_id':key,'baseline_preserved':True,'actual_dates_preserved':True})
        db.execute('UPDATE items SET updated_at=? WHERE id=?',(timestamp(),project_id))
    return store.detail(project_id)


def change_method(store,user,project_id,payload):
    store.actor(user)
    with store.db(True) as db:
        project=store.item(db,project_id);store.manage(project,user,db)
        if project['type']!='project':raise HTTPException(400,'Choose a project.')
        if payload.get('version')!=project['version']:raise HTTPException(409,'Refresh the project before changing the planning method.')
        selected=method(payload.get('methodology'))
        db.execute('UPDATE items SET methodology=?,version=version+1,updated_at=? WHERE id=?',(selected,timestamp(),project_id))
        store.event(db,project,user,'planning_method_updated',{'before':project['methodology'],'after':selected,'existing_work_preserved':True})
    return store.detail(project_id)

def save_sprint(store,user,project_id,payload,sprint_id=None):
    store.actor(user)
    with store.db(True) as db:
        project=store.item(db,project_id)
        if project['type']!='project' or project['stage']=='released':raise HTTPException(409,'Choose an active project.')
        if project.get('methodology') not in {'agile','sprint'}:raise HTTPException(400,'Choose Agile or Sprint in the project plan first.')
        existing=db.execute('SELECT * FROM sprints WHERE id=? AND project_id=?',(sprint_id,project_id)).fetchone() if sprint_id else None
        if sprint_id and not existing:raise HTTPException(404,'Sprint not found.')
        if not existing or existing['owner_id']!=user['id']:store.manage(project,user,db)
        if existing and payload.get('version')!=existing['version']:raise HTTPException(409,'This sprint changed. Refresh before saving.')
        old=dict(existing) if existing else {};status=payload.get('status',old.get('status','planned'))
        if status not in {'planned','active','closed'}:raise HTTPException(400,'Choose Planned, Active or Closed.')
        start,finish=bounds({**old,**payload},True)
        if (date.fromisoformat(finish)-date.fromisoformat(start)).days>90:raise HTTPException(400,'A sprint can span at most 91 calendar days.')
        if status=='closed':
            work=list(db.execute('SELECT stage FROM items WHERE sprint_id=?',(sprint_id,))) if sprint_id else []
            if not work:raise HTTPException(409,'Assign and complete sprint work before closing it.')
            if any(row['stage'] not in DONE_DEVELOPMENT for row in work):raise HTTPException(409,'Complete the sprint tasks or move unfinished work to the backlog before closing it.')
        title=text(payload.get('title',old.get('title','')),120,True);goal=text(payload.get('goal',old.get('goal','')),2000)
        owner=store.user_id(payload.get('owner_id',old.get('owner_id',project['owner_id'])))
        key=sprint_id or identity()
        if existing:db.execute('UPDATE sprints SET title=?,goal=?,owner_id=?,start_date=?,due_date=?,status=?,version=version+1 WHERE id=?',(title,goal,owner,start,finish,status,key))
        else:db.execute('INSERT INTO sprints(id,project_id,title,goal,owner_id,start_date,due_date,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(key,project_id,title,goal,owner,start,finish,status,timestamp()))
        store.event(db,project,user,'sprint_updated' if existing else 'sprint_created',{'sprint_id':key,'title':title,'status':status,'start_date':start,'due_date':finish})
        store.notify(db,project,user['id'],[owner],'Sprint '+status+': '+title,goal or 'Open the project sprint plan.')
    return store.detail(project_id)
