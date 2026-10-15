"""Local integration check: isolated accounts/settings, no controller traffic."""
from pathlib import Path
import json
import os
import re
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.build' / 'workspace-review-20261015'
USERNAME = 'workspace_check'
PASSWORD = 'LocalCheck.2026'


def serve(port):
    sys.path.insert(0, str(ROOT))
    os.environ.pop('USOPP_DATA_ROOT', None)
    os.environ.pop('USOPP_LLM_BASE_URL', None)
    os.environ['USOPP_LLM_PROVIDER'] = 'local'
    # Import resource paths first without copying the multi-GB reference tree.
    # Mutable stores and workspaces are redirected before application imports.
    from backend.core import runtime
    runtime.BASE = ARTIFACTS / 'isolated-data'
    runtime.WORK = runtime.BASE / '.usopp_workspaces'
    runtime.EXPORTS = runtime.BASE / '.usopp_exports'
    for directory in (runtime.BASE, runtime.WORK, runtime.EXPORTS):
        directory.mkdir(parents=True, exist_ok=True)
    from backend.core import accounts
    import sqlite3
    try:
        accounts.store.register(USERNAME, PASSWORD, 'Test engineer', 'Local integration check')
    except sqlite3.IntegrityError:
        pass
    try:
        accounts.store.register('activity_colleague', PASSWORD, 'Test engineer', 'Local integration check')
    except sqlite3.IntegrityError:
        pass
    # Seed only the isolated test store. The dashboard uses its real history API.
    from datetime import datetime, timedelta, timezone
    import uuid
    from backend.core import run_history
    people = {person['username']: person for person in accounts.store.list_users()}
    for index, (kind, age, owner) in enumerate([
        ('validation', 0, USERNAME), ('rules', 1, USERNAME),
        ('datainspect', 1, USERNAME), ('compare', 3, USERNAME),
        ('metadata', 12, USERNAME), ('validation', 0, 'activity_colleague'),
    ]):
        identity = uuid.uuid5(uuid.NAMESPACE_URL, f'usopp-workspace-review-activity-{index}').hex
        when = (datetime.now(timezone.utc)-timedelta(days=age, minutes=1)).isoformat()
        person = people[owner]
        record = {'id': identity, 'kind': kind, 'testId': f'UI-REVIEW-{index}',
                  'projectName': 'Isolated workflow fixture', 'machineDepartment': 'Finisher',
                  'createdAt': when, 'completedAt': when, 'status': 'completed', 'summary': {},
                  'user': {'id': person['id'], 'username': person['username']}}
        run_history.write_json(run_history.RECORDS/identity/'record.json', record)
        run_history.write_json(run_history.RECORDS/identity/'result.json', {})
        run_history.archive_database(record, {})
    from backend.app import app
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=port, access_log=False)


