"""Portfolio navigation API and calculations, using isolated existing models."""
from contextlib import ExitStack
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app import app
from backend.core import accounts
from backend.core.workhub import store as hub, identity, timestamp
from backend.core import workhub_portfolio as portfolio
from backend.core.workhub_quality import store as quality


class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse a real hash for fixture accounts; these tests do not test hashing.
        cls.fixture_hash = accounts.password_hash('Isolated.Portfolio.2026')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.store = accounts.AccountStore(Path(self.tmp.name) / 'accounts.sqlite3')
        self.stack.enter_context(patch.object(accounts, 'store', self.store))
        self.stack.enter_context(patch.object(hub, 'root', Path(self.tmp.name) / 'workhub'))
        self.stack.enter_context(patch.object(hub, 'ready', False))
        self.stack.enter_context(patch.object(accounts, 'password_hash', return_value=self.fixture_hash))
        self.manager = self.store.register('portfolio_manager', 'Isolated.Portfolio.2026', 'Manager', 'Test')
        self.engineer = self.store.register('portfolio_engineer', 'Isolated.Portfolio.2026', 'Engineer', 'Test')
        self.lead = self.store.register('portfolio_lead', 'Isolated.Portfolio.2026', 'Reviewer', 'Test')
        self.outsider = self.store.register('portfolio_outsider', 'Isolated.Portfolio.2026', 'Engineer', 'Test')
        self.admin = self.store.register('portfolio_admin', 'Isolated.Portfolio.2026', 'Admin', 'Test', role='admin')
        self.today = date.today()
        self.project = hub.create(self.manager, {'title': 'Fixture portfolio project', 'owner_id': self.manager['id'],
            'quality_id': self.lead['id'], 'approver_id': self.lead['id'], 'release_id': self.lead['id'],
            'start_date': (self.today - timedelta(days=20)).isoformat(), 'due_date': (self.today + timedelta(days=10)).isoformat()})
        self.other = hub.create(self.outsider, {'title': 'Unrelated private dashboard scope'})
        self.first = hub.create(self.manager, {'title': 'First milestone', 'owner_id': self.engineer['id'],
            'milestone': True, 'planned_hours': 2, 'start_date': self.today.isoformat(), 'due_date': self.today.isoformat()}, self.project['id'])
        self.last = hub.create(self.manager, {'title': 'Final milestone', 'owner_id': self.engineer['id'],
            'milestone': True, 'planned_hours': 6, 'start_date': (self.today + timedelta(days=5)).isoformat(), 'due_date': (self.today + timedelta(days=5)).isoformat()}, self.project['id'])
        with hub.db(True) as db:
            db.execute("UPDATE items SET stage='development_completed' WHERE id=?", (self.first['id'],))
        self.client = TestClient(app)
        self.login(self.admin)

    def tearDown(self):
        self.client.close()
        portfolio.READY.discard(str(hub.root.resolve()))
        self.stack.close()
        self.tmp.cleanup()

    def login(self, user):
        self.client.cookies.clear()
        self.client.cookies.set(accounts.COOKIE, self.store.new_session(user['id']))

    def request(self, method, path, payload=None, expected=200):
        response = self.client.request(method, '/api/workhub' + path, **({'json': payload} if payload is not None else {}))
        self.assertEqual(expected, response.status_code, response.text[:2000])
        return response.json()

    def value(self, user=None, **filters):
        return portfolio.dashboard(user or self.admin, **filters)

    def primary(self, value):
        return next(p for p in value['projects'] if p['id'] == self.project['id'])

    def test_weighted_milestones_and_original_workflow_unchanged(self):
        p = self.primary(self.value())
        self.assertEqual(25, p['progress'])
        self.assertEqual(1, p['completed_milestones'])
        self.assertEqual(2, p['milestone_count'])
        self.assertEqual(p['workflow_progress'], hub.detail(self.project['id'])['project']['progress'])
        with hub.db(True) as db:
            db.execute("UPDATE items SET stage='development_completed' WHERE id=?", (self.last['id'],))
        self.assertEqual(99, self.primary(self.value())['progress'])
        with hub.db(True) as db:
            db.execute("UPDATE items SET stage='released' WHERE id=?", (self.project['id'],))
        p = self.primary(self.value())
        self.assertEqual(100, p['progress'])
        self.assertEqual('Completed', p['health'])

    def test_progress_does_not_imply_health(self):
        with hub.db(True) as db:
            db.execute('UPDATE items SET due_date=?,baseline_due=? WHERE id=?', ((self.today - timedelta(days=1)).isoformat(),) * 2 + (self.project['id'],))
        p = self.primary(self.value())
        self.assertEqual(25, p['progress'])
        self.assertEqual('Delayed', p['health'])
        self.assertGreater(len(p['reasons']), 0)

    def test_missing_plan_is_not_zero_or_on_track(self):
        p = next(p for p in self.value()['projects'] if p['id'] == self.other['id'])
        self.assertIsNone(p['progress'])
        self.assertEqual('Not assessed', p['health'])
        self.assertIsNone(p['planned_progress'])

    def test_overdue_milestone_flags_project_without_overdue_project_date(self):
        with hub.db(True) as db:
            db.execute('UPDATE items SET due_date=?,start_date=? WHERE id=?', ((self.today - timedelta(days=1)).isoformat(),) * 2 + (self.last['id'],))
        p = self.primary(self.value())
        self.assertEqual('Delayed', p['health'])
        self.assertEqual(1, p['overdue_milestones'])
        self.assertEqual(1, self.value()['summary']['overdue_tasks'])

    def test_blocked_and_open_issue_risk(self):
        with hub.db(True) as db:
            db.execute("UPDATE items SET stage='blocked' WHERE id=?", (self.last['id'],))
        p = self.primary(self.value())
        self.assertEqual(1, p['blocked_tasks'])
        self.assertEqual('Blocked', p['health'])
        with hub.db(True) as db:
            db.execute('INSERT INTO issues VALUES(?,?,?,?,?,?,?,?,?)', (identity(), self.project['id'], self.last['id'], 'Recorded issue', self.engineer['id'], self.manager['id'], 'open', timestamp(), timestamp(),))
        self.assertEqual(1, self.primary(self.value())['open_issues'])

    def test_server_role_permissions_and_filter_injection(self):
        self.login(self.engineer)
        v = self.request('GET', '/portfolio?role=engineer')
        self.assertEqual(1, v['summary']['total'])
        self.assertNotIn(self.other['id'], json.dumps(v))
        self.request('GET', '/portfolio?role=management', expected=403)
        self.request('GET', '/portfolio?role=project_manager', expected=403)
        self.request('GET', '/portfolio?role=team_lead', expected=403)
        v = self.request('GET', '/portfolio?role=engineer&project_id=' + self.other['id'])
        self.assertEqual(0, v['summary']['total'])
        v = self.request('GET', "/portfolio?department=%27%20OR%201=1--")
        self.assertEqual(0, v['summary']['total'])

    def test_management_manager_lead_and_engineer_scopes(self):
        self.assertEqual(2, self.value()['summary']['total'])
        self.assertEqual('project_manager', self.value(self.manager)['role'])
        self.assertEqual(1, self.value(self.manager)['summary']['total'])
        self.assertEqual('team_lead', self.value(self.lead)['role'])
        self.assertEqual(1, self.value(self.lead)['summary']['total'])
        self.assertEqual('engineer', self.value(self.engineer)['role'])
        self.assertEqual(1, self.value(self.engineer)['summary']['total'])

    def test_pagination_aggregates_remain_complete(self):
        v = self.request('GET', '/portfolio?page_size=1')
        self.assertEqual(2, v['summary']['total'])
        self.assertEqual(1, len(v['projects']))
        self.assertEqual(2, v['total_projects'])
        self.assertNotEqual(v['projects'][0]['id'], self.request('GET', '/portfolio?page_size=1&page=2')['projects'][0]['id'])
        self.request('GET', '/portfolio?page_size=10000', expected=400)
        self.request('GET', '/portfolio?page=-1', expected=400)

    def test_manager_status_date_filters_and_no_fake_org(self):
        v = self.request('GET', '/portfolio?manager=' + str(self.manager['id']))
        self.assertEqual(1, v['summary']['total'])
        self.assertIsNone(self.primary(v)['department'])
        self.assertEqual([], v['options']['departments'])
        self.assertEqual(1, self.request('GET', '/portfolio?status=active&manager=' + str(self.manager['id']))['summary']['total'])
        self.assertEqual(0, self.request('GET', '/portfolio?from=2099-01-01')['summary']['total'])
        self.request('GET', '/portfolio?from=2026-12-01&to=2026-01-01', expected=400)

    def test_rules_permissions_optimistic_version_and_valid_weights(self):
        self.login(self.manager)
        rule = self.request('GET', '/portfolio/rules?project_id=' + self.project['id'])
        payload = {'project_id': self.project['id'], 'version': rule['version'], 'health': rule['health'], 'milestone_weights': {self.first['id']: 9, self.last['id']: 1}}
        new = self.request('PUT', '/portfolio/rules', payload)
        self.assertEqual(1, new['version'])
        self.assertEqual(90, self.primary(self.value())['progress'])
        self.request('PUT', '/portfolio/rules', payload, expected=409)
        payload.update(version=1, milestone_weights={self.other['id']: 10})
        self.request('PUT', '/portfolio/rules', payload, expected=400)
        self.request('GET', '/portfolio/rules', expected=403)
        self.login(self.outsider)
        self.request('GET', '/portfolio/rules?project_id=' + self.project['id'], expected=403)
        self.request('PUT', '/portfolio/rules', payload, expected=403)

    def test_global_rules_finite_thresholds_and_risk(self):
        rules = self.request('GET', '/portfolio/rules')
        payload = {'version': rules['version'], 'health': {**rules['health'], 'slippage_tolerance': 100, 'minimum_progress': 30}}
        self.request('PUT', '/portfolio/rules', payload)
        self.assertEqual('On track', self.primary(self.value())['health'])
        payload['version'] = 1
        payload['health']['minimum_progress'] = 101
        self.request('PUT', '/portfolio/rules', payload, expected=400)
        payload['health']['minimum_progress'] = float('nan')
        with self.assertRaises(HTTPException):
            portfolio.save_rules(self.admin, payload)

    def test_workload_counts_leaf_tasks_and_personal_scope(self):
        parent = hub.create(self.manager, {'title': 'Parent summary', 'owner_id': self.engineer['id'], 'planned_hours': 100}, self.project['id'])
        hub.create(self.manager, {'title': 'Leaf delivery', 'owner_id': self.engineer['id'], 'parent_id': parent['id'], 'planned_hours': 3}, self.project['id'])
        value = self.value(self.engineer)
        self.assertTrue(all(w['engineer_id'] == self.engineer['id'] for w in value['workload']))
        self.assertEqual(2, sum(w['open_tasks'] for w in value['workload']))
        self.assertEqual(9, sum(w['planned_hours'] for w in value['workload']))
        self.assertTrue(all(e['actor_id'] == self.engineer['id'] for e in value['activity']))

    def test_planned_actual_delivery_uses_only_recorded_dates(self):
        with hub.db(True) as db:
            db.execute("UPDATE items SET stage='released',completed_at=? WHERE id=?", ((self.today + timedelta(days=12)).isoformat() + 'T00:00:00+00:00', self.project['id']))
            db.execute("UPDATE items SET stage='released' WHERE id=?", (self.other['id'],))
        v = self.value()
        self.assertEqual(1, v['summary']['recorded_deliveries'])
        self.assertEqual(0, v['summary']['on_time_deliveries'])
        self.assertEqual(2, self.primary(v)['delivery_variance_days'])

    def document(self, title, controlled=False):
        quality.initialize()
        did, rid, cid = identity(), identity(), identity()
        with hub.db(True) as db:
            db.execute('INSERT INTO pi_documents(id,project_id,kind,title,current_revision,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)', (did, self.project['id'], 'frd' if controlled else 'mom', title, rid, self.manager['id'], timestamp(), timestamp()))
            db.execute('INSERT INTO pi_revisions(id,document_id,number,content,status,reviewer_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)', (rid, did, 1, '{}', 'review', self.lead['id'], self.manager['id'], timestamp()))
            if controlled:
                db.execute('INSERT INTO qc_documents VALUES(?,?,?,?,?,?,?,?)', (cid, self.project['id'], 'frd', did, 'FIXTURE-FRD-001', 1, '{}', timestamp()))
                db.execute('INSERT INTO qc_revisions(id,control_id,number,label,status,reason,owner_id,template_version,template_snapshot,content_hash,reviewer_id,approver_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (rid, cid, 1, 'R00', 'in_review', '', self.manager['id'], '1', '{}', 'fixture', self.lead['id'], self.manager['id'], timestamp()))
        return did, rid

    def test_document_approvals_are_counted_once_and_paginated(self):
        self.document('Review MOM')
        self.document('Review FRD', controlled=True)
        v = self.value(self.lead)
        self.assertEqual(2, v['summary']['pending_approvals'])
        self.assertEqual(2, v['reports']['pending'])
        self.login(self.lead)
        q = self.request('GET', '/portfolio/approvals?documents_only=true&page_size=1')
        self.assertEqual(2, q['total'])
        self.assertEqual(1, len(q['items']))
        self.assertTrue(q['items'][0]['can_review'])
        self.login(self.engineer)
        self.assertEqual(0, self.request('GET', '/portfolio/approvals')['total'])

    def test_existing_project_and_reporting_apis_are_preserved(self):
        before = hub.detail(self.project['id'])['project']
        self.request('GET', '/portfolio')
        after=self.request('GET', '/projects/' + self.project['id'])['project']
        self.assertEqual(before,{k:after[k] for k in before})
        self.assertEqual(4, len(self.request('GET', '/overview')['items']))
        self.assertEqual(200, self.client.get('/api/workhub/reports/json').status_code)

    def test_department_team_filters_use_existing_organization_links(self):
        quality.initialize()
        oid=identity()
        with hub.db(True) as db:
            db.execute('INSERT INTO wh_brand_records VALUES(?,?,?,?,?,?)', ('organization',oid,1,json.dumps({'name':'Fixture org','department':'Engineering','team':'Controls','active':True}),self.admin['id'],timestamp()))
            db.execute('INSERT INTO qc_projects VALUES(?,?,?,?,?,?,?,?)', (self.project['id'],'{}',0,'General',json.dumps({'organization_id':oid}),1,timestamp(),timestamp()))
        value=self.request('GET','/portfolio?department=Engineering&team=Controls')
        self.assertEqual(1,value['summary']['total'])
        self.assertEqual('Controls',self.primary(value)['team_name'])
        self.assertEqual(1,self.request('GET','/portfolio?department=__unassigned')['summary']['total'])

    def test_overdue_phase_dates_affect_health_without_changing_progress(self):
        with hub.db(True) as db:
            db.execute('INSERT INTO project_phases(id,project_id,phase,title,due_date) VALUES(?,?,?,?,?)', (identity(),self.project['id'],'quality','Quality review',(self.today-timedelta(days=1)).isoformat()))
        p=self.primary(self.value())
        self.assertEqual(25,p['progress'])
        self.assertEqual('Delayed',p['health'])
        self.assertIn('1 overdue delivery phase(s)',p['reasons'])


if __name__ == '__main__':
    unittest.main()
