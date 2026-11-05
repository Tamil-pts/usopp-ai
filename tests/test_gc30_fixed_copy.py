"""The accepted GC30 fixed fault-buffer copy must not mask real packet errors."""
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook
from tests.test_source_parsing import ENGINE
from tests.test_packet_response_controls import FINALIZE


SOURCE = '''CASE nw_group_code OF
30:(*Read current fault data*)
nw_snd_buffer[2] := 0;(*Result code*)
nw_snd_buffer[3] := 0;(*Group size bytes msb*)
nw_snd_buffer[4] := 20;(*Group size bytes lsb*)
memcpy(ADR(nw_snd_buffer[5]),ADR(Temp_nw_snd_buffer[1]),20);
''' + FINALIZE + 'END_CASE\n'


def project(root, source=SOURCE, source_high=49, destination_high=255):
    task = root/'Logical'/'SpinConnect'/'mms_nw_r'
    task.mkdir(parents=True, exist_ok=True)
    path = task/'Cyclic.st'; path.write_text(source, encoding='utf8')
    (task/'Variables.var').write_text(f'''VAR
nw_i : UINT;
Temp_nw_snd_buffer : ARRAY[0..{source_high}] OF USINT;
nw_snd_buffer : ARRAY[0..{destination_high}] OF BYTE;
END_VAR
''', encoding='utf8')
    return path


