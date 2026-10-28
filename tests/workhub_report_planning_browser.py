"""Browser acceptance against isolated sample data and the candidate UI."""
from pathlib import Path
import asyncio,hashlib,importlib,json,os,socket,sys,tempfile,threading,time,traceback
from contextlib import asynccontextmanager
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));OUT=ROOT/'.build/workhub-navigation'
fixture=json.loads((OUT/'six-samples-isolated.json').read_text())
assert fixture['complete'] and not fixture['live']
DATA=Path(fixture['data_root']).resolve();assert Path(tempfile.gettempdir()).resolve() in DATA.parents
os.environ.update(USOPP_DATA_ROOT=str(DATA.parent),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
from backend.core import accounts
from backend.core.workhub import store as hub,identity
from backend.core.workhub_quality import store as quality,documents,service,checks as qc_checks
from backend.core.workhub_intelligence import jobs
import uvicorn
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright,expect

quality.initialize();users={u['username']:u for u in accounts.store.list_users()}
admin,tamil=users['Admin'],users['Tamil'];sample=fixture['projects'][3];pid=sample['id']
# Leave the assigned review task open to exercise completion with approval.
rev=service.get_document(tamil,pid,'quality')['revision']
with hub.db() as db:basis=qc_checks.baseline(db,hub.item(db,pid))
d=documents.draft(tamil,pid,'quality',rev['content'],'Isolated sample review after completing the planned quality task.',generated_by='revision:'+identity(),expected_current=rev['id'],baseline=basis)
for action in ('confirm','submit'):
 r=service.get_document(tamil,pid,'quality')['revision'];service.action(tamil,pid,'quality',{'version':r['version'],'revision_id':r['id'],'action':action,'comment':'Fictional sample only.'})

module=importlib.import_module('backend.app');app=module.app;module.DIST=OUT/'candidate'
from backend.api import system
from backend.core.build_info import frontend_build_info
system.frontend_build_info=lambda distribution,expected:frontend_build_info(module.DIST,expected)
for route in app.routes:
 if getattr(route,'name','')=='assets':route.app=StaticFiles(directory=module.DIST/'assets')
@asynccontextmanager
async def lifespan(app):yield
app.router.lifespan_context=lifespan
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
for _ in range(100):
 if server.started:break
 time.sleep(.05)
base='http://127.0.0.1:'+str(port);results=[];errors=[];token=accounts.store.new_session(admin['id'])
def check(name,passed,**details):
 results.append({'check':name,'passed':bool(passed),**details});assert passed,name
def wait_for(read,predicate):
 end=time.monotonic()+20
 while time.monotonic()<end:
  value=read()
  if predicate(value):return value
  time.sleep(.1)
 raise AssertionError('Saved record did not reach expected state')

try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1440,'height':1000});context.add_cookies([{'name':accounts.COOKIE,'value':token,'url':base}]);page=context.new_page();page.set_default_timeout(20000);page.on('pageerror',lambda e:errors.append(str(e)))
  try:
   page.goto(base,wait_until='domcontentloaded');page.get_by_role('heading',name='My Dashboard',exact=True).wait_for()
   page.get_by_role('button',name='Settings',exact=True).click();controls=page.locator('#quality-company-settings');controls.locator('summary').get_by_text('Company numbering and revisions',exact=True).click();controls.get_by_label('Project number prefix',exact=True).fill('UI-PRJ')
   with page.expect_response(lambda r:'/api/admin/settings/engineering-quality' in r.url and r.request.method=='PUT') as response:controls.get_by_role('button',name='Save company controls',exact=True).click()
   check('Admin can configure a project-specific prefix',response.value.status==200)
   page.get_by_role('button',name='WorkHub',exact=True).click();page.locator('.wh-heading').get_by_role('button',name='New project',exact=True).click();dialog=page.get_by_role('dialog',name='Create project',exact=True)
   dialog.get_by_label('Project name',exact=True).fill('UI project with client and sprints');dialog.get_by_label('Customer / Client name',exact=True).fill('Fictional Browser Client');dialog.get_by_label('Project number',exact=True).fill('441')
   dialog.locator('summary').get_by_text('Workflow, assignment and target date',exact=True).click();dialog.get_by_label('Responsible engineer',exact=True).select_option(str(tamil['id']))
   dialog.locator('summary').get_by_text('Timeline and planning method',exact=True).click();dialog.get_by_label('Planning method',exact=True).select_option('agile');dialog.get_by_label('Initial sprints',exact=True).fill('3')
   check('Agile creation shows a sprint and phase preview',dialog.get_by_role('heading',name='Project timeline preview',exact=True).is_visible())
   for width in (960,720,390):
    page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(150);check('Project creation fits width '+str(width),page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'))
   page.set_viewport_size({'width':1440,'height':1000});dialog.get_by_role('button',name='Create project & FRD',exact=True).click();dialog.wait_for(state='hidden')
   created=next(p for p in page.request.get(base+'/api/workhub/overview').json()['items'] if p['title']=='UI project with client and sprints');newid=created['id'];detail=page.request.get(base+'/api/workhub/projects/'+newid).json()
   check('Creation applies prefix and creates three real sprints',created['project_number']=='UI-PRJ-441' and len(detail['sprints'])==3 and len(detail['tasks'])==11)
   quality_url=base+'/api/workhub/projects/'+newid+'/quality'
   check('Client is reused in document context',page.request.get(quality_url).json()['context']['customer']=='Fictional Browser Client')
   frd=page.locator('.frd-workspace');frd.get_by_role('button',name='Add requirement',exact=True).click();frd.get_by_label('Title',exact=True).fill('Fixture alarm');frd.get_by_label('Functional description',exact=True).fill('SAMPLE: the PLC shall indicate the fixture alarm.');frd.get_by_label('Acceptance criteria',exact=True).fill('The fictional alarm follows the fixture input.')
   field=frd.locator('.qc-field-files').filter(has=page.get_by_text('for FR-001 Functional description',exact=True));field.locator('summary').first.click();field.get_by_label('Upload files for FR-001 Functional description',exact=True).set_input_files({'name':'fixture-input.txt','mimeType':'text/plain','buffer':b'Fictional requirement input attachment.'})
   wait_for(lambda:page.request.get(quality_url+'/documents/frd').json(),lambda r:bool(r['revision']['content'].get('field_files',{}).get('requirement/FR-001/description')))
   check('An FRD field upload is saved to that specific field',True)
   page.locator('.qc-document-actions').get_by_role('button',name='Review & Confirm',exact=True).click()
   wait_for(lambda:page.request.get(quality_url).json(),lambda q:all(next(s for s in q['stages'] if s['id']==stage)['document'] for stage in ('test','fat','closure')))
   test=page.request.get(quality_url+'/documents/test').json()['revision'];check('FRD prepares test procedures and carries field attachments',test['content']['cases'][0]['objective']=='Fixture alarm' and bool(test['content']['field_files']['case/TC-001/procedure']) and test['content']['cases'][0]['execution'] is None)
   page.get_by_role('navigation',name='Project workspace sections').get_by_role('button',name='Quality & Closure',exact=True).click();panel=page.get_by_role('region',name='Reports before quality approval',exact=True);panel.get_by_role('button',name='View Validation Report',exact=True).click();page.get_by_role('region',name='Saved report preview',exact=True).get_by_text('Fixture alarm',exact=False).first.wait_for();check('The generated Validation Report can be viewed before approval',True)
   panel.get_by_role('button',name='Open / edit Validation Report',exact=True).click();page.locator('.qc-editor details.qc-item').first.locator('summary').first.click();page.get_by_label('TC-001 procedure',exact=True).fill('SAMPLE revised procedure after engineering review.')
   expected_field=page.locator('.qc-field-files').filter(has=page.get_by_text('for TC-001 expected result',exact=True));expected_field.locator('summary').first.click();expected_field.get_by_label('Upload files for TC-001 expected result',exact=True).set_input_files({'name':'expected-result.txt','mimeType':'text/plain','buffer':b'Fictional expected behavior reference.'})
   saved=wait_for(lambda:page.request.get(quality_url+'/documents/test').json()['revision'],lambda r:bool(r['content'].get('field_files',{}).get('case/TC-001/expected_result')))
   check('Generated report fields remain editable with individual uploads',saved['content']['cases'][0]['procedure']=='SAMPLE revised procedure after engineering review.')
   page.get_by_role('navigation',name='Project workspace sections').get_by_role('button',name='Overview',exact=True).click();page.locator('#project-tracking').get_by_role('button',name='New sprint',exact=True).click();sprint=page.get_by_role('dialog',name='New sprint',exact=True);sprint.get_by_label('Sprint name',exact=True).fill('Added after creation');sprint.get_by_role('button',name='Save sprint',exact=True).click();sprint.wait_for(state='hidden');check('Agile projects can add another sprint from their timeline',len(page.request.get(base+'/api/workhub/projects/'+newid).json()['sprints'])==4)
   page.evaluate('(id)=>window.dispatchEvent(new CustomEvent("workhub-open-project",{detail:{project:id}}))',pid);page.locator('.wh-project-title h2').get_by_text(sample['title'],exact=True).wait_for();page.get_by_role('button',name='Quality passed / Send for release approval',exact=True).first.click();action=page.get_by_role('dialog',name='Quality passed / Send for release approval',exact=True);action.get_by_role('button',name='View Validation Report / FAT and Quality Review',exact=True).click()
   panel=page.get_by_role('region',name='Reports before quality approval',exact=True);approve=page.locator('.qc-document-actions').get_by_role('button',name='Approve',exact=True);approve.wait_for();check('Quality approval waits for report review',approve.is_disabled())
   panel.get_by_role('button',name='View Validation Report',exact=True).click();page.get_by_role('region',name='Saved report preview',exact=True).wait_for();panel.get_by_role('button',name='View FAT',exact=True).click();page.get_by_role('region',name='Saved report preview',exact=True).get_by_text('FAT-001',exact=False).first.wait_for()
   for box in page.locator('.qc-review').get_by_role('checkbox').all():box.check()
   check('Current Validation Report and FAT can both be reviewed before the quality decision',approve.is_enabled())
   with page.expect_response(lambda r:'/quality/documents/' in r.url and r.url.endswith('/action') and r.request.method=='POST') as response:approve.click()
   check('Reviewed quality approval succeeds through the existing workflow',response.value.status==200)
   wait_for(lambda:page.request.get(base+'/api/workhub/projects/'+pid).json(),lambda d:d['project']['stage']=='release_approval')
   check('Quality approval advances to the assigned release approver',True)
   completed=fixture['projects'][0];closed=completed['id'];pdf_url=base+'/api/workhub/projects/'+closed+'/quality/documents/frd/export/pdf';pdf_before=page.request.get(pdf_url).body();before=page.request.get(base+'/api/workhub/projects/'+closed).json()['project']
   page.evaluate('(id)=>window.dispatchEvent(new CustomEvent("workhub-open-project",{detail:{project:id}}))',closed);page.locator('.wh-project-title h2').get_by_text(completed['title'],exact=True).wait_for();page.locator('#project-tracking').get_by_role('button',name='Edit workflow plan: '+completed['title'],exact=True).click();dates=page.get_by_role('dialog',name='Edit timeline dates',exact=True);dates.get_by_label('Finish date',exact=True).fill('2026-12-01');dates.get_by_role('button',name='Save dates',exact=True).click();dates.wait_for(state='hidden')
   after=page.request.get(base+'/api/workhub/projects/'+closed).json()['project'];q=page.request.get(base+'/api/workhub/projects/'+closed+'/quality').json();check('Timeline dates remain editable after completion without changing actuals',after['due_date']=='2026-12-01' and before['completed_at']==after['completed_at'] and before['baseline_due']==after['baseline_due'] and q['report']['quality_approved'])
   check('Approved PDF bytes retain their original snapshot after a timeline edit',pdf_before==page.request.get(pdf_url).body())
   page.screenshot(path=str(OUT/'report-planning-completed-timeline.png'),full_page=True);check('No browser runtime errors',not errors,errors=errors)
  except Exception as error:
   results.append({'check':'Browser run completed','passed':False,'error':str(error),'traceback':traceback.format_exc()});page.screenshot(path=str(OUT/'report-planning-browser-failure.png'),full_page=True)
  finally:browser.close()
finally:
 accounts.store.logout(token);server.should_exit=True;thread.join(timeout=5)
 (OUT/'report-planning-browser-results.json').write_text(json.dumps({'checks':results,'errors':errors},indent=2),encoding='utf8')
print(json.dumps({'passed':sum(c['passed'] for c in results),'total':len(results),'last':results[-1]}));sys.exit(0 if results and all(c['passed'] for c in results) and not errors else 1)
