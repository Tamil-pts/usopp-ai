import json
from pathlib import Path
import pytest

from backend.core import assist_model as am,engineering_analysis as analysis,local_model_runtime as runtime,project_intelligence as pi
from python_engine.c_control_flow import c_flow
from python_engine.function_flow import _text_flow
from python_engine.machine_function_engine import analyze
from python_engine.working_sequence import records


@pytest.fixture
def project(tmp_path,monkeypatch):
    monkeypatch.setattr(pi,'WORK',tmp_path/'data')
    root=tmp_path/'machine';root.mkdir()
    (root/'LastUser.set').write_text('<Settings><ConfigurationManager ActiveConfigurationName="CFG"/></Settings>')
    folder=root/'Logical';folder.mkdir()
    for number in range(26):
        (folder/f'Routine{number:02}.st').write_text(f'PROGRAM Routine{number}\nIF Input{number} THEN\nOutput{number} := TRUE;\nEND_IF\nEND_PROGRAM')
    index=pi.Index(root,'test-engineer');index.build();return index


def model_stub(system,prompt,*args,**kwargs):
    evidence=kwargs['evidence']
    return {'answer':'\n\n'.join(f"[{item['sourceId']}] Literal source finding." for item in evidence),
            'model':'fixture','sentEvidence':evidence,'finishReason':'stop',
            'contextUsage':{'usedTokens':600,'promptTokens':500,'maxContext':4096,'reservedAnswerTokens':300}}


def test_iterative_analysis_continues_beyond_two_batches_and_resumes(project):
    machine=analyze(project);payload={'context':{'analysisBatchLimit':6}}
    first=analysis.run(project,'Explain the complete machine working sequence',payload,machine,model_stub,{'provider':'embedded'},'Rules')
    coverage=first['retrieval']['coverage']
    assert coverage['analysisPasses']==6 and coverage['checkedBatches']==6
    assert coverage['modelSuppliedFiles']>14 and coverage['analyzedFiles']>14
    assert not coverage['complete'] and coverage['remainingSections']>0
    assert first['retrieval']['unvisitedFunctions']
    assert list((project.path.parent/'analysis_runs').glob('*.json'))
    second=analysis.run(project,'Explain the complete machine working sequence',{'context':{'analysisBatchLimit':2}},machine,model_stub,{'provider':'embedded'},'Rules')
    assert second['retrieval']['coverage']['analyzedSections']>coverage['analyzedSections']
    assert second['retrieval']['coverage']['remainingSections']<coverage['remainingSections']


def test_failed_citation_is_never_counted_as_analyzed(project):
    def wrong(*args,**kwargs):return {**model_stub(*args,**kwargs),'answer':'[S999999] Invented finding.'}
    out=analysis.run(project,'Explain the complete machine working sequence',{'context':{'analysisBatchLimit':3}},analyze(project),wrong,{'provider':'embedded'},'Rules')
    assert out['retrieval']['coverage']['analysisPasses']==3
    assert out['retrieval']['coverage']['analyzedFiles']==0
    assert out['retrieval']['coverage']['modelSuppliedFiles']>0
    assert all(not row['checked'] for row in out['retrieval']['analysisPasses'])


def test_retrieval_pages_and_relationships_after_old_cap(project):
    with pi.connection(project.path) as db:
        db.executemany('INSERT INTO edges VALUES (?,?,?,?,?,?,?)',[(f'button{i}','signal','hmi-binding','Logical/Routine00.st',1,'shared','binding') for i in range(1250)])
        db.commit()
    page=project.relationships(kind='hmi-binding',offset=1200,limit=20)
    assert page['total']==1250 and len(page['items'])==20 and page['nextOffset']==1220
    machine=analyze(project)
    assert machine['coverage']['hmiBindingCount']==1250 and len(machine['hmiLinks'])==1250
    first=project.retrieve('Output',characters=30000,limit=10)
    second=project.retrieve('Output',characters=30000,offset=first['nextOffset'],limit=10)
    assert not ({(row['file'],row['line']) for row in first['evidence']} & {(row['file'],row['line']) for row in second['evidence']})


def test_whole_prompt_budget_includes_nested_machine_facts(monkeypatch):
    monkeypatch.setattr(runtime,'status',lambda:{'contextLimit':4096})
    class Response:
        status_code=200
        def __init__(self,data):self.data=data
        def json(self):return self.data
    def post(url,json,**kwargs):
        if url.endswith('apply-template'):return Response({'prompt':' '.join(row['content'] for row in json['messages'])})
        return Response({'tokens':list(range(len(json['content'])//3))})
    monkeypatch.setattr(am.requests,'post',post)
    messages=[{'role':'system','content':'Source rules'},{'role':'user','content':'Question about Output'}]
    facts={'coverage':{'indexedFiles':1000},'stateMachines':[{'conditions':['condition '*200]*100,'actions':['action '*200]*100}]*200}
    evidence=[{'sourceId':f'S{i}','file':f'{i}.st','line':1,'endLine':60,'excerpt':'Output := Input;\n'*60,'completeSection':True} for i in range(8)]
    usage,sent=am._fit_context(messages,{'baseUrl':'http://127.0.0.1:8202/v1'},768,evidence,facts)
    assert usage['usedTokens']+768+32<=4096
    assert usage['factsReduced'] and sent
    assert 'Question about Output' in messages[-1]['content']


def test_c_conditions_and_single_statement_else_use_shared_ir():
    sections,_,calls,notices=c_flow('void _CYCLIC Main(void) { if (Start && !Fault) Motor = 1; else Motor = 0; Update(Motor); }','Main.c')
    rows=[row for section in sections for row in records(section['nodes'])]
    motor=[row for row in rows if row['row']['code'].startswith('Motor =')]
    assert len(motor)==2 and 'Start && !Fault' in motor[0]['guards']
    assert any('NOT' in guard for guard in motor[1]['guards'])
    assert [call['name'] for call in calls]==['Update'] and not notices


def test_c_unsupported_semantics_remain_explicit():
    _,_,_,notices=c_flow('#if CONFIG\nvoid Main(){switch(State){case 0: Motor = 1; case 1: Motor = 0; break;} *ptr = 1;}\n#endif','Main.c')
    assert any('preprocessing' in notice for notice in notices)
    assert any('fall-through' in notice for notice in notices)
    assert any('pointer' in notice for notice in notices)


def test_st_var_out_and_ab_action_branches_are_not_false_parser_errors():
    parts,_,_,notices=_text_flow('FUNCTION_BLOCK ADD\nIF Enable THEN\n VAR_OUT := VAR_1 + VAR_2;\nEND_IF\nEND_FUNCTION_BLOCK','ADD.st',False)
    assert not notices
    assert any(row['row']['code'].startswith('VAR_OUT :=') for part in parts for row in records(part['nodes']))
    parts,_,_,notices=_text_flow('PROGRAM _CYCLIC\nCASE Step OF\nACTION 0:\nIF Start THEN\nStep = 10\nENDIF\nENDACTION\nELSEACTION:\nStep = 0\nENDACTION\nENDCASE\nEND_PROGRAM','Main.ab',True)
    assert not notices
    assignments=[row for part in parts for row in records(part['nodes'])]
    assert any('Step matches 0' in row['guards'] for row in assignments)
