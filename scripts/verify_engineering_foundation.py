"""Explicit local architecture build/audit, without LLM calls or validation-engine changes."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.core.project_intelligence import Index, WORK
from python_engine.engineering_model import build, EngineeringModel


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--index',required=True);parser.add_argument('--label',default='reference')
    args=parser.parse_args()
    if not re.fullmatch('[a-f0-9]{64}',args.index):parser.error('Invalid index key')
    if not re.fullmatch('[A-Za-z0-9_-]+',args.label):parser.error('Invalid report label')
    index=Index.__new__(Index);index.path=WORK/'chopper_intelligence'/args.index/'project.sqlite3';index.key=args.index
    with closing(sqlite3.connect(index.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        index.root=Path(json.loads(db.execute("SELECT value FROM meta WHERE key='root'").fetchone()[0]));count=db.execute('SELECT count(*) FROM files').fetchone()[0]
    started=time.monotonic();structure=build(index);model=EngineeringModel(index)
    trace=model.trace_signal('DO_CAN_CHANGER_MOTOR',limit=80)
    # The model is new; the existing index remains a read-only input.
    with closing(sqlite3.connect(index.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:assert count==db.execute('SELECT count(*) FROM files').fetchone()[0]
    result={'seconds':round(time.monotonic()-started,2),'indexedFilesUnchanged':count,'structure':structure,
            'validation':model.validate(limit=30),'motorTrace':trace,'flow':model.execution_flow(limit=20),
            'canChangeCandidates':model.find_function('can changer doffing',limit=12),
            'privateTempDeclarations':model.blocks(kind='variable',q='TEMP',limit=100)}
    output=Path('.build/chopper-foundation')/args.label;output.mkdir(parents=True,exist_ok=True)
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'seconds':result['seconds'],'files':structure['counts']['files'],'blocks':structure['counts']['blocks'],
                      'relations':structure['counts']['relations'],'sourceTokens':structure['sourceTokens'],
                      'validation':structure['validation'],'activeContexts':len(result['flow']['contexts']),
                      'motorResolved':trace['resolved'],'artifact':str(output/'results.json')},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
