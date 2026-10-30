"""Versioned drawing comments and account-bound, conflict-checked undo/redo."""
import json
import time

from fastapi import HTTPException

FIELDS=('page','kind','shape','box','body','status','reverseX','reverseY')


def public(row):
    value=dict(row)
    if isinstance(value['box'],str):value['box']=json.loads(value['box'])
    value['reverseX']=bool(value.pop('reverse_x',value.get('reverseX',False)))
    value['reverseY']=bool(value.pop('reverse_y',value.get('reverseY',False)))
    value['deleted']=bool(value.get('deleted',False))
    return value


def migrate(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='marks'").fetchone():return
    if 'deleted' not in {c[1] for c in db.execute('PRAGMA table_info(marks)')}:
        db.execute('ALTER TABLE marks ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')
    db.execute('''CREATE TABLE IF NOT EXISTS revisions(mark_id TEXT NOT NULL,version INTEGER NOT NULL,
        snapshot TEXT NOT NULL,action TEXT NOT NULL,actor_id INTEGER,actor TEXT NOT NULL,at REAL NOT NULL,
        origin TEXT NOT NULL DEFAULT '',PRIMARY KEY(mark_id,version))''')
    db.execute('''CREATE TABLE IF NOT EXISTS commands(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id INTEGER NOT NULL,
        label TEXT NOT NULL,before_state TEXT NOT NULL,after_state TEXT NOT NULL,state TEXT NOT NULL,at REAL NOT NULL)''')
    db.execute('CREATE TABLE IF NOT EXISTS portable_bases(mark_id TEXT PRIMARY KEY,version INTEGER NOT NULL,snapshot TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS foreign_history(mark_id TEXT NOT NULL,fingerprint TEXT NOT NULL,entry TEXT NOT NULL,PRIMARY KEY(mark_id,fingerprint))')
    # Retain available pre-upgrade snapshots without inventing the missing editor identity.
    for row in db.execute('SELECT * FROM marks WHERE id NOT IN (SELECT DISTINCT mark_id FROM revisions)').fetchall():
        mark=public(row)
        for event in db.execute('SELECT * FROM events WHERE mark_id=? ORDER BY id',(mark['id'],)).fetchall():
            try:
                snapshot=json.loads(event['snapshot'])
                if snapshot.get('version',0)>0 and 'author' in snapshot:
                    db.execute('INSERT OR IGNORE INTO revisions VALUES (?,?,?,?,?,?,?,?)',
                               (mark['id'],snapshot['version'],json.dumps(snapshot),'legacy snapshot',None,'Editor unavailable',snapshot.get('updated',event['at']),'pre-upgrade'))
            except (ValueError,TypeError):pass
        db.execute('INSERT OR IGNORE INTO revisions VALUES (?,?,?,?,?,?,?,?)',
                   (mark['id'],mark['version'],json.dumps(mark),'legacy snapshot',None,'Editor unavailable',mark['updated'],'pre-upgrade'))


def current(db,mark_id):
    row=db.execute('SELECT * FROM marks WHERE id=?',(mark_id,)).fetchone()
    return public(row) if row else None


def semantic(mark):
    if not mark or mark.get('deleted'):return None
    return {k:mark[k] for k in (*FIELDS,'author','author_id')}


def revision(db,desired,who,action,origin=''):
    old=current(db,desired['id']);now=time.time()
    value={**desired,'version':old['version']+1 if old else 1,'updated':now,'created':old['created'] if old else desired.get('created',now)}
    db.execute('''INSERT OR REPLACE INTO marks(id,page,kind,shape,box,body,status,author_id,author,created,updated,version,reverse_x,reverse_y,deleted)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (value['id'],value['page'],value['kind'],value['shape'],json.dumps(value['box']),value['body'],value['status'],
         value['author_id'],value['author'],value['created'],now,value['version'],value['reverseX'],value['reverseY'],bool(value.get('deleted'))))
    value=current(db,value['id'])
    db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)',
               (value['id'],value['version'],json.dumps(value),action,who['id'],who['username'],now,origin))
    db.execute('INSERT INTO events(at,actor,action,mark_id,snapshot) VALUES (?,?,?,?,?)',
               (now,who['id'],action,value['id'],json.dumps(value)))
    return value


def change(db,desired,who,label,origin=''):
    before={v['id']:current(db,v['id']) for v in desired}
    after={v['id']:revision(db,v,who,label,origin) for v in desired}
    db.execute("UPDATE commands SET state='abandoned' WHERE actor_id=? AND state='undone'",(who['id'],))
    command=db.execute('INSERT INTO commands(actor_id,label,before_state,after_state,state,at) VALUES (?,?,?,?,?,?)',
                      (who['id'],label,json.dumps(before),json.dumps(after),'applied',time.time())).lastrowid
    return after,command


def stacks(db,who):
    rows=db.execute("SELECT id,label,state FROM commands WHERE actor_id=? AND state IN ('applied','undone') ORDER BY id DESC",(who['id'],)).fetchall()
    undo=next((dict(r) for r in rows if r['state']=='applied'),None)
    # Undo newest first; redo the oldest still-undone command first.
    redo=next((dict(r) for r in reversed(rows) if r['state']=='undone'),None)
    return {'undo':undo,'redo':redo}


def travel(db,who,direction,command_id):
    choice=stacks(db,who)[direction]
    if not choice or choice['id']!=command_id:raise HTTPException(409,'The undo history changed. Refresh the drawing.')
    command=db.execute('SELECT * FROM commands WHERE id=? AND actor_id=?',(command_id,who['id'])).fetchone()
    before,after=json.loads(command['before_state']),json.loads(command['after_state'])
    expected=after if direction=='undo' else before
    desired=before if direction=='undo' else after
    for key,value in expected.items():
        if semantic(current(db,key))!=semantic(value):raise HTTPException(409,'This comment was changed by another reviewer. Refresh before undoing.')
    for key,value in desired.items():
        value=value or {**after[key],'deleted':True}
        revision(db,value,who,direction+' / '+command['label'])
    db.execute('UPDATE commands SET state=? WHERE id=?',('undone' if direction=='undo' else 'applied',command_id))


def history(db,mark_id):
    local=[{**{k:r[k] for k in ('version','action','actor','at','origin')},'snapshot':json.loads(r['snapshot'])}
           for r in db.execute('SELECT * FROM revisions WHERE mark_id=? ORDER BY version DESC',(mark_id,))]
    external=[json.loads(r['entry']) for r in db.execute('SELECT entry FROM foreign_history WHERE mark_id=?',(mark_id,))]
    return local+sorted(external,key=lambda v:v['at'],reverse=True)


def portable_history(db,mark_id):
    # Account IDs and sharing permissions never leave the server in a portable PDF.
    return [{**{k:v[k] for k in ('version','action','actor','at','origin')},
             'snapshot':{k:v['snapshot'][k] for k in (*FIELDS,'deleted') if k in v['snapshot']}}
            for v in history(db,mark_id)]


def retain_portable(db,mark,keep_base=True):
    import hashlib
    baseline=mark.get('baseline')
    if keep_base and baseline and isinstance(baseline.get('version'),int) and baseline['version']>=0:
        db.execute('INSERT OR IGNORE INTO portable_bases VALUES (?,?,?)',(mark['id'],baseline['version'],json.dumps(baseline['snapshot'])))
    for entry in mark.get('history',[]):
        if not isinstance(entry,dict) or not isinstance(entry.get('version'),int) or not isinstance(entry.get('snapshot'),dict):continue
        try:at=float(entry['at'])
        except (ValueError,TypeError,KeyError):continue
        if not __import__('math').isfinite(at):continue
        safe={'version':entry['version'],'action':str(entry.get('action','PDF revision'))[:120],
              'actor':str(entry.get('actor','PDF reviewer'))[:150],'at':at,'origin':'Imported PDF history (reported)',
              'snapshot':{k:entry['snapshot'].get(k) for k in (*FIELDS,'deleted')}}
        encoded=json.dumps(safe,sort_keys=True)
        db.execute('INSERT OR IGNORE INTO foreign_history VALUES (?,?,?)',(mark['id'],hashlib.sha256(encoded.encode()).hexdigest(),encoded))
