"""Resource planning from native WorkHub responsibilities and planned effort."""
from collections import defaultdict
import json
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from backend.core.workhub import store as hub,day
from backend.core import workhub_organization as org

CURRENT={'todo':'owner_id','development':'owner_id','blocked':'owner_id','development_completed':'owner_id',
         'quality':'quality_id','release_approval':'approver_id','ready_release':'release_id','released':'owner_id'}


def days(start,end):
    return [start+timedelta(days=i) for i in range((end-start).days+1) if (start+timedelta(days=i)).weekday()<5]


def snapshot(user,from_date='',to_date='',project_id='',team_id='',department_id='',status=''):
    org.initialize();org.personal(user)
    start=date.fromisoformat(day(from_date)) if from_date else datetime.now(ZoneInfo('Asia/Kolkata')).date()
    end=date.fromisoformat(day(to_date)) if to_date else start+timedelta(days=13)
    if end<start or (end-start).days>366:raise HTTPException(400,'Choose a planning period up to one year.')
    workdays=days(start,end)
    directory=org.directory(user);people={u['id']:u for u in directory['users'] if u['active']}
    units={u['id']:u for u in directory['units']}
    with hub.db() as db:
        projects={r['id']:dict(r) for r in db.execute("SELECT * FROM items WHERE type='project'")}
        if project_id and project_id not in projects:raise HTTPException(404,'Project not found.')
        raw=[dict(r) for r in db.execute("SELECT * FROM items WHERE type='task' AND stage!='released' ORDER BY due_date,title LIMIT 10001")]
        stages={r['id']:r['stage'] for r in db.execute("SELECT id,stage FROM items WHERE type='task'")}
        if len(raw)>10000:raise HTTPException(422,'Narrow the planning period: too many active tasks.')
        parents={r[0] for r in db.execute('SELECT DISTINCT parent_id FROM items WHERE parent_id IS NOT NULL')}
        approved={r['item_id']:r['minutes'] for r in db.execute("SELECT item_id,SUM(minutes) AS minutes FROM updates WHERE time_status='approved' GROUP BY item_id")}
        tasks=[];allocations=defaultdict(list)
        for task in raw:
            project=projects.get(task['project_id'])
            if not project or project['stage']=='released' or task['id'] in parents:continue
            a=date.fromisoformat(task['start_date']) if task.get('start_date') else None
            b=date.fromisoformat(task['due_date']) if task.get('due_date') else None
            if a and a>end:continue
            role=CURRENT.get(task['stage'],'owner_id');responsible=task.get(role)
            unassigned=task.get('assignment_state')=='unassigned'
            planned=task.get('planned_hours') or None
            # Development estimates do not become review estimates when the
            # responsibility changes to an independent reviewer.
            if role!='owner_id' and responsible!=task['owner_id']:planned=None
            remaining=max(0,float(planned)-approved.get(task['id'],0)/60) if planned is not None else None
            scheduled=remaining
            if a and b and remaining is not None:
                total=days(a,b);overlap=[d for d in total if start<=d<=end]
                scheduled=remaining*len(overlap)/len(total) if total else remaining if start<=a<=end else 0
            overdue=bool(b and b<start)
            if not a or not b or overdue:scheduled=None
            dependencies=json.loads(task.get('dependencies') or '[]')
            blocked_dependencies=[key for key in dependencies if stages.get(key) not in {'development_completed','quality','release_approval','ready_release','released'}]
            state='Blocked' if task['stage']=='blocked' or project.get('exception_status')=='on_hold' or blocked_dependencies else 'In progress' if task['stage']=='development' else 'Assigned'
            row={'id':task['id'],'type':'task','project_id':project['id'],'project':project['title'],'title':task['title'],
                 'responsible_id':None if unassigned else responsible,'responsibility':role,'stage':task['stage'],'status':state,
                 'start_date':task['start_date'],'due_date':task['due_date'],'planned_hours':planned,'remaining_hours':remaining,
                 'period_hours':round(scheduled,2) if scheduled is not None else None,'version':task['version'],'overdue':overdue,'blocked_dependencies':blocked_dependencies,
                 'can_assign':user['role']=='admin' or user['id'] in {task['created_by'],task['owner_id'],project['created_by'],project['owner_id']}}
            tasks.append(row)
            if not unassigned:allocations[responsible].append(row)
            for uid in json.loads(task.get('supporting_ids') or '[]'):
                if uid==responsible or unassigned:continue
                supporting={**row,'responsible_id':uid,'responsibility':'supporting_ids','planned_hours':None,'remaining_hours':None,'period_hours':None,'can_assign':False}
                tasks.append(supporting);allocations[uid].append(supporting)
        # A project-level responsibility without a corresponding task plan is
        # still an assignment. Do not invent spare capacity for its owner.
        for project in projects.values():
            if project['stage']=='released':continue
            role=CURRENT.get(project['stage'],'owner_id');uid=project[role]
            if any(t['project_id']==project['id'] for t in allocations[uid]):continue
            if project.get('start_date') and project['start_date']>end.isoformat():continue
            unassigned=project.get('assignment_state')=='unassigned'
            row={'id':project['id'],'type':'project','project_id':project['id'],'project':project['title'],'title':'Project responsibility',
                 'responsible_id':None if unassigned else uid,'responsibility':role,'stage':project['stage'],
                 'status':'Blocked' if project['stage']=='blocked' or project.get('exception_status')=='on_hold' else 'Assigned',
                 'start_date':project['start_date'],'due_date':project['due_date'],'planned_hours':None,'remaining_hours':None,'period_hours':None,
                 'overdue':bool(project['due_date'] and project['due_date']<start.isoformat()),'blocked_dependencies':[],'version':project['version'],
                 'can_assign':user['role']=='admin' or user['id'] in {project['created_by'],project['owner_id']}}
            tasks.append(row)
            if not unassigned:allocations[uid].append(row)
        rows=[]
        for uid,person in people.items():
            profile=person['profile']
            if team_id and team_id not in profile['team_ids'] or department_id and profile['department_id']!=department_id:continue
            all_tasks=allocations[uid]
            matching=[t for t in all_tasks if not project_id or t['project_id']==project_id]
            # Capacity includes other projects to avoid reporting a resource as
            # free merely because the selected project has no assignment yet.
            unavailable=profile['availability']!='available' and (not profile['unavailable_until'] or profile['unavailable_until']>=start.isoformat())
            blocked_days=len([d for d in workdays if not profile['unavailable_until'] or d.isoformat()<=profile['unavailable_until']]) if unavailable else 0
            capacity=profile['weekly_hours']/5*(len(workdays)-blocked_days)
            assigned=sum(t['period_hours'] or 0 for t in all_tasks)
            unknown=sum(t['period_hours'] is None for t in all_tasks)
            blocked=sum(t['status']=='Blocked' for t in all_tasks)
            free=max(0,capacity-assigned) if not unknown else None
            state='Unavailable' if capacity==0 else 'Overallocated' if assigned>capacity else 'Needs planning' if unknown else 'Blocked work' if blocked else 'Available' if free and free>0 else 'Fully allocated'
            assignment=org.assignments(db,uid)
            if status and status not in {state,assignment['status']}:continue
            rows.append({'id':uid,'username':person['username'],'designation':person['designation'],
                         'department':units.get(profile['department_id'],{}).get('name','Not assigned'),
                         'role':units.get(profile['role_id'],{}).get('name',person['designation']),
                         'teams':[units[t]['name'] for t in profile['team_ids'] if t in units],
                         'capacity_hours':round(capacity,2),'allocated_hours':round(assigned,2),'available_hours':round(free,2) if free is not None else None,
                         'utilization':round(100*assigned/capacity,1) if capacity else None,'unplanned_tasks':unknown,'blocked_tasks':blocked,
                         'status':state,'assignment_status':assignment['status'],'assigned_projects':assignment['projects'],
                         'assigned_project_details':[{'id':pid,'title':projects[pid]['title']} for pid in dict.fromkeys(t['project_id'] for t in assignment['items']) if pid in projects],
                         'daily_hours':profile['daily_hours'],'workdays':profile['workdays'],
                         'availability':profile['availability'],'unavailable_until':profile['unavailable_until'],
                         'availability_note':profile['availability_note'],'tasks':matching,'all_open_tasks':len(all_tasks),
                         'selected_project_tasks':len(matching)})
        rows.sort(key=lambda r:(r['status']!='Available',r['username'].casefold()))
        selected_tasks=[t for t in tasks if not project_id or t['project_id']==project_id]
        return {'from':start.isoformat(),'to':end.isoformat(),'resources':rows,'tasks':selected_tasks,
                'projects':[{'id':p['id'],'title':p['title']} for p in projects.values()],
                'summary':{'people':len(rows),'available':sum(r['assignment_status']=='Available' for r in rows),'assigned':sum(r['assignment_status']=='Assigned' for r in rows),'blocked':sum(r['blocked_tasks']>0 or r['status']=='Unavailable' for r in rows),
                           'overallocated':sum(r['status']=='Overallocated' for r in rows),'unplanned':sum(r['unplanned_tasks'] for r in rows),
                           'unassigned_tasks':sum(t['responsible_id'] is None for t in selected_tasks)},
                'organization':directory,'methodology':'Capacity uses weekday hours and recorded team availability. Planned remaining effort is apportioned across scheduled weekdays. Missing estimates or dates remain unknown. Other-project assignments count toward capacity.'}
