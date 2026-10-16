"""Explicit large-index check: synthetic scale plus a supplied real PLC project."""
import hashlib,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.core import project_intelligence as pi

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'.build/chopper-intelligence-qa';OUTPUT.mkdir(parents=True,exist_ok=True)
pi.WORK=OUTPUT/'indexes'

def fingerprint(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in pi.Index(root,'qa').discover(__import__('threading').Event(),{},lambda:None)}

def check(root,label):
    from backend.core.runtime import locate_root
    root=locate_root(root) if label.startswith('Supplied') else root
    before=fingerprint(root);i=pi.Index(root,'qa');start=time.monotonic();first=i.build(mode='rebuild');duration=round(time.monotonic()-start,2)
    start=time.monotonic();second=i.build();incremental=round(time.monotonic()-start,2)
    start=time.monotonic();r=i.retrieve('MotorRun Start Fault ip_addr motor interlock',characters=16000);retrieval=round(time.monotonic()-start,3)
    assert before==fingerprint(root),'Indexing must not change PLC sources'
    assert first['ready'] and second['changedFiles']==0 and r['evidence']
    result={'label':label,'buildSeconds':duration,'unchangedRefreshSeconds':incremental,'retrievalSeconds':retrieval,'index':second,'retrievalPasses':r['passes'],'retrievedSections':len(r['evidence']),'sourcesUnchanged':True,'databaseMB':round(i.path.stat().st_size/1048576,2)}
    print(json.dumps({k:v for k,v in result.items() if k!='index'}),flush=True)
    return result

synthetic=OUTPUT/'synthetic-10000';synthetic.mkdir(exist_ok=True)
for n in range(10000):
    folder=synthetic/f'Task{n//100:03}';folder.mkdir(exist_ok=True)
    (folder/f'Routine{n:05}.st').write_text(f'PROGRAM Routine{n}\nVAR\nMotorRun{n} : BOOL;\nEND_VAR\nIF Start{n} AND NOT Fault{n} THEN\nMotorRun{n} := TRUE;\nEND_IF;\nEND_PROGRAM',encoding='utf-8')
results=[check(synthetic,'Synthetic 10,000 PLC source files')]
for project in (ROOT.parent/'project 2',ROOT.parent/'Project 3'):
    if project.is_dir():results.append(check(project,'Supplied real project: '+project.name))
(OUTPUT/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('Saved '+str(OUTPUT/'results.json'),flush=True)
