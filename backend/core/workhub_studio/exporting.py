"""Format-faithful Studio exports and immutable approved export snapshots."""
from pathlib import Path
import hashlib,io,json,threading
from fastapi import HTTPException
from . import store,bindings,render_common,html_renderer
from .store import hub,quality,pi,timestamp

PDF_SLOTS=threading.BoundedSemaphore(2)
PAGINATOR=Path(__file__).resolve().parents[3]/'public/studio/paged.polyfill.min.js'

def export_schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS ds_export_context(revision_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_hash TEXT NOT NULL,context TEXT NOT NULL,context_hash TEXT NOT NULL,created_at TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS ds_exports(revision_id TEXT NOT NULL,format TEXT NOT NULL,data BLOB NOT NULL,sha256 TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(revision_id,format))')

def freeze(db,p,doc,rev,user,control=None):
    """Called within the existing approval transaction; never renders in it."""
    native=pi.document(db,doc['document_id'],p['id']) if doc.get('document_id') else doc
    native_rev=pi.revision(db,rev['id'],native['id'])
    if not native_rev['content'].get('studio'):return
    export_schema(db)
    if db.execute('SELECT 1 FROM ds_export_context WHERE revision_id=?',(rev['id'],)).fetchone():return
    ctrl=control or (doc if doc.get('stage') else None)
    full=quality.detail(db,ctrl,quality.revision(db,ctrl['id'],rev['id'])) if ctrl else native_rev
    value=render_common.context(db,p,native,full,ctrl);raw=quality.bounded(value,24*1024*1024)
    db.execute('INSERT INTO ds_export_context VALUES(?,?,?,?,?,?)',(rev['id'],p['id'],bindings.digest(native_rev['content']),raw,hashlib.sha256(raw.encode()).hexdigest(),timestamp()))
    if store.exists(db):store.audit(db,user,p['id'],native['id'],rev['id'],'studio_export_source_frozen',{'source_hash':value['source_hash'],'image_hashes':value['manifest']['image_hashes']})

def render_pdf(value):
    if not PDF_SLOTS.acquire(timeout=2):raise HTTPException(503,'The local PDF worker is busy. Retry after the current documents finish.')
    try:
        from playwright.sync_api import sync_playwright
        if not PAGINATOR.is_file():raise HTTPException(503,'The bundled document pagination worker is missing. Restore public/studio before exporting.')
        markup=html_renderer.html(value,embed_script=PAGINATOR.read_text(encoding='utf-8'))
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,timeout=30000)
            try:
                ctx=browser.new_context(service_workers='block',offline=True)
                ctx.route('**/*',lambda route:route.abort())
                page=ctx.new_page();page.set_default_timeout(60000);page.set_content(markup,wait_until='load')
                page.wait_for_function("document.documentElement.dataset.studioReady==='true'||!!document.documentElement.dataset.studioError")
                error=page.evaluate('document.documentElement.dataset.studioError||null')
                if error:raise HTTPException(422,'The page layout could not be paginated: '+str(error)[:300])
                count=page.evaluate('window.__studioPages')
                if not count or count>300:raise HTTPException(413,'Split this document into up to 300 pages before export.')
                # Print each already-paginated sheet at its own physical size.
                # This also supports mixed portrait/landscape/A3 sections.
                from pypdf import PdfReader,PdfWriter
                combined=PdfWriter();style=page.add_style_tag(content='/* Studio print selection */')
                for index in range(count):
                    geometry=page.locator('.pagedjs_page').nth(index).locator('.pagedjs_sheet').evaluate('(e)=>({width:e.getBoundingClientRect().width/96*25.4,height:e.getBoundingClientRect().height/96*25.4})')
                    w=round(geometry['width'],2);h=round(geometry['height'],2)
                    page.evaluate('(index)=>document.querySelectorAll(".pagedjs_page").forEach((p,i)=>p.classList.toggle("ds-print-selected",i===index))',index)
                    style.evaluate('(e,css)=>e.textContent=css',f'@page{{size:{w}mm {h}mm;margin:0}}@media print{{html,body{{margin:0!important;padding:0!important;width:{w}mm!important;min-height:0!important;height:auto!important}}.ds-output{{padding:0!important}}.pagedjs_pages{{display:block!important}}.pagedjs_page{{display:none!important;break-before:auto!important;break-after:auto!important;page:auto!important}}.pagedjs_page.ds-print-selected{{display:block!important;margin:0!important}}.ds-print-selected [data-section-id]{{page:auto!important}}}}')
                    raw=page.pdf(width=str(w)+'mm',height=str(h)+'mm',prefer_css_page_size=True,print_background=True,margin={'top':'0','bottom':'0','left':'0','right':'0'})
                    part=PdfReader(io.BytesIO(raw))
                    if len(part.pages)!=1:raise HTTPException(422,'A rendered page exceeds its chosen paper size. Adjust the layout before export.')
                    combined.append(part)
                merged=io.BytesIO();combined.write(merged);data=merged.getvalue()
            finally:browser.close()
        from pypdf import PdfReader,PdfWriter
        reader=PdfReader(io.BytesIO(data));writer=PdfWriter();writer.append(reader)
        writer.add_metadata({'/Title':value['fields']['document_title'],'/Author':value['fields']['company'],'/Subject':value['fields']['document_number']+' / '+value['fields']['revision'],'/Keywords':'WorkHub Document Studio'})
        writer.add_attachment('workhub-document-manifest.json',json.dumps(value['manifest'],ensure_ascii=False,indent=2).encode())
        output=io.BytesIO();writer.write(output);return output.getvalue()
    except ImportError:raise HTTPException(503,'Install the existing local PDF worker requirements and Chromium before exporting.') from None
    finally:PDF_SLOTS.release()

