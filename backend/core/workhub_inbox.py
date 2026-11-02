"""One personal inbox over the existing work, document and time approvals."""
from collections import Counter
from fastapi import HTTPException
from .workhub import store as hub, NEXT_OWNER
from .workhub_quality import store


def inbox(user,page=1,kind=''):
    store.initialize();hub.actor(user);rows=[]
    with hub.db() as db:
        people={u['id']:u['username'] for u in hub.users()}
        for raw in db.execute("SELECT * FROM items WHERE type IN ('project','task') AND stage IN ('quality','release_approval','ready_release') ORDER BY updated_at"):
            item=dict(raw)
            if item[NEXT_OWNER[item['stage']]]!=user['id']:continue
            try:project=hub.contribute(db,item['project_id'],user)
            except HTTPException:continue
            rows.append({'id':'workflow:'+item['id'],'kind':'workflow','title':item['title'],'project_id':item['project_id'],
              'project':project['title'],'status':hub.public(item)['stage_label'],'updated_at':item['updated_at'],'item':hub.public(item)})
        for raw in db.execute('''SELECT d.id,d.title,d.project_id,d.kind,q.id AS control_id,q.stage,COALESCE(q.number,dn.number) AS document_number,
          r.id AS revision_id,r.number AS revision_number,r.created_at,c.label,c.status AS controlled_status,
          COALESCE(c.reviewer_id,r.reviewer_id) AS reviewer FROM pi_documents d JOIN pi_revisions r ON r.id=d.current_revision
          LEFT JOIN qc_documents q ON q.document_id=d.id LEFT JOIN qc_revisions c ON c.id=r.id
          LEFT JOIN wh_document_numbers dn ON dn.document_id=d.id
          WHERE COALESCE(c.status,r.status) IN ('in_review','review') AND COALESCE(c.reviewer_id,r.reviewer_id)=?''',(user['id'],)):
            d=dict(raw)
            try:
                p=store.project(db,d['project_id'],user)
                if p.get('is_document_space'):
                    assigned=p.get('reviewer_id');project_name=p.get('linked_project_name') or 'Standalone document'
                else:
                    hub.contribute(db,p['id'],user);assigned=p['release_id'] if d['stage']=='closure' else p['quality_id'];project_name=p['title']
                if d['control_id'] and assigned!=user['id']:continue
            except HTTPException:continue
            stage=d['stage'] or d['kind'];section='meetings' if stage in {'mom','frd','flowchart'} else 'quality' if stage in {'fat','quality','closure'} else 'documents'
            rows.append({'id':'document:'+d['id'],'kind':'document','title':d['title'],'project_id':d['project_id'],
              'project':project_name,'status':'Document review','updated_at':d['created_at'],'document_id':d['id'],
              'number':d['document_number'] or 'MOM / '+d['id'][:8].upper(),'revision':d['label'] or 'R'+str(d['revision_number']),
              'stage':stage,'section':section,'control_id':d['control_id'],'independent':bool(p.get('is_document_space'))})
        for raw in db.execute("SELECT * FROM updates WHERE (reviewer_id=? AND time_status='submitted') OR (author_id=? AND time_status='changes_requested')",(user['id'],user['id'])):
            row=dict(raw)
            try:p=hub.contribute(db,row['project_id'],user)
            except HTTPException:continue
            correction=row['time_status']=='changes_requested'
            rows.append({'id':('correction:' if correction else 'time:')+row['id'],'kind':'correction' if correction else 'time',
              'title':('Correct time entry' if correction else 'Review time entry')+' / '+people.get(row['author_id'],'Engineer'),
              'project_id':p['id'],'project':p['title'],'status':'Needs correction' if correction else 'Time approval',
              'updated_at':row['created_at'],'entry':row})
    rows.sort(key=lambda r:r['updated_at'])
    counts=dict(Counter(r['kind'] for r in rows));selected=[r for r in rows if not kind or r['kind']==kind]
    return {'items':selected[(page-1)*20:page*20],'total':len(selected),'page':page,'page_size':20,'counts':counts,'pending':sum(v for k,v in counts.items() if k!='correction')}
