"""Local, source-linked meeting analysis and reviewable engineering proposals."""
from copy import deepcopy
import html
import json
from pathlib import Path
import re
from backend.core.workhub import store as hub,identity,timestamp,encode
from backend.core import workhub_files as files
from . import store,documents
from .local_ai import llm_json,transcribe


def _timestamp(value):
    parts=[float(v) for v in value.replace(',','.').split(':')]
    return sum(value*60**index for index,value in enumerate(reversed(parts)))


def transcript_file(file_id,project_id):
    row,path=files.file_record(file_id,project_id);extension=Path(row['name']).suffix.lower()
    if extension in {'.vtt','.srt'}:
        if row['size']>25*1024*1024:raise ValueError('Split transcript files larger than 25 MiB.')
        raw=path.read_text(encoding='utf-8-sig');segments=[]
        pattern=re.compile(r'(?m)^(?P<start>(?:\d{1,3}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*(?P<end>(?:\d{1,3}:)?\d{2}:\d{2}[.,]\d{3})[^\n]*\n(?P<text>[\s\S]*?)(?=\n\s*\n|\Z)')
        for index,match in enumerate(pattern.finditer(raw)):
            if _timestamp(match['end'])<_timestamp(match['start']) or _timestamp(match['end'])>86400:raise ValueError('Transcript cue timestamps must increase and stay within 24 hours.')
            if index>=20000:raise ValueError('Split transcripts longer than 20,000 segments.')
            speaker=re.search(r'<v\s+([^>]+)>',match['text']);body=html.unescape(re.sub(r'<[^>]*>','',match['text'])).strip()
            if body:segments.append({'id':'S'+str(index+1),'start':_timestamp(match['start']),'end':_timestamp(match['end']),
                                     'text':body,'original_text':body,'speaker':speaker[1].strip() if speaker else None,'uncertain':False})
        if not segments:raise ValueError('No timestamped VTT/SRT cues were found in this transcript.')
        return {'segments':segments,'language':'source','duration':max(s['end'] for s in segments),'speaker_note':'Speaker names are retained from explicit VTT voice labels only.'}
    if extension=='.txt':
        if row['size']>25*1024*1024:raise ValueError('Split transcript files larger than 25 MiB.')
        raw=path.read_text(encoding='utf-8-sig');segments=[]
        for line in raw.splitlines():
            if line.strip():segments.append({'id':'S'+str(len(segments)+1),'start':None,'end':None,'text':line.strip(),'original_text':line.strip(),'speaker':None,'uncertain':False})
        if len(segments)>20000:raise ValueError('Split transcripts longer than 20,000 segments.')
        return {'segments':segments,'language':'source','duration':None,'speaker_note':'Plain-text files have no verified timestamps or voice identities.'}
    if extension=='.docx':
        value=documents.extract(file_id,project_id);segments=[]
        for source in value['sources']:
            body=source['text'].strip()
            # Teams-export paragraphs may carry names and timestamps. Preserve
            # everything as supplied; unknown speakers/timestamps stay unknown.
            match=re.match(r'^(?P<speaker>[^:\n]{1,80})\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*$',body)
            if match:segments.append({'id':'S'+str(len(segments)+1),'start':_timestamp(match['time']),'end':None,'speaker':match['speaker'].strip(),'text':body,'original_text':body,'uncertain':False})
            else:segments.append({'id':'S'+str(len(segments)+1),'start':None,'end':None,'speaker':None,'text':body,'original_text':body,'uncertain':False,'paragraph':source.get('paragraph')})
        return {'segments':segments,'language':'source','duration':None,'speaker_note':'DOCX timestamps and speakers are available only where explicitly supplied.'}
    return None


