import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from backend.core import assist_model
from backend.core.window_help import answer, guide
from python_engine import rule_engine_v4_30 as engine
from python_engine.structured_requirements import evaluate
from python_engine.rule_references import check_hash, load_reference


def test_new_install_defaults_to_local_model_and_server_start(tmp_path,monkeypatch):
    monkeypatch.setattr(assist_model,'CONFIG',tmp_path/'settings.json')
    monkeypatch.delenv('USOPP_LLM_BASE_URL',raising=False)
    monkeypatch.delenv('USOPP_LLM_PROVIDER',raising=False)
    config=assist_model.configuration()
    assert config['provider']=='embedded'
    assert config['autoStart'] is True
    assert config['modelPath'].endswith('.gguf')


@pytest.mark.parametrize('provider,autostart',[('local',False),('api',False),('embedded',False)])
def test_saved_connection_and_disabled_start_are_preserved(tmp_path,monkeypatch,provider,autostart):
    config=tmp_path/'settings.json';config.write_text(json.dumps({'provider':provider,'autoStart':autostart}),encoding='utf-8')
    monkeypatch.setattr(assist_model,'CONFIG',config)
    assert assist_model.configuration()['provider']==provider
    assert assist_model.configuration()['autoStart'] is autostart


def test_model_port_must_not_collide_with_api(monkeypatch):
    monkeypatch.setenv('USOPP_API_PORT','8200')
    with pytest.raises(HTTPException,match='application API port'):
        assist_model.save_configuration({'provider':'embedded','localPort':8200})


def test_missing_model_file_is_not_reported_installed(tmp_path,monkeypatch):
    monkeypatch.setattr(assist_model,'configuration',lambda:{'provider':'embedded','modelPath':str(tmp_path/'missing.gguf')})
    assert assist_model.public_configuration()['modelFileAvailable'] is False


def test_window_guide_retains_manual_capture_and_reported_verdict():
    context={'currentWindow':{'page':'plc','details':{'target':'Finisher 01','captureSource':'Manual capture','captureStatus':'Not read yet','groupCode':260}},'counts':{'pass':2,'fail':1}}
    text=answer(context)
    assert 'Manual capture' in text and 'Not read yet' in text
    assert 'fail: 1' in text and '30 days' in text
    assert guide({'currentWindow':{'page':'unknown'}}) is None


def test_window_guide_does_not_call_the_model():
    from backend.api.assist import _assist
    with patch('backend.api.assist.chat_model',side_effect=AssertionError('Model must not run for a guide')):
        result=_assist({'task':'Window assistant','guideOnly':True,'question':'How do I use this window?','context':{'currentWindow':{'page':'rules'}}})
    assert result['source']=='local-window-guide'
    assert 'cross reference' in result['answer']


def test_shared_datasource_folder_is_checked_outside_screen_root(tmp_path):
    source=tmp_path/'Logical/VCShared/DataSources/Local.dso';source.parent.mkdir(parents=True)
    source.write_text('<DataSource><Folder Name="GLOBAL"><DataPoint Name="Speed"><Property Name="PLCType" Value="DINT"/></DataPoint></Folder><Folder Name="OTHER"><DataPoint Name="Speed"><Property Name="PLCType" Value="REAL"/></DataPoint></Folder></DataSource>',encoding='utf-8')
    check={'type':'hmi','file':'Logical/VCShared/DataSources/Local.dso','variants':[{'entity':'DataPoint','name':'Speed','ancestorFolders':['GLOBAL'],'properties':{'PLCType':'DINT'}}]}
    rule={'id':'dso','name':'Exact shared datasource','category':'PLC logic + HMI','kind':'structured_requirements','checks':[check]}
    assert evaluate(tmp_path,rule,engine)['status']=='PASS'
    check['variants'][0]['ancestorFolders']=['OTHER']
    assert evaluate(tmp_path,rule,engine)['status']=='FAIL'


def test_reference_uses_saved_expected_logic_and_fails_changed_source(tmp_path,monkeypatch):
    monkeypatch.setenv('USOPP_DATA_ROOT',str(tmp_path))
    path=tmp_path/'Logical/Main/Main.st';path.parent.mkdir(parents=True);path.write_text('output := TRUE;',encoding='utf-8')
    definition={'type':'logic','file':'Logical/Main/Main.st','alternatives':['output := TRUE;']}
    digest=check_hash(definition);identifier='C-'+digest[:24]
    reference=tmp_path/'rules/references/LAPFORMER-SAMPLE_v1.0.json';reference.parent.mkdir(parents=True)
    reference.write_text(json.dumps({'schemaVersion':1,'checks':{identifier:definition}}),encoding='utf-8')
    check={'type':'reference','file':definition['file'],'referenceFile':reference.name,'checkId':identifier,'referenceHash':digest}
    rule={'id':'sample','name':'Saved expected logic','category':'PLC logic + HMI','kind':'structured_requirements','checks':[check]}
    assert evaluate(tmp_path,rule,engine)['status']=='PASS'
    path.write_text('output := FALSE;',encoding='utf-8')
    assert evaluate(tmp_path,rule,engine)['status']=='FAIL'
    reference.write_text(json.dumps({'schemaVersion':1,'checks':{identifier:{**definition,'alternatives':['output := FALSE;']}}}),encoding='utf-8')
    with pytest.raises(ValueError,match='saved reference changed'):load_reference(check)


def test_reference_path_cannot_escape_saved_definitions():
    with pytest.raises(ValueError,match='filename'):
        load_reference({'referenceFile':'../../secrets.json','checkId':'C-'+'0'*24})


def test_reference_authoring_hash_bytes_survive_git_line_normalization(tmp_path):
    from scripts.build_lapformer_rules import write_json
    path=tmp_path/'reference.json';write_json(path,{'checks':{'name':'Example'}})
    assert b'\r\n' not in path.read_bytes()
