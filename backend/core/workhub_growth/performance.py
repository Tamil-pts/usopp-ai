"""Explainable indicators from native facts and independently verified evidence."""
from collections import defaultdict,Counter
from datetime import datetime,timedelta,timezone
import json
import math
import os
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from . import store,collector
from .store import hub,identity,timestamp,text,encode,day


def window(days):
    if type(days) is not int or days not in {30,90,180,365}:raise HTTPException(400,'Choose 30, 90, 180 or 365 days.')
    return (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()


def _event(row):return {**dict(row),'data':json.loads(row['data'])}


def manual_save(user,payload,key=None):
    store.initialize();store.personal(user)
    with hub.db(True) as db:
        previous=store.object_row(db,'evidence',key) if key else None
        if previous:
            store.author(user,previous)
            if payload.get('version')!=previous['current_revision']:raise HTTPException(409,'This evidence changed. Refresh before saving.')
        project_id,task_id=store.project_link(db,user,payload.get('project_id') or None,payload.get('task_id') or None,contribute=True)
        if previous and previous['approved_revision'] and (project_id!=previous['project_id'] or task_id!=previous['task_id']):raise HTTPException(409,'Keep the project and task link of previously approved evidence. Create a separate record for other work.')
        content=payload.get('content',{})
        if not isinstance(content,dict):raise HTTPException(400,'Provide the evidence details.')
        value={field:text(content.get(field,'') or '',4000,field in {'title','description'}) for field in ('title','description','outcome','verification_method')}
        value['title']=text(value['title'],180,True);value['activity']=text(content.get('activity','General engineering'),100,True)
        value['work_date']=day(content.get('work_date') or datetime.now(timezone.utc).date().isoformat())
        value['capabilities']=store.capabilities(content.get('capabilities',[]));value['source_event_id']=content.get('source_event_id') or None
        if value['source_event_id']:
            source=db.execute('SELECT * FROM pc_events WHERE id=?',(value['source_event_id'],)).fetchone()
            if not source or source['project_id'] and source['project_id']!=project_id or user['id'] not in {source['subject_id'],source['actor_id']}:raise HTTPException(400,'Link your own recorded activity in this project.')
            if source['task_id'] and source['task_id']!=task_id:raise HTTPException(400,'Keep the task already recorded on the source event.')
        now=timestamp();object_id=key or identity()
        if not previous:db.execute('INSERT INTO pc_manual(id,author_id,project_id,task_id,created_at,updated_at) VALUES(?,?,?,?,?,?)',(object_id,user['id'],project_id,task_id,now,now))
        value['file_ids']=store.owned_files(db,user,'evidence',object_id,content.get('file_ids',[]))
        number=db.execute('SELECT COALESCE(MAX(number),0)+1 FROM pc_manual_revisions WHERE evidence_id=?',(object_id,)).fetchone()[0];rev=identity()
        db.execute('INSERT INTO pc_manual_revisions(id,evidence_id,number,content,created_at) VALUES(?,?,?,?,?)',(rev,object_id,number,store.bounded(value),now))
        db.execute('UPDATE pc_manual SET project_id=?,task_id=?,current_revision=?,updated_at=? WHERE id=?',(project_id,task_id,rev,now,object_id))
        store.action(db,user,'evidence',object_id,rev,'draft_saved')
        return {'id':object_id,'revision_id':rev,'number':number}


def manual_detail(user,key):
    store.initialize()
    with hub.db() as db:
        obj=store.object_row(db,'evidence',key);store.require_read(db,user,'evidence',obj)
        privileged=obj['author_id']==user['id'] or user['role']=='admin'
        managed=obj['project_id'] in store.managed_projects(db,user)
        revisions=[store.revision(db,'evidence',r['id'],key) for r in db.execute('SELECT id FROM pc_manual_revisions WHERE evidence_id=? ORDER BY number DESC',(key,))]
        revisions=[r for r in revisions if privileged or r['reviewer_id']==user['id'] and r['status']!='draft' or managed and r['status']=='approved']
        if not revisions:raise HTTPException(403,'No evidence revision is available to your account.')
        file_ids={file_id for r in revisions for file_id in r['content'].get('file_ids',[])};revision_ids={r['id'] for r in revisions}
        return {'evidence':obj,'revisions':revisions,'reviewers':store.reviewers(db,obj['project_id'],obj['author_id']),
                'files':[dict(r) for r in db.execute("SELECT * FROM cp_files WHERE object_type='evidence' AND object_id=?",(key,)) if privileged or r['id'] in file_ids],
                'history':[dict(r) for r in db.execute("SELECT * FROM cp_actions WHERE object_type='evidence' AND object_id=? ORDER BY created_at DESC",(key,)) if privileged or r['revision_id'] in revision_ids]}


def manual_review(user,key,payload):
    store.initialize();store.personal(user)
    with hub.db(True) as db:
        obj=store.object_row(db,'evidence',key);rev=store.revision(db,'evidence',payload.get('revision_id'),key)
        if obj['current_revision']!=rev['id']:raise HTTPException(409,'Review the latest evidence revision.')
        action=payload.get('action');comment=text(payload.get('comment',''),4000);now=timestamp()
        if action=='submit':
            store.author(user,obj)
            if rev['status']!='draft':raise HTTPException(409,'Save a new draft revision before resubmitting.')
            reviewer=store.review_user(db,obj['project_id'],obj['author_id'],payload.get('reviewer_id'))
            if not rev['content'].get('outcome') or not rev['content'].get('verification_method'):raise HTTPException(400,'Describe the result and how the reviewer can verify it.')
            db.execute("UPDATE pc_manual_revisions SET status='submitted',reviewer_id=? WHERE id=?",(reviewer,rev['id']))
            store.notify(db,user,obj,[reviewer],'Engineering evidence review',rev['content']['title'])
        elif action in {'approve','reject'}:
            if rev['status']!='submitted' or rev['reviewer_id']!=user['id']:raise HTTPException(403,'Only the assigned reviewer can verify this evidence.')
            store.review_user(db,obj['project_id'],obj['author_id'],user['id'])
            if not comment:raise HTTPException(400,'Record the verification checks or reason for rejection.')
            if action=='approve' and rev['content'].get('source_event_id'):
                for other in db.execute('SELECT m.id,r.content FROM pc_manual m JOIN pc_manual_revisions r ON r.id=m.approved_revision WHERE m.author_id=? AND m.id!=?',(obj['author_id'],key)):
                    if json.loads(other['content']).get('source_event_id')==rev['content']['source_event_id']:raise HTTPException(409,'This source activity already has approved evidence. Revise that evidence record instead of verifying the same activity twice.')
            caps=store.capabilities(payload.get('capabilities',[])) if action=='approve' else []
            db.execute('UPDATE pc_manual_revisions SET status=?,reviewed_at=?,reviewed_by=?,comment=?,verified_capabilities=? WHERE id=?',('approved' if action=='approve' else 'rejected',now,user['id'],comment,encode(caps),rev['id']))
            if action=='approve':db.execute('UPDATE pc_manual SET approved_revision=?,updated_at=? WHERE id=?',(rev['id'],now,key))
            store.notify(db,user,obj,[obj['author_id']],'Engineering evidence '+('verified' if action=='approve' else 'returned'),comment)
        else:raise HTTPException(400,'Choose submit, approve or reject.')
        store.action(db,user,'evidence',key,rev['id'],action,{'comment':comment})
    return manual_detail(user,key)


def _scoped(project_id,projects):return projects is None or project_id in projects


def _proofs(db,person_id,projects,since):
    proofs=[]
    for row in db.execute('SELECT m.*,r.content,r.reviewed_at,r.verified_capabilities,r.reviewed_by,r.number FROM pc_manual m JOIN pc_manual_revisions r ON r.id=m.approved_revision WHERE m.author_id=? AND r.reviewed_at>=?',(person_id,since)):
        if not _scoped(row['project_id'],projects):continue
        content=json.loads(row['content']);proofs.append({'id':'manual:'+row['id'],'source':'manual','object_id':row['id'],'revision_id':row['approved_revision'],'title':content['title'],'at':row['reviewed_at'],'project_id':row['project_id'],'task_id':row['task_id'],'capabilities':json.loads(row['verified_capabilities']),'reviewed_by':row['reviewed_by'],'revision':row['number'],'activity':content['activity']})
    for row in db.execute('SELECT a.*,r.title,r.published_at,r.verified_capabilities,r.reviewed_by,r.number FROM cp_articles a JOIN cp_revisions r ON r.id=a.published_revision WHERE a.author_id=? AND r.published_at>=?',(person_id,since)):
        if not _scoped(row['project_id'],projects):continue
        proofs.append({'id':'article:'+row['id'],'source':'article','object_id':row['id'],'revision_id':row['published_revision'],'title':row['title'],'at':row['published_at'],'project_id':row['project_id'],'task_id':row['task_id'],'capabilities':list(set(json.loads(row['verified_capabilities']))|{'knowledge_sharing'}),'reviewed_by':row['reviewed_by'],'revision':row['number'],'activity':'Knowledge sharing'})
    return proofs


def _profile(db,user,person_id,days,project_filter=None,with_details=True):
    since=window(days);projects=store.scope(db,user,person_id)
    if project_filter:
        hub.item(db,project_filter)
        if projects is not None and project_filter not in projects:raise HTTPException(403,'Choose a managed project.')
        projects={project_filter}
    person=next((u for u in hub.users() if u['id']==person_id),None)
    if not person:raise HTTPException(404,'Engineer not found.')
    events=[_event(r) for r in db.execute('SELECT * FROM pc_events WHERE (subject_id=? OR actor_id=?) AND occurred_at>=? ORDER BY occurred_at DESC',(person_id,person_id,since)) if _scoped(r['project_id'],projects)]
    # Facts are de-duplicated by deliverable, independent of run/issue counts.
    reviewed={};released={};completed={};document_proofs={}
    for event in events:
        if event['subject_id']!=person_id:continue
        item_id=event['data'].get('item_id')
        if event['event_type']=='complete_development' and item_id not in completed:completed[item_id]=event
        if event['verification']=='independent_review' and event['event_type']=='quality_pass':reviewed.setdefault(item_id,event)
        if event['verification']=='independent_review' and event['event_type']=='release':released.setdefault(item_id,event)
        if event['verification']=='independent_review' and event['event_type']=='intelligence_document_approve':document_proofs.setdefault(event['data'].get('document_id'),event)
    # A project and its tasks represent different levels of the same work. Use
    # leaf task evidence when available, otherwise retain project-level reviews.
    leafs={r['id'] for r in db.execute("SELECT id FROM items i WHERE type='task' AND NOT EXISTS(SELECT 1 FROM items child WHERE child.parent_id=i.id)")}
    task_review_projects={event['project_id'] for event in reviewed.values() if event['task_id'] in leafs}
    task_release_projects={event['project_id'] for event in released.values() if event['task_id'] in leafs}
    def deliverable(event,task_projects):return event['task_id'] in leafs if event['task_id'] else event['project_id'] not in task_projects
    reviewed={key:value for key,value in reviewed.items() if deliverable(value,task_review_projects)};released={key:value for key,value in released.items() if deliverable(value,task_release_projects)}
    proofs=_proofs(db,person_id,projects,since)
    for kind,values,caps in [('quality',reviewed,['work_quality','execution']),('release',released,['ownership']),('document',document_proofs,['work_quality'])]:
        for key,event in values.items():proofs.append({'id':'native:'+kind+':'+str(key),'source':'event','object_id':event['id'],'title':event['title'],'at':event['occurred_at'],'project_id':event['project_id'],'task_id':event['task_id'],'capabilities':caps,'reviewed_by':event['actor_id'],'activity':'Reviewed delivery' if kind!='document' else 'Reviewed documentation'})
    eligible=[e for e in released.values() if e['data'].get('due_date') and e['data'].get('completed_at')]
    tz_name=os.getenv('USOPP_WORKHUB_TIMEZONE') or os.getenv('TZ') or 'UTC'
    try:tz=ZoneInfo(tz_name)
    except (KeyError,ValueError):tz=timezone.utc;tz_name='UTC'
    def finished_day(value):
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(tz).date().isoformat()
    on_time=[e for e in eligible if finished_day(e['data']['completed_at'])<=e['data']['due_date']]
    cap_data=[]
    for key,title in store.CAPABILITIES.items():
        matching=[p for p in proofs if key in p['capabilities']];diversity=len({p['project_id'] or p['id'] for p in matching})
        cap_data.append({'id':key,'title':title,'verified_records':len(matching),'projects':len({p['project_id'] for p in matching if p['project_id']}),'level':'Evidence-backed strength' if len(matching)>=3 and diversity>=2 else 'Evidence emerging' if matching else 'Evidence not yet recorded','evidence_ids':[p['id'] for p in matching]})
    assigned=[hub.public(r) for r in db.execute('SELECT * FROM items WHERE ? IN (owner_id,quality_id,approver_id,release_id)',(person_id,)) if _scoped(r['project_id'],projects)]
    project_ids={i['project_id'] for i in assigned}|{e['project_id'] for e in events if e['project_id']}
    project_rows=[]
    for key in project_ids:
        parent=db.execute("SELECT * FROM items WHERE id=? AND type='project'",(key,)).fetchone()
        if not parent:continue
        tasks=[hub.public(row) for row in db.execute("SELECT * FROM items WHERE project_id=? AND type='task'",(key,))]
        public=hub.public(parent);public.update(hub.completion(public,tasks));project_rows.append(public)
    runs=[e for e in events if e['source_type']=='run' and e['subject_id']==person_id]
    latest={}
    # Runs can complete out of order, and imported runs can share a timestamp.
    # The native per-project iteration is the recorded ordering of that work.
    for event in runs:
        key=(event['project_id'] or 'archive-label:'+event['data'].get('source_project_name',''),event['data'].get('kind'));previous=latest.get(key)
        if previous is None or (event['data'].get('iteration') or 0,event['occurred_at'])>(previous['data'].get('iteration') or 0,previous['occurred_at']):latest[key]=event
    validations=[]
    for event in latest.values():
        result=event['data'];summary=result.get('summary') or {};scores=list(result.get('recorded_scores') or [])
        for key in collector.SCORE_FIELDS:
            value=summary.get(key)
            if type(value) in (float,int) and math.isfinite(value) and key not in {row['field'] for row in scores}:scores.append({'field':key,'value':value})
        validations.append({'event_id':event['id'],'project_id':event['project_id'],'source_project_name':result.get('source_project_name'),'origin':result.get('origin'),'tool':result.get('tool'),'kind':result.get('kind'),'iteration':result.get('iteration'),'status':result.get('status'),'summary':summary,'scores':scores,'at':event['occurred_at'],'evidence_url':result.get('evidence_url')})
    start=datetime.now(timezone.utc).date()-timedelta(days=days-1);weeks={}
    for offset in range(0,days,7):
        date=start+timedelta(days=offset);weeks[date.isoformat()]={'week':date.isoformat(),'verified':0,'completed':0,'iterations':0,'issues_resolved':0,'contributions':0}
    def add(at,field):
        try:date=datetime.fromisoformat(at.replace('Z','+00:00')).date()
        except (ValueError,AttributeError):return
        delta=(date-start).days
        if delta<0:return
        key=(start+timedelta(days=(delta//7)*7)).isoformat()
        if key in weeks:weeks[key][field]+=1
    for proof in proofs:add(proof['at'],'verified');add(proof['at'],'contributions') if proof['source']=='article' else None
    for event in completed.values():add(event['occurred_at'],'completed')
    for event in runs:add(event['occurred_at'],'iterations')
    for event in events:
        if event['event_type']=='issue_resolved' and event['actor_id']==person_id:add(event['occurred_at'],'issues_resolved')
    improvements=[];seen_feedback=set()
    for event in events:
        if event['event_type']!='request_changes' or event['subject_id']!=person_id:continue
        key=event['data'].get('item_id');comment=event['data'].get('detail',{}).get('comment')
        current=db.execute('SELECT stage FROM items WHERE id=?',(key,)).fetchone()
        if comment and key not in seen_feedback and current and current['stage'] in {'development','blocked','todo'}:
            seen_feedback.add(key);improvements.append({'title':'Address recorded review feedback','detail':comment,'event_id':event['id'],'project_id':event['project_id'],'task_id':event['task_id']})
    for row in db.execute("SELECT * FROM issues WHERE owner_id=? AND status='open' ORDER BY updated_at DESC LIMIT 10",(person_id,)):
        if _scoped(row['project_id'],projects) and row['title'] not in {item['detail'] for item in improvements}:improvements.append({'title':'Resolve assigned engineering issue','detail':row['title'],'project_id':row['project_id'],'task_id':row['item_id']})
    reviewed_ids={e['data'].get('item_id') for e in events if e['event_type']=='quality_pass' and e['subject_id']==person_id and e['verification']=='independent_review'}
    unverified=len(set(completed)-reviewed_ids)
    if unverified:improvements.append({'title':'Complete independent evidence review','detail':str(unverified)+' completed work item(s) have no independent quality review recorded in this period. This is a verification gap, not a performance deduction.'})
    for capability in cap_data:
        if not capability['verified_records']:improvements.append({'title':'Document '+capability['title'].lower()+' evidence','detail':'A relevant project example, research result, design review or published contribution can establish this capability. Missing evidence is not a negative rating.'})
    manual=[]
    if with_details:
        for row in db.execute('SELECT m.*,r.number,r.status,r.reviewer_id,r.content FROM pc_manual m JOIN pc_manual_revisions r ON r.id=m.current_revision WHERE m.author_id=? ORDER BY m.updated_at DESC',(person_id,)):
            if _scoped(row['project_id'],projects):manual.append({**dict(row),'content':json.loads(row['content'])})
    return {'person':person,'days':days,'scope':'All own records' if projects is None and user['role']!='admin' else 'All authorized records' if projects is None else 'Managed projects only',
        'indicators':{'assigned_projects':len({r['project_id'] for r in assigned}),'contributed_projects':len(project_rows),'assigned_tasks':sum(r['type']=='task' for r in assigned),'completed_tasks':sum(e['task_id'] is not None for e in completed.values()),'development_completed':len(completed),'independently_reviewed_deliverables':len(reviewed),'reviewed_documents':len(document_proofs),'verified_evidence':len(proofs),'published_contributions':sum(p['source']=='article' for p in proofs),'on_time':len(on_time),'on_time_eligible':len(eligible),'on_time_percent':round(100*len(on_time)/len(eligible)) if eligible else None,'validation_iterations':len(runs),'issues_resolved':sum(e['event_type']=='issue_resolved' and e['actor_id']==person_id for e in events)},
        'capabilities':cap_data,'strengths':[c for c in cap_data if c['level']=='Evidence-backed strength'],'improvement_areas':improvements,'trends':list(weeks.values()),
        'projects':sorted(project_rows,key=lambda p:p['title']),'tasks':[t for t in assigned if t['type']=='task'],'validation_results':validations,'proofs':proofs if with_details else [],'events':events[:300] if with_details else [],'event_count':len(events),'manual_evidence':manual,
        'methodology':{'version':'1.0','timezone':tz_name,'composite_score':False,'iteration_penalty':False,'bug_discovery_penalty':False,'capability_basis':'Distinct independently reviewed leaf tasks, or project-level delivery when no task review establishes the same contribution; plus verified manual records and published reviewed articles. Counts show evidence coverage, not a standardized skill grade.','timeliness_basis':'Independently reviewed deliveries with a deadline preserved at their current release. Task and project closure are not both counted for the same person/project. Unknown or historical changed dates are excluded. Completion dates use '+tz_name+'.','validation_basis':'Latest run per project and tool. Recorded scores retain their original field/unit; a completed run is not assumed to have passed.'}}


def profile(user,person_id,days=90,project_id=None):
    store.initialize();collector.collect()
    with hub.db() as db:
        value=_profile(db,user,person_id,days,project_id)
        synced=db.execute("SELECT value FROM pc_state WHERE key='last_collected'").fetchone();value['last_collected']=synced[0] if synced else None
        return value


def team(user,days=90,project_id=None):
    store.initialize();collector.collect();window(days)
    with hub.db() as db:
        projects=store.managed_projects(db,user)
        if user['role']!='admin' and not projects:raise HTTPException(403,'Team overview is available to project managers and Admin.')
        people=hub.users();result=[]
        for person in people:
            try:result.append(_profile(db,user,person['id'],days,project_id,False))
            except HTTPException as error:
                if error.status_code not in {403,404}:raise
        return {'days':days,'people':result,'scope':'All engineers' if user['role']=='admin' else 'Engineers in managed projects','ranking':False}


def event_detail(user,key):
    store.initialize();store.personal(user)
    with hub.db() as db:
        row=db.execute('SELECT * FROM pc_events WHERE id=?',(key,)).fetchone()
        if not row:raise HTTPException(404,'Evidence event not found.')
        if user['role']!='admin' and user['id'] not in {row['subject_id'],row['actor_id']} and row['project_id'] not in store.managed_projects(db,user) and not shared_source(db,user,key):raise HTTPException(403,'This evidence is outside your performance scope.')
        return _event(row)


def history(user,person_id,days=90,project_id=None,kind='all',page=1):
    store.initialize();since=window(days);collector.collect()
    if kind not in {'all','runs','issues'}:raise HTTPException(400,'Choose all activity, engineering runs or issues.')
    if not 1<=page<=10000:raise HTTPException(400,'Choose a valid history page.')
    with hub.db() as db:
        projects=store.scope(db,user,person_id)
        if person_id not in {u['id'] for u in hub.users()}:raise HTTPException(404,'Engineer not found.')
        if project_id:
            hub.item(db,project_id)
            if projects is not None and project_id not in projects:raise HTTPException(403,'Choose a managed project.')
            projects={project_id}
        clauses=['(subject_id=? OR actor_id=?)','occurred_at>=?'];params=[person_id,person_id,since]
        if projects is not None:
            if not projects:return {'items':[],'total':0,'page':page,'page_size':50}
            clauses.append('project_id IN ('+','.join('?' for _ in projects)+')');params.extend(sorted(projects))
        if kind=='runs':clauses.append("source_type='run'")
        elif kind=='issues':clauses.append("event_type IN ('issue_created','issue_resolved','issue_open')")
        query=' FROM pc_events WHERE '+' AND '.join(clauses)
        total=db.execute('SELECT COUNT(*)'+query,params).fetchone()[0]
        values=[_event(row) for row in db.execute('SELECT *'+query+' ORDER BY occurred_at DESC,id DESC LIMIT 50 OFFSET ?',(*params,(page-1)*50))]
        return {'items':values,'total':total,'page':page,'page_size':50}


def shared_source(db,user,key):
    for row in db.execute("SELECT m.project_id,m.approved_revision,r.id,r.content,r.reviewer_id,r.status FROM pc_manual m JOIN pc_manual_revisions r ON r.evidence_id=m.id WHERE r.status IN ('submitted','approved')"):
        if json.loads(row['content']).get('source_event_id')!=key:continue
        if row['reviewer_id']==user['id'] or row['approved_revision']==row['id'] and row['project_id'] in store.managed_projects(db,user):return True
    return False


def source_result(user,key):
    event=event_detail(user,key)
    if event['source_type']!='run':raise HTTPException(400,'This event has no archived engineering result.')
    from backend.core.persistent_store import archived_run
    archived=archived_run(event['source_id'])
    if not archived:raise HTTPException(404,'The original archived result is unavailable.')
    return archived[1]
