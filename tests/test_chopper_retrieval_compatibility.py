"""Exercise the production chat dispatch and real SQLite retrieval, not a stub index."""
from contextlib import nullcontext
import inspect
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.api import assist,project_intelligence as project_api
from backend.core import assist_model,local_model_runtime,project_assistant,project_intelligence
from backend.core.project_retrieval import retrieve_page
from backend.core.run_history import current_user


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setattr(project_intelligence,'WORK',tmp_path/'indexes')
    root=tmp_path/'project';root.mkdir()
    for number in range(24):
        (root/f'Main{number:02}.st').write_text(f'PROGRAM Main{number}\nIF Enable{number} THEN\nOutput{number:02} := TRUE;\nEND_IF\nEND_PROGRAM',encoding='utf-8')
    index=project_intelligence.Index(root,'chat-regression');index.build()
    monkeypatch.setattr(project_assistant,'reference_evidence',lambda *args:[])
    monkeypatch.setattr(project_assistant,'configuration',lambda:{'provider':'local'})
    monkeypatch.setattr('backend.core.assist_training.capture',lambda *args:None)
    app=FastAPI();app.include_router(assist.router);app.include_router(project_api.router)
    @app.middleware('http')
    async def user_context(request,call_next):
        user={'id':'chat-regression','role':'user'};request.state.user=user;token=current_user.set(user)
        try:return await call_next(request)
        finally:current_user.reset(token)
    with TestClient(app) as client:yield index,client


class LegacyIndex:
    """The actual pre-pagination signature backed by the current SQLite index."""
    def __init__(self,index):self.index=index;self.calls=[]
    def __getattr__(self,key):
        if key=='relationships':raise AttributeError(key)
        return getattr(self.index,key)
    def retrieve(self,question,characters=18000,passes=3):
        self.calls.append((question,characters,passes))
        return self.index.retrieve(question,characters=characters,passes=passes)


def test_real_chopper_chat_route_accepts_legacy_loaded_index(workspace,monkeypatch):
    index,client=workspace;legacy=LegacyIndex(index)
    with pytest.raises(TypeError,match='limit'):
        legacy.retrieve('Explain Output00',limit=48)
    monkeypatch.setattr(project_assistant,'opened',lambda *args:legacy)
    before={str(path):path.read_bytes() for path in index.root.iterdir()}
    response=client.post('/api/assist',json={'question':'Review project source operations','context':{'intelligenceProjectId':index.key}})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['evidence'] and legacy.calls
    assert any('legacy retrieval interface' in notice for notice in result['retrieval']['notices'])
    assert result['retrieval']['nextRetrievalOffset'] is None
    assert before=={str(path):path.read_bytes() for path in index.root.iterdir()}
    assert index.snapshot()['indexedFiles']==24


def test_actual_chat_route_and_public_retrieval_api_use_supported_keywords(workspace,monkeypatch):
    index,client=workspace;calls=[];actual=project_intelligence.Index.retrieve
    def observed(self,question,characters=18000,passes=3,offset=0,limit=14):
        calls.append({'characters':characters,'passes':passes,'offset':offset,'limit':limit})
        return actual(self,question,characters=characters,passes=passes,offset=offset,limit=limit)
    monkeypatch.setattr(project_intelligence.Index,'retrieve',observed)
    response=client.post('/api/assist',json={'question':'Review project source operations','context':{'intelligenceProjectId':index.key}})
    assert response.status_code==200 and response.json()['evidence']
    assert calls[0]['limit']==48 and calls[0]['characters']==16000
    supported=set(inspect.signature(actual).parameters)
    assert all(set(call)<=supported for call in calls)
    seen=set();offset=0;pages=0
    while offset is not None:
        page=client.post(f'/api/assist/projects/{index.key}/retrieve',json={'question':'project overview','limit':4,'offset':offset})
        assert page.status_code==200,page.text
        result=page.json();assert len(result['evidence'])<=4
        keys={(item['file'],item['line'],item['endLine']) for item in result['evidence']}
        assert not seen&keys
        seen.update(keys);offset=result.get('nextOffset');pages+=1
        assert pages<20
    assert pages>2 and len(seen)>14


def test_legacy_does_not_repeat_first_page_or_hide_internal_type_error(workspace):
    index,_=workspace;legacy=LegacyIndex(index)
    first=retrieve_page(legacy,'project overview',limit=3)
    assert len(first['evidence'])==3 and first['nextOffset'] is None
    second=retrieve_page(legacy,'project overview',offset=3,limit=3)
    assert not second['evidence'] and len(legacy.calls)==1
    class Broken:
        def retrieve(self,question,characters=18000,passes=3,offset=0,limit=14):
            raise TypeError('Internal parser failure')
    with pytest.raises(TypeError,match='Internal parser failure'):
        retrieve_page(Broken(),'test')


def test_limits_are_bounded_and_unknown_options_are_rejected(workspace):
    index,_=workspace
    assert len(retrieve_page(index,'project overview',limit=0)['evidence'])==1
    assert len(retrieve_page(index,'project overview',limit=999)['evidence'])<=200
    with pytest.raises(ValueError,match='numeric'):retrieve_page(index,'test',offset='invalid')
    with pytest.raises(TypeError,match='unknown_option'):retrieve_page(index,'test',unknown_option=1)


def test_chat_multibatch_preserves_4096_context_budget(workspace,monkeypatch):
    index,client=workspace
    config={'provider':'embedded','baseUrl':'http://127.0.0.1:8202/v1','model':'token-budget-test','contextSize':4096,'maxTokens':300,'responseTimeoutSeconds':60}
    monkeypatch.setattr(project_assistant,'configuration',lambda:config)
    monkeypatch.setattr(assist_model,'configuration',lambda:config)
    monkeypatch.setattr(local_model_runtime,'status',lambda:{'ready':True,'contextLimit':4096})
    monkeypatch.setattr('backend.core.workhub_intelligence.resources.inference_slot',lambda **kwargs:nullcontext())
    measured={'tokens':0};requests=[]
    class Response:
        status_code=200
        def __init__(self,data):self.data=data
        def json(self):return self.data
        def __enter__(self):return self
        def __exit__(self,*args):return False
    def post(url,json,**kwargs):
        if url.endswith('/apply-template'):return Response({'prompt':' '.join(item['content'] for item in json['messages'])})
        if url.endswith('/tokenize'):
            measured['tokens']=len(json['content'])//3
            return Response({'tokens':list(range(measured['tokens']))})
        assert url.endswith('/chat/completions')
        requests.append((measured['tokens'],json['max_tokens']))
        source=json['response_format']['json_schema']['schema']['properties']['paragraphs']['items']['properties']['sourceIds']['items']['enum'][0]
        text=__import__('json').dumps({'paragraphs':[{'text':'A source assignment is shown.','sourceIds':[source]}]})
        return Response({'choices':[{'message':{'content':text},'finish_reason':'stop'}],
                         'usage':{'prompt_tokens':measured['tokens'],'completion_tokens':20,'total_tokens':measured['tokens']+20}})
    monkeypatch.setattr(assist_model.requests,'post',post)
    response=client.post('/api/assist',json={'question':'Explain the complete machine working sequence','context':{'intelligenceProjectId':index.key,'analysisBatchLimit':3}})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['retrieval']['coverage']['analysisPasses']==3
    assert result['retrieval']['coverage']['modelSuppliedFiles']>=6
    assert len(requests)>=4 and all(tokens+reserve+32<=4096 for tokens,reserve in requests)
    assert index.snapshot()['indexedFiles']==24
