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
from backend.core import workhub_organization as org
team=org.save_unit(admin,{'kind':'team','name':'Automation Team','version':0})
for person in (admin,other):org.save_profile(admin,person['id'],{'team_ids':[team['id']],'version':0})
from io import BytesIO
import zipfile
archive=BytesIO()
with zipfile.ZipFile(archive,'w') as z:z.writestr('Main.st','PROGRAM _CYCLIC\nEND_PROGRAM')
with sync_playwright() as pw:
 browser=pw.chromium.launch();a=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Asia/Kolkata');b=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Asia/Kolkata');errors=[]
 a.add_init_script("window.__asked=0;window.Notification=class{static permission='default';static requestPermission(){window.__asked++;this.permission='granted';return Promise.resolve('granted')}constructor(){}close(){}}")
 pa=a.new_page();pb=b.new_page();base=f'http://127.0.0.1:{port}'
 def login(page,who):
  page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base+'/?page=home');page.get_by_label('Username',exact=True).fill(who['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('button',name='Team inbox, 0 unread',exact=True).wait_for(timeout=60000)
 login(pa,admin);login(pb,other);pa.get_by_role('button',name='Team inbox, 0 unread',exact=True).click();dialog=pa.get_by_role('dialog',name='Team inbox');dialog.wait_for();assert pa.evaluate('window.__asked')==1
 dialog.get_by_role('button',name='Automation Team',exact=False).click();dialog.get_by_label('Message',exact=True).fill('Discuss engineering evidence');pa.locator('.team-chat-composer input[type=file]').set_input_files({'name':'source.zip','mimeType':'application/zip','buffer':archive.getvalue()});dialog.get_by_role('button',name='Send',exact=True).click();dialog.get_by_role('link',name='source.zip',exact=False).wait_for()
 pb.get_by_role('button',name='Team inbox, 1 unread',exact=True).wait_for(timeout=20000);pb.get_by_role('button',name='Team inbox, 1 unread',exact=True).click();inbox=pb.get_by_role('dialog',name='Team inbox');inbox.get_by_role('button',name='Automation Team',exact=False).click();inbox.get_by_role('link',name='source.zip',exact=False).wait_for()
 with pb.expect_download() as dl:inbox.get_by_role('link',name='source.zip',exact=False).click()
 assert Path(dl.value.path()).read_bytes()==archive.getvalue()
 dialog.get_by_role('button',name='Meetings',exact=True).click();dialog.get_by_role('button',name='Schedule meeting',exact=True).click();dialog.get_by_label('Meeting title',exact=True).fill('Engineering review')
 dates=pa.evaluate("()=>[1,2].map(h=>{let d=new Date(Date.now()+h*3600000);let pad=n=>String(n).padStart(2,'0');return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'T'+pad(d.getHours())+':'+pad(d.getMinutes())})")
 dialog.get_by_label('Meeting starts',exact=True).fill(dates[0]);dialog.get_by_label('Meeting ends',exact=True).fill(dates[1]);dialog.get_by_label('Meeting agenda',exact=True).fill('Review test evidence and remaining tasks.');dialog.get_by_role('button',name='Save meeting invitation',exact=True).click();dialog.get_by_role('heading',name='Engineering review',exact=False).wait_for()
 assert dialog.get_by_role('button',name='Join local meeting',exact=True).is_disabled()
 with pa.expect_download() as dl:dialog.get_by_role('link',name='Add to calendar',exact=True).click()
 assert b'Engineering review' in Path(dl.value.path()).read_bytes()
 inbox.get_by_role('button',name='Meetings',exact=True).click();inbox.get_by_role('button',name='Accept',exact=True).wait_for(timeout=20000);inbox.get_by_role('button',name='Accept',exact=True).click();inbox.get_by_text('1 accepted',exact=False).wait_for()
 Path('.build/team-collaboration-20261114').mkdir(exist_ok=True);pa.screenshot(path='.build/team-collaboration-20261114/meetings.png');pa.set_viewport_size({'width':390,'height':900});assert dialog.locator('.teamMeetings').is_visible();pa.screenshot(path='.build/team-collaboration-20261114/meetings-mobile.png');pa.set_viewport_size({'width':1440,'height':1000});dialog.get_by_role('button',name='Chats',exact=True).click();dialog.get_by_role('button',name='Create task / project',exact=True).first.click();work=dialog.locator('.messageWork').first;work.get_by_label('Create',exact=True).select_option('task');work.get_by_label('Parent project',exact=True).select_option(project['id']);work.get_by_label('Work title',exact=True).fill('Follow-up from chat');work.get_by_role('button',name='Create work item',exact=True).click();work.get_by_role('link',name='Open created work',exact=True).wait_for()
 dialog.get_by_role('button',name='New chat',exact=True).click();dialog.get_by_role('button',name='Create group',exact=True).click();dialog.get_by_label('Group name',exact=True).fill('Review team');dialog.get_by_label(other['username'],exact=True).check();dialog.get_by_role('button',name='Create group',exact=True).click();dialog.locator('.team-chat-peer').get_by_text('Review team',exact=True).wait_for()
 for width in (1440,760,390):
  pa.set_viewport_size({'width':width,'height':900});Path('.build/team-collaboration-20261114').mkdir(exist_ok=True);pa.screenshot(path=f'.build/team-collaboration-20261114/inbox-{width}.png');assert pa.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
 assert not errors,errors;print('PASS team defaults, ZIP byte-for-byte sharing, group creation, notification permission request, scheduling, calendar export, participant RSVP, message-to-task permissions and mobile layout; live Jitsi calls not available')
 browser.close();server.should_exit=True
