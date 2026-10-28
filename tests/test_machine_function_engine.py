import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from backend.api import project_intelligence as project_intelligence_api
from backend.core import project_intelligence
from backend.core import project_assistant
from python_engine.machine_function_engine import _active_task_for, analyze, compact_for_chat
from backend.core.project_assistant import _complete_sequence_question


REFERENCE_ST = """PROGRAM MainCyclic
VAR
    State : INT;
    RunReq : BOOL;
    StartPermissive : BOOL;
    MotorCmd : BOOL;
    SpeedFb : BOOL;
    StopReq : BOOL;
    Fault : BOOL;
    Reset : BOOL;
    StartDelay : TON;
    Alarm : BOOL;
END_VAR
CASE State OF
0:
    IF RunReq AND StartPermissive THEN
        MotorCmd := TRUE;
        State := 10;
    END_IF
10:
    StartDelay(IN := MotorCmd, PT := T#2S);
    IF StartDelay.Q AND SpeedFb THEN
        State := 20;
    END_IF
20:
    IF StopReq THEN
        MotorCmd := FALSE;
        State := 30;
    ELSIF Fault THEN
        MotorCmd := FALSE;
        State := 40;
    END_IF
30:
    IF NOT SpeedFb THEN
        State := 0;
    END_IF
40:
    Alarm := TRUE;
    IF Reset AND NOT Fault THEN
        State := 50;
    END_IF
50:
    Alarm := FALSE;
    State := 0;
END_CASE
END_PROGRAM
"""


class MachineFunctionEngineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="chopper-machine-reference-")
        self.base = Path(self.temp.name)
        self.root = self.base / "known-sequence"
        (self.root / "Logical" / "MainTask").mkdir(parents=True)
        (self.root / "Physical" / "CFG" / "PLC1").mkdir(parents=True)
        (self.root / "LastUser.set").write_text(
            '<Settings><ConfigurationManager ActiveConfigurationName="CFG"/></Settings>', encoding="utf-8"
        )
        (self.root / "Physical" / "CFG" / "PLC1" / "Cpu.sw").write_text(
            '<Cpu><Task Name="Main" Source="MainTask" Disabled="false" CycleTime="20" Priority="5"/><VcDataObject Name="HmiA"/></Cpu>',
            encoding="utf-8",
        )
        (self.root / "Logical" / "MainTask" / "mainCyclic.st").write_text(
            REFERENCE_ST.replace("CASE State OF", "StartSequence();\nCASE State OF"), encoding="utf-8"
        )
        (self.root / "Logical" / "SharedLibs").mkdir(parents=True)
        (self.root / "Logical" / "SharedLibs" / "sequence.st").write_text(
            """FUNCTION StartSequence : BOOL
VAR
    Step : INT;
END_VAR
CASE Step OF
0:
    IF RunReq THEN
        Step := 1;
    END_IF
1:
    IF StopReq THEN
        Step := 0;
    END_IF
END_CASE
StartSequence := TRUE;
END_FUNCTION
""",
            encoding="utf-8",
        )
        (self.root / "Logical" / "MainTask" / "mainCyclic.ld").write_text(
            'PROGRAM MainCyclic\n<networks><network label="Motor start"><row><line/><contact name="StartReq" type="open"/><coil name="MotorOut" type="normal"/></row></network></networks>\nEND_PROGRAM',
            encoding="utf-8",
        )
        (self.root / "Logical" / "MainTask" / "Globals.var").write_text(
            "VAR_GLOBAL RETAIN\n    State : INT;\nEND_VAR\n", encoding="utf-8"
        )
        (self.root / "Logical" / "HmiA" / "Pages").mkdir(parents=True)
        (self.root / "Logical" / "HmiB" / "Pages").mkdir(parents=True)
        (self.root / "Logical" / "HmiA" / "Pages" / "main.page").write_text(
            '<Page><Control Name="RunButton"><Property Name="ValueDatapoint" Value="::PLC.Variable[RunReq]"/></Control></Page>',
            encoding="utf-8",
        )
        (self.root / "Logical" / "HmiB" / "Pages" / "other.page").write_text(
            '<Page><Control Name="AltRunButton"><Property Name="ValueDatapoint" Value="::PLC.Variable[MotorCmd]"/></Control></Page>',
            encoding="utf-8",
        )
        (self.root / "Physical" / "CFG" / "PLC1" / "IoMap.iom").write_text("MotorCmd AT %QX0.0;\n", encoding="utf-8")
        (self.root / "Physical" / "ALT" / "PLC1").mkdir(parents=True)
        (self.root / "Physical" / "ALT" / "PLC1" / "IoMap.iom").write_text("MotorCmd AT %QX0.1;\n", encoding="utf-8")
        self.work_patch = patch.object(project_intelligence, "WORK", self.base / "runtime")
        self.work_patch.start()
        self.index = project_intelligence.Index(self.root, "machine-reference")
        self.index_state = self.index.build(mode="rebuild")
        self.result = analyze(self.index)

    def tearDown(self):
        self.work_patch.stop()
        self.temp.cleanup()

    def test_known_start_run_stop_fault_and_recovery_are_source_linked(self):
        self.assertTrue(self.index_state["ready"])
        self.assertEqual(self.result["project"]["activeConfiguration"], "CFG")
        machine = next(item for item in self.result["stateMachines"] if item["ownership"] == "active task")
        transitions = {(item["from"], item["to"]): item for item in machine["transitions"]}
        expected = {("0", "10"), ("10", "20"), ("20", "30"), ("20", "40"), ("30", "0"), ("40", "50"), ("50", "0")}
        self.assertTrue(expected.issubset(transitions))
        for pair in expected:
            self.assertTrue(transitions[pair]["evidence"], pair)
        self.assertIn("RunReq AND StartPermissive", transitions[("0", "10")]["conditions"])
        self.assertTrue(any("MotorCmd := TRUE" in action["code"] for action in transitions[("0", "10")]["actions"]))
        self.assertTrue(any("MotorCmd := FALSE" in action["code"] for action in transitions[("20", "40")]["actions"]))
        self.assertTrue(any("Reset" in condition for condition in transitions[("40", "50")]["conditions"]))

    def test_timer_retention_multiple_writes_and_limits_are_reported(self):
        self.assertTrue(any(item["instance"] == "StartDelay" and item["type"] == "TON" for item in self.result["timers"]))
        self.assertTrue(any(item["name"] == "State" and "RETAIN" in item["status"] for item in self.result["retainedVariables"]))
        writes = next(item for item in self.result["multipleWriters"] if item["signal"] == "MotorCmd")
        self.assertGreaterEqual(writes["writerCount"], 3)
        self.assertIn("does not prove", " ".join(self.result["coverage"]["notices"]))
        compact = compact_for_chat(self.result)
        self.assertFalse(compact["coverage"]["indexReady"] is False)
        self.assertTrue(compact["stateMachines"])
        self.assertEqual(9, compact["totalTransitionCount"])
        self.assertTrue(compact["reachableStateMachines"])

    def test_ladder_topology_and_complete_sequence_question_are_detected(self):
        self.assertEqual(1, self.result["coverage"]["ladderNetworkCount"])
        network = self.result["ladderNetworks"][0]
        self.assertIn("StartReq", network["summary"])
        self.assertIn("MotorOut", network["summary"])
        self.assertTrue(network["evidence"])
        self.assertTrue(all(item["evidence"] for item in self.result["ladderNetworks"]))
        self.assertTrue(_complete_sequence_question("Explain the complete machine working sequence"))
        self.assertTrue(_complete_sequence_question("Reconstruct the entire machine operating sequence"))

    def test_hardware_and_hmi_links_stay_in_the_selected_configuration(self):
        self.assertEqual(2, self.result["coverage"]["hardwareMappingCount"])
        self.assertEqual(1, self.result["coverage"]["activeHardwareMappingCount"])
        active_mapping = next(item for item in self.result["hardwareLinks"] if item["ownership"] == "active configuration")
        self.assertEqual("CFG", active_mapping["configuration"])
        self.assertEqual(2, self.result["coverage"]["hmiBindingCount"])
        self.assertEqual(1, self.result["coverage"]["selectedHmiBindingCount"])
        selected = [item for item in self.result["hmiLinks"] if item["ownership"] == "selected HMI project"]
        self.assertEqual(["HmiA"], [item["hmiProject"] for item in selected])

    def test_active_task_resolution_rejects_foreign_and_unresolved_configurations(self):
        tasks = [
            {"name": "disabled", "source": "MainTask", "configuration": "CFG", "enabled": False},
            {"name": "foreign", "source": "MainTask", "configuration": "ALT", "enabled": True},
            {"name": "selected", "source": "MainTask", "configuration": "CFG", "enabled": True},
        ]
        task, ownership = _active_task_for("Logical/MainTask/mainCyclic.st", tasks, "CFG")
        self.assertEqual("selected", task["name"])
        self.assertEqual("active task", ownership)
        task, ownership = _active_task_for("Logical/MainTask/mainCyclic.st", tasks, "ALT")
        self.assertEqual("foreign", task["name"])
        self.assertEqual("active task", ownership)
        _, ownership = _active_task_for("Logical/MainTask/mainCyclic.st", tasks, "MISSING")
        self.assertEqual("other configuration task", ownership)
        _, ownership = _active_task_for("Logical/MainTask/mainCyclic.st", tasks, "")
        self.assertEqual("task assignment found; active configuration unresolved", ownership)

    def test_call_graph_records_have_source_evidence(self):
        self.assertTrue(self.result["callGraph"])
        self.assertTrue(all(item["evidence"] for item in self.result["callGraph"]))

    def test_local_call_graph_marks_shared_routines_as_potentially_reachable(self):
        machine = next(item for item in self.result["stateMachines"] if item["name"].casefold() == "step")
        self.assertEqual("shared / task ownership unconfirmed", machine["ownership"])
        self.assertEqual(["Main"], machine["reachableFromTasks"])
        self.assertIn("not executed", machine["reachabilityStatus"])
        self.assertGreaterEqual(self.result["coverage"]["reachableStateGroupCount"], 1)
        compact = compact_for_chat(self.result)
        self.assertTrue(compact["reachableStateMachines"])
        self.assertTrue(any(item["callee"] == "StartSequence" and item["reachableFromTasks"] == ["Main"] for item in compact["callGraph"]))

    def test_source_excerpt_endpoint_data_is_index_scoped_and_freshness_checked(self):
        source = self.index.source_excerpt("Logical/MainTask/mainCyclic.st", 17)
        self.assertEqual("matches indexed source", source["freshness"])
        self.assertIn("State := 10", source["excerpt"])
        request = SimpleNamespace(state=SimpleNamespace(user={"id": "machine-reference"}))
        response = project_intelligence_api.project_source(self.index.key, request, "Logical/MainTask/mainCyclic.st", 17)
        self.assertEqual(source["excerpt"], response["excerpt"])
        with self.assertRaises(HTTPException):
            project_intelligence_api.project_source(self.index.key, SimpleNamespace(state=SimpleNamespace(user={"id": "another-user"})), "Logical/MainTask/mainCyclic.st", 17)
        with self.assertRaises(PermissionError):
            self.index.source_excerpt("..\\outside.st", 1)
        with self.assertRaises(PermissionError):
            self.index.source_excerpt("Logical\\MainTask\\not-indexed.st", 1)
        (self.root / "Logical" / "MainTask" / "mainCyclic.st").write_text(REFERENCE_ST + "(* changed after indexing *)\n", encoding="utf-8")
        changed = self.index.source_excerpt("Logical/MainTask/mainCyclic.st", 17)
        self.assertIn("source changed since indexing", changed["freshness"])

    def test_chopper_chat_returns_the_machine_model_and_cited_static_findings(self):
        token = project_assistant.current_user.set({"id": "machine-reference"})
        try:
            with patch.object(project_assistant, "configuration", return_value={"provider": "unavailable"}), \
                 patch.object(project_assistant, "report"):
                response = project_assistant.answer({
                    "question": "Explain the complete machine working sequence",
                    "context": {"intelligenceProjectId": self.index.key},
                })
        finally:
            project_assistant.current_user.reset(token)
        self.assertIn("machineAnalysis", response)
        self.assertTrue(response["machineAnalysis"]["detailLimited"])
        self.assertEqual(self.index.key, response["machineAnalysisProjectId"])
        self.assertTrue(response["machineAnalysis"]["stateMachines"])
        self.assertIn("source-parsed CASE transitions", response["answer"])
        self.assertIn("Selected source-parsed call relationships", response["answer"])
        cited = set(__import__("re").findall(r"\bS\d+\b", response["answer"]))
        supplied = {item["sourceId"] for item in response["evidence"] if item.get("sourceId")}
        self.assertTrue(cited, response["answer"])
        self.assertTrue(cited.issubset(supplied))


if __name__ == "__main__":
    unittest.main()
