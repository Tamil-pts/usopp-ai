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
        self.assertEqual(response.status_code,202)
        self.assertTrue(response.json()['pending'])
        self.assertIsNone(self.client.get('/api/auth/session').json()['user'])
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'engineer','password':'Test.pass.2026'}).status_code,403)
        user=next(item for item in self.store.list_users() if item['username']=='engineer')
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
        user=next(item for item in self.store.list_users() if item['username']=='engineer')
        self.store.manage_user(user['id'],'engineer','PLC Engineer','Test Company',True)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'engineer','password':'Test.pass.2026'}).status_code,200)
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

    def test_simultaneous_registration_is_not_limited_to_six_accounts(self):
        barrier=threading.Barrier(6)
        def create(index):
            barrier.wait(timeout=5)
            self.store.register(f'concurrent{index}','Test.pass.2026','Engineer','Test')
            return 'created'
        with patch.object(accounts,'password_hash',return_value='test-hash'),ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(create,range(6)))
            self.assertEqual(results.count('created'),6)
            self.assertEqual(self.store.capacity(),{'maxActiveUsers':None,'activeUsers':7,'availableSlots':None,'includesAdmin':True,'unlimited':True})
            users=self.store.list_users()
            self.assertEqual(sum(user['role']=='user' for user in users),6)
            self.assertEqual(sum(user['role']=='admin' for user in users),1)

    def test_admin_can_create_more_than_six_accounts_and_keeps_session(self):
        with patch.object(accounts,'password_hash',return_value='test-hash'):
            self.client.post('/api/auth/login',json={'username':'Admin','password':'usopp.2026'})
            for index in range(200):
                response=self.client.post('/api/auth/users',json={'username':f'created{index}',
                    'password':'Test.pass.2026','designation':'Engineer','company':'Test'})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['user']['role'],'user')
                if index in (0,199):
                    self.assertEqual(self.client.get('/api/auth/session').json()['user']['role'],'admin')
            capacity=self.client.get('/api/auth/users').json()['capacity']
            self.assertEqual(capacity['activeUsers'],201)
            self.assertTrue(capacity['unlimited'])

    def test_disabled_account_history_identity_and_reenable_without_slot_limit(self):
        user=self.store.register('engineer','Test.pass.2026','Engineer','Test')
        self.store.manage_user(user['id'],'engineer','Engineer','Test',False)
        self.store.register('replacement','Test.pass.2026','Engineer','Test')
        reenabled=self.store.manage_user(user['id'],'engineer','Engineer','Test',True)
        self.assertTrue(reenabled['active'])
        self.assertEqual(self.store.capacity()['activeUsers'],3)
        with self.store.db() as db:
            row=db.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
            self.assertTrue(row['active'])
            self.assertTrue(accounts.password_matches('Test.pass.2026',row['password_hash']))

if __name__=='__main__': unittest.main()
