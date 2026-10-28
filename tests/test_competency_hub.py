"""Self profiles, private insight layouts and explicit engineering attribution."""
import copy
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from tests import test_workhub_praxis as fixtures
from backend.core import workhub_organization as org,workhub_resources as resources,workhub_tool_context as context
from backend.core.workhub import store as hub
from backend.core.workhub_praxis import insights,service,store


class CompetencyHubTests(unittest.TestCase):
    setUp=fixtures.PraxisTests.setUp
    tearDown=fixtures.PraxisTests.tearDown
    unit=fixtures.PraxisTests.unit
    assign=fixtures.PraxisTests.assign
    configure=fixtures.PraxisTests.configure

    def person_profile(self,person):
        return next(u['profile'] for u in org.directory(person)['users'] if u['id']==person['id'])

    def test_employee_can_manage_own_department_team_and_daily_hours(self):
        p=self.person_profile(self.employee)
        saved=org.save_profile(self.employee,self.employee['id'],{**p,'daily_hours':7,'workdays':5,'availability_note':'Available for planned work'})
        self.assertEqual(35,saved['weekly_hours']);self.assertEqual(7,saved['daily_hours'])
        self.assertEqual([self.team['id']],saved['team_ids'])
        with self.assertRaises(HTTPException):org.save_profile(self.employee,self.manager['id'],self.person_profile(self.manager))
        with self.assertRaises(HTTPException):org.save_profile(self.employee,self.employee['id'],{**saved,'manager_id':self.outsider['id']})
        with self.assertRaises(HTTPException):org.save_profile(self.employee,self.employee['id'],{**saved,'managed_team_ids':[self.team['id']]})
        with hub.db() as db:self.assertNotIn(self.outsider['id'],org.managed_people(db,self.employee))

    def test_daily_schedule_validation_and_legacy_weekly_updates(self):
        p=self.person_profile(self.employee)
        for daily in (25,-1,float('nan'),True,'8'):
            with self.assertRaises(HTTPException):org.save_profile(self.employee,self.employee['id'],{**p,'daily_hours':daily})
        saved=org.save_profile(self.admin,self.employee['id'],{**p,'weekly_hours':32})
        self.assertEqual(32,saved['weekly_hours']);self.assertEqual(6.4,saved['daily_hours'])

    def test_availability_comes_from_active_assignments_not_remaining_estimates(self):
        with hub.db() as db:self.assertEqual('Available',org.assignments(db,self.employee['id'])['status'])
        project=hub.create(self.admin,{'title':'Numbered assigned project','owner_id':self.employee['id'],'project_number':'FIX-001'})
        with hub.db() as db:self.assertEqual('Assigned',org.assignments(db,self.employee['id'])['status'])
        data=resources.snapshot(self.admin,project_id=project['id'])
        row=next(r for r in data['resources'] if r['id']==self.employee['id'])
        self.assertEqual('Assigned',row['assignment_status']);self.assertIsNone(row['available_hours'])
        with hub.db(True) as db:db.execute("UPDATE items SET stage='released' WHERE id=?",(project['id'],))
        with hub.db() as db:self.assertEqual('Available',org.assignments(db,self.employee['id'])['status'])

    def test_personal_insights_do_not_change_scores_or_other_users(self):
        own=insights.layout(self.employee);other=insights.layout(self.manager)
        changed=copy.deepcopy(own['widgets']);changed[0].update(title='My delivery view',note='Review project outcomes',value=99)
        saved=insights.save(self.employee,{'version':0,'widgets':changed})
        self.assertEqual(1,saved['version']);self.assertNotIn('value',saved['widgets'][0])
        self.assertEqual(other,insights.layout(self.manager))
        p=service.profile(self.employee,self.employee['id'],'period')
        self.assertIsNone(p['performance_index']);self.assertIsNone(p['competency_index'])
        self.assertIsNone(insights.values(p)['contribution_impact'])
        with self.assertRaises(HTTPException):insights.save(self.employee,{'version':0,'widgets':changed})
        changed[0]['metric']='invented_score'
        with self.assertRaises(HTTPException):insights.save(self.employee,{'version':1,'widgets':changed})

    def test_project_context_is_authorized_explicit_and_captured_once(self):
        project=hub.create(self.admin,{'title':'Assigned test','owner_id':self.employee['id'],'quality_id':self.manager['id'],'project_number':'FIX-002'})
        choice=context.validate(self.employee,project['id'])
        with self.assertRaises(HTTPException):context.validate(self.outsider,project['id'])
        token=context.selection.set(choice)
        try:
            record={};data={};context.capture(data,record)
            self.assertEqual(project['id'],record['workhubProjectId']);self.assertTrue(data['workhubCapture'])
            self.assertEqual(project['project_number'],data['workhubProjectNumber'])
            automatic={'workhubCapture':False};context.capture(automatic);self.assertNotIn('workhubProjectId',automatic)
        finally:context.selection.reset(token)
        choices=context.options(self.employee);self.assertEqual([project['id']],[p['project_id'] for p in choices['projects']])
        self.assertEqual([],context.options(self.outsider)['projects'])
        with hub.db(True) as db:db.execute("UPDATE items SET stage='released' WHERE id=?",(project['id'],))
        with self.assertRaises(HTTPException):context.validate(self.employee,project['id'])

    def test_work_activity_respects_existing_permissions_and_does_not_infer_passes(self):
        from backend.core.workhub_growth import performance
        with patch.object(performance,'profile',side_effect=HTTPException(403,'Private')):
            self.assertFalse(insights.work_activity(self.manager,self.employee['id'])['available'])
        p=service.profile(self.employee,self.employee['id'],'period')
        p['work_activity']={'indicators':{'validation_iterations':8,'on_time_percent':None}}
        values=insights.values(p)
        self.assertEqual(8,values['validation_runs']);self.assertIsNone(values['competency_index']);self.assertIsNone(values['on_time_delivery'])

    def test_completed_run_retains_original_project_when_selection_changes(self):
        from pathlib import Path
        from backend.core import run_history
        root=Path(self.temp.name);first=hub.create(self.admin,{'title':'First run project','owner_id':self.employee['id']})
        second=hub.create(self.admin,{'title':'Second run project','owner_id':self.employee['id']})
        for key in ('RECORDS','SNAPSHOTS','WORK'):
            self.stack.enter_context(patch.object(run_history,key,root/key))
        self.stack.enter_context(patch.object(run_history,'archive_database',lambda *args:None))
        user_token=run_history.current_user.set(self.employee);project_token=context.selection.set(context.validate(self.employee,first['id']))
        try:
            data={'projectName':'Synthetic test fixture','machineDepartment':'Engineering'}
            record=run_history.begin_run('validation',data)
            context.selection.set(context.validate(self.employee,second['id']))
            data.update(summary={'pass':0,'fail':2},runStatus='completed')
            saved=run_history.record_run('validation',data)
            self.assertEqual(first['id'],saved['workhubProjectId'])
            with hub.db() as db:
                captured=dict(db.execute('SELECT * FROM engineering_runs WHERE run_id=?',(record['id'],)).fetchone())
                self.assertEqual(first['id'],captured['project_id']);self.assertEqual(self.employee['id'],captured['author_id'])
                self.assertEqual(1,db.execute('SELECT count(*) FROM engineering_runs').fetchone()[0])
            context.selection.set({'capture':False})
            independent={'projectName':'Independent fixture','machineDepartment':'Engineering'}
            private=run_history.begin_run('compare',independent);run_history.record_run('compare',independent)
            self.assertFalse(private.get('workhubAutoCapture',False))
            with hub.db() as db:self.assertEqual(1,db.execute('SELECT count(*) FROM engineering_runs').fetchone()[0])
            context.selection.set(context.validate(self.employee,second['id']))
            model={'projectName':'Synthetic data validation','machineDepartment':'Engineering','summary':{'passed':2,'failed':1}}
            result=run_history.record_run('data-model',model)
            self.assertEqual(second['id'],result['workhubProjectId'])
            with hub.db() as db:self.assertEqual(2,db.execute('SELECT count(*) FROM engineering_runs').fetchone()[0])
        finally:context.selection.reset(project_token);run_history.current_user.reset(user_token)
