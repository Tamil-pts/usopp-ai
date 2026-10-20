"""Executable contracts for reusable B&R Ladder dataflow and jump support."""
import unittest
from virtual_plc.core.compiler import compile_ladder
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.tests.test_runtime import project, variable, values


def xml(*networks):
    return "<networks>" + "".join(networks) + "</networks>"


def runtime(code, variables):
    result = VirtualRuntime(project(code, variables, language="ld"))
    if not result.run_allowed:
        raise AssertionError(result.diagnostics)
    return result


class LadderDataflowTests(unittest.TestCase):
    def test_extensible_comparison_and_series_contact(self):
        code = xml('<network><row><analog type="input" name="Count"/><function position="top" type="GE"><input name="IN1" extensible="true"/><output name="1"/></function><contact type="open" name="Enabled"/><coil type="open" name="Reached"/></row><row><analog type="input" name="10"/><function position="bottom" type="GE"><input name="" extensible="true"/></function></row></network>')
        instance = runtime(code, [variable("Count", initial=12), variable("Enabled", "BOOL", True), variable("Reached", "BOOL", False)])
        instance.command("scan")
        self.assertTrue(values(instance)["Reached"])
        instance.set_value("Count", 9); instance.command("scan")
        self.assertFalse(values(instance)["Reached"])

    def test_multiple_functions_and_numeric_output(self):
        code = xml('<network><row><analog type="input" name="A"/><function position="top" type="ADD"><input name="IN1"/><output name="1"/></function><function position="topbottom" type="DINT_TO_REAL"><input name="IN"/><output name="1"/></function><analog type="output" name="Result"/></row><row><analog type="input" name="2"/><function position="bottom" type="ADD"><input name="IN2"/></function></row></network>')
        instance = runtime(code, [variable("A", initial=3), variable("Result", "REAL", 0.0)])
        instance.command("scan")
        self.assertEqual(5.0, values(instance)["Result"])

    def test_two_blocks_at_different_columns_execute_once(self):
        code = xml('<network><row><empty/><functionblock position="header" name="First" type="TON"/><empty/><functionblock position="header" name="Second" type="R_TRIG"/></row><row><contact type="open" name="Start"/><functionblock position="top" type="TON"><input name="IN"/><output name="Q"/></functionblock><line/><functionblock position="topbottom" type="R_TRIG"><input name="CLK"/><output name="Q"/></functionblock><coil type="open" name="Pulse"/></row><row><analog type="input" name="T#0s"/><functionblock position="bottom" type="TON"><input name="PT"/><output name="ET"/></functionblock></row></network>')
        instance = runtime(code, [variable("Start", "BOOL", True), variable("Pulse", "BOOL", False), variable("First", "TON", None), variable("Second", "R_TRIG", None)])
        instance.command("scan"); self.assertTrue(values(instance)["Pulse"])
        instance.command("scan"); self.assertFalse(values(instance)["Pulse"])
        events = [item for item in instance.trace if item["kind"] == "function-block"]
        self.assertEqual(4, len(events))

    def test_unwired_fb_input_retains_declared_member(self):
        code = xml('<network><row><empty/><functionblock position="header" name="Timer" type="TON"/></row><row><contact type="open" name="Start"/><functionblock position="top" type="TON"><input name="IN"/><output name="Q"/></functionblock><coil type="open" name="Done"/></row><row><empty/><functionblock position="bottom" type="TON"><input name="PT"/><output name="ET"/></functionblock></row></network>')
        instance = runtime(code, [variable("Start", "BOOL", True), variable("Done", "BOOL", False), variable("Timer", "TON", None)])
        instance.set_value("Timer.PT", 20)
        for _ in range(2): instance.command("scan")
        self.assertFalse(values(instance)["Done"])
        instance.command("scan"); self.assertTrue(values(instance)["Done"])

    def test_branch_feeds_block_without_series_neighbor(self):
        code = xml('<network><row><contact type="open" name="Start"/><line/><coil type="reset" name="ResetMe"/></row><row><empty or="true"/><functionblock position="header" name="Edge" type="R_TRIG"/></row><row><empty or="true"/><functionblock position="topbottom" type="R_TRIG"><input name="CLK"/><output name="Q"/></functionblock><coil type="open" name="Pulse"/></row></network>')
        instance = runtime(code, [variable("Start", "BOOL", True), variable("ResetMe", "BOOL", True), variable("Pulse", "BOOL", False), variable("Edge", "R_TRIG", None)])
        instance.command("scan")
        self.assertTrue(values(instance)["Pulse"])
        self.assertFalse(values(instance)["ResetMe"])

    def test_empty_network_is_noop(self):
        instance = runtime(xml('<network><row><empty/><empty/></row></network>'), [variable("A", initial=7)])
        instance.command("scan"); self.assertEqual(7, values(instance)["A"])

    def test_forward_jump_skips_network_and_backward_jump_is_bounded(self):
        code = xml('<network><row><line/><coil type="jump" name="Finish"/></row></network>',
                   '<network><row><contact name="TRUE"/><coil type="set" name="Skipped"/></row></network>',
                   '<network label="Finish"><row><contact name="TRUE"/><coil type="set" name="Done"/></row></network>')
        instance = runtime(code, [variable("Skipped", "BOOL", False), variable("Done", "BOOL", False)])
        instance.command("scan")
        self.assertFalse(values(instance)["Skipped"]); self.assertTrue(values(instance)["Done"])
        instance = runtime(xml('<network label="Forever"><row><line/><coil type="jump" name="Forever"/></row></network>'), [])
        instance.command("scan")
        self.assertEqual("faulted", instance.status)
        self.assertIn("budget", instance.diagnostics[-1]["message"])

    def test_return_coil_stops_remaining_networks(self):
        instance = runtime(xml('<network><row><contact name="TRUE"/><coil type="return"/></row></network>',
                               '<network><row><contact name="TRUE"/><coil type="set" name="Skipped"/></row></network>'),
                           [variable("Skipped", "BOOL", False)])
        instance.command("scan"); self.assertFalse(values(instance)["Skipped"])

    def test_unknown_element_missing_pin_and_missing_label_block(self):
        invalid = [xml('<network><row><mystery/><coil name="A"/></row></network>'),
                   xml('<network><row><empty/><function position="topbottom" type="ABS"><input name="IN"/><output name="1"/></function><analog type="output" name="A"/></row></network>'),
                   xml('<network><row><line/><coil type="jump" name="Absent"/></row></network>')]
        for code in invalid:
            self.assertFalse(compile_ladder(code)["compatibility"]["runAllowed"])

    def test_unknown_library_block_remains_blocked(self):
        code = xml('<network><row><empty/><functionblock position="header" name="Motion" type="VendorMotion"/></row><row><contact name="TRUE"/><functionblock position="topbottom" type="VendorMotion"><input name="Enable"/><output name="Done"/></functionblock></row></network>')
        instance = VirtualRuntime(project(code, [variable("Motion", "VendorMotion", None)], language="ld"))
        self.assertFalse(instance.run_allowed)
        self.assertTrue(any(item["code"] == "UNSUPPORTED_CALL" for item in instance.diagnostics))

    def test_declared_function_block_inout_and_case_preserved(self):
        code = xml('<network><row><empty/><functionblock position="header" name="Adder" type="Accumulate"/></row>'
                   '<row><analog type="input" name="Total"/><functionblock position="top" type="Accumulate"><input name="Value" varinout="true"/><output name="Value" varinout="true"/></functionblock><analog type="output" name="Total"/></row>'
                   '<row><analog type="input" name="3"/><functionblock position="bottom" type="Accumulate"><input name="Step"/></functionblock></row></network>')
        model = project(code, [variable("Total", initial=4), variable("Adder", "Accumulate", None)], language="ld", symbolCaseSensitive=True)
        model["functions"] = [{"id": "accumulate", "name": "Accumulate", "scope": "Library", "language": "st", "source": "Accumulate.st",
                               "code": "FUNCTION_BLOCK Accumulate VAR_INPUT Step : DINT; END_VAR VAR_IN_OUT Value : DINT; END_VAR Value := Value + Step; END_FUNCTION_BLOCK"}]
        instance = VirtualRuntime(model)
        self.assertTrue(instance.run_allowed, instance.diagnostics)
        instance.command("scan"); self.assertEqual(7, values(instance)["Total"])
        instance.command("scan"); self.assertEqual(10, values(instance)["Total"])

    def test_unwired_unknown_output_pin_blocks_before_execution(self):
        code = xml('<network><row><empty/><functionblock position="header" name="Edge" type="R_TRIG"/></row>'
                   '<row><contact name="TRUE"/><functionblock position="topbottom" type="R_TRIG"><input name="CLK"/><output name="NotAPin"/></functionblock></row></network>')
        instance = VirtualRuntime(project(code, [variable("Edge", "R_TRIG", None)], language="ld"))
        self.assertFalse(instance.run_allowed)
        self.assertTrue(any(item["code"] == "LADDER_BLOCK_INTERFACE" for item in instance.diagnostics))

    def test_ladder_integer_assignment_matches_st_and_external_input_stays_strict(self):
        # A zero speed minus five is a valid PLC arithmetic result. Storage in
        # UINT keeps its low 16 bits, exactly as the source assignment does.
        code = xml('<network><row><analog type="input" name="Reference"/>'
                   '<function position="top" type="SUB"><input name="IN1"/><output name="40"/></function>'
                   '<analog type="output" name="Unsigned"/></row>'
                   '<row><analog type="input" name="5"/>'
                   '<function position="bottom" type="SUB"><input name="IN2"/></function><empty/></row></network>',
                   '<network><row><analog type="input" name="200"/>'
                   '<function position="topbottom" type="MOVE"><input name="IN"/><output name="40"/></function>'
                   '<analog type="output" name="Signed"/></row></network>')
        declarations = [variable("Reference", "UINT", 0), variable("Unsigned", "UINT", 0), variable("Signed", "SINT", 0)]
        ladder = runtime(code, declarations)
        structured_text = VirtualRuntime(project('Unsigned := Reference - 5; Signed := 200;', declarations))
        self.assertTrue(structured_text.run_allowed, structured_text.diagnostics)
        for instance in (ladder, structured_text):
            instance.command("scan")
            self.assertEqual("paused", instance.status)
            self.assertEqual(65531, values(instance)["Unsigned"])
            self.assertEqual(-56, values(instance)["Signed"])
            with self.assertRaisesRegex(ValueError, "out of range"):
                instance.set_value("Unsigned", -5)
            with self.assertRaisesRegex(ValueError, "out of range"):
                instance.set_value("Signed", 200)
            self.assertEqual(65531, values(instance)["Unsigned"])
            self.assertEqual(-56, values(instance)["Signed"])
