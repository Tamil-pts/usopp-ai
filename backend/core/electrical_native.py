"""Native editable objects reconstructed from PDF vectors, separate from source pages."""
from collections import Counter
import copy
import hashlib
import json
import math
import re
import time
import xml.etree.ElementTree as ET

import pdfplumber
from fastapi import HTTPException
from .electrical_library import BY_KIND,pin

VERSION=2
IMPORT_REVISION=3
PATH=re.compile(r'^[MmLlHhVvCcSsQqTtAaZz0-9eE.,+\-\s]+$')


def excluded_page(page,scene):
    text=re.sub(r'\s+',' ',page.get('searchText','')).upper();compact=re.sub(r'\s+','',text)
    functional=bool(re.search(r'SCHEMATIC|CONTROL CIRCUIT|POWER CIRCUIT|LADDER DIAGRAM',text))
    if not functional and (any(s in compact for s in ('CABLEKIT','CABLEASSEMBLY','CONNECTORASSEMBLY','TERMINALASSEMBLY')) or scene.get('drawingKind','').startswith('cable assembly')):
        return 'Cable-kit / connector assembly drawing excluded.'
    if not functional and ('HEATSHRINK' in compact and any(s in compact for s in ('CRIMP','CABLESHOE','MARKERSLEEVE'))):
        return 'Cable-kit assembly / crimping instructions excluded.'
    if not functional and 'SIDE-A' in compact and 'SIDE-B' in compact and len(re.findall(r'\bX[A-Z]*\d+[-:]\d+',text))>=4:
        return 'Connector and terminal wiring schedule excluded.'
    schedule=r'^(?:BOM\b|BILL OF MATERIALS?\b|PARTS LIST\b|MATERIAL LIST\b|TERMINAL (?:SCHEDULE|LIST)\b|CONNECTOR (?:SCHEDULE|PINOUT)\b)'
    if not functional and (re.search(schedule,text) or re.search(schedule,page.get('title','').upper())):
        return 'BOM, connector or terminal schedule excluded.'
    return None


