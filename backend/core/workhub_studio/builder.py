"""Reviewable builder proposals using the existing durable Chopper job engine."""
from copy import deepcopy
import json,re
from fastapi import HTTPException
from . import store,bindings,schema,service
from .store import hub,quality,pi,identity,timestamp,text


def reserved_ids(db,did,binding):
    return store.reserved_ids(db,did,binding)


def append_rows(existing,proposed,fields,prefix,reserved):
    """New proposals retain existing identities and never reuse retired IDs."""
    result=deepcopy(existing);seen={tuple(str(row.get(k) or '').strip().casefold() for k in fields) for row in existing}
    number=max([int(key[len(prefix):]) for key in reserved if re.fullmatch(re.escape(prefix)+r'\d+',key)] or [0])
    for row in proposed:
        signature=tuple(str(row.get(k) or '').strip().casefold() for k in fields)
        if signature in seen:continue
        seen.add(signature);number+=1;result.append({**row,'id':prefix+str(number).zfill(3)})
    return result


def append_notes(existing,proposed,fields):
    result=deepcopy(existing);seen={tuple(str(row.get(k) or '').strip().casefold() for k in fields) for row in existing if isinstance(row,dict)};ids={r.get('id') for r in existing if isinstance(r,dict)}
    for row in proposed:
        signature=tuple(str(row.get(k) or '').strip().casefold() for k in fields)
        if signature in seen:continue
        seen.add(signature);value=deepcopy(row)
        if not value.get('id') or value['id'] in ids:value['id']=identity()
        ids.add(value['id']);result.append(value)
    return result


def ensure_sections(layout,content):
    placed={b['data']['binding'] for b in layout['blocks'] if b['type']=='native_text'}
    for section in content.get('sections',[]):
        binding='section:'+section['id']+':text'
        if binding in placed:continue
        at=next((i for i,b in enumerate(layout['blocks']) if b['type']=='approval'),len(layout['blocks']))
        layout['blocks'][at:at]=[bindings.b('section-title-'+identity(),'heading',{'level':2,'runs':[{'text':section['heading']}]},{'font_size':13,'bold':True}),bindings.b('section-body-'+identity(),'native_text',{'binding':binding,'runs':[{'text':section.get('text','')}],'source_hash':bindings.digest(section.get('text',''))})]

def queue(user,pid,did,payload):
    store.initialize()
    with hub.db() as db:
        p,doc,rev,control=store.editable(db,user,pid,did,payload.get('revision_id'),payload.get('version'))
        options={'document_id':did,'revision_id':rev['id'],'base_hash':bindings.digest(pi.revision(db,rev['id'],did)['content']),
          'kind':control['stage'] if control else doc['kind'],'brief':text(payload.get('brief',''),16000),'language':schema.choice(payload.get('language','auto'),{'auto','en','ta'}),
          'file_ids':schema.seq(payload.get('file_ids',[]),20,'source files'),'meeting_id':payload.get('meeting_id') or None,
          'instruction':text(payload.get('instruction',''),3000),'request_id':text(payload.get('request_id') or identity(),100)}
        if not options['brief'] and not options['file_ids'] and not options['meeting_id']:raise HTTPException(400,'Describe the document, select source files or choose a reviewed meeting transcript.')
    from backend.core.workhub_intelligence import jobs
    return jobs.enqueue(user,pid,'studio_build',options)

