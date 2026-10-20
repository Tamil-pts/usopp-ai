"""Reusable B&R grammar regressions, including documented Basic forms."""
import unittest

from virtual_plc.core.compiler import compile_source, walk_ir
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.tests.test_runtime import project, variable


class BasicLanguageTests(unittest.TestCase):
    def test_case_actions_share_consecutive_labels_and_keep_source_lines(self):
        code = '''CASE Choice OF
ACTION 1:
ACTION 5:
    Result = 10 ; an inline Basic comment
ENDACTION
ACTION 6..9:
    Result = 30
ENDACTION
ELSEACTION:
    Result = 40
ENDACTION
ENDCASE'''
        compiled = compile_source(code, 'ab', 'Case.ab')
        self.assertEqual([], compiled['diagnostics'])
        case = compiled['sections'][0]['instructions'][0]
        self.assertEqual(2, len(case['cases']))
        self.assertEqual(2, len(case['cases'][0]['labels']))
        self.assertEqual(4, case['cases'][0]['body'][0]['line'])
        runtime = VirtualRuntime(project(code, [variable('Choice'), variable('Result')], 'ab'))
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        for choice, result in [(1, 10), (5, 10), (8, 30), (2, 40)]:
            runtime.set_value('Choice', choice, return_snapshot=False)
            runtime.command('scan')
            self.assertEqual(result, runtime.get_value('Result'))

    def test_loop_exitif_forms_and_downto(self):
        code = '''i = 0
LOOP
  EXITIF i >= 3
  i = i + 1
ENDLOOP
LOOP j = 3 DOWNTO 1 DO
  Total = Total + j
  EXITIF (Total > 100)
ENDLOOP'''
        compiled = compile_source(code, 'ab')
        self.assertEqual([], compiled['diagnostics'])
        instructions = compiled['sections'][0]['instructions']
        self.assertEqual('while', instructions[1]['op'])
        self.assertEqual({'op': 'unary', 'operator': '-', 'value': {'op': 'literal', 'value': 1}},
                         instructions[2]['step'])
        runtime = VirtualRuntime(project(code, [variable('i'), variable('j'), variable('Total')], 'ab'))
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command('scan')
        self.assertEqual(3, runtime.get_value('i'))
        self.assertEqual(6, runtime.get_value('Total'))

    def test_unbalanced_loops_block(self):
        for code in ['ENDLOOP', 'LOOP\nx = 1']:
            self.assertFalse(compile_source(code, 'ab')['compatibility']['runAllowed'])

    def test_goto_labels_are_explicit_and_validated(self):
        valid = compile_source('IF Stop THEN\nGOTO finished\nENDIF\nx = 3\nfinished:', 'ab')
        self.assertEqual([], valid['diagnostics'])
        self.assertTrue(any(n['op'] == 'goto' for n in walk_ir(valid['sections'])))
        for code in ['GOTO nowhere', 'again:\nx = 2\nAGAIN:']:
            result = compile_source(code, 'ab')
            self.assertFalse(result['compatibility']['runAllowed'])
            self.assertIn('GOTO label', result['diagnostics'][0]['message'])

    def test_generated_scalar_reference_and_simplified_block_invocation(self):
        compiled = compile_source('Counter;\nTimer;\nTimer();', 'st')
        self.assertEqual([], compiled['diagnostics'])
        instructions = compiled['sections'][0]['instructions']
        self.assertEqual(['reference_statement', 'reference_statement', 'call'], [n['op'] for n in instructions])

    def test_action_sections_and_variable_names_beginning_var(self):
        action = compile_source('ACTION SetStatus:\nStatus := TRUE;\nEND_ACTION')
        self.assertEqual([], action['diagnostics'])
        self.assertEqual('action', action['sections'][0]['kind'])
        basic = compile_source('FUNCTION Example\nVAR_1 = VAR_2\nExample = TRUE\nEND_FUNCTION', 'ab')
        self.assertEqual([], basic['diagnostics'])
        self.assertEqual(2, len(basic['sections'][0]['instructions']))


