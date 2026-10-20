"""Export reproducible adapter acceptance evidence without changing PLC inputs.

Usage: python -m virtual_plc.tests.inspect_real_project --project PATH --output PATH
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from python_engine.project_paths import project_files
from virtual_plc.core.project import analyze_project


def inspect(project, output):
    project, output = Path(project).resolve(), Path(output).resolve()
    if output.is_relative_to(project):
        raise ValueError('Acceptance output must be outside the original PLC project.')
    before = {path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in project_files(project)}
    model = analyze_project(project, progress=lambda event: print(
        event['stage'], event.get('indexedFiles', 0), '/', event.get('totalFiles', 0), flush=True))
    after = {path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in project_files(project)}
    evidence = {'project': str(project), 'statistics': model['statistics'],
                'controllers': [{'name': item['name'], 'model': item['model']} for item in model['hardware']['controllers']],
                'modules': len(model['hardware']['modules']), 'channels': len(model['hardware']['channels']),
                'tasks': [{'name': task['name'], 'intervalMs': task['intervalMs'], 'programCount': len(task['programs']),
                           'initProgramCount': len(task['initializationPrograms'])} for task in model['tasks']],
                'interfaces': len(model['interfaces']), 'diagnosticCount': model['diagnosticCount'],
                'diagnosticsByCode': dict(Counter(row['code'] for row in model['diagnostics'])),
                'sourceFilesHashed': len(before), 'sourcesUnchanged': before == after,
                'notes': ['Import proves static project representation, not whole-project execution compatibility.',
                          'Original source hashes include all non-generated files, including hardware and HMI resources.']}
    if before != after:
        raise AssertionError('Original project files changed during analysis.')
    if not model['files'] or not model['programs'] or not model['variables']:
        raise AssertionError('Real project import did not establish source, programs and variable declarations.')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'real_project_model.json').write_text(json.dumps(model, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    (output / 'real_project_adapter_results.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(json.dumps(evidence, indent=2), flush=True)
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    inspect(options.project, options.output)
