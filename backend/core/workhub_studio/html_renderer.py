"""One safe paginated canvas for browser editing and the PDF worker."""
from html import escape
import base64,json
from . import schema
from .render_common import sections,field_text,run_text,image_data,diagram_svg,chart_svg

def css_style(style,page):
    font=page['font'] if style.get('inherit_font') else style['font'];size=page['font_size'] if style.get('inherit_font') else style['font_size'];color=page['color'] if style.get('inherit_color') else style['color']
    return (('min-height:'+str(style['height'])+'mm;') if style['height'] else '')+';'.join([f'font-family:"{font}",Arial,sans-serif',f'font-size:{size}pt',f'color:{color}',f'background:{style["background"]}',f'text-align:{style["align"]}',f'line-height:{page["line_height"] if style.get("inherit_font") else style["line_height"]}',f'padding:{style["padding"]}mm',f'margin-top:{style["space_before"]}mm',f'margin-bottom:{page["paragraph_spacing"]}pt' if style.get('inherit_spacing') else f'margin-bottom:{style["space_after"]}mm',f'width:{style["width"]}%',f'margin-left:{style["x"]}%',f'border:{style["border_width"]}mm {style["border_style"]} {style["border_color"]}',f'font-weight:{"bold" if style["bold"] else "normal"}',f'font-style:{"italic" if style["italic"] else "normal"}',f'text-decoration:{"underline" if style["underline"] else "none"}', 'break-inside:avoid' if style['keep_together'] else 'break-inside:auto'])

def rich(runs,fields):
    result=[]
    for run in runs:
        value=escape(run_text(run,fields)).replace('\n','<br>');style=[]
        for flag,prop,val in [('bold','font-weight','bold'),('italic','font-style','italic'),('underline','text-decoration','underline')]:
            if run.get(flag):style.append(prop+':'+val)
        if run.get('color'):style.append('color:'+run['color'])
        if run.get('font_size'):style.append('font-size:'+str(run['font_size'])+'pt')
        extra=' data-field="'+run['field']+'" contenteditable="false"' if run.get('field') else ''
        result.append('<span style="'+';'.join(style)+'"'+extra+'>'+value+'</span>')
    return ''.join(result) or '<br data-placeholder="true">'

