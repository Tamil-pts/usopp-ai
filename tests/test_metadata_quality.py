import copy
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from python_engine.metadata_quality import inspect_workbook, source_fields, wire_size

OFFSET = 'OFFSET_FROM_THE_START_OF_THE_GROUP_IN_BYTES'
HEADERS = ['Parameters', 'GROUP_CODE', 'TAG_CODE', 'TAG_DATA_TYPE', OFFSET, 'Machine Varients', 'IS_SHOWN_VALUE_DIFFERENT']


def sheets(offsets=(0, 2, 3)):
    records = [('Product code', 'UINT'), ('Alarm byte', 'BYTE'), ('Alarm count', 'UDINT')]
    return [{'name': 'Metadata', 'headers': HEADERS, 'rows': [
        dict(zip(HEADERS, [name, 30, index, dtype, offset, 'BOTH', 'NO']))
        for index, ((name, dtype), offset) in enumerate(zip(records, offsets), 1)]}]


def reference():
    return [{'sheet': 'Metadata', 'row': index + 2, 'groupCode': 30,
             'offset': offset, 'size': size, 'dataType': dtype}
            for index, (offset, size, dtype) in enumerate([(0, 2, 'UINT'), (2, 1, 'BYTE'), (3, 4, 'UDINT')])]


