"""Local meeting scheduling and room-scoped tokens for a self-hosted Jitsi server."""
import base64,hashlib,hmac,json,math,os,re,time,uuid
from datetime import datetime,timezone
from urllib.parse import urlsplit,urlencode
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from fastapi import APIRouter,Depends,Request,HTTPException,UploadFile,File
from fastapi.responses import Response
from backend.api import team_chat as chat

router=APIRouter(prefix='/api/team-chat',dependencies=[Depends(chat.actor)],tags=['Team meetings'])

def config():
    try:value=json.loads((chat.BASE/'.usopp_meetings.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):value={}
    if not isinstance(value,dict):value={}
    url=os.getenv('USOPP_MEETING_URL',value.get('url',''));secret=os.getenv('USOPP_MEETING_JWT_SECRET',value.get('secret',''));app=os.getenv('USOPP_MEETING_JWT_APP_ID',value.get('appId','usopp'))
    if not all(isinstance(v,str) for v in (url,secret,app)):return '', '', 'usopp',False
    url=url.rstrip('/')
    try:parsed=urlsplit(url)
    except ValueError:return '', '', 'usopp',False
    ready=parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and parsed.path in {'','/'} and len(secret)>=32
    return url,secret,app,bool(ready)

@router.get('/meetings/config')
def status():return {'provider':'Self-hosted Jitsi','configured':config()[3],'requiresHttps':True,'recordingUploadMaxBytes':200*1024*1024,'note':'Live calls require the configured local Jitsi server. Recording, transcription, whiteboard and other server features depend on its enabled services.'}

def meeting(db,key,user):
    row=db.execute('SELECT * FROM meetings WHERE id=?',(key,)).fetchone()
    if not row:raise HTTPException(404,'Meeting not found.')
    chat.store.thread(db,row['thread'],user['id']);return row

def view(db,row,user):
    item=dict(row);item['can_manage']=row['host']==user['id'] and row['host_identity']==chat.stamp(user)
    item['responses']=[dict(r) for r in db.execute('SELECT user,response FROM meeting_rsvp WHERE meeting=?',(row['id'],))]
    item['join_requests']=[dict(r) for r in db.execute('SELECT user,joined FROM meeting_attendance WHERE meeting=?',(row['id'],))]
    item['recordings']=[dict(r) for r in db.execute('SELECT a.id,a.name,a.size FROM meeting_recordings r JOIN attachments a ON a.id=r.attachment WHERE r.meeting=?',(row['id'],))]
    return item

@router.get('/meetings')
def list_meetings(request:Request,thread:str=''):
    user=chat.actor(request);out=[]
    with chat.store.db() as db:
        chat.sync_groups(db)
        for row in db.execute('SELECT * FROM meetings WHERE (?="" OR thread=?) AND end>? ORDER BY start LIMIT 1000',(thread,thread,time.time()-90*86400)):
            try:chat.store.thread(db,row['thread'],user['id'],sync=False)
            except HTTPException:continue
            out.append(view(db,row,user))
    return {'meetings':out}

@router.post('/threads/{thread}/meetings')
def schedule(thread:str,request:Request,payload:dict):
    user=chat.actor(request);title=payload.get('title','');agenda=payload.get('agenda','');start=payload.get('start');end=payload.get('end');tz=payload.get('timezone','Asia/Kolkata')
    if not isinstance(title,str) or not 1<=len(title.strip())<=180 or not isinstance(agenda,str) or len(agenda)>8000:raise HTTPException(400,'Enter a meeting title and agenda up to 8,000 characters.')
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end)) or not 0<end-start<=12*3600 or end<=time.time():raise HTTPException(400,'Choose a future meeting lasting up to 12 hours.')
    try:ZoneInfo(tz)
    except (TypeError,ValueError,ZoneInfoNotFoundError):raise HTTPException(400,'Choose a valid time zone.') from None
    project=payload.get('project_id','');item=payload.get('item_id','')
    if project:chat.work_link(user,project,item)
    elif item:raise HTTPException(400,'Choose a project for the linked task.')
    key=uuid.uuid4().hex
    with chat.store.db() as db:
        chat.store.thread(db,thread,user['id'])
        db.execute('INSERT INTO meetings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(key,thread,user['id'],chat.stamp(user),title.strip(),start,end,tz,agenda,'scheduled',project,item,time.time()))
        db.execute('INSERT INTO messages(thread,sender,body,created,client_id) VALUES(?,?,?,?,?)',(thread,user['id'],'Meeting scheduled: '+title.strip()+' · '+datetime.fromtimestamp(start,ZoneInfo(tz)).strftime('%d %b %Y %H:%M')+' '+tz,time.time(),key))
        return view(db,meeting(db,key,user),user)

@router.post('/meetings/{key}/response')
def respond(key:str,request:Request,payload:dict):
    user=chat.actor(request);response=payload.get('response')
    if response not in {'accepted','tentative','declined'}:raise HTTPException(400,'Choose accepted, tentative or declined.')
    with chat.store.db() as db:
        row=meeting(db,key,user)
        if row['status']=='cancelled':raise HTTPException(409,'This meeting was cancelled.')
        db.execute('INSERT INTO meeting_rsvp VALUES(?,?,?,?) ON CONFLICT(meeting,user) DO UPDATE SET identity=excluded.identity,response=excluded.response',(key,user['id'],chat.stamp(user),response))
    return {'ok':True}

@router.post('/meetings/{key}/cancel')
def cancel(key:str,request:Request):
    user=chat.actor(request)
    with chat.store.db() as db:
        row=meeting(db,key,user)
        if row['host']!=user['id'] or row['host_identity']!=chat.stamp(user):raise HTTPException(403,'Only the meeting organizer can cancel it.')
        db.execute("UPDATE meetings SET status='cancelled' WHERE id=?",(key,))
        db.execute('INSERT INTO messages(thread,sender,body,created,client_id) VALUES(?,?,?,?,?)',(row['thread'],user['id'],'Meeting cancelled: '+row['title'],time.time(),uuid.uuid4().hex))
    return {'ok':True}

@router.post('/meetings/{key}/join')
def join(key:str,request:Request):
    user=chat.actor(request)
    with chat.store.db() as db:
        row=meeting(db,key,user)
        if row['status']=='cancelled' or row['end']+3600<time.time():raise HTTPException(409,'This meeting is cancelled or has ended.')
        url,secret,app,ready=config()
        if not ready:raise HTTPException(503,'Configure the local Jitsi HTTPS URL and shared JWT credentials on the server before joining.')
        now=int(time.time());room='usopp'+key
        def encode(value):return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).rstrip(b'=').decode()
        header=encode({'alg':'HS256','typ':'JWT'});payload=encode({'iss':app,'aud':app,'sub':urlsplit(url).hostname,'room':room,'iat':now,'nbf':now-10,'exp':now+900,'context':{'user':{'id':str(user['id']),'name':user['username'],'moderator':row['host']==user['id']}}})
        signed=header+'.'+payload;signature=base64.urlsafe_b64encode(hmac.new(secret.encode(),signed.encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
        db.execute('INSERT INTO meeting_attendance VALUES(?,?,?,?) ON CONFLICT(meeting,user) DO UPDATE SET identity=excluded.identity,joined=excluded.joined',(key,user['id'],chat.stamp(user),time.time()))
        return {'url':url+'/'+room+'?'+urlencode({'jwt':signed+'.'+signature}),'expires':now+900}

@router.get('/meetings/{key}/calendar.ics')
def calendar(key:str,request:Request):
    with chat.store.db() as db:row=meeting(db,key,chat.actor(request))
    def esc(value):return str(value).replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(',','\\,').replace(';','\\;')
    def date(value):return datetime.fromtimestamp(value,timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//uSOPp.ai//Meetings//EN','BEGIN:VEVENT','UID:'+key+'@usopp.local','DTSTAMP:'+date(time.time()),'DTSTART:'+date(row['start']),'DTEND:'+date(row['end']),'SUMMARY:'+esc(row['title']),'DESCRIPTION:'+esc(row['agenda']),'STATUS:'+('CANCELLED' if row['status']=='cancelled' else 'CONFIRMED'),'BEGIN:VALARM','TRIGGER:-PT10M','ACTION:DISPLAY','DESCRIPTION:Meeting reminder','END:VALARM','END:VEVENT','END:VCALENDAR']
    # Fold UTF-8 calendar lines to RFC 5545's 75-octet limit.
    folded=[]
    for line in lines:
        current=''
        for char in line:
            if len((current+char).encode())>74:folded.append(current);current=' '
            current+=char
        folded.append(current)
    return Response('\r\n'.join(folded)+'\r\n',media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="meeting-'+key+'.ics"','Cache-Control':'private, no-store'})

@router.post('/meetings/{key}/recordings')
def recording(key:str,request:Request,file:UploadFile=File(...)):
    user=chat.actor(request);path=None
    try:
        with chat.store.db() as db:
            row=meeting(db,key,user)
            if row['host']!=user['id'] or row['host_identity']!=chat.stamp(user):raise HTTPException(403,'Only the organizer can publish meeting recordings.')
            name=re.sub(r'[\x00-\x1f\x7f]','',str(file.filename or '').replace('\\','/').rsplit('/',1)[-1])[:180]
            if not name.lower().endswith(('.webm','.mp4')):raise HTTPException(400,'Upload a WebM or MP4 recording.')
            identity=uuid.uuid4().hex;folder=chat.store.root/'files';folder.mkdir(exist_ok=True);path=folder/identity;size=0
            with path.open('xb') as output:
                while chunk:=file.file.read(262144):
                    size+=len(chunk)
                    if size>200*1024*1024:raise HTTPException(413,'Upload a recording up to 200 MB; split longer recordings.')
                    output.write(chunk)
            with path.open('rb') as source:head=source.read(16)
            if not (head.startswith(b'\x1aE\xdf\xa3') or head[4:8]==b'ftyp'):raise HTTPException(400,'The file is not a WebM or MP4 recording.')
            message=db.execute('INSERT INTO messages(thread,sender,body,created,client_id) VALUES(?,?,?,?,?)',(row['thread'],user['id'],'Meeting recording: '+row['title'],time.time(),uuid.uuid4().hex)).lastrowid
            db.execute('INSERT INTO attachments VALUES(?,?,?,?,?)',(identity,message,name,'video/webm' if name.lower().endswith('.webm') else 'video/mp4',size));db.execute('INSERT INTO meeting_recordings VALUES(?,?)',(key,identity))
        return {'id':identity,'name':name,'size':size}
    except Exception:
        if path:path.unlink(missing_ok=True)
        raise
    finally:file.file.close()
