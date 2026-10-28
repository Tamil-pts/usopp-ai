"""Materialized revision context and non-executable chart/diagram geometry."""
from copy import deepcopy
import base64,hashlib,io,json,math,re
import textwrap
from html import escape
from . import store,bindings,schema,media,service

def context(db,p,doc,rev,control):
    from backend.core.workhub_quality import branding
    content=bindings.synchronize(rev['content']);kind=control['stage'] if control else doc['kind'];layout=bindings.layout(content,kind);fields=service.fields(db,p,doc,rev,control)
    state=store.quality.policy_row(db,p);org=branding.organization(db,state['context']);customer=branding.record(db,'customer',state['context']['customer_id']) if state['context'].get('customer_id') else None
    assets=media.snapshot(p['id'],layout)
    for label,record in [('company',org),('customer',customer)]:
        asset=branding.asset(db,record['data'].get('logo_id')) if record else None
        if asset:assets[label]={'name':label+'-logo.png','data':base64.b64encode(asset['data']).decode(),'sha256':asset['sha256']}
    return {'schema':1,'fields':fields,'studio':bindings.materialize(content,layout,fields),'editable_layout':layout,'assets':assets,'revision_id':rev['id'],'document_id':doc['id'],'project_id':p['id'],'source_hash':bindings.digest(rev['content']),'approved':rev['status'] in store.APPROVED,
       'manifest':{'source_revision_id':rev['id'],'source_hash':bindings.digest(rev['content']),'document_id':doc['id'],'project_id':p['id'],'organization_version':org['version'],'customer_version':customer['version'] if customer else None,'template_id':layout.get('template_id',''),'image_hashes':{k:v['sha256'] for k,v in assets.items()}}}

def field_text(text,fields,page=None,pages=None):
    values={**fields,'page':page if page is not None else '{page}','pages':pages if pages is not None else '{pages}'}
    return re.sub(r'\{([a-z_]+)\}',lambda m:str(values.get(m[1],m[0])),str(text))

def run_text(run,fields):return str(fields.get(run['field'],'Not recorded')) if run.get('field') else run.get('text','')

def image_data(value,source,file_id=''):
    key=source if source in {'company','customer'} else file_id;asset=value['assets'].get(key)
    if not asset:return None
    raw=base64.b64decode(asset['data'],validate=True)
    if hashlib.sha256(raw).hexdigest()!=asset['sha256']:raise ValueError('Document image snapshot integrity verification failed.')
    return raw

def sections(value):
    root=value['studio'];result=[{'id':'section-0','title':'','page':root['page'],'header':root['header'],'footer':root['footer'],'blocks':[]}]
    for b in root['blocks']:
        if not b['style']['visible']:continue
        if b['type']=='section_break':result.append({'id':'section-'+str(len(result)),'title':b['data']['title'],'page':b['data']['page'],'header':b['data']['header'],'footer':b['data']['footer'],'blocks':[]})
        else:result[-1]['blocks'].append(b)
    return result

def diagram_svg(block,accent='#235789'):
    data=block['data'];nodes=data.get('nodes',[])
    if not nodes:return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 100"><text x="20" y="50" fill="'+accent+'">Add flowchart steps</text></svg>'
    lines={n['id']:textwrap.wrap(n.get('label',''),25) or [''] for n in nodes};heights={key:max(56,len(value)*15+20) for key,value in lines.items()}
    w=max(n['x'] for n in nodes)+230;h=max(n['y']+heights[n['id']] for n in nodes)+30
    pieces=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="{accent}"/></marker></defs>']
    byid={n['id']:n for n in nodes}
    for edge in data.get('edges',[]):
        a=byid.get(edge.get('source'));b=byid.get(edge.get('target'))
        if not a or not b:continue
        x1=a['x']+100;y1=a['y']+heights[a['id']];x2=b['x']+100;y2=b['y']
        pieces.append(f'<path d="M{x1},{y1} L{x1},{(y1+y2)/2} L{x2},{(y1+y2)/2} L{x2},{y2}" stroke="{accent}" fill="none" stroke-width="2" marker-end="url(#arrow)"/>')
        if edge.get('label'):pieces.append(f'<text x="{(x1+x2)/2+5}" y="{(y1+y2)/2-6}" font-family="Arial" font-size="12">{escape(edge["label"])}</text>')
    for n in nodes:
        x=n['x'];y=n['y'];kind=n.get('kind','process');height=heights[n['id']]
        shape=f'<polygon points="{x+100},{y} {x+200},{y+height/2} {x+100},{y+height} {x},{y+height/2}"' if kind=='decision' else f'<rect x="{x}" y="{y}" width="200" height="{height}" rx="{25 if kind in {"start","end"} else 6}"'
        pieces.append(shape+f' fill="#f2f7fb" stroke="{accent}" stroke-width="2"/>')
        for i,line in enumerate(lines[n['id']]):pieces.append(f'<text x="{x+100}" y="{y+height/2-(len(lines[n["id"]])-1)*7.5+4+i*15}" text-anchor="middle" font-family="Arial" font-size="12" fill="#243b53">{escape(line)}</text>')
    return ''.join(pieces)+'</svg>'

