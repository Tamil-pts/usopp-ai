import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app import app
from backend.core.build_info import frontend_build_info


class BuildVersionTests(unittest.TestCase):
    def test_frontend_manifest_checks_version_hash_and_asset_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'assets').mkdir();asset=root/'assets/app.js';asset.write_bytes(b'compiled UI')
            doc={'version':'1.2.3','entryFile':'assets/app.js','entrySha256':hashlib.sha256(asset.read_bytes()).hexdigest()}
            manifest=root/'build-info.json';manifest.write_text(json.dumps(doc))
            self.assertTrue(frontend_build_info(root,'1.2.3')['matches'])
            self.assertFalse(frontend_build_info(root,'1.2.4')['matches'])
            asset.write_bytes(b'old UI');self.assertFalse(frontend_build_info(root,'1.2.3')['integrity'])
            doc['entryFile']='../outside.js';manifest.write_text(json.dumps(doc))
            self.assertFalse(frontend_build_info(root,'1.2.3')['integrity'])

    def test_health_fails_mismatched_container_ui_and_is_never_cached(self):
        bad={'version':'old','matches':False,'integrity':True,'error':'Rebuild the interface.'}
        with patch.dict('os.environ',{'USOPP_REQUIRE_FRONTEND_BUILD':'1'}),patch('backend.api.system.frontend_build_info',return_value=bad):
            client=TestClient(app)
            try:
                response=client.get('/api/health')
                self.assertEqual(503,response.status_code)
                self.assertEqual('version-mismatch',response.json()['status'])
                self.assertEqual('no-store',response.headers['cache-control'])
            finally:client.close()


if __name__=='__main__':unittest.main()
