"""Read-derived frames, original setting policies, and local ST execution."""
import base64
import hashlib
import json
import importlib.util
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest

from python_engine.spinconnect_write import Study, generate, cases, declarations
from python_engine.spinconnect_read_basis import catalog
from virtual_plc.core.compiler import compile_source
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.tests.test_runtime import project, variable


READ = '''IF nw_rcv_buffer[2] = 1 THEN
CASE nw_group_code OF
130: (* Settings and live context *)
nw_snd_buffer[2] := 0;
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 8;
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Actual),4);
nw_i := nw_i + 4;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Speed),2);
nw_i := nw_i + 2;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Flag),1);
nw_i := nw_i + 1;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(State),1);
nw_i := nw_i + 1;
nw_snd_buffer_length := nw_i;
nw_snd_response := TRUE;
20: (* Monitoring only *)
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Actual),4);
nw_i := nw_i + 4;
nw_snd_buffer_length := nw_i;
ELSE
nw_snd_buffer[2] := 14;
END_CASE;
END_IF;
'''

WRITE = '''IF nw_rcv_buffer[2] = 1 THEN
CASE nw_group_code OF
10: nw_snd_buffer[2] := 0;
11: nw_snd_buffer[2] := 0;
130: (* Old settings layout *)
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Flag),1);
nw_i := nw_i + 1;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Actual),4);
nw_i := nw_i + 4;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Speed),2);
nw_i := nw_i + 2;
nw_snd_buffer_length := nw_i;
nw_snd_response := TRUE;
ELSE
nw_snd_buffer[2] := 14;
END_CASE;
ELSIF nw_rcv_buffer[2] = 2 THEN
CASE nw_group_code OF
130: (* Write settings *)
nw_snd_buffer[2] := 0;
nw_i := 7;
nw_j := 0;
IF (MACHINE_STATUS = 1) THEN
memcpy(ADR(temp_flag),ADR(nw_rcv_buffer[nw_i]),1);
nw_i := nw_i + 1;
nw_j := nw_j + 1;
Flag := temp_flag;
memcpy(ADR(temp_real),ADR(nw_rcv_buffer[nw_i]),4);
nw_i := nw_i + 4;
nw_j := nw_j + 1;
memcpy(ADR(temp_speed),ADR(nw_rcv_buffer[nw_i]),2);
nw_i := nw_i + 2;
nw_j := nw_j + 1;
IF (temp_speed >= 1) AND (temp_speed <= 100) THEN
Speed := temp_speed;
ELSE
nw_snd_buffer[2] := 16;
END_IF;
ELSE
nw_snd_buffer[2] := 18;
END_IF;
nw_snd_buffer_length := 5;
nw_snd_response := TRUE;
ELSE
nw_snd_buffer[2] := 14;
END_CASE;
END_IF;
'''

VARS = '''VAR
nw_rcv_buffer : ARRAY[0..255] OF USINT;
nw_snd_buffer : ARRAY[0..255] OF USINT;
nw_error_code : ARRAY[0..99] OF USINT;
nw_rcv_buffer_length : UINT;
nw_snd_buffer_length : UINT;
nw_i : UINT;
nw_j : UINT;
nw_group_code : UINT;
nw_snd_response : BOOL;
nxt_adr : UDINT;
temp_flag : BOOL;
temp_real : REAL;
temp_speed : UINT;
END_VAR
'''


def fixture(root):
    r = root/'Logical/SpinConnect/mms_nw_r';r.mkdir(parents=True)
    w = root/'Logical/SpinConnect/mms_nw_w';w.mkdir(parents=True)
    (r/'mms_nw_rCyclic.st').write_text(READ)
    (w/'mms_nw_wCyclic.st').write_text(WRITE)
    (w/'mms_nw_w.var').write_text(VARS)
    (root/'Logical/Global.var').write_text('VAR\nActual : REAL;\nSpeed : UINT;\nFlag : BOOL;\nState : USINT;\nMACHINE_STATUS : USINT;\nHMI_EN_Write : BOOL;\nEND_VAR')
    hmi=root/'Logical/HMI';hmi.mkdir()
    (hmi/'Settings.page').write_text('''<Page><Controls><Control Name="Speed"><Property Name="ValueDatapoint" Value="Variable[Local.Speed]"/><Property Name="StyleClass" Value="NumericInput"/><Property Name="MinValue" Value="1"/><Property Name="MaxValue" Value="100"/></Control></Controls></Page>''')
    return Study(root)


class ReadBasisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name);self.study=fixture(self.root)
        self.before={str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}

    def tearDown(self):
        self.assertEqual(self.before,{str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()})
        self.temp.cleanup()

    def draft(self):return generate(self.study,[130],reviewed=True)

    def test_catalog_comes_from_read_source_and_marks_unmapped_groups(self):
        data=self.study.public();self.assertEqual('mms_nw_r',data['layoutBasis'])
        self.assertEqual([130,20],[g['code'] for g in data['groups']])
        group=data['groups'][0]
        self.assertEqual([8],group['payloadVariants']);self.assertEqual([7],group['legacyPayloadVariants'])
        self.assertEqual(['Actual','Speed','Flag','State'],[f['readVariable'] for f in group['fields']])
        self.assertEqual([False,True,True,False],[f['writable'] for f in group['fields']])
        with self.assertRaisesRegex(ValueError,'No setting-write policy'):generate(self.study,[20],reviewed=True)
        with self.assertRaisesRegex(ValueError,'does not exist in mms_nw_r'):generate(self.study,[999],reviewed=True)

    def test_generated_function_one_and_mapping_use_read_layout(self):
        draft=self.draft();code=draft['files'][0]['text']
        self.assertEqual([],compile_source(code)['diagnostics'])
        branch=next(b for c in cases(code) if c.function==1 for b in c.branches if b.code==130)
        body=code[branch.body_start:branch.end]
        self.assertLess(body.index('ADR(Actual)'),body.index('ADR(Speed)'))
        self.assertIn('ADR(State)',body)
        mapping=json.loads(next(f['text'] for f in draft['files'] if f['name']=='write_mapping.json'))
        self.assertEqual('mms_nw_r',mapping['layoutBasis'])
        layout=mapping['dataInspect']['groups'][0]['variants'][0]
        self.assertEqual((8,8),(layout['readPayloadBytes'],layout['payloadBytes']))
        self.assertEqual([(0,4),(4,2),(6,1),(7,1)],[(f['writeOffset'],f['size']) for f in layout['fields']])
        self.assertTrue(draft['bundleBase64']);self.assertTrue(base64.b64decode(draft['bundleBase64']).startswith(b'PK'))

    def runtime(self, *,speed=65,flag=1,machine=1,enabled=True,length=None):
        draft=self.draft();code=draft['files'][0]['text'];branch=next(b for c in cases(code) if c.function==2 for b in c.branches if b.code==130)
        body=code[branch.body_start:branch.end]
        symbols={}
        for file in draft['files']:
            if file['name'].endswith('.var'):symbols.update(declarations(file['text']))
        symbols.update(declarations((self.root/'Logical/Global.var').read_text()))
        wire=bytearray(17);wire[7:15]=struct.pack('<fHBB',77.5,speed,flag,9)
        initial={'nw_rcv_buffer':list(wire)+[0]*(256-len(wire)), 'nw_rcv_buffer_length':len(wire) if length is None else length,
                 'MACHINE_STATUS':machine,'HMI_EN_Write':enabled,'Actual':12.5,'Speed':20,'Flag':False,'State':3}
        initial={name.casefold():value for name,value in initial.items()}
        runtime=VirtualRuntime(project(body,[variable(name,info['declaration'],initial.get(name)) for name,info in symbols.items()]))
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        runtime.command('scan');self.assertEqual('paused',runtime.status,runtime.diagnostics)
        return runtime,wire

    def test_generated_adapter_executes_original_assignments_from_read_positions(self):
        runtime,wire=self.runtime()
        self.assertEqual(65,runtime.get_value('Speed'));self.assertTrue(runtime.get_value('Flag'))
        self.assertEqual(12.5,runtime.get_value('Actual'));self.assertEqual(3,runtime.get_value('State'))
        self.assertEqual(0,runtime.get_value('nw_snd_buffer')[2])
        self.assertEqual(list(wire),runtime.get_value('nw_rcv_buffer')[:len(wire)])
        self.assertEqual(len(wire),runtime.get_value('nw_rcv_buffer_length'))

    def test_preflight_rejects_short_length_machine_disabled_and_bad_values(self):
        for changes,status in [({'length':16},13),({'machine':2},18),({'enabled':False},18),({'speed':101},16),({'flag':2},16)]:
            with self.subTest(changes=changes):
                runtime,_=self.runtime(**changes)
                self.assertEqual(20,runtime.get_value('Speed'))
                self.assertFalse(runtime.get_value('Flag'))
                self.assertEqual(status,runtime.get_value('nw_snd_buffer')[2])

    def test_copy_increment_mismatch_is_blocked(self):
        self.study.rt=READ.replace('nw_i := nw_i + 4;','nw_i := nw_i + 1;',1)
        self.study.rcases=cases(self.study.rt)
        self.assertTrue(any('copies 4 bytes but advances 1' in e for e in catalog(self.study)[0]['issues']))
        with self.assertRaisesRegex(ValueError,'copies 4 bytes but advances 1'):self.draft()

    def test_data_inspect_uses_the_read_offset_and_preserves_all_context(self):
        from backend.core.nami_edit import select_field,build_write
        draft=self.draft();mapping=json.loads(next(f['text'] for f in draft['files'] if f['name']=='write_mapping.json'))
        row={'groupCode':130,'offset':4,'dataType':'UINT','isWritable':True}
        layout,field=select_field(mapping,row,'0')
        baseline=struct.pack('<fHBB',77.5,20,1,9)
        request=build_write(7,130,baseline,layout,field,struct.pack('<H',65))
        self.assertEqual(17,len(request))
        self.assertEqual(struct.pack('<fHBB',77.5,65,1,9),request[7:-2])
        with self.assertRaisesRegex(ValueError,'no unique writable source field'):
            select_field(mapping,{'groupCode':130,'offset':0,'dataType':'REAL','isWritable':True},'0')

    def test_real_reference_groups_and_byte_findings(self):
        root=Path(__file__).resolve().parents[2]
        for name,count in [('project 1',31),('project 2',31),('project 5',32)]:
            if not (root/name).is_dir():continue
            study=Study(root/name);groups=study.public()['groups'];self.assertEqual(count,len(groups))
            g140=next(g for g in groups if g['code']==140)
            if name in ('project 1','project 2'):self.assertTrue(g140['issues'])
            else:
                self.assertEqual([],g140['issues']);draft=generate(study,[130,140],reviewed=True)
                self.assertEqual([],compile_source(draft['files'][0]['text'])['diagnostics'])
                mapping=json.loads(next(f['text'] for f in draft['files'] if f['name']=='write_mapping.json'))
                self.assertEqual({130:[115],140:[211]},{g['code']:sorted({v['payloadBytes'] for v in g['variants']}) for g in mapping['dataInspect']['groups']})
                # The user's Motor pulley example remains the original write
                # syntax, including the typed temp, 2-byte cursor and 0..310.
                snippet=re.search(r'memcpy\(ADR\(nw_temp_UINT_received_value\),ADR\(nw_rcv_buffer\[nw_i\]\),2\);\s*\(\*Motor pulley\*\).*?END_IF',study.wt,re.S)
                self.assertIsNotNone(snippet)
                self.assertIn('TS_Teeth_in_MOT_Pulley_VD5100 := nw_temp_UINT_received_value;',snippet[0])
                self.assertIn('(nw_temp_UINT_received_value <= 310)',snippet[0])
                self.assertIn(' '.join(snippet[0].split()),' '.join(draft['files'][0]['text'].split()))

    def test_multiline_comment_keeps_reported_bool_declaration(self):
        path=Path(__file__).resolve().parents[1]/'python_engine/packet_validation_report_uSOPp_v1.71_final.py'
        spec=importlib.util.spec_from_file_location('read_basis_packet_declarations',path)
        engine=importlib.util.module_from_spec(spec);sys.modules[spec.name]=engine;spec.loader.exec_module(engine)
        symbols=engine.parse_var_sections('VAR RETAIN\nHK1_RYC_SPL : BOOL; (* comment\nends here *)\nEND_VAR\n')
        self.assertEqual('BOOL',symbols['HK1_RYC_SPL'].name)
        self.assertEqual(1,engine.size_from_type_info(symbols['HK1_RYC_SPL']))
        archived=Path(__file__).resolve().parents[1]/'.usopp_workspaces/15664_71mh4apw/source/LR9AXV13750/Logical/Global.var'
        if archived.is_file():
            self.assertEqual('BOOL',engine.parse_var_sections(archived.read_text(encoding='utf8'))['HK1_RYC_SPL'].name)


if __name__=='__main__':unittest.main()
