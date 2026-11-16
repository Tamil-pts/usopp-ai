from io import BytesIO
from types import SimpleNamespace
import uuid
import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import team_chat as chat

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(chat,'store',chat.ChatStore(tmp_path/'chat'))
    monkeypatch.setattr(chat,'team_directory',lambda:[])
    rows=[{'id':n,'username':f'Engineer {n}','designation':'PLC','active':n!=4,'approved':n!=5,'avatarUrl':None} for n in range(1,6)]
    monkeypatch.setattr(chat.accounts,'store',SimpleNamespace(list_users=lambda:rows))
    app=FastAPI();app.include_router(chat.router)
    @app.middleware('http')
    async def who(request,call_next):
        value=request.headers.get('who','1');request.state.user={'id':int(value),'username':'Engineer '+value,'role':'admin' if value=='1' else 'engineer','workspaceModules':request.headers.get('modules','workhub').split(','),'createdAt':0,'isDemo':request.headers.get('demo')=='1'} if value else None
        return await call_next(request)
    with TestClient(app) as c:yield c

def thread(c,user=2):
    r=c.post('/api/team-chat/threads',json={'user_id':user});assert r.status_code==200,r.text;return r.json()['id']

def send(c,key,body='Test message',files=None,who='1',client_id=None):
    return c.post(f'/api/team-chat/threads/{key}/messages',data={'body':body,'client_id':client_id or str(uuid.uuid4())},files=files,headers={'who':who})

def test_private_history_unread_receipts_pagination_and_idempotency(client):
    key=thread(client);assert thread(client)==key
    assert client.get('/api/team-chat/users').json()['users']==[{'id':n,'username':f'Engineer {n}','designation':'PLC','active':True,'approved':True,'avatarUrl':None} for n in (2,3)]
    token=str(uuid.uuid4());a=send(client,key,'Hello',client_id=token);assert a.status_code==200
    assert send(client,key,'Hello',client_id=token).json()['id']==a.json()['id']
    b=send(client,key,'Reply with emoji \U0001F44D',who='2');assert b.status_code==200
    assert client.get('/api/team-chat/threads').json()['unread']==1
    assert client.get('/api/team-chat/threads',headers={'who':'2'}).json()['unread']==1
    data=client.get(f'/api/team-chat/threads/{key}/messages?limit=1').json();assert data['has_more'] and data['messages'][0]['id']==b.json()['id']
    older=client.get(f'/api/team-chat/threads/{key}/messages?before={b.json()["id"]}').json();assert len(older['messages'])==1
    assert client.post(f'/api/team-chat/threads/{key}/read',json={'last_id':b.json()['id']}).status_code==200
    assert client.get('/api/team-chat/threads').json()['unread']==0
    assert client.get(f'/api/team-chat/threads/{key}/messages',headers={'who':'2'}).json()['peer_read_id']==b.json()['id']
    # Reopen the persisted database, not a process-only conversation cache.
    chat.store=chat.ChatStore(chat.store.root)
    assert len(client.get(f'/api/team-chat/threads/{key}/messages').json()['messages'])==2
    for suffix in ('/messages','/read'):
        r=client.get(f'/api/team-chat/threads/{key}'+suffix,headers={'who':'3'}) if suffix=='/messages' else client.post(f'/api/team-chat/threads/{key}'+suffix,json={'last_id':0},headers={'who':'3'})
        assert r.status_code==404
    assert send(client,key,'Intrusion',who='3').status_code==404
    other=thread(client,3);assert client.post(f'/api/team-chat/threads/{other}/read',json={'last_id':a.json()['id']}).status_code==400
    assert send(client,other,client_id=token).status_code==409

def test_private_attachments_and_failed_upload_cleanup(client):
    key=thread(client);raw=BytesIO();Image.new('RGB',(8,8),'green').save(raw,format='PNG')
    response=send(client,key,'image',files=[('files',('picture.png',raw.getvalue(),'image/png')),('files',('data.csv',b'tag,value\n1,2','text/csv'))]);assert response.status_code==200,response.text
    images=response.json()['attachments'];assert len(images)==2
    url='/api/team-chat/files/'+images[0]['id'];assert client.get(url+'?preview=true',headers={'who':'2'}).headers['content-type'].startswith('image/png')
    assert client.get(url,headers={'who':'3'}).status_code==404
    assert 'attachment' in client.get(url).headers['content-disposition']
    assert send(client,key,'',files=[('files',('bad.svg',b'<svg/>','image/svg+xml'))]).status_code==400
    assert send(client,key,'',files=[('files',('fake.png',b'not an image','image/png'))]).status_code==400
    assert send(client,key,'',files=[('files',('big.txt',b'x'*(20*1024*1024+1),'text/plain'))]).status_code==413
    assert len(list((chat.store.root/'files').iterdir()))==2
    assert len(client.get(f'/api/team-chat/threads/{key}/messages').json()['messages'])==1

@pytest.mark.parametrize('peer',[1,4,5,999,True,{},'2'])
def test_recipient_validation(client,peer):
    assert client.post('/api/team-chat/threads',json={'user_id':peer}).status_code==400

def test_personal_accounts_and_message_validation(client):
    assert client.get('/api/team-chat/threads',headers={'who':''}).status_code==401
    assert client.get('/api/team-chat/threads',headers={'demo':'1'}).status_code==403
    key=thread(client)
    assert send(client,key,'').status_code==400
    assert send(client,key,'x'*8001).status_code==400
    assert client.post(f'/api/team-chat/threads/{key}/read',json={'last_id':True}).status_code==400


def test_deleted_account_id_reuse_does_not_expose_previous_history(client):
    key=thread(client);assert send(client,key,'Private old history').status_code==200
    # An account deleted/recreated with the same numeric ID has a new identity.
    for person in chat.accounts.store.list_users():
        if person['id']==2:person['createdAt']=123456789
    assert client.get(f'/api/team-chat/threads/{key}/messages',headers={'who':'2'}).status_code==404
    assert client.get('/api/team-chat/threads',headers={'who':'2'}).json()['threads']==[]
    assert send(client,key,'New send to removed person').status_code==409
    replacement=thread(client);assert replacement!=key
    assert client.get(f'/api/team-chat/threads/{replacement}/messages',headers={'who':'2'}).json()['messages']==[]
