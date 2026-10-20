"""Focused executable contracts for the independent Virtual PLC module."""
import unittest
from unittest.mock import patch

from virtual_plc.core.compiler import compile_ladder, compile_source
from virtual_plc.core.runtime import VirtualRuntime, RuntimeErrorPLC
from virtual_plc.core.memory import PLCMemory


def project(code, variables=None, language="st", **extra):
    result = {"programs": [{"id": "main", "name": "Main", "scope": "Main", "source": "Logical/Main/Main."+language,
                            "language": language, "code": code}],
              "variables": variables or [],
              "tasks": [{"id": "Cyclic1", "name": "Cyclic #1", "intervalMs": 10, "priority": 1, "programs": ["main"]}]}
    result.update(extra)
    return result


def variable(name, typename="DINT", initial=0, scope="Main", **extra):
    return {"id": scope+"::"+name, "name": name, "scope": scope, "type": typename, "initial": initial, **extra}


def values(runtime):
    return {item["name"]: item["value"] for item in runtime.snapshot()["variables"]}


class CompilerTests(unittest.TestCase):
    def test_st_ir_source_locations_and_literals(self):
        compiled = compile_source("PROGRAM _CYCLIC\nA := 16#FF;\nB := T#1s500ms;\nEND_PROGRAM", source="Main.st")
        self.assertEqual([], compiled["diagnostics"])
        self.assertEqual(2, compiled["sections"][0]["instructions"][0]["line"])
        self.assertEqual(1500, compiled["sections"][0]["instructions"][1]["value"]["value"])

    def test_unsupported_never_silently_skipped(self):
        compiled = compile_source("A := 1; GOTO somewhere;")
        self.assertFalse(compiled["compatibility"]["runAllowed"])
        self.assertEqual([], compiled["sections"])

    def test_restricted_c_rejects_unallocated_local_pointer_and_function_macro(self):
        for code in ["void _CYCLIC cyclic(void){ int *p; }", "#define A(x) (x + 2)\nvoid _CYCLIC x(void){}"]:
            self.assertFalse(compile_source(code, "c")["compatibility"]["runAllowed"])


