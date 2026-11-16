"""Native chat praise/shared components and scoped projections of WorkHub workflow."""
import json,re,time,uuid
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from backend.api import team_chat as chat

router=APIRouter(prefix='/api/team-chat',dependencies=[Depends(chat.actor)],tags=['Inbox apps'])
KINDS={'praise','note','checklist','table'}
BADGES={'thank_you','teamwork','quality','problem_solver','leadership'}

def text(value,limit,required=False):
    if not isinstance(value,str) or '\x00' in value or len(value)>limit or required and not value.strip():raise HTTPException(400,'Enter valid text within the field limit.')
    return value.strip()

def participants(db,thread):
    group=db.execute('SELECT 1 FROM chat_groups WHERE thread=?',(thread,)).fetchone()
    if group:return {m['id']:m for m in chat.members(db,thread)}
    row=db.execute('SELECT * FROM threads WHERE id=?',(thread,)).fetchone();known=chat.people()
    return {u:known[u] for u,identity in ((row['a'],row['a_identity']),(row['b'],row['b_identity'])) if u in known and chat.stamp(known[u])==identity and known[u]['active'] and known[u]['approved']}

def content(kind,value,db,thread,user,creating=True):
    if kind not in KINDS or not isinstance(value,dict):raise HTTPException(400,'Choose praise, note, checklist or table.')
    out={'title':text(value.get('title',''),160,True)}
    if kind=='praise':
        if not creating:raise HTTPException(409,'Posted praise is retained as a recognition record.')
        recipient=value.get('recipient');known=participants(db,thread)
        if type(recipient) is not int or recipient==user['id'] or recipient not in known:raise HTTPException(400,'Choose another current conversation member.')
        if value.get('badge') not in BADGES:raise HTTPException(400,'Choose an available praise badge.')
        out.update(recipient=recipient,recipient_name=known[recipient]['username'],badge=value['badge'],body=text(value.get('body',''),2000))
    elif kind=='note':out['body']=text(value.get('body',''),16000)
    elif kind=='checklist':
        items=value.get('items');out['items']=[]
        if not isinstance(items,list) or not 1<=len(items)<=100:raise HTTPException(400,'Use between 1 and 100 checklist items.')
        for row in items:
            if not isinstance(row,dict) or type(row.get('done',False)) is not bool:raise HTTPException(400,'Use valid checklist items.')
            identity=row.get('id') or uuid.uuid4().hex
            if not isinstance(identity,str) or not re.fullmatch('[a-zA-Z0-9-]{1,64}',identity):raise HTTPException(400,'Invalid item identity.')
            out['items'].append({'id':identity,'text':text(row.get('text',''),500,True),'done':row.get('done',False)})
        if len({i['id'] for i in out['items']})!=len(items):raise HTTPException(400,'Keep checklist identities unique.')
    else:
        columns=value.get('columns');rows=value.get('rows')
        if not isinstance(columns,list) or not 1<=len(columns)<=8 or not isinstance(rows,list) or len(rows)>100:raise HTTPException(400,'Use up to 8 columns and 100 rows.')
        out.update(columns=[text(v,80,True) for v in columns],rows=[])
        for row in rows:
            if not isinstance(row,list) or len(row)!=len(columns):raise HTTPException(400,'Each table row must match its columns.')
            out['rows'].append([text(v,1000) for v in row])
    if len(json.dumps(out,ensure_ascii=False).encode())>65536:raise HTTPException(413,'Keep a shared component under 64 KB.')
    return out

def save_history(db,message,version,user,value):
    db.execute('INSERT INTO chat_component_history VALUES(?,?,?,?,?,?,?)',(message,version,user['id'],chat.stamp(user),user['username'],json.dumps(value,ensure_ascii=False),time.time()))

@router.post('/threads/{thread}/components')
def create(thread:str,request:Request,payload:dict):
    user=chat.actor(request);kind=payload.get('kind');retry=payload.get('client_id')
    if not isinstance(retry,str) or not re.fullmatch('[a-zA-Z0-9-]{8,80}',retry):raise HTTPException(400,'Provide a valid request identity.')
    with chat.store.db() as db:
        chat.store.thread(db,thread,user['id'])
        previous=db.execute('SELECT * FROM messages WHERE sender=? AND client_id=?',(user['id'],retry)).fetchone()
        if previous:
            if previous['thread']!=thread:raise HTTPException(409,'The request belongs to another conversation.')
            return chat.store.message(db,previous)
        value=content(kind,payload.get('content'),db,thread,user)
        if db.execute('SELECT COUNT(*) FROM messages WHERE sender=? AND created>?',(user['id'],time.time()-60)).fetchone()[0]>=60:raise HTTPException(429,'Message limit reached. Try again in a minute.')
        body=('Praise for '+value['recipient_name'] if kind=='praise' else 'Shared '+kind)+': '+value['title']
        message=db.execute('INSERT INTO messages(thread,sender,body,created,client_id) VALUES(?,?,?,?,?)',(thread,user['id'],body,time.time(),retry)).lastrowid
        db.execute('INSERT INTO chat_components VALUES(?,?,?,?,?,?)',(message,kind,json.dumps(value,ensure_ascii=False),1,time.time(),user['id']));save_history(db,message,1,user,value)
        return chat.store.message(db,db.execute('SELECT * FROM messages WHERE id=?',(message,)).fetchone())

