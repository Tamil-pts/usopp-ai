import asyncio
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import project_intelligence as pi
from backend.core.run_history import current_user
from python_engine.engineering_model import build, EngineeringModel


@pytest.fixture
def reference(tmp_path,monkeypatch):
    monkeypatch.setattr(pi,'WORK',tmp_path/'work')
    root=tmp_path/'reference';root.mkdir()
    sources={
      'LastUser.set':'<Settings><ConfigurationManager ActiveConfigurationName="CFG"/></Settings>',
      'Physical/CFG/PLC1/Cpu.sw':'<Cpu><TaskClass Name="Cyclic#2" CycleTime="20"><Task Name="ScheduledMachine" Source="Drive.prg"/><Task Name="Second" Source="Other.prg" Disabled="true"/></TaskClass></Cpu>',
      'Physical/ALT/PLC1/Cpu.sw':'<Cpu><Task Name="Alternate" Source="Other.prg"/></Cpu>',
      'Logical/Drive/IEC.prg':'<Program><Files><File>Cyclic.st</File><File>Init.st</File><File>Rung.ld</File><File Private="true">Local.var</File></Files></Program>',
      'Logical/Other/IEC.prg':'<Program><Files><File>Main.ab</File><File Private="true">Local.var</File></Files></Program>',
      'Logical/Drive/Local.var':'VAR\nLocalEnable : BOOL;\nDelay : FBDelay;\nEND_VAR',
      'Logical/Other/Local.var':'VAR\nLocalEnable : BOOL;\nEND_VAR',
      'Logical/Global.var':'VAR_GLOBAL\nStart : BOOL;\nFault : BOOL;\nMotor : BOOL;\nState : UINT;\nEND_VAR',
      'Logical/Drive/Init.st':'PROGRAM _INIT\nMotor := FALSE;\nEND_PROGRAM',
      'Logical/Drive/Cyclic.st':'PROGRAM _CYCLIC\nDelay(IN := Start);\nIF LocalEnable AND NOT Fault THEN\nMotor := TRUE;\nEND_IF\nCASE State OF\n0:\nIF Start THEN\nState := 10;\nEND_IF\n10:\nIF Fault THEN\nState := 0;\nEND_IF\nEND_CASE\nEND_PROGRAM',
      'Logical/Drive/Rung.ld':'PROGRAM _CYCLIC\n<networks><network><row><contact type="open" name="Start"/><contact type="closed" name="Fault"/><coil type="open" name="Motor"/></row></network></networks>\nEND_PROGRAM',
      'Logical/Other/Main.ab':'PROGRAM _CYCLIC\nIF LocalEnable THEN\nMotor = 0\nENDIF\nEND_PROGRAM',
      'Logical/Unassigned/main.st':'PROGRAM _CYCLIC\nMotor := TRUE;\nEND_PROGRAM',
      'Logical/Library/Delay.st':'FUNCTION_BLOCK FBDelay\nVendorClock();\nIF IN THEN\nTEMP := TRUE;\nEND_IF\nEND_FUNCTION_BLOCK',
      'Logical/Library/Types.fun':'FUNCTION_BLOCK FBDelay\nVAR_INPUT\nIN : BOOL;\nEND_VAR\nVAR\nTEMP : BOOL;\nEND_VAR\nEND_FUNCTION_BLOCK\nFUNCTION_BLOCK OtherFB\nVAR\nTEMP : BOOL;\nEND_VAR\nEND_FUNCTION_BLOCK',
      'Logical/HMI/Start.page':'<Page><Control Name="StartButton"><Property Name="ValueDatapoint" Value="::PLC.Variable[Start]"/></Control></Page>',
      'Physical/CFG/PLC1/IoMap.iom':'Motor AT %QX0.0;\n',
      'Physical/ALT/PLC1/IoMap.iom':'Motor AT %QX0.1;\n',
      'Temp/Generated.st':'PROGRAM _CYCLIC\nBogus := TRUE;\nEND_PROGRAM',
      'manual.xyz':'opaque unsupported resource',
    }
    for relative,text in sources.items():
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    index=pi.Index(root,'engineer');index.build()
    return index


def test_build_accounts_for_sources_and_preserves_originals(reference):
    before={p.relative_to(reference.root).as_posix():p.read_bytes() for p in reference.root.rglob('*') if p.is_file()}
    summary=build(reference);counts=summary['counts']
    assert summary['validation']['structurallyValid']
    assert summary['validation']['activeExecutionContexts']==1
    assert summary['validation']['reachableRoutineBlocks']==4
    assert summary['validation']['unreachableOrUnassignedRoutineBlocks']>=2
    assert not summary['automaticChatEnabled'] and not summary['runtimeSimulated']
    assert counts['files']['excluded-generated']==1 and counts['files']['unsupported']==1
    assert sum(counts['files'].values())==len(before)
    assert summary['sourceTokens']>100
    assert counts['relations']['READS']>0 and counts['relations']['WRITES']>0 and counts['relations']['TRANSITIONS']==2
    assert counts['relations']['BINDS_INPUT']==1 and counts['relations']['NEXT_IN_SOURCE']>0
    assert before=={p.relative_to(reference.root).as_posix():p.read_bytes() for p in reference.root.rglob('*') if p.is_file()}


