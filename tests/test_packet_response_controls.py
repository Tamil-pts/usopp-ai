"""Regression checks for payload headers, response setup and task-local cursors."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
from tests.test_source_parsing import ENGINE


FINALIZE = """nw_snd_buffer_length := ((nw_snd_buffer[3] * 256) + nw_snd_buffer[4] + 5);
nw_snd_response := TRUE;
"""
SOURCE = """CASE nw_group_code OF
10:(*Read program version*)
nw_snd_buffer[2] := 0;
nw_snd_buffer[3] := 0;(*Group size bytes msb*)
nw_snd_buffer[4] := 4;(*Group size bytes lsb*)
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(product),2);(*Product code*)
nw_i := nw_i + 2;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(PLC_PROGRAM_VERSION),SIZEOF(PLC_PROGRAM_VERSION));(*Program version*)
""" + FINALIZE + """11:(*Read TCP Close Command*)
TCP_CLOSE_ON := TRUE;
20:(*Read Default Screens*)
nw_snd_buffer[2] := 0;
nw_snd_buffer[3] := 0;(*Group size bytes msb*)
nw_snd_buffer[4] := 32;(*Group size bytes lsb*)
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(screen_payload),32);(*Default screen data*)
nw_i := nw_i + 32;
30:(*Read current fault data*)
nw_snd_buffer[3] := 0;(*Group size bytes msb*)
nw_snd_buffer[4] := 8;(*Group size bytes lsb*)
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(fault_payload),8);
nw_i := nw_i + 8;
""" + FINALIZE + "END_CASE\n"


def write_project(root, source=SOURCE, cursor_type="USINT"):
    task = root / "Logical" / "SpinConnect" / "mms_nw_r"
    task.mkdir(parents=True, exist_ok=True)
    path = task / "Cyclic.st"
    path.write_text(source, encoding="utf-8")
    (task / "mms_nw_r.var").write_text(f"""VAR
nw_i : {cursor_type};
product : UINT;
PLC_PROGRAM_VERSION : REAL;
screen_payload : ARRAY[0..31] OF BYTE;
fault_payload : ARRAY[0..7] OF BYTE;
END_VAR
""", encoding="utf-8")
    return path


class PacketResponseControlTests(unittest.TestCase):
    def test_all_three_bugs_reach_json_excel_and_failure_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = write_project(root)
            report = ENGINE.run_engine_json(root, output_excel_path=root / "report.xlsx")
            issues = report["issues"]
            overflow = next(issue for issue in issues if issue["validationType"] == "Packet Overflow")
            self.assertEqual(("4", "6"), (overflow["expected"], overflow["actual"]))
            self.assertIn("nw_snd_buffer[4] := 6;", overflow["suggestedFix"])
            self.assertEqual("5", str(overflow["lineNumber"]))
            missing = [issue for issue in issues if issue["validationType"].startswith("Response ")]
            self.assertEqual({"Response Length Missing", "Response Trigger Missing"},
                             {issue["validationType"] for issue in missing})
            self.assertTrue(all(str(issue["groupCode"]) == "20" for issue in missing))
            cursor = [issue for issue in issues if issue["validationType"] == "Packet Cursor Data Type"]
            self.assertEqual(3, len(cursor))
            self.assertTrue(all(issue["actual"] == "USINT" and str(issue["lineNumber"]) == "2" for issue in cursor))
            self.assertTrue(all(issue["sourceFile"].endswith("mms_nw_r.var") for issue in cursor))
            self.assertGreaterEqual(report["summary"]["failed"], 6)
            groups = {group["groupCode"]: group for group in report["groups"]}
            self.assertEqual("PASS", groups[11]["overallStatus"])
            self.assertEqual("FAIL", groups[10]["overallStatus"])
            self.assertEqual("FAIL", groups[20]["overallStatus"])
            workbook = load_workbook(root / "report.xlsx", read_only=True, data_only=True)
            try:
                cells = {str(value) for sheet in workbook for row in sheet.values for value in row}
                self.assertTrue({"Packet Overflow", "Response Length Missing", "Response Trigger Missing",
                                 "Packet Cursor Data Type"}.issubset(cells))
            finally:
                workbook.close()

    def test_corrected_packets_pass_and_other_task_does_not_hide_usint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corrected = SOURCE.replace("[4] := 4;", "[4] := 6;")
            corrected = corrected.replace("(*Program version*)\n", "(*Program version*)\nnw_i := nw_i + 4;\n")
            corrected = corrected.replace("30:(", FINALIZE + "30:(")
            source = write_project(root, corrected, "UINT")
            ENGINE.initialize_project_context(root)
            groups, issues, _, _ = ENGINE.build_group_results(metadata_compare_enabled=False)
            self.assertTrue(all(group.overall_status == "PASS" for group in groups), issues)
            write_project(root, corrected, "USINT")
            ENGINE.VARIABLES["nw_i"] = ENGINE.SymbolInfo("nw_i", ENGINE.parse_type_expr("UINT"), "OtherTask.var")
            declaration, line = ENGINE.packet_cursor_declaration(source)
            self.assertEqual("USINT", declaration.type_info.name)
            self.assertEqual(2, line)

    def test_response_setup_is_required_on_each_conditional_path(self):
        source_text = """CASE nw_group_code OF
20:(*Default screen*)
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 2;
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(product),2);
nw_i := nw_i + 2;
IF mode = 1 THEN
""" + FINALIZE + "ELSE\nEND_IF\nEND_CASE\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root, source_text, "UINT")
            ENGINE.initialize_project_context(root)
            groups, issues, _, _ = ENGINE.build_group_results(metadata_compare_enabled=False)
            variants = groups[0].packet_variants
            self.assertEqual(2, len(variants))
            self.assertEqual({"PASS", "FAIL"}, {variant["status"] for variant in variants})
            response_issues = [issue for issue in issues if issue.validation_type.startswith("Response ")]
            self.assertEqual(2, len(response_issues))
            self.assertTrue(all("ELSE" in issue.condition for issue in response_issues))

    def test_as27_cursor_uses_packet_program_scope_and_exact_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "mms_nw_r.src"
            source.write_text("CASE nw_group_code OF\nEND_CASE", encoding="utf-8")
            cpu = root / "CPU.txt"
            cpu.write_text("PROGRAM mms_nw_r 3\nVAR\n\nnw_i %MB :USINT;\nEND_VAR\n"
                           "PROGRAM mms_nw_w 3\nVAR\nnw_i %MW :UINT;\nEND_VAR\n", encoding="utf-8")
            symbols = {"nw_i": ENGINE.SymbolInfo("nw_i", ENGINE.parse_type_expr("UINT"), "CPU.txt")}
            with patch.multiple(ENGINE, ROOT=root, VARIABLES=symbols):
                declaration, line = ENGINE.packet_cursor_declaration(source)
                self.assertEqual("USINT", declaration.type_info.name)
                self.assertEqual(4, line)


if __name__ == "__main__":
    unittest.main()
