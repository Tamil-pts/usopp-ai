import csv,io
from datetime import date,timedelta
from test_team_inbox_apps import inbox,client
from backend.core import workhub

ADMIN={'id':1,'username':'Engineer 1','role':'admin'}
ENGINEER={'id':2,'username':'Engineer 2','role':'engineer'}
REVIEWER={'id':3,'username':'Engineer 3','role':'engineer'}

def project():
 return workhub.store.create(ADMIN,{'title':'Inbox delivery','owner_id':2,'quality_id':3})

def create(c,p,owner=2,who='1'):
 return c.post('/api/team-chat/work-center/tasks',json={'project_id':p['id'],'title':'Verify saved report','description':'Review actual test evidence','owner_id':owner,'planned_hours':2},headers={'who':who})

def test_task_creation_self_and_teammate_permissions_notifications(inbox):
 c=inbox;p=project();r=create(c,p);assert r.status_code==200,r.text
 task=r.json();assert task['owner_id']==2 and task['project_id']==p['id']
 own=c.get('/api/team-chat/work-center/tasks?view=mine',headers={'who':'2'}).json()
 assert task['id'] in {r['id'] for r in own['items']}
 assert c.get('/api/team-chat/work-center/tasks?view=tasks',headers={'who':'1'}).json()['total']==1
 assert c.get('/api/team-chat/work-center/tasks?view=tasks',headers={'who':'3'}).json()['total']==0
 assert create(c,p,2,'2').status_code==200 # Assigned project owner can assign self.
 assert create(c,p,3,'2').status_code==200 # Same existing manager permission for another user.
 assert create(c,p,2,'3').status_code==403 # Reviewer cannot change the plan.
 assert create(c,p,4).status_code==400 # Disabled assignee.
 assert c.post('/api/team-chat/work-center/tasks',json={'title':'No parent'}).status_code==400
 notes=workhub.store.notifications(ENGINEER)['items'];assert any('Work assigned' in r['title'] for r in notes)
 options=c.get('/api/team-chat/work-center/options',headers={'who':'3'}).json()
 assert options['projects'][0]['can_create'] is False
 assert all(u['id'] not in (4,5) for u in options['users'])


def test_timesheet_private_approved_hours_and_full_csv(inbox):
 c=inbox;p=project();task=create(c,p).json();day=date.today().isoformat()
 def log(minutes,body,who='2',extra=None):
  return c.post('/api/team-chat/work-center/time',json={'item_id':task['id'],'work_date':day,'minutes':minutes,'body':body,**(extra or {})},headers={'who':who})
 a=log(90,'=Evidence recorded');assert a.status_code==200,a.text
 b=log(30,'Reviewed source code');assert b.status_code==200
 workhub.store.time_review(REVIEWER,a.json()['id'],{'status':'approved'})
 rows=c.get('/api/team-chat/work-center/timesheet',headers={'who':'2'}).json()
 assert rows['totals']=={'logged_minutes':120,'approved_minutes':90,'pending_minutes':30}
 assert rows['total']==2 and all(r['author_id']==2 for r in rows['items'])
 assert c.get('/api/team-chat/work-center/timesheet',headers={'who':'1'}).json()['total']==0
 out=c.get('/api/team-chat/work-center/timesheet?export=csv',headers={'who':'2'})
 values=list(csv.DictReader(io.StringIO(out.text.lstrip('\ufeff'))));assert len(values)==2
 assert any(r['What work was done'].startswith("'=") for r in values)
 assert c.get('/api/team-chat/work-center/timesheet?date_from=2000-01-01&date_to=2000-01-02',headers={'who':'2'}).json()['total']==0
 assert c.get('/api/team-chat/work-center/timesheet?date_from=2026-02-30',headers={'who':'2'}).status_code==400
 assert c.get('/api/team-chat/work-center/timesheet?date_from=2026-02-02&date_to=2026-02-01',headers={'who':'2'}).status_code==400
 assert log(10,'Cannot forge author',extra={'author_id':3}).status_code==200
 assert c.get('/api/team-chat/work-center/timesheet',headers={'who':'3'}).json()['total']==0
 assert log(10,'Unassigned user','3').status_code==200 # Project reviewer can contribute under existing permission.
 other=workhub.store.create(REVIEWER,{'title':'Other project'})
 denied=c.post('/api/team-chat/work-center/time',json={'item_id':other['id'],'minutes':30,'body':'No membership'},headers={'who':'2'})
 assert denied.status_code==403
 for minutes in (0,-1,1441,1.5):assert log(minutes,'Bad').status_code==400
 assert log(10,'Future',extra={'work_date':(date.today()+timedelta(days=1)).isoformat()}).status_code==400
 assert log(10,'').status_code==400


def test_work_center_module_and_demo_denials(inbox):
 c=inbox
 for path in ('options','tasks','timesheet'):
  assert c.get('/api/team-chat/work-center/'+path,headers={'who':'2','modules':''}).status_code==403
  assert c.get('/api/team-chat/work-center/'+path,headers={'demo':'1'}).status_code==403


