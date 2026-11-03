"""FRD report fields, project numbering and editable planning; isolated data only."""
import copy
import json
import unittest
from unittest.mock import patch
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import store as hub
from backend.core.workhub_quality import store as quality,configuration,documents,authoring,service
from backend.core.workhub_intelligence.documents import generated_file

class ReportPlanningTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    setUp=fixture.PortfolioTests.setUp
    tearDown=fixture.PortfolioTests.tearDown
    login=fixture.PortfolioTests.login
    request=fixture.PortfolioTests.request

    def new_project(self,**extra):
        return self.request('POST','/projects',{'workspace_schema':3,'title':'Isolated planning example','customer':'Fixture Client','description':'Fixture scope','scope':'Fixture scope','owner_id':self.manager['id'],'quality_id':self.lead['id'],'release_id':self.lead['id'],**extra})

    def test_prefix_preview_manual_automatic_and_client_context(self):
        quality.initialize()
        with hub.db() as db:setting=configuration.current(db)
        config=copy.deepcopy(setting['configuration']);config['project_prefix']='FIX-PRJ'
        configuration.save(self.admin,{'version':setting['version'],'configuration':config})
        first=self.request('GET','/project-numbering')
        second=self.request('GET','/project-numbering')
        self.assertEqual(first,second)
        p=self.new_project();self.assertEqual(first['preview'],p['project_number'])
        self.assertEqual('Fixture Client',service.overview(self.admin,p['id'])['context']['customer'])
        manual=self.new_project(title='Manual ID',project_number='CUSTOM42')
        self.assertEqual('FIX-PRJ-CUSTOM42',manual['project_number'])
        self.new_project(title='Already prefixed ID',project_number='FIX-PRJ-CUSTOM43')
        self.request('POST','/projects',{'title':'Duplicate fixture','project_number':'CUSTOM42'},409)

    def test_agile_sprints_waterfall_custom_and_no_duplicate_named_steps(self):
        phases=[{'phase':code,'title':code,'start_date':'2026-10-27','due_date':'2026-11-20'} for code in ('development','quality','release')]
        for method,count in [('waterfall',3),('custom',0),('agile',8)]:
            p=self.new_project(methodology=method,phase_plan=phases,sprints=[{'title':'Sprint 1','start_date':'2026-10-27','due_date':'2026-11-02'},{'title':'Sprint 2','start_date':'2026-11-03','due_date':'2026-11-09'}] if method=='agile' else [])
            d=self.request('GET','/projects/'+p['id']);self.assertEqual(3,len(d['phases']));self.assertEqual(count,len(d['tasks']))
            self.assertEqual(2 if method=='agile' else 0,len(d['sprints']))
        p=self.new_project(methodology='agile',phase_plan=phases,sprints=[{'title':'Plan only sprint','start_date':'2026-10-27','due_date':'2026-11-02'}],generate_plan_tasks=False)
        d=self.request('GET','/projects/'+p['id']);self.assertEqual(0,len(d['tasks']));self.assertEqual(1,len(d['sprints']))

    def test_schedule_changes_at_quality_and_after_completion_preserve_actuals(self):
        p=self.new_project(start_date='2026-10-27',due_date='2026-11-20')
        with hub.db(True) as db:db.execute("UPDATE items SET stage='released',started_at='2026-10-27T00:00:00Z',completed_at='2026-10-28T00:00:00Z' WHERE id=?",(p['id'],))
        before=self.request('GET','/projects/'+p['id'])['project']
        from backend.core.workhub_quality import checks
        with hub.db() as db:original_review=checks.baseline(db,hub.item(db,p['id']),True)
        d=self.request('PUT','/projects/'+p['id']+'/schedule',{'items':[{'type':'project','id':p['id'],'version':before['version'],'start_date':'2026-10-28','due_date':'2026-11-21'}]})
        after=d['project'];self.assertEqual(before['baseline_due'],after['baseline_due']);self.assertEqual(before['completed_at'],after['completed_at']);self.assertEqual('released',after['stage'])
        self.assertEqual('2026-11-21',after['due_date'])
        with hub.db() as db:self.assertEqual(original_review,checks.baseline(db,hub.item(db,p['id']),True))
        self.request('PUT','/projects/'+p['id']+'/schedule',{'items':[{'type':'project','id':p['id'],'version':before['version'],'start_date':'2026-10-28','due_date':'2026-11-22'}]},409)
        self.login(self.outsider)
        self.request('PUT','/projects/'+p['id']+'/schedule',{'items':[{'type':'project','id':p['id'],'version':after['version'],'start_date':'2026-10-28','due_date':'2026-11-22'}]},403)

    def test_change_method_at_quality_can_add_sprints_preserving_existing_work(self):
        p=self.new_project()
        with hub.db(True) as db:db.execute("UPDATE items SET stage='quality' WHERE id=?",(p['id'],))
        p=self.request('GET','/projects/'+p['id'])['project']
        d=self.request('PUT','/projects/'+p['id']+'/planning-method',{'version':p['version'],'methodology':'agile'})
        self.assertEqual('quality',d['project']['stage']);self.assertEqual('agile',d['project']['methodology'])
        self.request('POST','/projects/'+p['id']+'/sprints',{'title':'New planned sprint','start_date':'2026-10-27','due_date':'2026-11-02'})
        self.assertEqual(1,len(self.request('GET','/projects/'+p['id'])['sprints']))

    def frd(self):
        p=self.new_project();pid=p['id']
        file=generated_file(self.manager,pid,'fixture-spec.txt',b'Fictional specification attachment')
        d=documents.draft(self.manager,pid,'frd',{'summary':'Fixture requirement','purpose':'Verify fixture','scope':'Fixture PLC alarm','requirements':[{'id':'FR-001','title':'Fixture alarm','description':'Assert the fixture alarm input.','expected_behavior':'The alarm is shown.','acceptance_criteria':'The fixture alarm follows the input.'}],'field_files':{'requirement/FR-001/description':[file['id']],'requirement/FR-001/acceptance_criteria':[file['id']]}})
        return p,file,d

    def test_field_links_persist_in_derived_test_and_fat_and_are_project_scoped(self):
        p,file,d=self.frd();pid=p['id']
        value=service.get_document(self.manager,pid,'frd');r=value['revision']
        self.assertIn(file['id'],r['content']['file_ids'])
        self.assertEqual([file['id']],r['content']['field_files']['requirement/FR-001/description'])
        authoring.prepare_related(self.manager,pid)
        for stage,prefix in [('test','TC-'),('fat','FAT-')]:
            value=service.get_document(self.manager,pid,stage);r=value['revision'];body=r['content']
            self.assertEqual([file['id']],body['field_files']['case/'+prefix+'001/procedure'])
            self.assertIsNone(body['cases'][0]['execution'])
            self.assertEqual('Fixture alarm',body['cases'][0]['objective'])
        value=service.get_document(self.manager,pid,'test');r=value['revision'];body=copy.deepcopy(r['content'])
        other=generated_file(self.outsider,self.other['id'],'private-file.txt',b'Unrelated private file')
        body['field_files']['case/TC-001/procedure']=[other['id']]
        self.request('PUT','/projects/'+pid+'/quality/documents/test',{'revision_id':r['id'],'version':r['version'],'content':body},400)
        body=copy.deepcopy(r['content']);body['field_files']['case/MISSING/procedure']=[file['id']]
        self.request('PUT','/projects/'+pid+'/quality/documents/test',{'revision_id':r['id'],'version':r['version'],'content':body},400)

    def test_changing_specification_attachment_changes_case_hash(self):
        p,file,d=self.frd();pid=p['id'];authoring.prepare_related(self.manager,pid)
        r=service.get_document(self.manager,pid,'test')['revision'];before=quality.case_hash(r['content']['cases'][0],r['frd_revision_id'])
        other=generated_file(self.manager,pid,'updated-fixture-spec.txt',b'Revised fictional specification')
        body=copy.deepcopy(r['content']);body['field_files']['case/TC-001/procedure']=[other['id']]
        documents.save(self.manager,pid,'test',{'version':r['version'],'revision_id':r['id'],'content':body})
        r=service.get_document(self.manager,pid,'test')['revision'];self.assertNotEqual(before,quality.case_hash(r['content']['cases'][0],r['frd_revision_id']))

    def test_frd_project_cannot_bypass_missing_report_review_via_transition(self):
        p,file,d=self.frd()
        with hub.db(True) as db:db.execute("UPDATE items SET stage='quality' WHERE id=?",(p['id'],))
        p=self.request('GET','/projects/'+p['id'])['project'];self.login(self.lead)
        response=self.request('POST','/items/'+p['id']+'/transition',{'action':'quality_pass','version':p['version']},409)
        self.assertIn('Validation Report and FAT',response['detail'])

    def test_review_task_completion_is_explicit_atomic_and_preserves_reviewed_content(self):
        p=self.new_project();pid=p['id']
        task=hub.create(self.admin,{'title':'Review the test report','work_phase':'quality','owner_id':self.lead['id']},pid)
        with hub.db(True) as db:
            policy=quality.policy_row(db,hub.item(db,pid))['policy'];policy.update(required_stages=['quality','closure'],required_project_fields=[])
            db.execute('UPDATE qc_projects SET policy=? WHERE project_id=?',(quality.bounded(policy),pid));db.execute("UPDATE items SET stage='quality' WHERE id=?",(pid,))
        validation=documents.draft(self.manager,pid,'test',{'summary':'Saved validation fixture'})
        from backend.core.workhub_approval_documents import attach
        with hub.db(True) as db:
            control=quality.control(db,pid,validation['control_id']);rid=validation['revision_id']
            db.execute("UPDATE qc_revisions SET status='approved',approved_by=? WHERE id=?",(self.lead['id'],rid))
            db.execute("UPDATE pi_revisions SET status='approved',reviewed_by=? WHERE id=?",(self.lead['id'],rid))
            db.execute('UPDATE pi_documents SET approved_revision=? WHERE id=?',(rid,control['document_id']))
            attach(db,hub.item(db,pid),self.lead,[{'document_id':control['document_id'],'revision_id':rid}],review=True)
        from backend.core.workhub_quality import checks
        with hub.db() as db:basis=checks.baseline(db,hub.item(db,pid))
        documents.draft(self.manager,pid,'quality',{'summary':'Prepared fictional review'},baseline=basis)
        for action in ('confirm','submit'):
            r=service.get_document(self.manager,pid,'quality')['revision'];service.action(self.manager,pid,'quality',{'version':r['version'],'revision_id':r['id'],'action':action})
        self.login(self.lead);r=service.get_document(self.lead,pid,'quality')['revision']
        payload={'version':r['version'],'revision_id':r['id'],'action':'approve','checklist':dict.fromkeys(['documents','requirements','tests','fat','issues','approvals'],True)}
        path='/projects/'+pid+'/quality/documents/quality/action'
        self.request('POST',path,payload,409)
        self.assertEqual('in_review',service.get_document(self.lead,pid,'quality')['revision']['status'])
        self.assertEqual('todo',hub.detail(pid)['tasks'][0]['stage'])
        self.request('POST',path,{**payload,'complete_review_tasks':True,'quality_task_versions':{task['id']:0}},409)
        with patch('backend.core.workhub_quality.pdf_templates.freeze'),patch('backend.core.workhub_intelligence.jobs.enqueue',return_value={}):
            self.request('POST',path,{**payload,'complete_review_tasks':True,'quality_task_versions':{task['id']:task['version']}})
        after=service.get_document(self.lead,pid,'quality')['revision']
        self.assertEqual('approved',after['status']);self.assertEqual(r['content_hash'],after['content_hash'])
        detail=hub.detail(pid);self.assertEqual('development_completed',detail['tasks'][0]['stage']);self.assertEqual('release_approval',detail['project']['stage'])
