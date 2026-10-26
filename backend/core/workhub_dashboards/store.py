"""Dashboard ownership and explicit per-account sharing in the existing WorkHub DB."""
import json
import threading
from fastapi import HTTPException
from backend.core.workhub import store as hub, identity, timestamp
from backend.core.workhub_growth.store import personal
from . import schema

LOCK=threading.RLock();READY=set()
def initialize():
    key=str(hub.root.resolve())
    if key in READY:return
    with LOCK:
        if key in READY:return
        with hub.db(True) as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS wh_dashboards(id TEXT PRIMARY KEY,owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,configuration TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS wh_dashboard_owner ON wh_dashboards(owner_id,updated_at);
              CREATE TABLE IF NOT EXISTS wh_dashboard_access(dashboard_id TEXT NOT NULL,user_id INTEGER NOT NULL,
                permission TEXT NOT NULL CHECK(permission IN ('viewer','editor')),PRIMARY KEY(dashboard_id,user_id));
              CREATE INDEX IF NOT EXISTS wh_dashboard_recipient ON wh_dashboard_access(user_id,dashboard_id);
              CREATE TABLE IF NOT EXISTS wh_dashboard_changes(id TEXT PRIMARY KEY,dashboard_id TEXT NOT NULL,
                actor_id INTEGER NOT NULL,action TEXT NOT NULL,version INTEGER NOT NULL,created_at TEXT NOT NULL);
            ''')
        READY.add(key)

def row(db,user,key,write=False,owner=False):
    personal(user)
    record=db.execute('SELECT * FROM wh_dashboards WHERE id=?',(key,)).fetchone()
    if not record:raise HTTPException(404,'Dashboard not found.')
    value=dict(record)
    access=db.execute('SELECT permission FROM wh_dashboard_access WHERE dashboard_id=? AND user_id=?',(key,user['id'])).fetchone()
    permission='owner' if value['owner_id']==user['id'] else access[0] if access else None
    # Admin status does not implicitly expose a personal dashboard or allow a takeover.
    if not permission or owner and permission!='owner' or write and permission not in {'owner','editor'}:
        raise HTTPException(403,'You do not have permission for this dashboard action.')
    value['permission']=permission
    return value

def public(db,value,full=True):
    result={key:value[key] for key in ('id','owner_id','name','version','created_at','updated_at','permission')}
    if full:
        result['configuration']=json.loads(value['configuration'])
        result['sharing']=[dict(r) for r in db.execute('SELECT user_id,permission FROM wh_dashboard_access WHERE dashboard_id=? ORDER BY user_id',(value['id'],))] if value['permission']=='owner' else []
    return result

def change(db,user,key,action,version):
    db.execute('INSERT INTO wh_dashboard_changes VALUES(?,?,?,?,?,?)',(identity(),key,user['id'],action,version,timestamp()))

def listing(user):
    personal(user);initialize()
    with hub.db() as db:
        values=db.execute('SELECT d.* FROM wh_dashboards d WHERE d.owner_id=? OR EXISTS(SELECT 1 FROM wh_dashboard_access a WHERE a.dashboard_id=d.id AND a.user_id=?) ORDER BY d.updated_at DESC',(user['id'],user['id'])).fetchall()
        return {'items':[public(db,row(db,user,r['id']),False) for r in values],
                'users':[u for u in hub.users() if u['active']]}

def get(user,key):
    initialize()
    with hub.db() as db:return public(db,row(db,user,key))

def save(user,payload,key=None):
    personal(user);initialize();schema.bounded(payload)
    config=schema.dashboard(payload.get('configuration',{}));now=timestamp()
    with hub.db(True) as db:
        if key:
            before=row(db,user,key,write=True)
            if payload.get('version')!=before['version']:raise HTTPException(409,'This dashboard changed. Reload it before saving, or duplicate your unsaved design.')
            db.execute('UPDATE wh_dashboards SET name=?,configuration=?,version=version+1,updated_at=? WHERE id=?',(config['name'],schema.bounded(config),now,key))
            version=before['version']+1
        else:
            count=db.execute('SELECT COUNT(*) FROM wh_dashboards WHERE owner_id=?',(user['id'],)).fetchone()[0]
            if count>=100:raise HTTPException(409,'You can own up to 100 dashboards. Delete an unused dashboard first.')
            key=identity();version=1
            db.execute('INSERT INTO wh_dashboards VALUES(?,?,?,?,?,?,?)',(key,user['id'],config['name'],schema.bounded(config),1,now,now))
        change(db,user,key,'saved',version)
        return public(db,row(db,user,key))

def duplicate(user,key,payload):
    original=get(user,key)['configuration'];original['name']=payload.get('name',original['name']+' copy')
    return save(user,{'configuration':original})


def from_template(user,key,payload):
    """Atomic first-use creation leaves all existing dashboards and sharing intact."""
    from . import templates
    personal(user);initialize();schema.bounded(payload)
    if key!=templates.KEY:raise HTTPException(404,'Dashboard template not found.')
    if type(payload.get('if_empty',False)) is not bool:schema.fail('Use true or false for first-use creation.')
    config=templates.configuration();now=timestamp()
    with hub.db(True) as db:
        if payload.get('if_empty'):
            existing=db.execute('SELECT d.id FROM wh_dashboards d WHERE d.owner_id=? OR EXISTS(SELECT 1 FROM wh_dashboard_access a WHERE a.dashboard_id=d.id AND a.user_id=?) ORDER BY d.updated_at DESC LIMIT 1',(user['id'],user['id'])).fetchone()
            if existing:return public(db,row(db,user,existing['id']))
        if db.execute('SELECT COUNT(*) FROM wh_dashboards WHERE owner_id=?',(user['id'],)).fetchone()[0]>=100:raise HTTPException(409,'You can own up to 100 dashboards.')
        key=identity()
        db.execute('INSERT INTO wh_dashboards VALUES(?,?,?,?,?,?,?)',(key,user['id'],config['name'],schema.bounded(config),1,now,now))
        change(db,user,key,'created_from_engineering_template',1)
        return public(db,row(db,user,key))

def share(user,key,payload):
    initialize();schema.bounded(payload);entries=schema.array(payload.get('sharing',[]),100)
    with hub.db(True) as db:
        before=row(db,user,key,owner=True)
        if payload.get('version')!=before['version']:raise HTTPException(409,'Sharing changed. Reload this dashboard.')
        allowed={u['id'] for u in hub.users() if u['active']};seen=set();values=[]
        for entry in entries:
            entry=schema.obj(entry);uid=entry.get('user_id')
            if type(uid) is not int or uid not in allowed or uid==before['owner_id'] or uid in seen:schema.fail('Choose distinct enabled accounts other than the owner.')
            seen.add(uid);values.append((key,uid,schema.choice(entry.get('permission'),['viewer','editor'])))
        db.execute('DELETE FROM wh_dashboard_access WHERE dashboard_id=?',(key,))
        db.executemany('INSERT INTO wh_dashboard_access VALUES(?,?,?)',values)
        db.execute('UPDATE wh_dashboards SET version=version+1,updated_at=? WHERE id=?',(timestamp(),key))
        change(db,user,key,'sharing_changed',before['version']+1)
        return public(db,row(db,user,key))

def delete(user,key,version):
    initialize()
    with hub.db(True) as db:
        before=row(db,user,key,owner=True)
        if version!=before['version']:raise HTTPException(409,'Dashboard changed. Reload before deleting.')
        change(db,user,key,'deleted',version)
        db.execute('DELETE FROM wh_dashboard_access WHERE dashboard_id=?',(key,));db.execute('DELETE FROM wh_dashboards WHERE id=?',(key,))
    return {'deleted':True}
