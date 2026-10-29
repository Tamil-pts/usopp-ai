import copy
import gc
import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import Workbook
from starlette.requests import Request

from backend.api import knowledge, metadata
from backend.core.metadata_parameter_mapping import resolve_parameter


OFFSET = 'OFFSET_FROM_THE_START_OF_THE_GROUP_IN_BYTES'
HEADERS = ['Parameters', 'GROUP_CODE', 'TAG_CODE', 'TAG_DATA_TYPE', OFFSET, 'MIN', 'MAX']


class MetadataParameterMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'metadata.xlsx'
        book = Workbook(); sheet = book.active; sheet.title = 'Metadata'
        sheet.append(HEADERS); sheet.append(['PLC Comment', 20, 52, 'UINT', 6, 0, 310])
        sheet2 = book.create_sheet('Sheet2'); sheet2.append(['TAG_CODE', 'PLCVAL', 'SHOWNVAL', 'MACHINE VARIANT', 'IS_ALARM'])
        sheet2.append([52, 0, 'Off', 'BOTH', 'NO'])
        book.save(self.path); book.close()
        self.sheets = metadata.read_sheets(self.path)
        self.master = self.root / 'parameter_mappings.json'
        self.write_master([])
        self.generated = {'sheetName': 'Metadata', 'machineDepartment': 'Carding', 'records': [
            {'plc_parameter': 'PLC Comment', 'plc_tag': 'Settings.Pulley', 'group_code': 20, 'tag_code': 52, 'offset': 6, 'datatype': 'UINT'}]}
        self.comparison = {'metadataSheet': 'Metadata', 'metadataRow': 2, 'metadataGroupCode': 20, 'metadataTagCode': 52,
                           'metadataOffset': 6, 'metadataType': 'UINT', 'groupCode': 20, 'plcOffset': 6,
                           'datatypeCompatibility': 'EXACT', 'plcTag': 'Settings.Pulley', 'logicComment': 'PLC Comment',
                           'logicSourceFile': 'Logical/mms_nw_r/Cyclic.st', 'logicLineNumber': 100}
        (self.root / 'inputs.json').write_text(json.dumps({'generated': str(self.path), 'uploaded': str(self.path), 'machineDepartment': 'Carding'}))
        self.write_results()
        self.payload = {'workbookPath': str(self.path), 'referenceSessionId': 'fixture', 'source': 'generated',
                        'sheetName': 'Metadata', 'rowNumber': 2, 'row': {**self.sheets[0]['rows'][0], 'Parameters': 'Motor pulley'}}
        self.request = Request({'type': 'http', 'state': {'user': {'id': 'fixture-user', 'role': 'user'}}})
        self.patches = [patch.object(knowledge, 'MASTER_PARAM_FILE', self.master),
                        patch.object(metadata, '_local_metadata_path', lambda _, raw: Path(raw)),
                        patch('backend.core.access.require_session', return_value=self.root)]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        gc.collect(); self.temp.cleanup()

    def write_master(self, rows):
        self.master.write_text(json.dumps({'version': '1.0', 'mappings': rows}), encoding='utf-8')

    def write_results(self):
        (self.root / 'generated_metadata.json').write_text(json.dumps(self.generated))
        (self.root / 'validation_results.json').write_text(json.dumps({'metadataComparison': {'results': [self.comparison]}}))

    def save(self, **changes):
        context = metadata.preview_parameter_mapping(self.payload, self.request)
        return metadata.save_parameter_mapping({**self.payload, 'revision': context['revision'], 'sourceRevision': context['sourceRevision'], 'metadataParameter': 'Motor pulley', **changes}, self.request)

    def test_preview_prefills_exact_source_and_never_writes(self):
        original_master, original_book = self.master.read_bytes(), self.path.read_bytes()
        context = metadata.preview_parameter_mapping(self.payload, self.request)
        self.assertEqual(('Settings.Pulley', 'PLC Comment', 'Carding'), tuple(context['mapping'][key] for key in ('plc_tag', 'plc_parameter', 'machine_department')))
        self.assertTrue(context['canSave'])
        self.assertEqual(original_master, self.master.read_bytes())
        self.assertEqual(original_book, self.path.read_bytes())

    def test_save_updates_existing_identity_preserving_limits_and_other_departments(self):
        row = {'plc_parameter': 'PLC Comment', 'plc_tag': 'Settings.Pulley', 'machine_department': 'Carding',
               'metadata_parameter': 'Old name', 'MIN': 0, 'MAX': 310, 'units': 'mm', 'scale_factor': 0.1, 'is_writable': 'YES'}
        global_row = {**row, 'machine_department': 'All'}
        other = {**row, 'plc_tag': 'Settings.Other'}
        self.write_master([row, global_row, other]); original_book = self.path.read_bytes()
        self.save(); self.save()  # Repeated confirmation cannot append duplicate mappings.
        rows = json.loads(self.master.read_text())['mappings']
        self.assertEqual([{**row, 'metadata_parameter': 'Motor pulley', 'status': 'configured'}, global_row, other], rows)
        self.assertEqual(original_book, self.path.read_bytes())

    def test_new_mapping_is_used_by_generator_only_for_same_tag_comment_and_department(self):
        self.save()
        # Load the existing v1.71 engine unchanged and verify its generation contract.
        spec = importlib.util.spec_from_file_location('metadata_rename_engine_contract', Path(__file__).resolve().parents[1] / 'python_engine' / 'packet_validation_report_uSOPp_v1.71_final.py')
        ENGINE = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = ENGINE
        spec.loader.exec_module(ENGINE)
        with patch.object(ENGINE, 'KNOWLEDGE_MASTER_FILE', self.master), patch.object(ENGINE, 'ACTIVE_MACHINE_DEPARTMENT', 'Carding'):
            self.assertEqual('Motor pulley', ENGINE.generated_metadata_parameter('PLC Comment', 'Settings.Pulley')[0])
            self.assertNotEqual('Motor pulley', ENGINE.generated_metadata_parameter('Other comment', 'Settings.Pulley')[0])
            self.assertNotEqual('Motor pulley', ENGINE.generated_metadata_parameter('PLC Comment', 'Settings.Other')[0])
        with patch.object(ENGINE, 'KNOWLEDGE_MASTER_FILE', self.master), patch.object(ENGINE, 'ACTIVE_MACHINE_DEPARTMENT', 'Ringframe'):
            self.assertNotEqual('Motor pulley', ENGINE.generated_metadata_parameter('PLC Comment', 'Settings.Pulley')[0])

    def test_department_mapping_retains_inherited_settings_without_modifying_shared_rule(self):
        shared = {'plc_parameter': 'PLC Comment', 'plc_tag': 'Settings.Pulley', 'machine_department': 'All',
                  'metadata_parameter': 'Shared name', 'units': 'rpm', 'MIN': 0, 'MAX': 100, 'scale_factor': 0.1, 'is_writable': 'YES'}
        self.write_master([shared]); self.save()
        rows = json.loads(self.master.read_text())['mappings']
        self.assertEqual(shared, rows[0])
        self.assertEqual({**shared, 'machine_department': 'Carding', 'metadata_parameter': 'Motor pulley', 'status': 'configured'}, rows[1])

    def test_uploaded_metadata_resolves_by_verified_row_and_packet_identity(self):
        self.payload['source'] = 'uploaded'
        context = metadata.preview_parameter_mapping(self.payload, self.request)
        self.assertEqual('Settings.Pulley', context['mapping']['plc_tag'])
        self.assertEqual(100, context['mapping']['lineNumber'])
        self.save()
        self.assertEqual('Motor pulley', json.loads(self.master.read_text())['mappings'][0]['metadata_parameter'])

    def test_mismatched_uploaded_offset_type_or_ambiguous_source_cannot_be_shared(self):
        self.payload['source'] = 'uploaded'
        for change in ({'plcOffset': 8}, {'datatypeCompatibility': 'MISMATCH'}, {'groupCode': 30}):
            with self.subTest(change=change):
                original = copy.deepcopy(self.comparison); self.comparison.update(change); self.write_results()
                with self.assertRaises(HTTPException): self.save()
                self.comparison = original
        self.write_results()
        result = {'metadataComparison': {'results': [self.comparison, {**self.comparison, 'plcTag': 'OtherTag'}]}}
        (self.root / 'validation_results.json').write_text(json.dumps(result))
        with self.assertRaises(HTTPException): self.save()
        self.assertEqual([], json.loads(self.master.read_text())['mappings'])

    def test_context_checks_workbook_session_ownership_and_original_path(self):
        with patch('backend.core.access.require_session', side_effect=HTTPException(403, 'Other user')):
            with self.assertRaises(HTTPException) as caught: metadata.preview_parameter_mapping(self.payload, self.request)
        self.assertEqual(403, caught.exception.status_code)
        (self.root / 'inputs.json').write_text(json.dumps({'generated': str(self.root / 'other.xlsx'), 'machineDepartment': 'Carding'}))
        with self.assertRaises(HTTPException): self.save()

    def test_changed_numeric_identity_or_sheet2_never_becomes_a_mapping(self):
        for field, value in [('GROUP_CODE', 30), ('TAG_CODE', 53), (OFFSET, 8), ('TAG_DATA_TYPE', 'REAL')]:
            with self.subTest(field=field):
                payload = copy.deepcopy(self.payload); payload['row'][field] = value
                with self.assertRaises(HTTPException): resolve_parameter(payload, self.path, self.sheets, self.root)
        with self.assertRaises(HTTPException): resolve_parameter({**self.payload, 'sheetName': 'Sheet2'}, self.path, self.sheets, self.root)

    def test_missing_reference_remains_edit_only(self):
        with self.assertRaises(HTTPException) as caught:
            metadata.preview_parameter_mapping({**self.payload, 'referenceSessionId': ''}, self.request)
        self.assertEqual(400, caught.exception.status_code)
        self.assertEqual([], json.loads(self.master.read_text())['mappings'])

    def test_stale_revision_duplicate_master_and_demo_save_leave_master_unchanged(self):
        context = metadata.preview_parameter_mapping(self.payload, self.request)
        original = self.master.read_bytes()
        with self.assertRaises(HTTPException) as caught:
            metadata.save_parameter_mapping({**self.payload, 'metadataParameter': 'Name', 'revision': 'stale', 'sourceRevision': context['sourceRevision']}, self.request)
        self.assertEqual(409, caught.exception.status_code)
        demo = Request({'type': 'http', 'state': {'user': {'id': 'demo', 'isDemo': True}}})
        self.assertFalse(metadata.preview_parameter_mapping(self.payload, demo)['canSave'])
        with self.assertRaises(HTTPException) as caught:
            metadata.save_parameter_mapping({**self.payload, 'metadataParameter': 'Name', 'revision': context['revision']}, demo)
        self.assertEqual(403, caught.exception.status_code)
        self.assertEqual(original, self.master.read_bytes())
        row = {'plc_parameter': 'PLC Comment', 'plc_tag': 'Settings.Pulley', 'machine_department': 'Carding', 'metadata_parameter': 'Old'}
        self.write_master([row, {**row, 'metadata_parameter': 'Conflicting'}])
        with self.assertRaises(HTTPException): self.save()

    def test_changed_plc_source_requires_new_preview_and_consent(self):
        context = metadata.preview_parameter_mapping(self.payload, self.request)
        self.generated['records'][0]['plc_tag'] = 'OtherTag'
        self.write_results()
        with self.assertRaises(HTTPException) as caught:
            metadata.save_parameter_mapping({**self.payload, 'metadataParameter': 'Name', 'revision': context['revision'], 'sourceRevision': context['sourceRevision']}, self.request)
        self.assertEqual(409, caught.exception.status_code)
        self.assertEqual([], json.loads(self.master.read_text())['mappings'])

    def test_workbook_save_keeps_all_columns_rows_sheet2_and_unedited_values(self):
        before = copy.deepcopy(self.sheets)
        self.sheets[0]['rows'][0]['Parameters'] = 'Motor pulley'
        with patch.object(metadata, 'EXPORTS', self.root), patch.object(metadata, '_local_session', return_value=('copy', self.root)), patch('backend.core.access.claim_resource'):
            (self.root / 'metadata').mkdir()
            saved = metadata.save_copy({**self.payload, 'sheets': self.sheets})
        after = metadata.read_sheets(Path(saved['workbookPath']))
        before[0]['rows'][0]['Parameters'] = 'Motor pulley'
        self.assertEqual(before, after)
        self.assertEqual('PLC Comment', metadata.read_sheets(self.path)[0]['rows'][0]['Parameters'])


if __name__ == '__main__':
    unittest.main()
