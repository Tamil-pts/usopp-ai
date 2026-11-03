"""Date selection uses inclusive saved dates and respects export reporting scope."""
import unittest
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import store as hub


class ProjectDateExportsTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    setUp=fixture.PortfolioTests.setUp;tearDown=fixture.PortfolioTests.tearDown
    login=fixture.PortfolioTests.login;request=fixture.PortfolioTests.request

    def exported(self,**filters):
        result=self.client.post('/api/workhub/project-exports',json={'format':'json','columns':['title'],**filters})
        self.assertEqual(200,result.status_code,result.text[:500])
        return {r[0] for r in result.json()['rows']}

    def test_inclusive_open_ended_ranges_and_missing_dates(self):
        with hub.db(True) as db:
            db.execute("UPDATE items SET due_date='2025-03-01' WHERE id=?",(self.project['id'],))
            db.execute("UPDATE items SET due_date='2025-03-31' WHERE id=?",(self.other['id'],))
        undated=hub.create(self.admin,{'title':'No dates fixture'})
        april=hub.create(self.admin,{'title':'April fixture','due_date':'2025-04-01'})
        both={self.project['title'],self.other['title']}
        self.assertEqual(both,self.exported(from_date='2025-03-01',to_date='2025-03-31'))
        self.assertEqual({april['title']},self.exported(from_date='2025-04-01'))
        self.assertEqual({self.project['title']},self.exported(to_date='2025-03-01'))
        self.assertEqual(both|{april['title'],undated['title']},self.exported())

    def test_date_basis_and_closure_require_a_closed_project(self):
        with hub.db(True) as db:
            db.execute("UPDATE items SET start_date='2025-03-01',due_date='2025-05-01',stage='released',completed_at='2025-03-31T23:59:59+00:00' WHERE id=?",(self.project['id'],))
            db.execute("UPDATE items SET start_date='2025-04-01',completed_at='2025-03-31T12:00:00+00:00' WHERE id=?",(self.other['id'],))
        for field in ('start_date','completed_at'):
            self.assertEqual({self.project['title']},self.exported(date_field=field,from_date='2025-03-01',to_date='2025-03-31'))
        self.assertEqual(set(),self.exported(date_field='due_date',from_date='2025-03-01',to_date='2025-03-31'))

    def test_custom_date_selection_is_saved_and_scope_is_still_enforced(self):
        p=self.request('POST','/projects',{'title':'Custom delivery fixture','owner_id':self.manager['id'],
            'custom_fields':[{'label':'Actual delivery','type':'date','value':'2025-03-20'}]})
        cat=self.request('GET','/project-exports');field=next(f['id'] for f in cat['date_fields'] if f['label']=='Custom: Actual delivery')
        settings={'date_field':field,'from_date':'2025-03-20','to_date':'2025-03-20','format':'json','columns':['title']}
        self.assertEqual({p['title']},self.exported(**{k:v for k,v in settings.items() if k not in {'format','columns'}}))
        saved=self.request('POST','/project-exports/views',{'name':'Historical date selection','config':settings})
        found=next(v for v in self.request('GET','/project-exports')['views'] if v['id']==saved['id'])
        self.assertEqual(field,found['config']['date_field'])
        self.login(self.outsider)
        self.request('POST','/project-exports',settings,400) # The custom field is outside this user's authorized catalog.

    def test_invalid_date_selection_is_rejected(self):
        for bad in [{'from_date':'2025-04-01','to_date':'2025-03-01'},
                    {'from_date':'2025-02-30'}, {'date_field':'__class__'}, {'date_field':{}}]:
            self.request('POST','/project-exports',{'format':'json','columns':['title'],**bad},400)


if __name__=='__main__':unittest.main()
