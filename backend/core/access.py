"""Persistent ownership for uploaded workspaces, archived runs and exports."""
import os
import re
import time
from pathlib import Path
from fastapi import HTTPException
from backend.core import accounts
from backend.core.run_history import current_user
from backend.core.runtime import WORK, EXPORTS

def resource_key(path):
    return os.path.normcase(str(Path(path).resolve()))

def claim_resource(path, user=None):
    user = current_user.get() if user is None else user
    if not user or not user.get('id'):
        return
    key = resource_key(path)
    with accounts.store.db() as db:
        db.execute('INSERT OR IGNORE INTO resource_owners VALUES (?,?,?)', (key, user['id'], time.time()))
        owner = db.execute('SELECT user_id FROM resource_owners WHERE path=?', (key,)).fetchone()[0]
    if owner != user['id'] and user.get('role') != 'admin':
        raise HTTPException(403, 'This workspace belongs to another user.')

def require_resource(path):
    user = current_user.get()
    if not user or user.get('role') == 'admin':
        return
    resolved = Path(path).resolve()
    if not any(resolved == root.resolve() or resolved.is_relative_to(root.resolve()) for root in (WORK, EXPORTS)):
        if user.get('isDemo'):
            raise HTTPException(403, 'Upload a project or file to use it in your demo workspace.')
        return
    keys = [resource_key(item) for item in (resolved, *resolved.parents)]
    with accounts.store.db() as db:
        rows = dict(db.execute('SELECT path,user_id FROM resource_owners WHERE path IN ('+','.join('?' for _ in keys)+')', keys))
    owner = next((rows[key] for key in keys if key in rows), None)
    if owner != user['id']:
        raise HTTPException(403, 'This result or workspace belongs to another user. Earlier unowned runs are available to Admin.')

def owns_resource(path):
    """Admin's cache action must also leave other users' inputs alone."""
    user = current_user.get() or {}
    keys = [resource_key(item) for item in (Path(path).resolve(), *Path(path).resolve().parents)]
    with accounts.store.db() as db:
        rows = dict(db.execute('SELECT path,user_id FROM resource_owners WHERE path IN ('+','.join('?' for _ in keys)+')', keys))
    owner = next((rows[key] for key in keys if key in rows), None)
    return owner == user.get('id') if owner is not None else user.get('role') == 'admin'

def require_session(sid):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', str(sid or '')):
        raise HTTPException(400, 'Invalid workspace session.')
    for path in (WORK/sid, WORK/'compare'/sid):
        if path.is_dir():
            require_resource(path)
            return path
    raise HTTPException(404, 'Workspace session was not found.')

async def authorize_request(request):
    """Cover session URLs and JSON references; multipart uploads use runtime checks."""
    path = request.url.path
    if request.state.user.get('isDemo') and request.method not in ('GET','HEAD','OPTIONS'):
        shared_prefixes=('/api/knowledge/','/api/local/knowledge/','/api/rules/features/',
                         '/api/rules/library/','/api/rules/pipelines/')
        shared_paths={'/api/rules/modules','/api/rules/feature-pipeline','/api/rules/feedback',
                      '/api/nami/data-models/import'}
        if path in shared_paths or path.startswith(shared_prefixes):
            raise HTTPException(403, 'Shared configuration changes require a personal account. Demo uploads and validation results stay in your demo workspace.')
    patterns = (
        r'^/api/download/([^/]+)', r'^/api/metadata/view/download/([^/]+)',
        r'^/api/local/metadata/download/([^/]+)', r'^/api/reports/rules/([^/]+)',
        r'^/api/local/compare/(?:status|detail|ladder)/([^/]+)',
        r'^/api/local/compare/(?:reports|export)/start/([^/]+)',
        r'^/api/local/compare/export/((?!start/|status/|download/)[^/]+)',
    )
    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            require_session(match.group(1))
    for key in ('sessionId','session_id','sid'):
        if request.query_params.get(key):
            require_session(request.query_params[key])
    if request.headers.get('content-type','').split(';',1)[0] == 'application/json':
        try:
            data = await request.json()
        except ValueError:
            return
        if isinstance(data, dict):
            for key in ('sessionId','session_id','sid'):
                if data.get(key): require_session(str(data[key]))
            for key in ('path','project_path','projectPath','metadata_path','metadataPath','workbookPath','base_path','new_path'):
                value = data.get(key)
                if isinstance(value,str) and value: require_resource(value)
