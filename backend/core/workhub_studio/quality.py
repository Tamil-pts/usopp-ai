"""Actionable preflight checks for saved and unsaved document content."""
import json,re
from fastapi import HTTPException
from . import store,schema,bindings

def inspect(db,p,doc,rev,control,content=None):
    c=content if content is not None else rev['content'];issues=[];kind=control['stage'] if control else doc['kind']
    def add(code,message,block='',severity='error'):issues.append({'code':code,'message':message,'block_id':block,'severity':severity})
    def unique(values,label):
        ids=[r.get('id') for r in values if isinstance(r,dict)]
        if len(ids)!=len(set(ids)):add('duplicate:'+label,'Duplicate '+label+' IDs. Give every item a stable unique ID.')
    unique(c.get('requirements',[]),'requirement');unique(c.get('cases',[]),'test case')
    if kind=='frd':
        if not c.get('requirements'):add('mandatory:requirements','Add at least one functional requirement.','native-requirements')
        for r in c.get('requirements',[]):
            if not r.get('title') or not r.get('acceptance_criteria'):add('requirement:'+str(r.get('id')),str(r.get('id','Requirement'))+': complete the title and acceptance criterion.','native-requirements')
    if kind in {'test','fat'}:
        if not c.get('cases'):add('mandatory:cases','Add test procedures and expected results.','native-cases')
        for r in c.get('cases',[]):
            missing=[k.replace('_',' ') for k in ('objective','procedure','expected_result','acceptance_criteria') if not r.get(k)]
            if missing:add('case:'+str(r.get('id')),str(r.get('id'))+': missing '+', '.join(missing)+'.','native-cases')
    if kind=='mom':
        if not (c.get('meeting_subject') or doc.get('title')):add('mandatory:meeting','Enter the meeting title.','native-meeting_subject')
        if not any(c.get(k) for k in ('discussion_summary','decisions','actions')):add('mandatory:discussion','Record the meeting discussion, decisions or action items.','native-discussion_summary')
    source_ids={s.get('id') for s in c.get('sources',[])}
    for name in ('requirements','cases','changes','actions','decisions','discussion_summary','engineering_requirements'):
        for r in c.get(name,[]):
            if not isinstance(r,dict):continue
            if any(k not in source_ids for k in r.get('source_ids',[])):add('broken:source','An item references an unavailable source.','native-'+name)
    if control:
        frd=db.execute("SELECT n.current_revision,n.approved_revision FROM qc_documents q JOIN pi_documents n ON n.id=q.document_id WHERE q.project_id=? AND q.stage='frd'",(p['id'],)).fetchone()
        if frd and kind!='frd':
            base=frd['approved_revision'] or frd['current_revision'];source=json.loads(db.execute('SELECT content FROM pi_revisions WHERE id=?',(base,)).fetchone()[0]);known={r['id'] for r in source.get('requirements',[])}
            for name in ('cases','changes'):
                for r in c.get(name,[]):
                    if any(k not in known for k in r.get('requirement_ids',[])):add('broken:requirement',str(r.get('id'))+': a linked FRD requirement is missing from the current baseline.','native-'+name)
            if kind in {'test','fat'} and frd['approved_revision'] and rev.get('frd_revision_id')!=frd['approved_revision']:add('stale:revision','This report is based on an older approved FRD. Prepare and review its successor revision.')
    studio=c.get('studio')
    if studio:
        try:layout=schema.normalize(studio)
        except HTTPException as exc:layout=None;add('format:layout',str(exc.detail))
        if layout:
            shown={b['data'].get('binding') for b in layout['blocks'] if b['style']['visible']}
            required='requirements' if kind=='frd' else 'cases' if kind in {'test','fat'} else 'changes' if kind=='corrections' and c.get('applicability')!='not_applicable' else None
            if required and c.get(required) and required not in shown:add('format:unplaced','The '+required+' exist but are absent from the visible document layout. Insert their connected table.','native-'+required)
            for b in layout['blocks']:
                if b['type']=='image' and b['data']['source']=='file' and not b['data']['file_id']:add('format:image','Choose a file for this image or remove the empty image element.',b['id'])
                if b['type']=='native_text' and b['data']['source_hash']!=bindings.digest(bindings.text_value(c,b['data']['binding'])):add('format:binding','Refresh this native text block after changes made in another editor.',b['id'])
                if b['type'] in {'paragraph','panel','heading'}:
                    literal=schema.plain(b['data'].get('runs',[]));mentions=re.findall(r'\bRev(?:ision)?\s+(\d{2,4})\b',literal,re.I)
                    if mentions and any(int(n)!=max(0,rev['number']-1) for n in mentions):add('format:revision','A typed revision number differs from this revision. Check the wording or insert a dynamic Revision field.',b['id'],'warning')
    reviewer=p.get('release_id') if kind=='closure' else p.get('quality_id')
    if not reviewer or p.get('is_document_space') and not p.get('reviewer_id'):add('approval:reviewer','Assign the document reviewer before submission.')
    if store.exists(db):
        for r in db.execute("SELECT id,block_id,kind,status FROM ds_comments WHERE document_id=? AND kind IN ('correction','clarification') AND status!='resolved'",(doc['id'],)):
            add('review:'+r['id'],'Resolve the open '+r['kind']+' before submitting this document.',r['block_id'])
    return {'ready':not any(i['severity']=='error' for i in issues),'issues':issues,'errors':sum(i['severity']=='error' for i in issues),'warnings':sum(i['severity']=='warning' for i in issues)}

def preflight(user,pid,did,payload=None):
    store.initialize()
    with store.hub.db() as db:
        p,doc,rev,control=store.document(db,user,pid,did,(payload or {}).get('revision_id'))
        content=(payload or {}).get('content',rev['content'])
        if (payload or {}).get('layout'):content={**content,'studio':payload['layout']}
        return inspect(db,p,doc,rev,control,content)

def assert_ready(db,p,doc,rev,control=None):
    if not rev['content'].get('studio') and not store.exists(db):return
    # Existing documents retain their established workflow; Studio-specific
    # required layout checks begin when a Studio layout or review is recorded.
    if not rev['content'].get('studio') and not db.execute("SELECT 1 FROM ds_comments WHERE document_id=? AND status!='resolved' AND kind IN ('correction','clarification')",(doc.get('document_id',doc['id']),)).fetchone():return
    native=store.pi.document(db,doc['document_id'],p['id']) if control else doc
    result=inspect(db,p,native,rev,control,rev['content'])
    if not result['ready']:raise HTTPException(409,'Document quality check: '+'; '.join(i['message'] for i in result['issues'] if i['severity']=='error')[:1800])
