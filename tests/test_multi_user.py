"""Six real HTTP sessions (five regular users plus Admin) against an isolated server; never contact a real PLC.

Run: python -m unittest tests.test_multi_user -v
The server uses a temporary account database, uploads and history. Engines are
real subprocesses. Only the controller in the TCP test is a loopback fixture.
"""
import io
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import httpx
from openpyxl import load_workbook

APP_ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'Concurrency.pass.2026'
ACCOUNT_COUNT = 6
SOURCE_PATH = 'Logical/SpinConnect/mms_nw_r/Cyclic.st'


def source(marker, size=4):
    return f'''PROGRAM _CYCLIC
(* {marker} *)
CASE nw_group_code OF
10:(*Program version*)
nw_snd_buffer[2] := 0;
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 4;
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(PLC_PROGRAM_VERSION),4);
nw_i := nw_i + 4;
nw_snd_buffer_length := nw_i;
nw_snd_response := TRUE;
11:(*Close*)
TCP_CLOSE_ON := TRUE;
20:(*{marker}*)
nw_snd_buffer[2] := 0;
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := {size};
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Speed_{marker}),4);(*{marker} Speed*)
nw_i := nw_i + 4;
nw_snd_buffer_length := nw_i;
nw_snd_response := TRUE;
END_CASE
END_PROGRAM
'''


class MultiUserHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='u')
        cls.data = Path(cls.temp.name)
        cls.clients = []
        cls.results = []
        cls.server = None
        cls.log = (cls.data/'server.log').open('w', encoding='utf-8')
        # Bundled help is read-only. Link it instead of copying gigabytes just
        # to exercise accounts and validations. All mutable defaults are copied.
        help_source = APP_ROOT/'knowledge/br_help'
        cls.help_link = cls.data/'knowledge/br_help'
        if help_source.is_dir():
            cls.help_link.parent.mkdir(parents=True)
            if os.name == 'nt':
                subprocess.run(['cmd', '/c', 'mklink', '/J', str(cls.help_link), str(help_source)],
                               check=True, capture_output=True)
            else:
                cls.help_link.symlink_to(help_source, target_is_directory=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cls.url = f'http://127.0.0.1:{port}'
        cls.env = {**os.environ, 'USOPP_DATA_ROOT': str(cls.data),
               'USOPP_MAX_PARALLEL_TESTS': '5', 'PYTHONUTF8': '1'}
        cls.env.pop('USOPP_MAX_USERS', None)  # Account count has no fixed cap.
        cls.command = [sys.executable, '-m', 'uvicorn', 'backend.app:app',
                       '--host', '127.0.0.1', '--port', str(port)]
        try:
            cls.launch_server()
            for index in range(ACCOUNT_COUNT):
                client = httpx.Client(base_url=cls.url, timeout=120)
                cls.clients.append(client)
                if index == 0:
                    response = client.post('/api/auth/login', json={'username':'Admin','password':'usopp.2026'})
                else:
                    created = cls.clients[0].post('/api/auth/users', json={'username':f'engineer{index}',
                        'password':PASSWORD,'designation':'Test engineer','company':'Isolated test'})
                    assert created.status_code == 200, created.text
                    response = client.post('/api/auth/login', json={'username':f'engineer{index}','password':PASSWORD})
                assert response.status_code == 200, response.text
            cls.users = [client.get('/api/auth/session').json()['user'] for client in cls.clients]
            cls.projects = [cls.upload(index) for index in range(ACCOUNT_COUNT)]
            cls.new_projects = [cls.upload(index, changed=True) for index in range(ACCOUNT_COUNT)]
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def launch_server(cls):
        cls.server = subprocess.Popen(cls.command,cwd=APP_ROOT,env=cls.env,stdout=cls.log,stderr=cls.log)
        deadline = time.monotonic()+150
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise AssertionError((cls.data/'server.log').read_text(encoding='utf-8'))
            try:
                if httpx.get(cls.url+'/api/health', timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.2)
        else:
            raise AssertionError('Isolated backend did not become ready: '+str(cls.data))

    @classmethod
    def stop_server(cls):
        if cls.server:
            if os.name == 'nt':
                subprocess.run(['taskkill','/PID',str(cls.server.pid),'/T','/F'],capture_output=True)
            else:
                cls.server.terminate()
            try:
                cls.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.server.kill(); cls.server.wait(timeout=10)

    @classmethod
    def tearDownClass(cls):
        for client in cls.clients:
            client.close()
        cls.stop_server()
        cls.log.close()
        if cls.help_link.exists():
            if os.name == 'nt':
                os.rmdir(cls.help_link)  # Remove only the junction, never its target.
            else:
                cls.help_link.unlink()
        cls.temp.cleanup()

    @classmethod
    def upload(cls, index, changed=False):
        marker = f'USER_{index}'
        code = source(marker, 8 if changed else 4)
        files = [('project_files', ('Demo/Machine.apj', b'<Project/>')),
                 ('project_files', ('Demo/'+SOURCE_PATH, code.encode())),
                 ('project_files', ('Demo/Logical/SpinConnect/mms_nw_r/mms_nw_r.var',
                   f'VAR\nnw_i : UINT;\nPLC_PROGRAM_VERSION : REAL;\nSpeed_{marker} : REAL;\nStart_{marker} : BOOL;\nRun_{marker} : BOOL;\nEND_VAR'.encode())),
                 ('project_files', ('Demo/Logical/SpinConnect/mms_nw_r/Cyclic.ld',
                   ('PROGRAM _CYCLIC\n<networks><network label="'+marker+'"><row><contact name="Start_'+marker+
                    '" type="'+('closed' if changed else 'open')+'"/><coil name="Run_'+marker+
                    '" type="open"/></row></network></networks>\nEND_PROGRAM').encode())),
                 ('project_files', ('Demo/Logical/HMI/Pages/Default.page',
                   ('<Page><Property Name="Width" Value="640"/><Property Name="Height" Value="480"/>'
                    '<Controls><Control Name="Numeric_'+marker+'" ClassId="0x00001006">'
                    '<Property Name="Datapoint" Value="Local.Speed_'+marker+'"/>'
                    '<Property Name="Width" Value="120"/><Property Name="Height" Value="40"/>'
                    '<Property Name="Left" Value="25"/><Property Name="Top" Value="'+str(21 if changed else 20)+
                    '"/></Control></Controls></Page>').encode()))]
        client = cls.clients[index]
        started = client.post('/api/project-upload/start', json={'project_name':'Demo','total_files':len(files)})
        assert started.status_code == 200, started.text
        sid = started.json()['sessionId']
        chunk = client.post('/api/project-upload/chunk', data={'session_id':sid}, files=files)
        assert chunk.status_code == 200, chunk.text
        result = client.post('/api/project-upload/finish', json={'session_id':sid})
        assert result.status_code == 200, result.text
        return result.json()

    def concurrent(self, function):
        barrier = threading.Barrier(ACCOUNT_COUNT)
        def run(index):
            barrier.wait(timeout=10)
            return function(index, self.clients[index])
        with ThreadPoolExecutor(max_workers=ACCOUNT_COUNT) as pool:
            return list(pool.map(run, range(ACCOUNT_COUNT)))

    def ok(self, response):
        self.assertEqual(response.status_code, 200, response.text[:1800])
        return response.json()

    def capture(self, index, data, kind):
        self.assertTrue(data.get('testId'), data)
        self.assertTrue(data.get('historyId'), data)
        archived = self.ok(self.clients[index].get('/api/history/'+data['historyId']))
        record, saved = archived['record'], archived['result']
        self.assertEqual(record['status'], 'completed', record)
        self.assertEqual(record['kind'], kind)
        self.assertEqual(record['user']['id'], self.users[index]['id'])
        self.assertEqual(saved['runOwner']['id'], self.users[index]['id'])
        self.assertEqual(saved['testId'], data['testId'])
        self.results.append((index, data, kind))
        return archived

    def test_01_six_concurrent_packet_and_metadata_engines(self):
        for route, kind in [('validate','validation'),('generate-metadata','metadata')]:
            results = self.concurrent(lambda i,c: self.ok(c.post('/api/local/'+route, json={
                'project_path':self.projects[i]['projectPath'],'project_name':'Demo'})))
            for index, result in enumerate(results):
                self.capture(index,result,kind)
                report = self.clients[index].get(result['downloadExcelUrl'])
                self.assertEqual(report.status_code,200,report.text[:150] if report.status_code!=200 else '')
                workbook = load_workbook(io.BytesIO(report.content),read_only=True,data_only=True)
                try:
                    cells = '\n'.join(str(cell) for sheet in workbook for row in sheet.values for cell in row)
                    # Generated metadata presents descriptive labels with spaces.
                    normalized=cells.replace('_',' ')
                    self.assertIn(f'USER {index}', normalized)
                    for other in range(ACCOUNT_COUNT):
                        if other != index: self.assertNotIn(f'USER {other}',normalized)
                finally: workbook.close()
            # Five engines overlap; the sixth account waits for an engine slot.
            # This also detects a globally serial server despite parallel clients.
            ordered=sorted(results,key=lambda row:row['createdAt'])
            first_five=ordered[:5]
            self.assertLess(max(datetime.fromisoformat(row['createdAt']) for row in first_five),
                            min(datetime.fromisoformat(row['completedAt']) for row in first_five))
            self.assertGreaterEqual(datetime.fromisoformat(ordered[5]['createdAt']),
                                    min(datetime.fromisoformat(row['completedAt']) for row in first_five))
        self.assertEqual(len({r[1]['testId'] for r in self.results}), len(self.results))

    def test_02_six_concurrent_rule_and_comparison_engines(self):
        results = self.concurrent(lambda i,c: self.ok(c.post('/api/local/rules/validate',json={
            'project_path':self.projects[i]['projectPath'],'project_name':'Demo','rules':{'rules':[
                {'id':f'owner_{i}','name':f'USER_{i}','kind':'source_regex','pattern':f'USER_{i}'}]}})))
        for index,result in enumerate(results):
            self.capture(index,result,'rules')
            self.assertEqual(result['counts']['pass'],1)
            self.assertEqual(result['results'][0]['name'],f'USER_{index}')
        compared = self.concurrent(lambda i,c: self.ok(c.post('/api/local/compare',json={
            'base_path':self.projects[i]['projectPath'],'new_path':self.new_projects[i]['projectPath']})))
        self.comparisons = compared
        for index,result in enumerate(compared):
            self.capture(index,result,'compare')
            self.assertEqual(result['summary']['modified'],3)
            ladder=self.ok(self.clients[index].get('/api/local/compare/ladder/'+result['sessionId'],
                params={'path':'Logical/SpinConnect/mms_nw_r/Cyclic.ld'}))
            self.assertIn(f'Start_USER_{index}',json.dumps(ladder))
            text = json.dumps(result)
            self.assertIn(f'USER_{index}',text)
            for other in range(ACCOUNT_COUNT):
                if other != index:self.assertNotIn(f'USER_{other}',text)
        # Results are needed by the independent export and access tests.
        type(self).comparisons = compared

    def test_03_concurrent_data_models_and_simulators(self):
        def run(index,client):
            name = f'USER_{index} Speed'
            raw = {'controleCode':'CARDING','keysList':{'shift':[
                {'tagName':name,'dataType':'FLOAT','groupCode':40,'isRequired':True}]}}
            model = self.ok(client.post('/api/nami/data-models/import',data={'service':'PMS'},
                files={'file':('PMS_Carding.json',json.dumps(raw).encode(),'application/json')}))
            result = self.ok(client.post(f'/api/nami/data-models/{model["id"]}/validate',json={
                'metadata':[{'parameter':name,'dataType':'REAL','groupCode':40,'tagCode':54}]}))
            self.assertEqual(result['status'],'PASS')
            self.assertEqual(result['summary']['PASS'],1)
            speed = 101.0+index
            self.ok(client.post('/api/nami/simulator/update',json={'deliverySpeed':speed}))
            metadata=[{'parameter':name,'groupCode':20,'dataType':'REAL','offset':0,'tagCode':2,
                       'screenName':'Default Screen','units':'m/min','min':None,'max':None,
                       'offsetFactor':0,'scaleFactor':1,'isVisible':True,'isWritable':False}]
            read = self.ok(client.post('/api/nami/plc/read-group',json={'isSimulated':True,
                'groupCode':20,'machineId':index,'metadata':metadata,'plc':{'name':f'USER_{index} PLC'}}))
            self.assertAlmostEqual(struct.unpack('<f',bytes(read['rawBytes'][5:9]))[0],speed)
            self.assertEqual(read['rawBytes'][1],index)
            decoded={'20':{**read,'lengthMatch':True,'dataLength':200,'resultCode':0,'timestamp':'Saved test',
                'parsedValues':[{**metadata[0],'name':name,'value':speed,'rawValue':speed,
                                 'formattedValue':str(speed),'rawHex':'','isInRange':True}]}}
            self.ok(client.post('/api/nami/history/'+read['historyId']+'/decoded',json={'groupResponses':decoded}))
            return result, read, model
        results=self.concurrent(run)
        for index,(model_check,read,model) in enumerate(results):
            self.capture(index,model_check,'data-model')
            saved=self.capture(index,read,'datainspect')['result']
            self.assertEqual(saved['metadata'][0]['parameter'],f'USER_{index} Speed')
            self.assertEqual(saved['groupResponses']['20']['parsedValues'][0]['value'],101.0+index)
            if index:
                other=self.clients[index%(ACCOUNT_COUNT-1)+1]
                self.assertEqual(other.get('/api/nami/data-models/'+model['id']).status_code,404)

    def test_04_shared_source_six_runs_have_separate_results(self):
        # Server-local folders are intentionally shared; staged uploads are private.
        shared=self.data/'shared_project'
        (shared/'Logical/SpinConnect/mms_nw_r').mkdir(parents=True)
        (shared/'Machine.apj').write_text('<Project/>')
        (shared/SOURCE_PATH).write_text(source('SHARED'))
        (shared/'Logical/SpinConnect/mms_nw_r/mms_nw_r.var').write_text(
            'VAR\nnw_i : UINT;\nPLC_PROGRAM_VERSION : REAL;\nSpeed_SHARED : REAL;\nEND_VAR')
        results=self.concurrent(lambda i,c:self.ok(c.post('/api/local/validate',json={
            'project_path':str(shared),'project_name':f'Owner_{i}'})))
        self.assertEqual(len({data['testId'] for data in results}),ACCOUNT_COUNT)
        for index,result in enumerate(results):
            self.capture(index,result,'validation')
            self.assertEqual(result['projectName'],f'Owner_{index}')

    def test_05_six_background_report_jobs(self):
        jobs=self.concurrent(lambda i,c:self.ok(c.post('/api/local/compare/reports/start/'+self.comparisons[i]['sessionId'],
            json={'formats':['html','pdf','json'],'cover':{'projectName':f'USER_{i} report',
                'description':f'PRIVATE_COVER_{i}','validatedBy':f'engineer{i}','date':'2026-10-10'}})))
        self.assertEqual(len({job['id'] for job in jobs}),ACCOUNT_COUNT)
        for index,job in enumerate(jobs):
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                result=self.ok(self.clients[index].get('/api/local/compare/reports/status/'+job['id']))
                if result['status'] not in {'running','queued'}:break
                time.sleep(.1)
            self.assertEqual(result['status'],'complete',result)
            for fmt,item in result['reports'].items():
                response=self.clients[index].get(item['downloadUrl'])
                self.assertEqual(response.status_code,200,response.text[:300] if fmt!='pdf' else '')
                if fmt=='pdf':
                    self.assertTrue(response.content.startswith(b'%PDF'))
                    from pypdf import PdfReader
                    text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
                    self.assertIn(f'PRIVATE_COVER_{index}',text)
                    for other in range(ACCOUNT_COUNT):
                        if other!=index:self.assertNotIn(f'PRIVATE_COVER_{other}',text)
                elif fmt=='json':self.assertEqual(response.json()['testId'],self.comparisons[index]['testId'])
                else:
                    self.assertIn(f'PRIVATE_COVER_{index}',response.text)
                    for other in range(ACCOUNT_COUNT):
                        if other!=index:self.assertNotIn(f'PRIVATE_COVER_{other}',response.text)
                if index:
                    self.assertEqual(self.clients[index%(ACCOUNT_COUNT-1)+1].get(item['downloadUrl']).status_code,404)
            archived=self.ok(self.clients[index].get('/api/history/'+self.comparisons[index]['historyId']))
            self.assertEqual(len(archived['record']['artifacts']),3)

    def test_06_access_history_source_and_account_capacity(self):
        seen=set()
        for index,data,kind in self.results:
            self.assertNotIn(data['testId'],seen);seen.add(data['testId'])
            if index:
                other=self.clients[index%(ACCOUNT_COUNT-1)+1]
                self.assertEqual(other.get('/api/history/'+data['historyId']).status_code,403)
                self.assertEqual(other.get('/api/history/'+data['historyId']+'/json').status_code,403)
                if data.get('downloadExcelUrl'):
                    self.assertEqual(other.get(data['downloadExcelUrl']).status_code,403)
                if kind in {'validation','metadata','rules'}:
                    self.assertEqual(other.post('/api/validation/source/read',json={'session_id':data['sessionId'],
                        'path':SOURCE_PATH}).status_code,403)
        for index in range(1,ACCOUNT_COUNT):
            other=self.clients[index%(ACCOUNT_COUNT-1)+1]
            denied=other.post('/api/project-upload/chunk',data={'session_id':self.projects[index]['sessionId']},
                files=[('project_files',('Demo/Injected.st',b'injected'))])
            self.assertEqual(denied.status_code,403,denied.text)
        for index,client in enumerate(self.clients):
            rows=self.ok(client.get('/api/history'))['runs']
            if index:self.assertTrue(all(row['user']['id']==self.users[index]['id'] for row in rows))
            else:self.assertEqual({row['user']['id'] for row in rows},{u['id'] for u in self.users})
            self.assertFalse(any(row.get('legacy') for row in rows),rows)
        capacity=self.ok(self.clients[0].get('/api/auth/users'))['capacity']
        self.assertEqual(capacity['activeUsers'],ACCOUNT_COUNT)
        self.assertIsNone(capacity['maxActiveUsers'])
        self.assertTrue(capacity['unlimited'])
        extra=self.clients[0].post('/api/auth/users',json={'username':'extra_enabled',
            'password':PASSWORD,'designation':'Test','company':'Test'})
        self.assertEqual(extra.status_code,200,extra.text)
        responses=self.concurrent(lambda i,c:c.post('/api/auth/register',json={'username':f'extra{i}',
            'password':PASSWORD,'designation':'Test','company':'Test'}))
        self.assertEqual([r.status_code for r in responses],[202]*ACCOUNT_COUNT)
        self.assertTrue(all(response.json()['pending'] for response in responses))
        self.assertEqual(self.ok(self.clients[0].get('/api/auth/users'))['capacity']['activeUsers'],ACCOUNT_COUNT)

    def test_07_same_plc_connections_do_not_interleave(self):
        # This small TCP controller closes after GC11 and refuses overlapping
        # sessions. Each response identifies the requesting account/machine ID.
        errors=[]; connections=[]
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(ACCOUNT_COUNT)
        listener.settimeout(15);port=listener.getsockname()[1]
        def controller():
            try:
                for _ in range(ACCOUNT_COUNT):
                    with listener.accept()[0] as conn:
                        conn.settimeout(4)
                        for expected_group in (10,20,11):
                            request=b''
                            while len(request)<9:request+=conn.recv(9-len(request))
                            machine_id=request[1]
                            self.assertEqual(int.from_bytes(request[5:7],'big'),expected_group)
                            if expected_group==11:break
                            value=struct.pack('<f',300.0+machine_id)
                            raw=bytes([3,machine_id,0,0,4])+value
                            checksum=0
                            for byte in raw:checksum^=byte
                            conn.sendall(raw[:2]);time.sleep(.015)
                            conn.sendall(raw[2:]+bytes([checksum,2]))
                        connections.append(machine_id)
            except Exception as exc:errors.append(exc)
            finally:listener.close()
        worker=threading.Thread(target=controller,daemon=True);worker.start()
        results=self.concurrent(lambda i,c:self.ok(c.post('/api/nami/plc/read-multiple-groups',json={
            'ip':'127.0.0.1','port':port,'machineId':i,'timeoutMs':1000,'groupCodes':[10,20]})))
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive());self.assertFalse(errors,errors)
        self.assertEqual(sorted(connections),list(range(ACCOUNT_COUNT)))
        for index,result in enumerate(results):
            self.assertIsNone(result.get('error'),result)
            self.assertTrue(result['closeResult']['plcClosed'])
            for row in result['results']:
                self.assertTrue(row['success'],row)
                self.assertEqual(struct.unpack('<f',bytes(row['rawBytes'][5:9]))[0],300.0+index)
            self.capture(index,result,'datainspect')

    def test_08_mixed_validations_and_source_save_guard(self):
        kinds=['validation','metadata','rules','compare','datainspect','datainspect']
        def run(index,client):
            payload={'project_path':self.projects[index]['projectPath'],'project_name':f'Mixed_{index}'}
            if index<2:
                return self.ok(client.post('/api/local/'+('validate' if index==0 else 'generate-metadata'),json=payload))
            if index==2:
                payload['rules']={'rules':[{'id':'mixed','name':'Mixed rule','kind':'source_regex','pattern':'USER_2'}]}
                return self.ok(client.post('/api/local/rules/validate',json=payload))
            if index==3:
                return self.ok(client.post('/api/local/compare',json={'base_path':self.projects[3]['projectPath'],
                    'new_path':self.new_projects[3]['projectPath']}))
            return self.ok(client.post('/api/nami/plc/read-multiple-groups',json={'isSimulated':True,
                'machineId':index,'groupCodes':[10,20,30,40]}))
        for index,result in enumerate(self.concurrent(run)):
            self.capture(index,result,kinds[index])
        previous=next(data for index,data,kind in self.results if index==1 and kind=='validation')
        reader={'session_id':previous['sessionId'],'path':SOURCE_PATH}
        original=self.ok(self.clients[1].post('/api/validation/source/read',json=reader))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.clients[1].post,'/api/local/validate',json={
                'project_path':self.projects[1]['projectPath'],'project_name':'Guarded_run'})
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                rows=self.ok(self.clients[0].get('/api/history'))['runs']
                if any(row['status']=='running' and row['projectName']=='Guarded_run' for row in rows):break
                time.sleep(.01)
            else:self.fail('Validation did not expose its running status')
            save=self.clients[1].post('/api/validation/source/save',json={**reader,'etag':original['etag'],
                'content':original['content']+'\n(*unsafe concurrent edit*)'})
            self.assertEqual(save.status_code,409,save.text)
            # Another user's clear action cannot delete the active upload.
            self.ok(self.clients[0].post('/api/cache/clear'))
            self.assertTrue(Path(self.projects[1]['projectPath']).is_dir())
            result=self.ok(future.result(timeout=30))
            archived=self.capture(1,result,'validation')
        saved=archived['result']
        read=self.ok(self.clients[1].post('/api/validation/source/read',json={
            'session_id':saved['sessionId'],'path':SOURCE_PATH}))
        self.assertTrue(read['readOnly'])
        self.assertEqual(self.clients[1].post('/api/validation/source/save',json={
            'session_id':saved['sessionId'],'path':SOURCE_PATH,'content':read['content'],'etag':read['etag']}).status_code,403)

    @unittest.skipUnless(os.getenv('USOPP_BROWSER_TESTS')=='1','Browser checks are opt-in: USOPP_BROWSER_TESTS=1.')
    def test_09_six_browser_profiles_and_saved_datainspect(self):
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(channel='msedge',headless=True) if os.name=='nt' else playwright.chromium.launch(headless=True)
            errors=[]; pages=[]
            try:
                for index,client in enumerate(self.clients):
                    context=browser.new_context(viewport={'width':1500,'height':1000})
                    context.add_cookies([{'name':key,'value':value,'url':self.url} for key,value in client.cookies.items()])
                    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(self.url)
                    expect(page.get_by_role('navigation',name='Main navigation')).to_be_visible(timeout=15000)
                    own=next(data for owner,data,kind in self.results if owner==index and kind=='validation')
                    expect(page.get_by_text(own['testId'],exact=True)).to_be_visible(timeout=10000)
                    if index == 0:
                        page.get_by_role('button',name='User management',exact=True).click()
                        expect(page.get_by_text('5 / 5 enabled regular users',exact=True)).to_be_visible()
                        page.get_by_role('button',name='Close user management',exact=True).click()
                    if index:
                        other=next(data for owner,data,kind in self.results if owner==index%(ACCOUNT_COUNT-1)+1 and kind=='validation')
                        expect(page.get_by_text(other['testId'],exact=True)).to_have_count(0)
                    page.locator('tr').filter(has_text=own['testId']).get_by_role('button',name='Reuse in ByteMap',exact=True).click()
                    expect(page.get_by_role('button',name='Run validation',exact=True)).to_be_enabled(timeout=10000)
                    pages.append(page)
                # Submit from the actual UI in every profile before waiting for
                # any run to finish, then check the six resulting identities.
                browser_results={}
                def capture_response(index,response):
                    if response.url.endswith('/api/local/validate') and response.status==200:
                        browser_results[index]=response.json()
                for index,page in enumerate(pages):
                    page.on('response',lambda response,i=index:capture_response(i,response))
                    page.get_by_role('button',name='Run validation',exact=True).click()
                for index,page in enumerate(pages):
                    expect(page.locator('p.mono').filter(has_text='Test ID:')).to_be_visible(timeout=30000)
                    result=browser_results[index]
                    self.capture(index,result,'validation')
                    expect(page.locator('p.mono').filter(has_text=result['testId'])).to_be_visible()
                    self.assertIn(f'USER_{index}',json.dumps(result))
                    page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='DataInspect',exact=True).click()
                    expect(page.locator('iframe')).to_be_visible()
                    page.get_by_role('button',name='Dark mode',exact=True).click()
                    prefix=f'usopp-user:{self.users[index]["id"]}:'
                    self.assertEqual(page.evaluate('(key)=>localStorage.getItem(key)',prefix+'usopp_theme'),'dark')
                    stored=page.evaluate('Object.keys(localStorage)')
                    self.assertFalse(any(key.startswith('usopp-user:') and not key.startswith(prefix) for key in stored))
                # All six contexts remain signed in simultaneously and see only
                # their own captured simulator bytes in the read-only viewer.
                for index,page in enumerate(pages):
                    saved=next(data for owner,data,kind in self.results if owner==index and kind=='datainspect')
                    page.goto(self.url+'/nami/index.html?historyId='+saved['historyId'])
                    expect(page.get_by_text('Saved test (read only)',exact=False)).to_be_visible(timeout=15000)
                    expect(page.get_by_text(saved['testId'],exact=True).first).to_be_visible()
                    expect(page.get_by_role('button',name='Read Group Data',exact=True)).to_be_disabled()
                    expect(page.get_by_text(f'USER_{index} Speed',exact=True)).to_be_visible()
                self.assertFalse(errors,errors)
            finally:browser.close()

    def test_10_simultaneous_manual_rtc_and_rule_report_versions(self):
        for operation in ('send-raw','send-rtc','manual'):
            def run(index,client):
                plc={'isSimulated':True,'ip':'','port':21010,'machineId':index,'timeoutMs':1000,'name':f'USER_{index} PLC'}
                if operation=='send-rtc':
                    return self.ok(client.post('/api/nami/plc/send-rtc',json={**plc,
                        'asciiPayload':f'2026-10-10 12:00:0{index}','rtcLayout':'spinconnect'}))
                request=[3,index,1,0,2,0,20]
                checksum=0
                for byte in request:checksum^=byte
                if operation=='send-raw':
                    return self.ok(client.post('/api/nami/plc/send-raw',json={**plc,'rawBytes':request+[checksum,2]}))
                raw=[3,index,0,0,0,3^index,2]
                return self.ok(client.post('/api/nami/history/manual',json={'plc':plc,'groupResponses':{
                    '20':{'groupCode':20,'rawBytes':raw,'success':True,'lengthMatch':True,'parsedValues':[]}}}))
            for index,result in enumerate(self.concurrent(run)):
                archived=self.capture(index,result,'datainspect')['result']
                self.assertEqual(archived['plc']['machineId'],index)
                if operation=='send-rtc':self.assertIn(f'12:00:0{index}',archived['asciiPayload'])
        for fmt in ('html','pdf'):
            def export(index,client):
                data=next(data for owner,data,kind in self.results if owner==index and kind=='rules')
                response=client.post(f'/api/reports/rules/{data["sessionId"]}/{fmt}',json={
                    'projectName':f'USER_{index}','description':f'RULE_COVER_{index}','date':'2026-10-10'})
                self.assertEqual(response.status_code,200,response.text[:200] if fmt!='pdf' else '')
                if fmt=='pdf':self.assertTrue(response.content.startswith(b'%PDF'))
                else:
                    self.assertIn(f'RULE_COVER_{index}',response.text)
                    for other in range(ACCOUNT_COUNT):
                        if other!=index:self.assertNotIn(f'RULE_COVER_{other}',response.text)
                return data
            for index,result in enumerate(self.concurrent(export)):
                saved=self.ok(self.clients[index].get('/api/history/'+result['historyId']))
                self.assertEqual(len(saved['record']['artifacts']),1 if fmt=='html' else 2)

    def test_11_one_engine_failure_does_not_interrupt_other_users(self):
        def run(index,client):
            if index==2:
                return client.post('/api/local/rules/validate',json={'project_path':self.projects[index]['projectPath'],
                    'project_name':'Expected_failure','rules':{'rules':[],'pipelineMode':'branches','pipelineStages':[]}})
            return client.post('/api/nami/plc/read-group',json={'isSimulated':True,'machineId':index,'groupCode':20})
        for index,response in enumerate(self.concurrent(run)):
            if index!=2:self.capture(index,self.ok(response),'datainspect')
            else:self.assertEqual(response.status_code,500,response.text)
        rows=self.ok(self.clients[2].get('/api/history'))['runs']
        failed=next(row for row in rows if row['projectName']=='Expected_failure')
        self.assertEqual(failed['status'],'failed');self.assertTrue(failed['testId']);self.assertTrue(failed['error'])
        self.assertEqual(self.clients[3].get('/api/history/'+failed['id']).status_code,403)

    def test_12_restart_retains_accounts_results_and_exports(self):
        before=self.ok(self.clients[0].get('/api/history'))['runs']
        self.stop_server();self.launch_server()
        after=self.ok(self.clients[0].get('/api/history'))['runs']
        self.assertEqual({row['id'] for row in before},{row['id'] for row in after})
        for index,client in enumerate(self.clients):
            self.assertEqual(self.ok(client.get('/api/auth/session'))['user']['id'],self.users[index]['id'])
            data=next(data for owner,data,kind in self.results if owner==index and kind=='compare')
            saved=self.ok(client.get('/api/history/'+data['historyId']))
            self.assertEqual(saved['record']['user']['id'],self.users[index]['id'])
            self.assertEqual(len(saved['record']['artifacts']),3)
            for artifact in saved['result']['historyDownloads']:
                self.assertEqual(client.get(artifact['url']).status_code,200)
        print(f'\nVerified {len(after)} retained runs across five regular users plus Admin and a backend restart.',flush=True)


