"""Structured MOM reports and authenticated decisions use isolated real API workflows."""
import hashlib,io,json,unittest,os
from unittest.mock import patch
from pypdf import PdfReader
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import store as hub,identity,timestamp
from backend.core.workhub_intelligence import store as pi
from backend.core.workhub_quality import store,service,pdf_templates
from backend.core.workhub_signoff import history


class MomSignoffTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    tearDown=fixture.PortfolioTests.tearDown;login=fixture.PortfolioTests.login;request=fixture.PortfolioTests.request

    def setUp(self):
        fixture.PortfolioTests.setUp(self)
        self.stack.enter_context(patch.dict(os.environ,{'USOPP_PI_WORKER_MODE':'external'}))

    def mom(self):
        draft=self.request('POST','/projects/'+self.project['id']+'/quality/drafts',{'stage':'mom','request_id':identity()})
        content={'project_name':self.project['title'],'customer':'Fixture customer','meeting_subject':'Controls design review',
          'meeting_date':'2026-11-01','meeting_start_time':'10:00','meeting_end_time':'11:00','meeting_mode':'Online (Teams)',
          'meeting_types':['Project Review','Issue / Resolution'],'meeting_objective':'Review controls and plan FAT.',
          'agenda':'1. Progress\n2. Open observations','participants':['Engineer One'],
          'participant_details':[{'name':'Engineer One','role':'Controls Engineer','organization':'Fixture Org','attendance':'Present'}],
          'discussion_summary':[{'topic':'Alarm mapping','text':'Mapping reviewed.','decision':'Retest at FAT.','source_ids':[]}],
          'actions':[{'id':'A1','text':'Share validation report','responsible':'Engineer One','target_date':'2026-11-02','status':'Planned','source_ids':[]}],
          'decisions':[{'text':'Retest at FAT.','source_ids':[]}],'next_meeting':{'date':'2026-11-03','time':'09:30','mode':'Factory'},
          'clarifications':[],'sources':[]}
        result=self.request('PUT','/projects/'+self.project['id']+'/intelligence/documents/'+draft['document_id'],{'version':draft['revision_id'],'content':content,'title':'Controls design review'})
        return result

    def review(self,doc,action,**values):
        return self.request('POST','/projects/'+self.project['id']+'/intelligence/documents/'+doc['document']['id']+'/review',
            {'revision_id':doc['revision']['id'],'action':action,**values})

    def signed(self,**values):return {'name':self.lead['username'],'acknowledged':True,**values}

    def test_mom_content_and_pdf_preserve_every_reference_section_and_real_approval(self):
        doc=self.mom();self.review(doc,'submit',reviewer_id=self.lead['id']);self.login(self.lead)
        approved=self.review(doc,'approve',sign_off=self.signed(),comment='Reviewed meeting details and action ownership.')
        details=self.request('GET','/projects/'+self.project['id']+'/intelligence/documents/'+doc['document']['id'])
        self.assertEqual('Planned',details['revisions'][0]['content']['actions'][0]['status'])
        self.assertEqual('Controls design review',details['document']['title'])
        self.assertEqual('approve',details['sign_offs'][0]['decision'])
        with hub.db() as db:
            value=pdf_templates.context(db,hub.item(db,self.project['id']),pi.document(db,doc['document']['id'],self.project['id']),pi.revision(db,doc['revision']['id'],doc['document']['id']),False)
            frozen=json.loads(db.execute('SELECT context FROM wh_pdf_snapshots WHERE revision_id=?',(doc['revision']['id'],)).fetchone()[0])
        html=pdf_templates.html(value)
        text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf_templates.fallback(value))).pages)
        for title in ['Meeting Objective','Agenda','Participants','Discussion Summary','Action Items','Next Meeting','Approval','Review Audit Stamps']:
            self.assertIn(title,html);self.assertIn(title,text)
        for detail in ['Controls Engineer','Fixture Org','Present','Planned','10:00','09:30','Retest at FAT.']:self.assertIn(detail,html)
        self.assertIn(self.lead['username'],html);self.assertEqual(frozen['engine_source'],value['engine_source'])
        self.assertEqual('approved',approved['revision']['status'])

    def test_native_review_requires_name_confirmation_and_remarks_and_reject_is_distinct(self):
        doc=self.mom();self.review(doc,'submit',reviewer_id=self.lead['id']);self.login(self.lead)
        path='/projects/'+self.project['id']+'/intelligence/documents/'+doc['document']['id']+'/review'
        for stamp in [self.signed(name='Another account'),self.signed(acknowledged=False)]:
            self.request('POST',path,{'revision_id':doc['revision']['id'],'action':'approve','sign_off':stamp},400)
        self.request('POST',path,{'revision_id':doc['revision']['id'],'action':'reject','sign_off':self.signed(),'comment':''},400)
        rejected=self.review(doc,'reject',sign_off=self.signed(),comment='Attendance and review outcome are incomplete.')
        self.assertEqual('rejected',rejected['revision']['status'])
        with hub.db() as db:
            rows=history(db,doc['revision']['id']);self.assertEqual(1,len(rows));self.assertEqual('reject',rows[0]['decision'])
            self.assertEqual(self.lead['id'],rows[0]['actor_id']);self.assertEqual(0,rows[0]['acknowledged'])

    def test_review_can_add_evidence_but_cannot_remove_submitted_documents(self):
        doc=self.mom();reference={'document_id':doc['document']['id'],'revision_id':doc['revision']['id']}
        with hub.db(True) as db:
            db.execute("UPDATE items SET stage='quality' WHERE id=?",(self.project['id'],))
            db.execute("UPDATE pi_revisions SET status='approved' WHERE id=?",(doc['revision']['id'],))
        self.login(self.lead);p=self.request('GET','/projects/'+self.project['id'])['project']
        endpoint='/items/'+p['id']+'/approval-documents'
        selected=self.request('PUT',endpoint,{'version':p['version'],'documents':[reference],'review_selection':True})
        self.request('PUT',endpoint,{'version':selected['item']['version'],'documents':[],'review_selection':True},409)
        self.assertEqual(1,len(self.request('GET',endpoint)['selected']))
        rejected=self.request('POST','/items/'+p['id']+'/transition',{'version':selected['item']['version'],'action':'reject',
            'comment':'Retest the observed alarm behavior.','sign_off':self.signed(documents=[reference])})
        self.assertEqual('development',rejected['stage'])
        with hub.db() as db:
            stamp=history(db,p['id'])[0];evidence=stamp['evidence']
            self.assertEqual(doc['revision']['id'],evidence['documents'][0]['revision_id'])
            self.assertEqual(hashlib.sha256(json.dumps(evidence,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),stamp['evidence_hash'])
            self.assertEqual(1,db.execute('SELECT count(*) FROM issues WHERE item_id=?',(p['id'],)).fetchone()[0])

    def test_foreign_evidence_or_issues_cannot_be_signed_and_failure_is_atomic(self):
        doc=self.mom()
        with hub.db(True) as db:db.execute("UPDATE items SET stage='release_approval' WHERE id=?",(self.project['id'],))
        self.login(self.outsider);foreign=self.request('POST','/projects/'+self.other['id']+'/issues',{'title':'Private issue'})
        self.request('POST','/projects/'+self.project['id']+'/issues',{'title':'Unauthorized'},403)
        self.login(self.lead);p=self.request('GET','/projects/'+self.project['id'])['project']
        self.request('POST','/items/'+p['id']+'/transition',{'version':p['version'],'action':'approve_release','sign_off':self.signed(issue_ids=[foreign['id']])},400)
        self.assertEqual('release_approval',self.request('GET','/projects/'+p['id'])['project']['stage'])
        with hub.db() as db:self.assertEqual([],history(db,p['id']))

    def test_controlled_document_rejection_keeps_signed_audit_and_current_reviewer_gate(self):
        draft=self.request('POST','/projects/'+self.project['id']+'/quality/drafts',{'stage':'test'})
        with hub.db(True) as db:
            db.execute("UPDATE qc_revisions SET status='in_review',reviewer_id=? WHERE id=?",(self.lead['id'],draft['revision_id']))
            db.execute("UPDATE pi_revisions SET status='review',reviewer_id=? WHERE id=?",(self.lead['id'],draft['revision_id']))
        row=service.get_document(self.admin,self.project['id'],draft['control_id']);payload={'version':row['revision']['version'],
            'revision_id':draft['revision_id'],'action':'request_corrections','comment':'Add recorded test results.','sign_off':self.signed()}
        path='/projects/'+self.project['id']+'/quality/documents/'+draft['control_id']+'/action'
        self.request('POST',path,payload,403);self.login(self.lead);self.request('POST',path,payload);result=self.request('GET','/projects/'+self.project['id']+'/quality/documents/'+draft['control_id'])
        self.assertEqual('correction_required',result['revision']['status']);self.assertEqual('request_changes',result['sign_offs'][0]['decision'])