class RuntimeTests(unittest.TestCase):
    def test_if_case_for_while_repeat_and_array_bounds(self):
        code = """PROGRAM _CYCLIC
        Sum := 0;
        FOR i := 1 TO 3 DO Sum := Sum + i; END_FOR;
        IF Sum = 6 THEN State := 2; ELSIF Sum = 4 THEN State := 1; ELSE State := 0; END_IF;
        CASE State OF 0: Sum := 99; 1,2: Sum := Sum + 1; 3..5: Sum := 44; ELSE Sum := -1; END_CASE;
        WHILE Sum < 9 DO Sum := Sum + 1; END_WHILE;
        REPEAT Sum := Sum - 1; UNTIL Sum = 8 END_REPEAT;
        Data[1] := Sum;
        END_PROGRAM"""
        runtime = VirtualRuntime(project(code, [variable("Sum"), variable("i"), variable("State"),
            variable("Data", "ARRAY [1..3] OF DINT", [0, 0, 0])]))
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command("scan")
        self.assertEqual(8, values(runtime)["Sum"])
        self.assertEqual([8, 0, 0], values(runtime)["Data"])

    def test_out_of_range_array_faults_with_source(self):
        runtime = VirtualRuntime(project("Data[Index] := 1;", [variable('Index', initial=0), variable("Data", "ARRAY [1..2] OF DINT", [0, 0])]))
        runtime.command("scan")
        self.assertEqual("faulted", runtime.status)
        self.assertIn("outside", runtime.diagnostics[-1]["message"])
        self.assertTrue(runtime.diagnostics[-1]["source"].endswith("Main.st"))

    def test_literal_out_of_range_array_blocks_before_run(self):
        runtime = VirtualRuntime(project("Data[0] := 1;", [variable("Data", "ARRAY [1..2] OF DINT", [0, 0])]))
        self.assertFalse(runtime.run_allowed)
        self.assertTrue(any('outside' in d['message'] and d.get('source','').endswith('Main.st') for d in runtime.diagnostics))

    def test_force_retention_reset_and_scope(self):
        runtime = VirtualRuntime(project("A := A + 1; Retained := Retained + 1;", [variable("A"), variable("Retained", retain=True)]))
        runtime.set_value("A", 10, force=True, scope="Main")
        runtime.command("scan")
        self.assertEqual(10, values(runtime)["A"])
        runtime.release_force("A", "Main")
        runtime.command("scan")
        self.assertEqual(11, values(runtime)["A"])
        runtime.command("reset")
        self.assertEqual(0, values(runtime)["A"])
        self.assertEqual(2, values(runtime)["Retained"])
        runtime.command("cold-reset")
        self.assertEqual(0, values(runtime)["Retained"])

    def test_deterministic_task_order_and_rates(self):
        data = project("A := A + 1;", [variable("A")])
        data["programs"].append({"id": "second", "name": "Second", "scope": "Main", "language": "st", "source": "Second.st", "code": "A := A * 2;"})
        data["tasks"].append({"id": "slow", "name": "slow", "priority": 2, "intervalMs": 20, "programs": ["second"]})
        runtime = VirtualRuntime(data)
        runtime.command("scan")
        runtime.command("scan")
        self.assertEqual(4, values(runtime)["A"])
        self.assertEqual([2, 1], [task["executionCount"] for task in runtime.tasks])
        self.assertEqual(20, runtime.time_ms)

    def test_initialization_runs_once(self):
        code = "PROGRAM _INIT A := 10; END_PROGRAM PROGRAM _CYCLIC A := A + 1; END_PROGRAM"
        runtime = VirtualRuntime(project(code, [variable("A")]))
        runtime.command("scan")
        runtime.command("scan")
        self.assertEqual(12, values(runtime)["A"])

    def test_unresolved_call_blocks_entire_active_program(self):
        runtime = VirtualRuntime(project("A := 1; ArTcpOpen();", [variable("A")]))
        self.assertFalse(runtime.run_allowed)
        with self.assertRaises(RuntimeErrorPLC): runtime.command("scan")
        self.assertEqual(0, values(runtime)["A"])

    def test_unknown_task_interval_blocks(self):
        data = project("A := 1;", [variable("A")])
        data["tasks"][0]["intervalMs"] = None
        runtime = VirtualRuntime(data)
        self.assertFalse(runtime.run_allowed)

    def test_unsupported_inactive_program_does_not_execute(self):
        data = project("A := A + 1;", [variable("A")])
        data["programs"].append({"id": "inactive", "name": "Inactive", "language": "st", "scope": "Inactive", "code": "GOTO X;"})
        runtime = VirtualRuntime(data)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command("scan")
        self.assertEqual(1, values(runtime)["A"])
        self.assertTrue(any(item.get("excluded") for item in runtime.diagnostics))

    def test_ton_tof_tp_and_edge_persistence(self):
        code = """Delay(IN := Start, PT := T#20ms); OffDelay(IN := Start, PT := T#20ms);
        Pulse(IN := Start, PT := T#20ms); Rising(CLK := Start); Falling(CLK := Start);
        Q := Delay.Q;"""
        runtime = VirtualRuntime(project(code, [variable("Start", "BOOL", False), variable("Q", "BOOL", False),
            variable("Delay", "TON", None), variable("OffDelay", "TOF", None), variable("Pulse", "TP", None),
            variable("Rising", "R_TRIG", None), variable("Falling", "F_TRIG", None)]))
        runtime.set_value("Start", True)
        runtime.command("scan")
        first = values(runtime)
        self.assertFalse(first["Delay"]["Q"])
        self.assertTrue(first["Rising"]["Q"])
        self.assertTrue(first["Pulse"]["Q"])
        runtime.command("scan")
        runtime.command("scan")
        self.assertTrue(values(runtime)["Q"])
        self.assertFalse(values(runtime)["Pulse"]["Q"])
        runtime.set_value("Start", False)
        runtime.command("scan")
        self.assertTrue(values(runtime)["Falling"]["Q"])
        self.assertTrue(values(runtime)["OffDelay"]["Q"])
        runtime.command("scan")
        runtime.command("scan")
        self.assertFalse(values(runtime)["OffDelay"]["Q"])

    def test_ctu_ctd_rising_edges_and_outputs(self):
        runtime = VirtualRuntime(project("Up(CU := Input, R := Reset, PV := 2, Q => Done); Down(CD := Input, LD := Reset, PV := 2);",
            [variable("Input", "BOOL", False), variable("Reset", "BOOL", True), variable("Done", "BOOL", False),
             variable("Up", "CTU", None), variable("Down", "CTD", None)]))
        runtime.command("scan")
        runtime.set_value("Reset", False)
        for _ in range(2):
            runtime.set_value("Input", True)
            runtime.command("scan")
            runtime.command("scan")
            runtime.set_value("Input", False)
            runtime.command("scan")
        self.assertEqual(2, values(runtime)["Up"]["CV"])
        self.assertEqual(0, values(runtime)["Down"]["CV"])
        self.assertTrue(values(runtime)["Done"])

    def test_custom_function_and_function_block(self):
        code = "A := Double(3); Counter(Enable := TRUE, Count => A);"
        data = project(code, [variable("A"), variable("Counter", "MyCounter", None)])
        data["functions"] = [
            {"id": "double", "name": "Double", "scope": "Library", "language": "st", "source": "Double.st", "code":
             "FUNCTION Double : DINT VAR_INPUT X : DINT; END_VAR Double := X * 2; END_FUNCTION"},
            {"id": "counter", "name": "MyCounter", "scope": "Library", "language": "st", "source": "MyCounter.st", "code":
             "FUNCTION_BLOCK MyCounter VAR_INPUT Enable : BOOL; END_VAR VAR_OUTPUT Count : DINT; END_VAR IF Enable THEN Count := Count + 1; END_IF; END_FUNCTION_BLOCK"}]
        runtime = VirtualRuntime(data)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command("scan")
        runtime.command("scan")
        self.assertEqual(2, values(runtime)["Counter"]["Count"])
        self.assertEqual(2, values(runtime)["A"])

    def test_fun_interface_is_merged_without_changing_source_lines(self):
        data = project("A := AddOne(4);", [variable("A")])
        data["functions"] = [{"id": "add", "name": "AddOne", "scope": "Library", "source": "AddOne.st", "language": "st",
            "code": "FUNCTION AddOne : DINT\nAddOne := X + 1;\nEND_FUNCTION",
            "interface": {"declaration": "FUNCTION AddOne : DINT VAR_INPUT X : DINT; END_VAR END_FUNCTION", "source": "Library.fun"}}]
        runtime = VirtualRuntime(data)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command("scan")
        self.assertEqual(5, values(runtime)["A"])

    def test_automation_basic_subset(self):
        code = "A = 0\nFOR i = 1 TO 3\nA = A + i\nNEXT i\nIF A = 6 THEN\nFlag = TRUE\nELSE\nFlag = FALSE\nENDIF"
        runtime = VirtualRuntime(project(code, [variable("A"), variable("i"), variable("Flag", "BOOL", False)], "ab"))
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command("scan")
        self.assertEqual(6, values(runtime)["A"])
        self.assertTrue(values(runtime)["Flag"])

    def test_restricted_c_functions_and_loops(self):
        code = "int twice(int x){return x*2;} void _CYCLIC cyclic(void){ A = twice(3); for(int i=0; i<3; i++){ A += 1; } if(A==9){ Flag=1; } }"
        runtime = VirtualRuntime(project(code, [variable("A"), variable("Flag", "BOOL", False)], "c"))
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command("scan")
        self.assertEqual(9, values(runtime)["A"])
        self.assertTrue(values(runtime)["Flag"])

    def test_ladder_series_parallel_and_negation(self):
        xml = """<Ladder><Network><Row><Contact name="Start" type="open"/><Contact name="Stop" type="closed"/><Coil name="Motor"/></Row>
        <Row><Contact name="Hold" type="open" or="true"/></Row></Network></Ladder>"""
        compiled = compile_ladder(xml)
        self.assertTrue(compiled["compatibility"]["runAllowed"], compiled["diagnostics"])
        data = project("", [variable("Start", "BOOL", False), variable("Hold", "BOOL", True), variable("Stop", "BOOL", False), variable("Motor", "BOOL", False)], "ld")
        data["programs"][0]["networks"] = [instruction["network"] for instruction in compiled["sections"][0]["instructions"]]
        runtime = VirtualRuntime(data)
        runtime.command("scan")
        self.assertTrue(values(runtime)["Motor"])
        runtime.set_value("Stop", True)
        runtime.command("scan")
        self.assertFalse(values(runtime)["Motor"])

    def test_ladder_unsupported_network_blocks(self):
        compiled = compile_ladder('<Ladder><Network><Row><FunctionBlock name="Motion" type="MpAxisBasic"/></Row></Network></Ladder>')
        self.assertFalse(compiled["compatibility"]["runAllowed"])

    def test_breakpoint_and_instruction_step(self):
        runtime = VirtualRuntime(project("A := 1;\nA := 2;", [variable("A")]))
        runtime.set_breakpoint("Logical/Main/Main.st", 2)
        runtime.command("scan")
        self.assertEqual(1, values(runtime)["A"])
        self.assertEqual("paused", runtime.status)
        runtime.command("step")
        self.assertEqual(2, values(runtime)["A"])

    def test_infinite_loop_is_bounded(self):
        runtime = VirtualRuntime(project("WHILE TRUE DO A := A; END_WHILE;", [variable("A")]))
        runtime.command("scan")
        self.assertEqual("faulted", runtime.status)
        self.assertTrue("limit" in runtime.diagnostics[-1]["message"] or "budget" in runtime.diagnostics[-1]["message"])
        self.assertLessEqual(len(runtime.trace), 3000)

    def test_struct_enum_and_digital_signal_share_memory(self):
        data = project("State := Running; Settings.Speed := 25; Output := State = Running;", [variable("State", "StateType", 0),
            variable("Settings", "SettingsType", None), variable("Output", "BOOL", False)], types={
                "StateType": {"kind": "enum", "values": {"Idle": 0, "Running": 1}},
                "SettingsType": {"kind": "struct", "fields": [{"name": "Speed", "type": "REAL"}]}},
            signals=[{"id": "do0", "name": "Output 0", "variable": "Main::Output", "direction": "output"}])
        runtime = VirtualRuntime(data)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command("scan")
        self.assertEqual(25, values(runtime)["Settings"]["Speed"])
        self.assertTrue(runtime.snapshot()["signals"][0]["value"])

    def test_unknown_inactive_vendor_type_remains_visible(self):
        runtime = VirtualRuntime(project("A := 2;", [variable("A"), variable("Unused", "ArVendorOpaque", None)]))
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        self.assertEqual(2, len(runtime.snapshot()["variables"]))
        runtime.command("scan")
        self.assertEqual(2, values(runtime)["A"])
        blocked = VirtualRuntime(project("Unused := 2;", [variable("Unused", "ArVendorOpaque", None)]))
        self.assertFalse(blocked.run_allowed)

    def test_hmi_completion_value_text_is_typed_and_exit_executes(self):
        runtime = VirtualRuntime(project("PROGRAM _CYCLIC Output := Start; END_PROGRAM PROGRAM _EXIT Output := FALSE; END_PROGRAM",
            [variable("Start", "BOOL", False), variable("Output", "BOOL", False)]))
        runtime.set_value("Start", "1")
        runtime.command("scan")
        self.assertTrue(values(runtime)["Output"])
        runtime.command("stop")
        self.assertFalse(values(runtime)["Output"])
        runtime.set_value("Start", "0")
        self.assertFalse(values(runtime)["Start"])

    def test_duplicate_function_subset_and_aliased_iec_timer(self):
        data = project("A := Double(2); Delay(IN := TRUE, PT := T#10ms);", [variable("A"), variable("Delay", "TimerType", None)],
                       types={"TimerType": {"kind": "alias", "type": "TON"}})
        function = {"id": "double", "name": "Double", "scope": "Library", "language": "st", "source": "Double.st", "code":
                    "FUNCTION Double : DINT VAR_INPUT X : DINT; END_VAR Double := 2 * X; END_FUNCTION"}
        data["programs"].append(function)
        data["functions"] = [function]
        runtime = VirtualRuntime(data)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command("scan")
        runtime.command("scan")
        self.assertEqual(4, values(runtime)["A"])
        self.assertTrue(values(runtime)["Delay"]["Q"])

    def test_ambiguous_variable_never_silently_selected(self):
        runtime = VirtualRuntime(project("Start := TRUE;", [variable("Start", "BOOL", False, ambiguous=True)]))
        self.assertFalse(runtime.run_allowed)
        with self.assertRaises(ValueError): runtime.set_value("Start", True)

    def test_trace_values_are_bounded_and_no_string_multiplication(self):
        runtime = VirtualRuntime(project("Data[0] := 3;", [variable("Data", "ARRAY [0..999] OF DINT", None)]))
        runtime.command("scan")
        event = next(event for event in runtime.trace if event["kind"] == "variable")
        self.assertLessEqual(len(event["changes"][0]["value"]), 33)
        self.assertEqual(1000, len(values(runtime)["Data"]))
        blocked = VirtualRuntime(project("Text := 'x' * 1000000000;", [variable("Text", "STRING[80]", "")]))
        blocked.command("scan")
        self.assertEqual("faulted", blocked.status)

    def test_user_function_missing_input_blocks_before_any_assignment(self):
        data = project("A := 3; A := Double();", [variable("A")])
        data["functions"] = [{"id": "double", "name": "Double", "scope": "Library", "language": "st", "source": "Double.st", "code":
             "FUNCTION Double : DINT VAR_INPUT X : DINT; END_VAR Double := X * 2; END_FUNCTION"}]
        runtime = VirtualRuntime(data)
        self.assertFalse(runtime.run_allowed)
        self.assertEqual(0, values(runtime)["A"])

    def test_total_memory_budget_spans_all_variables_and_struct_initializers(self):
        array = {"kind": "array", "bounds": [[0, 39]], "elementType": "DINT"}
        nested = {"kind": "struct", "fields": [{"name": "Values", "type": "Buffer", "initial": list(range(40))}]}
        with patch("virtual_plc.core.memory.MAX_MEMORY_ELEMENTS", 100):
            memory = PLCMemory([variable("One", "Record", None), variable("Two", "Record", None), variable("Three", "Record", None)],
                               {"Buffer": array, "Record": nested}, strict=False)
        self.assertLessEqual(sum(item["quality"] == "simulated" for item in memory.snapshot()), 2)
        self.assertTrue(any(item["code"] == "MEMORY_UNRESOLVED_TYPE" for item in memory.diagnostics))

    def test_recursive_calls_and_large_call_frames_fault_without_unbounded_allocation(self):
        data = project("A := Recurse(1);", [variable("A")])
        data["functions"] = [{"id": "rec", "name": "Recurse", "scope": "Library", "language": "st", "source": "Recursive.st", "code":
            "FUNCTION Recurse : DINT VAR_INPUT X : DINT; END_VAR Recurse := Recurse(X); END_FUNCTION"}]
        runtime = VirtualRuntime(data)
        runtime.command("scan")
        self.assertEqual("faulted", runtime.status)
        self.assertIn("depth limit", runtime.diagnostics[-1]["message"])
        data["functions"][0]["code"] = "FUNCTION Recurse : DINT VAR_INPUT X : DINT; END_VAR VAR Buffer : ARRAY [0..60000] OF DINT; END_VAR Recurse := X; END_FUNCTION"
        runtime = VirtualRuntime(data)
        runtime.command("scan")
        self.assertEqual("faulted", runtime.status)
        self.assertIn("memory element limit", runtime.diagnostics[-1]["message"])

    def test_qualified_enum_prevents_unrelated_name_collision(self):
        data = project("State := First#Running;", [variable("State", "First", 0)], types={
            "First": {"kind": "enum", "values": {"Idle": 0, "Running": 1}},
            "Second": {"kind": "enum", "values": {"Idle": 0, "Running": 2}}})
        runtime = VirtualRuntime(data)
        self.assertTrue(runtime.run_allowed, runtime.diagnostics)
        runtime.command("scan")
        self.assertEqual(1, values(runtime)["State"])
        data["programs"][0]["code"] = "State := Running;"
        runtime = VirtualRuntime(data)
        self.assertFalse(runtime.run_allowed)


if __name__ == "__main__":
    unittest.main()