class ProjectJobTests(unittest.TestCase):
    def test_five_slots_and_queued_sixth_job(self):
        from backend.core import jobs
        started=threading.Event();release=threading.Event();guard=threading.Lock()
        active=0;peak=0;entered=0
        def work(index):
            nonlocal active,peak,entered
            with jobs.project_job(Path(tempfile.gettempdir())/f'slot_{index}'):
                with guard:
                    active+=1;entered+=1;peak=max(peak,active)
                    if entered==5:started.set()
                release.wait(timeout=5)
                with guard:active-=1
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures=[pool.submit(work,index) for index in range(6)]
            try:
                self.assertTrue(started.wait(timeout=5));time.sleep(.03)
                self.assertEqual(entered,5);self.assertEqual(peak,5)
            finally:release.set()
            for future in futures:future.result(timeout=5)
        self.assertEqual(entered,6);self.assertFalse(jobs.ACTIVE)

    def test_same_project_serializes_and_reversed_comparisons_finish(self):
        from backend.core import jobs
        roots=[Path(tempfile.gettempdir())/'project_a',Path(tempfile.gettempdir())/'project_b']
        guard=threading.Lock();active=0;peak=0
        def work(index):
            nonlocal active,peak
            with jobs.projects_job(roots if index%2 else list(reversed(roots))):
                with guard:active+=1;peak=max(peak,active)
                time.sleep(.015)
                with guard:active-=1
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures=[pool.submit(work,index) for index in range(5)]
            for future in futures:future.result(timeout=5)
        self.assertEqual(peak,1);self.assertFalse(jobs.ACTIVE)

    def test_edit_and_cleanup_skip_active_and_waiting_projects(self):
        from backend.core import jobs
        from fastapi import HTTPException
        root=Path(tempfile.gettempdir())/'protected_source'
        held=threading.Event();release=threading.Event()
        def work():
            with jobs.project_job(root):
                held.set();release.wait(timeout=5)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(work)
            self.assertTrue(held.wait(timeout=5))
            second=pool.submit(work)
            try:
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    with jobs.GUARD:count=jobs.ACTIVE.get(os.path.normcase(str(root.resolve())),0)
                    if count==2:break
                    time.sleep(.01)
                self.assertEqual(count,2)
                with self.assertRaises(HTTPException) as caught:
                    with jobs.project_job(root,editing=True):pass
                self.assertEqual(caught.exception.status_code,409)
                with jobs.workspace_cleanup(root.parent) as available:self.assertFalse(available)
            finally:release.set()
            first.result(timeout=5);second.result(timeout=5)
        with jobs.workspace_cleanup(root) as available:self.assertTrue(available)
        self.assertFalse(jobs.ACTIVE)

    def test_failed_job_releases_slot_and_project(self):
        from backend.core import jobs
        root=Path(tempfile.gettempdir())/'failed_job'
        with self.assertRaises(RuntimeError):
            with jobs.project_job(root):raise RuntimeError('fixture failure')
        with jobs.project_job(root,editing=True):pass
        self.assertFalse(jobs.ACTIVE)


if __name__ == '__main__':
    unittest.main()
