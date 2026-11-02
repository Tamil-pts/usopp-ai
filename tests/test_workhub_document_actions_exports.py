"""Document lifecycle actions and scoped custom project exports with real APIs."""
import csv,io,json,os,unittest
from unittest.mock import patch
from openpyxl import load_workbook
from pypdf import PdfReader
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import store as hub,identity,timestamp
from backend.core.workhub_quality import service
from backend.core.workhub_intelligence import store as pi


class DocumentActionsExportsTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    tearDown=fixture.PortfolioTests.tearDown;login=fixture.PortfolioTests.login;request=fixture.PortfolioTests.request
    def setUp(self):
        fixture.PortfolioTests.setUp(self)
        self.stack.enter_context(patch.dict(os.environ,{'USOPP_PI_WORKER_MODE':'external'}))

    def test_every_document_type_can_be_deleted_without_losing_revisions(self):
        ids=[]
        for kind in ['mom','frd','test','test_report','fat','closure']:
            d=self.request('POST','/document-spaces',{'request_id':identity(),'document_type':kind,'stage':'test' if kind=='test_report' else kind,'title':kind+' deletion fixture'})
            register=self.request('GET','/documents')
            row=next(r for r in register['items'] if r['project_id']==d['scope_id']);ids.append(row['id'])
            self.assertTrue(row['can_edit']);self.assertTrue(row['can_delete'])
            payload={'revision_id':row['current_revision'],'version':row['revision_version'],'reason':'Duplicate test document.'}
            self.request('POST','/documents/'+row['id']+'/delete',{**payload,'revision_id':'stale'},409)
            self.request('POST','/documents/'+row['id']+'/delete',{**payload,'reason':''},400)
            self.request('POST','/documents/'+row['id']+'/delete',payload)
            with hub.db() as db:
                self.assertIsNone(db.execute('SELECT approved_revision FROM pi_documents WHERE id=?',(row['id'],)).fetchone()[0])
                self.assertEqual('archived',db.execute('SELECT status FROM pi_revisions WHERE id=?',(row['current_revision'],)).fetchone()[0])
                self.assertTrue(db.execute('SELECT 1 FROM pi_revisions WHERE document_id=?',(row['id'],)).fetchone())
        self.assertTrue(set(ids).isdisjoint({r['id'] for r in self.request('GET','/documents')['items']}))
        archived=self.request('GET','/documents?status=archived')
        self.assertTrue(set(ids).issubset({r['id'] for r in archived['items']}))

    def test_unauthorized_delete_denied_and_approved_content_retained(self):
        d=self.request('POST','/projects/'+self.project['id']+'/quality/drafts',{'stage':'frd'})
        rec=service.get_document(self.admin,self.project['id'],d['control_id']);rid=rec['revision']['id'];docid=rec['document']['document_id']
        with hub.db(True) as db:
            before=db.execute('SELECT content FROM pi_revisions WHERE id=?',(rid,)).fetchone()[0]
            db.execute("UPDATE pi_revisions SET status='approved' WHERE id=?",(rid,))
            db.execute("UPDATE qc_revisions SET status='approved' WHERE id=?",(rid,))
            db.execute('UPDATE pi_documents SET approved_revision=? WHERE id=?',(rid,docid))
        payload={'revision_id':rid,'version':rec['revision']['version'],'reason':'Document replaced after review.'}
        self.login(self.outsider);self.request('POST','/documents/'+docid+'/delete',payload,403)
        self.login(self.admin);self.request('POST','/documents/'+docid+'/delete',{**payload,'version':0},409)
        self.request('POST','/documents/'+docid+'/delete',payload)
        with hub.db() as db:
            self.assertEqual(before,db.execute('SELECT content FROM pi_revisions WHERE id=?',(rid,)).fetchone()[0])
            self.assertTrue(db.execute("SELECT 1 FROM qc_audit WHERE action='document_deleted' AND revision_id=?",(rid,)).fetchone())
        self.assertFalse(service.get_document(self.admin,self.project['id'],d['control_id'])['can_delete'])

    def test_custom_fields_roundtrip_validation_and_template(self):
        custom=[{'label':'Machine serial','type':'text','value':'MC-781','required':True},{'label':'Budget','type':'number','value':42.5}]
        p=self.request('POST','/projects',{'title':'Custom columns fixture','custom_fields':custom})
        row=self.request('GET','/projects/'+p['id'])['project'];self.assertEqual('MC-781',row['custom_fields'][0]['value'])
        field_id=row['custom_fields'][0]['id'];self.assertTrue(field_id.startswith('custom_'))
        overview=next(r for r in self.request('GET','/overview')['items'] if r['id']==p['id']);self.assertEqual(row['custom_fields'],overview['custom_fields'])
        self.request('PUT','/items/'+p['id'],{'version':row['version'],'custom_fields':[{'label':'Machine serial','type':'text','value':'MC-782'}]})
        changed=self.request('GET','/projects/'+p['id'])['project'];self.assertEqual(field_id,changed['custom_fields'][0]['id'])
        self.request('PUT','/items/'+p['id'],{'version':row['version'],'custom_fields':[]},409)
        for bad in [[{'label':'Blank required','required':True}],custom+[custom[0]],[{'label':'Bad number','type':'number','value':True}]]:
            self.request('POST','/projects',{'title':'Invalid fields rollback','custom_fields':bad},400)
        templates=self.request('GET','/project-templates')['items'][0]['content']
        saved=self.request('POST','/project-templates',{'name':'Reusable field definitions','content':{**templates,'custom_fields':custom}})
        item=next(r for r in self.request('GET','/project-templates')['items'] if r['id']==saved['id']);self.assertEqual(field_id,item['content']['custom_fields'][0]['id'])
        self.login(self.outsider);self.request('PUT','/items/'+p['id'],{'version':changed['version'],'custom_fields':[]},403)

    def test_exports_filters_custom_columns_approved_hours_and_private_history(self):
        self.login(self.admin)
        custom=[{'label':'Contract reference','type':'text','value':'=HYPERLINK("unsafe")'}]
        self.request('PUT','/items/'+self.project['id'],{'version':self.project['version'],'custom_fields':custom})
        a=hub.add_update(self.engineer,self.first['id'],{'body':'Approved work','minutes':90});hub.time_review(self.lead,a['id'],{'status':'approved','comment':''})
        hub.add_update(self.engineer,self.first['id'],{'body':'Pending work','minutes':120})
        catalog=self.request('GET','/project-exports');cid=next(c['id'] for c in catalog['columns'] if c['label']=='Contract reference')
        cfg={'format':'xlsx','columns':['title',cid,'billing','tasks'],'project':self.project['id'],'member':self.engineer['id'],'status':'ongoing','files':True}
        response=self.client.post('/api/workhub/project-exports',json=cfg);self.assertEqual(200,response.status_code,response.text[:300] if response.status_code!=200 else '')
        ws=load_workbook(io.BytesIO(response.content),data_only=False).active;rows=list(ws.values)
        self.assertEqual(2,len(rows));self.assertEqual('Billing Hours (Approved Time)',rows[0][2]);self.assertEqual(1.5,rows[1][2]);self.assertTrue(rows[1][1].startswith("'="))
        self.assertEqual('s',ws.cell(2,2).data_type)
        for fmt in ['csv','pdf','json']:
            r=self.client.post('/api/workhub/project-exports',json={**cfg,'format':fmt});self.assertEqual(200,r.status_code)
            if fmt=='csv':self.assertEqual('1.5',list(csv.reader(io.StringIO(r.text.lstrip('\ufeff'))))[1][2])
            if fmt=='pdf':self.assertIn(self.project['title'],' '.join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages))
        view=self.request('POST','/project-exports/views',{'name':'Team progress','config':cfg})
        self.assertEqual(4,len(self.request('GET','/project-exports')['history']))
        self.login(self.outsider);other=self.request('GET','/project-exports');self.assertEqual([],other['views']);self.assertEqual([],other['history'])
        self.request('DELETE','/project-exports/views/'+view['id'],expected=404)
        self.request('POST','/project-exports',{**cfg,'role':'management'},403)
        self.request('POST','/project-exports',{**cfg,'columns':['title','billing'],'member':''},403)
        self.login(self.admin)
        empty=self.client.post('/api/workhub/project-exports',json={**cfg,'format':'json','status':'completed'});self.assertEqual([],empty.json()['rows'])

    def test_team_filter_does_not_double_count_shared_projects(self):
        self.request('GET','/project-exports')
        with hub.db(True) as db:
            db.execute("INSERT INTO wh_org_units(id,kind,name,updated_at) VALUES('export_team','team','Controls team',?)",(timestamp(),))
            for uid in [self.engineer['id'],self.manager['id']]:db.execute('INSERT INTO wh_org_members(team_id,user_id) VALUES(?,?)',('export_team',uid))
        r=self.client.post('/api/workhub/project-exports',json={'format':'json','columns':['title'],'team':'export_team'})
        self.assertEqual(200,r.status_code,r.text);self.assertEqual(1,len(r.json()['rows']))

