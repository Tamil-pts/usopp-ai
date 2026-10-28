"""Versioned Competency Hub assessments, independent review and scoped work profiles."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from . import store,scoring
from .store import hub,org,identity,timestamp,text,encode,day


def _config():
    store.initialize()
    with hub.db() as db:return store.configuration(db)


def metadata(user):
    store.initialize();org.personal(user)
    with hub.db() as db:
        allowed=org.managed_people(db,user);config=store.configuration(db)
        return {'configuration':config,'organization':org.directory(user),'subject_ids':sorted(allowed),
                'can_configure':user['role']=='admin' or bool(allowed-{user['id']}),'can_team':bool(allowed-{user['id']}),
                'levels':store.LEVELS,'user_id':user['id'],'can_configure_work':user['role']=='admin',
                'projects':[dict(r) for r in db.execute("SELECT id,title FROM items WHERE type='project' ORDER BY title")],
                'reviewers':{str(subject):[u['id'] for u in org.people() if u['active'] and org.can_review(db,u,subject)] for subject in allowed}}


def _row(db,key):
    row=db.execute('SELECT * FROM px_assessments WHERE id=?',(key,)).fetchone()
    if not row:raise HTTPException(404,'Assessment not found.')
    return dict(row)


def _revision(db,key):
    row=db.execute('SELECT * FROM px_revisions WHERE id=?',(key,)).fetchone()
    if not row:raise HTTPException(404,'Assessment revision not found.')
    value=dict(row)
    for name in ('content','methodology'):value[name]=json.loads(value[name])
    return value


def _source(db,user,kind,key):
    if not isinstance(key,str) or len(key)>80:raise HTTPException(400,'Choose a valid work reference.')
    if not isinstance(kind,str):raise HTTPException(400,'Choose a valid work reference type.')
    if kind in {'project','task'}:
        row=hub.item(db,key)
        if row['type']!=kind:raise HTTPException(400,'Choose the matching work reference type.')
        return {'kind':kind,'id':key,'title':row['title'],'project_id':row['project_id'],'task_id':key if kind=='task' else None,'status':row['stage']}
    if kind=='document':
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pi_documents'").fetchone():raise HTTPException(404,'No WorkHub documents are available.')
        row=db.execute('SELECT * FROM pi_documents WHERE id=?',(key,)).fetchone()
        if not row:raise HTTPException(404,'WorkHub document not found.')
        project=hub.item(db,row['project_id'])
        library_preview=False
        if project.get('is_document_space'):
            from backend.core.workhub_document_spaces import authorize
            authorize(db,project,user,allow_library=True)
            library_preview=user['role']!='admin' and user['id'] not in {project['owner_id'],project['reviewer_id']}
            if library_preview and not row['approved_revision']:raise HTTPException(403,'This library document has no approved revision to reference.')
        control=db.execute('SELECT id,stage FROM qc_documents WHERE document_id=?',(key,)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_documents'").fetchone() else None
        revision=db.execute('SELECT status FROM pi_revisions WHERE id=?',(row['approved_revision'] if library_preview else row['current_revision'],)).fetchone()
        return {'kind':kind,'id':key,'title':row['title'],'project_id':row['project_id'],'status':revision['status'] if revision else 'draft',
                'section':'meetings' if row['kind'] in {'frd','mom','flowchart'} else 'quality' if row['kind'] in {'fat','quality','closure'} else 'documents',
                'stage':control['stage'] if control else 'native:'+key,'independent':bool(project.get('is_document_space')),
                'library_preview_only':library_preview,'pdf_url':'/api/workhub/documents/'+key+'/library-preview' if library_preview else None}
    if kind=='contribution':
        from backend.core.workhub_growth import store as growth
        obj=growth.object_row(db,'article',key);growth.require_read(db,user,'article',obj)
        rev=growth.revision(db,'article',obj['published_revision'] or obj['current_revision'],key)
        return {'kind':kind,'id':key,'title':rev['title'],'project_id':obj['project_id']}
    raise HTTPException(400,'Choose a project, task, document or TechShare contribution.')


def _references(db,user,reviewer,values):
    if not isinstance(values,list) or len(values)>25:raise HTTPException(400,'Use up to 25 work references per dimension.')
    result=[];seen=set()
    for value in values:
        if not isinstance(value,dict):raise HTTPException(400,'Choose structured work references.')
        source=_source(db,user,value.get('kind'),value.get('id'))
        _source(db,reviewer,value.get('kind'),value.get('id'))
        key=(source['kind'],source['id'])
        if key not in seen:seen.add(key);result.append(source)
    return result


def _content(db,user,reviewer,payload,methodology):
    raw=payload.get('content',{})
    if not isinstance(raw,dict):raise HTTPException(400,'Provide assessment details.')
    value={'summary':text(raw.get('summary',''),4000),'references':_references(db,user,reviewer,raw.get('references',[])),'competencies':{},'performance':{}}
    model=methodology['template']
    for field in ('competencies','performance'):
        entered=raw.get(field,{})
        if not isinstance(entered,dict) or len(entered)>100:raise HTTPException(400,'Provide structured dimension values.')
        allowed={b['competency_id'] for b in model[field]} if field=='competencies' else {b['id'] for b in model[field]}
        if not entered.keys()<=allowed:raise HTTPException(400,'A dimension is outside the selected role model.')
        for key,row in entered.items():
            if not isinstance(row,dict):raise HTTPException(400,'Provide dimension details.')
            item={'note':text(row.get('note',''),4000),'references':_references(db,user,reviewer,row.get('references',[]))}
            if field=='competencies':
                score=row.get('level');item['level']=None if score is None else store.number(score,1,5,'Current proficiency',True)
            else:
                score=row.get('value');item['value']=None if score is None else store.number(score,0,100,'Performance measurement')
                na=row.get('not_applicable',False)
                if type(na)is not bool:raise HTTPException(400,'Choose whether the dimension is applicable.')
                if na and (not item['note'] or score is not None):raise HTTPException(400,'A not-applicable dimension needs a reason and no score.')
                item['not_applicable']=na
            value[field][key]=item
    return value


def save_assessment(user,payload,key=None):
    store.initialize()
    from backend.core.workhub_growth import store as growth
    growth.initialize()
    with hub.db(True) as db:
        previous=_row(db,key) if key else None
        subject=previous['subject_id'] if previous else payload.get('subject_id',user['id'])
        store.authorize(db,user,subject)
        if previous and previous['status']=='submitted':raise HTTPException(409,'This revision is in review. Request changes before editing.')
        if payload.get('version')!=(previous['version'] if previous else 0):raise HTTPException(409,'The assessment changed. Refresh before saving.')
        if previous and user['id'] not in {subject,previous['created_by']} and user['role']!='admin':raise HTTPException(403,'Only the author, employee or Admin can prepare this assessment.')
        config=store.configuration(db);template_id=previous['template_id'] if previous else payload.get('template_id')
        period_id=previous['period_id'] if previous else payload.get('period_id')
        period=next((p for p in config['content']['periods'] if p['id']==period_id and p['active']),None)
        model=next((p for p in config['content']['templates'] if p['id']==template_id and p['active']),None)
        if not period or not model:raise HTTPException(400,'Choose an active assessment period and role model.')
        profile=org.profile(db,subject)
        if profile['role_id']!=model['role_id'] or model['department_id'] and profile['department_id']!=model['department_id']:raise HTTPException(400,'Use the employee role and department recorded in Team Details.')
        reviewer_id=payload.get('reviewer_id',previous['reviewer_id'] if previous else None)
        reviewer=org.person(reviewer_id)
        if reviewer_id==user['id'] or not org.can_review(db,reviewer,subject):raise HTTPException(403,'Choose another authorized manager or Admin as independent reviewer. The preparer cannot review their own revision.')
        if not previous and db.execute('SELECT 1 FROM px_assessments WHERE subject_id=? AND period_id=? AND template_id=?',(subject,period_id,template_id)).fetchone():raise HTTPException(409,'An assessment already exists for this employee, period and role. Open it to prepare a new revision.')
        methodology={'configuration_version':config['version'],'period':period,'template':model,'competencies':config['content']['competencies'],'levels':store.LEVELS}
        content=_content(db,user,reviewer,payload,methodology);now=timestamp();key=key or identity()
        if not previous:db.execute('INSERT INTO px_assessments(id,subject_id,period_id,template_id,reviewer_id,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(key,subject,period_id,template_id,reviewer_id,user['id'],now,now))
        revision=identity();number=db.execute('SELECT COALESCE(MAX(number),0)+1 FROM px_revisions WHERE assessment_id=?',(key,)).fetchone()[0]
        db.execute('INSERT INTO px_revisions VALUES(?,?,?,?,?,?,?)',(revision,key,number,encode(content),encode(methodology),user['id'],now))
        db.execute("UPDATE px_assessments SET current_revision=?,reviewer_id=?,status='draft',version=?,updated_at=? WHERE id=?",(revision,reviewer_id,(previous['version'] if previous else 0)+1,now,key))
        store.audit(db,user,key,revision,'draft_saved')
    return assessment(user,key)


def assessment(user,key):
    store.initialize()
    with hub.db() as db:
        row=_row(db,key);store.authorize(db,user,row['subject_id'])
        revision=_revision(db,row['current_revision'])
        # Return navigable references only while the current reader retains
        # access. The original immutable revision remains in the audit store.
        content=revision['content']
        content['references']=[r for ref in content.get('references',[]) if (r:=_visible_reference(db,user,ref))]
        for field in ('competencies','performance'):
            for dimension in content.get(field,{}).values():dimension['references']=[r for ref in dimension.get('references',[]) if (r:=_visible_reference(db,user,ref))]
        return {'assessment':row,'revision':revision,
                'can_edit':user['role']=='admin' or user['id'] in {row['subject_id'],row['created_by']},
                'revisions':[{'id':r['id'],'number':r['number'],'author_id':r['author_id'],'created_at':r['created_at']} for r in db.execute('SELECT * FROM px_revisions WHERE assessment_id=? ORDER BY number DESC',(key,))],
                'audit':[dict(r) for r in db.execute('SELECT * FROM px_reviews WHERE assessment_id=? ORDER BY created_at,id',(key,))],
                'preview':scoring.calculate(revision['methodology']['template'],revision['content'],{c['id']:c for c in revision['methodology']['competencies']}),
                'can_review':row['status']=='submitted' and row['reviewer_id']==user['id'] and revision['author_id']!=user['id'] and org.can_review(db,user,row['subject_id'])}


def review(user,key,payload):
    store.initialize()
    with hub.db(True) as db:
        row=_row(db,key);store.authorize(db,user,row['subject_id'])
        if payload.get('version')!=row['version'] or payload.get('revision_id')!=row['current_revision']:raise HTTPException(409,'Review the current assessment revision.')
        action=payload.get('action');comment=text(payload.get('comment',''),4000)
        if action=='submit':
            if row['status'] not in {'draft','changes_requested'} or user['id'] not in {row['subject_id'],row['created_by']} and user['role']!='admin':raise HTTPException(403,'Only the assessment author can submit this draft.')
            revision=_revision(db,row['current_revision']);content=revision['content']
            if not any(c.get('level') is not None for c in content['competencies'].values()) and not any(c.get('value') is not None for c in content['performance'].values()):raise HTTPException(400,'Record at least one supported assessment value before submission.')
            status='submitted'
        elif action in {'approve','request_changes'}:
            if row['status']!='submitted' or row['reviewer_id']!=user['id'] or _revision(db,row['current_revision'])['author_id']==user['id'] or not org.can_review(db,user,row['subject_id']):raise HTTPException(403,'Only the assigned independent reviewer can decide this assessment. The preparer cannot approve their own revision.')
            if not comment:raise HTTPException(400,'Record reviewer comments and verification details.')
            status='approved' if action=='approve' else 'changes_requested'
            if action=='approve':db.execute('UPDATE px_assessments SET approved_revision=current_revision WHERE id=?',(key,))
        else:raise HTTPException(400,'Choose submit, approve or request changes.')
        db.execute('UPDATE px_assessments SET status=?,version=version+1,updated_at=? WHERE id=?',(status,timestamp(),key))
        store.audit(db,user,key,row['current_revision'],action,comment)
    return assessment(user,key)


def _visible_reference(db,user,value):
    try:return _source(db,user,value['kind'],value['id'])
    except (HTTPException,KeyError):return None


def _experience(db,user,subject):
    tasks=[dict(r) for r in db.execute("SELECT id,project_id,title,kind,stage,start_date,due_date,completed_at,owner_id,quality_id,approver_id,release_id FROM items WHERE type='task' AND ? IN (created_by,owner_id,quality_id,approver_id,release_id) ORDER BY created_at DESC LIMIT 500",(subject,))]
    projects=[dict(r) for r in db.execute("SELECT DISTINCT p.id,p.title,p.kind,p.stage,p.due_date FROM items p WHERE p.type='project' AND (? IN (p.created_by,p.owner_id,p.quality_id,p.approver_id,p.release_id) OR EXISTS(SELECT 1 FROM items t WHERE t.project_id=p.id AND t.type='task' AND ? IN (t.created_by,t.owner_id,t.quality_id,t.approver_id,t.release_id))) ORDER BY p.created_at DESC",(subject,subject))]
    return {'projects':projects,'assignments':tasks,'domains':sorted({p['kind'] for p in projects}),
            'completed_assignments':sum(t['stage'] in {'development_completed','quality','release_approval','ready_release','released'} for t in tasks),
            'responsibilities':[{'project_id':p['id'],'project':p['title']} for p in projects]}


def profile(user,subject,period_id=''):
    store.initialize()
    with hub.db() as db:
        store.authorize(db,user,subject);config=store.configuration(db);today=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()
        periods=config['content']['periods']
        period=next((p for p in periods if p['id']==period_id),None) if period_id else next((p for p in reversed(periods) if p['active'] and p['start']<=today<=p['end']),periods[-1] if periods else None)
        if period_id and not period:raise HTTPException(404,'Assessment period not found.')
        rows=[dict(r) for r in db.execute('SELECT * FROM px_assessments WHERE subject_id=? ORDER BY updated_at DESC',(subject,))]
        if period:rows=[r for r in rows if r['period_id']==period['id']]
        approval_times={r['revision_id']:r['created_at'] for r in db.execute("SELECT revision_id,created_at FROM px_reviews WHERE action='approve'")}
        approved=max((r for r in rows if r['approved_revision']),key=lambda r:(approval_times.get(r['approved_revision'],''),r['id']),default=None)
        revision=_revision(db,approved['approved_revision']) if approved else None
        if revision:period=revision['methodology']['period']
        org_profile=org.profile(db,subject)
        model=revision['methodology']['template'] if revision else next((t for t in config['content']['templates'] if t['active'] and t['role_id']==org_profile['role_id'] and (not t['department_id'] or t['department_id']==org_profile['department_id'])),{'competencies':[],'performance':[],'method':'weighted_mean'})
        definitions={c['id']:c for c in (revision['methodology']['competencies'] if revision else config['content']['competencies'])}
        result=scoring.calculate(model,revision['content'] if revision else {},definitions)
        for row in [*result['competencies'],*result['performance']]:row['references']=[r for ref in row['references'] if (r:=_visible_reference(db,user,ref))]
        history=[]
        for r in db.execute("SELECT rev.*,review.created_at AS reviewed_at,review.actor_id AS reviewer_id,review.comment FROM px_revisions rev JOIN px_assessments a ON a.id=rev.assessment_id JOIN px_reviews review ON review.revision_id=rev.id AND review.action='approve' WHERE a.subject_id=? ORDER BY review.created_at",(subject,)):
            data=dict(r);method=json.loads(data['methodology']);content=json.loads(data['content']);score=scoring.calculate(method['template'],content,{c['id']:c for c in method['competencies']})
            for dimension in [*score['competencies'],*score['performance']]:dimension['references']=[r for ref in dimension['references'] if (r:=_visible_reference(db,user,ref))]
            history.append({'revision_id':data['id'],'at':data['reviewed_at'],'period':method['period'],'performance_index':score['performance_index'],'competency_index':score['competency_index'],
                            'competencies':score['competencies'],'performance':score['performance'],'reviewer_id':data['reviewer_id'],'comment':data['comment']})
        goals=[dict(r) for r in db.execute('SELECT * FROM px_development WHERE subject_id=? ORDER BY due_date,title',(subject,))]
        progress=round(100*sum(g['status']=='completed' for g in goals)/len(goals),1) if goals else None
        person=org.person(subject,False)
        reviewer=next((h for h in reversed(history) if revision and h['revision_id']==revision['id']),None)
        if reviewer:
            reviewer_person=next((u for u in org.people() if u['id']==reviewer['reviewer_id']),{'username':'Former user '+str(reviewer['reviewer_id']),'designation':''})
            reviewer={**reviewer,'reviewer_name':reviewer_person['username'],'reviewer_designation':reviewer_person['designation']}
        units={r['id']:r['name'] for r in db.execute('SELECT id,name FROM wh_org_units')}
        org_profile={**org_profile,'department':units.get(org_profile['department_id'],'Not assigned'),'professional_role':units.get(org_profile['role_id'],person['designation']),'teams':[units[t] for t in org_profile['team_ids'] if t in units]}
        if subject not in org.managed_people(db,user):org_profile['availability_note']=''
        return {**result,'person':{'id':person['id'],'username':person['username'],'designation':person['designation']},'team_details':org_profile,'period':period,
                'model':model,'approved_revision':revision['id'] if revision else None,'review':reviewer,'assessments':rows,
                'history':history,'development':goals,'development_progress':progress,'experience':_experience(db,user,subject)}


def team(user,period_id='',department_id='',team_id='',role_id='',employee_id=None,project_id=''):
    store.initialize();org.personal(user)
    with hub.db() as db:
        allowed=org.managed_people(db,user);people=[]
        for u in org.people():
            if not u['active'] or u['id'] not in allowed or employee_id and employee_id!=u['id']:continue
            p=org.profile(db,u['id'])
            if department_id and p['department_id']!=department_id or team_id and team_id not in p['team_ids'] or role_id and p['role_id']!=role_id:continue
            if project_id and not db.execute('SELECT 1 FROM items WHERE project_id=? AND ? IN (created_by,owner_id,quality_id,approver_id,release_id) LIMIT 1',(project_id,u['id'])).fetchone():continue
            people.append(u['id'])
    rows=[profile(user,uid,period_id) for uid in people]
    return {'people':rows,'scope':'Managed teams and reporting relationships' if user['role']!='admin' else 'All authorized employees',
            'assessed':sum(r['approved_revision'] is not None for r in rows),'total':len(rows)}


def save_development(user,payload,key=None):
    store.initialize()
    with hub.db(True) as db:
        previous=db.execute('SELECT * FROM px_development WHERE id=?',(key,)).fetchone() if key else None
        if key and not previous:raise HTTPException(404,'Development goal not found.')
        subject=previous['subject_id'] if previous else payload.get('subject_id',user['id']);store.authorize(db,user,subject)
        if payload.get('version')!=(previous['version'] if previous else 0):raise HTTPException(409,'This development goal changed.')
        competency=payload.get('competency_id') or ''
        if competency and competency not in {c['id'] for c in store.configuration(db)['content']['competencies']}:raise HTTPException(400,'Choose a configured competency.')
        status=payload.get('status','planned')
        if not isinstance(status,str) or status not in {'planned','in_progress','completed','on_hold'}:raise HTTPException(400,'Choose a development status.')
        target=payload.get('target_level')
        if target is not None:store.number(target,1,5,'Target proficiency',True)
        project_id=payload.get('project_id') or None;task_id=payload.get('task_id') or None
        if project_id:_source(db,user,'project',project_id)
        if task_id:
            task=_source(db,user,'task',task_id)
            if task['project_id']!=project_id:raise HTTPException(400,'Choose a task within the selected project.')
        value={'id':key or identity(),'subject_id':subject,'competency_id':competency,'title':text(payload.get('title',''),180,True),'description':text(payload.get('description',''),4000),
               'target_level':target,'due_date':day(payload.get('due_date','')),'status':status,'project_id':project_id,'task_id':task_id,'version':(previous['version'] if previous else 0)+1,
               'created_by':previous['created_by'] if previous else user['id'],'updated_at':timestamp()}
        db.execute('INSERT OR REPLACE INTO px_development VALUES(:id,:subject_id,:competency_id,:title,:description,:target_level,:due_date,:status,:project_id,:task_id,:version,:created_by,:updated_at)',value)
        org.audit(db,user,'development_goal',value['id'],dict(previous) if previous else {},value)
        return value
