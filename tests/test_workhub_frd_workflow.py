"""FRD acceptance checks in an isolated database, with a labelled local model fixture.

Run directly; no production records or external AI endpoints are touched. The HTTP
fixture checks integration and schemas, not real model or speech accuracy.
"""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
SANDBOX=Path(tempfile.mkdtemp(prefix='ufrdtest-'))
os.environ.update(USOPP_DATA_ROOT=str(SANDBOX),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1',USOPP_LLM_PROVIDER='local')
OUT=ROOT/'.build/workhub-frd-validation';OUT.mkdir(parents=True,exist_ok=True)


class ModelFixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        instruction=body['messages'][0]['content'];data=json.loads(body['messages'][-1]['content'])
        sources=data.get('sources',[]);refs=[s['id'] for s in sources]
        if 'Create meeting notes.' in instruction:
            claims=[{'text':s['text'],'source_ids':[s['id']]} for s in sources if 'shall' in s['text']]
            result={'discussion_summary':claims[:1],'decisions':claims[:1],'engineering_requirements':claims,
                'actions':[{'text':'Confirm the reset condition.','responsible':'Invented engineer','target_date':'2099-01-01','source_ids':refs[-1:]}],
                'clarifications':[{'question':'Confirm reset conditions before approval.','source_ids':refs[-1:]}],
                'english_segments':[{'source_id':s['id'],'text':s['text']} for s in sources]}
        elif 'Extract' in instruction:
            requirements=[]
            for signal,title,description in [('TRAIN_MOTOR_TRIP','Motor trip detection','The PLC shall latch TRAIN_TRIP_ALARM when TRAIN_MOTOR_TRIP is active.'),('TRAIN_RESET_REQUEST','Controlled reset','The PLC shall clear TRAIN_TRIP_ALARM only when TRAIN_RESET_REQUEST is active and TRAIN_MOTOR_TRIP is clear.')]:
                matching=[s['id'] for s in sources if signal in s['text'] and all(t in s['text'] for t in ['TRAIN_TRIP_ALARM','TRAIN_MOTOR_TRIP'])]
                if matching:requirements.append({'existing_id':None,'id':None,'change':'new','title':title,'description':description,'trigger':signal,'expected_behavior':description,'acceptance_criteria':description,'source_ids':matching})
            result={'requirements':requirements,'clarifications':[]}
        else:
            selected=data.get('selected_requirements') or [{'id':s['id']} for s in sources if s['id'].startswith('FR-')]
            ids=[r['id'] for r in selected];source=next((s for s in sources if 'TRAIN_MOTOR_TRIP' in s['text']),sources[0])
            flow={'nodes':[{'id':'start','position':{'x':0,'y':0},'data':{'label':'Monitor TRAIN_MOTOR_TRIP','kind':'start','requirement_ids':ids[:1],'source_ids':[source['id']],'plc_references':['TRAIN_MOTOR_TRIP']}},
                {'id':'check','position':{'x':300,'y':0},'data':{'label':'Trip detected?','kind':'decision','requirement_ids':ids[:1],'source_ids':[source['id']]}}],
                'edges':[{'id':'e1','source':'start','target':'check','label':None},{'id':'e2','source':'check','target':'start','label':'No'}]}
            result={'answer':{'nodes':flow['nodes'],'edges':flow['edges']},'source_ids':[source['id']],'requirement_updates':[],
                'clarification_questions':[],'clarifications':[],'flowchart':flow}
        raw=json.dumps({'choices':[{'message':{'content':json.dumps(result)}}]}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)


class FRDWorkflow(unittest.TestCase):
    report_file='workflow-results.json'
    @classmethod
    def setUpClass(cls):
        from backend.app import app
        from backend.core import accounts
        from backend.core import assist_model
        from backend.core.workhub_quality import store,training,documents,service,packages,branding
        from backend.core.workhub_intelligence import jobs,operations,processing,local_ai
        from fastapi.testclient import TestClient
        # Imports can already be cached by unittest discovery. Always replace
        # the stores explicitly; environment variables alone are insufficient.
        cls.isolation=ExitStack()
        cls.addClassCleanup(cls.isolation.close)
        cls.isolation.enter_context(patch.object(accounts,'store',accounts.AccountStore(SANDBOX/'accounts.sqlite3')))
        cls.isolation.enter_context(patch.object(store.hub,'root',SANDBOX/'.usopp_workhub'))
        cls.isolation.enter_context(patch.object(store.hub,'ready',False))
        cls.isolation.enter_context(patch.object(assist_model,'CONFIG',SANDBOX/'.usopp_assist_model.json'))
        assert store.hub.root.resolve().is_relative_to(SANDBOX.resolve())
        cls.store=store;cls.hub=store.hub;cls.training=training;cls.documents=documents;cls.service=service;cls.packages=packages;cls.branding=branding
        cls.jobs=jobs;cls.operations=operations;cls.processing=processing;cls.local_ai=local_ai
        store.initialize();cls.users=[];cls.clients=[]
        for username in ['frd_author','frd_reviewer','frd_outsider']:
            user=accounts.store.register(username,'Fictional-pass-2026!','Training Engineer','Fictional training','admin')
            if username!='frd_author':
                with accounts.store.db() as db:db.execute("UPDATE users SET role='user' WHERE id=?",(user['id'],))
                user=next(u for u in accounts.store.list_users() if u['id']==user['id'])
            cls.users.append(user);client=TestClient(app);response=client.post('/api/auth/login',json={'username':username,'password':'Fictional-pass-2026!'})
            assert response.status_code==200,response.text
            cls.clients.append(client)
        cls.author,cls.reviewer,cls.outsider=cls.users;cls.client,cls.review_client,cls.other_client=cls.clients
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),ModelFixture)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.isolation.enter_context(patch.dict(os.environ,{'USOPP_PI_LLM_URL':'http://127.0.0.1:'+str(cls.server.server_port),'USOPP_PI_LLM_MODEL':'controlled-test-fixture'}))
        cls.evidence=[]

    @classmethod
    def tearDownClass(cls):
        for client in cls.clients:client.close()
        cls.server.shutdown();cls.server.server_close();cls.thread.join(3)
        (OUT/cls.report_file).write_text(json.dumps({'model':'Controlled local HTTP fixture, not real AI accuracy','database':str(SANDBOX),'checks':cls.evidence},indent=2,ensure_ascii=False),encoding='utf-8')

    def setUp(self):
        self.pid=self.hub.create(self.author,{'title':'Fictional FRD acceptance '+self._testMethodName,'quality_id':self.reviewer['id'],'approver_id':self.reviewer['id'],'release_id':self.reviewer['id']})['id']
        self.pi='/api/workhub/projects/'+self.pid+'/intelligence';self.qc='/api/workhub/projects/'+self.pid+'/quality'

    def tearDown(self):
        with self.hub.db(True) as db:db.execute("UPDATE pi_jobs SET status='cancelled',lease_until=0 WHERE status IN ('queued','running')")

    def note(self,step,expected,actual):self.evidence.append({'test':self._testMethodName,'step':step,'expected':expected,'actual':actual,'status':'Working'})

    def ok(self,response,status=200):
        self.assertEqual(response.status_code,status,response.text[:1200]);return response.json()

    def upload(self,name,content):
        if isinstance(content,str):content=content.encode('utf-8')
        upload=self.ok(self.client.post('/api/workhub/projects/'+self.pid+'/uploads',json={'name':name,'size':len(content)}))
        self.ok(self.client.put('/api/workhub/uploads/'+upload['id']+'?offset=0',content=content))
        file=self.ok(self.client.post('/api/workhub/uploads/'+upload['id']+'/finish'))
        self.assertEqual(file['sha256'],hashlib.sha256(content).hexdigest());return file

    def execute(self,value,success=True):
        key=value['id'];job=self.jobs.claim();self.assertIsNotNone(job);self.assertEqual(job.row['id'],key)
        started=time.monotonic();self.jobs.execute(job,threading.Event());result=self.jobs.get_job(self.author,self.pid,key)
        if success:self.assertEqual(result['status'],'completed',result)
        else:self.assertIn(result['status'],{'blocked','failed'},result)
        self.evidence.append({'test':self._testMethodName,'step':'Background '+job.row['kind'],'status':result['status'],'seconds':round(time.monotonic()-started,3),'result':result['result'],'error':result.get('error')})
        return result

    def test_01_end_to_end_reviewed_transcript_to_approved_pdf(self):
        text='WEBVTT\n\n00:00:00.000 --> 00:00:05.000\n<v Engineer A>The PLC shall latch TRAIN_TRIP_ALARM when TRAIN_MOTOR_TRIP is active.\n\n00:00:06.000 --> 00:00:10.000\n<v Engineer B>The PLC shall clear TRAIN_TRIP_ALARM only when TRAIN_RESET_REQUEST is active and TRAIN_MOTOR_TRIP is clear.\n\n00:00:11.000 --> 00:00:14.000\nConfirm the reset condition.\n'
        file=self.upload('fictional-meeting.vtt',text)
        meeting=self.ok(self.client.post(self.pi+'/meetings',json={'file_id':file['id'],'subject':'Fictional motor trip discussion','participants':['Engineer A','Engineer B']}));mid=meeting['id']
        self.ok(self.client.post(self.pi+'/jobs',json={'kind':'meeting','payload':{'meeting_id':mid}}),409)
        self.execute(self.ok(self.client.post(self.pi+'/jobs',json={'kind':'transcribe','payload':{'meeting_id':mid}})))
        value=self.ok(self.client.get(self.pi+'/meetings/'+mid));self.assertEqual(value['transcript']['segments'][0]['start'],0)
        self.assertEqual(value['transcript']['segments'][0]['speaker'],'Engineer A');self.assertFalse(value['review'])
        with self.hub.db() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM pi_documents WHERE project_id=? AND kind='mom'",(self.pid,)).fetchone()[0],0)
        segments=value['transcript']['segments'];segments[-1]['text']='Confirm the reset condition before approval.'
        self.ok(self.client.put(self.pi+'/meetings/'+mid+'/transcript',json={'version':value['transcript_version'],'segments':segments}))
        value=self.ok(self.client.get(self.pi+'/meetings/'+mid))
        self.ok(self.client.post(self.pi+'/meetings/'+mid+'/transcript/confirm',json={'version':value['transcript_version'],'confirmed':True}))
        mom_job=self.execute(self.ok(self.client.post(self.pi+'/jobs',json={'kind':'meeting','payload':{'meeting_id':mid}})))
        doc=mom_job['result']['document_id'];rid=mom_job['result']['revision_id']
        with self.hub.db() as db:mom=self.store.pi.revision(db,rid,doc)['content']
        self.assertEqual(len(mom['engineering_requirements']),2);self.assertIsNone(mom['actions'][0]['responsible']);self.assertIsNone(mom['actions'][0]['target_date'])
        self.assertEqual(mom['sources'][0]['start'],0);self.assertEqual(mom['sources'][0]['transcript_version'],2)
        value=self.ok(self.client.get(self.pi+'/meetings/'+mid));self.assertEqual(value['transcript']['segments'][0]['original_text'],segments[0]['text']);self.assertTrue(value['transcript']['segments'][0]['english'])
        self.note('Transcript review and MOM','Reviewed saved transcript; original and interpretation retained; unknown owners/dates null','MOM has 2 engineering requirements with exact transcript version and timestamps; invented fixture owner/date discarded')
        self.ok(self.client.post(self.pi+'/documents/'+doc+'/review',json={'action':'submit','revision_id':rid,'reviewer_id':self.reviewer['id']}))
        self.ok(self.other_client.post(self.pi+'/documents/'+doc+'/review',json={'action':'approve','revision_id':rid}),403)
        approval=self.ok(self.review_client.post(self.pi+'/documents/'+doc+'/review',json={'action':'approve','revision_id':rid,'comment':'Reviewed fictional fixture transcript.'}))
        frd_job=self.execute(approval['frd_job'])
        self.ok(self.client.get(self.qc))
        controlled=self.ok(self.client.get(self.qc+'/documents/frd'));key=controlled['document']['id'];rev=controlled['revision'];content=rev['content']
        self.assertEqual(len(content['requirements']),2);self.assertEqual([r['id'] for r in content['requirements']],['FR-001','FR-002']);self.assertEqual(len({r['description'] for r in content['requirements']}),2)
        self.assertTrue(controlled['document']['number'].startswith('PTPL-ES-PLC-FRD-'))
        proposal=self.execute(self.ok(self.client.post(self.qc+'/documents/'+key+'/assist',json={'action':'flowchart','version':rev['version'],'revision_id':rev['id'],'requirement_ids':[],'question':'Propose a source-linked training flowchart.'})))
        self.assertIsNone(self.ok(self.client.get(self.qc+'/documents/'+key))['revision']['content'].get('flowchart'))
        self.ok(self.client.post(self.qc+'/documents/'+key+'/assist/'+proposal['id']+'/apply',json={'version':rev['version'],'revision_id':rev['id'],'flowchart':True}))
        controlled=self.ok(self.client.get(self.qc+'/documents/'+key));rev=controlled['revision'];self.assertTrue(rev['content']['flowchart']['needs_review'])
        self.ok(self.client.post(self.qc+'/documents/'+key+'/action',json={'version':rev['version'],'revision_id':rev['id'],'action':'confirm'}),409)
        self.ok(self.client.post(self.qc+'/documents/'+key+'/flowchart/confirm',json={'version':rev['version'],'revision_id':rev['id'],'confirmed':True}))
        controlled=self.ok(self.client.get(self.qc+'/documents/'+key));rev=controlled['revision'];self.assertFalse(rev['content']['flowchart']['needs_review'])
        edited=deepcopy(rev['content']);edited['requirements'][0]['title']='Reviewed motor trip detection'
        self.ok(self.client.put(self.qc+'/documents/'+key,json={'version':rev['version'],'revision_id':rev['id'],'content':edited}))
        controlled=self.ok(self.client.get(self.qc+'/documents/'+key));rev=controlled['revision'];self.assertTrue(rev['content']['flowchart']['needs_review'])
        self.ok(self.client.post(self.qc+'/documents/'+key+'/flowchart/confirm',json={'version':rev['version'],'revision_id':rev['id'],'confirmed':True}))
        rev=self.ok(self.client.get(self.qc+'/documents/'+key))['revision']
        draft=self.client.get(self.qc+'/documents/'+key+'/export/pdf');self.assertEqual(draft.status_code,200,draft.text[:300]);(OUT/'acceptance-draft-frd.pdf').write_bytes(draft.content)
        self.ok(self.client.post(self.qc+'/documents/'+key+'/action',json={'version':rev['version'],'revision_id':rev['id'],'action':'confirm'}))
        rev=self.ok(self.client.get(self.qc+'/documents/'+key))['revision']
        self.ok(self.client.post(self.qc+'/documents/'+key+'/action',json={'version':rev['version'],'revision_id':rev['id'],'action':'submit'}))
        rev=self.ok(self.client.get(self.qc+'/documents/'+key))['revision']
        self.ok(self.client.post(self.qc+'/documents/'+key+'/action',json={'version':rev['version'],'revision_id':rev['id'],'action':'approve'}),403)
        self.ok(self.review_client.post(self.qc+'/documents/'+key+'/action',json={'version':rev['version'],'revision_id':rev['id'],'action':'approve','comment':'Approved fictional fixture only.'}))
        approved=self.client.get(self.qc+'/documents/'+key+'/export/pdf');self.assertEqual(approved.status_code,200,approved.text[:300]);(OUT/'acceptance-approved-frd.pdf').write_bytes(approved.content)
        self.branding.save(self.author,'organization',{'data':{**self.branding.ORG,'name':'Changed fictional branding','header_color':'#123456'},'make_default':True})
        again=self.client.get(self.qc+'/documents/'+key+'/export/pdf');self.assertEqual(approved.content,again.content)
        rev=self.ok(self.client.get(self.qc+'/documents/'+key))['revision']
        self.ok(self.client.put(self.qc+'/documents/'+key,json={'version':rev['version'],'revision_id':rev['id'],'content':edited}),409)
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(approved.content));pages=[p.extract_text() for p in pdf.pages]
        for i,page in enumerate(pages):
            self.assertIn(controlled['document']['number'],page);self.assertIn(self.pid,page);self.assertIn('Page '+str(i+1)+' of '+str(len(pages)),page)
        self.assertIn('Revision history',' '.join(pages));self.assertIn(self.reviewer['username'],' '.join(pages))
        self.note('FRD, reviewed flowchart, approval and frozen PDF','Unique source-linked IDs; explicit diagram review; real assigned reviewer; immutable approved PDF','2 unique requirements; flow review invalidated on requirement edit; PDF headers/footers on '+str(len(pages))+' pages; approved bytes identical after branding change')
        self.execute(self.ok(self.client.post(self.qc+'/generate',json={'stage':'test'})))
        report=self.ok(self.client.get(self.qc+'/documents/test'))
        self.assertTrue(report['revision']['content']['cases']);self.assertTrue(all(c.get('execution') is None for c in report['revision']['content']['cases']))
        self.note('Report preparation','Cases trace approved requirements; results not invented','Generated actual background test-report draft; all cases have no execution')

    def test_02_training_is_private_and_never_consumes_production_numbers(self):
        tables=['items','pi_documents','pi_revisions','qc_documents','qc_revisions','qc_sequences','qc_audit','events']
        def counts():
            with self.hub.db() as db:return {t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables}
        before=counts();sample=self.ok(self.client.get('/api/workhub/training/frd'))['sample'];self.assertIn('fictional',sample['notice'].lower())
        row=self.ok(self.client.post('/api/workhub/training/frd/copies',json={}));key=row['id'];content=deepcopy(row['data']['frd']);content['purpose']='Saved private practice purpose.'
        row=self.ok(self.client.put('/api/workhub/training/frd/copies/'+key,json={'version':row['version'],'frd':content,'submit_for_review':True}))
        self.assertEqual(row['status'],'training_review');self.assertEqual(len(row['revision_history']),2)
        self.ok(self.other_client.get('/api/workhub/training/frd/copies/'+key),404)
        self.ok(self.other_client.get('/api/workhub/training/frd/copies/'+key+'/pdf'),404)
        proposal=self.ok(self.client.post('/api/workhub/training/frd/copies/'+key+'/assist',json={'version':row['version'],'action':'flowchart'}))
        self.ok(self.client.post('/api/workhub/training/frd/copies/'+key+'/apply',json={'proposal_id':proposal['id'],'flowchart':True}),400)
        row=self.ok(self.client.post('/api/workhub/training/frd/copies/'+key+'/apply',json={'proposal_id':proposal['id'],'flowchart':True,'reviewed':True}))
        pdf=self.client.get('/api/workhub/training/frd/copies/'+key+'/pdf');self.assertEqual(pdf.status_code,200,pdf.text[:200]);self.assertTrue(pdf.content.startswith(b'%PDF'))
        self.assertEqual(self.ok(self.client.get('/api/workhub/training/frd'))['sample'],sample);self.assertEqual(counts(),before)
        self.assertTrue(all(c['outcome']=='not_run' and c['execution'] is None for c in row['data']['fat']['cases']))
        (OUT/'training-sample-frd.pdf').write_bytes(self.client.get('/api/workhub/training/frd/pdf').content)
        self.note('Training isolation','Private editable copies; no production projects, approvals or sequences changed','Owner-only copy, save/history, local proposal/apply and PDF pass; production table counts unchanged; sample immutable')

    def test_03_transcript_formats_timestamps_and_unknown_speakers(self):
        for name,text in [('example.srt','1\n00:00:01,000 --> 00:00:04,000\nPLC HMI servo VFD Modbus OPC UA\n'),('example.txt','PLC HMI servo VFD Modbus OPC UA\nTamil-English technical discussion')]:
            file=self.upload(name,text);value=self.processing.transcript_file(file['id'],self.pid)
            self.assertEqual(value['segments'][0]['original_text'],'PLC HMI servo VFD Modbus OPC UA');self.assertIsNone(value['segments'][0]['speaker'])
            self.assertEqual(value['segments'][0]['start'],1 if name.endswith('srt') else None)
        file=self.upload('invalid.vtt','WEBVTT\n\n00:00:05.000 --> 00:00:01.000\nPLC\n')
        with self.assertRaises(ValueError):self.processing.transcript_file(file['id'],self.pid)
        self.note('Transcript imports','Preserve terms, explicit timestamps, unknown speaker identities','SRT/TXT imports pass; reverse timestamps rejected; no voice identity inferred')

    def test_04_missing_speech_service_failure_retry_cancel_retains_original(self):
        file=self.upload('recording.wav',b'RIFF'+b'\0'*100)
        meeting=self.ok(self.client.post(self.pi+'/meetings',json={'file_id':file['id'],'language':'auto'}))
        value=self.execute(self.ok(self.client.post(self.pi+'/jobs',json={'kind':'transcribe','payload':{'meeting_id':meeting['id']}})),False)
        self.assertTrue(value['can_retry']);self.assertIn('Whisper',value.get('error',''))
        self.ok(self.client.post(self.pi+'/jobs/'+value['id']+'/retry'))
        self.ok(self.client.post(self.pi+'/jobs/'+value['id']+'/cancel'))
        self.assertEqual(self.ok(self.client.get(self.pi+'/jobs/'+value['id']))['status'],'cancelled')
        downloaded=self.client.get('/api/workhub/files/'+file['id']+'/download');self.assertEqual(hashlib.sha256(downloaded.content).hexdigest(),file['sha256'])
        self.note('Unavailable speech service recovery','Actionable failure and safe retry/cancel; original retained','Missing local Whisper reported, saved job retried/cancelled, original SHA-256 unchanged; real speech accuracy remains unverified')

    def test_05_unsupported_ai_values_and_source_references_rejected(self):
        from backend.core.workhub_intelligence.local_ai import ModelOutputError
        source={'S1':{'text':'The PLC shall show an HMI alarm.'}}
        for proposal in [{'text':'Use 400 RPM.','source_ids':['S1']},{'text':'Use FAKE_PLC_TAG.','source_ids':['S1']},{'text':'Use the alarm.','source_ids':['unknown']}]:
            with self.assertRaises(ModelOutputError):self.processing._claims([proposal],source)
        self.note('AI schema and source guard','Reject unknown sources and unsupported numeric/tag additions','All 3 adversarial proposals rejected without saving a document; semantic correctness still requires human review')

    def test_06_project_permissions_and_cross_project_file_references(self):
        file=self.upload('source.txt','Fictional requirement source.')
        pid=self.hub.create(self.author,{'title':'Other fictional project'})['id']
        self.ok(self.client.post('/api/workhub/projects/'+pid+'/intelligence/meetings',json={'file_id':file['id']}),404)
        self.ok(self.other_client.post(self.pi+'/meetings',json={'subject':'Unauthorized edit'}),403)
        self.ok(self.other_client.post(self.pi+'/jobs',json={'kind':'extract','payload':{'file_ids':[file['id']]}}),403)
        self.ok(self.other_client.get(self.qc))
        self.note('Existing permissions','Project membership required to write; company visibility unchanged; foreign project file rejected','Outsider writes 403; cross-project reference 404; existing signed-in project read policy preserved')

    def test_07_pdf_logos_unicode_sandbox_and_page_layout(self):
        from PIL import Image
        from backend.core.workhub_quality import pdf_templates
        from fastapi import HTTPException
        import fitz
        organization=self.branding.save(self.author,'organization',{'data':{**self.branding.ORG,'name':'Fictional PDF Test Company','header_color':'#114455'},'make_default':True})
        org_id=organization['id'];image=io.BytesIO();Image.new('RGB',(120,40),'teal').save(image,format='PNG')
        logo=self.branding.upload(self.author,'organization',org_id,image.getvalue(),'fictional-logo.png')
        self.branding.save(self.author,'organization',{'version':organization['version'],'data':{**organization['data'],'logo_id':logo['id']}},org_id)
        with self.assertRaises(HTTPException):self.branding.upload(self.author,'organization',org_id,b'<svg onload="alert(1)"></svg>','bad.svg')
        raw=self.training.pdf(self.author);(OUT/'training-branding-unicode-frd.pdf').write_bytes(raw)
        pdf=fitz.open(stream=raw,filetype='pdf');texts=[p.get_text() for p in pdf]
        for i,page in enumerate(pdf):
            self.assertIn('Page '+str(i+1)+' of '+str(len(pdf)),texts[i]);self.assertIn('PTPL-ES-PLC-FRD-SAMPLE-001',texts[i])
            self.assertTrue(page.get_images(),'Configured logo absent on page '+str(i+1))
            self.assertIn('Fictional PDF Test Company',texts[i])
        self.assertIn('DRAFT - NOT APPROVED',' '.join(texts));self.assertIn('Revision history',' '.join(texts))
        customer=self.branding.save(self.author,'customer',{'data':{'name':'Fictional PDF Customer','address':'Fictional training address'}})
        image=io.BytesIO();Image.new('RGB',(100,40),'orange').save(image,format='PNG')
        logo=self.branding.upload(self.author,'customer',customer['id'],image.getvalue(),'fictional-customer.png')
        self.branding.save(self.author,'customer',{'version':customer['version'],'data':{**customer['data'],'logo_id':logo['id']}},customer['id'])
        overview=self.service.overview(self.author,self.pid)
        self.service.context(self.author,self.pid,{'version':overview['context_version'],'customer_id':customer['id'],'machine':'Fictional PDF test machine'})
        controlled=self.documents.draft(self.author,self.pid,'frd',self.training.example()['frd'])
        both,_,_=self.packages.export_document(self.author,self.pid,'frd',format='pdf')
        both_pdf=fitz.open(stream=both,filetype='pdf')
        self.assertTrue(all(len(p.get_images())>=2 for p in both_pdf));self.assertIn('Fictional PDF Customer',both_pdf[0].get_text())
        (OUT/'company-customer-logo-frd.pdf').write_bytes(both)
        pdf[0].get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(OUT/'pdf-first-page.png')
        graph=next((i for i,t in enumerate(texts) if 'Monitor training trip' in t),None);self.assertIsNotNone(graph)
        pdf[graph].get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(OUT/'pdf-flowchart-page.png')
        with self.hub.db() as db:value=pdf_templates.preview(db,self.branding.LAYOUT)
        value['metadata'].append(['Unicode text','Motor trip வந்தால் HMI alarm காட்ட வேண்டும்.'])
        markup=pdf_templates.html(value);self.assertIn('வந்தால்',markup)
        raw,engine=pdf_templates.render(value);self.assertEqual(engine,'chromium')
        unicode_pdf=fitz.open(stream=raw,filetype='pdf');text=' '.join(p.get_text() for p in unicode_pdf)
        self.assertTrue(any('\u0b80'<=c<='\u0bff' for c in text));self.assertNotIn('\ufffd',text)
        (OUT/'unicode-layout-preview.pdf').write_bytes(raw)
        value['metadata'].append(['Unsafe title','<script>alert(1)</script>'])
        self.assertIn('&lt;script&gt;',pdf_templates.html(value))
        self.note('Shared PDF renderer','Logos, configured color, Unicode, repeated footer and real status; unsafe asset rejected','Chromium PDF has logo and exact page numbering on '+str(len(pdf))+' pages; Tamil glyph extraction verified; SVG/script input rejected or escaped; draft only')


if __name__=='__main__':
    try:unittest.main(verbosity=2)
    finally:
        # Test records are intentionally left in this isolated temp location for
        # debugging until the process ends; no production cleanup is performed.
        pass
