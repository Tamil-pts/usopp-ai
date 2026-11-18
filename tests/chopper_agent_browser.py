import os,sys,tempfile,threading,time,socket,json
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
os.environ.update(USOPP_DATA_ROOT=tempfile.mkdtemp(prefix='usopp-agent-browser-'),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
import uvicorn
from virtual_plc.server import create_app
from backend.core import accounts
from playwright.sync_api import sync_playwright,expect
app=create_app();password='Agent.Browser.2026!'
user=accounts.store.register('agent_browser',password,'Engineer','Fixture',role='admin')
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True).start()
while not server.started:time.sleep(.05)
out=ROOT/'.build/chopper-agent-browser';out.mkdir(exist_ok=True)
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)));base=f'http://127.0.0.1:{port}'
 page.goto(base+'/?page=chatbot&assistTab=agent')
 page.get_by_label('Username',exact=True).fill(user['username']);page.get_by_label('Password',exact=True).fill(password)
 page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 page.get_by_role('heading',name='Chopper Agent workspace',exact=True).wait_for(timeout=60000)
 page.get_by_role('button',name='Run safety checks',exact=True).click()
 expect(page.get_by_text('20 safety fixtures passed',exact=True)).to_be_visible(timeout=30000)
 print('PASS actual authenticated agent routes and installation evaluation',flush=True)
 page.get_by_role('button',name='Text to SQL',exact=True).click()
 page.get_by_label('Upload agent worksheet',exact=True).set_input_files({'name':'hours.csv','mimeType':'text/csv','buffer':b'Person,Hours\nOne,2\nTwo,3\n'})
 expect(page.get_by_text('hours.csv',exact=True)).to_be_visible()
 page.get_by_label('Agent question',exact=True).fill('What is the total Hours?')
 page.get_by_role('button',name='Prepare & validate query',exact=True).click()
 page.get_by_role('button',name='Publish query result',exact=True).wait_for(timeout=30000)
 assert 'SUM(c1)' in page.get_by_label('Validated agent result',exact=True).inner_text()
 page.get_by_role('button',name='Publish query result',exact=True).click()
 page.get_by_role('heading',name='Worksheet query result',exact=True).wait_for(timeout=30000)
 assert page.get_by_label('Validated agent result',exact=True).locator('td').inner_text()=='5'
 with page.expect_download() as download:page.get_by_role('button',name='Export result CSV',exact=True).click()
 download.value.save_as(str(out/'query.csv'));assert '5' in (out/'query.csv').read_text(encoding='utf-8-sig')
 print('PASS owned CSV -> dry-run SQL -> reviewed publish -> CSV download',flush=True)
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(150)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),f'Overflow at {width}'
  page.screenshot(path=str(out/f'agent-{width}.png'))
 page.set_viewport_size({'width':1440,'height':1000})
 page.get_by_role('button',name='Chat',exact=True).click()
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(150)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
  page.screenshot(path=str(out/f'chat-{width}.png'))
 page.set_viewport_size({'width':1440,'height':1000})
 page.get_by_label('Choose appearance theme',exact=True).click()
 page.get_by_role('menuitemradio',name='Dark theme',exact=True).click()
 page.screenshot(path=str(out/'chat-dark.png'))
 page.get_by_label('Choose appearance theme',exact=True).click()
 page.get_by_role('menuitemradio',name='Light theme',exact=True).click()
 page.get_by_text('Build a clear prompt',exact=True).click()
 page.get_by_label('Exact target / scope',exact=True).fill('GC 30 / TAG_CODE 653')
 page.get_by_label('Question or observed result',exact=True).fill('Check the missing shown-value reference.')
 page.get_by_role('button',name='Use this prompt',exact=True).click()
 expect(page.get_by_label('Message Chopper',exact=True)).to_have_value(__import__('re').compile('.*TAG_CODE 653.*',__import__('re').S))
 assert 'Do not invent missing values' in page.get_by_label('Message Chopper',exact=True).input_value()
 page.get_by_role('button',name='KnowHub',exact=True).click()
 page.get_by_role('tab',name='Agent controls & evaluation',exact=True).click()
 page.get_by_role('heading',name='Chopper Agent workspace',exact=True).wait_for()
 page.go_back();page.get_by_label('Message Chopper',exact=True).wait_for()
 page.get_by_role('button',name='KnowHub',exact=True).click()
 page.get_by_role('tab',name='Project answer training',exact=True).click()
 expect(page.get_by_text('Collect more reviewed training evidence',exact=True)).to_be_visible(timeout=30000)
 page.goto(base+'/?page=chatbot&assistTab=training');page.reload();expect(page.get_by_text('Collect more reviewed training evidence',exact=True)).to_be_visible(timeout=30000)
 print('PASS guided prompt fills draft, mode navigation, browser Back and direct training refresh',flush=True)
 for width in (1440,390):
  page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(150)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
  page.screenshot(path=str(out/f'training-{width}.png'))
 assert not errors,errors
 (out/'result.json').write_text(json.dumps({'passed':True,'pageErrors':errors,'widths':[1440,760,390],'isolation':'Temporary data root; no live records changed'},indent=2))
 browser.close();server.should_exit=True
