"""Offline DataInspect browser regression; all PLC API calls are intercepted."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

def frame(payload):
    raw = [3, 0, 0, 0, len(payload), *payload]
    checksum = 0
    for b in raw: checksum ^= b
    return raw + [checksum, 2]

target = dict(id='offline-check', name='Offline check', machineType='Carding',
              ip='192.0.2.5', port=21010, machineId=0, isSimulated=False,
              endianness='little', timeoutMs=2500, status='idle')
metadata = [dict(sNo=i, screenName='Check', machineVariants='BOTH', parameter='Value '+str(gc),
                 units='', min=None, max=None, tagCode=i, groupCode=gc, offset=0,
                 fromVersion='', toVersion='', dataType='UINT', offsetFactor=1, scaleFactor=1,
                 isVisible=True, isWritable=False) for i,gc in enumerate([10,20,150],1)]
seed = {'plc_configs':json.dumps([target]), 'spinning_metadata_Carding':json.dumps(metadata),
        'spinning_metadata_source_Carding':'offline-check.xlsx'}
artifacts=Path('.build/nami-checks')
artifacts.mkdir(parents=True,exist_ok=True)
mode='passed'
requests=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1450,'height':1000})
    page.add_init_script('for(const [k,v] of Object.entries('+json.dumps(seed)+')) localStorage.setItem(k,v);')
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def api(route):
        if route.request.url.endswith('/server-status'):
            route.fulfill(json={'serverTime':'2026-10-06T14:40:00+05:30','timezone':'Asia/Calcutta','applicationPort':8200})
            return
        assert route.request.url.endswith('/plc/read-multiple-groups'),route.request.url
        body=route.request.post_data_json
        requests.append(body)
        assert body['groupCodes']==[10,20,150]
        assert body['ip']=='192.0.2.6'
        results=[]
        for gc in body['groupCodes']:
            result=dict(groupCode=gc,success=True,rawBytes=frame([1,0]),sentBytes=[3,0,1,0,2,0,gc,0,2],
                        tcpConnected=True,stage='complete',rttMs=20)
            if mode=='failed' and gc>=20:
                result.update(success=False,rawBytes=[],error='timed out' if gc==20 else 'Not requested after GC 20 failed',
                              stage='receive' if gc==20 else 'not_sent',sentBytes=result['sentBytes'] if gc==20 else [])
            if mode=='mismatch' and gc==10: result['rawBytes']=frame([1])
            results.append(result)
        route.fulfill(json=dict(success=mode!='failed',results=results,tcpConnected=True,
                         error='timed out' if mode=='failed' else None,
                         closeResult=dict(success=True,sentBytes=[3,0,1,0,2,0,11,11,2],rawBytes=[],plcClosed=True)))
    page.route('**/api/nami/**',api)
    page.goto('http://127.0.0.1:8200/nami/index.html')
    expect(page.get_by_label('PLC IP',exact=True)).to_have_value('192.0.2.5')
    assert page.get_by_text('Request settings',exact=True).count()==0
    assert page.get_by_role('button',name='Change file',exact=True).count()==1
    assert page.locator('details.di-more[open]').count()==0
    page.get_by_label('PLC IP',exact=True).fill('192.0.2.6')
    expect(page.get_by_role('button',name='Test all metadata groups',exact=True)).to_be_disabled()
    page.get_by_role('button',name='Save IP',exact=True).click()
    page.get_by_role('button',name='Test all metadata groups',exact=True).click()
    expect(page.get_by_text('3 passed, 0 metadata mismatch, 0 failed, 0 not requested.',exact=False)).to_be_visible()
    expect(page.get_by_text('3 Passed',exact=True)).to_be_visible()
    expect(page.get_by_text('Request GC 150',exact=True)).to_be_visible()
    page.screenshot(path=str(artifacts/'compact-light.png'))
    mode='failed'
    page.get_by_role('button',name='Test all metadata groups',exact=True).click()
    expect(page.get_by_text('1 passed, 0 metadata mismatch, 1 failed, 1 not requested.',exact=False)).to_be_visible()
    expect(page.get_by_text('Last test: TCP opened, no valid PLC response',exact=False)).to_be_visible()
    expect(page.get_by_text('Response received',exact=True)).to_be_visible()
    page.screenshot(path=str(artifacts/'sequence-timeout.png'))
    mode='mismatch'
    page.get_by_role('button',name='Test all metadata groups',exact=True).click()
    expect(page.get_by_text('2 passed, 1 metadata mismatch, 0 failed, 0 not requested.',exact=False)).to_be_visible()
    expect(page.get_by_text('CHECK METADATA',exact=True)).to_be_visible()
    page.locator('html').evaluate("(el)=>el.setAttribute('data-theme','dark')")
    page.screenshot(path=str(artifacts/'compact-dark.png'))
    assert not errors,errors
    browser.close()
print('Offline browser checks passed: inline IP, collapsed settings, complete run, timeout/skipped groups, payload mismatch, light/dark.')
