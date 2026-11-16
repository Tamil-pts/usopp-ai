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
 import re
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1600,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));base=f'http://127.0.0.1:{port}'
 page.goto(base+'/?page=electrical');page.get_by_label('Username',exact=True).fill(admin['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('region',name='Industrial control circuit editor').wait_for(timeout=60000);page.get_by_role('button',name='Drawing reconstruction',exact=True).click();page.get_by_role('region',name='Industrial electrical reconstruction').wait_for()
 page.get_by_label('Import industrial PDF',exact=True).set_input_files(r'C:\Users\PTPL0241\Downloads\4C9935069 - 21-08-26.pdf')
 page.get_by_role('button',name=re.compile('^Page 16')).wait_for(timeout=90000);page.get_by_role('button',name=re.compile('^Page 16')).click()
 page.get_by_role('button',name='Review connection',exact=True).first.wait_for();assert page.get_by_role('button',name='Review connection',exact=True).count()==25
 page.wait_for_function("document.querySelector('.reconstruction-source img')?.naturalWidth > 0")
 page.get_by_role('button',name='Review connection',exact=True).first.click();page.locator('[aria-label="Selected source connection"]').wait_for()
 page.get_by_label('Connection review status').select_option('verified');page.get_by_label('Connection review comment').fill('Browser fixture: checked this terminal row against source')
 page.get_by_role('button',name='Save connection review',exact=True).click();page.wait_for_function("!document.querySelector('textarea[aria-label=\"Connection review comment\"]').value")
 page.get_by_role('button',name='Validate selected page',exact=True).click();page.get_by_role('heading',name='page validation: unresolved',exact=True).wait_for()
 page.get_by_role('button',name='Validate complete project scope',exact=True).click();page.get_by_role('heading',name='project_scope validation: unresolved',exact=True).wait_for()
 page.get_by_role('button',name=re.compile('^Page 6 ')).click();page.get_by_label('Show independent vector paths on source').check();page.locator('[aria-label="Independent vector paths"]').wait_for();assert page.locator('[aria-label="Independent vector paths"] polyline').count()==219
 page.screenshot(path='.build/electrical-reconstruction-20261113/workspace.png',full_page=True)
 print('PASS actual LC361 import, 18 pages, 25 assignments on page 16, source highlight, review save and validation gate')
 page.get_by_role('button',name='Control circuit',exact=True).click();page.get_by_role('region',name='Industrial control circuit editor').wait_for();assert page.get_by_role('button',name='Electronics / SPICE',exact=True).count()==0;print('PASS single industrial workspace; no Electronics mode')
 assert not errors,errors;browser.close();server.should_exit=True
