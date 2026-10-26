"""Read existing WorkHub facts; never invoke or alter an engineering engine."""
import json
import math
import os
import threading
from . import store
from .store import hub,timestamp,encode

TOOLS={'validation':'ByteMap','metadata':'ByteMap metadata','datainspect':'DataInspect','rules':'LogicScan','compare':'MatchView'}
SCORE_FIELDS=('score','validationScore','overallScore','complianceScore')
EVENTS={'created','start','complete_development','submit_quality','quality_pass','approve_release','release','request_changes',
        'reopen','block','resume','issue_created','issue_resolved','issue_open','time_approved','daily_update',
        'intelligence_document_approve','sprint_updated'}
STOP=threading.Event();THREAD=None;GUARD=threading.Lock();COLLECT=threading.Lock()


def put(db,source_type,source_id,project_id,task_id,actor,subject,event,title,at,verification,data):
    key=source_type+':'+str(source_id)
    db.execute('''INSERT INTO pc_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
      project_id=excluded.project_id,task_id=excluded.task_id,actor_id=excluded.actor_id,subject_id=excluded.subject_id,event_type=excluded.event_type,title=excluded.title,
      verification=excluded.verification,data=excluded.data,occurred_at=excluded.occurred_at,updated_at=excluded.updated_at
      WHERE pc_events.data!=excluded.data OR pc_events.verification!=excluded.verification OR pc_events.subject_id IS NOT excluded.subject_id OR pc_events.actor_id IS NOT excluded.actor_id OR pc_events.project_id IS NOT excluded.project_id OR pc_events.task_id IS NOT excluded.task_id''',
      (key,source_type,str(source_id),project_id,task_id,actor,subject,event,title,at,verification,store.bounded(data),timestamp()))


