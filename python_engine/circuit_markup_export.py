"""Self-contained circuit review exports; source drawings remain unchanged."""
import base64
import html
import math
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject,DecodedStreamObject,DictionaryObject,FloatObject,NameObject,NumberObject,TextStringObject
from reportlab.pdfgen.canvas import Canvas

COLORS={'blue':'#1479d1','red':'#d53248','amber':'#bc8200','green':'#00966c','purple':'#8954a8'}
def esc(value):return html.escape(str(value or ''),quote=True)
def numbers(values):return ArrayObject([FloatObject(v) for v in values])
def raw_point(page,x,y):
    rot=page.rotation%360
    if rot==90:x,y=y,1-x
    elif rot==180:x,y=1-x,1-y
    elif rot==270:x,y=1-y,x
    return (float(page.cropbox.left)+x*float(page.cropbox.width),float(page.cropbox.bottom)+(1-y)*float(page.cropbox.height))

def editable_pdf(folder,data,marks,target):
    writer=PdfWriter();offsets={}
    for side in ('base','developed'):
        reader=PdfReader(folder/f'{side}.pdf')
        if reader.is_encrypted:raise ValueError('The drawing PDF must be unlocked before export.')
        offsets[side]=len(writer.pages);writer.append(reader)
        if len(reader.pages):writer.add_outline_item(side.title()+' drawing',offsets[side])
    for mark in marks:
        index=offsets[mark['side']]+mark['page']-1;page=writer.pages[index]
        x0,y0,x1,y1=mark['box'];points=[raw_point(page,x,y) for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]
        rect=[min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)]
        width,height=rect[2]-rect[0],rect[3]-rect[1];colour=COLORS[mark['color']];color=[int(colour[i:i+2],16)/255 for i in (1,3,5)]
        start=raw_point(page,x1 if mark.get('reverseX') else x0,y1 if mark.get('reverseY') else y0)
        end=raw_point(page,x0 if mark.get('reverseX') else x1,y0 if mark.get('reverseY') else y1)
        stream=BytesIO();canvas=Canvas(stream,pagesize=(width,height));canvas.setStrokeColorRGB(*color);canvas.setLineWidth(1.5)
        if mark['shape']=='arrow':
            sx,sy=start[0]-rect[0],start[1]-rect[1];ex,ey=end[0]-rect[0],end[1]-rect[1];canvas.line(sx,sy,ex,ey);angle=math.atan2(ey-sy,ex-sx)
            for delta in (-.5,.5):canvas.line(ex,ey,ex-8*math.cos(angle+delta),ey-8*math.sin(angle+delta))
        elif mark['shape']=='cloud':
            from python_engine.edesign_export import cloud_segments
            outline=canvas.beginPath();outline.moveTo(.04*width,.96*height)
            for ax,ay,cx,cy,bx,by in cloud_segments(.04,.04,.96,.96):
                outline.curveTo((ax+2*(cx-ax)/3)*width,(1-ay-2*(cy-ay)/3)*height,(bx+2*(cx-bx)/3)*width,(1-by-2*(cy-by)/3)*height,bx*width,(1-by)*height)
            outline.close();canvas.drawPath(outline)
        else:canvas.rect(1,1,max(0,width-2),max(0,height-2),stroke=1,fill=0)
        canvas.save();stream.seek(0);ap_page=PdfReader(stream).pages[0];form=DecodedStreamObject();form.set_data(ap_page.get_contents().get_data())
        form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),NameObject('/BBox'):numbers([0,0,width,height]),NameObject('/Resources'):ap_page['/Resources'].clone(writer)})
        ann=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Line' if mark['shape']=='arrow' else '/Square'),NameObject('/Rect'):numbers(rect),NameObject('/NM'):TextStringObject('circuit:'+mark['id']),NameObject('/Contents'):TextStringObject(mark['text']),NameObject('/T'):TextStringObject(mark.get('author','')),NameObject('/Subj'):TextStringObject(f"Circuit markup / {mark['shape']} / {mark['status']}"),NameObject('/F'):NumberObject(4),NameObject('/C'):numbers(color),NameObject('/BS'):DictionaryObject({NameObject('/W'):FloatObject(1.5),NameObject('/S'):NameObject('/S')}),NameObject('/AP'):DictionaryObject({NameObject('/N'):writer._add_object(form)}),NameObject('/StateModel'):TextStringObject('Review'),NameObject('/State'):TextStringObject('Completed' if mark['status']=='resolved' else 'None')})
        if mark['shape']=='cloud':ann[NameObject('/BE')]=DictionaryObject({NameObject('/S'):NameObject('/C'),NameObject('/I'):NumberObject(1)})
        if mark['shape']=='arrow':ann[NameObject('/L')]=numbers([*start,*end]);ann[NameObject('/LE')]=ArrayObject([NameObject('/None'),NameObject('/OpenArrow')])
        root=writer.add_annotation(index,ann)
        popup=writer.add_annotation(index,DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Popup'),NameObject('/Parent'):root.indirect_reference,NameObject('/Rect'):numbers([rect[2],rect[1],rect[2]+160,rect[1]+100])}))
        root[NameObject('/Popup')]=popup.indirect_reference
    writer.add_metadata({'/Title':'Circuit comparison: '+str(data.get('developedName','')),'/Creator':'uSOPp.ai','/Subject':'Editable drawing review comments'})
    with open(target,'wb') as out:writer.write(out)

def markup_svg(mark):
    x0,y0,x1,y1=(n*1000 for n in mark['box']);color=COLORS[mark['color']];label=esc(mark['text'])
    if mark['shape']=='arrow':
        sx,ex=(x1,x0) if mark.get('reverseX') else (x0,x1);sy,ey=(y1,y0) if mark.get('reverseY') else (y0,y1)
        length=math.hypot(ex-sx,ey-sy) or 1;ux,uy=(ex-sx)/length,(ey-sy)/length
        body=f'<path d="M {sx} {sy} L {ex} {ey} M {ex-ux*18-uy*8} {ey-uy*18+ux*8} L {ex} {ey} L {ex-ux*18+uy*8} {ey-uy*18-ux*8}" fill="none" stroke="{color}" stroke-width="3"/>'
    elif mark['shape']=='cloud':
        from python_engine.edesign_export import cloud_segments
        path=f'M {x0} {y0} '+''.join(f'Q {cx*1000} {cy*1000} {bx*1000} {by*1000} ' for ax,ay,cx,cy,bx,by in cloud_segments(*mark['box']))+'Z'
        body=f'<path d="{path}" fill="{color}" fill-opacity=".16" stroke="{color}" stroke-width="3"/>'
    else:body=f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="{color}" fill-opacity=".16" stroke="{color}" stroke-width="3"/>'
    return f'<g><title>{label}</title>{body}</g>'

def circuit_html(folder,data,marks,target):
    folder=Path(folder);limit=160*1024*1024;size=0
    with open(target,'w',encoding='utf-8') as out:
        out.write('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Circuit comparison review</title><style>body{font:14px system-ui;margin:24px;color:#183040}h2{margin-top:35px}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.drawing{position:relative}.drawing img{display:block;width:100%}.drawing svg{position:absolute;inset:0;width:100%;height:100%}li{margin:.5em 0}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #ccd8df;text-align:left;overflow-wrap:anywhere}@media(max-width:700px){.pair{grid-template-columns:1fr}}</style><h1>Circuit comparison review</h1>')
        out.write(f'<p>Base: {esc(data.get("baseName"))} &rarr; Developed: {esc(data.get("developedName"))}</p><p>Engineer markups and automatic differences require review.</p>')
        for pair in data['pairs']:
            pairmarks=[m for m in marks if m['pairId']==pair['id']];out.write(f'<h2>{esc(pair["id"])}: {esc(pair.get("title"))}</h2><div class="pair">')
            for side in ('base','developed'):
                number=pair.get(side);out.write('<section><h3>'+esc(side.title())+' page '+esc(number or 'absent')+'</h3>')
                if number:
                    page=data['basePages' if side=='base' else 'developedPages'][number-1];name=page['image'];path=(folder/name).resolve()
                    if path.parent!=folder.resolve() or not path.is_file():raise ValueError('A drawing preview is unavailable for HTML export.')
                    size+=path.stat().st_size
                    if size>limit:raise ValueError('The drawing images exceed the 160 MB HTML export limit. Use the PDF summary instead.')
                    image=base64.b64encode(path.read_bytes()).decode('ascii');out.write(f'<div class="drawing"><img alt="{esc(side)} page {number}" src="data:image/png;base64,{image}"><svg viewBox="0 0 1000 1000" preserveAspectRatio="none">')
                    out.write(''.join(markup_svg(m) for m in pairmarks if m['side']==side));out.write('</svg></div>')
                out.write('</section>')
            out.write('</div><ul>')
            for m in pairmarks:out.write(f'<li><b>{esc(m["side"])} page {m["page"]} / {esc(m["status"])} / {esc(m["author"])}:</b> {esc(m["text"])}</li>')
            out.write('</ul><table><tr><th>Change</th><th>Base</th><th>Developed</th><th>Review</th></tr>')
            for c in data['changes']:
                if c['pairId']==pair['id']:out.write(f'<tr><td>{esc(c.get("id"))} / {esc(c.get("label"))}</td><td>{esc((c.get("before") or {}).get("text"))}</td><td>{esc((c.get("after") or {}).get("text"))}</td><td>{esc(c.get("review"))} {esc(c.get("note"))}</td></tr>')
            out.write('</table>')
        out.write('</html>')
