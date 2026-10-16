"""Isolated browser check for Chopper setup and window help; no controller I/O."""
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
VERSION=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
ARTIFACTS=ROOT/('.build/chopper-ui-'+VERSION)


def serve(port):
    sys.path.insert(0,str(ROOT))
    for key in ('USOPP_DATA_ROOT','USOPP_LLM_BASE_URL','USOPP_LLM_PROVIDER'):os.environ.pop(key,None)
    from backend.core import runtime
    runtime.BASE=ARTIFACTS/'isolated-data'
    runtime.WORK=runtime.BASE/'.usopp_workspaces';runtime.EXPORTS=runtime.BASE/'.usopp_exports'
    for folder in (runtime.BASE,runtime.WORK,runtime.EXPORTS):folder.mkdir(parents=True,exist_ok=True)
    os.environ['USOPP_DATA_ROOT']=str(runtime.BASE)
    os.environ['USOPP_INITIAL_ADMIN_PASSWORD']=os.environ['USOPP_QA_PASSWORD']
    from backend.app import app
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=port,access_log=False)


def run():
    from playwright.sync_api import sync_playwright,expect
    import urllib.request
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    url=f'http://127.0.0.1:{port}'
    password=secrets.token_urlsafe(24)
    # Keep an existing isolated test account usable on repeat checks.
    password_file=ARTIFACTS/'qa-password.txt'
    if password_file.is_file():password=password_file.read_text(encoding='utf-8')
    else:password_file.write_text(password,encoding='utf-8')
    environment={**os.environ,'USOPP_QA_PASSWORD':password,'PYTHONUTF8':'1'}
    with (ARTIFACTS/'server.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,__file__,'--serve',str(port)],cwd=ROOT,env=environment,
            stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            deadline=time.monotonic()+40
            while True:
                if process.poll() is not None:raise RuntimeError('Isolated server exited. See its log.')
                try:
                    with urllib.request.urlopen(url+'/api/health',timeout=1) as response:health=json.load(response)
                    break
                except OSError:
                    if time.monotonic()>deadline:raise
                    time.sleep(.2)
            assert health['version']==VERSION
            with sync_playwright() as engine:
                browser=engine.chromium.launch(channel='msedge',headless=True)
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.route('**/api/nami/plc/**',lambda route:route.fulfill(status=403,json={'detail':'Controller I/O disabled in this check.'}))
                page.goto(url)
                page.get_by_label('Username',exact=True).fill('Admin')
                page.get_by_label('Password',exact=True).fill(password)
                page.get_by_role('button',name='Sign in',exact=True).click()
                nav=page.get_by_role('navigation',name='Main navigation');expect(nav).to_be_visible(timeout=20000)
                expect(page.get_by_text(f'UI {VERSION} | API {VERSION}',exact=True)).to_be_visible()
                page.get_by_role('button',name='Open Chopper chat',exact=True).click()
                panel=page.get_by_role('dialog',name='Chopper',exact=True)
                panel.get_by_role('button',name='Window guide',exact=True).click()
                expect(panel.locator('.chopperQuickMessage.assistant').last).to_contain_text('Choose your next engineering task',timeout=15000)
                page.get_by_role('navigation',name='Settings and help').get_by_role('button',name='Settings',exact=True).click()
                setup=page.locator('.assistModelSettings')
                expect(setup.get_by_role('button',name='Local CPU model',exact=False)).to_have_attribute('aria-pressed','true')
                expect(setup.locator('.modelAdvanced')).not_to_have_attribute('open','')
                expect(setup.get_by_role('checkbox',name='Start with the server',exact=False)).to_be_checked()
                expect(setup.get_by_role('button',name='Set up local Chopper',exact=True)).to_be_visible()
                panel.get_by_role('button',name='Close Chopper chat',exact=True).click()
                setup.scroll_into_view_if_needed()
                setup.screenshot(path=str(ARTIFACTS/'chopper-settings.png'))
                setup.get_by_role('button',name='Engineering tools',exact=False).click()
                setup.get_by_role('button',name='Save settings',exact=True).click()
                expect(setup.get_by_role('status')).to_contain_text('settings saved',timeout=10000)
                assert page.request.get(url+'/api/assist/model').json()['provider']=='local'
                setup.get_by_role('button',name='Local CPU model',exact=False).click()
                setup.get_by_role('button',name='Save settings',exact=True).click()
                expect(setup.get_by_role('status')).to_contain_text('settings saved')
                assert page.request.get(url+'/api/assist/model').json()['autoStart'] is True
                # Use a single offline metadata row to exercise an actual manual decode.
                account=page.request.get(url+'/api/auth/session').json()['user']
                metadata=[{'sNo':1,'screenName':'Settings','machineVariants':'','parameter':'Speed','units':'m/min','min':None,'max':None,'tagCode':1,'groupCode':20,'offset':0,'dataType':'REAL','offsetFactor':0,'scaleFactor':1,'isVisible':True,'isWritable':False}]
                plc={'id':'qa-offline','name':'Offline Finisher','machineType':'Finisher','ip':'127.0.0.1','port':21010,'machineId':0,'isSimulated':False,'targetMode':'real-plc','endianness':'little','timeoutMs':1000,'status':'idle','liveEnabled':False,'storeLiveData':False}
                values={'plc_configs':json.dumps([plc]),'spinning_metadata_Finisher':json.dumps(metadata),'spinning_metadata_source_Finisher':'Offline QA fixture'}
                storage=page.request.get(url+'/api/account/storage').json()['entries']
                response=page.request.post(url+'/api/account/storage',data={'accountId':account['id'],'changes':[{'key':key,'value':value,'revision':storage.get(key,{}).get('revision',0)} for key,value in values.items()]})
                assert response.ok,response.text()
                page.reload();expect(nav).to_be_visible(timeout=20000)
                nav.get_by_role('button',name='DataInspect',exact=True).click()
                frame=page.frame_locator('iframe[title="Nami PLC Data Verification V1.5"]')
                frame.get_by_role('button',name='Manual received data',exact=True).click(timeout=30000)
                manual=frame.get_by_role('dialog',name='Manual PLC received data',exact=True)
                data=[3,0,0,0,4,*struct.pack('<f',36.5)];checksum=0
                for byte in data:checksum^=byte
                manual.get_by_label('Received bytes (decimal 0..255)',exact=True).fill(' '.join(map(str,[*data,checksum,2])))
                manual.get_by_role('button',name='Decode and map',exact=True).click()
                expect(manual).not_to_be_visible()
                page.get_by_role('button',name='Open Chopper chat',exact=True).click()
                expect(panel.locator('.chopperQuickContext')).to_contain_text('Offline Finisher',timeout=15000)
                panel.get_by_role('button',name='Window guide',exact=True).click()
                expect(panel.locator('.chopperQuickMessage.assistant').last).to_contain_text('Manual capture',timeout=15000)
                expect(panel.locator('.chopperQuickMessage.assistant').last).to_contain_text('Manual frame decoded')
                page.evaluate("window.postMessage({type:'usopp:datainspect-context',context:{target:'Untrusted page message'}},location.origin)")
                expect(panel.locator('.chopperQuickContext')).to_contain_text('Offline Finisher')
                page.screenshot(path=str(ARTIFACTS/'chopper-datainspect-help.png'))
                panel.get_by_role('button',name='Open full Chopper Chat',exact=True).click()
                chat=page.locator('.chopperInterface')
                chat.get_by_role('button',name='Guide me step by step',exact=True).click()
                expect(chat.locator('.chopperMessage.assist').last).to_contain_text('one step at a time')
                chat.locator('.chopperMessage.assist').last.get_by_role('button',name='ByteMap',exact=True).click()
                expect(chat.locator('.chopperMessage.assist').last).to_contain_text('Step 1 of')
                chat.locator('.chopperMessage.assist').last.get_by_role('button',name='Next step',exact=True).click()
                expect(chat.locator('.chopperMessage.assist').last).to_contain_text('Step 2 of')
                # Upload through the existing chat attachment path, without validation.
                fixture=ARTIFACTS/'upload-project';fixture.mkdir(exist_ok=True)
                (fixture/'QA.apj').write_text('<Project/>',encoding='utf-8')
                (fixture/'Main.st').write_text('PROGRAM Main\nIF Start AND NOT Fault THEN\nMotor := TRUE;\nEND_IF;\nEND_PROGRAM',encoding='utf-8')
                chat.locator('input[type=file][multiple]').first.set_input_files(str(fixture))
                expect(chat.locator('.projectIntelligence summary')).to_contain_text('Ready',timeout=30000)
                chat.locator('.projectIntelligence summary').click()
                expect(chat.get_by_role('button',name='Refresh changes',exact=True)).to_be_visible()
                expect(chat.locator('.intelligenceCounts')).to_contain_text('Programs')
                index_response=page.request.post(url+'/api/assist/projects/index',data={'projectPath':str(ROOT.parent/'project 2'),'mode':'refresh'})
                assert index_response.ok,index_response.text()
                project_id=index_response.json()['projectId']
                deadline=time.monotonic()+45
                while True:
                    state=page.request.get(url+'/api/assist/projects/'+project_id).json()
                    if state.get('ready') and not state.get('running'):break
                    if time.monotonic()>deadline:raise RuntimeError('Project index did not finish')
                    time.sleep(.2)
                sources=page.request.post(url+'/api/assist/projects/'+project_id+'/retrieve',data={'question':'LUB_TIME_IN_HOUR TIME_IN_SEC'})
                assert sources.ok and sources.json()['evidence']
                # A second account must never read this user's index.
                anonymous=browser.new_context(base_url=url)
                denied=anonymous.request.get(url+'/api/assist/projects/'+project_id)
                assert denied.status==401
                anonymous.close()
                page.screenshot(path=str(ARTIFACTS/'chopper-project-intelligence.png'))
                assert not errors,errors
                (ARTIFACTS/'verification.json').write_text(json.dumps({'version':health['version'],'browserErrors':errors,'checks':['UI/API agreement','embedded default','collapsed advanced settings','saved connection mode','window guides','manual capture context','frame message guard']},indent=2),encoding='utf-8')
                browser.close()
        finally:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    print('Chopper browser checks passed:',ARTIFACTS)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--serve':serve(int(sys.argv[2]))
    else:run()
