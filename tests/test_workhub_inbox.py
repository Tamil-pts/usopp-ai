"""Personal work inbox combines existing decisions without broadening access."""
import unittest
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import store as hub,identity
from backend.core.workhub_quality import store


class InboxTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    setUp=fixture.PortfolioTests.setUp;tearDown=fixture.PortfolioTests.tearDown
    login=fixture.PortfolioTests.login;request=fixture.PortfolioTests.request

    def test_one_personal_queue_contains_workflow_documents_and_time(self):
        frd=self.request('POST','/projects/'+self.project['id']+'/quality/drafts',{'stage':'frd'})
        mom=self.request('POST','/document-spaces',{'stage':'mom','title':'Standalone reviewed MOM','request_id':identity()})
        scope=self.request('GET','/document-spaces/'+mom['scope_id'])['project']
        self.request('PUT','/document-spaces/'+mom['scope_id'],{'version':scope['version'],'reviewer_id':self.lead['id']})
        time=hub.add_update(self.manager,self.project['id'],{'body':'Project planning work','minutes':45})
        with hub.db(True) as db:
            db.execute("UPDATE items SET stage='quality' WHERE id=?",(self.project['id'],))
            db.execute("UPDATE qc_revisions SET status='in_review',reviewer_id=? WHERE id=?",(self.lead['id'],frd['revision_id']))
            db.execute("UPDATE pi_revisions SET status='review',reviewer_id=? WHERE id IN (?,?)",(self.lead['id'],frd['revision_id'],mom['revision_id']))
        self.login(self.lead);queue=self.request('GET','/inbox')
        self.assertEqual({'document':2,'workflow':1,'time':1},queue['counts']);self.assertEqual(4,queue['pending'])
        self.assertTrue(any(r['independent'] and r['project']=='Standalone document' for r in queue['items'] if r['kind']=='document'))
        self.assertEqual(2,self.request('GET','/inbox?kind=document')['total'])
        self.assertEqual([],self.request('GET','/inbox?page=2')['items'])
        self.request('POST','/updates/'+time['id']+'/review',{'status':'approved','comment':''})
        self.assertEqual(3,self.request('GET','/inbox')['pending'])
        self.login(self.outsider);self.assertEqual(0,self.request('GET','/inbox')['total'])

    def test_time_corrections_stay_with_author_and_resolved_decisions_disappear(self):
        store.initialize();row=hub.add_update(self.manager,self.project['id'],{'body':'Time correction fixture','minutes':30})
        self.login(self.lead)
        self.request('POST','/updates/'+row['id']+'/review',{'status':'changes_requested','comment':'Clarify work done'})
        self.assertEqual(0,self.request('GET','/inbox')['total'])
        self.login(self.manager);queue=self.request('GET','/inbox')
        self.assertEqual(0,queue['pending']);self.assertEqual({'correction':1},queue['counts'])
        self.assertEqual('Clarify work done',queue['items'][0]['entry']['review_comment'])
        self.login(self.engineer);self.assertEqual(0,self.request('GET','/inbox')['total'])
