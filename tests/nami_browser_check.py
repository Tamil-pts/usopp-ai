"""Optional browser regression check against a local test server on port 8300."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

artifacts=Path('.build/nami-checks')
artifacts.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1500,'height':1000})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    # Reject accidental real-controller requests during browser checks.
    def protect(route):
        if route.request.url.endswith('/api/nami/plc/ping'):
            route.fulfill(status=200,json={'success':True,'ip':'127.0.0.1','rttMs':1,
                'message':'127.0.0.1 replied to ICMP ping.','protocolRequestSent':False})
            return
        data=route.request.post_data_json or {}
        if not data.get('isSimulated'):
            route.fulfill(status=400,json={'error':'Real PLC requests disabled during UI checks'})
        else: route.continue_()
    page.route('**/api/nami/plc/**',protect)
    page.goto('http://127.0.0.1:8300/')
    page.get_by_label('Username',exact=True).fill('Admin')
    page.get_by_label('Password',exact=True).fill('usopp.2026')
    page.get_by_role('button',name='Sign in',exact=True).click()
    page.get_by_role('button',name='Nami Live',exact=True).click()
    workspace=page.frame_locator('iframe[title="Nami PLC Data Verification V1.5"]')
    expect(workspace.locator('html')).to_have_attribute('data-theme','light')
    expect(workspace.get_by_role('heading',name='Nami Live',exact=True)).to_be_visible()
    assert len(page.frames)==2,'Nested application frames returned'
    page.get_by_role('button',name='Help',exact=True).click()
    expect(page.get_by_role('heading',name='Help',exact=True)).to_be_visible()
    page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Nami Live',exact=True).click()
    workspace.get_by_title('Manage PLCs').click()
    dialog=workspace.locator('div').filter(has=workspace.get_by_role('heading',name='PLC Settings & Protocol Tools')).last
    names=workspace.get_by_placeholder('PLC Machine Name')
    original=names.first.input_value()
    names.first.fill('Cancelled draft')
    workspace.get_by_role('button',name='Cancel',exact=True).click()
    workspace.get_by_title('Manage PLCs').click()
    expect(names.first).to_have_value(original)
    # Invalid Machine ID must block Save, with an actionable error.
    workspace.locator('input[type="number"]').nth(1).fill('256')
    workspace.get_by_role('button',name='Save & Apply',exact=True).click()
    expect(workspace.get_by_role('alert')).to_contain_text('Machine ID must be')
    workspace.locator('input[type="number"]').nth(1).fill('0')
    workspace.get_by_role('button',name='Ping IP',exact=True).first.click()
    expect(workspace.get_by_text('ICMP only — no PLC protocol request was sent.').first).to_be_visible()
    expect(workspace.get_by_text('127.0.0.1 replied to ICMP ping.').first).to_be_visible()
    workspace.get_by_role('button',name='TCP / GC 10 Test',exact=True).first.click()
    expect(workspace.get_by_text('Handshake Verified: Program Version').first).to_be_visible()
    assert workspace.locator('div.bg-slate-900').first.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(255, 255, 255)'
    page.screenshot(path=str(artifacts/'settings-light.png'))
    names.first.fill('Saved simulator')
    workspace.get_by_role('button',name='Save & Apply',exact=True).click()
    saved=json.loads(page.evaluate('localStorage.getItem("plc_configs")'))
    assert saved[0]['name']=='Saved simulator'
    page.get_by_role('button',name='Dark mode',exact=True).click()
    expect(workspace.locator('html')).to_have_attribute('data-theme','dark')
    workspace.get_by_title('Manage PLCs').click()
    page.screenshot(path=str(artifacts/'settings-dark.png'))
    workspace.get_by_role('button',name='Cancel',exact=True).click()
    page.get_by_role('button',name='Light mode',exact=True).click()
    expect(workspace.locator('html')).to_have_attribute('data-theme','light')
    assert not errors,errors
    browser.close()
print('Browser checks passed: one workspace, separate ping and GC10 controls, theme sync, help, Cancel, validation, simulator and Save.')
