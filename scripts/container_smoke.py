"""HTTP checks against an isolated container; never send a PLC request."""
import argparse
import hashlib
import http.cookiejar
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:18200')
    parser.add_argument('--version',required=True)
    parser.add_argument('--password-file',type=Path,required=True)
    args=parser.parse_args()
    cookies=http.cookiejar.CookieJar()
    client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    def get(path):
        with client.open(args.url+path,timeout=10) as response:return response.read(),dict(response.headers)
    def data(path):return json.loads(get(path)[0])
    health=None
    for _ in range(180):
        try:
            health=data('/api/health')
            if health.get('status')=='ok':break
        except (OSError,ValueError):pass
        time.sleep(1)
    assert health and health['status']=='ok','Container did not become healthy.'
    assert health['version']==args.version,health
    assert health['frontendBuild']['version']==args.version and health['frontendBuild']['matches'],health
    manifest=data('/build-info.json')
    assert manifest['version']==args.version
    bundle,_=get('/'+manifest['entryFile'])
    assert hashlib.sha256(bundle).hexdigest()==manifest['entrySha256']
    assert args.version.encode() in bundle,'Compiled interface version is missing.'
    for page in ('/','/nami/','/virtual-plc/'):
        document,headers=get(page)
        assert 'no-store' in headers.get('cache-control',headers.get('Cache-Control','')),page
        scripts=re.findall(r'<script[^>]+src="([^"]+)"',document.decode())
        assert scripts,page+' has no interface entry.'
        styles=re.findall(r'<link[^>]+href="([^"]+)"',document.decode())
        for source in scripts+styles:
            path=urllib.parse.urljoin(page,source)
            if not path.startswith('/'):continue
            body,_=get(path)
            assert body and not body.lstrip().lower().startswith(b'<!doctype'),path+' did not return an asset.'
    try:get('/api/nami/server-status')
    except urllib.error.HTTPError as error:assert error.code==401
    else:raise AssertionError('A protected API accepted an anonymous request.')
    password=args.password_file.read_text(encoding='utf-8').strip()
    request=urllib.request.Request(args.url+'/api/auth/login',data=json.dumps({'username':'Admin','password':password}).encode(),
                                   headers={'Content-Type':'application/json'},method='POST')
    with client.open(request,timeout=15) as response:assert response.status==200
    assert data('/api/auth/session')['user']['role']=='admin'
    data('/api/account/storage');data('/api/nami/server-status')
    assert any(item['kind']=='cylinder' for item in data('/api/virtual-plc/component-catalog')['catalog'])
    assert isinstance(data('/api/virtual-plc/component-library')['items'],list)
    schema=data('/openapi.json')
    routes={path for path in schema['paths'] if path.startswith('/api/')}
    assert len(routes)>100,len(routes)
    for required in ('/api/spinconnect/write-st/discover','/api/spinconnect/write-st/analyze',
                     '/api/spinconnect/write-st/generate','/api/nami/plc/prepare-edit','/api/nami/plc/send-edit',
                     '/api/virtual-plc/projects/{identity}/simulation-jig',
                     '/api/virtual-plc/projects/{identity}/environment/mappings/{mapping_id}/confirm'):
        assert required in routes,required
    print(json.dumps({'result':'passed','ui':manifest['version'],'api':health['version'],
                      'apiPaths':len(routes),'sourceCommit':manifest.get('sourceCommit'),
                      'checks':['three UI entries and assets','compiled UI checksum','version agreement',
                                'cache headers','authentication','account storage','registered feature APIs',
                                'cylinder catalog and account component library']}))


if __name__=='__main__':main()
