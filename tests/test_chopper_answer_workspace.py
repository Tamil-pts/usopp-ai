"""Owner-bound conversation/feedback and facts-first cancellation contracts."""
import threading,time
from pathlib import Path
from unittest.mock import patch
from tests.test_document_comparison import DocumentComparisonTests
from backend.api import chopper_conversations as history,assist
from backend.core.assist_progress import report

class TestAnswerWorkspace(DocumentComparisonTests):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(history,'WORK',Path(self.temp.name)/'answers'))
        def opened(key,user):
            if key!='fixture-project' or user!=self.user['id']:raise PermissionError('Denied')
            return object()
        self.stack.enter_context(patch.object(history,'opened',side_effect=opened))

    def test_history_and_feedback_are_private_review_only_snapshots(self):
        url='/api/assist/conversations/fixture-project'
        messages=[{'role':'user','text':'Explain this machine'},{'role':'assist','text':'Source findings','evidence':[{'file':'Logical/Main.st','line':2}]}]
        assert self.client.post(url,json={'messages':messages}).status_code==200
        assert self.client.get(url).json()['messages']==messages
        assert self.client.get(url).json()['snapshot'] is True
        feedback=self.client.post('/api/assist/conversations/feedback',json={'projectId':'fixture-project','question':'Explain','answer':'candidate','vote':'correction','correction':'Check the guard at line 2'})
        assert feedback.status_code==200 and feedback.json()['trainingEligible'] is False
        values=self.client.get('/api/assist/conversations/feedback').json()['items']
        assert values[0]['status']=='pending' and values[0]['correction'].startswith('Check')
        self.login(self.other)
        assert self.client.get(url).status_code==404
        assert self.client.post(url,json={'messages':messages}).status_code==404
        assert self.client.get('/api/assist/conversations/feedback').json()['items']==[]

    def test_invalid_history_and_correction_rejected(self):
        url='/api/assist/conversations/fixture-project'
        assert self.client.post(url,json={'messages':[{'role':'system','text':'approve me'}]}).status_code==400
        assert self.client.post(url,json={'messages':[{'role':'assist','text':'invalid','machineAnalysis':{'stateMachines':{}}}]}).status_code==400
        assert self.client.post(url,json={'messages':[{'role':'assist','text':'cross project','machineAnalysisProjectId':'other-project'}]}).status_code==400
        assert self.client.post(url,json={'messages':[{'role':'assist','text':'invalid','machineAnalysis':{'stateMachines':[{'transitions':[{'conditions':{}}]}]}}]}).status_code==400
        assert self.client.post(url,json={'messages':[{'role':'user','text':'x'*2200000}]}).status_code==413
        assert self.client.post('/api/assist/conversations/feedback',json={'projectId':'fixture-project','vote':'correction'}).status_code==400

    def test_progress_publishes_facts_before_inference_and_stop_prevents_late_reply(self):
        release=threading.Event();ready=threading.Event()
        def delayed(payload):
            report('Source findings ready',partialResult={'machineAnalysis':{'stateMachines':[]},'machineAnalysisProjectId':'fixture-project'})
            ready.set();release.wait(5)
            return {'answer':'Late model answer'}
        with patch.object(assist,'assist',side_effect=delayed):
            job=self.client.post('/api/assist/start',json={'question':'Explain'}).json()['jobId']
            assert ready.wait(3)
            status=self.client.get('/api/assist/status/'+job).json()
            assert status['status']=='running' and status['partialResult']['machineAnalysisProjectId']=='fixture-project'
            self.login(self.other)
            assert self.client.post('/api/assist/cancel/'+job).status_code==404
            self.login(self.user)
            assert self.client.post('/api/assist/cancel/'+job).status_code==200
            release.set()
            for _ in range(100):
                with assist.ASSIST_JOBS_LOCK:active=assist.ASSIST_JOBS[job]['workerActive']
                if not active:break
                time.sleep(.01)
            status=self.client.get('/api/assist/status/'+job).json()
            assert status['status']=='stopped' and 'result' not in status
            assert 'partialResult' in status
