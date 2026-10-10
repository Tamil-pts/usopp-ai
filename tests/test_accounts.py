import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import threading
from fastapi.testclient import TestClient
from backend.app import app
from backend.core import accounts

class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=accounts.AccountStore(Path(self.temp.name)/'accounts.sqlite3')
        self.override=patch.object(accounts,'store',self.store)
        self.override.start()
        self.client=TestClient(app)

    def tearDown(self):
        self.client.close();self.override.stop();self.temp.cleanup()

    def register(self,username='engineer'):
        return self.client.post('/api/auth/register',json={'username':username,'password':'Test.pass.2026','designation':'PLC Engineer','company':'Test Company','role':'admin'})

    def test_login_required_for_all_engineering_apis(self):
        for path in ['/api/nami/health','/api/local/browse','/api/rules/features','/api/auth/password']:
            self.assertEqual(self.client.get(path).status_code,401)
        self.assertEqual(self.client.get('/api/health').status_code,200)
        self.assertIsNone(self.client.get('/api/auth/session').json()['user'])

    def test_admin_login_and_logout(self):
        response=self.client.post('/api/auth/login',json={'username':'Admin','password':'usopp.2026'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['user']['role'],'admin')
        self.assertIn('HttpOnly',response.headers['set-cookie'])
        self.assertIn('SameSite=lax',response.headers['set-cookie'])
        self.assertEqual(self.client.get('/api/nami/health').status_code,200)
        self.client.post('/api/auth/logout')
        self.assertEqual(self.client.get('/api/nami/health').status_code,401)

    def test_registration_fields_duplicate_and_hash(self):
        response=self.register()
        self.assertEqual(response.status_code,200)
        user=response.json()['user']
        self.assertEqual(user['role'],'user')
        self.assertEqual(user['designation'],'PLC Engineer')
        self.assertEqual(user['company'],'Test Company')
        self.assertNotIn('password_hash',user)
        self.assertEqual(self.register('ENGINEER').status_code,409)
        with self.store.db() as db:
            password=db.execute("SELECT password_hash FROM users WHERE username_key='engineer'").fetchone()[0]
            self.assertNotIn('Test.pass.2026',password)
            self.assertTrue(accounts.password_matches('Test.pass.2026',password))

    def test_password_change_revokes_other_sessions_and_persists(self):
        self.register()
        other=TestClient(app)
        other.post('/api/auth/login',json={'username':'engineer','password':'Test.pass.2026'})
        self.assertEqual(self.client.post('/api/auth/password',json={'currentPassword':'wrong','newPassword':'Changed.pass.2026'}).status_code,403)
        result=self.client.post('/api/auth/password',json={'currentPassword':'Test.pass.2026','newPassword':'Changed.pass.2026'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.get('/api/nami/health').status_code,200)
        self.assertEqual(other.get('/api/nami/health').status_code,401)
        other.close()
        reopened=accounts.AccountStore(self.store.path)
        self.assertIsNotNone(reopened.login('engineer','Changed.pass.2026','test')[0])
        self.assertIsNone(reopened.login('engineer','Test.pass.2026','test')[0])

    def test_cross_origin_and_invalid_credentials(self):
        self.assertEqual(self.client.post('/api/auth/register',headers={'Origin':'http://untrusted.example'},json={}).status_code,403)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'Admin','password':'wrong'}).status_code,401)
        self.assertEqual(self.client.post('/api/auth/register',json={'username':'x','password':'short','designation':'','company':''}).status_code,400)
        response=self.client.post('/api/auth/login',json=[{'password':'secret-must-not-be-returned'}])
        self.assertEqual(response.status_code,400)
        self.assertNotIn('secret-must-not-be-returned',response.text)

    def test_simultaneous_registration_cannot_exceed_capacity(self):
        barrier=threading.Barrier(6)
        def create(index):
            barrier.wait(timeout=5)
            try:
                self.store.register(f'concurrent{index}','Test.pass.2026','Engineer','Test')
                return 'created'
            except accounts.AccountCapacityError:
                return 'full'
        with patch.object(accounts,'MAX_ACTIVE_USERS',6),ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(create,range(6)))
            self.assertEqual(results.count('created'),5)
            self.assertEqual(results.count('full'),1)
            self.assertEqual(self.store.capacity(),{'maxActiveUsers':6,'activeUsers':6,'availableSlots':0,'includesAdmin':True})
            users=self.store.list_users()
            self.assertEqual(sum(user['role']=='user' for user in users),5)
            self.assertEqual(sum(user['role']=='admin' for user in users),1)

    def test_admin_creation_uses_five_regular_user_slots_and_keeps_session(self):
        with patch.object(accounts,'MAX_ACTIVE_USERS',6):
            self.client.post('/api/auth/login',json={'username':'Admin','password':'usopp.2026'})
            for index in range(5):
                response=self.client.post('/api/auth/users',json={'username':f'created{index}',
                    'password':'Test.pass.2026','designation':'Engineer','company':'Test'})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['user']['role'],'user')
                self.assertEqual(self.client.get('/api/auth/session').json()['user']['role'],'admin')
            extra=self.client.post('/api/auth/users',json={'username':'one_too_many',
                'password':'Test.pass.2026','designation':'Engineer','company':'Test'})
            self.assertEqual(extra.status_code,409,extra.text)

    def test_disabled_account_history_identity_and_reenable_capacity(self):
        with patch.object(accounts,'MAX_ACTIVE_USERS',2):
            user=self.store.register('engineer','Test.pass.2026','Engineer','Test')
            self.store.manage_user(user['id'],'engineer','Engineer','Test',False)
            self.assertEqual(self.store.capacity()['availableSlots'],1)
            self.store.register('replacement','Test.pass.2026','Engineer','Test')
            with self.assertRaises(accounts.AccountCapacityError):
                self.store.manage_user(user['id'],'engineer','Engineer','Test',True)
            with self.store.db() as db:
                row=db.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
                self.assertFalse(row['active'])
                self.assertTrue(accounts.password_matches('Test.pass.2026',row['password_hash']))

if __name__=='__main__': unittest.main()
