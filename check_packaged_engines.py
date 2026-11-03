"""Smoke-check a release's engine dispatch without using developer source."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import os
import socket
import time
import urllib.request

exe = Path(sys.argv[1]).resolve()
results = []
with tempfile.TemporaryDirectory(prefix='usopp_exe_smoke_') as folder:
    root = Path(folder)
    logical = root / 'Logical'
    logical.mkdir()
    (root / 'Demo.apj').write_text('<Project/>')
    subroutine = logical / 'SpinConnect' / 'mms_nw_r'
    subroutine.mkdir(parents=True)
    (subroutine / 'mms_nw_rCyclic.st').write_text('IF Ready THEN Status := 1; END_IF;')
    other = logical / 'Machine' / 'mms_Pms'
    other.mkdir(parents=True)
    (other / 'Cyclic.st').write_text('IF Status = 1 THEN Running := TRUE; END_IF;')
    (logical / 'Screen.page').write_text('<Page Name="Screen"><Control ClassId="0x0000100B" Name="String_1"><Property Name="ValueDatapoint" Value="Source[global].Variable[Local.Name]"/></Control></Page>')
    (logical / 'Timing.ld').write_text('<networks><network><row><contact type="open" name="TRUE"/><coil type="set" name="ResetPower"/></row></network></networks>')
    checks = [
        {'type': 'logic', 'file': r'mms_nw_r\mms_nw_rCyclic.st', 'alternatives': ['IF Ready THEN Status := 1; END_IF;'],
         'crossChecks': [{'type': 'logic', 'file': r'mms_Pms\Cyclic.st', 'alternatives': ['IF Status = 1 THEN Running := TRUE; END_IF;']}]},
        {'type': 'hmi', 'file': 'Screen.page', 'variants': [{'entity': 'Control', 'name': 'String', 'nameMatch': 'prefix', 'properties': {'ValueDatapoint': 'Local.Name'}}]},
        {'type': 'ladder', 'file': 'Timing.ld', 'networks': [{'id': 'n1', 'mode': 'elements', 'relation': 'presence', 'elements': [{'kind': 'contact', 'type': 'open', 'name': 'TRUE'}, {'kind': 'coil', 'type': 'set', 'name': 'ResetPower'}]}]},
    ]
    rules = root / 'rules.json'
    rules.write_text(json.dumps({'rules': [{'id': 'SMOKE', 'name': 'Packaged requirements', 'category': 'PLC logic + HMI', 'kind': 'structured_requirements', 'enabled': True, 'checks': checks}]}))
    commands = [
        ['packet_validation_report_uSOPp_v1.71_final.py', '--help'],
        ['compare.py', '--base', str(root), '--new', str(root), '--output', str(root / 'compare.json')],
        ['rule_engine_v4_30.py', '--project', str(root), '--rules', str(rules), '--output-json', str(root / 'result.json')],
    ]
    for command in commands:
        completed = subprocess.run([str(exe), '--usopp-engine', *command], cwd=root, capture_output=True, text=True, timeout=120)
        results.append({'engine': command[0], 'returncode': completed.returncode, 'stderr': completed.stderr[-3000:]})
    if (root / 'result.json').exists():
        result = json.loads((root / 'result.json').read_text())
        results.append({'structuredRequirementResults': result})
        assert result['counts']['fail'] == 0 and result['counts']['pass'] == 1, result
    else:
        raise RuntimeError(results)
    assert all(r.get('returncode', 0) == 0 for r in results), results
    with socket.socket() as available:
        available.bind(('127.0.0.1', 0))
        port = available.getsockname()[1]
    env = {**os.environ, 'USOPP_API_PORT': str(port), 'USOPP_DATA_ROOT': str(root / 'appdata'), 'USOPP_NO_BROWSER': '1'}
    with (root / 'server.log').open('w') as log:
        process = subprocess.Popen([str(exe)], cwd=root, env=env, stdout=log, stderr=log)
        try:
            for attempt in range(60):
                if process.poll() is not None:
                    raise RuntimeError((root / 'server.log').read_text())
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
                        health = json.load(response)
                    break
                except OSError:
                    time.sleep(0.5)
            else:
                raise RuntimeError('Packaged server did not become ready')
            expected_id=hashlib.sha256(os.path.normcase(str((root/'appdata').resolve())).encode()).hexdigest()
            assert health.get('installationId')==expected_id if 'installationId' in health else Path(health['applicationRoot'])==root/'appdata'
            for route in ('/', '/api/rules/library', '/api/rules/features'):
                with urllib.request.urlopen(f'http://127.0.0.1:{port}{route}', timeout=10) as response:
                    assert response.status == 200
            results.append({'packagedServer': 'PASS', 'version': health['version']})
        finally:
            process.terminate()
            process.wait(timeout=20)
Path('logs/packaged_engine_check.json').write_text(json.dumps(results, indent=2))
print('Packaged engine checks passed: packet CLI, comparison, PLC/cross-reference, HMI, ladder.')
