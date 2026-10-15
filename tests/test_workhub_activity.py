from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app import app
from backend.core import accounts, run_history
from backend.core.workhub_activity import summarize_activity


NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def record(identity, when=NOW, user_id=3, kind='validation', status='completed'):
    return {'id': identity, 'kind': kind, 'createdAt': when.isoformat(), 'testId': 'T-' + identity,
            'projectName': 'Machine ' + identity, 'status': status,
            'user': {'id': user_id, 'username': 'engineer-' + str(user_id), 'company': 'Private company'},
            'projectPath': 'private/source/path', 'snapshotPath': 'private/archive/path',
            'summary': {'pass': 99, 'fail': 1}}


class ActivitySummaryTests(unittest.TestCase):
    def test_actual_runs_group_by_day_user_and_tool(self):
        result = summarize_activity([record('a'), record('b', NOW-timedelta(days=1), kind='rules'),
                                     record('c', user_id=4, kind='compare')], now=NOW)
        self.assertEqual(result['totalRuns'], 3)
        self.assertEqual([item['count'] for item in result['daily']][-2:], [1, 2])
        self.assertEqual({item['id']: item['count'] for item in result['users']}, {3: 2, 4: 1})
        self.assertEqual({item['label'] for item in result['tools']}, {'ByteMap', 'LogicScan', 'MatchView'})

    def test_empty_range_has_real_zero_bins_and_no_fabricated_people(self):
        result = summarize_activity([], days=30, now=NOW)
        self.assertEqual(len(result['daily']), 30)
        self.assertEqual(result['totalRuns'], 0)
        self.assertEqual(result['users'], [])
        self.assertEqual(result['recent'], [])

    def test_time_boundaries_invalid_records_and_future_runs(self):
        first = NOW.replace(hour=0)-timedelta(days=6)
        rows = [record('first', first), record('too-old', first-timedelta(seconds=1)),
                record('future', NOW+timedelta(seconds=1)), record('unknown', kind='not-a-run'),
                {**record('legacy-import'), 'legacy': True},
                {**record('bad-date'), 'createdAt': 'not a timestamp'}]
        result = summarize_activity(rows, now=NOW)
        self.assertEqual(result['totalRuns'], 1)
        self.assertEqual(result['daily'][0]['count'], 1)

    def test_status_counts_do_not_become_validation_verdicts_or_leak_source(self):
        result = summarize_activity([record('a', status='failed'), record('b', status='running')], now=NOW)
        self.assertEqual(result['totalRuns'], 2)
        self.assertEqual({row['status'] for row in result['recent']}, {'failed', 'running'})
        for row in result['recent']:
            self.assertNotIn('summary', row)
            self.assertNotIn('projectPath', row)
            self.assertNotIn('snapshotPath', row)
            self.assertNotIn('company', row['user'])
        self.assertNotIn('pass', result)
        self.assertNotIn('fail', result)

    def test_unattributed_runs_are_explicit_and_recent_list_is_bounded(self):
        rows = [{**record(str(i), NOW-timedelta(minutes=i)), 'user': None} for i in range(12)]
        result = summarize_activity(rows, now=NOW)
        self.assertEqual(result['users'][0]['username'], 'User not recorded')
        self.assertEqual(result['users'][0]['count'], 12)
        self.assertEqual(len(result['recent']), 8)
        self.assertIsNone(result['recent'][0]['user'])


class ActivityAccessTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.store = accounts.AccountStore(Path(self.work.name)/'accounts.sqlite3')
        self.accounts = patch.object(accounts, 'store', self.store)
        self.accounts.start()
        self.owner = self.store.register('activity_owner', 'Activity.check.2026', 'Engineer', 'Local test')
        self.other = self.store.register('activity_other', 'Activity.check.2026', 'Engineer', 'Local test')
        now = datetime.now(timezone.utc)-timedelta(seconds=1)
        self.rows = [record('mine', now, self.owner['id']), record('other', now, self.other['id']),
                     {**record('legacy', now), 'user': None}]
        self.history = patch.object(run_history, 'list_records', return_value=self.rows)
        self.history.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.history.stop()
        self.accounts.stop()
        self.work.cleanup()

    def sign_in(self, user_id):
        self.client.cookies.set(accounts.COOKIE, self.store.new_session(user_id))

    def test_regular_user_only_receives_own_activity(self):
        self.sign_in(self.owner['id'])
        response = self.client.get('/api/history/activity?days=7&scope=all&userId=' + str(self.other['id']))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['scope'], 'own')
        self.assertEqual(data['totalRuns'], 1)
        self.assertEqual([row['id'] for row in data['recent']], ['mine'])

    def test_admin_can_see_all_recorded_users_and_unattributed_activity(self):
        self.sign_in(1)
        data = self.client.get('/api/history/activity?days=30').json()
        self.assertEqual(data['scope'], 'all')
        self.assertEqual(data['totalRuns'], 3)
        self.assertEqual(len(data['users']), 3)

    def test_authentication_and_range_validation(self):
        self.assertEqual(self.client.get('/api/history/activity').status_code, 401)
        self.sign_in(self.owner['id'])
        for days in (0, 31, 'wrong'):
            self.assertEqual(self.client.get('/api/history/activity?days=' + str(days)).status_code, 400)


if __name__ == '__main__':
    unittest.main()
