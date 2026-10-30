"""Versioned layouts and approved reusable content, distinct from project data."""
from copy import deepcopy
import json
from fastapi import HTTPException
from . import store,bindings,schema,media,service
from .store import hub,quality,pi,identity,timestamp,text

def _template_author(user):
    quality.personal(user)


def template_drafts(user):
    _template_author(user);store.initialize()
    with hub.db() as db:
        return {'items':[dict(r) for r in db.execute('SELECT * FROM ds_template_drafts WHERE owner_id=? OR ? ORDER BY created_at DESC LIMIT 200',(user['id'],user['role']=='admin'))]}


def create_template_draft(user,payload):
    from backend.core.workhub_document_spaces import find
    from backend.core.workhub_quality import authoring,documents
    _template_author(user);store.initialize()
    kind=payload.get('kind');name=text(payload.get('name',''),180,True)
    if kind not in {*quality.STAGES,'mom'}:raise HTTPException(400,'Choose a supported document type.')
    with hub.db(True) as db:
        scope=identity();now=timestamp()
        db.execute('INSERT INTO wh_document_spaces(id,title,owner_id,created_at,updated_at) VALUES(?,?,?,?,?)',(scope,'Template: '+name,user['id'],now,now))
        db.execute('INSERT INTO ds_template_drafts VALUES(?,?,?,?,?,?)',(scope,'',kind,name,user['id'],now))
        p=find(db,scope);quality.ensure_project(db,p,user)
        if kind=='mom':
            doc,rev=pi.create_document(db,user,scope,'mom',name,{'meeting_subject':'','participants':[],'discussion_summary':[],'decisions':[],'actions':[],'clarifications':[],'next_meeting_items':[],'engineering_requirements':[],'sources':[]})
        else:
            content=documents.clean_content(db,scope,kind,authoring.blank(kind))
            control=documents.create_control(db,p,user,kind,initial_content=content)
            doc=quality.native(db,control);rev=pi.revision(db,doc['current_revision'],doc['id'])
        db.execute('UPDATE ds_template_drafts SET document_id=? WHERE scope_id=?',(doc['id'],scope))
        store.audit(db,user,scope,doc['id'],rev['id'],'template_design_started',{'kind':kind,'name':name})
    return {'scope_id':scope,'document_id':doc['id'],'kind':kind,'name':name,'owner_id':user['id'],'created_at':now}


def templates(user):
    store.initialize();quality.personal(user)
    with hub.db() as db:
        rows=[dict(r) for r in db.execute('SELECT t.id,t.version,t.name,t.kind,t.owner_id,t.shared,t.locked,t.active,t.created_at FROM ds_templates t JOIN (SELECT id,MAX(version) version FROM ds_templates GROUP BY id) latest ON latest.id=t.id AND latest.version=t.version WHERE t.shared=1 OR t.owner_id=? OR ? ORDER BY t.name',(user['id'],user['role']=='admin'))]
        return {'items':rows}

def save_template(user,pid,did,payload):
    store.initialize()
    with hub.db(True) as db:
        p,doc,rev,control=store.document(db,user,pid,did,payload.get('revision_id'),write=True)
        key=payload.get('id') or identity();old=db.execute('SELECT * FROM ds_templates WHERE id=? ORDER BY version DESC LIMIT 1',(key,)).fetchone()
        if old and user['role']!='admin' and old['owner_id']!=user['id']:raise HTTPException(403,'Only the template owner or Admin may revise this template.')
        if old and old['locked']:raise HTTPException(423,'Unlock the template before revising its layout.')
        if payload.get('version',0)!=(old['version'] if old else 0):raise HTTPException(409,'The reusable template changed. Refresh before saving.')
        layout=schema.normalize(payload.get('layout') or bindings.layout(rev['content'],control['stage'] if control else doc['kind']))
        wrapper={'studio':layout,'assets':media.snapshot(pid,layout),'source_project_id':pid}
        version=(old['version'] if old else 0)+1
        row={'id':key,'version':version,'name':text(payload.get('name',''),180,True),'kind':control['stage'] if control else doc['kind'],'layout':quality.bounded(wrapper,20*1024*1024),'owner_id':old['owner_id'] if old else user['id'],'shared':int(schema.boolean(payload.get('shared',False))),'locked':0,'active':1,'created_at':timestamp()}
        db.execute('INSERT INTO ds_templates VALUES(:id,:version,:name,:kind,:layout,:owner_id,:shared,:locked,:active,:created_at)',row)
        store.audit(db,user,pid,did,rev['id'],'layout_template_saved',{'template_id':key,'version':version,'shared':bool(row['shared'])})
    return {'id':key,'version':version}

