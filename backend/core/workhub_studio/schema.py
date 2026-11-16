"""Bounded, non-executable page and element schema shared by Studio exports."""
from copy import deepcopy
import math,re
from fastapi import HTTPException

VERSION=1
FIELDS={'project_name','project_number','customer','machine','document_number','document_title','revision','status','prepared_by','reviewed_by','approved_by','approval_date','date','page','pages','company','department','section_title'}
from backend.core.visual_content import FONTS as VISUAL_FONTS
FONTS=set(VISUAL_FONTS)
TYPES={'paragraph','heading','panel','cover','table','checklist','image','flowchart','chart','signature','approval','line','page_break','section_break','field','checkbox','native_text','native_table','native_flowchart','metadata'}
PAGE={'size':'A4','orientation':'portrait','margins':{'top':25,'right':20,'bottom':25,'left':20},'header_height':13,'footer_height':10,'header_gap':5,'footer_gap':5,'columns':1,'column_gap':8,'background':'#ffffff','color':'#243b53','accent':'#235789','font':'Arial','font_size':11,'line_height':1.45,'paragraph_spacing':8,'border_color':'#b8c9da','border_width':0,'watermark':'','watermark_color':'#8293a5','watermark_opacity':0.12,'watermark_angle':40}
STYLE={'align':'left','color':'#243b53','background':'transparent','border_color':'#ccd7e2','border_width':0,'border_style':'solid','padding':2,'width':100,'height':0,'x':0,'space_before':2,'space_after':3,'font':'Arial','font_size':11,'line_height':1.45,'bold':False,'italic':False,'underline':False,'visible':True,'keep_together':False,'inherit_font':True,'inherit_color':True,'inherit_spacing':True}

def fail(message):raise HTTPException(400,message)
def obj(value,label='element'):
    if not isinstance(value,dict):fail('Provide structured '+label+' properties.')
    return value
def seq(value,limit=400,label='elements'):
    if not isinstance(value,list) or len(value)>limit:fail('Use up to '+str(limit)+' '+label+'.')
    return value
def string(value,limit=16000):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value:fail('Use text up to '+str(limit)+' characters.')
    return value
def key(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',value):fail('Use stable document element identifiers.')
    return value
def number(value,low,high,integer=False):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high or integer and type(value)is not int:fail('A layout measurement is outside its allowed range.')
    return value
def choice(value,options):
    if not isinstance(value,str) or value not in options:fail('Choose a supported document property.')
    return value
def boolean(value):
    if type(value)is not bool:fail('Choose an enabled or disabled property.')
    return value
def color(value,transparent=False):
    if transparent and value=='transparent':return value
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):fail('Use a six-digit document color.')
    return value.lower()

def page(raw=None):
    raw=obj(raw or {},'page');v=deepcopy(PAGE)
    for k in ('size','orientation','font'):v[k]=choice(raw.get(k,v[k]),{'A4','A3','Letter'} if k=='size' else {'portrait','landscape'} if k=='orientation' else FONTS)
    for k in ('background','color','accent','border_color','watermark_color'):v[k]=color(raw.get(k,v[k]))
    for k,low,high in [('header_height',0,45),('footer_height',0,40),('header_gap',0,20),('footer_gap',0,20),('column_gap',2,30),('font_size',7,28),('line_height',1,3),('paragraph_spacing',0,40),('border_width',0,5),('watermark_opacity',0,0.5),('watermark_angle',-90,90)]:v[k]=number(raw.get(k,v[k]),low,high)
    v['columns']=number(raw.get('columns',1),1,3,True);v['watermark']=string(raw.get('watermark',''),120)
    margins=obj(raw.get('margins',v['margins']),'margins');v['margins']={k:number(margins.get(k,v['margins'][k]),5,80) for k in v['margins']}
    w,h=dimensions(v)
    if w-v['margins']['left']-v['margins']['right']<70 or h-v['margins']['top']-v['margins']['bottom']<90:fail('Keep enough printable space within the page margins.')
    if v['header_height']+v['header_gap']>v['margins']['top'] or v['footer_height']+v['footer_gap']>v['margins']['bottom']:fail('The header and footer must fit within their page margins.')
    return v
def dimensions(p):
    w,h={'A4':(210,297),'A3':(297,420),'Letter':(215.9,279.4)}[p['size']]
    return (h,w) if p['orientation']=='landscape' else (w,h)

