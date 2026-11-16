"""Evidence-preserving PDF inventory and conservative connector-table reconstruction."""
from collections import defaultdict
from copy import deepcopy
import hashlib,re,time
import pdfplumber
from fastapi import HTTPException
from backend.core.virtual_electrical import read,write,LOCK

REVISION=2
PIN=re.compile(r'^(-?X[A-Z]?\d+)[\-\xad\ufffd\u2010-\u2015]([A-Z0-9/]+)\(([^)]+)\)$',re.I)
def identity(*parts):return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:24]
def checksum(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def category(text):
    value=text.upper()
    if 'SIDE' in value and ('SL.NO' in value or 'TABLE' in value):return 'connection_table'
    if 'CONNECTION DIAGRAM' in value:return 'connection_diagram'
    if re.search(r'S.NO|SQMM|SQ.MM',value):return 'cable_assembly'
    if re.search(r'BILL OF|BOM|PARTS LIST',value):return 'bom'
    return 'unclassified'
def table_connections(words,number,digest,text):
    # A candidate needs explicit terminal syntax, a common row and SIDE table headers.
    if category(text)!='connection_table':return [],[]
    rows=defaultdict(list)
    for word in words:
        match=PIN.fullmatch(word['text'])
        if match:
            entry={'device':match[1].lstrip('-').upper(),'pin':match[2].upper(),'conductor':match[3],'text':word['text'],'bbox':[word[k] for k in ('x0','top','x1','bottom')]}
            key=next((k for k in rows if abs(k-word['top'])<=1.5),round(word['top'],2));rows[key].append(entry)
    connections=[];issues=[]
    for top,entries in sorted(rows.items()):
        entries.sort(key=lambda e:e['bbox'][0]);remaining=list(entries)
        while len(remaining)>=2:
            a,b=remaining[:2];remaining=remaining[2:]
            # Do not pair across table regions or identical device labels.
            if a['device']==b['device'] or b['bbox'][0]-a['bbox'][2]>110:
                issues.append({'page':number,'status':'unresolved','message':'Ambiguous terminal row; no connection inferred.','bbox':a['bbox']});continue
            scope=f'page:{number}/table:{a["device"]}:{b["device"]}'
            endpoints=[{'device':scope+'/'+e['device'],'pin':e['pin'],'conductor':e['conductor']} for e in (a,b)]
            connections.append({'id':identity(digest,number,top,a['text'],b['text']),'from':endpoints[0],'to':endpoints[1],'status':'needs_review','method':'explicit_terminal_table_row','confidence':None,'source':{'sha256':digest,'page':number,'bbox':[a['bbox'][0],min(a['bbox'][1],b['bbox'][1]),b['bbox'][2],max(a['bbox'][3],b['bbox'][3])],'text':a['text']+' -> '+b['text']},'review':[]})
        if remaining:issues.append({'page':number,'status':'unresolved','message':'Unpaired terminal label.','bbox':remaining[0]['bbox']})
    return connections,issues

def build(folder,progress=lambda *_:None):
    from backend.electrical.graphical import trace,reconcile
    source=folder/'source.pdf';digest=checksum(source);model={'schema_version':'1.0','decoder_revision':REVISION,'revision':1,'project_id':read(folder/'workspace.json').get('id',folder.name),'source':{'sha256':digest,'filename':read(folder/'workspace.json')['name']},'pages':[],'devices':[],'connections':[],'issues':[],'review_history':[],'simulation_ready':False}
    graphics=[]
    with pdfplumber.open(source) as pdf:
        model['source']['encrypted']=bool(pdf.doc.encryption)
        if not 1<=len(pdf.pages)<=200:raise ValueError('Use 1-200 PDF pages.')
        for index,page in enumerate(pdf.pages,1):
            progress('Extracting electrical source evidence',index,len(pdf.pages))
            words=page.extract_words();text=page.extract_text() or '';lines=page.lines;curves=page.curves;images=page.images
            image_area=sum(max(0,i['x1']-i['x0'])*max(0,i['bottom']-i['top']) for i in images)/(page.width*page.height)
            kind='mixed' if image_area>.5 and (words or lines or curves) else 'scanned' if image_area>.5 else 'vector' if words or lines or curves else 'empty'
            record={'number':index,'width':page.width,'height':page.height,'rotation':page.rotation,'source_kind':kind,'classification':category(text),'word_count':len(words),'line_count':len(lines),'curve_count':len(curves),'image_count':len(images),'image_coverage':round(image_area,3),'status':'needs_review','geometry_file':f'electrical-page-{index}.json'}
            # Keep per-page evidence separate; do not make touching primitives into nets.
            evidence={'page':index,'sha256':digest,'words':[{k:w[k] for k in ('text','x0','top','x1','bottom')} for w in words],'lines':[{k:l.get(k) for k in ('x0','top','x1','bottom','linewidth','stroking_color')} for l in lines],'curves':[{k:c.get(k) for k in ('x0','top','x1','bottom','pts','linewidth')} for c in curves],'images':[{k:i.get(k) for k in ('x0','top','x1','bottom','width','height')} for i in images],'text':text}
            for target,original in zip(evidence['lines'],lines):target['pts']=original.get('pts',[])
            graphical=trace(words,lines,index,digest,text,table=record['classification']=='connection_table')
            graphics.append(graphical);write(folder/f'electrical-graphical-{index}.json',graphical)
            record['graphical_path_count']=len(graphical['paths']);record['graphical_connection_count']=len(graphical['connections'])
            write(folder/record['geometry_file'],evidence)
            connections,issues=table_connections(words,index,digest,text);model['connections'].extend(connections);model['issues'].extend(issues);record['connection_count']=len(connections)
            if lines or curves:model['issues'].append({'page':index,'status':'unresolved','code':'graphical_review_required','message':'Graphical elements require a separate page review; connection approval alone is insufficient.'})
            if kind in {'scanned','mixed'}:model['issues'].append({'page':index,'status':'unresolved','message':'Raster content retained. OCR and symbol recognition are not implemented in this decoder.'})
            if not connections:model['issues'].append({'page':index,'status':'unresolved','message':'Source retained; no verified electrical objects reconstructed on this page.'})
            model['pages'].append(record);page.flush_cache()
    devices={}
    for c in model['connections']:
        for endpoint in (c['from'],c['to']):
            d=devices.setdefault(endpoint['device'],{'id':endpoint['device'],'designation':endpoint['device'].rsplit('/',1)[-1],'scope':endpoint['device'].rsplit('/',1)[0],'type':'connector','pins':[],'page':c['source']['page']})
            if endpoint['pin'] not in d['pins']:d['pins'].append(endpoint['pin'])
    model['devices']=list(devices.values())
    model['graphical_pages']=[{k:g[k] for k in ('page','device_designations','table_references','line_count')} for g in graphics]
    model['graphical_connections']=[c for g in graphics for c in g['connections']]
    model['corroboration']=reconcile(graphics,model['connections'])
    model['verification_levels']=['connection','page','project_scope']
    if checksum(source)!=digest:raise ValueError('Source PDF changed during reconstruction.')
    write(folder/'electrical-model.json',model)
    write(folder/'drawing.json',{'pages':model['pages'],'references':[],'sourceSha256':digest,'pageCount':len(model['pages'])})
    write(folder/'layout.json',{'version':1,'positions':[],'mode':'industrial'})
    return model

def load(folder):
    if not (folder/'electrical-model.json').exists():raise HTTPException(409,'This workspace has no industrial reconstruction. Import in Industrial mode.')
    model=read(folder/'electrical-model.json')
    if checksum(folder/'source.pdf')!=model['source']['sha256']:raise HTTPException(409,'The source PDF changed. Reimport before reviewing.')
    if model.get('decoder_revision')!=REVISION:raise HTTPException(409,'Reimport with the current decoder before verification; the existing model predates independent graphical tracing.')
    return model

def validate(model,page=None,pages=None):
    if pages is not None:
        # Explicit simulation scope must include every source occurrence of its connectors.
        chosen=set(pages);required=set(chosen);designations=set()
        for d in model['devices']:
            if d['page'] in chosen:designations.add(d['designation'].upper())
        for g in model.get('graphical_pages',[]):
            if g['page'] in chosen:designations.update(x.upper() for x in g['device_designations'])
        changed=True
        while changed:
            changed=False
            for g in model.get('graphical_pages',[]):
                names={x.upper() for x in g['device_designations']}
                if names & designations and g['page'] not in required:
                    required.add(g['page']);designations.update(names);changed=True
            for d in model['devices']:
                if d['designation'].upper() in designations and d['page'] not in required:
                    required.add(d['page']);changed=True
        results=[dict(page=p,**validate(model,p)) for p in sorted(required)]
        missing=sorted(required-chosen)
        issues=[{'page':p,'status':'unresolved','message':'Dependent source page is outside the selected scope.'} for p in missing]
        issues.extend(i for r in results for i in r['issues'])
        return {'level':'project_scope','status':'verified' if results and not issues and all(r['status']=='verified' for r in results) else 'unresolved',
                'selected_pages':sorted(chosen),'required_pages':sorted(required),'missing_dependency_pages':missing,'page_results':results,
                'issues':issues,'simulation_ready':False,'meaning':'Scope verification does not certify executable device or control semantics.'}
    reviewed={r['page'] for r in model.get('page_reviews',[]) if r['source_sha256']==model['source']['sha256']}
    devices={d['id']:set(d['pins']) for d in model['devices']};issues=[i for i in model['issues'] if (page is None or i['page']==page) and not (i.get('code')=='graphical_review_required' and i['page'] in reviewed)];seen=set()
    connections=[c for c in model['connections'] if page is None or c['source']['page']==page]
    for c in connections:
        if c['status']!='verified':issues.append({'page':c['source']['page'],'connection_id':c['id'],'status':c['status'],'message':'Connection not engineer-verified.'})
        for endpoint in (c['from'],c['to']):
            if endpoint['pin'] not in devices.get(endpoint['device'],set()):issues.append({'page':c['source']['page'],'status':'unresolved','message':'Unknown device terminal.'})
        if c['from']['device']==c['to']['device'] and c['from']['pin']==c['to']['pin']:issues.append({'page':c['source']['page'],'status':'unresolved','message':'Connection joins a terminal to itself.'})
        key=tuple(sorted((e['device'],e['pin']) for e in (c['from'],c['to'])))
        if key in seen:issues.append({'page':c['source']['page'],'status':'unresolved','message':'Duplicate connection assignment.'})
        seen.add(key)
    graphical=[c for c in model.get('graphical_connections',[]) if page is None or c['source']['page']==page]
    for r in model.get('corroboration',[]):
        if r['status']=='conflict' and (page is None or r['table_page']==page):issues.append({'page':r['table_page'],'status':'unresolved','message':'Table assignment conflicts with independently traced graphical evidence.','connection_id':r['table_connection_id']})
    for c in graphical:
        if c['status']!='verified':issues.append({'page':c['source']['page'],'status':'unresolved','message':'Graphically traced connection remains unverified.','connection_id':c['id']})
    return {'level':'page' if page else 'project','status':'verified' if connections and not issues else 'unresolved' if not connections or any(i['status']=='unresolved' for i in issues) else 'needs_review','connection_count':len(connections),'verified_connection_count':sum(c['status']=='verified' for c in connections),'graphical_connection_count':len(graphical),'issues':issues,'simulation_ready':False,'scope':'selected page' if page else 'whole source','meaning':'Continuity evidence only; page approval does not resolve cross-page dependencies or certify machine simulation.'}

def review(folder,payload,actor):
    with LOCK:
        model=load(folder)
        if payload.get('revision')!=model['revision']:raise HTTPException(409,'The model changed. Reload before saving a review.')
        connection=next((c for c in model['connections'] if c['id']==payload.get('connection_id')),None)
        if not connection:raise HTTPException(404,'Connection not found.')
        status=payload.get('status');comment=str(payload.get('comment','')).strip()
        if status not in {'verified','needs_review','unresolved'} or not 3<=len(comment)<=2000:raise HTTPException(400,'Choose a status and record a 3-2000 character engineering review comment.')
        stamp={'actor_id':actor['id'],'time':time.time(),'status':status,'comment':comment,'connection_id':connection['id'],'source_sha256':model['source']['sha256']}
        # Existing terminal IDs are the correction boundary; no invented devices.
        corrected=payload.get('endpoints')
        if corrected is not None:
            if not isinstance(corrected,list) or len(corrected)!=2:raise HTTPException(400,'Provide two existing device terminals.')
            terminals={d['id']:d['pins'] for d in model['devices'] if d['page']==connection['source']['page']}
            for end in corrected:
                if not isinstance(end,dict) or end.get('pin') not in terminals.get(end.get('device'),[]):raise HTTPException(400,'Choose an existing device pin.')
            stamp['previous_endpoints']=[deepcopy(connection['from']),deepcopy(connection['to'])];connection['from'],connection['to']=corrected
        connection['status']=status;connection['review'].append(stamp);model['review_history'].append(stamp)
        # Any terminal correction or status change invalidates dependent page review.
        model['page_reviews']=[r for r in model.get('page_reviews',[]) if r['page']!=connection['source']['page']]
        if corrected is not None:
            from backend.electrical.graphical import reconcile
            graphics=[read(folder/f'electrical-graphical-{p["number"]}.json') for p in model['pages'] if (folder/f'electrical-graphical-{p["number"]}.json').exists()]
            model['corroboration']=reconcile(graphics,model['connections'])
        model['revision']+=1;write(folder/'electrical-model.json',model);return model

def review_page(folder,payload,actor):
    """Explicit graphical review does not erase unresolved wiring or unknown symbols."""
    with LOCK:
        model=load(folder);page=payload.get('page');comment=str(payload.get('comment','')).strip()
        if payload.get('revision')!=model['revision']:raise HTTPException(409,'The model changed. Reload before reviewing.')
        if type(page) is not int or not 1<=page<=len(model['pages']) or not 3<=len(comment)<=2000:raise HTTPException(400,'Choose a source page and record a 3-2000 character review comment.')
        result=validate(model,page)
        blocking=[i for i in result['issues'] if i.get('code')!='graphical_review_required']
        if blocking or not result['connection_count']:raise HTTPException(409,{'message':'Resolve missing wiring and verify the extracted connections before page approval.','issues':blocking})
        stamp={'page':page,'actor_id':actor['id'],'time':time.time(),'source_sha256':model['source']['sha256'],'comment':comment,'level':'page','status':'verified'}
        model.setdefault('page_reviews',[]).append(stamp);model['review_history'].append(stamp);model['revision']+=1
        write(folder/'electrical-model.json',model);return model