def lock_template(user,key,payload):
    store.initialize();quality.personal(user)
    with hub.db(True) as db:
        row=db.execute('SELECT * FROM ds_templates WHERE id=? ORDER BY version DESC LIMIT 1',(key,)).fetchone()
        if not row:raise HTTPException(404,'Template not found.')
        if row['owner_id']!=user['id'] and user['role']!='admin':raise HTTPException(403,'Only the template owner or Admin can change its protection.')
        if payload.get('version')!=row['version']:raise HTTPException(409,'Refresh the current template version.')
        lock=schema.boolean(payload.get('locked'));reason=text(payload.get('reason',''),1000,True)
        # A new protection version preserves all earlier template revisions.
        new={**dict(row),'version':row['version']+1,'locked':int(lock),'created_at':timestamp()}
        db.execute('INSERT INTO ds_templates VALUES(:id,:version,:name,:kind,:layout,:owner_id,:shared,:locked,:active,:created_at)',new)
        store.audit(db,user,None,None,None,'template_locked' if lock else 'template_unlocked',{'template_id':key,'version':new['version'],'reason':reason})
    return {'saved':True,'version':new['version']}

def _apply_layout(current,template,include_design_elements=False):
    """Keep existing content and add reusable elements from Settings template drafts."""
    result=deepcopy(current);result.update({k:deepcopy(template[k]) for k in ('page','header','footer')});remaining=deepcopy(current['blocks']);blocks=[]
    used_ids={b['id'] for b in remaining}
    for slot in template['blocks']:
        binding=slot['data'].get('binding')
        if include_design_elements:
            match=next((b for b in remaining if b['id']==slot['id'] and b['type']==slot['type']),None)
            if not match and binding:match=next((b for b in remaining if b['type']==slot['type'] and b['data'].get('binding')==binding),None)
        else:
            match=next((b for b in remaining if b['type']==slot['type'] and (not binding or b['data'].get('binding')==binding)),None)
        if not match:
            if include_design_elements and not slot['type'].startswith('native_'):
                match=deepcopy(slot)
                if match['id'] in used_ids:match['id']=identity()
                used_ids.add(match['id']);blocks.append(match)
            continue
        match['style']=deepcopy(slot['style'])
        if match['type']=='native_table':match['data'].update({k:deepcopy(v) for k,v in slot['data'].items() if k!='binding'})
        blocks.append(match);remaining.remove(match)
    result['blocks']=[*blocks,*remaining];return result

def apply_template(user,pid,did,key,payload):
    store.initialize()
    with hub.db() as db:
        p,doc,rev,control=store.editable(db,user,pid,did,payload.get('revision_id'),payload.get('version'))
        row=db.execute('SELECT * FROM ds_templates WHERE id=? ORDER BY version DESC LIMIT 1',(key,)).fetchone()
        if not row or not row['active'] or not row['shared'] and row['owner_id']!=user['id'] and user['role']!='admin':raise HTTPException(404,'Reusable template is unavailable.')
        if row['kind']!=(control['stage'] if control else doc['kind']):raise HTTPException(400,'Choose a template for this document type.')
        wrapper=json.loads(row['layout']);current=bindings.layout(rev['content'],control['stage'] if control else doc['kind'])
        is_design=bool(db.execute('SELECT 1 FROM ds_template_drafts WHERE scope_id=?',(wrapper.get('source_project_id',''),)).fetchone())
        result=_apply_layout(current,wrapper['studio'],is_design);result['template_id']=key+':'+str(row['version'])
        store.guard(db,user,rev['id'],{**rev['content'],'studio':current},{**rev['content'],'studio':result})
    result=media.restore(user,pid,result,wrapper.get('assets',{}))
    # Applying is an explicit normal draft save, not a parallel layout store.
    return service.save(user,pid,did,{**payload,'etag':bindings.digest(rev['content']),'content':rev['content'],'layout':result})