def test_export_covers_all_pages_and_matches_filtered_totals(inbox):
 c=inbox;p=project();today=date.today().isoformat()
 for i in range(23):
  response=c.post('/api/team-chat/work-center/time',json={'item_id':p['id'],'minutes':1,'body':'Reviewed item '+str(i),'work_date':today},headers={'who':'2'})
  assert response.status_code==200,response.text
 values=c.get('/api/team-chat/work-center/timesheet?page=2',headers={'who':'2'}).json()
 assert len(values['items'])==3 and values['total']==23 and values['totals']['logged_minutes']==23
 export=c.get('/api/team-chat/work-center/timesheet?page=2&export=csv&project='+p['id'],headers={'who':'2'})
 assert len(list(csv.DictReader(io.StringIO(export.text.lstrip('\ufeff')))))==23


def test_combined_daily_updates_requests_and_project_feed(inbox):
 c=inbox;p=project();task=create(c,p).json();day=date.today().isoformat()
 payload={'item_id':task['id'],'work_date':day,'minutes':0,'body':'Need help checking offsets','work_status':'blocked','request_kind':'support','mention_ids':[3]}
 response=c.post('/api/team-chat/work-center/updates',json=payload,headers={'who':'2'})
 assert response.status_code==200,response.text
 update=response.json()['id']
 old=c.get('/api/team-chat/work-center/timesheet',headers={'who':'2'}).json();assert old['total']==0
 feed=c.get('/api/team-chat/work-center/timesheet?include_updates=true',headers={'who':'2'}).json()
 assert feed['total']==1 and feed['totals']['logged_minutes']==0
 assert feed['items'][0]['work_status']=='blocked' and feed['items'][0]['mention_names']==['Engineer 3']
 actions=c.get('/api/team-chat/work-center/requests',headers={'who':'3'}).json()['items']
 assert len(actions)==1 and actions[0]['update_id']==update
 assert c.get('/api/team-chat/work-center/requests',headers={'who':'1'}).json()['items']==[]
 action=actions[0]['id']
 assert c.post('/api/team-chat/work-center/requests/'+action+'/resolve',headers={'who':'2'}).status_code==404
 assert c.post('/api/team-chat/work-center/requests/'+action+'/resolve',headers={'who':'3'}).status_code==200
 assert c.get('/api/team-chat/work-center/requests',headers={'who':'3'}).json()['items']==[]
 # A completed daily status is informational, never an approval/workflow transition.
 response=c.post('/api/team-chat/work-center/updates',json={**payload,'minutes':75,'work_status':'completed','request_kind':'progress','mention_ids':[]},headers={'who':'2'})
 assert response.status_code==200,response.text
 with workhub.store.db() as db:
  saved=workhub.store.item(db,task['id']);assert saved['stage'] not in {'released','ready_release'}
  entry=db.execute('SELECT * FROM updates WHERE id=?',(response.json()['id'],)).fetchone();assert entry['time_status']=='submitted'
 workhub.store.time_review(REVIEWER,response.json()['id'],{'status':'approved'})
 feed=c.get('/api/team-chat/work-center/timesheet?include_updates=true&scope=project&project='+p['id'],headers={'who':'3'}).json()
 assert feed['total']==2 and feed['totals']['approved_minutes']==75
 export=c.get('/api/team-chat/work-center/timesheet?include_updates=true&scope=project&project='+p['id']+'&export=csv',headers={'who':'3'})
 rows=list(csv.DictReader(io.StringIO(export.text.lstrip('\ufeff'))));assert len(rows)==2
 assert any(r['Mentions']=='Engineer 3' and r['Work status']=='blocked' for r in rows)
 outsider=workhub.store.create(REVIEWER,{'title':'Unrelated private project'})
 assert c.get('/api/team-chat/work-center/timesheet?scope=project&project='+outsider['id'],headers={'who':'2'}).status_code==403
 assert c.get('/api/team-chat/work-center/timesheet?scope=project',headers={'who':'2'}).status_code==400
 for change in ({'mention_ids':[4]},{'mention_ids':[True]},{'mention_ids':[]},{'work_status':'fake'},{'request_kind':'approve_everything'}):
  assert c.post('/api/team-chat/work-center/updates',json={**payload,**change},headers={'who':'2'}).status_code==400


def test_assigned_work_separate_from_personal_responsibilities(inbox):
 c=inbox;p=project();task=create(c,p,owner=3).json()
 mine=c.get('/api/team-chat/work-center/tasks?view=mine',headers={'who':'2'}).json()
 assigned=c.get('/api/team-chat/work-center/tasks?view=assigned',headers={'who':'2'}).json()
 assert task['id'] not in {r['id'] for r in mine['items']}
 assert task['id'] in {r['id'] for r in assigned['items']}
 assert c.get('/api/team-chat/work-center/tasks?view=mine',headers={'who':'3'}).json()['total']==1
 assert c.get('/api/team-chat/work-center/tasks?view=assigned',headers={'who':'3'}).json()['total']==0
