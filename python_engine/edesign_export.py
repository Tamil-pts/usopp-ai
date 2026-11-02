"""Export drawing markups without changing the uploaded PDF."""
from datetime import datetime, timezone
from io import BytesIO
import csv
import math
from xml.sax.saxutils import escape

from .edesign_style import COLOURS,color,opacity,reference,reference_color


def cloud_segments(x0, y0, x1, y1):
    """Clockwise scallops in top-left drawing coordinates."""
    segments = []
    for ax, ay, bx, by, nx, ny in [(x0,y0,x1,y0,0,-1),(x1,y0,x1,y1,1,0),(x1,y1,x0,y1,0,1),(x0,y1,x0,y0,-1,0)]:
        n = max(2, min(18, math.ceil(math.hypot(bx-ax,by-ay)/.025)))
        for i in range(n):
            sx,sy=ax+(bx-ax)*i/n,ay+(by-ay)*i/n
            ex,ey=ax+(bx-ax)*(i+1)/n,ay+(by-ay)*(i+1)/n
            depth=min(.009,math.hypot(ex-sx,ey-sy)*.5)
            segments.append((sx,sy,(sx+ex)/2+nx*depth,(sy+ey)/2+ny*depth,ex,ey))
    return segments


def draw_mark(canvas, mark, width, height, index):
    from reportlab.lib.colors import HexColor
    x0,y0,x1,y1=mark['box']
    canvas.saveState()
    canvas.setStrokeColor(HexColor(color(mark)))
    canvas.setFillColor(HexColor(color(mark)))
    canvas.setLineWidth(1.8)
    if mark['status']=='resolved': canvas.setDash(4,3)
    if mark['shape'] in {'cloud','cloud-only'}:
        p=canvas.beginPath();p.moveTo(x0*width,(1-y0)*height)
        for ax,ay,cx,cy,bx,by in cloud_segments(x0,y0,x1,y1):
            # Quadratic converted to a cubic Bezier.
            p.curveTo((ax+2/3*(cx-ax))*width,(1-ay-2/3*(cy-ay))*height,
                      (bx+2/3*(cx-bx))*width,(1-by-2/3*(cy-by))*height,bx*width,(1-by)*height)
        p.close();canvas.drawPath(p)
    elif mark['shape']=='highlight':
        canvas.setFillAlpha(opacity(mark));canvas.rect(x0*width,(1-y1)*height,(x1-x0)*width,(y1-y0)*height,stroke=0,fill=1);canvas.setFillAlpha(1)
    elif mark['shape']=='underline':
        canvas.line(x0*width,(1-y1)*height,x1*width,(1-y1)*height)
    elif mark['shape']=='marker':
        canvas.setStrokeAlpha(opacity(mark));canvas.setLineWidth(max(3,width*.005));canvas.setLineCap(1);canvas.setLineJoin(1)
        points=mark.get('points') or [[x0,y0],[x1,y1]];p=canvas.beginPath();p.moveTo(points[0][0]*width,(1-points[0][1])*height)
        for x,y in points[1:]:p.lineTo(x*width,(1-y)*height)
        canvas.drawPath(p);canvas.setStrokeAlpha(1)
    elif mark['shape']=='arrow':
        ax,bx=(x1,x0) if mark['reverseX'] else (x0,x1)
        ay,by=(y1,y0) if mark['reverseY'] else (y0,y1)
        ax,bx,ay,by=ax*width,bx*width,(1-ay)*height,(1-by)*height
        canvas.line(ax,ay,bx,by)
        angle=math.atan2(by-ay,bx-ax)
        for delta in (-.5,.5):canvas.line(bx,by,bx-5*math.cos(angle+delta),by-5*math.sin(angle+delta))
    elif mark['shape']=='note':
        canvas.circle(x0*width,(1-y0)*height,7,stroke=1,fill=0)
    else: canvas.rect(x0*width,(1-y1)*height,(x1-x0)*width,(y1-y0)*height,stroke=1,fill=0)
    canvas.setFont('Helvetica-Bold',9)
    canvas.setFillColor(HexColor(reference_color(mark)))
    canvas.drawString(max(0,x0*width),min(height-10,(1-y0)*height+5),reference(mark,index))
    canvas.restoreState()
    if mark.get('callout'):
        from .edesign_callout import draw_callout
        draw_callout(canvas,mark,width,height)


