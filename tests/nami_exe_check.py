"""Smoke check a portable release on 8301, isolated from the user's data."""
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar

exe=Path(sys.argv[1]).resolve()
data=Path('.build/nami-checks/exe-data').resolve()
env=dict(os.environ,USOPP_API_PORT='8301',USOPP_API_HOST='127.0.0.1',
         USOPP_NO_BROWSER='1',USOPP_DATA_ROOT=str(data))
process=subprocess.Popen([str(exe)],cwd=exe.parent,env=env,
                         creationflags=subprocess.CREATE_NO_WINDOW)
try:
    opener=build_opener(HTTPCookieProcessor(CookieJar()))
    def request(path, body=None):
        payload=json.dumps(body).encode() if body is not None else None
        with opener.open(Request('http://127.0.0.1:8301'+path,data=payload,
                             headers={'Content-Type':'application/json'}),timeout=15) as response:
            return response.read()
    deadline=time.monotonic()+30
    while True:
        if process.poll() is not None: raise AssertionError(f'Executable exited: {process.returncode}')
        try:
            health=json.loads(request('/api/health'))
            break
        except OSError:
            if time.monotonic()>deadline: raise
            time.sleep(.2)
    expected_id=hashlib.sha256(os.path.normcase(str(data)).encode()).hexdigest()
    assert health.get('installationId')==expected_id if 'installationId' in health else Path(health['applicationRoot']).resolve()==data
    html=request('/nami/index.html').decode()
    assets=re.findall(r'(?:src|href)="(/nami/assets/[^"]+)"',html)
    assert assets
    for asset in assets: assert request(asset)
    assert request('/nami/default_metadata.csv')
    account=json.loads(request('/api/auth/login',{'username':'Admin','password':'usopp.2026'}))
    assert account['user']['role']=='admin'
    result=json.loads(request('/api/nami/plc/test-connection',{'isSimulated':True}))
    assert result['success'] and result['programVersionStr']=='5.296'
    print('Packaged EXE passed: startup on 8301, isolated data, feature assets, metadata and simulator API.')
finally:
    process.terminate()
    process.wait(timeout=10)
