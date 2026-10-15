import unittest

from python_engine.function_flow import build_function_flow, flow_html


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get('children', []))
        for branch in node.get('branches', []):
            yield from walk(branch['nodes'])


def statements(nodes):
    return [row for node in walk(nodes) for row in node.get('statements', [])]


class FunctionFlowTests(unittest.TestCase):
    def test_nested_st_branches_preserve_scope_and_source_lines(self):
        text="""PROGRAM _CYCLIC
IF enable THEN
    IF fault THEN output := FALSE; ELSE output := TRUE; END_IF;
ELSIF retry THEN output := FALSE;
ELSE output := fallback;
END_IF;
after := output;
END_PROGRAM
"""
        flow=build_function_flow(text,'Logical/task/task.st')
        nodes=flow['sections'][0]['nodes']
        self.assertEqual(flow['notices'],[])
        outer=nodes[0]
        self.assertEqual(outer['line'],2)
        self.assertEqual(outer['endLine'],6)
        self.assertEqual([branch['label'] for branch in outer['branches']],['TRUE','ELSE IF','ELSE'])
        self.assertEqual(outer['branches'][0]['nodes'][0]['condition'],'fault')
        self.assertEqual([s['code'] for s in statements(outer['branches'][2]['nodes'])],['output := fallback'])
        self.assertEqual(nodes[1]['statements'][0]['line'],7)

    def test_st_else_followed_by_if_is_nested_not_elsif(self):
        flow=build_function_flow('IF a THEN x := 1; ELSE IF b THEN x := 2; END_IF; END_IF;','main.st')
        outer=flow['sections'][0]['nodes'][0]
        self.assertEqual(outer['branches'][1]['label'],'ELSE')
        self.assertEqual(outer['branches'][1]['nodes'][0]['condition'],'b')
        self.assertEqual(flow['notices'],[])

    def test_iec_escaped_quotes_keep_comment_markers_inside_string(self):
        flow=build_function_flow("message := 'quote $' // IF fake THEN';\nvalue := 2;",'main.st')
        rows=statements(flow['sections'][0]['nodes'])
        self.assertEqual(len(rows),2)
        self.assertIn("$' // IF fake THEN",rows[0]['code'])
        self.assertEqual(flow['notices'],[])

    def test_comments_and_quoted_control_words_do_not_create_actions(self):
        flow=build_function_flow("""(* IF fake THEN output := bad; END_IF; *)
url := 'http://server/IF; THEN  two   spaces'; // fake_call()
IF ready THEN output := source; END_IF;
""",'main.st')
        rows=statements(flow['sections'][0]['nodes'])
        self.assertEqual(len(rows),2)
        self.assertIn('two   spaces',rows[0]['code'])
        self.assertEqual(rows[0]['line'],2)
        self.assertNotIn('fake_call',[call['name'] for call in flow['calls']])
        self.assertNotIn('bad',[row['name'] for row in flow['variables']])

    def test_automation_basic_loops_fub_and_else_if(self):
        text="""PROGRAM _CYCLIC
IF start = 1 THEN
  LOOP index = 0 TO 3 DO
    Data[index] = Source[index]
    EXITIF (index = stopIndex)
  ENDLOOP
  timer.PT = T#3S
  timer FUB TON()
ELSE IF retry = 1 THEN
  start = 0
ELSE
  start = 1
ENDIF
; disabled = 1
END_PROGRAM
"""
        flow=build_function_flow(text,'ip_addCyclic.ab')
        node=flow['sections'][0]['nodes'][0]
        self.assertEqual(flow['notices'],[])
        self.assertEqual([branch['label'] for branch in node['branches']],['TRUE','ELSE IF','ELSE'])
        self.assertTrue(any(n['kind']=='exit' for n in walk([node])))
        self.assertTrue(any(call['name']=='TON' and call['instance']=='timer' for call in flow['calls']))
        by_name={v['name']:v for v in flow['variables']}
        self.assertEqual(by_name['index']['writes'],[3])
        self.assertNotIn('disabled',by_name)

    def test_case_arms_and_repeat_until_keep_conditions(self):
        flow=build_function_flow('CASE mode OF\n1,2: out := a;\n3: out := b;\nELSE out := c;\nEND_CASE;\nREPEAT count := count + 1; UNTIL count >= limit END_REPEAT;', 'main.st')
        nodes=flow['sections'][0]['nodes']
        self.assertEqual([b['label'] for b in nodes[0]['branches']],['1,2','3','ELSE'])
        self.assertEqual(nodes[1]['until'],'UNTIL count >= limit')
        self.assertEqual(flow['notices'],[])

    def test_variable_case_is_combined_and_library_names_are_not_variables(self):
        flow=build_function_flow('Output := atoi(ADR(Data));\nIF output > 0 THEN Retry := output; END_IF;', 'main.st')
        variables={v['name'].casefold():v for v in flow['variables']}
        self.assertEqual(variables['output']['writes'],[1])
        self.assertEqual(variables['output']['reads'],[2])
        self.assertNotIn('atoi',variables)
        self.assertNotIn('adr',variables)

    def test_ladder_keeps_parallel_wiring_and_excludes_commented_outputs(self):
        text='''PROGRAM _CYCLIC
<networks>
<network commented="0"><row><contact name="start" type="open"/><coil name="motor" type="set"/></row><row><contact name="reset" type="closed" or="true"/><empty/></row></network>
<network commented="1"><row><contact name="TRUE" type="open"/><coil name="disabled_output" type="reset"/></row></network>
</networks>END_PROGRAM'''
        flow=build_function_flow(text,'motorCyclic.ld')
        nodes=flow['sections'][0]['nodes']
        self.assertTrue(nodes[0]['parallel'])
        self.assertEqual(nodes[0]['line'],3)
        self.assertIn('Latch TRUE: motor',nodes[0]['actions'])
        self.assertTrue(nodes[1]['disabled'])
        self.assertNotIn('disabled_output',[v['name'] for v in flow['variables']])
        self.assertNotIn('TRUE',[v['name'] for v in flow['variables']])

    def test_legacy_ladder_instruction_source_does_not_invent_rung_topology(self):
        flow=build_function_flow('LD start\nANDN stop\nST motor\n\nLD motor\nCAL timer\n','motor.src')
        self.assertIn('Instruction List',flow['language'])
        self.assertEqual(len(flow['sections'][0]['nodes']),2)
        self.assertEqual(next(v for v in flow['variables'] if v['name']=='motor')['writes'],[3])
        self.assertTrue(flow['notices'])

    def test_unmatched_control_is_reported_and_html_escapes_source(self):
        flow=build_function_flow("IF ready THEN text := '<script>alert(1)</script>';",'main.st')
        self.assertTrue(flow['notices'])
        report=flow_html(flow)
        self.assertNotIn('<script>',report)
        self.assertIn('&lt;script&gt;',report)
        with self.assertRaises(ValueError):build_function_flow('VAR','main.var')


if __name__=='__main__':
    unittest.main()
