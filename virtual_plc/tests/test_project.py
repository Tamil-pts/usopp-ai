"""Adapter acceptance fixtures; sources are always read-only inputs."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from virtual_plc.core.project import analyze_project


class ProjectAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.write('Test.apj', '<?AutomationStudio Version="4.12.1"?><Project/>')
        self.write('LastUser.set', '<Settings><ConfigurationManager ActiveConfigurationName="Config1"/></Settings>')
        self.write('Physical/Config1/Hardware.hw', '''<Hardware>
          <Module Name="PLC1" Type="X20CP1586"><Parameter ID="Cyclic1Duration" Value="10000"/></Module>
          <Module Name="Inputs" Type="X20DI9371"><Connection Connector="X2X" TargetModule="PLC1" TargetConnector="IF1"/></Module>
        </Hardware>''')
        self.write('Physical/Config1/Hardware.hwl', '')
        self.write('Physical/Config1/PLC1/CPU.sw', '''<SwConfiguration><TaskClass Name="Cyclic#1">
          <Task Name="Main" Source="Main.prg"/>
          <Task Name="Disabled" Source="Disabled.prg" Disabled="true"/>
        </TaskClass></SwConfiguration>''')
        self.write('Physical/Config1/PLC1/IoMap.iom', 'VAR_CONFIG\n::Start AT %IX."Inputs".DigitalInput01;\nEND_VAR')
        self.write('Logical/Global.var', 'VAR_GLOBAL RETAIN\nStart : BOOL := TRUE;\nCounter : DINT := 2;\nEND_VAR')
        self.write('Logical/Types.typ', '''TYPE
          Position : STRUCT
            X : REAL := 1.5;
            Y : REAL;
          END_STRUCT;
          States : (Stopped := 0, Running := 5, Paused);
          Samples : ARRAY[-1..2] OF REAL;
        END_TYPE''')
        self.write('Logical/Main/IEC.prg', '<Program><Files><File>MainInit.st</File><File>MainCyclic.st</File><File Private="true">Main.var</File></Files></Program>')
        self.write('Logical/Main/MainInit.st', 'PROGRAM _INIT\nCounter := 0;\nEND_PROGRAM')
        self.write('Logical/Main/MainCyclic.st', 'PROGRAM _CYCLIC\nIF Start THEN Counter := Counter + 1; END_IF;\nEND_PROGRAM')
        self.write('Logical/Main/Main.var', 'VAR\nTimer : TON;\nEND_VAR')
        self.write('Temp/Bogus.st', 'DO_NOT_READ := TRUE;')
        self.write('Logical/HMI/Pages/Main.page', '''<Page Name="Main"><Property Name="Width" Value="320"/><Property Name="Height" Value="240"/>
         <Layers><Layer Name="Default"><Controls>
          <Control Name="Start" ClassId="0x00001002">
           <Property Name="Left" Value="12"/><Property Name="Top" Value="21"/>
           <Property Name="Width" Value="80"/><Property Name="Height" Value="30"/>
           <Property Name="CompletionDatapoint" Value="Source[global].Variable[Local.Start]"/>
           <Property Name="CompletionValue" Value="1"/>
          </Control>
          <Control Name="Value" ClassId="0x00001007"><Property Name="ValueDatapoint" Value="Source[global].Variable[Local.Counter]"/></Control>
         </Controls></Layer></Layers></Page>''')
        self.write('Logical/VCShared/TextGroups/Status.txtgrp', '''<TextGroup Name="Status"><TextLayer LanguageId="en"><Text ID="1" Value="Ready"/></TextLayer><IndexMap><Index ID="1" Value="0"/></IndexMap></TextGroup>''')

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def test_hardware_tasks_declarations_hmi_and_source_integrity(self):
        before = {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.root.rglob('*') if p.is_file()}
        progress = []
        model = analyze_project(self.root, progress.append)
        after = {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual('4.12', model['projectInfo']['automationStudioVersion'])
        self.assertEqual('X20CP1586', model['hardware']['controllers'][0]['model'])
        self.assertEqual(1, len(model['hardware']['modules']))
        self.assertEqual(12, model['hardware']['modules'][0]['channelCount'])
        self.assertEqual(1, model['hardware']['modules'][0]['mappedChannelCount'])
        self.assertEqual('Start', model['hardware']['channels'][0]['variable'])
        task = model['tasks'][0]
        self.assertEqual(10, task['intervalMs'])
        self.assertEqual(['Logical/Main/MainCyclic.st'], task['programs'])
        self.assertEqual(['Logical/Main/MainInit.st'], task['initializationPrograms'])
        self.assertFalse(task['assignments'][1]['enabled'])
        start = next(v for v in model['variables'] if v['name'] == 'Start')
        self.assertTrue(start['initial'])
        self.assertTrue(start['retain'])
        self.assertEqual('@global', start['scope'])
        self.assertEqual([[-1, 2]], model['types']['Samples']['bounds'])
        self.assertEqual(6, model['types']['States']['values']['Paused'])
        self.assertEqual('X', model['types']['Position']['fields'][0]['name'])
        self.assertNotIn('Temp/Bogus.st', {f['path'] for f in model['files']})
        page = model['hmi']['pages'][0]
        self.assertEqual(320, page['width'])
        self.assertEqual('write', page['objects'][0]['completion']['kind'])
        self.assertEqual('@global:Start', page['objects'][0]['completion']['variable'])
        self.assertIsNone(page['objects'][0]['action'])  # A completion write alone is not a key action.
        self.assertEqual('@global:Counter', page['objects'][1]['binding'])
        self.assertEqual('Ready', model['hmi']['textGroups']['Logical/VCShared/TextGroups/Status.txtgrp']['0']['en'])
        self.assertTrue(progress)
        json.dumps(model, allow_nan=False)

    def test_cancellation_is_observed_before_loading(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(InterruptedError):
            analyze_project(self.root, cancel=event)

    def test_hmi_does_not_guess_datasource_scope_or_status_visibility(self):
        from virtual_plc.core.hmi import binding, read_hmi
        self.assertEqual('Start', binding('Source[global].Variable[Local.Start]'))
        self.assertIsNone(binding('Source[local].Variable[Local.Start]'))
        layout = {'name': 'Main', 'width': 320, 'height': 200, 'layers': [{
            'id': 'base', 'name': 'Base', 'controls': [{'id': '1', 'name': 'Value', 'class': 'numeric',
                'left': 0, 'top': 0, 'width': 80, 'height': 20,
                'effective_properties': {
                    'ValueDatapoint': 'Source[local].Variable[Local.Counter]',
                    'StatusDatapoint': 'Source[global].Variable[Local.Status]'}}]}]}
        diagnostics = []
        with patch('virtual_plc.core.hmi.hmi_screen_layout', return_value=layout):
            result = read_hmi(self.root, {'Main.page': '<Page/>'}, diagnostics)
        control = result['pages'][0]['objects'][0]
        self.assertIsNone(control['binding'])
        self.assertIsNone(control['visibilityBinding'])
        self.assertTrue(control['visible'])
        self.assertEqual('Status', control['statusBinding'])
        self.assertEqual({'hmi-datasource-unresolved'},
                         {row['code'] for row in diagnostics})

    def test_unknown_task_interval_remains_unresolved(self):
        self.write('Physical/Config1/Hardware.hw', '<Hardware><Module Name="PLC1" Type="X20CP1586"/></Hardware>')
        model = analyze_project(self.root)
        self.assertIsNone(model['tasks'][0]['intervalMs'])
        self.assertTrue(any(d['code'] == 'task-interval-unresolved' for d in model['diagnostics']))

    def test_empty_task_source_is_unassigned_but_missing_nonempty_source_blocks(self):
        self.write('Physical/Config1/PLC1/CPU.sw', '''<SwConfiguration><TaskClass Name="Cyclic#1">
          <Task Name="Empty" Source=""/><Task Name="Missing" Source="NotFound.prg"/>
        </TaskClass></SwConfiguration>''')
        model = analyze_project(self.root)
        assignments = model['tasks'][0]['assignments']
        self.assertTrue(assignments[0]['placeholder'])
        self.assertEqual([], model['tasks'][0]['programs'])
        self.assertTrue(any(d['code']=='task-placeholder' and d['severity']=='info' for d in model['diagnostics']))
        self.assertEqual(1, sum(d['code']=='program-unresolved' for d in model['diagnostics']))

    def test_other_physical_configuration_never_mixes_hardware(self):
        self.write('Physical/Other/Hardware.hw', '<Hardware><Module Name="PLC1" Type="OTHER"/></Hardware>')
        model = analyze_project(self.root)
        self.assertEqual(['X20CP1586'], [c['model'] for c in model['hardware']['controllers']])
        self.assertIn('Physical/Other/Hardware.hw', {f['path'] for f in model['files']})

    def test_pragma_decorated_function_interfaces_have_private_scope(self):
        self.write('Logical/Libraries/User/User.fun', '''{REDUND_CONTEXT} FUNCTION_BLOCK Twice
          VAR_INPUT
            Value : REAL;
          END_VAR
          VAR_OUTPUT
            Result : REAL;
          END_VAR
        END_FUNCTION_BLOCK
        {REDUND_CONTEXT} FUNCTION_BLOCK Triple
          VAR_INPUT
            Value : REAL;
          END_VAR
        END_FUNCTION_BLOCK''')
        self.write('Logical/Libraries/User/Twice.st', 'FUNCTION_BLOCK Twice\nResult := Value * 2;\nEND_FUNCTION_BLOCK')
        model = analyze_project(self.root)
        values = [v for v in model['variables'] if v['name'] == 'Value']
        self.assertEqual([], values)  # Interface formals are not shared PLC memory.
        program = next(p for p in model['programs'] if p['name'] == 'Twice')
        self.assertEqual('functionblock', program['kind'])
        self.assertEqual('logical/libraries/user/twice', program['scope'])
        self.assertEqual('Twice', program['interface']['name'])
        self.assertTrue(program['interface']['implemented'])
        self.assertIn('Value : REAL;', program['interface']['declaration'])
        self.assertFalse(any(d['code'] == 'variable-conflict' for d in model['diagnostics']))

    def test_ladder_uses_existing_geometry_and_preserves_branches(self):
        self.write('Logical/Ladder/Logic.ld', '''<networks><network label="Motor"><row>
          <contact name="Start" type="open"/><coil name="Motor" type="open"/>
        </row><row><contact name="Hold" type="open" or="true"/><line/></row></network></networks>''')
        model = analyze_project(self.root)
        program = next(p for p in model['programs'] if p['language'] == 'ld')
        self.assertEqual('Start', program['networks'][0]['cells'][0]['name'])
        self.assertEqual(2, program['networks'][0]['rows'])
        self.assertTrue(any(connection['kind'] == 'branch' for connection in program['networks'][0]['connections']))

    def test_conflicting_variables_are_explicitly_ambiguous(self):
        self.write('Logical/Global.var', 'VAR_GLOBAL\nStart : BOOL;\nSTART : INT;\nEND_VAR')
        model = analyze_project(self.root)
        variables = [v for v in model['variables'] if v['name'].casefold() == 'start']
        self.assertEqual(2, len(variables))
        self.assertFalse(any(v.get('ambiguous') for v in variables))
        self.assertFalse(any(d['code'] == 'variable-conflict' for d in model['diagnostics']))
        self.write('Logical/Duplicate.var', 'VAR_GLOBAL\nStart : INT;\nEND_VAR')
        model = analyze_project(self.root)
        variables = [v for v in model['variables'] if v['name'] == 'Start']
        self.assertEqual(1, len(variables))
        self.assertTrue(variables[0]['ambiguous'])
        self.assertEqual({'INT', 'BOOL'}, {variables[0]['type'], variables[0]['conflictingDeclarations'][0]['type']})
        self.assertTrue(any(d['code'] == 'variable-conflict' for d in model['diagnostics']))

    def test_cpu_task_times_are_kept_separate(self):
        self.write('Physical/Config1/Hardware.hw', '''<Hardware>
           <Module Name="PLC1" Type="X20CP1586"><Parameter ID="Cyclic1Duration" Value="10000"/></Module>
           <Module Name="PLC2" Type="X20CP1586"><Parameter ID="Cyclic1Duration" Value="20000"/></Module>
        </Hardware>''')
        self.write('Physical/Config1/PLC2/CPU.sw', '<SwConfiguration><TaskClass Name="Cyclic#1"><Task Name="Main" Source="Main.prg"/></TaskClass></SwConfiguration>')
        model = analyze_project(self.root)
        self.assertEqual({'PLC1': 10, 'PLC2': 20}, {task['controller']: task['intervalMs'] for task in model['tasks']})

    def test_compound_c_lifecycle_keeps_translation_unit_and_header_separate(self):
        self.write('Logical/Main/IEC.prg', '<Program><Files><File>Main.c</File><File>Main.h</File></Files></Program>')
        self.write('Logical/Main/Main.c', 'void _INIT MainInit(void) { Counter = 0; }\nvoid _CYCLIC MainCyclic(void) { Counter = Counter + 1; }\nvoid _EXIT MainExit(void) { Counter = 0; }')
        self.write('Logical/Main/Main.h', 'extern int Counter;')
        model = analyze_project(self.root)
        self.assertEqual(['Logical/Main/Main.c'], model['tasks'][0]['programs'])
        program = next(p for p in model['programs'] if p['source'].endswith('Main.c'))
        self.assertEqual('cyclic', program['entry'])
        self.assertIn('_INIT', program['code'])
        self.assertIn('_EXIT', program['code'])
        self.assertFalse(any(p['source'].endswith('.h') for p in model['programs']))


if __name__ == '__main__':
    unittest.main()
