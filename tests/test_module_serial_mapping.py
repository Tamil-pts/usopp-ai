import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from python_engine import module_serial_mapping as serial
from python_engine import rule_engine_v4_30 as engine


class ModuleSerialMappingTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.rule = serial.normalize_configuration({
            'id': 'BR_MODULE_SERIAL_420', 'name': 'Module serial no mapping',
        })
        self.write('LastUser.set', '<ProjectSettings><ConfigurationManager ActiveConfigurationName="Active"/></ProjectSettings>')
        self.write('Physical/Active/Hardware.hw', '''<Hardware>
  <Module Name="4PP065.IF23-1" Type="4PP065.IF23-1">
    <Connection Connector="SS" TargetModule="PLC1" TargetConnector="SS1"/>
  </Module>
  <Module Name="PLC1" Type="4PP065.0571-K37"/>
  <Module Name="Remote1" Type="X20DI9371"/>
  <Module Name="Terminal1" Type="X20TB12"/>
  <Module Name="Base1" Type="X20BM11"/>
</Hardware>''')
        self.write('Physical/Active/PLC1/Cpu.sw', '<Cpu><Task Name="mms_nw_r" Source="SpinConnect.mms_nw_r.prg"/></Cpu>')
        self.write('Physical/Active/PLC1/IoMap.iom', '''VAR_CONFIG
  Cyclic#1.Serials[0] AT %ID."Remote1".SerialNumber;
  Serials[3] AT %ID."PLC1".SerialNumber;
END_VAR''')
        self.write('Logical/Global.var', '''VAR_GLOBAL
  Serials : ARRAY[0..3] OF UDINT;
  CpuSerial : UDINT;
  RemoteSerial : UDINT;
  nw_i : UINT;
  nw_snd_buffer : ARRAY[0..511] OF BYTE;
END_VAR''')
        self.packet('memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Serials[0]),16);\nnw_i := nw_i + 16;', 16)

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def packet(self, copies, size):
        self.write('Logical/SpinConnect/mms_nw_r/mms_nw_rCyclic.st', f'''PROGRAM _CYCLIC
CASE nw_group_code OF
420:
  nw_snd_buffer[2] := 0;
  nw_snd_buffer[3] := {size // 256};
  nw_snd_buffer[4] := {size % 256};
  nw_i := 5;
  {copies}
  nw_snd_buffer_length := ((nw_snd_buffer[3] * 256) + nw_snd_buffer[4] + 5);
  nw_snd_response := TRUE;
END_CASE
END_PROGRAM''')

    def evaluate(self):
        result = engine.evaluate(self.root, [self.rule], self.root / 'reports')['results'][0]
        self.assertNotIn('Rule evaluation error:', result['actual'], result)
        return result

    def failures(self, result):
        return [row for row in result['evidence'] if row['status'] == 'FAIL']

    def test_panel_interface_accessory_and_passive_bases_are_not_controllers(self):
        result = self.evaluate()
        self.assertEqual('PASS', result['status'], result)
        traced = [row for row in result['evidence'] if row['check'] == 'SerialNumber -> GC 420']
        self.assertEqual(2, len(traced))
        self.assertTrue(all(row['status'] == 'PASS' for row in traced))
        self.assertTrue(any(row['check'] == 'GC 420 serial array copy bounds' for row in result['evidence']))

    def test_scalar_serial_numbers_are_supported(self):
        self.write('Physical/Active/PLC1/IoMap.iom', '''VAR_CONFIG
  CpuSerial AT %ID."PLC1".SerialNumber;
  RemoteSerial AT %ID."Remote1".SerialNumber;
END_VAR''')
        self.packet('''memcpy(ADR(nw_snd_buffer[nw_i]),ADR(CpuSerial),4);
nw_i := nw_i + 4;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(RemoteSerial),4);
nw_i := nw_i + 4;''', 8)
        self.assertEqual('PASS', self.evaluate()['status'])

    def test_direct_script_execution_used_by_the_backend(self):
        rule_file = self.root / 'rule.json'
        rule_file.write_text(json.dumps({'rules': [self.rule]}), encoding='utf-8')
        output = self.root / 'result.json'
        completed = subprocess.run([
            sys.executable, str(Path(engine.__file__).resolve()),
            '--project', str(self.root), '--rules', str(rule_file),
            '--output-json', str(output),
        ], cwd=self.root, env={**os.environ, 'PYTHONPATH': ''},
            capture_output=True, text=True, timeout=60)
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(output.read_text(encoding='utf-8'))['results'][0]
        self.assertEqual('PASS', result['status'], result)
        self.assertTrue(result['structuredRequirements'])

    def test_missing_controller_serial_binding_still_fails(self):
        self.write('Physical/Active/PLC1/IoMap.iom', 'Serials[0] AT %ID."Remote1".SerialNumber;')
        result = self.evaluate()
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(any(row['check'] == 'Module SerialNumber binding' and 'PLC1' in row['expected'] for row in self.failures(result)))

    def test_real_second_controller_still_requires_target_ownership(self):
        path = self.root / 'Physical/Active/Hardware.hw'
        path.write_text(path.read_text().replace('</Hardware>', '<Module Name="PLC2" Type="X20CP0484"/></Hardware>'))
        result = self.evaluate()
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(any(row['check'] == 'PLC target ownership' and '2 controllers' in row['actual'] for row in self.failures(result)))

    def test_bulk_copy_outside_array_bounds_fails(self):
        self.packet('memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Serials[0]),20);\nnw_i := nw_i + 20;', 20)
        result = self.evaluate()
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(any(row['check'] == 'GC 420 serial array copy bounds' for row in self.failures(result)))

    def test_bound_element_not_in_bulk_copy_fails(self):
        self.packet('memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Serials[0]),12);\nnw_i := nw_i + 12;', 12)
        result = self.evaluate()
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(any(row['check'] == 'SerialNumber -> GC 420' and 'Serials[3]' in row['actual'] for row in self.failures(result)))

    def test_duplicate_variable_ownership_fails(self):
        self.write('Physical/Active/PLC1/IoMap.iom', '''VAR_CONFIG
  Cyclic#1.Serials[0] AT %ID."Remote1".SerialNumber;
  Serials[0] AT %ID."PLC1".SerialNumber;
END_VAR''')
        result = self.evaluate()
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(any(row['check'] == 'Serial variable ownership' for row in self.failures(result)))

    def test_packet_header_mismatch_fails(self):
        self.packet('memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Serials[0]),16);\nnw_i := nw_i + 16;', 12)
        result = self.evaluate()
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(any(row['check'] == 'GC 420 payload length' for row in self.failures(result)))

    def test_wrong_serial_datatype_fails(self):
        path = self.root / 'Logical/Global.var'
        path.write_text(path.read_text().replace('ARRAY[0..3] OF UDINT', 'ARRAY[0..3] OF REAL'))
        result = self.evaluate()
        self.assertEqual('FAIL', result['status'])
        self.assertTrue(any(row['check'] == 'Serial declaration cross reference' for row in self.failures(result)))

    def test_inactive_configuration_is_excluded(self):
        self.write('Physical/Inactive/Hardware.hw', '<Hardware><Module Name="Unmapped" Type="X20CP0484"/></Hardware>')
        self.write('Physical/Inactive/PLC2/IoMap.iom', 'Unused AT %ID."Unmapped".SerialNumber;')
        result = self.evaluate()
        self.assertEqual('PASS', result['status'], result)
        self.assertEqual('Active', result['activeConfiguration'])
        self.assertTrue(all('Physical/Inactive/' not in row.get('file', '') for row in result['evidence']))

    def test_unknown_active_configuration_fails(self):
        self.write('LastUser.set', '<ProjectSettings><ConfigurationManager ActiveConfigurationName="Missing"/></ProjectSettings>')
        result = self.evaluate()
        self.assertEqual('FAIL', result['status'])
        self.assertEqual('Active configuration selection', self.failures(result)[0]['check'])


if __name__ == '__main__':
    unittest.main()
