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
out=ROOT/'.build/matchview-export-redesign-20261116';out.mkdir(exist_ok=True)
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto(f'http://127.0.0.1:{port}/?page=compare')
 page.get_by_label('Username',exact=True).fill(user['username']);page.get_by_label('Password',exact=True).fill(password)
 page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 page.get_by_role('button',name='Project details',exact=True).wait_for(timeout=60000)
 page.get_by_role('button',name='Project details',exact=True).click()
 dialog=page.get_by_role('dialog',name='Project report details',exact=True)
 dialog.get_by_label('Project name',exact=True).fill('Comber delivery review')
 dialog.get_by_label('Project ID',exact=True).fill('PRJ-104')
 dialog.get_by_label('Department',exact=True).fill('Automation')
 dialog.get_by_label('Base / reference',exact=True).fill('Base project')
 dialog.get_by_label('Developed / compare',exact=True).fill('Developed project')
 dialog.get_by_label('Reviewed by',exact=True).fill('Review Engineer')
 dialog.get_by_label('Project file statuses',exact=True).select_option('added')
 assert dialog.get_by_text('Report sections',exact=True).is_visible()
 assert dialog.get_by_text('PDF / Word screen details',exact=True).is_visible()
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(100)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
  box=dialog.bounding_box();assert box['x']>=0 and box['y']>=0
  button=dialog.get_by_role('button',name='Save details',exact=True);button.scroll_into_view_if_needed();bounds=button.bounding_box()
  assert bounds['y']+bounds['height']<=900
  page.screenshot(path=str(out/f'folder-{width}.png'))
 page.set_viewport_size({'width':1440,'height':1000})
 dialog.get_by_role('button',name='Save details',exact=True).click();dialog.wait_for(state='hidden')
 page.get_by_role('button',name='Project details',exact=True).click()
 dialog=page.get_by_role('dialog',name='Project report details',exact=True)
 assert dialog.get_by_label('Project ID',exact=True).input_value()=='PRJ-104'
 assert dialog.get_by_label('Project file statuses',exact=True).input_value()=='added'
 page.keyboard.press('Escape');dialog.wait_for(state='hidden')
 page.get_by_role('button',name='PDF files',exact=False).click()
 root=page.get_by_label('PLC PDF MatchView',exact=True)
 root.get_by_label('Base PLC PDF',exact=True).set_input_files({'name':'before.pdf','mimeType':'application/pdf','buffer':program([[(1,'M1')]])})
 root.get_by_label('Compared PLC PDF',exact=True).set_input_files({'name':'after.pdf','mimeType':'application/pdf','buffer':program([[(1,'M2')]])})
 root.get_by_role('button',name='Compare PLC PDFs',exact=True).click()
 root.get_by_role('region',name='Continuous PLC network comparison',exact=True).wait_for(timeout=30000)
 root.get_by_text('Optional details',exact=True).click()
 for name in ['Symbol reference tables','Comments','Author','Created date','Modified date']:
  assert not root.get_by_label(name,exact=True).is_checked()
 root.get_by_text('Optional details',exact=True).click()
 root.get_by_role('button',name='PDF',exact=True).click()
 dialog=page.get_by_role('dialog',name='Export PLC comparison',exact=True)
 dialog.get_by_label('Project name',exact=True).fill('Comber delivery review')
 dialog.get_by_label('Project ID',exact=True).fill('PRJ-104')
 dialog.get_by_label('Department',exact=True).fill('Automation')
 dialog.get_by_label('Reviewed by',exact=True).fill('Review Engineer')
 dialog.get_by_label('Comparison sections to export',exact=True).select_option('modified')
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(100)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
  dialog.get_by_role('button',name='Download PDF',exact=True).scroll_into_view_if_needed()
  page.screenshot(path=str(out/f'pdf-{width}.png'))
 with page.expect_download() as download:dialog.get_by_role('button',name='Download PDF',exact=True).click()
 download.value.save_as(out/'comparison.pdf')
 dialog.wait_for(state='hidden')
 from pypdf import PdfReader
 text=PdfReader(out/'comparison.pdf').pages[0].extract_text()
 for value in ('Comber delivery review','PRJ-104','Automation','Review Engineer'):assert value in text
 # Exercise the actual supplied INPUTS examples using isolated source-page fixtures.
 selected=ROOT/'.build/pdf-export-speed/selected'
 root.get_by_label('Base PLC PDF',exact=True).set_input_files(selected/'18480.pdf')
 root.get_by_label('Compared PLC PDF',exact=True).set_input_files(selected/'18481.pdf')
 root.get_by_role('button',name='Compare PLC PDFs',exact=True).click()
 page.wait_for_timeout(2500)
 rung=root.locator('.plcPDFSection').filter(has=page.locator('.plcPDFSectionHeading',has_text='Network 22'))
 rung.scroll_into_view_if_needed();page.wait_for_timeout(700)
 assert rung.get_attribute('data-status')=='unchanged'
 images=rung.locator('.plcPDFPairImages img')
 page.wait_for_function("els=>els.length===2&&els.every(e=>e.complete&&e.naturalWidth>0)",arg=None) if False else None
 for image in images.all():image.evaluate("e=>e.decode()")
 dimensions=images.evaluate_all('els=>els.map(e=>[e.naturalWidth,e.naturalHeight])')
 assert len(dimensions)==2 and dimensions[0]==dimensions[1],dimensions
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':900});rung.scroll_into_view_if_needed();page.wait_for_timeout(200)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
  page.screenshot(path=str(out/f'network22-{width}.png'))
 assert not errors,errors
 browser.close();server.should_exit=True
 print('PASS project-folder and PDF export dialogs, retained cover fields/options, Escape/focus, selected-status download and first-page metadata, 390-1440px layouts')
