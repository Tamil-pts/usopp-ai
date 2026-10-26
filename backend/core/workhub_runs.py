"""Publish new, personal engineering runs to shared project development evidence."""
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from .workhub import store,identity,timestamp,encode,NEXT_OWNER

TOOLS={'validation':'ByteMap','metadata':'ByteMap metadata','datainspect':'DataInspect','compare':'MatchView','rules':'LogicScan'}

def normalized(value):return ''.join(char for char in str(value).casefold() if char.isalnum())[:200]

def file_title(value):
    value=Path(str(value).replace('\\','/')).name
    value=re.sub(r'\s*\(\d+\)(?=\.[^.]+$)','',value)
    value=re.sub(r'\.(xlsx?|csv)(?:\s.*)?$','',value,flags=re.I)
    value=re.sub(r'\.(xlsx?|csv|zip|apj|s7p|zap\d*|pdf)$','',value,flags=re.I)
    value=re.sub(r'_[A-Za-z0-9]+_TEST_\d{8}_\d{6}_[a-f0-9]+.*$','',value,flags=re.I)
    return value.strip()[:180]

def source_identity(record,data,root=None):
    location=Path(root or record.get('snapshotPath') or record.get('projectPath') or '.')
    native=sorted(path for path in location.iterdir() if path.is_file() and path.suffix.casefold()=='.apj') if location.is_dir() and (root or record.get('snapshotPath') or record.get('projectPath')) else []
    display=str((data.get('newName') or record.get('projectName') or '') if record['kind']=='compare' else record.get('projectName') or '').strip()
    aliases=set()
    if native:
        native_name=native[0].name
        title=display if display and display.casefold() not in {'source','project','uploadedproject'} else native[0].stem
        aliases.update(normalized(value) for value in (title,native[0].stem))
        return 'native:'+native_name.casefold(),title[:180],native_name,aliases,'B&R PLC'
    if record['kind']=='datainspect':
        plc=data.get('plc') or {};source=str(data.get('metadataSource') or '')
        title=file_title(source) if re.search(r'\.(xlsx?|csv)(?:$|\s)',source,re.I) else ''
        if title:aliases.add(normalized(title))
        else:title=str(plc.get('name') or display or 'PLC readings')[:180]
        layout=[{key:row.get(key) for key in ('tagCode','groupCode','offset','dataType','arraySize')} for row in data.get('metadata',[]) if isinstance(row,dict)]
        signature=hashlib.sha256(encode(layout).encode()).hexdigest()[:24]
        target=':'.join(str(plc.get(key) or '') for key in ('frameProtocol','targetMode','ip','port','machineId'))
        return 'readings:'+normalized(file_title(source))+':'+target+':'+signature,title,source[:500],aliases,'Other PLC' if plc.get('frameProtocol')=='ybs' else 'B&R PLC'
    title=file_title(display or location.name) or 'Engineering project'
    aliases.add(normalized(title))
    return 'project:'+normalized(title),title,location.name,aliases,'General'

def run_body(record,iteration,source):
    label=TOOLS[record['kind']];status=str(record.get('status') or 'running')
    lines=[f'Iteration {iteration} - {label}',f'Test ID: {record.get("testId","")}',f'Recorded run: {status}. This is engineering evidence; workflow approval is separate.']
    if source:lines.append('Source: '+source)
    summary=record.get('summary') or {}
    numbers=[str(key)+': '+str(value) for key,value in summary.items() if isinstance(value,(int,float)) and not isinstance(value,bool)]
    if numbers:lines.append('Summary: '+', '.join(numbers[:16]))
    if record.get('error'):lines.append('Run error: '+str(record['error'])[:1500])
    return '\n'.join(lines)[:8000]

