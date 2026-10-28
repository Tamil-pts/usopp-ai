"""Bounded, assignment-scoped portfolio projections of existing WorkHub records.

This module does not change workflow/performance calculations or document controls.
Dashboard rules live in WorkHub's existing config table; no parallel status records
or database are created. Every request rechecks scope before reading project facts.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
import json
import math
import threading

from fastapi import HTTPException
from backend.core.workhub import store as hub, DONE_DEVELOPMENT, NEXT_OWNER, encode, day, timestamp

DEFAULT_HEALTH = {'due_soon_days': 7, 'minimum_progress': 75,
                  'slippage_tolerance': 10, 'open_issues_at_risk': True}
ROLE_LABELS = {'management': 'Management', 'project_manager': 'Project Manager',
               'team_lead': 'Team Lead', 'engineer': 'Engineer'}
MAX_PROJECTS, MAX_ROWS = 5000, 100000
READY, LOCK = set(), threading.RLock()


def initialize():
    key = str(hub.root.resolve())
    if key in READY:
        return
    with LOCK:
        if key in READY:
            return
        with hub.db(True) as db:
            db.executescript('''
            CREATE INDEX IF NOT EXISTS portfolio_type_due ON items(type,due_date);
            CREATE INDEX IF NOT EXISTS portfolio_project_stage ON items(project_id,stage,type);
            CREATE INDEX IF NOT EXISTS portfolio_creator ON items(created_by,type);
            CREATE INDEX IF NOT EXISTS portfolio_owner ON items(owner_id,type);
            CREATE INDEX IF NOT EXISTS portfolio_events ON events(project_id,created_at);
            CREATE INDEX IF NOT EXISTS portfolio_issues ON issues(project_id,status);
            CREATE INDEX IF NOT EXISTS portfolio_time ON updates(project_id,time_status);
            ''')
        READY.add(key)


def read(db, sql, args=(), limit=MAX_ROWS):
    rows = db.execute(sql, args).fetchmany(limit + 1)
    if len(rows) > limit:
        raise HTTPException(422, 'Narrow the portfolio filters: this request exceeds the dashboard record limit.')
    return [dict(row) for row in rows]


def roles(db, user):
    hub.actor(user)
    uid = user['id']
    available = ['engineer']
    if user['role'] == 'admin':
        return list(ROLE_LABELS), 'management'
    if db.execute("SELECT 1 FROM items WHERE type='project' AND ? IN (quality_id,approver_id,release_id) LIMIT 1", (uid,)).fetchone():
        available.insert(0, 'team_lead')
    if db.execute("SELECT 1 FROM items WHERE type='project' AND ? IN (created_by,owner_id) LIMIT 1", (uid,)).fetchone():
        available.insert(0, 'project_manager')
    return available, available[0]


def scope(db, user, requested):
    available, default = roles(db, user)
    role = requested or default
    if role not in available:
        raise HTTPException(403, 'This dashboard role is outside your existing project responsibilities.')
    uid = user['id']
    if role == 'management':
        return role, available, '1=1', ()
    if role == 'project_manager':
        return role, available, '? IN (p.created_by,p.owner_id)', (uid,)
    if role == 'team_lead':
        return role, available, '? IN (p.quality_id,p.approver_id,p.release_id)', (uid,)
    return role, available, ('EXISTS (SELECT 1 FROM items a WHERE a.project_id=p.id '
                             'AND (? IN (a.created_by,a.owner_id,a.quality_id,a.approver_id,a.release_id) '
                             'OR EXISTS(SELECT 1 FROM json_each(a.supporting_ids) WHERE value=?)))'), (uid,uid)


def policy(db, project_id=''):
    global_row = db.execute("SELECT value FROM config WHERE key='portfolio:rules'", ()).fetchone()
    global_value = json.loads(global_row[0]) if global_row else {}
    row = db.execute('SELECT value FROM config WHERE key=?', ('portfolio:project:' + project_id,)).fetchone() if project_id else None
    local = json.loads(row[0]) if row else {}
    return {'version': (local if project_id else global_value).get('version', 0),
            'health': {**DEFAULT_HEALTH, **global_value.get('health', {}), **local.get('health', {})},
            'milestone_weights': local.get('milestone_weights', {}),
            'updated_at': (local if project_id else global_value).get('updated_at')}


def calculate(project, tasks, issues, rule, today=None, phase_schedule=()):
    """Pure calculation with explicit lineage and unknown values, used by tests."""
    today = today or date.today()
    closed = project['stage'] == 'released'
    parents = {t['parent_id'] for t in tasks if t.get('parent_id')}
    leaves = [t for t in tasks if t['id'] not in parents]
    milestones = [t for t in tasks if t.get('milestone')]
    existing = hub.completion(project, tasks)
    progress = existing['progress'] if tasks or project['stage'] != 'todo' else None
    basis = 'Existing development, quality and release calculation' if progress is not None else 'No work plan recorded'
    milestone_progress = None
    if milestones:
        weights = rule['milestone_weights']
        total = sum(weights.get(t['id'], t.get('planned_hours') or 1) for t in milestones)
        done = sum(weights.get(t['id'], t.get('planned_hours') or 1) for t in milestones if t['stage'] in DONE_DEVELOPMENT)
        milestone_progress = round(100 * done / total)
        progress = 100 if closed else min(99, milestone_progress)
        basis = 'Weighted milestones; 100% project completion requires release / closure'
    if closed:
        progress = 100
    due = project.get('due_date') or ''
    baseline = project.get('baseline_due') or ''
    start = project.get('start_date') or ''
    planned_progress = None
    plan_finish = baseline or due
    if start and plan_finish and start <= plan_finish:
        duration = (date.fromisoformat(plan_finish) - date.fromisoformat(start)).days
        elapsed = (today - date.fromisoformat(start)).days
        planned_progress = round(100 * min(1, max(0, elapsed / duration))) if duration else (100 if today.isoformat() >= plan_finish else 0)
    overdue_milestones = [t for t in milestones if t['stage'] not in DONE_DEVELOPMENT and t.get('due_date') and t['due_date'] < today.isoformat()]
    blocked = [t for t in tasks if t['stage'] == 'blocked']
    open_issues = [i for i in issues if i['status'] == 'open']
    reasons = []
    if not closed:
        if due and due < today.isoformat():
            reasons.append('Project deadline exceeded')
        if baseline and baseline < today.isoformat():
            reasons.append('Original completion date exceeded')
        if overdue_milestones:
            reasons.append(f'{len(overdue_milestones)} overdue milestone(s)')
        overdue_phases = [p for p in phase_schedule if p['due_date'] and p['due_date'] < today.isoformat()
                          and existing['phase_progress'].get(p['phase'], 0) < 100]
        if overdue_phases:
            reasons.append(f'{len(overdue_phases)} overdue delivery phase(s)')
    if project.get('exception_status')=='cancelled':
        health,status='Not assessed','unassessed'
        reasons=[]
    elif not closed and (blocked or project['stage']=='blocked' or project.get('exception_status')=='on_hold'):
        health,status='Blocked','blocked'
        reasons.append('Project is on hold' if project.get('exception_status')=='on_hold' else 'Unresolved blocked work')
    elif closed:
        health, status = 'Completed', 'completed'
    elif reasons:
        health, status = 'Delayed', 'delayed'
    else:
        if blocked or project['stage'] == 'blocked':
            reasons.append('Unresolved blocked work')
        if open_issues and rule['health']['open_issues_at_risk']:
            reasons.append(f'{len(open_issues)} unresolved issue(s)')
        if planned_progress is not None and progress is not None and planned_progress - progress > rule['health']['slippage_tolerance']:
            reasons.append('Progress is behind the recorded baseline schedule')
        near = today.isoformat() <= due <= (today + timedelta(days=rule['health']['due_soon_days'])).isoformat() if due else False
        if near and (progress is None or progress < rule['health']['minimum_progress']):
            reasons.append('Upcoming deadline needs delivery review')
        health, status = ('At risk', 'at_risk') if reasons else ('On track', 'on_track') if due or any(t.get('due_date') for t in [*milestones, *phase_schedule]) else ('Not assessed', 'unassessed')
    next_milestone = sorted([t for t in milestones if t['stage'] not in DONE_DEVELOPMENT], key=lambda t: (not bool(t.get('due_date')), t.get('due_date') or '', t['title']))
    completed_date = (project.get('completed_at') or '')[:10]
    variance = (date.fromisoformat(completed_date) - date.fromisoformat(baseline)).days if closed and completed_date and baseline else None
    return {**project, 'progress': progress, 'progress_basis': basis, 'workflow_progress': existing['progress'], 'phase_progress': existing['phase_progress'],
            'milestone_progress': milestone_progress, 'planned_progress': planned_progress,
            'health': health, 'status': status, 'reasons': reasons, 'open_issues': len(open_issues),
            'blocked_tasks': len(blocked), 'task_count': len(leaves),
            'completed_tasks': sum(t['stage'] in DONE_DEVELOPMENT for t in leaves),
            'milestone_count': len(milestones), 'completed_milestones': sum(t['stage'] in DONE_DEVELOPMENT for t in milestones),
            'overdue_milestones': len(overdue_milestones), 'next_milestone': next_milestone[0] if next_milestone else None,
            'delivery_variance_days': variance, 'can_configure': False}


def organizations(db, tables):
    if 'wh_brand_records' not in tables:
        return {}, None
    values = read(db, "SELECT r.id,r.data FROM wh_brand_records r WHERE r.kind='organization' AND r.version=(SELECT MAX(x.version) FROM wh_brand_records x WHERE x.kind=r.kind AND x.id=r.id)")
    records = {r['id']: json.loads(r['data']) for r in values}
    default = db.execute('SELECT organization_id FROM wh_brand_defaults WHERE id=1').fetchone()
    return records, default[0] if default else None


def snapshot(user, *, role='', department='', team='', manager=None, status='', from_date='', to_date='', project_id='', today=None):
    initialize()
    today = today or date.today()
    from_date, to_date = day(from_date), day(to_date)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, 'The delivery date range is reversed.')
    if status not in {'', 'active', 'completed', 'delayed', 'at_risk', 'on_track', 'unassessed','blocked','created','assigned','in_progress','quality_review','closure','on_hold','cancelled'}:
        raise HTTPException(400, 'Choose a supported project status.')
    with hub.db() as db:
        db.execute('BEGIN')  # All dashboard totals and lists share one SQLite read snapshot.
        role, available, predicate, args = scope(db, user, role)
        projects = read(db, "SELECT p.* FROM items p WHERE p.type='project' AND " + predicate + ' ORDER BY p.created_at DESC', args, MAX_PROJECTS)
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        orgs, default_org = organizations(db, tables)
        procedures={r['project_id']:r for r in read(db,'SELECT project_id,context,project_type,policy_version FROM qc_projects')} if 'qc_projects' in tables else {}
        contexts={pid:json.loads(row['context']) for pid,row in procedures.items()}
        people = {u['id']: u for u in hub.users()}
        for p in projects:
            org = orgs.get(contexts.get(p['id'], {}).get('organization_id') or default_org, {})
            p.update(department=org.get('department') or None, team_name=org.get('team') or None,
                     manager_id=p['created_by'], manager=people.get(p['created_by'], {}).get('username'),
                     can_configure=user['role'] == 'admin' or user['id'] in {p['created_by'], p['owner_id']})
        options = {'departments': sorted({p['department'] for p in projects if p['department']}),
                   'teams': sorted({p['team_name'] for p in projects if p['team_name']}),
                   'managers': [{'id': uid, 'name': people.get(uid, {}).get('username') or 'Account unavailable'} for uid in sorted({p['manager_id'] for p in projects})],
                   'projects': [{'id': p['id'], 'title': p['title']} for p in projects]}
        projects = [p for p in projects if (not department or (p['department'] or '__unassigned') == department)
                    and (not team or (p['team_name'] or '__unassigned') == team)
                    and (manager is None or p['manager_id'] == manager)
                    and (not project_id or p['id'] == project_id)
                    and (not from_date or p['due_date'] and p['due_date'] >= from_date)
                    and (not to_date or p['due_date'] and p['due_date'] <= to_date)]
        selected_ids = [p['id'] for p in projects]
        def rows(table, extra='1=1', columns='*'):
            if not selected_ids or table not in tables:
                return []
            return read(db, f'SELECT {columns} FROM {table} WHERE project_id IN (' + ','.join('?' for _ in selected_ids) + ') AND ' + extra, selected_ids)
        tasks = rows('items', "type='task'")
        issues = rows('issues', "status='open'")
        tasks_by, issues_by, phases_by = defaultdict(list), defaultdict(list), defaultdict(list)
        for t in tasks:
            tasks_by[t['project_id']].append(t)
        for i in issues:
            issues_by[i['project_id']].append(i)
        for phase in rows('project_phases'):
            phases_by[phase['project_id']].append(phase)
        global_policy = policy(db)
        local_policies = {r['key'].removeprefix('portfolio:project:'): json.loads(r['value']) for r in db.execute("SELECT key,value FROM config WHERE key LIKE 'portfolio:project:%'")}
        result = []
        from .workhub_workspace import lifecycle
        for p in projects:
            local = local_policies.get(p['id'], {})
            rule = {**global_policy, 'health': {**global_policy['health'], **local.get('health', {})}, 'milestone_weights': local.get('milestone_weights', {})}
            value = calculate(p, tasks_by[p['id']], issues_by[p['id']], rule, today, phases_by[p['id']])
            value['can_configure'] = p['can_configure']
            members = sorted({t[f] for t in [p, *tasks_by[p['id']]] for f in ('owner_id', 'quality_id', 'approver_id', 'release_id')})
            members=sorted(set(members)|set(json.loads(p.get('supporting_ids','[]'))))
            value['assigned_team'] = [{'id': uid, 'name': people.get(uid, {}).get('username') or 'Account unavailable'} for uid in members]
            value['assigned_engineer']=people.get(p['owner_id'],{}).get('username') if p.get('assignment_state')!='unassigned' else None
            value['workflow_name']=procedures.get(p['id'],{}).get('project_type') or p['kind']
            value['workflow_version']=procedures.get(p['id'],{}).get('policy_version',0)
            value['current_responsibility']=people.get(p[NEXT_OWNER[p['stage']]],{}).get('username') if p.get('assignment_state')!='unassigned' else None
            value['project_status']=lifecycle(p)
            value['project_status_id']=value['project_status'].lower().replace(' ','_')
            result.append(value)
        result = [p for p in result if not status or (p['stage'] != 'released' and p.get('exception_status')!='cancelled' if status == 'active' else p['project_status_id']==status if status in {'created','assigned','in_progress','quality_review','closure','on_hold','cancelled'} else p['status'] == status)]
        allowed = {p['id'] for p in result}
        def included(values):
            return [r for r in values if r['project_id'] in allowed]
        tasks = included(tasks)
        all_items = {r['id']: r for r in [*result, *tasks]}
        updates = included(rows('updates', columns='id,project_id,item_id,author_id,minutes,time_status,reviewer_id,work_date,created_at'))
        events = included(rows('events', columns='id,project_id,item_id,actor_id,event,created_at'))
        approvals = []
        def approval(key, pid, title, kind, assignee, at, **extra):
            if pid not in allowed or role == 'engineer' and assignee != user['id']:
                return
            approvals.append({'id': key, 'project_id': pid, 'title': title, 'kind': kind,
                              'assignee_id': assignee, 'assignee': people.get(assignee, {}).get('username'),
                              'created_at': at, 'can_review': assignee == user['id'], **extra})
        for r in all_items.values():
            if r['stage'] in {'quality', 'release_approval', 'ready_release'}:
                uid = r[{'quality': 'quality_id', 'release_approval': 'approver_id', 'ready_release': 'release_id'}[r['stage']]]
                approval('work:' + r['id'], r['project_id'], r['title'], 'workflow', uid, r['updated_at'], item_id=r['id'], stage=r['stage'])
        for u in updates:
            if u['time_status'] == 'submitted':
                approval('time:' + u['id'], u['project_id'], 'Time entry · ' + u['work_date'], 'time', u['reviewer_id'], u['created_at'], item_id=u['item_id'])
        documents = []
        if selected_ids and 'pi_documents' in tables:
            marks = ','.join('?' for _ in selected_ids)
            documents = read(db, 'SELECT d.id,d.project_id,d.title,d.kind,d.approved_revision,r.status,r.reviewer_id,r.reviewed_by,r.created_at FROM pi_documents d JOIN pi_revisions r ON r.id=d.current_revision WHERE d.project_id IN (' + marks + ')', selected_ids)
            controls = {r['document_id']: r for r in read(db, 'SELECT d.document_id,d.stage,r.status,r.reviewer_id,r.approver_id,r.reviewed_by FROM qc_documents d JOIN pi_documents n ON n.id=d.document_id JOIN qc_revisions r ON r.id=n.current_revision WHERE d.project_id IN (' + marks + ')', selected_ids)} if 'qc_documents' in tables else {}
            documents = included(documents)
            for d in documents:
                control = controls.get(d['id'])
                if control:
                    d.update(status=control['status'], stage=control['stage'])
                    if control['status'] == 'in_review':
                        uid = control['approver_id'] if control['reviewed_by'] else control['reviewer_id']
                        approval('document:' + d['id'], d['project_id'], d['title'], 'document', uid, d['created_at'], section='meetings' if control['stage'] == 'frd' else 'documents' if control['stage'] in {'test', 'corrections'} else 'quality', document_stage=control['stage'])
                elif d['status'] == 'review':
                    approval('document:' + d['id'], d['project_id'], d['title'], 'document', d['reviewer_id'], d['created_at'], section='meetings' if d['kind'] in {'mom', 'frd', 'flowchart'} else 'documents', document_stage='')
        approved_plans = {d['project_id']: d['approved_revision'] for d in documents if d['kind'] == 'plan' and d['approved_revision']}
        for p in result:
            p['approved_plan_revision'] = approved_plans.get(p['id'])
            quality=next((d for d in documents if d['project_id']==p['id'] and d.get('stage')=='quality'),None)
            p['quality_status']=quality['status'] if quality else 'Workflow review' if p['stage'] in {'quality','release_approval','ready_release'} else 'Not submitted'
        by_project = {p['id']: p for p in result}
        for a in approvals:
            a['project'] = by_project[a['project_id']]['title']
        approvals.sort(key=lambda r: r['created_at'])
        distribution = Counter(p['status'] for p in result)
        active_ids = {p['id'] for p in result if p['stage'] != 'released' and p.get('exception_status')!='cancelled'}
        parents = {t['parent_id'] for t in tasks if t.get('parent_id')}
        leaves = [t for t in tasks if t['id'] not in parents]
        open_tasks = [t for t in leaves if t['stage'] not in DONE_DEVELOPMENT and t['project_id'] in active_ids]
        if role == 'engineer':
            open_tasks = [t for t in open_tasks if user['id'] in {t['owner_id'], t['quality_id'], t['approver_id'], t['release_id']}]
        overdue = [t for t in open_tasks if t['due_date'] and t['due_date'] < today.isoformat()]
        deadlines = [{'id': t['id'], 'project_id': t['project_id'], 'title': t['title'], 'due_date': t['due_date'], 'kind': 'Milestone' if t['milestone'] else 'Task'} for t in open_tasks if t['due_date'] and t['due_date'] >= today.isoformat()]
        deadlines += [{'id': p['id'], 'project_id': p['id'], 'title': p['title'], 'due_date': p['due_date'], 'kind': 'Project'} for p in result if p['id'] in active_ids and p['due_date'] and p['due_date'] >= today.isoformat()]
        deadlines += [{'id': p['id'], 'item_id': p['project_id'], 'project_id': p['project_id'], 'title': p['title'], 'due_date': p['due_date'], 'kind': 'Delivery phase'} for pid in active_ids for p in phases_by[pid] if p['due_date'] and p['due_date'] >= today.isoformat() and by_project[pid]['phase_progress'].get(p['phase'],0) < 100]
        deadlines.sort(key=lambda r: (r['due_date'], r['title']))
        workload = defaultdict(lambda: {'open_tasks': 0, 'planned_hours': 0, 'approved_hours': 0, 'project_ids': set()})
        for t in open_tasks:
            if role == 'engineer' and t['owner_id'] != user['id']:
                continue
            p = by_project[t['project_id']]
            key = (p['department'], p['team_name'], t['owner_id'])
            w = workload[key]
            w['open_tasks'] += 1
            w['planned_hours'] += t['planned_hours']
            w['project_ids'].add(t['project_id'])
        for u in updates:
            if u['time_status'] != 'approved' or role == 'engineer' and u['author_id'] != user['id']:
                continue
            p = by_project[u['project_id']]
            w = workload[(p['department'], p['team_name'], u['author_id'])]
            w['approved_hours'] += u['minutes'] / 60
            w['project_ids'].add(u['project_id'])
        workload_rows = [{'department': k[0], 'team': k[1], 'engineer_id': k[2], 'engineer': people.get(k[2], {}).get('username'),
                          **w, 'planned_hours': round(w['planned_hours'], 2), 'approved_hours': round(w['approved_hours'], 2),
                          'project_ids': sorted(w['project_ids'])} for k, w in workload.items()]
        workload_rows.sort(key=lambda r: ((r['department'] or ''), (r['team'] or ''), (r['engineer'] or '')))
        activity = sorted([e for e in events if role != 'engineer' or e['actor_id'] == user['id']], key=lambda e: e['created_at'], reverse=True)
        for e in activity[:12]:
            e.update(actor=people.get(e['actor_id'], {}).get('username'), project=by_project[e['project_id']]['title'])
        if {'wh_document_spaces','pi_documents','pi_revisions','qc_documents','qc_revisions'}.issubset(tables):
            standalone=read(db,'''SELECT d.id,d.title,d.project_id,d.kind,d.current_revision,s.title AS scope_title,s.linked_project_id,
                COALESCE(q.stage,d.kind) AS document_stage,COALESCE(cr.status,r.status) AS status,
                COALESCE(cr.reviewer_id,r.reviewer_id) AS reviewer_id,r.created_at
                FROM pi_documents d JOIN wh_document_spaces s ON s.id=d.project_id JOIN pi_revisions r ON r.id=d.current_revision
                LEFT JOIN qc_documents q ON q.document_id=d.id LEFT JOIN qc_revisions cr ON cr.id=r.id
                WHERE (? OR s.owner_id=? OR s.reviewer_id=?) AND COALESCE(cr.status,r.status) IN ('review','in_review')''',(user['role']=='admin',user['id'],user['id']))
            for d in standalone:
                if project_id and d['linked_project_id']!=project_id:continue
                uid=d['reviewer_id']
                approvals.append({'id':'document:'+d['id'],'project_id':d['project_id'],'project':d['scope_title'],'title':d['title'],
                    'kind':'document','assignee_id':uid,'assignee':people.get(uid,{}).get('username'),'can_review':uid==user['id'],
                    'created_at':d['created_at'],'section':'documents','document_stage':'independent:'+('native:'+d['id'] if d['kind']=='mom' else d['document_stage'])})
        recorded_delivery = [p for p in result if p['delivery_variance_days'] is not None]
        summary = {'total': len(result), 'active': len(active_ids), 'completed': distribution['completed'],
                   'delayed': distribution['delayed'], 'at_risk': distribution['at_risk'], 'unassessed': distribution['unassessed'],
                   'overdue_tasks': len(overdue), 'pending_approvals': len(approvals), 'milestones': sum(p['milestone_count'] for p in result),
                   'completed_milestones': sum(p['completed_milestones'] for p in result),
                   'on_time_deliveries': sum(p['delivery_variance_days'] <= 0 for p in recorded_delivery),
                   'recorded_deliveries': len(recorded_delivery), 'engineering_activities': len(activity)}
        summary.update(created=sum(p['project_status']=='Created' for p in result),assigned=sum(p['project_status']=='Assigned' for p in result),
                       in_progress=sum(p['project_status']=='In Progress' for p in result),quality_review=sum(p['project_status']=='Quality Review' for p in result),closure=sum(p['project_status']=='Closure' for p in result),
                       pending_assignments=sum(p.get('assignment_state')=='unassigned' and p.get('exception_status')!='cancelled' for p in result),blocked=distribution['blocked'])
        notices=read(db,'SELECT id,project_id,item_id,title,body,created_at,read_at FROM notifications WHERE recipient_id=? ORDER BY created_at DESC',(user['id'],))
        notices=[n for n in notices if n['project_id'] in allowed]
        reports = {'documents': len(documents), 'approved': sum(d['status'] in {'approved', 'released'} for d in documents),
                   'drafts': sum(d['status'] in {'draft', 'correction_required'} for d in documents),
                   'pending': sum(d['status'] in {'review', 'in_review'} for d in documents)}
        return {'role': role, 'roles': [{'id': r, 'label': ROLE_LABELS[r]} for r in available],
                'scope_note': {'management': 'All company projects', 'project_manager': 'Projects you created or own', 'team_lead': 'Projects with your assigned review or release responsibility', 'engineer': 'Your assigned projects; personal activity and workload'}[role],
                'generated_at': timestamp(), 'as_of': today.isoformat(), 'options': options, 'summary': summary,
                'distribution': dict(distribution), 'projects': result, 'deadlines': deadlines, 'overdue': overdue,
                'approvals': approvals, 'activity': activity[:12], 'workload': workload_rows, 'reports': reports,
                'report_documents': documents, 'notifications':notices[:8], 'unread_notifications':sum(not n['read_at'] for n in notices),
                'health_rules': global_policy['health'], 'can_configure': user['role'] == 'admin'}


def dashboard(user, *, page=1, page_size=15, **filters):
    value = snapshot(user, **filters)
    projects = sorted(value['projects'], key=lambda p: ({'blocked':0,'delayed': 1, 'at_risk': 2, 'on_track': 3, 'unassessed': 4, 'completed': 5}[p['status']], not bool(p['due_date']), p['due_date'], p['title']))
    page = min(page, max(1, (len(projects) + page_size - 1) // page_size))
    value.update(projects=projects[(page - 1) * page_size:page * page_size], page=page, page_size=page_size, total_projects=len(projects),
                 deadlines=value['deadlines'][:10], overdue=value['overdue'][:10], approvals=value['approvals'][:8],
                 workload=value['workload'][:200], workload_total=len(value['workload']),
                 plan_comparisons=[p for p in projects if p['stage'] != 'released' and p['planned_progress'] is not None and p['progress'] is not None][:4],
                 risks=[{'id': p['id'], 'title': p['title'], 'health': p['health'], 'reasons': p['reasons'], 'open_issues': p['open_issues'], 'blocked_tasks': p['blocked_tasks']} for p in projects if p['reasons']][:10],
                 report_documents=value['report_documents'][:10])
    return value


def approval_queue(user, *, page=1, page_size=20, documents_only=False, **filters):
    value = snapshot(user, **filters)
    rows = [a for a in value['approvals'] if not documents_only or a['kind'] == 'document']
    return {'items': rows[(page - 1) * page_size:page * page_size], 'total': len(rows), 'page': page, 'page_size': page_size, 'role': value['role']}


def get_rules(user, project_id=''):
    hub.actor(user)
    initialize()
    with hub.db() as db:
        if project_id:
            project = hub.item(db, project_id)
            if project['type'] != 'project':
                raise HTTPException(400, 'Choose a project.')
            hub.manage(project, user, db)
        elif user['role'] != 'admin':
            raise HTTPException(403, 'Only Admin can configure company dashboard rules.')
        return {**policy(db, project_id), 'project_id': project_id,
                'milestones': read(db, "SELECT id,title,planned_hours FROM items WHERE project_id=? AND milestone=1 ORDER BY due_date,title", (project_id,)) if project_id else []}


def save_rules(user, payload):
    pid = payload.get('project_id') or ''
    get_rules(user, pid)
    health = payload.get('health', {})
    if not isinstance(health, dict) or set(health) - set(DEFAULT_HEALTH):
        raise HTTPException(400, 'Use the supported project health rules.')
    clean = {}
    for k, val in health.items():
        if k == 'open_issues_at_risk':
            if type(val) is not bool:
                raise HTTPException(400, 'Choose whether open issues affect health.')
        elif type(val) not in (int, float) or not math.isfinite(val) or not 0 <= val <= (365 if k == 'due_soon_days' else 100) or k == 'due_soon_days' and int(val) != val:
            raise HTTPException(400, 'Enter valid health thresholds.')
        clean[k] = val
    weights = payload.get('milestone_weights', {})
    if not isinstance(weights, dict) or len(weights) > 1000:
        raise HTTPException(400, 'Provide a bounded mapping of milestone weights.')
    with hub.db(True) as db:
        old = policy(db, pid)
        if payload.get('version') != old['version']:
            raise HTTPException(409, 'These dashboard rules changed. Reload before saving.')
        if pid:
            hub.manage(hub.item(db, pid), user, db)
        elif user['role'] != 'admin':
            raise HTTPException(403, 'Only Admin can change company dashboard rules.')
        valid = {r[0] for r in db.execute('SELECT id FROM items WHERE project_id=? AND milestone=1', (pid,))}
        if set(weights) - valid or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= 100000 for v in weights.values()):
            raise HTTPException(400, 'Use positive weights for existing project milestones only.')
        value = {'version': old['version'] + 1, 'health': clean, 'milestone_weights': weights,
                 'updated_by': user['id'], 'updated_at': timestamp()}
        key = 'portfolio:project:' + pid if pid else 'portfolio:rules'
        db.execute('INSERT INTO config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, encode(value)))
        if pid:
            hub.event(db, hub.item(db, pid), user, 'dashboard_rules_updated', value)
    return get_rules(user, pid)
