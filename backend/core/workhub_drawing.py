"""Versioned drawing extension. Geometry is evidence; it is not a circuit solver."""
from __future__ import annotations
import math
import re
from copy import deepcopy
from html import escape
import textwrap
from fastapi import HTTPException

COLORS=re.compile(r'#[0-9a-fA-F]{6}')
PATH=re.compile(r'[MmLlHhVvCcSsQqTtAaZz0-9., +\-eE]+')
from backend.core.visual_content import FONTS as VISUAL_FONTS
FONTS=set(VISUAL_FONTS)
PAPER={'A4':(794,1123),'A3':(1123,1587),'A2':(1587,2245)}
SHAPES={'rect','roundrect','ellipse','diamond','io','document','subprocess','path'}

def fail(message):raise HTTPException(400,message)
def number(value,low,high,label):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:fail('Use a valid '+label+'.')
def color(value):
    if not isinstance(value,str) or not COLORS.fullmatch(value):fail('Use hexadecimal drawing colors.')
def bounded(value,limit,label):
    if not isinstance(value,str) or len(value)>limit:fail('Use bounded '+label+'.')
def asset(value):
    if not isinstance(value,dict) or value.get('shape') not in SHAPES:fail('Choose a supported geometric drawing symbol.')
    if value['shape']=='path':
        path=value.get('path','');bounded(path,12000,'SVG paths')
        if not PATH.fullmatch(path):fail('Scripts, HTML, external images and arbitrary SVG are unsupported.')
        # Keep geometry finite, including exponent notation accepted by SVG.
        for token in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',path):number(float(token),-10000,10000,'SVG coordinates')

