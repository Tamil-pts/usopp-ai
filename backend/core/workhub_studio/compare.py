"""Revision comparison by native identities, block IDs and individual cells."""
from copy import deepcopy
import re
from difflib import SequenceMatcher
from . import store,bindings,schema

def text_diff(left,right):
    a=re.findall(r'\s+|\w+|[^\w\s]',str(left),re.UNICODE);b=re.findall(r'\s+|\w+|[^\w\s]',str(right),re.UNICODE);result=[]
    # Bound quadratic diff costs for long source paragraphs.
    if len(a)+len(b)>12000:return [{'type':'deleted','text':str(left)},{'type':'added','text':str(right)}]
    for tag,i,j,x,y in SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
        if tag=='equal':result.append({'type':'equal','text':''.join(a[i:j])})
        else:
            if i!=j:result.append({'type':'deleted','text':''.join(a[i:j])})
            if x!=y:result.append({'type':'added','text':''.join(b[x:y])})
    return result

def mapping(content,kind):
    layout=bindings.layout(content,kind);items=[]
    for b in layout['blocks']:
        data=b['data'];value={'id':b['id'],'type':b['type'],'style':b['style'],'text':schema.plain(data.get('runs',[])),'cells':{}}
        if b['type']=='native_table':
            table=bindings.native_table(content,data['binding'])
            value['cells']={row['id']+':'+col['field']:row['cells'][i] for row in table['rows'] for i,col in enumerate(table['columns'])}
        elif b['type'] in {'table','checklist'}:value['cells']={c['id']:schema.plain(c['runs']) for c in data['cells']}
        elif b['type'] in {'image','chart','flowchart','section_break','field','signature','approval'}:value['content']=data
        if b['type']=='native_flowchart':value['content']=content.get('flowchart',content.get('nodes',[]))
        items.append(value)
    return layout,items

def compare(user,pid,did,left,right):
    store.initialize()
    with store.hub.db() as db:
        p,doc,l,control=store.document(db,user,pid,did,left);_,_,r,_=store.document(db,user,pid,did,right)
        kind=control['stage'] if control else doc['kind'];ll,a=mapping(l['content'],kind);rr,b=mapping(r['content'],kind)
        old={x['id']:x for x in a};new={x['id']:x for x in b};changes=[];old_order=[x['id'] for x in a];new_order=[x['id'] for x in b]
        for key in dict.fromkeys([*new,*old]):
            before=old.get(key);after=new.get(key);state='added' if before is None else 'deleted' if after is None else 'unchanged' if before==after else 'modified'
            cells=[]
            for cell in dict.fromkeys([*((after or {}).get('cells',{})),*((before or {}).get('cells',{}))]):
                av=(before or {}).get('cells',{}).get(cell);bv=(after or {}).get('cells',{}).get(cell)
                if av!=bv:cells.append({'id':cell,'before':av,'after':bv,'state':'added' if av is None else 'deleted' if bv is None else 'modified','spans':text_diff(av or '',bv or '')})
            moved=bool(before and after and old_order.index(key)!=new_order.index(key))
            if state=='unchanged' and moved:state='moved'
            changes.append({'id':key,'type':(after or before)['type'],'state':state,'moved':moved,'before':before,'after':after,'text':text_diff((before or {}).get('text',''),(after or {}).get('text','')),'cells':cells,'formatting':bool(before and after and before['style']!=after['style'])})
        return {'left':{'id':l['id'],'number':l['number'],'label':l.get('label') or 'Rev '+str(l['number']-1).zfill(2),'status':l['status']},
                'right':{'id':r['id'],'number':r['number'],'label':r.get('label') or 'Rev '+str(r['number']-1).zfill(2),'status':r['status']},
                'changes':changes,'page_changes':{k:{'before':ll[k],'after':rr[k]} for k in ('page','header','footer','template_id') if ll[k]!=rr[k]},
                'summary':{state:sum(v['state']==state for v in changes) for state in ('added','deleted','modified','moved','unchanged')}}
