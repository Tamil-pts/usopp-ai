"""Approved project hours and the existing custom dashboard save/query path."""
import csv,io,unittest
from copy import deepcopy
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import store as hub
from backend.core.workhub_dashboards import templates


class DashboardBillingTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    setUp=fixture.PortfolioTests.setUp;tearDown=fixture.PortfolioTests.tearDown
    login=fixture.PortfolioTests.login;request=fixture.PortfolioTests.request

    def time(self,author,item,minutes,status=None,reviewer=None):
        row=hub.add_update(author,item['id'],{'body':'Isolated billing time fixture','minutes':minutes})
        if status:hub.time_review(reviewer or self.lead,row['id'],{'status':status,'comment':'Clarify this entry' if status=='changes_requested' else ''})
        return row

    def hours(self):
        return {r['id']:r for r in self.request('GET','/overview')['items']}

    def test_project_and_task_approved_time_is_counted_once_and_exports_match(self):
        self.time(self.manager,self.project,60,'approved')
        self.time(self.engineer,self.first,90,'approved')
        self.time(self.manager,self.project,180)
        returned=self.time(self.manager,self.project,75,'changes_requested')
        self.time(self.outsider,self.other,90,'approved',self.outsider)
        rows=self.hours()
        self.assertEqual(2.5,rows[self.project['id']]['billing_hours'])
        self.assertEqual(1.5,rows[self.other['id']]['billing_hours'])
        self.assertNotIn('billing_hours',rows[self.first['id']])
        response=self.client.get('/api/workhub/reports/csv');self.assertEqual(200,response.status_code)
        exported=list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
        row=next(r for r in exported if r['Project / task']==self.project['title'])
        self.assertEqual('2.5',row['Billing hours (approved time)'])
        self.assertEqual('',next(r for r in exported if r['Project / task']==self.first['title'])['Billing hours (approved time)'])
        hub.resubmit_time(self.manager,returned['id'],{'minutes':30,'work_date':self.today.isoformat(),'comment':'Corrected activity detail'})
        self.assertEqual(2.5,self.hours()[self.project['id']]['billing_hours'])
        hub.time_review(self.lead,returned['id'],{'status':'approved','comment':''})
        self.assertEqual(3,self.hours()[self.project['id']]['billing_hours'])

    def test_dashboard_sum_average_min_max_use_the_same_unrounded_project_totals(self):
        for _ in range(3):self.time(self.manager,self.project,1,'approved')
        self.time(self.outsider,self.other,2,'approved',self.outsider)
        empty=hub.create(self.manager,{'title':'No approved time'})
        query={'source':'projects','dimensions':[],
          'metrics':[{'field':'billing_hours','aggregation':a} for a in ('sum','avg','min','max')]}
        result=self.request('POST','/dashboards/query',query)
        self.assertEqual(3,result['total_records'])
        for actual,expected in zip(result['totals'],[5/60,5/180,0,3/60]):self.assertAlmostEqual(expected,actual)
        self.assertEqual(0,self.hours()[empty['id']]['billing_hours'])
        by_project=self.request('POST','/dashboards/query',{**query,'global':{'project_id':self.project['id']}})
        self.assertAlmostEqual(3/60,by_project['totals'][0])
        registry=self.request('GET','/dashboards/registry')
        self.assertEqual(['count','distinct','sum','avg','min','max'],registry['sources']['projects']['fields']['billing_hours']['aggregations'])

    def test_custom_comparison_and_responsive_sizes_save_without_replacing_other_dashboards(self):
        config=templates.configuration();config['name']='Billing comparison fixture'
        widget=deepcopy(config['widgets'][0]);widget.update(id='billing_compare',type='combo',title='Billing and planned hours')
        widget['query'].update(source='projects',dimensions=[{'field':'project','grain':'value'}],metrics=[{'field':'billing_hours','aggregation':'sum'},{'field':'hours','aggregation':'sum'}])
        widget['appearance'].update(format='hours',series_types=['bar','line'],secondary_axis=True)
        config['widgets']=[widget];config['layouts']={bp:[{'i':widget['id'],'x':0,'y':0,'w':w,'h':h}] for bp,w,h in [('desktop',9,8),('tablet',8,7),('mobile',4,6)]}
        original=self.request('POST','/dashboards',{'configuration':templates.configuration()})
        created=self.request('POST','/dashboards',{'configuration':config})
        changed=deepcopy(created['configuration']);changed['layouts']['desktop'][0].update(w=12,h=10)
        saved=self.request('PUT','/dashboards/'+created['id'],{'version':created['version'],'configuration':changed})
        loaded=self.request('GET','/dashboards/'+created['id'])
        self.assertEqual(changed,loaded['configuration'])
        self.assertEqual(12,loaded['configuration']['layouts']['desktop'][0]['w'])
        self.assertEqual(templates.configuration(),self.request('GET','/dashboards/'+original['id'])['configuration'])
        self.request('PUT','/dashboards/'+created['id'],{'version':created['version'],'configuration':config},409)
        self.request('PUT','/dashboards/'+created['id']+'/sharing',{'version':saved['version'],'sharing':[{'user_id':self.lead['id'],'permission':'viewer'}]})
        self.login(self.lead);self.assertEqual('viewer',self.request('GET','/dashboards/'+created['id'])['permission'])
        self.request('PUT','/dashboards/'+created['id'],{'version':saved['version'],'configuration':config},403)
        self.login(self.outsider);self.request('GET','/dashboards/'+created['id'],expected=403)
