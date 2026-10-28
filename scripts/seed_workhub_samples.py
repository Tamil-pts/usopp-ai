"""Create six explicitly fictional demonstration projects through WorkHub services.

Default: isolated temporary data. --live is an explicit, backed-up, idempotent
operation for the six samples requested by the workspace administrator.
"""
from pathlib import Path
import argparse
import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
if not args.live:
    os.environ['USOPP_DATA_ROOT']=tempfile.mkdtemp(prefix='workhub-six-samples-')
    os.environ['USOPP_PI_WORKER_MODE']='external';os.environ['USOPP_PI_CHILD']='1'
from backend.core import accounts, workhub_workspace as workspace
from backend.core.workhub import store as hub, timestamp
from backend.core.workhub_quality import authoring, documents, service, checks, branding, configuration, store as qc
from backend.core.workhub_intelligence import store as pi, jobs
from backend.core.workhub_intelligence.documents import generated_file

NOTICE='SAMPLE ONLY - FICTIONAL DEMONSTRATION. No physical PLC/HMI testing, real customer acceptance or human engineering sign-off is represented. Workflow actions were populated at the administrator request using Admin and Tamil.'
PLAN=[('completed','Ring Frame PLC Upgrade','released'),('progress-a','Conveyor Interlock Upgrade','development'),('progress-b','Pump HMI Alarm Update','development'),('quality','Packaging Line Validation','quality'),('closure','Winder Control Handover','ready_release'),('assigned','Utility Panel Integration','todo')]
out=ROOT/'.build/workhub-navigation';out.mkdir(parents=True,exist_ok=True)
manifest=out/('six-samples-live.json' if args.live else 'six-samples-isolated.json')
qc.initialize()
if args.live:
    users=accounts.store.list_users()
    admin=next(u for u in users if u['username']=='Admin' and u['role']=='admin' and u['active'])
    tamil=next(u for u in users if u['username']=='Tamil' and u['active'])
    if manifest.exists():
        prior=json.loads(manifest.read_text())
        if prior.get('complete'):
            with hub.db() as db:
                assert all(db.execute('SELECT 1 FROM items WHERE id=? AND title=? AND is_sample=1',(p['id'],p['title'])).fetchone() for p in prior['projects']), 'Sample register changed; inspect before reseeding.'
            print(json.dumps({'already_created':True,'projects':prior['projects']}));sys.exit(0)
        raise RuntimeError('A partial sample manifest exists. Inspect and resume explicitly; never duplicate records.')
    backup=out/('before-requested-six-samples-'+datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir()
    with hub.db() as db, sqlite3.connect(backup/'projects.sqlite3') as target:db.backup(target)
    with accounts.store.db() as db, sqlite3.connect(backup/'accounts.sqlite3') as target:db.backup(target)
else:
    (Path(os.environ['USOPP_DATA_ROOT'])/'.usopp_assist_model.json').write_text('{"provider":"local"}')
    password='Isolated.SixSamples.2026!'
    admin=next((u for u in accounts.store.list_users() if u['username']=='Admin'),None) or accounts.store.register('Admin',password,'Administrator','Sample',role='admin')
    tamil=accounts.store.register('Tamil',password,'Engineer','Sample')
    backup=None

progress={'complete':False,'live':args.live,'data_root':str(hub.root),'backup':str(backup) if backup else None,'notice':NOTICE,'projects':[]}
def checkpoint():manifest.write_text(json.dumps(progress,indent=2),encoding='utf8')
checkpoint()
stop=threading.Event()
if not args.live:
    thread=threading.Thread(target=jobs.run,args=(stop,),daemon=True);thread.start()

def row(pid):
    with hub.db() as db:return hub.item(db,pid)
def transition(key,action):
    p=row(key);u=admin if p[{'todo':'owner_id','development':'owner_id','development_completed':'owner_id','quality':'quality_id','release_approval':'approver_id','ready_release':'release_id'}[p['stage']]]==admin['id'] else tamil
    return hub.transition(u,key,{'version':p['version'],'action':action,'comment':NOTICE})
def current(pid,stage):return service.get_document(tamil,pid,stage)['revision']
def act(pid,stage,action,u=None):
    r=current(pid,stage)
    return service.action(u or tamil,pid,stage,{'version':r['version'],'revision_id':r['id'],'action':action,'comment':NOTICE,'checklist':{k:True for k in ['documents','requirements','tests','fat','issues','approvals']}})
def approve(pid,stage,pending=False):
    act(pid,stage,'confirm');act(pid,stage,'submit')
    if not pending:act(pid,stage,'approve',admin)
def draft(pid,stage,content,**kwargs):
    content=copy.deepcopy(content)
    if not content.get('summary','').startswith(NOTICE):content['summary']=NOTICE+'\n'+content.get('summary','')
    return documents.draft(tamil,pid,stage,content,'Administrator-requested fictional sample.',**kwargs)
def drain(pid):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        with hub.db() as db:pending=[dict(r) for r in db.execute("SELECT id,status,error FROM pi_jobs WHERE project_id=? AND status IN ('queued','running','failed')",(pid,))]
        if any(r['status']=='failed' for r in pending):raise RuntimeError('Sample preparation job failed: '+json.dumps(pending))
        if not pending:return
        time.sleep(.25)
    raise TimeoutError('Sample report preparation has not finished')
def native(pid,kind,content):
    result=pi.save_document(tamil,pid,{'kind':kind,'title':'SAMPLE - '+('Minutes of Meeting' if kind=='mom' else 'Functional Flowchart'),'content':content})
    d,r=result['document'],result['revision']
    with hub.db(True) as db:
        setting=branding.numbering(db,hub.item(db,pid),configuration.current(db))
        setting['configuration']['codes'][kind]='MOM' if kind=='mom' else 'FC'
        number=configuration.allocate(db,kind,setting)
        db.execute('INSERT INTO wh_document_numbers VALUES(?,?,?)',(d['id'],number,qc.bounded(setting['configuration'])))
    pi.review(tamil,pid,d['id'],{'action':'submit','revision_id':r['id'],'reviewer_id':admin['id'],'comment':NOTICE})
    pi.review(admin,pid,d['id'],{'action':'approve','revision_id':r['id'],'comment':NOTICE})
    return d['id']

try:
    for index,(slug,title,target) in enumerate(PLAN):
        today=date(2026,10,27)
        p=workspace.create(admin,{'workspace_schema':3,'title':'SAMPLE '+str(index+1).zfill(2)+' - '+title,'is_sample':True,'kind':'B&R PLC','description':NOTICE+'\n'+title,'owner_id':tamil['id'],'quality_id':admin['id'],'approver_id':tamil['id'],'release_id':admin['id'],'start_date':today.isoformat(),'due_date':(today+timedelta(days=14+index)).isoformat(),'customer':'SAMPLE Customer - Fictional','machine':title.split()[0]+' SAMPLE Machine','scope':'Demonstrate alarm detection, HMI indication, controlled reset and the project approval process. '+NOTICE})
        pid=p['id'];entry={'id':pid,'title':p['title'],'requested_stage':target,'sample':True};progress['projects'].append(entry);checkpoint()
        print('Preparing '+p['title'],flush=True)
        attachment=generated_file(tamil,pid,'SAMPLE-ONLY-demonstration-record.txt',(NOTICE+'\nProject: '+p['title']+'\nSynthetic scenario: trip input active -> alarm displayed; reset held while trip active; trip clear + reset request -> alarm cleared. These are demonstration entries, not observations from equipment.\nSimulated customer acceptance: solely for this fictional example.').encode())['id']
        tasks=[]
        for i,(name,phase,hours) in enumerate([('Confirm requirements','development',2),('Modify PLC logic','development',4),('Update HMI and internal validation','development',4),('Review validation and FAT','quality',2),('Complete handover and closure','release',1)]):
            t=hub.create(admin,{'title':'SAMPLE - '+name,'description':NOTICE,'owner_id':tamil['id'] if phase=='development' else admin['id'],'quality_id':admin['id'],'approver_id':tamil['id'],'release_id':admin['id'],'work_phase':phase,'planned_hours':hours,'start_date':(today+timedelta(days=i)).isoformat(),'due_date':(today+timedelta(days=i+2)).isoformat()},pid);tasks.append(t['id'])
        source={'id':'SAMPLE-BRIEF','label':'Fictional sample brief','text':NOTICE+' Detect SAMPLE_TRIP; show SAMPLE_ALARM; reset only after trip clears.','type':'manual_brief'}
        reqs=[{'id':'FR-001','title':'SAMPLE trip and HMI indication','description':'In the fictional scenario, SAMPLE_TRIP activates SAMPLE_ALARM and its HMI indicator.','expected_behavior':'The sample alarm is latched and shown on the sample HMI.','acceptance_criteria':'Synthetic trip=true produces synthetic alarm=true and visible indication.','trigger':'SAMPLE_TRIP','source_ids':['SAMPLE-BRIEF'],'mandatory':True},
              {'id':'FR-002','title':'SAMPLE controlled reset','description':'The sample alarm can be reset only when SAMPLE_TRIP is clear and SAMPLE_RESET is requested.','expected_behavior':'An active trip prevents reset.','acceptance_criteria':'Synthetic reset while trip=true keeps alarm=true; trip=false plus reset clears it.','trigger':'SAMPLE_RESET','source_ids':['SAMPLE-BRIEF'],'mandatory':True}]
        flow={'nodes':[{'id':n,'position':{'x':i*230,'y':0},'data':{'kind':k,'label':label,'requirement_ids':refs,'source_ids':['SAMPLE-BRIEF']}} for i,(n,k,label,refs) in enumerate([('start','start','SAMPLE: monitor trip',['FR-001']),('alarm','alarm','SAMPLE: show alarm',['FR-001']),('reset','decision','SAMPLE: trip clear and reset?',['FR-002']),('end','end','SAMPLE: clear alarm',['FR-002'])])],'edges':[{'id':'e'+str(i),'source':a,'target':b} for i,(a,b) in enumerate([('start','alarm'),('alarm','reset'),('reset','end')])],'sources':[source]}
        native(pid,'mom',{'meeting_subject':'SAMPLE design review','meeting_date':today.isoformat(),'participants':['Tamil','Admin'],'summary':NOTICE,'discussion_summary':[{'text':NOTICE,'source_ids':['SAMPLE-BRIEF']}],'decisions':[{'text':'Use the fictional trip/reset scenario for demonstration only.','source_ids':['SAMPLE-BRIEF']}],'engineering_requirements':[{'text':r['description'],'source_ids':['SAMPLE-BRIEF']} for r in reqs],'actions':[{'text':'Populate sample project reports.','responsible':'Tamil','status':'Completed' if target=='released' else 'Open','source_ids':['SAMPLE-BRIEF']}],'clarifications':[],'sources':[source],'file_ids':[attachment]})
        native(pid,'flowchart',{**flow,'notice':NOTICE})
        draft(pid,'frd',{'summary':title,'purpose':NOTICE,'scope':'Fictional trip/reset behavior.','requirements':reqs,'sources':[source],'flowchart':flow,'file_ids':[attachment]})
        r=current(pid,'frd');documents.confirm_flowchart(tamil,pid,'frd',{'version':r['version'],'revision_id':r['id'],'confirmed':True})
        approve(pid,'frd')
        draft(pid,'corrections',{'summary':'SAMPLE correction note','sources':[source],'file_ids':[attachment],'changes':[{'id':'CN-001','summary':'SAMPLE reset interlock modification','existing_behavior':'Fictional prior behavior permits reset with active trip.','expected_behavior':'Block reset while the sample trip is active.','impact':'SAMPLE alarm handling and HMI only.','before_evidence':'SAMPLE-ONLY demonstration record; no equipment observation.','after_evidence':'Fictional corrected scenario described in the attached sample record.','verification':'Synthetic scenario for portfolio demonstration.','source_ids':['SAMPLE-BRIEF'],'requirement_ids':['FR-002']} ]})
        advanced=target in {'released','quality','ready_release'}
        if target!='todo':
            transition(pid,'start')
            completed=3 if advanced else 1 if slug=='progress-a' else 2
            for t in tasks[:completed]:transition(t,'start');transition(t,'complete_development')
            if not advanced:transition(tasks[completed],'start')
        if advanced:
            approve(pid,'corrections')
            for stage in ('test','fat'):
                r=current(pid,stage)
                for c in r['content']['cases']:
                    r=current(pid,stage);documents.execute(tamil,pid,stage,{'version':r['version'],'revision_id':r['id'],'case_id':c['id'],'outcome':'pass','actual':'SAMPLE ONLY: synthetic expected outcome populated for demonstration. '+c['expected_result'],'observations':NOTICE,'file_ids':[attachment]})
                if stage=='fat':
                    r=current(pid,stage);documents.acceptance(tamil,pid,stage,{'version':r['version'],'revision_id':r['id'],'status':'accepted','customer':'SAMPLE Customer - Fictional','representative':'SAMPLE simulated representative','accepted_at':timestamp(),'file_ids':[attachment],'remarks':NOTICE})
                approve(pid,stage)
            transition(pid,'complete_development');transition(pid,'submit_quality');transition(tasks[3],'start')
            if target!='quality':transition(tasks[3],'complete_development')
            with hub.db() as db:basis=checks.baseline(db,hub.item(db,pid))
            draft(pid,'quality',{'summary':'SAMPLE quality review','sections':[{'heading':'Review conclusion','text':NOTICE+' All synthetic test cases and document links have been checked in this demonstration.'}],'file_ids':[attachment]},baseline=basis)
            approve(pid,'quality',pending=target=='quality')
            if target!='quality':
                drain(pid)
                # The auto-prepared closure belongs to the quality reviewer.
                # Tamil takes a controlled successor revision so Admin can review
                # independently; do not rewrite authorship of the original draft.
                r=current(pid,'closure')
                if r['owner_id']!=tamil['id']:
                    service.new_revision(tamil,pid,'closure',{'revision_id':r['id'],'reason':'Tamil prepares a controlled sample handover revision for independent Admin review. '+NOTICE})
                transition(pid,'approve_release');transition(tasks[4],'start')
                if target=='released':transition(tasks[4],'complete_development')
                with hub.db() as db:basis=checks.baseline(db,hub.item(db,pid),True)
                draft(pid,'closure',{'summary':'SAMPLE project closure','sections':[{'heading':'Completion summary','text':NOTICE},{'heading':'Final deliverables','text':'Sample MOM, FRD, flowchart, correction note, validation report, FAT and quality review.'},{'heading':'Handover information','text':'SAMPLE ONLY: fictional PLC/HMI handover recorded in attached demonstration file.'},{'heading':'Open issues','text':'No open sample issues.'}],'file_ids':[attachment]},baseline=basis)
                approve(pid,'closure',pending=target=='ready_release')
                if target=='released':
                    drain(pid);transition(pid,'release')
        else:
            authoring.create(tamil,pid,{'stage':'quality'})
        # Keep every report visibly labelled, including the early-stage drafts.
        for stage in ('test','fat','quality','closure'):
            r=current(pid,stage)
            if r['status']=='draft':
                content=r['content']
                if not content.get('summary','').startswith(NOTICE):content['summary']=NOTICE+'\n'+content.get('summary','')
                documents.save(tamil,pid,stage,{'version':r['version'],'revision_id':r['id'],'content':content})
        final=row(pid);assert final['stage']==target,(slug,final['stage'],target)
        with hub.db() as db:
            entry.update(stage=final['stage'],tasks=tasks,reports=[dict(r) for r in db.execute('SELECT q.stage,q.number,r.status,r.approved_by,r.reviewer_id FROM qc_documents q JOIN pi_documents d ON d.id=q.document_id JOIN qc_revisions r ON r.id=d.current_revision WHERE q.project_id=?',(pid,))],native_documents=[dict(r) for r in db.execute('SELECT kind,title,approved_revision FROM pi_documents WHERE project_id=? AND kind IN (\'mom\',\'flowchart\')',(pid,))])
        checkpoint();print('Ready '+p['title']+' -> '+target,flush=True)
    # Keep demonstration notifications in the app; do not retry them externally
    # later if an engineer connects email or Teams.
    with hub.db(True) as db:
        db.execute("UPDATE outbox SET status='disabled',detail='Fictional sample: in-app notification only.' WHERE status NOT IN ('sent','delivered') AND notification_id IN (SELECT id FROM notifications WHERE project_id IN (SELECT value FROM json_each(?)))",(json.dumps([p['id'] for p in progress['projects']]),))
    progress['complete']=True;checkpoint();print(json.dumps({'complete':True,'manifest':str(manifest),'projects':[(p['title'],p['stage']) for p in progress['projects']]}),flush=True)
finally:
    stop.set()
