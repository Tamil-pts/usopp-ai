import importlib.util
import io
import sys
import tempfile
import unittest
import json
from unittest.mock import patch
from pathlib import Path
from openpyxl import Workbook, load_workbook


ENGINE_PATH = Path(__file__).resolve().parents[1] / "python_engine" / "packet_validation_report_uSOPp_v1.71_final.py"
SPEC = importlib.util.spec_from_file_location("usopp_packet_engine_source_tests", ENGINE_PATH)
ENGINE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ENGINE
SPEC.loader.exec_module(ENGINE)


class SourceParsingTests(unittest.TestCase):
    def test_master_mapping_scope_excludes_other_machines_and_prefers_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'mappings.json'
            base={'plc_parameter':'Mode','plc_tag':'ModeTag','metadata_parameter':'Mode','mapping':[{'PLCVAL':0,'SHOWNVAL':'Off'}]}
            file.write_text(json.dumps({'mappings':[base,{**base,'machine_department':'Carding'},{**base,'machine_department':'Ringframe'}]}),encoding='utf-8')
            with patch.object(ENGINE,'KNOWLEDGE_MASTER_FILE',file),patch.object(ENGINE,'KNOWLEDGE_MASTER_DROPDOWN_FILE',file):
                for scope,expected in [('All',['All']),('Carding',['Carding','All']),('Unknown',['All'])]:
                    with patch.object(ENGINE,'ACTIVE_MACHINE_DEPARTMENT',scope):
                        for loader in (ENGINE.load_master_parameter_mappings,ENGINE.load_master_dropdown_mappings):
                            self.assertEqual(expected,[m.get('machine_department','All') for m in loader()])

    def test_generated_duplicate_highlights_are_group_scoped_and_persist(self):
        workbook = Workbook()
        metadata = workbook.active
        metadata.title = "Metadata"
        metadata.append(["Parameters", "GROUP_CODE", "Value"])
        metadata.append(["Same name", 20, "first"])
        metadata.append([" same   name ", 20, "second"])
        metadata.append(["Same name", 30, "different group"])
        sheet2 = workbook.create_sheet("Sheet2")
        sheet2.append(["Parameters", "GROUP_CODE"])
        sheet2.append(["Same name", 20])
        sheet2.append(["Same name", 20])

        self.assertEqual({2, 3}, ENGINE.apply_generated_metadata_duplicate_highlights(metadata))
        first_save = io.BytesIO()
        workbook.save(first_save)
        workbook.close()
        first_save.seek(0)
        saved = load_workbook(first_save)
        second_save = io.BytesIO()
        saved.save(second_save)
        saved.close()
        first_save.close()
        second_save.seek(0)
        checked = load_workbook(second_save)
        try:
            owned_ranges = {
                str(conditional.sqref)
                for conditional, rules in checked["Metadata"].conditional_formatting._cf_rules.items()
                if any(ENGINE.DUPLICATE_PARAMETER_FORMULA in (rule.formula or []) for rule in rules)
            }
            self.assertEqual({"A2:C2", "A3:C3"}, owned_ranges)
            self.assertEqual(0, len(checked["Sheet2"].conditional_formatting._cf_rules))
        finally:
            checked.close()
            second_save.close()

    def test_c_global_comma_declarations_resolve_datatypes(self):
        symbols = ENGINE.parse_c_global_declarations("""
            /* exported by Automation Studio */
            _GLOBAL REAL QM_A_Percent, cv_100cm,
                         cv_1cm, u_percent;
            _GLOBAL_RETAIN unsigned long total_count;
        """)
        self.assertEqual("REAL", symbols["QM_A_Percent"].name)
        self.assertEqual("REAL", symbols["cv_100cm"].name)
        self.assertEqual("REAL", symbols["cv_1cm"].name)
        self.assertEqual("REAL", symbols["u_percent"].name)
        self.assertEqual("UDINT", symbols["total_count"].name)

    def test_as27_cpu_txt_global_declarations_resolve_datatypes(self):
        symbols = ENGINE.parse_as27_cpu_symbols("""
            VAR_GLOBAL
                MACHINE_DELIVERY_RATE %MB :REAL ; ! exported global
                MACHINE_STATUS %MW :UINT ; ! exported global
                Drawframe_Alarms %MX :ARRAY [0..164] OF BOOL ; ! exported global
                hmi_material_processed %MB168 :STRING(80) ; ! fixed address
                total_count %ML88 :UDINT ;
            VAR_CONSTANT
                ERR_OK %CW :UINT := 0;
            END_VAR
        """)
        self.assertEqual("REAL", symbols["MACHINE_DELIVERY_RATE"].name)
        self.assertEqual("UINT", symbols["MACHINE_STATUS"].name)
        self.assertEqual((0, 164), symbols["Drawframe_Alarms"].array_range)
        self.assertEqual(80, symbols["hmi_material_processed"].string_len)
        self.assertEqual("UDINT", symbols["total_count"].name)
        self.assertEqual("UINT", symbols["ERR_OK"].name)

    def test_as27_cpu_txt_struct_members_resolve_nested_arrays(self):
        types = ENGINE.parse_as27_c_struct_types("""
            typedef struct SHIFT_REPORT
            {
                float CURRENT_SHIFT_PARAMETER[120];
                unsigned short CURRENT_SHIFT_NUMBER;
                plcbit INITIALIZE;
                struct R_TRIG set_first_pass;
            } SHIFT_REPORT_typ;
        """)
        self.assertIn("_$SHIFT_REPORT", types)
        struct_type = types["_$SHIFT_REPORT"]
        self.assertEqual("struct", struct_type.kind)
        self.assertEqual("ARRAY[0..119] OF REAL", ENGINE.format_type_info(struct_type.fields["CURRENT_SHIFT_PARAMETER"]))
        self.assertEqual("UINT", struct_type.fields["CURRENT_SHIFT_NUMBER"].name)
        self.assertEqual("BOOL", struct_type.fields["INITIALIZE"].name)

    def test_later_groups_survive_extra_comment_opener_and_are_reported(self):
        source = """CASE nw_group_code OF
20:(*First*)
nw_snd_buffer[4] := 0;
(* ---------------- (* Added by engineering ---------------- *)
30:(*Later*)
nw_snd_buffer[4] := 0;
END_CASE
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mms_nw_rCyclic.st"
            path.write_text(source, encoding="utf-8")
            self.assertEqual([20, 30], [row[0] for row in ENGINE.extract_case_blocks(path)])
            diagnostics = ENGINE.packet_source_diagnostics(path)
        warning = next(item for item in diagnostics if item.validation_type == "Recovered Nested Comment Marker")
        self.assertEqual("WARNING", warning.severity)
        self.assertEqual("4", warning.line_number)

    def test_unterminated_packet_case_is_a_hard_source_diagnostic(self):
        source = """CASE nw_group_code OF
20:(*First*)
nw_snd_buffer[4] := 0;
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mms_nw_rCyclic.st"
            path.write_text(source, encoding="utf-8")
            diagnostics = ENGINE.packet_source_diagnostics(path)
        failure = next(item for item in diagnostics if item.validation_type == "CASE Block Termination")
        self.assertEqual("FAIL", failure.severity)
        self.assertEqual("1", failure.line_number)

    def test_comment_after_unmatched_quote_is_not_parsed_as_packet_logic(self):
        source = "value := 'legacy\n(*// memcpy(ADR(nw_snd_buffer[nw_i]),ADR(MODBUS_374),2);*)\n"
        cleaned = ENGINE.packet_code_lines(source)
        self.assertNotIn("memcpy", cleaned[1])


if __name__ == "__main__":
    unittest.main()
