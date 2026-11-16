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
 page.goto(base+'/?page=home&hubView=projects');page.get_by_label('Username',exact=True).fill(admin['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 documents=page.get_by_role('button',name='Documents',exact=True);documents.wait_for(timeout=60000);documents.focus();page.keyboard.press('ArrowDown');panel=page.get_by_role('group',name='Documents options');panel.wait_for();page.keyboard.press('End');assert 'Project closure' in page.locator(':focus').inner_text();page.keyboard.press('Escape');assert not panel.is_visible();print('PASS top document menu keyboard and dismissal')
 page.get_by_role('button',name='Open Chopper chat',exact=True).click();page.screenshot(path='.build/chopper-tasks-20261113/assistant.png',full_page=True);page.set_viewport_size({'width':390,'height':844});box=page.locator('#chopper-quick-help').bounding_box();assert box and box['x']>=0 and box['x']+box['width']<=391;page.set_viewport_size({'width':1440,'height':1000});print('PASS Chopper task panel fits mobile width');page.get_by_label('Find Chopper task').fill('FRD');page.locator('.chopperTaskCatalog button').filter(has_text='Create FRD').click();page.get_by_label('Document Type',exact=True).wait_for();assert page.get_by_label('Document Type',exact=True).input_value()=='frd';print('PASS Chopper opens actual FRD creation workflow')
 page.goto(base+'/?page=home&hubView=projects');page.get_by_role('button',name='Open Chopper chat',exact=True).click();page.get_by_label('Ask Chopper',exact=True).fill('create a flowchart for requirements, design, validation and release review');page.get_by_role('button',name='Send question',exact=True).click();page.get_by_role('button',name='Start this task',exact=True).click();page.get_by_label('Document Type',exact=True).wait_for();assert page.get_by_label('Document Type',exact=True).input_value()=='flowchart';assert page.get_by_label('Describe the requirement',exact=True).input_value()=='create a flowchart for requirements, design, validation and release review';print('PASS text command prefills Chopper diagram drafting')
 page.goto(base+'/?page=home&hubView=projects');page.get_by_role('button',name='Open Chopper chat',exact=True).click();page.get_by_label('Find Chopper task').fill('Compare documents');page.locator('.chopperTaskCatalog button').filter(has_text='Compare documents').click();page.wait_for_function("new URL(location.href).searchParams.get('assistTab')==='documents'");print('PASS document comparison task route')
 created=page.request.post(base+'/api/workhub/document-spaces',data={'stage':'flowchart','document_type':'flowchart','request_id':'assistant-guard','title':'Assistant guard'}).json()
 page.goto(base+'/?page=home&hubView=documents&documentScope='+created['scope_id']+'&documentStage=native:'+created['document_id']);page.get_by_role('region',name='Visual design workspace').wait_for(timeout=60000);page.get_by_role('button',name='Insert',exact=True).click();page.get_by_role('button',name='process',exact=True).click();page.wait_for_timeout(300)
 page.on('dialog',lambda dialog:dialog.dismiss());before=page.url;page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='PLC',exact=True).click();assert page.url==before;assert page.get_by_role('group',name='WorkHub submenu',exact=True).is_visible();print('PASS cancelled dirty navigation retains current menu and workspace')
 assert not errors,errors
 browser.close();server.should_exit=True
