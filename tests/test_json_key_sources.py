"""All-source views retain the original JSON records and existing access rules."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request
from backend.core import data_model_json_keys as keys
from backend.api.data_models import get_all_json_key_sources


class JsonKeySourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.enterContext(patch.object(keys, '_data_root', return_value=self.root))
        original = self.root / 'reference_sources' / 'PMS' / 'Carding.json'
        original.parent.mkdir(parents=True)
        self.original = original
        self.record = {'tagName': 'Shift Number', 'dataType': 'FLOAT', 'groupCode': '40',
                       'tdEngineKey': 'shift_number', 'mongoKey': 'shift_id', 'isRequired': True,
                       'formula': None, 'type': 'instant', 'numericValueType': True}
        original.write_text(json.dumps({'keysList': {
            'pms_CARDING_shift': [self.record], 'qms_CARDING_live': [dict(self.record, tagName='CVM%')],
            'cms_OTHER_hidden': [dict(self.record, tagName='Not an installed model')],
        }}), encoding='utf-8')
        entries = [dict(service=service, department='CARDING', originalSource='PMS/Carding.json', file=service+'.json')
                   for service in ['PMS', 'QMS']]
        (self.root / 'source_manifest.json').write_text(json.dumps({'fixedModels': entries}), encoding='utf-8')

    def request(self, user=None):
        return Request({'type': 'http', 'state': {'user': user}})

    def test_all_sources_keep_service_scope_and_original_fields(self):
        before = hashlib.sha256(self.original.read_bytes()).hexdigest()
        sources = keys.get_sources()
        self.assertEqual(['PMS:CARDING', 'QMS:CARDING'], [source['id'] for source in sources])
        self.assertEqual({'pms_CARDING_shift'}, set(sources[0]['collections']))
        self.assertEqual({'qms_CARDING_live'}, set(sources[1]['collections']))
        self.assertEqual(self.record, sources[0]['collections']['pms_CARDING_shift'][0])
        self.assertEqual([1, 1], [source['parameterCount'] for source in sources])
        self.assertEqual(before, hashlib.sha256(self.original.read_bytes()).hexdigest())

    def test_all_source_endpoint_preserves_user_and_admin_permissions(self):
        for role in ['user', 'admin']:
            with self.subTest(role=role):
                response = get_all_json_key_sources(self.request({'role': role, 'id': 'test'}))
                self.assertEqual(role == 'admin', response['canEdit'])
                self.assertEqual(2, len(response['sources']))
        with self.assertRaises(HTTPException) as error:
            get_all_json_key_sources(self.request())
        self.assertEqual(401, error.exception.status_code)

    def test_missing_source_fails_instead_of_returning_a_partial_export(self):
        self.original.unlink()
        with self.assertRaises(HTTPException) as error:
            get_all_json_key_sources(self.request({'role': 'user'}))
        self.assertEqual(503, error.exception.status_code)


if __name__ == '__main__':
    unittest.main()
