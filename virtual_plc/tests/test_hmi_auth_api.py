import json

from virtual_plc.core.service import Workspace
from virtual_plc.tests.test_hmi_auth import login_fixture
from virtual_plc.tests.test_workspace_api import client


def workspace_for(primary,service,secret=''):
    from backend.core import accounts
    user=accounts.store.user_for_token(primary.cookies.get(accounts.COOKIE))
    model,page,control,runtime=login_fixture(secret)
    owner=str(user['id'])
    document=service.store.create(owner,'Scheduled HMI login')
    document['status']='ready'
    workspace=Workspace(owner,document['id'],document,model=model,runtime=runtime)
    service.workspaces[(owner,document['id'])]=workspace
    return workspace,page,control


def test_one_input_initializes_scheduled_sources_and_sets_level_and_caption(client):
    primary,_,service=client
    workspace,page,control=workspace_for(primary,service)
    response=primary.post('/api/virtual-plc/projects/'+workspace.identity+'/hmi-action',json={
        'pageId':page['id'],'objectId':control['id'],'phase':'input','value':'400'})
    assert response.status_code==200,response.text
    assert response.json()['loginLevel']==4
    assert workspace.runtime.get_value('Caption')=='4th level'
    assert workspace.runtime.status=='paused'
    assert '400' not in json.dumps(response.json())
    saved=json.loads((service.store.folder(workspace.owner,workspace.identity)/'state.json').read_text())
    assert saved['memory']['Main::Secret']=='400'


def test_password_is_not_hardcoded_and_blank_request_does_not_start_plc(client):
    primary,_,service=client
    workspace,page,control=workspace_for(primary,service,'retained-test')
    url='/api/virtual-plc/projects/'+workspace.identity+'/hmi-action'
    body={'pageId':page['id'],'objectId':control['id'],'phase':'input','value':''}
    response=primary.post(url,json=body)
    assert response.status_code==400
    assert workspace.runtime.time_ms==0
    body['value']='400'
    response=primary.post(url,json=body)
    assert response.status_code==200 and response.json()['loginLevel']==0
    assert workspace.runtime.get_value('Secret')=='retained-test'
    body['value']='retained-test'
    response=primary.post(url,json=body)
    assert response.status_code==200 and response.json()['loginLevel']==4


def test_explicit_preparation_never_authenticates(client):
    primary,_,service=client
    workspace,page,control=workspace_for(primary,service)
    response=primary.post('/api/virtual-plc/projects/'+workspace.identity+'/hmi-password/prepare',json={
        'pageId':page['id'],'objectId':control['id']})
    assert response.status_code==200,response.text
    assert response.json()['passwordSources'][control['id']]['waitingLevels']==[]
    assert workspace.runtime.get_value('Level')==0
    assert workspace.runtime.status=='paused'


def test_source_init_cannot_reset_a_successfully_compared_retained_password(client):
    from virtual_plc.core.runtime import VirtualRuntime
    primary,_,service=client
    workspace,page,control=workspace_for(primary,service,'400')
    workspace.model['programs'][0]['code']="PROGRAM _INIT\nLevel := 0;\nEND_PROGRAM\nPROGRAM _CYCLIC\n"+workspace.model['programs'][0]['code']+'\nEND_PROGRAM'
    workspace.runtime=VirtualRuntime(workspace.model)
    response=primary.post('/api/virtual-plc/projects/'+workspace.identity+'/hmi-action',json={
        'pageId':page['id'],'objectId':control['id'],'phase':'input','value':'400'})
    assert response.status_code==200,response.text
    assert response.json()['loginLevel']==4
    assert workspace.runtime.get_value('Caption')=='4th level'
