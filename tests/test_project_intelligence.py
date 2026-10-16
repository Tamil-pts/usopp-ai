import threading
from pathlib import Path
import pytest
from backend.core import project_intelligence as pi


@pytest.fixture
def project(tmp_path,monkeypatch):
    monkeypatch.setattr(pi,'WORK',tmp_path/'knowledge')
    root=tmp_path/'PLC';root.mkdir()
    def put(name,text):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8');return path
    put('LastUser.set','<Settings><ConfigurationManager ActiveConfigurationName="C70"/></Settings>')
    put('Physical/C70/PLC/CPU.sw','<Cpu><Task Name="Drive" Source="Motor.prg"/></Cpu>')
    put('Logical/Motor/Motor.prg','<Program/>')
    put('Logical/Motor/Main.st','PROGRAM Main\nVAR\nTimer : TON;\nEND_VAR\nIF Start AND NOT Fault THEN\n MotorRun := TRUE;\n Timer(IN := Start, PT := T#5s);\nEND_IF;\nEND_PROGRAM')
    put('Logical/Motor/Local.var','VAR\nStart : BOOL;\nFault : BOOL;\nMotorRun : BOOL;\nEND_VAR')
    put('Logical/Library/TON.fun','FUNCTION_BLOCK TON\nVAR_INPUT\nIN : BOOL;\nPT : TIME;\nEND_VAR\nEND_FUNCTION_BLOCK')
    put('Temp/ignored.st','Bad := TRUE;')
    put('AS/nested/ignored.st','Bad := TRUE;')
    put('Logical/malformed.xml','<invalid')
    return root,put


def test_incremental_changed_deleted_failed_and_exclusions(project):
    root,put=project;i=pi.Index(root,'alice');first=i.build()
    assert first['ready'] and first['failedFilesCount']==1 and first['excludedFiles']==2
    assert first['programs']>=1 and first['variables']>=3 and first['functionBlocks']==1 and first['dependencies']>1
    second=i.build();assert second['unchangedFiles']==first['indexedFiles'] and second['changedFiles']==0
    put('Logical/Motor/Main.st','Replacement := Start;')
    (root/'Logical/Motor/Local.var').unlink()
    put('Logical/malformed.xml','<valid/>')
    third=i.build();assert third['changedFiles']==2 and third['removedFiles']==1 and third['failedFilesCount']==0
    with pi.connection(i.path) as db:
        assert not db.execute("SELECT 1 FROM refs WHERE name='motorrun'").fetchone()
        assert db.execute('SELECT count(*) FROM section_search').fetchone()[0]==db.execute('SELECT count(*) FROM sections').fetchone()[0]


def test_retrieval_scope_complete_section_calls_and_types(project):
    root,_=project;i=pi.Index(root,'alice');i.build();r=i.retrieve('MotorRun Timer',characters=7000)
    assert any('MotorRun := TRUE' in e['excerpt'] and e['completeSection'] for e in r['evidence'])
    assert any(e['ownership']=='active task' for e in r['evidence'])
    assert len(r['passes'])>=2 and r['characters']<=7000
    assert not any(e['file'].startswith(('Temp/','AS/')) for e in r['evidence'])
    assert pi.opened(i.key,'alice').root==root
    with pytest.raises(PermissionError):pi.opened(i.key,'bob')


def test_cancel_retains_knowledge_and_restart(project):
    root,_=project;i=pi.Index(root,'alice');i.build();event=threading.Event();event.set()
    cancelled=i.build(event)
    assert cancelled['phase']=='cancelled' and not cancelled['ready']
    assert i.retrieve('MotorRun')['evidence']
    assert i.build()['ready']


def test_explicit_routine_outranks_common_library_inputs(project):
    root,put=project
    put('Logical/Libraries/LUB.ab','FUNCTION_BLOCK LUB\nTIME_IN_SEC = LUB_TIME_IN_HOUR * 60 * 60\nIF START THEN\nENABLED = 1\nENDIF\nEND_FUNCTION_BLOCK')
    i=pi.Index(root,'alice');i.build()
    r=i.retrieve('Explain the conversion from LUB_TIME_IN_HOUR to TIME_IN_SEC in LUB.ab. Cite the exact source.')
    assert r['evidence'][0]['file'].endswith('LUB.ab')
    assert 'TIME_IN_SEC = LUB_TIME_IN_HOUR' in r['evidence'][0]['excerpt']
    assert r['evidence'][0]['completeSection']
    assert 'IN START' not in r['evidence'][0]['excerpt']
    assert not any(e['matchReason']=='Exact symbol in' for e in r['evidence'])