def build(folder):
    from .virtual_electrical import read,write,LOCK
    with LOCK:
        cached=read(folder/'circuit.json') if (folder/'circuit.json').is_file() else None
        if cached and (not cached.get('imported') or cached.get('importRevision')==IMPORT_REVISION or cached.get('version',1)>1):return cached
        info=read(folder/'drawing.json');positions={p['page']:p for p in read(folder/'layout.json')['positions']}
        elements=[];issues=[];sources=[]
        with pdfplumber.open(folder/'source.pdf') as pdf:
            for page in info['pages']:
                n=page['number'];w,h=page['width'],page['height'];offset=positions[n]
                scene=read(folder/f'scene-drawing-{n}.json');original=pdf.pages[n-1]
                excluded=excluded_page(page,scene)
                if excluded:
                    sources.append({'page':n,'title':page['title'],'excluded':True,'reason':excluded});original.close();continue
                frame=scene.get('frame') or {};top=frame.get('bodyTop',.035)*h;bottom=frame.get('footerTop',.90)*h
                from python_engine.circuit_compare import _tables
                omitted=[t['bbox'] for t in _tables(original)]
                def in_table(b):return any(b[0]<t[2] and b[2]>t[0] and b[1]<t[3] and b[3]>t[1] for t in omitted)
                ox,oy=offset['x'],offset['y']-top
                ref=lambda box:{'page':n,'bbox':box,'sourceSha256':info['sourceSha256']}
                sources.append({'page':n,'title':page['title'],'x':ox,'y':offset['y'],'width':w,'height':bottom-top,'drawingKind':scene.get('drawingKind')})
                for line in scene['lines']:
                    if in_table(line['bbox']):continue
                    points=[[ox+x*w,oy+y*h] for x,y in line['points']]
                    elements.append({'id':f'p{n}-{line["id"]}','kind':'wire','x':0,'y':0,'points':points,'reviewed':False,'source':ref(line['bbox'])})
                # Preserve the actual curves and symbol outlines, not page pixels.
                for index,obj in enumerate([*original.rects,*original.curves]):
                    x0,y0,x1,y1=obj['x0'],obj['top'],obj['x1'],obj['bottom']
                    if y0<top or y1>bottom or x0<.025*w or x1>.975*w or x1-x0>1.0*w:continue
                    if in_table([x0/w,y0/h,x1/w,y1/h]):continue
                    if any(x0<i['x1'] and x1>i['x0'] and y0<i['bottom'] and y1>i['top'] for i in original.images):continue
                    commands=[];valid=True
                    for command in obj.get('path',[]):
                        op=command[0].upper()
                        if op not in {'M','L','C','Q','Z','H'}:valid=False;break
                        # pdfplumber uses h to close a subpath.
                        if op in {'Z','H'}:commands.append('Z');continue
                        values=[v for point in command[1:] for v in (point[0]-x0,point[1]-y0)]
                        commands.append(op+' '.join(f'{v:.4f}' for v in values))
                    path=' '.join(commands)
                    if not valid or not path or len(path)>16000:continue
                    native={'id':f'p{n}-path-{index}','kind':'drawing','x':ox+x0,'y':oy+y0,'paths':[path],
                                     'width':max(1,x1-x0),'height':max(1,y1-y0),'label':'','reviewed':False,
                                     'source':ref([x0/w,y0/h,x1/w,y1/h])}
                    nearby=[l for l in scene['labels'] if re.fullmatch(r'R\d+',l['text'].strip(),re.I) and abs((l['bbox'][0]+l['bbox'][2])*w/2-(x0+x1)/2)<35 and abs((l['bbox'][1]+l['bbox'][3])*h/2-(y0+y1)/2)<35]
                    if len(nearby)==1 and obj.get('object_type')=='rect' and 8<max(x1-x0,y1-y0)<100 and max(x1-x0,y1-y0)>2*min(x1-x0,y1-y0):
                        native.update(kind='resistor',label=nearby[0]['text'].strip(),x=ox+(x0+x1)/2,y=oy+(y0+y1)/2,rotation=0 if x1-x0>y1-y0 else 90,scale=max(x1-x0,y1-y0)/80,params={'value':1000})
                        issues.append({'page':n,'kind':'value','message':native['label']+': resistor symbol candidate; confirm its resistance before simulation.'})
                    elif 'Z' in path and 5<x1-x0<120 and 5<y1-y0<120:
                        native['kind']='unknown'
                    elements.append(native)
                for label in scene['labels']:
                    b=label['bbox']
                    if b[1]*h<top or b[3]*h>bottom:continue
                    if in_table(b) or re.fullmatch(r'X[A-Z]*\d*(?:[-:]\S+)?',label['text'].strip(),re.I):continue
                    elements.append({'id':f'p{n}-{label["id"]}','kind':'text','x':ox+b[0]*w,'y':oy+b[3]*h,
                                     'text':label['text'][:1000],'fontSize':max(5,min(20,(b[3]-b[1])*h*.8)),'source':ref(b),'reviewed':True})
                if original.images:issues.append({'page':n,'kind':'raster','message':'Embedded pictures are not circuit objects. Their symbols and connections need manual reconstruction.'})
                if not scene['lines'] and not original.curves:issues.append({'page':n,'kind':'raster','message':'No usable vector circuit geometry. Supply a vector drawing or recreate the circuit with the component palette.'})
                if scene.get('drawingKind','').startswith('cable assembly'):issues.append({'page':n,'kind':'assembly','message':'This source is a cable/manufacturing drawing. Its contours are not automatically electrical nets.'})
                original.close()
        if len(elements)>50000:raise HTTPException(422,'The native redraw exceeds 50,000 objects. Split the source drawing.')
        title=read(folder/'workspace.json').get('name') if (folder/'workspace.json').exists() else None
        result={'schemaVersion':VERSION,'importRevision':IMPORT_REVISION,'version':cached['version']+1 if cached else 1,'name':title or info.get('name','Imported circuit'),'elements':elements,'sources':sources,
                'issues':issues,'imported':True,'sourceSha256':info['sourceSha256'],'created':time.time(),
                'modelNotice':'Source vectors are editable. Imported wires require review; symbol outlines must be assigned component types and values before simulation.'}
        write(folder/'circuit.json',result)
        return result


