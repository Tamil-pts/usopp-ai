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
FIELDS=('page','kind','shape','box','body','status','reverseX','reverseY')


def array(values):return ArrayObject([FloatObject(v) for v in values])
def date(value):return datetime.fromtimestamp(value,timezone.utc).strftime('D:%Y%m%d%H%M%SZ')
def snapshot(mark):return {k:mark[k] for k in FIELDS}


def managed_annotation(annotation):
    a=annotation.get_object()
    return (str(a.get('/NM','')).startswith('edesign-history:') or bool(a.get('/IRT')) or
            (a.get('/Subtype') in SUPPORTED and bool(str(a.get('/Contents','')).strip())) or a.get('/Subtype')=='/Popup')


def review_background(source,target):
    """A display copy retains unmanaged annotations; the uploaded file is intact."""
    writer=PdfWriter();writer.clone_document_from_reader(PdfReader(source))
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
    if mark['shape']=='cloud':
        inset=min(.008,(x1-x0)/5,(y1-y0)/5)
        drawn['box']=[x0+inset,y0+inset,x1-inset,y1-inset]
    draw_mark(c,drawn,width,height,index);c.save();stream.seek(0)
    ap_page=PdfReader(stream).pages[0]
    form=DecodedStreamObject()
    form.set_data(f'q 1 0 0 1 {left} {bottom} cm\n'.encode()+ap_page.get_contents().get_data()+b'\nQ')
    form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
                 NameObject('/BBox'):array(rect),NameObject('/Resources'):ap_page['/Resources'].clone(writer)})
    return rect,writer._add_object(form)


