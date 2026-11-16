import os,sys,tempfile,threading,time,socket
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
os.environ.update(USOPP_DATA_ROOT=tempfile.mkdtemp(prefix='usopp-history-'),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
import uvicorn
from backend.app import app
from backend.core import accounts
from backend.core.workhub import store as hub
from backend.core.workhub_quality import store as quality
from playwright.sync_api import sync_playwright
quality.initialize();password='History.Check.2026!'
admin=accounts.store.register('history_admin',password,'Admin','Fixture',role='admin')
other=accounts.store.register('history_other',password,'Other','Fixture')
project=hub.create(admin,{'title':'History navigation fixture'})
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'));threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True).start()
while not server.started:time.sleep(.05)
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));base=f'http://127.0.0.1:{port}'
 page.goto(base+'/?page=home&hubView=projects&workhubProject='+project['id'])
 page.get_by_label('Username',exact=True).fill(admin['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 page.get_by_role('navigation',name='Breadcrumbs').get_by_role('button',name=project['title'],exact=True).wait_for(timeout=60000)
 print('PASS direct authorized project link')
 page.reload();page.get_by_role('navigation',name='Breadcrumbs').get_by_role('button',name=project['title'],exact=True).wait_for(timeout=60000);print('PASS refresh project')
 page.get_by_role('navigation',name='Breadcrumbs').get_by_role('button',name='Projects',exact=True).click();page.wait_for_function("!new URL(location.href).searchParams.has('workhubProject')")
 page.go_back();page.get_by_role('navigation',name='Breadcrumbs').get_by_role('button',name=project['title'],exact=True).wait_for();print('PASS browser Back')
 page.go_forward();page.wait_for_function("!new URL(location.href).searchParams.has('workhubProject')");print('PASS browser Forward')
 assert page.request.get(base+'/api/not-a-real-endpoint').status==404
 assert page.request.get(base+'/api').status==404
 assert page.request.get(base+'/workspace/bookmark').status==200
 print('PASS SPA fallback and API separation')
 utilities=page.get_by_role('navigation',name='Settings and help')
 utilities.get_by_role('button',name='Help',exact=True).click();page.wait_for_function("new URL(location.href).searchParams.get('page')==='help'")
 utilities.get_by_role('button',name='Settings',exact=True).click();page.wait_for_function("new URL(location.href).searchParams.get('page')==='settings'")
 page.go_back();page.wait_for_function("new URL(location.href).searchParams.get('page')==='help'")
 page.reload();page.wait_for_function("new URL(location.href).searchParams.get('page')==='help'");print('PASS module history and refresh')
 page.goto(base+'/?page=home&hubView=mine&mineMode=approvals');page.get_by_label('Approval type',exact=True).wait_for();page.reload();page.get_by_label('Approval type',exact=True).wait_for();print('PASS approvals route survives refresh')
 page.goto(base+'/?page=home&hubView=projects');search=page.get_by_placeholder('Search project, customer, reference or owner...');search.fill('History');page.wait_for_timeout(800);page.reload();page.get_by_placeholder('Search project, customer, reference or owner...').wait_for();assert page.get_by_placeholder('Search project, customer, reference or owner...').input_value()=='History';print('PASS project filters retained')
 created=page.request.post(base+'/api/workhub/document-spaces',data={'stage':'flowchart','document_type':'flowchart','request_id':'history-drawing','title':'History drawing'}).json()
 assert 'scope_id' in created,created
 link=base+'/?page=home&hubView=documents&documentScope='+created['scope_id']+'&documentStage=native:'+created['document_id']
 page.goto(link);page.get_by_role('region',name='Visual design workspace').wait_for(timeout=60000)
 page.get_by_role('button',name='Insert',exact=True).click();page.get_by_role('button',name='process',exact=True).click();page.wait_for_timeout(300)
 dialogs=[]
 def reject(dialog):dialogs.append(dialog.type);dialog.dismiss()
 page.on('dialog',reject)
 before=page.url;page.go_back();page.wait_for_timeout(800);assert page.url==before,(page.url,before)
 assert 'confirm' in dialogs;print('PASS unsaved drawing blocks Back when cancelled')
 utilities.get_by_role('button',name='Help',exact=True).click();page.wait_for_timeout(300);assert page.url==before;print('PASS unsaved drawing blocks module navigation when cancelled')
 page.remove_listener('dialog',reject)
 page.get_by_role('button',name='Save diagram',exact=True).click();page.wait_for_timeout(1000)
 page.reload();page.get_by_role('region',name='Visual design workspace').wait_for(timeout=60000)
 assert page.locator('.react-flow__node').count()>=1;print('PASS direct document, save and refresh')
 page.get_by_role('navigation',name='Breadcrumbs').get_by_role('button',name='Documents',exact=True).click();page.wait_for_function("!new URL(location.href).searchParams.has('documentScope')")
 page.go_back();page.get_by_role('region',name='Visual design workspace').wait_for();print('PASS document breadcrumb and browser return')
 before=page.url;page.locator('body').click(position={'x':5,'y':5});page.keyboard.press('Backspace');assert page.url==before;print('PASS Backspace outside inputs stays in application')
 page.goto(base+'/?page=home&hubView=projects&workhubProject=missing-project');page.get_by_role('alert').filter(has_text='could not be opened').first.wait_for(timeout=20000)
 print('PASS inaccessible direct link rejected');outsider=browser.new_context();outsider.request.post(base+'/api/auth/login',data={'username':other['username'],'password':password});assert outsider.request.get(base+'/api/workhub/document-spaces/'+created['scope_id']).status==403;outsider.close();print('PASS other account access denied');assert not errors,errors
 browser.close();server.should_exit=True