def validate(payload):
    elements=payload.get('elements')
    if not isinstance(elements,list) or len(elements)>50000:raise HTTPException(400,'Use a circuit with at most 50,000 objects.')
    if len(json.dumps(elements))>20*1024*1024:raise HTTPException(413,'The edited circuit exceeds the 20 MB document budget.')
    ids=set();clean=[]
    def coordinate(v):return type(v)in (float,int) and math.isfinite(v) and abs(v)<=1000000
    for raw in elements:
        if not isinstance(raw,dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',str(raw.get('id',''))) or raw['id'] in ids:raise HTTPException(400,'Every circuit object needs a unique valid identity.')
        kind=raw.get('kind')
        if kind not in {*BY_KIND,'wire','text','drawing','unknown'}:raise HTTPException(400,'Choose a supported object or mark it unresolved.')
        if not coordinate(raw.get('x')) or not coordinate(raw.get('y')):raise HTTPException(400,'Use finite circuit coordinates.')
        if raw.get('rotation',0)not in (0,90,180,270):raise HTTPException(400,'Rotate components in 90 degree steps.')
        e={k:copy.deepcopy(v) for k,v in raw.items() if k in {'id','kind','x','y','rotation','scale','label','text','fontSize','params','paths','points','from','to','reviewed','source','width','height'}}
        if type(raw.get('scale',1))not in (int,float) or not .02<=raw.get('scale',1)<=20:raise HTTPException(400,'Use a component scale from 0.02 to 20.')
        for dimension in ('width','height'):
            if dimension in raw and (not coordinate(raw[dimension]) or raw[dimension]<0):raise HTTPException(400,'Use finite nonnegative object dimensions.')
        e['reviewed']=raw.get('reviewed') is True;e['label']=str(raw.get('label',''))[:120]
        if kind=='wire':
            pts=raw.get('points')
            if not isinstance(pts,list) or not 2<=len(pts)<=256 or any(not isinstance(p,list) or len(p)!=2 or not all(coordinate(v) for v in p) for p in pts):raise HTTPException(400,'Draw a wire with 2–256 finite points.')
        if kind in {'drawing','unknown'}:
            paths=raw.get('paths',[])
            if not isinstance(paths,list) or len(paths)>100 or any(not isinstance(p,str) or len(p)>16000 or not PATH.fullmatch(p) for p in paths):raise HTTPException(400,'Use native vector path geometry without embedded content.')
        if kind=='text':
            e['text']=str(raw.get('text',''))[:1000]
            if not coordinate(raw.get('fontSize',12)) or not 2<=raw.get('fontSize',12)<=100:raise HTTPException(400,'Choose text size from 2 to 100.')
        if kind in BY_KIND:
            params=raw.get('params',{})
            if not isinstance(params,dict):raise HTTPException(400,'Enter component parameters.')
            e['params']={**BY_KIND[kind]['defaults'],**{f['key']:params[f['key']] for f in BY_KIND[kind]['fields'] if f['key'] in params}}
            for f in BY_KIND[kind]['fields']:
                v=e['params'].get(f['key'])
                if f['type']=='number' and (type(v)not in (float,int) or not math.isfinite(v) or not f['min']<=v<=f['max']):raise HTTPException(400,'Enter a valid '+f['label'].lower()+'.')
                if f['type']=='boolean' and type(v)is not bool:raise HTTPException(400,'Choose the switch state.')
                if f['type']=='enum' and v not in f['options']:raise HTTPException(400,'Choose a supported '+f['label'].lower()+'.')
                if f['type']=='text' and (not isinstance(v,str) or len(v)>120):raise HTTPException(400,'Use a component label up to 120 characters.')
        ids.add(e['id']);clean.append(e)
    by_id={e['id']:e for e in clean}
    for e in clean:
        if e['kind']!='wire':continue
        for key,index in [('from',0),('to',-1)]:
            a=e.get(key)
            if a is None:continue
            target=by_id.get(a.get('id')) if isinstance(a,dict) else None
            if not target or target['kind'] not in BY_KIND or a.get('port')not in {p['id'] for p in BY_KIND[target['kind']]['ports']}:raise HTTPException(400,'A wire endpoint refers to a missing component pin.')
            e['points'][index]=pin(target,a['port'])
    return clean


def save(folder,payload):
    from .virtual_electrical import LOCK,read,write
    with LOCK:
        old=build(folder)
        if type(payload.get('version'))is not int or old['version']!=payload['version']:raise HTTPException(409,'Circuit changed in another window. Reopen before saving.')
        clean=validate(payload)
        prior={e['id']:e for e in old['elements']}
        for e in clean:
            if e['id'] in prior and prior[e['id']].get('source'):e['source']=prior[e['id']]['source']
            else:e.pop('source',None)
        result={**old,'elements':clean,'name':str(payload.get('name',old['name']))[:180],'version':old['version']+1,'updated':time.time()}
        write(folder/'circuit.json',result);return result


def svg(document):
    elements=document['elements'];points=[]
    for e in elements:
        if e['kind']=='wire':points.extend(e['points'])
        else:points.extend([[e['x']-50,e['y']-65],[e['x']+max(60,e.get('width',0)),e['y']+max(65,e.get('height',0))]])
    if not points:points=[[0,0],[800,500]]
    x=min(p[0] for p in points)-20;y=min(p[1] for p in points)-20;w=max(p[0] for p in points)-x+20;h=max(p[1] for p in points)-y+20
    root=ET.Element('svg',{'xmlns':'http://www.w3.org/2000/svg','viewBox':f'{x} {y} {w} {h}','width':str(w),'height':str(h)})
    ET.SubElement(root,'rect',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'fill':'white'})
    for e in elements:
        if e['kind']=='wire':
            ET.SubElement(root,'polyline',{'points':' '.join(f'{a},{b}' for a,b in e['points']),'fill':'none','stroke':'#245c45','stroke-width':'1.5'});continue
        g=ET.SubElement(root,'g',{'transform':f'translate({e["x"]} {e["y"]}) rotate({e.get("rotation",0)}) scale({e.get("scale",1)})'})
        if e['kind']=='text':ET.SubElement(g,'text',{'font-family':'sans-serif','font-size':str(e.get('fontSize',12))}).text=e['text'];continue
        for path in BY_KIND.get(e['kind'],{}).get('paths',e.get('paths',[])):
            ET.SubElement(g,'path',{'d':path,'fill':'none','stroke':'#1e293b','stroke-width':'1.5'})
        if e.get('label'):ET.SubElement(g,'text',{'x':'0','y':'-25','text-anchor':'middle','font-family':'sans-serif','font-size':'12'}).text=e['label']
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
