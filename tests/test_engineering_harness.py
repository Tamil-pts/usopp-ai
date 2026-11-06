import json
import pytest
from backend.core import engineering_harness as harness
from test_engineering_foundation import reference
from python_engine.engineering_model import build


def test_two_pass_graph_rag_publishes_only_checked_facts(reference):
    build(reference)
    result=harness.investigate(reference.key,'What conditions are required before Motor starts?',{'id':'engineer'},use_model=False)
    assert result['passesCompleted']==2 and len(result['memory']['passes'])==2
    assert result['rag']['verifiedFacts']>=2 and result['rag']['retrievedSections']>0
    assert any(f['kind']=='rung_condition' and 'NOT Fault' in f['text'] for f in result['facts'])
    assert any(f['kind']=='physical_mapping' for f in result['facts'])
    assert not result['engineeringVerification']['trainingEligible'] and not result['agiClaimed']
    assert list((reference.path.parent/'investigations').glob('*.json'))
    for evidence in result['evidence']:assert evidence['sourceHash']


def test_restored_mtime_edit_during_inference_is_still_rejected(reference,monkeypatch):
    import os
    build(reference);monkeypatch.setattr(harness,'configuration',lambda:{'provider':'embedded'})
    def changed(*args,**kwargs):
        target=reference.root/kwargs['evidence'][0]['file'];stat=target.stat();raw=target.read_bytes()
        # Change bytes without changing file length, then restore its timestamp.
        target.write_bytes(raw.replace(b'Motor',b'Other',1));os.utime(target,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        return {'answer':'[S1] F1'}
    with pytest.raises(ValueError,match='Source hash changed'):
        harness.investigate(reference.key,'What conditions are required before Motor starts?',{'id':'engineer'},model_call=changed)


@pytest.mark.parametrize('answer',['[S1] Motor is ON because Start is TRUE.','[S1] F999','[S999] F1'])
def test_hallucination_protocol_rejects_free_text_fabricated_facts_and_sources(reference,monkeypatch,answer):
    build(reference);monkeypatch.setattr(harness,'configuration',lambda:{'provider':'embedded'})
    result=harness.investigate(reference.key,'What conditions are required before Motor starts?',{'id':'engineer'},model_call=lambda *a,**k:{'answer':answer})
    assert result['modelNotice'] and not result['modelUsedForFactSelection']
    assert 'Motor is ON because' not in result['answer'] and 'F999' not in result['answer']
    assert result['facts']


def test_model_can_only_select_existing_facts(reference,monkeypatch):
    build(reference);monkeypatch.setattr(harness,'configuration',lambda:{'provider':'embedded'})
    def model(system,question,**kwargs):
        facts=kwargs['facts']['verifiedFacts'];fact=facts[0]
        assert kwargs['max_tokens']==160 and kwargs['evidence']
        return {'answer':'['+fact['sourceIds'][0]+'] '+fact['id'],
                'contextUsage':{'promptTokens':600,'reservedAnswerTokens':160,'maxContext':4096}}
    result=harness.investigate(reference.key,'What conditions are required before Motor starts?',{'id':'engineer'},model_call=model)
    assert result['modelUsedForFactSelection'] and result['facts']
    assert {f['kind'] for f in result['facts']} <= {'assignment','rung_condition','physical_mapping'}
    assert any(f['kind']=='rung_condition' for f in result['facts'])
    assert result['contextUsage']['maxContext']==4096


def test_one_pass_or_ambiguous_identity_cannot_publish_control_claims(reference):
    build(reference)
    result=harness.investigate(reference.key,'Trace Motor',{'id':'engineer'},use_model=False,max_passes=1)
    assert not result['facts'] and 'second-pass' in result['answer']
    result=harness.investigate(reference.key,'Trace LocalEnable',{'id':'engineer'},use_model=False)
    assert not result['facts'] and len(result['candidates'])==2


def test_source_change_during_model_selection_prevents_publication(reference,monkeypatch):
    build(reference);monkeypatch.setattr(harness,'configuration',lambda:{'provider':'embedded'})
    def changed(*a,**k):
        (reference.root/'Logical/Drive/Init.st').write_text('PROGRAM _INIT\nMotor := TRUE;\nEND_PROGRAM')
        return {'answer':'[S1] F1'}
    with pytest.raises(ValueError,match='Source changed'):
        harness.investigate(reference.key,'Trace Motor',{'id':'engineer'},model_call=changed)