def write_review(source,meta,marks,target):
    from python_engine.edesign_export import COLOURS
    from reportlab.lib.colors import HexColor
    writer=PdfWriter();reader=PdfReader(source)
    writer.append(reader,pages=(0,len(meta['pages'])))
    for page in writer.pages:
        page.transfer_rotation_to_content()
        # Supported source annotations are represented by the editable mark layer,
        # so do not export duplicate, stale source versions of those annotations.
        page[NameObject('/Annots')]=ArrayObject([a for a in page.get('/Annots',[]) if not managed_annotation(a)])
    portable=[]
    for i,mark in enumerate(marks,1):
        page=writer.pages[mark['page']-1]
        rect,ap=appearance(writer,page,mark,i)
        colour=HexColor(COLOURS[mark['kind']])
        annotation=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Text' if mark['shape']=='note' else '/Line' if mark['shape']=='arrow' else '/Square'),
            NameObject('/Rect'):array(rect),NameObject('/NM'):TextStringObject('edesign:'+mark['id']),
            NameObject('/Contents'):TextStringObject(mark['body']),NameObject('/T'):TextStringObject(mark['author']),
            NameObject('/Subj'):TextStringObject(f'{mark["kind"].title()} / R{i:03} / revision {mark["version"]}'),
            NameObject('/M'):TextStringObject(date(mark['updated'])),NameObject('/CreationDate'):TextStringObject(date(mark['created'])),
            NameObject('/F'):NumberObject(4),NameObject('/C'):array([colour.red,colour.green,colour.blue]),
            NameObject('/BS'):DictionaryObject({NameObject('/W'):NumberObject(2),NameObject('/S'):NameObject('/S')}),
            NameObject('/AP'):DictionaryObject({NameObject('/N'):ap}),NameObject('/Open'):BooleanObject(False),
            NameObject('/StateModel'):TextStringObject('Review'),NameObject('/State'):TextStringObject('Completed' if mark['status']=='resolved' else 'None')})
        if mark['shape']=='cloud':annotation[NameObject('/BE')]=DictionaryObject({NameObject('/S'):NameObject('/C'),NameObject('/I'):NumberObject(1)})
        if mark['shape']=='arrow':
            x0,y0,x1,y1=mark['box'];w,h=float(page.cropbox.width),float(page.cropbox.height);l,b=float(page.cropbox.left),float(page.cropbox.bottom)
            annotation[NameObject('/L')]=array([l+(x1 if mark['reverseX'] else x0)*w,b+(1-(y1 if mark['reverseY'] else y0))*h,
                                               l+(x0 if mark['reverseX'] else x1)*w,b+(1-(y0 if mark['reverseY'] else y1))*h])
            annotation[NameObject('/LE')]=ArrayObject([NameObject('/None'),NameObject('/OpenArrow')])
        root=writer.add_annotation(mark['page']-1,annotation)
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
        portable.append({'id':mark['id'],'author':mark['author'],'created':mark['created'],'updated':mark['updated'],'version':mark['version'],
                         **snapshot(mark),'baseline':baseline,'history':mark.get('history',[])})
    envelope={'schema':1,'reviewId':meta.get('lineageId',meta['id']),
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
    if not 1<=len(reader.pages)<=150:raise ValueError('Use a PDF with 1–150 pages.')
    envelope={}
    if ATTACHMENT in reader.attachments:
        raw=reader.attachments[ATTACHMENT][0]
        if len(raw)>8*1024*1024:raise ValueError('The embedded review history is too large.')
        envelope=json.loads(raw)
        if not isinstance(envelope,dict) or envelope.get('schema')!=1 or not isinstance(envelope.get('marks'),list):raise ValueError('Unsupported review metadata.')
    page_count=envelope.get('pageCount',len(reader.pages))
    if not isinstance(page_count,int) or not 1<=page_count<=len(reader.pages):raise ValueError('Invalid drawing page count.')
    originals={v['id']:v for v in envelope.get('marks',[]) if isinstance(v,dict) and re.fullmatch('[a-f0-9]{32}',str(v.get('id','')))}
    marks=[];replies=[];skipped=0;seen=set()
    identity=envelope.get('sourceHash') or hashlib.sha256(path.read_bytes()).hexdigest()
    for number,page in enumerate(reader.pages,1):
        rotation=page.rotation%360
        left,bottom=float(page.cropbox.left),float(page.cropbox.bottom);w,h=float(page.cropbox.width),float(page.cropbox.height)
        def display(x,y):
            u,v=(float(x)-left)/w,1-(float(y)-bottom)/h
            if rotation==90:u,v=1-v,u
            elif rotation==180:u,v=1-u,1-v
            elif rotation==270:u,v=v,1-u
            return max(0,min(1,u)),max(0,min(1,v))
        for reference in page.get('/Annots',[]):
            a=reference.get_object();name=str(a.get('/NM',''));subtype=a.get('/Subtype')
            if name.startswith('edesign-history:') or subtype=='/Popup':continue
            content=str(a.get('/Contents','')).strip()
            if len(content)>6000:raise ValueError('A PDF comment exceeds 6,000 characters. Shorten it before importing.')
            if a.get('/IRT'):
                parent=a['/IRT'].get_object();parent_name=str(parent.get('/NM',''))
                replies.append({'parent':parent_name,'name':name,'body':content,
                                'author':str(a.get('/T','PDF reviewer'))[:150],'state':str(a.get('/State','')).lstrip('/')})
                continue
            if subtype not in SUPPORTED:skipped+=1;continue
            if not content:continue
            if len(marks)>=5000:raise ValueError('Use a PDF with up to 5,000 comments.')
            match=re.fullmatch('edesign:([a-f0-9]{32})',name)
            mark_id=match.group(1) if match else uuid.uuid5(uuid.NAMESPACE_URL,f'pdf:{identity}:{number}:{name or content+str(a.get("/Rect"))}').hex
            if mark_id in seen:raise ValueError('The PDF contains duplicate comment identities.')
            seen.add(mark_id);original=originals.get(mark_id,{})
            rect=a.get('/Rect',[0,0,10,10]);points=[display(rect[i],rect[j]) for i,j in [(0,1),(2,1),(2,3),(0,3)]]
            x0,y0=min(p[0] for p in points),min(p[1] for p in points);x1,y1=max(p[0] for p in points),max(p[1] for p in points)
            if x1-x0<.001 or y1-y0<.001:skipped+=1;continue
            effect=a.get('/BE',{});effect=effect.get_object() if hasattr(effect,'get_object') else effect
            shape='arrow' if subtype=='/Line' else 'note' if subtype in ('/Text','/FreeText') else 'cloud' if effect.get('/S')=='/C' else 'rectangle'
            status='resolved' if str(a.get('/State')).lstrip('/') in ('Completed','Accepted') else 'open'
            kind=str(a.get('/Subj','')).split('/')[0].strip().lower()
            if kind not in ('modify','add','remove','comment'):kind=original.get('kind','comment')
            mark={'id':mark_id,'page':number,'kind':kind,'shape':shape,'box':[x0,y0,x1,y1],
                  'body':content,'status':status,'reverseX':False,'reverseY':False,
                  'author':str(a.get('/T',original.get('author','PDF reviewer')))[:150],
                  'baseline':original.get('baseline',{'version':original.get('version',0),'snapshot':{k:original.get(k) for k in FIELDS}}),
                  'history':original.get('history',[]),'pdfName':name,'reportedVersion':original.get('version',0)}
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
    return {'envelope':envelope,'marks':marks,'pages':len(reader.pages),'skipped':skipped}
