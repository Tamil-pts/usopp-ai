"""Created documents retain their number through save and each export path."""
import os,unittest
from urllib.parse import unquote
from unittest.mock import patch
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import identity
from backend.core.workhub_quality import service
from backend.core.workhub_document_filename import filename
from backend.core.workhub_intelligence import store as pi,exports,jobs,resources


class DocumentFilenameTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    tearDown=fixture.PortfolioTests.tearDown;login=fixture.PortfolioTests.login;request=fixture.PortfolioTests.request
    def setUp(self):
        fixture.PortfolioTests.setUp(self)
        self.stack.enter_context(patch.dict(os.environ,{'USOPP_PI_WORKER_MODE':'external'}))

    def create(self,kind,request_id=None):
        return self.request('POST','/document-spaces',{'stage':'test' if kind=='test_report' else kind,'document_type':kind,'request_id':request_id or identity()})

    def test_all_created_document_types_export_using_their_issued_number(self):
        numbers=set()
        for kind in ('mom','frd','corrections','test','test_report','fat','quality','closure','flowchart','mindmap'):
            with self.subTest(kind=kind):
                created=self.create(kind);scope=created['scope_id'];details=self.request('GET','/document-spaces/'+scope)
                if created.get('control_id'):
                    record=service.get_document(self.admin,scope,created['control_id']);document=record['document'];revision=record['revision'];path=f'/projects/{scope}/quality/documents/{document["id"]}'
                    self.assertEqual('test' if kind=='test_report' else kind,details['initial_document'])
                else:
                    record=pi.get_document(self.admin,scope,created['document_id']);document=record['document'];revision=record['revisions'][0];path=f'/projects/{scope}/intelligence/documents/{document["id"]}'
                    self.assertEqual('native:'+document['id'],details['initial_document'])
                number=details['document_number'];self.assertTrue(number);self.assertNotIn(number,numbers);numbers.add(number)
                self.assertEqual(document['number'],number)
                for format in ('json','pdf','docx'):
                    response=self.client.get('/api/workhub'+path+'/export/'+format,params={'revision_id':revision['id']})
                    self.assertEqual(200,response.status_code,response.text[:500] if response.status_code!=200 else '')
                    header=unquote(response.headers['content-disposition'].split("filename*=UTF-8''",1)[1])
                    self.assertEqual(filename(document,revision,format),header);self.assertTrue(header.startswith(number+'-'))

    def test_saving_completed_frd_and_retrying_creation_keep_the_same_number(self):
        token=identity();created=self.create('frd',token);scope=created['scope_id'];control=created['control_id'];record=service.get_document(self.admin,scope,control);revision=record['revision'];number=record['document']['number']
        content={**revision['content'],'summary':'Complete draft for review.','requirements':[{'id':'FR-001','title':'Saved requirement','acceptance_criteria':'Engineer verifies the supplied behavior.'}]}
        self.request('PUT',f'/projects/{scope}/quality/documents/{control}',{'revision_id':revision['id'],'version':revision['version'],'content':content})
        retried=self.create('frd',token);self.assertEqual(scope,retried['scope_id'])
        saved=service.get_document(self.admin,scope,control);self.assertEqual(number,saved['document']['number']);self.assertEqual('Complete draft for review.',saved['revision']['content']['summary'])
        self.assertEqual(number,self.request('GET','/document-spaces/'+scope)['document_number'])

    def test_queued_native_exports_use_numbered_names(self):
        for kind in ('mom','flowchart','mindmap'):
            created=self.create(kind);pid=created['scope_id'];doc=pi.get_document(self.admin,pid,created['document_id'])
            key=jobs.enqueue(self.admin,pid,'export',{'document_id':doc['document']['id'],'revision_id':doc['revisions'][0]['id'],'format':'json'})['id']
            job=jobs.claim();self.assertEqual(key,job.row['id'])
            token=resources.CURRENT_JOB.set(job)
            try:result=exports.process(job,self.admin)
            finally:resources.CURRENT_JOB.reset(token)
            jobs.finish(job,'completed',result)
            result,path=exports.download(self.admin,pid,key)
            self.assertTrue(path.is_file())
            self.assertEqual(filename(doc['document'],doc['revisions'][0],'json'),result['filename'])

    def test_numbered_filenames_are_portable_and_cannot_inject_headers(self):
        name=filename({'number':'PTPL/FRD:2026\\003\r\nX: value','id':'f'*32},{'label':'R01'},'pdf')
        self.assertNotIn('/',name);self.assertNotIn('\\',name);self.assertNotIn('\r',name);self.assertNotIn('\n',name);self.assertTrue(name.endswith('-R01.pdf'))


if __name__=='__main__':unittest.main()
