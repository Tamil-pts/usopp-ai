"""Editable OOXML pages, tables and header/footer layouts from the Studio model."""
import io,re
from lxml import etree
from docx import Document
from docx.enum.section import WD_SECTION,WD_ORIENT
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from . import schema
from .render_common import sections,field_text,run_text,image_data,raster

V='urn:schemas-microsoft-com:vml';W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
MM=72/25.4
def el(name,**attrs):
    node=OxmlElement(name)
    for key,value in attrs.items():node.set(qn('w:'+key),str(value))
    return node
def xml_child(parent,name,**attrs):
    old=parent.find(qn(name))
    if old is None:old=el(name);parent.append(old)
    for key,value in attrs.items():old.set(qn('w:'+key),str(value))
    return old

def add_field(paragraph,name,value=''):
    field=el('w:fldSimple',instr={'page':'PAGE','pages':'NUMPAGES'}.get(name,name));run=el('w:r');text=el('w:t');text.text=str(value or '1');run.append(text);field.append(run);paragraph._p.append(field)

def add_runs(paragraph,runs,fields,base=None):
    for source in runs:
        if source.get('field') in {'page','pages'}:add_field(paragraph,source['field']);continue
        value=run_text(source,fields);run=paragraph.add_run(value)
        for name in ('bold','italic','underline'):
            if source.get(name) is not None:setattr(run,name,source[name])
        if source.get('color'):run.font.color.rgb=RGBColor.from_string(source['color'][1:])
        if source.get('font_size'):run.font.size=Pt(source['font_size'])
        if base:
            run.font.name=base['font'];run.font.size=Pt(source.get('font_size',base['font_size']))
            if 'color' not in source:run.font.color.rgb=RGBColor.from_string(base['color'][1:])
            if 'bold' not in source:run.bold=base['bold']
            if 'italic' not in source:run.italic=base['italic']
            if 'underline' not in source:run.underline=base['underline']

def effective(style,page):return {**style,'font':page['font'] if style.get('inherit_font') else style['font'],'font_size':page['font_size'] if style.get('inherit_font') else style['font_size'],'color':page['color'] if style.get('inherit_color') else style['color'],'line_height':page['line_height'] if style.get('inherit_font') else style['line_height'],'space_after':page['paragraph_spacing']/MM if style.get('inherit_spacing') else style['space_after']}

def paragraph_style(paragraph,style,page,width):
    s=effective(style,page);f=paragraph.paragraph_format
    paragraph.alignment={'left':WD_ALIGN_PARAGRAPH.LEFT,'center':WD_ALIGN_PARAGRAPH.CENTER,'right':WD_ALIGN_PARAGRAPH.RIGHT,'justify':WD_ALIGN_PARAGRAPH.JUSTIFY}[s['align']]
    f.space_before=Mm(s['space_before']);f.space_after=Mm(s['space_after']);f.line_spacing=s['line_height'];f.keep_together=s['keep_together'];f.left_indent=Mm(width*s['x']/100);f.right_indent=Mm(width*(100-s['width']-s['x'])/100)
    props=paragraph._p.get_or_add_pPr()
    if s['background']!='transparent':xml_child(props,'w:shd',fill=s['background'][1:],val='clear')
    if s['border_width']:
        borders=xml_child(props,'w:pBdr')
        for side in ('top','bottom','left','right'):borders.append(el('w:'+side,val={'solid':'single','dashed':'dashed','dotted':'dotted','double':'double'}[s['border_style']],sz=max(1,round(s['border_width']*MM*8)),color=s['border_color'][1:],space=round(s['padding']*MM)))
    return s

def vshape(story,x,y,width,height,background='none',line='none',line_width=0,z=1,rotation=0):
    paragraph=story.add_paragraph();paragraph.paragraph_format.space_after=Pt(0);paragraph.paragraph_format.space_before=Pt(0)
    pict=el('w:pict');shape=etree.SubElement(pict,'{'+V+'}rect',nsmap={'v':V,'r':R})
    shape.set('id','studio-shape-'+str(len(story.paragraphs)));shape.set('style',f'position:absolute;margin-left:{x*MM:.2f}pt;margin-top:{y*MM:.2f}pt;width:{width*MM:.2f}pt;height:{height*MM:.2f}pt;z-index:{z};mso-position-horizontal-relative:page;mso-position-vertical-relative:page;rotation:{rotation}')
    shape.set('filled','f' if background=='none' else 't');shape.set('stroked','f' if line=='none' or not line_width else 't')
    if background!='none':shape.set('fillcolor',background)
    if line!='none':shape.set('strokecolor',line);shape.set('strokeweight',str(line_width*MM)+'pt')
    paragraph.add_run()._r.append(pict);return shape

