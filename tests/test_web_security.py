"""Real middleware/authorization checks against isolated account and file stores."""
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.app import app
from backend.core import accounts,access
from backend.core.run_history import current_user


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.delenv('USOPP_ALLOWED_HOSTS',raising=False)
    monkeypatch.delenv('USOPP_PROJECT_ROOTS',raising=False)
    monkeypatch.setattr(accounts,'store',accounts.AccountStore(tmp_path/'accounts.sqlite3'))
    c=TestClient(app,raise_server_exceptions=False)
    yield c
    c.close()


def sign_in(client,role='admin'):
    if role=='admin':
        with accounts.store.db() as db:uid=db.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()[0]
    else:uid=accounts.store.register('engineer','Test.private.2026','Engineer','Example')['id']
    client.cookies.set(accounts.COOKIE,accounts.store.new_session(uid))
    return uid


def test_headers_cover_public_and_authentication_errors(client):
    for path,status in [('/',200),('/api/auth/users',401),('/openapi.json',401)]:
        r=client.get(path);assert r.status_code==status
        assert r.headers['x-content-type-options']=='nosniff'
        assert r.headers['x-frame-options']=='SAMEORIGIN'
        assert "frame-ancestors 'self'" in r.headers['content-security-policy']
        assert 'strict-transport-security' not in r.headers
    assert client.get('/api/auth/session').headers['cache-control']=='private, no-store'
    assert 'applicationRoot' not in client.get('/api/health').json()
    assert 'logFile' not in client.get('/api/health').json()


def test_unexpected_dns_host_rejected_and_private_server_names_configurable(client,monkeypatch):
    assert client.get('/api/health',headers={'Host':'attacker.example'}).status_code==400
    assert client.get('/api/health',headers={'Host':'192.168.19.10:8200'}).status_code==200
    monkeypatch.setenv('USOPP_ALLOWED_HOSTS','app.company.local,127.0.0.1')
    assert client.get('/api/health',headers={'Host':'app.company.local'}).status_code==200
    assert client.get('/api/health',headers={'Host':'192.168.19.10'}).status_code==400
    assert client.get('/api/health',headers={'Host':'app.company.local@evil.example'}).status_code==400


def test_browser_origin_and_fetch_metadata_enforced(client):
    for headers in [{'Origin':'http://attacker.example'},{'Origin':'null'},{'Sec-Fetch-Site':'cross-site'},{'Referer':'http://attacker.example/path'}]:
        assert client.post('/api/auth/logout',headers=headers).status_code==403
    assert client.post('/api/auth/logout',headers={'Origin':'http://testserver'}).status_code==200
    # Authenticated local tools need not fabricate browser-only headers.
    assert client.post('/api/auth/logout').status_code==200


def test_api_schema_requires_admin(client):
    sign_in(client,'user');assert client.get('/openapi.json').status_code==403
    sign_in(client);assert client.get('/openapi.json').status_code==200


def test_https_has_secure_session_cookie_and_hsts(client):
    c=TestClient(app,base_url='https://testserver')
    try:
        # Fixture-only login: this value is not a production password change.
        with accounts.store.db() as db:uid=db.execute("SELECT id FROM users WHERE role='admin'").fetchone()[0]
        accounts.store.manage_user(uid,'Admin','Admin','Example',True,'Unique.private.2026')
        r=c.post('/api/auth/login',json={'username':'Admin','password':'Unique.private.2026'})
        assert r.status_code==200
        assert 'secure' in r.headers['set-cookie'].lower()
        assert 'HttpOnly;' in r.headers['set-cookie']
        assert r.headers['strict-transport-security']=='max-age=31536000'
    finally:c.close()


def test_initial_password_reminder_clears_after_private_change(client):
    uid=sign_in(client);assert client.get('/api/auth/session').json()['user']['passwordChangeRequired'] is True
    accounts.store.manage_user(uid,'Admin','Admin','Example',True,'Unique.private.2026')
    sign_in(client);assert client.get('/api/auth/session').json()['user']['passwordChangeRequired'] is False


def test_error_details_not_returned(client):
    sign_in(client)
    async def broken():raise RuntimeError('SECRET_INTERNAL_DIRECTORY')
    app.add_api_route('/api/security-test-boom',broken,methods=['GET']);app.router.routes.insert(0,app.router.routes.pop())
    try:
        r=client.get('/api/security-test-boom');assert r.status_code==500
        assert 'SECRET_INTERNAL_DIRECTORY' not in r.text
        assert 'nosniff'==r.headers['x-content-type-options']
    finally:app.router.routes[:]=[r for r in app.router.routes if getattr(r,'endpoint',None) is not broken]


def test_server_paths_restricted_to_approved_roots(client,tmp_path,monkeypatch):
    approved=tmp_path/'approved';approved.mkdir();outside=tmp_path/'private';outside.mkdir()
    token=current_user.set({'id':2,'role':'user'})
    try:
        with pytest.raises(HTTPException):access.require_resource(outside)
        monkeypatch.setenv('USOPP_PROJECT_ROOTS',str(approved))
        access.require_resource(approved/'project')
        with pytest.raises(HTTPException):access.require_resource(approved/'..'/'private')
        with pytest.raises(HTTPException):access.require_resource(tmp_path/'approved-other')
    finally:current_user.reset(token)


def test_new_password_policy_and_redacted_invalid_input(client):
    r=client.post('/api/auth/register',json={'username':'engineer','password':'shortpass9','designation':'Engineer','company':'Example'})
    assert r.status_code==400
    r=client.post('/api/auth/login',json=[{'password':'secret-not-for-response'}]);assert r.status_code==400
    assert 'secret-not-for-response' not in r.text


def test_failed_login_throttling_is_persistent(client):
    for _ in range(10):assert accounts.store.login('Admin','incorrect','security-test-client')[1]=='invalid'
    assert accounts.store.login('Admin','incorrect','security-test-client')[1]=='throttled'
    reopened=accounts.AccountStore(accounts.store.path)
    assert reopened.login('Admin','incorrect','security-test-client')[1]=='throttled'
