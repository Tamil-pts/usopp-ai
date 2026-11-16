import os,sys,tempfile,threading,time,socket
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
os.environ.update(USOPP_DATA_ROOT=tempfile.mkdtemp(prefix='usopp-history-'),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
import uvicorn
from virtual_plc.server import create_app
app=create_app()
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
 page.goto(base+'/?page=home');page.get_by_label('Username',exact=True).fill(admin['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('button',name='Choose appearance theme',exact=True).wait_for(timeout=60000)
 for theme in ('Light','Dark','Retro','Classic','Monochrome'):
  page.get_by_role('button',name='Choose appearance theme',exact=True).click();picker=page.get_by_role('menu',name='Appearance themes',exact=True);picker.get_by_role('menuitemradio',name=theme+' theme',exact=True).click();page.wait_for_function('(t)=>document.documentElement.dataset.workspaceTheme===t',arg=theme.lower())
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
  page.get_by_text('Total projects',exact=True).wait_for()
  page.screenshot(path='.build/navigation-themes-20261113/'+theme.lower()+'.png',full_page=True)
 page.reload();page.get_by_role('button',name='Choose appearance theme',exact=True).wait_for();assert page.locator('html').get_attribute('data-workspace-theme')=='monochrome'
 page.get_by_role('button',name='Collapse sidebar',exact=True).click();assert page.locator('.rail').get_attribute('data-collapsed')=='true';page.reload();page.get_by_role('button',name='Expand sidebar',exact=True).wait_for();page.get_by_role('button',name='Expand sidebar',exact=True).click()
 assert page.locator('.railBrand').get_attribute('aria-label')=='Collapse sidebar'
 assert page.get_by_text('Compact view',exact=True).count()==0
 page.get_by_role('button',name='Account menu for '+admin['username']).click()
 menu=page.get_by_role('menu',name='Your account');menu.wait_for()
 assert menu.evaluate('(e)=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+20,r.y+20))}'), 'Account menu obscured by submenu'
 page.screenshot(path='.build/navigation-themes-20261113/account-layer.png')
 page.keyboard.press('Escape')
 page.get_by_role('button',name='Documents',exact=True).click();page.get_by_role('group',name='Documents options').get_by_role('button',name='Requirements / FRD',exact=True).wait_for();page.keyboard.press('Escape')
 page.get_by_role('navigation',name='Main navigation',exact=True).get_by_role('button',name='PLC',exact=False).click();page.get_by_role('button',name='Spin Connect Workspace',exact=True).click();page.get_by_role('group',name='Spin Connect tools').get_by_role('button',name='DataInspect',exact=True).wait_for();page.keyboard.press('Escape')
 page.get_by_role('button',name='Choose appearance theme',exact=True).focus();page.keyboard.press('ArrowDown');page.wait_for_function("document.activeElement?.getAttribute('role')==='menuitemradio'");page.keyboard.press('End');assert page.get_by_role('menuitemradio',name='Monochrome theme',exact=True).evaluate('(e)=>e===document.activeElement');page.keyboard.press('Escape')
 for width in (1200,1024,760,390):
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(150);assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'),width
  page.get_by_role('button',name='Choose appearance theme',exact=True).click();picker=page.get_by_role('menu',name='Appearance themes',exact=True);assert picker.bounding_box()['x']>=0;picker.get_by_role('menuitemradio',name='Retro theme',exact=True).click()
 page.screenshot(path='.build/navigation-themes-20261113/mobile.png',full_page=True)
 page.set_viewport_size({'width':1600,'height':1050});page.goto(base+'/?page=settings#settings/appearance');page.get_by_role('button',name='Classic theme',exact=True).wait_for(timeout=30000);page.get_by_role('button',name='Classic theme',exact=True).click();page.wait_for_function("document.documentElement.dataset.workspaceTheme==='classic'")
 assert not errors,errors;print('PASS Settings gallery, five theme presets, account persistence, collapse persistence, dropdowns, keyboard controls and 390-1600px layouts')
 browser.close();server.should_exit=True