class MetadataQualityTests(unittest.TestCase):
    def test_sizes_reuse_packet_contract(self):
        self.assertEqual([1, 2, 4, 8, 50, 6], [wire_size(value) for value in ['BYTE', 'UINT', 'REAL', 'LREAL', 'STRING[10]', 'ARRAY[0..2] OF UINT']])
        self.assertIsNone(wire_size('VendorStructure'))

    def test_valid_gc30_offsets_and_source_payload_zero(self):
        result = inspect_workbook(sheets(), reference())
        self.assertEqual('PASS', result['stages'][0]['status'])
        self.assertEqual([0, 2, 3], [row['sourceOffset'] for row in result['offsetRows']])
        self.assertEqual([[0], [2], [3]], [row['expectedOffsets'] for row in result['offsetRows']])

    def test_no_source_comparison_does_not_claim_pass(self):
        result = inspect_workbook(sheets())['stages'][0]
        self.assertEqual(('REVIEW', 'PASS', False), (result['status'], result['workbookStatus'], result['sourceCompared']))

    def test_gap_overlap_and_original_data_are_preserved(self):
        data = sheets((0, 4, 1)); original = copy.deepcopy(data)
        result = inspect_workbook(data, reference())
        checks = {issue['check'] for issue in result['stages'][0]['issues']}
        self.assertTrue({'Offset gap', 'Offset overlap', 'PLC byte offset mismatch'} <= checks)
        self.assertEqual(data, original)
        self.assertEqual(['PASS', 'FAIL', 'FAIL'], [row['status'] for row in result['offsetRows']])

    def test_invalid_fraction_negative_and_missing_offsets(self):
        result = inspect_workbook(sheets((-1, 1.5, '')))
        self.assertEqual(3, sum(issue['check'] == 'Invalid byte offset' for issue in result['stages'][0]['issues']))

    def test_plc_size_and_type_change_is_reported(self):
        data = sheets(); data[0]['rows'][0]['TAG_DATA_TYPE'] = 'BYTE'
        checks = {issue['check'] for issue in inspect_workbook(data, reference())['stages'][0]['issues']}
        self.assertTrue({'PLC field size mismatch', 'PLC datatype mismatch'} <= checks)

    def test_variants_and_groups_keep_separate_cursors(self):
        data = sheets(); data[0]['rows'] = [
            dict(zip(HEADERS, ['Shared', 20, 1, 'BYTE', 0, 'BOTH', 'NO'])),
            dict(zip(HEADERS, ['A value', 20, 2, 'REAL', 1, 'A', 'NO'])),
            dict(zip(HEADERS, ['B value', 20, 3, 'UINT', 1, 'B', 'NO'])),
            dict(zip(HEADERS, ['Other group', 30, 4, 'UINT', 0, 'BOTH', 'NO'])),
        ]
        self.assertEqual('PASS', inspect_workbook(data)['stages'][0]['workbookStatus'])

    def test_sheet2_zero_value_and_target_overrides_are_valid(self):
        data = sheets(); data[0]['rows'][0]['IS_SHOWN_VALUE_DIFFERENT'] = 'YES'
        data.append({'name': 'Sheet2', 'headers': ['TAG_CODE', 'PLCVAL', 'SHOWNVAL', 'MACHINE VARIANT'], 'rows': [
            {'TAG_CODE': 1, 'PLCVAL': 0, 'SHOWNVAL': 'OFF', 'MACHINE VARIANT': 'BOTH'},
            {'TAG_CODE': 1, 'PLCVAL': 0, 'SHOWNVAL': 'Inactive', 'MACHINE VARIANT': 'C70'},
        ]})
        self.assertEqual('PASS', inspect_workbook(data)['stages'][1]['status'])
        data[1]['rows'].append(dict(data[1]['rows'][0]))
        self.assertEqual('FAIL', inspect_workbook(data)['stages'][1]['status'])

    def test_sheet2_missing_and_orphan_mappings(self):
        data = sheets(); data[0]['rows'][0]['IS_SHOWN_VALUE_DIFFERENT'] = 'YES'
        self.assertEqual('Missing Sheet2 mapping', inspect_workbook(data)['stages'][1]['issues'][0]['check'])
        data.append({'name': 'Sheet2', 'headers': ['TAG_CODE', 'PLCVAL', 'SHOWNVAL'], 'rows': [{'TAG_CODE': 99, 'PLCVAL': 0, 'SHOWNVAL': 'OFF'}]})
        self.assertIn('Orphan Sheet2 tag', {issue['check'] for issue in inspect_workbook(data)['stages'][1]['issues']})

    def test_sheet2_shared_variant_aliases_cannot_hide_collisions(self):
        data=sheets()
        data.append({'name':'Sheet2','headers':['TAG_CODE','PLCVAL','SHOWNVAL','MACHINE VARIANT'],'rows':[
            {'TAG_CODE':1,'PLCVAL':0,'SHOWNVAL':'OFF','MACHINE VARIANT':'BOTH'},
            {'TAG_CODE':1,'PLCVAL':0,'SHOWNVAL':'Inactive','MACHINE VARIANT':'ALL'},
        ]})
        self.assertEqual('FAIL',inspect_workbook(data)['stages'][1]['status'])

    def test_duplicate_names_are_group_scoped(self):
        data = sheets(); data[0]['rows'].append({**data[0]['rows'][0], 'Parameters': ' product CODE '})
        self.assertEqual(2, len(inspect_workbook(data)['stages'][2]['issues']))
        data[0]['rows'][-1]['GROUP_CODE'] = 40
        self.assertEqual('PASS', inspect_workbook(data)['stages'][2]['status'])

    def test_uploaded_source_offsets_remain_payload_relative(self):
        result = source_fields({'metadataComparison': {'results': [{'metadataSheet': 'Metadata', 'metadataRow': 2, 'plcOffset': 0, 'plcSize': 2, 'groupCode': 30}]}}, 'uploaded')
        self.assertEqual(0, result[0]['offset'])

    def test_export_adds_highlights_without_changing_any_cells_or_shape(self):
        from backend.api import metadata as api
        with TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'input.xlsx'; export = root / 'exports'
            (export / 'metadata').mkdir(parents=True)
            data = sheets((0, 4, 3)); book = Workbook(); ws = book.active; ws.title = 'Metadata'
            ws.append(HEADERS)
            for row in data[0]['rows']:ws.append([row[key] for key in HEADERS])
            expected = list(ws.values); book.save(path); book.close()
            with patch.object(api, 'resolve_workbook', return_value=path), patch.object(api, 'EXPORTS', export), patch.object(api, '_local_session', return_value=('qualitytest', root)), patch('backend.core.identifiers.run_identity', return_value='fixture'):
                output = api.save_copy({'workbookPath': str(path), 'sheets': data, 'projectName': 'fixture'})
            saved = load_workbook(io.BytesIO(Path(output['workbookPath']).read_bytes()))
            try:
                self.assertEqual(expected, list(saved['Metadata'].values))
                rules = [rule for values in saved['Metadata'].conditional_formatting._cf_rules.values() for rule in values]
                self.assertTrue(any(api.OFFSET_FORMULA in (rule.formula or []) for rule in rules))
            finally:saved.close()

    def test_readiness_requires_source_and_data_model(self):
        from backend.api import metadata as api
        from backend.core.data_models import parse_model
        import json
        model = parse_model(json.dumps({'controleCode': 'CARDING', 'keysList': {'module': [{'tagName': 'Product code', 'dataType': 'UINT', 'groupCode': '30'}]}}).encode(), 'CARDING.json', 'PMS')
        payload = {'sheets': sheets(), 'modelId': model['id'], 'machineDepartment': 'Carding'}
        with patch.object(api, 'quality_reference', return_value=reference()), patch('backend.api.data_models.model_for', return_value=model):
            self.assertTrue(api.workbook_quality(payload, Path('input.xlsx'))['ready'])
            self.assertFalse(api.workbook_quality({'sheets': sheets()}, Path('input.xlsx'))['ready'])

    def test_department_required_before_files_are_processed(self):
        from backend.api import validation as api
        for department in (None, '', 'All', ' all '):
            with self.subTest(department=department), patch.object(api, '_local_path', side_effect=AssertionError('must not read project')):
                with self.assertRaises(HTTPException) as error:api.local_validate({'machine_department': department})
                self.assertEqual(400, error.exception.status_code)
                with self.assertRaises(HTTPException):api.local_generate_metadata({'machine_department': department})
        self.assertEqual('Carding', api._machine_department(' Carding '))


if __name__ == '__main__':
    unittest.main()
