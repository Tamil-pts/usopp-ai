import os,sys,tempfile,threading,time,socket
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
os.environ.update(USOPP_DATA_ROOT=tempfile.mkdtemp(prefix='usopp-export-popup-'),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
import uvicorn
from virtual_plc.server import create_app
from backend.core import accounts
from playwright.sync_api import sync_playwright
from tests.test_plc_pdf_comparison import program
app=create_app();password='Export.Popup.2026!'
user=accounts.store.register('export_popup',password,'Engineer','Fixture',role='admin')
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True).start()
while not server.started:time.sleep(.05)
out=ROOT/'.build/matchview-performance-20261116/browser';out.mkdir(exist_ok=True)
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto(f'http://127.0.0.1:{port}/?page=compare')
 page.get_by_label('Username',exact=True).fill(user['username']);page.get_by_label('Password',exact=True).fill(password)
 page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 page.get_by_role('button',name='Project details',exact=True).wait_for(timeout=60000)

 fixture=Path(tempfile.mkdtemp(prefix='matchview-folders-'))
 for name in ('Base','Developed'):
  root=fixture/name/name;root.mkdir(parents=True)
  (root/(name+'.apj')).write_text('<Project/>')
  (root/'LastUser.set').write_text('<?AutomationStudio Version="4.10.2"?><ConfigurationManager ActiveConfigurationName="TestConfig"/>')
  (root/'Logical/Task').mkdir(parents=True)
  (root/'Logical/Task/main.st').write_text('PROGRAM _CYCLIC\nTag := TRUE;\nEND_PROGRAM')
 inputs=page.locator('.compareDarkWorkspace input[type=file][webkitdirectory]')
 assert inputs.count()==2,inputs.count()
 inputs.nth(0).set_input_files(str(fixture/'Base'))
 page.wait_for_timeout(500)
 inputs.nth(1).set_input_files(str(fixture/'Developed'))
 page.wait_for_timeout(1500)
 page.screenshot(path=str(out/'metadata.png'))
 assert page.get_by_text('4.10',exact=True).count()>=2, page.locator('.compareProjectMeta').all_inner_texts()
 page.route('**/api/compare/start',lambda route:route.fulfill(json={'sessionId':'browser_fixture'}))
 page.route('**/api/local/compare/status/browser_fixture',lambda route:route.fulfill(json={'status':'running','phase':'comparing','percent':35,'current':35,'total':100,'baseFile':'Logical/Task/main.st','newFile':'Logical/Task/main.st','message':'Comparing source files'}))
 page.get_by_role('button',name='Run Comparison',exact=True).click()
 page.get_by_text('Comparing source files',exact=True).wait_for()
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':900});page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(150)
  timer=page.locator('.processingTimePopup');header=page.locator('.workspaceTopBar')
  assert timer.is_visible()
  assert timer.evaluate("el=>getComputedStyle(el).position")=='relative'
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
  page.screenshot(path=str(out/f'progress-{width}.png'))
 assert page.locator('.compareDarkCurrent').inner_text().count('main.st')==2
 assert not errors,errors
 browser.close()
server.should_exit=True
print('Uploaded progress, nested folder metadata and inline timer passed at 1440/760/390px.')