def synchronize(record,data,root=None):
    if record.get('kind') not in TOOLS:return {}
    user=record.get('user') or {}
    if not user.get('id') or user.get('isDemo'):return {}
    enabled=next((row for row in store.users() if row['id']==user['id'] and row['active']),None)
    if not enabled:return {}
    source_key,title,source,aliases,kind=source_identity(record,data,root)
    created=record.get('createdAt') or timestamp();now=timestamp();run_id=record['id']
    with store.db(True) as db:
        existing=db.execute('SELECT * FROM engineering_runs WHERE run_id=?',(run_id,)).fetchone()
        if existing:
            project=store.item(db,existing['project_id']);iteration=existing['iteration'];update_id=existing['update_id']
        else:
            matches={row[0] for row in db.execute('SELECT project_id FROM engineering_sources WHERE owner_id=? AND source_key=?',(user['id'],source_key))}
            if not matches:
                matches={row[0] for row in db.execute('SELECT DISTINCT s.project_id FROM engineering_sources s JOIN items i ON i.id=s.project_id WHERE s.source_key=? AND (i.created_by=? OR i.owner_id=? OR EXISTS(SELECT 1 FROM items t WHERE t.project_id=i.id AND t.owner_id=?))',(source_key,user['id'],user['id'],user['id']))}
            native_id=Path(source).stem.casefold() if source_key.startswith('native:') else ''
            if not matches and len(normalized(native_id))>=6 and re.search(r'[a-z].*\d',native_id) and not native_id.startswith(('project','application','main','controller')):
                matches={row[0] for row in db.execute('SELECT project_id FROM engineering_sources WHERE source_key=?',(source_key,))}
            if not matches and aliases:
                for alias in aliases:
                    candidates={row[0] for row in db.execute('SELECT project_id FROM engineering_sources WHERE owner_id=? AND source_key=?',(user['id'],'alias:'+alias))}
                    if source_key.startswith('native:'):
                        candidates={key for key in candidates if not db.execute("SELECT 1 FROM engineering_sources WHERE project_id=? AND source_key LIKE 'native:%' LIMIT 1",(key,)).fetchone()}
                    matches.update(candidates)
            if not matches:
                candidates=[dict(row) for row in db.execute("SELECT * FROM items WHERE type='project' AND (created_by=? OR owner_id=?)",(user['id'],user['id']))]
                candidates=[row for row in candidates if normalized(row['title']) in aliases and not db.execute('SELECT 1 FROM engineering_sources WHERE project_id=? LIMIT 1',(row['id'],)).fetchone()]
                if len(candidates)==1:matches.add(candidates[0]['id'])
            if len(matches)==1:project=store.item(db,next(iter(matches)))
            else:
                key=identity()
                db.execute('''INSERT INTO items(id,project_id,type,title,kind,description,created_by,owner_id,quality_id,approver_id,release_id,stage,started_at,created_at,updated_at)
                  VALUES(?,?,'project',?,?,?,?,?,?,?,?,'development',?,?,?)''',
                  (key,key,title,kind,'Created automatically from saved engineering work. Reviewers and release ownership can be reassigned when needed.',user['id'],user['id'],user['id'],user['id'],user['id'],created,created,now))
                project=store.item(db,key);store.event(db,project,user,'project_created_from_engineering',{'source':source,'tool':TOOLS[record['kind']]})
            for value in [source_key,*('alias:'+alias for alias in aliases if alias)]:
                db.execute('INSERT OR IGNORE INTO engineering_sources VALUES(?,?,?)',(user['id'],value,project['id']))
            iteration=db.execute('SELECT COALESCE(MAX(iteration),0)+1 FROM engineering_runs WHERE project_id=?',(project['id'],)).fetchone()[0]
            update_id=identity()
            db.execute('INSERT INTO engineering_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (run_id,project['id'],update_id,iteration,record['kind'],record.get('testId',''),user['id'],record.get('status','running'),encode(record.get('summary') or {}),source,created,record.get('completedAt')))
            previous=project['stage'];review_check=previous in {'quality','release_approval','ready_release'} and project[NEXT_OWNER[previous]]==user['id']
            stage=previous if review_check or previous=='blocked' else 'development'
            db.execute("UPDATE items SET stage=?,started_at=COALESCE(started_at,?),completed_at=NULL,review_revision=?,review_run_id=?,version=version+1,updated_at=? WHERE id=?",(stage,created,project['review_revision'] if review_check else None,project.get('review_run_id') if review_check else None,now,project['id']))
            store.event(db,project,user,'engineering_iteration_started',{'run_id':run_id,'iteration':iteration,'tool':TOOLS[record['kind']],'from':previous,'to':stage,'review_check':review_check})
            if stage=='development' and previous not in {'todo','development','blocked'}:
                store.notify(db,project,user['id'],[project['owner_id'],project[NEXT_OWNER[previous]]],'New development iteration: '+project['title'],f'Iteration {iteration} was started. The project returned to development; earlier decisions remain in history.')
        reference={'id':run_id,'kind':record['kind'],'testId':record.get('testId',''),'projectName':record.get('projectName',''),'iteration':iteration}
        body=run_body(record,iteration,source)
        db.execute('''INSERT INTO updates(id,project_id,item_id,author_id,body,work_date,minutes,file_ids,run_ids,created_at,time_status)
          VALUES(?,?,?,?,?,?,0,'[]',?,?,'none') ON CONFLICT(id) DO UPDATE SET body=excluded.body,run_ids=excluded.run_ids''',
          (update_id,project['id'],project['id'],user['id'],body,date.today().isoformat(),encode([reference]),created))
        db.execute('UPDATE engineering_runs SET status=?,summary=?,completed_at=? WHERE run_id=?',
                   (record.get('status','running'),encode(record.get('summary') or {}),record.get('completedAt'),run_id))
        db.execute('UPDATE items SET updated_at=? WHERE id=?',(now,project['id']))
        return {'workhubProjectId':project['id'],'workhubIteration':iteration,'workhubUpdateId':update_id}

def reconcile_pending():
    """Only retry new runs explicitly opted into automatic capture, never old history."""
    from . import run_history
    from .persistent_store import archived_records
    for record in [row for row in archived_records() if row.get('workhubAutoCapture') and row.get('workhubSyncPending')][:10]:
        folder=run_history.RECORDS/record['id']
        try:
            with run_history.run_lock(record['id']):
                data=json.loads((folder/'result.json').read_text(encoding='utf-8'))
                record=run_history.read_record(record['id'])
                if not record.get('workhubSyncPending'):continue
                link=synchronize(record,data)
                record.update(link,workhubSyncPending=False);data.update(link,workhubSyncPending=False)
                run_history.write_json(folder/'record.json',record);run_history.write_json(folder/'result.json',data)
                run_history.archive_database(record,data)
        except Exception:
            from .runtime import log
            log.exception('WORKHUB_RUN_RECONCILE_ERROR run=%s',record['id'])
    with store.db() as db:running=[row[0] for row in db.execute("SELECT run_id FROM engineering_runs WHERE status='running' LIMIT 50")]
    for key in running:
        try:
            record=run_history.read_record(key)
            if record.get('status')!='running':
                data=json.loads((run_history.RECORDS/key/'result.json').read_text(encoding='utf-8'));synchronize(record,data)
        except (OSError,ValueError):continue
