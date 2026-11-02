"""Native, editable PDF review annotations and a portable revision envelope.

The PDF comments remain ordinary Square/Line/Text annotations. The attachment
retains e-design properties/history; no account IDs, cookies or ACLs are exported.
"""
from datetime import datetime,timezone
from io import BytesIO
import hashlib
import json
import re
import uuid

from pypdf import PdfReader,PdfWriter
from pypdf.generic import (ArrayObject,BooleanObject,DecodedStreamObject,DictionaryObject,
                           FloatObject,NameObject,NumberObject,TextStringObject)

ATTACHMENT='uSOPp-e-design-review.json'
SUPPORTED={'/Square','/Circle','/Line','/Text','/FreeText','/Polygon','/PolyLine','/Highlight','/Underline','/StrikeOut','/Ink'}
FIELDS=('page','kind','shape','box','body','status','reverseX','reverseY','callout','color','opacity','points')


def array(values):return ArrayObject([FloatObject(v) for v in values])
def date(value):return datetime.fromtimestamp(value,timezone.utc).strftime('D:%Y%m%d%H%M%SZ')
def snapshot(mark):return {k:mark.get(k) for k in FIELDS}

def envelope_data(reader):
    if ATTACHMENT not in reader.attachments:return {}
    raw=reader.attachments[ATTACHMENT][0]
    if len(raw)>8*1024*1024:raise ValueError('The embedded review history is too large.')
    data=json.loads(raw)
    if not isinstance(data,dict) or data.get('schema')!=1 or not isinstance(data.get('marks'),list):raise ValueError('Unsupported review metadata.')
    return data

def drawing_range(reader):
    data=envelope_data(reader);offset=data.get('drawingPageOffset',0);count=data.get('pageCount',len(reader.pages))
    if type(offset)is not int or type(count)is not int or offset<0 or count<1 or count>150 or offset+count>len(reader.pages):raise ValueError('Invalid drawing page count.')
    return offset,offset+count


def managed_annotation(annotation):
    a=annotation.get_object()
    return (str(a.get('/NM','')).startswith(('edesign:','edesign-history:')) or bool(a.get('/IRT')) or
            (a.get('/Subtype') in SUPPORTED and bool(str(a.get('/Contents','')).strip())) or a.get('/Subtype')=='/Popup')


def review_background(source,target):
    """A display copy retains unmanaged annotations; the uploaded file is intact."""
    reader=PdfReader(source);writer=PdfWriter();writer.append(reader,pages=drawing_range(reader))
    for page in writer.pages:
        page[NameObject('/Annots')]=ArrayObject([a for a in page.get('/Annots',[]) if not managed_annotation(a)])
    with target.open('wb') as stream:writer.write(stream)


def appearance(writer,page,mark,index):
    from reportlab.pdfgen.canvas import Canvas
    from python_engine.edesign_export import draw_mark
    width,height=float(page.cropbox.width),float(page.cropbox.height)
    left,bottom=float(page.cropbox.left),float(page.cropbox.bottom)
    x0,y0,x1,y1=mark['box'];rect=[left+x0*width,bottom+(1-y1)*height,left+x1*width,bottom+(1-y0)*height]
    stream=BytesIO();c=Canvas(stream,pagesize=(width,height))
    # Keep cloud lobes inside its native annotation rectangle.
    drawn=dict(mark)
    drawn['callout']=None
    if mark['shape'] in {'cloud','cloud-only'}:
        inset=min(.008,(x1-x0)/5,(y1-y0)/5)
        drawn['box']=[x0+inset,y0+inset,x1-inset,y1-inset]
    draw_mark(c,drawn,width,height,index);c.save();stream.seek(0)
    ap_page=PdfReader(stream).pages[0]
    form=DecodedStreamObject()
    form.set_data(f'q 1 0 0 1 {left} {bottom} cm\n'.encode()+ap_page.get_contents().get_data()+b'\nQ')
    form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
                 NameObject('/BBox'):array(rect),NameObject('/Resources'):ap_page['/Resources'].clone(writer)})
    return rect,writer._add_object(form)


