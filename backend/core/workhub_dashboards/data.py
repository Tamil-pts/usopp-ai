"""Server aggregation over whitelisted projections of existing authorized records.

SQL below is static; field names, predicates and user expressions never enter SQL.
All limits are explicit. A query cannot silently aggregate only the first N records.
"""
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from fastapi import HTTPException
from backend.core.workhub import store as hub,timestamp
from backend.core.workhub_growth import store as growth,performance
from . import schema

MAX_RECORDS=100000
def read(db,sql,args=()):
    rows=db.execute(sql,args).fetchmany(MAX_RECORDS+1)
    if len(rows)>MAX_RECORDS:raise HTTPException(422,'This source exceeds the dashboard record limit. Archive older records or use a narrower source.')
    return [dict(row) for row in rows]

def records(user,key):
    growth.personal(user);growth.initialize()
    people={u['id']:u['username'] for u in hub.users()}
    with hub.db() as db:
        items=read(db,'SELECT * FROM items');projects={r['id']:r for r in items if r['type']=='project'}
        names={k:r['title'] for k,r in projects.items()};tasks_by_project=defaultdict(list)
        if key=='projects':
            for task in items:
                if task['type']=='task':tasks_by_project[task['project_id']].append(hub.public(task))
        managed=growth.managed_projects(db,user)
        def visible(r):return user['role']=='admin' or user['id'] in {r.get('subject_id'),r.get('actor_id')} or r.get('project_id') in managed
        def base(r,uid=None,at=None):
            pid=r.get('project_id');uid=uid if uid is not None else r.get('owner_id')
            return {'id':str(r['id']),'title':r.get('title',''),'project_id':pid,'project':names.get(pid),
              'engineer_id':str(uid) if uid is not None else None,'engineer':people.get(uid),
              'date':at or r.get('created_at'),'status':r.get('stage',r.get('status'))}
        output=[]
        if key in {'projects','tasks','milestones','assignments'}:
            for r in items:
                if key=='projects' and r['type']!='project' or key=='tasks' and r['type']!='task' or key=='milestones' and (r['type']!='task' or not r['milestone']):continue
                if key=='assignments':
                    for field,label in [('owner_id','Development'),('quality_id','Quality'),('approver_id','Release approval'),('release_id','Release owner')]:
                        if r[field] is not None:output.append({**base(r,r[field]),'id':r['id']+':'+field,'role':label,'item_type':r['type']})
                    continue
                value=hub.public(r)
                if r['type']=='project':value.update(hub.completion(value,tasks_by_project[r['id']]))
                output.append({**base(r),'work_type':r['kind'],'phase':r.get('work_phase'),'progress':value['progress'],
                  'development_progress':value.get('development_progress'),'completed':int(r['stage'] in {'development_completed','quality','release_approval','ready_release','released'}),
                  'released':int(r['stage']=='released'),'start':r.get('start_date'),'end':r.get('due_date'),
                  'hours':r.get('planned_hours'),'health':value.get('health'),
                  '_url':'/?workhubProject='+r['project_id']+'&workhubItem='+r['id']})
        elif key=='approvals':
            item_map={r['id']:r for r in items}
            for r in items:
                if r['stage'] in {'quality','release_approval'}:
                    uid=r['quality_id'] if r['stage']=='quality' else r['approver_id']
                    output.append({**base(r,uid,r['updated_at']),'id':'pending:'+r['id'],'status':'pending','decision':r['stage'],'item_type':r['type']})
            for e in read(db,"SELECT * FROM events WHERE event IN ('quality_pass','approve_release','request_changes')"):
                r=item_map.get(e['item_id'])
                if r:output.append({**base(r,e['actor_id'],e['created_at']),'id':'decision:'+str(e['id']),
                  'status':'changes_requested' if e['event']=='request_changes' else 'approved','decision':e['event'],'item_type':r['type']})
        elif key in {'activity','validation'}:
            for r in read(db,'SELECT * FROM pc_events ORDER BY occurred_at'):
                if not visible(r) or key=='validation' and r['source_type']!='run':continue
                d=json.loads(r['data']);scores=d.get('recorded_scores') or []
                # A run remains one record. Ambiguous multiple score fields are not averaged or selected arbitrarily.
                score=scores[0] if len(scores)==1 else {}
                output.append({**base(r,r['subject_id'],r['occurred_at']),'event':r['event_type'],
                  'verification':r['verification'],'tool':d.get('tool'),'status':d.get('status',r['verification']),
                  'iteration':d.get('iteration'),'score':score.get('value'),'score_field':score.get('field'),
                  '_url':('/?workhubProject='+r['project_id']+('&workhubItem='+r['task_id'] if r['task_id'] else '')) if r['project_id'] else '/api/workhub/growth/events/'+r['id']+('/result' if r['source_type']=='run' else '')})
        elif key in {'contributions','capabilities'}:
            # Existing profile rules and calculations define the authorized facts, including leaf-task de-duplication.
            for uid in people:
                try:p=performance._profile(db,user,uid,365,with_details=True)
                except HTTPException as exc:
                    if exc.status_code==403:continue
                    raise
                if key=='contributions':
                    for r in p['proofs']:
                        output.append({**base(r,uid,r['at']),'activity':r.get('activity'),'reviewer':people.get(r.get('reviewed_by')),
                          '_url':('/?workhubArticle='+r['object_id']) if r['source']=='article' else ('/?workhubEvidence='+r['object_id']) if r['source']=='manual' else ('/?workhubProject='+r['project_id']+('&workhubItem='+r['task_id'] if r['task_id'] else '')) if r['project_id'] else '/api/workhub/growth/events/'+r['object_id']})
                else:
                    for c in p['capabilities']:
                        output.append({'id':str(uid)+':'+c['id'],'title':c['title'],'engineer_id':str(uid),'engineer':people[uid],
                          'project_id':None,'project':None,'date':None,'capability':c['title'],
                          'assessment':c['level'] if c['verified_records'] else 'Not enough information',
                          'reviewed_records':c['verified_records'] or None,'projects_count':c['projects'] if c['verified_records'] else None})
        elif key=='knowledge':
            for r in read(db,'SELECT a.id,a.author_id,a.project_id,r.title,r.category,r.number,r.published_at FROM cp_articles a JOIN cp_revisions r ON r.id=a.published_revision WHERE r.status=\'published\''):
                output.append({**base(r,r['author_id'],r['published_at']),'category':growth.CATEGORIES.get(r['category'],r['category']),
                  'revision':r['number'],'_url':'/?workhubArticle='+r['id']})
        elif key=='documents':
            for r in read(db,'SELECT * FROM files'):
                output.append({**base({**r,'title':r['name']},r['uploaded_by']),'kind':'Project attachment','size':r['size'],'revision':None,
                  '_url':'/api/workhub/files/'+r['id']+'/download'})
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='pi_documents'").fetchone()
            if exists:
                controls={r['document_id']:dict(r) for r in db.execute('SELECT document_id,stage FROM qc_documents')} if db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_documents'").fetchone() else {}
                for r in read(db,"SELECT d.id,d.project_id,d.title,d.kind,d.created_by,r.created_at,r.number FROM pi_documents d JOIN pi_revisions r ON r.id=d.approved_revision WHERE r.status='approved'"):
                    control=controls.get(r['id']);section='meetings' if r['kind'] in {'mom','frd','flowchart'} else 'overview' if r['kind']=='plan' else 'documents'
                    if control:section='meetings' if control['stage']=='frd' else 'documents' if control['stage'] in {'corrections','test'} else 'quality'
                    link='/?workhubProject='+r['project_id']+'&workhubSection='+section
                    if control:link+='&qualityStage='+control['stage']
                    elif r['kind']=='source':link+='&piDocument='+r['id']
                    else:link+='&piReview='+r['id']+('&workhubView=planning' if r['kind']=='plan' else '')
                    output.append({**base(r,r['created_by']),'kind':r['kind'],'size':None,'revision':r['number'],
                      '_url':link})
        else:schema.fail('Unsupported data source.')
    if len(output)>MAX_RECORDS:raise HTTPException(422,'Too many source records for one dashboard query.')
    return output

