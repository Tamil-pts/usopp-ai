"""Verify an entire imported PLC configuration without changing its sources.

Usage: python -m virtual_plc.verify_project PROJECT --output DIRECTORY
The exit code is nonzero for active blockers, runtime faults or source changes.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from .core.project import analyze_project
from .core.runtime import VirtualRuntime
from virtual_plc import __version__
from python_engine.project_paths import project_files


def fingerprints(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project_files(root) if p.is_file()}


def verify(project, output, configuration=None, milliseconds=1000, cached=False,profile=None,corrections=None):
    root, out = Path(project).resolve(), Path(output).resolve()
    if out.is_relative_to(root):
        raise ValueError('Write readiness evidence outside the original PLC project.')
    out.mkdir(parents=True, exist_ok=True)
    before = fingerprints(root)
    started = time.monotonic()
    cache = out/'model.json'
    if cached and cache.is_file():
        model = json.loads(cache.read_text(encoding='utf-8'))
        if Path(model.get('root','')).resolve() != root:
            raise ValueError('The cached model belongs to another source directory.')
    else:
        model = analyze_project(root, configuration=configuration)
        cache.write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
    if model.get('executionScope'):
        raise ValueError('Full-project verification cannot use a partial execution scope.')
    model.pop('compatibility', None)
    if profile:model['simulationProfile']=json.loads(Path(profile).read_text(encoding='utf-8-sig'))
    if corrections:
        from .core.source_corrections import apply_corrections
        apply_corrections(model,json.loads(Path(corrections).read_text(encoding='utf-8-sig')))
    runtime = VirtualRuntime(model)
    errors = [d for d in runtime.diagnostics if d.get('severity')=='error' and not d.get('excluded')]
    compiled = not errors and runtime.run_allowed
    print(json.dumps({'stage':'compiled','runAllowed':compiled,'blockers':dict(Counter(d['code'] for d in errors))}), flush=True)
    if compiled:
        runtime.status='running'
        deadline=time.monotonic()+600
        next_progress=milliseconds/10
        while runtime.time_ms < milliseconds and runtime.status=='running':
            runtime.tick()
            if runtime.time_ms>=next_progress:
                print(json.dumps({'stage':'running','scans':runtime.scan_count,'timeMs':runtime.time_ms}),flush=True)
                next_progress+=milliseconds/10
            if time.monotonic()>deadline:
                runtime.status='paused'
                runtime.diagnostics.append({'severity':'error','code':'VERIFICATION_TIMEOUT','message':'Full-project run exceeded 600 seconds.'})
                break
        if runtime.status=='running':runtime.status='paused'
    after = fingerprints(root)
    result = {'moduleVersion':__version__,'project':str(root),'configuration':model.get('projectInfo',{}).get('activeConfiguration'),
              'completeMachineExecution':True,'sourceFiles':len(before),'sourcesUnchanged':before==after,
              'runAllowed':compiled,'status':runtime.status,'scans':runtime.scan_count,'timeMs':runtime.time_ms,
              'requestedTimeMs':milliseconds,'elapsedSeconds':round(time.monotonic()-started,3),
              'statistics':model.get('statistics',{}),'activeBlockers':errors,
              'simulationProfile':runtime.simulation_profile,
              'simulationSourceCorrections':model.get('sourceCorrections'),
              'blockersByCode':dict(Counter(d['code'] for d in errors)),
              'runtimeFaults':[d for d in runtime.diagnostics if d.get('code')=='RUNTIME_FAULT'],
              'tasks':[{'name':t['name'],'intervalMs':t.get('intervalMs'),'executionCount':t['executionCount'],
                        'programs':t.get('programs',[])} for t in runtime.tasks]}
    result['allTasksExecuted']=bool(runtime.tasks) and all(t['executionCount']>0 for t in runtime.tasks)
    result['passed']=compiled and result['allTasksExecuted'] and runtime.scan_count>0 and not result['runtimeFaults'] and runtime.time_ms>=milliseconds and before==after
    (out/'readiness.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'activeBlockers','tasks','statistics'}},ensure_ascii=False),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project');parser.add_argument('--output',required=True)
    parser.add_argument('--configuration');parser.add_argument('--milliseconds',type=float,default=1000)
    parser.add_argument('--cached',action='store_true')
    parser.add_argument('--profile',help='Explicit simulation initial values JSON; original source remains unchanged')
    parser.add_argument('--corrections',help='Reviewed source-copy corrections JSON with exact source hashes')
    args=parser.parse_args()
    if not 0<args.milliseconds<=3_600_000:parser.error('Use 0..3600000 virtual milliseconds.')
    result=verify(args.project,args.output,args.configuration,args.milliseconds,args.cached,args.profile,args.corrections)
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