def run():
    from urllib.request import urlopen
    from playwright.sync_api import sync_playwright, expect
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    with (ARTIFACTS / 'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, __file__, '--serve', str(port)], cwd=ROOT,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            deadline = time.monotonic() + 45
            while True:
                if process.poll() is not None:
                    raise AssertionError('Isolated server exited; see server.log')
                try:
                    urlopen(url + '/api/health', timeout=1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.2)
            with sync_playwright() as engine:
                browser = engine.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width': 1536, 'height': 1100})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('**/api/nami/plc/**', lambda route: route.fulfill(
                    status=403, json={'detail': 'Controller requests disabled during local UI checks.'}))
                page.goto(url)
                page.get_by_label('Username', exact=True).fill(USERNAME)
                page.get_by_label('Password', exact=True).fill(PASSWORD)
                page.get_by_role('button', name='Sign in', exact=True).click()
                navigation = page.get_by_role('navigation', name='Main navigation')
                expect(navigation).to_be_visible(timeout=20000)
                dashboard = page.locator('.workHubDashboard')
                expect(dashboard).to_be_visible()
                expect(page.locator('.homeProject')).to_have_count(0)
                expect(page.locator('.kpis')).to_have_count(0)
                expect(dashboard.locator('.workHubTask')).to_have_count(4)
                activity = dashboard.locator('.workHubActivity')
                expect(activity.get_by_role('heading', name='Your engineering activity')).to_be_visible()
                expect(activity.locator('.workHubActivitySubheading')).to_contain_text('4 saved runs')
                expect(activity.locator('.workHubActivityRecent li')).to_have_count(4)
                expect(activity).not_to_contain_text('activity_colleague')
                expect(activity.locator('.workHubActivityBarZero')).to_have_count(4)
                assert activity.locator('.workHubActivityBarZero').evaluate_all(
                    '(bars)=>bars.every(bar=>bar.getBoundingClientRect().height<=3)'), 'Zero-activity bars must stay on the baseline'
                actual_activity = page.request.get(url + '/api/history/activity?days=7').json()
                assert actual_activity['scope'] == 'own' and actual_activity['totalRuns'] == 4
                activity.get_by_role('button', name='30 days', exact=True).click()
                expect(activity.locator('.workHubActivitySubheading')).to_contain_text('5 saved runs')
                expect(activity.locator('.workHubActivityDay')).to_have_count(30)
                activity.get_by_role('button', name='7 days', exact=True).click()
                expect(activity.locator('.workHubActivitySubheading')).to_contain_text('4 saved runs')
                activity.get_by_text('View daily totals', exact=True).click()
                expect(activity.locator('.workHubActivityDaily dl > div')).to_have_count(7)
                activity.get_by_text('View daily totals', exact=True).click()
                activity.screenshot(path=str(ARTIFACTS / 'workhub-activity-light.png'))
                # Failure and empty states must not present invented activity totals.
                activity_pattern = '**/api/history/activity?days=*'
                page.route(activity_pattern, lambda route: route.fulfill(status=503, json={'detail': 'Local activity error fixture'}))
                activity.get_by_role('button', name='Refresh engineering activity').click()
                expect(activity.get_by_role('alert')).to_contain_text('Activity is unavailable')
                expect(activity.locator('.workHubActivityChart')).to_have_count(0)
                page.unroute(activity_pattern)
                empty_activity = {**actual_activity, 'totalRuns': 0, 'users': [], 'tools': [], 'recent': [],
                                  'daily': [{**point, 'count': 0} for point in actual_activity['daily']]}
                page.route(activity_pattern, lambda route: route.fulfill(json=empty_activity))
                activity.get_by_role('button', name='Try again', exact=True).click()
                expect(activity).to_contain_text('No saved activity in the last 7 days')
                expect(activity.locator('.workHubActivityChart')).to_have_count(0)
                page.unroute(activity_pattern)
                activity.get_by_role('button', name='Refresh engineering activity').click()
                expect(activity.locator('.workHubActivitySubheading')).to_contain_text('4 saved runs')
                activity.get_by_role('button', name='View saved history', exact=True).click()
                expect(page.locator('.adminHistory h2')).to_be_focused()
                dashboard.get_by_role('heading', name='WorkHub', exact=True).scroll_into_view_if_needed()
                page.screenshot(path=str(ARTIFACTS / 'workhub-light.png'))
                page.get_by_role('button', name='Dark mode', exact=True).click()
                expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
                page.screenshot(path=str(ARTIFACTS / 'workhub-dark.png'))
                activity.screenshot(path=str(ARTIFACTS / 'workhub-activity-dark.png'))
                page.get_by_role('button', name='Light mode', exact=True).click()
                page.set_viewport_size({'width': 430, 'height': 930})
                expect(dashboard.locator('.workHubTask')).to_have_count(4)
                assert dashboard.evaluate('(el)=>el.scrollWidth<=el.clientWidth+2'), 'Dashboard horizontal overflow'
                assert activity.locator('.workHubActivityBarZero').evaluate_all(
                    '(bars)=>bars.every(bar=>bar.getBoundingClientRect().height<=3)'), 'Mobile zero-activity bars must stay on the baseline'
                activity.locator('h2').scroll_into_view_if_needed()
                page.screenshot(path=str(ARTIFACTS / 'workhub-activity-narrow.png'))
                activity.locator('.workHubActivityRecentHeading').scroll_into_view_if_needed()
                page.screenshot(path=str(ARTIFACTS / 'workhub-activity-narrow-recent.png'))
                dashboard.get_by_role('button', name='Open Chopper', exact=True).scroll_into_view_if_needed()
                expect(dashboard.get_by_role('button', name='Open Chopper', exact=True)).to_be_visible()
                expect(dashboard.get_by_role('heading', name='Understand how it works.', exact=True)).to_be_visible()
                page.screenshot(path=str(ARTIFACTS / 'workhub-narrow-bottom.png'))
                dashboard.get_by_role('heading', name='WorkHub', exact=True).scroll_into_view_if_needed()
                page.screenshot(path=str(ARTIFACTS / 'workhub-narrow.png'))
                page.set_viewport_size({'width': 1536, 'height': 1100})
                guide = dashboard.locator('.workHubGuide')
                expect(guide.locator('ol > li')).to_have_count(4)
                guide.screenshot(path=str(ARTIFACTS / 'workhub-workflow-guide.png'))
                for label, destination in [('Open ByteMap', 'ByteMap'), ('Open LogicScan', 'LogicScan'),
                                           ('Open DataInspect', 'DataInspect'), ('Ask Chopper', 'AI Assistant')]:
                    guide.get_by_role('button', name=label, exact=True).click()
                    expect(navigation.get_by_role('button', name=destination, exact=True)).to_have_class('active')
                    navigation.get_by_role('button', name='WorkHub', exact=True).click()
                    expect(dashboard).to_be_visible()
                for name in ('ByteMap', 'DataInspect', 'MatchView', 'LogicScan'):
                    dashboard.locator('.workHubTask').filter(has_text=name).click()
                    expect(navigation.get_by_role('button', name=name, exact=True)).to_have_class('active')
                    expect(dashboard).not_to_be_visible()
                    navigation.get_by_role('button', name='WorkHub', exact=True).click()
                    expect(dashboard).to_be_visible()

                # Seed metadata in this test user's isolated server-owned storage.
                account = page.request.get(url + '/api/auth/session').json()['user']
                names = ['doffs', 'Production in kg', 'Powerfail_Time_Minute', 'Delivery Hanks', 'Feed Roller Stoppage']
                metadata = [{'sNo': i + 1, 'screenName': 'Current Shift Report', 'machineVariants': '',
                             'parameter': name, 'units': '', 'min': None, 'max': None, 'tagCode': 55 + i,
                             'groupCode': 40, 'offset': i * 4, 'fromVersion': '', 'toVersion': '',
                             'dataType': 'REAL', 'arraySize': None, 'offsetFactor': 1, 'scaleFactor': 1,
                             'isVisible': True, 'isWritable': False} for i, name in enumerate(names)]
                plc = {'id': 'review-finisher', 'name': 'Local Finisher fixture', 'machineType': 'Finisher',
                       'ip': '127.0.0.1', 'port': 21010, 'machineId': 0, 'isSimulated': True,
                       'endianness': 'little', 'timeoutMs': 2500, 'status': 'idle'}
                values = {'plc_configs': [plc], 'spinning_metadata_Finisher': metadata,
                          'spinning_metadata_source_Finisher': 'Local source-review fixture'}
                storage = page.request.get(url + '/api/account/storage').json()['entries']
                response = page.request.post(url + '/api/account/storage', data={
                    'accountId': account['id'], 'changes': [{'key': key, 'value': json.dumps(value) if not isinstance(value, str) else value,
                    'revision': storage.get(key, {}).get('revision', 0)} for key, value in values.items()]})
                assert response.ok, response.text()
                dashboard.locator('.workHubTask').filter(has_text='DataInspect').click()
                frame = page.frame_locator('iframe[title="Nami PLC Data Verification V1.5"]')
                production = frame.locator('tbody tr').filter(has=frame.get_by_text('Production in kg', exact=True)).last
                expect(production).to_be_visible(timeout=30000)
                expect(production).to_contain_text('Reference conflict')
                expect(production).not_to_contain_text('Fail - datatype differs')
                production.get_by_text('Source details', exact=True).click()
                expect(production).to_contain_text('TIMESTAMP')
                expect(production).to_contain_text('FLOAT')
                doffs = frame.locator('tbody tr').filter(has=frame.get_by_text('doffs', exact=True)).last
                expect(doffs).to_contain_text('Pass')
                unmatched = frame.locator('tbody tr').filter(has=frame.get_by_text('Delivery Hanks', exact=True)).last
                expect(unmatched).to_contain_text('No matching reference for this department')
                production.hover()
                page.screenshot(path=str(ARTIFACTS / 'datainspect-reference-review.png'))

                # Real source analysis uses local tools in this isolated backend.
                response = page.request.post(url + '/api/assist', timeout=120000, data={
                    'question': 'Explain the machine functions of this project.',
                    'context': {'projectPath': str(ROOT.parent / 'project 2'), 'projectName': 'project 2'}})
                assert response.ok, response.text()[:1000]
                answer = response.json()
                assert '### Main functions' in answer['answer']
                assert '21010' in answer['answer'] and '21011' in answer['answer']
                assert 'Draft and sliver settings' not in answer['answer']
                assert answer['machineSummary']['enabledTasks'] == 70
                (ARTIFACTS / 'chopper-api-summary.md').write_text(answer['answer'], encoding='utf-8')
                # Exercise the chat renderer with this real API result delivered through its job protocol.
                page.route('**/api/assist/start', lambda route: route.fulfill(json={'jobId': 'local-browser-summary'}))
                page.route('**/api/assist/status/local-browser-summary', lambda route: route.fulfill(json={
                    'status': 'complete', 'stage': 'Answer ready', 'result': answer, 'elapsedSeconds': 0}))
                navigation.get_by_role('button', name='AI Assistant', exact=True).click()
                composer = page.locator('.chopperComposer textarea')
                composer.fill('Explain the machine functions of project 2.')
                page.locator('.chopperComposer').get_by_role('button', name='Send', exact=True).click()
                expect(page.locator('.chopperReply').get_by_role('heading', name='Main functions', exact=True)).to_be_visible(timeout=20000)
                page.get_by_role('button', name=re.compile(r'^Show source S\d+$')).first.click()
                expect(page.locator('.assistEvidenceList details[open]')).to_have_count(1)
                page.screenshot(path=str(ARTIFACTS / 'chopper-project-specific.png'))
                assert not errors, errors
                (ARTIFACTS / 'verification.json').write_text(json.dumps({
                    'workhub': 'light/dark/narrow, four working tool cards, no project/KPI cards',
                    'workhubActivity': 'actual isolated history API, own-user scope, 7/30-day totals, daily values, empty/error/retry, history link',
                    'workhubGuide': 'four working workflow navigation buttons',
                    'dataInspect': 'actual Finisher reference conflict, case-insensitive pass and unmatched-name wording',
                    'chopper': 'actual project 2 API + formatted chat rendering + source citation expansion',
                    'pageErrors': errors, 'controllerTraffic': 'blocked', 'modelGeneration': 'local tools only',
                    'isolatedData': str(ARTIFACTS / 'isolated-data')}, indent=2), encoding='utf-8')
                browser.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    print('Workspace integration checks passed. Screenshots and verification.json:', ARTIFACTS)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--serve':
        serve(int(sys.argv[2]))
    else:
        run()
