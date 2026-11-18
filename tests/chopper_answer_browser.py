"""Real authenticated spreadsheet API/browser checks; controlled delayed project reply fixture."""
import os,sys,tempfile,threading,time,socket,json,io
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
os.environ.update(USOPP_DATA_ROOT=tempfile.mkdtemp(prefix='usopp-answer-browser-'),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')
import uvicorn
from virtual_plc.server import create_app
from backend.core import accounts,project_intelligence
from playwright.sync_api import sync_playwright,expect
from openpyxl import Workbook
app=create_app();password='Answer.Browser.2026!'
user=accounts.store.register('answer_browser',password,'Engineer','Fixture',role='admin')
project=Path(tempfile.mkdtemp(prefix='answer-project-'));(project/'Logical').mkdir();(project/'Logical'/'Main.st').write_text('PROGRAM _CYCLIC\nCASE Step OF\n0: IF Start THEN Step := 1; END_IF;\n1: IF Done THEN Step := 0; END_IF;\nEND_CASE;\nEND_PROGRAM')
state=project_intelligence.start(project,user['id']);key=state['projectId']
for _ in range(100):
 state=project_intelligence.status(project_intelligence.opened(key,user['id']),user['id'])
 if not state.get('running'):break
 time.sleep(.1)
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'));threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True).start()
while not server.started:time.sleep(.05)
out=ROOT/'.build/chopper-answer-browser';out.mkdir(exist_ok=True)
with sync_playwright() as pw:
 browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)));base=f'http://127.0.0.1:{port}'
 page.goto(base+'/?page=chatbot&assistTab=chat');page.get_by_label('Username',exact=True).fill(user['username']);page.get_by_label('Password',exact=True).fill(password);page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
 page.get_by_label('Message Chopper',exact=True).wait_for(timeout=60000)
 assert page.get_by_role('button',name='Checked agent',exact=False).count()==0
 assert page.get_by_role('button',name='Agent workspace',exact=True).count()==0
 upload=page.locator('.chopperStudio input[type=file]:not([webkitdirectory])').first
 upload.set_input_files({'name':'production.csv','mimeType':'text/csv','buffer':b'Date,Line,Production,Hours\n2026-01-01,A,10,2\n2026-01-02,B,20,4\n2026-02-01,A,30,6\n2026-02-02,B,40,8\n'})
 dash=page.get_by_label('Automatic worksheet dashboard',exact=True)
 expect(dash).to_be_visible(timeout=30000);expect(dash.locator('.biKpis')).to_contain_text('100',timeout=30000)
 assert dash.locator('.biChartCard').count()==5
 page.get_by_label('Message Chopper',exact=True).fill('show monthly Production by Line');page.get_by_label('Message Chopper',exact=True).press('Enter')
 expect(dash.locator('.biQuestionResult')).to_contain_text('Production',timeout=30000)
 dash.get_by_role('button',name='Pin to dashboard',exact=True).click()
 dash.get_by_label('Dashboard name',exact=True).fill('Production MIS')
 dash.get_by_role('button',name='Save dashboard',exact=True).click();expect(dash).to_contain_text('Dashboard snapshot saved',timeout=30000)
 with page.expect_download() as download:dash.get_by_role('button',name='PDF',exact=True).click()
 download.value.save_as(str(out/'dashboard.pdf'));assert (out/'dashboard.pdf').read_bytes().startswith(b'%PDF')
 with page.expect_download() as download:dash.get_by_role('button',name='HTML',exact=True).click()
 download.value.save_as(str(out/'dashboard.html'));assert 'production.csv' in (out/'dashboard.html').read_text()
 with page.expect_download() as download:dash.locator('.biChartCard').first.get_by_role('button',name='Download PNG:',exact=False).click()
 download.value.save_as(str(out/'chart.png'))
 print('PASS real CSV profile -> KPI/chart -> monthly series -> pin/save -> PDF/HTML/PNG',flush=True)
 book=Workbook();book.active.title='One';book.active.append(['Hours']);book.active.append([11]);sheet=book.create_sheet('Two');sheet.append(['Hours']);sheet.append([22]);data=io.BytesIO();book.save(data);book.close()
 upload.set_input_files({'name':'sheets.xlsx','mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','buffer':data.getvalue()})
 page.get_by_label('Workbook',exact=True).select_option(label='sheets.xlsx')
 page.get_by_label('Workbook sheet',exact=True).select_option('Two')
 expect(dash.locator('.biKpis')).to_contain_text('22',timeout=30000)
 print('PASS multi-sheet profile isolation',flush=True)
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(250);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),f'Dataset overflow {width}';page.screenshot(path=str(out/f'worksheet-{width}.png'))
 page.set_viewport_size({'width':1440,'height':1000})
 # Clear attachments and use a deliberately delayed reply to test early tabs and Stop.
 page.get_by_label('New chat',exact=True).click()
 machine={'project':{'name':'Fixture machine'},'coverage':{'indexedFiles':1,'activeTaskCount':1},'stateMachines':[{'name':'Step','file':'Logical/Main.st','line':2,'ownership':'active task','transitions':[{'from':'0','to':'1','line':3,'conditions':['Start'],'actions':[]},{'from':'1','to':'0','line':4,'conditions':['Done'],'actions':[]}]}],'hardwareLinks':[{'variable':'Motor','address':'%QX0','file':'Logical/Main.st','line':3}],'alarmCandidates':[{'name':'Alarm','writers':[{'file':'Logical/Main.st','line':3}]}]}
 partial={'machineAnalysis':machine,'machineAnalysisProjectId':key,'evidence':[],'source':'local-project-intelligence'}
 counter={'n':0,'finish':False,'cancel':False}
 page.route('**/api/assist/start',lambda route:route.fulfill(json={'jobId':'fixture'}))
 def status(route):
  counter['n']+=1
  value={'status':'complete','result':{**partial,'answer':'Source-parsed transitions are available. Verify with the code.'}} if counter['finish'] else {'status':'running','stage':'Checking explanation','elapsedSeconds':counter['n'],'partialResult':partial}
  route.fulfill(json=value)
 page.route('**/api/assist/status/fixture',status)
 page.route('**/api/assist/cancel/fixture',lambda route:(counter.update(cancel=True),route.fulfill(json={'status':'stopped'})))
 page.get_by_label('Message Chopper',exact=True).fill('Explain this machine');page.get_by_label('Message Chopper',exact=True).press('Enter')
 card=page.get_by_label('Project answer',exact=True);expect(card).to_be_visible(timeout=15000)
 assert card.get_by_role('tab',name='Summary',exact=True).count()==0
 card.get_by_role('tab',name='Sequence',exact=True).click();expect(card).to_contain_text('Step 1: 0',timeout=5000)
 card.get_by_role('tab',name='Flow',exact=True).click();card.locator('svg g.node').first.wait_for(timeout=30000)
 with page.expect_download() as download:card.get_by_role('button',name='SVG',exact=True).click()
 download.value.save_as(str(out/'flow.svg'))
 with page.expect_download() as download:card.get_by_role('button',name='PNG',exact=True).click()
 download.value.save_as(str(out/'flow.png'));assert (out/'flow.png').read_bytes().startswith(b'\x89PNG')
 card.get_by_role('button',name='-',exact=True).click();expect(card.locator('.answerFlowTools')).to_contain_text('90%');card.get_by_role('button',name='Fit to screen',exact=True).click()
 card.locator('svg g.node').first.click();expect(card.get_by_role('tab',name='Sources',exact=True)).to_have_attribute('aria-selected','true');expect(card.locator('.answerSourcePeek')).to_contain_text('CASE Step',timeout=10000)
 card.get_by_role('tab',name='Sequence',exact=True).click();scroll_before=card.locator('.projectAnswerPanel').evaluate('(el)=>el.scrollTop');counter['finish']=True
 expect(card.get_by_role('tab',name='Summary',exact=True)).to_be_visible(timeout=10000)
 expect(card.get_by_role('tab',name='Sequence',exact=True)).to_have_attribute('aria-selected','true');assert card.locator('.projectAnswerPanel').evaluate('(el)=>el.scrollTop')==scroll_before
 card.get_by_role('button',name='Correct this answer',exact=True).click();card.get_by_label('Correction for engineer review',exact=True).fill('Confirm the physical meaning of Step before publication.');card.get_by_role('button',name='Send for review',exact=True).click();expect(card).to_contain_text('Saved for review in KnowHub',timeout=10000)
 page.get_by_label('Answer detail mode',exact=True).select_option('simple');assert card.get_by_role('tab',name='Sources',exact=True).count()==0;assert card.get_by_role('tab',name='I/O & axes',exact=True).count()==0
 page.get_by_label('Answer detail mode',exact=True).select_option('engineer')
 print('PASS facts-first tabs, lazy Mermaid, source click, SVG, stable tab on late reply, feedback and Simple mode',flush=True)
 counter['finish']=False
 page.get_by_label('Message Chopper',exact=True).fill('Show the main sequence');page.get_by_label('Message Chopper',exact=True).press('Enter');page.get_by_role('button',name='Stop',exact=True).click();page.wait_for_timeout(300);assert counter['cancel']
 assert page.get_by_label('Message Chopper',exact=True).is_enabled()
 for width in (1440,760,390):
  page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(200);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),f'Answer overflow {width}';page.screenshot(path=str(out/f'answer-{width}.png'))
 page.get_by_label('Choose appearance theme',exact=True).click();page.get_by_role('menuitemradio',name='Dark theme',exact=True).click();page.screenshot(path=str(out/'answer-dark.png'))
 page.get_by_role('button',name='KnowHub',exact=True).click();page.get_by_role('tab',name='Answer feedback',exact=True).click();expect(page.get_by_text('correction | pending',exact=False)).to_be_visible(timeout=15000)
 assert not errors,errors
 (out/'result.json').write_text(json.dumps({'passed':True,'pageErrors':errors,'widths':[1440,760,390],'isolation':'Temporary storage; controlled delayed project reply; actual source, feedback and BI endpoints'},indent=2))
 print('PASS Stop, dark mode and responsive layouts without page errors',flush=True)
 browser.close();server.should_exit=True

