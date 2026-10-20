"""Additive-module integration tests; no model downloads or physical PLC calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
import pytest

from virtual_plc.core.storage import WorkspaceStore, relative_path, safe_source
from virtual_plc.core.service import VirtualPLCService, Workspace, public_model, runtime_view
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.tests.test_runtime import project, variable


@pytest.fixture
def plc_folder(tmp_path):
    root = tmp_path / 'FixturePLC'
    files = {
        'Fixture.apj': '<?AutomationStudio Version="4.12.1"?><Project/>',
        'LastUser.set': '<Settings><ConfigurationManager ActiveConfigurationName="Config1"/></Settings>',
        'Physical/Config1/Hardware.hw': '<Hardware><Module Name="PLC1" Type="X20CP1586"><Parameter ID="Cyclic1Duration" Value="10000"/></Module></Hardware>',
        'Physical/Config1/PLC1/CPU.sw': '<SwConfiguration><TaskClass Name="Cyclic#1"><Task Name="Main" Source="Main.prg"/></TaskClass></SwConfiguration>',
        'Logical/Main/IEC.prg': '<Program><Files><File>Main.st</File></Files></Program>',
        'Logical/Main/Main.st': 'PROGRAM _CYCLIC\nIF Start THEN Counter := Counter + 1; END_IF;\nEND_PROGRAM',
        'Logical/Global.var': 'VAR_GLOBAL RETAIN\nStart : BOOL := FALSE;\nCounter : DINT := 0;\nEND_VAR',
        'Logical/VCShared/Pages/Main.page': '<Page Name="Main"><Property Name="Width" Value="320"/><Property Name="Height" Value="240"/><Layers><Layer Name="Main"><Controls><Control Name="Start" ClassId="0x00001006"><Property Name="CompletionDatapoint" Value="Source[global].Variable[Local.Start]"/><Property Name="CompletionValue" Value="1"/></Control></Controls></Layer></Layers></Page>',
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend.core import accounts, project_intelligence
    from virtual_plc import api
    from virtual_plc.server import create_app
    store = accounts.AccountStore(tmp_path / 'accounts.sqlite3')
    first = store.register('virtual.engineer', 'TestOnly.pass.2026', 'Engineer', 'Fixture')
    second = store.register('other.engineer', 'TestOnly.pass.2026', 'Engineer', 'Fixture')
    monkeypatch.setattr(accounts, 'store', store)
    monkeypatch.setattr(project_intelligence, 'WORK', tmp_path / 'indexes')
    service = VirtualPLCService(tmp_path / 'workspaces')
    monkeypatch.setattr(api, 'service', service)
    application = create_app()
    # Without a context manager the existing application lifespan does not
    # launch model/live-data processes. These tests own only their temp storage.
    primary = TestClient(application)
    primary.cookies.set(accounts.COOKIE, store.new_session(first['id']))
    other = TestClient(application)
    other.cookies.set(accounts.COOKIE, store.new_session(second['id']))
    yield primary, other, service
    service.close()
    primary.close()
    other.close()


def wait_ready(client, identity):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        response = client.get('/api/virtual-plc/projects/' + identity)
        assert response.status_code == 200, response.text
        state = response.json()
        if state['status'] != 'analyzing':
            assert state['status'] == 'ready', state
            return state
        time.sleep(.02)
    raise AssertionError('Fixture analysis did not finish in 20 seconds')


def test_existing_routes_and_new_auth_are_preserved(client):
    primary, _, _ = client
    assert primary.get('/api/health').status_code == 200
    assert primary.get('/api/nami/health').status_code == 200
    assert primary.get('/api/virtual-plc/health').json()['originalSourceWrites'] is False
    assert '/virtual-plc/assets/' in primary.get('/virtual-plc/').text
    assert 'Open Virtual PLC workspace' in primary.get('/').text
    assert '/virtual-plc/navigation.js' in primary.get('/workhub').text
    script = primary.get('/virtual-plc/navigation.js')
    assert script.status_code == 200 and '__usoppVirtualNavigation' in script.text
    assert '.railMainNav' in script.text and '.workHubTaskGrid' in script.text
    unauthenticated = TestClient(primary.app)
    try:
        assert unauthenticated.get('/api/virtual-plc/projects').status_code == 401
    finally:
        unauthenticated.close()
    assert primary.post('/api/virtual-plc/projects', json={}, headers={'origin': 'http://unrelated.invalid'}).status_code == 403


def test_actual_analysis_hmi_memory_forcing_trace_and_export(client, plc_folder):
    primary, other, service = client
    hashes = {path.relative_to(plc_folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in plc_folder.rglob('*') if path.is_file()}
    created = primary.post('/api/virtual-plc/projects', json={'projectPath': str(plc_folder), 'name': 'PLC fixture'})
    assert created.status_code == 200, created.text
    identity = created.json()['id']
    path = '/api/virtual-plc/projects/' + identity
    state = wait_ready(primary, identity)
    assert state['model']['hardware']['controllers'][0]['model'] == 'X20CP1586'
    assert state['runtime']['compatibility']['runAllowed'], state['runtime']['diagnostics']
    assert other.get(path).status_code == 404
    # HMI and I/O use the same typed-memory API, never a second logic engine.
    button = state['model']['hmi']['pages'][0]['objects'][0]
    response = primary.post(path + '/values', json={'name': button['completion']['variable'], 'value': button['completion']['value']})
    assert response.status_code == 200, response.text
    scanned = primary.post(path + '/control', json={'action': 'scan'})
    assert scanned.status_code == 200, scanned.text
    runtime = scanned.json()
    counter = next(row for row in runtime['variables'] if row['name'] == 'Counter')
    assert counter['value'] == 1
    assert runtime['timeMs'] == 10
    assert any(event.get('source') == 'Logical/Main/Main.st' for event in runtime['trace'])
    forced = primary.post(path + '/values', json={'name': counter['id'], 'value': 42, 'force': True})
    assert forced.status_code == 200
    frozen = primary.post(path + '/control', json={'action': 'scan'}).json()
    assert frozen['memory'][counter['id']] == 42
    assert primary.delete(path + '/forces', params={'name': counter['id']}).status_code == 200
    assert primary.patch(path, json={'watchlist': [counter['id']], 'settings': {'templateKind': 'simulation'}}).status_code == 200
    assert primary.get('/api/virtual-plc/templates').json()['templates'][0]['id'] == identity
    assert primary.get(path + '/variables', params={'query': 'Counter', 'limit': 1, 'watchlist': True}).json()['total'] == 1
    assert primary.get(path + '/source', params={'path': '../outside.txt'}).status_code == 400
    original_source = primary.get(path + '/source', params={'path': 'Logical/Main/Main.st'}).json()
    assert 'Counter := Counter + 1' in original_source['text']
    portable = primary.get(path + '/export')
    assert portable.status_code == 200, portable.text
    payload = portable.json()
    payload['workspace']['projectRoot'] = str(plc_folder.parent)
    payload['model']['root'] = str(plc_folder.parent)
    imported = primary.post('/api/virtual-plc/import', files={'file': ('PLC.json', json.dumps(payload), 'application/json')})
    assert imported.status_code == 200, imported.text
    imported_state = imported.json()
    assert imported_state['runtime']['status'] == 'stopped'
    loaded = service.store.load(next(iter(service.workspaces))[0], imported_state['id'])
    assert loaded['projectRoot'] == '' and loaded['imported'] is True
    assert primary.get('/api/virtual-plc/projects/' + imported_state['id'] + '/source', params={'path': 'Logical/Main/Main.st'}).status_code == 200
    after = {path.relative_to(plc_folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in plc_folder.rglob('*') if path.is_file()}
    assert after == hashes


def test_unsupported_active_logic_cannot_run(client, plc_folder):
    primary, _, _ = client
    (plc_folder / 'Logical/Main/Main.st').write_text('PROGRAM _CYCLIC\nUnknownVendorBlock();\nCounter := 900;\nEND_PROGRAM', encoding='utf-8')
    response = primary.post('/api/virtual-plc/projects', json={'projectPath': str(plc_folder)})
    state = wait_ready(primary, response.json()['id'])
    assert not state['runtime']['compatibility']['runAllowed']
    path = '/api/virtual-plc/projects/' + state['id']
    assert primary.post(path + '/control', json={'action': 'run'}).status_code == 400
    assert next(row for row in state['runtime']['variables'] if row['name'] == 'Counter')['value'] == 0


def test_program_test_is_separate_owned_and_preserves_source_snapshot(client, plc_folder):
    primary, other, service = client
    created = primary.post('/api/virtual-plc/projects', json={'projectPath': str(plc_folder)})
    parent = wait_ready(primary, created.json()['id'])
    path = '/api/virtual-plc/projects/' + parent['id']
    program = next(p for p in parent['model']['programs'] if p.get('entry') == 'cyclic')
    assert other.post(path + '/program-test', json={'programId': program['id']}).status_code == 404
    response = primary.post(path + '/program-test', json={'programId': program['id']})
    assert response.status_code == 200, response.text
    scoped = response.json()
    assert scoped['id'] != parent['id']
    assert scoped['model']['executionScope']['parentProjectId'] == parent['id']
    assert scoped['model']['executionScope']['completeMachineExecution'] is False
    assert scoped['sourceCacheComplete'] == parent['sourceCacheComplete']
    assert scoped['runtime']['compatibility']['runAllowed']
    assert primary.post('/api/virtual-plc/projects/' + scoped['id'] + '/control', json={'action': 'scan'}).status_code == 200
    assert primary.get(path).json()['runtime']['scanCount'] == 0
    assert primary.get('/api/virtual-plc/projects/' + scoped['id'] + '/source', params={'path': program['source']}).status_code == 200


def test_hmi_layer_keys_return_immediate_states_and_cpu_config_persists(client, plc_folder):
    primary, other, service = client
    created=primary.post('/api/virtual-plc/projects',json={'projectPath':str(plc_folder)})
    state=wait_ready(primary,created.json()['id'])
    identity=state['id'];path='/api/virtual-plc/projects/'+identity
    workspace=next(w for w in service.workspaces.values() if w.identity==identity)
    model=project('',[variable('Layer','INT',1)])
    layer={'id':'popup','statusBinding':'Layer','statusConfigured':True}
    open_key={'id':'open','name':'Open','kind':'button','x':0,'y':0,'width':20,'height':20,
              'actions':[{'kind':'write','variable':'Layer','value':'0'}]}
    close_key={**open_key,'id':'close','layerState':layer,'actions':[{'kind':'write','variable':'Layer','value':'1'}]}
    model['hmi']={'pages':[{'id':'page','objects':[open_key,close_key],'layers':[{'id':'empty'},layer]}]}
    with workspace.lock:
        workspace.model=model;workspace.runtime=VirtualRuntime(model)
    assert other.post(path+'/hmi-action',json={'pageId':'page','objectId':'open','phase':'press'}).status_code==404
    for control,visible in [('open',True),('close',False)]:
        response=primary.post(path+'/hmi-action',json={'pageId':'page','objectId':control,'phase':'press'})
        assert response.status_code==200,response.text
        assert response.json()['layers']['popup']['visible']==visible
        assert response.json()['controls']['close']['visible']==visible
    polled=primary.post(path+'/interface-values',json={'pageId':'page','names':[]}).json()
    assert polled['layers']['empty']['visible'] is True
    assert polled['layers']['popup']['visible'] is False
    assert other.put(path+'/cpu-services',json={}).status_code==404
    saved=primary.put(path+'/cpu-services',json={'dateTime':'2026-10-18T12:00:00Z'})
    assert saved.status_code==200,saved.text
    assert saved.json()['virtualOnly'] is True
    assert service.store.load(workspace.owner,identity)['manualCorrections']['cpuServices']['dateTime']=='2026-10-18T12:00:00+00:00'
    workspace.runtime.status='running'
    assert primary.put(path+'/cpu-services',json={}).status_code==400


def test_hotspot_virtual_key_opens_login_and_back_sets_it_hidden(client, plc_folder):
    primary, _, service = client
    resources = {
        'Logical/T30_5/VCObject.vc': '<Visualization/>',
        'Logical/loginout/IEC.prg': '<Program><Files><File>loginoutCyclic.ab</File></Files></Program>',
        'Logical/loginout/loginoutCyclic.ab': 'PROGRAM _CYCLIC\nLogin_Layer = Login_Layer\nEND_PROGRAM',
        'Logical/loginout/loginout.var': 'VAR\nLogin_Layer : INT := 1;\nEND_VAR',
        'Logical/T30_5/Local.dso': '''<DataSource Name="Local"><Folder Name="loginout">
            <Property Name="FolderType" Value="Program"/><Datapoint Name="Login_Layer"/>
            </Folder></DataSource>''',
        'Logical/T30_5/VirtualKeys.vcvk': '''<VirtualKeys>
            <VirtualKey Name="LOGIN_LAYER"><KeyActions><KeyAction ClassId="0x00000161">
            <Property Name="ValueDatapoint" Value="Source[global].Variable[Local.loginout.Login_Layer]"/>
            <Property Name="SetValue" Value="0"/></KeyAction></KeyActions></VirtualKey>
            <VirtualKey Name="CLOSE_LOGIN_LAYER"><KeyActions><KeyAction ClassId="0x00000161">
            <Property Name="ValueDatapoint" Value="Source[global].Variable[Local.loginout.Login_Layer]"/>
            <Property Name="SetValue" Value="1"/></KeyAction></KeyActions></VirtualKey>
            </VirtualKeys>''',
        'Logical/T30_5/Layers/LOG_IN_OUT.layer': '''<Layer Name="LOG_IN_OUT">
            <Property Name="StatusDatapoint" Value="Source[global].Variable[Local.loginout.Login_Layer]"/>
            <Property Name="Width" Value="320"/><Property Name="Height" Value="240"/>
            <Controls><Control Name="Button_1" ClassId="0x00001002">
            <Property Name="VirtualKey" Value="Source[local].VirtualKey[CLOSE_LOGIN_LAYER]"/>
            <Property Name="KeyMode" Value="Immediate"/><Property Name="Top" Value="180"/>
            <Property Name="Width" Value="100"/><Property Name="Height" Value="40"/>
            </Control></Controls></Layer>''',
        'Logical/T30_5/Pages/MMS_CONFIG.page': '''<Page Name="MMS_CONFIG">
            <Property Name="Width" Value="320"/><Property Name="Height" Value="240"/>
            <Layers><Layer Name="Default"><Controls><Control Name="HotSpot_13" ClassId="0x00001003">
            <Property Name="VirtualKey" Value="Source[local].VirtualKey[LOGIN_LAYER]"/>
            <Property Name="StatusDatapoint" Value="Source[global].Variable[Local.Login_11_V]"/>
            <Property Name="KeyMode" Value="Immediate"/><Property Name="Left" Value="20"/>
            <Property Name="Top" Value="20"/><Property Name="Width" Value="100"/>
            <Property Name="Height" Value="40"/></Control></Controls></Layer>
            <LayerRef Source="Source[local].Layer[LOG_IN_OUT]">
            <Property Name="Z-Order" Value="2"/><Property Name="VisibilityMode" Value="Hidden"/>
            </LayerRef></Layers></Page>''',
    }
    for name, text in resources.items():
        target=plc_folder/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text,encoding='utf-8')
    globals_path=plc_folder/'Logical/Global.var'
    globals_path.write_text(globals_path.read_text(encoding='utf-8')+'\nVAR_GLOBAL\nLogin_11_V : USINT := 0;\nEND_VAR\n',encoding='utf-8')
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in plc_folder.rglob('*') if p.is_file()}
    created=primary.post('/api/virtual-plc/projects',json={'projectPath':str(plc_folder)})
    state=wait_ready(primary,created.json()['id']);path='/api/virtual-plc/projects/'+state['id']
    workspace=next(w for w in service.workspaces.values() if w.identity==state['id'])
    page=next(p for p in state['model']['hmi']['pages'] if p['name']=='MMS_CONFIG')
    hotspot=next(o for o in page['objects'] if o['name']=='HotSpot_13')
    back=next(o for o in page['objects'] if o['name']=='Button_1')
    layer=next(l for l in page['layers'] if l['name']=='LOG_IN_OUT')
    binding=layer['statusBinding']
    assert hotspot['actions'][0]['variable']==back['actions'][0]['variable']==binding
    assert hotspot['actions'][0]['value']=='0' and back['actions'][0]['value']=='1'
    assert workspace.runtime.get_value(binding)==1
    initial=primary.post(path+'/interface-values',json={'names':[],'pageId':page['id']}).json()
    assert not initial['layers'][layer['id']]['visible']
    for control,phase,value,visible in [(hotspot,'press',0,True),(hotspot,'release',0,True),
                                      (back,'press',1,False),(back,'release',1,False)]:
        response=primary.post(path+'/hmi-action',json={'pageId':page['id'],'objectId':control['id'],'phase':phase})
        assert response.status_code==200,response.text
        assert workspace.runtime.get_value(binding)==value
        assert response.json()['layers'][layer['id']]['visible']==visible
    # The hotspot has its own visibility word, independent of the layer word.
    workspace.runtime.set_value('Login_11_V',1,return_snapshot=False)
    assert primary.post(path+'/hmi-action',json={'pageId':page['id'],'objectId':hotspot['id'],'phase':'press'}).status_code==400
    assert workspace.runtime.get_value(binding)==1
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before}


def test_hmi_preview_is_a_separate_owned_workspace(client, plc_folder):
    primary, other, service=client
    source=plc_folder/'Logical/Main/Main.st'
    source.write_text("PROGRAM _CYCLIC IF Secret = '' THEN Secret := 'qa1'; END_IF; END_PROGRAM",encoding='utf-8')
    globals_path=plc_folder/'Logical/Global.var'
    globals_path.write_text(globals_path.read_text(encoding='utf-8')+'\nVAR_GLOBAL\nSecret : STRING[8];\nEND_VAR\n',encoding='utf-8')
    created=primary.post('/api/virtual-plc/projects',json={'projectPath':str(plc_folder)})
    parent=wait_ready(primary,created.json()['id']);path='/api/virtual-plc/projects/'+parent['id']
    workspace=next(w for w in service.workspaces.values() if w.identity==parent['id'])
    # Bind to a declared source writer; preview selection uses source IR, not names.
    page=workspace.model['hmi']['pages'][0]
    page['objects'].append({'id':'password','kind':'password','passwordLevelBinding':'@global:Counter','textGroup':'fixture'})
    workspace.model['hmi']['textSnippets']={'fixture':{'secret':{'classId':'0x00002002','binding':'@global:Secret'}}}
    service.store.save_model(workspace.owner,workspace.identity,workspace.model)
    assert other.post(path+'/hmi-preview',json={'pageId':page['id']}).status_code==404
    response=primary.post(path+'/hmi-preview',json={'pageId':page['id']})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['id']!=parent['id']
    assert result['model']['executionScope']['mode']=='hmi-preview'
    assert result['model']['executionScope']['completeMachineExecution'] is False
    assert workspace.runtime.scan_count==0


def test_module_help_auth_and_path_boundary(client):
    primary, _, _ = client
    response = primary.get('/api/virtual-plc/module-help', params={'q': 'X20DI9371'})
    assert response.status_code == 200, response.text
    assert response.json()['results'][0]['channelCount'] == 12
    assert primary.get('/api/virtual-plc/module-help/document', params={'path': '../../backend/app.py'}).status_code == 400
    guest = TestClient(primary.app)
    try:
        assert guest.get('/api/virtual-plc/module-help', params={'q': 'X20DI9371'}).status_code == 401
    finally:
        guest.close()


def test_source_snapshots_and_untrusted_imports_cannot_escape(tmp_path):
    store = WorkspaceStore(tmp_path / 'saved')
    model = project('A := A + 1;', [variable('A', retain=True)])
    model['files'] = [{'path': 'Logical/Main/Main.st'}]
    document = {'format': 'usopp-virtual-plc', 'schemaVersion': 1, 'model': model,
                'workspace': {'name': 'Saved PLC'}, 'sources': {'Logical/Main/Main.st': {'text': 'A := A + 1;', 'sha256': 'snapshot'}}}
    imported = store.import_document('alice', document)
    assert store.source('alice', imported['id'], 'Logical/Main/Main.st')['snapshot']
    with pytest.raises(FileNotFoundError):
        store.load('bob', imported['id'])
    for name in ('../secrets.txt', 'C:\\private.txt', '/etc/passwd', 'nested/../../secret', 'file:///private'):
        with pytest.raises(ValueError):
            relative_path(name)
    malicious = deepcopy(document)
    malicious['sources']['../secrets.txt'] = {'text': 'outside'}
    with pytest.raises(ValueError):
        store.import_document('alice', malicious)
    malformed = deepcopy(document)
    malformed['workspace']['settings'] = {'speed': 'unbounded'}
    with pytest.raises(ValueError):
        store.import_document('alice', malformed)
    malformed = deepcopy(document)
    malformed['workspace']['scenarios'] = [{'events': [{'name': 'A', 'timeMs': float('nan')}]}]
    with pytest.raises(ValueError):
        store.import_document('alice', malformed)


def test_reopen_retains_memory_and_running_is_explicit(tmp_path):
    service = VirtualPLCService(tmp_path)
    model = project('A := A + 1;', [variable('A', retain=True)])
    model['files'] = []
    model['symbolCaseSensitive'] = True  # This synthetic model has no source cache to migrate.
    document = service.store.create('alice', 'Retained memory')
    document['status'] = 'ready'
    identity = document['id']
    service.store.save_model('alice', identity, model)
    service.store.write('alice', identity, document)
    workspace = service.get('alice', identity)
    service.command(workspace, 'scan')
    assert workspace.runtime.memory.resolve('A', 'Main')['value'] == 1
    service.close()
    reopened = VirtualPLCService(tmp_path)
    try:
        workspace = reopened.get('alice', identity)
        assert workspace.runtime.status == 'stopped'
        assert workspace.runtime.memory.resolve('A', 'Main')['value'] == 1
        reopened.command(workspace, 'run')
        deadline = time.monotonic() + 2
        while workspace.runtime.scan_count < 2 and time.monotonic() < deadline:
            time.sleep(.02)
        reopened.command(workspace, 'pause')
        assert workspace.runtime.scan_count >= 2
    finally:
        reopened.close()


def test_chopper_failure_leaves_simulation_usable(monkeypatch):
    from virtual_plc.core.chopper import answer
    from backend.core import assist_model
    monkeypatch.setattr(assist_model, 'configuration', lambda: {'provider': 'embedded'})
    monkeypatch.setattr(assist_model, 'chat_model', lambda *a, **k: (_ for _ in ()).throw(ValueError('Model unavailable')))
    model = project('A := A + 1;', [variable('A')])
    runtime = VirtualRuntime(model)
    result = answer(model, runtime.snapshot(), 'Why is A zero?', 'alice')
    assert result['modelNotice']
    assert result['evidence'][0]['file'] == 'Logical/Main/Main.st'
    runtime.command('scan')
    assert runtime.memory.resolve('A', 'Main')['value'] == 1


def test_nested_hmi_memory_and_bounded_public_snapshots():
    declarations = [variable('Value' + str(index), initial=index) for index in range(1005)]
    declarations.extend([variable('Samples', 'ARRAY [-1..1] OF DINT', [3, 4, 5]),
                         variable('Large', 'ARRAY [0..99] OF DINT', list(range(100)))])
    model = project('Value0 := Value0 + 1;', declarations)
    model['hmi'] = {'pages': [{'objects': [{'binding': 'Samples[0]'}, {'binding': 'Value1004'}]}]}
    runtime = VirtualRuntime(model)
    runtime._budget = 123
    runtime.set_value('Samples[0]', 22)
    assert runtime.get_value('Samples[0]') == 22
    assert runtime._budget == 123
    with pytest.raises(ValueError):
        runtime.set_value('Samples[0]', 1, force=True)
    with pytest.raises(ValueError):
        runtime.get_value('Samples[UnknownCall()]')
    view = runtime_view(runtime)
    assert len(view['variables']) == 1000 and view['variablesTotal'] == 1007
    assert len(view['memory']) <= 1002
    assert view['memory']['Samples[0]'] == 22
    assert view['memory']['Value1004'] == 1004
    watched = runtime_view(runtime, ['Main::Large'])
    large = next(row for row in watched['variables'] if row['name'] == 'Large')
    assert large['valueTruncated'] and len(large['value']) == 32
    assert len(runtime.memory.resolve('Large')['value']) == 100


def test_hmi_status_layer_and_login_bindings_survive_variable_pagination():
    declarations = [variable('Value' + str(index), initial=index) for index in range(1010)]
    model = project('Value0 := Value0 + 1;', declarations)
    model['hmi'] = {'pages': [{'objects': [{'statusBinding': 'Value1004',
        'lockingBinding': 'Value1005', 'passwordLevelBinding': 'Value1006',
        'textIndexBinding': 'Value1007', 'layerState': {'statusBinding': 'Value1008'}}]}]}
    view = runtime_view(VirtualRuntime(model))
    assert len(view['variables']) == 1000
    for index in range(1004,1009):
        assert view['memory']['Value' + str(index)] == index


def test_empty_task_slots_and_scenario_switch_are_explicit(tmp_path):
    model = project('A := A + 1;', [variable('A')])
    model['tasks'].append({'id': 'Unused', 'name': 'Unused cyclic class', 'intervalMs': 20,
                           'assignments': [], 'programs': [], 'enabled': True})
    runtime = VirtualRuntime(model)
    assert runtime.run_allowed
    assert any(row['code'] == 'TASK_EMPTY' and row['excluded'] for row in runtime.diagnostics)
    service = VirtualPLCService(tmp_path)
    document = service.store.create('alice', 'Scenarios')
    document['status'] = 'ready'
    service.store.save_model('alice', document['id'], model)
    service.store.write('alice', document['id'], document)
    workspace = service.get('alice', document['id'])
    workspace.document['settings']['activeScenario'] = 'first'
    workspace.scenario_cursor = 12
    service.update(workspace, {'settings': {'activeScenario': 'second'}})
    assert workspace.scenario_cursor == 0
    service.close()
