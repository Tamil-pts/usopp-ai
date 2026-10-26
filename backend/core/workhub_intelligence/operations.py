"""Project-scoped editing, annotations and confirmed WorkHub plan application."""
import json
import math
import re
from fastapi import HTTPException
from backend.core.workhub import store as hub,identity,timestamp,text,encode,day
from backend.core import workhub_files as files
from . import store


def create_meeting(user,key,payload):
    store.initialize()
    with hub.db(True) as db:
        project=store.project(db,key,user,write=True)
        file_id=payload.get('file_id');file=None
        if file_id:file,_=files.file_record(file_id,key)
        language=payload.get('language','auto')
        if language not in store.LANGUAGES:raise HTTPException(400,'Choose automatic Tamil + English, English or Tamil.')
        participants=payload.get('participants',[])
        if not isinstance(participants,list) or len(participants)>100:raise HTTPException(400,'Use up to 100 known participants.')
        participants=[text(p,120,True) for p in participants]
        subject=text(payload.get('subject') or (file['name'] if file else 'Project discussion'),240,True)
        date=day(payload.get('meeting_date',''));now=timestamp();meeting_id=identity()
        db.execute('INSERT INTO pi_meetings(id,project_id,subject,meeting_date,language,participants,file_id,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (meeting_id,key,subject,date,language,encode(participants),file_id,user['id'],now,now))
        hub.event(db,project,user,'intelligence_meeting_saved',{'meeting_id':meeting_id,'subject':subject,'file_id':file_id,'recording_consent_confirmed':payload.get('recording_consent') is True})
        return store.meeting(db,meeting_id,key)


def get_meeting(user,key,meeting_id,version=None):
    store.initialize()
    with hub.db() as db:
        store.project(db,key,user);meeting=store.meeting(db,meeting_id,key)
        if version is None:transcript=json.loads(meeting['transcript'])
        else:
            row=db.execute('SELECT transcript FROM pi_transcript_history WHERE meeting_id=? AND version=?',(meeting_id,version)).fetchone()
            if not row:raise HTTPException(404,'This transcript revision is unavailable.')
            transcript=json.loads(row['transcript'])
        history=[dict(r) for r in db.execute('SELECT version,changed_by,created_at FROM pi_transcript_history WHERE meeting_id=? ORDER BY version DESC',(meeting_id,))]
        file_name=files.file_record(meeting['file_id'],key)[0]['name'] if meeting['file_id'] else ''
        reviewed=db.execute('SELECT reviewed_by,reviewed_at,transcript_hash FROM pi_transcript_reviews WHERE meeting_id=? AND version=?',(meeting_id,version or meeting['transcript_version'])).fetchone()
        return {**meeting,'file_name':file_name,'participants':json.loads(meeting['participants']),'transcript':transcript,'viewed_version':version or meeting['transcript_version'],'history':history,'review':dict(reviewed) if reviewed else None}


def confirm_transcript(user,key,meeting_id,payload):
    store.initialize()
    from .reliability import digest
    with hub.db(True) as db:
        item=store.project(db,key,user,write=True);meeting=store.meeting(db,meeting_id,key)
        if payload.get('confirmed') is not True:raise HTTPException(400,'Confirm the transcript, technical terms and unresolved uncertainties.')
        if payload.get('version')!=meeting['transcript_version'] or not meeting['transcript_version']:raise HTTPException(409,'Review the current saved transcript revision.')
        transcript=json.loads(meeting['transcript'])
        if not transcript.get('segments'):raise HTTPException(400,'A transcript needs recorded text before confirmation.')
        db.execute('INSERT OR IGNORE INTO pi_transcript_reviews VALUES(?,?,?,?,?)',(meeting_id,meeting['transcript_version'],digest(transcript),user['id'],timestamp()))
        hub.event(db,item,user,'intelligence_transcript_confirmed',{'meeting_id':meeting_id,'version':meeting['transcript_version']})
    return get_meeting(user,key,meeting_id)


def edit_transcript(user,key,meeting_id,payload):
    store.initialize()
    from .processing import _save_transcript,_protected_changes
    with hub.db(True) as db:
        item=store.project(db,key,user,write=True);meeting=store.meeting(db,meeting_id,key)
        if payload.get('version')!=meeting['transcript_version']:raise HTTPException(409,'This transcript changed. Refresh before saving your corrections.')
        previous=json.loads(meeting['transcript']);old={s['id']:s for s in previous.get('segments',[])};segments=payload.get('segments')
        if not isinstance(segments,list) or len(segments)>20000:raise HTTPException(400,'Use up to 20,000 timestamped transcript segments.')
        seen=set();rows=[]
        for segment in segments:
            sid=segment.get('id') if isinstance(segment,dict) else None
            if not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',sid) or sid in seen:raise HTTPException(400,'Transcript segment IDs must be unique.')
            seen.add(sid);first=segment.get('start');last=segment.get('end')
            if any(v is not None and (type(v) not in (float,int) or not math.isfinite(v) or v<0 or v>86400) for v in (first,last)) or first is not None and last is not None and last<first:raise HTTPException(400,'Use valid audio timestamps in seconds.')
            body=text(segment.get('text',''),40000,True);english=text(segment.get('english',''),40000)
            rows.append({**old.get(sid,{}),'id':sid,'start':first,'end':last,'text':body,'english':english,
                         'original_text':old.get(sid,{}).get('original_text',body),'speaker':text(segment.get('speaker') or '',120) or None,
                         'corrected_by':user['id'],'interpretation_uncertain':bool(english and _protected_changes(body,english))})
        value={**previous,'segments':rows};version=_save_transcript(db,user,meeting,value,meeting['transcript_version'])
        hub.event(db,item,user,'intelligence_transcript_corrected',{'meeting_id':meeting_id,'version':version})
        return {'version':version,'transcript':value}


def preferences(user,key,payload):
    with hub.db(True) as db:
        project=store.project(db,key,user,manage=True)
        terms=payload.get('terminology',[]);templates=payload.get('templates',[])
        if not isinstance(terms,list) or len(terms)>200 or not isinstance(templates,list) or len(templates)>100:raise HTTPException(400,'Use up to 200 engineering terms and 100 activity templates.')
        terms=list(dict.fromkeys(text(t,100,True) for t in terms))
        templates=[text(t,180,True) for t in templates]
        db.execute('INSERT INTO pi_preferences VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET terminology=excluded.terminology,templates=excluded.templates,updated_at=excluded.updated_at',
                   (key,encode(terms),encode(templates),timestamp()))
        hub.event(db,project,user,'intelligence_preferences_updated',{'terminology_count':len(terms),'template_count':len(templates)})
        return {'terminology':terms,'templates':templates}


def annotate(user,key,document_id,payload):
    with hub.db(True) as db:
        item=store.project(db,key,user,write=True);doc=store.document(db,document_id,key)
        revision=store.revision(db,payload.get('revision_id'),document_id);page=payload.get('page')
        if type(page) is not int or not 1<=page<=2000:raise HTTPException(400,'Choose a PDF page from 1 to 2,000.')
        position=[payload.get('x'),payload.get('y')]
        if any(v is not None and (type(v) not in (float,int) or not math.isfinite(v) or not 0<=v<=1) for v in position):raise HTTPException(400,'Use page coordinates between 0 and 1.')
        annotation={'id':identity(),'document_id':document_id,'revision_id':revision['id'],'page':page,'body':text(payload.get('body',''),4000,True),
                    'x':position[0],'y':position[1],'author_id':user['id'],'created_at':timestamp()}
        db.execute('INSERT INTO pi_annotations VALUES(?,?,?,?,?,?,?,?,?)',tuple(annotation.values()))
        hub.event(db,item,user,'intelligence_document_annotated',{'document_id':document_id,'revision_id':revision['id'],'page':page})
        return annotation


def apply_plan(user,key,document_id,payload):
    store.initialize()
    if payload.get('confirmed') is not True:raise HTTPException(400,'Review and confirm before updating the official WorkHub plan.')
    with hub.db(True) as db:
        project=store.project(db,key,user,manage=True);doc=store.document(db,document_id,key);revision=store.revision(db,payload.get('revision_id'),document_id)
        if doc['kind']!='plan' or revision['status']!='approved' or doc['approved_revision']!=revision['id']:raise HTTPException(409,'Apply the currently approved project plan revision.')
        links={r['proposal_key']:r['task_id'] for r in db.execute('SELECT * FROM pi_task_links WHERE document_id=?',(document_id,))}
        if revision['applied_at']:return {'applied_at':revision['applied_at'],'task_ids':links}
        store.validate_content('plan',revision['content']);tasks=revision['content'].get('tasks',[])
        if not tasks:raise HTTPException(400,'Add planned activities before applying this proposal.')
        use_phase_owners=payload.get('use_phase_owners') is True
        # The same WorkHub Store methods run in this transaction. Validation,
        # assignment notifications, permissions and event history stay intact.
        for task in tasks:
            owner=task.get('owner_id')
            if owner is None and use_phase_owners:owner=project[{'development':'owner_id','quality':'quality_id','release':'release_id'}.get(task.get('phase'),'owner_id')]
            if owner is None:raise HTTPException(400,'Assign each proposed activity, or confirm use of the existing phase assignees.')
            info={'title':task['title'],'description':(str(task.get('description') or '')+'\nRequirements: '+', '.join(task.get('requirement_ids',[]))+'\nProject Intelligence plan '+document_id+' revision '+str(revision['number']))[:4000],
                  'owner_id':hub.user_id(owner),'start_date':task.get('start_date') or '', 'due_date':task.get('due_date') or '',
                  'planned_hours':task.get('planned_hours') or 0,'milestone':bool(task.get('milestone')),'work_phase':task.get('phase','development')}
            if task['id'] in links:
                current=hub.item(db,links[task['id']])
                if current['project_id']!=key:raise HTTPException(409,'A task mapping no longer belongs to this project.')
                hub.edit(user,current['id'],{**info,'version':current['version']},transaction=db)
            else:
                created=hub.create(user,{**info,'dependencies':[]},key,transaction=db);links[task['id']]=created['id']
                db.execute('INSERT INTO pi_task_links VALUES(?,?,?)',(document_id,task['id'],created['id']))
        for task in tasks:
            current=hub.item(db,links[task['id']]);hub.edit(user,current['id'],{'dependencies':[links[k] for k in task.get('dependencies',[])],'version':current['version']},transaction=db)
        now=timestamp();db.execute('UPDATE pi_revisions SET applied_at=? WHERE id=?',(now,revision['id']))
        hub.event(db,project,user,'intelligence_plan_applied',{'document_id':document_id,'revision_id':revision['id'],'tasks':links})
        return {'applied_at':now,'task_ids':links}


def save_text(user,key,document_id,payload):
    from .documents import generated_file
    with hub.db() as db:
        store.project(db,key,user,write=True);doc=store.document(db,document_id,key);revision=store.revision(db,doc['current_revision'],document_id)
    if payload.get('version')!=revision['id']:raise HTTPException(409,'This document changed. Refresh before saving.')
    if not revision.get('file_id'):raise HTTPException(400,'Choose a text or CSV source document.')
    row,_=files.file_record(revision['file_id'],key)
    from pathlib import Path
    if Path(row['name']).suffix.lower() not in {'.txt','.csv'}:raise HTTPException(400,'Use the PDF tools or local office editor for this document format.')
    body=text(payload.get('body',''),1000000)
    file=generated_file(user,key,row['name'],body.encode('utf-8'))
    content={**revision['content'],'body':body,'sources':[{'id':file['id']+':1','file_id':file['id'],'filename':row['name'],'text':body,'line':1}]}
    with hub.db(True) as db:doc,rev=store.create_document(db,user,key,'source',doc['title'],content,file_id=file['id'],document_id=document_id,expected_revision=revision['id'])
    return {'document':doc,'revision':rev}
