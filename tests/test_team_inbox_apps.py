import uuid
import pytest
from test_team_chat import client,thread,send
from backend.api import team_chat as chat,team_inbox_apps as apps
from backend.core import workhub,workhub_portfolio as portfolio

@pytest.fixture
def inbox(client,tmp_path,monkeypatch):
    client.app.include_router(apps.router)
    hub=workhub.WorkHub(tmp_path/'hub');monkeypatch.setattr(workhub,'store',hub);monkeypatch.setattr(portfolio,'hub',hub)
    return client

def post(c,key,kind,content,who='1',client_id=None):
    return c.post(f'/api/team-chat/threads/{key}/components',json={'kind':kind,'content':content,'client_id':client_id or uuid.uuid4().hex},headers={'who':who})

def test_praise_participant_recipient_and_immutable_recognition(inbox):
    c=inbox;key=thread(c);value={'title':'Great validation','recipient':2,'badge':'quality','body':'Thanks for checking the offsets.'}
    request=uuid.uuid4().hex;r=post(c,key,'praise',value,client_id=request);assert r.status_code==200,r.text
    assert post(c,key,'praise',value,client_id=request).json()['id']==r.json()['id']
    message=r.json()['id'];assert r.json()['component']['content']['recipient_name']=='Engineer 2'
    assert c.post(f'/api/team-chat/components/{message}',json={'version':1,'content':value}).status_code==409
    assert c.get(f'/api/team-chat/components/{message}',headers={'who':'3'}).status_code==404
    for recipient in (1,3,4,5,True):assert post(c,key,'praise',{**value,'recipient':recipient}).status_code==400
    assert c.get(f'/api/team-chat/threads/{key}/messages',headers={'who':'2'}).json()['messages'][0]['component']['kind']=='praise'

@pytest.mark.parametrize('kind,value',[
    ('note',{'title':'Meeting notes','body':'Review source 123'}),
    ('checklist',{'title':'Quality checks','items':[{'text':'Check offsets','done':False}]}),
    ('table',{'title':'Actions','columns':['Action','Owner'],'rows':[['Review','Engineer 2']]})])
def test_shared_components_version_conflict_and_persistent_history(inbox,kind,value):
    c=inbox;key=thread(c);r=post(c,key,kind,value);assert r.status_code==200,r.text;message=r.json()['id'];saved=r.json()['component']['content']
    changed={**saved,'title':'Reviewed together'}
    r=c.post(f'/api/team-chat/components/{message}',json={'version':1,'content':changed},headers={'who':'2'});assert r.status_code==200,r.text
    assert r.json()['component']['version']==2
    assert c.post(f'/api/team-chat/components/{message}',json={'version':1,'content':saved}).status_code==409
    chat.store=chat.ChatStore(chat.store.root)
    assert c.get(f'/api/team-chat/components/{message}').json()['component']['content']['title']=='Reviewed together'
    history=c.get(f'/api/team-chat/components/{message}/history').json()['items'];assert [r['version'] for r in history]==[2,1]
    assert history[0]['editor_name']=='Engineer 2' and history[1]['content']['title']==saved['title']
    assert c.get(f'/api/team-chat/components/{message}/history',headers={'who':'3'}).status_code==404
    assert c.post(f'/api/team-chat/components/{message}',json={'version':2,'content':changed},headers={'who':'3'}).status_code==404

def test_shared_validation_and_membership_revocation(inbox,monkeypatch):
    c=inbox;teams=[{'id':'t1','name':'Engineering','users':[1,2]}];monkeypatch.setattr(chat,'team_directory',lambda:teams)
    key=c.get('/api/team-chat/threads').json()['threads'][0]['id'];r=post(c,key,'note',{'title':'Private team note','body':'Saved'});message=r.json()['id']
    teams[0]['users']=[1,3]
    assert c.get(f'/api/team-chat/components/{message}',headers={'who':'2'}).status_code==404
    assert c.get(f'/api/team-chat/components/{message}/history',headers={'who':'2'}).status_code==404
    for kind,value in [('table',{'title':'Bad','columns':['One'],'rows':[['a','b']]}),('checklist',{'title':'Bad','items':[{'text':'x','done':1}]}),('note',{'title':'Bad','body':'x'*16001}),('unsupported',{'title':'Bad'})]:assert post(c,key,kind,value).status_code==400
    assert post(c,key,'checklist',{'title':'Bad','items':[{'id':'same','text':'a'},{'id':'same','text':'b'}]}).status_code==400

def test_workhub_inbox_only_shows_assigned_review_and_work(inbox):
    c=inbox;user={'id':1,'username':'Engineer 1','role':'admin'}
    project=workhub.store.create(user,{'title':'Assigned project','quality_id':2,'approver_id':3})
    with workhub.store.db(True) as db:db.execute("UPDATE items SET stage='quality' WHERE id=?",(project['id'],))
    mine=c.get('/api/team-chat/workhub-inbox?view=approvals',headers={'who':'2'});assert mine.status_code==200,mine.text
    assert mine.json()['total']==1 and mine.json()['items'][0]['saved_version']==1
    assert c.get('/api/team-chat/workhub-inbox?view=approvals',headers={'who':'1'}).json()['total']==0
    assert c.get('/api/team-chat/workhub-inbox?view=workflows',headers={'who':'3'}).json()['items'][0]['id']==project['id']
    assert c.get('/api/team-chat/workhub-inbox?view=workflows',headers={'who':'4'}).json()['total']==0
    notifications=c.get('/api/team-chat/workhub-inbox?view=updates').json()['items'];assert all(r['recipient_id']==1 for r in notifications)
    assert c.get('/api/team-chat/workhub-inbox?view=invalid').status_code==400
    assert c.get('/api/team-chat/workhub-inbox?view=approvals&page_size=51').status_code==422
    assert c.get('/api/team-chat/workhub-inbox?view=approvals',headers={'who':'2','modules':''}).status_code==403

def test_workhub_document_approval_displays_saved_revision(inbox,monkeypatch):
    c=inbox;hub=workhub.store;hub.initialize();doc=uuid.uuid4().hex;revision=uuid.uuid4().hex
    with hub.db(True) as db:
        db.execute('CREATE TABLE pi_documents(id TEXT PRIMARY KEY,current_revision TEXT)');db.execute('INSERT INTO pi_documents VALUES(?,?)',(doc,revision))
    monkeypatch.setattr(portfolio,'snapshot',lambda *a,**k:{'approvals':[{'id':'document:'+doc,'project_id':'scope','kind':'document','can_review':True}]})
    r=c.get('/api/team-chat/workhub-inbox?view=approvals');assert r.status_code==200,r.text
    assert r.json()['items'][0]['saved_revision']==revision