class GC30FixedCopyTests(unittest.TestCase):
    def test_user_pattern_is_warning_in_json_and_excel_with_true_offsets(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=project(root); original=source.read_bytes()
            report=ENGINE.run_engine_json(root, output_excel_path=root/'accepted.xlsx')
            self.assertEqual(report['summary']['failed'], 0)
            self.assertEqual(report['summary']['warnings'], 1)
            group=report['groups'][0]
            self.assertEqual((group['overallStatus'],group['configuredBytes'],group['calculatedBytes']),('WARNING',20,20))
            variant=group['packetVariants'][0]
            self.assertEqual((variant['addressingMode'],variant['status'],variant['writtenBytes'],variant['calculatedByOffset']),('fixed','WARNING',20,20))
            self.assertTrue(variant['packetCalResult'].startswith('WARNING'))
            self.assertEqual(len(report['issues']),1)
            warning=report['issues'][0]
            self.assertEqual((warning['validationType'],warning['severity'],str(warning['lineNumber'])),('GC30 Fixed Bulk Copy','WARNING','6'))
            self.assertIn('20 bytes',warning['actual']);self.assertIn('Accepted with warning',warning['suggestedFix'])
            self.assertTrue(warning['sourceFile'].endswith('Cyclic.st'))
            self.assertEqual(source.read_bytes(),original)
            book=load_workbook(root/'accepted.xlsx',read_only=True,data_only=True)
            try:
                cells={str(c) for sheet in book for row in sheet.values for c in row}
                self.assertIn('GC30 Fixed Bulk Copy',cells);self.assertIn('WARNING',cells)
            finally:book.close()

    def test_configured_payload_mismatch_still_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project(root,SOURCE.replace('[4] := 20','[4] := 18'))
            result=ENGINE.run_engine_json(root)
            self.assertEqual(result['groups'][0]['overallStatus'],'FAIL')
            issue=next(i for i in result['issues'] if i['validationType']=='Packet Overflow')
            self.assertEqual((issue['severity'],issue['expected'],issue['actual']),('FAIL','18','20'))

    def test_source_and_destination_bounds_remain_failures(self):
        for source_high,destination_high,kind in [(19,255,'Packet Source Bounds'),(49,23,'Packet Destination Bounds')]:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);project(root,source_high=source_high,destination_high=destination_high)
                result=ENGINE.run_engine_json(root)
                self.assertEqual(result['groups'][0]['overallStatus'],'FAIL')
                self.assertTrue(any(i['validationType']==kind and i['severity']=='FAIL' for i in result['issues']))

    def test_other_groups_and_conditional_or_multi_copy_layouts_are_not_exempted(self):
        variants=[SOURCE.replace('30:', '20:'),
                  SOURCE.replace('ADR(Temp_nw_snd_buffer[1])','ADR(nw_snd_buffer[4])'),
                  SOURCE.replace('memcpy(', 'IF enable THEN\nmemcpy(').replace(FINALIZE,'END_IF\n'+FINALIZE),
                  SOURCE.replace(FINALIZE,'memcpy(ADR(nw_snd_buffer[25]),ADR(Temp_nw_snd_buffer[21]),1);\n'+FINALIZE)]
        for text in variants:
            with self.subTest(text=text),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);project(root,text);result=ENGINE.run_engine_json(root)
                self.assertEqual(result['groups'][0]['overallStatus'],'FAIL')
                self.assertNotIn('GC30 Fixed Bulk Copy',{i['validationType'] for i in result['issues']})
                self.assertIn('Packet Cursor Initialization',{i['validationType'] for i in result['issues']})

    def test_cursor_relative_gc30_keeps_its_existing_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=SOURCE.replace('memcpy(ADR(nw_snd_buffer[5])','nw_i := 5;\nmemcpy(ADR(nw_snd_buffer[nw_i])')
            source=source.replace(FINALIZE,'nw_i := nw_i + 20;\n'+FINALIZE)
            project(root,source);result=ENGINE.run_engine_json(root)
            self.assertEqual(result['groups'][0]['overallStatus'],'PASS')
            self.assertEqual(result['groups'][0]['packetVariants'][0]['addressingMode'],'cursor')
            self.assertNotIn('GC30 Fixed Bulk Copy',{i['validationType'] for i in result['issues']})

    def test_missing_response_controls_still_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project(root,SOURCE.replace(FINALIZE,''));result=ENGINE.run_engine_json(root)
            self.assertEqual(result['groups'][0]['overallStatus'],'FAIL')
            self.assertTrue({'Response Length Missing','Response Trigger Missing'} <= {i['validationType'] for i in result['issues']})

    def test_unresolved_and_special_source_types_do_not_receive_a_blanket_waiver(self):
        for datatype in ('BOOL','STRING[80]',None):
            with self.subTest(datatype=datatype),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);path=project(root);declaration=path.parent/'Variables.var'
                text=declaration.read_text(encoding='utf8')
                declaration.write_text(text.replace('Temp_nw_snd_buffer : ARRAY[0..49] OF USINT;',
                    f'Temp_nw_snd_buffer : ARRAY[0..49] OF {datatype};' if datatype else ''),encoding='utf8')
                result=ENGINE.run_engine_json(root)
                self.assertEqual(result['groups'][0]['overallStatus'],'FAIL')
                if datatype:self.assertNotIn('GC30 Fixed Bulk Copy',{i['validationType'] for i in result['issues']})
                else:self.assertIn('Variable Resolution',{i['validationType'] for i in result['issues']})

    def test_metadata_mismatch_still_fails_and_fault_byte_types_stay_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project(root);ENGINE.initialize_project_context(root)
            metadata=root/'metadata.xlsx';ENGINE.generate_metadata_workbook(metadata)
            book=load_workbook(metadata);sheet=book.worksheets[0]
            headers={c.value:c.column for c in sheet[1]}
            self.assertEqual(sheet.max_row,21)
            self.assertEqual([sheet.cell(r,headers['TAG_DATA_TYPE']).value for r in range(2,22)],['BYTE']*20)
            field='OFFSET_FROM_THE_START_OF_THE_GROUP_IN_BYTES'
            self.assertEqual([sheet.cell(r,headers[field]).value for r in range(2,22)],list(range(20)))
            sheet.cell(2,headers['TAG_DATA_TYPE'],'UINT');book.save(metadata);book.close()
            result=ENGINE.run_engine_json(root,metadata_file=metadata)
            self.assertEqual(result['groups'][0]['overallStatus'],'FAIL')
            self.assertTrue(any(i['severity']=='FAIL' and 'Type' in i['validationType'] for i in result['issues']))


if __name__=='__main__':unittest.main()
