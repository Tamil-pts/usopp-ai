"""Isolated browser flow for the read-derived Write ST generator."""
from pathlib import Path
import os
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
SANDBOX=Path(tempfile.mkdtemp(prefix='usopp-read-st-browser-'))
os.environ.update(USOPP_DATA_ROOT=str(SANDBOX),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')


def main():
    from contextlib import asynccontextmanager
    import importlib,json,socket,threading,time
    import uvicorn
    from fastapi.staticfiles import StaticFiles
    from playwright.sync_api import sync_playwright
    module=importlib.import_module('backend.app');app=module.app
    out=ROOT/'.build/spinconnect-read-derived';module.DIST=out/'candidate'
    from backend.api import system
    from backend.core.build_info import frontend_build_info
    system.frontend_build_info=lambda distribution,expected:frontend_build_info(module.DIST,expected)
    for route in app.routes:
        if getattr(route,'name','')=='assets':route.app=StaticFiles(directory=module.DIST/'assets')
    from backend.core import accounts
    user=accounts.store.register('write_flow_reviewer','Isolated.Write.Flow.2026!','Reviewer','Fixture',role='admin')
    token=accounts.store.new_session(user['id'])
    @asynccontextmanager
    async def lifespan(app):yield
    app.router.lifespan_context=lifespan
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    checks=[];errors=[]
    def check(name,passed):
        checks.append({'check':name,'passed':bool(passed)})
        assert passed,name
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
            context.add_cookies([{'name':accounts.COOKIE,'value':token,'url':f'http://127.0.0.1:{port}'}])
            page=context.new_page();page.set_default_timeout(30000);page.on('pageerror',lambda e:errors.append(str(e)))
            try:
                page.goto(f'http://127.0.0.1:{port}',wait_until='domcontentloaded')
                health=page.request.get(f'http://127.0.0.1:{port}/api/health').json()
                check('Candidate UI and API match with valid build integrity',health['uiVersion']==health['apiVersion']=='4.94.1' and health['frontendBuild']['integrity'])
                page.get_by_role('button',name='ByteMap',exact=True).click()
                page.get_by_label('Project path',exact=True).fill(str(ROOT.parent/'project 5'))
                page.locator('.selectionProjectCard').get_by_role('button',name='Use path',exact=True).click()
                page.get_by_role('tab',name='Write ST',exact=True).click()
                panel=page.locator('.writeST')
                panel.get_by_role('button',name='Generate ST',exact=True).click()
                page.get_by_label('Groups from mms_nw_r',exact=True).wait_for()
                check('Catalog lists all 32 outgoing Project 5 groups',panel.locator('.writeSTGroups>label').count()==32)
                check('The generator explains read source and existing setting policies','mms_nw_r group codes and packet bytes' in panel.inner_text())
                check('Read-derived GC130 payload is 115 bytes','115 bytes' in panel.locator('.writeSTMapping').inner_text())
                group20=panel.locator('.writeSTGroups>label').filter(has=page.get_by_text('GC 20',exact=True))
                check('Unmapped monitoring group is shown without making it writable',group20.locator('input').is_disabled())
                group20.get_by_role('button',name='Inspect',exact=False).click()
                check('Inspect explains the missing write policy','No setting-write policy exists' in panel.locator('.writeSTMapping').inner_text())
                group130=panel.locator('.writeSTGroups>label').filter(has=page.get_by_text('GC 130',exact=True))
                group130.get_by_role('button',name='Inspect',exact=False).click()
                for width in (960,720,390):
                    page.set_viewport_size({'width':width,'height':1000})
                    check('Write ST panel fits width '+str(width),panel.evaluate('(e)=>e.getBoundingClientRect().right<=window.innerWidth+1'))
                page.set_viewport_size({'width':1440,'height':1000})
                panel.locator('.writeSTGenerate input').check()
                panel.get_by_role('button',name='Generate ST',exact=True).click()
                code=panel.locator('.writeSTCode');code.wait_for()
                text=code.input_value()
                check('Generated source declares its mms_nw_r layout basis','Packet layout source: mms_nw_r' in text)
                check('Motor pulley retains received-value syntax and limit',all(v in text for v in ['TS_Teeth_in_MOT_Pulley_VD5100 := nw_temp_UINT_received_value;','nw_i := nw_i + 2;','nw_j := nw_j + 1;','nw_temp_UINT_received_value <= 310','nw_error_code[nw_j] := 1;']))
                with page.expect_download() as download:
                    panel.get_by_role('button',name='Download complete ZIP',exact=True).click()
                check('Complete ST ZIP can be downloaded',download.value.suggested_filename=='SpinConnect_Write_ST.zip')
                panel.locator('.writeSTFileTabs').get_by_role('button',name='write_mapping.json',exact=True).click()
                mapping=json.loads(code.input_value())
                check('Downloaded mapping uses read-derived request and response bytes',mapping['layoutBasis']=='mms_nw_r' and all(v['payloadBytes']==v['readPayloadBytes'] for g in mapping['dataInspect']['groups'] for v in g['variants']))
                page.screenshot(path=str(out/'read-derived-write-st.png'),full_page=True)
                page.get_by_label('Project path',exact=True).fill(str(ROOT.parent/'project 2'))
                page.locator('.selectionProjectCard').get_by_role('button',name='Use path',exact=True).click()
                panel.get_by_role('button',name='Generate ST',exact=True).click()
                page.get_by_label('Groups from mms_nw_r',exact=True).wait_for()
                group140=panel.locator('.writeSTGroups>label').filter(has=page.get_by_text('GC 140',exact=True))
                group140.get_by_role('button',name='Inspect',exact=False).click()
                check('Conflicting read/write widths block the affected group',group140.locator('input').is_disabled() and 'ED_Break_Draft' in panel.locator('.writeSTMapping').inner_text())
                page.screenshot(path=str(out/'read-write-width-finding.png'),full_page=True)
                check('No browser runtime errors',not errors)
            finally:
                browser.close()
    finally:
        accounts.store.logout(token);server.should_exit=True;thread.join(5)
        (out/'browser-results.json').write_text(json.dumps({'checks':checks,'errors':errors},indent=2),encoding='utf8')
    print(json.dumps({'passed':sum(c['passed'] for c in checks),'total':len(checks)}))


if __name__=='__main__':main()