def guided(user,pid,did,payload):
    store.initialize()
    with hub.db() as db:
        p,doc,rev,control=store.editable(db,user,pid,did,payload.get('revision_id'),payload.get('version'))
        kind=control['stage'] if control else doc['kind'];c=deepcopy(pi.revision(db,rev['id'],did)['content'])
        goal=text(payload.get('goal',''),8000);behavior=text(payload.get('behavior',''),8000);acceptance=text(payload.get('acceptance',''),8000);source='GUIDED-'+identity()
        if not goal:raise HTTPException(400,'Enter the purpose or meeting topic.')
        c.setdefault('sources',[]).append({'id':source,'type':'user_brief','label':'Guided document input','text':goal+'\n'+behavior+'\n'+acceptance})
        if kind=='frd':
            if not behavior or not acceptance:raise HTTPException(400,'Describe the requested behavior and how it will be accepted.')
            c['purpose']=c.get('purpose') or goal;c['scope']=c.get('scope') or p.get('description') or goal
            c['requirements']=append_rows(c.get('requirements',[]),[{'title':goal[:180],'description':behavior,'trigger':'','expected_behavior':behavior,'acceptance_criteria':acceptance,'subsystem':'','source_ids':[source],'mandatory':True,'change':'new'}],('title','description','expected_behavior','acceptance_criteria'),'FR-',reserved_ids(db,did,'requirements'))
        elif kind=='mom':
            c['meeting_subject']=goal;c['agenda']=c.get('agenda') or goal
            if behavior:c.setdefault('discussion_summary',[]).append({'id':identity(),'topic':goal,'text':behavior,'source_ids':[source]})
            if acceptance:c.setdefault('decisions',[]).append({'id':identity(),'text':acceptance,'source_ids':[source]})
        elif kind in {'test','fat'}:
            if not behavior or not acceptance:raise HTTPException(400,'Describe the test procedure and expected outcome.')
            c['cases']=append_rows(c.get('cases',[]),[{'objective':goal,'procedure':behavior,'expected_result':acceptance,'acceptance_criteria':acceptance,'requirement_ids':[],'source_ids':[source],'mandatory':True}],('objective','procedure','expected_result'),'FAT-' if kind=='fat' else 'TC-',reserved_ids(db,did,'cases'))
        elif kind=='corrections':
            c['changes']=append_rows(c.get('changes',[]),[{'summary':goal,'existing_behavior':behavior,'expected_behavior':acceptance,'verification':'','requirement_ids':[],'source_ids':[source]}],('summary','existing_behavior','expected_behavior'),'CN-',reserved_ids(db,did,'changes'))
        else:
            c['summary']=c.get('summary') or goal
            c.setdefault('sections',[]).append({'id':'section-'+identity(),'heading':goal[:160],'text':behavior+('\n'+acceptance if acceptance else '')})
        layout=bindings.layout(c,kind);ensure_sections(layout,c)
    return service.save(user,pid,did,{'revision_id':rev['id'],'version':rev.get('version'),'etag':bindings.digest(rev['content']),'content':c,'layout':layout})

