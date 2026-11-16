import base64,hmac,hashlib,json,time,zipfile
from io import BytesIO
import pytest
from test_team_chat import client,thread,send
from backend.api import team_chat as chat,team_meetings as meetings
from backend.core import workhub
REAL_DIRECTORY=chat.team_directory

@pytest.fixture
def extended(client,tmp_path,monkeypatch):
    client.app.include_router(meetings.router)
    monkeypatch.setattr(workhub,'store',workhub.WorkHub(tmp_path/'hub'))
    return client

def group(c):
    r=c.post('/api/team-chat/groups',json={'name':'PLC Team','user_ids':[2,3]});assert r.status_code==200,r.text;return r.json()['id']

def schedule(c,key,**patch):
    value={'title':'Review PLC','start':time.time()+600,'end':time.time()+4200,'timezone':'Asia/Kolkata','agenda':'Review evidence'};value.update(patch)
    return c.post('/api/team-chat/threads/'+key+'/meetings',json=value)

def test_zip_and_groups_keep_direct_history(extended):
    c=extended;direct=thread(c);assert send(c,direct,'Keep direct history').status_code==200
    key=group(c);buf=BytesIO()
    with zipfile.ZipFile(buf,'w') as z:z.writestr('Main.st','PROGRAM _CYCLIC\nEND_PROGRAM')
    r=send(c,key,'PLC source',files=[('files',('source.zip',buf.getvalue(),'application/zip'))]);assert r.status_code==200,r.text
    attachment=r.json()['attachments'][0]['id']
    for who in ('1','2','3'):assert c.get('/api/team-chat/files/'+attachment,headers={'who':who}).content==buf.getvalue()
    assert c.get('/api/team-chat/files/'+attachment,headers={'who':'4'}).status_code==404
    assert send(c,key,'bad',files=[('files',('bad.zip',b'not zip','application/zip'))]).status_code==400
    assert c.get(f'/api/team-chat/threads/{direct}/messages').json()['messages'][0]['body']=='Keep direct history'

def test_default_team_group_tracks_membership_and_revokes_files(extended,monkeypatch):
    c=extended;teams=[{'id':'team-one','name':'Engineering','users':[1,2]}];monkeypatch.setattr(chat,'team_directory',lambda:teams)
    data=c.get('/api/team-chat/threads').json();g=next(t for t in data['threads'] if t['kind']=='team');key=g['id']
    assert g['peer']['username']=='Engineering' and len(g['members'])==2
    assert next(t for t in c.get('/api/team-chat/threads').json()['threads'] if t['kind']=='team')['id']==key
    sent=send(c,key,'team',files=[('files',('note.txt',b'private','text/plain'))]).json();file=sent['attachments'][0]['id']
    teams[0]['users']=[1,3]
    assert c.get('/api/team-chat/files/'+file,headers={'who':'2'}).status_code==404
    assert c.get('/api/team-chat/files/'+file,headers={'who':'3'}).status_code==200
    teams.clear();assert c.get('/api/team-chat/files/'+file).status_code==404

def test_meeting_invitation_rsvp_calendar_and_room_scoped_token(extended,monkeypatch):
    c=extended;key=group(c);r=schedule(c,key);assert r.status_code==200,r.text;meeting=r.json()['id']
    assert len(c.get('/api/team-chat/meetings',headers={'who':'2'}).json()['meetings'])==1
    assert c.post(f'/api/team-chat/meetings/{meeting}/response',json={'response':'accepted'},headers={'who':'2'}).status_code==200
    calendar=c.get(f'/api/team-chat/meetings/{meeting}/calendar.ics');assert b'BEGIN:VEVENT' in calendar.content and b'TRIGGER:-PT10M' in calendar.content
    assert c.get(f'/api/team-chat/meetings/{meeting}/calendar.ics',headers={'who':'4'}).status_code==404
    assert c.post(f'/api/team-chat/meetings/{meeting}/join').status_code==503
    monkeypatch.setenv('USOPP_MEETING_URL','https://meet.factory.local');monkeypatch.setenv('USOPP_MEETING_JWT_SECRET','x'*40)
    value=c.post(f'/api/team-chat/meetings/{meeting}/join',headers={'who':'2'}).json();token=value['url'].split('jwt=')[1];header,payload,signature=token.split('.')
    data=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
    assert data['room']=='usopp'+meeting and data['exp']-data['iat']==900
    assert hmac.compare_digest(base64.urlsafe_b64decode(signature+'='*(-len(signature)%4)),hmac.new(b'x'*40,(header+'.'+payload).encode(),hashlib.sha256).digest())
    assert c.post(f'/api/team-chat/meetings/{meeting}/cancel',headers={'who':'2'}).status_code==403
    assert c.post(f'/api/team-chat/meetings/{meeting}/cancel').status_code==200
    assert c.post(f'/api/team-chat/meetings/{meeting}/join').status_code==409

