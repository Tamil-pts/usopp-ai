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
from io import BytesIO
from PIL import Image
png=BytesIO();Image.new('RGB',(10,10),'green').save(png,format='PNG')
with sync_playwright() as pw:
 browser=pw.chromium.launch();a=browser.new_context(viewport={'width':1440,'height':1000});b=browser.new_context(viewport={'width':1440,'height':1000});errors=[]
 # Deterministic native-alert adapter verifies browser calls without claiming OS delivery.
 b.add_init_script("""window.__alerts=[];window.Notification=class {static permission='granted';static requestPermission(){return Promise.resolve('granted')}constructor(title,options){window.__alerts.push({title,...options})}close(){}}""")
 pa=a.new_page();pb=b.new_page();base=f'http://127.0.0.1:{port}'
 def login(page,who):
  page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base+'/?page=home');page.get_by_label('Username',exact=True).fill(who['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('button',name='Team inbox, 0 unread',exact=True).wait_for(timeout=60000)
 login(pa,admin);login(pb,other)
 pa.get_by_role('button',name='Team inbox, 0 unread',exact=True).click();dialog=pa.get_by_role('dialog',name='Team inbox',exact=True);dialog.wait_for()
 dialog.get_by_role('button',name='New chat',exact=True).click();dialog.get_by_role('button',name=other['username'],exact=False).click();dialog.get_by_label('Message',exact=True).fill('Engineering chat browser fixture');dialog.get_by_role('button',name='Choose emoji',exact=True).click();dialog.locator('.team-chat-emojis button').first.click();dialog.get_by_role('button',name='Send',exact=True).click();dialog.get_by_role('log').get_by_text('Engineering chat browser fixture',exact=False).wait_for()
 pb.get_by_role('button',name='Team inbox, 1 unread',exact=True).wait_for(timeout=15000);pb.wait_for_function('window.__alerts.length > 0')
 pb.get_by_role('button',name='Team inbox, 1 unread',exact=True).click();inbox=pb.get_by_role('dialog',name='Team inbox',exact=True);inbox.get_by_role('button',name=admin['username'],exact=False).click();inbox.get_by_role('log').get_by_text('Engineering chat browser fixture',exact=False).wait_for()
 inbox.get_by_label('Message',exact=True).fill('Reviewed - thanks');inbox.get_by_role('button',name='Send',exact=True).click();dialog.get_by_role('log').get_by_text('Reviewed - thanks',exact=True).wait_for(timeout=15000)
 pa.locator('.team-chat-composer input[type=file]').set_input_files([{'name':'fixture.csv','mimeType':'text/csv','buffer':b'tag,value\n1,25'},{'name':'pixel.png','mimeType':'image/png','buffer':png.getvalue()}]);dialog.get_by_role('button',name='Send',exact=True).click()
 inbox.get_by_role('link',name='fixture.csv',exact=False).wait_for(timeout=15000);inbox.get_by_alt_text('pixel.png',exact=True).wait_for();assert pb.locator('.team-chat-attachment img').evaluate('(img)=>img.complete && img.naturalWidth > 0')
 inbox.get_by_role('button',name='Send test alert',exact=True).click();assert pb.evaluate("window.__alerts.some(x=>x.title==='uSOPp.ai test notification')")
 pa.screenshot(path='.build/team-chat-20261113/inbox.png',full_page=True)
 dialog.get_by_role('button',name='Close team inbox',exact=True).click();pa.reload();pa.get_by_role('button',name='Team inbox, 0 unread',exact=True).click();dialog=pa.get_by_role('dialog',name='Team inbox',exact=True);dialog.get_by_role('button',name=other['username'],exact=False).click();dialog.get_by_role('log').get_by_text('Reviewed - thanks',exact=True).wait_for();dialog.get_by_role('link',name='fixture.csv',exact=False).wait_for()
 pa.set_viewport_size({'width':390,'height':844});assert pa.evaluate('document.documentElement.scrollWidth <= innerWidth + 2');dialog.get_by_role('button',name='Back to conversations',exact=True).click();dialog.get_by_role('button',name='Close team inbox',exact=True).click()
 assert not errors,errors;print('PASS two-account messages, emoji, unread badge, history reload, private CSV/image sharing, native-alert adapter and mobile popup')
 browser.close();server.should_exit=True
