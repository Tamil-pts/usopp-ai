"""Project summaries must describe the selected source, never a machine template."""
from pathlib import Path
import tempfile
import unittest

from python_engine.machine_summary import _operation_sentence, prepare_summary, retained_summary, summary_answer
from python_engine.project_analysis import block_family, collect_file
from python_engine.project_knowledge import build_index
from python_engine.source_operations import collect_operations


class MachineSummaryTests(unittest.TestCase):
    def project(self, folder):
        root = Path(folder)
        files = {
            'Machine.apj': '<?AutomationStudio Version="4.12.2.93" WorkingVersion="4.12"?><Project/>',
            'LastUser.set': '<ProjectSettings><ConfigurationManager ActiveConfigurationName="Heating"/></ProjectSettings>',
            'Physical/Heating/PLC1/Cpu.sw': '<SwConfiguration><Task Name="Heat" Source="HeatControl.prg"/>'
                '<Task Name="OldDraft" Source="Draft.prg" Disabled="true"/></SwConfiguration>',
            'Physical/Heating/PLC1/IoMap.iom': 'VAR_CONFIG\nCyclic#1.HEATER_OUTPUT AT %QX.Heater.Output;\nEND_VAR',
            'Logical/HeatControl/Main.st': 'PROGRAM _INIT\nINIT_ONLY := 99;\nEND_PROGRAM\n'
                'PROGRAM _CYCLIC\nIF PRESSURE_HIGH THEN\nHEATER_OUTPUT := FALSE;\n'
                'ELSIF START_HEATING THEN\nHEATER_OUTPUT := TRUE;\nEND_IF;\n'
                'Watts := Voltage * Current;\nEND_PROGRAM',
            'Logical/Draft/Main.st': 'PROGRAM _CYCLIC\nTargSliverWght := Feed_Sl_Wt * No_of_Doubling;\nEND_PROGRAM',
            'Logical/motor/Main.st': '(* motor name alone is not a motor implementation *)',
            'Temp/Coiler/Main.st': 'DOFF := TRUE;',
        }
        for name, text in files.items():
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text, encoding='utf-8')
        return root

    def test_unrelated_project_uses_actual_operations_and_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            index = build_index(self.project(folder))
            summary, evidence = prepare_summary(index)
            answer = summary_answer(summary, evidence)
        self.assertEqual(summary['configuredTasks'], 2)
        self.assertEqual(summary['enabledTasks'], 1)
        self.assertEqual(len(summary['functions']), 1)
        self.assertEqual(summary['functions'][0]['routine'], 'HeatControl')
        self.assertIn('HEATER_OUTPUT', answer)
        self.assertIn('PRESSURE_HIGH', answer)
        self.assertNotIn('INIT_ONLY', answer)
        for unsupported in ('drawframe', 'Autolevelling', 'Draft and sliver', 'can change', 'TargSliverWght', 'DOFF', 'Motor control'):
            self.assertNotIn(unsupported, answer)
        self.assertTrue(summary['functions'][0]['references'])

    def test_else_and_parallel_boolean_guards_stay_scoped(self):
        source = 'IF A OR B THEN\nX := TRUE;\nELSE\nIF C THEN\nX := FALSE;\nEND_IF;\nEND_IF;'
        operations = collect_operations('Logical/Heat/Main.st', source, 'Logic', 'active task')
        self.assertEqual(operations[0]['guards'], ['A OR B'])
        self.assertEqual(operations[1]['guards'], ['NOT (A OR B)', 'C'])
        nested = collect_operations('Logical/Heat/Main.st', 'IF A OR B THEN\nIF C THEN\nX := TRUE;\nEND_IF;\nEND_IF;', 'Logic', 'active task')
        self.assertIn('(A is TRUE or B is TRUE) and C is TRUE', _operation_sentence(nested[0], True))

    def test_init_is_labelled_and_comments_do_not_add_operations(self):
        source = 'PROGRAM _INIT\nX := 42;\n(* IF START THEN\nFAKE := TRUE;\nEND_IF; *)\nEND_PROGRAM'
        operations = collect_operations('Logical/Heat/Main.st', source, 'Logic', 'active task')
        self.assertEqual([item['name'] for item in operations], ['X'])
        self.assertEqual(operations[0]['section'], '_INIT')

    def test_missing_guard_evidence_drops_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            summary, evidence = prepare_summary(build_index(self.project(folder)))
        selected = summary['functions'][0]
        filtered = [item for item in evidence if not any(item['file'] == ref['file'] for ref in selected['references'])]
        self.assertEqual(retained_summary(summary, filtered)['functions'], [])

    def test_bare_blocks_resolve_type_and_variables_do_not_become_protocols(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.project(folder)
            routine = root / 'Logical/HeatControl'
            (routine / 'Main.st').write_text('TcpOpen_0.port := 22222;\nTcpOpen_0;\nCAN_DOFF;\n', encoding='utf-8')
            (routine / 'Main.var').write_text('TcpOpen_0 : TcpOpen;\nCAN_DOFF : UINT;', encoding='utf-8')
            summary, _ = prepare_summary(build_index(root))
        tcp = [item for item in summary['communications'] if item['title'] == 'TCP / Ethernet']
        self.assertEqual(len(tcp), 1)
        self.assertIn('22222', tcp[0]['settings'])
        self.assertFalse(any('CAN API' in item['title'] for item in summary['communications']))
        self.assertIsNone(block_family('CAN_DOFF'))

    def test_c_is_not_decoded_with_iec_guards(self):
        operations = collect_operations('Logical/Heat/Main.c', 'if (A) { HEAT = 1; }', 'Logic', 'active task')
        self.assertEqual(operations, [])
        self.assertTrue(any(item['kind'] == 'call' for item in collect_file('Logical/Heat/Main.c', 'poll_sensor(&sensor);', 'Logic', 'active task')))

    def test_ports_remain_bound_to_the_called_protocol(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.project(folder)
            routine = root / 'Logical/HeatControl'
            (routine / 'Main.st').write_text('TcpOpen_0.port := 21010;\nTcpOpen_0;\nUdpOpen_0.port := 5000;\nUdpOpen_0;', encoding='utf-8')
            (routine / 'Main.var').write_text('TcpOpen_0 : TcpOpen;\nUdpOpen_0 : UdpOpen;', encoding='utf-8')
            summary, _ = prepare_summary(build_index(root))
        settings = {item['title']: item['settings'] for item in summary['communications']}
        self.assertEqual(settings['TCP / Ethernet'], 'port 21010')
        self.assertEqual(settings['UDP / Ethernet'], 'port 5000')


if __name__ == '__main__':
    unittest.main()
