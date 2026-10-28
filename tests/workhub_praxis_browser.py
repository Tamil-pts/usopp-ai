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
    module=importlib.import_module('backend.app');app=module.app;module.DIST=ROOT/'.build/praxis-upgrade/candidate'
    from backend.api import system
    from backend.core.build_info import frontend_build_info
    system.frontend_build_info=lambda distribution,expected:frontend_build_info(module.DIST,expected)
    for route in app.routes:
        if getattr(route,'name','')=='assets':route.app=StaticFiles(directory=module.DIST/'assets')
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
    out=ROOT/'.build/praxis-upgrade';checks=[];errors=[];tokens=[];contexts=[];base=f'http://127.0.0.1:{port}'
    def check(name,passed,**details):
        checks.append({'check':name,'passed':bool(passed),**details});print(name+': '+str(bool(passed)),flush=True)
        if not passed:raise AssertionError(name)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        def page_for(person,width=1440):
            token=accounts.store.new_session(person['id']);tokens.append(token)
            context=browser.new_context(viewport={'width':width,'height':1000});contexts.append(context)
            context.add_cookies([{'name':accounts.COOKIE,'value':token,'url':base,'httpOnly':True,'sameSite':'Lax'}])
            page=context.new_page();page.set_default_timeout(20000);page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base,wait_until='domcontentloaded');page.get_by_role('navigation',name='WorkHub main sections').wait_for();return page
        def main_menu(page,name):page.get_by_role('navigation',name='WorkHub main sections').get_by_role('button',name=name,exact=True).click()
        def praxis(page):main_menu(page,'Praxis');page.get_by_role('heading',name='Praxis',exact=True).wait_for();page.locator('.px-kpis').wait_for()
        def fit(page):return page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2 && document.querySelector('.main').scrollWidth <= document.querySelector('.main').clientWidth + 2")
        page=None
        try:
            page=page_for(admin)
            nav=page.get_by_role('navigation',name='WorkHub main sections')
            check('Exactly four native WorkHub menus',nav.get_by_role('button').all_text_contents()==['Overview','Projects','Praxis','TechShare'])
            check('Anonymous confidential API is protected',pw.request.new_context().get(base+'/api/workhub/praxis/metadata').status in (401,403))
            main_menu(page,'Projects');page.get_by_role('navigation',name='Projects views').get_by_role('button',name='Task Management',exact=True).click()
            page.get_by_role('heading',name='Task Management',exact=True).wait_for();page.locator('.resource-grid').wait_for()
            page.locator('.resource-filters').get_by_label('From',exact=True).fill(start.isoformat());page.locator('.resource-filters').get_by_label('To',exact=True).fill(finish.isoformat())
            person=page.locator('.resource-person').filter(has_text=employee['username']);person.get_by_text('50 h',exact=True).wait_for()
            check('Resource workload includes both native projects',person.get_by_text('Overallocated',exact=True).is_visible())
            page.locator('.resource-filters').get_by_label('Project',exact=True).select_option(projects[0]['id'])
            page.locator('.resource-tasks').get_by_text('Budget planning',exact=True).wait_for(state='hidden')
            check('Single-project filter retains cross-project load',person.get_by_text('50 h',exact=True).is_visible())
            check('Configured resource block is shown',page.locator('.resource-person').filter(has_text=outsider['username']).get_by_text('Unavailable',exact=True).is_visible())
            row=page.locator('.resource-tasks tbody tr').filter(has_text='Dependent software work')
            row.get_by_role('button',name='Assign / reassign',exact=True).click();dialog=page.get_by_role('dialog',name='Assign resource')
            dialog.get_by_label('Responsible person',exact=True).select_option(str(manager['id']));dialog.get_by_role('button',name='Save responsibility',exact=True).click();dialog.wait_for(state='hidden')
            expect(row.locator('td').nth(1)).to_contain_text(manager['username']);check('Resource assignment updates the original task',page.request.get(base+'/api/workhub/projects/'+projects[0]['id']).json()['tasks'][-1]['owner_id']==manager['id'])
            check('Desktop resource planning fits the viewport',fit(page));page.screenshot(path=str(out/'task-management-desktop.png'),full_page=True)
            praxis(page);page.locator('.px-filters').get_by_label('Employee',exact=True).select_option(str(employee['id']))
            page.locator('.px-person-heading').get_by_role('heading',name=employee['username'],exact=True).wait_for()
            check('Unassessed values are not fake zeroes',page.locator('.px-kpis strong').all_text_contents()[:2]==['Not Assessed','Not Assessed'])
            check('Exactly four internal Praxis views',page.get_by_role('navigation',name='Praxis views').get_by_role('button').all_text_contents()==['My Praxis','Team Insights','Competency Matrix','Reports'])
            page.get_by_role('button',name='Configure Praxis',exact=True).click();config=page.get_by_role('dialog',name='Configure Praxis')
            config.get_by_role('button',name='Accounting',exact=False).first.click();config.get_by_label('Description',exact=True).fill('Finance role competency reviewed against accounting work.')
            config.get_by_role('button',name='Save Praxis configuration',exact=True).click();config.wait_for(state='hidden')
            check('Role-based configuration saves with a version',page.request.get(base+'/api/workhub/praxis/metadata').json()['configuration']['version']==2)
            # Prepare and submit through the employee UI; manager reviews separately.
            ep=page_for(employee);praxis(ep);ep.get_by_role('button',name='New assessment',exact=True).click();assessment=ep.get_by_role('dialog',name='Praxis assessment',exact=True)
            assessment.get_by_label('Independent reviewer',exact=True).select_option(str(manager['id']))
            for name,level in [('Accounting','3'),('Planning','4'),('Reporting','2')]:assessment.locator('.px-dimension').filter(has=ep.locator('b',has_text=name)).get_by_role('combobox').select_option(level)
            assessment.get_by_label('Measured value',exact=False).nth(0).fill('80');assessment.get_by_label('Measured value',exact=False).nth(1).fill('60')
            assessment.locator('summary').get_by_text('Related work for this assessment',exact=True).click();assessment.get_by_label('Add existing work reference',exact=True).select_option(projects[0]['id'])
            assessment.get_by_label('Work reference type',exact=True).select_option('document');assessment.get_by_label('Add existing work reference',exact=True).select_option(document['id'])
            assessment.get_by_role('button',name='Save assessment draft',exact=True).click();assessment.get_by_text('Preview',exact=False).wait_for()
            assessment.get_by_role('button',name='Submit for review',exact=True).click();assessment.get_by_text('Revision 1',exact=False).filter(has_text='submitted').wait_for()
            check('Employee cannot approve their own assessment',assessment.get_by_role('button',name='Approve assessment',exact=True).count()==0)
            assessment.get_by_role('button',name='Close Praxis assessment',exact=True).click()
            check('Draft submission does not change approved indices',ep.locator('.px-kpis strong').all_text_contents()[:2]==['Not Assessed','Not Assessed'])
            mp=page_for(manager);praxis(mp);mp.locator('.px-filters').get_by_label('Employee',exact=True).select_option(str(employee['id']));mp.locator('.px-record').filter(has_text='submitted').click()
            review=mp.get_by_role('dialog',name='Praxis assessment',exact=True);review.get_by_label('Reviewer comments',exact=True).fill('Reviewed the original finance work and role criteria.');review.get_by_role('button',name='Approve assessment',exact=True).click();review.get_by_text('Revision 1',exact=False).filter(has_text='approved').wait_for()
            review.get_by_role('button',name='Close Praxis assessment',exact=True).click();mp.locator('.px-kpis strong').filter(has_text='75.0').wait_for()
            check('Approved performance and competency use separate calculations',mp.locator('.px-kpis strong').all_text_contents()[:2]==['75.0','65.0'])
            mp.get_by_role('img',name='Competency proficiency radar').wait_for();check('Approved charts render',mp.locator('.px-chart canvas').count()>=4)
            mp.get_by_role('navigation',name='Praxis views').get_by_role('button',name='Competency Matrix',exact=True).click();mp.get_by_role('button',name='Accounting',exact=True).click()
            drawer=mp.get_by_role('dialog',name='Competency details');check('Competency drilldown includes criteria and approved review',drawer.get_by_role('heading',name='Historical assessments',exact=True).is_visible() and drawer.get_by_text('Reviewed the original finance work and role criteria.',exact=True).count()>0)
            drawer.get_by_role('button',name='Plan development',exact=True).click();goal=mp.get_by_role('dialog',name='Development goal',exact=True);goal.get_by_role('button',name='Save development goal',exact=True).click();goal.wait_for(state='hidden')
            check('Development recommendation creates a native scoped goal',len(mp.request.get(base+'/api/workhub/praxis/profiles/'+str(employee['id'])).json()['development'])==1)
            mp.get_by_role('navigation',name='Praxis views').get_by_role('button',name='My Praxis',exact=True).click();mp.locator('.px-record').filter(has_text='Develop Accounting').click();goal=mp.get_by_role('dialog',name='Development goal',exact=True);goal.get_by_label('Status',exact=True).select_option('completed');goal.get_by_role('button',name='Save development goal',exact=True).click();goal.wait_for(state='hidden')
            check('Goal completion does not automatically change competency',mp.request.get(base+'/api/workhub/praxis/profiles/'+str(employee['id'])).json()['competency_index']==65)
            mp.get_by_role('navigation',name='Praxis views').get_by_role('button',name='Team Insights',exact=True).click();mp.get_by_role('heading',name='Skill coverage and available expertise',exact=True).wait_for();mp.get_by_role('img',name='Department and team competency heatmap').wait_for()
            check('Team filter API accepts empty optional filters',mp.locator('.px-workspace [role=alert]').count()==0)
            check('Manager cannot view unrelated employee assessment',mp.request.get(base+'/api/workhub/praxis/profiles/'+str(outsider['id'])).status==403)
            check('Employee cannot view manager confidential assessment',ep.request.get(base+'/api/workhub/praxis/profiles/'+str(manager['id'])).status==403)
            check('Professional team role does not grant Admin access',mp.request.post(base+'/api/workhub/organization/units',data={'version':0,'kind':'team','name':'Forbidden'}).status==403)
            mp.screenshot(path=str(out/'praxis-team-insights.png'),full_page=True)
            for kind in ('individual','matrix','development','team','gaps'):
                for format in ('pdf','xlsx'):
                    result=mp.request.get(base+'/api/workhub/praxis/reports/'+kind+'/'+format+'?subject='+str(employee['id'])+'&period_id=current')
                    check(kind+' '+format+' export',result.status==200 and (result.body().startswith(b'%PDF') if format=='pdf' else result.body().startswith(b'PK')))
                    if kind=='individual' and format=='xlsx':
                        book=load_workbook(BytesIO(result.body()));check('Excel matches approved indices, reviewer and filterable data',book['Summary'].cell(5,4).value==75 and book['Summary'].cell(5,5).value==65 and book['Summary'].cell(5,8).value==manager['username'] and book['Summary'].auto_filter.ref.startswith('A4:'));book.close()
            # Open the original document through the competency, rather than a duplicate record.
            mp.get_by_role('navigation',name='Praxis views').get_by_role('button',name='Competency Matrix',exact=True).click();mp.get_by_role('button',name='Accounting',exact=True).click()
            mp.get_by_role('dialog',name='Competency details').locator('.px-reference').filter(has_text='document').click();mp.locator('#workhub-frd-editor').wait_for()
            check('Work reference opens the original FRD editor',mp.get_by_role('navigation',name='Project workspace sections').get_by_role('button',name='Meetings & Requirements',exact=True).get_attribute('aria-current')=='page')
            # Settings and profile integration use existing account users.
            page.get_by_role('button',name='Settings',exact=True).click();people=page.locator('#workhub-team-settings');people.get_by_role('heading',name='Departments, roles & teams',exact=True).wait_for();people.locator('summary').click()
            people.get_by_role('button',name='Edit Finance group',exact=True).click();people.get_by_label('Name',exact=True).fill('Finance resource group');people.get_by_role('button',name='Save organization record',exact=True).click();people.get_by_role('button',name='Edit Finance resource group',exact=True).wait_for()
            check('Admin can maintain team groups and administrators',page.request.get(base+'/api/workhub/organization').json()['memberships'][0]['team_id']==team['id'])
            people.locator('.people-person').filter(has_text=employee['username']).click();profile=page.get_by_role('dialog',name='Edit Team Details',exact=True);profile.get_by_label('Weekly capacity (hours)',exact=True).fill('32');profile.get_by_role('button',name='Save Team Details',exact=True).click();profile.wait_for(state='hidden')
            check('Team Details updates capacity without changing account role',next(u for u in page.request.get(base+'/api/workhub/organization').json()['users'] if u['id']==employee['id'])['profile']['weekly_hours']==32)
            check('My profile includes Team Details',page.locator('.setting').filter(has=page.get_by_role('heading',name='My profile',exact=True)).get_by_role('heading',name='Team Details',exact=True).is_visible())
            page.get_by_role('button',name='WorkHub',exact=True).click();praxis(page);page.locator('.px-filters').get_by_label('Employee',exact=True).select_option(str(employee['id']));page.locator('.px-kpis strong').filter(has_text='75.0').wait_for()
            check('Native project and document records retained',len(page.request.get(base+'/api/workhub/overview').json()['items'])==5 and page.request.get(base+'/api/workhub/documents').json()['total']==1)
            check('Desktop Praxis fits the viewport',fit(page));page.screenshot(path=str(out/'praxis-desktop.png'),full_page=True)
            page.get_by_role('button',name='Dark mode',exact=True).click();page.screenshot(path=str(out/'praxis-dark.png'),full_page=True)
            page.locator('.px-chart-grid').screenshot(path=str(out/'praxis-approved-charts.png'))
            check('Dark mode applies to charts and dashboard',page.locator('html').get_attribute('data-theme')=='dark' and page.locator('.px-chart canvas').count()>=4)
            for width in (1000,768,390):
                page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(250)
                check('Praxis reflows at '+str(width)+'px',fit(page))
            page.screenshot(path=str(out/'praxis-mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000});page.evaluate("document.body.style.zoom='1.5'");page.wait_for_timeout(300);check('Praxis fits at 150 percent CSS zoom',fit(page));page.evaluate("document.body.style.zoom='1'")
            main_menu(page,'TechShare');page.locator('.gr-knowledge').wait_for();check('TechShare preserves existing library and contribution workflow',page.get_by_role('button',name='Share a contribution',exact=True).count()>0 or page.get_by_role('button',name='Add contribution',exact=True).count()>0)
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


if __name__=='__main__':raise SystemExit(main())
