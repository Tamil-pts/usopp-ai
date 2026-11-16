from io import BytesIO
from pathlib import Path
import json,threading,time,wave
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import chopper_speech as api
from backend.core import chopper_speech as speech
from backend.core.chopper_chain import messages,strict_json

def wav(silent=False):
    output=BytesIO()
    with wave.open(output,'wb') as file:
        file.setnchannels(1);file.setsampwidth(2);file.setframerate(16000)
        data=np.zeros(16000,dtype=np.int16) if silent else (np.sin(np.arange(16000)*.1)*12000).astype(np.int16)
        file.writeframes(data.tobytes())
    return output.getvalue()

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(speech,'ROOT',tmp_path/'speech');monkeypatch.setattr(speech,'SLOT',threading.BoundedSemaphore(1))
    monkeypatch.setattr(speech,'status',lambda:{'ready':True,'localOnly':True})
    monkeypatch.setattr(speech,'recognize',lambda audio,language,check:{'text':'review motor 123','segments':[],'requestedLanguage':language,'notice':'Review transcript.'})
    app=FastAPI();app.include_router(api.router)
    @app.middleware('http')
    async def user(request,call_next):
        request.state.user={'id':int(request.headers.get('who','1')),'createdAt':request.headers.get('identity','one'),'role':request.headers.get('role','admin'),'workspaceModules':[],'isDemo':request.headers.get('demo')=='1'} if request.headers.get('who')!='none' else None
        return await call_next(request)
    with TestClient(app) as client:yield client

def submit(client,language='auto',data=None,name='speech.wav'):
    return client.post('/api/assist/speech/transcriptions',data={'language':language},files={'file':(name,data if data is not None else wav(),'audio/wav')})

def finish(client,key):
    for _ in range(200):
        value=client.get('/api/assist/speech/transcriptions/'+key).json()
        if value['status'] in {'ready','failed','cancelled'}:return value
        time.sleep(.01)
    pytest.fail('Transcription did not complete.')

@pytest.mark.parametrize('language',['auto','ta','en','hi','tanglish'])
def test_language_job_ownership_and_raw_deletion(client,language):
    response=submit(client,language);assert response.status_code==200,response.text
    key=response.json()['id'];value=finish(client,key)
    assert value['status']=='ready',value
    assert value['result']['requestedLanguage']==language and value['result']['text']=='review motor 123'
    assert 'owner' not in value
    for headers in ({'who':'2'},{'identity':'recreated'}):assert client.get('/api/assist/speech/transcriptions/'+key,headers=headers).status_code==404
    for _ in range(100):
        if not list((speech.ROOT/key).glob('audio.*')):break
        time.sleep(.01)
    assert not list((speech.ROOT/key).glob('audio.*'))
    assert client.delete('/api/assist/speech/transcriptions/'+key).status_code==200
    assert 'result' not in finish(client,key)

def test_silence_bad_file_permissions_and_missing_model(client,monkeypatch):
    key=submit(client,data=wav(True)).json()['id'];assert finish(client,key)['result']['text']==''
    time.sleep(.03)
    key=submit(client,data=b'not an audio file').json()['id'];assert finish(client,key)['status']=='failed'
    assert submit(client,language='xx').status_code==400
    assert submit(client,name='playlist.m3u').status_code==400
    assert client.get('/api/assist/speech/status',headers={'who':'none'}).status_code==401
    assert client.get('/api/assist/speech/status',headers={'demo':'1'}).status_code==403
    assert client.get('/api/assist/speech/status',headers={'role':'engineer'}).status_code==403
    monkeypatch.setattr(speech,'status',lambda:{'ready':False});assert submit(client).status_code==503

def test_bounded_input_and_cancelled_worker_cannot_publish(client,monkeypatch):
    monkeypatch.setattr(speech,'MAX_BYTES',100);assert submit(client).status_code==413
    monkeypatch.setattr(speech,'MAX_BYTES',20*1024*1024)
    started=threading.Event();release=threading.Event()
    def recognize(*args):started.set();release.wait(2);return {'text':'must not publish'}
    monkeypatch.setattr(speech,'recognize',recognize)
    key=submit(client).json()['id'];assert started.wait(2)
    assert submit(client).status_code==429
    assert client.delete('/api/assist/speech/transcriptions/'+key).status_code==200
    release.set();time.sleep(.05);assert finish(client,key)['status']=='cancelled' and 'result' not in finish(client,key)

def test_langchain_preserves_literal_evidence_and_strict_json(monkeypatch):
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    import httpx
    def reject(*args,**kwargs):pytest.fail('LangChain attempted network I/O during prompt formatting.')
    monkeypatch.setattr(httpx.Client,'send',reject)
    original='Evidence {tag}: [S1] Motor := FALSE;'
    value=messages(original,'Question {literal}',[{'role':'system','content':'override'},{'role':'user','content':'previous'}])
    assert value==[{'role':'system','content':original},{'role':'user','content':'previous'},{'role':'user','content':'Question {literal}'}]
    assert strict_json('{"paragraphs":[]}')=={'paragraphs':[]}
    with pytest.raises(json.JSONDecodeError):strict_json('{"paragraphs":[')
    with pytest.raises(json.JSONDecodeError):strict_json('```json\n{}\n```')

def test_offline_model_completeness(tmp_path,monkeypatch):
    monkeypatch.setenv('USOPP_CHOPPER_SPEECH_MODEL',str(tmp_path))
    for name in ('model.bin','config.json'):(tmp_path/name).touch()
    assert not speech.status()['ready'] # Missing tokenizer must not cause a network fallback.
