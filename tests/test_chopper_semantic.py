"""Hybrid retrieval must improve discovery without promoting relevance into proof."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil

import numpy as np
import pytest
from pydantic import ValidationError
from backend.core import project_intelligence as pi,semantic_retrieval as semantic,semantic_runtime as runtime,assist_model
from backend.core.engineering_claims import StaticEngineeringFact
from backend.core.model_policy import enforce,request_options


@pytest.fixture
def indexed(tmp_path,monkeypatch):
    monkeypatch.setattr(pi,'WORK',tmp_path/'work');monkeypatch.setattr(runtime,'CONFIG',tmp_path/'semantic.json')
    runtime.CONFIG.write_text(json.dumps({'enabled':True,'rerank':True}))
    root=tmp_path/'machine';root.mkdir()
    sources={'LastUser.set':'<Settings><ConfigurationManager ActiveConfigurationName="CFG"/></Settings>',
       'Logical/Global.var':'VAR_GLOBAL\nFanMotor : BOOL;\nTotalMetres : DINT;\nEND_VAR',
       'Logical/Air.st':'PROGRAM _CYCLIC\n(* Enclosure ventilation blower circulates air *)\nFanMotor := TRUE;\nEND_PROGRAM',
       'Logical/Production.st':'PROGRAM _CYCLIC\n(* Accumulated textile output *)\nTotalMetres := TotalMetres + 1;\nEND_PROGRAM',
       'Physical/CFG/IoMap.iom':'FanMotor AT %QX0.0;',
       'Physical/ALT/IoMap.iom':'FanMotor AT %QX9.0;'}
    for relative,text in sources.items():
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    index=pi.Index(root,'engineer');index.build()
    def embedding(texts,query=False):
        vectors=np.zeros((len(texts),384),dtype=np.float32)
        for position,text in enumerate(texts):
            vectors[position,0 if any(word in text.casefold() for word in ('air','blower','fan','cooling')) else 1]=1
        return vectors
    monkeypatch.setattr(runtime,'embeddings',embedding)
    monkeypatch.setattr(runtime,'rerank',lambda q,texts:{position:float('air' in text.casefold()) for position,text in enumerate(texts)})
    return index


def test_hybrid_discovers_aliases_and_retains_exact_tag_priority(indexed):
    before={p.relative_to(indexed.root):p.read_bytes() for p in indexed.root.rglob('*') if p.is_file()}
    built=semantic.build(indexed);assert built['ready'] and built['dimensions']==384
    result=indexed.retrieve('Which cooling appliance ventilates the cabinet?',limit=30)
    assert result['semantic']['used'] and result['semantic']['reranked']
    assert any(e['file']=='Logical/Air.st' for e in result['evidence'])
    assert not any(e['file'].startswith('Physical/ALT/') and 'semantic' in e['matchReason'] for e in result['evidence'])
    exact=indexed.retrieve('FanMotor',limit=30)
    reasons=[e['matchReason'] for e in exact['evidence']]
    assert reasons[0].startswith(('Exact symbol','Declaration '))
    assert before=={p.relative_to(indexed.root):p.read_bytes() for p in indexed.root.rglob('*') if p.is_file()}


def test_missing_disabled_busy_and_bad_reranker_are_explicit_fallbacks(indexed,monkeypatch):
    result=indexed.retrieve('FanMotor');assert not result['semantic']['used'] and any('no semantic index' in n for n in result['notices'])
    semantic.build(indexed)
    monkeypatch.setattr(runtime,'rerank',lambda *args:(_ for _ in ()).throw(ValueError('Invalid candidate IDs')))
    result=indexed.retrieve('cabinet cooling appliance');assert result['semantic']['used'] and not result['semantic']['reranked']
    assert any('Reranking unavailable' in n for n in result['notices'])
    with runtime.QUERY_LOCK:
        result=indexed.retrieve('FanMotor');assert not result['semantic']['used'] and any('busy' in n for n in result['notices'])
    runtime.save_settings({'enabled':False})
    result=indexed.retrieve('FanMotor');assert not result['semantic']['enabled'] and result['evidence']


def test_source_hash_edit_restored_mtime_and_added_files_reject_vectors(indexed):
    semantic.build(indexed);source=indexed.root/'Logical/Air.st';stat=source.stat();old=source.read_bytes()
    source.write_bytes(old.replace(b'TRUE',b'FAKE'));os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    result=indexed.retrieve('cooling appliance');assert not result['semantic']['used'];assert any('source changed' in n for n in result['notices'])
    source.write_bytes(old);os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert indexed.retrieve('cooling appliance')['semantic']['used']
    (indexed.root/'Logical/New.st').write_text('NewSignal := TRUE;')
    assert not indexed.retrieve('cooling appliance')['semantic']['used']


def test_owner_parser_and_source_revision_bind_index_and_atomic_failure(indexed,monkeypatch):
    semantic.build(indexed);saved=semantic.index_path(indexed).read_bytes()
    other=pi.Index(indexed.root,'another-account');other.build();shutil.copyfile(semantic.index_path(indexed),semantic.index_path(other))
    result=other.retrieve('cooling appliance');assert not result['semantic']['used']
    monkeypatch.setattr(runtime,'embeddings',lambda *args,**kwargs:(_ for _ in ()).throw(ValueError('Model failed')))
    with pytest.raises(ValueError,match='Model failed'):semantic.build(indexed)
    assert semantic.index_path(indexed).read_bytes()==saved
    with pi.connection(indexed.path) as db:pi.metadata(db,'parser_revision',999);db.commit()
    assert not semantic.status(indexed,check=True)['ready']


def test_mid_rerank_edit_blocks_publication(indexed,monkeypatch):
    semantic.build(indexed)
    def mutate(question,texts):
        source=indexed.root/'Logical/Air.st';stat=source.stat();source.write_bytes(source.read_bytes().replace(b'TRUE',b'FAKE'));os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        return {position:float(position) for position in range(len(texts))}
    monkeypatch.setattr(runtime,'rerank',mutate)
    with pytest.raises(ValueError,match='source changed'):indexed.retrieve('cooling appliance')


def test_untrusted_embedding_and_rerank_shapes_rejected(monkeypatch):
    monkeypatch.setattr(runtime,'fit',lambda kind,text,budget:text)
    monkeypatch.setattr(runtime,'post',lambda *args:{'data':[{'index':0,'embedding':[float('nan')]*384}]})
    with pytest.raises(ValueError,match='values'):runtime.embeddings(['x'])
    monkeypatch.setattr(runtime,'post',lambda *args:{'results':[{'index':5,'relevance_score':1.}]})
    with pytest.raises(ValueError,match='indices'):runtime.rerank('x',['y'])
    for malformed in [None,[],{'data':[None]},{'data':[{'index':True,'embedding':[1]*384}]}]:
        monkeypatch.setattr(runtime,'post',lambda *args:malformed)
        with pytest.raises(ValueError):runtime.embeddings(['x'])
        with pytest.raises(ValueError):runtime.rerank('x',['y'])


def test_corrupt_optional_settings_retain_lexical_retrieval(indexed):
    for content in ['invalid JSON','[]','null']:
        runtime.CONFIG.write_text(content)
        result=indexed.retrieve('FanMotor')
        assert result['evidence'] and not result['semantic']['used']
        assert any('settings cannot be read' in notice for notice in result['notices'])


def test_disabling_retrieval_prevents_model_restart(indexed,monkeypatch):
    runtime.save_settings({'enabled':False})
    monkeypatch.setattr(runtime,'verify',lambda *args:pytest.fail('Disabled retrieval attempted model startup'))
    with pytest.raises(ValueError,match='disabled'):runtime.ensure('embedding')


@pytest.mark.parametrize('url',['https://external.example/v1','http://127.0.0.1.evil.example/v1','http://127.0.0.1@external.example/v1','http://192.168.1.5/v1','http://0.0.0.0/v1'])
def test_local_policy_blocks_remote_before_transport(url,monkeypatch):
    cfg={'provider':'api','baseUrl':url,'localOnly':True}
    monkeypatch.setattr(assist_model,'configuration',lambda:cfg)
    monkeypatch.setattr(assist_model.requests,'post',lambda *a,**k:pytest.fail('Evidence was sent'))
    with pytest.raises(ValueError,match='Local-only'):assist_model.chat_model('secret','PLC source')
    with pytest.raises(ValueError,match='Local-only'):assist_model.check_model()


def test_loopback_policy_disables_proxies_and_remote_is_explicit():
    for url in ['http://127.0.0.1:8202/v1','http://localhost:8202/v1','http://[::1]:8202/v1']:
        cfg={'provider':'api','baseUrl':url,'localOnly':True};enforce(cfg)
        assert request_options(cfg)['proxies']=={'http':'','https':'','all':''}
    enforce({'provider':'api','baseUrl':'https://external.example/v1','localOnly':False})
    with pytest.raises(ValueError):enforce({'provider':'embedded','baseUrl':'https://external.example','localOnly':False})


def test_typed_claims_reject_runtime_status_unknown_kinds_and_duplicate_sources():
    fact={'id':'F1','kind':'assignment','relationshipId':'edge1','text':'Source assigns Motor := TRUE.','sourceIds':['S1'],'details':{'value':'TRUE'},'status':'source-verified-static'}
    assert StaticEngineeringFact.model_validate(fact).sourceIds==['S1']
    for change in [{'status':'live-verified'},{'runtimeObserved':True},{'kind':'motor_is_running'},{'sourceIds':['S1','S1']},{'sourceIds':['https://made-up.example']}]:
        with pytest.raises(ValidationError):StaticEngineeringFact.model_validate({**fact,**change})


def test_api_owner_and_admin_boundaries(indexed,monkeypatch,tmp_path):
    from fastapi import FastAPI,Request
    from fastapi.testclient import TestClient
    from backend.api import assist_settings,project_intelligence
    app=FastAPI();app.include_router(assist_settings.router);app.include_router(project_intelligence.router)
    @app.middleware('http')
    async def authenticated(request:Request,call_next):
        request.state.user={'id':request.headers.get('x-test-owner','engineer'),'role':request.headers.get('x-test-role','user')}
        return await call_next(request)
    monkeypatch.setattr(semantic,'begin_build',lambda index:{'phase':'building','projectId':index.key})
    monkeypatch.setattr(runtime,'begin_install',lambda:{'installation':{'phase':'downloading'}})
    with TestClient(app) as client:
        url=f'/api/assist/projects/{indexed.key}'
        assert client.post(url+'/semantic-build').json()['projectId']==indexed.key
        assert client.get(url+'/semantic-status',headers={'x-test-owner':'other'}).status_code==404
        assert client.post(url+'/semantic-build',headers={'x-test-owner':'other'}).status_code==404
        assert client.get('/api/assist/model/retrieval').status_code==403
        assert client.post('/api/assist/model/retrieval/install').status_code==403
        admin={'x-test-role':'admin'}
        assert client.get('/api/assist/model/retrieval',headers=admin).status_code==200
        assert client.post('/api/assist/model/retrieval',json={'enabled':False},headers=admin).json()['enabled'] is False
        assert client.post('/api/assist/model/retrieval',json={'baseUrl':'https://external.example'},headers=admin).status_code==400
        assert client.post('/api/assist/model/retrieval/install',headers=admin).status_code==200