def preview(user,pid,did,payload=None):
    store.initialize();payload=payload or {}
    with hub.db() as db:
        p,doc,rev,control=store.document(db,user,pid,did,payload.get('revision_id'))
        from .service import can_edit
        editable=payload.get('editable',True) is True and can_edit(db,user,p,doc,rev,control)
        if payload.get('content') is not None:
            if not editable:raise HTTPException(403,'Preview saved content for this protected revision.')
            content=payload['content']
            if payload.get('layout'):content={**content,'studio':payload['layout']}
            content=bindings.synchronize(content)
            # Only recorded test results from an unchanged saved specification
            # can appear as native actual results in an unsaved preview.
            saved={r['id']:r for r in rev['content'].get('cases',[])}
            for case in content.get('cases',[]):
                old=saved.get(case.get('id'));a={k:v for k,v in case.items() if k!='execution'};b={k:v for k,v in (old or {}).items() if k!='execution'}
                case['execution']=old.get('execution') if old and a==b else None
            rev={**rev,'content':content}
        frozen=db.execute('SELECT context FROM ds_export_context WHERE revision_id=?',(rev['id'],)).fetchone() if rev['status'] in store.APPROVED else None
        value=json.loads(frozen['context']) if frozen else render_common.context(db,p,doc,rev,control);locks=store.locks(db,rev['id'])
    return html_renderer.html(value,editable,locks)

def export(user,pid,did,rid=None,format='pdf'):
    from backend.core.workhub_document_filename import filename
    store.initialize()
    if format not in {'pdf','docx'}:raise HTTPException(400,'Choose PDF or DOCX.')
    with hub.db(True) as db:
        p,doc,rev,control=store.document(db,user,pid,did,rid)
        if format=='pdf' and rev['status'] in store.APPROVED and not rev['content'].get('studio'):
            legacy=(p,doc,rev,control);value=None;approved=False
        else:
            legacy=None;approved=rev['status'] in store.APPROVED
            if approved and rev['content'].get('studio'):
                freeze(db,p,control or doc,rev,user,control)
                row=db.execute('SELECT * FROM ds_export_context WHERE revision_id=?',(rev['id'],)).fetchone()
                if not row or hashlib.sha256(row['context'].encode()).hexdigest()!=row['context_hash']:raise HTTPException(409,'The approved Studio layout failed integrity verification.')
                if row['source_hash']!=bindings.digest(pi.revision(db,rev['id'],did)['content']):raise HTTPException(409,'The approved document content failed source verification.')
                value=json.loads(row['context'])
            else:value=render_common.context(db,p,doc,rev,control)
            old=db.execute('SELECT * FROM ds_exports WHERE revision_id=? AND format=?',(rev['id'],format)).fetchone() if approved else None
            if old:
                if hashlib.sha256(old['data']).hexdigest()!=old['sha256']:raise HTTPException(409,'The approved export failed integrity verification.')
                return old['data'],'application/pdf' if format=='pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename(control or doc,rev,format)
    if legacy:
        from backend.core.workhub_quality.pdf_templates import export as legacy_export
        p,doc,rev,control=legacy;data=legacy_export(user,pid,control or doc,rev,controlled=bool(control));name=filename(control or doc,rev,'pdf')
        return data,'application/pdf',name
    if format=='pdf':data=render_pdf(value)
    else:
        from .docx_renderer import render
        data=render(value)
    if approved and rev['content'].get('studio'):
        with hub.db(True) as db:
            store.document(db,user,pid,did,rev['id'])
            db.execute('INSERT OR IGNORE INTO ds_exports VALUES(?,?,?,?,?)',(rev['id'],format,data,hashlib.sha256(data).hexdigest(),timestamp()))
            row=db.execute('SELECT * FROM ds_exports WHERE revision_id=? AND format=?',(rev['id'],format)).fetchone()
            if hashlib.sha256(row['data']).hexdigest()!=row['sha256']:raise HTTPException(409,'The preserved export failed integrity verification.')
            data=row['data']
            store.audit(db,user,pid,did,rev['id'],'approved_studio_export_stored',{'format':format,'sha256':row['sha256']})
    return data,'application/pdf' if format=='pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename(control or doc,rev,format)