def test_task_entries_come_from_cpu_and_manifest_not_main_name(reference):
    build(reference);model=EngineeringModel(reference)
    flow=model.execution_flow()
    assert len(flow['contexts'])==1
    context=flow['contexts'][0]
    assert context['task']['name']=='ScheduledMachine'
    assert context['task']['properties']['taskClass']=='Cyclic#2'
    assert context['task']['properties']['timing']['CycleTime']=='20'
    files={r['file'] for r in context['entryRoutines']}
    assert files=={'Logical/Drive/Init.st','Logical/Drive/Cyclic.st','Logical/Drive/Rung.ld'}
    phases={r['properties']['phase'] for r in context['entryRoutines']}
    assert phases=={'initialization','cyclic'}
    assert not flow['completeMachineSequence']
    assert context['reachableCalls']


def test_private_program_and_function_template_tags_stay_separate(reference):
    build(reference);model=EngineeringModel(reference)
    tags=model.blocks(kind='variable',q='LocalEnable')['items']
    assert len(tags)==2 and len({t['scope'] for t in tags})==2
    assert not model.trace_signal('LocalEnable')['resolved']
    for tag in tags:
        trace=model.trace_signal(tag['id'])
        other=next(t for t in tags if t['id']!=tag['id'])
        assert other['id'] not in {b['id'] for b in trace['blocks']}
    temps=model.blocks(kind='variable',q='TEMP')['items']
    assert {t['scope'] for t in temps}=={'callable:FBDelay','callable:OtherFB'}
    calls=model.relations(kind='INSTANCE_OF')['items']
    assert calls and model.block(calls[0]['target'])['kind']=='function_block'


def test_layers_trace_and_token_pages_are_independently_inspectable(reference):
    build(reference);model=EngineeringModel(reference)
    assert model.relations(kind='BINDS_TO')['total']==1
    assert model.relations(kind='MAPS_TO')['total']==2
    hardware=model.blocks(kind='io_channel')['items']
    assert {h['properties']['active'] for h in hardware}=={True,False}
    assert {h['properties']['logicalAddress'] for h in hardware}=={'%QX0.0','%QX0.1'}
    trace=model.trace_signal('Motor',limit=100)
    assert trace['resolved'] and not trace['runtimeValuesSupplied']
    assert any(e['kind']=='CONTROLS' and 'NOT Fault' in e['properties'].get('expression','') for e in trace['relationships'])
    first=model.tokens('Logical/Drive/Cyclic.st',limit=4)
    second=model.tokens('Logical/Drive/Cyclic.st',offset=first['nextOffset'],limit=4)
    assert first['items'][0]['line']==1
    assert not {r['ordinal'] for r in first['items']}&{r['ordinal'] for r in second['items']}
    routines=model.blocks(kind='routine')['items']
    assert all('ir' not in r['properties'] for r in routines)
    assert model.block(routines[0]['id'],include_ir=True)['properties']['ir']


def test_validation_reports_semantic_gaps_without_pretending_completeness(reference):
    build(reference);report=EngineeringModel(reference).validate(limit=1)
    assert report['structurallyValid'] and report['unresolvedChecks']>0
    assert not report['safeForAutomaticMachineClaims'] and not report['completeMachineUnderstanding']
    assert len(report['issues'])==1 and report['nextOffset']==1


def test_stale_sources_reject_queries_and_failed_build_retains_previous_model(reference):
    build(reference);model=EngineeringModel(reference);before=model.path.read_bytes()
    (reference.root/'Logical/Drive/Init.st').write_text('PROGRAM _INIT\nMotor := TRUE;\nEND_PROGRAM')
    with pytest.raises(ValueError,match='Source changed'):model.structure()
    with pytest.raises(ValueError,match='Refresh the index'):build(reference)
    assert before==model.path.read_bytes()


def test_new_source_invalidates_model_even_without_refreshing_search_index(reference):
    build(reference);model=EngineeringModel(reference)
    (reference.root/'Logical/Drive/NewRoutine.st').write_text('PROGRAM _CYCLIC\nMotor := FALSE;\nEND_PROGRAM')
    with pytest.raises(ValueError,match='inventory changed'):model.structure()


def test_routine_interfaces_and_function_block_ports_are_linked_to_scoped_symbols(reference):
    build(reference);model=EngineeringModel(reference)
    routine=model.blocks(kind='function_block',q='FBDelay')['items'][0]
    interface=model.block(routine['id'])['properties']['interface']
    ports=[model.block(identifier) for identifier in interface['declaredPorts']]
    assert [(port['name'],port['properties']['declarationRole']) for port in ports]==[('IN','input')]
    assert interface['inputs'] and interface['outputs']