def callout_appearance(writer,page,mark,part):
    from reportlab.pdfgen.canvas import Canvas
    from .edesign_callout import draw_callout,leader
    w,h=float(page.cropbox.width),float(page.cropbox.height);left,bottom=float(page.cropbox.left),float(page.cropbox.bottom)
    if part=='label':
        x0,y0,x1,y1=mark['callout'];rect=[left+x0*w,bottom+(1-y1)*h,left+x1*w,bottom+(1-y0)*h]
    else:
        points=leader(mark);rect=[left+min(x for x,y in points)*w-10,bottom+(1-max(y for x,y in points))*h-10,left+max(x for x,y in points)*w+10,bottom+(1-min(y for x,y in points))*h+10]
    stream=BytesIO();c=Canvas(stream,pagesize=(w,h));draw_callout(c,mark,w,h,part);c.save();stream.seek(0);ap=PdfReader(stream).pages[0]
    form=DecodedStreamObject();form.set_data(f'q 1 0 0 1 {left} {bottom} cm\n'.encode()+ap.get_contents().get_data()+b'\nQ')
    form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),NameObject('/BBox'):array(rect),NameObject('/Resources'):ap['/Resources'].clone(writer)})
    return rect,writer._add_object(form)

def reference_annotation(writer,page,mark,index,root):
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.colors import HexColor
    from .edesign_style import reference_color,reference
    w,h=float(page.cropbox.width),float(page.cropbox.height);left,bottom=float(page.cropbox.left),float(page.cropbox.bottom)
    x=left+mark['box'][0]*w;y=min(bottom+h-12,bottom+(1-mark['box'][1])*h+2)
    rect=[x,y,min(left+w,x+52),y+11];stream=BytesIO();canvas=Canvas(stream,pagesize=(w,h))
    canvas.setFont('Helvetica-Bold',8);canvas.setFillColor(HexColor(reference_color(mark)));canvas.drawString(x-left,y-bottom+2,reference(mark,index));canvas.save();stream.seek(0)
    ap=PdfReader(stream).pages[0];form=DecodedStreamObject();form.set_data(f'q 1 0 0 1 {left} {bottom} cm\n'.encode()+ap.get_contents().get_data()+b'\nQ')
    form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),NameObject('/BBox'):array(rect),NameObject('/Resources'):ap['/Resources'].clone(writer)})
    return DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/FreeText'),NameObject('/Rect'):array(rect),
        NameObject('/NM'):TextStringObject('edesign-reference:'+mark['id']),NameObject('/Contents'):TextStringObject(reference(mark,index)),
        NameObject('/IRT'):root.indirect_reference,NameObject('/RT'):NameObject('/Group'),NameObject('/F'):NumberObject(4),NameObject('/AP'):DictionaryObject({NameObject('/N'):writer._add_object(form)}),NameObject('/DA'):TextStringObject('/Helv 8 Tf 0 0 0 rg')})


