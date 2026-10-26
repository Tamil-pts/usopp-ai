"""Repeatable local benchmark. Synthetic records live ONLY in a new temporary root.

No model calls, production writes, network services or application lifespan hooks.
API measurements exercise the existing authenticated WorkHub router with a fixture
principal; they exclude password verification, transport and reverse proxy latency.
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc
import threading

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def stats(values):
    ordered = sorted(values)
    return {'samples': len(values), 'median_ms': round(statistics.median(values), 3),
            'p95_ms': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='usopp-perf-') as root:
        os.environ['USOPP_DATA_ROOT'] = root
        os.environ['USOPP_PI_WORKER_MODE'] = 'external'
        # Runtime normally seeds bundled company knowledge into a new data root.
        # A synthetic benchmark needs no bundled data and must not copy it.
        from unittest.mock import patch
        original_rglob = Path.rglob
        def fixture_rglob(path, pattern):
            return iter(()) if path in {REPO/'knowledge', REPO/'rules'} else original_rglob(path, pattern)
        with patch.object(Path, 'rglob', fixture_rglob):
            from backend.core import runtime
        from backend.core import accounts
        import logging
        logging.getLogger('httpx').setLevel(logging.WARNING)
        import psutil
        samples = []; monitor_stop = threading.Event()
        def monitor():
            process = psutil.Process()
            while not monitor_stop.wait(.05):
                samples.append(process.memory_info().rss)
        monitor_thread = threading.Thread(target=monitor, daemon=True); monitor_thread.start()
        from backend.core.workhub import store as hub, identity, timestamp, encode
        from backend.core.workhub_intelligence import store, documents
        user = {'id': 900001, 'username': 'Benchmark engineer', 'designation': 'Engineer',
                'role': 'admin', 'active': True, 'approved': True, 'isDemo': False}
        accounts.store.list_users = lambda: [user]
        store.initialize()
        pid = hub.create(user, {'title': 'Synthetic performance fixture'})['id']
        # Representative bounded dashboard: 150 source documents and 400 jobs.
        with hub.db(True) as db:
            for i in range(150):
                store.create_document(db, user, pid, 'source', f'Fixture {i}', {'body': 'Fixture text'})
            for i in range(400):
                db.execute('INSERT INTO pi_jobs(id,project_id,kind,payload,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                           (identity(), pid, 'extract', encode({}), 'completed', user['id'], timestamp(), timestamp()))
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.api.workhub_intelligence import router
        app = FastAPI()
        @app.middleware('http')
        async def fixture_principal(request, call_next):
            request.state.user = user
            return await call_next(request)
        app.include_router(router)
        output = {'fixture': {'documents': 150, 'jobs': 400, 'pdf_pages': 40},
                  'scope': 'Local router, fixture principal; no external AI/OCR/Docker or real accounts',
                  'version': json.loads((REPO/'package.json').read_text())['version'], 'api': {}}
        with TestClient(app) as client:
            url = '/api/workhub/projects/'+pid+'/intelligence'
            assert client.get(url).status_code == 200
            for concurrency in (1, 4, 8):
                def request(_):
                    start = time.perf_counter()
                    response = client.get(url)
                    assert response.status_code == 200, response.text
                    return (time.perf_counter()-start)*1000
                begin = time.perf_counter()
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                    values = list(executor.map(request, range(40)))
                output['api'][str(concurrency)] = {**stats(values), 'requests_per_second': round(40/(time.perf_counter()-begin), 2)}
        from reportlab.pdfgen.canvas import Canvas
        stream = io.BytesIO(); canvas = Canvas(stream)
        for i in range(40):
            for line in range(35):
                canvas.drawString(30, 800-line*20, f'Engineering fixture page {i+1} line {line+1}: input feedback and reviewed requirements.')
            canvas.showPage()
        canvas.save()
        file = documents.generated_file(user, pid, 'fixture.pdf', stream.getvalue())
        tracemalloc.start(); times = []
        for _ in range(6):
            begin = time.perf_counter(); value = documents.extract(file['id'], pid)
            times.append((time.perf_counter()-begin)*1000)
            assert len(value['sources']) == 40
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        output['extraction'] = {'cold_ms': round(times[0], 3), 'repeat': stats(times[1:]),
                                'python_peak_bytes': peak, 'source_count': len(value['sources']),
                                'content_hash': hashlib.sha256(value['text'].encode()).hexdigest()}
        db = __import__('sqlite3').connect(hub.root/'projects.sqlite3')
        output['database_integrity'] = db.execute('PRAGMA integrity_check').fetchone()[0]; db.close()
        monitor_stop.set(); monitor_thread.join()
        output['rss_peak_bytes'] = max(samples, default=0)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(output, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(output, indent=2))
        for handler in logging.getLogger().handlers[:]:
            if isinstance(handler, logging.FileHandler):
                handler.close(); logging.getLogger().removeHandler(handler)


if __name__ == '__main__':
    main()
