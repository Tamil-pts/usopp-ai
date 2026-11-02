"""Default Validation/FAT reports, real result records and configured identities."""
from copy import deepcopy
import io,json,unittest
from pypdf import PdfReader
from tests.test_workhub_portfolio import PortfolioTests
from backend.core.workhub import store as hub,identity,timestamp
from backend.core.workhub_quality import authoring,documents,configuration,service,store,training,pdf_templates
from backend.core.workhub_quality.report_templates import summary

class ReportTemplateTests(unittest.TestCase):
    setUpClass=classmethod(PortfolioTests.setUpClass.__func__)
    setUp=PortfolioTests.setUp;tearDown=PortfolioTests.tearDown;login=PortfolioTests.login;request=PortfolioTests.request

    def frd(self):
        content=training.example()['frd'];content.pop('flowchart',None)
        row=documents.draft(self.admin,self.project['id'],'frd',content,'Report source fixture')
        # Approved source fixture only; separate workflow tests exercise real decisions.
        with hub.db(True) as db:
            db.execute("UPDATE qc_revisions SET status='approved',reviewed_by=?,approved_by=?,approved_at=? WHERE id=?",(self.lead['id'],self.lead['id'],timestamp(),row['revision_id']))
            db.execute("UPDATE pi_revisions SET status='approved' WHERE id=?",(row['revision_id'],))
            db.execute('UPDATE pi_documents SET approved_revision=current_revision WHERE id=(SELECT document_id FROM qc_documents WHERE id=?)',(row['control_id'],))
        return row

    def draft(self,stage='test'):
        row=self.request('POST','/projects/'+self.project['id']+'/quality/drafts',{'stage':stage})
        return self.detail(row['control_id'])

    def detail(self,key):return service.get_document(self.admin,self.project['id'],key)

    def import_cases(self,record,**payload):
        r=record['revision'];return self.request('POST','/projects/'+self.project['id']+'/quality/documents/'+record['document']['id']+'/import-cases',{'revision_id':r['id'],'version':r['version'],**payload})

    def run_fixture(self,pid=None,status='completed',summary_value=None):
        key=identity()
        with hub.db(True) as db:db.execute('INSERT INTO engineering_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(key,pid or self.project['id'],identity(),1,'validation','fixture',self.admin['id'],status,json.dumps(summary_value or {'total':5,'failed':0}),'Fixture source',timestamp(),timestamp()))
        return key

    def test_default_reports_use_approved_frd_and_configured_numbers_and_revisions(self):
        settings=configuration.get(self.admin);config=deepcopy(settings['configuration'])
        config['codes']['test']='VTR';config['codes']['fat']='FATX';config['revision_pattern']='Rev-{REV}';config['revision_width']=3
        configuration.save(self.admin,{'version':settings['version'],'configuration':config})
        frd=self.frd()
        for stage,code in [('test','VTR'),('fat','FATX')]:
            with self.subTest(stage=stage):
                record=self.draft(stage);rev=record['revision'];content=rev['content']
                self.assertIn('-'+code+'-',record['document']['number']);self.assertEqual('Rev-001',rev['label'])
                self.assertEqual(stage,content['report_type']);self.assertTrue(content['cases']);self.assertEqual(frd['revision_id'],rev['frd_revision_id'])
                self.assertEqual(frd['revision_id'],content['references'][0]['revision_id'])
                self.assertEqual({'not_run'},{c['outcome'] for c in content['cases']});self.assertEqual(0,summary(content)['passed'])
                result=self.import_cases(record,source='frd');self.assertEqual(0,result['added'])
                self.assertEqual(len(content['cases']),len(self.detail(record['document']['id'])['revision']['content']['cases']))
        original=self.draft('test');doc=original['document'];r=original['revision']
        with hub.db(True) as db:
            db.execute("UPDATE qc_revisions SET status='approved' WHERE id=?",(r['id'],))
            db.execute("UPDATE pi_revisions SET status='approved' WHERE id=?",(r['id'],))
            db.execute('UPDATE pi_documents SET approved_revision=current_revision WHERE id=?',(doc['document_id'],))
        service.new_revision(self.admin,self.project['id'],doc['id'],{'revision_id':r['id'],'reason':'Update the report scope'})
        revised=self.detail(doc['id']);self.assertEqual(doc['number'],revised['document']['number']);self.assertEqual('Rev-002',revised['revision']['label'])

    def test_manual_results_retest_summary_and_nine_section_pdf(self):
        record=self.draft();key=record['document']['id'];rev=record['revision'];content=rev['content']
        content.update(purpose='Validate controls',scope='PLC and HMI',conclusion='Retest verified.',report_date='2026-11-01',
            references=[{'id':'REF-001','title':'Customer specification','number':'SPEC-12','revision':'03','date':'2026-10-20'}],
            report_issues=[{'id':'ISS-001','description':'Alarm delay','correction':'Updated logic','retest_result':'Responded within 2 s','status':'closed'}],
            cases=[{'id':'TC-001','objective':'Alarm delay','procedure':'Assert the test input','expected_result':'Delay ≤ 2 s','acceptance_criteria':'Within 2 s','source_ids':[],'requirement_ids':[]}])
        documents.save(self.admin,self.project['id'],key,{'revision_id':rev['id'],'version':rev['version'],'content':content})
        with hub.db(True) as db:
            p=hub.item(db,self.project['id']);state=store.policy_row(db,p);policy=state['policy'];policy['require_test_evidence']=False
            db.execute('UPDATE qc_projects SET policy=? WHERE project_id=?',(store.bounded(policy),self.project['id']))
        for outcome,actual in [('fail','4 s'),('pass','1.5 s')]:
            r=self.detail(key)['revision'];documents.execute(self.admin,self.project['id'],key,{'revision_id':r['id'],'version':r['version'],'case_id':'TC-001','outcome':outcome,'actual':actual,'observations':'Retest' if outcome=='pass' else 'Initial failure','file_ids':[]})
        record=self.detail(key);r=record['revision'];self.assertEqual(2,len(r['execution_history']));self.assertEqual({'total':1,'passed':1,'failed':0,'pending':0,'not_applicable':0},summary(r['content']))
        with hub.db() as db:value=pdf_templates.context(db,hub.item(db,self.project['id']),record['document'],r)
        output=pdf_templates.fallback(value);text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(output)).pages)
        for label in ['1. Document Details','2. Project Details','3. Validation Objective','4. Reference Documents','5. Validation Test Results','6. Issues & Corrections','7. Validation Summary','8. Conclusion','9. Sign-Off',record['document']['number'],r['label'],'SPEC-12','1.5 s','Responded within 2 s']:
            self.assertIn(label,text)
        edited=r['content'];edited['cases'][0]['expected_result']='Delay ≤ 1 s'
        documents.save(self.admin,self.project['id'],key,{'revision_id':r['id'],'version':r['version'],'content':edited})
        self.assertEqual(1,summary(self.detail(key)['revision']['content'])['pending'])

    def test_native_import_is_scoped_idempotent_and_requires_confirmation(self):
        record=self.draft();key=record['document']['id'];run_id=self.run_fixture()
        self.assertEqual(1,self.import_cases(record,source='validation',run_id=run_id)['added'])
        record=self.detail(key);r=record['revision'];case=r['content']['cases'][0]
        self.assertEqual('pass',case['source_result']['outcome']);self.assertEqual('not_run',case['outcome'])
        self.assertEqual(0,self.import_cases(record,source='validation',run_id=run_id)['added'])
        record=self.detail(key);r=record['revision'];service.action(self.admin,self.project['id'],key,{'revision_id':r['id'],'version':r['version'],'action':'confirm'})
        self.assertEqual(1,summary(self.detail(key)['revision']['content'])['passed'])
        other_run=self.run_fixture(self.other['id'])
        record=self.detail(key);r=record['revision']
        self.request('POST','/projects/'+self.project['id']+'/quality/documents/'+key+'/import-cases',{'revision_id':r['id'],'version':r['version'],'source':'validation','run_id':other_run},404)
        self.login(self.outsider);self.request('POST','/projects/'+self.project['id']+'/quality/documents/'+key+'/import-cases',{'revision_id':r['id'],'version':r['version'],'source':'frd'},403)

    def test_unapproved_frd_and_forged_reference_are_rejected(self):
        record=self.draft();key=record['document']['id'];r=record['revision']
        self.request('POST','/projects/'+self.project['id']+'/quality/documents/'+key+'/import-cases',{'revision_id':r['id'],'version':r['version'],'source':'frd'},409)
        other=authoring.create(self.admin,self.other['id'],{'stage':'fat'})
        content=r['content'];content['references']=[{'id':'REF-001','title':'Wrong project','control_id':other['control_id'],'revision_id':other['revision_id']}]
        self.request('PUT','/projects/'+self.project['id']+'/quality/documents/'+key,{'revision_id':r['id'],'version':r['version'],'content':content},404)

    def test_fat_pdf_starts_without_invented_acceptance_or_signatures(self):
        record=self.draft('fat');r=record['revision']
        with hub.db() as db:value=pdf_templates.context(db,hub.item(db,self.project['id']),record['document'],r)
        text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf_templates.fallback(value))).pages)
        for label in ['3. FAT Objective','5. FAT Test Results','6. Issues & Observations','7. FAT Summary','8. Final Acceptance','Not recorded','9. Sign-Off','Pending acceptance']:
            self.assertIn(label,text)
        self.assertIsNone(r['acceptance']);self.assertFalse(r.get('approved_by'))

    def test_fat_references_the_approved_validation_revision(self):
        self.frd();test=self.draft();r=test['revision']
        with hub.db(True) as db:
            db.execute("UPDATE qc_revisions SET status='approved' WHERE id=?",(r['id'],))
            db.execute("UPDATE pi_revisions SET status='approved' WHERE id=?",(r['id'],))
            db.execute('UPDATE pi_documents SET approved_revision=current_revision WHERE id=?',(test['document']['document_id'],))
        fat=self.draft('fat');ref=next(v for v in fat['revision']['content']['references'] if v.get('control_id')==test['document']['id'])
        self.assertEqual(r['id'],ref['revision_id']);self.assertEqual(test['document']['number'],ref['number']);self.assertEqual(r['label'],ref['revision'])
