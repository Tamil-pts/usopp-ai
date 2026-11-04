"""Indexed, immutable project PDFs and narrowly projected customer exports."""
import io
import json
import os
from pathlib import Path
from xml.sax.saxutils import escape
from fastapi import HTTPException
from . import store,configuration,checks
from .store import hub,pi,identity,timestamp
from backend.core.workhub_intelligence.documents import generated_file
from backend.core.workhub_intelligence.local_ai import ServiceUnavailable

def snapshot(db,p):
    report=checks.report(db,p,True);state=store.policy_row(db,p);docs=[]
    for d in report['documents']:
        if d['approved_revision']:
            rev=store.revision(db,d['id'],d['approved_revision'])
            if rev['status'] not in {'approved','released','superseded'}:continue
            docs.append({'document':{k:d[k] for k in ('id','stage','number','document_id')},'revision':store.detail(db,d,rev)})
    return {'project':store.source_header(db,p,state),'policy':state['policy'],'quality':report,'documents':docs,
      'branding':configuration.current(db)['configuration']['branding'],
      'audit':[{**dict(r),'detail':json.loads(r['detail'])} for r in db.execute('SELECT * FROM qc_audit WHERE project_id=? ORDER BY id',(p['id'],))],
      'approval_history':[{**dict(r),'detail':json.loads(r['detail'])} for r in db.execute("SELECT * FROM events WHERE project_id=? AND event IN ('quality_pass','approve_release','release','request_changes','reopen') ORDER BY id",(p['id'],))],
      'issues':[dict(r) for r in db.execute('SELECT * FROM issues WHERE project_id=? ORDER BY created_at',(p['id'],))],
      'updates':[dict(r) for r in db.execute('SELECT id,author_id,body,work_date,created_at FROM updates WHERE project_id=? ORDER BY created_at',(p['id'],))],
      'files':[dict(r) for r in db.execute('SELECT * FROM files WHERE project_id=? AND NOT EXISTS(SELECT 1 FROM qc_generated_files g WHERE g.file_id=files.id)',(p['id'],))],
      'users':{str(u['id']):u['username'] for u in hub.users()},'captured_at':timestamp(),'final':p['stage']=='released'}

def export_signature(db,p):
    return store.digest({'baseline':checks.baseline(db,p,True),'final':p['stage']=='released',
      'authorization':[dict(r) for r in db.execute('SELECT r.id,r.customer_safe,r.customer_authorized_at FROM qc_revisions r JOIN qc_documents q ON q.id=r.control_id WHERE q.project_id=? ORDER BY r.id',(p['id'],))]})

def customer_projection(data):
    docs=[]
    for record in data['documents']:
        r=record['revision']
        if not r['customer_safe']:continue
        content=r['content'];cases=[]
        for c in content.get('cases',[]):
            ex=c.get('execution');cases.append({k:c.get(k) for k in ('id','objective','procedure','expected_result','acceptance_criteria','requirement_ids')}|
               {'execution':{k:ex.get(k) for k in ('outcome','actual','observations','executed_at')} if ex else None})
        # Source excerpts, internal issue history, raw tool data, user IDs, file locations and audit comments are excluded.
        clean={'summary':content.get('summary'),'requirements':[{k:r.get(k) for k in ('id','title','description','expected_behavior','acceptance_criteria','mandatory')} for r in content.get('requirements',[])],
          'cases':cases,'changes':[{k:c.get(k) for k in ('id','summary','requirement_ids')} for c in content.get('changes',[])],
          'sections':content.get('sections',[]),'applicability':content.get('applicability'),'na_reason':content.get('na_reason')}
        for k in ('purpose','scope','acceptance_summary'):clean[k]=content.get(k)
        if content.get('flowchart'):
            f=content['flowchart'];clean['flowchart']={'nodes':[{k:n[k] for k in ('id','position')}|{'data':{k:n.get('data',{}).get(k) for k in ('label','kind','requirement_ids')}} for n in f.get('nodes',[])],
                'edges':[{k:e.get(k) for k in ('id','source','target','label')} for e in f.get('edges',[])],'notice':'Engineering interpretation from this customer-authorized FRD revision; not validated PLC logic.'}
        acceptance=r.get('acceptance')
        docs.append({'document':record['document'],'revision':{k:r.get(k) for k in ('id','number','label','status','template_version','approved_at','released_at')}|
          {'content':clean,'acceptance':{k:acceptance.get(k) for k in ('status','customer','representative','accepted_at','remarks')} if acceptance else None}})
    return {'project':{k:data['project'].get(k) for k in ('project_id','project_name','project_type','customer','machine','completed_at')},
       'branding':data['branding'],'documents':docs,'final':data['final'],'captured_at':data['captured_at'],
       'authorized_file_ids':list({key for r in data['documents'] if r['revision']['customer_safe'] for key in r['revision'].get('customer_file_ids',[])}),
       'notice':'Only revisions explicitly authorized for customer release are included. Supporting internal records and attachments remain in the internal audit package.'}

