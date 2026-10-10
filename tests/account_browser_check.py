"""Local browser checks for accounts, shared help and feature navigation."""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

artifacts=Path('.build/account-checks');artifacts.mkdir(parents=True,exist_ok=True)
username='ui_engineer_'+str(int(time.time()))
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1500,'height':1050})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8300/')
    expect(page.get_by_role('heading',name='Sign in to uSOPp.ai')).to_be_visible()
    page.get_by_role('button',name='New user? Create account',exact=True).click()
    page.get_by_label('Username',exact=True).fill(username)
    page.get_by_label('Password',exact=True).fill('Browser.pass.2026')
    page.get_by_label('Confirm password',exact=True).fill('Browser.pass.2026')
    page.get_by_label('Designation',exact=True).fill('Automation Engineer')
    page.get_by_label('Company name',exact=True).fill('Browser Test Company')
    page.get_by_role('button',name='Create account',exact=True).click()
    expect(page.get_by_role('navigation',name='Main navigation')).to_be_visible(timeout=15000)
    nav=page.get_by_role('navigation',name='Main navigation')
    for label in ['Packet Lens','Nami Live','Twin Scope','Rule Pilot','Chopper Desk']:
        nav.get_by_role('button',name=label,exact=True).click()
        expect(page.get_by_role('complementary',name=label+' recommendations')).to_be_visible()
    utilities=page.get_by_role('navigation',name='Settings and help')
    assert utilities.bounding_box()['y']>700,'Common utilities are not at the bottom left'
    utilities.get_by_role('button',name='Help',exact=True).click()
    expect(page.get_by_role('heading',name='Help',exact=True)).to_be_visible()
    for label in ['Packet Lens','Nami Live','Twin Scope','Rule Pilot','Chopper Desk']:
        expect(page.get_by_role('heading',name=label,exact=True)).to_be_visible()
    page.screenshot(path=str(artifacts/'common-help.png'))
    utilities.get_by_role('button',name='Settings',exact=True).click()
    expect(page.get_by_text('Automation Engineer · Browser Test Company')).to_be_visible()
    page.get_by_label('Current password',exact=True).fill('Browser.pass.2026')
    page.get_by_label('New password',exact=True).fill('Browser.changed.2026')
    page.get_by_label('Confirm new password',exact=True).fill('Browser.changed.2026')
    page.get_by_role('button',name='Change password',exact=True).click()
    expect(page.get_by_text('Password changed. Other sessions have been signed out.')).to_be_visible(timeout=15000)
    page.get_by_role('button',name='Sign out',exact=True).click()
    expect(page.get_by_role('heading',name='Sign in to uSOPp.ai')).to_be_visible()
    page.get_by_label('Username',exact=True).fill(username)
    page.get_by_label('Password',exact=True).fill('Browser.changed.2026')
    page.get_by_role('button',name='Sign in',exact=True).click()
    expect(nav).to_be_visible(timeout=15000)
    assert not errors,errors
    browser.close()
print('Browser checks passed: registration, all renamed features, recommendations, bottom-left Help, profile, password change and new-password login.')
