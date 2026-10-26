"""User-authorized delivery extensions. In-app workflow records remain authoritative."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlparse, urlencode
import requests
from fastapi import HTTPException
from .workhub import store, timestamp, text, identity

STOP=threading.Event();WORKER=None;GUARD=threading.Lock();MAIL_LOCK=threading.RLock();KEY_LOCK=threading.Lock()
GRAPH_SCOPES=['User.Read','Mail.Send']

def cipher():
    from cryptography.fernet import Fernet
    store.initialize();path=store.root/'connections.key'
    with KEY_LOCK:
        if not path.exists():
            try:
                descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(descriptor,'wb') as output:output.write(Fernet.generate_key())
            except FileExistsError:pass
        return Fernet(path.read_bytes())
def seal(value):return cipher().encrypt(value.encode()).decode() if value else ''
def unseal(value):return cipher().decrypt(value.encode()).decode() if value else ''
def pref(db,user_id):
    db.execute('INSERT OR IGNORE INTO preferences(user_id) VALUES(?)',(user_id,))
    return dict(db.execute('SELECT * FROM preferences WHERE user_id=?',(user_id,)).fetchone())
def config():
    with store.db() as db:return {row['key']:row['value'] for row in db.execute('SELECT * FROM config')}
def public_config(user):
    cfg=config()
    return {'microsoftReady':bool(cfg.get('tenant_id') and cfg.get('client_id') and cfg.get('client_secret') and cfg.get('public_url') and oauth_origin(cfg['public_url'])),
            'public_url':cfg.get('public_url',''),'teams_chat_url':cfg.get('teams_chat_url',''),**({key:cfg.get(key,'') for key in ('tenant_id','client_id')} if user['role']=='admin' else {}),
            'hasClientSecret':bool(cfg.get('client_secret'))}

def oauth_origin(value):
    parsed=urlparse(value)
    return parsed.scheme=='https' or parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1'}

def app_origin(value):
    value=text(value,500).rstrip('/')
    try:
        parsed=urlparse(value);port=parsed.port
        valid=parsed.scheme in {'http','https'} and parsed.hostname and not (parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path.strip('/'))
    except ValueError:valid=False
    if value and (not valid or any(char.isspace() or ord(char)<32 for char in value)):
        raise HTTPException(400,'Enter the WorkHub application address, for example http://192.168.1.10:8200 or https://usop.company.com.')
    return value

def chat_url(value):
    value=text(value,5000)
    if not value:return ''
    try:
        parsed=urlparse(value)
        valid=parsed.scheme=='https' and parsed.hostname in {'teams.microsoft.com','teams.cloud.microsoft','teams.live.com'} and not (parsed.username or parsed.password) and parsed.port in (None,443)
    except ValueError:valid=False
    if not valid or any(char.isspace() or ord(char)<32 for char in value):
        raise HTTPException(400,'Paste an HTTPS Teams group chat or message link copied from Teams. A workflow URL belongs in the optional automatic-delivery settings.')
    return value
def save_config(user,payload):
    if user.get('role')!='admin':raise HTTPException(403,'Only Admin can configure the company Microsoft application.')
    cfg=config();tenant=text(payload.get('tenant_id',''),180);client=text(payload.get('client_id',''),100)
    if tenant and not re.fullmatch(r'[A-Za-z0-9.-]+',tenant):raise HTTPException(400,'Enter the tenant ID or verified tenant domain.')
    if client and not re.fullmatch(r'[0-9a-fA-F-]{36}',client):raise HTTPException(400,'Enter the Microsoft application client ID.')
    public=text(payload.get('public_url',''),500).rstrip('/');url=urlparse(public)
    if public and (url.scheme not in {'http','https'} or not url.hostname or url.username or url.password or url.query or url.fragment or url.path.strip('/')):
        raise HTTPException(400,'Enter the application origin, for example https://usop.company.com.')
    if public and url.scheme!='https' and url.hostname not in {'localhost','127.0.0.1'}:
        raise HTTPException(400,'Microsoft sign-in requires HTTPS for a company server address. Localhost HTTP is supported for local setup.')
    changes={'tenant_id':tenant,'client_id':client,'public_url':public}
    if payload.get('client_secret'):changes['client_secret']=seal(text(payload['client_secret'],4000,True))
    with MAIL_LOCK,store.db(True) as db:
        changed_app=any(cfg.get(key,'')!=changes[key] for key in ('tenant_id','client_id','public_url'))
        for key,value in changes.items():db.execute('INSERT INTO config VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
        if changed_app:
            db.execute("UPDATE preferences SET mail_cache='',mail_address='',email_enabled=0")
            db.execute('DELETE FROM oauth_states')
    return public_config(user)
def own_settings(user):
    with store.db(True) as db:row=pref(db,user['id'])
    return {'contact_email':row['contact_email'],'email_enabled':bool(row['email_enabled']),
            'mail_connected':bool(row['mail_cache']),'mail_address':row['mail_address'],
            'teams_enabled':bool(row['teams_enabled']),'teams_connected':bool(row['teams_secret']),
            'teams_mode':row['teams_mode'],'teams_chat_url':row['teams_chat_url'],
            'configuration':public_config(user)}
def workflow_url(value):
    parsed=urlparse(value);host=(parsed.hostname or '').lower()
    allowed=any(host.endswith('.'+suffix) for suffix in ('logic.azure.com','api.powerplatform.com','powerautomate.com'))
    if parsed.scheme!='https' or not allowed or parsed.username or parsed.password or parsed.port not in (None,443):
        raise HTTPException(400,'Paste an HTTPS Microsoft Teams / Power Automate workflow URL.')
    return value
def save_settings(user,payload):
    store.actor(user);company={}
    if 'shared_teams_chat_url' in payload or 'public_url' in payload:
        if user['role']!='admin':raise HTTPException(403,'Only Admin can change the shared group or WorkHub address.')
        if 'shared_teams_chat_url' in payload:company['teams_chat_url']=chat_url(payload['shared_teams_chat_url'])
        if 'public_url' in payload:company['public_url']=app_origin(payload['public_url'])
    with MAIL_LOCK,store.db(True) as db:
        row=pref(db,user['id']);url=text(payload.get('teams_url',''),5000)
        email=text(payload.get('contact_email',row['contact_email']),254)
        if email and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email):raise HTTPException(400,'Enter a valid contact email address.')
        mode=payload.get('teams_mode',row['teams_mode'])
        if mode not in {'chat','workflow'}:raise HTTPException(400,'Choose group chat sharing or an automatic workflow.')
        personal_chat=chat_url(payload.get('teams_chat_url',row['teams_chat_url']))
        if url and payload.get('disconnect_teams'):raise HTTPException(400,'Choose either a new workflow URL or removal of the saved workflow.')
        secret=seal(workflow_url(url)) if url else row['teams_secret']
        if payload.get('disconnect_teams'):secret=''
        enabled=bool(payload.get('email_enabled',row['email_enabled']))
        if enabled and not row['mail_cache']:raise HTTPException(400,'Connect your own Microsoft account before enabling email delivery.')
        teams_enabled=mode=='workflow' and bool(payload.get('teams_enabled',row['teams_enabled']))
        if teams_enabled and not secret:raise HTTPException(400,'Save a Teams workflow URL before enabling automatic delivery, or choose group chat sharing.')
        previous=dict(db.execute('SELECT key,value FROM config'))
        address_changed='public_url' in company and company['public_url']!=previous.get('public_url','')
        if address_changed:
            db.execute("UPDATE preferences SET mail_cache='',mail_address='',email_enabled=0")
            db.execute('DELETE FROM oauth_states');enabled=False
        for key,value in company.items():db.execute('INSERT INTO config VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
        db.execute('UPDATE preferences SET contact_email=?,email_enabled=?,teams_secret=?,teams_enabled=?,teams_mode=?,teams_chat_url=? WHERE user_id=?',
                   (email,int(enabled),secret,int(teams_enabled),mode,personal_chat,user['id']))
        if mode=='chat':
            db.execute("UPDATE outbox SET status='manual',detail='Share using the Teams chat link; no automatic message was sent.' WHERE channel='teams' AND status IN ('pending','failed','waiting_connection') AND notification_id IN (SELECT id FROM notifications WHERE recipient_id=?)",(user['id'],))
    return own_settings(user)

def prepare_share(user,key,origin,notification_id=None):
    """Prepare text for an explicit user action; this never calls Teams or sends."""
    store.actor(user);cfg=config()
    with store.db(True) as db:
        item=store.item(db,key);project=store.item(db,item['project_id']);row=pref(db,user['id'])
        users={person['id']:person['username'] for person in store.users()}
        public=store.public(item)
        lines=['usop.ai WorkHub','Project: '+project['title']]
        if item['type']=='task':lines.append('Task: '+item['title'])
        if notification_id:
            notification=db.execute('SELECT * FROM notifications WHERE id=? AND recipient_id=? AND item_id=?',(notification_id,user['id'],key)).fetchone()
            if not notification:raise HTTPException(404,'Notification not found.')
            lines.extend([notification['title'],notification['body'],'Recorded: '+notification['created_at']])
        else:
            lines.extend(['Stage: '+public['stage_label'],'Current responsibility: '+users.get(public['current_user_id'],'Account unavailable')])
            if item['due_date']:lines.append('Due: '+item['due_date'])
            update=db.execute('SELECT body FROM updates WHERE item_id=? ORDER BY created_at DESC LIMIT 1',(key,)).fetchone()
            if update:lines.append('Latest update: '+update['body'][:1500])
        if item['review_revision'] and not notification_id:
            revision=db.execute('SELECT label FROM revisions WHERE id=?',(item['review_revision'],)).fetchone()
            if revision:lines.append('Submitted revision: '+revision['label'])
    address=(cfg.get('public_url') or origin).rstrip('/')
    link=address+'/?'+urlencode({'workhubProject':item['project_id'],'workhubItem':item['id']})
    lines.extend(['Review and record the decision in WorkHub: '+link])
    effective=row['teams_chat_url'] or cfg.get('teams_chat_url','')
    return {'message':'\n'.join(lines),'chatUrl':chat_url(effective),'projectUrl':link,
            'localAddress':urlparse(address).hostname in {'localhost','127.0.0.1','::1'},'automatic':False}
def msal_app(cache=None):
    try:import msal
    except ImportError:raise HTTPException(503,'Install the updated application requirements to enable Microsoft sign-in.') from None
    cfg=config()
    if not all(cfg.get(key) for key in ('tenant_id','client_id','client_secret','public_url')):
        raise HTTPException(409,'Ask Admin to configure the company Microsoft application and HTTPS application address first.')
    if not oauth_origin(cfg['public_url']):raise HTTPException(409,'Microsoft sign-in needs an HTTPS company address. Group chat sharing can use your existing office address.')
    class BoundedSession(requests.Session):
        def request(self,*args,**kwargs):
            if kwargs.get('timeout') is None:kwargs['timeout']=20
            return super().request(*args,**kwargs)
    return msal.ConfidentialClientApplication(cfg['client_id'],authority='https://login.microsoftonline.com/'+cfg['tenant_id'],
            client_credential=unseal(cfg['client_secret']),token_cache=cache,http_client=BoundedSession()),cfg
def connect(user):
    store.actor(user);app,cfg=msal_app()
    flow=app.initiate_auth_code_flow(GRAPH_SCOPES,redirect_uri=cfg['public_url']+'/api/workhub/connections/microsoft/callback',prompt='select_account')
    if not flow.get('auth_uri') or not flow.get('state'):raise HTTPException(502,'Microsoft sign-in could not be started.')
    with store.db(True) as db:
        db.execute('DELETE FROM oauth_states WHERE expires<?',(time.time(),))
        db.execute('INSERT INTO oauth_states VALUES(?,?,?,?)',(flow['state'],user['id'],seal(json.dumps(flow)),time.time()+600))
    return flow['auth_uri']
def callback(user,params):
    import msal
    state=params.get('state','')
    with store.db(True) as db:
        row=db.execute('SELECT * FROM oauth_states WHERE state=? AND user_id=? AND expires>?',(state,user['id'],time.time())).fetchone()
        if not row:raise HTTPException(400,'Microsoft connection expired. Start the connection again from WorkHub.')
        db.execute('DELETE FROM oauth_states WHERE state=?',(state,))
    cache=msal.SerializableTokenCache();app,_=msal_app(cache)
    try:token=app.acquire_token_by_auth_code_flow(json.loads(unseal(row['flow'])),params)
    except ValueError:raise HTTPException(400,'Microsoft connection state could not be verified.') from None
    if not token.get('access_token'):raise HTTPException(400,'Microsoft authorization was not completed. Check company consent settings and try again.')
    response=requests.get('https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName',headers={'Authorization':'Bearer '+token['access_token']},timeout=20,allow_redirects=False)
    if response.status_code!=200:raise HTTPException(502,'Microsoft account details could not be confirmed.')
    profile=response.json();address=profile.get('mail') or profile.get('userPrincipalName') or ''
    if not address:raise HTTPException(400,'This Microsoft account has no usable email address.')
    with MAIL_LOCK,store.db(True) as db:
        pref(db,user['id'])
        # Consent connects the account; the user separately enables automatic sending.
        db.execute('UPDATE preferences SET mail_cache=?,mail_address=?,contact_email=?,email_enabled=0 WHERE user_id=?',
                   (seal(cache.serialize()),address,address,user['id']))
    return address
def disconnect(user):
    with MAIL_LOCK,store.db(True) as db:
        pref(db,user['id']);db.execute("UPDATE preferences SET mail_cache='',mail_address='',email_enabled=0 WHERE user_id=?",(user['id'],))
    return own_settings(user)
def email_token(sender):
    import msal
    with MAIL_LOCK:
        with store.db(True) as db:row=pref(db,sender)
        if not row['email_enabled'] or not row['mail_cache']:return None,'Sender has not enabled their connected email account.'
        cache=msal.SerializableTokenCache();cache.deserialize(unseal(row['mail_cache']));app,_=msal_app(cache)
        available=app.get_accounts()
        token=app.acquire_token_silent(GRAPH_SCOPES,account=available[0]) if available else None
        if cache.has_state_changed:
            with store.db(True) as db:db.execute('UPDATE preferences SET mail_cache=? WHERE user_id=?',(seal(cache.serialize()),sender))
        if not token or not token.get('access_token'):return None,'Sender must reconnect their Microsoft email account.'
        return token['access_token'],''
def deliver(row):
    with store.db(True) as db:
        recipient=pref(db,row['recipient_id']);sender=pref(db,row['sender_id'])
    if row['channel']=='teams' and recipient['teams_mode']=='chat':return 'manual','Share using the Teams chat link; no automatic message was sent.'
    if row['channel']=='email' and not sender['email_enabled']:return 'disabled','The sender has not enabled automatic email.'
    cfg=config();link=(cfg.get('public_url') or '').rstrip('/')+'/?workhubProject='+row['project_id']+'&workhubItem='+row['item_id']
    if not cfg.get('public_url'):return 'waiting_connection','Admin must configure the application address.'
    if not any(user['id']==row['sender_id'] and user['active'] for user in store.users()):return 'waiting_connection','The sender account is disabled or unavailable.'
    if not any(user['id']==row['recipient_id'] and user['active'] for user in store.users()):return 'waiting_connection','The recipient account is disabled or unavailable.'
    if row['channel']=='email':
        if not cfg.get('public_url'):return 'waiting_connection','Admin must configure the application address.'
        if not recipient['contact_email']:return 'waiting_connection','Recipient has not saved a contact email.'
        token,notice=email_token(row['sender_id'])
        if not token:return 'waiting_connection',notice
        response=requests.post('https://graph.microsoft.com/v1.0/me/sendMail',headers={'Authorization':'Bearer '+token},
            json={'message':{'subject':row['title'],'body':{'contentType':'Text','content':row['body']+'\n\nReview in WorkHub: '+link},
                    'toRecipients':[{'emailAddress':{'address':recipient['contact_email']}}]},'saveToSentItems':True},timeout=25,allow_redirects=False)
        return ('accepted','Microsoft accepted the message for delivery.') if response.status_code==202 else ('failed',f'Microsoft email returned HTTP {response.status_code}; check the connection or company policy.')
    if not recipient['teams_enabled'] or not recipient['teams_secret']:return 'waiting_connection','Recipient has not enabled a Teams workflow.'
    url=workflow_url(unseal(recipient['teams_secret']))
    response=requests.post(url,json={'type':'message','attachments':[{'contentType':'application/vnd.microsoft.card.adaptive','contentUrl':None,
        'content':{'type':'AdaptiveCard','version':'1.2','body':[{'type':'TextBlock','text':row['title'],'weight':'Bolder','wrap':True},
          {'type':'TextBlock','text':row['body'],'wrap':True},{'type':'TextBlock','text':'Review in WorkHub: '+link,'wrap':True}]}}]},timeout=25,allow_redirects=False)
    return ('accepted','Teams workflow accepted the notification.') if 200<=response.status_code<300 else ('failed',f'Teams workflow returned HTTP {response.status_code}; check its URL and trigger permissions.')
def run():
    last_reminder=0;last_cleanup=0;last_reconcile=0
    while not STOP.wait(3):
        try:
            if time.time()-last_reconcile>60:
                from .workhub_runs import reconcile_pending
                reconcile_pending();last_reconcile=time.time()
            if time.time()-last_reminder>3600:
                reminders();last_reminder=time.time()
            if time.time()-last_cleanup>86400:
                from .workhub_files import cleanup_uploads
                cleanup_uploads();last_cleanup=time.time()
            with store.db(True) as db:
                row=db.execute("SELECT o.*,n.sender_id,n.recipient_id,n.project_id,n.item_id,n.title,n.body FROM outbox o JOIN notifications n ON n.id=o.notification_id WHERE o.status IN ('pending','waiting_connection','failed') AND o.attempts<5 AND o.next_attempt<? ORDER BY n.created_at LIMIT 1",(time.time(),)).fetchone()
                if not row:continue
                row=dict(row)
                db.execute("UPDATE outbox SET status='sending',updated_at=? WHERE id=?",(timestamp(),row['id']))
            try:status,detail=deliver(row)
            except Exception:status,detail='failed','Delivery could not complete. Check extension settings and reconnect if necessary.'
            with store.db(True) as db:
                attempts=row['attempts']+(status=='failed')
                db.execute('UPDATE outbox SET status=?,detail=?,attempts=?,next_attempt=?,updated_at=? WHERE id=?',
                           (status,detail,attempts,time.time()+(3600 if status=='waiting_connection' else min(3600,60*2**attempts)),timestamp(),row['id']))
        except Exception:
            from backend.core.runtime import log
            log.exception('WorkHub notification worker could not complete its pending operation.')
def reminders():
    from datetime import datetime,timedelta
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo('Asia/Kolkata')).date()
    with store.db(True) as db:
        rows=db.execute("SELECT * FROM items WHERE stage!='released' AND due_date!='' AND due_date<=?",((today+timedelta(days=1)).isoformat(),)).fetchall()
        for row in rows:
            item=dict(row)
            if db.execute('SELECT 1 FROM reminders WHERE item_id=? AND day=?',(item['id'],today.isoformat())).fetchone():continue
            db.execute('INSERT INTO reminders VALUES(?,?)',(item['id'],today.isoformat()))
            from .workhub import NEXT_OWNER
            store.notify(db,item,item['created_by'],[item[NEXT_OWNER[item['stage']]]],'Deadline: '+item['title'],'Due '+item['due_date']+'. Review the task and record any blocker or updated plan.')
def start():
    global WORKER
    with GUARD:
        if WORKER and WORKER.is_alive():return
        store.initialize();STOP.clear()
        with store.db(True) as db:db.execute("UPDATE outbox SET status='pending' WHERE status='sending'")
        WORKER=threading.Thread(target=run,name='workhub-notifications',daemon=True);WORKER.start()
def shutdown():
    STOP.set()
    if WORKER:WORKER.join(timeout=2)
