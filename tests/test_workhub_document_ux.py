"""Document editor contracts and real starter-template creation paths."""
import os,unittest
from unittest.mock import patch
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import store as hub,identity
from backend.core.workhub_quality import service
from backend.core.workhub_intelligence import store as pi


class DocumentUXTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    tearDown=fixture.PortfolioTests.tearDown;login=fixture.PortfolioTests.login;request=fixture.PortfolioTests.request
    def setUp(self):
        fixture.PortfolioTests.setUp(self)
        self.stack.enter_context(patch.dict(os.environ,{'USOPP_PI_WORKER_MODE':'external'}))

    def create(self,kind,**extra):
        return self.request('POST','/document-spaces',{'stage':'test' if kind=='test_report' else kind,'document_type':kind,'request_id':identity(),**extra})

    def test_each_template_creates_an_editable_numbered_draft_and_saves_a_revision(self):
        catalog=self.request('GET','/diagram-templates')['items']
        self.assertEqual({'programming','process','system','navigation'},{t['id'] for t in catalog if t['kind']=='flowchart'})
        for template in catalog:
            with self.subTest(template=template['id']):
                created=self.create(template['kind'],diagram_template=template['id']);pid=created['scope_id'];did=created['document_id']
                value=pi.get_document(self.admin,pid,did);doc=value['document'];rev=value['revisions'][0]
                self.assertTrue(value['can_edit']);self.assertTrue(doc['number'])
                self.assertEqual(template['id'],rev['content']['starter_template'])
                self.assertEqual(template['content']['nodes'],rev['content']['nodes'])
                ids={n['id'] for n in rev['content']['nodes']}
                self.assertTrue(all(e['source'] in ids and e['target'] in ids for e in rev['content']['edges']))
                content=rev['content'];content['nodes'][0]['data']['label']='Engineer edited start'
                self.request('PUT',f'/projects/{pid}/intelligence/documents/{did}',{'version':rev['id'],'content':content})
                saved=pi.get_document(self.admin,pid,did);self.assertEqual(doc['number'],saved['document']['number']);self.assertEqual(2,len(saved['revisions']))
                self.assertEqual('Engineer edited start',saved['revisions'][0]['content']['nodes'][0]['data']['label'])

    def test_wrong_template_rolls_back_without_consuming_document_number(self):
        with hub.db() as db:before=db.execute('SELECT count(*) FROM wh_document_spaces').fetchone()[0]
        self.request('POST','/document-spaces',{'stage':'mindmap','document_type':'mindmap','diagram_template':'programming','request_id':identity()},400)
        with hub.db() as db:self.assertEqual(before,db.execute('SELECT count(*) FROM wh_document_spaces').fetchone()[0])

    def test_all_controlled_types_save_editable_information_and_clear_text(self):
        for kind in ('frd','corrections','test','test_report','fat','quality','closure'):
            with self.subTest(kind=kind):
                created=self.create(kind);pid=created['scope_id'];did=created['control_id'];record=service.get_document(self.admin,pid,did);rev=record['revision']
                content={**rev['content'],'summary':'A saved draft','purpose':'A purpose','document_info':{**rev['content'].get('document_info',{}),'customer':'Demo customer','project_name':'Editable document only'}}
                self.request('PUT',f'/projects/{pid}/quality/documents/{did}',{'version':rev['version'],'revision_id':rev['id'],'content':content})
                saved=service.get_document(self.admin,pid,did);self.assertEqual('Demo customer',saved['revision']['content']['document_info']['customer'])
                content={**saved['revision']['content'],'summary':'','purpose':''}
                self.request('PUT',f'/projects/{pid}/quality/documents/{did}',{'version':saved['revision']['version'],'revision_id':rev['id'],'content':content})
                final=service.get_document(self.admin,pid,did);self.assertEqual('',final['revision']['content']['summary']);self.assertEqual('',final['revision']['content'].get('purpose',''));self.assertEqual(record['document']['number'],final['document']['number'])

    def test_mom_review_state_and_private_reader_do_not_offer_editing(self):
        created=self.create('mom');pid=created['scope_id'];did=created['document_id'];doc=pi.get_document(self.admin,pid,did);self.assertTrue(doc['can_edit'])
        with hub.db(True) as db:db.execute("UPDATE pi_revisions SET status='review' WHERE id=?",(doc['document']['current_revision'],))
        self.assertFalse(pi.get_document(self.admin,pid,did)['can_edit'])
        self.login(self.outsider);self.request('GET',f'/projects/{pid}/intelligence/documents/{did}',expected=403)

    def test_diagram_reviewer_can_read_but_cannot_edit_the_authors_draft(self):
        created=self.create('flowchart',diagram_template='process');pid=created['scope_id'];did=created['document_id']
        details=self.request('GET','/document-spaces/'+pid)
        self.request('PUT','/document-spaces/'+pid,{'version':details['project']['version'],'reviewer_id':self.lead['id']})
        self.login(self.lead);value=self.request('GET',f'/projects/{pid}/intelligence/documents/{did}');self.assertFalse(value['can_edit'])
        self.request('PUT',f'/projects/{pid}/intelligence/documents/{did}',{'version':value['document']['current_revision'],'content':value['revisions'][0]['content']},403)


if __name__=='__main__':unittest.main()