def band(story,cfg,variant,page,fields,value,part):
    # Unlink before writing; native Word retains section-specific definitions.
    story.is_linked_to_previous=False
    for p in story.paragraphs:p.clear()
    if not cfg['enabled']:return
    layout=cfg['variants'][variant]
    if not layout['items'] and variant!='first':layout=cfg['variants']['default']
    w,h=schema.dimensions(page);m=page['margins'];top=m['top']-page['header_height']-page['header_gap'] if part=='header' else h-m['bottom']+page['footer_gap'];height=page[part+'_height'];width=w-m['left']-m['right']
    if layout['background']!='#ffffff':vshape(story,m['left'],top,width,height,layout['background'],z=-10)
    if layout['line_width']:
        line_y=top+height if part=='header' else top
        vshape(story,m['left'],line_y,width,.1,'none',layout['line_color'],layout['line_width'])
    for item in layout['items']:
        x=m['left']+width*item['x']/100;y=top+item['y'];ww=width*item['width']/100;hh=item['height']
        shape=vshape(story,x,y,ww,hh)
        if item['type']=='logo':
            raw=image_data(value,item['source'],item.get('file_id',''))
            if not raw:continue
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:ratio=im.width/im.height
            fitted_w=min(ww,hh*ratio);fitted_h=fitted_w/ratio
            shape.set('style',f'position:absolute;margin-left:{(x+(ww-fitted_w)/2)*MM:.2f}pt;margin-top:{(y+(hh-fitted_h)/2)*MM:.2f}pt;width:{fitted_w*MM:.2f}pt;height:{fitted_h*MM:.2f}pt;z-index:1;mso-position-horizontal-relative:page;mso-position-vertical-relative:page')
            rid,_=story.part.get_or_add_image(io.BytesIO(raw));image=etree.SubElement(shape,'{'+V+'}imagedata');image.set('{'+R+'}id',rid)
        elif item['type']=='line':shape.set('stroked','t');shape.set('strokecolor',item['color']);shape.set('strokeweight','1pt');shape.set('style',shape.get('style').replace(f'height:{hh*MM:.2f}pt','height:0.1pt'))
        else:
            box=etree.SubElement(shape,'{'+V+'}textbox');box.set('inset','0,0,0,0');content=el('w:txbxContent');box.append(content)
            paragraph=story.add_paragraph();story._element.remove(paragraph._p);content.append(paragraph._p)
            paragraph.alignment={'left':WD_ALIGN_PARAGRAPH.LEFT,'center':WD_ALIGN_PARAGRAPH.CENTER,'right':WD_ALIGN_PARAGRAPH.RIGHT}[item['align']]
            paragraph.paragraph_format.space_after=Pt(0)
            text=item.get('text','') if item['type']=='text' else '{'+item['field']+'}'
            parts=re.split(r'(\{(?:page|pages)\})',field_text(text,fields))
            for text in parts:
                if text in {'{page}','{pages}'}:add_field(paragraph,text[1:-1]);continue
                run=paragraph.add_run(text);run.font.name=page['font'];run.font.size=Pt(item['font_size']);run.font.color.rgb=RGBColor.from_string(item['color'][1:]);run.bold=item['bold']

def page_background(story,page):
    w,h=schema.dimensions(page)
    if page['background']!='#ffffff':vshape(story,0,0,w,h,page['background'],z=-251658241)
    if page['border_width']:vshape(story,4,4,w-8,h-8,'none',page['border_color'],page['border_width'],z=-251658240)
    if page['watermark']:
        shape=vshape(story,15,h/2-20,w-30,50,z=-251658239,rotation=-page['watermark_angle']);box=etree.SubElement(shape,'{'+V+'}textbox');content=el('w:txbxContent');box.append(content)
        p=story.add_paragraph();story._element.remove(p._p);content.append(p._p);p.alignment=WD_ALIGN_PARAGRAPH.CENTER;r=p.add_run(page['watermark']);r.font.name=page['font'];r.font.size=Pt(42)
        rgb=[int(page['watermark_color'][i:i+2],16) for i in (1,3,5)];bg=[int(page['background'][i:i+2],16) for i in (1,3,5)];alpha=page['watermark_opacity'];r.font.color.rgb=RGBColor(*[round(alpha*c+(1-alpha)*b) for c,b in zip(rgb,bg)])

