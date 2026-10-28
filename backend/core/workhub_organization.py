"""WorkHub departments, roles, teams and capacity, linked to existing accounts."""
import json
import math
import re
import threading
from fastapi import HTTPException
from backend.core import accounts
from backend.core.workhub import store as hub,identity,timestamp,text,encode,day

LOCK=threading.RLock();READY=set()


def initialize():
    key=str(hub.root.resolve())
    if key in READY:return
    with LOCK:
        if key in READY:return
        with hub.db(True) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS wh_org_units(
              id TEXT PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,department_id TEXT NOT NULL DEFAULT '',
              active INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS wh_org_unit_name ON wh_org_units(kind,department_id,name COLLATE NOCASE);
            CREATE TABLE IF NOT EXISTS wh_org_members(
              team_id TEXT NOT NULL,user_id INTEGER NOT NULL,team_role TEXT NOT NULL DEFAULT 'member',
              PRIMARY KEY(team_id,user_id));
            CREATE TABLE IF NOT EXISTS wh_org_profiles(
              user_id INTEGER PRIMARY KEY,department_id TEXT NOT NULL DEFAULT '',role_id TEXT NOT NULL DEFAULT '',
              manager_id INTEGER,weekly_hours REAL NOT NULL DEFAULT 40,
              availability TEXT NOT NULL DEFAULT 'available',unavailable_until TEXT NOT NULL DEFAULT '',
              availability_note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS wh_org_audit(
              id TEXT PRIMARY KEY,actor_id INTEGER NOT NULL,object_type TEXT NOT NULL,object_id TEXT NOT NULL,
              before_data TEXT NOT NULL,after_data TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS wh_org_schedule(
              user_id INTEGER PRIMARY KEY,daily_hours REAL NOT NULL,workdays INTEGER NOT NULL);
            ''')
        READY.add(key)


def personal(user):
    hub.actor(user)
    if not user.get('active',True) or not user.get('approved',True):raise HTTPException(403,'Use an enabled personal account.')


def admin(user):
    personal(user)
    if user.get('role')!='admin':raise HTTPException(403,'Only Admin can manage departments, roles, teams and user capacity.')


def people():
    return [u for u in accounts.store.list_users() if u.get('approved') and not u.get('isDemo')]


def person(user_id,enabled=True):
    if type(user_id)is not int:raise HTTPException(400,'Choose an existing user.')
    value=next((u for u in people() if u['id']==user_id),None)
    if not value or enabled and not value['active']:raise HTTPException(400,'Choose an enabled personal account.')
    return value


def unit(db,key,kind,allow_empty=True,include_archived=False):
    if not key and allow_empty:return None
    if not isinstance(key,str):raise HTTPException(400,'Choose a valid '+kind+'.')
    row=db.execute('SELECT * FROM wh_org_units WHERE id=? AND kind=?'+('' if include_archived else ' AND active=1'),(key,kind)).fetchone()
    if not row:raise HTTPException(400,'Choose an active '+kind+'.')
    return dict(row)


def version(previous,payload):
    if payload.get('version')!=(previous['version'] if previous else 0):raise HTTPException(409,'This team or profile changed. Refresh before saving.')


def audit(db,user,kind,key,before,after):
    db.execute('INSERT INTO wh_org_audit VALUES(?,?,?,?,?,?,?)',(identity(),user['id'],kind,str(key),encode(before or {}),encode(after),timestamp()))


def managed_people(db,user):
    if user['role']=='admin':return {u['id'] for u in people()}
    ids={user['id']}
    ids.update(r[0] for r in db.execute('SELECT user_id FROM wh_org_profiles WHERE manager_id=?',(user['id'],)))
    ids.update(r[0] for r in db.execute("SELECT DISTINCT member.user_id FROM wh_org_members manager JOIN wh_org_members member ON member.team_id=manager.team_id JOIN wh_org_units t ON t.id=manager.team_id AND t.active=1 WHERE manager.user_id=? AND manager.team_role='manager'",(user['id'],)))
    return ids


def can_review(db,user,subject):
    return user['id']!=subject and (user['role']=='admin' or subject in managed_people(db,user))


def profile(db,user_id):
    row=db.execute('SELECT * FROM wh_org_profiles WHERE user_id=?',(user_id,)).fetchone()
    value=dict(row) if row else {'user_id':user_id,'department_id':'','role_id':'','manager_id':None,'weekly_hours':40,
                               'availability':'available','unavailable_until':'','availability_note':'','version':0,'updated_at':None}
    value['team_ids']=[r[0] for r in db.execute('SELECT team_id FROM wh_org_members WHERE user_id=? ORDER BY team_id',(user_id,))]
    value['managed_team_ids']=[r[0] for r in db.execute("SELECT team_id FROM wh_org_members WHERE user_id=? AND team_role='manager'",(user_id,))]
    schedule=db.execute('SELECT daily_hours,workdays FROM wh_org_schedule WHERE user_id=?',(user_id,)).fetchone()
    value['daily_hours']=schedule['daily_hours'] if schedule else value['weekly_hours']/5
    value['workdays']=schedule['workdays'] if schedule else 5
    return value


def assignments(db,user_id):
    """Current responsibilities, independent of estimates or personal status flags."""
    roles={'todo':'owner_id','development':'owner_id','blocked':'owner_id','development_completed':'owner_id',
           'quality':'quality_id','release_approval':'approver_id','ready_release':'release_id'}
    result=[]
    for row in db.execute("SELECT * FROM items WHERE stage!='released'"):
        r=dict(row)
        if r.get('assignment_state')=='unassigned':continue
        if r['type']=='task':
            parent=db.execute("SELECT stage FROM items WHERE id=?",(r['project_id'],)).fetchone()
            if not parent or parent[0]=='released':continue
        responsible=r.get(roles.get(r['stage'],'owner_id'))==user_id
        supporting=user_id in json.loads(r.get('supporting_ids') or '[]')
        if responsible or supporting:result.append({'id':r['id'],'project_id':r['project_id'],'title':r['title'],'type':r['type'],'stage':r['stage']})
    return {'status':'Assigned' if result else 'Available','projects':len({r['project_id'] for r in result}),'items':result}


def directory(user):
    initialize();personal(user)
    with hub.db() as db:
        managed=managed_people(db,user)
        units=[dict(r) for r in db.execute('SELECT * FROM wh_org_units ORDER BY kind,name')]
        members=[dict(r) for r in db.execute('SELECT * FROM wh_org_members ORDER BY team_id,user_id')]
        values=[]
        for u in people():
            p=profile(db,u['id'])
            if u['id'] not in managed:p['availability_note']=''
            values.append({k:u[k] for k in ('id','username','designation','role','active')}|{'profile':p,
                          'email':u.get('email','') if user['role']=='admin' or user['id']==u['id'] else '',
                          'assignment':assignments(db,u['id']),'can_edit_profile':user['role']=='admin' or user['id']==u['id']})
        return {'units':units,'memberships':members,'users':values,'user_id':user['id'],
                'can_administer':user['role']=='admin','managed_user_ids':sorted(managed),
                'capacity_note':'Daily hours and workdays determine weekly capacity. Existing weekly capacities are retained until edited. Assigned means an active project or task responsibility; it does not imply all working hours are booked.'}


def save_unit(user,payload,key=None):
    initialize();admin(user)
    kind=payload.get('kind')
    if not isinstance(kind,str) or kind not in {'department','role','team'}:raise HTTPException(400,'Choose department, role or team.')
    name=text(payload.get('name',''),120,True)
    if type(payload.get('active',True))is not bool:raise HTTPException(400,'Choose an active status.')
    with hub.db(True) as db:
        row=db.execute('SELECT * FROM wh_org_units WHERE id=?',(key,)).fetchone() if key else None
        previous=dict(row) if row else None
        if key and not previous:raise HTTPException(404,'Organization record not found.')
        version(previous,payload)
        if previous and previous['kind']!=kind:raise HTTPException(400,'Keep the organization record type.')
        department=payload.get('department_id') or ''
        if kind!='department':unit(db,department,'department',include_archived=bool(previous and department==previous['department_id']))
        else:department=''
        duplicate=db.execute('SELECT id FROM wh_org_units WHERE kind=? AND department_id=? AND name=? COLLATE NOCASE AND id!=?',(kind,department,name,key or '')).fetchone()
        if duplicate:raise HTTPException(409,'That name already exists in this department.')
        record={'id':key or identity(),'kind':kind,'name':name,'department_id':department,'active':int(payload.get('active',True)),
                'version':(previous['version'] if previous else 0)+1,'updated_at':timestamp()}
        if kind=='team':
            selected=payload.get('member_ids',[]);managers=payload.get('manager_ids',[])
            if not isinstance(selected,list) or not isinstance(managers,list) or len(selected)>1000 or len(managers)>100:raise HTTPException(400,'Choose valid team members and team administrators.')
            if any(type(x)is not int for x in [*selected,*managers]):raise HTTPException(400,'Choose existing team members by name.')
            selected=set(selected);managers=set(managers)
            if not managers<=selected:raise HTTPException(400,'Every team administrator must also be a team member.')
            old_members={r[0] for r in db.execute('SELECT user_id FROM wh_org_members WHERE team_id=?',(key,))} if previous else set()
            for user_id in selected:person(user_id,user_id not in old_members)
            if previous:
                previous['member_ids']=[r[0] for r in db.execute('SELECT user_id FROM wh_org_members WHERE team_id=?',(key,))]
                previous['manager_ids']=[r[0] for r in db.execute("SELECT user_id FROM wh_org_members WHERE team_id=? AND team_role='manager'",(key,))]
        db.execute('INSERT OR REPLACE INTO wh_org_units VALUES(:id,:kind,:name,:department_id,:active,:version,:updated_at)',record)
        if kind=='team':
            record['member_ids']=sorted(selected);record['manager_ids']=sorted(managers)
            db.execute('DELETE FROM wh_org_members WHERE team_id=?',(record['id'],))
            db.executemany('INSERT INTO wh_org_members VALUES(?,?,?)',[(record['id'],uid,'manager' if uid in managers else 'member') for uid in selected])
            # A stale user-profile form must not undo a concurrent team edit.
            for uid in old_members^selected:
                p=profile(db,uid)
                db.execute('INSERT OR IGNORE INTO wh_org_profiles(user_id,version,updated_at) VALUES(?,0,?)',(uid,timestamp()))
                db.execute('UPDATE wh_org_profiles SET version=version+1,updated_at=? WHERE user_id=?',(timestamp(),uid))
        audit(db,user,kind,record['id'],previous,record)
    return record


def save_profile(user,user_id,payload):
    initialize();personal(user);person(user_id,False)
    if user['role']!='admin' and user['id']!=user_id:raise HTTPException(403,'Edit your own profile or ask Admin to update another account.')
    with hub.db(True) as db:
        previous=profile(db,user_id);version(previous,payload)
        # Reporting relationships and team administration grant confidential
        # assessment access. They remain under Admin control on every API path.
        if user['role']!='admin':
            if payload.get('manager_id',previous['manager_id'])!=previous['manager_id']:raise HTTPException(403,'Only Admin can change reporting relationships.')
            if payload.get('managed_team_ids',previous['managed_team_ids'])!=previous['managed_team_ids']:raise HTTPException(403,'Only Admin can grant team administration.')
        department=payload.get('department_id') or '';role=payload.get('role_id') or ''
        unit(db,department,'department',include_archived=department==previous['department_id']);r=unit(db,role,'role',include_archived=role==previous['role_id'])
        if r and r['department_id'] and r['department_id']!=department:raise HTTPException(400,'Choose a role in the selected department.')
        manager=payload.get('manager_id') or None
        if manager:
            person(manager)
            if manager==user_id:raise HTTPException(400,'Choose another person as reporting manager.')
            seen={user_id};current=manager
            while current:
                if current in seen:raise HTTPException(400,'The reporting relationship would create a cycle.')
                seen.add(current);current=profile(db,current)['manager_id']
        hours=payload.get('weekly_hours',previous['weekly_hours'])
        if isinstance(hours,bool) or not isinstance(hours,(int,float)) or not math.isfinite(hours) or not 0<=hours<=168:raise HTTPException(400,'Weekly capacity must be between 0 and 168 hours.')
        daily=payload.get('daily_hours');workdays=payload.get('workdays',previous['workdays'])
        use_daily=daily is not None and (hours==previous['weekly_hours'] or daily!=previous['daily_hours'] or workdays!=previous['workdays'])
        if use_daily:
            if isinstance(daily,bool) or not isinstance(daily,(int,float)) or not math.isfinite(daily) or not 0<=daily<=24:raise HTTPException(400,'Daily work hours must be between 0 and 24.')
            if type(workdays)is not int or not 1<=workdays<=7:raise HTTPException(400,'Workdays per week must be between 1 and 7.')
            hours=daily*workdays
        availability=payload.get('availability','available')
        if not isinstance(availability,str) or availability not in {'available','blocked','leave'}:raise HTTPException(400,'Choose available, blocked or leave.')
        teams=payload.get('team_ids',[])
        if not isinstance(teams,list) or len(teams)>30:raise HTTPException(400,'Choose valid teams.')
        if any(not isinstance(x,str) or not re.fullmatch(r'[0-9a-f]{32}',x) for x in teams):raise HTTPException(400,'Choose existing teams.')
        teams=set(teams)
        for team in teams:unit(db,team,'team',False,include_archived=team in previous['team_ids'])
        value={'user_id':user_id,'department_id':department,'role_id':role,'manager_id':manager,'weekly_hours':hours,
               'availability':availability,'unavailable_until':day(payload.get('unavailable_until','')),
               'availability_note':text(payload.get('availability_note',''),1000),'version':previous['version']+1,'updated_at':timestamp()}
        db.execute('INSERT OR REPLACE INTO wh_org_profiles VALUES(:user_id,:department_id,:role_id,:manager_id,:weekly_hours,:availability,:unavailable_until,:availability_note,:version,:updated_at)',value)
        if use_daily:db.execute('INSERT OR REPLACE INTO wh_org_schedule VALUES(?,?,?)',(user_id,daily,workdays))
        elif hours!=previous['weekly_hours']:db.execute('DELETE FROM wh_org_schedule WHERE user_id=?',(user_id,))
        if user['role']!='admin' and not set(previous['managed_team_ids'])<=teams:raise HTTPException(403,'Ask Admin to change your team administrator membership.')
        for row in db.execute('SELECT team_id FROM wh_org_members WHERE user_id=?',(user_id,)).fetchall():
            if row[0] not in teams:db.execute('DELETE FROM wh_org_members WHERE user_id=? AND team_id=?',(user_id,row[0]))
        db.executemany("INSERT OR IGNORE INTO wh_org_members VALUES(?,?,'member')",[(team,user_id) for team in teams])
        for team in set(previous['team_ids'])^teams:db.execute('UPDATE wh_org_units SET version=version+1,updated_at=? WHERE id=?',(timestamp(),team))
        audit(db,user,'profile',user_id,previous,{**value,'team_ids':sorted(teams)})
        return profile(db,user_id)