def validate(content):
    ws=content.get('workspace')
    if ws is None:return  # Legacy FRD diagrams retain their existing validation.
    if not isinstance(ws,dict) or ws.get('schema_version')!=2:fail('Unsupported drawing workspace version.')
    pages,layers=ws.get('pages'),ws.get('layers')
    if not isinstance(pages,list) or not 1<=len(pages)<=20 or not isinstance(layers,list) or not 1<=len(layers)<=30:fail('Use 1–20 pages and 1–30 layers.')
    def identities(items):
        keys=[p.get('id') if isinstance(p,dict) else None for p in items]
        if any(not isinstance(k,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',k) for k in keys) or len(set(keys))!=len(keys):fail('Page and layer IDs must be unique.')
        for p in items:bounded(p.get('name',''),160,'page and layer names')
        return set(keys)
    pids,lids=identities(pages),identities(layers)
    for p in pages:
        if p.get('paper') not in {'infinite',*PAPER} or p.get('orientation') not in {'portrait','landscape'}:fail('Choose A4, A3, A2 or an infinite drawing page.')
        color(p.get('background','#ffffff'))
    for l in layers:
        if any(type(l.get(k)) is not bool for k in ('visible','locked')):fail('Use valid layer visibility and locks.')
    for k in ('grid','snap','snap_objects','rulers'):
        if type(ws.get(k)) is not bool:fail('Use valid canvas options.')
    if ws.get('units') not in {'px','mm','in'}:fail('Choose supported canvas units.')
    nodes=content.get('nodes',[]);by_id={n['id']:n for n in nodes}
    for node in nodes:
        data=node['data']
        if data.get('page_id') not in pids or data.get('layer_id') not in lids:fail('Every object needs an existing page and layer.')
        for key in ('locked','hide_label'):
            if key in data and type(data[key]) is not bool:fail('Use valid object locks and label visibility.')
        bounded(data.get('group_id',''),80,'group IDs')
        s=data.get('appearance',{})
        if not isinstance(s,dict):fail('Use structured drawing styles.')
        allowed={'fill','stroke','text','gradient','font','font_size','stroke_width','rotation','opacity','line_height','letter_spacing','bold','italic','underline','shadow','flip_x','flip_y','align','valign','dash','join'}
        if set(s)-allowed:fail('Unsupported drawing style property.')
        for key in ('fill','stroke','text','gradient'):
            if s.get(key):color(s[key])
        for key,low,high in [('font_size',6,96),('stroke_width',0,12),('rotation',-360,360),('opacity',0,1),('line_height',.5,3),('letter_spacing',-2,20)]:
            if key in s:number(s[key],low,high,key)
        for key in ('bold','italic','underline','shadow','flip_x','flip_y'):
            if key in s and type(s[key]) is not bool:fail('Use valid drawing effects.')
        for key,options in [('font',FONTS),('align',{'left','center','right'}),('valign',{'top','center','bottom'}),('dash',{'solid','dashed','dotted'}),('join',{'round','miter','bevel'})]:
            if key in s and s[key] not in options:fail('Choose a supported '+key+'.')
        symbol=data.get('symbol')
        if symbol:
            if not isinstance(symbol,dict):fail('Provide structured symbol provenance.')
            for key in ('id','library_id','source','license','version'):bounded(symbol.get(key,''),1000,'symbol provenance')
            asset(symbol.get('asset'))
            ports=symbol.get('ports',[])
            if not isinstance(ports,list) or len(ports)>32:fail('Use up to 32 symbol ports.')
            ids=set()
            for port in ports:
                if not isinstance(port,dict):fail('Use structured symbol ports.')
                bounded(port.get('id',''),80,'port IDs')
                if not port['id'] or port['id'] in ids:fail('Use unique port IDs.')
                ids.add(port['id']);number(port.get('x'),0,1,'port x');number(port.get('y'),0,1,'port y')
                if port.get('direction') not in {'input','output','bidirectional'}:fail('Choose a supported port direction.')
                if 'domain' in port:bounded(port['domain'],80,'port domains')
    for edge in content.get('edges',[]):
        a,b=by_id[edge['source']],by_id[edge['target']]
        if a['data']['page_id']!=b['data']['page_id']:fail('Use a reference symbol instead of a cross-page connector.')
        if edge.get('type','smoothstep') not in {'smoothstep','default','straight','routed'}:fail('Choose supported connector routing.')
        points=edge.get('data',{}).get('waypoints',[])
        if not isinstance(points,list) or len(points)>40:fail('Use up to 40 connector waypoints.')
        for point in points:
            if not isinstance(point,dict):fail('Use structured connector waypoints.')
            for k in ('x','y'):number(point.get(k),-100000,100000,'waypoint coordinates')
        s=edge.get('style',{})
        if not isinstance(s,dict) or set(s)-{'stroke','strokeWidth','strokeDasharray'}:fail('Unsupported connector style.')
        if 'stroke' in s:color(s['stroke'])
        if 'strokeWidth' in s:number(s['strokeWidth'],0,12,'connector width')
        if 'strokeDasharray' in s and s['strokeDasharray'] not in {'','8 5','2 4'}:fail('Choose a supported connector pattern.')
        for marker in ('markerStart','markerEnd'):
            if edge.get(marker) and (not isinstance(edge[marker],dict) or edge[marker].get('type') not in {'arrow','arrowclosed'}):fail('Choose a supported connector arrow.')
        for side,n in [('source',a),('target',b)]:
            symbol=n['data'].get('symbol',{});ports=symbol.get('ports',[]);key=edge.get(side+'Handle') or ('out' if side=='source' else 'in')
            if ports and key not in {p['id'] for p in ports}:fail('Connect an existing symbol port.')
        ap=next((p for p in a['data'].get('symbol',{}).get('ports',[]) if p['id']==edge.get('sourceHandle','out')),None)
        bp=next((p for p in b['data'].get('symbol',{}).get('ports',[]) if p['id']==edge.get('targetHandle','in')),None)
        if ap and bp and ap.get('domain') and bp.get('domain') and ap['domain']!=bp['domain']:fail('Connection port domains do not match.')
        if ap and ap.get('direction')=='input' or bp and bp.get('direction')=='output':fail('Connect an output port to an input port.')

def page_contents(content):
    ws=content.get('workspace',{});pages=ws.get('pages') or [{'id':'page-1','name':'Page 1','paper':'infinite','orientation':'portrait','background':'#ffffff'}]
    hidden={l['id'] for l in ws.get('layers',[]) if l.get('visible') is False}
    for p in pages:
        nodes=[n for n in content.get('nodes',[]) if n.get('data',{}).get('page_id',pages[0]['id'])==p['id'] and n.get('data',{}).get('layer_id','default') not in hidden]
        ids={n['id'] for n in nodes};edges=[e for e in content.get('edges',[]) if e['source'] in ids and e['target'] in ids]
        yield p,nodes,edges

def primitive(asset,fill,stroke,width,dash=''):
    props=f'fill="{fill}" stroke="{escape(stroke)}" stroke-width="{width}" vector-effect="non-scaling-stroke"'+(f' stroke-dasharray="{dash}"' if dash else '')
    shape=asset['shape']
    if shape=='path':return f'<path d="{escape(asset["path"])}" '+props.replace(f'fill="{fill}"','fill="none"')+'/>'
    if shape=='ellipse':return '<ellipse cx="50" cy="50" rx="49" ry="49" '+props+'/>'
    if shape=='diamond':return '<polygon points="50,1 99,50 50,99 1,50" '+props+'/>'
    if shape=='io':return '<polygon points="12,1 99,1 87,99 1,99" '+props+'/>'
    if shape=='document':return '<path d="M1 1 H99 V85 Q75 110 50 90 Q25 70 1 90 Z" '+props+'/>'
    value='<rect x="1" y="1" width="98" height="98" rx="'+('35' if shape=='roundrect' else '5')+'" '+props+'/>'
    if shape=='subprocess':value+='<path d="M10 1 V99 M90 1 V99" fill="none" stroke="'+escape(stroke)+'"/>'
    return value

def render_page(page,nodes,edges,mindmap=False):
    sizes={n['id']:(float(n.get('width') or 240),float(n.get('height') or 100)) for n in nodes};by_id={n['id']:n for n in nodes}
    if page['paper'] in PAPER:
        w,h=PAPER[page['paper']];w,h=(h,w) if page.get('orientation')=='landscape' else (w,h);lx=ly=0
    else:
        lx=min([n['position']['x']-max(sizes[n['id']]) for n in nodes]+[0])-30;ly=min([n['position']['y']-max(sizes[n['id']]) for n in nodes]+[0])-30
        w=max([n['position']['x']+2*max(sizes[n['id']]) for n in nodes]+[450])-lx+30;h=max([n['position']['y']+2*max(sizes[n['id']]) for n in nodes]+[260])-ly+30
    if w*h>32_000_000 or w>20000 or h>20000:fail('This drawing is too large to render. Split it across pages.')
    result=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="{lx} {ly} {w} {h}"><title>{escape(page["name"])}</title><rect x="{lx}" y="{ly}" width="{w}" height="{h}" fill="{page.get("background","#ffffff")}"/><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#126575"/></marker></defs>']
    def anchor(n,handle):
        x,y=n['position']['x'],n['position']['y'];nw,nh=sizes[n['id']]
        return {'in':(x,y+nh/2),'out':(x+nw,y+nh/2),'top':(x+nw/2,y),'bottom':(x+nw/2,y+nh)}.get(handle,(x+nw,y+nh/2))
    for e in edges:
        a,b=by_id[e['source']],by_id[e['target']];x,y=anchor(a,e.get('sourceHandle','out'));tx,ty=anchor(b,e.get('targetHandle','in'));mid=(x+tx)/2
        path=f'M{x} {y} L{tx} {ty}' if e.get('type')=='straight' else f'M{x} {y} C{mid} {y} {mid} {ty} {tx} {ty}' if e.get('type')=='default' else f'M{x} {y} H{mid} V{ty} H{tx}'
        if e.get('type')=='routed':path=f'M{x} {y} '+' '.join(f'L{p["x"]} {p["y"]}' for p in e.get('data',{}).get('waypoints',[]))+f' L{tx} {ty}'
        s=e.get('style',{});arrow=' marker-end="url(#arrow)"' if e.get('markerEnd') or not mindmap and 'markerEnd' not in e else ''
        result.append(f'<path d="{path}" fill="none" stroke="{s.get("stroke","#087f83")}" stroke-width="{s.get("strokeWidth",2)}" stroke-dasharray="{s.get("strokeDasharray","")}"{arrow}/><text x="{mid}" y="{(y+ty)/2-8}" text-anchor="middle" font-size="12">{escape(str(e.get("label") or ""))}</text>')
    for i,n in enumerate(nodes):
        x,y=n['position']['x'],n['position']['y'];nw,nh=sizes[n['id']];d=n.get('data',{});s=d.get('appearance',{});kind=d.get('kind','process');a=d.get('symbol',{}).get('asset') or {'shape':'diamond' if kind=='decision' else 'io' if kind=='io' else 'roundrect' if kind in {'start','end','topic'} else kind if kind in {'subprocess','document'} else 'rect'}
        fill=s.get('fill',d.get('color','#e7f5f4'));stroke=s.get('stroke','#087f83');uid='gradient'+str(i)
        if s.get('gradient'):
            result.append(f'<defs><linearGradient id="{uid}" x2="0" y2="1"><stop offset="0" stop-color="{fill}"/><stop offset="1" stop-color="{s["gradient"]}"/></linearGradient></defs>');fill=f'url(#{uid})'
        transform=f'translate({x+nw/2} {y+nh/2}) rotate({s.get("rotation",0)}) scale({-1 if s.get("flip_x") else 1} {-1 if s.get("flip_y") else 1}) translate({-nw/2} {-nh/2})'
        dash={'dashed':'8 5','dotted':'2 4'}.get(s.get('dash'),'')
        result.append(f'<g opacity="{s.get("opacity",1)}"><g transform="{transform}"><svg width="{nw}" height="{nh}" viewBox="0 0 100 100" preserveAspectRatio="none" overflow="visible">'+primitive(a,fill,stroke,s.get('stroke_width',1.5),dash)+'</svg></g>')
        if not d.get('hide_label'):
            fs=s.get('font_size',14);spacing=fs*s.get('line_height',1.35);limit=max(4,int(nw*(.55 if a['shape']=='diamond' else .9)/(fs*.55)))
            label=str(d.get('label',''))
            refs=', '.join(d.get('requirement_ids',[])+d.get('plc_references',[]));label+='\n'+refs if refs else ''
            lines=[v for line in label.splitlines() for v in (textwrap.wrap(line,width=limit) or [''])] or ['']
            lines=lines[:max(1,int((nh-20)/spacing))]
            first=y+20 if s.get('valign')=='top' else y+nh-12-(len(lines)-1)*spacing if s.get('valign')=='bottom' else y+(nh-(len(lines)-1)*spacing)/2+fs*.3
            tx=x+10 if s.get('align')=='left' else x+nw-10 if s.get('align')=='right' else x+nw/2;anchor_name={'left':'start','right':'end'}.get(s.get('align'),'middle')
            for j,line in enumerate(lines):result.append(f'<text x="{tx}" y="{first+j*spacing}" text-anchor="{anchor_name}" font-family="{escape(s.get("font","Arial"))}" font-size="{fs}" font-weight="{700 if s.get("bold") else 400}" font-style="{"italic" if s.get("italic") else "normal"}" text-decoration="{"underline" if s.get("underline") else "none"}" letter-spacing="{s.get("letter_spacing",0)}" fill="{s.get("text","#17344b")}">{escape(line)}</text>')
        result.append('</g>')
    result.append('</svg>');return ''.join(result)

def svg_pages(content):
    return [(page['name'],render_page(page,nodes,edges,content.get('diagram_type')=='mindmap')) for page,nodes,edges in page_contents(content)]

def svg(content):
    pages=svg_pages(content)
    if len(pages)==1:return pages[0][1]
    from xml.etree import ElementTree as ET
    roots=[ET.fromstring(value) for _,value in pages];width=max(float(r.attrib['width']) for r in roots);height=sum(float(r.attrib['height']) for r in roots)+30*(len(roots)-1)
    if width*height>32_000_000:fail('Use the multi-page PDF export for this large drawing.')
    y=0;parts=[]
    for i,r in enumerate(roots):
        value=pages[i][1].replace('id="arrow"',f'id="arrow{i}"').replace('url(#arrow)',f'url(#arrow{i})').replace('id="gradient',f'id="p{i}gradient').replace('url(#gradient',f'url(#p{i}gradient')
        # Nested SVG viewBoxes retain each page coordinate system.
        value=value.replace('<svg ',f'<svg y="{y}" ',1);parts.append(value);y+=float(r.attrib['height'])+30
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'+''.join(parts)+'</svg>'
