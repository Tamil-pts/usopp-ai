"""First-use WorkHub dashboard creation must preserve saved designs and account isolation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import unittest
from tests import test_workhub_portfolio as fixture
from backend.core.workhub_dashboards import schema,store,templates


class DefaultDashboardTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PortfolioTests.setUpClass.__func__)
    setUp=fixture.PortfolioTests.setUp;tearDown=fixture.PortfolioTests.tearDown
    login=fixture.PortfolioTests.login;request=fixture.PortfolioTests.request

    def home(self):return self.request('POST','/dashboards/templates/workhub-overview',{'if_default_missing':True})

    def test_default_is_created_once_and_edited_widgets_survive_reopening(self):
        original=self.request('POST','/dashboards',{'configuration':templates.configuration()})
        home=self.home();config=deepcopy(home['configuration'])
        self.assertEqual(8,len(config['widgets']))
        self.assertEqual({'work','projects','approvals','team','actions','milestones','recent','links'},
            {w['overview']['content'] for w in config['widgets']})
        config['widgets'][0]['title']='My responsibilities';config['widgets'][0]['overview']['tone']='purple'
        config['widgets'][4]['overview']['limit']=9;config['layouts']['desktop'][0]['h']=5
        extra=deepcopy(templates.configuration()['widgets'][4]);extra['id']='additional_chart'
        config['widgets'].append(extra)
        saved=self.request('PUT','/dashboards/'+home['id'],{'version':home['version'],'configuration':config})
        reopened=self.home()
        self.assertEqual(saved,reopened)
        self.assertEqual(9,len(reopened['configuration']['widgets']))
        self.assertEqual('purple',reopened['configuration']['widgets'][0]['overview']['tone'])
        self.assertEqual(original['configuration'],self.request('GET','/dashboards/'+original['id'])['configuration'])
        listing=self.request('GET','/dashboards')
        self.assertEqual(home['id'],listing['default_id']);self.assertEqual(2,len(listing['items']))

    def test_shared_dashboard_never_becomes_another_accounts_default(self):
        home=self.home()
        self.request('PUT','/dashboards/'+home['id']+'/sharing',{'version':home['version'],
            'sharing':[{'user_id':self.engineer['id'],'permission':'viewer'}]})
        self.login(self.engineer);own=self.home()
        self.assertNotEqual(home['id'],own['id']);self.assertEqual(self.engineer['id'],own['owner_id'])
        self.assertEqual(own['id'],self.request('GET','/dashboards')['default_id'])
        self.request('PUT','/dashboards/'+home['id'],{'version':2,'configuration':own['configuration']},403)
        self.request('DELETE','/dashboards/'+own['id']+'?version=1')
        recreated=self.home();self.assertNotEqual(own['id'],recreated['id'])
        self.assertEqual('viewer',self.request('GET','/dashboards/'+home['id'])['permission'])
        self.login(self.outsider);self.request('GET','/dashboards/'+home['id'],expected=403)

    def test_concurrent_initialization_and_widget_settings_are_bounded(self):
        store.initialize()
        with ThreadPoolExecutor(max_workers=3) as pool:
            values=list(pool.map(lambda _:store.from_template(self.admin,templates.OVERVIEW_KEY,{'if_default_missing':True}),range(3)))
        self.assertEqual(1,len({v['id'] for v in values}))
        self.assertEqual(1,len(self.request('GET','/dashboards')['items']))
        for field,value in [('content','other-account-private-data'),('tone','url(javascript:alert(1))'),('limit',21)]:
            config=deepcopy(values[0]['configuration']);config['widgets'][0]['overview'][field]=value
            self.request('POST','/dashboards/validate',{'configuration':config},400)
        self.assertEqual(values[0]['configuration'],schema.dashboard(values[0]['configuration']))