def style(raw=None):
    raw=obj(raw or {},'formatting');v=deepcopy(STYLE)
    v['align']=choice(raw.get('align',v['align']),{'left','center','right','justify'});v['font']=choice(raw.get('font',v['font']),FONTS)
    v['border_style']=choice(raw.get('border_style','solid'),{'solid','dashed','dotted'})
    for k in ('color','background','border_color'):v[k]=color(raw.get(k,v[k]),k=='background')
    for k,low,high in [('border_width',0,5),('padding',0,15),('width',10,100),('height',0,300),('x',0,90),('space_before',0,50),('space_after',0,50),('font_size',7,60),('line_height',1,3)]:v[k]=number(raw.get(k,v[k]),low,high)
    for k in ('bold','italic','underline','visible','keep_together','inherit_font','inherit_color','inherit_spacing'):v[k]=boolean(raw.get(k,v[k]))
    if 'font_size' in raw or 'font' in raw:v['inherit_font']=boolean(raw.get('inherit_font',False))
    if 'color' in raw:v['inherit_color']=boolean(raw.get('inherit_color',False))
    if v['width']+v['x']>100:fail('The element must fit within the printable page width.')
    return v

def runs(raw):
    result=[];length=0
    for run in seq(raw,2000,'text spans'):
        run=obj(run,'text span');text=string(run.get('text',''),40000);length+=len(text)
        if length>80000:fail('Split long text into separate paragraphs.')
        v={'text':text}
        for k in ('bold','italic','underline'):
            if run.get(k):v[k]=boolean(run[k])
        if run.get('color'):v['color']=color(run['color'])
        if run.get('font_size') is not None:v['font_size']=number(run['font_size'],7,60)
        if run.get('field'):v['field']=choice(run['field'],FIELDS)
        result.append(v)
    return result
def plain(value):return ''.join(r.get('text','') for r in value or [])

def table(raw):
    raw=obj(raw,'table');v={'rows':number(raw.get('rows',3),1,2000,True),'columns':number(raw.get('columns',3),1,20,True),'header_rows':number(raw.get('header_rows',1),0,3,True),'cells':[]}
    if v['rows']*v['columns']>12000:fail('Split very large tables into smaller tables.')
    v['header_rows']=min(v['header_rows'],v['rows']);widths=seq(raw.get('widths',[100/v['columns']]*v['columns']),20,'column widths')
    if len(widths)!=v['columns']:fail('Configure a width for every table column.')
    v['widths']=[number(x,1,100) for x in widths];v['highlight']=boolean(raw.get('highlight',False));v['border_color']=color(raw.get('border_color','#c7d4e2'));v['border_width']=number(raw.get('border_width',0.5),0,4)
    v['header_background']=color(raw.get('header_background','#edf3f9'));seen=set();ids=set()
    for r in seq(raw.get('cells',[]),12000,'table cells'):
        r=obj(r,'cell');row=number(r.get('row'),0,v['rows']-1,True);col=number(r.get('col'),0,v['columns']-1,True)
        rs=number(r.get('rowspan',1),1,min(100,v['rows']-row),True);cs=number(r.get('colspan',1),1,v['columns']-col,True);cid=key(r.get('id'))
        if row<v['header_rows']<row+rs:fail('Keep merged header cells within the header rows.')
        if cid in ids:fail('Table cells need unique identifiers.')
        ids.add(cid)
        for y in range(row,row+rs):
            for x in range(col,col+cs):
                if (y,x) in seen:fail('Merged table cells must not overlap.')
                seen.add((y,x))
        v['cells'].append({'id':cid,'row':row,'col':col,'rowspan':rs,'colspan':cs,'runs':runs(r.get('runs',[])),'style':style(r.get('style',{}))})
    if len(seen)!=v['rows']*v['columns']:fail('Every table position needs a cell or a merged-cell anchor.')
    return v

def band(raw=None):
    raw=obj(raw or {},'header/footer');v={'enabled':boolean(raw.get('enabled',True)),'different_first':boolean(raw.get('different_first',False)),'different_even':boolean(raw.get('different_even',False)),'variants':{}}
    variants=obj(raw.get('variants',{}),'header/footer variants')
    for name in ('default','first','odd','even'):
        variant=obj(variants.get(name,{}),'header/footer layout');items=[];ids=set()
        for item in seq(variant.get('items',[]),20,'header/footer elements'):
            item=obj(item);r={'id':key(item.get('id')),'type':choice(item.get('type'),{'text','field','logo','line'}),'x':number(item.get('x',0),0,100),'y':number(item.get('y',0),0,45),'width':number(item.get('width',40),1,100),'height':number(item.get('height',7),1,40),'align':choice(item.get('align','left'),{'left','center','right'}),'color':color(item.get('color','#235789')),'font_size':number(item.get('font_size',9),6,24),'bold':boolean(item.get('bold',False))}
            if r['id'] in ids:fail('Header/footer elements need unique identifiers.')
            ids.add(r['id'])
            if r['type']=='text':r['text']=string(item.get('text',''),1000)
            if r['type']=='field':r['field']=choice(item.get('field','document_number'),FIELDS)
            if r['type']=='logo':r.update(source=choice(item.get('source','company'),{'company','customer','file'}),file_id=string(item.get('file_id',''),100))
            if r['x']+r['width']>100:fail('Header/footer elements must fit within their layout.')
            items.append(r)
        v['variants'][name]={'items':items,'background':color(variant.get('background','#ffffff')),'line_color':color(variant.get('line_color','#235789')),'line_width':number(variant.get('line_width',0.4),0,4)}
    return v