def write_review(source,meta,marks,target):
    from python_engine.edesign_style import color,opacity,reference
    from reportlab.lib.colors import HexColor
    writer=PdfWriter();reader=PdfReader(source)
    writer.append(reader,pages=drawing_range(reader))
    for page in writer.pages:
        page.transfer_rotation_to_content()
        # Supported source annotations are represented by the editable mark layer,
        # so do not export duplicate, stale source versions of those annotations.
        page[NameObject('/Annots')]=ArrayObject([a for a in page.get('/Annots',[]) if not managed_annotation(a)])
    portable=[]
    for i,mark in enumerate(marks,1):
        page=writer.pages[mark['page']-1]
        rect,ap=appearance(writer,page,mark,i)
        colour=HexColor(color(mark))
        subtype={'note':'/Text','arrow':'/Line','highlight':'/Highlight','underline':'/Underline','marker':'/Ink'}.get(mark['shape'],'/Square')
        annotation=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject(subtype),
            NameObject('/Rect'):array(rect),NameObject('/NM'):TextStringObject('edesign:'+mark['id']),
            NameObject('/Contents'):TextStringObject(mark['body']),NameObject('/T'):TextStringObject(mark['author']),
            NameObject('/Subj'):TextStringObject(f'{mark["kind"].title()} / {reference(mark,i)} / revision {mark["version"]}'),
            NameObject('/M'):TextStringObject(date(mark['updated'])),NameObject('/CreationDate'):TextStringObject(date(mark['created'])),
            NameObject('/F'):NumberObject(4),NameObject('/C'):array([colour.red,colour.green,colour.blue]),NameObject('/CA'):FloatObject(opacity(mark)),
            NameObject('/BS'):DictionaryObject({NameObject('/W'):NumberObject(2),NameObject('/S'):NameObject('/S')}),
            NameObject('/AP'):DictionaryObject({NameObject('/N'):ap}),NameObject('/Open'):BooleanObject(False),
            NameObject('/StateModel'):TextStringObject('Review'),NameObject('/State'):TextStringObject('Completed' if mark['status']=='resolved' else 'None')})
        if mark['shape'] in {'cloud','cloud-only'}:annotation[NameObject('/BE')]=DictionaryObject({NameObject('/S'):NameObject('/C'),NameObject('/I'):NumberObject(1)})
        if mark['shape'] in {'highlight','underline'}:
            annotation[NameObject('/QuadPoints')]=array([rect[0],rect[3],rect[2],rect[3],rect[0],rect[1],rect[2],rect[1]])
        if mark['shape']=='marker':
            w,h=float(page.cropbox.width),float(page.cropbox.height);l,b=float(page.cropbox.left),float(page.cropbox.bottom)
            points=mark.get('points') or [[mark['box'][0],mark['box'][1]],[mark['box'][2],mark['box'][3]]]
            annotation[NameObject('/InkList')]=ArrayObject([array([v for x,y in points for v in (l+x*w,b+(1-y)*h)])])
        if mark['shape']=='arrow':
            x0,y0,x1,y1=mark['box'];w,h=float(page.cropbox.width),float(page.cropbox.height);l,b=float(page.cropbox.left),float(page.cropbox.bottom)
            annotation[NameObject('/L')]=array([l+(x1 if mark['reverseX'] else x0)*w,b+(1-(y1 if mark['reverseY'] else y0))*h,
                                               l+(x0 if mark['reverseX'] else x1)*w,b+(1-(y0 if mark['reverseY'] else y1))*h])
            annotation[NameObject('/LE')]=ArrayObject([NameObject('/None'),NameObject('/OpenArrow')])
        root=writer.add_annotation(mark['page']-1,annotation)
        writer.add_annotation(mark['page']-1,reference_annotation(writer,page,mark,i,root))
        if mark.get('callout'):
            from .edesign_callout import leader
            for part,prefix in [('leader','edesign-leader:'),('label','edesign-callout:')]:
                bounds,ap=callout_appearance(writer,page,mark,part)
                child=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/FreeText' if part=='label' else '/Line'),
                    NameObject('/Rect'):array(bounds),NameObject('/NM'):TextStringObject(prefix+mark['id']),NameObject('/IRT'):root.indirect_reference,NameObject('/RT'):NameObject('/Group'),
                    NameObject('/Contents'):TextStringObject(mark['body'] if part=='label' else ''),NameObject('/T'):TextStringObject(mark['author']),NameObject('/F'):NumberObject(4),
                    NameObject('/C'):array([colour.red,colour.green,colour.blue]),NameObject('/AP'):DictionaryObject({NameObject('/N'):ap}),
                    NameObject('/BS'):DictionaryObject({NameObject('/W'):NumberObject(1),NameObject('/S'):NameObject('/S')})})
                if part=='label':
                    child[NameObject('/DA')]=TextStringObject(f'/Helv {max(5,min(14,float(page.cropbox.width)*.013))} Tf 0.09 0.125 0.17 rg')
                    child[NameObject('/Q')]=NumberObject(0)
                else:
                    points=leader(mark);a,b=points[0],points[-1];w,h=float(page.cropbox.width),float(page.cropbox.height);l,t=float(page.cropbox.left),float(page.cropbox.bottom)
                    child[NameObject('/L')]=array([l+a[0]*w,t+(1-a[1])*h,l+b[0]*w,t+(1-b[1])*h])
                    child[NameObject('/LE')]=ArrayObject([NameObject('/None'),NameObject('/OpenArrow')])
                writer.add_annotation(mark['page']-1,child)
        popup=writer.add_annotation(mark['page']-1,DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Popup'),
            NameObject('/Parent'):root.indirect_reference,NameObject('/Rect'):array([rect[2]+4,rect[1],rect[2]+224,rect[1]+100]),NameObject('/Open'):BooleanObject(False)}))
        root[NameObject('/Popup')]=popup.indirect_reference
        # Historical versions are ordinary PDF reply comments, as well as being
        # in the portable envelope. Reader-specific timeline UI may vary.
        for entry in reversed(mark.get('history',[])[:100]):
            version=entry['version'];old=entry['snapshot']
            if version==mark['version'] and not entry.get('origin'):continue
            reply=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Text'),
                NameObject('/Rect'):array([rect[0],rect[1],rect[0]+12,rect[1]+12]),NameObject('/IRT'):root.indirect_reference,
                NameObject('/RT'):NameObject('/R'),NameObject('/NM'):TextStringObject(f'edesign-history:{mark["id"]}:{version}:{entry.get("origin","")}'),
                NameObject('/Contents'):TextStringObject(f'Revision {version} / {entry["action"]} / {old.get("status","open")}\n{old.get("body","")}'),
                NameObject('/T'):TextStringObject(entry['actor']),NameObject('/M'):TextStringObject(date(entry['at'])),NameObject('/F'):NumberObject(0)})
            writer.add_annotation(mark['page']-1,reply)
        writer.add_annotation(mark['page']-1,DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Text'),
            NameObject('/Rect'):array([rect[0],rect[1],rect[0]+12,rect[1]+12]),NameObject('/IRT'):root.indirect_reference,NameObject('/RT'):NameObject('/R'),
            NameObject('/NM'):TextStringObject('edesign-status:'+mark['id']),NameObject('/Contents'):TextStringObject('Status: '+mark['status']),
            NameObject('/T'):TextStringObject(mark.get('history',[{}])[0].get('actor',mark['author']) if mark.get('history') else mark['author']),
            NameObject('/M'):TextStringObject(date(mark['updated'])),NameObject('/StateModel'):TextStringObject('Review'),
            NameObject('/State'):TextStringObject('Completed' if mark['status']=='resolved' else 'None'),NameObject('/F'):NumberObject(0)}))
        baseline=mark.get('baseline') or {'version':mark['version'],'snapshot':snapshot(mark)}
        portable.append({'id':mark['id'],'referenceNo':mark.get('referenceNo',i),'author':mark['author'],'created':mark['created'],'updated':mark['updated'],'version':mark['version'],
                         **snapshot(mark),'baseline':baseline,'history':mark.get('history',[])})
    offset=0
    if meta.get('cover'):
        from .edesign_cover import pdf
        covers=PdfReader(pdf(meta['cover']));offset=len(covers.pages)
        for index,page in enumerate(covers.pages):writer.insert_page(page,index)
    envelope={'schema':1,'reviewId':meta.get('lineageId',meta['id']),'drawingPageOffset':offset,'cover':meta.get('cover'),
              'sourceHash':meta.get('originSourceHash',meta['sourceHash']),'pageCount':len(meta['pages']),
              'name':meta['name'],'marks':portable,'exported':datetime.now(timezone.utc).isoformat()}
    encoded=json.dumps(envelope,ensure_ascii=False).encode('utf-8')
    if len(encoded)>8*1024*1024:raise ValueError('The complete portable revision history exceeds 8 MB. No history was truncated; export the correction report or split the review.')
    writer.add_attachment(ATTACHMENT,encoded)
    writer.add_metadata({'/Title':meta['name']+' / e-design review','/Subject':'Editable PDF comments and revision history','/Creator':'uSOPp.ai e-design'})
    with target.open('wb') as stream:writer.write(stream)


