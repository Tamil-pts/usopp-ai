"""Isolated browser acceptance for the native WorkHub Praxis upgrade."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
SANDBOX=Path(tempfile.mkdtemp(prefix='praxis-browser-'))
os.environ.update(USOPP_DATA_ROOT=str(SANDBOX),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')


def main():
    import importlib,json,socket,threading,time,traceback
    from contextlib import asynccontextmanager
    from datetime import date,timedelta
    from io import BytesIO
    from openpyxl import load_workbook
    from playwright.sync_api import sync_playwright,expect,expect
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    module=importlib.import_module('backend.app');app=module.app;module.DIST=Path(os.environ.get('USOPP_TEST_DIST',ROOT/'.build/competency-hub/candidate'))
    from backend.api import system
    from backend.core.build_info import frontend_build_info
    system.frontend_build_info=lambda distribution,expected:frontend_build_info(module.DIST,expected)
    for route in app.routes:
        if getattr(route,'name','')=='assets':route.app=StaticFiles(directory=module.DIST/'assets')
        if getattr(route,'name','')=='nami':route.app=StaticFiles(directory=Path(os.environ.get('USOPP_TEST_NAMI',ROOT/'.build/competency-hub/nami')),html=True)
    from backend.core import accounts,workhub_organization as org
    from backend.core.workhub import store as hub
    from backend.core.workhub_praxis import store,service
    from backend.core.workhub_quality import store as quality,authoring
    quality.initialize()
    admin=next(u for u in accounts.store.list_users() if u['username']=='Admin')
    password='Isolated.Praxis.2026!'
    employee=accounts.store.register('praxis_analyst',password,'Accounts analyst','Fixture')
    manager=accounts.store.register('praxis_manager',password,'Department manager','Fixture')
    outsider=accounts.store.register('praxis_software',password,'Software developer','Fixture')
    def unit(kind,name,**extra):return org.save_unit(admin,{'kind':kind,'name':name,'version':0,**extra})
    finance=unit('department','Finance');software=unit('department','Software')
    analyst=unit('role','Accounts analyst',department_id=finance['id']);developer=unit('role','Software developer',department_id=software['id'])
    team=unit('team','Finance group',department_id=finance['id'],member_ids=[employee['id'],manager['id']],manager_ids=[manager['id']])
    def assign(person,dept,role,reporting=None,**extra):
        p=next(u['profile'] for u in org.directory(admin)['users'] if u['id']==person['id'])
        return org.save_profile(admin,person['id'],{**p,'department_id':dept['id'],'role_id':role['id'],'manager_id':reporting,**extra})
    assign(employee,finance,analyst,manager['id']);assign(manager,finance,analyst)
    assign(outsider,software,developer,availability='blocked',availability_note='Private planning note')
    today=date.today();start=today-timedelta(days=today.weekday());finish=start+timedelta(days=4)
    projects=[hub.create(admin,{'title':title,'owner_id':employee['id'],'quality_id':manager['id'],'approver_id':admin['id'],'release_id':admin['id'],'methodology':'custom'}) for title in ('Fixture finance delivery','Fixture second assignment')]
    tasks=[hub.create(admin,{'title':title,'owner_id':employee['id'],'planned_hours':hours,'start_date':start.isoformat(),'due_date':finish.isoformat()},project['id']) for project,hours,title in zip(projects,(20,30),('Financial close','Budget planning'))]
    blocked=hub.create(admin,{'title':'Dependent software work','owner_id':outsider['id'],'planned_hours':4,'start_date':start.isoformat(),'due_date':finish.isoformat(),'dependencies':[tasks[0]['id']]},projects[0]['id'])
    authoring.create(admin,projects[0]['id'],{'stage':'frd','from_project':True})
    with hub.db() as db:document=dict(db.execute('SELECT * FROM pi_documents WHERE project_id=?',(projects[0]['id'],)).fetchone())
    competencies=[{'id':'c'+str(i),'name':name,'category':'Financial practice','department_id':finance['id'],'description':'Professional '+name.lower(),'criteria':'Review the recorded finance deliverables','review_frequency_days':90,'active':True} for i,name in enumerate(('Accounting','Planning','Reporting'),1)]
    competencies.append({'id':'software_competency','name':'Software quality','category':'Development','department_id':software['id'],'description':'Software quality','criteria':'Reviewed code and tests','review_frequency_days':90,'active':True})
    model={'id':'finance_model','name':'Finance role model','active':True,'department_id':finance['id'],'role_id':analyst['id'],'description':'Finance professional responsibilities','method':'weighted_mean',
      'competencies':[{'id':'b'+str(i),'competency_id':'c'+str(i),'required_level':4,'weight':2 if i==2 else 1} for i in range(1,4)],
      'performance':[{'id':'delivery','name':'Deliverable quality','criteria':'Reviewed finance deliverables','weight':3},{'id':'goals','name':'Goal achievement','criteria':'Agreed objectives','weight':1}]}
    period={'id':'current','name':'Current review period','start':start.isoformat(),'end':(finish+timedelta(days=30)).isoformat(),'active':True}
    store.save_configuration(admin,{'version':0,'content':{'competencies':competencies,'templates':[model],'periods':[period]}})
    @asynccontextmanager
    async def lifespan(app):yield
    app.router.lifespan_context=lifespan
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    out=Path(os.environ.get('USOPP_TEST_OUT',ROOT/'.build/competency-hub'));checks=[];errors=[];tokens=[];base=f'http://127.0.0.1:{port}'
    def check(name,passed,**details):
        checks.append({'check':name,'passed':bool(passed),**details});print(name+': '+str(bool(passed)),flush=True)
        if not passed:raise AssertionError(name)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        def page_for(person):
            token=accounts.store.new_session(person['id']);tokens.append(token)
            ctx=browser.new_context(viewport={'width':1440,'height':1000})
            ctx.add_cookies([{'name':accounts.COOKIE,'value':token,'url':base,'httpOnly':True,'sameSite':'Lax'}])
            p=ctx.new_page();p.set_default_timeout(20000);p.on('pageerror',lambda e:errors.append(str(e)))
            p.goto(base,wait_until='domcontentloaded');p.get_by_role('navigation',name='WorkHub main sections').wait_for();return p
        def menu(p,name):p.get_by_role('navigation',name='WorkHub main sections').get_by_role('button',name=name,exact=True).click()
        def competency(p):
            menu(p,'Competency Hub');p.get_by_role('heading',name='Competency Hub',exact=True).wait_for();p.locator('.ch-insight-grid').wait_for()
        def tab(p,name):p.get_by_role('navigation',name='Competency Hub sections').get_by_role('button',name=name,exact=True).click()
        def fit(p):return p.evaluate("document.documentElement.scrollWidth<=innerWidth+2 && document.querySelector('.main').scrollWidth<=document.querySelector('.main').clientWidth+2")
        page=None
        try:
            page=page_for(admin);nav=page.get_by_role('navigation',name='WorkHub main sections')
            check('Praxis replaced in four native menus',nav.get_by_role('button').all_text_contents()==['Overview','Projects','Competency Hub','TechShare'])
            competency(page);page.locator('.px-filters').get_by_label('Employee',exact=True).select_option(str(employee['id']))
            page.locator('.px-person-heading').get_by_role('heading',name=employee['username'],exact=True).wait_for()
            check('Four requested Competency Hub sections',page.get_by_role('navigation',name='Competency Hub sections').get_by_role('button').all_text_contents()==['My Competency','Team Capability','Competency Matrix','Reports & Insights'])
            expect(page.locator('.ch-insight').filter(has_text='Performance Index').locator('strong').first).to_have_text('Not Assessed')
            check('No fabricated initial score',page.locator('.ch-insight').filter(has_text='Competency Index').locator('strong').first.inner_text()=='Not Assessed')
            page.get_by_role('button',name='Customize insights',exact=True).click();dialog=page.get_by_role('dialog',name='Customize insights')
            dialog.get_by_label('Insight title',exact=True).first.fill('Delivery review focus');dialog.get_by_label('Insight note',exact=True).first.fill('Inspect the completed project record before assessment.')
            dialog.get_by_role('button',name='Add insight',exact=True).click();dialog.get_by_label('Insight title',exact=True).last.fill('My assessment coverage');dialog.get_by_label('Insight measurement',exact=True).last.select_option('competency_coverage')
            dialog.get_by_role('button',name='Save insights',exact=True).click();dialog.wait_for(state='hidden');page.get_by_role('button',name='Delivery review focus',exact=False).wait_for()
            check('Personal cards, notes and added insights persist',page.request.get(base+'/api/workhub/praxis/insights').json()['widgets'][-1]['title']=='My assessment coverage')
            ep=page_for(employee);competency(ep)
            check('Another account retains its own insight layout',ep.request.get(base+'/api/workhub/praxis/insights').json()['version']==0)
            ep.get_by_role('button',name='New assessment',exact=True).click();assessment=ep.get_by_role('dialog',name='Competency assessment',exact=True)
            assessment.get_by_label('Independent reviewer',exact=True).select_option(str(manager['id']))
            for name,level in [('Accounting','3'),('Planning','4'),('Reporting','2')]:assessment.locator('.px-dimension').filter(has=ep.locator('b',has_text=name)).get_by_role('combobox').select_option(level)
            assessment.get_by_label('Measured value',exact=False).nth(0).fill('80');assessment.get_by_label('Measured value',exact=False).nth(1).fill('60')
            assessment.locator('summary').get_by_text('Related work for this assessment',exact=True).click();assessment.get_by_label('Add existing work reference',exact=True).select_option(projects[0]['id'])
            assessment.get_by_role('button',name='Save assessment draft',exact=True).click();assessment.get_by_text('Preview',exact=False).wait_for();assessment.get_by_role('button',name='Submit for review',exact=True).click();assessment.get_by_text('Revision 1',exact=False).filter(has_text='submitted').wait_for()
            check('Self approval remains unavailable',assessment.get_by_role('button',name='Approve assessment',exact=True).count()==0)
            assessment.get_by_role('button',name='Close Competency assessment',exact=True).click()
            mp=page_for(manager);competency(mp);mp.locator('.px-filters').get_by_label('Employee',exact=True).select_option(str(employee['id']));mp.locator('.px-record').filter(has_text='submitted').click()
            review=mp.get_by_role('dialog',name='Competency assessment',exact=True);review.get_by_label('Reviewer comments',exact=True).fill('Verified finance work and the configured role criteria.');review.get_by_role('button',name='Approve assessment',exact=True).click();review.get_by_text('Revision 1',exact=False).filter(has_text='approved').wait_for();review.get_by_role('button',name='Close Competency assessment',exact=True).click()
            expect(mp.locator('.ch-insight').filter(has_text='Performance Index').locator('strong').first).to_contain_text('75')
            check('Approved indices remain separate',mp.locator('.ch-insight').filter(has_text='Competency Index').locator('strong').first.inner_text().startswith('65'))
            card=mp.locator('.ch-insight').filter(has_text='Performance Index').first;card.locator('.ch-insight-heading').click();card.get_by_text('Verified finance work and the configured role criteria.',exact=True).wait_for()
            check('Insight click expands actual reviewer details',card.get_by_role('button',name='Accounting',exact=True).is_visible())
            card.locator('.ch-insight-heading').click()
            tab(mp,'Team Capability');mp.get_by_role('heading',name='Team capability and coverage',exact=True).wait_for();mp.locator('.px-chart canvas').first.wait_for();check('Team chart uses approved levels',mp.locator('.px-chart canvas').count()>0)
            tab(mp,'Competency Matrix');mp.get_by_role('heading',name='Cross-functional contribution matrix',exact=True).wait_for();mp.get_by_role('button',name='80',exact=True).first.click();mp.get_by_role('heading',name=employee['username']+' · Deliverable quality',exact=True).wait_for()
            check('Contribution cell expands scored criterion',mp.get_by_text('Reviewed finance deliverables',exact=True).count()>0)
            mp.get_by_role('button',name='3 / 4',exact=True).first.click();drawer=mp.get_by_role('dialog',name='Competency details',exact=True);drawer.get_by_role('heading',name='Assessment criteria',exact=True).wait_for();check('Proficiency cell opens independent skill details',drawer.get_by_text('Current: 3',exact=True).is_visible());drawer.get_by_role('button',name='Close competency details').click()
            tab(mp,'Reports & Insights');mp.get_by_label('Report type',exact=True).select_option('individual');mp.get_by_text('Expand detailed report',exact=True).click();check('Detailed reports expand before download',mp.locator('.ch-report-preview').get_by_text('Verified finance work and the configured role criteria.',exact=True).is_visible())
            pdf=mp.request.get(base+mp.get_by_role('link',name='Export PDF',exact=True).get_attribute('href'));xlsx=mp.request.get(base+mp.get_by_role('link',name='Export Excel',exact=True).get_attribute('href'))
            book=load_workbook(BytesIO(xlsx.body()));check('PDF and Excel exports retain approved values and custom insights',pdf.body().startswith(b'%PDF') and book['Summary'].cell(5,4).value==75 and 'Insights' in book.sheetnames);book.close()
            tab(mp,'My Competency');mp.screenshot(path=str(out/'competency-hub-desktop.png'),full_page=True);check('Desktop layout fits',fit(mp))
            for width in (1000,768,390):
                mp.set_viewport_size({'width':width,'height':1000});mp.wait_for_timeout(250);check('Competency Hub fits '+str(width)+'px',fit(mp))
            mp.screenshot(path=str(out/'competency-hub-mobile.png'),full_page=True);mp.set_viewport_size({'width':1440,'height':1000});mp.evaluate("document.body.style.zoom='1.5'");mp.wait_for_timeout(250);check('Competency Hub fits 150 percent zoom',fit(mp));mp.evaluate("document.body.style.zoom='1'")
            mp.get_by_role('button',name='Dark mode',exact=True).click();mp.screenshot(path=str(out/'competency-hub-dark.png'),full_page=True);check('Dark theme remains functional',mp.locator('html').get_attribute('data-theme')=='dark')
            ep.get_by_role('button',name='Settings',exact=True).click();ep.get_by_role('button',name='Edit work profile',exact=True).click();profile=ep.get_by_role('dialog',name='Edit work profile');profile.get_by_label('Daily work hours',exact=True).fill('7');profile.get_by_role('button',name='Save work profile',exact=True).click();profile.wait_for(state='hidden')
            me=next(u for u in ep.request.get(base+'/api/workhub/organization').json()['users'] if u['id']==employee['id']);check('Employee edits own work hours without role escalation',me['profile']['weekly_hours']==35 and me['role']=='user')
            check('No manual resource availability selector',ep.get_by_role('combobox',name='Resource availability',exact=True).count()==0)
            page.get_by_role('button',name='Settings',exact=True).click();page.get_by_role('heading',name='Workflow Configuration',exact=True).wait_for();check('Settings removes separate rules and organization cards',page.locator('#testing-rule-settings').count()==0 and page.locator('#workhub-team-settings').count()==0)
            page.get_by_role('button',name='Manage users',exact=True).click();page.get_by_text('Manage departments, professional roles and teams',exact=True).click();page.locator('#workhub-team-settings').wait_for();check('Organization directory now belongs to user management',page.get_by_role('heading',name='Organization directory',exact=True).is_visible())
            ep.get_by_role('button',name='ByteMap',exact=True).click();selector=ep.get_by_label('Project number / assigned project',exact=True);selector.select_option(projects[0]['id']);expect(ep.get_by_label('Record results for this project',exact=True)).to_be_checked()
            check('ByteMap selector includes project number',selector.locator('option:checked').inner_text().startswith(projects[0]['project_number']))
            ep.get_by_role('button',name='MatchView',exact=True).click();ep.get_by_label('Project number / assigned project',exact=True).select_option(projects[1]['id']);check('MatchView has independent project selection',ep.get_by_label('Record results for this project',exact=True).is_checked())
            ep.get_by_role('button',name='DataInspect',exact=True).click();frame=ep.frame_locator('iframe[title="Nami PLC Data Verification V1.5"]');frame.get_by_label('Project number / assigned project',exact=True).wait_for();frame.get_by_label('Project number / assigned project',exact=True).select_option(projects[0]['id']);check('DataInspect has project attribution in its own window',frame.get_by_label('Record results for this project',exact=True).is_checked())
            outsider_page=page_for(outsider);check('Confidential assessment permissions retained',outsider_page.request.get(base+'/api/workhub/praxis/profiles/'+str(employee['id'])).status==403)
            check('Testing selector follows actual task assignments',set(p['project_id'] for p in outsider_page.request.get(base+'/api/workhub/testing-projects').json()['projects'])=={projects[0]['id']})
            check('No frontend runtime errors',not errors,errors=errors)
        except Exception as exc:
            checks.append({'check':'Browser completed','passed':False,'error':str(exc)});traceback.print_exc()
            if page:page.screenshot(path=str(out/'browser-failure.png'),full_page=True)
        finally:
            (out/'browser-results.json').write_text(json.dumps({'checks':checks,'errors':errors,'sandbox':str(SANDBOX)},indent=2),encoding='utf-8')
            browser.close()
            for token in tokens:accounts.store.logout(token)
            server.should_exit=True;thread.join(timeout=5)
    return 0 if checks and all(c['passed'] for c in checks) and not errors else 1

if __name__=='__main__':sys.exit(main())
