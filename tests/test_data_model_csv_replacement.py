"""An authoritative CSV replaces active keys without resurrecting supplements."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.core import data_model_json_keys as keys
from scripts.replace_data_model_json_keys import build_plan, apply_plan, parse_shortlist


class DataModelCsvReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root/'knowledge'/'data_models'
        source = self.output/'reference_sources'/'old.json'
        source.parent.mkdir(parents=True)
        old = {'tagName': 'Deleted parameter', 'dataType': 'FLOAT', 'groupCode': '40',
               'excelReference': {'source': 'old.xlsx', 'row': 2}}
        source.write_text(json.dumps({'controleCode': 'CARDING', 'keysList': {
            'pms_CARDING_shift': [old], 'cms_CARDING_shift': [old]}}), encoding='utf-8')
        fixed = [{'service': service, 'department': 'CARDING', 'originalSource': 'old.json',
                  'file': service+'/CARDING.json'} for service in ['PMS', 'CMS']]
        (self.output/'source_manifest.json').write_text(json.dumps({'schemaVersion': 1, 'fixedModels': fixed}))
        models = [{'service': service, 'machine': 'CARDING', 'id': service+'-stable-id',
                   'parameters': [dict(old, referenceOrigin='workbook-supplement')]} for service in ['PMS', 'CMS']]
        (self.output/'catalog.json').write_text(json.dumps({'models': models}))
        (self.output/'legacy_catalog.json').write_text('{"legacy":"must remain only in backup"}')
        self.csv = self.root/'shortlist.csv'
        text = io.StringIO(newline='')
        writer = csv.writer(text)
        writer.writerow(['Service', 'Department', 'JSON collection', 'tagName', 'dataType',
                         'groupCode', 'tdEngineKey', 'mongoKey', 'formula', 'type', 'isRequired', 'precision'])
        writer.writerow(['PMS', 'CARDING', 'pms_CARDING_shift', 'Speed', 'FLOAT', '40',
                         'delivery_speed', 'speed', '', 'instant', 'FALSE', 'COL005ID'])
        writer.writerow(['PMS', 'CARDING', 'pms_CARDING_shift', 'Calculated, total', 'FLOAT', 'formula',
                         '', 'total', 'a + b', 'aggregate', 'TRUE', ''])
        writer.writerow(['CMS', 'CARDING', 'cms_CARDING_shift', 'Count', 'UINT', '40H',
                         'count', '', '', 'instant', 'TRUE', ''])
        self.csv.write_text(text.getvalue(), encoding='utf-8')

    def test_preview_is_read_only_and_preserves_csv_values_and_flags(self):
        before = {p.relative_to(self.output): p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        plan = build_plan(self.csv, self.output)
        self.assertEqual(3, plan['summary']['rows'])
        self.assertEqual(2, plan['summary']['previousSourceRows'])
        self.assertEqual(before, {p.relative_to(self.output): p.read_bytes() for p in self.output.rglob('*') if p.is_file()})
        model = json.loads(plan['files']['PMS/CARDING.json'])
        records = model['keysList']['pms_CARDING_shift']
        self.assertIs(records[0]['isRequired'], False)
        self.assertIsNone(records[0]['formula'])
        self.assertEqual('COL005ID', records[0]['precision'])
        self.assertEqual('Calculated, total', records[1]['tagName'])
        self.assertEqual('a + b', records[1]['formula'])
        self.assertNotIn('Service', records[0])
        self.assertEqual('40H', json.loads(plan['files']['CMS/CARDING.json'])['keysList']['cms_CARDING_shift'][0]['groupCode'])

    def test_apply_keeps_ids_and_backup_and_removes_all_old_active_definitions(self):
        old_bytes = (self.output/'reference_sources'/'old.json').read_bytes()
        plan = build_plan(self.csv, self.output)
        backup = apply_plan(plan, self.output, self.root/'backups')
        self.assertEqual(old_bytes, (backup/'previous_data_models'/'reference_sources'/'old.json').read_bytes())
        self.assertTrue((backup/'previous_data_models'/'legacy_catalog.json').is_file())
        self.assertFalse((self.output/'legacy_catalog.json').exists())
        self.assertFalse((self.output/'reference_sources'/'old.json').exists())
        self.assertEqual(self.csv.read_bytes(), (self.output/'reference_sources'/'shortlist.csv').read_bytes())
        catalog = json.loads((self.output/'catalog.json').read_text())
        self.assertEqual(['PMS-stable-id', 'CMS-stable-id'], [model['id'] for model in catalog['models']])
        self.assertEqual(3, sum(len(model['parameters']) for model in catalog['models']))
        self.assertNotIn('Deleted parameter', (self.output/'catalog.json').read_text())
        self.assertNotIn('workbook-supplement', (self.output/'catalog.json').read_text())
        with patch.object(keys, '_data_root', return_value=self.output):
            sources = keys.get_sources()
            self.assertEqual(3, sum(source['parameterCount'] for source in sources))
            source = keys.get_source('PMS:CARDING')
            changed = dict(source['collections'])
            changed['pms_CARDING_shift'] = changed['pms_CARDING_shift'][:1]
            keys.save_source('PMS:CARDING', {'revision': source['revision'], 'collections': changed})
            # Editing one collection after replacement must not revive deleted
            # workbook parameters or lose the other service in the shared file.
            self.assertEqual(2, sum(source['parameterCount'] for source in keys.get_sources()))
            self.assertEqual(2, sum(len(model['parameters']) for model in json.loads((self.output/'catalog.json').read_text())['models']))

    def test_invalid_scope_and_empty_shortlist_do_not_change_active_data(self):
        raw = self.csv.read_bytes()
        with self.assertRaisesRegex(ValueError, 'collection must begin'):
            parse_shortlist(raw.replace(b'pms_CARDING_shift', b'pms_OTHER_shift'))
        with self.assertRaisesRegex(ValueError, 'no records'):
            parse_shortlist(raw.splitlines()[0]+b'\n')
        self.assertTrue((self.output/'reference_sources'/'old.json').is_file())

    def test_failed_directory_cutover_restores_the_original_dataset(self):
        plan = build_plan(self.csv, self.output)
        before = (self.output/'catalog.json').read_bytes()
        rename = Path.rename
        def reject_stage(path, target):
            if path.name.startswith('.data_models_stage_'):
                raise OSError('Simulated cutover failure')
            return rename(path, target)
        with patch.object(Path, 'rename', reject_stage), self.assertRaisesRegex(OSError, 'cutover failure'):
            apply_plan(plan, self.output, self.root/'backups')
        self.assertEqual(before, (self.output/'catalog.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
