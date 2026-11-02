"""Reproduce machine-context decoding without changing PLC source or live workspaces."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',required=True)
    parser.add_argument('--query',default='HS fan motor')
    parser.add_argument('--output',default='.build/chopper-machine-context/verification')
    parser.add_argument('--foundation',action='store_true')
    parser.add_argument('--call-name',default='')
    args=parser.parse_args();root=Path(args.project).resolve();out=Path(args.output).resolve()
    if out.is_relative_to(root):raise ValueError('Place verification artifacts outside the PLC project.')
    out.mkdir(parents=True,exist_ok=True)
    from backend.core import project_intelligence as pi
    from backend.core.machine_context import analyze,decorate,signature
    from virtual_plc.core.machine_identity import select
    from virtual_plc.core.machine_calls import add_help
    from backend.core.run_history import current_user
    from backend.core import project_assistant
    start=time.monotonic();before=signature(root)
    print('Indexing source snapshot',flush=True)
    pi.WORK=out/'indexes'
    index=pi.Index(root,'machine-context-verification');index.build()
    context=analyze(index);view=add_help(select(context,args.query,80))
    print('Decoded active machine context',flush=True)
    (out/'context.json').write_text(json.dumps(context,ensure_ascii=False),encoding='utf-8')
    (out/'view.json').write_text(json.dumps(view,ensure_ascii=False,indent=2),encoding='utf-8')
    token=current_user.set({'id':'machine-context-verification','role':'user'})
    print('Checking ordinary Chopper writer tracing',flush=True)
    try:
        reply=project_assistant.answer({'question':'What controls '+args.query+'?',
            'context':{'intelligenceProjectId':index.key}})
        call_reply=None
        if args.call_name:
            print('Checking callable identity and installed B&R help',flush=True)
            call_reply=project_assistant.answer({'question':'Explain '+args.call_name+' function block',
                'context':{'intelligenceProjectId':index.key}})
            assert call_reply['source']=='local-machine-context'
            assert call_reply['machineContext']['calls']
            (out/'call-answer.json').write_text(json.dumps(call_reply,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:current_user.reset(token)
    (out/'answer.json').write_text(json.dumps(reply,ensure_ascii=False,indent=2),encoding='utf-8')
    assert reply.get('machineContext'),reply.get('machineContextNotice')
    assert reply['machineContext']['roots']==view['roots']
    assert not reply['machineContext']['completeMachineSequence']
    assert not reply.get('engineeringVerification',{}).get('runtimeObserved',False)
    if args.foundation:
        print('Building and checking independent engineering graph',flush=True)
        from python_engine.engineering_model import build,EngineeringModel
        build(index);found=EngineeringModel(index).find_function(args.query)
        (out/'foundation-candidates.json').write_text(json.dumps(found,ensure_ascii=False,indent=2),encoding='utf-8')
        assert any(row.get('hmiNames') for row in found['candidates'])
    # Raw content checks independently verify that decoding made no PLC edits.
    for name,sha in context['indexedSourceHashes'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,name
    assert signature(root)==before
    summary={'seconds':round(time.monotonic()-start,2),'project':str(root),'configuration':context['activeConfiguration'],
             'roots':view['roots'],'counts':{k:len(context[k]) for k in ['aliases','controls','operations','functions','transitions','hardware','interfaces','calls']},
             'unresolvedOperations':context['unresolvedOperations'],'sourceUnchanged':True,'modelInferenceRequested':False,
             'callDocumentationMatches':sum(bool(c.get('documentation')) for c in call_reply['machineContext']['calls']) if call_reply else None,
             'answerSource':reply.get('source'),'partialSequence':not view['completeMachineSequence']}
    (out/'result.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':main()
