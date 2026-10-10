import importlib.util
import re
import sys
import unittest
from pathlib import Path


ENGINE_PATH = Path(__file__).resolve().parents[1] / "python_engine" / "packet_validation_report_uSOPp_v1.71_final.py"
SPEC = importlib.util.spec_from_file_location("usopp_packet_engine_branch_tests", ENGINE_PATH)
ENGINE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ENGINE
SPEC.loader.exec_module(ENGINE)


class MemoryPath:
    def __init__(self, text: str, name: str):
        self.text = text
        self.name = name

    def read_text(self, **_kwargs):
        return self.text

    def resolve(self):
        return (Path.cwd() / self.name).resolve()


def parse_fixture(text: str, group_code: int):
    declarations = re.findall(r"ADR\(([A-Za-z_]\w*)\)\s*,\s*(\d+)\)", text)
    aliases = {1: "BYTE", 2: "UINT", 4: "REAL"}
    ENGINE.VARIABLES = {
        name: ENGINE.SymbolInfo(
            name=name,
            type_info=(
                ENGINE.TypeInfo(aliases[int(size)], "alias")
                if int(size) in aliases
                else ENGINE.parse_type_expr(f"ARRAY[0..{int(size)-1}] OF BYTE")
            ),
            source_file="fixture.var",
        )
        for name, size in declarations
        if name != "nw_snd_buffer"
    }
    ENGINE.resolve_type_info.cache_clear()
    return ENGINE.parse_group(
        MemoryPath(text, f"gc{group_code}.st"),
        group_code,
        "Fixture",
        1,
        len(text.splitlines()),
        include_variants=True,
    )


GC140 = """140:(*Read Process Settings*)
nw_snd_buffer[3] := 0;(*Group size bytes msb*)
nw_snd_buffer[4] := 13;(*Group size bytes lsb*)
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(CUR_PGM),1);(*Current Program*)
nw_i := nw_i + 1;
IF (CUR_PGM = 1) THEN(*PROCESS 1*)
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(HMI_CAN_LENGTH_PGM2),2);(*CAN Length*)
nw_i := nw_i + 2;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(TARGET_FEED_WT),2);(*Target Feed Weight*)
nw_i := nw_i + 2;
ELSIF (CUR_PGM = 2) THEN (*PROCESS 2*)
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(HMI_CAN_LENGTH_PGM2),2);(*CAN Length*)
nw_i := nw_i + 2;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(TARGET_FEED_WT_2),4);(*Target Feed Weight*)
nw_i := nw_i + 2;
ELSIF (CUR_PGM = 3) THEN (*PROCESS 3*)
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(HMI_CAN_LENGTH_PGM3),2);(*CAN Length*)
nw_i := nw_i + 2;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(MMS_TARGET_FEED_WT_3),2);(*Target Feed Weight*)
nw_i := nw_i + 2;
END_IF
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(ST_REF),4);(*ST ref*)
nw_i := nw_i + 4;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(ST_INST),4);(*ST inst*)
nw_i := nw_i + 4;
"""


GC20 = """20:(*Read machine status*)
nw_snd_buffer[3] := 0;(*Group size bytes msb for 2Q*)
nw_snd_buffer[4] := 8;(*Group size bytes lsb for 2Q*)
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(MODEL_VW4141),2);(*MACHINE TYPE*)
nw_i := nw_i+2;
IF LINK_V4168_0 THEN
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(NOCOPREQ_V4169_0_V),1);(*AUTOCONER LINK STATUS*)
ELSE
nw_snd_buffer[nw_i] := 2;
END_IF
nw_i := nw_i+1;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Ring_center_sel_V4268_0_V),1);(*RING CENTERING STATUS*)
nw_i := nw_i+1;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Traveller_Run_IN_Status_V),1);(*TRAVELLER RUNNING STATUS*)
nw_i := nw_i+1;
nw_i := nw_i+1;
IF(V4118_6_Display_2Q_Selection = 0) THEN
nw_snd_buffer[3] := 0;(*Group size bytes msb for 4Q*)
nw_snd_buffer[4] := 16;(*Group size bytes lsb for 4Q*)
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(TS_LHS_J9_4THROLL_TPI_DISP),4);(*TAIL STOCK LHS TPI*)
nw_i := nw_i+4;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(TS_LHS_J9_4THROLL_DELIVERY),4);(*TAIL STOCK LHS DELIVERY*)
nw_i := nw_i+4;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(TS_LHS_Disengaged_V40_2),1);(*TAIL STOCK*)
nw_i := nw_i+1;
ELSE
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(HS_FEEDROLL_ENGAGED),1);(*HS FEED*)
nw_i := nw_i+1;
END_IF
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(PMS_Machine_Stoppage),2);(*Machine Stoppage Reason*)
nw_i := nw_i+2;
"""