def block_html(block,value,page,editable=False,locks=None):
    typ=block['type'];data=block['data'];bid=block['id'];style=block['style'];attrs=' data-block-id="'+escape(bid,quote=True)+'" data-block-type="'+typ+'"';locked=any(l['element_id'] in {'document',bid} and l['kind']=='content' for l in locks or [])
    edit='true' if editable and not locked else 'false'
    def text(content,key='text',extra=''):return '<div class="ds-text" data-text-key="'+escape(bid+'|'+key,quote=True)+'" contenteditable="'+edit+'" spellcheck="true" '+extra+'>'+rich(content,value['fields'])+'</div>'
    content=''
    if typ in {'paragraph','heading','cover','panel'}:
        content=(('<div class="ds-panel-title">'+escape(data.get('title',''))+'</div>') if typ=='panel' else '')+text(data.get('runs',[]))
    elif typ in {'table','checklist'}:
        cells={(c['row'],c['col']):c for c in data['cells']};widths=data['widths'];colgroup='<colgroup>'+''.join('<col style="width:'+str(w/sum(widths)*100)+'%">' for w in widths)+'</colgroup>'
        rows=[]
        for y in range(data['rows']):
            pieces=[]
            for x in range(data['columns']):
                cell=cells.get((y,x))
                if not cell:continue
                header=y<data['header_rows'];tag='th' if header else 'td';cs={**cell['style'],'width':100,'x':0,'space_before':0,'space_after':0,'height':0,'inherit_spacing':False};fill=cs['background']
                plain=schema.plain(cell['runs']).strip().casefold()
                if data.get('highlight'):
                    if plain in {'pass','passed','completed'}:fill='#dcf4e9'
                    elif plain in {'fail','failed','blocked'}:fill='#fde7e5'
                    elif plain in {'n/a','not applicable'}:fill='#f0f2f5'
                if header:fill=data['header_background']
                cs['background']=fill;cs['border_width']=data['border_width'];cs['border_color']=data['border_color']
                cell_id=cell['id'];native=' data-native-binding="'+escape(data['binding'])+'" data-native-row="'+escape(cell.get('native_row',''),quote=True)+'" data-native-index="'+str(cell.get('native_index',''))+'" data-native-field="'+escape(cell.get('native_field',''))+'"' if data.get('binding') else ''
                cell_edit='false' if cell.get('native_readonly') or data.get('binding') and header else edit
                key=bid+'|cell:'+cell_id
                content_html='<div class="ds-text" data-text-key="'+escape(key,quote=True)+'" data-cell-id="'+escape(cell_id,quote=True)+'"'+native+' contenteditable="'+cell_edit+'">'+rich(cell['runs'],value['fields'])+'</div>'
                pieces.append('<'+tag+' data-cell-id="'+escape(cell_id,quote=True)+'" rowspan="'+str(cell['rowspan'])+'" colspan="'+str(cell['colspan'])+'" style="'+css_style(cs,page)+'">'+content_html+'</'+tag+'>')
            rows.append('<tr data-row="'+str(y)+'">'+''.join(pieces)+'</tr>')
        n=data['header_rows'];content='<table class="ds-table" style="'+('height:'+str(style['height'])+'mm;' if style['height'] else '')+'" data-native-binding="'+escape(data.get('binding',''))+'">'+colgroup+('<thead>'+''.join(rows[:n])+'</thead>' if n else '')+'<tbody>'+''.join(rows[n:])+'</tbody></table>'
    elif typ=='image':
        raw=image_data(value,data.get('source','file'),data.get('file_id',''));src='data:image/png;base64,'+base64.b64encode(raw).decode() if raw else ''
        content=('<img class="ds-picture" src="'+src+'" alt="'+escape(data.get('alt',''),quote=True)+'" style="'+('height:'+str(style['height'])+'mm;' if style['height'] else '')+'">') if raw else '<div class="ds-empty-image">Choose an image or logo</div>'
        if data.get('caption'):content+='<div class="ds-caption">'+escape(data['caption'])+'</div>'
    elif typ in {'flowchart','chart'}:content=(chart_svg(block,page['accent']) if typ=='chart' else diagram_svg(block,page['accent']))
    elif typ=='line':content='<hr style="border:0;border-top:'+str(max(.3,style['border_width']))+'mm '+style['border_style']+' '+style['color']+'">'
    elif typ=='checkbox':content='<span class="ds-checkbox" data-checkbox="'+escape(bid)+'">'+('☑' if data['checked'] else '☐')+'</span>'+text(data.get('runs',[]))
    elif typ=='signature':
        raw=image_data(value,'file',data.get('file_id','')) if data.get('file_id') else None
        content='<div class="ds-signature-label">'+escape(data['label'])+'</div>'
        if raw:content+='<img class="ds-signature-image" src="data:image/png;base64,'+base64.b64encode(raw).decode()+'">'
        content+='<div class="ds-signature-line">'+escape(data.get('name') or 'Signature / name')+'</div><div>'+escape(data.get('role',''))+' &nbsp; '+escape(data.get('date',''))+'</div>'+text(data.get('runs',[]))
    elif typ=='approval':
        content='<div class="ds-approval-heading">'+escape(data.get('label','Review and approval'))+'</div><table class="ds-table"><tbody>'
        for row in data.get('recorded',[]):content+='<tr><th>'+escape(row['label'])+'</th><td>'+escape(str(row['name']))+'</td><td>'+escape(str(row['date']))+'</td></tr>'
        content+='</tbody></table>'
    elif typ=='page_break':return '<div'+attrs+' class="ds-page-break"><span>Page break</span></div>'
    grip='<button class="ds-block-grip" type="button" data-grip="'+escape(bid)+'" draggable="true" aria-label="Move block">⋮⋮</button>' if editable else ''
    return '<div'+attrs+' class="ds-block ds-'+typ+(' ds-content-locked' if locked else '')+'" style="'+css_style(style,page)+'">'+grip+content+'</div>'