def collect():
    store.initialize()
    if not COLLECT.acquire(blocking=False):return
    try:
      with hub.db(True) as db:
        state=db.execute("SELECT value FROM pc_state WHERE key='native_event_cursor'").fetchone();cursor=int(state[0]) if state else 0
        items={r['id']:dict(r) for r in db.execute('SELECT * FROM items')}
        users={u['id'] for u in hub.users()}
        collect_archives(db,users)
        native=db.execute('SELECT * FROM events WHERE id>? ORDER BY id LIMIT 1000',(cursor,)).fetchall()
        for event in native:
            if event['event'] not in EVENTS or event['actor_id'] not in users:continue
            item=items.get(event['item_id'])
            if not item:continue
            detail=json.loads(event['detail']);subject=event['actor_id'];verification='recorded';data={'native_event_id':event['id'],'detail':detail,'item_type':item['type'],'work_type':item['kind']}
            task_id=item['id'] if item['type']=='task' else None
            if event['event'] in {'quality_pass','approve_release','release','request_changes'}:
                development=db.execute("SELECT actor_id,id FROM events WHERE item_id=? AND id<? AND event='complete_development' ORDER BY id DESC LIMIT 1",(item['id'],event['id'])).fetchone()
                subject=development['actor_id'] if development else None
                verification='independent_review' if subject and subject!=event['actor_id'] else 'self_review' if subject else 'attribution_missing'
                if event['event']=='request_changes':verification='recorded_feedback'
                data['development_event_id']=development['id'] if development else None
                # A current closed record preserves the deadline at that closure.
                # Historical reopened cycles do not borrow today's assignee/dates.
                latest_release=db.execute("SELECT id FROM events WHERE item_id=? AND event='release' ORDER BY id DESC LIMIT 1",(item['id'],)).fetchone() if event['event']=='release' else None
                if event['event']=='release' and item['stage']=='released' and item.get('completed_at') and latest_release and latest_release['id']==event['id']:
                    data['due_date']=item.get('due_date') or None
                    data['completed_at']=item['completed_at']
                if event['event']=='release' and subject:
                    quality=db.execute("SELECT actor_id FROM events WHERE item_id=? AND id>? AND id<=? AND event IN ('quality_pass','approve_release') AND actor_id!=? ORDER BY id DESC LIMIT 1",(item['id'],development['id'],event['id'],subject)).fetchone()
                    if quality and quality['actor_id']!=subject:verification='independent_review'
            elif event['event']=='time_approved':
                entry=db.execute('SELECT author_id,minutes FROM updates WHERE id=?',(detail.get('update_id'),)).fetchone()
                subject=entry['author_id'] if entry else None;data['minutes']=entry['minutes'] if entry else None
                verification='time_review_only' # Hours are not a work-quality score.
            elif event['event']=='issue_resolved':
                issue=db.execute('SELECT title,status,owner_id FROM issues WHERE id=?',(detail.get('issue_id'),)).fetchone()
                data['issue']=dict(issue) if issue else None
                data['note']='The recorded resolver receives activity attribution; independent technical verification is separate.'
            elif event['event']=='intelligence_document_approve':
                exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='pi_revisions'").fetchone()
                revision=db.execute('SELECT created_by,number,document_id FROM pi_revisions WHERE id=?',(detail.get('revision_id'),)).fetchone() if exists else None
                subject=revision['created_by'] if revision else None
                verification='independent_review' if subject and subject!=event['actor_id'] else 'self_review' if subject else 'attribution_missing'
                data['document_id']=revision['document_id'] if revision else None
            data['item_id']=item['id']
            put(db,'workhub',event['id'],event['project_id'],task_id,event['actor_id'],subject,event['event'],event['event'].replace('_',' ').capitalize()+': '+item['title'],event['created_at'],verification,data)
        if native:db.execute("INSERT OR REPLACE INTO pc_state VALUES('native_event_cursor',?)",(str(native[-1]['id']),))
        task_links={}
        for update in db.execute("SELECT project_id,item_id,run_ids FROM updates WHERE run_ids!='[]'"):
            item=items.get(update['item_id'])
            if not item or item['type']!='task':continue
            for reference in json.loads(update['run_ids']):
                if isinstance(reference,dict) and reference.get('id'):task_links.setdefault((update['project_id'],reference['id']),set()).add(item['id'])
        for row in db.execute('SELECT r.*,u.item_id FROM engineering_runs r LEFT JOIN updates u ON u.id=r.update_id'):
            value=dict(row)
            if value['author_id'] not in users:continue
            summary=json.loads(value['summary']);summary=summary if isinstance(summary,dict) else {'source_summary':summary}
            data={'run_id':value['run_id'],'tool':TOOLS.get(value['kind'],value['kind']),'kind':value['kind'],'test_id':value['test_id'],
                  'iteration':value['iteration'],'status':value['status'],'summary':summary,'completed_at':value['completed_at'],'origin':'workhub',
                  'evidence_url':'/api/workhub/projects/'+value['project_id']+'/shared-results/'+value['run_id']+'/evidence',
                  'note':'An executed run records tool activity. Completion is not proof that its engineering checks passed.'}
            links=task_links.get((value['project_id'],value['run_id']),set());data['related_task_ids']=sorted(links)
            item=items.get(value.get('item_id'));task_id=item['id'] if item and item['type']=='task' else next(iter(links)) if len(links)==1 else None
            old=db.execute('SELECT data FROM pc_events WHERE id=?',('run:'+value['run_id'],)).fetchone()
            old=json.loads(old[0]) if old else {}
            data['recorded_scores']=old.get('recorded_scores',[]);data['archive_score_checked']=old.get('archive_score_checked',False)
            if value['status']!='running' and not data['archive_score_checked']:
                # Read existing archived score fields, without invoking validators.
                try:
                    from backend.core.persistent_store import db as archive_db
                    with archive_db() as archive:
                        score=archive.execute("SELECT json_extract(record_json,'$.completedAt'),json_extract(result_json,'$.score'),json_extract(result_json,'$.validationScore'),json_extract(result_json,'$.overallScore') FROM run_archive WHERE id=?",(value['run_id'],)).fetchone()
                    if score and score[0]:
                        data['archive_score_checked']=True
                        data['recorded_scores']=[{'field':field,'value':score[index]} for index,field in enumerate(('score','validationScore','overallScore'),1) if type(score[index]) in (int,float) and math.isfinite(score[index])]
                except Exception:pass # The original result remains the evidence source.
            put(db,'run',value['run_id'],value['project_id'],task_id,value['author_id'],value['author_id'],'engineering_run',
                data['tool']+' · Iteration '+str(value['iteration']),value['completed_at'] or value['created_at'],'native_result',data)
        db.execute("INSERT OR REPLACE INTO pc_state VALUES('last_collected',?)",(timestamp(),))
    finally:COLLECT.release()


