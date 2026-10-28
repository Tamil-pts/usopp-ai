"""WorkHub growth workflows exercised with isolated accounts, files and databases."""
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app import app
from backend.core import accounts, persistent_store
from backend.core.workhub import store as hub
from backend.core.workhub_growth import store, collector, passport


class WorkHubGrowthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.patches = ExitStack()
        self.account_store = accounts.AccountStore(self.root/'accounts.sqlite3')
        self.patches.enter_context(patch.object(accounts, 'store', self.account_store))
        self.patches.enter_context(patch.object(hub, 'root', self.root/'workhub'))
        self.patches.enter_context(patch.object(hub, 'ready', False))
        self.patches.enter_context(patch.object(persistent_store, 'DATABASE', self.root/'application.sqlite3'))
        self.patches.enter_context(patch.object(persistent_store, 'READY', False))
        self.engineer = self.account_store.register('growth_engineer', 'Isolated.Check.2026', 'Engineer', 'Test')
        self.manager = self.account_store.register('growth_manager', 'Isolated.Check.2026', 'Manager', 'Test')
        self.outsider = self.account_store.register('growth_outsider', 'Isolated.Check.2026', 'Engineer', 'Test')
        self.client = TestClient(app)
        self.sign_in(self.manager)
        self.project = self.request('POST', '/api/workhub/projects', {
            'title': 'Isolated control panel', 'kind': 'Electrical / CAD',
            'owner_id': self.engineer['id'], 'quality_id': self.manager['id'],
            'approver_id': self.manager['id'], 'release_id': self.manager['id'],
        })
        self.task = self.request('POST', '/api/workhub/projects/'+self.project['id']+'/tasks', {
            'title': 'Verify circuit design', 'owner_id': self.engineer['id'],
        })
        self.sign_in(self.engineer)

    def tearDown(self):
        self.client.close()
        store.READY.discard(str(hub.root.resolve()))
        self.patches.close()
        self.directory.cleanup()

    def sign_in(self, user):
        self.client.cookies.clear()
        self.client.cookies.set(accounts.COOKIE, self.account_store.new_session(user['id']))

    def request(self, method, path, payload=None, expected=200):
        response = self.client.request(method, path, **({'json': payload} if payload is not None else {}))
        self.assertEqual(expected, response.status_code, response.text[:2000])
        return response.json()

    def article(self, category='troubleshooting'):
        answers = {q[0]: 'Recorded '+q[0]+' with applicability limits and evidence.' for q in passport.QUESTIONS[category]}
        return self.request('POST', '/api/workhub/growth/articles', {
            'title': 'Resolved inverter trip through terminal inspection', 'category': category,
            'answers': answers, 'project_id': self.project['id'], 'task_id': self.task['id'],
        })

    def review(self, value, action, **extra):
        return self.request('POST', '/api/workhub/growth/articles/'+value['id']+'/review', {
            'revision_id': value['revision_id'], 'action': action,
            'comment': 'Checked the recorded method, result and limits.', **extra,
        })

    def publish(self, value):
        self.review(value, 'submit', reviewer_id=self.manager['id'])
        self.sign_in(self.manager)
        self.review(value, 'approve', capabilities=['problem_solving', 'work_quality'])
        self.review(value, 'publish')
        self.sign_in(self.engineer)

    def profile(self):
        return self.request('GET', '/api/workhub/growth/performance/'+str(self.engineer['id']))

    def test_metadata_individual_team_and_profile_scope(self):
        metadata = self.request('GET', '/api/workhub/growth/metadata')
        self.assertEqual(5, len(metadata['categories']))
        self.assertIn(self.manager['id'], {u['id'] for u in metadata['reviewers'][self.project['id']]})
        self.assertNotIn(self.engineer['id'], {u['id'] for u in metadata['reviewers'][self.project['id']]})
        self.assertEqual(1, self.profile()['indicators']['assigned_projects'])
        # Existing project owners are managers even when their account role is user.
        self.request('GET', '/api/workhub/growth/team')
        self.sign_in(self.outsider)
        self.request('GET', '/api/workhub/growth/team', expected=403)
        self.sign_in(self.manager)
        team = self.request('GET', '/api/workhub/growth/team')
        self.assertIn(self.engineer['id'], {p['person']['id'] for p in team['people']})
        self.request('GET', '/api/workhub/growth/performance/'+str(self.outsider['id']), expected=403)

    def test_all_five_categories_generate_useful_structured_drafts(self):
        for category in passport.QUESTIONS:
            with self.subTest(category=category):
                value = self.article(category)
                detail = self.request('GET', '/api/workhub/growth/articles/'+value['id'])
                self.assertEqual('draft', detail['revision']['status'])
                self.assertEqual(category, detail['revision']['category'])
                self.assertIn('Recorded', detail['revision']['body'])

    def test_independent_review_publication_search_and_capability_credit(self):
        value = self.article()
        self.assertEqual(0, self.request('GET', '/api/workhub/growth/library')['total'])
        self.review(value, 'submit', reviewer_id=self.manager['id'])
        self.request('POST', '/api/workhub/growth/articles/'+value['id']+'/review', {
            'revision_id': value['revision_id'], 'action': 'approve', 'comment': 'Self review',
        }, expected=403)
        self.sign_in(self.manager)
        self.assertEqual(1, len(self.request('GET', '/api/workhub/growth/workspace')['article_reviews']))
        self.review(value, 'approve', capabilities=['problem_solving'])
        self.assertEqual(0, self.request('GET', '/api/workhub/growth/library')['total'])
        self.review(value, 'publish')
        self.sign_in(self.engineer)
        found = self.request('GET', '/api/workhub/growth/library?q=inverter')
        self.assertEqual(1, found['total'])
        self.assertEqual(value['revision_id'], found['items'][0]['revision_id'])
        indicators = self.profile()
        self.assertEqual(1, indicators['indicators']['published_contributions'])
        self.assertEqual(1, next(c for c in indicators['capabilities'] if c['id']=='knowledge_sharing')['verified_records'])
        answer = self.request('POST', '/api/workhub/growth/assistant', {'question':'inverter trip'})
        self.assertEqual(value['revision_id'], answer['sources'][0]['revision_id'])

    def test_published_article_keeps_draft_and_attachment_private(self):
        value = self.article()
        response = self.client.post('/api/workhub/growth/files/article/'+value['id'], files={'file':('evidence.txt', b'Checked terminal continuity')})
        self.assertEqual(200, response.status_code, response.text)
        public_file = response.json()['id']
        detail = self.request('GET', '/api/workhub/growth/articles/'+value['id'])
        revised = self.request('PUT', '/api/workhub/growth/articles/'+value['id'], {
            'version':value['revision_id'], 'category':detail['revision']['category'],
            'answers':detail['revision']['answers'], 'title':detail['revision']['title'],
            'project_id':self.project['id'], 'task_id':self.task['id'], 'file_ids':[public_file],
        })
        self.publish(revised)
        secret = self.client.post('/api/workhub/growth/files/article/'+value['id'], files={'file':('draft.txt',b'Private draft content')}).json()['id']
        draft = self.request('PUT', '/api/workhub/growth/articles/'+value['id'], {
            'version':revised['revision_id'], 'category':detail['revision']['category'],
            'answers':detail['revision']['answers'], 'title':'Private unsubmitted revision',
            'project_id':self.project['id'], 'task_id':self.task['id'], 'file_ids':[secret],
        })
        self.sign_in(self.outsider)
        visible = self.request('GET', '/api/workhub/growth/articles/'+value['id'])
        self.assertEqual(revised['revision_id'], visible['revision']['id'])
        self.request('GET', '/api/workhub/growth/articles/'+value['id']+'?revision_id='+draft['revision_id'], expected=403)
        self.assertEqual(200, self.client.get('/api/workhub/growth/files/'+public_file).status_code)
        self.assertEqual(403, self.client.get('/api/workhub/growth/files/'+secret).status_code)

    def test_manual_evidence_requires_review_and_retains_verified_revision(self):
        payload = {'project_id':self.project['id'], 'task_id':self.task['id'], 'content':{
            'title':'Circuit review', 'description':'Compared terminal labels with wiring diagram.',
            'outcome':'All terminal labels agree.', 'verification_method':'Inspect marked diagram.',
            'activity':'Electrical / circuit design', 'capabilities':['work_quality'],
        }}
        value = self.request('POST','/api/workhub/growth/evidence',payload)
        self.assertEqual(0,self.profile()['indicators']['verified_evidence'])
        self.request('POST','/api/workhub/growth/evidence/'+value['id']+'/review',{
            'revision_id':value['revision_id'],'action':'submit','reviewer_id':self.manager['id'],
        })
        self.sign_in(self.manager)
        self.request('POST','/api/workhub/growth/evidence/'+value['id']+'/review',{
            'revision_id':value['revision_id'],'action':'approve','comment':'Verified terminal map.',
            'capabilities':['work_quality'],
        })
        self.sign_in(self.engineer)
        self.assertEqual(1,self.profile()['indicators']['verified_evidence'])
        self.request('PUT','/api/workhub/growth/evidence/'+value['id'],{**payload,'version':value['revision_id']})
        profile = self.profile()
        self.assertEqual(value['revision_id'],profile['proofs'][0]['revision_id'])

    def test_native_scores_task_links_and_iterations_are_neutral(self):
        now = datetime.now(timezone.utc).isoformat()
        with hub.db(True) as db:
            for iteration in range(1,5):
                run_id='isolated-run-'+str(iteration);update_id='isolated-update-'+str(iteration)
                reference=json.dumps([{'id':run_id}])
                db.execute("INSERT INTO updates(id,project_id,item_id,author_id,body,work_date,minutes,file_ids,run_ids,created_at) VALUES(?,?,?,?,?,?,0,'[]',?,?)",(update_id,self.project['id'],self.task['id'],self.engineer['id'],'Run evidence',now[:10],reference,now))
                db.execute('INSERT INTO engineering_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(run_id,self.project['id'],update_id,iteration,'validation','Audit',self.engineer['id'],'completed',json.dumps({'pass':iteration,'fail':5-iteration,'score':80+iteration}),'source.apj',now,now))
        profile=self.profile()
        self.assertEqual(4,profile['indicators']['validation_iterations'])
        self.assertEqual(0,profile['indicators']['verified_evidence'])
        self.assertFalse(profile['methodology']['iteration_penalty'])
        self.assertFalse(profile['methodology']['bug_discovery_penalty'])
        self.assertEqual(84,profile['validation_results'][0]['scores'][0]['value'])
        self.assertTrue(all(e['task_id']==self.task['id'] for e in profile['events'] if e['source_type']=='run'))

    def test_rejected_submission_stays_out_of_search(self):
        value=self.article();self.review(value,'submit',reviewer_id=self.manager['id'])
        self.sign_in(self.manager);self.review(value,'reject')
        self.assertEqual(0,self.request('GET','/api/workhub/growth/library')['total'])

    def test_existing_archive_is_captured_without_guessing_project_or_sharing_private_result(self):
        now=datetime.now(timezone.utc).isoformat()
        record={'id':'existing-private-run','kind':'validation','createdAt':now,'completedAt':now,
                'user':self.engineer,'projectName':self.project['title'],'status':'completed',
                'summary':{'passed':90,'failed':10,'complianceScore':90}}
        persistent_store.archive_run(record,{'findings':['Original private result']})
        profile=self.profile()
        event=next(e for e in profile['events'] if e['source_id']==record['id'])
        self.assertIsNone(event['project_id'])
        self.assertIsNone(event['task_id'])
        self.assertEqual(90,profile['validation_results'][0]['scores'][0]['value'])
        self.assertEqual(1,profile['indicators']['validation_iterations'])
        self.request('GET','/api/workhub/growth/events/'+event['id']+'/result')
        self.sign_in(self.manager)
        managed=self.request('GET','/api/workhub/growth/performance/'+str(self.engineer['id']))
        self.assertEqual(0,managed['indicators']['validation_iterations'])
        self.request('GET','/api/workhub/growth/events/'+event['id']+'/result',expected=403)
        self.sign_in(self.engineer)
        evidence=self.request('POST','/api/workhub/growth/evidence',{
            'project_id':self.project['id'],'task_id':self.task['id'],'content':{
                'title':'Explicit archive attribution','description':'The archive supports this task.',
                'outcome':'Recorded validation findings.','verification_method':'Inspect the native result.',
                'source_event_id':event['id'],'capabilities':['work_quality']}})
        self.request('POST','/api/workhub/growth/evidence/'+evidence['id']+'/review',{
            'revision_id':evidence['revision_id'],'action':'submit','reviewer_id':self.manager['id']})
        self.sign_in(self.manager)
        self.request('GET','/api/workhub/growth/events/'+event['id']+'/result')
        self.sign_in(self.outsider)
        self.request('GET','/api/workhub/growth/events/'+event['id']+'/result',expected=403)

    def test_manual_reviewers_do_not_receive_unsubmitted_revisions(self):
        payload={'project_id':self.project['id'],'content':{'title':'Reviewed note','description':'Evidence description',
                 'outcome':'Result','verification_method':'Inspect evidence'}}
        value=self.request('POST','/api/workhub/growth/evidence',payload)
        self.request('POST','/api/workhub/growth/evidence/'+value['id']+'/review',{
            'revision_id':value['revision_id'],'action':'submit','reviewer_id':self.manager['id']})
        self.sign_in(self.manager)
        self.request('POST','/api/workhub/growth/evidence/'+value['id']+'/review',{
            'revision_id':value['revision_id'],'action':'approve','comment':'Inspected evidence','capabilities':['execution']})
        self.sign_in(self.engineer)
        self.request('PUT','/api/workhub/growth/evidence/'+value['id'],{**payload,'version':value['revision_id'],
            'content':{**payload['content'],'description':'Unsubmitted private revision'}})
        self.sign_in(self.manager)
        detail=self.request('GET','/api/workhub/growth/evidence/'+value['id'])
        self.assertEqual([value['revision_id']],[r['id'] for r in detail['revisions']])

    def test_health_reports_matching_current_interface_and_api(self):
        from backend.api import system
        # Exercise the health contract using an isolated checksummed UI fixture.
        # Publication integrity is verified separately against the real build.
        root=self.root/'health-fixture';assets=root/'dist/assets';assets.mkdir(parents=True)
        entry=b'/* Isolated health contract fixture */';(assets/'fixture.js').write_bytes(entry)
        (root/'dist/build-info.json').write_text(json.dumps({'version':system.VERSION,'entryFile':'assets/fixture.js','entrySha256':hashlib.sha256(entry).hexdigest()}))
        with patch.object(system,'RESOURCE_ROOT',root):health=self.request('GET','/api/health')
        self.assertEqual('ok',health['status'])
        self.assertEqual(health['version'],health['frontendBuild']['version'])
        self.assertTrue(health['frontendBuild']['matches'])
        self.assertTrue(health['frontendBuild']['integrity'])
        self.assertEqual(health['apiVersion'],health['uiVersion'])
        self.assertTrue(health['capabilities']['workhubPerformanceCapability'])
        self.assertTrue(health['capabilities']['contributionPassport'])

    def test_history_pagination_filters_and_issue_resolution(self):
        for index in range(55):
            issue=self.request('POST','/api/workhub/projects/'+self.project['id']+'/issues',{
                'title':'Observed circuit condition '+str(index),'item_id':self.task['id'],'owner_id':self.engineer['id']})
        self.request('PUT','/api/workhub/issues/'+issue['id'],{'status':'resolved'})
        first=self.request('GET','/api/workhub/growth/events?person_id='+str(self.engineer['id'])+'&kind=issues')
        second=self.request('GET','/api/workhub/growth/events?person_id='+str(self.engineer['id'])+'&kind=issues&page=2')
        self.assertEqual(56,first['total']);self.assertEqual(50,len(first['items']));self.assertEqual(6,len(second['items']))
        self.assertFalse({r['id'] for r in first['items']}&{r['id'] for r in second['items']})
        self.assertEqual(1,self.profile()['indicators']['issues_resolved'])
        self.sign_in(self.outsider)
        self.request('GET','/api/workhub/growth/events?person_id='+str(self.engineer['id']),expected=403)


if __name__=='__main__':unittest.main()