BASE_CSS='''
*{box-sizing:border-box}html,body{margin:0;padding:0}body{background:#e8edf3;color:#243b53;font-family:Arial,sans-serif}.ds-source{visibility:hidden;position:absolute;left:-100000px;top:0}.ds-output{padding:24px 10px}.pagedjs_pages{display:flex;flex-direction:column;align-items:center;gap:24px}.pagedjs_page{background:white;flex:none;box-shadow:0 5px 22px #243b5326;position:relative}.pagedjs_sheet{position:relative;background:white}.pagedjs_area{z-index:2}.ds-block{position:relative;max-width:100%;overflow-wrap:anywhere}.ds-text{outline:0;min-height:1em;white-space:pre-wrap;overflow-wrap:anywhere}.ds-table{border-collapse:collapse;table-layout:fixed;width:100%;font-size:9pt}.ds-table th,.ds-table td{vertical-align:top;white-space:normal;overflow-wrap:anywhere}.ds-table th{font-weight:600}.ds-table thead{display:table-header-group}.ds-table tr{break-inside:avoid}.ds-picture{max-width:100%;max-height:205mm;object-fit:contain;display:block}.ds-caption{font-size:9pt;color:#657a91;text-align:center;margin-top:2mm}.ds-block svg{display:block;max-width:100%;max-height:205mm;width:100%;height:auto}.ds-signature-line{border-bottom:1px solid #9babb9;min-height:12mm;padding-top:4mm}.ds-signature-label,.ds-approval-heading,.ds-panel-title{font-weight:bold;margin-bottom:3mm}.ds-signature-image{max-width:60mm;max-height:25mm;object-fit:contain}.ds-checkbox{float:left;margin-right:3mm}.ds-empty-image{border:1px dashed #aab9c9;padding:10mm;text-align:center;color:#8191a2}.ds-page-break{break-after:page;height:0}.ds-page-break span{display:none}.ds-page-band{position:absolute;left:0;z-index:3;overflow:hidden;pointer-events:none}.ds-band-item{position:absolute;overflow:hidden;white-space:pre-wrap}.ds-band-item img{width:100%;height:100%;object-fit:contain}.ds-page-watermark{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:0;pointer-events:none}.ds-page-watermark span{white-space:nowrap;font-size:45pt}.ds-page-border{position:absolute;inset:4mm;z-index:0;pointer-events:none}.ds-block-grip{display:none}.ds-editor .ds-block-grip{display:block;position:absolute;left:-6mm;top:0;border:0;background:transparent;color:#8396aa;padding:1mm;cursor:grab;opacity:0;z-index:6}.ds-editor .ds-block:hover>.ds-block-grip,.ds-editor .ds-block.ds-selected>.ds-block-grip{opacity:1}.ds-editor .ds-block.ds-selected{outline:1px solid #2a78c5;outline-offset:1mm}.ds-editor [contenteditable=true]:focus{box-shadow:0 0 0 1px #b8d2ee}.ds-editor .ds-page-break{height:6mm;border-top:1px dashed #bdcbd9;color:#70869d;break-after:page}.ds-editor .ds-page-break span{display:block;font-size:8pt}.ds-editor .ds-content-locked:after{content:'Locked';position:absolute;right:0;top:0;font-size:7pt;color:#718399;background:#edf1f6;padding:1mm;pointer-events:none}.ds-editor .ds-cell-selected{outline:2px solid #2782cb;outline-offset:-2px}.ds-editor .ds-comment-mark{background:#fff0af}.ds-editor .ds-band-selected{outline:1px dashed #2782cb}.ds-page-band:focus{outline:0}@media print{body{background:white}.ds-output{padding:0}.pagedjs_pages{display:block}.pagedjs_page{margin:0!important;box-shadow:none!important;break-after:page}.pagedjs_page:last-child{break-after:auto}.ds-block-grip{display:none!important}.ds-page-break span{display:none!important}.ds-page-break{height:0!important;border:0!important}.ds-selected{outline:0!important}.ds-content-locked:after{display:none!important}}
'''

