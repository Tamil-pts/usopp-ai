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
with hub.db(True) as db:db.execute("UPDATE items SET stage='quality',quality_id=? WHERE id=?",(other['id'],project['id']))
with sync_playwright() as pw:
 browser=pw.chromium.launch();a=browser.new_context(viewport={'width':1440,'height':1000});b=browser.new_context(viewport={'width':1440,'height':1000});errors=[]
 for context in (a,b):context.add_init_script("window.Notification=class{static permission='granted';constructor(){}close(){}}")
 pa=a.new_page();pb=b.new_page();base=f'http://127.0.0.1:{port}'
 def login(page,who):
  page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base+'/?page=home');page.get_by_label('Username',exact=True).fill(who['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('button',name='Team inbox, 0 unread',exact=True).wait_for(timeout=60000)
 login(pa,admin);login(pb,other)
 pa.get_by_role('button',name='Team inbox, 0 unread',exact=True).click();dialog=pa.get_by_role('dialog',name='Team inbox');dialog.get_by_role('button',name='New chat',exact=True).click();dialog.get_by_role('button',name=other['username'],exact=False).click()
 dialog.get_by_role('button',name='Add praise or shared component',exact=True).click();editor=pa.get_by_role('dialog',name='Praise & shared components');editor.get_by_label('Component title',exact=True).fill('Excellent evidence review');editor.get_by_label('Praise recipient',exact=True).select_option(str(other['id']));editor.get_by_label('Praise badge',exact=True).select_option('quality');editor.get_by_label('Component content',exact=True).fill('Thank you for verifying the PLC offsets.');editor.get_by_role('button',name='Share in chat',exact=True).click();dialog.get_by_role('heading',name='Excellent evidence review',exact=True).wait_for()
 pb.get_by_role('button',name='Team inbox, 1 unread',exact=True).wait_for(timeout=20000);pb.get_by_role('button',name='Team inbox, 1 unread',exact=True).click();inbox=pb.get_by_role('dialog',name='Team inbox');inbox.get_by_role('button',name=admin['username'],exact=False).click();inbox.get_by_role('heading',name='Excellent evidence review',exact=True).wait_for()
 def component(kind,title,content,columns=None):
  dialog.get_by_role('button',name='Add praise or shared component',exact=True).click();editor=pa.get_by_role('dialog',name='Praise & shared components');editor.get_by_label('Component type',exact=True).select_option(kind);editor.get_by_label('Component title',exact=True).fill(title);editor.get_by_label('Component content',exact=True).fill(content)
  if columns:editor.get_by_label('Shared table columns',exact=True).fill(columns)
  editor.get_by_role('button',name='Share in chat',exact=True).click();dialog.get_by_role('heading',name=title,exact=True).wait_for()
 component('checklist','Validation checklist','Check offsets\nReview report');check=inbox.get_by_role('region',name='Shared checklist');check.get_by_label('Check offsets',exact=True).wait_for(timeout=20000);check.get_by_label('Check offsets',exact=True).check();pa.wait_for_function("document.querySelector('section[aria-label=\"Shared checklist\"] input[type=checkbox]')?.checked",timeout=20000)
 component('note','Engineering notes','Initial evidence');noteA=dialog.get_by_role('region',name='Shared note');noteB=inbox.get_by_role('region',name='Shared note');noteB.wait_for(timeout=20000)
 noteA.get_by_role('button',name='Edit component',exact=True).click();noteA.get_by_label('Edit shared note',exact=True).fill('Admin unsaved draft');noteB.get_by_role('button',name='Edit component',exact=True).click();noteB.get_by_label('Edit shared note',exact=True).fill('Reviewer verified evidence');noteB.get_by_role('button',name='Save component',exact=True).click();noteA.get_by_text('A newer version is available.',exact=False).wait_for(timeout=20000);noteA.get_by_role('button',name='Save component',exact=True).click();noteA.get_by_text('Someone changed this component.',exact=False).wait_for();assert noteA.get_by_label('Edit shared note',exact=True).input_value()=='Admin unsaved draft';noteA.get_by_role('button',name='Load latest version',exact=True).click();pa.wait_for_function("document.querySelector('textarea[aria-label=\"Edit shared note\"]')?.value==='Reviewer verified evidence'");noteA.get_by_role('button',name='Save component',exact=True).click();noteA.locator('summary').filter(has_text='Version history').click();noteA.get_by_text('Version 2',exact=False).wait_for()
 component('table','Action owners','Review | Engineer 2','Action, Owner');table=inbox.get_by_role('region',name='Shared table');table.get_by_role('cell',name='Engineer 2',exact=True).wait_for(timeout=20000)
 inbox.get_by_role('button',name='Approvals',exact=True).click();inbox.get_by_role('link',name='Review saved evidence',exact=True).wait_for(timeout=30000);assert project['id'] in inbox.get_by_role('link',name='Review saved evidence',exact=True).get_attribute('href')
 inbox.get_by_role('button',name='Workflows',exact=True).click();inbox.get_by_role('link',name='Open workflow',exact=True).wait_for(timeout=20000)
 dialog.get_by_label('Message',exact=True).fill('Keep unread while reviewing workflow.');dialog.get_by_role('button',name='Send',exact=True).click();pa.wait_for_timeout(5500);assert pb.request.get(base+'/api/team-chat/threads').json()['unread']>=1
 dialog.get_by_role('button',name='Updates',exact=True).click();dialog.get_by_label('Update project',exact=True).select_option(project['id']);dialog.get_by_label('Work update',exact=True).fill('Inbox work update with checked evidence.');dialog.get_by_role('button',name='Save work update',exact=True).click();dialog.get_by_text('WorkHub update saved.',exact=True).wait_for()
 for width in (1440,760,390):
  pa.set_viewport_size({'width':width,'height':900});dialog.get_by_role('button',name='Approvals',exact=True).click();pa.wait_for_timeout(200);assert dialog.get_by_role('region',name='Inbox Approvals').is_visible();assert pa.evaluate('document.documentElement.scrollWidth<=innerWidth+2');Path('.build/inbox-apps-20261114').mkdir(exist_ok=True);pa.screenshot(path=f'.build/inbox-apps-20261114/apps-{width}.png')
 pa.set_viewport_size({'width':1440,'height':1000});dialog.get_by_role('button',name='Chats',exact=True).click();pa.screenshot(path='.build/inbox-apps-20261114/components.png');dialog.get_by_role('button',name='Add praise or shared component',exact=True).click();pa.keyboard.press('Escape');assert dialog.is_visible()
 assert not errors,errors;print('PASS two-user praise, shared checklist, note edit conflict and draft preservation, persistent revision history, table, assigned approval links, workflows, real WorkHub updates, nested Escape and 390-1440px app layouts')
 browser.close();server.should_exit=True
