"""Project deletion permissions, concurrency and recovery in an isolated store."""
import json
import unittest
from unittest.mock import patch
from tests.test_workhub_portfolio import PortfolioTests
from backend.core.workhub import store as hub
from backend.core.workhub_quality import store as quality
from backend.core.workhub import identity,timestamp

class DeletionTests(unittest.TestCase):
    setUpClass = classmethod(PortfolioTests.setUpClass.__func__)
    setUp = PortfolioTests.setUp
    tearDown = PortfolioTests.tearDown
    login = PortfolioTests.login
    request = PortfolioTests.request

    def test_admin_only_version_and_exact_confirmation(self):
        p=hub.detail(self.project['id'])['project'];payload={'version':p['version'],'title':p['title']}
        self.login(self.manager)
        self.request('DELETE','/projects/'+p['id'],payload,403)
        self.login(self.admin)
        self.request('DELETE','/projects/'+p['id'],{**payload,'version':0},409)
        self.request('DELETE','/projects/'+p['id'],{**payload,'title':'wrong'},400)
        self.assertFalse((hub.root/'deleted-projects').exists())

    def test_project_rows_removed_archive_and_unrelated_documents_retained(self):
        from backend.core.workhub_quality import authoring
        from backend.core.workhub_document_spaces import create
        authoring.create(self.manager,self.project['id'],{'stage':'frd'})
        scope=create(self.admin,{'title':'Independent retained FRD','stage':'frd','reviewer_id':self.lead['id'],'linked_project_id':self.project['id']})
        with hub.db() as db:
            p=hub.item(db,self.project['id'])
            numbers=[tuple(r) for r in db.execute('SELECT * FROM qc_sequences')]
        result=self.request('DELETE','/projects/'+p['id'],{'version':p['version'],'title':p['title']})
        archive=json.loads((hub.root/'deleted-projects'/result['archive_name']).read_text(encoding='utf8'))
        self.assertEqual(3,len(archive['rows']['items']))
        self.assertEqual(1,len(archive['rows']['qc_documents']))
        self.request('GET','/projects/'+p['id'],expected=404)
        self.assertEqual(self.other['id'],self.request('GET','/overview')['items'][0]['id'])
        with hub.db() as db:
            self.assertEqual(numbers,[tuple(r) for r in db.execute('SELECT * FROM qc_sequences')])
            self.assertIsNone(db.execute('SELECT linked_project_id FROM wh_document_spaces WHERE id=?',(scope['scope_id'],)).fetchone()[0])
            self.assertTrue(db.execute("SELECT 1 FROM qc_audit WHERE project_id=? AND action='admin_project_deleted'",(p['id'],)).fetchone())
            self.assertEqual(1,db.execute('SELECT count(*) FROM qc_documents').fetchone()[0])

    def test_knowledge_and_file_bytes_survive_and_active_jobs_block(self):
        from backend.core.workhub_growth import store as growth
        from backend.core.workhub_intelligence import jobs
        from backend.core.workhub_intelligence.documents import generated_file
        from backend.core.workhub_files import blob_path
        growth.initialize()
        key=self.project['id'];article=identity();manual=identity()
        with hub.db(True) as db:
            for table,ident in [('cp_articles',article),('pc_manual',manual)]:
                db.execute('INSERT INTO '+table+'(id,author_id,project_id,task_id,created_at,updated_at) VALUES(?,?,?,?,?,?)',(ident,self.manager['id'],key,self.first['id'],timestamp(),timestamp()))
        file=generated_file(self.manager,key,'retained-sample.txt',b'fixture bytes retained after deletion')
        job=jobs.enqueue(self.manager,key,'q_generate',{'stage':'frd'})
        p=hub.detail(key)['project'];payload={'version':p['version'],'title':p['title']}
        self.request('DELETE','/projects/'+key,payload,409)
        with hub.db(True) as db:db.execute("UPDATE pi_jobs SET status='cancelled' WHERE id=?",(job['id'],))
        result=self.request('DELETE','/projects/'+key,payload)
        self.assertTrue(blob_path(file['sha256']).exists())
        with hub.db() as db:
            for table,ident in [('cp_articles',article),('pc_manual',manual)]:
                self.assertEqual((None,None),tuple(db.execute('SELECT project_id,task_id FROM '+table+' WHERE id=?',(ident,)).fetchone()))
        archive=json.loads((hub.root/'deleted-projects'/result['archive_name']).read_text(encoding='utf8'))
        self.assertEqual(file['sha256'],archive['rows']['files'][0]['sha256'])

    def test_archive_failure_keeps_project_and_retry_is_safe(self):
        p=hub.detail(self.project['id'])['project'];payload={'version':p['version'],'title':p['title']}
        with patch('backend.core.workhub_deletion.os.fsync',side_effect=OSError('Fixture disk failure')):
            with self.assertRaises(OSError):self.request('DELETE','/projects/'+p['id'],payload)
        self.assertEqual(p['id'],self.request('GET','/projects/'+p['id'])['project']['id'])
        self.assertTrue(self.request('DELETE','/projects/'+p['id'],payload)['deleted'])

    def test_overview_counts_pending_report_decisions_once(self):
        from backend.core.workhub_intelligence import store as intelligence
        d=intelligence.save_document(self.manager,self.project['id'],{'kind':'note','title':'Review count fixture','content':{'summary':'Fixture'}})
        doc,r=d['document'],d['revision']
        intelligence.review(self.manager,self.project['id'],doc['id'],{'action':'submit','revision_id':r['id'],'reviewer_id':self.lead['id']})
        self.assertEqual(1,self.request('GET','/overview')['summary']['pending_reviews'])
        intelligence.review(self.lead,self.project['id'],doc['id'],{'action':'request_changes','revision_id':r['id'],'comment':'Fixture changes requested.'})
        self.assertEqual(0,self.request('GET','/overview')['summary']['pending_reviews'])