PAGINATE_JS=r'''
async function startStudio(){
 try{
 const model=window.__studioModel, editable=window.__studioEditable;
 const source=document.getElementById('studio-source'),output=document.getElementById('studio-output');
 const flow=await new Paged.Previewer().preview(source.innerHTML,[{'studio-layout':window.__studioCSS}],output);
 const pages=[...output.querySelectorAll('.pagedjs_page')];let last='',local=0;
 function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
 function replace(s,fields){return String(s??'').replace(/\{([a-z_]+)\}/g,(m,k)=>fields[k]??m);}
 pages.forEach((page,index)=>{
   let key=page.getAttribute('data-page-name')||'';
   let section=model.sections.find(s=>key===s.id||page.classList.contains('pagedjs_'+s.id+'_page'));
   if(!section){const marker=page.querySelector('[data-section-id]');section=model.sections.find(s=>s.id===marker?.getAttribute('data-section-id'))||model.sections[0];}
   if(section.id!==last){last=section.id;local=0;}local++;
   page.dataset.studioSection=section.id;page.dataset.studioPage=String(index+1);
   const p=section.page,sheet=page.querySelector('.pagedjs_sheet')||page;
   const dims=p.orientation==='landscape'?[model.sizes[p.size][1],model.sizes[p.size][0]]:model.sizes[p.size];
   for(const side of ['', '-left','-right']){page.style.setProperty('--pagedjs-width'+side,dims[0]+'mm');page.style.setProperty('--pagedjs-height'+side,dims[1]+'mm');}
   const fields={...model.fields,page:String(index+1),pages:String(pages.length),section_title:section.title};
   sheet.style.background=p.background;
   const border=document.createElement('div');border.className='ds-page-border';border.style.border=p.border_width+'mm solid '+p.border_color;sheet.prepend(border);
   if(p.watermark){const wm=document.createElement('div');wm.className='ds-page-watermark';wm.innerHTML='<span>'+esc(replace(p.watermark,fields))+'</span>';wm.style.opacity=String(p.watermark_opacity);wm.style.color=p.watermark_color;wm.firstChild.style.transform='rotate('+p.watermark_angle+'deg)';sheet.prepend(wm);}
   for(const part of ['header','footer']){
    const cfg=section[part];if(!cfg.enabled)continue;
    const variant=cfg.different_first&&local===1?'first':cfg.different_even?(index+1)%2===0?'even':'odd':'default';
    let layout=cfg.variants[variant];if(!layout.items.length&&variant!=='first')layout=cfg.variants.default;
    const band=document.createElement('div');band.className='ds-page-band ds-'+part;band.dataset.band=part;band.dataset.variant=variant;band.dataset.section=section.id;
    band.style.left=p.margins.left+'mm';band.style.width=(dims[0]-p.margins.left-p.margins.right)+'mm';band.style.height=p[part+'_height']+'mm';band.style.background=layout.background;
    if(part==='header'){band.style.top=(p.margins.top-p.header_height-p.header_gap)+'mm';band.style.borderBottom=layout.line_width+'mm solid '+layout.line_color;}
    else{band.style.bottom=(p.margins.bottom-p.footer_height-p.footer_gap)+'mm';band.style.borderTop=layout.line_width+'mm solid '+layout.line_color;}
    for(const item of layout.items){
      const el=document.createElement('div');el.className='ds-band-item';el.dataset.bandItem=item.id;
      Object.assign(el.style,{left:item.x+'%',top:item.y+'mm',width:item.width+'%',height:item.height+'mm',textAlign:item.align,color:item.color,fontSize:item.font_size+'pt',fontWeight:item.bold?'bold':'normal'});
      if(item.type==='logo'){const key=item.source==='file'?item.file_id:item.source,asset=model.assets[key];if(asset)el.innerHTML='<img alt="'+esc(item.source+' logo')+'" src="data:image/png;base64,'+asset.data+'">';}
      else if(item.type==='line')el.style.borderTop='0.4mm solid '+item.color;
      else el.innerHTML=esc(item.type==='field'?fields[item.field]??'':replace(item.text,fields)).replace(/\n/g,'<br>');
      band.append(el);
    }
    if(editable){band.style.pointerEvents='auto';band.title='Double-click to design '+part;band.addEventListener('dblclick',()=>parent.postMessage({type:'studio-band',part,section:section.id,variant},'*'));}
    sheet.append(band);
   }
   page.querySelectorAll('[data-field=page],[data-field=pages]').forEach(el=>el.textContent=fields[el.dataset.field]);
 });
 source.remove();document.documentElement.dataset.studioReady='true';window.__studioPages=pages.length;
 parent.postMessage({type:'studio-ready',pages:pages.length},'*');
 }catch(error){document.documentElement.dataset.studioError=String(error);parent.postMessage({type:'studio-error',message:String(error)},'*');}
}
'''

