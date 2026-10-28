"""Explicit FRD links and advisory downstream change impact."""
import json
from fastapi import HTTPException
from . import store,bindings,schema
from .store import hub,pi,quality,identity,timestamp,text
SEMANTIC=('id','title','description','trigger','expected_behavior','acceptance_criteria','subsystem','mandatory')
def requirement_hash(r):return bindings.digest({k:r.get(k) for k in SEMANTIC})

def _requirements(db,did,rid=None):
    row=db.execute('SELECT * FROM pi_documents WHERE id=?',(did,)).fetchone()
    if not row:raise HTTPException(404,'Source FRD document no longer exists.')
    doc=dict(row);rev=pi.revision(db,rid or doc['current_revision'],did)
    return doc,rev,{r['id']:r for r in rev['content'].get('requirements',[])}

def _touch(db,control,rev):
    if control:db.execute('UPDATE qc_revisions SET confirmed_by=NULL,confirmed_at=NULL,confirmed_hash=NULL,version=version+1 WHERE id=?',(rev['id'],))

def add(user,pid,did,payload):
    store.initialize()
    with hub.db(True) as db:
        p,doc,rev,control=store.editable(db,user,pid,did,payload.get('revision_id'),payload.get('version'))
        source_id=schema.string(payload.get('source_document_id'),100);_,source,source_rev,source_control=store.document(db,user,pid,source_id)
        if source_control and source_control['stage']!='frd' or not source_control and source['kind']!='frd':raise HTTPException(400,'Choose a functional requirements document.')
        rid=schema.string(payload.get('requirement_id'),80);requirements={r['id']:r for r in source_rev['content'].get('requirements',[])}
        if rid not in requirements:raise HTTPException(404,'Choose a current FRD requirement.')
        block=schema.key(payload.get('block_id','document'))
        layout=bindings.layout(rev['content'],control['stage'] if control else doc['kind'])
        if block!='document' and not any(b['id']==block for b in layout['blocks']):raise HTTPException(404,'Choose an existing target document block.')
        if any(l['kind']=='content' and l['element_id'] in {'document',block} for l in store.locks(db,rev['id'])):raise HTTPException(423,'Unlock the target content before changing its requirement links.')
        key=identity();db.execute('INSERT INTO ds_links VALUES(?,?,?,?,?,?,?,?,?,?)',(key,did,rev['id'],block,rid,source_id,source_rev['id'],requirement_hash(requirements[rid]),user['id'],timestamp()))
        _touch(db,control,rev);store.audit(db,user,pid,did,rev['id'],'requirement_linked',{'link_id':key,'requirement_id':rid,'source_revision':source_rev['id'],'block_id':block})
    return {'saved':True}

def remove(user,pid,did,key,payload):
    store.initialize()
    with hub.db(True) as db:
        p,doc,rev,control=store.editable(db,user,pid,did,payload.get('revision_id'),payload.get('version'))
        row=db.execute('SELECT * FROM ds_links WHERE id=? AND document_id=? AND revision_id=?',(key,did,rev['id'])).fetchone()
        if not row:raise HTTPException(404,'Link not found in this draft.')
        if any(l['kind']=='content' and l['element_id'] in {'document',row['block_id']} for l in store.locks(db,rev['id'])):raise HTTPException(423,'Unlock this content before removing its requirement link.')
        db.execute('DELETE FROM ds_links WHERE id=?',(key,));_touch(db,control,rev)
        store.audit(db,user,pid,did,rev['id'],'requirement_link_removed',{'link_id':key,'reason':text(payload.get('reason',''),1000,True)})
    return {'saved':True}

def graph(user,pid,did):
    store.initialize()
    with hub.db() as db:
        p,doc,rev,control=store.document(db,user,pid,did);documents=[];links=[];requirements=[];frd=None
        for raw in db.execute('SELECT d.*,q.stage,q.number AS document_number,q.id AS control_id FROM pi_documents d LEFT JOIN qc_documents q ON q.document_id=d.id WHERE d.project_id=?',(pid,)):
            d=dict(raw);r=pi.revision(db,d['current_revision'],d['id']);d['content']=r['content'];d['revision']=r
            documents.append({'id':d['id'],'title':d['title'],'stage':d['stage'] or d['kind'],'number':d['document_number'],'revision_id':r['id'],'revision':r['number'],'status':r['status']})
            if d['stage']=='frd' or d['kind']=='frd':frd=d
        if frd:
            current={r['id']:r for r in frd['content'].get('requirements',[])};requirements=list(current.values())
            for raw in db.execute("SELECT q.*,n.current_revision FROM qc_documents q JOIN pi_documents n ON n.id=q.document_id WHERE q.project_id=? AND q.stage!='frd'",(pid,)):
                d=dict(raw);target=quality.revision(db,d['id'],d['current_revision']);c=pi.revision(db,target['id'],d['document_id'])['content'];base={}
                if target.get('frd_revision_id'):
                    try:_,_,base=_requirements(db,frd['id'],target['frd_revision_id'])
                    except HTTPException:pass
                for group in ('cases','changes'):
                    for item in c.get(group,[]):
                        for rid in item.get('requirement_ids',[]):
                            before=base.get(rid);after=current.get(rid);changed=not after or not before or requirement_hash(before)!=requirement_hash(after)
                            links.append({'id':target['id']+':'+item['id']+':'+rid,'native':True,'source_document_id':frd['id'],'source_revision_id':target.get('frd_revision_id'),'requirement_id':rid,'target_document_id':d['document_id'],'target_revision_id':target['id'],'target':d['number']+' / '+item['id'],'stage':d['stage'],'requires_review':changed,'reason':'Requirement changed or source baseline is not recorded.' if changed else 'The linked requirement matches its recorded FRD baseline.','changed_fields':[k for k in SEMANTIC if before and after and before.get(k)!=after.get(k)]})
        for raw in db.execute('SELECT l.*,d.title AS target_title FROM ds_links l JOIN pi_documents d ON d.id=l.document_id AND d.current_revision=l.revision_id WHERE d.project_id=?',(pid,)):
            value=dict(raw)
            try:source,r,now=_requirements(db,value['source_document_id']);current=now.get(value['requirement_id']);changed=not current or requirement_hash(current)!=value['source_hash'];reason='Requirement changed; review this linked document item.' if changed else 'Requirement matches the linked baseline.'
            except HTTPException:changed=True;reason='The linked FRD or requirement is unavailable.'
            links.append({**value,'native':False,'target_document_id':value['document_id'],'target_revision_id':value['revision_id'],'target':value['target_title']+' / '+value['block_id'],'requires_review':changed,'reason':reason,'stage':'linked item','changed_fields':[]})
        relevant=[link for link in links if link['source_document_id']==did or link['target_document_id']==did]
        return {'documents':documents,'requirements':requirements,'frd_document_id':frd['id'] if frd else None,'links':relevant,'affected':sum(l['requires_review'] for l in relevant),
                'notice':'Draft FRD changes are advisory. Existing approval and test execution checks continue to use their recorded approved baselines.'}
