import itertools
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import assist
from backend.core import project_assistant as pa, project_intelligence as pi, assist_training
from backend.core.engineering_question import plan, answer, Trace
from backend.core.run_history import current_user
from python_engine.compare import _ladder_networks
from python_engine.ladder_model import coil_condition
from python_engine.machine_function_engine import analyze


def rung(rows):
    return 'PROGRAM _CYCLIC\n<networks><network commented="0">' + ''.join('<row>'+row+'</row>' for row in rows) + '</network></networks>\nEND_PROGRAM'


def test_ladder_parallel_branch_matches_truth_table_and_excludes_side_timer():
    text = rung([
        '<contact type="open" name="Permit"/><contact type="open" name="Mode"/><line/><contact type="closed" name="Fault"/><coil type="open" name="Motor"/>',
        '<empty or="true"/><empty/><empty or="true"/><empty/><empty/>',
        '<empty or="true"/><contact type="closed" name="Mode"/><contact type="closed" name="Cutting" or="true"/><empty/><empty/>'
    ])
    result = coil_condition(_ladder_networks(text)[0]['diagram'], 'Motor')
    assert result['resolved'] and 'OR' in result['expression'] and 'NOT Fault' in result['expression']
    expression = result['expression'].replace(' AND ', ' and ').replace(' OR ', ' or ').replace('NOT ', 'not ')
    for permit, mode, cutting, fault in itertools.product((False, True), repeat=4):
        actual = eval(expression, {'__builtins__': {}}, dict(Permit=permit, Mode=mode, Cutting=cutting, Fault=fault))
        assert actual == (permit and (mode or (not mode and not cutting)) and not fault)


def test_unsupported_blocks_and_edge_contacts_do_not_become_guessed_conditions():
    for instruction in ('positive transition', 'negative transition', 'unknown'):
        diagram = _ladder_networks(rung([f'<contact type="{instruction}" name="Edge"/><coil type="set" name="Motor"/>']))[0]['diagram']
        result = coil_condition(diagram, 'Motor')
        assert not result['resolved'] and 'expression' not in result


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(pi, 'WORK', tmp_path/'indexes')
    root = tmp_path/'project'; root.mkdir()
    (root/'Control.ld').write_text(rung(['<contact type="open" name="Ready"/><contact type="closed" name="Fault"/><coil type="open" name="DO_CAN_CHANGER_MOTOR"/>']))
    (root/'Init.st').write_text('PROGRAM _INIT\nDO_CAN_CHANGER_MOTOR := FALSE;\nEND_PROGRAM')
    (root/'Upstream.st').write_text('PROGRAM _CYCLIC\nIF Start THEN\nReady := TRUE;\nEND_IF\nEND_PROGRAM')
    (root/'USB.st').write_text('PROGRAM _CYCLIC\nah_open_stage := 4;\nDI_FEED_SENSOR := TRUE;\nEND_PROGRAM')
    index = pi.Index(root, 'trace-test'); index.build()
    machine = analyze(index)
    monkeypatch.setattr(pa, 'opened', lambda *args: index)
    return index, machine


