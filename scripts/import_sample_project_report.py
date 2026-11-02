"""Stage a traceable WorkHub replacement from this user's sample.xlsx report.

Does not touch the running installation. Installation is a separate, offline step
after the staged database, documents and identity mappings have been checked.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIELDS = ['project_number','machine','complexity','category','description','software','software_version',
          'lmw_target_hours','lmw_target_date','customer_reference','customer_contact','planned_engineer',
          'actual_engineer','qc_engineer','planned_start','actual_start','planned_delivery','actual_delivery',
          'estimated_hours','execution_days','engineer_hours','qc_hours','actual_hours','checkpoints','peer_qc','status','remarks']
DATE_FIELDS = {'lmw_target_date','planned_start','actual_start','planned_delivery','actual_delivery'}
HOUR_FIELDS = {'lmw_target_hours','estimated_hours','engineer_hours','qc_hours','actual_hours'}
ALIASES = {'prasath':'Prasath P','gokulr':'Gokul R','vigneshrlmw':'Vignesh R',
           'vigneshr':'Vignesh R','harithirunavukkarsua':'Hari Thirunavukkarasu A',
           'harithirunavukkarasua':'Hari Thirunavukkarasu A'}
MANAGERS = ['Sampathkumar A', 'Sasikumar T']

def text(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('\xa0',' ')).strip()

def person(value):
    value = text(value)
    if value.casefold() in {'','na','n/a','customer','ok','off shore','-'}:
        return ''
    key = re.sub('[^a-z0-9]', '', value.casefold())
    return ALIASES.get(key, value.title().replace('_Lmw',' LMW'))

def fingerprint(path):
    db = sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro', uri=True)
    result = {}
    for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        rows = [json.dumps(list(r),default=lambda b:hashlib.sha256(b).hexdigest(),ensure_ascii=False,sort_keys=True) for r in db.execute('SELECT * FROM "'+table+'"')]
        result[table] = {'count':len(rows),'sha256':hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
    db.close()
    return result

def copy_db(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)

def normalize(source):
    from openpyxl import load_workbook
    from openpyxl.utils.datetime import from_excel
    w = load_workbook(source,data_only=True,read_only=True)
    rows=[]
    for rn,raw in enumerate(w.active.iter_rows(min_row=2,values_only=True),2):
        if not re.fullmatch(r'LMW-SOF-\d+',str(raw[0] or '')):
            continue
        values=dict(zip(FIELDS,raw));notes=[]
        for key in DATE_FIELDS:
            v=values[key]
            if isinstance(v,(int,float)) and 30000<=v<=60000:
                values[key]=from_excel(v,w.epoch).date().isoformat()
            elif isinstance(v,datetime):values[key]=v.date().isoformat()
            else:
                if v is not None:notes.append(f'{key}: invalid source value {v!r}; replaced by a documented planning default.')
                values[key]=''
        for key in HOUR_FIELDS:
            v=values[key]
            values[key]=round(v*24,4) if type(v) in (int,float) and 0<=v<2000 else None
        for key in ['execution_days','checkpoints','peer_qc']:
            v=values[key];values[key]=v if type(v) in (int,float) and 0<=v<10000 else None
        for key in set(FIELDS)-DATE_FIELDS-HOUR_FIELDS-{'execution_days','checkpoints','peer_qc'}:
            values[key]=text(values[key])
        if rn==4:
            # The only expanded/corrupted row: retain the status in the aligned
            # Z column, and retain the conflicting appended AJ value as evidence.
            notes.append('Expanded row: status Z4=In-QC retained; appended AJ4=HOLD conflicts. L4=ok is not a person; O4=Off shore and P4/Q4 contain names instead of dates.')
            if not values['actual_start'] and type(raw[19]) in (int,float) and 30000<=raw[19]<=60000:
                values['actual_start']=from_excel(raw[19],w.epoch).date().isoformat()
                values['execution_days']=None
                notes.append('Recovered actual start from the only valid extra date T4; interpretation requires review.')
        duration=max(1,min(3650,int(values['execution_days'] or max(1,(values['estimated_hours'] or values['lmw_target_hours'] or 24)/8))))
        due=values['planned_delivery'] or values['lmw_target_date'] or values['actual_delivery']
        start=values['planned_start'] or values['actual_start']
        if not due:
            due=((date.fromisoformat(start) if start else date.today())+timedelta(days=duration-1)).isoformat()
            notes.append('Planned delivery auto-filled from available start and planned duration; not a reported actual date.')
        if not start:
            start=(date.fromisoformat(due)-timedelta(days=duration-1)).isoformat()
            notes.append('Planned start auto-filled backwards from target date and planned duration.')
        if start>due:
            notes.append(f'Planning sequence conflict: source start {start} follows target {due}; operational target uses start, raw dates retained.')
            due=start
        estimated=values['estimated_hours'] if values['estimated_hours'] is not None else values['lmw_target_hours']
        if estimated is None:
            estimated=duration*8
            notes.append('Estimated hours auto-filled at 8 planning hours/day; not actual or approved billing time.')
        elif values['estimated_hours'] is None:notes.append('Petrus estimate defaults to the customer target hours.')
        if values['actual_hours'] is not None and values['engineer_hours'] is not None and values['engineer_hours']>values['actual_hours']+.01:
            notes.append(f"Workbook hour conflict: engineer hours {values['engineer_hours']} exceed Petrus total hours {values['actual_hours']}. Both source values are preserved; billing approval is not inferred.")
        versions=re.findall(r'(?:PV[_ :\-]*|HS(?:-MC)?[-_ ]*|TS(?:-MC)?[-_ ]*|DS(?:-MC)?[-_ ]*)(\d+(?:\.\d+)+|\d{4,})',values['description'],re.I)
        values.update(row=rn,source_range=f'Sheet1!A{rn}:AM{rn}',start_date=start,due_date=due,
                      planned_hours=round(estimated,4),program_versions=list(dict.fromkeys(versions)),notes=notes,
                      raw=[v.isoformat() if isinstance(v,(date,datetime)) else v for v in raw],
                      owner=person(values['actual_engineer']) or person(values['planned_engineer']) or MANAGERS[0])
        rows.append(values)
    assert len(rows)==53 and len({r['project_number'] for r in rows})==53
    return rows

def remove_old(db):
    tables={r[0]:[c[1] for c in db.execute('PRAGMA table_info("'+r[0]+'")')] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    def ids(table,column,where_column,values):
        if not values or table not in tables:return set()
        return {r[0] for r in db.execute(f'SELECT "{column}" FROM "{table}" WHERE "{where_column}" IN ({",".join("?" for _ in values)})',list(values))}
    old={r[0] for r in db.execute("SELECT id FROM items WHERE type='project'")}
    objects={
        'project_id':old,'item_id':ids('items','id','project_id',old),'task_id':ids('items','id','project_id',old),
        'document_id':ids('pi_documents','id','project_id',old),'control_id':ids('qc_documents','id','project_id',old),
        'meeting_id':ids('pi_meetings','id','project_id',old),'job_id':ids('pi_jobs','id','project_id',old),
        'file_id':ids('files','id','project_id',old),'article_id':ids('cp_articles','id','project_id',old),
        'evidence_id':ids('pc_manual','id','project_id',old),
    }
    objects['revision_id']=ids('pi_revisions','id','document_id',objects['document_id'])|ids('cp_revisions','id','article_id',objects['article_id'])|ids('pc_manual_revisions','id','evidence_id',objects['evidence_id'])
    objects['comment_id']=ids('ds_comments','id','document_id',objects['document_id'])
    removed={}
    for table,columns in tables.items():
        if table in {'wh_document_spaces','cp_search_fts_data','cp_search_fts_idx','cp_search_fts_content','cp_search_fts_docsize','cp_search_fts_config'}:continue
        conditions=[];params=[]
        for col,values in objects.items():
            if values and col in columns:
                conditions.append('"'+col+'" IN ('+','.join('?' for _ in values)+')');params.extend(values)
        if conditions:
            cursor=db.execute('DELETE FROM "'+table+'" WHERE '+' OR '.join(conditions),params)
            if cursor.rowcount:removed[table]=cursor.rowcount
    if old:
        marks=','.join('?' for _ in old)
        db.execute(f'UPDATE wh_document_spaces SET linked_project_id=NULL,version=version+1 WHERE linked_project_id IN ({marks})',list(old))
    for table in ('outbox','notifications','cp_notification_targets','pc_state'):
        if table in tables:db.execute('DELETE FROM "'+table+'"')
    # Project-bound TechShare search entries may have been removed above.
    if objects['article_id'] and 'cp_search_fts' in tables:
        db.execute('DELETE FROM cp_search_fts WHERE article_id IN ('+','.join('?' for _ in objects['article_id'])+')',list(objects['article_id']))
    return sorted(old),removed

def build(source,folder,rows):
    os.environ['USOPP_DATA_ROOT']=str(folder/'stage')
    os.environ['USOPP_PI_CHILD']='1'
    from backend.core import accounts,workhub_organization as org,workhub_workspace as workspace
    from backend.core.workhub import store as hub,identity,timestamp,encode
    from backend.core.workhub_quality import store as quality,documents,authoring
    from backend.core import workhub_approval_documents as attachments
    quality.initialize();org.initialize()
    admin=next(u for u in accounts.store.list_users() if u['username'].casefold()=='admin')
    engineers={person(r[k]) for r in rows for k in ('planned_engineer','actual_engineer','qc_engineer') if person(r[k]) and person(r[k]) not in {person(r['customer_contact'])}}
    contacts={person(r['customer_contact']) for r in rows if person(r['customer_contact'])}
    engineers-=contacts;engineers.update(MANAGERS)
    users={u['username'].casefold():u for u in accounts.store.list_users()};created=[];mapping={}
    password=os.environ.get('USOPP_IMPORT_DEFAULT_PASSWORD')
    if not password:raise RuntimeError('Set USOPP_IMPORT_DEFAULT_PASSWORD for newly created accounts.')
    for name in sorted(engineers|contacts):
        designation='Delivery Manager' if name in MANAGERS else 'Customer Project Contact' if name in contacts else 'Project Engineer'
        u=users.get(name.casefold())
        if not u:
            u=accounts.store.register(name,password,designation,'LMW' if name in contacts else 'Petrus Technologies Pvt',workspace_modules=['workhub'] if name in contacts else list(accounts.WORKSPACE_MODULES))
            created.append({'id':u['id'],'username':name,'designation':designation,'company':u['company']})
        elif name in MANAGERS:
            with accounts.store.db() as db:db.execute('UPDATE users SET designation=? WHERE id=?',(designation,u['id']))
        mapping[name]=u['id']
    def unit(kind,name,department=''):
        with hub.db() as db:
            row=db.execute('SELECT id FROM wh_org_units WHERE kind=? AND name=? AND department_id=?',(kind,name,department)).fetchone()
        return row[0] if row else org.save_unit(admin,{'kind':kind,'name':name,'department_id':department,'version':0,'member_ids':[],'manager_ids':[]})['id']
    dept=unit('department','Engineering Services');cust_dept=unit('department','Customer Collaboration')
    role=unit('role','Project Engineer',dept);manager_role=unit('role','Delivery Manager',dept);contact_role=unit('role','Customer Project Contact',cust_dept)
    team=unit('team','LMW Software Delivery',dept)
    with hub.db() as db:version=db.execute('SELECT version FROM wh_org_units WHERE id=?',(team,)).fetchone()[0]
    org.save_unit(admin,{'kind':'team','name':'LMW Software Delivery','department_id':dept,'version':version,'member_ids':sorted({mapping[n] for n in engineers}),'manager_ids':[mapping[n] for n in MANAGERS]},team)
    for name,uid in mapping.items():
        with hub.db() as db:profile=org.profile(db,uid)
        manager=None if name in MANAGERS or name in contacts else mapping[MANAGERS[1] if name in {'Karthick R','Navaneethan S','Hariprasath'} else MANAGERS[0]]
        org.save_profile(admin,uid,{'version':profile['version'],'department_id':cust_dept if name in contacts else dept,
            'role_id':manager_role if name in MANAGERS else contact_role if name in contacts else role,
            'manager_id':manager,'team_ids':[] if name in contacts else [team],
            'daily_hours':8,'workdays':5,'availability_note':'Imported from sample.xlsx. Standard planning capacity 8 h/day, 5 days/week; reporting manager allocated during import.'})
    with hub.db(True) as db:old,removed=remove_old(db)
    source_bytes=source.read_bytes();sha=hashlib.sha256(source_bytes).hexdigest()
    blob=hub.root/'blobs'/sha[:2]/sha;blob.parent.mkdir(parents=True,exist_ok=True);blob.write_bytes(source_bytes)
    imported=[]
    for row in rows:
        owner=mapping[row['owner']];manager=mapping[MANAGERS[1] if row['owner'] in {'Karthick R','Navaneethan S','Sasikumar T'} else MANAGERS[0]]
        other=mapping[MANAGERS[0]] if manager==mapping[MANAGERS[1]] else mapping[MANAGERS[1]]
        qc=mapping.get(person(row['qc_engineer'])) or other
        if qc==owner:qc=other if other!=owner else manager
        actual_platform=row['software'] or 'PLC platform to be confirmed'
        platform_version=row['software_version'] or 'Engineering software version not supplied'
        program='; '.join(row['program_versions']) or 'Program revision to be confirmed from source project'
        notice=f"Imported from sample.xlsx / {row['source_range']}. Reported status: {row['status']}. Import preserves historical completion without generating electronic signatures. Test execution evidence, exact I/O lists and approved machine sequences were not supplied. Auto-filled engineering wording requires review."
        notes=notice+'\n'+'\n'.join(row['notes'])
        scope=f"{row['category']}: {row['description']}\nMachine: {row['machine']}. Platform: {actual_platform}; engineering software: {platform_version}. Customer change reference: {row['customer_reference']}."
        accepts=[f"The requested change is implemented for {row['machine']} against {row['customer_reference']}.",
                 'Affected PLC/HMI behavior and existing interlocks are verified against the agreed change scope.',
                 'Validation and FAT test evidence is recorded and any deviations receive an authorized disposition.',
                 'Source project, program version references and reviewed engineering documents are handed over.']
        reqs=[{'id':'REQ-001','title':row['description'][:180],'description':row['description'],'category':row['category'],'acceptance_criteria':accepts[0]},
              {'id':'REQ-002','title':'Platform and program version traceability','description':f'Use {actual_platform}, {platform_version}. Verify the developed program references: {program}.','category':'Configuration','acceptance_criteria':'Developed source versions match the recorded release references; missing versions are confirmed by the engineer.'},
              {'id':'REQ-003','title':'Functional and HMI regression verification','description':'Review affected PLC functions, HMI interfaces, alarms and interlocks in the requested change scope. Confirm exact test conditions from the source project.','category':'Functional','acceptance_criteria':accepts[1]},
              {'id':'REQ-004','title':'Validation, FAT and handover evidence','description':'Record validation and customer acceptance evidence; deliver the source program and controlled project documents.','category':'Documentation','acceptance_criteria':accepts[2]+' '+accepts[3]}]
        fields=[]
        def field(label,value,kind='text'):fields.append({'label':label,'type':kind,'value':value if value is not None else ''})
        for key,label,kind in [('machine','Machine','text'),('complexity','Project Complexity','text'),('category','Category','text'),('software','Software','text'),('software_version','Software Version','text'),('lmw_target_hours','LMW Target Hours','number'),('lmw_target_date','LMW Target Date','date'),('customer_reference','TC ID','text'),('customer_contact','LMW Point of Contact','text'),('planned_engineer','Planned Engineer','text'),('actual_engineer','Actual Engineer','text'),('qc_engineer','QC Checked By','text'),('planned_start','Planned Start (Reported)','date'),('actual_start','Actual Start','date'),('planned_delivery','Planned Delivery (Reported)','date'),('actual_delivery','Actual Delivery','date'),('estimated_hours','Petrus Estimated Hours','number'),('execution_days','Execution Days (Plan)','number'),('engineer_hours','Engineers Actual Hours','number'),('qc_hours','QC Hours','number'),('actual_hours','Petrus Actual Hours','number'),('checkpoints','Quality Total Checkpoints','number'),('peer_qc','Peer QC (QC2)','number'),('status','Source Status','text'),('remarks','Source Remarks','text')]:field(label,row[key],kind)
        field('Delivery Managers',', '.join(MANAGERS));field('Import Source',row['source_range']);field('Import Notes','\n'.join(row['notes']) or 'No structural corrections required.');field('Source File SHA256',sha)
        steps=[{'id':key,'title':title,'description':desc,'phase':phase,'days':1,'planned_hours':row['planned_hours'] if key=='development' else 0,'milestone':False,'depends_on':[prev] if prev else []} for key,title,desc,phase,prev in [
            ('requirements','Requirements & Planning','Review the source report and FRD.','development',''),('development','Development','Implement the requested PLC/HMI change.','development','requirements'),
            ('validation','Testing & Validation','Execute and review the validation report.','quality','development'),('fat','FAT & Approval','Record acceptance evidence and review deviations.','quality','validation'),('closure','Project Closure','Verify deliverables and authorize handover.','release','fat')]]
        title=row['description'][:180]
        project=workspace.create(admin,{'workspace_schema':3,'title':title,'project_number':row['project_number'],'kind':'B&R PLC' if row['software']=='B&R' else 'Siemens PLC' if row['software']=='Siemens' else 'Other PLC',
            'description':scope,'owner_id':owner,'quality_id':qc,'approver_id':manager,'release_id':other,'supporting_ids':sorted({mapping[n] for n in MANAGERS}|{mapping[person(row['planned_engineer'])]} if person(row['planned_engineer']) else {mapping[n] for n in MANAGERS}),
            'start_date':row['start_date'],'due_date':row['due_date'],'planned_hours':row['planned_hours'],'customer':'LMW','customer_project_reference':row['customer_reference'],'machine':row['machine'],'scope':scope,
            'project_requirements':'\n'.join(r['description'] for r in reqs),'acceptance_criteria':'\n'.join(accepts),'base_reference':f'Customer reference {row["customer_reference"]}; baseline project filename not supplied.',
            'developed_reference':row['description']+'\nProgram version references: '+program,'additional_information':notes,'responsibility':'Assigned engineer: '+row['owner']+'. Delivery management: '+', '.join(MANAGERS),
            'assignment_remarks':'Assignments and planning defaults imported from the project report.','custom_fields':fields,'workflow_steps':steps,
            'workflow_assignees':{'requirements':owner,'development':owner,'validation':qc,'fat':manager,'closure':other}})
        pid=project['id']
        with hub.db(True) as db:
            p=hub.item(db,pid);fid=identity();now=timestamp()
            db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?)',(fid,pid,admin['id'],'sample.xlsx',sha,len(source_bytes),now))
            source_id='REPORT-ROW-'+str(row['row'])
            evidence={'id':source_id,'type':'project_report','file_id':fid,'label':'sample.xlsx / '+row['source_range'],'text':json.dumps({k:row[k] for k in FIELDS},ensure_ascii=False),'sheet':'Sheet1','cell':'A'+str(row['row'])+':AM'+str(row['row'])}
            missing=['Exact PLC/HMI source project and full customer specification are not attached.','Detailed executed test results, signed review and customer acceptance are not in the source workbook.']+row['notes']
            frd=authoring.blank('frd');frd.update(summary=scope,purpose=row['description'],scope=scope,background='Historical LMW software project imported from the project report. '+notice,
                expected_outcome='\n'.join(accepts),acceptance_summary='\n'.join(accepts),acceptance_items=[{'id':'AC-'+str(i+1).zfill(3),'text':a,'confirmed':False} for i,a in enumerate(accepts)],
                requirements=[{**r,'expected_behavior':r['acceptance_criteria'],'subsystem':row['machine'],'source_ids':[source_id],'source_label':'sample.xlsx row '+str(row['row']),'priority':'medium','status':'open','mandatory':True,'change':'unresolved'} for r in reqs],
                sources=[evidence],file_ids=[fid],missing=missing,sections=[{'heading':h,'text':v} for h,v in [
                    ('Functional Description',row['description']+'\nDetailed operating sequence must be confirmed from the PLC/HMI source.'),('Included in Scope',scope),('Not in Scope','Mechanical changes, electrical hardware changes and unrelated machine functions unless confirmed in the customer scope.'),
                    ('Deliverables','Developed PLC/HMI project and version record; FRD; Validation Test Report; FAT report; Project Closure record.'),('Additional Information',notes),('Review & Approval','Assigned engineer: '+row['owner']+'. Delivery managers: '+', '.join(MANAGERS)+'. Reviewer and approval signatures are pending.')]])
            frd=documents.clean_content(db,pid,'frd',frd);doc=documents.create_control(db,p,admin,'frd',initial_content=frd,generated_by='project-report:'+sha+':'+str(row['row'])+':frd');rid=quality.native(db,doc)['current_revision']
            doc_refs={'frd':{'control_id':doc['id'],'document_id':doc['document_id'],'revision_id':rid,'number':doc['number']}}
            for stage in ['test','fat','closure']:
                content=authoring.blank(stage);content.update(summary=notice,purpose=('Verify '+row['description']) if stage!='closure' else 'Record project delivery and outstanding evidence.',scope=scope,file_ids=[fid],sources=[evidence,{'id':'FRD-'+rid,'type':'frd_revision','revision_id':rid,'sha256':quality.revision(db,doc['id'],rid)['content_hash'],'label':doc['number']+' / R01 (draft)','text':'Draft requirements derived from the project report. Approval is pending.'}],missing=missing)
                if stage in {'test','fat'}:
                    content.update(report_date=date.today().isoformat(),conclusion='Pending engineer review and executed test evidence. Source project status: '+row['status']+'. No pass/fail result is inferred from that status.',
                        references=[{'id':'REF-001','title':'Functional Requirements Document (draft)','control_id':doc['id'],'revision_id':rid},{'id':'REF-002','title':'LMW project report / '+row['source_range'],'file_id':fid,'number':row['project_number'],'revision':'Source workbook','date':row['actual_delivery'] or ''}],
                        cases=[{'id':('TC-' if stage=='test' else 'FAT-')+str(i+1).zfill(3),'objective':r['title'],'procedure':'Verify against the authorized source project: '+r['description'],'expected_result':r['acceptance_criteria'],'acceptance_criteria':r['acceptance_criteria'],'requirement_ids':[r['id']],'source_ids':['FRD-'+rid],'mandatory':True} for i,r in enumerate(reqs)],
                        report_issues=[{'id':'ISS-001','description':'Executed test logs and signed acceptance are missing from the imported report.','correction':'Attach project-specific evidence and record the actual results.','retest_result':'Pending','status':'open'}])
                    content['sections']=[{'heading':h,'text':v} for h,v in [('Test Environment',actual_platform+' / '+platform_version+'; target hardware and I/O configuration require confirmation.'),('Reference documents',doc['number']+' R01 (draft), sample.xlsx '+row['source_range']),('Imported Project Status',row['status']),('Source Remarks',row['remarks'] or 'No additional remarks recorded in source report.'),('Review & Approval','Results and acceptance must be recorded by authorized personnel.')]]
                else:
                    content['sections']=[{'heading':h,'text':v} for h,v in [('Completion summary','Source workbook reports '+row['status']+' for '+row['project_number']+'. This is imported historical status, not a new electronic sign-off.'),('Final deliverables',row['description']+'\nProgram references: '+program+'\nFRD, Validation and FAT drafts prepared from the source report. Actual source-program attachments and approved revisions remain to be supplied.'),('Document revisions','\n'.join(d['number']+' / R01 (draft)' for d in doc_refs.values())),('Handover information','Engineer: '+row['owner']+'; customer contact: '+row['customer_contact']+'; delivery managers: '+', '.join(MANAGERS)),('Open issues','\n'.join(missing)),('Closure remarks',row['remarks'] or 'Confirm final handover and closure evidence.'),('Approval fields','Prepared by import under Admin. Assigned owner: '+row['owner']+'. Authorized review and signatures pending.')]]
                clean=documents.clean_content(db,pid,stage,content);related=documents.create_control(db,p,admin,stage,initial_content=clean,generated_by='project-report:'+sha+':'+str(row['row'])+':'+stage);related_rid=quality.native(db,related)['current_revision']
                db.execute('UPDATE qc_revisions SET frd_revision_id=?,owner_id=?,reviewer_id=?,approver_id=?,reason=? WHERE id=?',(rid,owner,qc,manager,'Imported draft from sample.xlsx; actual evidence and authorized approval pending.',related_rid))
                doc_refs[stage]={'control_id':related['id'],'document_id':related['document_id'],'revision_id':related_rid,'number':related['number']}
            db.execute('UPDATE qc_revisions SET owner_id=?,reviewer_id=?,approver_id=? WHERE id=?',(owner,qc,manager,rid))
            workflow={r['step_id']:r['task_id'] for r in db.execute('SELECT * FROM wh_workflow_steps WHERE project_id=?',(pid,))}
            for stage,step in [('frd','requirements'),('test','validation'),('fat','fat'),('closure','closure')]:
                attachments.attach(db,hub.item(db,workflow[step]),admin,[doc_refs[stage]])
            hub.event(db,p,admin,'project_report_imported',{'file_id':fid,'source_sha256':sha,'source_range':row['source_range'],'source_status':row['status'],'normalized':{k:row[k] for k in FIELDS},'corrections':row['notes'],'historical_only':True,'generated_approvals':False})
            update_id=identity();db.execute('INSERT INTO updates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(update_id,pid,pid,admin['id'],notes+'\nSource actual hours: '+str(row['actual_hours'])+'; no daily or billing time approval inferred.',row['actual_delivery'] or row['due_date'],0,encode([fid]),'[]',now,qc,'none','Imported history; no time approval'))
            status=row['status'].casefold();completed=status in {'completed','completed by customer'}
            stage='released' if completed else 'quality' if status=='in-qc' else 'blocked'
            exception='cancelled' if 'withdrawn' in status else 'on_hold' if status=='hold' else ''
            end=(row['actual_delivery']+'T12:00:00+00:00') if row['actual_delivery'] and completed else None
            start=(row['actual_start']+'T09:00:00+00:00') if row['actual_start'] else None
            db.execute('UPDATE items SET stage=?,exception_status=?,exception_reason=?,started_at=?,completed_at=?,version=version+1 WHERE id=?',(stage,exception,'Imported source status: '+row['status'] if exception else '',start,end,pid))
            for index,(step,tid) in enumerate(workflow.items()):
                task_stage='released' if completed else 'released' if stage=='quality' and step in {'requirements','development'} else 'quality' if stage=='quality' and step=='validation' else 'blocked' if exception else 'todo'
                planned_start=row['start_date'] if step in {'requirements','development'} else row['due_date']
                planned_end=planned_start if step=='requirements' else row['due_date']
                db.execute('UPDATE items SET stage=?,start_date=?,due_date=?,baseline_due=?,started_at=?,completed_at=?,exception_status=?,exception_reason=?,version=version+1 WHERE id=?',(task_stage,planned_start,planned_end,planned_end,start,end,exception,'Imported status: '+row['status'] if exception else '',tid))
            db.execute('UPDATE project_phases SET start_date=?,due_date=?,baseline_due=? WHERE project_id=?',(row['start_date'],row['due_date'],row['due_date'],pid))
            quality.audit(db,admin,pid,'historical_status_imported',{'status':row['status'],'source_file':fid,'source_row':row['row'],'approvals_generated':False,'actual_completion_date_supplied':bool(row['actual_delivery'])})
            imported.append({'project_id':pid,'project_number':row['project_number'],'owner':row['owner'],'source_status':row['status'],'documents':doc_refs,'file_id':fid})
        print('Imported',row['project_number'],flush=True)
    with hub.db(True) as db:
        db.execute('DELETE FROM outbox');db.execute('DELETE FROM notifications');db.execute('DELETE FROM cp_notification_targets')
        # Do not replay years of overdue reminders immediately after migration.
        db.executemany('INSERT OR IGNORE INTO reminders VALUES(?,?)',[(r[0],date.today().isoformat()) for r in db.execute('SELECT id FROM items')])
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute("SELECT count(*) FROM items WHERE type='project'").fetchone()[0]==53
        assert db.execute('SELECT count(*) FROM qc_documents WHERE project_id IN (SELECT id FROM items WHERE type=\'project\')').fetchone()[0]==212
        assert db.execute('SELECT count(*) FROM qc_revisions r JOIN qc_documents d ON d.id=r.control_id JOIN items i ON i.id=d.project_id WHERE r.status!=\'draft\' OR r.approved_by IS NOT NULL OR r.reviewed_by IS NOT NULL').fetchone()[0]==0
    result={'source':str(source),'source_sha256':sha,'project_count':len(imported),'document_count':212,'documents_per_project':['FRD','Validation Test Report','FAT','Project Closure'],'created_users':created,'user_mapping':mapping,'delivery_managers':MANAGERS,'old_project_ids':old,'removed_rows':removed,'source_statuses':dict(Counter(r['status'] for r in rows)),'projects':imported,'hour_conversion':'Workbook Excel day fractions multiplied by 24; no imported time is marked approved.','document_notice':'Drafts only; no test executions, approvals or signatures fabricated.'}
    (folder/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--folder',type=Path,required=True)
    args=parser.parse_args();source=args.source.resolve();folder=args.folder.resolve()
    if folder.exists():raise RuntimeError('Choose a new staging folder to retain previous audit artifacts.')
    if not folder.is_relative_to(ROOT/'.build'):raise RuntimeError('Stage this migration inside the checkout .build folder.')
    rows=normalize(source);folder.mkdir(parents=True)
    shutil.copy2(source,folder/'sample.xlsx')
    (folder/'normalized.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
    before={}
    for relative in ['accounts.sqlite3','.usopp_workhub/projects.sqlite3']:
        src=ROOT/relative;copy_db(src,folder/'backup'/relative);before[relative]=fingerprint(folder/'backup'/relative)
        copy_db(folder/'backup'/relative,folder/'stage'/relative)
    (folder/'before-fingerprints.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
    result=build(source,folder,rows)
    print(json.dumps({k:result[k] for k in ['project_count','document_count','delivery_managers','source_statuses']},indent=2))

if __name__=='__main__':main()