def _chunks(sources,limit=None):
    if limit is None:
        from .local_ai import source_budget
        limit=source_budget()
    chunk=[];size=0
    for source in sources:
        if len(source['text'])>limit:
            parts=[{**source,'id':source['id']+':part'+str(i//limit+1),'text':source['text'][i:i+limit]} for i in range(0,len(source['text']),limit)]
        else:parts=[source]
        for part in parts:
            if chunk and size+len(part['text'])>limit:yield chunk;chunk=[];size=0
            chunk.append(part);size+=len(part['text'])
    if chunk:yield chunk


def _claims(values,source_map,label='item'):
    from .local_ai import ModelOutputError
    if values is None:return []
    if not isinstance(values,list) or len(values)>500:raise ModelOutputError('The local model returned an invalid '+label+' list.')
    result=[]
    for value in values:
        if not isinstance(value,dict):raise ModelOutputError('The local model omitted structured source references for '+label+'.')
        refs=value.get('source_ids',[])
        if not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or ref not in source_map for ref in refs):raise ModelOutputError('The local model supplied a missing or unknown source reference for '+label+'. Review the transcript or retry.')
        supplied=' '.join(str(source_map[ref]['text']) for ref in refs)
        proposed=' '.join(str(value.get(k) or '') for k in ('text','description','trigger','expected_behavior','acceptance_criteria'))
        invented=unsupported_values(supplied,proposed)
        if invented:raise ModelOutputError('The proposal contains technical values or PLC tags absent from its cited sources: '+', '.join(invented[:10])+'. Clarify the source before generating again.')
        result.append(value)
    return result


def _protected_changes(original,interpretation):
    values=set(re.findall(r'\b\d+(?:\.\d+)?\b',original))
    proposed=set(re.findall(r'\b\d+(?:\.\d+)?\b',interpretation))
    tags=set(re.findall(r'\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b',original))
    return sorted((values^proposed)|{tag for tag in tags if tag not in interpretation})


def unsupported_values(source,proposal):
    numbers=lambda s:set(re.findall(r'(?<![\w-])\d+(?:\.\d+)?',s))
    tags=lambda s:set(re.findall(r'\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b',s))
    return sorted((numbers(proposal)-numbers(source))|(tags(proposal)-tags(source)))


def source_model(instruction,payload,check=lambda:None):
    """Use short, unambiguous prompt references; retain exact stored source IDs."""
    sources=payload['sources'];aliases={'SRC'+str(i+1).zfill(3):s['id'] for i,s in enumerate(sources)}
    prompt={**payload,'sources':[{'id':alias,'text':source['text']} for alias,source in zip(aliases,sources)]}
    result=llm_json(instruction,prompt,check)
    def restore(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='source_ids' and isinstance(item,list):value[key]=[aliases.get(ref,ref) if isinstance(ref,str) else ref for ref in item]
                else:restore(item)
        elif isinstance(value,list):
            for item in value:restore(item)
    restore(result);return result


def _save_transcript(db,user,meeting,value,expected):
    current=store.meeting(db,meeting['id'],meeting['project_id'])
    if current['transcript_version']!=expected:raise ValueError('The transcript was edited during processing. Retry using the saved correction.')
    version=expected+1;now=timestamp()
    db.execute('INSERT INTO pi_transcript_history VALUES(?,?,?,?,?)',(meeting['id'],version,store._bounded(value),user['id'],now))
    db.execute("UPDATE pi_meetings SET transcript=?,transcript_version=?,duration=?,status='transcript_ready',updated_at=? WHERE id=?",
               (store._bounded(value),version,value.get('duration'),now,meeting['id']))
    return version


def meeting_job(job,user):
    key=job.row['project_id'];payload=job.row['payload']
    with hub.db() as db:
        meeting=store.meeting(db,payload['meeting_id'],key);project=hub.item(db,key)
        preferences=db.execute('SELECT terminology FROM pi_preferences WHERE project_id=?',(key,)).fetchone()
    if not meeting['file_id']:raise ValueError('Save a recording or transcript before processing this meeting.')
    if meeting['transcript_version']:
        transcript=json.loads(meeting['transcript']);version=meeting['transcript_version']
    else:
        job.progress(5,'Reading the original meeting file')
        transcript=transcript_file(meeting['file_id'],key)
        if transcript is None:
            record,path=files.file_record(meeting['file_id'],key)
            if Path(record['name']).suffix.lower() not in {'.mp3','.wav','.m4a','.mp4','.webm','.ogg'}:raise ValueError('Choose MP3, WAV, M4A, MP4, browser WebM/OGG, VTT or DOCX.')
            transcript=transcribe(path,meeting['language'],json.loads(preferences['terminology']) if preferences else ['PLC','HMI','servo','VFD','Modbus','OPC UA'],job)
        with hub.db(True) as db:version=_save_transcript(db,user,meeting,transcript,0)
    if not transcript.get('segments'):raise ValueError('No speech or transcript text was found. The original file remains saved.')
    # Transcription/import is a complete, independently retryable operation.
    # A reviewed transcript is required before a separate MOM job can use it.
    if job.row['kind']=='transcribe' or payload.get('phase')=='transcribe':
        return {'meeting_id':meeting['id'],'transcript_version':version,'segments':len(transcript['segments']),'requires_review':True}
    with hub.db() as db:
        review=db.execute('SELECT transcript_hash FROM pi_transcript_reviews WHERE meeting_id=? AND version=?',(meeting['id'],version)).fetchone()
    from .reliability import digest
    if not review or review['transcript_hash']!=digest(transcript):raise ValueError('Review and confirm the current saved transcript before generating the MOM.')
    sources=[{'id':meeting['id']+':'+segment['id'],'meeting_id':meeting['id'],'transcript_version':version,'segment_id':segment['id'],
              'start':segment.get('start'),'end':segment.get('end'),'speaker':segment.get('speaker'),'text':segment['text'],'file_id':meeting['file_id']} for segment in transcript['segments']]
    chunks=list(_chunks(sources));all_sources=[];merged={key:[] for key in ('discussion_summary','decisions','engineering_requirements','actions','clarifications','next_meeting_items')};english={};warnings=[]
    for index,chunk in enumerate(chunks):
        job.progress(45+int(40*index/max(len(chunks),1)),'Preparing evidence-linked MOM draft '+str(index+1)+' / '+str(len(chunks)))
        model=llm_json('Create meeting notes. Schema: {"discussion_summary":[{"text":"...","source_ids":["..."]}],"decisions":[{"text":"...","source_ids":["..."]}],'
                       '"engineering_requirements":[{"text":"...","source_ids":["..."]}],"actions":[{"text":"...","responsible":null,"target_date":null,"source_ids":["..."]}],"clarifications":[{"question":"...","options":[],"source_ids":["..."]}],'
                       '"next_meeting_items":[{"text":"...","source_ids":["..."]}],"english_segments":[{"source_id":"...","text":"faithful English interpretation"}]}. '
                       'Use source-language text plus a separate faithful English interpretation. Extract only explicit actions and decisions. Keep unknown responsibilities/dates null. '
                       'Do not infer a deadline from a general target. Ask short clarification questions for missing engineering decisions.',
                       {'project':project['title'],'subject':meeting['subject'],'meeting_date':meeting['meeting_date'] or None,'sources':chunk,'confirmed_answers':confirmed_answers(key)},job.check)
        source_map={s['id']:s for s in chunk};all_sources.extend(chunk)
        for field in merged:merged[field].extend(_claims(model.get(field,[]),source_map,field))
        for value in model.get('english_segments',[]):
            if not isinstance(value,dict) or value.get('source_id') not in source_map:raise ValueError('English interpretation references an unknown transcript segment.')
            interpretation=str(value.get('text',''))[:40000];english[value['source_id']]=interpretation
            changed=_protected_changes(source_map[value['source_id']]['text'],interpretation)
            if changed:warnings.append({'source_id':value['source_id'],'message':'Verify technical values/tags in this interpretation: '+', '.join(changed[:20])})
    for action in merged['actions']:
        source=' '.join(s['text'] for s in all_sources if s['id'] in action['source_ids'])
        person=action.get('responsible')
        if not isinstance(person,str) or person.casefold() not in source.casefold():action['responsible']=None
        due=action.get('target_date')
        if not isinstance(due,str) or due not in source:action['target_date']=None
    content={'project_name':project['title'],'meeting_subject':meeting['subject'],'meeting_date':meeting['meeting_date'] or None,
             'participants':json.loads(meeting['participants']),**merged,'sources':all_sources,'warnings':warnings,
             'transcript_version':version,'notice':'Draft from recorded conversation. Review technical values, decisions, responsibilities and dates before approval.'}
    # Interpretations are additional evidence, never replacements for original
    # speech. Preserve corrections and every prior transcript version.
    updated=deepcopy(transcript)
    for segment in updated['segments']:
        segment['english']='\n'.join(value for source_id,value in english.items() if source_id==meeting['id']+':'+segment['id'] or source_id.startswith(meeting['id']+':'+segment['id']+':part'))
        segment['interpretation_uncertain']=any(w['source_id'].startswith(meeting['id']+':'+segment['id']) for w in warnings)
    with hub.db(True) as db:
        job.check()
        latest=store.meeting(db,meeting['id'],key)
        if latest['transcript_version']!=version:raise ValueError('The transcript changed during MOM generation. Retry using the latest correction.')
        _save_transcript(db,user,meeting,updated,version)
        doc,rev=store.create_document(db,user,key,'mom','MOM — '+meeting['subject'],content,meeting_id=meeting['id'],generated_by=job.row['id'])
        for question in merged['clarifications']:store.add_clarification(db,key,question.get('question',''),question.get('options'),question['source_ids'])
        db.execute("UPDATE pi_meetings SET status='draft_ready',updated_at=? WHERE id=?",(timestamp(),meeting['id']))
    return {'meeting_id':meeting['id'],'document_id':doc['id'],'revision_id':rev['id'],'warnings':len(warnings)}


def confirmed_answers(project_id):
    with hub.db() as db:return [{'id':'clarification:'+row['id'],'question':row['question'],'answer':row['answer'],'file_id':row['file_id']} for row in db.execute("SELECT * FROM pi_clarifications WHERE project_id=? AND status='confirmed' ORDER BY updated_at",(project_id,))]


def approved_sources(project_id,payload,include_frd=False):
    values=[]
    with hub.db() as db:
        query="SELECT * FROM pi_documents WHERE project_id=? AND approved_revision IS NOT NULL AND kind IN ('mom','source'"+(",'frd'" if include_frd else '')+") ORDER BY updated_at DESC LIMIT 100"
        for row in db.execute(query,(project_id,)):
            if payload.get('document_ids') and row['id'] not in payload['document_ids']:continue
            rev=store.revision(db,row['approved_revision'],row['id']);content=rev['content']
            # An approved MOM/FRD is itself reviewed evidence. Carry its source
            # links while preserving the exact approved revision identity.
            if row['kind'] in {'mom','frd'}:
                if row['kind']=='mom':
                    # A meeting decision often names a signal that a later item
                    # calls "the alarm". Keep the approved MOM revision as one
                    # coherent source, retaining its exact upstream references.
                    # Repeated summary/decision/requirement text is sent once.
                    statements=[];seen=set();upstream=[]
                    for field in ('engineering_requirements','decisions','discussion_summary','actions'):
                        for section in content.get(field,[]):
                            upstream.extend(section.get('source_ids',[]));value={k:v for k,v in section.items() if k!='source_ids'}
                            signature=json.dumps(value,ensure_ascii=False,sort_keys=True)
                            if signature not in seen:seen.add(signature);statements.append(value)
                    if statements:values.append({'id':rev['id']+':mom','document_id':row['id'],'revision_id':rev['id'],
                        'text':json.dumps({'approved_meeting_statements':statements},ensure_ascii=False),'filename':row['title'],
                        'upstream_sources':list(dict.fromkeys(upstream)),'transcript_version':content.get('transcript_version')})
                    continue
                sections=[r for r in content.get('requirements',[]) if r.get('change')!='removed_proposed']
                for index,section in enumerate(sections):
                    values.append({'id':rev['id']+':item'+str(index+1),'document_id':row['id'],'revision_id':rev['id'],
                                   'text':json.dumps({k:v for k,v in section.items() if k!='source_ids'},ensure_ascii=False),'filename':row['title'],'upstream_sources':section.get('source_ids',[])})
            else:
                for source in content.get('sources',[]):values.append({**source,'id':rev['id']+':'+source['id'],'document_id':row['id'],'revision_id':rev['id']})
    for answer in confirmed_answers(project_id):values.append({**answer,'text':answer['question']+'\nConfirmed answer: '+answer['answer']})
    if not values:raise ValueError('Approve a MOM or extracted source document before generating the FRD or project plan.')
    return values


def requirement_job(job,user):
    key=job.row['project_id'];sources=approved_sources(key,job.row['payload']);project_name=''
    with hub.db() as db:
        project=hub.item(db,key);project_name=project['title'];doc=db.execute("SELECT * FROM pi_documents WHERE project_id=? AND kind='frd' ORDER BY created_at LIMIT 1",(key,)).fetchone()
        baseline=store.revision(db,doc['approved_revision'],doc['id']) if doc and doc['approved_revision'] else None
        header={}
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_projects'").fetchone():
            from backend.core.workhub_quality import store as quality_store
            header=quality_store.source_header(db,project,quality_store.policy_row(db,project))
    previous=(baseline or {}).get('content',{}).get('requirements',[]);requirements={r['id']:{**deepcopy(r),'change':'unchanged'} for r in previous};next_id=max([int(r['id'].split('-')[-1]) for r in previous]+[0])+1
    all_sources=[];chunks=list(_chunks(sources));seen=set();clarifications=[]
    for index,chunk in enumerate(chunks):
        job.progress(10+int(70*index/max(1,len(chunks))),'Comparing requirements with the approved FRD')
        instruction=('Extract requirements from reviewed evidence and compare with existing approved requirements. Schema: '
            '{"requirements":[{"existing_id":null,"change":"new|modified|confirmed|removed_proposed|unresolved","title":"...","description":"...",'
            '"trigger":null,"expected_behavior":null,"subsystem":null,"acceptance_criteria":null,"source_ids":["..."]}],"clarifications":[{"question":"...","options":[],"source_ids":["..."]}]}. '
            'Use an existing_id only for an existing requirement. A requirement not mentioned in this meeting stays unchanged. Propose removal only if the supplied evidence explicitly requests its removal. '
            'Unknown criteria and conditions stay null. Preserve every technical value and tag. '
            'Merge repeated statements into one requirement with all supporting source IDs. Keep titles short and each description and criterion to one concise sentence; do not repeat the same engineering behavior as multiple requirements. '
            'Every technical tag and number must occur literally in at least one of the cited source texts; cite all sources needed for the requirement.')
        prompt={'project':project_name,'sources':chunk,'approved_requirements':previous}
        if not previous:
            instruction=('Extract explicit functional requirements from the sources. Return JSON only: '
              '{"requirements":[{"change":"new","title":"short title","description":"one concise sentence","trigger":null,"expected_behavior":null,"acceptance_criteria":null,"source_ids":["SRC001"]}],"clarifications":[]}. '
              'Keep each requirement under 45 words. Merge repeated statements; do not duplicate requirements. '
              'Do not invent technical values, tags, test criteria or conditions. Unknown fields are null. '
              'Every tag/number must occur literally in a cited source; cite all necessary sources. Do not copy source metadata into the output.')
        result=source_model(instruction,prompt,job.check)
        mapping={s['id']:s for s in chunk};all_sources.extend(chunk)
        from .local_ai import ModelOutputError
        try:proposals=_claims(result.get('requirements',[]),mapping,'requirement')
        except ModelOutputError as error:
            # One bounded correction, still validated against the same sources.
            # Neither the first proposal nor an invalid correction is saved.
            result=source_model(instruction,{**prompt,'validation_error':str(error),'correction':'Correct the cited references or omit the unsupported claim. Never invent a missing value.'},job.check)
            proposals=_claims(result.get('requirements',[]),mapping,'requirement')
        for item in proposals:
            change=item.get('change');old=item.get('existing_id')
            if change not in {'new','modified','confirmed','removed_proposed','unresolved'}:raise ValueError('The local model returned an unknown requirement change class.')
            if old and old not in requirements:raise ValueError('The local model referenced an unknown approved requirement.')
            signature=json.dumps([old,item.get('title'),item.get('description'),change],ensure_ascii=False)
            if signature in seen:continue
            seen.add(signature)
            if not old:
                old='FR-'+str(next_id).zfill(3);next_id+=1
                if change not in {'new','unresolved'}:raise ValueError('A modified or removed requirement must identify its approved baseline.')
            if change=='confirmed':requirements[old]={**requirements[old],'change':'confirmed','source_ids':list(dict.fromkeys(requirements[old].get('source_ids',[])+item['source_ids']))};continue
            requirements[old]={'id':old,'title':str(item.get('title',''))[:240],'description':str(item.get('description',''))[:8000],
                              **{k:item.get(k) for k in ('trigger','expected_behavior','subsystem','acceptance_criteria')},'change':change,'source_ids':item['source_ids'],'status':'draft'}
        with hub.db(True) as db:
            for question in _claims(result.get('clarifications',[]),mapping,'clarification'):
                clarifications.append(question);store.add_clarification(db,key,question.get('question',''),question.get('options'),question['source_ids'])
    content={'project_name':project_name,'requirements':list(requirements.values()),'sources':all_sources+(baseline or {}).get('content',{}).get('sources',[]),
             'base_approved_revision':(baseline or {}).get('id'),'notice':'Requirement changes are proposals until this revision is reviewed and approved. Unmentioned approved requirements are retained.'}
    prior=(baseline or {}).get('content',{})
    content.update(purpose=prior.get('purpose') or project.get('description') or '',scope=prior.get('scope') or header.get('scope') or '',acceptance_summary=prior.get('acceptance_summary') or '',
      sections=[{'heading':'Machine / system details','text':header.get('machine') or header.get('machine_name') or 'Not specified in reviewed project information.'},
        {'heading':'Operating sequence','text':'Review the linked functional flowchart and its source requirements. Unconfirmed conditions require engineering clarification.'},
        {'heading':'PLC / HMI behavior, interlocks and alarms','text':'See the source-linked functional requirements and their acceptance criteria.'},
        {'heading':'Open clarifications','text':'\n'.join(q.get('question','') for q in clarifications) or 'Review the project clarification list before approval.'}])
    store.validate_content('frd',content)
    with hub.db(True) as db:
        current=db.execute("SELECT * FROM pi_documents WHERE project_id=? AND kind='frd' ORDER BY created_at LIMIT 1",(key,)).fetchone()
        if (current['approved_revision'] if current else None)!=(baseline or {}).get('id'):raise ValueError('The approved FRD changed during generation. Retry against the new baseline.')
        doc,rev=store.create_document(db,user,key,'frd','Functional Requirements Document',content,generated_by=job.row['id'])
    return {'document_id':doc['id'],'revision_id':rev['id']}


def layout_graph(nodes,edges):
    ids={n['id'] for n in nodes};parents={k:set() for k in ids}
    for edge in edges:
        if edge.get('source') in ids and edge.get('target') in ids:parents[edge['target']].add(edge['source'])
    remaining=set(ids);levels={};level=0
    while remaining:
        ready=sorted(k for k in remaining if not (parents[k]&remaining))
        if not ready:ready=[sorted(remaining)[0]] # Explicit loops remain editable.
        for index,key in enumerate(ready):levels[key]={'x':index*280,'y':level*180}
        remaining.difference_update(ready);level+=1
    return [{**n,'position':levels[n['id']]} for n in nodes]


def generation_job(job,user):
    key=job.row['project_id'];kind=job.row['kind'];payload=job.row['payload']
    if not payload.get('document_ids'):
        with hub.db() as db:
            frd=db.execute("SELECT id FROM pi_documents WHERE project_id=? AND kind='frd' AND approved_revision IS NOT NULL ORDER BY updated_at DESC LIMIT 1",(key,)).fetchone()
            if frd:payload={**payload,'document_ids':[frd['id']]}
    sources=approved_sources(key,payload,include_frd=True)
    # Long source sets are summarized into bounded reviewed requirements rather
    # than silently cutting off the tail of a specification.
    if sum(len(s['text']) for s in sources)>45000:raise ValueError('Select fewer approved source documents or generate an approved FRD first; this proposal exceeds the local model context budget.')
    instruction=('Generate an editable '+str(payload.get('flow_kind') or 'engineering flowchart')[:80]+'. Schema: {"title":"...","nodes":[{"id":"n1","data":{"label":"...","kind":"start|end|process|decision","requirement_ids":["FR-001"],"source_ids":["..."]}}],'
                 '"edges":[{"id":"e1","source":"n1","target":"n2","label":"Yes"}]}. Every node needs actual source references. Keep unknown conditions marked clarification needed. Never claim this is validated PLC logic.') if kind=='flowchart' else (
                 'Propose an engineering project plan based on approved requirements. Schema: {"title":"...","tasks":[{"id":"t1","title":"...","phase":"development|quality|release",'
                 '"owner_id":null,"start_date":null,"due_date":null,"planned_hours":0,"milestone":false,"dependencies":[],"requirement_ids":[],"source_ids":["..."]}],'
                 '"risks":[{"text":"...","source_ids":["..."]}]}. Use only relevant activities. Dates/durations not explicitly confirmed are proposals; never invent an assignee. Do not schedule official WorkHub tasks.')
    job.progress(25,'Preparing an editable '+('flowchart' if kind=='flowchart' else 'timeline and roadmap proposal'))
    result=llm_json(instruction,{'sources':sources,'confirmed_answers':confirmed_answers(key),'activity_templates':payload.get('templates',[])},job.check)
    mapping={s['id']:s for s in sources}
    if kind=='flowchart':
        nodes=_claims(result.get('nodes',[]),mapping,'flowchart node') if all('source_ids' in n for n in result.get('nodes',[])) else result.get('nodes',[])
        for node in nodes:_claims([node.get('data',{})],mapping,'flowchart node')
        content={'nodes':layout_graph(nodes,result.get('edges',[])),'edges':result.get('edges',[]),'sources':sources,'notice':'Engineering diagram draft. This sequence has not been validated as PLC logic.'}
    else:
        tasks=_claims(result.get('tasks',[]),mapping,'planned task')
        for task in tasks:
            task['owner_id']=None;task['proposed']=True;task['phase']=task.get('phase') if task.get('phase') in {'development','quality','release'} else 'development'
            task['planned_hours']=max(0,min(100000,float(task.get('planned_hours') or 0)))
            task['milestone']=bool(task.get('milestone'))
        content={'tasks':tasks,'risks':_claims(result.get('risks',[]),mapping,'risk'),'sources':sources,'notice':'Proposed plan only. Review assignments, dates and estimates, approve the revision and confirm before applying to WorkHub.'}
    store.validate_content(kind,content)
    with hub.db(True) as db:doc,rev=store.create_document(db,user,key,kind,str(result.get('title') or ('Engineering flowchart' if kind=='flowchart' else 'Project execution plan'))[:240],content,generated_by=job.row['id'])
    return {'document_id':doc['id'],'revision_id':rev['id']}


def document_job(job,user):
    payload=job.row['payload'];key=job.row['project_id'];kind=job.row['kind'];ids=payload.get('file_ids',[])
    if not ids:raise ValueError('Choose an uploaded project document.')
    new_file=None
    # A conversion may have committed its durable output before the old worker
    # stopped. Reuse it before invoking OCR/LibreOffice again.
    with hub.db() as db:
        saved=db.execute('SELECT f.* FROM pi_job_outputs o JOIN files f ON f.id=o.file_id WHERE o.job_id=? AND f.project_id=? LIMIT 1',(job.row['id'],key)).fetchone()
    if saved and kind in {'pdf','ocr','convert'}:
        row,path=files.file_record(saved['id'],key)
        from .cache import _file_hash
        if _file_hash(path)!=row['sha256']:raise ValueError('The committed conversion output failed integrity verification.')
        ids=[saved['id']]
    elif kind in {'pdf','ocr','convert'}:
        from .cache import compute,_file_hash
        from .reliability import digest
        inputs=[files.file_record(fid,key)[0] for fid in ids]
        if sum(r['size'] for r in inputs)>256*1024*1024:raise ValueError('Select conversion/PDF inputs below 256 MiB in total.')
        options={k:v for k,v in payload.items() if k not in {'file_ids','document_id','version','reason'}}
        cache_key=digest({'processor':'transform-v1','kind':kind,'inputs':[{k:r[k] for k in ('sha256','name')} for r in inputs],'options':options})
        def transform():
            if kind in {'pdf','ocr'}:
                data,name=documents.pdf_operation(key,{**payload,'action':'ocr' if kind=='ocr' else payload.get('action')},job)
            else:
                row,path=files.file_record(ids[0],key)
                if row['size']>documents.MAX_DOCUMENT:raise ValueError('Convert documents up to the processing file-size limit.')
                extension=payload.get('format','pdf');data=documents.office_convert(path,extension,Path(row['name']).suffix);name=Path(row['name']).stem+'.'+extension
            return documents.generated_file(user,key,name,data)
        new_file,_=compute(key,cache_key,'transform-v1',transform,job.check)
        row,path=files.file_record(new_file['id'],key)
        if _file_hash(path)!=row['sha256']:raise ValueError('The reusable transformation failed integrity verification.')
        with hub.db(True) as db:db.execute('INSERT OR IGNORE INTO pi_job_outputs(job_id,slot,file_id) VALUES(?,?,?)',(job.row['id'],row['name'],row['id']))
        ids=[row['id']]
    job.progress(65,'Extracting source text and references locally')
    extracted=documents.extract(ids[0],key,job.check)
    title=files.file_record(ids[0],key)[0]['name']
    content={'filename':title,'body':extracted['text'][:40000],'body_is_preview':len(extracted['text'])>40000,'sources':extracted['sources'],'notices':extracted['notices'],'coverage_limited':extracted['coverage_limited']}
    with hub.db(True) as db:
        doc,rev=store.create_document(db,user,key,'source',title,content,file_id=ids[0],generated_by=job.row['id'],document_id=payload.get('document_id'),expected_revision=payload.get('version'))
    return {'document_id':doc['id'],'revision_id':rev['id'],'file_id':ids[0]}


def answer_job(job,user):
    key=job.row['project_id'];payload=job.row['payload'];sources=[]
    if not payload.get('document_id'):sources=approved_sources(key,payload,include_frd=True)
    else:
        with hub.db() as db:
            doc=store.document(db,payload['document_id'],key);rev=store.revision(db,payload.get('revision_id') or doc['current_revision'],doc['id'])
            def add_revision(value,caption):
                if doc['kind']=='source':
                    for source in value['content'].get('sources',[]):sources.append({**source,'id':value['id']+':'+source['id'],'document_id':doc['id'],'revision_id':value['id'],'revision_label':caption})
                else:sources.append({'id':value['id'],'document_id':doc['id'],'revision_id':value['id'],'revision_label':caption,'text':json.dumps(value['content'],ensure_ascii=False)})
            add_revision(rev,'Selected revision '+str(rev['number']))
            if payload.get('compare_previous'):
                previous=db.execute('SELECT id FROM pi_revisions WHERE document_id=? AND number<? ORDER BY number DESC LIMIT 1',(doc['id'],rev['number'])).fetchone()
                if not previous:raise ValueError('This document has no earlier revision to compare.')
                add_revision(store.revision(db,previous['id'],doc['id']),'Previous revision')
            if payload.get('compare_frd'):
                frd=db.execute("SELECT * FROM pi_documents WHERE project_id=? AND kind='frd' AND approved_revision IS NOT NULL LIMIT 1",(key,)).fetchone()
                if not frd:raise ValueError('Approve an FRD before comparing this document with its baseline.')
                approved=store.revision(db,frd['approved_revision'],frd['id'])
                for requirement in approved['content'].get('requirements',[]):sources.append({'id':approved['id']+':'+requirement['id'],'document_id':frd['id'],'revision_id':approved['id'],'text':json.dumps(requirement,ensure_ascii=False)})
    if sum(len(s['text']) for s in sources)>45000:raise ValueError('Select a smaller source document or a reviewed FRD for this question.')
    result=llm_json('Answer the engineering question using supplied sources. Schema: {"answer":"...","source_ids":["..."],"clarifications":[{"question":"...","options":[],"source_ids":["..."]}]}. State missing evidence plainly. Provide source IDs for the answer.',
                    {'question':str(payload.get('question',''))[:4000],'sources':sources,'confirmed_answers':confirmed_answers(key)},job.check)
    _claims([result],{s['id']:s for s in sources},'document answer')
    with hub.db(True) as db:
        for question in _claims(result.get('clarifications',[]),{s['id']:s for s in sources},'clarification'):store.add_clarification(db,key,question['question'],question.get('options'),question['source_ids'])
    return {'document_id':payload.get('document_id'),'question':str(payload.get('question',''))[:4000],'answer':str(result.get('answer',''))[:16000],'source_ids':result['source_ids'],'sources':[{**s,'text':s['text'][:2000]} for s in sources if s['id'] in result['source_ids']]}


def process(job,user):
    if job.row['kind']=='studio_build':
        from backend.core.workhub_studio.builder import process as studio_build
        return studio_build(job,user)
    if job.row['kind'] in {'export','q_export'}:
        from .exports import process as export_process
        return export_process(job,user)
    if job.row['kind'].startswith('q_'):
        from backend.core.workhub_quality.processing import process as quality_process
        return quality_process(job,user)
    with hub.db() as db:
        existing=db.execute('SELECT r.id,r.document_id FROM pi_revisions r JOIN pi_documents d ON d.id=r.document_id WHERE r.generated_by=? AND d.project_id=?',(job.row['id'],job.row['project_id'])).fetchone()
        if existing:return {'document_id':existing['document_id'],'revision_id':existing['id'],'recovered':True}
    kind=job.row['kind']
    if kind in {'meeting','transcribe'}:return meeting_job(job,user)
    if kind=='diagram_assist':
        from backend.core.workhub_diagrams import generate_job
        return generate_job(job,user)
    if kind=='frd':return requirement_job(job,user)
    if kind in {'flowchart','plan'}:return generation_job(job,user)
    if kind in {'extract','ocr','pdf','convert'}:return document_job(job,user)
    if kind in {'document_answer','clarifications'}:return answer_job(job,user)
    raise ValueError('Unknown Project Intelligence job.')