def comment_pdf(meta, marks):
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    stream=BytesIO();styles=getSampleStyleSheet()
    story=[Paragraph('e-design / Drawing review comments',styles['Title']),Paragraph(escape(meta['name']),styles['Normal']),Spacer(1,16)]
    if not marks:story.append(Paragraph('No correction comments recorded.',styles['Normal']))
    for i,mark in enumerate(marks,1):
        story.extend([Paragraph(f'{reference(mark,i)} / Page {mark["page"]} / {mark["kind"].title()} / {mark["status"]}',styles['Heading2']),
                      Paragraph(escape(mark['body']).replace('\n','<br/>'),styles['Normal']),
                      Paragraph(escape(mark['author'])+' / '+datetime.fromtimestamp(mark['updated'],timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),styles['Normal']),Spacer(1,12)])
    SimpleDocTemplate(stream,title='e-design correction list').build(story)
    stream.seek(0);return stream


def export_review(source, meta, marks, target, format):
    if format=='pdf':
        from python_engine.edesign_pdf import write_review
        write_review(source,meta,marks,target)
    elif format=='report':
        from pypdf import PdfReader, PdfWriter, Transformation
        from pypdf.generic import NameObject,ArrayObject
        from python_engine.edesign_pdf import managed_annotation
        from reportlab.pdfgen.canvas import Canvas
        from python_engine.edesign_pdf import drawing_range
        reader=PdfReader(source);writer=PdfWriter();writer.append(reader,pages=drawing_range(reader))
        for page in writer.pages:
            page[NameObject('/Annots')]=ArrayObject([a for a in page.get('/Annots',[]) if not managed_annotation(a)])
        for number,page in enumerate(writer.pages,1):
            entries=[(i,m) for i,m in enumerate(marks,1) if m['page']==number]
            if not entries:continue
            page.transfer_rotation_to_content()
            width,height=float(page.cropbox.width),float(page.cropbox.height)
            stream=BytesIO();canvas=Canvas(stream,pagesize=(width,height))
            for index,mark in entries:draw_mark(canvas,mark,width,height,index)
            canvas.save();stream.seek(0)
            page.merge_transformed_page(PdfReader(stream).pages[0],Transformation().translate(float(page.cropbox.left),float(page.cropbox.bottom)))
        writer.append(PdfReader(comment_pdf(meta,marks)))
        if meta.get('cover'):
            from .edesign_cover import pdf
            for index,page in enumerate(PdfReader(pdf(meta['cover'])).pages):writer.insert_page(page,index)
        with target.open('wb') as stream:writer.write(stream)
    elif format=='html':
        import base64
        from html import escape as html_escape
        import pypdfium2 as pdfium
        from pathlib import Path
        background=Path(source).with_name('background.pdf')
        source=background if background.exists() else source
        size=0
        with pdfium.PdfDocument(str(source)) as doc,open(target,'w',encoding='utf-8') as output:
            output.write('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Drawing review</title><style>body{font:14px system-ui;margin:24px;color:#193444}.page{position:relative;max-width:1400px}.page img{display:block;width:100%}.page svg{position:absolute;inset:0;width:100%;height:100%}li{margin:.5em 0;white-space:pre-wrap}</style><h1>e-design / Drawing review</h1><p>'+html_escape(meta['name'])+'</p>')
            if meta.get('cover'):
                from .edesign_cover import html
                output.write(html(meta['cover']))
            for number in range(1,len(meta['pages'])+1):
                page=doc[number-1]
                try:
                    bitmap=page.render(scale=min(1400/page.get_width(),1800/page.get_height()),draw_annots=True)
                    try:
                        image=BytesIO();bitmap.to_pil().convert('RGB').save(image,format='PNG');raw=image.getvalue()
                    finally:bitmap.close()
                finally:page.close()
                size+=len(raw)
                if size>160*1024*1024:raise ValueError('Drawing images exceed the 160 MB HTML limit. Use the PDF report instead.')
                output.write(f'<h2>Page {number}</h2><div class="page"><img alt="Page {number}" src="data:image/png;base64,{base64.b64encode(raw).decode()}"><svg viewBox="0 0 1000 1000" preserveAspectRatio="none">')
                entries=[m for m in marks if m['page']==number]
                for mark in entries:
                    x0,y0,x1,y1=(v*1000 for v in mark['box']);colour=color(mark)
                    title=html_escape(mark['body'])
                    if mark['shape']=='arrow':
                        sx,ex=(x1,x0) if mark.get('reverseX') else (x0,x1);sy,ey=(y1,y0) if mark.get('reverseY') else (y0,y1)
                        length=math.hypot(ex-sx,ey-sy) or 1;ux,uy=(ex-sx)/length,(ey-sy)/length
                        output.write(f'<path d="M {sx} {sy} L {ex} {ey} M {ex-ux*18-uy*8} {ey-uy*18+ux*8} L {ex} {ey} L {ex-ux*18+uy*8} {ey-uy*18-ux*8}" fill="none" stroke="{colour}" stroke-width="3"><title>{title}</title></path>')
                    elif mark['shape']=='underline':output.write(f'<path d="M{x0} {y1} L{x1} {y1}" stroke="{colour}" stroke-width="2"/>')
                    elif mark['shape']=='marker':output.write(f'<polyline points="'+ ' '.join(f'{x*1000},{y*1000}' for x,y in (mark.get('points') or [[x0/1000,y0/1000],[x1/1000,y1/1000]]))+f'" fill="none" stroke="{colour}" stroke-width="5" stroke-opacity="{opacity(mark)}" stroke-linecap="round"/>')
                    elif mark['shape'] in {'cloud','cloud-only'}:
                        segments=cloud_segments(*mark['box']);path=f'M {x0} {y0} '+''.join(f'Q {cx*1000} {cy*1000} {bx*1000} {by*1000} ' for ax,ay,cx,cy,bx,by in segments)+'Z'
                        output.write(f'<path d="{path}" fill="{colour}" fill-opacity=".12" stroke="{colour}" stroke-width="3"><title>{title}</title></path>')
                    else:output.write(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="{colour}" fill-opacity="{opacity(mark) if mark["shape"]=="highlight" else .12}" stroke="{colour}" stroke-width="{0 if mark["shape"]=="highlight" else 2}"><title>{title}</title></rect>')
                    output.write(f'<text x="{x0}" y="{max(14,y0-5)}" font-size="12" fill="{reference_color(mark)}">{reference(mark)}</text>')
                    if mark.get('callout'):
                        from .edesign_callout import leader
                        points=[(x*1000,y*1000) for x,y in leader(mark)];a,b=points[-2:];angle=math.atan2(b[1]-a[1],b[0]-a[0])
                        arrow=' '.join(f'{x},{y}' for x,y in points)
                        output.write(f'<polyline points="{arrow}" fill="none" stroke="{colour}" stroke-width="2"/>')
                        for delta in (-.5,.5):output.write(f'<path d="M{b[0]} {b[1]} L{b[0]-6*math.cos(angle+delta)} {b[1]-6*math.sin(angle+delta)}" stroke="{colour}" fill="none" stroke-width="2"/>')
                output.write('</svg>')
                for mark in entries:
                    if not mark.get('callout'):continue
                    x0,y0,x1,y1=mark['callout'];colour=color(mark)
                    output.write(f'<div class="callout" style="position:absolute;box-sizing:border-box;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;left:{x0*100}%;top:{y0*100}%;width:{(x1-x0)*100}%;height:{(y1-y0)*100}%;border:1px solid {colour};color:{colour};background:#fffde8;padding:4px;font:12px/1.4 Arial">{html_escape(mark["body"])}</div>')
                output.write('</div><ul>')
                for mark in entries:output.write(f'<li><b>{reference(mark)} / {html_escape(mark["kind"])} / {html_escape(mark["status"])} / {html_escape(mark["author"])}:</b> {html_escape(mark["body"])}</li>')
                output.write('</ul>')
            output.write('</html>')
    elif format=='docx':
        from docx import Document
        document=Document()
        if meta.get('cover'):
            from .edesign_cover import docx
            docx(document,meta['cover'])
        document.add_heading('e-design / Drawing review',0)
        document.add_paragraph(meta['name']);document.add_paragraph(f'{len(meta["pages"])} drawing pages / {len(marks)} corrections')
        for number in sorted(set(m['page'] for m in marks)):
            document.add_heading(f'Page {number}',1)
            for i,mark in enumerate(marks,1):
                if mark['page']!=number:continue
                document.add_heading(f'{reference(mark,i)} / {mark["kind"].title()} / {mark["status"].title()}',2)
                document.add_paragraph(mark['body'])
                document.add_paragraph(f'By {mark["author"]} | Area: '+', '.join(f'{v:.3f}' for v in mark['box']))
        if not marks:document.add_paragraph('No correction comments recorded.')
        document.save(target)
    else:
        def cell(value):
            value=str(value)
            return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
        with target.open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.writer(stream);writer.writerow(['ID','Page','Correction','Shape','Comment','Status','Author','Last updated (UTC)','Area'])
            for i,m in enumerate(marks,1):writer.writerow([reference(m,i),m['page'],m['kind'],m['shape'],cell(m['body']),m['status'],cell(m['author']),datetime.fromtimestamp(m['updated'],timezone.utc).isoformat(),json_box(m['box'])])


def json_box(box):
    return ', '.join(f'{v:.4f}' for v in box)
