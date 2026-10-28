"""Real page-editor checks; every fixture lives in an isolated data root."""
import os,sys,tempfile,json,socket,threading,time,importlib,traceback
from pathlib import Path
from contextlib import asynccontextmanager
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.update(USOPP_DATA_ROOT=tempfile.mkdtemp(prefix='studio-browser-'),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
OUT=ROOT/'.build/document-studio';OUT.mkdir(parents=True,exist_ok=True)

def main():
    import uvicorn
    from fastapi.staticfiles import StaticFiles
    from playwright.sync_api import sync_playwright,expect
    from backend.core import accounts
    from backend.core.workhub import store as hub
    from backend.core.workhub_quality import authoring
    from backend.core.workhub_studio import service
    module=importlib.import_module('backend.app');app=module.app;module.DIST=OUT/'candidate'
    from backend.api import system
    from backend.core.build_info import frontend_build_info
    system.frontend_build_info=lambda distribution,expected:frontend_build_info(module.DIST,expected)
    for route in app.routes:
        if getattr(route,'name','')=='assets':route.app=StaticFiles(directory=module.DIST/'assets')
    admin=next(u for u in accounts.store.list_users() if u['username']=='Admin')
    reviewer=accounts.store.register('studio_browser_reviewer','Fixture.Studio.2026','Reviewer','Fictional')
    p=hub.create(admin,{'title':'Isolated Studio browser delivery','owner_id':admin['id'],'quality_id':reviewer['id'],'release_id':reviewer['id']})
    made=authoring.create(admin,p['id'],{'stage':'frd'})
    with hub.db() as db:did=db.execute('SELECT document_id FROM qc_documents WHERE id=?',(made['control_id'],)).fetchone()[0]
    m=service.get(admin,p['id'],did);c=m['revision']['content'];c.update(purpose='Verify the existing motor trip alarm.',requirements=[{'id':'FR-001','title':'Motor trip alarm','description':'Show the motor trip alarm.','expected_behavior':'Alarm is displayed.','acceptance_criteria':'Verify alarm indication.','source_ids':[],'mandatory':True,'change':'new'}])
    service.save(admin,p['id'],did,{'revision_id':m['revision']['id'],'version':m['revision']['version'],'etag':m['revision']['etag'],'content':c,'layout':m['layout']})
    from backend.core.workhub_intelligence import store as pi
    with hub.db(True) as db:
        mom,momrev=pi.create_document(db,admin,p['id'],'mom','Isolated meeting',{'meeting_subject':'Motor alarm meeting','agenda':'Confirm reset behavior.','discussion_summary':[{'id':'discussion','topic':'Reset','text':'Review reset conditions.','source_ids':[]}],'sources':[]})
    @asynccontextmanager
    async def lifespan(app):yield
    app.router.lifespan_context=lifespan
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    base=f'http://127.0.0.1:{port}';checks=[];errors=[];http_errors=[]
    def check(name,value,**extra):
        checks.append({'check':name,'passed':bool(value),**extra});print(name+': '+str(bool(value)),flush=True)
        if not value:raise AssertionError(name)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True);ctx=browser.new_context(viewport={'width':1440,'height':1000})
            token=accounts.store.new_session(admin['id']);ctx.add_cookies([{'name':accounts.COOKIE,'value':token,'url':base,'httpOnly':True,'sameSite':'Lax'}])
            page=ctx.new_page();page.set_default_timeout(30000);page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('response',lambda r:http_errors.append({'url':r.url,'status':r.status}) if r.status>=400 and '/studio/' in r.url else None)
            try:
                page.goto(base+'/?workhubProject='+p['id']+'&workhubSection=meetings',wait_until='domcontentloaded')
                studio=page.locator('.ds-studio:visible').first;studio.wait_for(timeout=60000)
                frame=studio.frame_locator('iframe');frame.locator('html[data-studio-ready=true]').wait_for(timeout=60000)
                check('Controlled FRD opens as a paginated editable document',frame.locator('.pagedjs_page').count()>0)
                text=frame.locator('[data-block-id="native-purpose"] [contenteditable=true]').first
                text.fill('Verify motor trip alarm and reset permission.');text.press('Tab')
                studio.get_by_role('button',name='Save draft',exact=False).click()
                page.wait_for_timeout(1400)
                actual=service.get(admin,p['id'],did)
                check('Page text saves to the native engineering field',actual['revision']['content']['purpose']=='Verify motor trip alarm and reset permission.')
                studio.get_by_role('button',name='Text box / panel',exact=True).click()
                frame.locator('[data-block-type=panel]').last.wait_for(timeout=60000)
                panel=frame.locator('[data-block-type=panel]').last;panel.click()
                studio.get_by_label('Element height',exact=True).fill('24');studio.get_by_label('Element height',exact=True).press('Tab')
                studio.get_by_role('button',name='Save draft',exact=False).click();page.wait_for_timeout(1400)
                actual=service.get(admin,p['id'],did)
                check('Inserted text box size persists',any(b['type']=='panel' and b['style']['height']==24 for b in actual['layout']['blocks']))
                studio.get_by_role('button',name='Header',exact=True).click()
                dialog=page.get_by_role('dialog',name='Header Designer');dialog.get_by_role('checkbox',name='Different first page',exact=True).check()
                dialog.get_by_role('button',name='Text',exact=True).click();dialog.get_by_label('Band text',exact=True).fill('Customer engineering document')
                dialog.get_by_role('button',name='Apply header layout',exact=True).click()
                studio.get_by_role('button',name='Save draft',exact=False).click();page.wait_for_timeout(1500)
                actual=service.get(admin,p['id'],did)
                check('Visual header designer saves first-page settings and text',actual['layout']['header']['different_first'] and any(i.get('text')=='Customer engineering document' for i in actual['layout']['header']['variants']['default']['items']))
                studio.get_by_role('button',name='Table',exact=True).click()
                generic=frame.locator('[data-block-type=table]:has(table[data-native-binding=""])').last;generic.wait_for()
                cell=generic.locator('td .ds-text[contenteditable=true]').first;cell.fill('Editable checklist item');cell.press('Tab')
                studio.get_by_role('button',name='Save draft',exact=False).click();page.wait_for_timeout(1400)
                check('Custom table cell remains editable and saves',any(b['type']=='table' and any('Editable checklist item' in ''.join(r['text'] for r in c['runs']) for c in b['data']['cells']) for b in service.get(admin,p['id'],did)['layout']['blocks']))
                cell=generic.locator('td .ds-text[contenteditable=true]').first;cell.click()
                links=studio.locator('.ds-field-links');links.locator('summary').click()
                links.locator('input[type=file]').set_input_files({'name':'field-note.txt','mimeType':'text/plain','buffer':b'Original attachment for the selected table cell.'})
                links.get_by_role('link',name='field-note.txt',exact=True).wait_for()
                studio.get_by_role('button',name='Save draft',exact=False).click();page.wait_for_timeout(1400)
                check('A file attaches to its selected document field',any(key.startswith('element/') and '/cell/' in key and ids for key,ids in service.get(admin,p['id'],did)['revision']['content'].get('field_files',{}).items()))
                studio.get_by_role('button',name='Review',exact=True).click();studio.get_by_role('button',name='Document quality check',exact=True).click()
                dialog=page.get_by_role('dialog',name='Document Quality Check');dialog.wait_for();check('Quality check opens with native document checks',bool(dialog.inner_text()))
                dialog.get_by_role('button',name='Close Document Quality Check').click()
                for width in (1000,768,390):
                    page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(700)
                    check('Editor fits viewport '+str(width),page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                page.set_viewport_size({'width':1440,'height':1000});studio.locator('.ds-heading').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'studio-browser.png'),full_page=True)
                for fmt in ('pdf','docx'):
                    response=page.request.get(base+'/api/workhub/projects/'+p['id']+'/studio/documents/'+did+'/export/'+fmt,timeout=120000)
                    check('Authenticated '+fmt.upper()+' export',response.status==200 and response.body().startswith(b'%PDF' if fmt=='pdf' else b'PK'),status=response.status)
                page.get_by_role('button',name='Review & Confirm',exact=True).click()
                page.get_by_role('button',name='Submit for approval',exact=False).wait_for()
                check('Native confirmation workflow remains available',bool(service.get(admin,p['id'],did)['revision']['confirmed_by']))
                page.get_by_role('button',name='Submit for approval',exact=False).click();page.wait_for_timeout(1400)
                check('Studio submission protects the reviewed revision',service.get(admin,p['id'],did)['revision']['status']=='in_review')
                readonly=studio.frame_locator('iframe');readonly.locator('html[data-studio-ready=true]').wait_for(timeout=60000)
                check('Submitted documents retain a readable protected page canvas',readonly.locator('[contenteditable=true]').count()==0 and readonly.locator('.pagedjs_page').count()>0)
                page.goto(base+'/?workhubProject='+p['id']+'&workhubSection=meetings&piReview='+mom['id'],wait_until='domcontentloaded')
                page.get_by_role('button',name='Meetings & MOM',exact=True).click()
                native=page.locator('.pi-document-draft .ds-studio:visible');native.wait_for();nf=native.frame_locator('iframe');nf.locator('html[data-studio-ready=true]').wait_for(timeout=60000)
                agenda=nf.locator('[data-block-id=native-agenda] [contenteditable=true]').first;agenda.fill('Updated meeting agenda from the document canvas.');agenda.press('Tab')
                page.get_by_role('dialog',name='Isolated meeting',exact=True).get_by_role('button',name='Close Isolated meeting',exact=True).click();page.get_by_role('dialog',name='Isolated meeting',exact=True).wait_for(state='hidden');page.get_by_role('button',name='All projects',exact=True).click();page.wait_for_timeout(1400)
                with hub.db() as db:
                    saved=pi.document(db,mom['id'],p['id']);revision=pi.revision(db,saved['current_revision'],mom['id'])
                check('Leaving native MOM flushes its draft through existing navigation',revision['content']['agenda']=='Updated meeting agenda from the document canvas.')
            except Exception as exc:
                checks.append({'check':'Browser interaction','passed':False,'error':str(exc),'traceback':traceback.format_exc(),'body':page.locator('body').inner_text()[-8000:]})
                page.screenshot(path=str(OUT/'studio-browser-failure.png'),full_page=True)
            finally:
                check_errors={'check':'No uncaught frontend exceptions','passed':not errors,'errors':errors,'http_errors':http_errors};checks.append(check_errors)
                (OUT/'browser-results.json').write_text(json.dumps(checks,indent=2),encoding='utf-8');print(json.dumps(checks,indent=2),flush=True);browser.close()
    finally:server.should_exit=True;thread.join(10)
    return 0 if all(c['passed'] for c in checks) else 1

if __name__=='__main__':raise SystemExit(main())
