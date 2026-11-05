import gc
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from openpyxl import load_workbook
from fastapi import HTTPException
from tests.test_source_parsing import ENGINE
from tests.test_sheet2_variants import write_project,SYMBOLS,SHEET2_HEADERS


class RequiredSheet2Tests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup);self.addCleanup(gc.collect)
        self.root=Path(self.directory.name)
        for key,value in {'KNOWLEDGE_MASTER_FILE':self.root/'none.json','KNOWLEDGE_MASTER_DROPDOWN_FILE':self.root/'none-dropdowns.json',
                          'BOOL_METADATA_MODE':'BOOL','ACTIVE_MACHINE_DEPARTMENT':'All'}.items():
            self.enterContext(patch.object(ENGINE,key,value))

    def setup_project(self):
        write_project(self.root,{'C70_7':{SYMBOLS[0]:{0:'Disabled',1:'Enabled'},SYMBOLS[1]:{0:'Absent',1:'Present'}}})
        ENGINE.initialize_project_context(self.root)

    def test_repeated_source_variable_has_sheet2_for_tag_653(self):
        self.setup_project();task=self.root/'Logical/SpinConnect/mms_nw_r'
        var=task/'mms_nw_r.var';var.write_text(var.read_text().replace('END_VAR','padding : ARRAY[0..649] OF BYTE;\nEND_VAR'))
        source=task/'Cyclic.st';text=source.read_text().replace('nw_snd_buffer[3] := 0','nw_snd_buffer[3] := 2').replace('nw_snd_buffer[4] := 3','nw_snd_buffer[4] := 141')
        text=text.replace('nw_i := 5;', 'nw_i := 5;\nmemcpy(ADR(nw_snd_buffer[nw_i]),ADR(padding[0]),650);\nnw_i := nw_i + 650;')
        text=text.replace(f'ADR({SYMBOLS[2]})',f'ADR({SYMBOLS[0]})')
        source.write_text(text);ENGINE.initialize_project_context(self.root)
        out=self.root/'generated.xlsx';data=ENGINE.generate_metadata_workbook(out)
        row=next(row for row in data['records'] if row['tag_code']==653)
        self.assertEqual(row['plc_tag'],SYMBOLS[0]);self.assertEqual(row['is_shown_value_different'],'YES')
        for tag in (651,653):
            pairs={(str(r['PLCVAL']),r['SHOWNVAL']) for r in data['sheet2Records'] if r['TAG_CODE']==tag}
            self.assertEqual(pairs,{('0','Disabled'),('1','Enabled')})
        wb=load_workbook(io.BytesIO(out.read_bytes()),read_only=True,data_only=True)
        try:self.assertEqual(list(next(wb['Sheet2'].values)),SHEET2_HEADERS)
        finally:wb.close()

    def test_missing_source_mapping_prevents_publication_and_preserves_old_workbook(self):
        self.setup_project();out=self.root/'generated.xlsx';ENGINE.generate_metadata_workbook(out);before=out.read_bytes()
        with patch.object(ENGINE,'_build_generated_sheet2',return_value=[SHEET2_HEADERS]):
            with self.assertRaisesRegex(ValueError,'Missing Sheet2 reference: TAG_CODE 1'):
                ENGINE.generate_metadata_workbook(out,self.root/'should-not-publish.json')
        self.assertEqual(out.read_bytes(),before);self.assertFalse((self.root/'should-not-publish.json').exists())

    def test_equal_caption_does_not_map_an_unrelated_plc_variable(self):
        self.setup_project();path=self.root/'Logical/SpinConnect/mms_nw_r/Cyclic.st'
        path.write_text(path.read_text().replace(f'(*{SYMBOLS[2]}*)',f'(*{SYMBOLS[0]}*)'))
        ENGINE.initialize_project_context(self.root);data=ENGINE.generate_metadata_workbook(self.root/'generated.xlsx')
        self.assertNotEqual(data['records'][2]['is_shown_value_different'],'YES')
        self.assertFalse(any(row['TAG_CODE']==3 for row in data['sheet2Records']))

    def test_validator_fails_when_required_reference_is_deleted(self):
        self.setup_project();out=self.root/'generated.xlsx';ENGINE.generate_metadata_workbook(out)
        book=load_workbook(io.BytesIO(out.read_bytes()));sheet=book['Sheet2']
        for row in range(sheet.max_row,1,-1):
            if sheet.cell(row,1).value==1:sheet.delete_rows(row)
        book.save(out);book.close()
        report=ENGINE.run_engine_json(self.root,metadata_file=out,output_excel_path=self.root/'validation.xlsx')
        self.assertEqual(report['groups'][0]['overallStatus'],'FAIL');self.assertGreater(report['summary']['failed'],0)
        issue=next(issue for issue in report['issues'] if issue['validationType']=='Sheet2 Reference Missing')
        self.assertIn('TAG_CODE 1',issue['expected']);self.assertIn('Missing Sheet2 reference',issue['suggestedFix'])

    def test_export_rejects_missing_reference_even_for_partial_sheet_payload(self):
        from backend.api import metadata as api
        self.setup_project();out=self.root/'generated.xlsx';ENGINE.generate_metadata_workbook(out)
        book=load_workbook(io.BytesIO(out.read_bytes()));sheet=book['Sheet2']
        for row in range(sheet.max_row,1,-1):
            if sheet.cell(row,1).value==1:sheet.delete_rows(row)
        book.save(out);book.close();before=out.read_bytes()
        with patch.object(api,'resolve_workbook',return_value=out):
            with self.assertRaises(HTTPException) as caught:
                api.save_copy({'sheetName':'Sheet2','headers':[],'rows':[],'workbookPath':str(out)})
        self.assertEqual(caught.exception.status_code,422);self.assertIn('TAG_CODE 1',caught.exception.detail)
        self.assertEqual(out.read_bytes(),before)


if __name__=='__main__':unittest.main()
