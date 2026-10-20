"""Regression checks for source topology, Basic calls and explicit program tests."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from virtual_plc.core.hardware import read_hardware
from virtual_plc.core.module_help import module_details, safe_path
from virtual_plc.core.program_test import program_model
from virtual_plc.core.project import upgrade_task_slots
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.tests.test_runtime import project, variable


class BasicAndMemoryTests(unittest.TestCase):
    def test_only_empty_unresolved_task_slot_is_skipped(self):
        empty = {'name': 'Empty', 'source': '', 'programs': [], 'line': 2}
        missing = {'name': 'Missing', 'source': 'Other.prg', 'programs': [], 'line': 3}
        resolved = {'name': 'Main', 'source': '', 'programs': ['main'], 'line': 4}
        model = {'tasks': [{'source': 'CPU.sw', 'assignments': [empty, missing, resolved]}],
                 'diagnostics': [{'code': 'program-unresolved', 'severity': 'error', 'source': 'CPU.sw',
                                  'line': line, 'message': name + ' unresolved'} for name,line in [('Empty',2),('Missing',3)]]}
        upgrade_task_slots(model)
        self.assertTrue(empty['placeholder'])
        self.assertNotIn('placeholder', missing)
        self.assertNotIn('placeholder', resolved)
        self.assertEqual('info', model['diagnostics'][0]['severity'])
        self.assertEqual('error', model['diagnostics'][1]['severity'])

    def test_basic_comments_else_if_strings_and_alias_calls(self):
        code = '''PROGRAM _CYCLIC
; MissingTag = 9
IF Choice = 0 THEN (* an inline block comment *)
Result = 1
ELSE IF Choice = 1 THEN
Result = 2
ELSE
Result = 3
ENDIF
Label = 'abc'
Timer.IN = TRUE
Timer.PT = T#10ms
Timer FUB TON()
END_PROGRAM'''
        model = project(code, [variable('Choice'), variable('Result'), variable('Label','STRING[20]',''), variable('Timer','TON',None)], 'ab')
        runtime = VirtualRuntime(model)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        for choice, result in [(0,1),(1,2),(2,3)]:
            runtime.set_value('Choice', choice, return_snapshot=False)
            runtime.command('scan')
            self.assertEqual(result, runtime.get_value('Result'))
            self.assertEqual('abc', runtime.get_value('Label'))
        self.assertTrue(runtime.get_value('Timer.Q'))

    def test_alias_type_mismatch_blocks(self):
        runtime = VirtualRuntime(project('Timer FUB TOF()', [variable('Timer','TON',None)], 'ab'))
        self.assertFalse(runtime.run_allowed)
        self.assertTrue(any(d['code']=='FUB_TYPE' for d in runtime.diagnostics))

    def test_library_formals_do_not_allocate_but_real_instances_are_checked(self):
        formal = variable('Parameter','ANY',None,source='Logical/Libraries/operator/operator.fun')
        runtime = VirtualRuntime(project('Result := Result + 1;', [variable('Result'),formal]))
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        self.assertFalse(any(v['name']=='Parameter' for v in runtime.memory.records.values()))
        real = variable('Controller','LCRPIDTune',None,source='Logical/Main/Main.var')
        runtime = VirtualRuntime(project('Controller();', [real]))
        self.assertFalse(runtime.run_allowed)

    def test_program_scope_preserves_parent_and_checks_selected_dependencies(self):
        model = project('Result := Result + 1;', [variable('Result')])
        model['programs'][0].update(entry='cyclic',kind='program')
        model['diagnostics'] = [{'severity':'error','code':'program-unresolved','message':'Other task missing'}]
        original = deepcopy(model)
        selected = program_model(model, 'main', 'parent')
        runtime = VirtualRuntime(selected)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command('scan')
        self.assertEqual(1,runtime.get_value('Result'))
        self.assertEqual(original,model)
        self.assertFalse(selected['executionScope']['completeMachineExecution'])
        model['programs'][0]['code'] = 'MissingVendor();'
        self.assertFalse(VirtualRuntime(program_model(model,'main','parent')).run_allowed)


class TopologyTests(unittest.TestCase):
    @patch('virtual_plc.core.hardware_topology.module_details', return_value={'available':False})
    def test_rack_and_remote_connections_use_bases_and_hwl_coordinates(self, reference):
        sources = {'Physical/C/Hardware.hw': '''<Hardware>
          <Module Name="PLC1" Type="X20CP1586"><Connection Connector="SL" TargetModule="Base" TargetConnector="SL1"/></Module>
          <Module Name="DI" Type="X20DI9371"><Connection Connector="SL" TargetModule="Slot1" TargetConnector="SL1"/></Module>
          <Module Name="Receiver" Type="X20BR9300"><Connection Connector="X2X1" TargetModule="DI" TargetConnector="X2X2"><Cable/></Connection></Module>
          <Module Name="Base" Type="X20BB52"/>
          <Module Name="Slot1" Type="X20BM11"><Connection Connector="X2X1" TargetModule="Base" TargetConnector="IF5"/></Module>
        </Hardware>''', 'Physical/C/Hardware.hwl': '''<Topology><Modules>
          <Module Name="PLC1" X="10" Y="20"/><Module Name="DI" X="50" Y="20"/>
          <Module Name="Receiver" X="30" Y="200"/>
        </Modules><Links><Link From="DI" To="Receiver" FromPort="X2X2" ToPort="X2X1"/></Links></Topology>'''}
        hardware = read_hardware(sources,'C',[])
        nodes={n['name']:n for n in hardware['topology']['nodes']}
        self.assertEqual(200,nodes['Receiver']['position']['y'])
        self.assertEqual('ST1',nodes['DI']['station'])
        self.assertEqual('ST1',nodes['Receiver']['station'])
        self.assertTrue(any(e['from']=='C:PLC1' and e['to']=='C:DI' and e['fromPort']=='IF5' for e in hardware['topology']['edges']))
        self.assertNotIn('Base',nodes)

    def test_module_help_paths_are_confined_to_hardware(self):
        for path in ['../../backend/app.py','AS12/Help-en/Data/programming/programmingmodel_compliancelist.html']:
            with self.assertRaises(ValueError): safe_path(path)


if __name__=='__main__': unittest.main()