def test_real_chat_route_uses_complete_writers_and_rejects_unrelated_model_claims(workspace, monkeypatch):
    index, machine = workspace
    monkeypatch.setattr(pa, 'chat_model', lambda *a, **k: pytest.fail('Unverified model claims must not enter a static output trace'))
    app = FastAPI(); app.include_router(assist.router)
    @app.middleware('http')
    async def context(request, call_next):
        user={'id': 'trace-test', 'role': 'user'}; request.state.user=user; token=current_user.set(user)
        try: return await call_next(request)
        finally: current_user.reset(token)
    monkeypatch.setattr(assist_training, '_initialize', lambda: pytest.fail('Partial answers must not create training records'))
    with TestClient(app) as client:
        response = client.post('/api/assist', json={'question': 'What conditions are required before the can changer motor starts?', 'context': {'intelligenceProjectId': index.key}})
    assert response.status_code == 200, response.text
    result = response.json(); check = result['engineeringVerification']
    assert check['target'] == 'DO_CAN_CHANGER_MOTOR' and check['conditionsEstablished']
    writers = [p for p in check['proofs'] if p['depth']==0]
    assert len(writers)==2 and any(p.get('value')=='FALSE' for p in writers)
    assert any('Ready AND NOT Fault' in p.get('expression', '') for p in writers)
    assert not check['runtimeObserved'] and not check['trainingEligible']
    assert 'DI_FEED_SENSOR' not in result['answer'] and 'USB.st' not in json.dumps(result['machineAnalysis'])
    assert not result.get('trainingExampleId')
    assert result['retrieval']['coverage']['modelSuppliedFiles']==0
    assert result['retrieval']['coverage']['modelSuppliedSections']==0
    assert result['retrieval']['coverage']['relevantFunctionsDiscovered']==3
    assert index.snapshot()['indexedFiles']==4


def test_output_candidates_require_identity_not_top_one_guess():
    machine={'signalWrites':[{'name':'DO_CAN_CHANGER_MOTOR'},{'name':'DO_CAN_CHANGER_MOTOR_2'}]}
    out=plan('What conditions are required before the can changer motor starts?', machine)
    assert out['ambiguous'] and len(out['candidates'])==2
    machine['hardwareLinks']=[{'variable':'do_can_changer_motor','address':'%QX.Output','ownership':'active configuration'}]
    out=plan('What conditions are required before the can changer motor starts?', machine)
    assert out['candidates']==['DO_CAN_CHANGER_MOTOR'] and out['resolution']['alternatives']==['DO_CAN_CHANGER_MOTOR_2']


def test_plans_separate_function_machine_mapping_and_troubleshooting():
    m={'signalWrites':[{'name':'DO_CAN_CHANGER_MOTOR'}], 'hmiLinks':[{'signal':'do_can_changer_motor'}]}
    assert plan('Explain the complete machine working sequence',m)['kind']=='whole-machine'
    assert plan('Explain the doffing sequence',m)['kind']=='function-sequence'
    assert plan('Trace HMI binding do_can_changer_motor',m)['kind']=='mapping'
    assert plan('Why is the can changer motor not turning ON?',m)['kind']=='troubleshooting'


def test_changed_source_cannot_reuse_cached_condition_proof(workspace):
    index,machine=workspace
    (index.root/'Control.ld').write_text(rung(['<contact type="open" name="Different"/><coil type="open" name="DO_CAN_CHANGER_MOTOR"/>']))
    result=answer(index,'Trace DO_CAN_CHANGER_MOTOR',machine,plan('Trace DO_CAN_CHANGER_MOTOR',machine))
    assert not result['engineeringVerification']['conditionsEstablished']
    assert any('changed since indexing' in message for message in result['engineeringVerification']['unresolved'])


def test_case_distinct_and_local_scope_writers_are_not_merged(workspace):
    index,machine=workspace
    trace=Trace(index,{**machine,'signalWrites':[
        {'name':'TEMP','file':'Control.ld'}, {'name':'Temp','file':'USB.st'}, {'name':'TEMP','file':'Libraries/Block.st'}]})
    trace.declarations=[{'display':'TEMP','scope':'libraries','file':'Libraries/Local.var'}]
    assert trace.writers('TEMP','Control.ld')==[{'name':'TEMP','file':'Control.ld'}]


def test_training_gate_precedes_database_access(monkeypatch):
    monkeypatch.setattr(assist_training,'_initialize',lambda:pytest.fail('No training DB write expected'))
    for status in ('partial','unresolved','rejected'):
        assert assist_training.capture({'id':1},'Question',{'engineeringVerification':{'status':status,'trainingEligible':False},'answer':'Wrong','evidence':[{'file':'Main.st'}]},'Project') is None


