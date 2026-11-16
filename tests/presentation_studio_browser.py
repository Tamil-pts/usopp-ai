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
output=ROOT/'.build/presentation-studio-20261114';output.mkdir(exist_ok=True)
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1600,'height':1050});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
 base=f'http://127.0.0.1:{port}'
 page.goto(base+'/?page=chatbot&assistTab=presentations')
 page.get_by_label('Username',exact=True).fill(admin['username']);page.get_by_label('Password',exact=True).fill(password)
 page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 page.get_by_label('Presentation prompt').wait_for(timeout=60000)
 page.get_by_label('Presentation prompt').fill('Engineering project review for the delivery team')
 page.locator('.studioSettings select').nth(0).select_option('2')
 source='\n'.join(['Capture project requirements.','Review source files.','Run validation checks.','Record issues and evidence.','Resolve reported findings.','Review the saved revision.','Request independent approval.','Retain the delivery record.'])
 page.locator('.studioSources input[type=file]').set_input_files({'name':'review-source.txt','mimeType':'text/plain','buffer':source.encode()})
 page.get_by_text('review-source.txt',exact=False).wait_for()
 page.get_by_role('button',name='Start without AI',exact=True).click()
 page.get_by_label('Editable slide canvas').wait_for(timeout=30000)
 page.get_by_label('Selected object text').fill('Engineering delivery review')
 page.get_by_role('button',name='Save revision',exact=True).click()
 page.get_by_text('Saved revision 2',exact=True).wait_for()
 assert page.get_by_label('Editable slide canvas').get_by_text('Engineering delivery review',exact=True).count()==1
 page.locator('.studioCanvasHeading').get_by_role('button',name='Text',exact=True).click()
 page.get_by_label('Selected object text').fill('Review the original evidence')
 page.get_by_label('Object y',exact=True).fill('570')
 page.get_by_role('button',name='Save revision',exact=True).click();page.get_by_text('Saved revision 3',exact=True).wait_for()
 page.locator('.studioExport>summary').click()
 with page.expect_download() as downloaded:page.get_by_role('button',name='Editable PowerPoint',exact=True).click()
 downloaded.value.save_as(output/'browser-edited.pptx')
 page.wait_for_function("!document.querySelector('.studioStatus')")
 with page.expect_download() as downloaded:page.locator('.studioExport').get_by_role('button',name='PDF',exact=True).click()
 downloaded.value.save_as(output/'browser-edited.pdf')
 page.wait_for_function("!document.querySelector('.studioStatus')")
 page.locator('.studioExport>summary').click()
 url=page.url;assert 'presentation=' in url
 page.reload();page.get_by_label('Editable slide canvas').wait_for(timeout=30000)
 page.get_by_label('Edit heading',exact=True).click();assert page.get_by_label('Selected object text').input_value()=='Engineering delivery review'
 # Pointer movement changes persisted structured coordinates, not just the visible image.
 target=page.get_by_label('Edit heading',exact=True).bounding_box()
 before=float(page.get_by_label('Object x',exact=True).input_value())
 page.mouse.move(target['x']+30,target['y']+30);page.mouse.down();page.mouse.move(target['x']+60,target['y']+35,steps=4);page.mouse.up()
 assert float(page.get_by_label('Object x',exact=True).input_value())>before
 page.get_by_role('button',name='Save revision',exact=True).click();page.get_by_text('Saved revision 4',exact=True).wait_for()
 for width in (1600,1024,390):
  page.set_viewport_size({'width':width,'height':1050});page.wait_for_timeout(100)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  page.screenshot(path=str(output/f'studio-{width}.png'),full_page=True)
 assert not errors,errors
 browser.close();server.should_exit=True
 from pptx import Presentation
 prs=Presentation(output/'browser-edited.pptx');assert len(prs.slides)==2
 assert any(shape.has_text_frame and 'Review the original evidence' in shape.text.replace('\n',' ') for shape in prs.slides[0].shapes)
 print('PASS source upload, starter generation, text editing, native object movement, saved revisions, editable PPTX/PDF downloads, refresh/direct URL and 390-1600px layouts')
