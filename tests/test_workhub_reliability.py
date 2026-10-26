"""Targeted reliability checks. Run directly to isolate every record and child.

    .venv/Scripts/python.exe tests/test_workhub_reliability.py

No production account/database/model service is used.
"""
import concurrent.futures
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))


class Reliability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='usopp-reliability-')
        cls.patches=ExitStack()
        cls.patches.enter_context(patch.dict(os.environ,{'USOPP_DATA_ROOT':cls.folder.name,'USOPP_PI_WORKER_MODE':'external','USOPP_PI_CHILD':'1','USOPP_LLM_PROVIDER':'local'}))
        from backend.core import accounts
        from backend.core import assist_model
        from backend.core.workhub import store as hub
        from backend.core.workhub_intelligence import store,jobs,documents,cache,reliability,resources
        from backend.core.workhub_quality import store as qc,configuration
        cls.patches.enter_context(patch.object(accounts,'store',accounts.AccountStore(Path(cls.folder.name)/'accounts.sqlite3')))
        cls.patches.enter_context(patch.object(hub,'root',Path(cls.folder.name)/'.usopp_workhub'))
        cls.patches.enter_context(patch.object(hub,'ready',False))
        cls.patches.enter_context(patch.object(assist_model,'CONFIG',Path(cls.folder.name)/'.usopp_assist_model.json'))
        cls.hub=hub;cls.store=store;cls.jobs=jobs;cls.documents=documents;cls.cache=cache;cls.reliability=reliability;cls.resources=resources;cls.qc=qc;cls.configuration=configuration
        qc.initialize()
        cls.user=accounts.store.register('Reliability fixture','Fixture-password-123!','Engineer','Fixture')
        with accounts.store.db() as db:db.execute("UPDATE users SET active=1,approved=1,role='admin' WHERE id=?",(cls.user['id'],))
        cls.user=next(u for u in accounts.store.list_users() if u['id']==cls.user['id'])
        logging.getLogger('httpx').setLevel(logging.WARNING)

    @classmethod
    def tearDownClass(cls):
        for handler in logging.getLogger().handlers[:]:
            if isinstance(handler,logging.FileHandler) and Path(handler.baseFilename).is_relative_to(cls.folder.name):handler.close();logging.getLogger().removeHandler(handler)
        cls.patches.close()
        cls.folder.cleanup()

    def setUp(self):
        self.pid=self.hub.create(self.user,{'title':'Reliability fixture '+self.id()})['id']

    def tearDown(self):
        with self.hub.db(True) as db:db.execute("UPDATE pi_jobs SET status='cancelled',lease_until=0 WHERE status IN ('queued','running')")

    def file(self,name='fixture.txt',data=b'The PLC shall retain the reviewed alarm state.',pid=None):
        return self.documents.generated_file(self.user,pid or self.pid,name,data)

    def queued(self,kind='extract',payload=None):
        return self.jobs.enqueue(self.user,self.pid,kind,payload or {'file_ids':[self.file()['id']]})['id']

    def test_01_additive_schema_and_canonical_idempotency(self):
        file=self.file();first=self.queued(payload={'file_ids':[file['id']],'format':'pdf'})
        second=self.queued(payload={'format':'pdf','file_ids':[file['id']]})
        self.assertEqual(first,second)
        with self.hub.db(True) as db:
            self.reliability.migrate(db)
            db.execute("UPDATE pi_jobs SET status='completed' WHERE id=?",(first,))
        self.assertEqual(first,self.queued(payload={'format':'pdf','file_ids':[file['id']]}))

    def test_02_project_references_and_write_permissions(self):
        other=self.hub.create(self.user,{'title':'Other project'})['id'];file=self.file(pid=other)
        with self.assertRaises(self.jobs.HTTPException) as error:self.queued(payload={'file_ids':[file['id']]})
        self.assertEqual(error.exception.status_code,404)
        outsider={**self.user,'id':999999,'role':'user'}
        with self.assertRaises(self.jobs.HTTPException) as error:self.jobs.enqueue(outsider,self.pid,'extract',{})
        self.assertEqual(error.exception.status_code,403)
        with self.assertRaises(self.jobs.HTTPException):self.documents.extract(file['id'],self.pid)

    def test_03_backpressure_and_memory_admission(self):
        self.queued()
        with patch.dict(os.environ,{'USOPP_PI_MAX_PENDING':'1'}):
            with self.assertRaises(self.jobs.HTTPException) as error:self.queued()
            self.assertEqual(error.exception.status_code,429)
        with patch.object(self.resources,'memory',return_value={'available_bytes':1}):
            self.assertIn('memory',self.resources.admission())
            self.assertIsNone(self.jobs.claim())

    def test_04_lease_recovery_and_poison_limit(self):
        key=self.queued();first=self.jobs.claim();self.assertEqual(first.row['id'],key)
        self.assertIsNone(self.jobs.claim())
        with self.hub.db(True) as db:db.execute('UPDATE pi_jobs SET lease_until=0 WHERE id=?',(key,))
        second=self.jobs.claim();self.assertEqual(second.row['id'],key);self.assertNotEqual(second.lease,first.lease)
        self.assertEqual(second.row['attempts'],2)
        with self.assertRaises(InterruptedError):first.check()
        with self.hub.db(True) as db:db.execute('UPDATE pi_jobs SET lease_until=0,attempts=max_attempts WHERE id=?',(key,))
        self.assertIsNone(self.jobs.claim());self.assertFalse(self.jobs.get_job(self.user,self.pid,key)['can_retry'])

    def test_05_real_child_restart_does_not_duplicate_revision(self):
        key=self.queued();job=self.jobs.claim();self.jobs.execute(job,threading.Event())
        result=self.jobs.get_job(self.user,self.pid,key)
        self.assertEqual(result['status'],'completed',result)
        rid=result['result']['revision_id']
        with self.hub.db(True) as db:db.execute("UPDATE pi_jobs SET status='queued',lease_until=0 WHERE id=?",(key,))
        self.jobs.execute(self.jobs.claim(),threading.Event())
        recovered=self.jobs.get_job(self.user,self.pid,key)
        self.assertEqual(recovered['result']['revision_id'],rid)
        with self.hub.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM pi_revisions WHERE generated_by=?',(key,)).fetchone()[0],1)
            self.assertEqual(db.execute('SELECT status FROM pi_revisions WHERE id=?',(rid,)).fetchone()[0],'draft')

    def _slow_child(self):
        import psutil
        original=subprocess.Popen;captured=[]
        def spawn(*args,**kwargs):
            process=original([sys.executable,'-c','import subprocess,sys,time;subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);time.sleep(60)'],**kwargs)
            captured.append(process);return process
        return spawn,captured,psutil

    def test_06_cancellation_stops_native_descendants(self):
        key=self.queued();job=self.jobs.claim();spawn,captured,psutil=self._slow_child()
        with patch.object(self.jobs.subprocess,'Popen',side_effect=spawn):
            thread=threading.Thread(target=self.jobs.execute,args=(job,threading.Event()));thread.start()
            until=time.monotonic()+5
            while not captured and time.monotonic()<until:time.sleep(.02)
            self.assertTrue(captured);time.sleep(.4)
            pids=[p.pid for p in psutil.Process(captured[0].pid).children(recursive=True)]
            self.jobs.cancel(self.user,self.pid,key);thread.join(timeout=8)
        self.assertFalse(thread.is_alive());self.assertIsNotNone(captured[0].poll())
        self.assertTrue(all(not psutil.pid_exists(pid) for pid in pids))
        self.assertEqual(self.jobs.get_job(self.user,self.pid,key)['status'],'cancelled')

    def test_07_timeout_and_graceful_restart(self):
        key=self.queued();job=self.jobs.claim();spawn,captured,_=self._slow_child()
        with patch.object(self.jobs.subprocess,'Popen',side_effect=spawn),patch.dict(os.environ,{'USOPP_PI_JOB_TIMEOUT':'1'}):self.jobs.execute(job,threading.Event())
        result=self.jobs.get_job(self.user,self.pid,key);self.assertEqual(result['error_code'],'timeout');self.assertTrue(result['can_retry'])
        self.jobs.retry(self.user,self.pid,key);job=self.jobs.claim();stop=threading.Event();stop.set()
        with patch.object(self.jobs.subprocess,'Popen',side_effect=spawn):self.jobs.execute(job,stop)
        self.assertEqual(self.jobs.get_job(self.user,self.pid,key)['status'],'queued')
        self.assertTrue(all(p.poll() is not None for p in captured))

    def test_08_unchanged_revision_cache_and_project_partition(self):
        file=self.file();original=self.documents._extract
        with patch.object(self.documents,'_extract',wraps=original) as extract:
            a=self.documents.extract(file['id'],self.pid);b=self.documents.extract(file['id'],self.pid)
            self.assertEqual(extract.call_count,1);self.assertEqual(a['sources'],b['sources']);self.assertTrue(b['processing']['cache_hit'])
            copy=self.file(name='renamed.txt');c=self.documents.extract(copy['id'],self.pid)
            self.assertEqual(extract.call_count,1);self.assertEqual(c['sources'][0]['file_id'],copy['id']);self.assertEqual(c['sources'][0]['filename'],'renamed.txt')
            pid=self.hub.create(self.user,{'title':'Cache partition'})['id'];other=self.file(pid=pid)
            self.documents.extract(other['id'],pid);self.assertEqual(extract.call_count,2)

    def test_09_simultaneous_cache_misses_compute_once(self):
        file=self.file();count=0;lock=threading.Lock();original=self.documents._extract
        def slow(*args):
            nonlocal count
            with lock:count+=1
            time.sleep(.1);return original(*args)
        with patch.object(self.documents,'_extract',side_effect=slow),concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            values=list(executor.map(lambda _:self.documents.extract(file['id'],self.pid),range(4)))
        self.assertEqual(count,1);self.assertTrue(all(v['text']==values[0]['text'] for v in values))

    @staticmethod
    def pdf(second='Original second page'):
        from reportlab.pdfgen.canvas import Canvas
        out=io.BytesIO();canvas=Canvas(out,invariant=1)
        for text in ('Stable first page',second):canvas.drawString(30,750,text);canvas.showPage()
        canvas.save();return out.getvalue()

    def test_10_incremental_pdf_reuses_unchanged_page(self):
        a=self.file('a.pdf',self.pdf());b=self.file('b.pdf',self.pdf('Revised second page'))
        self.documents.extract(a['id'],self.pid);value=self.documents.extract(b['id'],self.pid)
        self.assertIn('Revised second page',value['text'])
        with self.hub.db() as db:hits=db.execute("SELECT SUM(hits) FROM pi_cache WHERE project_id=? AND processor='pdf-page-v1'",(self.pid,)).fetchone()[0]
        self.assertGreaterEqual(hits,1)

    def test_11_cache_integrity_and_durable_output_identity(self):
        file=self.file();self.documents.extract(file['id'],self.pid)
        with self.hub.db(True) as db:db.execute("UPDATE pi_cache SET output=X'01' WHERE project_id=? AND processor='extract-v2'",(self.pid,))
        self.assertIn('PLC',self.documents.extract(file['id'],self.pid)['text'])
        key=self.queued();job=self.jobs.claim();token=self.resources.CURRENT_JOB.set(job)
        try:
            a=self.file('generated.txt',b'Generated reviewed draft');b=self.file('generated.txt',b'Retry has the same output slot')
            self.assertEqual(a['id'],b['id'])
        finally:self.resources.CURRENT_JOB.reset(token)

    def test_12_inference_global_limit_and_expired_reservation(self):
        active=0;peak=0;lock=threading.Lock()
        def call(_):
            nonlocal active,peak
            with self.resources.inference_slot():
                with lock:active+=1;peak=max(peak,active)
                time.sleep(.06)
                with lock:active-=1
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:list(executor.map(call,range(3)))
        self.assertEqual(peak,1)
        with self.hub.db(True) as db:db.execute("INSERT INTO pi_inference(id,state,created,expires) VALUES('expired','running',0,0)")
        with self.resources.inference_slot():pass
        with self.hub.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM pi_inference').fetchone()[0],0)

    def test_13_source_changes_invalidate_derived_results(self):
        with self.hub.db(True) as db:doc,rev=self.store.create_document(db,self.user,self.pid,'source','Requirements',{'body':'Original requirements'})
        key=self.queued('document_answer',{'document_id':doc['id'],'question':'Explain requirements'})
        with self.hub.db(True) as db:self.store.create_document(db,self.user,self.pid,'source','Requirements',{'body':'Changed requirements'},document_id=doc['id'],expected_revision=rev['id'])
        with self.hub.db() as db:
            self.assertTrue(self.reliability.source_changed(db,dict(db.execute('SELECT * FROM pi_jobs WHERE id=?',(key,)).fetchone())))
            with self.assertRaises(self.reliability.SourceChanged):self.reliability.guard_generation(db,key)

    def test_14_transaction_safe_administrator_numbering(self):
        def allocate(_):
            with self.hub.db(True) as db:return self.configuration.allocate(db,'frd',self.configuration.current(db))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:numbers=list(executor.map(allocate,range(16)))
        self.assertEqual(len(set(numbers)),16)
        self.assertTrue(all('PTPL' in number and 'ES' in number and 'PLC' in number for number in numbers))

    def test_15_paginated_status_and_control_permissions(self):
        for _ in range(4):self.queued()
        page=self.jobs.list_jobs(self.user,self.pid,2);self.assertEqual(len(page['jobs']),2);self.assertTrue(page['next_cursor'])
        next_page=self.jobs.list_jobs(self.user,self.pid,2,page['next_cursor'])
        self.assertFalse(set(j['id'] for j in page['jobs'])&set(j['id'] for j in next_page['jobs']))
        outsider={**self.user,'role':'user','id':999999}
        self.assertFalse(self.jobs.list_jobs(outsider,self.pid,2)['jobs'][0]['can_cancel'])
        with self.assertRaises(self.jobs.HTTPException):self.jobs.cancel(outsider,self.pid,page['jobs'][0]['id'])

    def test_16_health_has_real_bounded_metrics(self):
        self.reliability.record_latency('/api/workhub/projects/{project_id}/intelligence',12.5)
        health=self.reliability.health();self.assertGreater(health['disk']['free_bytes'],0)
        self.assertTrue(health['api_latency']);self.assertIn('available_bytes',health['memory'])
        self.assertNotIn('payload',json.dumps(health))

    def test_17_controlled_frd_child_and_http_replay(self):
        file=self.file('requirement.txt',b'The PLC shall display the motor alarm on the HMI.')
        payload={'stage':'frd','file_ids':[file['id']]};key=self.queued('q_generate',payload)
        self.jobs.execute(self.jobs.claim(),threading.Event());result=self.jobs.get_job(self.user,self.pid,key)
        self.assertEqual(result['status'],'completed',result);self.assertFalse(result['source_changed'])
        self.assertEqual(self.queued('q_generate',payload),key)
        # Downstream FAT preparation must not invalidate its upstream FRD.
        from backend.core.workhub_quality import documents as controlled
        controlled.draft(self.user,self.pid,'fat',{'cases':[],'sources':[]},'Fixture FAT draft')
        self.assertFalse(self.jobs.get_job(self.user,self.pid,key)['source_changed'])
        with self.hub.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM qc_documents WHERE project_id=? AND stage='frd'",(self.pid,)).fetchone()[0],1)
            revision=db.execute('SELECT status,approved_by FROM qc_revisions WHERE id=?',(result['result']['revision_id'],)).fetchone()
            self.assertEqual(revision['status'],'draft');self.assertIsNone(revision['approved_by'])

    def test_18_iso_retry_reuses_package_file_and_number(self):
        from backend.core.workhub import identity,timestamp
        file=self.file('internal-package.pdf',self.pdf())
        with self.hub.db(True) as db:db.execute('INSERT INTO qc_packages VALUES(?,?,?,?,?,?,?,?,?,?,?)',(identity(),self.pid,'internal',1,'fixture-baseline','[]',file['id'],file['sha256'],self.user['id'],timestamp(),0))
        key=self.queued('q_iso',{'project_ids':[self.pid]});self.jobs.execute(self.jobs.claim(),threading.Event())
        result=self.jobs.get_job(self.user,self.pid,key);self.assertEqual(result['status'],'completed',result)
        with self.hub.db(True) as db:db.execute("UPDATE pi_jobs SET status='queued',lease_until=0 WHERE id=?",(key,))
        self.jobs.execute(self.jobs.claim(),threading.Event());recovered=self.jobs.get_job(self.user,self.pid,key)
        self.assertEqual(recovered['result']['package_id'],result['result']['package_id'])
        with self.hub.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM qc_packages WHERE project_id=? AND audience='iso'",(self.pid,)).fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM files WHERE project_id=? AND name LIKE 'QC-ISO-%'",(self.pid,)).fetchone()[0],1)

    def test_19_invalid_model_citations_are_not_published_or_cached(self):
        from backend.core.workhub_intelligence import job_runner,local_ai,processing
        key=self.queued('frd',{'reason':'Fixture'});job=self.jobs.claim()
        def invalid(job,user):
            result=local_ai.llm_json('Fixture schema',{'sources':[{'id':'known','text':'Source'}]},job.check)
            processing._claims(result['requirements'],{'known':{'id':'known'}},'requirement')
        with patch.object(local_ai,'_llm_json',return_value={'requirements':[{'title':'Unsupported','source_ids':['unknown']}]}),patch.object(processing,'process',side_effect=invalid):job_runner.run(key,job.lease)
        result=self.jobs.get_job(self.user,self.pid,key);self.assertEqual(result['status'],'failed');self.assertTrue(result['can_retry'])
        with self.hub.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pi_cache WHERE project_id=? AND processor='llm-json-v1'",(self.pid,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM pi_documents WHERE project_id=?',(self.pid,)).fetchone()[0],0)

    def test_20_queued_export_preserves_existing_reader_access(self):
        from backend.core import accounts
        from backend.core.workhub_intelligence import exports
        from backend.core.workhub_quality import packages
        reader=accounts.store.register('Export reader','Fixture-password-123!','Engineer','Fixture')
        with accounts.store.db() as db:db.execute('UPDATE users SET active=1,approved=1 WHERE id=?',(reader['id'],))
        reader=next(u for u in accounts.store.list_users() if u['id']==reader['id'])
        with self.hub.db(True) as db:doc,rev=self.store.create_document(db,self.user,self.pid,'note','Review notes',{'body':'Reviewed source notes'})
        payload={'document_id':doc['id'],'revision_id':rev['id'],'format':'pdf'}
        key=self.jobs.enqueue(reader,self.pid,'export',payload)['id'];self.jobs.execute(self.jobs.claim(),threading.Event())
        result=self.jobs.get_job(reader,self.pid,key);self.assertEqual(result['status'],'completed',result)
        value,path=exports.download(reader,self.pid,key);self.assertTrue(path.read_bytes().startswith(b'%PDF'))
        self.assertEqual(self.jobs.enqueue(reader,self.pid,'export',payload)['id'],key)
        with self.hub.db() as db:
            file=db.execute('SELECT * FROM files WHERE id=?',(value['file_id'],)).fetchone()
            with self.assertRaises(self.jobs.HTTPException):packages.file_access(db,reader,file)

    def test_21_controlled_export_cache_tracks_draft_versions(self):
        from backend.core.workhub_quality import documents as controlled
        doc=controlled.draft(self.user,self.pid,'frd',{'requirements':[],'sources':[]},'Fixture')
        payload={'control_id':doc['control_id'],'revision_id':doc['revision_id'],'format':'pdf'}
        key=self.queued('q_export',payload);self.jobs.execute(self.jobs.claim(),threading.Event())
        self.assertEqual(self.jobs.get_job(self.user,self.pid,key)['status'],'completed')
        self.assertEqual(self.queued('q_export',payload),key)
        # Use the existing optimistic-save path; the approved-record rules stay intact.
        with self.hub.db(True) as db:
            p=self.qc.project(db,self.pid,self.user,True);control=self.qc.control(db,self.pid,doc['control_id']);rev=self.qc.revision(db,control['id'],doc['revision_id'])
            content=self.store.revision(db,rev['id'],control['document_id'])['content'];content['purpose']='Updated purpose'
            controlled._save(db,self.user,p,control,rev,content,rev['version'])
        self.assertTrue(self.jobs.get_job(self.user,self.pid,key)['source_changed'])
        self.assertNotEqual(self.queued('q_export',payload),key)

    def test_22_child_uses_existing_private_model_transport(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        config=Path(self.folder.name)/'.usopp_assist_model.json';seen=[]
        class Model(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                request=json.loads(self.rfile.read(int(self.headers['Content-Length'])));payload=json.loads(request['messages'][-1]['content']);seen.append(self.path)
                reply={'requirements':[{'id':None,'change':'new','title':'Motor alarm','description':'Display the source alarm on the HMI','source_ids':[payload['sources'][0]['id']]}]}
                raw=json.dumps({'choices':[{'message':{'content':json.dumps(reply)}}]}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Model);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            config.write_text(json.dumps({'provider':'embedded','baseUrl':'http://127.0.0.1:'+str(server.server_port)+'/v1','contextSize':8192,'maxTokens':1024,'autoStart':False}))
            file=self.file('requirements.txt',b'The PLC shall show the motor alarm on the HMI.')
            key=self.queued('q_generate',{'stage':'frd','file_ids':[file['id']]});self.jobs.execute(self.jobs.claim(),threading.Event())
            result=self.jobs.get_job(self.user,self.pid,key);self.assertEqual(result['status'],'completed',result);self.assertEqual(seen,['/v1/chat/completions'])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2);config.unlink(missing_ok=True)

    def test_23_unchanged_recording_reuses_transcription(self):
        from backend.core.workhub_intelligence import local_ai
        file=self.file('recording.wav',b'Fixture audio bytes');key=self.queued(payload={'file_ids':[file['id']]});job=self.jobs.claim()
        from backend.core.workhub_files import file_record
        row,path=file_record(file['id'],self.pid)
        transcript={'segments':[{'id':'S1','text':'PLC alarm','start':0,'end':1}]}
        with patch.object(local_ai,'_transcribe',return_value=transcript) as speech:
            self.assertEqual(local_ai.transcribe(path,'en',['PLC'],job),transcript)
            self.assertEqual(local_ai.transcribe(path,'en',['PLC'],job),transcript);self.assertEqual(speech.call_count,1)

    def test_24_operational_health_is_admin_only(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        from backend.core import accounts
        client=TestClient(app)
        try:
            self.assertEqual(client.get('/api/admin/settings/workhub-health').status_code,401)
            reader=accounts.store.register('Health reader','Fixture-password-123!','Engineer','Fixture')
            with accounts.store.db() as db:db.execute('UPDATE users SET active=1,approved=1 WHERE id=?',(reader['id'],))
            client.cookies.set(accounts.COOKIE,accounts.store.new_session(reader['id']))
            self.assertEqual(client.get('/api/admin/settings/workhub-health').status_code,403)
            client.cookies.set(accounts.COOKIE,accounts.store.new_session(self.user['id']))
            response=client.get('/api/admin/settings/workhub-health');self.assertEqual(response.status_code,200);self.assertIn('queues',response.json())
        finally:client.close()

    def test_25_worker_rechecks_account_revocation(self):
        from backend.core import accounts
        self.queued();job=self.jobs.claim()
        try:
            with accounts.store.db() as db:db.execute('UPDATE users SET active=0 WHERE id=?',(self.user['id'],))
            with self.assertRaises(PermissionError):job.check()
        finally:
            with accounts.store.db() as db:db.execute('UPDATE users SET active=1 WHERE id=?',(self.user['id'],))


if __name__=='__main__':unittest.main(verbosity=2)
