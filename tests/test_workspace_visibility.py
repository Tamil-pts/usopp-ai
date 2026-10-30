from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app import app
from backend.core import accounts


def test_account_module_visibility_is_persistent_and_admin_managed(tmp_path):
    store = accounts.AccountStore(tmp_path / 'accounts.sqlite3')
    store.initialize()
    with patch.object(accounts, 'store', store):
        admin, user = TestClient(app), TestClient(app)
        assert admin.post('/api/auth/login', json={'username':'Admin','password':'usopp.2026'}).status_code == 200
        payload={'username':'visibility_user','password':'Example.pass.2026','designation':'Engineer','company':'Example','workspaceModules':['workhub','edesign']}
        created=admin.post('/api/auth/users',json=payload)
        assert created.status_code==200, created.text
        uid=created.json()['user']['id']
        assert user.post('/api/auth/login',json={'username':payload['username'],'password':payload['password']}).json()['user']['workspaceModules']==['workhub','edesign']
        assert user.get('/api/auth/users').status_code==403
        update={**payload,'active':True,'password':'','workspaceModules':[]}
        assert admin.post(f'/api/auth/users/{uid}',json=update).status_code==200
        assert user.get('/api/auth/session').json()['user']['workspaceModules']==[]
        del update['workspaceModules']
        assert admin.post(f'/api/auth/users/{uid}',json=update).json()['user']['workspaceModules']==[]
        update['workspaceModules']=['unknown']
        assert admin.post(f'/api/auth/users/{uid}',json=update).status_code==400
        assert accounts.AccountStore(store.path).list_users()[-1]['workspaceModules']==[]
        assert set(admin.get('/api/auth/session').json()['user']['workspaceModules'])==set(accounts.WORKSPACE_MODULES)
