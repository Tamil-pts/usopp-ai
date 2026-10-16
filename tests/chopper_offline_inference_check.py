"""Opt-in local inference check. Requires the app-owned model already on loopback.

Does not connect to a PLC, download, switch models, or write PLC project files.
"""
import json
from pathlib import Path
import sys
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.core import assist_model,local_model_runtime
from backend.core.project_intelligence import Index
from backend.core.project_assistant import answer
from backend.core.run_history import current_user

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'.build/chopper-intelligence-qa'


def run():
    config=assist_model.configuration()
    assert config['provider']=='embedded','Select the bundled local CPU model first.'
    port=int(config['localPort'])
    assert requests.get(f'http://127.0.0.1:{port}/health',timeout=3).status_code==200
    # This test client is a separate Python process from the API. Only its
    # status adapter is substituted; inference and tokenizer calls stay real.
    local_model_runtime.status=lambda:{'ready':True,'contextLimit':config['contextSize']}
    assist_model.configuration=lambda:{**config,'maxTokens':400}
    index=Index(ROOT.parent/'project 2','offline-inference-check')
    index.build(mode='rebuild')
    token=current_user.set({'id':'offline-inference-check'})
    try:
        scope=answer({'question':'In LUB.ab is TIME_IN_SEC inside START or outside it?',
                      'context':{'intelligenceProjectId':index.key}})
        assert scope['source']=='local-control-flow' and 'no enclosing' in scope['answer']
        result=answer({'question':'In LUB.ab explain only how TIME_IN_SEC = LUB_TIME_IN_HOUR * 60 * 60 converts hours to seconds. Begin with [S1].',
                       'context':{'intelligenceProjectId':index.key}})
    finally:current_user.reset(token)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/'3b-live-answer-final.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({key:result.get(key) for key in ('source','modelNotice','responseSeconds','contextUsage')}),flush=True)
    assert result['source']=='embedded' and '[S1]' in result['answer']
    assert '60' in result['answer'] or '3600' in result['answer'] or '3,600' in result['answer']
    assert result['contextUsage']['usedTokens']<=config['contextSize']
    print('Offline source-cited 3B inference and control scope checks passed.',flush=True)


if __name__=='__main__':run()