def opened(db,message,user):
    row=db.execute('SELECT c.*,m.thread FROM chat_components c JOIN messages m ON m.id=c.message WHERE c.message=?',(message,)).fetchone()
    if not row:raise HTTPException(404,'Shared component not found.')
    chat.store.thread(db,row['thread'],user['id']);return row

@router.get('/components/{message}')
def read_component(message:int,request:Request):
    with chat.store.db() as db:
        opened(db,message,chat.actor(request));return chat.store.message(db,db.execute('SELECT * FROM messages WHERE id=?',(message,)).fetchone())

@router.post('/components/{message}')
def edit(message:int,request:Request,payload:dict):
    user=chat.actor(request)
    with chat.store.db() as db:
        row=opened(db,message,user)
        if db.execute('SELECT COUNT(*) FROM chat_component_history WHERE editor=? AND created>?',(user['id'],time.time()-60)).fetchone()[0]>=60:raise HTTPException(429,'Shared edit limit reached. Try again in a minute.')
        if type(payload.get('version')) is not int or payload['version']!=row['version']:raise HTTPException(409,'Someone changed this component. Keep your draft, reload the latest version, and review before saving again.')
        value=content(row['kind'],payload.get('content'),db,row['thread'],user,False);version=row['version']+1
        changed=db.execute('UPDATE chat_components SET content=?,version=?,updated=?,editor=? WHERE message=? AND version=?',(json.dumps(value,ensure_ascii=False),version,time.time(),user['id'],message,row['version']))
        if changed.rowcount!=1:raise HTTPException(409,'Someone changed this component. Reload the latest version before saving.')
        save_history(db,message,version,user,value)
        db.execute('UPDATE messages SET body=? WHERE id=?',('Shared '+row['kind']+': '+value['title'],message))
        return chat.store.message(db,db.execute('SELECT * FROM messages WHERE id=?',(message,)).fetchone())

@router.get('/components/{message}/history')
def history(message:int,request:Request,before:int=Query(2147483647,ge=1)):
    with chat.store.db() as db:
        opened(db,message,chat.actor(request));rows=list(db.execute('SELECT version,editor_name,content,created FROM chat_component_history WHERE message=? AND version<? ORDER BY version DESC LIMIT 51',(message,before)))
        return {'items':[{**dict(r),'content':json.loads(r['content'])} for r in rows[:50]],'has_more':len(rows)>50}

def workhub_user(request):
    user=chat.actor(request)
    if user.get('role')!='admin' and 'workhub' not in user.get('workspaceModules',[]):raise HTTPException(403,'WorkHub access is required.')
    return user

@router.get('/workhub-inbox')
def inbox(request:Request,view:str='approvals',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50)):
    user=workhub_user(request)
    from backend.core.workhub import store as hub
    if view=='approvals':
        from backend.core import workhub_portfolio as portfolio
        rows=[r for r in portfolio.snapshot(user,role='engineer')['approvals'] if r['can_review']]
        with hub.db() as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for row in rows:
                if row['kind']=='document' and 'pi_documents' in tables:
                    document=db.execute('SELECT current_revision FROM pi_documents WHERE id=?',(row['id'].split(':',1)[1],)).fetchone()
                    row['saved_revision']=document['current_revision'] if document else None
                elif row['kind']=='workflow':row['saved_version']=hub.item(db,row['item_id'])['version']
    elif view=='workflows':
        with hub.db() as db:
            rows=[hub.public(r) for r in db.execute("SELECT * FROM items WHERE stage!='released' AND (? IN (created_by,owner_id,quality_id,approver_id,release_id) OR EXISTS(SELECT 1 FROM json_each(supporting_ids) WHERE value=?)) ORDER BY updated_at DESC",(user['id'],user['id']))]
    elif view=='updates':rows=hub.notifications(user)['items']
    else:raise HTTPException(400,'Choose approvals, workflows or updates.')
    return {'items':rows[(page-1)*page_size:page*page_size],'total':len(rows),'page':page,'page_size':page_size}


@router.get('/work-center/options')
def work_center_options(request:Request):
    user=workhub_user(request)
    from backend.core.workhub import store as hub
    projects=[]
    with hub.db() as db:
        for raw in db.execute("SELECT * FROM items WHERE type='project' ORDER BY title"):
            project=dict(raw)
            try:hub.contribute(db,project['id'],user)
            except HTTPException:continue
            try:hub.manage(project,user);can_create=project['stage'] in {'todo','development','blocked'}
            except HTTPException:can_create=False
            projects.append({'id':project['id'],'title':project['title'],'can_create':can_create,
                'tasks':[dict(r) for r in db.execute("SELECT id,title,stage FROM items WHERE project_id=? AND type='task' ORDER BY title",(project['id'],))]})
    return {'projects':projects,'users':[u for u in hub.users() if u['active']],'current_user':user['id']}


