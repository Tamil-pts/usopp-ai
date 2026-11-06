"""One safe view model and renderer for engineering document PDFs.

Approved source/layout snapshots are frozen at approval. The first PDF bytes are
stored once, hash checked on every retrieval and never replaced on template edits.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
from xml.sax.saxutils import escape
from fastapi import HTTPException
from . import store, branding
from .store import hub, pi, timestamp

TEMPLATE=Path(__file__).with_name('templates')/'engineering.html.j2'
APPROVED={'approved','released','superseded','archived'}


def source_hash(rev):
    return rev.get('content_hash') or store.digest(rev['content'])


def context(db,p,doc,rev,controlled=True):
    state=store.policy_row(db,p);org=branding.organization(db,state['context'])
    customer=branding.record(db,'customer',state['context']['customer_id']) if state['context'].get('customer_id') else None
    kind=doc.get('stage',doc.get('kind','note'));layout=branding.template(db,kind,state['context'])
    detail=store.detail(db,doc,rev) if controlled else rev
    content=detail['content']
    users={u['id']:u['username'] for u in hub.users()}
    org_data=json.loads(store.bounded(org['data']));customer_data=customer['data'].copy() if customer else {'name':state['context'].get('customer') or p.get('customer') or '','address':''}
    if kind=='mom' and not customer_data.get('name'):customer_data['name']=content.get('customer') or ''
    assets=[]
    for value in [org_data,customer_data]:
        item=branding.asset(db,value.get('logo_id'))
        value['logo_data']=''
        if item:
            value['logo_data']='data:image/png;base64,'+base64.b64encode(item['data']).decode()
            assets.append({'id':item['id'],'version':item['version'],'sha256':item['sha256']})
    # Read only a previously configured, bounded project logo; new logos use the
    # decoded versioned store. No filesystem path or remote URL is accepted.
    if org_data.get('legacy_logo_file_id'):
        from backend.core.workhub_files import file_record
        _,path=file_record(org_data['legacy_logo_file_id'])
        if path.stat().st_size<=2*1024*1024:
            from PIL import Image
            with Image.open(path) as im:
                im.thumbnail((1600,1000));out=io.BytesIO();im.convert('RGBA').save(out,format='PNG')
                raw=out.getvalue();org_data['logo_data']='data:image/png;base64,'+base64.b64encode(raw).decode()
                assets.append({'id':org_data['legacy_logo_file_id'],'sha256':hashlib.sha256(raw).hexdigest()})
    author=users.get(rev.get('owner_id',rev.get('created_by')),'Not recorded')
    reviewed=users.get(rev.get('reviewed_by'),'Pending review')
    approved=users.get(rev.get('approved_by',rev.get('reviewed_by') if rev['status'] in APPROVED else None),'Pending approval')
    linked=hub.item(db,p['linked_project_id']) if p.get('is_document_space') and p.get('linked_project_id') else None
    project_name=(linked['title'] if linked else 'Independent document') if p.get('is_document_space') else p['title']
    project_number=(linked.get('project_number') or linked['id'] if linked else '') if p.get('is_document_space') else p.get('project_number') or state['context'].get('project_reference') or p['id']
    information=content.get('document_info',{})
    project_name=information.get('project_name',project_name);project_number=information.get('project_number',project_number)
    if 'customer' in information:customer_data['name']=information['customer']
    metadata=[['Project',project_name],['Project reference',project_number or 'Not linked'],
       ['Customer',customer_data['name'] or 'Not linked'],['Customer address',customer_data.get('address','')],
       ['Machine / System',state['context'].get('machine') or p.get('machine') or ''],['Document number',doc.get('number') or doc['id']],
       ['Project due date',p.get('due_date') or 'Not set'],
       ['Customer project reference',state['context'].get('customer_project_reference') or ''],
       ['Project type',p.get('kind') or ''],['Base reference',state['context'].get('base_reference') or ''],
       ['Developed reference',state['context'].get('developed_reference') or ''],
       ['Revision',rev.get('label',str(rev['number']))],['Status','APPROVED SNAPSHOT' if rev['status'] in APPROVED else 'DRAFT - NOT APPROVED'],
       ['Prepared by',author],['Reviewed by',reviewed],['Approved by',approved],['Approval date',rev.get('approved_at',rev.get('reviewed_at')) or 'Pending']]
    overrides={'Customer project reference':'customer_project_reference','Project type':'project_type','Base reference':'base_reference','Developed reference':'developed_reference'}
    metadata=[[label,information.get(overrides[label],value) if label in overrides else value] for label,value in metadata]
    if information.get('document_date'):metadata.append(['Document date',information['document_date']])
    structured=kind in {'test','fat','mom'}
    if kind in {'test','fat'}:
        from .report_templates import blocks as report_blocks
        sections=report_blocks(content,kind,detail.get('acceptance'),report_label='Test' if p.get('document_type')=='test_report' else None)
        if layout['data']['show_metadata']:
            sections[:0]=[
                {'key':'summary','title':'1. Document Details','text':'','columns':['Document No.','Revision','Date'],'rows':[[doc.get('number') or doc['id'],rev.get('label',str(rev['number'])),content.get('report_date') or rev['created_at'][:10]]],'svg':''},
                {'key':'summary','title':'2. Project Details','text':'','columns':['Project Name','Project ID','Customer','Customer Reference ID'],'rows':[[project_name,project_number,customer_data['name'],state['context'].get('customer_project_reference') or '']],'svg':''}]
    elif kind=='mom':
        from .mom_template import blocks as mom_blocks
        sections=mom_blocks(content)
    else:sections=blocks(content)
    if content.get('field_files'):
        names={r['id']:r['name'] for r in db.execute('SELECT id,name FROM files WHERE project_id=?',(p['id'],))}
        sections.append({'key':'details','title':'Attachments by field','text':'Files linked to this document revision.','columns':['Document field','Attachment'],
          'rows':[[path.replace('/',' / '),names.get(key,'Attachment unavailable')] for path,ids in content['field_files'].items() for key in ids],'svg':''})
    if controlled:
        history=[list(row) for row in db.execute('SELECT label,status,reason,created_at,approved_at FROM qc_revisions WHERE control_id=? AND number<=? ORDER BY number',(doc['id'],rev['number']))]
    else:
        history=[list(row) for row in db.execute('SELECT number,status,review_comment,created_at,reviewed_at FROM pi_revisions WHERE document_id=? AND number<=? ORDER BY number',(doc['id'],rev['number']))]
    if history:sections.append({'key':'details','title':'Revision history','text':'Recorded revisions only.','columns':['Revision','Status','Reason / review note','Prepared','Approval / review date'],'rows':history,'svg':''})
    signatures=[[label,name,status,at] for label,name,status,at in zip(layout['data']['signature_labels'],
        [author,reviewed,approved],['Prepared','Reviewed' if rev.get('reviewed_at') else 'Pending','Approved' if rev['status'] in APPROVED else 'Pending'],
        [rev.get('created_at',''),rev.get('reviewed_at') or '',rev.get('approved_at',rev.get('reviewed_at')) or ''])]
    if structured and kind=='fat':
        acceptance=detail.get('acceptance') or {}
        signatures[2]=['Customer / Authorized Approver',acceptance.get('representative') or 'Pending acceptance',acceptance.get('status') or 'Pending',acceptance.get('accepted_at') or '']
    sections.append({'key':'signatures','title':'Approval' if kind=='mom' else '9. Sign-Off' if structured else 'Review and approval','text':'Recorded review decisions.' if kind=='mom' else 'Recorded identities and decisions. Signature images are not generated.',
                     'columns':['Stage','Name / Role','Status','Date'],'rows':signatures,'svg':''})
    from backend.core.workhub_signoff import history
    stamps=history(db,rev['id'])
    if stamps:sections.append({'key':'signatures','title':'Review Audit Stamps','text':'Authenticated account attestations for this exact revision.','columns':['Stamp / Account','Decision','Recorded At','Remarks'],
        'rows':[[s['id']+' / '+s['account_name'],s['decision'],s['recorded_at'],s['remarks']] for s in stamps],'svg':''})
    for stamp in stamps:
        evidence=stamp['evidence'];rows=[['Document',d['number'],d['revision'],d['title']] for d in evidence.get('documents',[])]
        rows.extend(['Issue',r['id'],r['status'],r['title']] for r in evidence.get('issues',[]))
        if rows:sections.append({'key':'details','title':'Evidence for Review '+stamp['id'],'text':'Evidence SHA-256 '+stamp['evidence_hash'],
            'columns':['Type','Reference','Revision / Status','Title'],'rows':rows,'svg':''})
    template=TEMPLATE.with_name('mom.html.j2') if kind=='mom' else TEMPLATE
    return {'engine':'engineering-html-v1','engine_hash':hashlib.sha256(template.read_text('utf-8').encode()).hexdigest(),
        'engine_source':template.read_text('utf-8'),'renderer_hash':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'organization':org_data,'customer':customer_data,'layout':layout['data'],
        'title':'Test Report' if kind=='test' and p.get('document_type')=='test_report' else layout['data'].get('title') or branding.KINDS.get(kind,doc.get('title','Engineering Document')),
        'project_name':project_name,'project_number':project_number,'number':doc.get('number',doc['id']),'revision':rev.get('label',str(rev['number'])),
        'revision_id':rev['id'],'source_hash':source_hash(rev),'approved':rev['status'] in APPROVED,
        'metadata':[] if structured else metadata,'sections':sections,'captured_at':rev.get('approved_at',rev.get('reviewed_at')) or rev['created_at'],
        'manifest':{'organization':{'id':org['id'],'version':org['version']},
          'customer':{'id':customer['id'],'version':customer['version']} if customer else None,
          'template':{'id':layout['id'],'version':layout['version']},'assets':assets,
          'source_revision_id':rev['id'],'source_revision_number':rev['number'],'source_hash':source_hash(rev)}}


def blocks(content):
    from backend.core.workhub_intelligence.documents import readable_lines,diagram_svg
    result=[]
    def add(key,title,body='',columns=None,rows=None,svg=''):
        if body or rows or svg:result.append({'key':key,'title':title,'text':str(body or ''),'columns':columns or [],'rows':rows or [],'svg':svg})
    for key,title in [('summary','Summary'),('purpose','Project objective'),('background','Background'),('expected_outcome','Expected outcome'),('scope','Included in scope')]:add('purpose' if key in {'background','expected_outcome'} else key,title,content.get(key))
    mom_fields={'meeting_subject','meeting_mode','meeting_date','location','agenda','participants','discussion_summary','decisions','actions','clarifications','next_meeting_items','engineering_requirements','follow_up','project_name'}
    if any(k in content for k in ('discussion_summary','meeting_subject','actions')):
        add('summary','Meeting information',columns=['Field','Detail'],rows=[[label,content.get(k) or 'Not recorded'] for k,label in [('meeting_subject','Meeting title'),('meeting_date','Meeting date'),('meeting_mode','Meeting mode'),('location','Location / platform')]])
        add('sections','Participants','\n'.join(content.get('participants',[])))
        add('sections','Meeting agenda',content.get('agenda'))
        topics=content.get('discussion_summary',[])
        add('sections','Discussion and decisions',columns=['Topic','Discussion','Decision','Responsible person'],rows=[[r.get('topic') or str(i+1),r.get('text') or '',r.get('decision') or (content.get('decisions',[])[i].get('text','') if i<len(content.get('decisions',[])) else ''),r.get('responsible') or 'Not assigned'] for i,r in enumerate(topics)])
        if not topics:add('sections','Decisions',columns=['Decision'],rows=[[r.get('text','')] for r in content.get('decisions',[])])
        add('sections','Action items',columns=['Action','Assigned to','Target date','Status'],rows=[[r.get('text',''),r.get('responsible') or 'Not assigned',r.get('target_date') or 'Not set',r.get('status') or 'Open'] for r in content.get('actions',[])])
        add('sections','Open clarifications','\n'.join(r.get('question') or r.get('text','') for r in content.get('clarifications',[])))
        add('sections','Next meeting / follow-up',content.get('follow_up') or '\n'.join(r.get('text','') for r in content.get('next_meeting_items',[])))
    rows=[[r.get('id',''),r.get('title',''),r.get('description',''),r.get('trigger',''),r.get('expected_behavior',''),r.get('acceptance_criteria','')]
          for r in content.get('requirements',[])]
    add('requirements','Functional requirements',columns=['ID','Requirement','Description','Trigger','Expected behavior','Acceptance criteria'],rows=rows)
    add('requirements','Requirement classification and sources',columns=['ID','Type / Category','Priority','Source','Status'],rows=[
        [r.get('id',''),r.get('category') or r.get('subsystem',''),r.get('priority','medium'),r.get('source_label') or ', '.join(r.get('source_ids',[])),r.get('status','open')] for r in content.get('requirements',[])])
    criteria=content.get('acceptance_items')
    if criteria:add('sections','Acceptance criteria',columns=['ID','Criterion','Wording confirmed'],rows=[[r['id'],r['text'],'Yes' if r.get('confirmed') else 'No'] for r in criteria])
    else:add('sections','Acceptance criteria',content.get('acceptance_summary'))
    flow=content.get('flowchart') or (content if content.get('nodes') else None)
    if flow:
        if flow.get('workspace',{}).get('schema_version')==2:
            from backend.core.workhub_drawing import svg_pages
            for name,image in svg_pages(flow):add('flowchart','Drawing: '+name,'Engineering interpretation; review against the linked requirements.',svg=image)
        else:add('flowchart','Functional sequence and flowchart','Engineering interpretation; review against the linked requirements.',svg=diagram_svg(flow))
    add('changes','Correction notes',columns=['ID','Change','Requirements'],rows=[[r.get('id',''),r.get('summary',''),', '.join(r.get('requirement_ids',[]))] for r in content.get('changes',[])])
    for correction in content.get('changes',[]):
        add('changes',str(correction.get('id',''))+' — modification and verification',columns=['Field','Recorded detail'],rows=[[key.replace('_',' ').title(),correction[key]] for key in ('existing_behavior','expected_behavior','plc_references','impact','before_evidence','after_evidence','verification') if correction.get(key)])
    add('cases','Test cases and FAT traceability',columns=['ID','Requirements','Objective','Procedure','Expected result','Acceptance criteria','Recorded outcome','Actual / observations'],rows=[
        [r.get('id',''),', '.join(r.get('requirement_ids',[])),r.get('objective',''),r.get('procedure',''),r.get('expected_result',''),r.get('acceptance_criteria',''),
         (r.get('execution') or {}).get('outcome','Recorded native validation' if r.get('native_run_id') else 'NOT TESTED'),
         json.dumps(r['execution'],ensure_ascii=False) if r.get('execution') else 'Linked validation run: '+r['native_run_id'] if r.get('native_run_id') else 'No execution recorded'] for r in content.get('cases',[])])
    add('sections','Document sections',columns=['Section','Content'],rows=[[r.get('heading',''),r.get('text','')] for r in content.get('sections',[])])
    known={'summary','purpose','background','expected_outcome','scope','acceptance_summary','acceptance_items','requirements','flowchart','changes','cases','sections','sources','nodes','edges','field_files','document_info','document_links','diagram_type','workspace','starter_template'}|mom_fields
    other={k:v for k,v in content.items() if k not in known}
    add('details','Supporting document details','\n'.join(readable_lines(other)))
    add('sources','Source references',columns=['Reference','Location','Source excerpt'],rows=[
       [r.get('id',''),json.dumps({k:v for k,v in r.items() if k!='text'},ensure_ascii=False),r.get('text','')] for r in content.get('sources',[])])
    return result


def freeze(db,p,doc,rev,user,controlled=True):
    if rev['status'] not in APPROVED:return
    row=db.execute('SELECT source_hash FROM wh_pdf_snapshots WHERE revision_id=?',(rev['id'],)).fetchone()
    if row:
        if row[0]!=source_hash(rev):raise HTTPException(409,'The approved source differs from its preserved snapshot.')
        return
    original=legacy_pdf(db,p,rev,controlled) if rev.get('_legacy_capture') else None
    if original:
        value={'manifest':{'source_revision_id':rev['id'],'source_hash':source_hash(rev),
            'legacy_original_export':{k:original[k] for k in ['job_id','file_id','sha256']},
            'template':{'id':'legacy','version':rev.get('template_version'),'historical_layout_not_recorded':True}},
            'approved':True,'engine':'legacy-original-pdf'}
    else:value=context(db,p,doc,rev,controlled)
    raw=store.bounded(value,16*1024*1024)
    sha=hashlib.sha256(raw.encode()).hexdigest()
    db.execute('INSERT INTO wh_pdf_snapshots(revision_id,project_id,source_hash,context,context_hash,created_at) VALUES(?,?,?,?,?,?)',
      (rev['id'],p['id'],source_hash(rev),raw,sha,timestamp()))
    if original:
        db.execute('UPDATE wh_pdf_snapshots SET pdf=?,pdf_hash=?,renderer=?,rendered_at=? WHERE revision_id=?',
            (original['pdf'],original['sha256'],'legacy-original-pdf',timestamp(),rev['id']))
    store.audit(db,user,p['id'],'approved_pdf_source_frozen',{'manifest':value['manifest'],'context_hash':sha,
      'legacy_capture':bool(rev.get('_legacy_capture'))},doc['id'] if controlled else None,rev['id'])


def legacy_pdf(db,p,rev,controlled):
    """Adopt existing verified approved exports; never replace their PDF bytes."""
    from backend.core.workhub_intelligence.reliability import digest
    from backend.core.workhub_files import file_record
    expected=rev['content_hash'] if controlled else digest(rev['content'])
    rows=db.execute('''SELECT id,result,input_snapshot FROM pi_jobs WHERE project_id=? AND kind=? AND status='completed'
       AND json_extract(payload,'$.revision_id')=? AND json_extract(payload,'$.format')='pdf'
       ORDER BY created_at,id LIMIT 100''',(p['id'],'q_export' if controlled else 'export',rev['id']))
    for row in rows:
        snapshot=json.loads(row['input_snapshot']).get('export',{})
        if snapshot.get('status') not in APPROVED or snapshot.get('hash')!=expected:continue
        result=json.loads(row['result']);key=result.get('file_id')
        if not key:continue
        file,path=file_record(key,p['id'])
        if file['size']>100*1024*1024:raise HTTPException(409,'The existing approved PDF exceeds the snapshot limit. Preserve and download its original export.')
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if sha!=file['sha256'] or result.get('sha256',sha)!=sha or not raw.startswith(b'%PDF-'):
            raise HTTPException(409,'The existing approved PDF failed integrity verification. Restore the original export before continuing.')
        return {'pdf':raw,'sha256':sha,'job_id':row['id'],'file_id':key}
    return None


def signature(db,p,doc,rev,controlled=True):
    row=db.execute('SELECT context_hash FROM wh_pdf_snapshots WHERE revision_id=? AND project_id=?',(rev['id'],p['id'])).fetchone()
    if row:return row[0]
    return hashlib.sha256(store.bounded(context(db,p,doc,rev,controlled),16*1024*1024).encode()).hexdigest()


def html(value):
    from jinja2 import StrictUndefined
    from jinja2.sandbox import ImmutableSandboxedEnvironment
    env=ImmutableSandboxedEnvironment(autoescape=True,undefined=StrictUndefined)
    env.globals.clear()
    source=value.get('engine_source') or TEMPLATE.read_text('utf-8')
    if value.get('engine_hash') and hashlib.sha256(source.encode()).hexdigest()!=value['engine_hash']:
        raise HTTPException(409,'The preserved template source failed integrity verification.')
    result=env.from_string(source).render(**value)
    if len(result.encode())>20*1024*1024:raise HTTPException(413,'Split this document before PDF export.')
    return result


def render(value):
    markup=html(value)
    # Chromium is optional on existing Windows installations. Both renderers use
    # the same frozen layout and data. No network, scripts or local file URLs.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError: return fallback(value),'reportlab'
    with sync_playwright() as pw:
        executable=os.getenv('USOPP_PDF_CHROMIUM','')
        if not executable and not Path(pw.chromium.executable_path).is_file():return fallback(value),'reportlab'
        browser=pw.chromium.launch(headless=True,executable_path=executable or None,timeout=30000)
        try:
            ctx=browser.new_context(java_script_enabled=False,service_workers='block',offline=True)
            ctx.route('**/*',lambda route:route.abort())
            page=ctx.new_page();page.set_default_timeout(30000);page.set_content(markup,wait_until='load')
            brand=value['organization'];layout=value['layout'];head=escape(layout['header'] or brand['header'] or brand['name'])
            foot=escape(layout['footer'] or brand['footer']);label=escape(value['number']+(' / Project '+value['project_number'] if value.get('project_number') else '')+' / '+value['revision'])
            color=layout['header_color'] or brand['header_color']
            company=escape(brand['name']+' / '+brand['department']+' / '+brand['team'])
            logos=''
            for enabled,item in [(layout['show_company_logo'],brand),(layout['show_customer_logo'],value['customer'])]:
                if enabled and item.get('logo_data'):logos+='<img style="height:18px;max-width:65px;object-fit:contain;background:white;margin-right:8px" src="'+item['logo_data']+'">'
            header='<div style="-webkit-print-color-adjust:exact;print-color-adjust:exact;font-family:Arial;font-size:8px;width:100%;margin:0 12mm;padding:6px 10px;color:white;background:'+color+';display:flex;align-items:center;justify-content:space-between"><span>'+logos+company+'</span><span>'+escape(value['title'])+' / '+escape(value['customer']['name'])+'<br>'+head+'</span></div>'
            footer='<div style="font-size:8px;width:100%;margin:0 12mm;color:#40576a;display:flex;justify-content:space-between"><span>'+foot+' / '+label+'</span>'
            if layout['show_page_numbers']:footer+='<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>'
            footer+='</div>'
            data=page.pdf(format=layout['paper'],landscape=layout['orientation']=='landscape',print_background=True,
                 display_header_footer=True,header_template=header,footer_template=footer,
                 margin={'top':'16mm','bottom':'18mm','left':'14mm','right':'14mm'})
            from pypdf import PdfReader,PdfWriter
            writer=PdfWriter();writer.append(PdfReader(io.BytesIO(data)))
            writer.add_metadata({'/Title':value['title'],'/Author':brand['name'],
              '/Subject':value['number']+' / '+value['revision'],'/Keywords':'WorkHub controlled document'})
            if value.get('manifest'):
                writer.add_attachment('workhub-document-manifest.json',json.dumps(value['manifest'],ensure_ascii=False,indent=2).encode())
            output=io.BytesIO();writer.write(output)
            return output.getvalue(),'chromium'
        finally:browser.close()


def fallback(v):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,TableStyle,Image
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4,letter,landscape
    from .packages import _pdf_font
    from svglib.svglib import svg2rlg
    font=_pdf_font(json.dumps(v,ensure_ascii=False));styles=getSampleStyleSheet()
    for s in styles.byName.values():s.fontName=font
    styles['Normal'].fontSize=8;styles['Normal'].leading=11;styles['Normal'].wordWrap='CJK'
    layout=v['layout'];brand=v['organization'];color=colors.HexColor(layout['header_color'] or brand['header_color'])
    size=A4 if layout['paper']=='A4' else letter
    if layout['orientation']=='landscape':size=landscape(size)
    width=size[0]-72;story=[]
    def para(x):return Paragraph(escape(str(x if x is not None else '')).replace('\n','<br/>'),styles['Normal'])
    def table(columns,rows):
        if not rows:return
        cells=([columns] if columns else [])+rows
        paragraphs=[[para(x) for x in r] for r in cells]
        if columns:
            from copy import copy
            for p in paragraphs[0]:
                p.style=copy(styles['Normal']);p.style.textColor=colors.white
        t=LongTable(paragraphs,colWidths=[width/len(cells[0])]*len(cells[0]),repeatRows=1 if columns else 0,splitInRow=1)
        commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),6)]
        if columns:commands += [('BACKGROUND',(0,0),(-1,0),color)]
        if layout['table_style']=='grid':commands+=[('GRID',(0,0),(-1,-1),.3,colors.HexColor('#d5e0e6'))]
        elif layout['table_style']=='striped':commands+=[('ROWBACKGROUNDS',(0,1 if columns else 0),(-1,-1),[colors.white,colors.HexColor('#f0f6f8')])]
        t.setStyle(TableStyle(commands))
        story.extend([t,Spacer(1,12)])
    logos=[]
    for show,data in [(layout['show_company_logo'],brand.get('logo_data')),(layout['show_customer_logo'],v['customer'].get('logo_data'))]:
        if show and data:
            im=Image(io.BytesIO(base64.b64decode(data.split(',',1)[1])));ratio=min(110/im.imageWidth,45/im.imageHeight);im.drawWidth=im.imageWidth*ratio;im.drawHeight=im.imageHeight*ratio;logos.append(im)
    story.extend(logos);story.extend([Paragraph(escape(v['title']),styles['Title']),para(v['project_name']),Spacer(1,12)])
    if layout['show_metadata'] and v['metadata']:table(['Document field','Value'],v['metadata'])
    for key in layout['sections']:
        for section in v['sections']:
            if section['key']!=key or key=='signatures' and not layout['show_signatures']:continue
            story.append(Paragraph(escape(section['title']),styles['Heading2']))
            if section['text']:story.extend([para(section['text']),Spacer(1,8)])
            table(section['columns'],section['rows'])
            if section['svg']:
                drawing=svg2rlg(io.BytesIO(section['svg'].encode()))
                if drawing:
                    scale=min(width/max(1,drawing.width),(size[1]-150)/max(1,drawing.height),1);drawing.scale(scale,scale);drawing.width*=scale;drawing.height*=scale;story.append(drawing)
    output=io.BytesIO()
    from reportlab.pdfgen.canvas import Canvas
    class Pages(Canvas):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.saved=[]
        def showPage(self):self.saved.append(dict(self.__dict__));self._startPage()
        def save(self):
            total=len(self.saved)
            for state in self.saved:
                self.__dict__.update(state);self.setFont(font,8);self.setFillColor(color)
                self.rect(0,size[1]-34,size[0],34,stroke=0,fill=1);self.setFillColor(colors.white)
                self.drawString(36,size[1]-22,(layout['header'] or brand['header'] or brand['name'])[:120])
                self.setFillColor(color);self.drawString(36,23,(layout['footer'] or brand['footer'])[:80])
                self.drawString(36,12,(v['number']+(' / Project '+v['project_number'] if v.get('project_number') else '')+' / '+v['revision'])[:140])
                if layout['show_page_numbers']:self.drawRightString(size[0]-36,23,f'Page {self._pageNumber} of {total}')
                if not v['approved']:
                    self.saveState();self.setFillAlpha(.12);self.setFont(font,48);self.translate(size[0]/2,size[1]/2);self.rotate(40);self.drawCentredString(0,0,'DRAFT - NOT APPROVED');self.restoreState()
                super().showPage()
            super().save()
    SimpleDocTemplate(output,pagesize=size,leftMargin=36,rightMargin=36,topMargin=50,bottomMargin=45,title=v['title'],author=brand['name']).build(story,canvasmaker=Pages)
    return output.getvalue()


def export(user,pid,doc,rev,controlled=True,library_read=False):
    store.initialize()
    def access(db):
        if not library_read:return store.project(db,pid,user)
        from backend.core.workhub_document_spaces import authorize
        p=hub.item(db,pid);authorize(db,p,user,allow_library=True)
        native=store.native(db,doc) if controlled else pi.document(db,doc['id'],pid)
        if not p.get('library') or native['approved_revision']!=rev['id']:raise HTTPException(403,'Only the shared approved revision is available in the library.')
        return p
    with hub.db(True) as db:
        p=access(db)
        if controlled:
            doc=store.control(db,pid,doc['id']);rev=store.revision(db,doc['id'],rev['id'])
        else:
            doc=pi.document(db,doc['id'],pid);rev=pi.revision(db,rev['id'],doc['id'])
            store.guard_native(db,doc['id'])
        if rev['status'] in APPROVED:
            freeze(db,p,doc,{**rev,'_legacy_capture':True},user,controlled)
            saved=dict(db.execute('SELECT * FROM wh_pdf_snapshots WHERE revision_id=?',(rev['id'],)).fetchone())
            if hashlib.sha256(saved['context'].encode()).hexdigest()!=saved['context_hash']:raise HTTPException(409,'Approved snapshot integrity verification failed.')
            if saved['pdf'] is not None:
                if hashlib.sha256(saved['pdf']).hexdigest()!=saved['pdf_hash']:raise HTTPException(409,'Approved PDF integrity verification failed. Restore the original snapshot.')
                return saved['pdf']
            value=json.loads(saved['context'])
            if value.get('renderer_hash')!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
                raise HTTPException(409,'This approval used an earlier renderer. Restore that renderer to create its first PDF; the approved source remains preserved.')
        else:saved=None;value=context(db,p,doc,rev,controlled)
    data,renderer=render(value)
    if not data.startswith(b'%PDF-'):raise ValueError('The document renderer did not produce a valid PDF.')
    if saved:
        sha=hashlib.sha256(data).hexdigest()
        with hub.db(True) as db:
            access(db)
            db.execute('UPDATE wh_pdf_snapshots SET pdf=?,pdf_hash=?,renderer=?,rendered_at=? WHERE revision_id=? AND pdf IS NULL',(data,sha,renderer,timestamp(),rev['id']))
            row=db.execute('SELECT pdf,pdf_hash FROM wh_pdf_snapshots WHERE revision_id=?',(rev['id'],)).fetchone()
            if hashlib.sha256(row['pdf']).hexdigest()!=row['pdf_hash']:raise HTTPException(409,'Approved PDF integrity verification failed.')
            store.audit(db,user,pid,'approved_pdf_snapshot_stored',{'sha256':row['pdf_hash'],'renderer':renderer,'manifest':value['manifest']},doc['id'] if controlled else None,rev['id'])
            data=row['pdf']
    return data


def preview(db,layout,org_id=None,customer_id=None):
    """Explicit demonstration data only. Never persisted as engineering results."""
    org=branding.record(db,'organization',org_id) if org_id else branding.organization(db,{})
    customer=branding.record(db,'customer',customer_id)['data'].copy() if customer_id else {'name':'Example customer (sample)','address':'Sample address'}
    brand={**org['data'],'logo_data':''};customer={**customer,'logo_data':''}
    for value in [brand,customer]:
        item=branding.asset(db,value.get('logo_id'))
        if item:value['logo_data']='data:image/png;base64,'+base64.b64encode(item['data']).decode()
    return {'organization':brand,'customer':customer,'layout':layout,'title':layout['title'] or branding.KINDS[layout['document_kind']],
        'project_name':'Sample engineering project - demonstration only','number':'PTPL-ES-PLC-'+layout['document_kind'].upper()+'-SAMPLE','revision':'R00',
        'approved':False,'metadata':[['Project','Sample project'],['Customer',customer['name']],['Status','SAMPLE / DRAFT - NOT APPROVED'],['Prepared by','Sample engineer'],['Reviewed by','Pending'],['Approved by','Pending']],
        'sections':blocks({'purpose':'Demonstrate the selected document layout. No project result or approval is implied.',
            'requirements':[{'id':'FR-001','title':'Sample requirement','description':'Replace with reviewed project requirements.','acceptance_criteria':'Verify actual project behavior.'}],
            'cases':[{'id':'FAT-001','objective':'Sample test','expected_result':'Actual execution must be recorded.'}],
            'flowchart':{'nodes':[{'id':'start','position':{'x':0,'y':0},'data':{'label':'Sample input','kind':'start'}},{'id':'check','position':{'x':300,'y':0},'data':{'label':'Engineering review','kind':'process'}}],
                         'edges':[{'id':'e1','source':'start','target':'check'}]}})+[
            {'key':'signatures','title':'Review and approval','text':'Sample only - no signatures or decisions recorded.','columns':['Stage','Name / Role','Status','Date'],
             'rows':[[label,'Sample / pending','Pending',''] for label in layout['signature_labels']],'svg':''}]}
