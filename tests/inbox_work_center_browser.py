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
output=ROOT/'.build/inbox-work-center-browser';output.mkdir(exist_ok=True)
from backend.core.workhub import store as hub
reviewer=accounts.store.register('time_reviewer',password,'Reviewer','Fixture',role='admin')
project=hub.create(admin,{'title':'Inbox project delivery','quality_id':reviewer['id']})
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(f'http://127.0.0.1:{port}/?page=home')
 page.get_by_label('Username',exact=True).fill(admin['username']);page.get_by_label('Password',exact=True).fill(password)
 page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 ribbon=page.get_by_role('group',name='WorkHub submenu',exact=True)
 ribbon.get_by_role('button',name='Inbox',exact=True).wait_for(timeout=60000)
 assert not page.get_by_role('button',name='My Work & Approvals',exact=True).count()
 ribbon.get_by_role('button',name='Inbox',exact=True).click()
 page.get_by_role('group',name='Inbox options').get_by_role('button',name='My Work',exact=True).click()
 dialog=page.get_by_role('dialog',name='Team inbox',exact=True)
 dialog.get_by_role('heading',name='My Work',exact=True).wait_for()
 dialog.get_by_role('button',name='Tasks',exact=True).click()
 dialog.get_by_role('button',name='New task',exact=True).click()
 dialog.get_by_label('Task project',exact=True).select_option(project['id'])
 dialog.get_by_label('Assign task to',exact=True).select_option(str(reviewer['id']))
 dialog.get_by_label('Task title',exact=True).fill('Review PLC result evidence')
 dialog.get_by_label('Task description',exact=True).fill('Inspect the saved validation report.')
 dialog.get_by_role('button',name='Create and assign task',exact=True).click()
 dialog.get_by_text('Task created and assigned in WorkHub.',exact=True).wait_for()
 with hub.db() as db:
  task=dict(db.execute("SELECT * FROM items WHERE title='Review PLC result evidence'").fetchone())
 assert task['owner_id']==reviewer['id']
 dialog.get_by_role('button',name='New task',exact=True).click()
 dialog.get_by_label('Task title',exact=True).fill('Retained task draft')
 dialog.get_by_role('button',name='Chats',exact=True).click()
 dialog.get_by_role('button',name='Tasks',exact=True).click()
 dialog.get_by_role('button',name='New task',exact=True).click()
 assert dialog.get_by_label('Task title',exact=True).input_value()=='Retained task draft'
 dialog.get_by_role('button',name='Keep draft and close',exact=True).click()
 dialog.get_by_role('button',name='Timesheets',exact=True).click()
 dialog.get_by_role('button',name='Log hours',exact=True).click()
 dialog.get_by_label('Log hours project',exact=True).select_option(project['id'])
 dialog.get_by_label('Log hours task',exact=True).select_option(task['id'])
 dialog.get_by_label('Hours worked',exact=True).fill('1')
 dialog.get_by_label('Minutes worked',exact=True).fill('30')
 dialog.get_by_label('What work was done',exact=True).fill('Verified source evidence and documented findings.')
 dialog.get_by_role('button',name='Save hours for review',exact=True).click()
 dialog.get_by_text('Work and hours saved.',exact=False).wait_for()
 page.wait_for_timeout(250)
 assert dialog.locator('.workCenterMetrics').inner_text().count('1.50 h')==2
 with hub.db() as db:entry=dict(db.execute('SELECT * FROM updates WHERE author_id=?',(admin['id'],)).fetchone())
 assert entry['minutes']==90 and entry['time_status']=='submitted'
 hub.time_review(reviewer,entry['id'],{'status':'approved'})
 dialog.get_by_role('button',name='Refresh My Timesheet',exact=True).click()
 page.wait_for_timeout(500)
 assert '1.50 h' in dialog.locator('.workCenterMetrics article').nth(1).inner_text()
 with page.expect_download() as pending:dialog.get_by_role('link',name='Export timesheet CSV',exact=True).click()
 pending.value.save_as(str(output/'timesheet.csv'))
 assert 'Verified source evidence' in (output/'timesheet.csv').read_text(encoding='utf-8-sig')
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(150)
  box=dialog.bounding_box();assert box['x']>=0 and box['x']+box['width']<=width+1
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
  page.screenshot(path=str(output/f'timesheet-{width}.png'))
 page.keyboard.press('Escape');dialog.wait_for(state='hidden')
 page.set_viewport_size({'width':1440,'height':900})
 for theme in ('Light','Dark','Retro','Classic','Monochrome'):
  page.get_by_role('button',name='Choose appearance theme',exact=True).click()
  page.get_by_role('menuitemradio',name=theme+' theme',exact=True).click()
  assert ribbon.get_by_role('button',name='Inbox',exact=True).is_visible()
  page.screenshot(path=str(output/f'ribbon-{theme.lower()}.png'))
 assert not errors,errors
 browser.close()
server.should_exit=True
print('Inbox navigation, task assignment, saved time, reviewer approval totals, CSV, 390/760/1440 layouts and five themes passed.')
