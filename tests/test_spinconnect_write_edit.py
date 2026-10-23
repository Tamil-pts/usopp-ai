"""Reference source contracts and localhost-only edit transport checks."""
import base64
from contextlib import ExitStack
import copy
import io
import json
from pathlib import Path
import socket
import re
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from backend.app import app
from backend.api import nami_edit as api
from backend.core import accounts, nami_transport as tcp, nami_edit as edit
from backend.core import runtime as runtime_paths, run_history, persistent_store
from backend.core.nami_simulator import frame
from python_engine.spinconnect_write import Study, generate, cases, number
from virtual_plc.core.compiler import compile_source, walk_ir
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.tests.test_runtime import project, variable

ROOT=Path(__file__).resolve().parents[1]


class MockPLC:
    """A bounded loopback service; never opens a remote controller connection."""
    def __init__(self,variant,baseline,result_code=0,apply=True):
        self.variant=variant;self.baseline=bytearray(baseline);self.result_code=result_code;self.apply=apply
        self.requests=[];self.errors=[];self.stop=threading.Event()
    def __enter__(self):
        self.listener=socket.socket();self.listener.bind(('127.0.0.1',0));self.listener.listen();self.listener.settimeout(.1)
        self.port=self.listener.getsockname()[1]
        self.worker=threading.Thread(target=self.run,daemon=True);self.worker.start();return self
    def run(self):
        while not self.stop.is_set():
            try: conn,_=self.listener.accept()
            except TimeoutError: continue
            except OSError: break
            try:
                with conn:
                    conn.settimeout(3)
                    while True:
                        request=bytes(tcp.receive(conn));self.requests.append(request)
                        gc=int.from_bytes(request[5:7],'big')
                        if gc==11: break
                        if request[2]==1: response=frame(request[1],bytes(self.baseline))
                        else:
                            if self.apply:
                                for f in self.variant['fields']:
                                    r,w,size=f['readOffset'],f['writeOffset']+7,f['size']
                                    self.baseline[r:r+size]=request[w:w+size]
                            response=frame(request[1],result=self.result_code)
                        # Exercise the application's bounded TCP frame assembler.
                        conn.sendall(response[:3]);conn.sendall(response[3:5]);conn.sendall(response[5:])
            except Exception as exc: self.errors.append(exc)
    def __exit__(self,*_):
        self.stop.set();self.listener.close();self.worker.join(4)
        if self.errors: raise AssertionError(self.errors)


class ReferenceSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples={}
        for name in ('project 2','project 5'):
            path=ROOT.parent/name
            if not path.is_dir(): raise unittest.SkipTest('Reference projects 2 and 5 are not installed.')
            study=Study(path);draft=generate(study,[130,140],reviewed=True)
            mapping=json.loads(next(f['text'] for f in draft['files'] if f['name']=='write_mapping.json'))
            cls.samples[name]=(study,draft,mapping)

    def test_both_samples_compile_in_local_st_parser(self):
        for name,(study,draft,mapping) in self.samples.items():
            with self.subTest(project=name):
                code=draft['files'][0]['text'];compiled=compile_source(code,'st','mms_nw_wCyclic.st')
                self.assertEqual([],compiled['diagnostics'])
                self.assertTrue(compiled['compatibility']['runAllowed'])
                parsed=cases(code)
                self.assertEqual([130,140],[b.code for c in parsed if c.function==2 for b in c.branches])
                self.assertIn('IF NOT HMI_EN_Write THEN',code)
                self.assertIn('IF (nw_i + 2) <> nw_rcv_buffer_length THEN',code)
                self.assertIn('nw_rcv_buffer_length >= 9',code)
                self.assertIn('UINT_TO_USINT((nw_i - 5) MOD 256)',code)
                for case in study.wwrite.branches:
                    if case.code in (130,140):
                        original=study.wt[case.body_start:case.end]
                        # Original write/recipe/readonly logic is retained verbatim,
                        # apart from indentation, inside the new preflight guard.
                        normalize=lambda text:' '.join(text.split())
                        self.assertIn(normalize(original),normalize(code))
                with zipfile.ZipFile(io.BytesIO(base64.b64decode(draft['bundleBase64']))) as archive:
                    self.assertEqual({f['name'] for f in draft['files']},set(archive.namelist()))
                    self.assertEqual(mapping,json.loads(archive.read('write_mapping.json')))

    def test_payload_variants_and_hmi_scaling(self):
        for name,expected in [('project 2',{130:[112],140:[89]}),('project 5',{130:[110,115],140:[211]})]:
            study,draft,mapping=self.samples[name]
            self.assertEqual(expected,{g['code']:[v['payloadBytes'] for v in g['variants']] for g in mapping['dataInspect']['groups']})
            self.assertTrue(all(not v['issues'] for g in mapping['dataInspect']['groups'] for v in g['variants']))
        fields=self.samples['project 2'][2]['fields']
        suction=next(f for f in fields if 'hmi_suction_mtr_delay' in f['destinations'])
        self.assertEqual((1000,15000),(number(suction['appliedMin']),number(suction['appliedMax'])))
        roller=self.samples['project 5'][2]['fields'][0]
        self.assertEqual((0,400),(number(roller['appliedMin']),number(roller['appliedMax'])))

    def test_all_variants_preserve_group_and_patch_only_selected_field(self):
        for name,(_,_,mapping) in self.samples.items():
            for group in mapping['dataInspect']['groups']:
                for v in group['variants']:
                    baseline=bytes(i%193 for i in range(v['readPayloadBytes']))
                    for field in v['fields']:
                        if not field['writable'] or field['type'] not in edit.FORMATS: continue
                        with self.subTest(project=name,group=group['code'],variant=v['id'],field=field['id']):
                            replacement=bytes([17])*field['size']
                            request=edit.build_write(7,group['code'],baseline,v,field,replacement)
                            self.assertEqual(len(request),v['payloadBytes']+9)
                            self.assertEqual(bytes([3,7,2]),request[:3])
                            self.assertEqual(v['payloadBytes']+2,int.from_bytes(request[3:5],'big'))
                            self.assertEqual(group['code'],int.from_bytes(request[5:7],'big'))
                            checksum=0
                            for b in request[:-2]:checksum^=b
                            self.assertEqual(checksum,request[-2]);self.assertEqual(2,request[-1])
                            expected=bytearray(v['payloadBytes'])
                            for f in v['fields']:expected[f['writeOffset']:f['writeOffset']+f['size']]=baseline[f['readOffset']:f['readOffset']+f['size']]
                            w=field['writeOffset'];expected[w:w+field['size']]=replacement
                            self.assertEqual(bytes(expected),request[7:-2])

    def test_known_unsafe_groups_are_blocked(self):
        for name,gc in [('project 2',250),('project 5',160),('project 5',180)]:
            with self.subTest(project=name,group=gc):
                study=self.samples[name][0]
                with self.assertRaises(ValueError):generate(study,[gc],reviewed=True)

    def test_generated_preflight_executes_length_machine_and_limit_guards(self):
        # Execute the generated preflight itself in the local bounded runtime.
        # The original commit block is replaced by a marker; no TCP service or
        # physical machine behavior is being simulated by this guard test.
        for name,(study,draft,mapping) in self.samples.items():
            text=draft['files'][0]['text']
            branch=next(b for c in cases(text) if c.function==2 for b in c.branches if b.code==130)
            prefix=re.split(r'ELSIF scw_allow THEN',text[branch.body_start:branch.end])[0]
            guard=prefix+'ELSIF scw_allow THEN write_reached := TRUE; ELSE nw_snd_buffer[2] := 16; END_IF; END_IF;'
            refs={n['name'] for n in walk_ir(compile_source(guard)['sections']) if n.get('op')=='ref'}
            group=next(g for g in mapping['dataInspect']['groups'] if g['code']==130)
            for v in group['variants']:
                review={f['id']:f for f in mapping['fields']}
                wire=bytearray(v['payloadBytes'])
                lower_vars={f['selectedHmi']['minDatapoint'] for f in review.values() if f.get('selectedHmi') and f['selectedHmi'].get('minDatapoint')}
                for f in v['fields']:
                    low=number(review.get(f['id'],{}).get('appliedMin'))
                    high=number(review.get(f['id'],{}).get('appliedMax'))
                    val=float((low+high)/2) if low is not None and high is not None else float(max(0,low)) if low is not None else 0
                    if f['type'] not in ('REAL','LREAL'):val=int(val)
                    if f['type'] in edit.FORMATS:
                        struct.pack_into('<'+edit.FORMATS[f['type']],wire,f['writeOffset'],val)
                request=frame(7,(130).to_bytes(2,'big')+wire,2)
                declarations=[]
                for symbol in refs:
                    known=study.vars.get(symbol.casefold())
                    typ=known['declaration'] if known else 'BOOL' if symbol in ('HMI_EN_Write','write_reached','scw_allow','scw_field_ok') else 'USINT' if symbol=='scw_bool' else 'DINT'
                    initial=None if typ.startswith(('ARRAY','STRING')) else 0 if symbol in lower_vars or known or symbol.startswith('scw_') else 1_000_000
                    if symbol=='HMI_EN_Write':initial=True
                    if symbol=='write_reached':initial=False
                    if symbol=='MACHINE_STATUS':initial=0 if name=='project 2' else 1
                    if symbol=='V4118_6_Display_2Q_Selection':initial=int(v['id'])
                    if symbol=='nw_rcv_buffer':initial=list(request)+[0]*(int(re.search(r'\.\.\s*(\d+)',typ)[1])+1-len(request))
                    if symbol=='nw_rcv_buffer_length':initial=len(request)
                    declarations.append(variable(symbol,typ,initial))
                with self.subTest(project=name,variant=v['id']):
                    runtime=VirtualRuntime(project(guard,declarations))
                    self.assertTrue(runtime.run_allowed,runtime.diagnostics[:4])
                    runtime.command('scan')
                    self.assertEqual('paused',runtime.status,runtime.diagnostics)
                    self.assertTrue(runtime.get_value('write_reached'),[(i,x) for i,x in enumerate(runtime.get_value('nw_error_code')) if x])
                    for label,changes,code in [('short',{'nw_rcv_buffer_length':len(request)-1},13),
                                               ('disabled',{'HMI_EN_Write':False},18),
                                               ('state',{'MACHINE_STATUS':5},18)]:
                        blocked=VirtualRuntime(project(guard,declarations))
                        for key,val in changes.items():blocked.set_value(key,val,return_snapshot=False)
                        blocked.command('scan')
                        self.assertFalse(blocked.get_value('write_reached'),label)
                        self.assertEqual(code,blocked.get_value('nw_snd_buffer')[2],label)
                    # A value outside a literal source/HMI bound must stop the
                    # preflight before the original commit block can run.
                    field=next(f for f in v['fields'] if f['writable'] and number(f.get('max')) is not None and f['type'] in ('REAL','UINT'))
                    invalid=bytearray(request);struct.pack_into('<'+edit.FORMATS[field['type']],invalid,7+field['writeOffset'],float(number(field['max'])+1) if field['type']=='REAL' else int(number(field['max'])+1))
                    blocked=VirtualRuntime(project(guard,declarations));blocked.set_value('nw_rcv_buffer',list(invalid)+[0]*(len(runtime.get_value('nw_rcv_buffer'))-len(invalid)),return_snapshot=False)
                    blocked.command('scan');self.assertFalse(blocked.get_value('write_reached'));self.assertEqual(16,blocked.get_value('nw_snd_buffer')[2])