class PacketBranchVariantTests(unittest.TestCase):
    def test_gc260_empty_statements_advance_cursor_once(self):
        for terminator in (';', ';;', '; ; ;'):
            with self.subTest(terminator=terminator):
                source = f'''260:(*Program status*)
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 4;
nw_i := 5{terminator}
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Blow_room_product_code),2);(*Product code*)
nw_i := nw_i + 2{terminator} (*advance once*)
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(HMI_A1_RSV_PROGRAM_STATUS),2);(*Program Status*)
nw_i := nw_i + 2{terminator}
'''
                parameters, _, _, _, issues, variants = parse_fixture(source, 260)
                self.assertEqual([5, 7], [p.running_offset for p in parameters])
                self.assertEqual([2, 2], [p.increment_value for p in parameters])
                self.assertEqual([0, 2], [p['tcpOffset'] for p in variants[0]['parameters']])
                self.assertEqual('PASS', variants[0]['status'])
                self.assertFalse(issues)

    def test_gc30_reports_missing_cursor_init_and_hardcoded_alarm_destination(self):
        source = """30:(*Read Current Fault History*)
nw_snd_buffer[2] := 0;
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 9;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Blow_room_product_code),2);(*Product code*)
nw_i := nw_i + 2;
memcpy(ADR(nw_snd_buffer[5]),ADR(Temp_nw_snd_buffer[1]),5);(*Alarm Byte*)
nw_i := nw_i + 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(machine_stauts_hmi[0]),2);(*Machine Status*)
nw_i := nw_i + 2;
"""
        parameters, _configured, _msb, _lsb, issues, variants = parse_fixture(source, 30)
        product = next(parameter for parameter in parameters if parameter.parameter_name == "Blow_room_product_code")
        alarm = next(parameter for parameter in parameters if parameter.parameter_name == "Temp_nw_snd_buffer[1]")
        init_issue = next(issue for issue in product.issues if issue.validation_type == "Packet Cursor Initialization")
        destination_issue = next(issue for issue in alarm.issues if issue.validation_type == "Hardcoded Packet Destination")
        offset_issue = next(issue for issue in alarm.issues if issue.validation_type == "Offset")
        self.assertEqual("nw_i := 5 before the first payload write", init_issue.expected)
        self.assertEqual("NOT FOUND", init_issue.actual)
        self.assertEqual("nw_snd_buffer[nw_i+2]", destination_issue.expected)
        self.assertEqual("nw_snd_buffer[5]", destination_issue.actual)
        self.assertEqual(("7", "5"), (offset_issue.expected, offset_issue.actual))
        self.assertEqual("FAIL", variants[0]["status"])
        self.assertTrue(any(issue.validation_type == "Overlapping Offset" for issue in issues))

    def test_same_start_and_end_offsets_report_overlap_without_crashing(self):
        source = """50:(*Duplicate write*)
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 2;
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(FIRST_VALUE),2);(*First*)
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(SECOND_VALUE),2);(*Second*)
nw_i := nw_i + 2;
"""
        parameters, _configured, _msb, _lsb, issues, variants = parse_fixture(source, 50)
        self.assertEqual(2, len(parameters))
        self.assertEqual("FAIL", variants[0]["status"])
        self.assertTrue(any(issue.validation_type in {"Duplicate Offset", "Overlapping Offset"} for issue in issues))

    def test_gc140_marks_only_bad_program_branch_as_failed(self):
        parameters, _configured, _msb, _lsb, issues, variants = parse_fixture(GC140, 140)
        by_condition = {variant["condition"]: variant for variant in variants}

        self.assertEqual("PASS", by_condition["IF (CUR_PGM = 1) THEN"]["status"])
        self.assertEqual("FAIL", by_condition["ELSIF (CUR_PGM = 2) THEN"]["status"])
        self.assertEqual("PASS", by_condition["ELSIF (CUR_PGM = 3) THEN"]["status"])
        self.assertTrue(any(condition.startswith("NO MATCH") for condition in by_condition))

        bad = next(parameter for parameter in parameters if parameter.parameter_name == "TARGET_FEED_WT_2")
        increment_issue = next(issue for issue in bad.issues if issue.validation_type == "Offset Increment")
        self.assertEqual("4", increment_issue.expected)
        self.assertEqual("2", increment_issue.actual)
        self.assertEqual("ELSIF (CUR_PGM = 2) THEN", increment_issue.condition)
        self.assertFalse(any(issue.validation_type == "Conditional Packet Size" for issue in issues))

    def test_gc20_keeps_variant_sizes_and_exposes_unwritten_gap(self):
        parameters, _configured, _msb, _lsb, issues, variants = parse_fixture(GC20, 20)
        by_size = {variant["configuredBytes"]: variant for variant in variants}

        self.assertEqual((16, 17, "FAIL"), (
            by_size[16]["writtenBytes"], by_size[16]["cursorBytes"], by_size[16]["status"]
        ))
        self.assertEqual((8, 9, "FAIL"), (
            by_size[8]["writtenBytes"], by_size[8]["cursorBytes"], by_size[8]["status"]
        ))
        self.assertTrue(all(
            any(issue["validationType"] == "Unwritten Packet Gap" for issue in variant["issues"])
            for variant in variants
        ))
        auto_coner = next(parameter for parameter in parameters if parameter.parameter_name == "NOCOPREQ_V4169_0_V")
        self.assertEqual({"memcpy", "direct-byte"}, {
            evidence["transferMethod"] for evidence in auto_coner.write_evidence
        })
        self.assertFalse(any(issue.validation_type == "Conditional Packet Size" for issue in issues))


if __name__ == "__main__":
    unittest.main()
