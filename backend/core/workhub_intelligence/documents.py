"""Local document extraction, transformations and generated WorkHub files."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
from fastapi import HTTPException
from backend.core.workhub import store as hub,identity,timestamp
from backend.core import workhub_files as files
from .local_ai import ServiceUnavailable
from .resources import setting

MAX_DOCUMENT=setting('MAX_DOCUMENT_MB',100,1,100)*1024*1024
MAX_PAGES=500
MAX_TEXT=1500000


def generated_file(user,project_id,name,data,read_access=False):
    from .resources import setting
    limit=min(files.MAX_FILE,setting('MAX_OUTPUT_MB',256)*1024*1024)
    if not isinstance(data,bytes) or not data or len(data)>limit:raise ValueError('Generated file exceeds the configured processing output limit or is empty.')
    digest=hashlib.sha256(data).hexdigest();path=files.blob_path(digest)
    # BEGIN IMMEDIATE serializes quota accounting across all worker processes.
    with files.BLOB_LOCK,hub.db(True) as db:
        from .resources import CURRENT_JOB
        job=CURRENT_JOB.get();slot=files.relative_name(name)
        if read_access:
            if not job or job.row['kind'] not in {'export','q_export'}:raise PermissionError('Read access exports require a worker lease.')
            hub.actor(user);hub.item(db,project_id)
        else:hub.contribute(db,project_id,user)
        if job:
            job.check()
            if job.row['project_id']!=project_id:raise PermissionError('Generated output must remain in its job project.')
            previous=db.execute('SELECT f.* FROM pi_job_outputs o JOIN files f ON f.id=o.file_id WHERE o.job_id=? AND o.slot=? AND f.project_id=?',(job.row['id'],slot,project_id)).fetchone()
            if previous:
                old=files.blob_path(previous['sha256'])
                from .cache import _file_hash
                if not old.exists() or old.stat().st_size!=previous['size'] or _file_hash(old)!=previous['sha256']:raise ValueError('The durable generated output failed integrity verification.')
                return dict(previous)
        registered=db.execute('SELECT 1 FROM files WHERE sha256=? LIMIT 1',(digest,)).fetchone()
        if not registered:
            physical=db.execute('SELECT COALESCE(SUM(size),0) FROM (SELECT MAX(size) AS size FROM files GROUP BY sha256)').fetchone()[0]
            reserved=db.execute("SELECT COALESCE(SUM(size),0) FROM uploads WHERE status='uploading'").fetchone()[0]
            if physical+reserved+len(data)>files.MAX_STORAGE:raise HTTPException(413,'WorkHub storage quota reached.')
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            if shutil.disk_usage(hub.root).free<len(data)+setting('DISK_RESERVE_MB',512,0)*1024*1024:raise HTTPException(507,'Insufficient disk capacity for a durable output. Originals were retained.')
            temporary=path.with_suffix('.'+identity()+'.tmp')
            if job:
                from .cache import workspace
                with workspace(job) as folder:temporary=folder/(identity()+'.tmp')
            try:
                with temporary.open('wb') as output:output.write(data);output.flush();os.fsync(output.fileno())
                from .cache import _file_hash
                if _file_hash(temporary)!=digest:raise ValueError('Generated file integrity verification failed.')
                os.replace(temporary,path)
                if os.name!='nt':
                    descriptor=os.open(path.parent,os.O_RDONLY)
                    try:os.fsync(descriptor)
                    finally:os.close(descriptor)
            finally:temporary.unlink(missing_ok=True)
        else:
            from .cache import _file_hash
            if path.stat().st_size!=len(data) or _file_hash(path)!=digest:raise ValueError('Existing blob integrity verification failed; the original was retained.')
        key=identity()
        db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?)',(key,project_id,user['id'],files.relative_name(name),digest,len(data),timestamp()))
        if job:db.execute('INSERT INTO pi_job_outputs(job_id,slot,file_id) VALUES(?,?,?)',(job.row['id'],slot,key))
        if job and job.row['kind'] in {'q_package','q_iso','export','q_export'} and db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_generated_files'").fetchone():
            purpose={'q_package':'closure_package','q_iso':'iso_pack'}.get(job.row['kind'],'document_export')
            db.execute('INSERT OR IGNORE INTO qc_generated_files VALUES(?,?,?,?)',(key,purpose,job.row['id'],timestamp()))
    return {'id':key,'name':name,'size':len(data),'sha256':digest}


def _zip_bound(path):
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist())>10000 or sum(i.file_size for i in archive.infolist())>250*1024*1024:
            raise ValueError('Expanded Office document exceeds the bounded processing limit.')


def extract(file_id,project_id,check=lambda:None):
    from .cache import extraction
    return extraction(file_id,project_id,_extract,check)


def _extract(file_id,project_id,check=lambda:None):
    row,path=files.file_record(file_id,project_id)
    if row['size']>MAX_DOCUMENT:raise ValueError('The original is retained. Split documents larger than 100 MiB before automatic extraction.')
    extension=Path(row['name']).suffix.lower();sources=[];notices=[];used=0
    def add(value,**where):
        nonlocal used
        if used>=MAX_TEXT:return
        value=str(value)[:min(40000,MAX_TEXT-used)]
        if value.strip():sources.append({'id':file_id+':'+str(len(sources)+1),'file_id':file_id,'filename':row['name'],'text':value,**where});used+=len(value)
    if extension=='.pdf':
        from pypdf import PdfReader,PdfWriter
        pdf=PdfReader(path)
        if pdf.is_encrypted and not pdf.decrypt(''):raise ValueError('Provide an unprotected PDF copy for local processing.')
        for index,page in enumerate(pdf.pages[:MAX_PAGES]):
            check()
            # A standalone page includes its resources/fonts, so changing a font
            # mapping cannot accidentally reuse text from an older page stream.
            writer=PdfWriter();writer.add_page(page);buffer=io.BytesIO();writer.write(buffer)
            page_hash=hashlib.sha256(buffer.getvalue()).hexdigest()
            from .cache import compute,library_version
            cached,_=compute(project_id,'pdf-page-v1:'+library_version('.pdf')+':'+page_hash,'pdf-page-v1',lambda:{'text':page.extract_text(extraction_mode='layout') or ''},check)
            add(cached['text'],page=index+1)
            if used>=MAX_TEXT:break
        if len(pdf.pages)>MAX_PAGES:notices.append(f'Only the first {MAX_PAGES} pages were extracted; the original retains every page.')
        if not sources:notices.append('No searchable text found. Run local OCR for this scanned PDF.')
    elif extension=='.docx':
        _zip_bound(path)
        from docx import Document
        doc=Document(path)
        for index,paragraph in enumerate(doc.paragraphs):
            check();add(paragraph.text,paragraph=index+1)
            if used>=MAX_TEXT:break
        for index,table in enumerate(doc.tables):
            for n,line in enumerate(table.rows[:5000]):add('\t'.join(c.text for c in line.cells),table=index+1,row=n+1)
        notices.append('DOCX references use paragraph/table locations; page numbers depend on the office layout engine.')
    elif extension=='.xlsx':
        _zip_bound(path)
        from openpyxl import load_workbook
        workbook=load_workbook(path,read_only=True,data_only=True)
        try:
            for sheet in workbook.worksheets[:50]:
                for number,values in enumerate(sheet.iter_rows(max_row=10000,max_col=100,values_only=True),1):
                    check();add('\t'.join('' if v is None else str(v) for v in values),sheet=sheet.title,row=number)
                    if used>=MAX_TEXT:break
        finally:workbook.close()
        notices.append('Spreadsheet extraction reads cached cell values; the original workbook retains formulas and layout.')
    elif extension in {'.txt','.csv','.vtt'}:
        raw=path.read_bytes()
        if raw.startswith((b'\xff\xfe',b'\xfe\xff')):value=raw.decode('utf-16')
        else:
            try:value=raw.decode('utf-8-sig')
            except UnicodeDecodeError:value=raw.decode('cp1252')
        for number,line in enumerate(value.splitlines(),1):
            add(line,line=number)
            if used>=MAX_TEXT:break
    elif extension in {'.png','.jpg','.jpeg','.tif','.tiff','.webp','.bmp'}:
        from PIL import Image,ImageSequence
        command=shutil.which('tesseract')
        if not command:raise ServiceUnavailable('Start the local document worker with Tesseract English and Tamil language packs to read this image.')
        with Image.open(path) as image,tempfile.TemporaryDirectory(prefix='usopp-ocr-') as folder:
            for index,frame in enumerate(ImageSequence.Iterator(image)):
                check()
                if index>=100:notices.append('Only the first 100 image frames were read.');break
                if frame.width*frame.height>50000000:raise ValueError('Image exceeds 50 million pixels. Provide a smaller scan.')
                png=Path(folder)/'page.png';frame.convert('RGB').save(png)
                result=subprocess.run([command,str(png),'stdout','-l',os.getenv('USOPP_PI_OCR_LANGUAGES','eng+tam')],capture_output=True,timeout=180)
                if result.returncode:raise ServiceUnavailable('Local OCR could not read this image. Verify installed Tesseract language packs.')
                add(result.stdout.decode('utf-8',errors='replace'),page=index+1)
    else:raise ValueError('This file is preserved for download. Automatic reading supports PDF, DOCX, XLSX, TXT, CSV, VTT and images.')
    if used>=MAX_TEXT:notices.append('The extracted-text limit was reached. Review the original for remaining content.')
    return {'sources':sources,'notices':notices,'original_file_id':file_id,'text':'\n'.join(s['text'] for s in sources),'coverage_limited':any('Only' in n or 'limit' in n for n in notices)}


def pdf_operation(project_id,payload,job):
    action=payload.get('action');ids=payload.get('file_ids',[])
    if not ids:raise ValueError('Choose project files for this PDF operation.')
    paths=[]
    for key in ids:
        row,path=files.file_record(key,project_id)
        if row['size']>MAX_DOCUMENT:raise ValueError('PDF utilities process files up to 100 MiB. The original remains available.')
        paths.append(path)
    if action=='ocr':
        command=shutil.which('ocrmypdf')
        if not command:raise ServiceUnavailable('Start the local document worker with OCRmyPDF and Tesseract to create a searchable PDF.')
        with tempfile.TemporaryDirectory(prefix='usopp-pdf-') as folder:
            output=Path(folder)/'searchable.pdf'
            job.progress(20,'Running local searchable-PDF OCR')
            result=subprocess.run([command,'--skip-text','--jobs','2','--language',os.getenv('USOPP_PI_OCR_LANGUAGES','eng+tam'),
                                   '--output-type','pdf',str(paths[0]),str(output)],capture_output=True,timeout=3600)
            if result.returncode not in (0,6) or not output.is_file():raise ServiceUnavailable('OCRmyPDF could not finish. Check the document worker language packs and PDF input.')
            job.check();return output.read_bytes(),'searchable.pdf'
    from pypdf import PdfReader,PdfWriter
    writer=PdfWriter();readers=[PdfReader(p) for p in paths]
    if any(r.is_encrypted and not r.decrypt('') for r in readers):raise ValueError('Provide an unprotected PDF copy.')
    if sum(len(r.pages) for r in readers)>2000:raise ValueError('Process up to 2,000 PDF pages at a time.')
    if action=='merge':
        for reader in readers:
            job.check();writer.append(reader)
    elif action=='split':
        indices=set()
        for chunk in str(payload.get('pages','')).split(','):
            match=re.fullmatch(r'\s*(\d+)(?:\s*-\s*(\d+))?\s*',chunk)
            if not match:raise ValueError('Enter page numbers such as 1,3-6.')
            first=int(match[1]);last=int(match[2] or first)
            if not 1<=first<=last<=len(readers[0].pages):raise ValueError('Selected pages are outside the PDF.')
            indices.update(range(first-1,last))
        for index in sorted(indices):writer.add_page(readers[0].pages[index])
    elif action=='rotate':
        angle=payload.get('angle',90)
        if type(angle) is not int or angle not in (90,180,270):raise ValueError('Choose 90, 180 or 270 degrees.')
        selected=payload.get('page')
        if selected is not None and (type(selected) is not int or not 1<=selected<=len(readers[0].pages)):raise ValueError('Choose an existing page.')
        for index,page in enumerate(readers[0].pages,1):
            job.check();writer.add_page(page.rotate(angle) if selected is None or selected==index else page)
    elif action=='annotate':
        from pypdf.annotations import Text
        annotations=payload.get('annotations',[])
        if not isinstance(annotations,list) or len(annotations)>1000:raise ValueError('Use up to 1,000 annotations.')
        for index,page in enumerate(readers[0].pages,1):
            job.check();writer.add_page(page);width=float(page.mediabox.width);height=float(page.mediabox.height)
            for annotation in (a for a in annotations if a.get('page')==index):
                x=max(0,min(.95,float(annotation.get('x') or .05)))*width
                y=(1-max(.05,min(1,float(annotation.get('y') or .1))))*height
                body=str(annotation.get('body',''))
                if not body or len(body)>4000:raise ValueError('Use annotations with up to 4,000 characters.')
                writer.add_annotation(index-1,Text(rect=(x,y-20,min(width,x+20),y),text=body,open=False))
    else:raise ValueError('Choose OCR, merge, split, rotate or annotate.')
    output=io.BytesIO();writer.write(output);return output.getvalue(),('merged' if action=='merge' else 'selected-pages' if action=='split' else 'annotated' if action=='annotate' else 'rotated')+'.pdf'


def office_convert(path,extension,source_suffix=None):
    command=shutil.which('libreoffice') or shutil.which('soffice')
    if not command:raise ServiceUnavailable('Start the local document worker with LibreOffice for document conversion.')
    if extension not in {'pdf','docx','xlsx','txt','csv'}:raise ValueError('Choose PDF, DOCX, XLSX, TXT or CSV.')
    with tempfile.TemporaryDirectory(prefix='usopp-office-') as folder:
        folder=Path(folder);input_path=folder/('input'+(source_suffix or path.suffix));shutil.copyfile(path,input_path)
        result=subprocess.run([command,'-env:UserInstallation='+str((folder/'profile').as_uri()),'--headless','--convert-to',extension,'--outdir',str(folder/'out'),str(input_path)],capture_output=True,timeout=180)
        outputs=list((folder/'out').glob('*'))
        if result.returncode or len(outputs)!=1:raise ValueError('The local office engine could not convert this format.')
        return outputs[0].read_bytes()


def readable_lines(value,depth=0):
    if depth>12:return
    if isinstance(value,dict):
        for key,item in value.items():
            if key in {'sources','nodes','edges','words','original_text','file_id','revision_id','base_approved','_base_approved_revision'}:continue
            if item is None or item=='' or item==[]:continue
            label=key.replace('_',' ').capitalize()
            if isinstance(item,(dict,list)):
                yield label
                yield from readable_lines(item,depth+1)
            else:yield label+': '+str(item)
    elif isinstance(value,list):
        for item in value:yield from readable_lines(item,depth+1)
    else:yield str(value)


def export_document(doc,revision,format,user=None):
    content=revision['content']
    if format=='pdf':
        from backend.core.workhub_quality.pdf_templates import export
        if user is None:
            from backend.core.run_history import current_user
            user=current_user.get()
        if not user:raise HTTPException(403,'A signed-in project account is required to export documents.')
        return export(user,doc['project_id'],doc,revision,controlled=False),'application/pdf'
    if format=='json':return json.dumps({'document':doc,'revision':revision},ensure_ascii=False,indent=2).encode(),'application/json'
    if doc['kind']=='flowchart' and format=='svg':return diagram_svg(content).encode(),'image/svg+xml'
    if doc['kind']=='flowchart' and format=='pdf':
        if any('\u0b80'<=c<='\u0bff' for c in json.dumps(content,ensure_ascii=False)):
            if not (shutil.which('libreoffice') or shutil.which('soffice')):raise ServiceUnavailable('Tamil diagram PDF export needs the local document worker with LibreOffice Draw and Tamil fonts. SVG/PNG preserve the complete labels.')
            with tempfile.TemporaryDirectory(prefix='usopp-flow-') as folder:
                path=Path(folder)/'diagram.svg';path.write_text(diagram_svg(content),encoding='utf-8');return office_convert(path,'pdf'),'application/pdf'
        from reportlab.pdfgen import canvas
        from reportlab.graphics import renderPDF
        from svglib.svglib import svg2rlg
        drawing=svg2rlg(io.BytesIO(diagram_svg(content).encode()))
        output=io.BytesIO();width=max(595,drawing.width+50);height=max(842,drawing.height+70)
        pdf=canvas.Canvas(output,pagesize=(width,height));pdf.setTitle(doc['title']);pdf.setFont('Helvetica',13)
        pdf.drawString(25,height-25,f'{doc["title"]} / r{revision["number"]} / {revision["status"]}')
        renderPDF.draw(drawing,pdf,25,25);pdf.save();return output.getvalue(),'application/pdf'
    if format=='docx' or format=='pdf':
        from docx import Document
        document=Document();document.add_heading(doc['title'],0);document.add_paragraph(f'Revision {revision["number"]} · {revision["status"]}')
        if doc['kind']=='flowchart':
            document.add_paragraph('Engineering discussion diagram. Review its sequence; it is not validated PLC logic.')
            document.add_heading('Nodes and connections',1)
            for node in content.get('nodes',[]):document.add_paragraph(str(node['id'])+': '+str(node.get('data',{}).get('label','')))
            for edge in content.get('edges',[]):document.add_paragraph(str(edge['source'])+' -> '+str(edge['target'])+' / '+str(edge.get('label','')))

        for line in list(readable_lines(content))[:10000]:document.add_paragraph(line)
        sources=content.get('sources',[])
        if sources:
            document.add_heading('Source references',1)
            for source in sources[:2000]:
                paragraph=document.add_paragraph(f'{source.get("id","")}: {source.get("filename",source.get("meeting_id",""))} / page {source.get("page","-")} / {source.get("start","-")} s: {source.get("text","")[:300]}')
                _source_hyperlink(paragraph,doc['project_id'],source)

        buffer=io.BytesIO();document.save(buffer)
        if format=='docx':return buffer.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        if shutil.which('libreoffice') or shutil.which('soffice'):
            with tempfile.TemporaryDirectory(prefix='usopp-export-') as folder:
                path=Path(folder)/'document.docx';path.write_bytes(buffer.getvalue());return office_convert(path,'pdf'),'application/pdf'
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from xml.sax.saxutils import escape
        lines=list(readable_lines(content))[:10000]
        if any('\u0b80'<=c<='\u0bff' for c in json.dumps(content,ensure_ascii=False)):raise ServiceUnavailable('Tamil PDF layout needs the local document worker with Tamil fonts. DOCX export remains available.')
        out=io.BytesIO();styles=getSampleStyleSheet();story=[Paragraph(escape(doc['title']),styles['Title']),Paragraph(f'Revision {revision["number"]} / {revision["status"]}',styles['Normal']),Spacer(1,12)]
        if doc['kind']=='flowchart':
            from svglib.svglib import svg2rlg
            drawing=svg2rlg(io.BytesIO(diagram_svg(content).encode()))
            if drawing:
                scale=min(1,480/max(1,drawing.width),650/max(1,drawing.height));drawing.scale(scale,scale);drawing.width*=scale;drawing.height*=scale;story.append(drawing)
        else:
            story.extend(Paragraph(escape(line),styles['Normal']) for line in lines)
            for source in content.get('sources',[])[:2000]:
                link=source_url(doc['project_id'],source)
                caption=escape(str(source.get('id',''))+' / '+str(source.get('filename',''))+' / page '+str(source.get('page','-'))+' / '+str(source.get('start','-'))+' s')
                story.append(Paragraph('<a href="'+escape(link)+'">'+caption+'</a>' if link else caption,styles['Normal']))

        SimpleDocTemplate(out).build(story);return out.getvalue(),'application/pdf'
    raise ValueError('Choose PDF, DOCX, JSON or diagram SVG.')


def source_url(project_id,source):
    from urllib.parse import urlencode
    base=os.getenv('USOPP_PI_PUBLIC_ORIGIN','').rstrip('/')
    if not base:return ''
    params={'workhubProject':project_id}
    if source.get('meeting_id'):
        params.update(piMeeting=source['meeting_id'],piTime=source.get('start') or 0,piVersion=source.get('transcript_version') or '')
    elif source.get('document_id'):params.update(piDocument=source['document_id'],piPage=source.get('page') or 1,piRevision=source.get('revision_id') or '')
    else:return base+'/api/workhub/files/'+str(source['file_id'])+'/download' if source.get('file_id') else ''
    return base+'/?'+urlencode(params)+'#workhub'


def _source_hyperlink(paragraph,project_id,source):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    url=source_url(project_id,source)
    if not url:return
    link=OxmlElement('w:hyperlink');link.set(qn('r:id'),paragraph.part.relate_to(url,RT.HYPERLINK,is_external=True))
    run=OxmlElement('w:r');value=OxmlElement('w:t');value.text=' Open exact source in WorkHub';run.append(value);link.append(run);paragraph._p.append(link)


def diagram_svg(content):
    from xml.sax.saxutils import escape
    import textwrap
    nodes=content.get('nodes',[]);edges=content.get('edges',[])
    positions={n['id']:n for n in nodes};sizes={}
    for node in nodes:
        body=str(node.get('data',{}).get('label',''))
        links=', '.join(str(i) for i in node.get('data',{}).get('requirement_ids',[]))
        lines=[]
        for line in (body+('\n'+links if links else '')).splitlines() or ['']:
            lines.extend(textwrap.wrap(line,width=30,replace_whitespace=False,drop_whitespace=False) or [''])
        sizes[node['id']]=(lines,max(75,len(lines)*17+30))
    low_x=min([n['position']['x'] for n in nodes]+[0])-40;low_y=min([n['position']['y'] for n in nodes]+[0])-40
    width=max([n['position']['x']+250 for n in nodes]+[500])-low_x+40
    height=max([n['position']['y']+sizes[n['id']][1] for n in nodes]+[300])-low_y+85
    result=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{low_x} {low_y} {width} {height}" width="{width}" height="{height}"><rect x="{low_x}" y="{low_y}" width="{width}" height="{height}" fill="white"/><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#126575"/></marker></defs>']
    for edge in edges:
        a=positions.get(edge['source']);b=positions.get(edge['target'])
        if not a or not b:continue
        x=a['position']['x']+240;y=a['position']['y']+sizes[a['id']][1]/2
        tx=b['position']['x'];ty=b['position']['y']+sizes[b['id']][1]/2;middle=(x+tx)/2
        result.append(f'<path d="M{x} {y} C{middle} {y} {middle} {ty} {tx} {ty}" stroke="#126575" stroke-width="2" fill="none" marker-end="url(#arrow)"/>')
        for i,line in enumerate(textwrap.wrap(str(edge.get('label','')),width=35)):
            result.append(f'<text x="{middle+5}" y="{(y+ty)/2+i*15}" font-size="12" fill="#17344b">{escape(line)}</text>')
    for node in nodes:
        x=node['position']['x'];y=node['position']['y'];data=node.get('data',{});kind=data.get('kind','process');lines,h=sizes[node['id']]
        if kind=='decision':result.append(f'<path d="M{x+120} {y-12} L{x+255} {y+h/2} L{x+120} {y+h+12} L{x-15} {y+h/2} Z" fill="#fff6d8" stroke="#b08623"/>')
        else:result.append(f'<rect x="{x}" y="{y}" width="240" height="{h}" rx="{30 if kind in ("start","end") else 8}" fill="#e7f5f4" stroke="#126575"/>')
        for index,line in enumerate(lines):result.append(f'<text x="{x+120}" y="{y+23+index*17}" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" fill="#17344b">{escape(line)}</text>')
    result.append(f'<text x="{low_x+20}" y="{height+low_y-20}" font-size="11" fill="#546b77">Engineering draft: sequence requires review; not validated PLC logic.</text></svg>')
    return ''.join(result)