def test_block_comparison_and_stable_ids(reference):
    build(reference);model=EngineeringModel(reference)
    assert model.compare(model)['counts']=={'added':0,'removed':0,'modified':0}
    ids={b['id'] for b in model.blocks(kind='routine')['items']}
    build(reference)
    assert ids=={b['id'] for b in model.blocks(kind='routine')['items']}


def test_comparison_detects_code_and_binding_changes(reference,tmp_path):
    import shutil
    build(reference);before=EngineeringModel(reference)
    root=tmp_path/'revision2';shutil.copytree(reference.root,root)
    (root/'Logical/Drive/Init.st').write_text('PROGRAM _INIT\nMotor := TRUE;\nEND_PROGRAM')
    other=pi.Index(root,'engineer');other.build();build(other)
    changes=before.compare(EngineeringModel(other))
    assert changes['counts']['modified']>0
    assert changes['relationshipCounts']['added']>0 and changes['relationshipCounts']['removed']>0


def test_authenticated_api_and_mcp_use_actual_model_and_owner_boundary(reference,monkeypatch):
    from backend.api import project_intelligence as api
    from backend.core import mcp_tools
    app=FastAPI();app.include_router(api.router)
    @app.middleware('http')
    async def session(request,call_next):
        user={'id':request.headers.get('test-user','engineer'),'role':'user'}
        request.state.user=user;token=current_user.set(user)
        try:return await call_next(request)
        finally:current_user.reset(token)
    with TestClient(app) as client:
        assert client.post(f'/api/assist/projects/{reference.key}/engineering-model/build').status_code==200
        assert client.get(f'/api/assist/projects/{reference.key}/engineering-model').json()['validation']['structurallyValid']
        assert client.get(f'/api/assist/projects/{reference.key}/engineering-model',headers={'test-user':'outsider'}).status_code==409
        assert client.get(f'/api/assist/projects/{reference.key}/engineering-model/trace',params={'signal':'Motor'}).json()['resolved']
    token=current_user.set({'id':'engineer'})
    try:
        async def mcp_call():
            tools=await mcp_tools.server.list_tools()
            assert {'get_project_structure','get_function_block','validate_graph','get_execution_flow'}<={t.name for t in tools}
            result=await mcp_tools.server.call_tool('get_project_structure',{'project_id':reference.key})
            return result
        result=asyncio.run(mcp_call())
        assert result
        assert mcp_tools.validate_graph(reference.key)['structurallyValid']
    finally:current_user.reset(token)


def test_actual_mcp_jsonrpc_transport_exposes_account_bound_graph(reference):
    from contextlib import asynccontextmanager
    from backend.core import mcp_tools
    build(reference)
    @asynccontextmanager
    async def lifespan(app):
        async with mcp_tools.server.session_manager.run():yield
    app=FastAPI(lifespan=lifespan);app.mount('/api/mcp',mcp_tools.http_app)
    @app.middleware('http')
    async def account(request,call_next):
        token=current_user.set({'id':request.headers.get('test-user','engineer')})
        try:return await call_next(request)
        finally:current_user.reset(token)
    headers={'accept':'application/json, text/event-stream'}
    with TestClient(app,base_url='http://127.0.0.1:8200') as client:
        initialized=client.post('/api/mcp/',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'architecture-regression','version':'1'}}})
        assert initialized.status_code==200,initialized.text
        payload={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'get_project_structure','arguments':{'project_id':reference.key}}}
        result=client.post('/api/mcp/',headers=headers,json=payload)
        assert result.status_code==200,result.text
        assert not result.json()['result'].get('isError')
        response_payload=result.json()['result']
        structured=response_payload.get('structuredContent') or json.loads(''.join(item.get('text','') for item in response_payload['content']))
        assert structured['validation']['structurallyValid']
        denied=client.post('/api/mcp/',headers={**headers,'test-user':'outsider'},json=payload)
        assert denied.json()['result']['isError']
        linked={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'get_machine_context','arguments':{'project_id':reference.key,'question':'Motor','limit':10}}}
        result=client.post('/api/mcp/',headers=headers,json=linked)
        assert result.status_code==200,result.text
        response_payload=result.json()['result']
        assert not response_payload.get('isError'),response_payload
        data=response_payload.get('structuredContent') or json.loads(''.join(item.get('text','') for item in response_payload['content']))
        assert data['roots']==['@global:Motor'] and not data['completeMachineSequence']
        denied=client.post('/api/mcp/',headers={**headers,'test-user':'outsider'},json=linked)
        assert denied.json()['result']['isError']


def test_empty_ladder_init_is_still_an_individual_routine(reference):
    (reference.root/'Logical/Drive/Empty.ld').write_text('PROGRAM _INIT\n<networks></networks>\nEND_PROGRAM')
    reference.build();build(reference)
    rows=EngineeringModel(reference).blocks(kind='routine',file='Logical/Drive/Empty.ld')['items']
    assert len(rows)==1 and rows[0]['properties']['phase']=='initialization'
    assert EngineeringModel(reference).block(rows[0]['id'],True)['properties']['ir']==[]