def chart_svg(block,accent='#235789'):
    data=block['data'];labels=data.get('labels',[]);values=data.get('values',[]);width=700;height=max(330,90+len(labels)*22) if data['kind']=='pie' else 330
    p=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"><text x="25" y="25" font-family="Arial" font-size="16" fill="{accent}">{escape(data.get("title","Chart"))}</text>']
    if not values:return ''.join(p)+f'<text x="25" y="100" font-family="Arial" font-size="13">Enter chart labels and values</text></svg>'
    if data['kind']=='pie':
        total=sum(values);angle=-math.pi/2;palette=[accent,'#19a88a','#f1b44c','#8565bd','#c76855','#609ec3']
        for i,(label,v) in enumerate(zip(labels,values)):
            end=angle+(v/total*2*math.pi if total else 0);x1=240+105*math.cos(angle);y1=175+105*math.sin(angle);x2=240+105*math.cos(end);y2=175+105*math.sin(end)
            if v and total and abs(end-angle)>=2*math.pi-1e-6:p.append(f'<circle cx="240" cy="175" r="105" fill="{palette[i%6]}"/>')
            elif v and total:p.append(f'<path d="M240,175 L{x1},{y1} A105,105 0 {int(end-angle>math.pi)},1 {x2},{y2} Z" fill="{palette[i%6]}"/>')
            p.append(f'<rect x="400" y="{65+i*22}" width="12" height="12" fill="{palette[i%6]}"/><text x="420" y="{76+i*22}" font-family="Arial" font-size="12">{escape(label)}: {v}</text>');angle=end
    else:
        low=min(0,min(values));high=max(1,max(values));span=max(1,high-low);zero=270-(0-low)/span*210;step=590/max(1,len(values));points=[]
        p.append(f'<line x1="65" x2="665" y1="{zero}" y2="{zero}" stroke="#b8c9da"/>')
        for i,(label,v) in enumerate(zip(labels,values)):
            x=65+step*(i+.5);y=270-(v-low)/span*210;points.append((x,y))
            if data['kind']=='bar':p.append(f'<rect x="{x-step*.3}" y="{min(y,zero)}" width="{step*.6}" height="{abs(zero-y)}" fill="{accent}"/>')
            else:p.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{accent}"/>')
            p.append(f'<text x="{x}" y="{y-8}" font-family="Arial" text-anchor="middle" font-size="11">{v}</text><text x="{x}" y="295" font-family="Arial" text-anchor="middle" font-size="10">{escape(label)}</text>')
        if data['kind']=='line':p.append('<polyline points="'+' '.join(str(x)+','+str(y) for x,y in points)+f'" fill="none" stroke="{accent}" stroke-width="2"/>')
    return ''.join(p)+'</svg>'

def raster(block,accent='#235789'):
    # The safe shipped SVG contains no scripts, links or external resources.
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    raw=(chart_svg(block,accent) if block['type']=='chart' else diagram_svg(block,accent)).encode()
    try:return renderPM.drawToString(svg2rlg(io.BytesIO(raw)),fmt='PNG')
    except Exception:
        # Render the identical bounded SVG when ReportLab has no raster backend.
        # No divergent drawing code: Word receives the same chart/diagram.
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport={'width':1800,'height':1400},device_scale_factor=1)
                page.route('**/*',lambda route:route.abort())
                page.set_content('<style>html,body{margin:0;background:white}svg{display:block;width:1600px;height:auto}</style>'+raw.decode())
                page.evaluate('document.fonts.ready')
                return page.locator('svg').screenshot(type='png',timeout=30000)
            finally:browser.close()
