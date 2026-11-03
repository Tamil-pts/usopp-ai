"""Workflow document selection, assigned decisions, isolation and stale revisions."""
import json,unittest
from fastapi import HTTPException
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import store as hub,identity,timestamp
from backend.core import workhub_approval_documents as attachments
from backend.core.workhub_quality import store


class WorkflowDocumentTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    setUp=fixture.PortfolioTests.setUp;tearDown=fixture.PortfolioTests.tearDown
    login=fixture.PortfolioTests.login;request=fixture.PortfolioTests.request

    def mom(self,linked=None):
        return self.request('POST','/document-spaces',{'stage':'mom','title':'Review MOM','request_id':identity(),
          'linked_project_id':linked or self.project['id']})

    def selection(self,row):
        return [{'document_id':row['document_id'],'revision_id':row['revision_id']}]

    def current(self,key=None):
        with hub.db() as db:return hub.item(db,key or self.project['id'])

    def approve_fixture(self,row):
        with hub.db(True) as db:
            db.execute("UPDATE qc_revisions SET status='approved',approved_by=?,approved_at=? WHERE id=?",(self.lead['id'],timestamp(),row['revision_id']))
            db.execute("UPDATE pi_revisions SET status='approved',reviewed_by=?,reviewed_at=? WHERE id=?",(self.lead['id'],timestamp(),row['revision_id']))
            db.execute('UPDATE pi_documents SET approved_revision=? WHERE id=?',(row['revision_id'],row['document_id']))

    def test_selected_documents_follow_submission_and_actual_project_decision(self):
        self.login(self.manager);doc=self.request('POST','/document-spaces',{'stage':'test','title':'Saved Validation Test Report','request_id':identity(),'linked_project_id':self.project['id']})
        with hub.db() as db:doc['document_id']=store.control(db,doc['scope_id'],doc['control_id'])['document_id']
        with hub.db(True) as db:db.execute("UPDATE items SET stage='development_completed' WHERE project_id=?",(self.project['id'],))
        p=self.current();payload={'action':'submit_quality','version':p['version'],'revision_id':None,'approval_documents':self.selection(doc)}
        submitted=self.request('POST','/items/'+p['id']+'/transition',payload)
        self.assertEqual('quality',submitted['stage'])
        self.login(self.lead)
        view=self.request('GET','/items/'+p['id']+'/approval-documents')
        self.assertEqual(doc['revision_id'],view['selected'][0]['revision_id']);self.assertFalse(view['can_attach'])
        # Attachment makes this workspace readable to the existing project team,
        # but does not let the project reviewer edit a private author's document.
        self.request('GET','/document-spaces/'+doc['scope_id'])
        scope=self.request('GET','/document-spaces/'+doc['scope_id'])['project']
        self.request('PUT','/document-spaces/'+doc['scope_id'],{'version':scope['version'],'reviewer_id':self.lead['id']},403)
        self.request('POST','/items/'+p['id']+'/transition',{'version':submitted['version'],'action':'quality_pass'},409)
        self.approve_fixture(doc)
        self.login(self.outsider)
        self.request('POST','/items/'+p['id']+'/transition',{'version':submitted['version'],'action':'quality_pass'},403)
        self.request('GET','/items/'+p['id']+'/approval-documents',expected=403)
        self.login(self.lead)
        approved=self.request('POST','/items/'+p['id']+'/transition',{'version':submitted['version'],'action':'quality_pass'})
        self.assertEqual('release_approval',approved['stage'])
        with hub.db() as db:
            event=json.loads(db.execute("SELECT detail FROM events WHERE item_id=? AND event='quality_pass' ORDER BY id DESC",(p['id'],)).fetchone()[0])
        self.assertEqual(doc['revision_id'],event['approval_documents'][0]['revision_id'])
        self.assertEqual(64,len(event['approval_documents'][0]['content_hash']))
        # A changed current revision invalidates the old selection at the next decision.
        with hub.db(True) as db:
            old=dict(db.execute('SELECT * FROM pi_revisions WHERE id=?',(doc['revision_id'],)).fetchone())
            old.update(id=identity(),number=old['number']+1,status='draft',generated_by=identity())
            db.execute('INSERT INTO pi_revisions('+','.join(old)+') VALUES('+','.join('?' for _ in old)+')',list(old.values()))
            db.execute('UPDATE pi_documents SET current_revision=? WHERE id=?',(old['id'],doc['document_id']))
        self.request('POST','/items/'+p['id']+'/transition',{'version':approved['version'],'action':'approve_release'},409)

    def test_selection_permissions_scope_version_and_current_revision_are_enforced(self):
        doc=self.mom();self.login(self.outsider)
        self.request('PUT','/items/'+self.project['id']+'/approval-documents',{'version':self.project['version'],'documents':self.selection(doc)},403)
        self.login(self.manager)
        self.request('PUT','/items/'+self.project['id']+'/approval-documents',{'version':self.project['version'],'documents':self.selection(doc)},403)
        self.login(self.admin)
        unrelated=self.mom(self.other['id'])
        endpoint='/items/'+self.project['id']+'/approval-documents'
        self.request('PUT',endpoint,{'version':self.project['version'],'documents':self.selection(unrelated)},400)
        saved=self.request('PUT',endpoint,{'version':self.project['version'],'documents':self.selection(doc)})
        self.assertEqual(self.project['version']+1,saved['item']['version'])
        self.request('PUT',endpoint,{'version':self.project['version'],'documents':[]},409)
        self.assertEqual(1,len(self.request('GET',endpoint)['selected']))
        removed=self.request('PUT',endpoint,{'version':saved['item']['version'],'documents':[]})
        self.assertFalse(removed['selected'])
        self.login(self.engineer)
        self.request('GET','/document-spaces/'+doc['scope_id'],expected=403)

    def test_release_step_documents_are_checked_at_release_and_summary_names_the_step(self):
        doc=self.mom()
        task=hub.create(self.manager,{'title':'Customer handover','owner_id':self.manager['id'],'work_phase':'release'},self.project['id'])
        self.request('PUT','/items/'+task['id']+'/approval-documents',{'version':task['version'],'documents':self.selection(doc)})
        view=self.request('GET','/items/'+self.project['id']+'/approval-documents')
        self.assertEqual('Customer handover',view['related'][0]['step_title'])
        with hub.db() as db:
            self.assertEqual([],attachments.guard(db,self.current(),'quality_pass'))
            with self.assertRaises(HTTPException) as failure:attachments.guard(db,self.current(),'release')
            self.assertEqual(409,failure.exception.status_code)