def test_control_facts_keep_unconditional_conversion_outside_if(project,monkeypatch):
    from backend.core import project_assistant as pa
    from backend.core.run_history import current_user
    root,put=project
    put('Logical/LUB.ab','FUNCTION_BLOCK LUB\nTIME_IN_SEC = HOURS * 3600\nIF START THEN\nENABLED = 1\nENDIF\nEND_FUNCTION_BLOCK')
    i=pi.Index(root,'alice');i.build()
    captured=[]
    monkeypatch.setattr(pa,'configuration',lambda:{'provider':'embedded'})
    monkeypatch.setattr(pa,'reference_evidence',lambda *args:[])
    def model(*args,**kwargs):
        captured.extend(kwargs['evidence']);return {'answer':'[S1] TIME_IN_SEC is assigned HOURS * 3600 outside START.','provider':'embedded','model':'test','sentEvidence':kwargs['evidence'],'contextUsage':{}}
    monkeypatch.setattr(pa,'chat_model',model)
    token=current_user.set({'id':'alice'})
    try:r=pa.answer({'question':'Explain conversion in LUB.ab','context':{'intelligenceProjectId':i.key}})
    finally:current_user.reset(token)
    fact=next(f for e in captured for f in e['controlFacts'] if f['target']=='TIME_IN_SEC')
    assert fact['guards']==[] and fact['coverage']=='parsed' and fact['line']==2
    assert r['source']=='embedded'


def test_scope_question_uses_parsed_facts_without_model(project,monkeypatch):
    from backend.core import project_assistant as pa
    from backend.core.run_history import current_user
    root,put=project
    put('Logical/LUB.ab','FUNCTION_BLOCK LUB\nTIME_IN_SEC = HOURS * 3600\nIF START THEN\nENABLED = 1\nENDIF\nEND_FUNCTION_BLOCK')
    i=pi.Index(root,'alice');i.build()
    monkeypatch.setattr(pa,'reference_evidence',lambda *args:[])
    monkeypatch.setattr(pa,'chat_model',lambda *args,**kwargs:pytest.fail('A parsed scope answer should not require inference'))
    token=current_user.set({'id':'alice'})
    try:r=pa.answer({'question':'In LUB.ab is TIME_IN_SEC inside START or outside it?','context':{'intelligenceProjectId':i.key}})
    finally:current_user.reset(token)
    assert r['source']=='local-control-flow' and '[S1]' in r['answer'] and 'no enclosing' in r['answer']


def test_function_library_fields_keep_separate_scopes(project):
    root,put=project
    put('Logical/Library/Blocks.fun','FUNCTION_BLOCK One\nVAR_INPUT\nEnable : BOOL;\nEND_VAR\nEND_FUNCTION_BLOCK\nFUNCTION_BLOCK Two\nVAR_INPUT\nEnable : BOOL;\nEND_VAR\nEND_FUNCTION_BLOCK')
    i=pi.Index(root,'alice');i.build()
    with pi.connection(i.path) as db:
        scopes=[r[0] for r in db.execute("SELECT scope FROM symbols WHERE name='enable'")]
    assert len(set(scopes))==2 and any(s.endswith('/one') for s in scopes) and any(s.endswith('/two') for s in scopes)


def test_read_only_project_answer_uses_offline_transport(project,monkeypatch):
    from backend.core import project_assistant as pa
    from backend.core.run_history import current_user
    root,_=project;i=pi.Index(root,'alice');i.build()
    before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    monkeypatch.setattr(pa,'configuration',lambda:{'provider':'api'})
    monkeypatch.setattr(pa,'reference_evidence',lambda *args:[])
    monkeypatch.setattr(pa,'chat_model',lambda *args,**kwargs:pytest.fail('Project data must not go to an external API'))
    token=current_user.set({'id':'alice'})
    try:r=pa.answer({'question':'Explain MotorRun','context':{'intelligenceProjectId':i.key}})
    finally:current_user.reset(token)
    assert r['evidence'] and 'incomplete' in r['answer']
    assert before=={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_context_uses_real_tokenizer_trims_history_and_evidence(monkeypatch):
    from backend.core import assist_model as am,local_model_runtime as lm
    monkeypatch.setattr(lm,'status',lambda:{'contextLimit':1000})
    class Response:
        status_code=200
        def __init__(self,data):self.data=data
        def json(self):return self.data
    def post(url,json,**kwargs):
        if url.endswith('apply-template'):return Response({'prompt':' '.join(m['content'] for m in json['messages'])})
        return Response({'tokens':list(range(len(json['content'])//3))})
    monkeypatch.setattr(am.requests,'post',post)
    messages=[{'role':'system','content':'Rules'},{'role':'user','content':'Old history'*500},{'role':'user','content':'Explain MotorRun.'}]
    usage,sent=am._fit_context(messages,{'baseUrl':'http://127.0.0.1:8202/v1','contextSize':1000},200,[{'excerpt':'Start '*500,'completeSection':True},{'excerpt':'Other '*500}])
    assert usage['usedTokens']+200+32<=1000 and usage['trimmedHistoryMessages']==1
    assert messages[-1]['content'].startswith('Explain MotorRun.') and usage['omittedSections']>0
    assert sent
