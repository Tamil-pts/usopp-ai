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
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1600,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));base=f'http://127.0.0.1:{port}'
 page.goto(base+'/?page=electrical');page.get_by_label('Username',exact=True).fill(admin['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('region',name='Industrial control circuit editor').wait_for(timeout=60000)
 def action(name,state):
  page.get_by_role('button',name=name,exact=True).click();page.get_by_role('status').filter(has_text='Stable').filter(has_text=state).wait_for()
 action('Run step','K1: OFF');action('Press Start','K1: ON');action('Release Start','K1: ON');action('Press Stop','K1: OFF');action('Release Stop','K1: OFF');action('Press Start','K1: ON');action('Trip overload','K1: OFF');action('Reset overload','K1: ON');action('Release Start','K1: ON');action('Trip overload','K1: OFF');action('Reset overload','K1: OFF')
 page.get_by_label('Control circuit name',exact=True).fill('Browser verified industrial starter');page.get_by_role('button',name='Save circuit',exact=True).click();page.reload();page.get_by_label('Control circuit name',exact=True).wait_for();assert page.get_by_label('Control circuit name',exact=True).input_value()=='Browser verified industrial starter'
 action('Press Start','K1: ON');page.screenshot(path='.build/electrical-reconstruction-20261113/industrial-control.png',full_page=True)
 page.get_by_role('button',name='Select K1',exact=True).click();page.get_by_role('heading',name='Symbol properties',exact=True).wait_for()
 page.get_by_label('Wire from',exact=True).select_option('PS1:plus');page.get_by_label('Wire to',exact=True).select_option('PS1:minus');page.get_by_role('button',name='Connect terminals',exact=True).click();page.get_by_role('button',name='Run step',exact=True).click();page.get_by_role('alert').filter(has_text='short circuit').wait_for();page.get_by_role('button',name='Save circuit',exact=True).click()
 page.get_by_role('button',name='Drawing reconstruction',exact=True).click();page.get_by_role('region',name='Industrial electrical reconstruction').wait_for();assert page.get_by_role('alert').count()==0
 page.get_by_role('button',name='Control circuit',exact=True).click()
 for width in (1024,390):
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(150);assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
 assert not errors,errors
 print('PASS start, hold, stop, overload, saved drawing reload, reconstruction API and responsive layouts; no browser errors')
 browser.close();server.should_exit=True
