"""Independent document identities, link permissions, saved facts and diagrams."""
import json,os,unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_workhub_portfolio import PortfolioTests
from backend.core.workhub import store as hub,identity
from backend.core.workhub_quality import service
from backend.core.workhub_intelligence import store as pi
from backend.core import workhub_diagrams as diagrams


class IndependentDiagramTests(unittest.TestCase):
    setUpClass=classmethod(PortfolioTests.setUpClass.__func__)
    tearDown=PortfolioTests.tearDown;login=PortfolioTests.login;request=PortfolioTests.request
    def setUp(self):
        PortfolioTests.setUp(self)
        self.stack.enter_context(patch.dict(os.environ,{'USOPP_PI_WORKER_MODE':'external'}))

    def create(self,kind='flowchart',**extra):
        return self.request('POST','/document-spaces',{'stage':kind,'document_type':kind,'request_id':identity(),'title':'Independent '+kind,**extra})

    def test_distinct_numbered_types_and_no_portfolio_projects(self):
        with hub.db() as db:before=db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0]
        a=self.create();b=self.create('mindmap');c=self.create('frd')
        rows=self.request('GET','/documents')['items'];selected=[r for r in rows if r['project_id'] in {a['scope_id'],b['scope_id'],c['scope_id']}]
        self.assertEqual({'flowchart','mindmap','frd'},{r['type'] for r in selected});self.assertEqual(3,len({r['document_number'] for r in selected}))
        self.assertTrue(any('MMAP' in r['document_number'] for r in selected))
        numbered=next(r for r in selected if r['type']=='mindmap')
        self.assertEqual(numbered['id'],self.request('GET','/documents?search='+numbered['document_number'])['items'][0]['id'])
        with hub.db() as db:self.assertEqual(before,db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0])
        detail=self.request('GET','/document-spaces/'+b['scope_id']);self.assertEqual('native:'+b['document_id'],detail['initial_document'])
        again=self.request('POST','/document-spaces',{'stage':'flowchart','document_type':'flowchart','request_id':'retry-fixture'})
        self.assertEqual(again['document_id'],self.request('POST','/document-spaces',{'stage':'flowchart','document_type':'flowchart','request_id':'retry-fixture'})['document_id'])

    def test_information_is_independent_and_pdf_uses_saved_values(self):
        for kind in ('frd','test','fat','closure'):
            created=self.create(kind,linked_project_id=self.project['id']);pid=created['scope_id']
            doc=service.get_document(self.admin,pid,created['control_id']);rev=doc['revision']
            self.assertEqual(self.project['title'],rev['content']['document_info']['project_name'])
            content={**rev['content'],'document_info':{**rev['content']['document_info'],'project_name':'Document-specific motor','customer':'Recorded customer','document_date':'2026-02-10'}}
            self.request('PUT',f'/projects/{pid}/quality/documents/{created["control_id"]}',{'revision_id':rev['id'],'version':rev['version'],'content':content})
            saved=service.get_document(self.admin,pid,created['control_id']);self.assertEqual('Document-specific motor',saved['revision']['content']['document_info']['project_name'])
            from backend.core.workhub_quality.pdf_templates import context
            with hub.db() as db:
                view=context(db,hub.item(db,pid),saved['document'],saved['revision'])
                self.assertIn('Document-specific motor',json.dumps(view))
            self.assertEqual(self.project['title'],self.request('GET','/projects/'+self.project['id'])['project']['title'])

    def test_link_unlink_prefill_and_private_frd_denial(self):
        source=self.create('frd');diagram=self.create(linked_document_id=service.get_document(self.admin,source['scope_id'],source['control_id'])['document']['document_id']);pid=diagram['scope_id']
        detail=self.request('GET','/document-spaces/'+pid)
        updated=self.request('PUT','/document-spaces/'+pid,{'version':detail['project']['version'],'linked_project_id':self.project['id'],'autofill':True})
        doc=pi.get_document(self.admin,pid,diagram['document_id']);self.assertEqual(self.project['title'],doc['revisions'][0]['content']['document_info']['project_name'])
        self.request('PUT','/document-spaces/'+pid,{'version':updated['project']['version'],'linked_project_id':None,'autofill':False})
        self.login(self.outsider);self.request('GET','/document-spaces/'+pid,expected=403)
        self.request('POST','/document-spaces',{'stage':'mindmap','document_type':'mindmap','linked_document_id':detail['project']['linked_document_id']},403)

    def test_shapes_saved_exported_and_review_requires_another_account(self):
        created=self.create('mindmap');pid=created['scope_id'];did=created['document_id'];path=f'/projects/{pid}/intelligence/documents/{did}'
        doc=pi.get_document(self.admin,pid,did);rev=doc['revisions'][0];content=rev['content'];content['nodes'][0].update(width=360,height=120);content['nodes'][0]['data']['color']='#cceeff'
        saved=self.request('PUT',path,{'version':rev['id'],'content':content});rid=saved['revision']['id']
        svg=self.client.get('/api/workhub'+path+'/export/svg?revision_id='+rid);self.assertEqual(200,svg.status_code);self.assertIn('#cceeff',svg.text);self.assertIn('width="360.0"',svg.text)
        self.request('POST',path+'/review',{'revision_id':rid,'action':'submit'},400)
        detail=self.request('GET','/document-spaces/'+pid)
        self.request('PUT','/document-spaces/'+pid,{'version':detail['project']['version'],'reviewer_id':self.admin['id']},400)
        detail=self.request('PUT','/document-spaces/'+pid,{'version':detail['project']['version'],'reviewer_id':self.lead['id']})
        self.request('POST',path+'/review',{'revision_id':rid,'action':'submit','reviewer_id':self.lead['id']})
        self.request('PUT','/document-spaces/'+pid,{'version':detail['project']['version'],'reviewer_id':self.engineer['id']},409)
        self.request('POST',path+'/review',{'revision_id':rid,'action':'approve'},403)
        self.login(self.lead)
        self.request('PUT',path,{'version':rid,'content':content},403)
        self.request('POST',path+'/review',{'revision_id':rid,'action':'request_changes','comment':'Add the maintenance branch.'})
        self.login(self.admin);latest=pi.get_document(self.admin,pid,did);self.assertEqual('changes_requested',latest['revisions'][0]['status'])
        self.request('POST',path+'/review',{'revision_id':rid,'action':'submit','reviewer_id':self.lead['id']})
        self.login(self.lead);self.request('POST',path+'/review',{'revision_id':rid,'action':'approve','sign_off':{'name':self.lead['username'],'acknowledged':True}})
        self.assertEqual(rid,pi.get_document(self.lead,pid,did)['document']['approved_revision'])

    def test_chopper_proposals_are_validated_and_stale_apply_is_denied(self):
        created=self.create();pid=created['scope_id'];did=created['document_id'];rid=created['revision_id']
        payload={'document_id':did,'revision_id':rid,'brief':'Start then stop.'}
        job=self.request('POST','/document-spaces/'+pid+'/diagram/assist',payload)
        stub=SimpleNamespace(row={'project_id':pid,'payload':payload},progress=lambda *a:None,check=lambda:None)
        model={'nodes':[{'id':'start','data':{'kind':'start','label':'Start','source_ids':['BRIEF']}}],'edges':[]}
        with patch('backend.core.workhub_intelligence.local_ai.llm_json',return_value=model):proposal=diagrams.generate_job(stub,self.admin)
        self.assertEqual(rid,pi.get_document(self.admin,pid,did)['document']['current_revision'])
        with hub.db(True) as db:db.execute("UPDATE pi_jobs SET status='completed',result=? WHERE id=?",(json.dumps(proposal),job['id']))
        applied=self.request('POST',f'/document-spaces/{pid}/diagram/proposals/{job["id"]}/apply',{'revision_id':rid})
        self.assertEqual(2,applied['revision']['number'])
        self.request('POST',f'/document-spaces/{pid}/diagram/proposals/{job["id"]}/apply',{'revision_id':applied['revision']['id']},409)
        model['nodes'][0]['data']['source_ids']=['invented']
        stub.row['payload']['revision_id']=applied['revision']['id']
        with patch('backend.core.workhub_intelligence.local_ai.llm_json',return_value=model):
            with self.assertRaisesRegex(ValueError,'unsupported source'):diagrams.generate_job(stub,self.admin)

    def test_duplicate_model_edge_records_are_normalized_without_inventing_sources(self):
        created=self.create('mindmap');pid=created['scope_id']
        connection={'id':'e1','source':'root','target':'child','label':'Checks'}
        model={'nodes':[{'id':'root','data':{'kind':'topic','label':'Motor','source_ids':['BRIEF']}},{'id':'child','data':{'kind':'subtopic','label':'Checks','source_ids':['BRIEF']}},connection], 'edges':[connection]}
        stub=SimpleNamespace(row={'project_id':pid,'payload':{'document_id':created['document_id'],'revision_id':created['revision_id'],'brief':'Motor with a Checks branch.'}},progress=lambda *a:None,check=lambda:None)
        with patch('backend.core.workhub_intelligence.local_ai.llm_json',return_value=model):result=diagrams.generate_job(stub,self.admin)
        self.assertEqual(2,len(result['proposal']['nodes']));self.assertEqual([connection],result['proposal']['edges'])
        self.assertEqual([{'kind':'duplicate_edge_records','count':1}],result['normalizations'])

    def test_information_and_geometry_malformed_inputs_rejected(self):
        created=self.create('mindmap');pid=created['scope_id'];did=created['document_id'];base=pi.get_document(self.admin,pid,did)['revisions'][0]
        for info in ({'approved_by':'invented'}, {'document_date':'not a date'}, {'customer':123}):
            self.request('PUT',f'/projects/{pid}/intelligence/documents/{did}',{'version':base['id'],'content':{**base['content'],'document_info':info}},400)
        bad=json.loads(json.dumps(base['content']));bad['nodes'][0]['width']=float('inf')
        with self.assertRaises(Exception):pi.validate_content('flowchart',bad)

    def test_independent_confirmation_does_not_create_other_documents_or_release_project(self):
        original=self.request('GET','/projects/'+self.project['id'])['project']['stage']
        for kind in ('frd','closure'):
            created=self.create(kind,linked_project_id=self.project['id']);pid=created['scope_id'];control=created['control_id']
            detail=self.request('GET','/document-spaces/'+pid)
            self.request('PUT','/document-spaces/'+pid,{'version':detail['project']['version'],'reviewer_id':self.lead['id']})
            record=service.get_document(self.admin,pid,control);rev=record['revision'];content=rev['content'];content['summary']='Reviewed document content and handover record.'
            if kind=='frd':content['requirements']=[{'id':'FR-001','title':'Documented sequence','acceptance_criteria':'Engineer verifies the supplied sequence.'}]
            self.request('PUT',f'/projects/{pid}/quality/documents/{control}',{'revision_id':rev['id'],'version':rev['version'],'content':content})
            def action(name):
                current=service.get_document(self.admin,pid,control)['revision']
                return self.request('POST',f'/projects/{pid}/quality/documents/{control}/action',{'revision_id':current['id'],'version':current['version'],'action':name})
            action('confirm');action('submit');self.login(self.lead);action('approve');self.login(self.admin)
            with hub.db() as db:self.assertEqual(1,db.execute('SELECT count(*) FROM pi_documents WHERE project_id=?',(pid,)).fetchone()[0])
            self.assertEqual(original,self.request('GET','/projects/'+self.project['id'])['project']['stage'])

    def test_link_change_clears_confirmation_even_when_prefill_is_disabled(self):
        created=self.create('frd');pid=created['scope_id'];control=created['control_id']
        record=service.get_document(self.admin,pid,control);rev=record['revision'];content=rev['content']
        content['requirements']=[{'id':'FR-001','title':'Original draft','acceptance_criteria':'Confirm the saved wording.'}]
        self.request('PUT',f'/projects/{pid}/quality/documents/{control}',{'revision_id':rev['id'],'version':rev['version'],'content':content})
        rev=service.get_document(self.admin,pid,control)['revision']
        self.request('POST',f'/projects/{pid}/quality/documents/{control}/action',{'revision_id':rev['id'],'version':rev['version'],'action':'confirm'})
        confirmed=service.get_document(self.admin,pid,control)['revision'];self.assertTrue(confirmed['confirmed'])
        detail=self.request('GET','/document-spaces/'+pid)
        self.request('PUT','/document-spaces/'+pid,{'version':detail['project']['version'],'linked_project_id':self.project['id'],'autofill':False})
        updated=service.get_document(self.admin,pid,control)['revision'];self.assertFalse(updated['confirmed'])
        self.assertNotEqual(confirmed['content_hash'],updated['content_hash'])
        self.assertEqual(self.project['id'],updated['content']['document_links']['project_id'])


if __name__=='__main__':unittest.main()