def snippets(user,query=''):
    store.initialize();quality.personal(user)
    with hub.db() as db:return {'items':[dict(r) for r in db.execute('SELECT id,title,kind,project_id,document_id,revision_id,source_hash,owner_id,shared,created_at FROM ds_library WHERE (shared=1 OR owner_id=? OR ?) AND title LIKE ? ORDER BY created_at DESC LIMIT 200',(user['id'],user['role']=='admin','%'+text(query,120)+'%'))]}

def save_snippet(user,pid,did,payload):
    store.initialize()
    with hub.db(True) as db:
        p,doc,rev,control=store.document(db,user,pid,did,payload.get('revision_id'))
        if rev['status'] not in store.APPROVED:raise HTTPException(409,'Save reusable content from a reviewed approved revision.')
        shared=schema.boolean(payload.get('shared',False))
        if shared and user['role']!='admin' and user['id'] not in {p['owner_id'],rev.get('owner_id',rev.get('created_by'))}:raise HTTPException(403,'The source author, project owner or Admin must share approved content company-wide.')
        ids=schema.seq(payload.get('block_ids',[]),30,'reusable blocks');layout=bindings.layout(rev['content'],control['stage'] if control else doc['kind'])
        material=bindings.materialize(rev['content'],layout,service.fields(db,p,doc,rev,control))
        chosen=[b for b in material['blocks'] if b['id'] in ids and b['type'] not in {'approval','signature','section_break','page_break'}]
        if not chosen or len(chosen)!=len(ids):raise HTTPException(400,'Choose text, tables, checklists, images or procedures; recorded signatures and approvals cannot be reused.')
        wrapper={'blocks':chosen,'assets':media.snapshot(pid,{**layout,'blocks':chosen,'header':schema.band(),'footer':schema.band()})}
        key=identity();db.execute('INSERT INTO ds_library VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,text(payload.get('title',''),180,True),control['stage'] if control else doc['kind'],pid,did,rev['id'],bindings.digest(rev['content']),quality.bounded(wrapper,20*1024*1024),user['id'],int(shared),timestamp()))
        store.audit(db,user,pid,did,rev['id'],'approved_content_saved',{'library_id':key,'block_ids':ids,'shared':shared})
    return {'id':key}

def insert_snippet(user,pid,did,key,payload):
    store.initialize()
    with hub.db() as db:
        p,doc,rev,control=store.editable(db,user,pid,did,payload.get('revision_id'),payload.get('version'))
        row=db.execute('SELECT * FROM ds_library WHERE id=? AND (shared=1 OR owner_id=? OR ?)',(key,user['id'],user['role']=='admin')).fetchone()
        if not row:raise HTTPException(404,'Reusable content is unavailable.')
        wrapper=json.loads(row['blocks']);layout=bindings.layout(rev['content'],control['stage'] if control else doc['kind']);position=payload.get('after_id');index=next((i+1 for i,b in enumerate(layout['blocks']) if b['id']==position),len(layout['blocks']))
        inserted=deepcopy(wrapper['blocks'])
        for b in inserted:
            b['id']=identity()
            if b['type'] in {'table','checklist'}:
                for cell in b['data']['cells']:cell['id']=identity()
        layout['blocks'][index:index]=inserted
        store.guard(db,user,rev['id'],rev['content'],{**rev['content'],'studio':layout})
    layout=media.restore(user,pid,layout,wrapper.get('assets',{}))
    return service.save(user,pid,did,{**payload,'etag':bindings.digest(rev['content']),'content':rev['content'],'layout':layout})