def configure(section,cfg,document,value):
    p=cfg['page'];w,h=schema.dimensions(p);m=p['margins'];section.orientation=WD_ORIENT.LANDSCAPE if p['orientation']=='landscape' else WD_ORIENT.PORTRAIT;section.page_width=Mm(w);section.page_height=Mm(h)
    for side in ('top','right','bottom','left'):setattr(section,side+'_margin',Mm(m[side]))
    section.header_distance=Mm(max(0,m['top']-p['header_height']-p['header_gap']));section.footer_distance=Mm(max(0,m['bottom']-p['footer_height']-p['footer_gap']))
    cols=section._sectPr.find(qn('w:cols'))
    if cols is None:cols=el('w:cols');section._sectPr.append(cols)
    cols.set(qn('w:num'),str(p['columns']));cols.set(qn('w:space'),str(round(p['column_gap']*MM*20)))
    section.different_first_page_header_footer=cfg['header']['different_first'] or cfg['footer']['different_first']
    if cfg['header']['different_even'] or cfg['footer']['different_even']:document.settings.odd_and_even_pages_header_footer=True
    fields={**value['fields'],'section_title':cfg['title']}
    for part in ('header','footer'):
        settings=cfg[part]
        for variant,story in [('default',getattr(section,part)),('first',getattr(section,'first_page_'+part)),('even',getattr(section,'even_page_'+part))]:
            selected='first' if variant=='first' and settings['different_first'] else 'even' if variant=='even' and settings['different_even'] else 'odd' if variant=='default' and settings['different_even'] else 'default'
            band(story,settings,selected,p,fields,value,part)
            if part=='header':page_background(story,p)

def add_table(target,block,page,width,value):
    d=block['data'];table=target.add_table(rows=d['rows'],cols=d['columns']);table.autofit=False
    props=table._tbl.tblPr;xml_child(props,'w:tblLayout',type='fixed');xml_child(props,'w:tblInd',w=round(width*block['style']['x']/100*MM*20),type='dxa')
    actual=width*block['style']['width']/100;widths=[actual*w/sum(d['widths']) for w in d['widths']]
    for x,w in enumerate(widths):table.columns[x].width=Mm(w)
    for y,row in enumerate(table.rows):
        if block['style']['height']:
            row.height=Mm(block['style']['height']/d['rows']);row.height_rule=WD_ROW_HEIGHT_RULE.AT_LEAST
        if y<d['header_rows']:row._tr.get_or_add_trPr().append(el('w:tblHeader',val='true'))
    for cell in sorted(d['cells'],key=lambda c:(c['row'],c['col'])):
        y,x=cell['row'],cell['col'];item=table.cell(y,x)
        if cell['rowspan']>1 or cell['colspan']>1:item=item.merge(table.cell(y+cell['rowspan']-1,x+cell['colspan']-1))
        item.width=Mm(sum(widths[x:x+cell['colspan']]));item._tc.clear_content();p=item.add_paragraph()
        s={**cell['style'],'x':0,'width':100,'space_before':0,'space_after':0,'inherit_spacing':False};plain=schema.plain(cell['runs']).strip().casefold()
        fill=s['background']
        if y<d['header_rows']:fill=d['header_background'];s['bold']=True
        elif d.get('highlight'):
            if plain in {'pass','passed','completed'}:fill='#dcf4e9'
            elif plain in {'fail','failed','blocked'}:fill='#fde7e5'
            elif plain in {'n/a','not applicable'}:fill='#f0f2f5'
        props=item._tc.get_or_add_tcPr()
        if fill!='transparent':xml_child(props,'w:shd',fill=fill[1:],val='clear')
        borders=xml_child(props,'w:tcBorders')
        for side in ('top','bottom','left','right'):borders.append(el('w:'+side,val='single' if d['border_width'] else 'nil',color=d['border_color'][1:],sz=max(1,round(d['border_width']*MM*8))))
        margins=xml_child(props,'w:tcMar')
        for side in ('top','bottom','left','right'):margins.append(el('w:'+side,w=round(s['padding']*MM*20),type='dxa'))
        base=paragraph_style(p,s,page,sum(widths[x:x+cell['colspan']]));add_runs(p,cell['runs'],value['fields'],base)
    return table