def test_c_writer_keeps_all_if_else_conditions(workspace):
    index,_=workspace
    (index.root/'Control.c').write_text('void Main(){if (Run && !Fault) {Motor = 1;} else {Motor = 0;}}')
    index.build(); machine=analyze(index)
    result=answer(index,'Trace Motor',machine,plan('Trace Motor',machine))
    proofs=result['engineeringVerification']['proofs']
    assert len([p for p in proofs if p['depth']==0])==2
    assert all(p['resolved'] for p in proofs if p['depth']==0)
    assert any('NOT' in p.get('expression','') for p in proofs)


def test_else_proof_includes_the_original_if_condition(workspace):
    index,_=workspace
    (index.root/'Else.st').write_text('PROGRAM _CYCLIC\nIF Enable THEN\nBranchMotor := TRUE;\nELSE\nBranchMotor := FALSE;\nEND_IF\nEND_PROGRAM')
    index.build();machine=analyze(index)
    result=answer(index,'Trace BranchMotor',machine,plan('Trace BranchMotor',machine))
    for proof in result['engineeringVerification']['proofs']:
        if proof['depth']==0:
            source=next(e for e in result['evidence'] if e['sourceId']==proof['sourceId'])
            assert 'IF Enable THEN' in source['excerpt'] and 'END_IF' in source['excerpt']


def test_project2_real_motor_reference_when_project_is_available():
    root=Path(__file__).resolve().parents[2]/'project 2'
    key='7e92a2d2d17ce2286c73b90aee7c074844a2f60eaa35df8c7e96bfdd2c39bf1b'
    path=pi.WORK/'chopper_intelligence'/key/'project.sqlite3'
    if not root.is_dir() or not path.is_file():pytest.skip('Local Project 2 reference/index is not installed')
    index=pi.Index.__new__(pi.Index);index.root=root.resolve();index.path=path;index.key=key;index.owner='reference-check'
    machine=analyze(index);question='What conditions are required before the can changer motor starts?'
    result=answer(index,question,machine,plan(question,machine));v=result['engineeringVerification']
    assert v['target']=='DO_CAN_CHANGER_MOTOR' and v['conditionsEstablished'] and not v['runtimeObserved']
    direct=[p for p in v['proofs'] if p['depth']==0]
    assert len(direct)==1 and direct[0]['network']==23 and direct[0]['coilLine']==458
    assert set(direct[0]['inputs'])=={'M501','hmi_sliver_cutting_device_toggle','SLIVER_CUTTING_ENABLE','DI_EMERGENCY_OFF_LHS','DI_EMERGENCY_OFF_RHS','DELAY','M1236','EMERGENCY_PB_PRESSED','ALARM_BIT_SAFETY_SWITCH_OFF','TEMP','SLOW_SPEED_FOR_DOFF_SCD'}
    assert ' OR ' in direct[0]['expression'] and 'NOT SLIVER_CUTTING_ENABLE' in direct[0]['expression']
    assert 'ah_open_stage' not in json.dumps(result['machineAnalysis'])
    assert v['status']=='partial' and not v['trainingEligible']
    assert result['retrieval']['coverage']['indexedFiles']==887


def test_broad_answer_does_not_publish_unverified_model_summary(workspace,monkeypatch):
    index,_=workspace
    from backend.core import engineering_analysis
    def unverified(*args,**kwargs):
        evidence=index.retrieve('Review project source operations')['evidence']
        return {'answer':'[S1] The motor starts because DI_FEED_SENSOR is ON.',
                'response':{'model':'fixture'},'evidence':evidence,'retrievedEvidence':evidence,
                'retrieval':{'coverage':{'analyzedFiles':1,'modelSuppliedFiles':1,'remainingSections':1}},
                'notices':[],'modelNotice':None,'contextUsage':None}
    monkeypatch.setattr(engineering_analysis,'run',unverified)
    result=pa.answer({'question':'Explain the complete machine working sequence','context':{'intelligenceProjectId':index.key}})
    assert 'motor starts because' not in result['answer']
    assert 'not semantically verified' in result['modelNotice']
    assert not result['engineeringVerification']['trainingEligible']
