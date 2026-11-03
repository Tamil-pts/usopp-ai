"""Projects presentation reuses saved dashboards and restricts queries to filtered IDs."""
from copy import deepcopy
import unittest
from tests import test_workhub_portfolio as fixture
from backend.core.workhub import store as hub
from backend.core.workhub_dashboards import schema, templates


class DashboardScopeTests(unittest.TestCase):
    setUpClass = classmethod(fixture.PortfolioTests.setUpClass.__func__)
    setUp = fixture.PortfolioTests.setUp
    tearDown = fixture.PortfolioTests.tearDown
    login = fixture.PortfolioTests.login
    request = fixture.PortfolioTests.request

    def query(self, source='projects', **extra):
        return self.request('POST', '/dashboards/query', {
            'source': source, 'dimensions': [],
            'metrics': [{'field': 'id', 'aggregation': 'count'}], **extra})

    def test_filtered_scope_intersects_saved_filters_and_never_expands_empty_selection(self):
        selected = {'project_ids': [self.project['id']]}
        self.assertEqual(1, self.query(**{'global': selected})['total_records'])
        self.assertEqual(2, self.query('tasks', **{'global': selected})['total_records'])
        self.assertEqual(0, self.query(**{'global': {'project_ids': []}})['total_records'])
        self.assertEqual([0], self.query(**{'global': {'project_ids': []}})['totals'])
        self.assertEqual(0, self.query('tasks', **{'global': {'project_ids': []}})['total_records'])
        self.assertEqual(0, self.query(**{'global': {**selected, 'project_id': self.other['id']}})['total_records'])
        self.assertEqual(0, self.query(filters=[{'field': 'status', 'op': 'eq', 'value': 'released'}],
                                      **{'global': selected})['total_records'])

    def test_scope_cannot_expand_existing_private_time_permissions(self):
        hub.add_update(self.engineer, self.first['id'], {'body': 'Authorized activity', 'minutes': 60})
        hub.add_update(self.outsider, self.other['id'], {'body': 'Private activity', 'minutes': 90})
        self.login(self.engineer)
        result = self.query('time_entries', **{'global': {'project_ids': [self.project['id'], self.other['id']]}})
        self.assertEqual(1, result['total_records'])
        self.assertEqual(0, self.query('time_entries', **{'global': {'project_ids': [self.other['id']]}})['total_records'])

    def test_scope_validation_and_unsupported_snapshot_are_explicit(self):
        for ids in ('all', [None], [''], ['a'] * 10001):
            self.request('POST', '/dashboards/query', {'global': {'project_ids': ids}}, 400)
        self.assertEqual(['a'], schema.global_filters({'project_ids': ['a', 'a']})['project_ids'])
        self.assertNotIn('project_ids', schema.global_filters({}))
        self.request('POST', '/dashboards/query', {'source': 'capabilities', 'global': {'project_ids': []}}, 422)

    def test_project_template_cards_charts_and_responsive_design_survive_save(self):
        catalog = self.request('GET', '/dashboards/templates')['items']
        self.assertIn(templates.PROJECTS_KEY, {row['id'] for row in catalog})
        created = self.request('POST', '/dashboards/templates/' + templates.PROJECTS_KEY, {})
        config = deepcopy(created['configuration'])
        self.assertEqual(4, sum(w['type'] == 'kpi' for w in config['widgets']))
        self.assertEqual({'bar', 'donut'}, {w['type'] for w in config['widgets'] if w['type'] != 'kpi'})
        # Filter selection belongs to the live page; it is never persisted into this template.
        self.assertNotIn('project_ids', config['filters'])
        config['name'] = 'Custom Projects presentation'
        config['widgets'][0]['title'] = 'Filtered project total'
        config['layouts']['desktop'][0].update(w=4, h=5)
        config = schema.dashboard(config)  # Existing grid settlement moves neighbors out of resized cards.
        saved = self.request('PUT', '/dashboards/' + created['id'], {
            'version': created['version'], 'configuration': config})
        self.assertEqual(config, self.request('GET', '/dashboards/' + saved['id'])['configuration'])
        for bp in schema.COLS:
            self.assertEqual({w['id'] for w in config['widgets']}, {r['i'] for r in config['layouts'][bp]})
        self.request('PUT', '/dashboards/' + saved['id'], {
            'version': created['version'], 'configuration': config}, 409)
        self.login(self.outsider)
        self.request('GET', '/dashboards/' + saved['id'], expected=403)
