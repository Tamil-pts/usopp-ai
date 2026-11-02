import hashlib
from virtual_plc.tests.test_workspace_api import client, plc_folder, wait_ready


def test_context_api_shares_runtime_values_without_executing_or_changing_source(client,plc_folder,monkeypatch):
    primary,other,service=client
    from backend.core import assist_model
    monkeypatch.setattr(assist_model,'configuration',lambda:{'provider':'local'})
    before={p.relative_to(plc_folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in plc_folder.rglob('*') if p.is_file()}
    created=primary.post('/api/virtual-plc/projects',json={'projectPath':str(plc_folder),'name':'Machine identity fixture'})
    assert created.status_code==200,created.text
    identity=created.json()['id'];base='/api/virtual-plc/projects/'+identity
    ready=wait_ready(primary,identity)
    workspace=next(w for w in service.workspaces.values() if w.identity==identity)
    assert 'machineContext' not in service.store.model(workspace.owner,identity)
    response=primary.get(base+'/machine-context',params={'q':'Start'})
    assert response.status_code==200,response.text
    context=response.json()
    assert context['activeConfiguration']=='Config1'
    assert context['roots']==['@global:Start']
    assert context['runtime']['values']['@global:Start'] is False
    assert context['runtime']['mode']=='virtual simulation'
    assert not context['completeMachineSequence']
    assert other.get(base+'/machine-context').status_code in {403,404}
    answer=primary.post(base+'/chopper',json={'question':'Explain Start'})
    assert answer.status_code==200,answer.text
    assert answer.json()['machineContext']['roots']==['@global:Start']
    after=primary.get(base).json()
    assert after['runtime']['timeMs']==ready['runtime']['timeMs']
    assert after['runtime']['scanCount']==ready['runtime']['scanCount']
    assert before=={p.relative_to(plc_folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in plc_folder.rglob('*') if p.is_file()}


def test_saved_workspace_builds_missing_context_from_its_cached_sources(client,plc_folder):
    primary,_,service=client
    identity=primary.post('/api/virtual-plc/projects',json={'projectPath':str(plc_folder)}).json()['id']
    wait_ready(primary,identity)
    workspace=next(w for w in service.workspaces.values() if w.identity==identity)
    workspace.model.pop('machineContext',None)
    # A saved snapshot must not need the physical controller or re-run startup.
    context=primary.get('/api/virtual-plc/projects/'+identity+'/machine-context',params={'q':'Start'})
    assert context.status_code==200,context.text
    assert context.json()['roots']==['@global:Start']


def test_linked_runtime_status_uses_hide_and_lock_bits_and_parent_layer(client,plc_folder):
    primary,_,_=client
    cpu=plc_folder/'Physical/Config1/PLC1/CPU.sw'
    cpu.write_text(cpu.read_text().replace('</SwConfiguration>','<VcDataObject Name="Panel" Source="Panel.dob"/></SwConfiguration>'))
    folder=plc_folder/'Logical/Panel/Pages';folder.mkdir(parents=True)
    (folder.parent/'VCObject.vc').write_text('<VisualComponents><Visualization Name="Panel"/></VisualComponents>')
    (folder/'Settings.page').write_text('''<Page Name="Settings"><Property Name="Width" Value="320"/><Property Name="Height" Value="240"/>
<Layers><Layer Name="Default"><Property Name="StatusDatapoint" Value="Source[global].Variable[Local.Start]"/>
<Controls><Control Name="CounterStatus" ClassId="0x00001006"><Property Name="ValueDatapoint" Value="Source[global].Variable[Local.Counter]"/>
<Property Name="StatusDatapoint" Value="Source[global].Variable[Local.Counter]"/></Control></Controls></Layer></Layers></Page>''')
    identity=primary.post('/api/virtual-plc/projects',json={'projectPath':str(plc_folder)}).json()['id']
    wait_ready(primary,identity);base='/api/virtual-plc/projects/'+identity
    def state():
        response=primary.get(base+'/machine-context',params={'q':'Counter'})
        assert response.status_code==200,response.text
        return next(v for k,v in response.json()['runtime']['controls'].items() if k.endswith(':CounterStatus') or 'CounterStatus' in k)
    assert state()['visible'] and not state()['locked']
    assert primary.post(base+'/values',json={'name':'@global:Counter','value':2,'force':True}).status_code==200
    assert state()['visible'] and state()['locked']
    assert primary.post(base+'/values',json={'name':'@global:Counter','value':3,'force':True}).status_code==200
    assert not state()['visible'] and state()['locked']
    primary.post(base+'/values',json={'name':'@global:Counter','value':0,'force':True})
    primary.post(base+'/values',json={'name':'@global:Start','value':True,'force':True})
    assert not state()['visible']