def html(value,editable=False,locks=None,script_url='/studio/paged.polyfill.min.js',embed_script=None):
    configs=sections(value);styles=[BASE_CSS];bodies=[]
    first=configs[0]['page'];fw,fh=schema.dimensions(first);fm=first['margins']
    styles.append('@page{size:'+str(fw)+'mm '+str(fh)+'mm;margin:'+str(fm['top'])+'mm '+str(fm['right'])+'mm '+str(fm['bottom'])+'mm '+str(fm['left'])+'mm;}')
    for section in configs:
        p=section['page'];w,h=schema.dimensions(p);m=p['margins'];sid=section['id']
        styles.append('@page '+sid+'{size:'+str(w)+'mm '+str(h)+'mm;margin:'+str(m['top'])+'mm '+str(m['right'])+'mm '+str(m['bottom'])+'mm '+str(m['left'])+'mm;}')
        styles.append('.'+sid+'{page:'+sid+';font-family:"'+p['font']+'",Arial,sans-serif;font-size:'+str(p['font_size'])+'pt;line-height:'+str(p['line_height'])+';color:'+p['color']+';'+('columns:'+str(p['columns'])+';column-gap:'+str(p['column_gap'])+'mm;' if p['columns']>1 else '')+'}')
        bodies.append('<section class="'+sid+'" data-section-id="'+sid+'">'+''.join(block_html(b,value,p,editable,locks) for b in section['blocks'])+'</section>')
    css='\n'.join(styles);model={'sections':[{k:v for k,v in s.items() if k!='blocks'} for s in configs],'fields':value['fields'],'assets':value['assets'],'sizes':{'A4':[210,297],'A3':[297,420],'Letter':[215.9,279.4]}}
    safe=lambda x:json.dumps(x,ensure_ascii=False).translate({ord('<'):chr(92)+'u003c',ord('>'):chr(92)+'u003e',ord('&'):chr(92)+'u0026'})
    script='<script>'+embed_script+'</script>' if embed_script is not None else '<script src="'+escape(script_url,quote=True)+'"></script>'
    return '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+escape(value['fields']['document_title'])+'</title><style>'+BASE_CSS+'</style><script>window.PagedConfig={auto:false};window.__studioModel='+safe(model)+';window.__studioCSS='+safe(css)+';window.__studioEditable='+('true' if editable else 'false')+';</script>'+script+'</head><body class="'+('ds-editor' if editable else 'ds-print')+'"><div id="studio-source" class="ds-source">'+''.join(bodies)+'</div><div id="studio-output" class="ds-output"></div><script>'+PAGINATE_JS+';startStudio();</script></body></html>'
