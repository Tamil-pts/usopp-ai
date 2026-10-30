"""Run the real two-pass graph RAG harness against the installed CPU transformer."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.core import engineering_harness as harness,project_intelligence as pi,assist_model as am,local_model_runtime as runtime
from python_engine.engineering_model import EngineeringModel


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--index',required=True);args=parser.parse_args()
    if not re.fullmatch('[a-f0-9]{64}',args.index):parser.error('Invalid project index')
    index=pi.Index.__new__(pi.Index);index.key=args.index;index.path=pi.WORK/'chopper_intelligence'/args.index/'project.sqlite3'
    with closing(sqlite3.connect(index.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        index.root=Path(json.loads(db.execute("SELECT value FROM meta WHERE key='root'").fetchone()[0]))
    model=EngineeringModel(index);cfg=am.configuration();base=cfg['baseUrl'].removesuffix('/v1')
    props=am.requests.get(base+'/props',timeout=5).json();context=props['default_generation_settings']['n_ctx']
    metadata=am.requests.get(base+'/v1/models',timeout=5).json()['data'][0]['meta']
    captures=[];post=am.requests.post
    def observed(url,**kwargs):
        response=post(url,**kwargs)
        if url.endswith('/chat/completions'):
            body=kwargs['json'];data=response.json();usage=data.get('usage',{})
            assert usage.get('prompt_tokens',0)+body['max_tokens']+32<=context
            captures.append({'usage':usage,'reservedAnswerTokens':body['max_tokens'],'finish':data.get('choices',[{}])[0].get('finish_reason')})
        return response
    with patch.object(harness,'owned_model',return_value=model),patch.object(runtime,'status',return_value={'ready':True,'contextLimit':context}),patch.object(am.requests,'post',side_effect=observed):
        result=harness.investigate(index.key,'What conditions are required before the can changer motor starts?',use_model=True)
        # Also measure actual-token fitting near the configured window, without
        # requesting inference on a deliberately oversized synthetic prompt.
        synthetic=[{'sourceId':'S'+str(n+1),'file':'budget-fixture.st','line':1,'endLine':300,'excerpt':'IF Enable THEN Motor := TRUE; END_IF\n'*300} for n in range(8)]
        fitted,_=am._fit_context([{'role':'system','content':'Use only cited source facts.'},{'role':'user','content':'Trace Motor'}],cfg,768,synthetic,facts={'summary':'source-only fixture'})
    assert result['passesCompleted']==2 and result['facts']
    assert not result['engineeringVerification']['trainingEligible']
    artifact={'runtimeContext':context,'modelMetadata':metadata,'requests':captures,'contextStressFit':fitted,'result':result}
    output=Path('.build/chopper-foundation/project2');output.mkdir(parents=True,exist_ok=True)
    (output/'harness.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'context':context,'trainedContext':metadata['n_ctx_train'],'parameters':metadata['n_params'],
                      'seconds':result['seconds'],'modelUsed':result['modelUsedForFactSelection'],'notice':result['modelNotice'],
                      'facts':len(result['facts']),'rag':result['rag'],'requests':captures,'stressFit':fitted},ensure_ascii=True),flush=True)
    print(result['answer'].encode('ascii',errors='backslashreplace').decode(),flush=True)


if __name__=='__main__':main()
