"""Browser acceptance for work-derived Competency Hub and optional project links."""
import os,sys,tempfile,json,socket,threading,time,importlib,traceback
from pathlib import Path
from contextlib import asynccontextmanager
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.update(USOPP_DATA_ROOT=tempfile.mkdtemp(prefix='work-outcomes-browser-'),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
OUT=ROOT/'.build/document-studio';OUT.mkdir(exist_ok=True)

def main():
    import uvicorn
    from fastapi.staticfiles import StaticFiles
    from playwright.sync_api import sync_playwright,expect
    from backend.core import accounts
    from backend.core.workhub import store as hub
    from backend.core.workhub_praxis import outcomes,insights
    module=importlib.import_module('backend.app');app=module.app;module.DIST=OUT/'candidate'
    from backend.api import system
    from backend.core.build_info import frontend_build_info
    system.frontend_build_info=lambda distribution,expected:frontend_build_info(module.DIST,expected)
    for route in app.routes:
        if getattr(route,'name','')=='assets':route.app=StaticFiles(directory=module.DIST/'assets')
        if getattr(route,'name','')=='nami':route.app=StaticFiles(directory=OUT/'nami',html=True)
    admin=next(u for u in accounts.store.list_users() if u['username']=='Admin')
    employee=accounts.store.register('Tamil_fixture','Fixture.Work.2026','Engineer','Fictional')
    p=hub.create(admin,{'title':'Fictional work tracking','owner_id':employee['id'],'quality_id':admin['id'],'approver_id':admin['id'],'release_id':admin['id']})
    task=hub.create(admin,{'title':'Fictional alarm correction','owner_id':employee['id'],'quality_id':admin['id'],'approver_id':admin['id'],'release_id':admin['id'],'due_date':'2026-10-31'},p['id'])
    for action in ('start','complete_development','submit_quality'):
        with hub.db() as db:version=hub.item(db,task['id'])['version']
        hub.transition(employee,task['id'],{'version':version,'action':action})
    @asynccontextmanager
    async def lifespan(app):yield
    app.router.lifespan_context=lifespan
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];base=f'http://127.0.0.1:{port}'
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    checks=[];errors=[]
    def check(name,value,**details):
        checks.append({'check':name,'passed':bool(value),**details});print(name+': '+str(bool(value)),flush=True)
        if not value:raise AssertionError(name)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch();ctx=browser.new_context(viewport={'width':1440,'height':1000})
            ctx.add_cookies([{'name':accounts.COOKIE,'value':accounts.store.new_session(admin['id']),'url':base,'httpOnly':True,'sameSite':'Lax'}])
            page=ctx.new_page();page.set_default_timeout(30000);page.on('pageerror',lambda e:errors.append(str(e)))
            try:
                page.goto(base+'/?workhubProject='+p['id']+'&workhubItem='+task['id'],wait_until='domcontentloaded')
                action=page.get_by_role('button',name='Quality passed / Send for release approval',exact=True).first;action.wait_for(timeout=60000);action.click()
                dialog=page.get_by_role('dialog',name='Quality passed / Send for release approval',exact=True)
                dialog.get_by_label('Corrections needed',exact=True).select_option('minor');dialog.get_by_label('Problem solving',exact=True).select_option('independent');dialog.get_by_label('Response and follow-through',exact=True).select_option('prompt')
                dialog.get_by_text('Corrections, troubleshooting and sharing (optional)',exact=True).click();dialog.get_by_label('Errors corrected',exact=True).fill('3');dialog.get_by_label('Troubleshooting cases solved',exact=True).fill('2');dialog.get_by_label('Additional solutions shared (outside TechShare)',exact=True).fill('2');dialog.get_by_label('Work feedback',exact=True).fill('Solved the reset issue and shared the correction.')
                dialog.get_by_role('button',name='Quality passed / Send for release approval',exact=True).click();dialog.wait_for(state='hidden')
                result=outcomes.profile(admin,employee['id']);check('Approval feedback immediately produces work-based indices',result['performance_index'] is not None and result['competency_index'] is not None and result['work_counts']['errors_corrected']==3)
                cfg=insights.layout(admin);extra=[{**cfg['widgets'][0],'id':'display-'+name,'display':name,'title':'Display '+name} for name in ('line','area','pie','donut','radar','gauge','heatmap','table','trend')]
                insights.save(admin,{'version':cfg['version'],'widgets':cfg['widgets']+extra})
                nav=page.get_by_role('navigation',name='WorkHub main sections');nav.get_by_role('button',name='Competency Hub',exact=True).click();page.get_by_role('heading',name='Competency Hub',exact=True).wait_for()
                page.get_by_label('Employee',exact=True).select_option(str(employee['id']));page.locator('.ch-insight-grid').wait_for();page.wait_for_timeout(1200)
                text=page.locator('.px-workspace').inner_text();check('No separate assessment or Not Assessed judgment is shown','New assessment' not in text and 'Not Assessed' not in text and 'No separate assessment is required.' in text)
                check('Expanded chart displays render from actual work',page.locator('.px-chart canvas').count()>=8)
                page.get_by_role('button',name='Customize insights',exact=True).click();custom=page.get_by_role('dialog',name='Customize insights');options=custom.get_by_label('Insight display').first.locator('option').evaluate_all('(rows)=>rows.map(r=>r.value)')
                check('All common insight displays are selectable',set(('card','bar','line','area','pie','donut','radar','gauge','heatmap','table','trend'))<=set(options));custom.get_by_role('button',name='Cancel',exact=True).click()
                first=page.locator('.ch-insight').first;first.locator('.ch-insight-heading').click();check('Clicking an insight expands work and feedback details','Calculation inputs' in first.inner_text() and 'Approval and completion feedback' in first.inner_text())
                for tab in ('Team Capability','Competency Matrix','Reports & Insights'):
                    page.get_by_role('navigation',name='Competency Hub sections').get_by_role('button',name=tab,exact=True).click();page.wait_for_timeout(800)
                    check(tab+' opens without formal assessment',page.get_by_role('heading',name='Competency Hub',exact=True).is_visible())
                page.get_by_text('Expand detailed report',exact=True).click();check('Detailed report includes project and task inputs','Calculation inputs' in page.locator('.ch-report-preview').inner_text())
                for kind in ('PDF','Excel'):
                    response=page.request.get(base+page.get_by_role('link',name='Export '+kind,exact=True).get_attribute('href'),timeout=60000)
                    check('Work-based '+kind+' export',response.status==200 and response.body().startswith(b'%PDF' if kind=='PDF' else b'PK'))
                for width in (1000,768,390):
                    page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(500);check('Work insights fit '+str(width),page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                page.set_viewport_size({'width':1440,'height':1000});page.get_by_role('navigation',name='Competency Hub sections').get_by_role('button',name='My Competency',exact=True).click();page.locator('.px-workspace>header').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'work-outcomes-browser.png'),full_page=True)
                page.get_by_role('button',name='ByteMap',exact=True).click();band=page.get_by_role('region',name='WorkHub project attribution');band.wait_for()
                check('Project recording is checked by default without requiring a project',band.get_by_role('checkbox',name='Record results for this project').is_checked() and band.locator('select').input_value()=='')
                check('No selected project explicitly skips linking','project recording is skipped' in band.inner_text())
                band.locator('select').select_option(p['id']);check('Selecting an assigned project enables recording',band.get_by_role('checkbox').is_checked())
                band.locator('select').select_option('');check('Clearing the project keeps independent testing available',band.get_by_role('checkbox').is_checked() and 'project recording is skipped' in band.inner_text())
            except Exception as exc:
                checks.append({'check':'Browser interaction','passed':False,'error':str(exc),'traceback':traceback.format_exc(),'body':page.locator('body').inner_text()[-7000:]});page.screenshot(path=str(OUT/'work-outcomes-browser-failure.png'),full_page=True)
            finally:
                checks.append({'check':'No frontend exceptions','passed':not errors,'errors':errors});(OUT/'work-browser-results.json').write_text(json.dumps(checks,indent=2),encoding='utf-8');print(json.dumps(checks,indent=2),flush=True);browser.close()
    finally:server.should_exit=True;thread.join(10)
    return 0 if all(c['passed'] for c in checks) else 1

if __name__=='__main__':raise SystemExit(main())
