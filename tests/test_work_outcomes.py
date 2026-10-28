"""Isolated project/task-derived competency and workflow feedback contracts."""
import copy,io,json,unittest
from datetime import datetime,timedelta,timezone
from fastapi import HTTPException
from tests import test_workhub_praxis as fixtures
from backend.core.workhub import store as hub
from backend.core.workhub_praxis import outcomes,service,reports,insights
from backend.core.workhub_growth import store as growth,collector

class WorkOutcomeTests(unittest.TestCase):
    setUp=fixtures.PraxisTests.setUp
    tearDown=fixtures.PraxisTests.tearDown
    unit=fixtures.PraxisTests.unit
    assign=fixtures.PraxisTests.assign
    configure=fixtures.PraxisTests.configure
    def project(self):
        return hub.create(self.admin,{'title':'Isolated delivery','owner_id':self.employee['id'],'quality_id':self.manager['id'],'approver_id':self.admin['id'],'release_id':self.admin['id'],'due_date':(datetime.now(timezone.utc)+timedelta(days=2)).date().isoformat()})
    def act(self,user,p,action,**extra):
        with hub.db() as db:version=hub.item(db,p['id'])['version']
        return hub.transition(user,p['id'],{'action':action,'version':version,**extra})
    def delivered(self):
        p=self.project();self.act(self.employee,p,'start');self.act(self.employee,p,'complete_development');self.act(self.employee,p,'submit_quality')
        self.act(self.manager,p,'quality_pass',work_feedback={'quality':'minor','problem_solving':'independent','response':'prompt','errors_corrected':3,'solutions_shared':1,'troubleshooting_cases':2})
        return p
    def test_scores_come_from_work_without_an_assessment(self):
        p=self.delivered();v=outcomes.profile(self.employee,self.employee['id'])
        self.assertIsNotNone(v['performance_index']);self.assertIsNotNone(v['competency_index']);self.assertNotEqual(v['performance_index'],v['competency_index'])
        self.assertTrue(v['work_based']);self.assertEqual([],v['assessments']);self.assertEqual(3,v['work_counts']['errors_corrected']);self.assertEqual(1,v['work_counts']['completed_work'])
        self.assertIsNone(service.profile(self.employee,self.employee['id'])['competency_index'])
    def test_feedback_is_not_double_counted_and_zero_can_correct_a_count(self):
        p=self.delivered();self.act(self.admin,p,'approve_release',work_feedback={'solutions_shared':1,'errors_corrected':0})
        v=outcomes.profile(self.employee,self.employee['id']);self.assertEqual(1,v['work_counts']['solutions_shared']);self.assertEqual(0,v['work_counts']['errors_corrected']);self.assertEqual(1,len(v['work_feedback']))
    def test_blank_work_and_completed_runs_do_not_invent_scores(self):
        p=self.project();growth.initialize()
        with hub.db(True) as db:collector.put(db,'run','finished-no-result',p['id'],None,self.employee['id'],self.employee['id'],'engineering_run','Completed check',hub.timestamp() if hasattr(hub,'timestamp') else datetime.now(timezone.utc).isoformat(),'native_result',{'tool':'ByteMap','kind':'validation','status':'completed','summary':{}})
        v=outcomes.profile(self.employee,self.employee['id']);self.assertIsNone(v['performance_index']);self.assertIsNone(v['competency_index']);self.assertEqual(1,v['work_counts']['validation_runs'])
    def test_explicit_validation_score_is_used_but_unlinked_runs_are_excluded(self):
        p=self.project();growth.initialize();at=datetime.now(timezone.utc).isoformat()
        with hub.db(True) as db:
            for key,project,score in [('linked',p['id'],60),('separate',None,100),('removed','removed-project',95)]:collector.put(db,'run',key,project,None,self.employee['id'],self.employee['id'],'engineering_run','Check',at,'native_result',{'tool':'ByteMap','kind':'validation','status':'completed','summary':{},'recorded_scores':[{'field':'score','value':score}]})
        v=outcomes.profile(self.employee,self.employee['id']);self.assertEqual(60,next(d['value'] for d in v['performance'] if d['id']=='quality'));self.assertEqual(1,v['work_counts']['validation_runs'])
    def test_workflow_authority_and_invalid_feedback_are_transactional(self):
        p=self.project();self.act(self.employee,p,'start');self.act(self.employee,p,'complete_development');self.act(self.employee,p,'submit_quality')
        with self.assertRaises(HTTPException):self.act(self.employee,p,'quality_pass',work_feedback={'quality':'none'})
        with self.assertRaises(HTTPException):self.act(self.manager,p,'quality_pass',work_feedback={'errors_corrected':-1})
        with hub.db() as db:self.assertEqual('quality',hub.item(db,p['id'])['stage'])
        with self.assertRaises(HTTPException):outcomes.profile(self.outsider,self.employee['id'])
    def test_weights_are_configurable_and_work_exports_use_actual_values(self):
        self.delivered();cfg=outcomes.settings(self.admin);payload=copy.deepcopy(cfg);payload['content']['performance_weights']={'delivery':100,'quality':0,'response':0};outcomes.settings(self.admin,payload)
        with self.assertRaises(HTTPException):outcomes.settings(self.employee,payload)
        p=outcomes.profile(self.employee,self.employee['id']);self.assertEqual(100,p['performance_index'])
        value=reports.data(self.employee,'individual',self.employee['id'],work_based=True)
        from openpyxl import load_workbook
        book=load_workbook(io.BytesIO(reports.excel(value)));self.assertEqual(100,book['Summary']['D5'].value)
        raw=reports.pdf(value);self.assertTrue(raw.startswith(b'%PDF'))
        from pypdf import PdfReader
        self.assertNotIn('Not Assessed',''.join(p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages))
    def test_all_requested_insight_displays_save_without_changing_scores(self):
        cfg=insights.layout(self.employee);widgets=[{**cfg['widgets'][0],'id':'display-'+name,'display':name} for name in ('card','bar','line','area','pie','donut','radar','gauge','heatmap','table','trend')]
        value=insights.save(self.employee,{'version':cfg['version'],'widgets':widgets});self.assertEqual(11,len(value['widgets']))
    def test_fictional_samples_do_not_inflate_real_employee_indices(self):
        p=self.delivered()
        with hub.db(True) as db:db.execute('UPDATE items SET is_sample=1 WHERE id=?',(p['id'],))
        real=outcomes.profile(self.employee,self.employee['id']);self.assertIsNone(real['competency_index']);self.assertEqual(0,real['work_counts']['completed_work'])
        sample=outcomes.profile(self.employee,self.employee['id'],project_id=p['id']);self.assertTrue(sample['sample_preview']);self.assertIsNotNone(sample['competency_index'])

if __name__=='__main__':unittest.main()
