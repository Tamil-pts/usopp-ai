"""Self-hosted ONLYOFFICE integration with scoped URLs and signed callbacks."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import requests
from fastapi import HTTPException
from backend.core.workhub import store as hub,identity,timestamp,encode
from backend.core import accounts,workhub_files as files
from . import store,documents
from .local_ai import local_url,ServiceUnavailable


def initialize():
    store.initialize()
    with hub.db(True) as db:db.execute('''CREATE TABLE IF NOT EXISTS pi_office_sessions(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
        document_id TEXT NOT NULL,base_revision TEXT NOT NULL,latest_revision TEXT NOT NULL,user_id INTEGER NOT NULL,
        expires INTEGER NOT NULL,office_key TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',last_hash TEXT)''')


def _b64(value):return base64.urlsafe_b64encode(value).decode().rstrip('=')
def _unb64(value):return base64.urlsafe_b64decode(value+'='*(-len(value)%4))


def _key():
    path=hub.root/'intelligence.key'
    try:return path.read_bytes()
    except FileNotFoundError:
        value=os.urandom(32)
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as output:output.write(value)
        except FileExistsError:return path.read_bytes()
        return value


def _cap(session_id,expires):
    data=session_id+':'+str(expires);return _b64(data.encode())+'.'+_b64(hmac.new(_key(),data.encode(),hashlib.sha256).digest())


def session(identity_value,token):
    initialize()
    try:
        data,signature=str(token).split('.',1);raw=_unb64(data);key,expires=raw.decode().split(':')
        if key!=identity_value or int(expires)<time.time() or not hmac.compare_digest(_unb64(signature),hmac.new(_key(),raw,hashlib.sha256).digest()):raise ValueError()
    except (ValueError,TypeError,UnicodeError):raise HTTPException(403,'This office document link is invalid or expired.')
    with hub.db() as db:row=db.execute('SELECT * FROM pi_office_sessions WHERE id=?',(identity_value,)).fetchone()
    if not row or row['expires']<time.time():raise HTTPException(403,'This office editing session expired. Reopen the editor.')
    user=next((u for u in accounts.store.list_users() if u['id']==row['user_id'] and u.get('active') and u.get('approved') and not u.get('isDemo')),None)
    if not user:raise HTTPException(403,'The editing account is no longer enabled.')
    return dict(row),user


def jwt_sign(value,secret):
    header=_b64(b'{"alg":"HS256","typ":"JWT"}');body=_b64(json.dumps(value,separators=(',',':'),ensure_ascii=False).encode());raw=(header+'.'+body).encode()
    return raw.decode()+'.'+_b64(hmac.new(secret.encode(),raw,hashlib.sha256).digest())


def jwt_verify(token,secret):
    try:
        a,b,c=str(token).split('.')
        if json.loads(_unb64(a)).get('alg')!='HS256' or not hmac.compare_digest(_unb64(c),hmac.new(secret.encode(),(a+'.'+b).encode(),hashlib.sha256).digest()):raise ValueError()
        payload=json.loads(_unb64(b))
        if payload.get('exp') and payload['exp']<time.time():raise ValueError()
        return payload.get('payload',payload)
    except (ValueError,TypeError,KeyError,UnicodeError):raise HTTPException(403,'The office server callback signature is invalid.')


def editor_config(user,project_id,document_id,payload):
    initialize();public=os.getenv('USOPP_PI_OFFICE_PUBLIC_URL','');secret=os.getenv('USOPP_PI_OFFICE_JWT_SECRET','')
    if not public or not secret:raise ServiceUnavailable('The local office editor is not configured. Set its company HTTPS URL and matching ONLYOFFICE JWT secret; uploaded documents remain available for download.')
    public=local_url(public);app_base=local_url(os.getenv('USOPP_PI_APP_INTERNAL_URL','http://127.0.0.1:8200'))
    with hub.db(True) as db:
        store.project(db,project_id,user,write=True);doc=store.document(db,document_id,project_id);rev=store.revision(db,doc['current_revision'],document_id)
        if payload.get('version')!=rev['id']:raise HTTPException(409,'This document changed. Refresh before opening the editor.')
        if doc['kind']!='source' or not rev['file_id']:raise HTTPException(400,'Choose an uploaded DOCX or XLSX document.')
        record,path=files.file_record(rev['file_id'],project_id);extension=Path(record['name']).suffix.lower()
        if extension not in {'.docx','.xlsx'}:raise HTTPException(400,'The office editor supports DOCX and XLSX. Use the document workspace for other formats.')
        sid=identity();expires=int(time.time()+12*3600);office_key='pi-'+sid
        db.execute('INSERT INTO pi_office_sessions(id,project_id,document_id,base_revision,latest_revision,user_id,expires,office_key) VALUES(?,?,?,?,?,?,?,?)',
                   (sid,project_id,document_id,rev['id'],rev['id'],user['id'],expires,office_key))
    token=_cap(sid,expires);base=app_base+'/api/workhub/intelligence/office/'
    config={'documentType':'word' if extension=='.docx' else 'cell','document':{'fileType':extension[1:],'key':office_key,'title':record['name'],
             'url':base+'files/'+sid+'?token='+token,'permissions':{'edit':True,'download':True,'print':True,'comment':True}},
            'editorConfig':{'mode':'edit','lang':'en','callbackUrl':base+'callback/'+sid+'?token='+token,
                            'user':{'id':str(user['id']),'name':user.get('username','Engineer')},'customization':{'forcesave':True}},
            'width':'100%','height':'100%'}
    config['token']=jwt_sign(config,secret)
    return {'session_id':sid,'script_url':public+'/web-apps/apps/api/documents/api.js','config':config,'expires':expires}


def original(identity_value,token):
    row,user=session(identity_value,token)
    with hub.db() as db:
        store.project(db,row['project_id'],user);rev=store.revision(db,row['base_revision'],row['document_id'])
    return files.file_record(rev['file_id'],row['project_id'])


def callback(identity_value,token,payload,authorization=''):
    row,user=session(identity_value,token);secret=os.getenv('USOPP_PI_OFFICE_JWT_SECRET','')
    if not secret:raise HTTPException(503,'The local office JWT secret is unavailable.')
    signed=payload.get('token') or (authorization[7:] if authorization.startswith('Bearer ') else '')
    body=jwt_verify(signed,secret)
    if body.get('key')!=row['office_key']:raise HTTPException(403,'The office callback belongs to another editing session.')
    if body.get('status') not in {2,6}:return {'error':0}
    url=local_url(body.get('url',''))
    allowed=[os.getenv('USOPP_PI_OFFICE_INTERNAL_URL',''),os.getenv('USOPP_PI_OFFICE_PUBLIC_URL','')]
    origin=lambda value:(urlsplit(value).scheme,urlsplit(value).hostname,urlsplit(value).port or (443 if urlsplit(value).scheme=='https' else 80))
    if origin(url) not in {origin(v) for v in allowed if v}:raise HTTPException(403,'The edited file must come from the configured local office server.')
    client=requests.Session();client.trust_env=False
    try:
        response=client.get(url,stream=True,timeout=(5,120),allow_redirects=False,verify=os.getenv('USOPP_PI_CA_BUNDLE') or True)
        if response.status_code!=200:raise HTTPException(502,'The local office server could not provide the saved document.')
        data=bytearray()
        for chunk in response.iter_content(1024*1024):
            data.extend(chunk)
            if len(data)>documents.MAX_DOCUMENT:raise HTTPException(413,'The saved office document exceeds 100 MiB.')
    except requests.RequestException:raise HTTPException(502,'The local office server is unavailable. Retry saving from the editor.')
    finally:client.close()
    digest=hashlib.sha256(data).hexdigest()
    with hub.db() as db:
        current_session=dict(db.execute('SELECT * FROM pi_office_sessions WHERE id=?',(identity_value,)).fetchone())
        if current_session.get('last_hash')==digest:return {'error':0}
        store.project(db,row['project_id'],user,write=True);doc=store.document(db,row['document_id'],row['project_id']);previous=store.revision(db,current_session['latest_revision'],doc['id'])
        if doc['current_revision']!=current_session['latest_revision']:raise HTTPException(409,'A newer document revision was saved outside this office session. Reopen it before continuing.')
    original_file,_=files.file_record(previous['file_id'],row['project_id']);record=documents.generated_file(user,row['project_id'],original_file['name'],bytes(data))
    with hub.db(True) as db:
        doc,rev=store.create_document(db,user,row['project_id'],'source',doc['title'],{'body':'','sources':[],'notices':['Office edits saved. Run Read document to refresh extracted text and requirement evidence.']},
                                     file_id=record['id'],document_id=doc['id'],expected_revision=current_session['latest_revision'],generated_by='office:'+identity_value+':'+digest)
        db.execute('UPDATE pi_office_sessions SET latest_revision=?,last_hash=?,status=? WHERE id=?',(rev['id'],digest,'saved' if body['status']==2 else 'open',identity_value))
    return {'error':0}
