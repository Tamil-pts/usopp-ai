"""Optional real private Chopper smoke test using fictional records only."""
from pathlib import Path
import json
import os
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'.usopp_assist_model.json').read_text(encoding='utf-8'))
sys.path.insert(0,str(Path(__file__).parent))
from test_workhub_frd_workflow import FRDWorkflow,OUT


def main():
    from urllib.parse import urlsplit
    if urlsplit(cfg.get('baseUrl','')).hostname not in {'127.0.0.1','localhost','::1'}:raise SystemExit('This optional check requires the existing loopback Chopper service.')
    FRDWorkflow.report_file='local-model-fixture-state.json';FRDWorkflow.setUpClass();case=FRDWorkflow('test_01_end_to_end_reviewed_transcript_to_approved_pdf');case.setUp()
    os.environ.update(USOPP_PI_LLM_URL=cfg['baseUrl'],USOPP_PI_LLM_MODEL=cfg.get('model','chopper-local'),USOPP_PI_LLM_MAX_TOKENS='1200')
    checks=[]
    def execute(value,label):
        job=case.jobs.claim();assert job and job.row['id']==value['id']
        started=time.monotonic();case.jobs.execute(job,__import__('threading').Event());result=case.jobs.get_job(case.author,case.pid,value['id'])
        checks.append({'step':label,'seconds':round(time.monotonic()-started,3),'status':result['status'],'error':result.get('error'),'result':result['result']})
        if result['status']!='completed':raise RuntimeError(label+': '+result.get('error',''))
        return result['result']
    try:
        import requests
        session=requests.Session();session.trust_env=False
        response=session.get(cfg['baseUrl']+'/models',timeout=5);checks.append({'step':'Existing local model health','status':response.status_code});response.raise_for_status();session.close()
        file=case.upload('fictional-local-model.vtt','WEBVTT\n\n00:00:00.000 --> 00:00:08.000\nThe PLC shall latch TRAIN_TRIP_ALARM when TRAIN_MOTOR_TRIP is active. The HMI shall display the latched alarm.\n\n00:00:09.000 --> 00:00:16.000\nTRAIN_RESET_REQUEST shall clear the alarm only after TRAIN_MOTOR_TRIP is clear. Confirm retention after restart before approval.\n')
        meeting=case.ok(case.client.post(case.pi+'/meetings',json={'file_id':file['id'],'subject':'Fictional alarm training discussion'}));mid=meeting['id']
        execute(case.ok(case.client.post(case.pi+'/jobs',json={'kind':'transcribe','payload':{'meeting_id':mid}})),'Import supplied timestamped transcript (no speech recognition)')
        value=case.ok(case.client.get(case.pi+'/meetings/'+mid));case.ok(case.client.post(case.pi+'/meetings/'+mid+'/transcript/confirm',json={'version':value['transcript_version'],'confirmed':True}))
        result=execute(case.ok(case.client.post(case.pi+'/jobs',json={'kind':'meeting','payload':{'meeting_id':mid}})),'Actual local Chopper MOM')
        doc=result['document_id'];rid=result['revision_id'];case.ok(case.client.post(case.pi+'/documents/'+doc+'/review',json={'action':'submit','revision_id':rid,'reviewer_id':case.reviewer['id']}))
        approved=case.ok(case.review_client.post(case.pi+'/documents/'+doc+'/review',json={'action':'approve','revision_id':rid,'comment':'Reviewed fictional smoke-test source only.'}))
        result=execute(approved['frd_job'],'Actual local Chopper FRD');case.ok(case.client.get(case.qc))
        frd=case.ok(case.client.get(case.qc+'/documents/frd'));rev=frd['revision'];reqs=rev['content']['requirements'];assert reqs
        checks.append({'step':'Actual FRD integrity','requirements':len(reqs),'unique_ids':len({r['id'] for r in reqs}),'content':rev['content']})
        execute(case.ok(case.client.post(case.qc+'/documents/frd/assist',json={'action':'flowchart','version':rev['version'],'revision_id':rev['id'],'requirement_ids':[reqs[0]['id']],'question':'Propose a concise source-linked diagram. Do not invent reset conditions.'})),'Actual local Chopper flowchart proposal')
        return 0
    except Exception as error:
        checks.append({'step':'Live model limitation','status':'Failed','error':str(error)});return 1
    finally:
        (OUT/'local-model-results.json').write_text(json.dumps({'provider':'Existing private Chopper on loopback','data':'Fictional isolated test only','checks':checks},indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(checks,indent=2,ensure_ascii=False));case.tearDown();FRDWorkflow.tearDownClass()


if __name__=='__main__':raise SystemExit(main())
