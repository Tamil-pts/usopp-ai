"""Admin project deletion with a durable recovery archive and retained file bytes."""
import base64
import hashlib
import json
import os
from fastapi import HTTPException
from .workhub import store as hub, timestamp, identity


def delete(user, key, payload):
    hub.actor(user)
    if user.get('role') != 'admin':
        raise HTTPException(403, 'Only Admin can delete a project.')
    from .workhub_quality import store
    store.initialize()
    with hub.db(True) as db:
        p = hub.item(db, key)
        if p['type'] != 'project':
            raise HTTPException(400, 'Choose a project to delete.')
        if payload.get('version') != p['version']:
            raise HTTPException(409, 'The project changed. Refresh before deleting.')
        if payload.get('title') != p['title']:
            raise HTTPException(400, 'Enter the exact project name to confirm deletion.')
        if db.execute("SELECT 1 FROM pi_jobs WHERE project_id=? AND status IN ('queued','running')", (key,)).fetchone() or db.execute("SELECT 1 FROM uploads WHERE project_id=? AND status='uploading'", (key,)).fetchone():
            raise HTTPException(409, 'Finish or cancel active project processing and uploads before deleting.')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'cp_search%'")}
        ids = {'project_id': {key}}
        for field, table, where, values in [
            ('item_id', 'items', 'project_id=?', [key]),
            ('document_id', 'pi_documents', 'project_id=?', [key]),
            ('control_id', 'qc_documents', 'project_id=?', [key]),
            *[(f,t,'project_id=?',[key]) for f,t in [('meeting_id','pi_meetings'),('job_id','pi_jobs'),('file_id','files'),('notification_id','notifications'),('package_id','qc_packages'),('update_id','updates'),('execution_id','qc_executions')]],
        ]:
            ids[field] = {r[0] for r in db.execute('SELECT id FROM "'+table+'" WHERE '+where, values)}
        ids['task_id'] = ids['item_id']
        ids['revision_id'] = {r[0] for r in db.execute('SELECT r.id FROM pi_revisions r JOIN pi_documents d ON d.id=r.document_id WHERE d.project_id=?', (key,))}
        ids['revision_id'].update(r[0] for r in db.execute('SELECT id FROM revisions WHERE project_id=?', (key,)))
        retained = {'qc_audit','qc_sequences','qc_settings','wh_brand_records','wh_brand_assets','wh_brand_defaults','pi_worker_health','wh_dashboards','wh_dashboard_access','wh_dashboard_changes','cp_articles','cp_revisions','cp_actions','cp_files','cp_notification_targets','pc_manual','pc_manual_revisions'}
        selected = {}
        for table in sorted(tables - retained):
            cols = {r[1] for r in db.execute('PRAGMA table_info("'+table+'")')}
            clauses, args = [], []
            for field, values in ids.items():
                if field in cols and values:
                    clauses.append('"'+field+'" IN (SELECT value FROM json_each(?))')
                    args.append(json.dumps(sorted(values)))
            if not clauses:
                continue
            sql = 'SELECT rowid AS __rowid__,* FROM "'+table+'" WHERE ('+' OR '.join(clauses)+')'
            if 'project_id' in cols:
                sql += " AND (project_id=? OR project_id IS NULL OR project_id='')"
                args.append(key)
            rows = [dict(r) for r in db.execute(sql, args)]
            if rows:
                selected[table] = rows
        # Preserve independent documents and published knowledge, detaching only links.
        detached = {}
        for table, field in [('wh_document_spaces','linked_project_id'),('cp_articles','project_id'),('pc_manual','project_id')]:
            if table not in tables:continue
            detached[table] = [dict(r) for r in db.execute('SELECT * FROM '+table+' WHERE '+field+'=?', (key,))]
        archive = {'format':1,'project':p,'deleted_by':user['id'],'deleted_at':timestamp(),'rows':selected,'detached':detached,'file_bytes_retained':True}
        data = json.dumps(archive, ensure_ascii=False, default=lambda v: {'base64':base64.b64encode(v).decode()} if isinstance(v,bytes) else str(v)).encode('utf-8')
        directory = hub.root/'deleted-projects'
        directory.mkdir(exist_ok=True)
        path = directory/(key+'-'+str(p['version'])+'-'+identity()+'.json')
        # An immutable complete archive must reach disk before any database removal.
        with path.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        for table, rows in reversed(list(selected.items())):
            db.executemany('DELETE FROM "'+table+'" WHERE rowid=?', [(r['__rowid__'],) for r in rows])
        for table, field in [('wh_document_spaces','linked_project_id'),('cp_articles','project_id'),('pc_manual','project_id')]:
            if table not in tables:continue
            db.execute('UPDATE '+table+' SET '+field+'=NULL'+(',task_id=NULL' if table in {'cp_articles','pc_manual'} else '')+' WHERE '+field+'=?', (key,))
        result = {'deleted':True,'project_id':key,'title':p['title'],'archived_rows':{t:len(v) for t,v in selected.items()},'archive_sha256':hashlib.sha256(data).hexdigest(),'archive_name':path.name,'files_retained':True}
        store.audit(db,user,key,'admin_project_deleted',result)
        return result