@router.get('/work-center/tasks')
def work_center_tasks(request:Request,view:str=Query('mine',pattern='^(mine|tasks)$'),page:int=Query(1,ge=1),search:str=Query('',max_length=180)):
    user=workhub_user(request)
    from backend.core.workhub import store as hub
    with hub.db() as db:
        condition="(i.owner_id=? OR EXISTS(SELECT 1 FROM json_each(i.supporting_ids) WHERE value=?))" if view=='mine' else "i.type='task' AND (i.owner_id=? OR i.created_by=?)"
        where=condition+" AND (instr(lower(i.title),lower(?))>0 OR instr(lower(p.title),lower(?))>0)"
        args=(user['id'],user['id'],search,search)
        total=db.execute('SELECT COUNT(*) FROM items i JOIN items p ON p.id=i.project_id WHERE '+where,args).fetchone()[0]
        rows=[hub.public(r) for r in db.execute('SELECT i.*,p.title AS project_title FROM items i JOIN items p ON p.id=i.project_id WHERE '+where+' ORDER BY i.updated_at DESC LIMIT 20 OFFSET ?',(*args,(page-1)*20))]
        users={u['id']:u['username'] for u in hub.users()}
        for row in rows:row['owner_name']=users.get(row['owner_id'],'Unavailable user')
        return {'items':rows,'total':total,'page':page,'page_size':20}


@router.post('/work-center/tasks')
def work_center_create_task(request:Request,payload:dict):
    user=workhub_user(request)
    from backend.core.workhub import store as hub
    project=payload.get('project_id')
    if not isinstance(project,str) or not project:raise HTTPException(400,'Select a project for this task.')
    return hub.create(user,{'title':payload.get('title'),'description':payload.get('description',''),
        'owner_id':payload.get('owner_id',user['id']),'due_date':payload.get('due_date',''),
        'planned_hours':payload.get('planned_hours',0)},project_id=project)


@router.post('/work-center/time')
def work_center_log_time(request:Request,payload:dict):
    user=workhub_user(request)
    from backend.core.workhub import store as hub
    if type(payload.get('minutes')) is not int or not 1<=payload['minutes']<=1440:raise HTTPException(400,'Log between 1 and 1440 working minutes.')
    return hub.add_update(user,payload.get('item_id'),{'body':payload.get('body'),'minutes':payload['minutes'],
        'work_date':payload.get('work_date'),'file_ids':[],'run_ids':[]})


@router.get('/work-center/timesheet')
def work_center_timesheet(request:Request,project:str='',date_from:str='',date_to:str='',page:int=Query(1,ge=1),export:str=Query('',pattern='^(|csv)$')):
    user=workhub_user(request)
    from backend.core.workhub import store as hub,day
    start,end=day(date_from),day(date_to)
    if start and end and start>end:raise HTTPException(400,'From date must be on or before To date.')
    conditions=['u.author_id=?','u.minutes>0'];args=[user['id']]
    if project:conditions.append('u.project_id=?');args.append(project)
    if start:conditions.append('u.work_date>=?');args.append(start)
    if end:conditions.append('u.work_date<=?');args.append(end)
    query=" FROM updates u JOIN items i ON i.id=u.item_id JOIN items p ON p.id=u.project_id WHERE "+' AND '.join(conditions)
    with hub.db() as db:
        total=db.execute('SELECT COUNT(*)'+query,args).fetchone()[0]
        totals=dict(db.execute("SELECT COALESCE(SUM(u.minutes),0) AS logged_minutes,COALESCE(SUM(CASE WHEN u.time_status='approved' THEN u.minutes ELSE 0 END),0) AS approved_minutes,COALESCE(SUM(CASE WHEN u.time_status='submitted' THEN u.minutes ELSE 0 END),0) AS pending_minutes"+query,args).fetchone())
        selection='SELECT u.*,i.title AS task_title,p.title AS project_title'+query+' ORDER BY u.work_date DESC,u.created_at DESC'
        if export:
            import csv,io
            from fastapi.responses import Response
            output=io.StringIO();writer=csv.writer(output)
            writer.writerow(['Date','User','Project','Task / project work','Hours','Minutes','What work was done','Status','Review comment'])
            def safe(value):
                value=str(value or '')
                return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
            for row in db.execute(selection,args):writer.writerow([row['work_date'],safe(user['username']),safe(row['project_title']),safe(row['task_title']),round(row['minutes']/60,4),row['minutes'],safe(row['body']),row['time_status'],safe(row['review_comment'])])
            return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="my-timesheet.csv"','Cache-Control':'private, no-store'})
        rows=[dict(r) for r in db.execute(selection+' LIMIT 20 OFFSET ?',(*args,(page-1)*20))]
        return {'items':rows,'total':total,'page':page,'page_size':20,'totals':totals}