def test_recording_download_participant_only_and_validation(extended):
    c=extended;key=group(c);meeting=schedule(c,key).json()['id'];payload=b'\x1aE\xdf\xa3'+b'fixture'
    assert c.post(f'/api/team-chat/meetings/{meeting}/recordings',files={'file':('session.webm',payload)},headers={'who':'2'}).status_code==403
    assert c.post(f'/api/team-chat/meetings/{meeting}/recordings',files={'file':('bad.webm',b'bad')}).status_code==400
    r=c.post(f'/api/team-chat/meetings/{meeting}/recordings',files={'file':('session.webm',payload)});assert r.status_code==200,r.text
    assert c.get('/api/team-chat/files/'+r.json()['id'],headers={'who':'2'}).content==payload
    assert c.get('/api/team-chat/files/'+r.json()['id'],headers={'who':'4'}).status_code==404

def test_message_creates_work_using_existing_workhub_permissions(extended):
    c=extended;key=thread(c);msg=send(c,key,'Engineering responsibility').json()['id'];url=f'/api/team-chat/threads/{key}/messages/{msg}/work-item'
    r=c.post(url,json={'kind':'project','title':'Chat project'});assert r.status_code==200,r.text;p=r.json()['project']
    r=c.post(url,json={'kind':'task','project_id':p,'title':'Task from message'});assert r.status_code==200,r.text
    options=c.get('/api/team-chat/work-options').json();assert options['projects'][0]['tasks'][0]['id']==r.json()['item']
    assert c.post(url,json={'kind':'task','project_id':p,'title':'Not member'},headers={'who':'3'}).status_code==404
    linked=c.post(f'/api/team-chat/threads/{key}/messages',data={'body':'Related task','client_id':'related-task-123','project_id':p,'item_id':r.json()['item']});assert linked.status_code==200,linked.text
    assert linked.json()['work_link']['project']==p

def test_invalid_dates_and_timezone(extended):
    key=thread(extended)
    for patch in ({'start':True},{'end':0},{'timezone':'not a zone'},{'end':time.time()+100000}):assert schedule(extended,key,**patch).status_code==400

def test_real_team_directory_blocks_reused_account_membership(extended,monkeypatch):
    from backend.core import workhub_organization as org
    from backend.core.workhub import timestamp
    monkeypatch.setattr(org,'hub',workhub.store);org.initialize()
    key='a'*32
    with workhub.store.db(True) as db:
        db.execute('INSERT INTO wh_org_units VALUES(?,?,?,?,?,?,?)',(key,'team','Actual Team','',1,1,timestamp()))
        for user in (1,2):
            db.execute('INSERT INTO wh_org_profiles(user_id,updated_at) VALUES(?,?)',(user,timestamp()))
            db.execute('INSERT INTO wh_org_members VALUES(?,?,?)',(key,user,'member'))
    monkeypatch.setattr(chat,'team_directory',REAL_DIRECTORY)
    groups=extended.get('/api/team-chat/threads').json()['threads'];thread=next(t['id'] for t in groups if t['kind']=='team')
    assert extended.get('/api/team-chat/threads/'+thread+'/messages',headers={'who':'2'}).status_code==200
    for user in chat.accounts.store.list_users():
        if user['id']==2:user['createdAt']=time.time()+1
    assert extended.get('/api/team-chat/threads/'+thread+'/messages',headers={'who':'2'}).status_code==404
