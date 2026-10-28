"""Isolated organization, resource and confidential Praxis contracts."""
from contextlib import ExitStack
from io import BytesIO
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from openpyxl import load_workbook
from backend.core import accounts,workhub_organization as org,workhub_resources as resources
from backend.core.workhub import store as hub
from backend.core.workhub_praxis import store,service,scoring,reports


class PraxisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.stack=ExitStack();root=Path(self.temp.name)
        self.stack.enter_context(patch.object(accounts,'store',accounts.AccountStore(root/'accounts.sqlite3')))
        self.stack.enter_context(patch.object(hub,'root',root/'workhub'));self.stack.enter_context(patch.object(hub,'ready',False))
        self.admin=next(u for u in accounts.store.list_users() if u['username']=='Admin')
        self.employee=accounts.store.register('finance_employee','Fixture.Password.2026','Accounts analyst','Fixture')
        self.manager=accounts.store.register('finance_manager','Fixture.Password.2026','Finance manager','Fixture')
        self.outsider=accounts.store.register('other_employee','Fixture.Password.2026','Operations','Fixture')
        self.department=self.unit('department','Finance')
        self.role=self.unit('role','Accounts analyst',department_id=self.department['id'])
        self.team=self.unit('team','Finance group',department_id=self.department['id'],member_ids=[self.employee['id'],self.manager['id']],manager_ids=[self.manager['id']])
        self.assign(self.employee,self.department['id'],self.role['id'],self.manager['id'])
        self.assign(self.manager,self.department['id'],self.role['id'],None)
        self.config=self.configure()

    def tearDown(self):self.stack.close();self.temp.cleanup()

    def unit(self,kind,name,**extra):return org.save_unit(self.admin,{'kind':kind,'name':name,'active':True,'version':0,**extra})

    def assign(self,person,department='',role='',manager=None):
        directory=org.directory(self.admin);previous=next(u['profile'] for u in directory['users'] if u['id']==person['id'])
        return org.save_profile(self.admin,person['id'],{**previous,'department_id':department,'role_id':role,'manager_id':manager})

    def configure(self):
        competencies=[{'id':'c'+str(i),'name':name,'category':'Financial practice','department_id':self.department['id'],'description':'Role-specific professional competency','criteria':'Reviewed work against the documented rubric','review_frequency_days':90,'active':True} for i,name in enumerate(['Accounting','Planning','Reporting'],1)]
        model={'id':'finance_model','name':'Finance model','active':True,'department_id':self.department['id'],'role_id':self.role['id'],'description':'Finance responsibilities','method':'weighted_mean',
               'competencies':[{'id':'b'+str(i),'competency_id':'c'+str(i),'required_level':4,'weight':2 if i==2 else 1} for i in range(1,4)],
               'performance':[{'id':'delivery','name':'Deliverable quality','criteria':'Reviewed accounting deliverables','weight':3},{'id':'goals','name':'Goal achievement','criteria':'Agreed role-specific objectives','weight':1}]}
        return store.save_configuration(self.admin,{'version':0,'content':{'competencies':competencies,'templates':[model],'periods':[{'id':'period','name':'October 2026','start':'2026-10-01','end':'2026-10-31','active':True}]}})

    def draft(self,**change):
        payload={'subject_id':self.employee['id'],'period_id':'period','template_id':'finance_model','reviewer_id':self.manager['id'],'version':0,
                 'content':{'summary':'Supported finance work','competencies':{'c1':{'level':3},'c2':{'level':4},'c3':{'level':2}},'performance':{'delivery':{'value':80},'goals':{'value':60}}},**change}
        return service.save_assessment(self.employee,payload)

    def submit(self,draft):
        return service.review(self.employee,draft['assessment']['id'],{'version':draft['assessment']['version'],'revision_id':draft['revision']['id'],'action':'submit'})

    def approve(self,draft):
        submitted=self.submit(draft)
        return service.review(self.manager,submitted['assessment']['id'],{'version':submitted['assessment']['version'],'revision_id':submitted['revision']['id'],'action':'approve','comment':'Verified the linked work against the role rubric.'})

    def test_missing_data_is_not_a_fabricated_zero(self):
        p=service.profile(self.employee,self.employee['id'],'period')
        self.assertIsNone(p['performance_index']);self.assertIsNone(p['competency_index'])
        self.assertEqual('Not Assessed',p['performance_status']);self.assertEqual(0,p['competencies_assessed'])
        self.assertTrue(all(c['current'] is None and c['gap'] is None for c in p['competencies']))

    def test_approved_indices_are_separate_weighted_and_frozen(self):
        draft=self.draft();self.assertIsNone(service.profile(self.employee,self.employee['id'],'period')['performance_index'])
        self.approve(draft)
        p=service.profile(self.employee,self.employee['id'],'period')
        self.assertEqual(75,p['performance_index']);self.assertEqual(65,p['competency_index']);self.assertEqual(3,p['competencies_assessed'])
        changed=copy.deepcopy(self.config['content']);changed['templates'][0]['method']='minimum'
        store.save_configuration(self.admin,{'version':1,'content':changed})
        self.assertEqual(75,service.profile(self.employee,self.employee['id'],'period')['performance_index'])
        self.assertEqual(1,len(service.profile(self.employee,self.employee['id'],'period')['history']))

    def test_confidentiality_independent_review_and_no_self_promotion(self):
        with self.assertRaises(HTTPException) as e:service.profile(self.outsider,self.employee['id'],'period')
        self.assertEqual(403,e.exception.status_code)
        with self.assertRaises(HTTPException):org.save_unit(self.manager,{'version':0,'kind':'team','name':'Unauthorized'})
        with self.assertRaises(HTTPException):self.draft(reviewer_id=self.employee['id'])
        draft=self.submit(self.draft())
        with self.assertRaises(HTTPException):service.review(self.employee,draft['assessment']['id'],{'version':draft['assessment']['version'],'revision_id':draft['revision']['id'],'action':'approve','comment':'Self approval'})
        self.assertEqual([self.employee['id'],self.manager['id']],sorted(service.metadata(self.manager)['subject_ids']))

    def test_concurrent_updates_and_configuration_history(self):
        draft=self.draft()
        with self.assertRaises(HTTPException) as e:service.save_assessment(self.employee,{'version':0},draft['assessment']['id'])
        self.assertEqual(409,e.exception.status_code)
        content=copy.deepcopy(self.config['content']);content['competencies']=[]
        with self.assertRaises(HTTPException):store.save_configuration(self.admin,{'version':1,'content':content})
        with self.assertRaises(HTTPException):store.save_configuration(self.admin,{'version':0,'content':self.config['content']})

    def test_missing_measurements_and_not_applicable_have_no_penalty(self):
        model=self.config['content']['templates'][0]
        result=scoring.calculate(model,{'performance':{'delivery':{'value':80}}},{c['id']:c for c in self.config['content']['competencies']})
        self.assertIsNone(result['performance_index']);self.assertEqual('Insufficient Data',result['performance_status'])
        result=scoring.calculate(model,{'performance':{'delivery':{'value':80},'goals':{'not_applicable':True}}},{})
        self.assertEqual(80,result['performance_index'])
        self.assertEqual(60,scoring.weighted([(80,3),(60,1)],'minimum'))
        self.assertAlmostEqual((80**3*60)**.25,scoring.weighted([(80,3),(60,1)],'weighted_geometric'),places=2)

    def test_reports_share_calculations_and_scope(self):
        self.approve(self.draft());value=reports.data(self.employee,'individual',self.employee['id'],'period')
        workbook=load_workbook(BytesIO(reports.excel(value)),read_only=True,data_only=True)
        self.assertEqual(75,workbook['Summary'].cell(5,4).value);self.assertEqual(65,workbook['Summary'].cell(5,5).value)
        self.assertIn('Methodology',workbook.sheetnames);workbook.close()
        self.assertTrue(reports.pdf(value).startswith(b'%PDF'))
        with self.assertRaises(HTTPException):reports.data(self.employee,'team',self.employee['id'],'period')

    def test_resource_capacity_includes_other_projects_and_unknowns(self):
        p1=hub.create(self.admin,{'title':'Accounting delivery','owner_id':self.employee['id'],'quality_id':self.manager['id'],'approver_id':self.admin['id'],'release_id':self.admin['id'],'planning_method':'custom','generate_plan_tasks':False})
        p2=hub.create(self.admin,{'title':'Other delivery','owner_id':self.employee['id'],'quality_id':self.manager['id'],'approver_id':self.admin['id'],'release_id':self.admin['id'],'planning_method':'custom','generate_plan_tasks':False})
        for project,hours in [(p1,20),(p2,30)]:hub.create(self.admin,{'title':'Scheduled work','owner_id':self.employee['id'],'start_date':'2026-10-26','due_date':'2026-10-30','planned_hours':hours},project['id'])
        result=resources.snapshot(self.admin,'2026-10-26','2026-10-30',p1['id']);row=next(p for p in result['resources'] if p['id']==self.employee['id'])
        self.assertEqual(40,row['capacity_hours']);self.assertEqual(50,row['allocated_hours']);self.assertEqual('Overallocated',row['status']);self.assertEqual(1,len(row['tasks']))
        hub.create(self.admin,{'title':'Needs an estimate','owner_id':self.employee['id']},p1['id'])
        row=next(p for p in resources.snapshot(self.admin,'2026-10-26','2026-10-30')['resources'] if p['id']==self.employee['id'])
        self.assertIsNone(row['available_hours']);self.assertEqual(1,row['unplanned_tasks'])

    def test_team_membership_profiles_and_audit_preserve_accounts(self):
        before=accounts.store.get_user(self.employee['id']) if hasattr(accounts.store,'get_user') else next(u for u in accounts.store.list_users() if u['id']==self.employee['id'])
        directory=org.directory(self.admin);p=next(u['profile'] for u in directory['users'] if u['id']==self.employee['id'])
        self.assertIn(self.team['id'],p['team_ids'])
        with self.assertRaises(HTTPException):org.save_profile(self.outsider,self.employee['id'],p)
        updated=org.save_profile(self.admin,self.employee['id'],{**p,'weekly_hours':32,'availability':'blocked','unavailable_until':'2026-10-30','availability_note':'Waiting for project access'})
        self.assertEqual(32,updated['weekly_hours'])
        outsider_profile=next(u['profile'] for u in org.directory(self.outsider)['users'] if u['id']==self.employee['id'])
        self.assertEqual('',outsider_profile['availability_note'])
        after=next(u for u in accounts.store.list_users() if u['id']==self.employee['id'])
        self.assertEqual(before['role'],after['role']);self.assertTrue(after['active'])
        with hub.db() as db:self.assertGreater(db.execute('SELECT count(*) FROM wh_org_audit').fetchone()[0],0)

    def test_preparer_cannot_select_self_as_independent_reviewer(self):
        with self.assertRaises(HTTPException):service.save_assessment(self.manager,{'subject_id':self.employee['id'],'period_id':'period','template_id':'finance_model','reviewer_id':self.manager['id'],'version':0,'content':{}})
        self.assertTrue(service.metadata(self.admin)['projects']==[])

    def test_managers_can_configure_only_managed_department_models(self):
        content=copy.deepcopy(self.config['content']);content['templates'][0]['performance'][0]['weight']=4
        saved=store.save_configuration(self.manager,{'version':1,'content':content});self.assertEqual(2,saved['version'])
        changed=copy.deepcopy(saved['content']);changed['periods'][0]['name']='Company-wide edit'
        with self.assertRaises(HTTPException):store.save_configuration(self.manager,{'version':2,'content':changed})
        changed=copy.deepcopy(saved['content']);changed['competencies'][0]['department_id']=''
        with self.assertRaises(HTTPException):store.save_configuration(self.manager,{'version':2,'content':changed})

    def test_revision_corrections_keep_last_approval_and_development_separate(self):
        approved=self.approve(self.draft());key=approved['assessment']['id'];content=copy.deepcopy(approved['revision']['content']);content['performance']['delivery']['value']=100
        updated=service.save_assessment(self.employee,{'version':approved['assessment']['version'],'content':content},key)
        self.assertEqual(75,service.profile(self.employee,self.employee['id'],'period')['performance_index'])
        submitted=self.submit(updated)
        changes=service.review(self.manager,key,{'version':submitted['assessment']['version'],'revision_id':submitted['revision']['id'],'action':'request_changes','comment':'Clarify the measurement basis.'})
        self.assertEqual('changes_requested',changes['assessment']['status'])
        goal=service.save_development(self.employee,{'version':0,'title':'Financial reporting training','competency_id':'c1','target_level':4,'status':'completed'})
        profile=service.profile(self.employee,self.employee['id'],'period');self.assertEqual(100,profile['development_progress']);self.assertEqual(65,profile['competency_index'])
        with self.assertRaises(HTTPException):service.save_development(self.outsider,{'version':1,'title':'Unauthorized edit'},goal['id'])

    def test_report_types_scope_reviewer_and_filterable_headers(self):
        self.approve(self.draft())
        for kind in reports.TYPES:
            value=reports.data(self.manager,kind,self.employee['id'],'period',self.department['id'],self.team['id'])
            self.assertTrue(reports.pdf(value).startswith(b'%PDF'))
            workbook=load_workbook(BytesIO(reports.excel(value)))
            self.assertTrue(workbook['Summary'].auto_filter.ref.startswith('A4:'));self.assertEqual('finance_manager',workbook['Summary'].cell(5,8).value)
            self.assertIn('Finance',[c.value for c in workbook['Summary'][5]]);workbook.close()

    def test_invalid_values_and_reporting_cycles_are_rejected(self):
        with self.assertRaises(HTTPException):org.save_unit(self.admin,{'kind':[],'name':'Invalid'})
        directory=org.directory(self.admin);p=next(u['profile'] for u in directory['users'] if u['id']==self.manager['id'])
        with self.assertRaises(HTTPException):org.save_profile(self.admin,self.manager['id'],{**p,'manager_id':self.employee['id']})
        content=copy.deepcopy(self.config['content']);content['templates'][0]['performance'][0]['weight']=float('nan')
        with self.assertRaises(HTTPException):store.save_configuration(self.admin,{'version':1,'content':content})

    def test_overdue_tasks_and_dependencies_do_not_make_resources_free(self):
        p=hub.create(self.admin,{'title':'Resource schedule','owner_id':self.employee['id']})
        blocked=hub.create(self.admin,{'title':'Overdue unresolved work','owner_id':self.employee['id'],'start_date':'2026-10-01','due_date':'2026-10-10','planned_hours':8},p['id'])
        hub.create(self.admin,{'title':'Waiting for prerequisite','owner_id':self.employee['id'],'start_date':'2026-10-26','due_date':'2026-10-30','planned_hours':8,'dependencies':[blocked['id']]},p['id'])
        row=next(r for r in resources.snapshot(self.admin,'2026-10-26','2026-10-30')['resources'] if r['id']==self.employee['id'])
        self.assertIsNone(row['available_hours']);self.assertEqual(1,row['blocked_tasks']);self.assertEqual(1,row['unplanned_tasks'])

    def test_team_and_profile_membership_edits_detect_stale_forms(self):
        p=next(u['profile'] for u in org.directory(self.admin)['users'] if u['id']==self.employee['id'])
        org.save_unit(self.admin,{**self.team,'active':True,'member_ids':[self.manager['id']],'manager_ids':[self.manager['id']]},self.team['id'])
        with self.assertRaises(HTTPException) as error:org.save_profile(self.admin,self.employee['id'],p)
        self.assertEqual(409,error.exception.status_code)

    def test_private_document_references_follow_current_reader_access(self):
        from backend.core import workhub_document_spaces as spaces
        created=spaces.create(self.employee,{'stage':'frd','title':'Private reviewed finance specification'})
        key=created['scope_id']
        with hub.db() as db:doc=db.execute('SELECT id FROM pi_documents WHERE project_id=?',(key,)).fetchone()[0]
        with self.assertRaises(HTTPException):self.draft(content={'references':[{'kind':'document','id':doc}],'competencies':{'c1':{'level':3}}})
        spaces.update(self.employee,key,{'version':1,'reviewer_id':self.manager['id']})
        approved=self.approve(self.draft(content={'references':[{'kind':'document','id':doc}],'competencies':{'c1':{'level':3}}}))
        self.assertEqual(1,len(service.profile(self.manager,self.employee['id'],'period')['competencies'][0]['references']))
        spaces.update(self.employee,key,{'version':2,'reviewer_id':None})
        p=service.profile(self.manager,self.employee['id'],'period');self.assertEqual([],p['competencies'][0]['references']);self.assertEqual([],p['history'][0]['competencies'][0]['references'])
        self.assertEqual([],service.assessment(self.manager,approved['assessment']['id'])['revision']['content']['references'])

    def test_unplanned_projects_and_supporting_roles_keep_capacity_unknown(self):
        p=hub.create(self.admin,{'title':'Unplanned responsibility','owner_id':self.employee['id']})
        row=next(r for r in resources.snapshot(self.admin,'2026-10-26','2026-10-30')['resources'] if r['id']==self.employee['id'])
        self.assertIsNone(row['available_hours']);self.assertEqual('project',row['tasks'][0]['type'])
        task=hub.create(self.admin,{'title':'Shared work','owner_id':self.employee['id'],'planned_hours':8,'start_date':'2026-10-26','due_date':'2026-10-30'},p['id'])
        with hub.db(True) as db:db.execute('UPDATE items SET supporting_ids=? WHERE id=?',('['+str(self.manager['id'])+']',task['id']))
        row=next(r for r in resources.snapshot(self.admin,'2026-10-26','2026-10-30')['resources'] if r['id']==self.manager['id'])
        self.assertIsNone(row['available_hours']);self.assertEqual('supporting_ids',row['tasks'][0]['responsibility'])


if __name__=='__main__':unittest.main()
