"""MIS hours use saved work dates, review status and authorized scope."""
from tests.test_workhub_portfolio import PortfolioTests as Fixture
from backend.core.workhub import store as hub
import unittest


class MISHoursTests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp;tearDown=Fixture.tearDown
    login=Fixture.login;request=Fixture.request

    def query(self, **extra):
        return self.request('POST','/dashboards/query',{'source':'time_entries',
          'dimensions':[{'field':'date','grain':'week'}],
          'metrics':[{'field':'hours','aggregation':'sum'},{'field':'approved_hours','aggregation':'sum'}],**extra})

    def test_original_dates_and_review_status_are_separate_from_recorded_hours(self):
        a=hub.add_update(self.engineer,self.first['id'],{'body':'Historical fixture','minutes':90,'work_date':'2025-04-07'})
        hub.add_update(self.engineer,self.first['id'],{'body':'Submitted fixture','minutes':45,'work_date':'2025-04-08'})
        hub.time_review(self.lead,a['id'],{'status':'approved','comment':'Reviewed fixture'})
        value=self.query(global_ignored=False) # Unsupported JSON keys cannot alter the source.
        self.assertEqual(2,value['total_records']);self.assertEqual([2.25,1.5],value['totals'])
        self.assertEqual(['2025-04-07'],value['rows'][0]['dimensions'])
        value=self.query(**{'global':{'from':'2025-04-08','to':'2025-04-08'}})
        self.assertEqual([.75,0],value['totals'])

    def test_other_engineers_time_is_not_exposed_by_a_shared_query(self):
        hub.add_update(self.engineer,self.first['id'],{'body':'Managed time','minutes':60})
        hub.add_update(self.outsider,self.other['id'],{'body':'Unrelated time','minutes':120})
        self.login(self.engineer);self.assertEqual([1,0],self.query()['totals'])
        self.login(self.outsider);self.assertEqual([2,0],self.query()['totals'])
        self.login(self.admin);self.assertEqual([3,0],self.query()['totals'])

    def test_samples_and_held_projects_have_explicit_labels(self):
        hub.add_update(self.manager,self.project['id'],{'body':'Sample time','minutes':60})
        with hub.db(True) as db:
            db.execute("UPDATE items SET is_sample=1,exception_status='on_hold' WHERE id=?",(self.project['id'],))
        value=self.query(filters=[{'field':'dataset','op':'eq','value':'Sample'}])
        self.assertEqual([1,0],value['totals'])
        groups=self.request('POST','/dashboards/query',{'source':'projects','dimensions':[{'field':'delivery_group','grain':'value'}]})
        self.assertIn(['On hold'],[r['dimensions'] for r in groups['rows']])


if __name__=='__main__':unittest.main()
