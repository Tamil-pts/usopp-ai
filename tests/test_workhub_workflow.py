"""Configurable project workflows use isolated existing WorkHub records."""
from copy import deepcopy
import json
import unittest
from fastapi import HTTPException
from tests.test_workhub_portfolio import PortfolioTests
from backend.core.workhub import store as hub,identity,timestamp
from backend.core.workhub_quality import configuration,store,authoring,service
from backend.core import workhub_workflow as workflow


class WorkflowTests(unittest.TestCase):
    setUpClass=classmethod(PortfolioTests.setUpClass.__func__)
    setUp=PortfolioTests.setUp
    tearDown=PortfolioTests.tearDown
    login=PortfolioTests.login
    request=PortfolioTests.request

    def rule(self,condition='project_field',parameter='customer',action='start',severity='block'):
        return {'id':identity(),'name':'Required '+parameter,'condition':condition,'parameter':parameter,'action':action,'severity':severity,'enabled':True}

    def procedure(self,steps=True,rules=None):
        profile=deepcopy(configuration.DEFAULT['default_profile']);profile['validation_rules']=rules or []
        profile['workflow_steps']=[{'id':'spec','title':'Prepare requirements','phase':'development','days':2,'planned_hours':4,'milestone':False,'depends_on':[]},
            {'id':'review','title':'Review engineering','phase':'quality','days':1,'planned_hours':2,'milestone':False,'depends_on':['spec']},
            {'id':'handover','title':'Handover milestone','phase':'release','days':1,'planned_hours':1,'milestone':True,'depends_on':['review']}] if steps else []
        return profile

    def save(self,profile):
        value=configuration.get(self.admin);config=deepcopy(value['configuration']);config['project_profiles']['Custom delivery']=profile
        return configuration.save(self.admin,{'version':value['version'],'configuration':config})

    def create(self):
        return self.request('POST','/projects',{'workspace_schema':3,'title':'Custom delivery project','kind':'Custom delivery','owner_id':self.admin['id'],
            'quality_id':self.lead['id'],'release_id':self.lead['id'],'approver_id':self.lead['id'],'assignment_mode':'now','start_date':'2099-01-01'})

    def test_settings_require_admin_and_version_and_publish_catalog(self):
        saved=self.save(self.procedure())
        with self.assertRaises(HTTPException) as conflict:configuration.save(self.admin,{'version':saved['version']-1,'configuration':saved['configuration']})
        self.assertEqual(409,conflict.exception.status_code)
        self.login(self.engineer)
        catalog=self.request('GET','/workflow/catalog');self.assertEqual(3,next(t for t in catalog['templates'] if t['id']=='Custom delivery')['steps'])
        self.assertEqual(403,self.client.get('/api/admin/settings/engineering-quality').status_code)
        self.assertEqual(403,self.client.put('/api/admin/settings/engineering-quality',json={'version':saved['version'],'configuration':saved['configuration']}).status_code)

    def test_template_creates_real_assigned_tasks_dates_dependencies_and_phases(self):
        self.save(self.procedure());p=self.create();result=self.request('GET','/projects/'+p['id']+'/tracking')
        self.assertEqual(3,len(result['tasks']));self.assertEqual([1,1,1],[v['total'] for v in result['phases']])
        tasks={t['title']:t for t in result['tasks']};dev=tasks['Prepare requirements'];review=tasks['Review engineering'];release=tasks['Handover milestone']
        self.assertEqual(('2099-01-01','2099-01-02'),(dev['start_date'],dev['due_date']))
        self.assertEqual([dev['id']],review['dependencies']);self.assertEqual(self.lead['id'],review['owner_id'])
        self.assertEqual(review['owner_id'],release['owner_id']);self.assertEqual(release['start_date'],release['due_date'])
        self.assertEqual('2099-01-04',result['project']['due_date'])
        detail=self.request('GET','/projects/'+p['id']);self.assertTrue(all(phase['start_date'] for phase in detail['phases']))
        portfolio=self.request('GET','/portfolio?project_id='+p['id'])['projects'][0]
        self.assertEqual(3,portfolio['task_count']);self.assertEqual('Custom delivery',portfolio['workflow_name']);self.assertEqual(1,portfolio['milestone_count'])

    def test_custom_blocker_is_enforced_by_the_existing_transition_api(self):
        self.save(self.procedure(False,[self.rule()]));p=self.create()
        self.request('POST','/items/'+p['id']+'/transition',{'action':'start','version':p['version']},409)
        p=self.request('PUT','/items/'+p['id'],{'version':p['version'],'customer':'Recorded customer'})
        p=self.request('POST','/items/'+p['id']+'/transition',{'action':'start','version':p['version']})
        self.assertEqual('development',p['stage'])

    def test_warning_does_not_block_and_is_recorded_in_activity(self):
        self.save(self.procedure(False,[self.rule(severity='warning')]));p=self.create()
        self.request('POST','/items/'+p['id']+'/transition',{'action':'start','version':p['version']})
        tracking=self.request('GET','/projects/'+p['id']+'/tracking')
        self.assertFalse(tracking['checks'][0]['passed']);self.assertTrue(any(e['event']=='workflow_warnings' for e in tracking['events']))

    def test_snapshots_change_only_on_explicit_adoption_and_existing_work_survives(self):
        original=self.save(self.procedure());p=self.create();before=self.request('GET','/projects/'+p['id']+'/tracking')
        first=before['tasks'][0]
        with hub.db(True) as db:db.execute("UPDATE items SET title='Preserved completed work',stage='development_completed' WHERE id=?",(first['id'],))
        profile=self.procedure(rules=[self.rule()]);profile['workflow_steps'].insert(1,{'id':'extra','title':'Additional design check','phase':'development','days':1,'planned_hours':1,'milestone':False,'depends_on':['spec']})
        latest=self.save(profile)
        tracking=self.request('GET','/projects/'+p['id']+'/tracking');self.assertEqual(original['version'],tracking['procedure']['version']);self.assertFalse(tracking['checks'])
        payload={'version':tracking['project']['version'],'settings_version':latest['version'],'template_id':'Custom delivery','reason':'Adopt the additional design check'}
        result=self.request('POST','/projects/'+p['id']+'/workflow',payload)
        self.assertEqual(latest['version'],result['procedure']['version']);self.assertEqual(4,len(result['tasks']));self.assertEqual(1,len(result['checks']))
        task=next(t for t in result['tasks'] if t['id']==first['id']);self.assertEqual('Preserved completed work',task['title']);self.assertEqual('development_completed',task['stage'])
        self.request('POST','/projects/'+p['id']+'/workflow',payload,409)
        payload['version']=result['project']['version'];replayed=self.request('POST','/projects/'+p['id']+'/workflow',payload)
        self.assertEqual(4,len(replayed['tasks']))

    def test_invalid_steps_rules_cycles_and_circular_approvals_are_rejected(self):
        profile=self.procedure();profile['workflow_steps'][0]['depends_on']=['handover']
        with self.assertRaises(HTTPException):self.save(profile)
        profile=self.procedure();profile['workflow_steps'][0]['phase']='release'
        with self.assertRaises(HTTPException):self.save(profile)
        profile=self.procedure(False,[self.rule('source_regex','x')])
        with self.assertRaises(HTTPException):self.save(profile)
        profile=self.procedure(False,[self.rule('document_approved','quality','quality_pass')])
        with self.assertRaises(HTTPException):self.save(profile)
        profile=self.procedure(False,[self.rule('phase_complete','release','start')])
        with self.assertRaises(HTTPException):self.save(profile)

    def test_saved_validation_requires_actual_pass_for_each_source_and_target(self):
        self.save(self.procedure(False,[self.rule('validation_pass','validation')]));p=self.create()
        def insert(iteration,target,summary):
            with hub.db(True) as db:db.execute('INSERT INTO engineering_runs(run_id,project_id,update_id,iteration,kind,test_id,author_id,status,summary,source_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (identity(),p['id'],identity(),iteration,'validation',identity(),self.admin['id'],'completed',json.dumps({**summary,'target':target}),'Same source',timestamp()))
        insert(1,'C70',{'total':2,'failed':1});insert(2,'T30',{'total':2,'failed':0})
        self.assertFalse(self.request('GET','/projects/'+p['id']+'/tracking')['checks'][0]['passed'])
        insert(3,'C70',{'total':2,'failed':0});self.assertTrue(self.request('GET','/projects/'+p['id']+'/tracking')['checks'][0]['passed'])
        insert(4,'T30',{});self.assertFalse(self.request('GET','/projects/'+p['id']+'/tracking')['checks'][0]['passed'])

    def test_current_approved_document_is_required_and_absent_tests_do_not_pass(self):
        self.save(self.procedure(False,[self.rule('document_approved','frd'),self.rule('tests_passed','fat')]))
        p=self.create();draft=authoring.create(self.admin,p['id'],{'stage':'frd'})
        self.assertFalse(self.request('GET','/projects/'+p['id']+'/tracking')['checks'][0]['passed'])
        with hub.db(True) as db:
            d=store.control(db,p['id'],'frd');db.execute("UPDATE qc_revisions SET status='approved' WHERE id=?",(draft['revision_id'],));db.execute("UPDATE pi_revisions SET status='approved' WHERE id=?",(draft['revision_id'],));db.execute('UPDATE pi_documents SET approved_revision=? WHERE id=?',(draft['revision_id'],d['document_id']))
        checks=self.request('GET','/projects/'+p['id']+'/tracking')['checks'];self.assertTrue(checks[0]['passed']);self.assertFalse(checks[1]['passed'])
        service.new_revision(self.admin,p['id'],d['id'],{'revision_id':draft['revision_id'],'reason':'An editable successor'})
        self.assertFalse(self.request('GET','/projects/'+p['id']+'/tracking')['checks'][0]['passed'])

    def test_project_scope_permissions_and_completed_project_protection(self):
        latest=self.save(self.procedure());p=self.create()
        payload={'version':p['version'],'settings_version':latest['version'],'reason':'Apply latest'}
        self.login(self.outsider);self.request('GET','/projects/'+p['id']+'/tracking',expected=403);self.request('POST','/projects/'+p['id']+'/workflow',payload,403)
        self.login(self.lead);self.request('POST','/projects/'+p['id']+'/workflow',payload,403)
        self.login(self.admin)
        with hub.db(True) as db:db.execute("UPDATE items SET stage='released' WHERE id=?",(p['id'],))
        self.request('POST','/projects/'+p['id']+'/workflow',payload,409)

    def test_independent_documents_never_inherit_project_transition_checks(self):
        value=configuration.get(self.admin);config=value['configuration'];config['default_profile']['validation_rules']=[self.rule()]
        configuration.save(self.admin,{'version':value['version'],'configuration':config})
        doc=self.request('POST','/document-spaces',{'stage':'frd','request_id':'independent-with-project-checks'})
        with hub.db() as db:self.assertEqual([],workflow.evaluate(db,hub.item(db,doc['scope_id'])))
        self.request('GET','/projects/'+doc['scope_id']+'/tracking',expected=400)

    def test_tracking_history_is_paginated_and_a_default_plan_is_not_invented(self):
        p=self.request('POST','/projects',{'title':'No custom plan'})
        result=self.request('GET','/projects/'+p['id']+'/tracking');self.assertFalse(result['tasks']);self.assertIsNone(result['assessment']['progress'])
        with hub.db(True) as db:
            item=hub.item(db,p['id'])
            for i in range(65):hub.event(db,item,self.admin,'isolated_tracking_record',{'number':i})
        first=self.request('GET','/projects/'+p['id']+'/tracking');second=self.request('GET','/projects/'+p['id']+'/tracking?event_page=2')
        self.assertEqual(30,len(first['events']));self.assertEqual(30,len(second['events']));self.assertFalse({e['id'] for e in first['events']} & {e['id'] for e in second['events']})

    def test_existing_quality_procedure_adoption_adds_missing_steps_once(self):
        self.save(self.procedure(False));p=self.create();self.save(self.procedure())
        service.rebaseline_policy(self.admin,p['id'],{'reason':'Adopt the project task plan'})
        self.assertEqual(3,len(self.request('GET','/projects/'+p['id']+'/tracking')['tasks']))
        service.rebaseline_policy(self.admin,p['id'],{'reason':'Review the same saved procedure'})
        self.assertEqual(3,len(self.request('GET','/projects/'+p['id']+'/tracking')['tasks']))

    def test_project_validation_rules_are_included_in_quality_readiness(self):
        from backend.core.workhub_quality import checks
        rule=self.rule('project_field','due_date','quality_pass');self.save(self.procedure(False,[rule]));p=self.create()
        with hub.db() as db:report=checks.report(db,hub.item(db,p['id']))
        self.assertTrue(any(b['code']=='workflow:'+rule['id'] and not b['waivable'] for b in report['blockers']))

del PortfolioTests
if __name__=='__main__':unittest.main()
