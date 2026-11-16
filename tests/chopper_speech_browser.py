import os,sys,tempfile,threading,time,socket
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
os.environ.update(USOPP_DATA_ROOT=tempfile.mkdtemp(prefix='usopp-history-'),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
os.environ['USOPP_CHOPPER_SPEECH_MODEL']=str(ROOT/'local_ai/models/whisper-small')
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
 browser=pw.chromium.launch(args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+str(ROOT/'.build/chopper-english-speech.wav')]);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));base=f'http://127.0.0.1:{port}'
 page.goto(base+'/?page=chatbot');page.get_by_label('Username',exact=True).fill(admin['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 page.get_by_role('button',name='Speech to text',exact=True).wait_for(timeout=60000)
 sent=[];page.on('request',lambda r:sent.append(r.url) if '/api/assist/start' in r.url else None)
 page.get_by_label('Message Chopper',exact=True).fill('Keep this draft.')
 page.get_by_role('button',name='Speech to text',exact=True).click();dialog=page.get_by_role('dialog',name='Speak to Chopper');dialog.wait_for()
 for language in ('ta','hi','tanglish','auto','en'):dialog.get_by_label('Speech language',exact=True).select_option(language)
 dialog.get_by_role('button',name='Upload audio',exact=True).wait_for();page.wait_for_function("!document.querySelector('.speechActions button').disabled")
 dialog.locator('input[type=file]').set_input_files('.build/chopper-english-speech.wav')
 dialog.get_by_role('button',name='Use transcript',exact=True).wait_for();page.wait_for_function("!Array.from(document.querySelectorAll('dialog button')).find(e=>e.textContent==='Use transcript').disabled",timeout=90000)
 assert 'motor speed' in dialog.get_by_label('Review speech transcript').input_value().lower()
 dialog.get_by_label('Review speech transcript').fill('Review motor tag 653.')
 dialog.get_by_role('button',name='Use transcript',exact=True).click();assert page.get_by_label('Message Chopper',exact=True).input_value()=='Keep this draft.\nReview motor tag 653.'
 assert not sent,'Speech review sent a chat request automatically.'
 page.get_by_role('button',name='Speech to text',exact=True).click();dialog.wait_for();page.wait_for_function("!document.querySelector('.speechActions button').disabled")
 dialog.get_by_role('button',name='Record audio',exact=True).click();dialog.get_by_role('button',name='Stop recording',exact=True).wait_for();page.wait_for_timeout(4200);dialog.get_by_role('button',name='Stop recording',exact=True).click()
 page.wait_for_function("!Array.from(document.querySelectorAll('dialog button')).find(e=>e.textContent==='Use transcript').disabled",timeout=90000)
 assert 'motor' in dialog.get_by_label('Review speech transcript').input_value().lower()
 dialog.get_by_role('button',name='Cancel',exact=True).click();assert not sent

 page.get_by_role('button',name='Speech to text',exact=True).click();dialog.wait_for();page.keyboard.press('Escape');assert not dialog.is_visible()
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':900});page.get_by_role('button',name='Speech to text',exact=True).click();dialog.wait_for();box=dialog.bounding_box();assert box['x']>=0 and box['x']+box['width']<=width+1
  Path('.build/chopper-speech-20261113').mkdir(exist_ok=True);page.screenshot(path=f'.build/chopper-speech-20261113/dialog-{width}.png');dialog.get_by_role('button',name='Cancel',exact=True).click()
 assert not errors,errors
 print('PASS real local audio upload and microphone WebM transcription, five language selections, editable review, draft append, no automatic send, Escape and 390-1440px dialog layouts')
 browser.close();server.should_exit=True