def block(raw):
    raw=obj(raw);v={'id':key(raw.get('id')),'type':choice(raw.get('type'),TYPES),'style':style(raw.get('style',{}))}
    data=obj(raw.get('data',{}),'element content');v['data']={}
    if v['type'] in {'paragraph','heading','panel','cover','signature','approval','checkbox'}:v['data']={'runs':runs(data.get('runs',[]))}
    if v['type'] in {'heading','cover'}:v['data']['level']=number(data.get('level',1),1,4,True)
    if v['type']=='panel':v['data']['title']=string(data.get('title','Information'),180)
    if v['type'] in {'signature','approval'}:v['data'].update(label=string(data.get('label','Signature'),180),name=string(data.get('name',''),180),role=string(data.get('role',''),180),date=string(data.get('date',''),80),file_id=string(data.get('file_id',''),100))
    if v['type']=='checkbox':v['data']['checked']=boolean(data.get('checked',False))
    if v['type'] in {'table','checklist'}:v['data']=table(data)
    if v['type']=='field':v['data']['field']=choice(data.get('field','project_name'),FIELDS)
    if v['type']=='image':v['data']={'file_id':string(data.get('file_id',''),100),'caption':string(data.get('caption',''),1000),'alt':string(data.get('alt',''),500),'source':choice(data.get('source','file'),{'company','customer','file'})}
    if v['type']=='native_text':v['data']={'binding':string(data.get('binding',''),180),'runs':runs(data.get('runs',[])),'source_hash':string(data.get('source_hash',''),80)}
    if v['type']=='native_table':v['data']={'binding':choice(data.get('binding'),{'requirements','cases','changes','participants','discussion_summary','decisions','actions','clarifications','next_meeting_items','engineering_requirements','sections'}),'widths':[number(x,1,100) for x in seq(data.get('widths',[]),20,'column widths')],'header_background':color(data.get('header_background','#edf3f9')),'border_color':color(data.get('border_color','#c7d4e2')),'border_width':number(data.get('border_width',0.5),0,4),'highlight':boolean(data.get('highlight',True))}
    if v['type'] in {'flowchart','native_flowchart'}:
        v['data']={'nodes':[],'edges':[]}
        for n in seq(data.get('nodes',[]),200,'flowchart nodes'):
            n=obj(n,'flowchart node');v['data']['nodes'].append({'id':key(n.get('id')),'label':string(n.get('label',''),500),'kind':choice(n.get('kind','process'),{'start','process','decision','end'}),'x':number(n.get('x',50),0,2000),'y':number(n.get('y',50),0,4000)})
        ids={n['id'] for n in v['data']['nodes']}
        if len(ids)!=len(v['data']['nodes']):fail('Flowchart nodes need unique identifiers.')
        for e in seq(data.get('edges',[]),400,'flowchart connections'):
            e=obj(e,'flowchart connection')
            if e.get('source') not in ids or e.get('target') not in ids:fail('Connect existing flowchart nodes.')
            v['data']['edges'].append({'source':e['source'],'target':e['target'],'label':string(e.get('label',''),180)})
    if v['type']=='chart':
        v['data']={'kind':choice(data.get('kind','bar'),{'bar','line','pie'}),'title':string(data.get('title','Chart'),180),'labels':[string(x,80) for x in seq(data.get('labels',[]),100,'chart labels')],'values':[number(x,-1e9,1e9) for x in seq(data.get('values',[]),100,'chart values')]}
        if len(v['data']['labels'])!=len(v['data']['values']):fail('Each chart label needs one value.')
        if v['data']['kind']=='pie' and any(x<0 for x in v['data']['values']):fail('Pie chart values cannot be negative.')
    if v['type']=='section_break':
        v['data']={'title':string(data.get('title','Section'),180),'page':page(data.get('page')),'header':band(data.get('header')),'footer':band(data.get('footer'))}
    return v

def normalize(raw):
    raw=obj(raw,'document layout');result={'schema':VERSION,'page':page(raw.get('page')),'header':band(raw.get('header')),'footer':band(raw.get('footer')),'blocks':[],'template_id':string(raw.get('template_id',''),100)}
    seen=set()
    for item in seq(raw.get('blocks',[]),1000,'document blocks'):
        value=block(item)
        if value['id'] in seen:fail('Document blocks need unique identifiers.')
        seen.add(value['id']);result['blocks'].append(value)
    return result