def collect_archives(db,users):
    """Project existing private archives into their recorded author's own profile.

    The archive is authoritative for author identity. No matching by username,
    project label or filename is used to publish or attribute historical work.
    INSERT OR REPLACE in the native archive gives updates a fresh rowid.
    """
    from backend.core.persistent_store import db as archive_db
    state=db.execute("SELECT value FROM pc_state WHERE key='archive_cursor'").fetchone()
    cursor=int(state[0]) if state else 0
    with archive_db() as archive:
        rows=archive.execute("SELECT rowid AS cursor,id,user_id,kind,created_at,record_json FROM run_archive WHERE rowid>? ORDER BY rowid LIMIT 1000",(cursor,)).fetchall()
    for row in rows:
        if row['kind'] not in TOOLS or row['user_id'] not in users:continue
        if db.execute('SELECT 1 FROM engineering_runs WHERE run_id=?',(row['id'],)).fetchone():continue
        try:record=json.loads(row['record_json'])
        except (TypeError,ValueError):continue
        owner=record.get('user') or {}
        if not isinstance(owner,dict) or owner.get('id')!=row['user_id'] or owner.get('isDemo'):continue
        summary=record.get('summary') or {};summary=summary if isinstance(summary,dict) else {}
        scores=[{'field':key,'value':summary[key]} for key in SCORE_FIELDS if type(summary.get(key)) in (int,float) and math.isfinite(summary[key])]
        data={'run_id':row['id'],'kind':row['kind'],'tool':TOOLS[row['kind']],'test_id':record.get('testId',''),
              'source_project_name':str(record.get('projectName') or ''),'iteration':None,
              'status':record.get('status') or 'recorded','summary':summary,'recorded_scores':scores,
              'completed_at':record.get('completedAt'),'origin':'private_archive',
              'evidence_url':'/api/workhub/growth/events/run:'+row['id']+'/result',
              'note':'Original private archive attributed to its recorded author. The source project label is not a WorkHub assignment. Submit reviewed evidence to establish a project/task contribution.'}
        put(db,'run',row['id'],None,None,row['user_id'],row['user_id'],'engineering_run',
            TOOLS[row['kind']]+' · Archived result',record.get('completedAt') or row['created_at'],'native_result',data)
    if rows:db.execute("INSERT OR REPLACE INTO pc_state VALUES('archive_cursor',?)",(str(rows[-1]['cursor']),))


def run():
    while not STOP.is_set():
        try:collect()
        except Exception:
            from backend.core.runtime import log
            log.exception('WORKHUB_GROWTH_COLLECTOR_ERROR')
        try:seconds=int(os.getenv('USOPP_PERFORMANCE_POLL_SECONDS','30'))
        except ValueError:seconds=30
        STOP.wait(max(5,min(300,seconds)))


def start():
    global THREAD
    with GUARD:
        if THREAD and THREAD.is_alive():return
        STOP.clear();THREAD=threading.Thread(target=run,name='workhub-performance-collector',daemon=True);THREAD.start()


def shutdown():STOP.set()