def _pdf_font(text):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if all(ord(c)<256 or c in '\u2013\u2014\u2018\u2019\u201c\u201d\u2022' for c in text):return 'Helvetica'
    choices=[os.getenv('USOPP_PDF_FONT',''),'/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',r'C:\Windows\Fonts\arial.ttf']
    for path in choices:
        if path and Path(path).is_file():
            try:
                font=TTFont('QCUnicode',path);chars=font.face.charToGlyph
                if all(c.isspace() or ord(c) in chars for c in text):pdfmetrics.registerFont(font);return 'QCUnicode'
            except Exception:continue
    raise ServiceUnavailable('A local Unicode PDF font covering this document is required. Configure USOPP_PDF_FONT on the document worker; the source records remain stored.')

def render(data,title,audience='internal',single=False):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,LongTable,TableStyle,Image
    from reportlab.platypus.tableofcontents import TableOfContents
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    all_text=json.dumps(data,ensure_ascii=False);font=_pdf_font(all_text);styles=getSampleStyleSheet()
    for s in styles.byName.values():s.fontName=font
    styles['Normal'].fontSize=9;styles['Normal'].leading=13;styles['Normal'].wordWrap='CJK';styles['Heading1'].fontSize=15
    brand=data.get('branding',{});accent=colors.HexColor(brand.get('accent','#0b6472'));out=io.BytesIO()
    class Indexed(SimpleDocTemplate):
        def afterFlowable(self,flowable):
            key=getattr(flowable,'_qc_key',None)
            if key:
                self.canv.bookmarkPage(key);self.canv.addOutlineEntry(flowable.getPlainText(),key,0,False)
                self.notify('TOCEntry',(0,flowable.getPlainText(),self.page,key))
    story=[];heading_count=0
    def para(value):return Paragraph(escape(str(value if value is not None and value!='' else 'Not recorded')).replace('\n','<br/>'),styles['Normal'])
    def heading(value):
        nonlocal heading_count
        heading_count+=1;p=Paragraph(escape(str(value)),styles['Heading1']);p._qc_key='section-'+str(heading_count);story.append(p)
    def table(rows):
        if not rows:return
        t=LongTable([[para(k),para(v)] for k,v in rows],colWidths=[145,350],hAlign='LEFT',splitInRow=1)
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#dce5e9')),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6)]));story.append(t);story.append(Spacer(1,10))
    logo=brand.get('logo_file_id')
    if logo:
        from backend.core.workhub_files import file_record
        _,path=file_record(logo);image=Image(str(path));scale=min(140/image.imageWidth,55/image.imageHeight,1);image.drawWidth=image.imageWidth*scale;image.drawHeight=image.imageHeight*scale;story.append(image)
    story.extend([Paragraph(escape(brand.get('name','PTPL')),styles['Title']),Paragraph(escape(title),styles['Title']),
      para('Internal audit copy' if audience=='internal' else 'Customer-authorized copy'),Spacer(1,16)])
    p=data.get('project',{});table([(k.replace('_',' ').title(),p.get(k)) for k in ('project_name','project_id','project_type','customer','machine','completed_at')])
    story.append(para('Historical audit compilation' if data.get('kind')=='iso_audit' else 'Final closure record' if data.get('final') else 'Quality preparation / closure pending'))
    story.append(para('Snapshot captured: '+str(data.get('captured_at'))))
    if data.get('notice'):story.append(para(data['notice']))
    story.append(PageBreak());heading('Package index');toc=TableOfContents();toc.levelStyles=[styles['Normal']];story.append(toc);story.append(PageBreak())
    heading('Document register')
    table([(r['document']['number'],store.STAGES.get(r['document']['stage'],r['document']['stage'])+' / '+r['revision']['label']+' / '+r['revision']['status']+' / template '+r['revision']['template_version']) for r in data.get('documents',[])])
    if not data.get('documents'):story.append(para('No document revisions are authorized for this audience in this snapshot.'))
    for record in data.get('documents',[]):
        d=record['document'];r=record['revision'];c=r['content'];story.append(PageBreak());template=json.loads(r['template_snapshot']) if r.get('template_snapshot') else {};heading(d['number']+' / '+r['label']+' / '+template.get('title',store.STAGES[d['stage']]))
        users=data.get('users',{});table([('Status',r['status']),('Owner',users.get(str(r.get('owner_id')))),('Human confirmation',r.get('confirmed_at')),
          ('Approved by',users.get(str(r.get('approved_by')))),('Approval timestamp',r.get('approved_at')),('Revision reason',r.get('reason'))] if audience=='internal' else [('Status',r['status']),('Approval timestamp',r.get('approved_at'))])
        story.append(para(c.get('summary')))
        for k in ('purpose','scope','acceptance_summary'):
            if c.get(k):table([(k.replace('_',' ').title(),c[k])])
        if c.get('applicability')=='not_applicable':story.append(para('Not Applicable: '+str(c.get('na_reason'))))
        for requirement in c.get('requirements',[]):table([(requirement['id'],requirement.get('title')),('Description',requirement.get('description')),('Expected behavior',requirement.get('expected_behavior')),('Acceptance criteria',requirement.get('acceptance_criteria'))])
        if c.get('flowchart'):
            heading('FRD functional flowchart / engineering interpretation')
            from backend.core.workhub_intelligence.documents import diagram_svg
            from svglib.svglib import svg2rlg
            drawing=svg2rlg(io.BytesIO(diagram_svg(c['flowchart']).encode()))
            if drawing:
                scale=min(495/max(1,drawing.width),620/max(1,drawing.height),1);drawing.scale(scale,scale);drawing.width*=scale;drawing.height*=scale;story.append(drawing)
            story.append(para(c['flowchart'].get('notice') or 'Review against the linked requirements. This is not validated PLC logic.'))
        for change in c.get('changes',[]):table([(change['id'],change.get('summary')),('Requirement links',', '.join(change.get('requirement_ids',[])))])
        for case in c.get('cases',[]):
            ex=case.get('execution');table([(case['id'],case.get('objective')),('Requirement links',', '.join(case.get('requirement_ids',[]))),('Procedure',case.get('procedure')),('Expected result',case.get('expected_result')),('Acceptance criteria',case.get('acceptance_criteria')),
               ('Actual outcome',ex.get('outcome') if ex else 'Native recorded result (see validation appendix)' if case.get('native_run_id') and audience=='internal' else 'Not executed / not recorded'),
               ('Actual result',ex.get('actual') if ex else None),('Observations',ex.get('observations') if ex else None),('Executed at',ex.get('executed_at') if ex else None)])
        if r.get('acceptance'):table([('Customer acceptance',json.dumps(r['acceptance'],ensure_ascii=False))])
        for section in c.get('sections',[]):story.extend([Paragraph(escape(section['heading']),styles['Heading2']),para(section.get('text'))])
        if audience=='internal':
            for source in c.get('sources',[]):table([('Source '+source['id'],source.get('label')),('Location',json.dumps({k:v for k,v in source.items() if k not in {'text','label'}},ensure_ascii=False)),('Source excerpt',source.get('text'))])
    if audience=='internal':
        q=data.get('quality',{});story.append(PageBreak());heading('Requirement traceability and quality dispositions')
        table([(r['requirement_id']+' / '+r['stage'],', '.join(r['case_ids'])+' / '+('Covered' if r['covered'] else 'Approved disposition' if r['waived'] else 'Not covered')) for r in q.get('traceability',[])])
        table([(r['code'],r['title']+' / '+json.dumps(r.get('waiver') or {},ensure_ascii=False)) for r in q.get('dispositions',[])])
        story.append(PageBreak());heading('Actual validation records')
        for run in q.get('validation_runs',[]):table([(run['kind']+' / '+run['run_id'],run['status']+' / '+run['outcome']),('Recorded native summary',json.dumps(run['summary'],ensure_ascii=False))])
        if data.get('raw_evidence'):story.append(para('Exact archived validation JSON is embedded in the PDF as attachments. Large native project files remain in controlled storage and are identified in the manifest.'))
        story.append(PageBreak());heading('Nonconformance, corrective action and project approval history')
        table([(r['title'],r['status']+' / '+r['updated_at']) for r in data.get('issues',[])])
        table([(r['work_date'],r['body']) for r in data.get('updates',[])])
        table([(str(r['id'])+' / '+r['event'],r['created_at']+' / '+json.dumps(r['detail'],ensure_ascii=False)) for r in data.get('approval_history',[])])
        story.append(PageBreak());heading('Controlled audit trail')
        table([(str(r['id'])+' / '+r['action'],r['created_at']+' / '+str(data.get('users',{}).get(str(r['actor_id']),r['actor_id']))+' / '+json.dumps(r['detail'],ensure_ascii=False)) for r in data.get('audit',[])])
        story.append(PageBreak());heading('File and revision manifest')
        table([(r['name'],'SHA-256 '+r['sha256']+' / '+str(r['size'])+' bytes / /api/workhub/files/'+r['id']+'/download') for r in data.get('files',[])])
    def page(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(accent);canvas.line(48,A4[1]-37,A4[0]-48,A4[1]-37);canvas.setFont(font,8);canvas.setFillColor(accent)
        canvas.drawString(48,A4[1]-29,brand.get('name','PTPL')+' / '+brand.get('subtitle',''));canvas.setFillColor(colors.grey);canvas.drawString(48,25,'Controlled snapshot / '+audience);canvas.drawRightString(A4[0]-48,25,'Page '+str(doc.page));canvas.restoreState()
    doc=Indexed(out,pagesize=A4,rightMargin=48,leftMargin=48,topMargin=55,bottomMargin=45,title=title,author=brand.get('name','PTPL'))
    doc.multiBuild(story,onFirstPage=page,onLaterPages=page,maxPasses=8)
    return out.getvalue()

def _raw_results(data):
    from backend.core.persistent_store import archived_run
    from backend.core import run_history
    result={};size=0
    for r in data['quality']['validation_runs']:
        archived=archived_run(r['run_id']);raw=archived[1] if archived else None
        if raw is None:
            path=run_history.RECORDS/r['run_id']/'result.json'
            if path.is_file() and path.stat().st_size<=20*1024*1024:
                try:raw=json.loads(path.read_text('utf-8'))
                except (OSError,ValueError):raw=None
        if raw is not None:
            encoded=json.dumps(raw,ensure_ascii=False).encode();size+=len(encoded)
            if size>100*1024*1024:raise ValueError('Exact run evidence exceeds 100 MiB. Select an audit scope with fewer runs; originals remain in storage.')
            result[r['run_id']]=encoded
    return result

def linked_files(data,audience):
    if audience=='customer':return set(data.get('authorized_file_ids',[]))
    result=set()
    for record in data['documents']:
        r=record['revision'];result.update(r['content'].get('file_ids',[]));result.update((r.get('acceptance') or {}).get('file_ids',[]))
        for c in r['content'].get('cases',[]):result.update((c.get('execution') or {}).get('file_ids',[]))
    return result

def embed_files(writer,data,pid,audience,job):
    from pypdf import PdfReader
    from backend.core.workhub_files import file_record
    included=[];external=[];size=0
    for key in sorted(linked_files(data,audience)):
        job.check();row,path=file_record(key,pid);size+=row['size']
        item={k:row[k] for k in ('id','name','sha256','size')}
        if row['size']>25*1024*1024 or size>100*1024*1024:
            external.append({**item,'reason':'Retained in controlled storage; exceeds the PDF embedding limit.'});continue
        raw=path.read_bytes();name=Path(row['name']).name
        writer.add_attachment(key+'-'+name,raw)
        if name.lower().endswith('.pdf'):
            reader=PdfReader(io.BytesIO(raw))
            if not reader.is_encrypted:writer.append(reader,outline_item='Evidence / '+name,import_outline=False,excluded_fields=['/Annots'])
        included.append(item)
    return included,external

def generate(job,user):
    store.initialize();pid=job.row['project_id']
    with hub.db() as db:
        p=store.project(db,pid,user,True);data=snapshot(db,p);sig=export_signature(db,p)
        if not data['quality']['quality_approved']:raise ValueError('Approve the current quality review before preparing a closure package.')
    job.progress(15,'Collecting immutable approved revisions and original validation records')
    evidence=_raw_results(data);data['raw_evidence']=list(evidence);created=[]
    from pypdf import PdfWriter,PdfReader
    for audience in ('internal','customer'):
        with hub.db() as db:
            prior=db.execute('SELECT q.id,q.number FROM qc_packages q JOIN qc_generated_files g ON g.file_id=q.file_id WHERE g.job_id=? AND q.project_id=? AND q.audience=?',(job.row['id'],pid,audience)).fetchone()
        if prior:
            created.append({'id':prior['id'],'audience':audience,'number':prior['number']});continue
        job.check();job.progress(35 if audience=='internal' else 70,'Rendering the '+audience+' indexed closure PDF')
        view=data if audience=='internal' else customer_projection(data);pdf=render(view,'Project closure package',audience)
        writer=PdfWriter();writer.append(PdfReader(io.BytesIO(pdf)))
        included,external=embed_files(writer,view,pid,audience,job)
        writer.add_attachment('controlled-manifest.json',store.bounded({'snapshot':view,'included_files':included,'externally_retained_files':external}).encode())
        if audience=='internal':
            for run_id,raw in evidence.items():writer.add_attachment('validation-'+run_id+'.json',raw)
        output=io.BytesIO();writer.write(output);payload=output.getvalue()
        with hub.db() as db:
            current=store.project(db,pid,user,True)
            if export_signature(db,current)!=sig:raise ValueError('The approved baseline or customer release authorization changed during PDF generation. Generate a fresh package.')
        file=generated_file(user,pid,'QC-'+audience.upper()+'-'+pid+'-'+job.row['id']+'.pdf',payload)
        with hub.db(True) as db:
            db.execute('INSERT OR IGNORE INTO qc_generated_files VALUES(?,?,?,?)',(file['id'],'closure_package',job.row['id'],timestamp()))
        with hub.db(True) as db:
            current=store.project(db,pid,user,True)
            if export_signature(db,current)!=sig:raise ValueError('The controlled baseline changed. The generated file is retained but was not registered as an approved package.')
            existing=db.execute('SELECT id,number FROM qc_packages WHERE project_id=? AND audience=? AND manifest LIKE ?',(pid,audience,'%"job_id": "'+job.row['id']+'"%')).fetchone()
            if existing:created.append({'id':existing['id'],'audience':audience,'number':existing['number']});continue
            number=db.execute('SELECT COALESCE(MAX(number),0)+1 FROM qc_packages WHERE project_id=? AND audience=?',(pid,audience)).fetchone()[0]
            key=identity();manifest={'job_id':job.row['id'],'signature':sig,'project_id':pid,'audience':audience,'number':number,'document_revisions':[{'number':d['document']['number'],'revision_id':d['revision']['id'],'label':d['revision']['label']} for d in view['documents']], 'raw_evidence_ids':list(evidence) if audience=='internal' else [],'included_files':included,'externally_retained_files':external,'captured_at':data['captured_at']}
            db.execute('INSERT INTO qc_packages VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,pid,audience,number,sig,store.bounded(manifest),file['id'],file['sha256'],user['id'],timestamp(),int(data['final'])))
            store.audit(db,user,pid,'closure_package_generated',{'package_id':key,'audience':audience,'number':number,'sha256':file['sha256'],'manifest':manifest})
            created.append({'id':key,'audience':audience,'number':number})
    return {'packages':created}

def export_document(user,pid,key,rid=None,format='pdf',record_download=True):
    from backend.core.workhub_document_filename import filename
    store.initialize()
    with hub.db(True) as db:
        p=store.project(db,pid,user);doc=store.control(db,pid,key);rev=store.revision(db,doc['id'],rid or store.native(db,doc)['current_revision'])
        value=snapshot(db,p);value['documents']=[{'document':doc,'revision':store.detail(db,doc,rev)}]
        value['quality']={};value['audit']=[];value['files']=[];value['approval_history']=[]
        if record_download:store.audit(db,user,pid,'document_downloaded',{'format':format,'status':rev['status']},doc['id'],rev['id'])
    if format=='json':return store.bounded(value).encode(),'application/json',filename(doc,rev,'json')
    if format=='svg':
        flow=value['documents'][0]['revision']['content'].get('flowchart')
        if not flow:raise HTTPException(404,'This FRD revision has no saved flowchart.')
        from backend.core.workhub_intelligence.documents import diagram_svg
        return diagram_svg(flow).encode(),'image/svg+xml',filename(doc,rev,'svg')
    if format=='docx' or format=='pdf' and value['documents'][0]['revision']['content'].get('studio'):
        from backend.core.workhub_studio.exporting import export as studio_export
        data,mime,_=studio_export(user,pid,doc['document_id'],rev['id'],format)
        return data,mime,filename(doc,rev,format)
    if format!='pdf':raise HTTPException(400,'Choose controlled PDF or JSON.')
    from .pdf_templates import export
    return export(user,pid,doc,rev),'application/pdf',filename(doc,rev,'pdf')

def package_download(user,pid,key):
    store.initialize()
    with hub.db(True) as db:
        store.project(db,pid,user);row=db.execute('SELECT * FROM qc_packages WHERE id=? AND project_id=?',(key,pid)).fetchone()
        if not row:raise HTTPException(404,'Controlled package not found.')
        if row['audience']=='iso':configuration.admin(user)
        store.audit(db,user,pid,'package_downloaded',{'package_id':key,'audience':row['audience'],'number':row['number']})
    from backend.core.workhub_files import file_record
    return file_record(row['file_id'],pid)

def iso(job,user):
    store.initialize()
    configuration.admin(user);payload=job.row['payload'];ids=payload.get('project_ids',[]);start=payload.get('from','');end=payload.get('to','')
    with hub.db() as db:
        store.project(db,job.row['project_id'],user,True)
        prior=db.execute("SELECT q.id FROM qc_packages q JOIN qc_generated_files g ON g.file_id=q.file_id WHERE g.job_id=? AND q.project_id=? AND q.audience='iso'",(job.row['id'],job.row['project_id'])).fetchone()
        if prior:return {'package_id':prior['id'],'audience':'iso','recovered':True}
    from datetime import date
    if not isinstance(ids,list) or len(ids)>100:raise ValueError('Select up to 100 projects.')
    for value in (start,end):
        if value:date.fromisoformat(value)
    if not ids and not (start and end):raise ValueError('Choose projects or a bounded date range.')
    if start and end and start>end:raise ValueError('The ISO range end must follow the start.')
    with hub.db() as db:
        sql="SELECT q.*,f.size AS file_size FROM qc_packages q JOIN files f ON f.id=q.file_id WHERE q.audience='internal'";params=[]
        if ids:sql+=' AND q.project_id IN ('+','.join('?' for _ in ids)+')';params.extend(ids)
        if start:sql+=' AND q.created_at>=?';params.append(start)
        if end:sql+=' AND substr(q.created_at,1,10)<=?';params.append(end)
        rows=[dict(r) for r in db.execute(sql+' ORDER BY q.project_id,q.number LIMIT 501',params)]
        if len(rows)>500:raise ValueError('Select a smaller audit scope (maximum 500 controlled packages).')
        config=configuration.current(db)['configuration']
    if not rows:raise ValueError('No controlled internal packages match this audit scope.')
    from pypdf import PdfWriter,PdfReader
    from backend.core.workhub_files import file_record
    index={'kind':'iso_audit','project':{'project_name':'ISO Audit Pack','project_id':job.row['project_id']},'documents':[],'branding':config['branding'],'captured_at':timestamp(),'final':False,
       'notice':'Controlled historical packages selected by project and package-creation dates. Individual package revision identities and approval status are preserved.',
       'files':[{'name':r['project_id']+' / internal package '+str(r['number']),'sha256':r['sha256'],'size':r['file_size'],'id':r['file_id']} for r in rows]}
    writer=PdfWriter();writer.append(PdfReader(io.BytesIO(render(index,'ISO Audit Pack'))))
    manifest=[];total_size=0
    for i,r in enumerate(rows):
        job.check();job.progress(10+int(75*i/len(rows)),'Collecting controlled historical project packages')
        file,path=file_record(r['file_id'],r['project_id']);total_size+=file['size']
        if total_size>500*1024*1024:raise ValueError('Select an audit scope below 500 MiB.')
        reader=PdfReader(str(path));writer.append(reader,outline_item=r['project_id']+' / internal r'+str(r['number']))
        for name,values in reader.attachments.items():
            for j,raw in enumerate(values):writer.add_attachment(r['id']+'-'+str(j)+'-'+name,raw)
        manifest.append({k:r[k] for k in ('id','project_id','number','baseline','sha256','created_at','final')})
    writer.add_attachment('iso-package-index.json',store.bounded(manifest).encode())
    from reportlab.pdfgen import canvas
    for i,page in enumerate(writer.pages):
        stamp=io.BytesIO();c=canvas.Canvas(stamp,pagesize=(float(page.mediabox.width),float(page.mediabox.height)));c.setFont('Helvetica',7);c.drawRightString(float(page.mediabox.width)-40,11,f'ISO Audit Pack / {i+1} of {len(writer.pages)}');c.save();page.merge_page(PdfReader(io.BytesIO(stamp.getvalue())).pages[0])
    out=io.BytesIO();writer.write(out)
    file=generated_file(user,job.row['project_id'],'QC-ISO-'+job.row['id']+'.pdf',out.getvalue())
    with hub.db(True) as db:
        job.check()
        from backend.core.workhub_intelligence.reliability import guard_generation
        guard_generation(db,job.row['id'])
        prior=db.execute("SELECT q.id FROM qc_packages q JOIN qc_generated_files g ON g.file_id=q.file_id WHERE g.job_id=? AND q.project_id=? AND q.audience='iso'",(job.row['id'],job.row['project_id'])).fetchone()
        if prior:return {'package_id':prior['id'],'audience':'iso','recovered':True}
        db.execute('INSERT OR IGNORE INTO qc_generated_files VALUES(?,?,?,?)',(file['id'],'iso_pack',job.row['id'],timestamp()))
        n=db.execute("SELECT COALESCE(MAX(number),0)+1 FROM qc_packages WHERE project_id=? AND audience='iso'",(job.row['project_id'],)).fetchone()[0];key=identity()
        db.execute('INSERT INTO qc_packages VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,job.row['project_id'],'iso',n,store.digest(manifest),store.bounded(manifest),file['id'],file['sha256'],user['id'],timestamp(),0))
        store.audit(db,user,job.row['project_id'],'iso_audit_pack_generated',{'id':key,'project_packages':len(rows),'sha256':file['sha256']})
    return {'package_id':key,'audience':'iso'}

def file_access(db,user,row):
    """Called by existing file routes too, so direct URLs cannot bypass pack permissions/audit."""
    p=hub.item(db,row['project_id'])
    if p.get('is_document_space'):
        from backend.core.workhub_document_spaces import authorize
        authorize(db,p,user)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='qc_packages'").fetchone():return
    if row['name'].startswith('QC-ISO-'):configuration.admin(user)
    pack=db.execute('SELECT * FROM qc_packages WHERE file_id=?',(row['id'],)).fetchone()
    if not pack and db.execute('SELECT 1 FROM qc_generated_files WHERE file_id=?',(row['id'],)).fetchone():raise HTTPException(409,'This preparation output was not registered as a controlled package. Use the current package register.')
    if pack:
        if pack['audience']=='iso':configuration.admin(user)
        store.audit(db,user,row['project_id'],'package_file_downloaded',{'package_id':pack['id'],'file_id':row['id']})
    else:
        for r in db.execute('SELECT q.id AS control_id,r.id AS revision_id,r.content FROM qc_documents q JOIN pi_revisions r ON r.document_id=q.document_id WHERE q.project_id=?',(row['project_id'],)):
            if row['id'] in json.loads(r['content']).get('file_ids',[]):store.audit(db,user,row['project_id'],'linked_document_file_downloaded',{'file_id':row['id']},r['control_id'],r['revision_id'])
