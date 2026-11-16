"""Real UI/export checks against isolated accounts and storage, never live projects."""
import os,sys,tempfile,threading,time,socket,json
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
os.environ.update(USOPP_DATA_ROOT=tempfile.mkdtemp(prefix='usopp-presentation-browser-'),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
import uvicorn
from virtual_plc.server import create_app
from backend.core import accounts
from playwright.sync_api import sync_playwright
app=create_app();password='Studio.Check.2026!'
admin=accounts.store.register('studio_browser',password,'Engineer','Fixture',role='admin')
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True).start()
while not server.started:time.sleep(.05)
output=ROOT/'.build/rs485-decoder-browser';output.mkdir(exist_ok=True)
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(f'http://127.0.0.1:{port}/?page=chatbot&assistTab=chat')
 page.get_by_label('Username',exact=True).fill(admin['username']);page.get_by_label('Password',exact=True).fill(password)
 page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 page.locator('.studioWelcomeCards button').filter(has_text='Log Decoder 2').wait_for(timeout=60000)
 page.locator('.studioWelcomeCards button').filter(has_text='Log Decoder 2').click()
 dialog=page.get_by_role('dialog',name='Log Decoder 2',exact=False)
 dialog.wait_for()
 frame=[0]*56
 for i,v in {0:253,1:1,2:90,3:56,6:16,7:11,8:234,9:7,20:44,21:1,54:123,55:240}.items():frame[i]=v
 capture=' '.join(f'{b:02X}' for b in frame)
 dialog.get_by_label('Received bytes / Docklight RX log').fill('16/11/2026 09:10:00.123 [RX] - '+capture)
 dialog.get_by_role('button',name='Decode received frames',exact=True).click()
 assert dialog.get_by_role('alert').inner_text()=='Select the device byte order for 2-byte fields.'
 dialog.get_by_label('Device byte order',exact=False).select_option('little')
 dialog.get_by_role('button',name='Decode received frames',exact=True).click()
 assert dialog.locator('section tbody tr').count()==40
 assert dialog.locator('section').get_by_text('2026',exact=True).is_visible()
 assert dialog.locator('section').get_by_text('300',exact=True).is_visible()
 with page.expect_download() as pending:
  dialog.get_by_role('button',name='Export all captures CSV',exact=True).click()
 download=pending.value;download.save_as(str(output/'decoded.csv'))
 import csv
 with (output/'decoded.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
 assert rows[0]==['Tag','Parameter','Offset','Type','Raw decimal bytes','Decoded value','Finding']
 assert len(rows)==41
 assert any(row[1]=='CRC' and 'not verified' in row[-1] for row in rows[1:])
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(100)
  box=dialog.bounding_box();assert box['x']>=0 and box['x']+box['width']<=width+1
  page.screenshot(path=str(output/f'decoder-{width}.png'))
 page.keyboard.press('Escape');assert not dialog.count()
 assert not errors,errors
 browser.close()
server.should_exit=True
print('RS485 browser: required byte order, 40 decoded fields, values, CSV, responsive modal and Escape passed.')
