"""Delivery handoffs use isolated existing WorkHub records and exact saved revisions."""
import json,unittest
from unittest.mock import patch
from fastapi import HTTPException
from tests.test_workhub_portfolio import PortfolioTests
from backend.core.workhub import store as hub,identity,timestamp
from backend.core import workhub_delivery as delivery,workhub_approval_documents as attached
from backend.core.workhub_quality import store,authoring,documents,service,checks


class DeliveryTests(unittest.TestCase):
    setUpClass=classmethod(PortfolioTests.setUpClass.__func__)
    setUp=PortfolioTests.setUp;tearDown=PortfolioTests.tearDown
    login=PortfolioTests.login;request=PortfolioTests.request

    def report(self,approved=False):
        content=authoring.blank('test');content['summary']='Saved validation report'
        result=documents.draft(self.manager,self.project['id'],'test',content)
        value=service.get_document(self.manager,self.project['id'],result['control_id'])
        if approved:
            with hub.db(True) as db:
                db.execute("UPDATE qc_revisions SET status='approved',approved_by=?,approved_at=? WHERE id=?",(self.lead['id'],timestamp(),result['revision_id']))
                db.execute("UPDATE pi_revisions SET status='approved',reviewed_by=? WHERE id=?",(self.lead['id'],result['revision_id']))
                db.execute('UPDATE pi_documents SET approved_revision=? WHERE id=?',(result['revision_id'],value['document']['document_id']))
        return {'document_id':value['document']['document_id'],'revision_id':result['revision_id'],'control_id':result['control_id']}

    def select(self,report):
        with hub.db(True) as db:attached.attach(db,hub.item(db,self.project['id']),self.manager,[{'document_id':report['document_id'],'revision_id':report['revision_id']}])

    def project_row(self):
        with hub.db() as db:return hub.item(db,self.project['id'])

    def test_submission_requires_saved_validation_report_and_preserves_exact_identity(self):
        self.login(self.manager)
        with hub.db(True) as db:db.execute("UPDATE items SET stage='development_completed' WHERE project_id=?",(self.project['id'],))
        p=self.project_row();url='/items/'+p['id']+'/transition'
        self.request('POST',url,{'action':'submit_quality','version':p['version'],'revision_id':None},409)
        report=self.report();self.select(report)
        submitted=self.request('POST',url,{'action':'submit_quality','version':p['version'],'revision_id':None})
        self.assertEqual('quality',submitted['stage'])
        with hub.db() as db:
            event=json.loads(db.execute("SELECT detail FROM events WHERE item_id=? AND event='submit_quality' ORDER BY created_at DESC LIMIT 1",(p['id'],)).fetchone()[0])
        self.assertEqual(report['revision_id'],event['approval_documents'][0]['revision_id'])

    def test_development_tasks_still_block_submission(self):
        self.login(self.manager);report=self.report();self.select(report)
        with hub.db(True) as db:db.execute("UPDATE items SET stage='development_completed' WHERE id=?",(self.project['id'],))
        p=self.project_row()
        self.request('POST','/items/'+p['id']+'/transition',{'action':'submit_quality','version':p['version'],'revision_id':None},409)

    def test_required_deliverables_need_completion_and_project_scoped_evidence(self):
        content=authoring.blank('frd');content['sections'].append({'heading':'Deliverables','text':'PLC project archive\nValidation evidence'})
        documents.draft(self.manager,self.project['id'],'frd',content)
        p=self.project_row()
        with hub.db() as db:
            self.assertEqual(2,len(delivery.deliverables(db,p)))
            for payload in [{},{'deliverables_complete':True},{'deliverables_complete':True,'deliverable_file_ids':['foreign-file']}]:
                with self.assertRaises(HTTPException):delivery.guard(db,p,'complete_development',payload)

    def test_review_cannot_approve_unapproved_or_stale_report(self):
        report=self.report();self.select(report);p=self.project_row()
        with hub.db() as db:
            with self.assertRaises(HTTPException):delivery.guard(db,p,'quality_pass',{})
        with hub.db(True) as db:
            db.execute("UPDATE pi_documents SET current_revision='newer-saved-revision' WHERE id=?",(report['document_id'],))
        with hub.db() as db:
            with self.assertRaises(HTTPException):delivery.guard(db,p,'quality_pass',{})

    def test_release_approval_checks_current_quality_conditions(self):
        report=self.report(True);self.select(report);p=self.project_row()
        with hub.db() as db:
            with self.assertRaises(HTTPException) as blocked:delivery.guard(db,p,'approve_release',{})
        self.assertIn('Release prerequisites',str(blocked.exception.detail))

    def test_closure_requires_explicit_handover_and_acceptance_verification(self):
        report=self.report(True);self.select(report);p=self.project_row()
        with hub.db() as db:
            with self.assertRaises(HTTPException):delivery.guard(db,p,'release',{})
            delivery.guard(db,p,'release',{'closure_checks':{k:True for k in ['final_deliverables','handover','required_acceptance']}})

    def test_fat_applicability_requires_manager_reason_and_saved_version(self):
        state=service.overview(self.manager,self.project['id'])
        self.login(self.engineer)
        self.request('PUT','/projects/'+self.project['id']+'/quality/context',{'version':state['context_version'],'fat_applicable':False,'fat_reason':'No physical FAT for this software-only project'},403)
        self.login(self.manager)
        self.request('PUT','/projects/'+self.project['id']+'/quality/context',{'version':state['context_version'],'fat_applicable':False,'fat_reason':''},400)
        self.request('PUT','/projects/'+self.project['id']+'/quality/context',{'version':state['context_version'],'fat_applicable':False,'fat_reason':'Software-only change; FAT does not apply'})
        value=self.request('GET','/projects/'+self.project['id']+'/quality')
        self.assertFalse(value['delivery']['fat_applicable'])
        self.assertNotIn('fat',value['report']['policy']['required_stages'])
        self.assertFalse(any(b['code'] in {'document:fat','fat:customer_acceptance'} for b in value['report']['blockers']))
        self.request('PUT','/projects/'+self.project['id']+'/quality/context',{'version':state['context_version'],'fat_applicable':True,'fat_reason':'Stale change'},409)

    def test_not_applicable_fat_does_not_block_adopted_fat_rules(self):
        from backend.core import workhub_workflow as workflow
        state=service.overview(self.manager,self.project['id'])
        service.context(self.manager,self.project['id'],{'version':state['context_version'],'fat_applicable':False,'fat_reason':'Software delivery; no site FAT'})
        with hub.db(True) as db:
            state=store.policy_row(db,self.project)
            state['policy']['validation_rules']=[{'id':'fat-'+c,'name':'FAT requirement','action':'quality_pass','condition':c,'parameter':'fat','severity':'block','enabled':True} for c in ['document_approved','tests_passed']]
            db.execute('UPDATE qc_projects SET policy=? WHERE project_id=?',(store.bounded(state['policy']),self.project['id']))
            self.assertTrue(all(r['passed'] for r in workflow.evaluate(db,hub.item(db,self.project['id']),'quality_pass')))

    def test_readiness_requires_project_access_and_keeps_history(self):
        self.login(self.outsider)
        self.request('GET','/projects/'+self.project['id']+'/delivery-readiness',expected=403)
        self.login(self.manager);report=self.report()
        with hub.db(True) as db:store.audit(db,self.lead,self.project['id'],'document_reject',{'comment':'Recheck outputs'},report['control_id'],report['revision_id'])
        value=self.request('GET','/projects/'+self.project['id']+'/delivery-readiness')
        self.assertEqual('document_reject',value['validation_history'][0]['action'])


if __name__=='__main__':unittest.main()