def matches(row,f):
    value=row.get(f['field']);op=f['op'];target=f['value']
    if op=='is_set':return (value is not None and value!='')==target
    if op=='eq':return value==target
    if op=='ne':return value!=target
    if op=='in':return value in target
    if value is None:return False
    if op=='contains':return str(target).casefold() in str(value).casefold()
    try:return value>=target if op=='gte' else value<=target
    except TypeError:return False

def grouped(value,grain):
    if value is None or value=='':return 'Not recorded'
    if grain=='value':return str(value)
    try:d=date.fromisoformat(str(value)[:10])
    except ValueError:return 'Not recorded'
    if grain=='week':return (d-timedelta(days=d.weekday())).isoformat()
    if grain=='month':return d.strftime('%Y-%m')
    if grain=='year':return str(d.year)
    return d.isoformat()

def aggregate(rows,metric):
    values=[r.get(metric['field']) for r in rows if r.get(metric['field']) is not None]
    agg=metric['aggregation']
    if agg=='count':return len(values)
    if agg=='distinct':return len(set(values))
    numbers=[v for v in values if type(v) in (int,float) and math.isfinite(v)]
    if not numbers:return None
    if agg=='sum':return sum(numbers)
    if agg=='avg':return sum(numbers)/len(numbers)
    return min(numbers) if agg=='min' else max(numbers)