def render(value):
    document=Document();configs=sections(value)
    normal=document.styles['Normal'];normal.font.name=configs[0]['page']['font'];normal.font.size=Pt(configs[0]['page']['font_size'])
    document.settings.element.append(el('w:updateFields',val='true'))
    for index,cfg in enumerate(configs):
        section=document.sections[0] if index==0 else document.add_section(WD_SECTION.NEW_PAGE);configure(section,cfg,document,value)
        page=cfg['page'];w,h=schema.dimensions(page);width=(w-page['margins']['left']-page['margins']['right']-(page['columns']-1)*page['column_gap'])/page['columns'];body_height=h-page['margins']['top']-page['margins']['bottom']
        for b in cfg['blocks']:
            typ=b['type'];data=b['data'];style=b['style']
            if typ=='page_break':document.add_page_break();continue
            if typ in {'table','checklist'}:add_table(document,b,page,width,value);continue
            if typ=='approval':
                p=document.add_paragraph();base=paragraph_style(p,style,page,width);add_runs(p,[{'text':data.get('label','Recorded approval'),'bold':True}],value['fields'],base)
                rows=data.get('recorded',[]);cells=[{'id':str(y)+':'+str(x),'row':y,'col':x,'rowspan':1,'colspan':1,'runs':[{'text':str(v)}],'style':schema.style({'font_size':9})} for y,r in enumerate(rows) for x,v in enumerate((r['label'],r['name'],r['date']))]
                if rows:add_table(document,{'style':style,'data':{'rows':len(rows),'columns':3,'header_rows':0,'widths':[25,40,35],'cells':cells,'border_width':0.3,'border_color':'#c7d4e2','header_background':'#edf3f9'}},page,width,value)
                continue
            if style['height'] and typ in {'paragraph','panel','heading','cover','checkbox'}:
                runs=([{'text':data['title']+'\n','bold':True}] if typ=='panel' and data.get('title') else [])+([{'text':chr(0x2611 if data['checked'] else 0x2610)+' '}] if typ=='checkbox' else [])+data.get('runs',[])
                add_table(document,{'style':style,'data':{'rows':1,'columns':1,'header_rows':0,'widths':[100],'cells':[{'id':'text','row':0,'col':0,'rowspan':1,'colspan':1,'runs':runs,'style':style}],'border_width':style['border_width'],'border_color':style['border_color'],'header_background':'#ffffff'}},page,width,value)
                continue
            p=document.add_paragraph();base=paragraph_style(p,style,page,width)
            if typ in {'heading','cover'}:p.paragraph_format.keep_with_next=True
            if typ=='panel' and data.get('title'):add_runs(p,[{'text':data['title']+'\n','bold':True}],value['fields'],base)
            if typ=='line':
                borders=xml_child(p._p.get_or_add_pPr(),'w:pBdr');borders.append(el('w:bottom',val='single',color=style['color'][1:],sz=max(4,round(max(.3,style['border_width'])*MM*8))));continue
            if typ in {'image','chart','flowchart','signature'}:
                raw=raster(b,page['accent']) if typ in {'chart','flowchart'} else image_data(value,data.get('source','file'),data.get('file_id',''))
                if raw:
                    from PIL import Image
                    with Image.open(io.BytesIO(raw)) as im:ratio=im.height/im.width
                    ww=width*style['width']/100;hh=style['height'] or ww*ratio
                    if hh>body_height-8:ww*=max(1,body_height-8)/hh;hh=max(1,body_height-8)
                    p.add_run().add_picture(io.BytesIO(raw),width=Mm(ww),height=Mm(hh))
                if typ=='image' and data.get('caption'):add_runs(p,[{'text':'\n'+data['caption'],'font_size':9}],value['fields'],base)
                if typ in {'image','chart','flowchart'}:continue
            if typ=='signature':
                add_runs(p,[{'text':data['label']+'\n'+(data.get('name') or 'Signature / name')+'\n'+data.get('role','')+' '+data.get('date','')}],value['fields'],base)
                borders=xml_child(p._p.get_or_add_pPr(),'w:pBdr');borders.append(el('w:bottom',val='single',color='9babb9',sz=4))
            if typ=='checkbox':
                run=p.add_run('☑ ' if data['checked'] else '☐ ');run.font.name='Segoe UI Symbol'
            add_runs(p,data.get('runs',[]),value['fields'],base)
    document.core_properties.title=value['fields']['document_title'];document.core_properties.author=value['fields']['company'];document.core_properties.subject=value['fields']['document_number']+' / '+value['fields']['revision'];document.core_properties.comments='WorkHub source revision '+value['revision_id']+' / SHA-256 '+value['source_hash']
    output=io.BytesIO();document.save(output);return output.getvalue()
