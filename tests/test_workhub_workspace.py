"""Isolated integration checks for project registration and document authoring."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json
import unittest
from fastapi import HTTPException
from tests.test_workhub_portfolio import PortfolioTests
from backend.core.workhub import store as hub
from backend.core import workhub_workspace as workspace
from backend.core.workhub_quality import authoring,documents,service,store,training

class WorkspaceTests(unittest.TestCase):
    setUpClass=classmethod(PortfolioTests.setUpClass.__func__)
    setUp=PortfolioTests.setUp
    tearDown=PortfolioTests.tearDown
    login=PortfolioTests.login
    request=PortfolioTests.request

    def draft(self,stage='frd',pid=None):
        return self.request('POST','/projects/'+(pid or self.project['id'])+'/quality/drafts',{'stage':stage})

    def document(self,result,pid=None):
        return service.get_document(self.admin,pid or self.project['id'],result['control_id'])

    def test_register_assign_later_and_workflow_guard(self):
        p=self.request('POST','/projects',{'workspace_schema':2,'title':'New registered project','kind':'General','customer':'Fixture Customer','description':'Authorized test project','due_date':'2099-01-01','assignment_mode':'later','supporting_ids':[self.engineer['id']]})
        self.assertTrue(p['project_number'].startswith('PTPL-ES-PLC-PRJ-'))
        detail=self.request('GET','/projects/'+p['id'])
        self.assertEqual('Created',detail['project']['project_status']);self.assertEqual('Fixture Customer',detail['project_context']['customer'])
        self.request('POST','/items/'+p['id']+'/transition',{'action':'start','version':p['version']},409)
        p=self.request('PUT','/items/'+p['id'],{'version':p['version'],'owner_id':self.engineer['id']})
        self.assertEqual('assigned',p['assignment_state']);self.assertTrue(p['assigned_at'])
        self.login(self.engineer)
        self.assertTrue(any(r['id']==p['id'] for r in self.request('GET','/portfolio?role=engineer')['projects']))
        started=self.request('POST','/items/'+p['id']+'/transition',{'action':'start','version':p['version']})
        self.assertEqual('development',started['stage'])
        self.login(self.admin)
        self.request('PUT','/items/'+p['id'],{'version':started['version'],'project_number':'CHANGED'},409)

    def test_required_new_registration_fields_preserve_legacy_api(self):
        self.request('POST','/projects',{'workspace_schema':2,'title':'Missing required'},400)
        p=self.request('POST','/projects',{'title':'Legacy compatible'})
        self.assertEqual('assigned',p['assignment_state'])

    def test_customer_project_reference_round_trips_to_portfolio(self):
        p=self.request('POST','/projects',{'workspace_schema':3,'title':'Customer reference fixture','customer':'Example Customer','customer_project_reference':'PO-871','scope':'Internal project scope'})
        detail=self.request('GET','/projects/'+p['id'])
        self.assertEqual('PO-871',detail['project_context']['customer_project_reference'])
        row=next(row for row in self.request('GET','/overview')['items'] if row['id']==p['id'])
        self.assertEqual(('Example Customer','PO-871'),(row['customer'],row['customer_project_reference']))
        self.assertNotIn('scope',row)
        self.request('POST','/projects/'+p['id']+'/issues',{'title':'Recorded issue','owner_id':self.admin['id']})
        self.assertEqual(1,next(row for row in self.request('GET','/overview')['items'] if row['id']==p['id'])['open_issue_count'])
        updated=self.request('PUT','/items/'+p['id'],{'version':detail['project']['version'],'customer_project_reference':'PO-872'})
        self.assertEqual('PO-872',self.request('GET','/projects/'+p['id'])['project_context']['customer_project_reference'])
        self.assertEqual('PO-872',next(row for row in self.request('GET','/overview')['items'] if row['id']==p['id'])['customer_project_reference'])

    def test_creation_wizard_saves_step_assignments_and_brief_atomically(self):
        steps=[{'id':'planning','title':'Planning','description':'Plan the work','phase':'development','days':2,'planned_hours':0,'milestone':True,'depends_on':[]},
               {'id':'review','title':'Review','description':'Review it','phase':'quality','days':1,'planned_hours':0,'milestone':True,'depends_on':['planning']}]
        payload={'workspace_schema':3,'title':'Wizard fixture','kind':'Electrical','customer':'Fixture','scope':'Upgrade',
                 'project_requirements':'Protect motor','acceptance_criteria':'Alarm appears','additional_information':'Await site input',
                 'start_date':'2099-01-01','generate_plan_tasks':False,'workflow_steps':steps,
                 'workflow_assignees':{'planning':self.engineer['id'],'review':self.manager['id']}}
        result=self.request('POST','/projects',payload)
        detail=self.request('GET','/projects/'+result['id'])
        self.assertEqual('Protect motor',detail['project_context']['project_requirements'])
        self.assertEqual('Alarm appears',detail['project_context']['acceptance_criteria'])
        self.assertEqual('Await site input',detail['project_context']['additional_information'])
        tasks={task['title']:task for task in detail['tasks']}
        self.assertEqual({'Planning','Review'},set(tasks))
        self.assertEqual(self.engineer['id'],tasks['Planning']['owner_id'])
        self.assertEqual(self.manager['id'],tasks['Review']['owner_id'])
        self.assertEqual([tasks['Planning']['id']],tasks['Review']['dependencies'])
        self.assertTrue(tasks['Planning']['milestone'])
        with hub.db() as db:before=db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0]
        invalid={**payload,'title':'Invalid wizard fixture','workflow_assignees':{'planning':999999}}
        self.request('POST','/projects',invalid,400)
        with hub.db() as db:self.assertEqual(before,db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0])

    def test_project_wizard_prepares_unapproved_frd_and_references(self):
        payload={'workspace_schema':3,'title':'Reference wizard','description':'Upgrade controls','scope':'Upgrade controls','customer':'Customer',
          'base_reference':'Existing PLC v1','developed_reference':'New PLC v2','project_requirements':'Protect motor',
          'acceptance_criteria':'Alarm visible','additional_information':'Confirm site network', 'prepare_frd':True,
          'requirement_items':[{'description':'Protect motor','category':'Alarm & Safety','priority':'high'},{'description':'Update HMI','category':'HMI','priority':'medium'}],
          'flowchart':{'nodes':[{'id':'start','position':{'x':0,'y':0},'data':{'kind':'start','label':'Start','requirement_ids':['FR-001'],'source_ids':[]}}],'edges':[],'sources':[]},
          'generate_plan_tasks':False}
        p=self.request('POST','/projects',payload);detail=self.request('GET','/projects/'+p['id'])
        self.assertEqual('Existing PLC v1',detail['project_context']['base_reference'])
        self.assertEqual('New PLC v2',detail['project_context']['developed_reference'])
        with hub.db() as db:
            doc=db.execute("SELECT * FROM qc_documents WHERE project_id=? AND stage='frd'",(p['id'],)).fetchone()
            native=db.execute('SELECT current_revision FROM pi_documents WHERE id=?',(doc['document_id'],)).fetchone()
            rev=json.loads(db.execute('SELECT content FROM pi_revisions WHERE id=?',(native[0],)).fetchone()[0])
            status=db.execute('SELECT status FROM qc_revisions WHERE id=?',(native[0],)).fetchone()[0]
        self.assertEqual('draft',status);self.assertEqual(['FR-001','FR-002'],[r['id'] for r in rev['requirements']])
        self.assertEqual(('Alarm & Safety','high'),(rev['requirements'][0]['category'],rev['requirements'][0]['priority']))
        self.assertEqual('Alarm visible',rev['acceptance_summary']);self.assertTrue(rev['flowchart']['needs_review'])
        self.assertEqual({'Base reference','Developed reference','Additional information'}, {r['heading'] for r in rev['sections']} & {'Base reference','Developed reference','Additional information'})

    def test_project_templates_have_a_default_and_need_no_approval(self):
        catalog=self.request('GET','/project-templates');self.assertEqual('default',catalog['items'][0]['id'])
        steps=catalog['items'][0]['content']['steps']
        row=self.request('POST','/project-templates',{'name':'Reusable workflow','shared':True,'content':{'kind':'PLC','steps':steps,'assignees':{'development':self.engineer['id']}}})
        self.login(self.engineer);catalog=self.request('GET','/project-templates')
        saved=next(v for v in catalog['items'] if v['id']==row['id']);self.assertTrue(saved['shared'])
        self.assertEqual(self.engineer['id'],saved['content']['assignees']['development'])
        self.assertNotIn('approval',saved)

    def test_project_default_frd_preserves_edited_content_and_stable_flow_links(self):
        content=authoring.blank('frd')
        content.update(purpose='Record production',background='Existing PLC',expected_outcome='Speed ≥ 10 µm/s',
            acceptance_summary='Alarm ≤ 2 s',acceptance_items=[{'id':'AC-001','text':'Alarm ≤ 2 s','confirmed':True}],
            requirements=[{'id':'FR-002','title':'Temperature','description':'Temperature ≥ 40 °C → alarm','category':'Alarm','priority':'high','status':'confirmed','source_ids':[]}],
            flowchart={'nodes':[{'id':'n1','position':{'x':0,'y':0},'data':{'kind':'process','label':'Temperature ≥ 40 °C','requirement_ids':['FR-002'],'source_ids':[]}}],'edges':[]})
        content['sections'].append({'heading':'Deliverables','text':'PLC archive\nValidation report'})
        p=self.request('POST','/projects',{'workspace_schema':3,'title':'Edited FRD fixture','customer':'Fixture',
            'scope':'Controls','prepare_frd':True,'frd_content':content,'generate_plan_tasks':False})
        with hub.db() as db:doc=dict(db.execute("SELECT * FROM qc_documents WHERE project_id=? AND stage='frd'",(p['id'],)).fetchone())
        result=self.request('GET','/projects/'+p['id']+'/quality/documents/'+doc['id']);saved=result['revision']['content']
        self.assertEqual('draft',result['revision']['status']);self.assertFalse(result['revision'].get('approved_by'))
        self.assertEqual('Speed ≥ 10 µm/s',saved['expected_outcome']);self.assertEqual('Existing PLC',saved['background'])
        self.assertEqual('FR-002',saved['requirements'][0]['id']);self.assertEqual('confirmed',saved['requirements'][0]['status'])
        self.assertTrue(saved['acceptance_items'][0]['confirmed']);self.assertTrue(saved['flowchart']['needs_review'])
        self.assertEqual(['FR-002'],saved['flowchart']['nodes'][0]['data']['requirement_ids'])
        from backend.core.workhub_quality.pdf_templates import blocks,context,fallback
        rendered=json.dumps(blocks(saved),ensure_ascii=False)
        for value in ['Existing PLC','Speed ≥ 10 µm/s','PLC archive','Alarm ≤ 2 s','Temperature ≥ 40 °C → alarm','high']:
            self.assertIn(value,rendered)
        import io
        from pypdf import PdfReader
        with hub.db() as db:
            value=context(db,hub.item(db,p['id']),doc,result['revision'])
        raw=fallback(value)
        pdf_text=' '.join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages)
        for value in ['Existing PLC','Speed ≥ 10 µm/s','PLC archive','Alarm ≤ 2 s','Temperature ≥ 40 °C']:
            self.assertIn(value,pdf_text)
        # Editing the older summary field must not silently restore stale checklist text.
        saved['acceptance_summary']='Updated criterion'
        documents.save(self.admin,p['id'],doc['id'],{'revision_id':result['revision']['id'],'version':result['revision']['version'],'content':saved})
        updated=self.request('GET','/projects/'+p['id']+'/quality/documents/'+doc['id'])['revision']['content']
        self.assertEqual('Updated criterion',updated['acceptance_items'][0]['text']);self.assertFalse(updated['acceptance_items'][0]['confirmed'])

    def test_invalid_project_frd_rolls_back_project_creation(self):
        with hub.db() as db:before=db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0]
        self.request('POST','/projects',{'title':'Invalid FRD','prepare_frd':True,'frd_content':{'requirements':[],
            'flowchart':{'nodes':[{'id':'bad','position':{'x':0,'y':0},'data':{'label':'Start','requirement_ids':['FR-999']}}],'edges':[]}}},400)
        with hub.db() as db:self.assertEqual(before,db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0])

    def test_concurrent_project_numbering_and_duplicate_number(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            values=list(pool.map(lambda i:workspace.create(self.admin,{'title':'Concurrent '+str(i)}),range(8)))
        self.assertEqual(8,len({p['project_number'] for p in values}))
        self.request('POST','/projects',{'title':'Duplicate','project_number':values[0]['project_number']},409)

    def test_hold_cancel_resume_requires_reason_and_blocks_transitions(self):
        p=self.project
        self.request('POST','/projects/'+p['id']+'/condition',{'version':p['version'],'condition':'on_hold','reason':''},400)
        held=self.request('POST','/projects/'+p['id']+'/condition',{'version':p['version'],'condition':'on_hold','reason':'Awaiting input'})
        with self.assertRaises(HTTPException) as denied:hub.transition(self.manager,p['id'],{'action':'start','version':held['version']})
        self.assertEqual(409,denied.exception.status_code)
        resumed=self.request('POST','/projects/'+p['id']+'/condition',{'version':held['version'],'condition':'','reason':'Input confirmed'})
        self.assertEqual('',resumed['exception_status'])

    def test_manual_templates_are_idempotent_and_need_no_ai_or_frd(self):
        for stage in store.STAGES:
            with self.subTest(stage=stage):
                first=self.draft(stage);second=self.draft(stage)
                self.assertEqual(first['control_id'],second['control_id']);self.assertEqual(first['revision_id'],second['revision_id'])
                doc=self.document(first);self.assertEqual('draft',doc['revision']['status'])
        with hub.db() as db:
            self.assertEqual(6,db.execute('SELECT count(*) FROM qc_documents WHERE project_id=?',(self.project['id'],)).fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM pi_jobs').fetchone()[0])

    def test_manual_mom_retry_and_source_original(self):
        endpoint='/projects/'+self.project['id']+'/quality/drafts';payload={'stage':'mom','request_id':'fixture-idempotency'}
        first=self.request('POST',endpoint,payload);second=self.request('POST',endpoint,payload)
        self.assertEqual(first,second)
        data=self.request('GET','/documents?kind=mom')
        self.assertEqual(1,data['total']);self.assertEqual('draft',data['items'][0]['status'])

    def test_readiness_rich_corrections_trace_and_autosave_version(self):
        frd=self.draft();r=self.document(frd)['revision']
        self.assertEqual('Missing Information',self.document(frd)['readiness']['state'])
        content=training.example()['frd'];content.pop('flowchart')
        saved=documents.save(self.admin,self.project['id'],frd['control_id'],{'revision_id':r['id'],'version':r['version'],'content':content})
        self.assertGreater(saved['version'],r['version'])
        cn=self.draft('corrections');cr=self.document(cn)['revision'];c=cr['content']
        c['changes']=[{'id':'CN-001','summary':'Reset review','requirement_ids':['FR-003'],'source_ids':[],'plc_references':'Main.reset','before_evidence':'Before.png','impact':'Alarm interlock review'}]
        documents.save(self.admin,self.project['id'],cn['control_id'],{'revision_id':cr['id'],'version':cr['version'],'content':c})
        trace=self.request('GET','/projects/'+self.project['id']+'/quality/trace/FR-003')
        self.assertEqual('Main.reset',trace['links'][0]['item']['plc_references'])
        self.assertFalse(self.request('GET','/projects/'+self.project['id']+'/quality/trace/FR-001')['links'])
        self.login(self.outsider);self.request('GET','/projects/'+self.project['id']+'/quality/trace/FR-003',expected=403)

    def test_library_scope_retains_original_and_discards_outcomes(self):
        source=self.draft('fat');r=self.document(source)['revision'];c=r['content'];c['cases']=[{'id':'FAT-001','objective':'Case','procedure':'Simulate','expected_result':'Alarm','acceptance_criteria':'Correct','source_ids':[],'requirement_ids':[]}]
        documents.save(self.admin,self.project['id'],source['control_id'],{'revision_id':r['id'],'version':r['version'],'content':c})
        with hub.db(True) as db:
            db.execute("UPDATE qc_revisions SET status='approved' WHERE id=?",(r['id'],));before=db.execute('SELECT content FROM pi_revisions WHERE id=?',(r['id'],)).fetchone()[0]
        self.login(self.outsider)
        self.request('POST','/projects/'+self.other['id']+'/quality/drafts',{'stage':'fat','library_revision_id':r['id']},403)
        self.login(self.admin)
        copied=self.request('POST','/projects/'+self.other['id']+'/quality/drafts',{'stage':'fat','library_revision_id':r['id']})
        current=self.document(copied,self.other['id'])
        self.assertEqual('draft',current['revision']['status']);self.assertIsNone(current['revision']['content']['cases'][0]['execution'])
        with hub.db() as db:self.assertEqual(before,db.execute('SELECT content FROM pi_revisions WHERE id=?',(r['id'],)).fetchone()[0])

    def test_register_is_bounded_filterable_and_project_scoped(self):
        self.draft('frd');self.draft('test');self.draft('fat',self.other['id'])
        self.login(self.engineer);data=self.request('GET','/documents?page_size=1')
        self.assertEqual(2,data['total']);self.assertEqual(1,len(data['items']))
        self.assertEqual(0,self.request('GET','/documents?project_id='+self.other['id'])['total'])
        self.assertEqual(1,self.request('GET','/documents?kind=frd')['total'])
        self.assertEqual(0,self.request('GET',"/documents?search=%27%20OR%201=1--")['total'])

    def test_full_sample_isolated_assets_revision_and_pdf_types(self):
        training.initialize()
        def counts():
            with hub.db() as db:return [db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('items','qc_sequences','qc_revisions','qc_executions')]
        before=counts();sample=training.example();self.assertEqual('DEMO-PRJ-001',sample['project']['number'])
        self.assertEqual(5,len(sample['documents']));self.assertTrue(all(c['execution'] is None for d in sample['documents'].values() for c in d.get('cases',[])))
        row=training.create(self.admin);updated=deepcopy(row['data']['documents']);updated['test']['cases'][0]['execution']={'outcome':'pass','actual':''}
        with self.assertRaises(HTTPException):training.save(self.admin,row['id'],{'version':row['version'],'documents':updated})
        updated['test']['cases'][0]['execution']['actual']='Fictional observed result'
        with self.assertRaises(HTTPException):training.save(self.admin,row['id'],{'version':row['version'],'documents':updated})
        row=training.upload(self.admin,row['id'],'observation.txt',b'Fictional private observation')
        asset=row['assets'][0];self.assertEqual(hashlib.sha256(b'Fictional private observation').hexdigest(),asset['sha256'])
        updated['test']['cases'][0]['execution']['file_ids']=[asset['id']]
        row=training.save(self.admin,row['id'],{'version':row['version'],'documents':updated})
        self.assertEqual('pass',row['data']['documents']['test']['cases'][0]['execution']['outcome'])
        blocked=deepcopy(row['data']['documents']);blocked['quality']['practice_status']='practice_approved'
        with self.assertRaises(HTTPException) as denied:training.save(self.admin,row['id'],{'version':row['version'],'documents':blocked})
        self.assertEqual(409,denied.exception.status_code)
        with self.assertRaises(HTTPException) as denied:training.asset(self.outsider,row['id'],asset['id'])
        self.assertEqual(404,denied.exception.status_code)
        for kind in ('frd','mom','flowchart','corrections','test','fat','quality','closure'):
            with self.subTest(kind=kind):self.assertTrue(training.pdf(self.admin,row['id'],kind).startswith(b'%PDF'))
        self.assertEqual(before,counts());self.assertEqual(sample,training.example())

    def test_independent_documents_do_not_create_projects_and_are_private(self):
        with hub.db() as db:before=db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0]
        payload={'stage':'frd','title':'Independent motor requirement','request_id':'standalone-frd-fixture'}
        first=self.request('POST','/document-spaces',payload);again=self.request('POST','/document-spaces',payload)
        self.assertEqual(first['scope_id'],again['scope_id']);self.assertEqual(first['revision_id'],again['revision_id'])
        value=self.request('GET','/document-spaces/'+first['scope_id'])
        self.assertTrue(value['project']['is_document_space'])
        self.assertTrue(any(r['independent'] for r in self.request('GET','/documents')['items']))
        with hub.db() as db:self.assertEqual(before,db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0])
        self.login(self.outsider)
        self.request('GET','/document-spaces/'+first['scope_id'],expected=403)
        self.request('GET','/projects/'+first['scope_id']+'/quality',expected=403)
        self.request('GET','/projects/'+first['scope_id']+'/intelligence',expected=403)
        self.assertEqual(0,self.request('GET','/documents')['total'])

    def test_numbered_requirements_keep_req_ids_in_project_frd_and_related_reports(self):
        content=training.example()['frd'];content.pop('flowchart',None)
        for index,row in enumerate(content['requirements']):row['id']='REQ-'+str(index*2+1).zfill(3)
        p=self.request('POST','/projects',{'workspace_schema':3,'title':'Numbered project requirements',
          'customer':'Fixture customer','description':'REQ identity test','prepare_frd':True,'frd_content':content})
        record=service.get_document(self.admin,p['id'],'frd')
        self.assertEqual([r['id'] for r in content['requirements']],[r['id'] for r in record['revision']['content']['requirements']])
        related=authoring.prepare_related(self.admin,p['id'])
        test=service.get_document(self.admin,p['id'],'test')
        self.assertEqual([r['id'] for r in content['requirements']],[c['requirement_ids'][0] for c in test['revision']['content']['cases']])

    def test_document_management_types_linked_or_standalone_keep_separate_records(self):
        before=self.request('GET','/overview')['items']
        created=[]
        for kind in ('mom','frd','test','test_report','fat','closure'):
            for linked in (False,True):
                payload={'stage':'test' if kind=='test_report' else kind,'document_type':kind,
                         'request_id':kind+str(linked),'title':'Test Report' if kind=='test_report' else kind}
                if linked:payload['linked_project_id']=self.project['id']
                row=self.request('POST','/document-spaces',payload);created.append(row)
                again=self.request('POST','/document-spaces',payload)
                self.assertEqual(row['scope_id'],again['scope_id'])
                space=self.request('GET','/document-spaces/'+row['scope_id'])['project']
                self.assertEqual(kind,space['document_type'])
                self.assertEqual(self.project['id'] if linked else None,space['linked_project_id'])
                register=self.request('GET','/documents?kind='+kind)['items']
                self.assertTrue(any(d['project_id']==row['scope_id'] for d in register))
                self.assertTrue(all(d['type']==kind for d in register))
        self.assertEqual({r['id'] for r in before},{r['id'] for r in self.request('GET','/overview')['items']})
        validation=self.request('GET','/documents?kind=test')['items']
        tests=self.request('GET','/documents?kind=test_report')['items']
        self.assertFalse({r['id'] for r in tests}&{r['id'] for r in validation})
        self.assertEqual(4,len({r['document_number'] for r in tests+validation}))
        linked_docs=self.request('GET','/documents?project_id='+self.project['id'])['items']
        self.assertTrue(all(d['linked_project_id']==self.project['id'] for d in linked_docs if d['independent']))
        self.login(self.outsider)
        self.assertEqual(0,self.request('GET','/documents?kind=test_report')['total'])
        self.request('GET','/document-spaces/'+created[7]['scope_id'],expected=403)

    def test_test_report_has_own_pdf_identity_and_rejects_request_type_changes(self):
        from backend.core.workhub_quality import pdf_templates
        payload={'stage':'test','document_type':'test_report','title':'Test Report','request_id':'distinct-test'}
        row=self.request('POST','/document-spaces',payload);pid=row['scope_id']
        self.request('POST','/document-spaces',{**payload,'document_type':'test'},expected=409)
        self.request('POST','/document-spaces',{**payload,'document_type':'test_report','stage':'fat'},expected=400)
        with hub.db() as db:
            p=hub.item(db,pid);doc=store.control(db,pid,row['control_id'])
            revision=store.revision(db,doc['id'],row['revision_id'])
            view=pdf_templates.context(db,p,doc,revision)
            self.assertEqual('Test Report',view['title'])
            self.assertIn('5. Test Results',[s['title'] for s in view['sections']])
            self.assertIn('Test result: Not tested',next(s['text'] for s in view['sections'] if s['title']=='8. Conclusion'))
            self.assertFalse(view['approved'])

    def test_frd_related_drafts_reuse_requirements_without_test_results(self):
        frd=self.draft();r=self.document(frd)['revision'];content=training.example()['frd'];content.pop('flowchart')
        documents.save(self.admin,self.project['id'],frd['control_id'],{'revision_id':r['id'],'version':r['version'],'content':content})
        endpoint='/projects/'+self.project['id']+'/quality/prepare-from-frd'
        first=self.request('POST',endpoint,{});again=self.request('POST',endpoint,{})
        self.assertEqual({'test','fat','closure'},{r['stage'] for r in first['documents']})
        self.assertTrue(all(r['existing'] for r in again['documents']))
        for stage in ('test','fat'):
            doc=service.get_document(self.admin,self.project['id'],stage)
            self.assertEqual(len(content['requirements']),len(doc['revision']['content']['cases']))
            self.assertTrue(all(c['execution'] is None for c in doc['revision']['content']['cases']))
            self.assertEqual(r['id'],doc['revision']['frd_revision_id'])

    def test_independent_library_keeps_review_and_file_permissions(self):
        first=self.request('POST','/document-spaces',{'stage':'frd','title':'Private library fixture','request_id':'library-fixture'})
        scope=first['scope_id'];detail=self.request('GET','/document-spaces/'+scope)
        self.request('PUT','/document-spaces/'+scope,{'version':detail['project']['version'],'library':True},409)
        detail=self.request('PUT','/document-spaces/'+scope,{'version':detail['project']['version'],'reviewer_id':self.lead['id']})
        with hub.db(True) as db:
            db.execute("UPDATE qc_revisions SET status='approved' WHERE id=?",(first['revision_id'],))
            db.execute("UPDATE pi_revisions SET status='approved' WHERE id=?",(first['revision_id'],))
            db.execute('UPDATE pi_documents SET approved_revision=current_revision WHERE project_id=?',(scope,))
        self.request('PUT','/document-spaces/'+scope,{'version':detail['project']['version'],'library':True})
        self.login(self.outsider)
        self.assertEqual(1,self.request('GET','/documents?library_only=true')['total'])
        self.request('GET','/document-spaces/'+scope,expected=403)
        copied=self.request('POST','/document-spaces',{'stage':'frd','request_id':'authorized-library-copy','library_revision_id':first['revision_id']})
        self.assertNotEqual(scope,copied['scope_id'])

    def test_minimal_project_only_requires_name(self):
        p=self.request('POST','/projects',{'workspace_schema':3,'title':'Minimal project','assignment_mode':'later'})
        self.assertEqual('unassigned',p['assignment_state'])
        self.assertEqual('',p['due_date'])

    def test_testing_tools_do_not_create_projects_without_assignment(self):
        from backend.core.workhub_runs import synchronize
        from backend.core.workhub import identity,timestamp
        with hub.db() as db:before=db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0]
        record={'id':identity(),'kind':'validation','user':self.admin,'projectName':'Separate testing fixture','status':'completed','createdAt':timestamp(),'summary':{}}
        self.assertEqual({},synchronize(record,{}))
        with hub.db() as db:self.assertEqual(before,db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0])
        first=synchronize(record,{'workhubProjectId':self.project['id']})
        other=synchronize({**record,'id':identity(),'kind':'metadata'},{'workhubProjectId':self.project['id']})
        self.assertEqual(first['workhubProjectId'],other['workhubProjectId'])
        with hub.db() as db:
            self.assertEqual({'validation','metadata'},{r[0] for r in db.execute('SELECT kind FROM engineering_runs')})
            self.assertEqual(before,db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0])

    def test_independent_review_queue_and_private_attachments(self):
        from backend.core.workhub_intelligence.documents import generated_file
        first=self.request('POST','/document-spaces',{'stage':'frd','request_id':'independent-review'})
        scope=first['scope_id'];detail=self.request('GET','/document-spaces/'+scope)
        self.request('PUT','/document-spaces/'+scope,{'version':detail['project']['version'],'reviewer_id':self.lead['id']})
        content=training.example()['frd'];content.pop('flowchart')
        doc=service.get_document(self.admin,scope,'frd');r=doc['revision']
        saved=documents.save(self.admin,scope,doc['document']['id'],{'revision_id':r['id'],'version':r['version'],'content':content})
        service.action(self.admin,scope,doc['document']['id'],{'action':'confirm','revision_id':r['id'],'version':saved['version']})
        r=service.get_document(self.admin,scope,'frd')['revision']
        service.action(self.admin,scope,doc['document']['id'],{'action':'submit','revision_id':r['id'],'version':r['version']})
        file=generated_file(self.admin,scope,'private-scope.txt',b'Private attachment')
        self.login(self.lead)
        queue=self.request('GET','/portfolio/approvals?documents_only=true')
        self.assertTrue(any(v['document_stage']=='independent:frd' and v['can_review'] for v in queue['items']))
        self.assertEqual(200,self.client.get('/api/workhub/files/'+file['id']+'/download').status_code)
        self.login(self.outsider)
        self.assertEqual(403,self.client.get('/api/workhub/files/'+file['id']+'/download').status_code)

    def test_independent_mom_pdf_and_numbering_reuse_saved_content(self):
        import fitz
        first=self.request('POST','/document-spaces',{'stage':'mom','request_id':'independent-mom-pdf'})
        scope=first['scope_id'];prefix='/projects/'+scope+'/intelligence/documents/'+first['document_id']
        content={'meeting_subject':'Independent technical discussion','meeting_date':'2026-10-27','participants':['Fixture engineer'],
            'discussion_summary':[{'topic':'Alarm indication','text':'Verify the trip input mapping','decision':'Review before implementation','source_ids':[]}],
            'decisions':[],'actions':[{'text':'Confirm the mapping','responsible':None,'target_date':None,'source_ids':[]}],
            'clarifications':[{'question':'Confirm reset conditions','source_ids':[]}],'sources':[]}
        saved=self.request('PUT',prefix,{'version':first['revision_id'],'title':content['meeting_subject'],'content':content})
        document=self.request('GET','/documents?kind=mom')['items'][0]
        self.assertIn('-MOM-',document['document_number'])
        response=self.client.get('/api/workhub'+prefix+'/export/pdf?revision_id='+saved['revision']['id'])
        self.assertEqual(200,response.status_code,response.text[:300] if response.status_code!=200 else '')
        pdf=fitz.open(stream=response.content,filetype='pdf');text=' '.join(p.get_text() for p in pdf)
        for value in ('Independent document','Independent technical discussion','Alarm indication','Confirm the mapping','Confirm reset conditions'):
            self.assertIn(value,text)

    def test_derived_test_readiness_detects_edited_source_frd(self):
        frd=self.draft();r=self.document(frd)['revision'];content=training.example()['frd'];content.pop('flowchart')
        documents.save(self.admin,self.project['id'],frd['control_id'],{'revision_id':r['id'],'version':r['version'],'content':content})
        authoring.prepare_related(self.admin,self.project['id'])
        current=self.document(frd)['revision'];content['purpose']='Changed source purpose'
        documents.save(self.admin,self.project['id'],frd['control_id'],{'revision_id':current['id'],'version':current['version'],'content':content})
        test=service.get_document(self.admin,self.project['id'],'test')
        self.assertTrue(any('source FRD content changed' in v for v in test['readiness']['issues']))
        with self.assertRaises(HTTPException) as denied:
            service.action(self.admin,self.project['id'],test['document']['id'],{'action':'confirm','revision_id':test['revision']['id'],'version':test['revision']['version']})
        self.assertEqual(409,denied.exception.status_code)

    def generation_job(self,payload):
        from backend.core.workhub import identity
        return SimpleNamespace(row={'id':identity(),'project_id':self.project['id'],'payload':payload},check=lambda:None,progress=lambda *args:None)

    def test_chopper_creates_source_linked_frd_from_one_brief(self):
        from backend.core.workhub_quality import processing
        from backend.core.workhub_intelligence import local_ai
        brief='The PLC shall show the motor trip on the HMI. Verify that the displayed alarm follows the trip input.'
        calls=[]
        def model(instruction,payload,check):
            calls.append(payload)
            return {'requirements':[{'id':None,'title':'Motor trip indication','description':brief,'expected_behavior':'Display the motor trip on the HMI','acceptance_criteria':'The displayed alarm follows the trip input','source_ids':[payload['sources'][0]['id']]}]}
        self.draft()
        with patch.object(local_ai,'configured',return_value=True),patch.object(local_ai,'_llm_json',side_effect=model):
            result=processing.generate(self.generation_job({'stage':'frd','brief':brief}),self.admin)
        doc=self.document(result);r=doc['revision'];c=r['content']
        self.assertEqual(1,len(calls));self.assertEqual('SRC001',calls[0]['sources'][0]['id'])
        self.assertEqual('draft',r['status']);self.assertIsNone(r['approved_at'])
        self.assertEqual(brief,c['sources'][0]['text']);self.assertEqual([c['sources'][0]['id']],c['requirements'][0]['source_ids'])
        reports=authoring.prepare_related(self.admin,self.project['id'])
        self.assertEqual({'test','fat','closure'},{v['stage'] for v in reports['documents']})
        self.assertIsNone(service.get_document(self.admin,self.project['id'],'fat')['revision']['content']['cases'][0]['execution'])

    def test_project_brief_is_reused_and_invalidates_generation_snapshot(self):
        from backend.core.workhub_quality import processing
        from backend.core.workhub_intelligence import local_ai,reliability
        store.initialize()
        brief='The PLC shall display the motor trip on the HMI.'
        with hub.db(True) as db:db.execute('UPDATE items SET description=? WHERE id=?',(brief,self.project['id']))
        with hub.db() as db:before=reliability.snapshot(db,self.project['id'],'q_generate',{'stage':'frd'})
        with patch.object(local_ai,'configured',return_value=False):result=processing.generate(self.generation_job({'stage':'frd'}),self.admin)
        self.assertEqual(brief,self.document(result)['revision']['content']['requirements'][0]['description'])
        with hub.db(True) as db:
            db.execute('UPDATE items SET description=? WHERE id=?',(brief+' Review reset conditions.',self.project['id']))
            after=reliability.snapshot(db,self.project['id'],'q_generate',{'stage':'frd'})
        self.assertNotEqual(before['project_brief'],after['project_brief'])

    def test_chopper_without_sources_does_not_report_a_successful_empty_draft(self):
        from backend.core.workhub_quality import processing
        first=self.draft()
        with self.assertRaisesRegex(ValueError,'Describe the requirement'):
            processing.generate(self.generation_job({'stage':'frd'}),self.admin)
        self.assertEqual(first['revision_id'],self.document(first)['revision']['id'])

    def test_chopper_preserves_edited_draft_and_validates_brief(self):
        first=self.draft();r=self.document(first)['revision'];content=r['content'];content['purpose']='Saved engineer work'
        documents.save(self.admin,self.project['id'],first['control_id'],{'revision_id':r['id'],'version':r['version'],'content':content})
        prefix='/projects/'+self.project['id']+'/quality/generate'
        self.request('POST',prefix,{'stage':'frd','brief':{'invalid':'object'}},400)
        self.request('POST',prefix,{'stage':'frd','brief':'Generate another draft'},409)
        with hub.db() as db:self.assertEqual(0,db.execute('SELECT count(*) FROM pi_jobs WHERE project_id=?',(self.project['id'],)).fetchone()[0])
        self.assertEqual('Saved engineer work',self.document(first)['revision']['content']['purpose'])

    def test_chopper_rejects_invented_technical_values(self):
        from backend.core.workhub_quality import processing
        from backend.core.workhub_intelligence import local_ai
        def model(instruction,payload,check):
            return {'requirements':[{'title':'Motor trip','description':'Display motor trip after 99 seconds','source_ids':[payload['sources'][0]['id']]}]}
        with patch.object(local_ai,'configured',return_value=True),patch.object(local_ai,'_llm_json',side_effect=model):
            with self.assertRaises(local_ai.ModelOutputError):processing.generate(self.generation_job({'stage':'frd','brief':'The PLC shall display the motor trip.'}),self.admin)

    def test_custom_dashboard_saves_widgets_layout_and_chopper_proposal(self):
        first=self.request('POST','/dashboards/templates/engineering-overview',{'if_empty':True})
        query=deepcopy(first['configuration']['widgets'][0]['query']);query['global']['from']='2099-01-01'
        empty=self.request('POST','/dashboards/query',query)
        self.assertEqual(0,empty['total_records']);self.assertEqual([0],empty['totals'])
        config=deepcopy(first['configuration']);config['name']='Saved engineering dashboard';config['layouts']['mobile'][0]['h']+=1
        saved=self.request('PUT','/dashboards/'+first['id'],{'configuration':config,'version':first['version']})
        self.assertEqual(config['layouts']['mobile'][0]['h'],saved['configuration']['layouts']['mobile'][0]['h'])
        config=saved['configuration']
        proposal=self.request('POST','/dashboards/propose',{'configuration':saved['configuration'],'prompt':'Add a bar chart of completed tasks by engineer.'})
        self.assertTrue(proposal['requires_review']);self.assertEqual(config,self.request('GET','/dashboards/'+first['id'])['configuration'])
        config=proposal['configuration'];applied=self.request('PUT','/dashboards/'+first['id'],{'configuration':config,'version':saved['version']})
        self.assertEqual(config,self.request('GET','/dashboards/'+first['id'])['configuration'])
        self.request('PUT','/dashboards/'+first['id'],{'configuration':config,'version':saved['version']},409)
        self.request('PUT','/dashboards/'+first['id']+'/sharing',{'version':applied['version'],'sharing':[{'user_id':self.engineer['id'],'permission':'viewer'}]})
        self.login(self.engineer);self.assertEqual('viewer',self.request('GET','/dashboards/'+first['id'])['permission'])
        self.request('PUT','/dashboards/'+first['id'],{'configuration':config,'version':applied['version']},403)
        self.login(self.outsider);self.request('GET','/dashboards/'+first['id'],expected=403)

del PortfolioTests
if __name__=='__main__':unittest.main()