def read_review(path):
    reader=PdfReader(path)
    if reader.is_encrypted:raise ValueError('Upload an unlocked PDF.')
    envelope=envelope_data(reader);first,last=drawing_range(reader);page_count=last-first
    originals={v['id']:v for v in envelope.get('marks',[]) if isinstance(v,dict) and re.fullmatch('[a-f0-9]{32}',str(v.get('id','')))}
    marks=[];replies=[];skipped=0;seen=set()
    identity=envelope.get('sourceHash') or hashlib.sha256(path.read_bytes()).hexdigest()
    for number,page in enumerate(reader.pages[first:last],1):
        rotation=page.rotation%360
        left,bottom=float(page.cropbox.left),float(page.cropbox.bottom);w,h=float(page.cropbox.width),float(page.cropbox.height)
        def display(x,y):
            u,v=(float(x)-left)/w,1-(float(y)-bottom)/h
            if rotation==90:u,v=1-v,u
            elif rotation==180:u,v=1-u,1-v
            elif rotation==270:u,v=v,1-u
            return max(0,min(1,u)),max(0,min(1,v))
        labels={}
        for reference in page.get('/Annots',[]):
            a=reference.get_object();match=re.fullmatch('edesign-callout:([a-f0-9]{32})',str(a.get('/NM','')))
            if not match:continue
            if a.get('/Subtype')!='/FreeText':continue
            rect=a.get('/Rect',[0,0,10,10]);points=[display(rect[i],rect[j]) for i,j in [(0,1),(2,1),(2,3),(0,3)]]
            labels[match.group(1)]={'box':[min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)],'body':str(a.get('/Contents','')).strip(),'author':str(a.get('/T','PDF reviewer'))[:150]}
        for reference in page.get('/Annots',[]):
            a=reference.get_object();name=str(a.get('/NM',''));subtype=a.get('/Subtype')
            if name.startswith(('edesign-history:','edesign-callout:','edesign-leader:','edesign-reference:')) or subtype=='/Popup':continue
            content=str(a.get('/Contents','')).strip()
            if len(content)>6000:raise ValueError('A PDF comment exceeds 6,000 characters. Shorten it before importing.')
            if a.get('/IRT'):
                parent=a['/IRT'].get_object();parent_name=str(parent.get('/NM',''))
                replies.append({'parent':parent_name,'name':name,'body':content,
                                'author':str(a.get('/T','PDF reviewer'))[:150],'state':str(a.get('/State','')).lstrip('/')})
                continue
            if subtype not in SUPPORTED:skipped+=1;continue
            if not content and not re.fullmatch('edesign:[a-f0-9]{32}',name):continue
            if len(marks)>=5000:raise ValueError('Use a PDF with up to 5,000 comments.')
            match=re.fullmatch('edesign:([a-f0-9]{32})',name)
            mark_id=match.group(1) if match else uuid.uuid5(uuid.NAMESPACE_URL,f'pdf:{identity}:{number}:{name or content+str(a.get("/Rect"))}').hex
            if mark_id in seen:raise ValueError('The PDF contains duplicate comment identities.')
            seen.add(mark_id);original=originals.get(mark_id,{})
            rect=a.get('/Rect',[0,0,10,10]);points=[display(rect[i],rect[j]) for i,j in [(0,1),(2,1),(2,3),(0,3)]]
            x0,y0=min(p[0] for p in points),min(p[1] for p in points);x1,y1=max(p[0] for p in points),max(p[1] for p in points)
            if x1-x0<.001 or y1-y0<.001:skipped+=1;continue
            effect=a.get('/BE',{});effect=effect.get_object() if hasattr(effect,'get_object') else effect
            shape={'/Line':'arrow','/Text':'note','/FreeText':'note','/Highlight':'highlight','/Underline':'underline','/Ink':'marker'}.get(subtype,'cloud' if effect.get('/S')=='/C' else 'rectangle')
            if shape=='cloud' and original.get('shape')=='cloud-only':shape='cloud-only'
            status='resolved' if str(a.get('/State')).lstrip('/') in ('Completed','Accepted') else 'open'
            kind=str(a.get('/Subj','')).split('/')[0].strip().lower()
            if kind not in ('modify','add','remove','comment'):kind=original.get('kind','comment')
            from .edesign_style import color as mark_color
            rgb=a.get('/C');color='#'+''.join(f'{max(0,min(255,round(float(v)*255))):02x}' for v in rgb) if rgb and len(rgb)==3 else None
            if color==mark_color({'kind':kind,'color':original.get('color')}):color=original.get('color')
            alpha=float(a.get('/CA',1));original_alpha=original.get('opacity')
            if abs(alpha-(original_alpha if original_alpha is not None else .28 if shape=='highlight' else .7 if shape=='marker' else 1))<.00005:alpha=original_alpha
            ink=a.get('/InkList') or [];stroke=list(ink[0]) if ink else []
            ink_points=[list(display(stroke[i],stroke[i+1])) for i in range(0,len(stroke)-1,2)] or original.get('points')
            if original.get('points') and ink_points and len(original['points'])==len(ink_points) and all(abs(a-b)<.00005 for p,q in zip(original['points'],ink_points) for a,b in zip(p,q)):ink_points=original['points']
            if original.get('shape')=='marker' and original.get('points') is None and ink_points and len(ink_points)==2 and all(abs(a-b)<.00005 for p,q in zip(ink_points,[original['box'][:2],original['box'][2:]]) for a,b in zip(p,q)):ink_points=None
            mark={'id':mark_id,'referenceNo':original.get('referenceNo'),'page':number,'kind':kind,'shape':shape,'box':[x0,y0,x1,y1],'color':color,'opacity':alpha,'points':ink_points,
                  'body':content,'status':status,'reverseX':bool(original.get('reverseX',False)),'reverseY':bool(original.get('reverseY',False)),'callout':original.get('callout'),
                  'author':str(a.get('/T',original.get('author','PDF reviewer')))[:150],
                  'baseline':original.get('baseline',{'version':original.get('version',0),'snapshot':{k:original.get(k) for k in FIELDS}}),
                  'history':original.get('history',[]),'pdfName':name,'reportedVersion':original.get('version',0)}
            label=labels.get(mark_id)
            if label:
                mark['callout']=label['box'];old=original.get('callout')
                if isinstance(old,list) and len(old)==4 and all(abs(x-y)<.00005 for x,y in zip(old,mark['callout'])):mark['callout']=old
                if label['body']!=original.get('body',content) and label['body']!=content:
                    if content!=original.get('body',content):raise ValueError('The bubble comment and its text box have conflicting edits.')
                    mark['body']=label['body'];mark['author']=label['author']
                if len(mark['body'])>6000:raise ValueError('A PDF comment exceeds 6,000 characters.')
            if subtype=='/Line' and len(a.get('/L',[]))==4:
                line=a['/L'];start,end=display(line[0],line[1]),display(line[2],line[3]);mark['reverseX']=start[0]>end[0];mark['reverseY']=start[1]>end[1]
            # Quantization by a PDF serializer must not create false revisions.
            for key in ('box','reverseX','reverseY','shape'):
                old=original.get(key)
                if key=='box' and isinstance(old,list) and len(old)==4 and all(abs(x-y)<.00005 for x,y in zip(old,mark[key])):mark[key]=old
                elif key!='box' and old==mark[key]:mark[key]=old
            marks.append(mark)
    by_name={m['pdfName']:m for m in marks}
    for reply in replies:
        parent=by_name.get(reply['parent'])
        if not parent:continue
        if reply['state'] in ('Completed','Accepted'):parent['status']='resolved'
        elif reply['state'] in ('None','Rejected','Cancelled'):parent['status']='open'
        elif reply['body']:
            combined=parent['body']+'\n\n'+reply['author']+': '+reply['body']
            if len(combined)>6000:raise ValueError('The combined PDF comment and replies exceed 6,000 characters.')
            parent['body']=combined
    return {'envelope':envelope,'marks':marks,'pages':page_count,'skipped':skipped}