def execute(user,payload):
    q=schema.query(payload);rows=records(user,q['source']);g=q['global'];notes=[]
    if q['source']=='capabilities' and any(g[k] for k in ('project_id','from','to')):
        # Capability snapshots are not dated facts; never pretend a date filter changed the assessment.
        raise HTTPException(422,'Capability snapshots use the existing 365-day profile window. Clear project/date filters for this widget, or use Reviewed contributions for date-filtered work.')
    filters=q['filters'][:]
    if g['project_id']:filters.append({'field':'project_id','op':'eq','value':g['project_id']})
    if g['engineer_id']:filters.append({'field':'engineer_id','op':'eq','value':g['engineer_id']})
    rows=[r for r in rows if all(matches(r,f) for f in filters) and (not g['from'] or r.get('date') and str(r['date'])[:10]>=g['from']) and (not g['to'] or r.get('date') and str(r['date'])[:10]<=g['to'])]
    if q['source']=='validation':notes.append('Runs and iterations measure activity. Run completion does not imply validation passed. Scores are included only when exactly one recorded score field exists.')
    if q['source']=='capabilities':notes.append('Existing 365-day capability profile. Supporting work counts are not capability scores. Missing reviewed work is not poor performance.')
    if q['source']=='contributions':notes.append('Reviewed contributions from the existing 365-day performance profile. Date filters narrow that window.')
    dims=q['dimensions'];metrics=q['metrics'];totals=[aggregate(rows,m) for m in metrics]
    histogram=None
    if q['mode']=='histogram':
        field=metrics[0]['field'];nums=[r.get(field) for r in rows if type(r.get(field)) in (int,float) and math.isfinite(r[field])]
        histogram=[];values=[]
        if nums:
            low=min(nums);high=max(nums);span=high-low or 1
            if not math.isfinite(span):raise HTTPException(422,'Numeric range is too large to bin safely.')
            step=span/q['bin_count'];counts=[0]*q['bin_count']
            for value in nums:counts[min(q['bin_count']-1,int((value-low)/step))]+=1
            histogram=[{'from':low+i*step,'to':low+(i+1)*step,'count':count} for i,count in enumerate(counts)]
        notes.append(f'Histogram bins use all {len(nums)} recorded numeric values from {len(rows)} matching records, before the display limit. Missing values are excluded.')
    elif q['mode']=='records':
        # Strip all non-semantic internals except validated internal record links.
        fields=schema.SOURCES[q['source']]['fields']
        if q['sort']=='dimension':ordered=sorted(rows,key=lambda r:tuple(grouped(r.get(d['field']),d['grain']) for d in dims) if dims else (str(r.get('date') or ''),))
        else:
            field=metrics[0]['field']
            ordered=sorted(rows,key=lambda r:(r.get(field) is not None,r.get(field) or (0 if fields[field]['type']=='number' else '')),reverse=q['sort']=='value_desc')
        values=[{**{k:r.get(k) for k in fields},'_url':r.get('_url')} for r in ordered[:q['limit']]]
        if len(rows)>q['limit']:notes.append(f"Showing {q['limit']} of {len(rows)} records. Aggregated totals include every matching record.")
    else:
        buckets=defaultdict(list)
        for r in rows:buckets[tuple(grouped(r.get(d['field']),d['grain']) for d in dims)].append(r)
        values=[{'dimensions':list(k),'values':[aggregate(bucket,m) for m in metrics],'records':len(bucket)} for k,bucket in buckets.items()]
        if q['sort']=='dimension':values.sort(key=lambda r:tuple(r['dimensions']))
        else:values.sort(key=lambda r:(r['values'][0] is not None,r['values'][0] or 0),reverse=q['sort']=='value_desc')
        if len(values)>q['limit']:notes.append(f"Showing {q['limit']} of {len(values)} groups. Totals include all matching records.")
        values=values[:q['limit']]
    return {'source':q['source'],'mode':q['mode'],'rows':values,'total_records':len(rows),'totals':totals,
       'dimensions':dims,'metrics':metrics,'histogram':histogram,'notes':notes,'generated_at':timestamp(),'truncated':len(rows)>q['limit'] if q['mode']=='records' else any('groups.' in n for n in notes)}
