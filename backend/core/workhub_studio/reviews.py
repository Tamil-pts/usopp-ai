"""Comments anchored to revision text, cells and stable block IDs."""
from fastapi import HTTPException
from . import store,bindings,schema
from .store import hub,quality,pi,identity,timestamp,text

def anchor_text(content,layout,block_id,cell_id='',fields=None):
    block=next((b for b in layout['blocks'] if b['id']==block_id),None)
    if not block:
        if block_id=='document':return str(content.get('summary') or '')
        raise HTTPException(404,'The comment target no longer exists.')
    if block['type']=='field':return str((fields or {}).get(block['data']['field'],''))
    if block['type']=='metadata':
        materialized=bindings.materialize(content,{'blocks':[block]},fields or {})['blocks'][0]
        return next((schema.plain(c['runs']) for c in materialized['data']['cells'] if c['id']==cell_id),'')
    if block['type']=='native_table' and cell_id:
        table=bindings.native_table(content,block['data']['binding'])
        for row in table['rows']:
            for i,col in enumerate(table['columns']):
                if cell_id==row['id']+':'+col['field']:return row['cells'][i]
        raise HTTPException(404,'The table cell no longer exists.')
    if block['type'] in {'table','checklist'} and cell_id:
        cell=next((c for c in block['data']['cells'] if c['id']==cell_id),None)
        if not cell:raise HTTPException(404,'The table cell no longer exists.')
        return schema.plain(cell['runs'])
    return schema.plain(block['data'].get('runs',[])) or block['data'].get('caption','')

def add(user,pid,did,payload):
    store.initialize()
    with hub.db(True) as db:
        p,doc,rev,control=store.document(db,user,pid,did,payload.get('revision_id'),write=True)
        kind=schema.choice(payload.get('kind','comment'),{'comment','correction','clarification'});block_id=schema.key(payload.get('block_id','document'));cell=schema.string(payload.get('cell_id',''),160)
        from .service import fields
        layout=bindings.layout(rev['content'],control['stage'] if control else doc['kind']);original=anchor_text(rev['content'],layout,block_id,cell,fields(db,p,doc,rev,control))
        start=schema.number(payload.get('start_offset',0),0,len(original),True);end=schema.number(payload.get('end_offset',start),start,len(original),True)
        quote=text(payload.get('quote',''),4000)
        if quote and original[start:end]!=quote:raise HTTPException(409,'The selected text changed. Save the document, then select the current text before commenting.')
        assignee=payload.get('assignee_id') or None
        if assignee:hub.user_id(assignee)
        value={'id':identity(),'document_id':did,'revision_id':rev['id'],'block_id':block_id,'cell_id':cell,'start_offset':start,'end_offset':end,'quote':quote,'source_hash':bindings.digest(original),
          'kind':kind,'body':text(payload.get('body',''),4000,True),'assignee_id':assignee,'due_date':store.pi.day(payload.get('due_date','')),'status':'open','version':1,'author_id':user['id'],'created_at':timestamp(),'updated_at':timestamp(),'resolved_by':None,'resolved_at':None}
        db.execute('INSERT INTO ds_comments VALUES('+','.join(':'+k for k in value)+')',value)
        db.execute('INSERT INTO ds_comment_events VALUES(?,?,?,?,?,?)',(identity(),value['id'],user['id'],'created',value['body'],timestamp()))
        store.audit(db,user,pid,did,rev['id'],'review_comment_created',{'comment_id':value['id'],'kind':kind,'block_id':block_id,'assignee_id':assignee})
        if assignee:hub.notify(db,p,user['id'],[assignee],'Document '+kind+': '+doc['title'],value['body'])
    return value

def update(user,pid,did,key,payload):
    store.initialize()
    with hub.db(True) as db:
        p,doc,rev,control=store.document(db,user,pid,did,write=True)
        raw=db.execute('SELECT * FROM ds_comments WHERE id=? AND document_id=?',(key,did)).fetchone()
        if not raw:raise HTTPException(404,'Review comment not found.')
        row=dict(raw)
        if payload.get('version')!=row['version']:raise HTTPException(409,'This review comment changed. Reload before responding.')
        action=schema.choice(payload.get('action','reply'),{'reply','resolve','reopen','addressed'})
        reviewer=p['release_id'] if control and control['stage']=='closure' else p['quality_id']
        if action in {'resolve','reopen'} and user['role']!='admin' and user['id'] not in {row['author_id'],reviewer}:raise HTTPException(403,'The reviewer, comment author or Admin must resolve this review item.')
        body=text(payload.get('body',''),4000,True);status='resolved' if action=='resolve' else 'open' if action=='reopen' else 'addressed' if action=='addressed' else row['status']
        db.execute('UPDATE ds_comments SET status=?,version=version+1,updated_at=?,resolved_by=?,resolved_at=? WHERE id=?',(status,timestamp(),user['id'] if status=='resolved' else None,timestamp() if status=='resolved' else None,key))
        db.execute('INSERT INTO ds_comment_events VALUES(?,?,?,?,?,?)',(identity(),key,user['id'],action,body,timestamp()))
        store.audit(db,user,pid,did,row['revision_id'],'review_comment_'+action,{'comment_id':key,'body':body})
    return {'saved':True}

def list_comments(user,pid,did):
    store.initialize()
    with hub.db() as db:
        p,doc,rev,control=store.document(db,user,pid,did)
        from .service import fields
        layout=bindings.layout(rev['content'],control['stage'] if control else doc['kind']);result=[];dynamic=fields(db,p,doc,rev,control)
        for raw in db.execute('SELECT * FROM ds_comments WHERE document_id=? ORDER BY created_at',(did,)):
            value=dict(raw)
            try:original=anchor_text(rev['content'],layout,value['block_id'],value['cell_id'],dynamic);value['stale']=bindings.digest(original)!=value['source_hash']
            except HTTPException:value['stale']=True
            value['events']=[dict(r) for r in db.execute('SELECT * FROM ds_comment_events WHERE comment_id=? ORDER BY created_at,id',(value['id'],))];result.append(value)
        return {'items':result}
