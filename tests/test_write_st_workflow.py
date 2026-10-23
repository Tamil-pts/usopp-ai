"""The reported Project 1 analysis/review/generation flow, without PLC writes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app import app
from backend.core import accounts


class WriteSTWorkflowTests(unittest.TestCase):
    def test_project1_generation_reports_and_resolves_required_hmi_choice(self):
        project=Path(__file__).resolve().parents[2]/'project 1'
        if not project.is_dir():self.skipTest('Reference Project 1 is not installed.')
        with tempfile.TemporaryDirectory() as temporary,patch.object(accounts,'store',accounts.AccountStore(Path(temporary)/'accounts.sqlite3')):
            client=TestClient(app)
            try:
                self.assertEqual(200,client.post('/api/auth/login',json={'username':'Admin','password':'usopp.2026'}).status_code)
                body={'project_path':str(project)}
                discovery=client.post('/api/spinconnect/write-st/discover',json=body)
                self.assertEqual(200,discovery.status_code,discovery.text)
                response=client.post('/api/spinconnect/write-st/analyze',json=body)
                self.assertEqual(200,response.status_code,response.text)
                analysis=response.json();self.assertEqual('HMI',analysis['hmiTarget'])
                selected=[g for g in analysis['groups'] if g['code'] in (130,140)]
                unresolved=[f for g in selected for f in g['fields'] if f['writable'] and f['hmiOptions'] and not f['hmiId']]
                self.assertTrue(any(f['id']=='130:21' for f in unresolved))
                request={**body,'hmiTarget':analysis['hmiTarget'],'fingerprint':analysis['fingerprint'],'groups':[130,140],'reviewed':True}
                missing=client.post('/api/spinconnect/write-st/generate',json=request)
                self.assertEqual(400,missing.status_code)
                self.assertIn('choose an HMI control',missing.json()['detail'])
                # Explicit fixture choice, preserving the separate controls.
                # The UI asks the engineer which control applies to the target.
                request['fields']={f['id']:{'hmiId':f['hmiOptions'][0]['id']} for f in unresolved}
                generated=client.post('/api/spinconnect/write-st/generate',json=request)
                self.assertEqual(200,generated.status_code,generated.text[:400])
                output=generated.json();self.assertEqual([130,140],output['groups'])
                self.assertTrue(any(f['name']=='write_mapping.json' for f in output['files']))
                self.assertIn('IF NOT HMI_EN_Write THEN',output['files'][0]['text'])
                stale=client.post('/api/spinconnect/write-st/generate',json={**request,'fingerprint':'old'})
                self.assertEqual(409,stale.status_code)
            finally:client.close()


if __name__=='__main__':unittest.main()