def process(job,user):
    """Generate a proposal only. Applying it remains a separate checked save."""
    from backend.core.workhub_intelligence import documents,processing
    payload=job.row['payload'];pid=job.row['project_id'];sources=[]
    with hub.db() as db:
        p,doc,rev,control=store.document(db,user,pid,payload['document_id'],payload['revision_id'])
        native=pi.revision(db,rev['id'],doc['id'])
        if doc['current_revision']!=rev['id'] or bindings.digest(native['content'])!=payload['base_hash']:raise ValueError('The document changed before preparation. Start a proposal for its current saved draft.')
        original=deepcopy(native['content']);header=quality.source_header(db,p,quality.policy_row(db,p));used={key:reserved_ids(db,doc['id'],key) for key in ('requirements','cases','changes')}
        if payload.get('meeting_id'):
            meeting=pi.meeting(db,payload['meeting_id'],pid);transcript=json.loads(meeting['transcript'])
            from backend.core.workhub_intelligence.reliability import digest
            review=db.execute('SELECT transcript_hash FROM pi_transcript_reviews WHERE meeting_id=? AND version=?',(meeting['id'],meeting['transcript_version'])).fetchone()
            if not review or review['transcript_hash']!=digest(transcript):raise ValueError('Review and confirm the saved transcript before preparing an English document.')
            for segment in transcript.get('segments',[]):sources.append({'id':meeting['id']+':'+segment['id'],'type':'meeting_transcript','meeting_id':meeting['id'],'transcript_version':meeting['transcript_version'],'segment_id':segment['id'],'text':segment.get('text',''),'original_text':segment.get('original_text',segment.get('text','')),'label':'Original meeting transcript','file_id':meeting['file_id']})
    if payload['brief']:sources.append({'id':'BRIEF-'+payload['request_id'],'type':'user_brief','label':'Original '+('Tamil / English' if payload['language']!='en' else 'English')+' document brief','text':payload['brief']})
    for i,fid in enumerate(payload.get('file_ids',[])):
        job.check();job.progress(8+int(15*i/max(1,len(payload['file_ids']))),'Reading selected document sources')
        value=documents.extract(fid,pid)
        sources.extend(value['sources'])
    if not sources:raise ValueError('The selected sources contain no readable document text.')
    kind=payload['kind'];chunks=list(processing._chunks(sources));merged={k:[] for k in ('requirements','cases','changes','discussion_summary','decisions','actions','clarifications')};summaries=[]
    instruction=('Prepare professional English content from the supplied Tamil/English sources. Retain every number, tag, unit and uncertainty. Return a JSON object with summary, purpose, scope, '
      'requirements:[{title,description,trigger,expected_behavior,acceptance_criteria,subsystem,source_ids}], '
      'cases:[{objective,procedure,expected_result,acceptance_criteria,source_ids}], changes:[{summary,existing_behavior,expected_behavior,verification,source_ids}], '
      'discussion_summary:[{topic,text,decision,responsible,source_ids}], decisions:[{text,source_ids}], actions:[{text,responsible,target_date,source_ids}], clarifications:[{question,source_ids}]. '
      'Use only arrays appropriate to the requested document kind. Every array item needs source_ids. Unknown fields are empty strings or null. Never invent test execution outcomes, signatures or approvals. '
      'Preserve original uncertainty as a clarification. A proposed test is a procedure to perform, not a completed result.')
    for i,chunk in enumerate(chunks):
        job.check();job.progress(25+int(60*i/max(1,len(chunks))),'Organizing editable English sections')
        model=processing.source_model(instruction,{'kind':kind,'project':header,'sources':chunk,'requested_style':payload.get('instruction','')},job.check)
        source_map={s['id']:s for s in chunk}
        for field in merged:
            rows=model.get(field,[])
            for row in rows or []:
                if isinstance(row,dict) and field in {'requirements','cases','changes'}:row.setdefault('text',' '.join(str(row.get(k) or '') for k in ('title','description','objective','procedure','expected_result','acceptance_criteria','summary')))
            merged[field].extend(processing._claims(rows,source_map,field))
        for field in ('summary','purpose','scope'):
            value=str(model.get(field) or '')
            if value:
                unsupported=processing.unsupported_values(' '.join(s['text'] for s in chunk),value)
                if unsupported:raise ValueError('Review unsupported technical values in '+field+': '+', '.join(unsupported[:8]))
                summaries.append((field,value))
    proposal=deepcopy(original);proposal['sources']=list({s['id']:s for s in [*original.get('sources',[]),*sources]}.values())
    if kind=='mom':
        for field in ('discussion_summary','decisions','actions','clarifications'):proposal[field]=append_notes(original.get(field,[]),merged[field],('topic','text','question'))
        for action in proposal['actions'][len(original.get('actions',[])):]:
            supplied=' '.join(s['text'] for s in sources if s['id'] in action.get('source_ids',[]))
            if not isinstance(action.get('responsible'),str) or action['responsible'].casefold() not in supplied.casefold():action['responsible']=None
            if not isinstance(action.get('target_date'),str) or action['target_date'] not in supplied:action['target_date']=None
    elif kind=='frd':
        proposed=[{**{k:str(r.get(k) or '') for k in ('title','description','trigger','expected_behavior','acceptance_criteria','subsystem')},'source_ids':r['source_ids'],'mandatory':True,'change':'new'} for r in merged['requirements']]
        proposal['requirements']=append_rows(original.get('requirements',[]),proposed,('title','description','expected_behavior','acceptance_criteria'),'FR-',used['requirements'])
        if not proposal['requirements']:raise ValueError('The sources did not support a functional requirement. Clarify the brief or enter a guided requirement.')
    elif kind in {'test','fat'}:
        proposed=[{**{k:str(r.get(k) or '') for k in ('objective','procedure','expected_result','acceptance_criteria')},'source_ids':r['source_ids'],'requirement_ids':[],'mandatory':True} for r in merged['cases']]
        proposal['cases']=append_rows(original.get('cases',[]),proposed,('objective','procedure','expected_result'),'FAT-' if kind=='fat' else 'TC-',used['cases'])
    elif kind=='corrections':
        proposed=[{**{k:str(r.get(k) or '') for k in ('summary','existing_behavior','expected_behavior','verification')},'source_ids':r['source_ids'],'requirement_ids':[]} for r in merged['changes']]
        proposal['changes']=append_rows(original.get('changes',[]),proposed,('summary','existing_behavior','expected_behavior'),'CN-',used['changes'])
    for field in ('summary','purpose','scope'):
        values=[v for k,v in summaries if k==field]
        if values:proposal[field]='\n\n'.join(values)
    proposal=bindings.synchronize(proposal)
    return {'document_id':doc['id'],'revision_id':rev['id'],'base_hash':payload['base_hash'],'proposal':proposal,'mode':'Chopper English document proposal','source_count':len(sources),'original_retained':True,'notice':'Review the proposed wording, requirement identities and source text before applying. Test results and approvals are not generated.'}

def apply(user,pid,did,job_id,payload):
    store.initialize()
    with hub.db() as db:
        p,doc,rev,control=store.editable(db,user,pid,did,payload.get('revision_id'),payload.get('version'))
        row=db.execute("SELECT * FROM pi_jobs WHERE id=? AND project_id=? AND kind='studio_build' AND status='completed'",(job_id,pid)).fetchone()
        if not row:raise HTTPException(409,'Choose a completed document builder proposal.')
        result=json.loads(row['result'])
        if result.get('document_id')!=did or result.get('revision_id')!=rev['id'] or result.get('base_hash')!=bindings.digest(pi.revision(db,rev['id'],did)['content']):raise HTTPException(409,'The document changed after this proposal. Review a new proposal for its current draft.')
        content=result['proposal'];layout=bindings.layout(content,control['stage'] if control else doc['kind'])
    if payload.get('confirmed') is not True:raise HTTPException(400,'Review the proposal and original sources before applying it.')
    ensure_sections(layout,content)
    return service.save(user,pid,did,{'revision_id':rev['id'],'version':rev.get('version'),'etag':bindings.digest(rev['content']),'content':content,'layout':layout})
