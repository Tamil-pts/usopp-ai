"""Exercise every API route with empty/missing-resource input in isolated storage.

This checks routing and error handling, not every successful business workflow.
Run separately from unittest so API modules import the isolated runtime paths.
"""
import json
import os
import re
import tempfile
from pathlib import Path

os.environ.pop('USOPP_LLM_BASE_URL', None)
from backend.core import runtime

report_path = runtime.BASE / 'logs' / 'api_surface_check.json'
with tempfile.TemporaryDirectory(prefix='usopp_api_smoke_') as folder:
    root = Path(folder)
    original_base = runtime.BASE
    for name, value in list(vars(runtime).items()):
        if isinstance(value, Path) and name not in {'RESOURCE_ROOT', 'ENGINE', 'RULE_ENGINE', 'COMPARE_ENGINE'}:
            try:
                relative = value.relative_to(original_base)
            except ValueError:
                continue
            setattr(runtime, name, root / relative)
    for path in (runtime.WORK, runtime.EXPORTS / 'metadata', runtime.MASTER, runtime.PROJECT_KB, runtime.LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
    runtime.DEFAULT_RULES.parent.mkdir(parents=True, exist_ok=True)
    runtime.DEFAULT_RULES.write_text('{"rules": []}')
    runtime.MASTER_PARAM_FILE.write_text('{"mappings": []}')
    from backend.app import app
    from fastapi.testclient import TestClient
    results = []
    with TestClient(app, raise_server_exceptions=False) as client:
        def sign_in():
            response=client.post('/api/auth/login',json={'username':'Admin','password':'usopp.2026'})
            assert response.status_code==200,response.text
        sign_in()
        for path, operations in app.openapi()['paths'].items():
            if not path.startswith('/api/'):
                continue
            url = re.sub(r'\{[^}]+\}', 'missing-smoke-resource', path)
            for method in operations:
                if method not in {'get', 'post', 'put', 'delete', 'patch'}:
                    continue
                response = client.request(method.upper(), url, **({'json': {}} if method in {'post', 'put', 'patch'} else {}))
                results.append({'method': method.upper(), 'path': path, 'status': response.status_code,
                                'detail': response.text[:300] if response.status_code >= 400 else ''})
                if path=='/api/auth/logout':
                    sign_in()
        project = root / 'Demo'
        source = project / 'Logical' / 'SpinConnect' / 'mms_nw_r'
        source.mkdir(parents=True)
        (source / 'Cyclic.st').write_text('IF Ready THEN Status := 1; END_IF;')
        draft = client.post('/api/assist/rule-config', json={'guided': True, 'answers': {
            'configurationFormat': 'grouped-v1', 'name': 'API path smoke', 'category': 'Logic',
            'checks': [{'type': 'logic', 'file': r'mms_nw_r\Cyclic.st',
                        'alternatives': ['IF Ready THEN Status := 1; END_IF;']}]}})
        assert draft.status_code == 200, draft.text
        config = draft.json()['config']
        config['rules'][0]['enabled'] = True
        checked = client.post('/api/local/rules/validate', json={'project_path': str(project), 'rules': config})
        assert checked.status_code == 200, checked.text
        assert checked.json()['counts']['pass'] == 1, checked.text
    failures = [r for r in results if r['status'] >= 500 or r['status'] == 405]
    report_path.write_text(json.dumps({'scope': 'Every route; empty input and missing-resource handling in temporary storage',
                                      'results': results, 'failures': failures,
                                      'functionalChecks': ['Grouped rule configuration and real engine validation of subroutine-relative Cyclic.st: PASS']}, indent=2), encoding='utf-8')
    print(f'{len(results)} API operations checked; {len(failures)} server/routing failures. Report: {report_path}')
    raise SystemExit(bool(failures))
