"""Opt-in local-model answer checks against an existing owner-scoped PLC index.

Usage: python scripts/verify_chopper_pipeline.py --index KEY --question "..." --inference
No model configuration, PLC source, packet validator or persistent file index is changed.
Machine-analysis caches and resumable analysis findings are written locally.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.core import assist_model as am,local_model_runtime as runtime,project_assistant as pa,project_intelligence as pi
from python_engine.machine_function_engine import analyze


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--index',required=True);parser.add_argument('--question',required=True)
    parser.add_argument('--batches',type=int,default=4);parser.add_argument('--inference',action='store_true')
    parser.add_argument('--label',default='answer')
    args=parser.parse_args()
    if not __import__('re').fullmatch('[a-f0-9]{64}',args.index):parser.error('Invalid index key')
    path=pi.WORK/'chopper_intelligence'/args.index/'project.sqlite3'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        root=json.loads(db.execute("SELECT value FROM meta WHERE key='root'").fetchone()[0])
        indexed_before=db.execute('SELECT count(*) FROM files').fetchone()[0]
    index=pi.Index.__new__(pi.Index);index.path=path;index.key=args.index;index.root=Path(root);index.owner='local-pipeline-verification'
    machine=analyze(index)
    if not args.inference:
        print(json.dumps(machine['coverage'],ensure_ascii=True));return
    cfg=am.configuration();assert cfg['provider']=='embedded'
    base=cfg['baseUrl'].removesuffix('/v1')
    health=am.requests.get(base+'/health',timeout=5);health.raise_for_status()
    props=am.requests.get(base+'/props',timeout=5).json();context=props['default_generation_settings']['n_ctx']
    output=Path('.build/chopper-pipeline-correction');output.mkdir(parents=True,exist_ok=True)
    requests=[];real_post=am.requests.post
    def post(url,**kwargs):
        is_model=url.endswith('/chat/completions')
        record=None
        if is_model:
            body=kwargs.get('json') or {};record={'messages':body.get('messages'),'reservedTokens':body.get('max_tokens'),'started':time.time()};requests.append(record)
        response=real_post(url,**kwargs)
        if record is not None:
            data=response.json();record.update(status=response.status_code,usage=data.get('usage'),choices=data.get('choices'),seconds=round(time.time()-record['started'],2))
        return response
    def progress(message,**details):
        if 'batch' in message.lower():print(message,flush=True)
    started=time.monotonic()
    with patch.object(pa,'opened',return_value=index),patch.object(pa,'report',progress),patch('backend.core.engineering_analysis.report',progress),patch.object(runtime,'status',return_value={'ready':True,'contextLimit':context}),patch.object(am.requests,'post',side_effect=post):
        result=pa.answer({'question':args.question,'context':{'intelligenceProjectId':index.key,'analysisBatchLimit':args.batches}})
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        assert indexed_before==db.execute('SELECT count(*) FROM files').fetchone()[0]
    summary={'question':args.question,'project':index.root.name,'elapsedSeconds':round(time.monotonic()-started,2),
             'source':result.get('source'),'modelNotice':result.get('modelNotice'),'coverage':result['retrieval']['coverage'],
             'requestCount':len(requests),'maxPromptTokens':max((row.get('usage',{}).get('prompt_tokens',0) for row in requests),default=0),
             'contextLimit':context,'actualIndexRecords':indexed_before}
    for record in requests:
        if record.get('usage'):assert record['usage']['prompt_tokens']+record['reservedTokens']<=context
    artifact={'summary':summary,'answer':result['answer'],'evidence':result['evidence'],'retrieval':result['retrieval'],'requests':requests,
              'engineeringVerification':result.get('engineeringVerification'),'machineAnalysis':result.get('machineAnalysis')}
    (output/(args.label+'.json')).write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True),flush=True)
    print(result['answer'][:3000].encode('ascii',errors='backslashreplace').decode(),flush=True)


if __name__=='__main__':main()
