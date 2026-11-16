import threading
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from python_engine.source_compare import aligned_source


def test_identical_repeated_source_keeps_all_lines_without_sequence_search():
    text = ('Tag := TRUE;\n\n' * 10000) + 'END_PROGRAM'
    with patch('python_engine.source_compare.difflib.SequenceMatcher', side_effect=AssertionError('unnecessary search')):
        rows = aligned_source(text, text)
    assert len(rows) == len(text.splitlines())
    assert all(row['status'] == 'unchanged' and row['base'] == row['new'] for row in rows)
    assert rows[-1]['base_line'] == len(rows)


def test_declaration_cache_reuses_global_parsing_without_merging_private_scopes(tmp_path):
    from python_engine.ladder_model import declaration_symbols
    files = {}
    for relative, text in [('Logical/Global.var','VAR\nShared : BOOL;\nEND_VAR'),
                           ('Logical/A/Local.var','VAR\nPrivate : INT;\nEND_VAR'),
                           ('Logical/B/Local.var','VAR\nPrivate : REAL;\nEND_VAR')]:
        path = tmp_path / relative; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text); files[relative] = path
    reads = []
    def read(path):
        reads.append(path)
        return path.read_text()
    cache = {}
    first = declaration_symbols(files,'Logical/A/init.ld',read,cache)
    again = declaration_symbols(files,'Logical/A/cyclic.ld',read,cache)
    other = declaration_symbols(files,'Logical/B/cyclic.ld',read,cache)
    assert first == again
    assert first['private']['datatype'] == 'INT'
    assert other['private']['datatype'] == 'REAL'
    assert other['shared'] == first['shared']
    assert len(reads) == 3


def test_uploaded_job_returns_before_completion_and_publishes_progress(tmp_path, monkeypatch):
    from backend.api import comparison as module
    from backend.core import access
    ready, finish, stopped = threading.Event(), threading.Event(), threading.Event()
    sid = 'progress_fixture'

    async def stage(files, name):
        root = tmp_path / name
        root.mkdir(exist_ok=True)
        return sid, root

    def worker(job_id, *args):
        try:
            module.COMPARE_JOBS[job_id].update(status='running', phase='comparing', percent=45, message='Comparing main.st')
            ready.set()
            finish.wait(10)
            module.COMPARE_JOBS[job_id].update(status='complete', percent=100, result={'summary':{'modified':1}})
        finally:
            stopped.set()

    def require(value):
        if value != sid:
            raise HTTPException(403, 'Other account')

    monkeypatch.setattr(module, 'stage_project', stage)
    monkeypatch.setattr(module, 'WORK', tmp_path)
    monkeypatch.setattr(module, '_compare_worker', worker)
    monkeypatch.setattr(access, 'require_session', require)
    app = FastAPI(); app.include_router(module.router)
    try:
        with TestClient(app) as client:
            response = client.post('/api/compare/start', files=[('base_files', ('Base/main.st', b'A')), ('new_files', ('New/main.st', b'B'))], data={'base_name':'Base','new_name':'New'})
            assert response.status_code == 200, response.text
            assert response.json()['sessionId'] == sid
            assert ready.wait(5)
            progress = client.get('/api/local/compare/status/' + sid).json()
            assert progress['percent'] == 45 and progress['message'] == 'Comparing main.st'
            assert client.get('/api/local/compare/status/another_account').status_code == 403
            finish.set(); assert stopped.wait(5)
            assert client.get('/api/local/compare/status/' + sid).json()['status'] == 'complete'
            assert client.post('/api/compare/start').status_code == 400
    finally:
        finish.set(); stopped.wait(5)
        module.COMPARE_JOBS.pop(sid, None)


def test_engine_completion_does_not_publish_success_before_history_is_saved(tmp_path, monkeypatch):
    import json
    from backend.api import comparison as module
    sid = 'saving_fixture'
    (tmp_path/'Fixture.apj').write_text('<Project/>')
    (tmp_path/'compare_results.json').write_text(json.dumps({'summary':{'modified':1}}))
    class Process:
        stdout = [json.dumps({'event':'complete','percent':100})]
        def wait(self): return 0
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *args,**kwargs:Process())
    monkeypatch.setattr(module, 'COMPARE_LOG_DIR', tmp_path)
    def save(*args):
        assert module.COMPARE_JOBS[sid]['status'] == 'running'
        assert module.COMPARE_JOBS[sid]['phase'] == 'saving'
        assert module.COMPARE_JOBS[sid]['percent'] < 100
    monkeypatch.setattr(module, 'record_run', save)
    identity = dict(testId='test',historyId='history',machineDepartment='Demo',runKind='compare')
    try:
        module._compare_project(sid,tmp_path,tmp_path,tmp_path,'Base','New','','',identity)
        assert module.COMPARE_JOBS[sid]['status'] == 'complete'
        assert module.COMPARE_JOBS[sid]['percent'] == 100
    finally:
        module.COMPARE_JOBS.pop(sid, None)