class CGrammarTests(unittest.TestCase):
    def test_bounded_object_macros_includes_and_conditionals(self):
        code = '''#include <bur/plctypes.h> // interface only
#ifdef _DEFAULT_INCLUDES
#include <AsDefault.h>
#endif
#define COUNT 3
#ifdef COUNT
void _CYCLIC Main(void) { Result = COUNT; }
#else
this is excluded source
#endif'''
        compiled = compile_source(code, 'c', 'Main.c')
        self.assertEqual([], compiled['diagnostics'])
        instruction = compiled['sections'][0]['instructions'][0]
        self.assertEqual(7, instruction['line'])
        self.assertEqual(3, instruction['value']['value'])
        for code in ['#define F(x) (x)\nvoid Main(void){}', '#ifdef TEST\nvoid Main(void){}',
                     '#else\nvoid Main(void){}', '#if HOST_OPTION\nvoid Main(void){}\n#endif']:
            self.assertFalse(compile_source(code, 'c')['compatibility']['runAllowed'])

    def test_virtual_address_cast_sizeof_and_struct_reference_ir(self):
        code = '''typedef struct { UINT year; USINT month; } stamp_typ;
_GLOBAL stamp_typ *Records;
_LOCAL UDINT Length;
void _CYCLIC Main(void) {
  Length = sizeof(stamp_typ);
  Buffer = (UDINT)&Records;
  Pointer = (void**)Records;
  Year = Records[Index].year;
  Month = Records->month;
}'''
        compiled = compile_source(code, 'c')
        self.assertEqual([], compiled['diagnostics'])
        body = compiled['sections'][0]['instructions']
        self.assertEqual({'op': 'sizeof_type', 'type': 'stamp_typ', 'pointers': 0}, body[0]['value'])
        self.assertEqual('ADR', body[1]['value']['value']['name'])
        self.assertEqual(2, body[2]['value']['pointers'])
        self.assertIn('index', body[3]['value']['path'][0])
        self.assertEqual({'dereference': True}, body[4]['value']['path'][0])

    def test_switch_break_and_conditional_are_not_dropped(self):
        code = '''void _CYCLIC Main(void) {
switch (Choice) {
case 1: case 3:
 Result = 10;
 break;
case 2:
 Result = 20;
default:
 Result += Choice ? 1 : 2;
}
}'''
        compiled = compile_source(code, 'c')
        self.assertEqual([], compiled['diagnostics'])
        switch = compiled['sections'][0]['instructions'][0]
        self.assertEqual('switch', switch['op'])
        self.assertEqual(2, len(switch['cases'][0]['labels']))
        self.assertEqual('exit', switch['cases'][0]['body'][-1]['op'])
        self.assertEqual('conditional', switch['default'][0]['value']['right']['op'])

    def test_c_unsigned_literals_keep_numeric_identity(self):
        compiled = compile_source('void _CYCLIC Main(void){ Mask = 0xFFUL; Value = 4294967295U; }', 'c')
        self.assertEqual([], compiled['diagnostics'])
        body = compiled['sections'][0]['instructions']
        self.assertEqual([255, 4294967295], [n['value']['value'] for n in body])

    def test_c_precedence_keeps_comparison_above_bitwise_and(self):
        compiled = compile_source('void Main(void){ Result = Mask & 3 == 2; }', 'c')
        self.assertEqual([], compiled['diagnostics'])
        value = compiled['sections'][0]['instructions'][0]['value']
        self.assertEqual('&', value['operator'])
        self.assertEqual('==', value['right']['operator'])

    def test_duplicate_or_nonfinal_default_blocks_instead_of_reordering(self):
        for code in ['switch(A){default: break; case 1: break;}',
                     'switch(A){default: break; default: break;}']:
            result = compile_source('void Main(void){' + code + '}', 'c')
            self.assertFalse(result['compatibility']['runAllowed'])


class RuntimeFaultLocationTests(unittest.TestCase):
    @staticmethod
    def with_action(body, main='Power;'):
        model = project(main, [variable('Result'), variable('Divisor')])
        model['programs'][0]['source'] = 'Logical/Server/Server.st'
        model['programs'].append({'id': 'power', 'name': 'Power', 'scope': 'Main',
                                  'source': 'Logical/Server/Power.st', 'language': 'st',
                                  'code': body})
        return model

    def assert_fault(self, runtime, source, line):
        self.assertEqual('faulted', runtime.status)
        diagnostic = next(d for d in reversed(runtime.diagnostics) if d['code'] == 'RUNTIME_FAULT')
        self.assertEqual(source, diagnostic['source'])
        self.assertEqual(line, diagnostic['line'])
        event = next(e for e in reversed(runtime.trace) if e['kind'] == 'error')
        self.assertEqual(source, event['source'])
        self.assertEqual(line, event['line'])

    def test_action_division_fault_points_inside_action_not_calling_statement(self):
        model = self.with_action('ACTION Power:\nIF Divisor = 0 THEN\nResult := 10 / Divisor;\nEND_IF\nEND_ACTION')
        runtime = VirtualRuntime(model)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command('scan')
        self.assert_fault(runtime, 'Logical/Server/Power.st', 3)

    def test_nested_actions_keep_deepest_failure_location(self):
        model = self.with_action('ACTION Power:\nCompute;\nEND_ACTION')
        model['programs'].append({'id': 'compute', 'name': 'Compute', 'scope': 'Main',
                                  'source': 'Logical/Server/Compute.st', 'language': 'st',
                                  'code': 'ACTION Compute:\nResult := 1;\nResult := 10 / Divisor;\nEND_ACTION'})
        runtime = VirtualRuntime(model)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command('scan')
        self.assert_fault(runtime, 'Logical/Server/Compute.st', 3)

    def test_source_function_failure_and_success_keep_return_semantics(self):
        model = project('Result := Divide(Divisor); Result := Result + 1;',
                        [variable('Result'), variable('Divisor')])
        model['programs'].append({'id': 'divide', 'name': 'Divide', 'scope': 'Functions',
                                  'source': 'Logical/Functions/Divide.st', 'language': 'st',
                                  'code': ('FUNCTION Divide : DINT\nVAR_INPUT\nInput : DINT;\nEND_VAR\n'
                                           'Divide := 10 / Input;\nRETURN;\nEND_FUNCTION')})
        runtime = VirtualRuntime(model)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command('scan')
        self.assert_fault(runtime, 'Logical/Functions/Divide.st', 5)
        runtime.command('reset')
        runtime.set_value('Divisor', 2, return_snapshot=False)
        runtime.command('scan')
        self.assertEqual('paused', runtime.status)
        self.assertEqual(6, runtime.get_value('Result'))

    def test_successful_actions_and_basic_goto_still_resume_correctly(self):
        runtime = VirtualRuntime(self.with_action('ACTION Power:\nResult := Result + 4;\nEND_ACTION',
                                                  'Power; Result := Result + 1;'))
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command('scan')
        self.assertEqual('paused', runtime.status)
        self.assertEqual(5, runtime.get_value('Result'))
        basic = VirtualRuntime(project('i = 0\nagain:\ni = i + 1\nIF i < 3 THEN\nGOTO again\nENDIF',
                                       [variable('i')], 'ab'))
        self.assertTrue(basic.run_allowed, basic.diagnostics)
        basic.command('scan')
        self.assertEqual('paused', basic.status)
        self.assertEqual(3, basic.get_value('i'))


if __name__ == '__main__':
    unittest.main()