class EditEndpointTests(ReferenceSamples):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.stack=ExitStack();root=Path(self.temp.name);work=root/'work';work.mkdir()
        self.stack.enter_context(patch.object(accounts,'store',accounts.AccountStore(root/'accounts.sqlite3')))
        self.stack.enter_context(patch.object(runtime_paths,'WORK',work))
        self.stack.enter_context(patch.object(run_history,'WORK',work))
        self.stack.enter_context(patch.object(run_history,'RECORDS',root/'history'))
        self.stack.enter_context(patch.object(run_history,'SNAPSHOTS',work/'history'))
        self.stack.enter_context(patch.object(persistent_store,'DATABASE',root/'application.sqlite3'))
        self.stack.enter_context(patch.object(persistent_store,'READY',False))
        self.client=TestClient(app)
        self.client.post('/api/auth/login',json={'username':'Admin','password':'usopp.2026'})
        api._pending.clear()
    def tearDown(self):
        api._pending.clear();self.client.close();self.stack.close();self.temp.cleanup()
    def body(self,plc,name='project 2',gc=130,variant='0'):
        mapping=self.samples[name][2]
        row={'isWritable':True,'groupCode':gc,'offset':4 if name=='project 2' else 0,
             'tagCode':2,'dataType':'REAL' if name=='project 2' else 'UINT','parameter':'Example setting','min':None,'max':None}
        return {'plc':{'id':'mock-edit','name':'Local mock','endianness':'little'},'ip':'127.0.0.1','writePort':plc.port,
                'machineId':7,'timeoutMs':1000,'parameter':row,'metadata':[row],'mapping':mapping,'variantId':variant}
    def test_confirmed_write_for_both_projects_and_conditional_variants(self):
        for name,vid,val in [('project 2','0','600'),('project 5','0','350'),('project 5','1','380')]:
            mapping=self.samples[name][2];v=mapping['dataInspect']['groups'][0]['variants'][int(vid)]
            baseline=bytes(v['readPayloadBytes'])
            with self.subTest(project=name,variant=vid),MockPLC(v,baseline) as plc:
                body=self.body(plc,name,variant=vid)
                prepared=self.client.post('/api/nami/plc/prepare-edit',json=body)
                self.assertEqual(200,prepared.status_code,prepared.text)
                token=prepared.json()['token']
                self.assertTrue(all(r[2]==1 for r in plc.requests))
                result=self.client.post('/api/nami/plc/send-edit',json={'token':token,'value':val}).json()
                self.assertTrue(result['success'],result);self.assertTrue(result['verified'])
                self.assertEqual(float(val),result['observedValue'])
                self.assertEqual(1,len([r for r in plc.requests if r[2]==2]))
                self.assertEqual(404,self.client.post('/api/nami/plc/send-edit',json={'token':token,'value':val}).status_code)
    def test_changed_baseline_prevents_write(self):
        v=self.samples['project 2'][2]['dataInspect']['groups'][0]['variants'][0]
        with MockPLC(v,bytes(v['readPayloadBytes'])) as plc:
            token=self.client.post('/api/nami/plc/prepare-edit',json=self.body(plc)).json()['token']
            plc.baseline[-1]=1
            result=self.client.post('/api/nami/plc/send-edit',json={'token':token,'value':'600'}).json()
            self.assertFalse(result['success']);self.assertFalse(result['writeAttempted'])
            self.assertFalse(any(r[2]==2 for r in plc.requests))
    def test_rejection_and_unconfirmed_readback_are_not_success(self):
        v=self.samples['project 2'][2]['dataInspect']['groups'][0]['variants'][0]
        for code,apply in [(18,False),(16,True),(0,False)]:
            with self.subTest(code=code,apply=apply),MockPLC(v,bytes(v['readPayloadBytes']),code,apply) as plc:
                token=self.client.post('/api/nami/plc/prepare-edit',json=self.body(plc)).json()['token']
                result=self.client.post('/api/nami/plc/send-edit',json={'token':token,'value':'600'}).json()
                self.assertFalse(result['success']);self.assertFalse(result['verified']);self.assertTrue(result['error'])
    def test_invalid_flag_ybs_layout_limits_and_expiry_do_not_send(self):
        v=self.samples['project 2'][2]['dataInspect']['groups'][0]['variants'][0]
        with MockPLC(v,bytes(v['readPayloadBytes'])) as plc:
            body=self.body(plc)
            for mutation in [dict(parameter={**body['parameter'],'isWritable':False}),dict(frameProtocol='ybs'),dict(variantId='missing')]:
                response=self.client.post('/api/nami/plc/prepare-edit',json={**body,**mutation})
                self.assertEqual(400,response.status_code,response.text)
            self.assertFalse(plc.requests)
            token=self.client.post('/api/nami/plc/prepare-edit',json=body).json()['token']
            for val in ['NaN','Infinity','',True,'249','1101','1e99']:
                self.assertEqual(400,self.client.post('/api/nami/plc/send-edit',json={'token':token,'value':val}).status_code)
            api._pending[token]['expires']=0
            self.assertEqual(409,self.client.post('/api/nami/plc/send-edit',json={'token':token,'value':'600'}).status_code)
            self.assertFalse(any(r[2]==2 for r in plc.requests))
    def test_layout_gaps_and_overlap_rejected(self):
        mapping=copy.deepcopy(self.samples['project 2'][2]);row={'groupCode':130,'offset':4,'dataType':'REAL','isWritable':True}
        mapping['dataInspect']['groups'][0]['variants'][0]['fields'][0]['writeOffset']=1
        with self.assertRaisesRegex(ValueError,'overlap'):edit.select_field(mapping,row,'0')


if __name__=='__main__':unittest.main()
