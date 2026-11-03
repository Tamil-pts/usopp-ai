"""Prepare an isolated, explicitly fictional WorkHub demo from sample.xlsx.

Never replaces live data. The checked stage can be installed offline after backing
up the live databases and WorkHub directory. Original dates are never shifted.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from import_sample_project_report import normalize, person, copy_db, FIELDS, DATE_FIELDS

NOTICE = ('DEMO ONLY - FICTIONAL WORKFLOW. Based on the supplied historical project register. '
          'Test outcomes, review actions and handover below are sample records, not physical '
          'machine tests, employee assessments, customer acceptance or human signatures.')


def original_rows(source):
    from openpyxl.utils.datetime import from_excel, WINDOWS_EPOCH
    rows = normalize(source)
    for row in rows:
        notes = [n for n in row['notes'] if 'auto-filled' not in n and 'defaults to' not in n
                 and 'planning default' not in n and 'Recovered actual start' not in n
                 and 'Planning sequence conflict' not in n]
        for field in DATE_FIELDS:
            value = row['raw'][FIELDS.index(field)]
            if type(value) in (int, float) and 30000 <= value <= 60000:
                row[field] = from_excel(value, WINDOWS_EPOCH).date().isoformat()
            elif isinstance(value, str) and len(value) == 10 and value[4:5] == '-':
                row[field] = value
            else:
                row[field] = ''
                if value is not None: notes.append(f'{field}: source value {value!r} is not a valid date; left blank.')
        # The expanded row has no reliable planned duration or actual-start field.
        if row['row'] == 4: row['execution_days'] = None
        row['start_date'] = row['planned_start'] or row['actual_start']
        row['due_date'] = row['planned_delivery'] or row['lmw_target_date'] or row['actual_delivery']
        row['planned_hours'] = row['estimated_hours'] or row['lmw_target_hours'] or 0
        row['notes'] = notes
    return rows


def prepare(source, folder, limit=0):
    if folder.exists(): raise RuntimeError('Use a new stage folder; existing demo artifacts are retained.')
    if not folder.is_relative_to(ROOT / '.build'): raise RuntimeError('Stage inside the checkout .build directory.')
    folder.mkdir(parents=True)
    stage = folder / 'stage'; stage.mkdir()
    rows = original_rows(source)
    if limit: rows = rows[:limit]
    (folder / 'normalized.json').write_text(json.dumps(rows, indent=2), encoding='utf8')
    (folder / 'sample.xlsx').write_bytes(source.read_bytes())
    copy_db(ROOT / 'accounts.sqlite3', stage / 'accounts.sqlite3')
    with sqlite3.connect(stage / 'accounts.sqlite3') as db:
        old_max = db.execute('SELECT MAX(id) FROM users').fetchone()[0]
        db.execute("DELETE FROM users WHERE username_key!='admin' AND is_demo=0")
        db.execute('DELETE FROM sessions'); db.execute('DELETE FROM login_attempts')
        db.execute('DELETE FROM resource_owners WHERE user_id NOT IN (SELECT id FROM users)')
    os.environ['USOPP_DATA_ROOT'] = str(stage)
    os.environ['USOPP_PI_CHILD'] = '1'
    os.environ['USOPP_PI_WORKER_MODE'] = 'external'
    from backend.core import accounts, workhub_workspace as workspace, workhub_organization as org
    from backend.core import workhub_planning as planning, workhub_approval_documents as attached
    from backend.core.workhub import store as hub, NEXT_OWNER, timestamp
    from backend.core.workhub_quality import store as qc, documents, service, checks, authoring
    from backend.core.workhub_intelligence.documents import generated_file
    from backend.core.workhub_dashboards import store as dashboards, data as queries
    from backend.core.workhub_praxis import store as praxis, outcomes
    qc.initialize(); org.initialize(); dashboards.initialize(); praxis.initialize()
    admin = next(u for u in accounts.store.list_users() if u['username'].casefold() == 'admin')
    # Retain shared procedures, numbering and branding; never copy old projects,
    # personal dashboards, assignments, approvals or employee profiles.
    with sqlite3.connect(ROOT / '.usopp_workhub/projects.sqlite3') as old, hub.db(True) as db:
        for table in ('qc_settings', 'qc_sequences', 'wh_brand_records', 'wh_brand_assets', 'wh_brand_defaults'):
            columns = [r[1] for r in old.execute(f'PRAGMA table_info({table})')]
            if not columns: continue
            values = old.execute(f'SELECT * FROM {table}').fetchall()
            db.executemany(f'INSERT OR REPLACE INTO {table} ({",".join(columns)}) VALUES({",".join("?" for _ in columns)})', values)
    names = sorted({person(r[k]) for r in rows for k in ('planned_engineer', 'actual_engineer', 'qc_engineer') if person(r[k])})
    people = {}; credentials = []
    for index, name in enumerate(names):
        password = secrets.token_urlsafe(24)
        user = accounts.store.register(name + ' (Demo)', password, 'Demo engineer / reviewer', 'FICTIONAL DEMO')
        uid = old_max + index + 1
        with accounts.store.db() as db: db.execute('UPDATE users SET id=? WHERE id=?', (uid, user['id']))
        user['id'] = uid; people[name] = user
        credentials.append({'username': user['username'], 'password': password, 'id': uid})
    # A dedicated review identity makes independence visible even where the
    # workbook names the same engineer as both developer and QC reviewer.
    review_password=secrets.token_urlsafe(24)
    reviewer = accounts.store.register('Independent Reviewer (Demo)', review_password, 'Demo independent reviewer', 'FICTIONAL DEMO')
    if reviewer['id'] <= old_max:
        with accounts.store.db() as db: db.execute('UPDATE users SET id=? WHERE id=?', (old_max + len(names) + 1, reviewer['id']))
        reviewer['id'] = old_max + len(names) + 1
    people['Independent Reviewer'] = reviewer
    credentials.append({'username':reviewer['username'],'password':review_password,'id':reviewer['id']})
    (folder / 'demo-credentials.json').write_text(json.dumps(credentials, indent=2), encoding='utf8')
    users = {u['id']:u for u in [admin, *people.values()]}
    dept = org.save_unit(admin, {'kind':'department','name':'Demonstration Engineering','version':0})['id']
    role = org.save_unit(admin, {'kind':'role','name':'Demo engineer / reviewer','department_id':dept,'version':0})['id']
    team = org.save_unit(admin, {'kind':'team','name':'Historical Excel Demo','department_id':dept,'version':0,
                                'member_ids':[admin['id'],*[u['id'] for u in people.values()]],'manager_ids':[admin['id']]})['id']
    for u in people.values():
        with hub.db() as db: previous=org.profile(db,u['id'])
        org.save_profile(admin, u['id'], {'version':previous['version'],'department_id':dept,'role_id':role,'manager_id':admin['id'],
          'team_ids':[team],'daily_hours':8,'workdays':5,'availability_note':NOTICE})

    def item(key):
        with hub.db() as db: return hub.item(db, key)

    def transition(key, action, **extra):
        p = item(key)
        return hub.transition(users[p[NEXT_OWNER[p['stage']]]], key,
          {'version':p['version'],'action':action,'comment':NOTICE,'revision_id':None, **extra})

    def current(pid, kind): return service.get_document(admin, pid, kind)['revision']

    def action(pid, kind, verb, who, **extra):
        r = current(pid, kind)
        return service.action(who, pid, kind, {'version':r['version'],'revision_id':r['id'],
          'action':verb,'comment':NOTICE,'checklist':{k:True for k in ('documents','requirements','tests','fat','issues','approvals')}, **extra})

    def approve(pid, kind, owner, review, pending=False):
        action(pid, kind, 'confirm', owner); action(pid, kind, 'submit', owner)
        if not pending: action(pid, kind, 'approve', review)

    imported = []; allocated = defaultdict(int); hour_notes = []
    for index, row in enumerate(rows):
        owner = people[row['owner']]; review = people.get(person(row['qc_engineer']), reviewer)
        if review['id'] == owner['id']: review = reviewer
        scope = row['description'] + '\nMachine: ' + row['machine'] + '; software: ' + row['software'] + ' ' + row['software_version']
        fields = [{'label':'Source '+key.replace('_',' ').title(),'type':'text','value':str(row[key] if row[key] is not None else '')} for key in FIELDS]
        fields += [{'label':'Import warnings','type':'text','value':'\n'.join(row['notes'])},
                   {'label':'Source row','type':'text','value':row['source_range']}]
        steps = [{'id':key,'title':'DEMO '+title,'description':NOTICE,'phase':phase,'days':1,'planned_hours':row['planned_hours'] if key=='development' else 0,
                  'depends_on':[before] if before else [],'milestone':key in {'validation','closure'}} for key,title,phase,before in (
          ('requirements','Requirements','development',''),('development','Development','development','requirements'),
          ('validation','Validation review','quality','development'),('fat','FAT review','quality','validation'),('closure','Handover','release','fat'))]
        p = workspace.create(admin, {'workspace_schema':3,'title':'DEMO '+row['project_number']+' - '+row['description'][:145],
          'project_number':row['project_number'],'kind':'B&R PLC' if row['software']=='B&R' else 'Other PLC',
          'is_sample':True,'description':NOTICE+'\n'+scope,'owner_id':owner['id'],'quality_id':review['id'],
          'approver_id':reviewer['id'],'release_id':review['id'],'start_date':row['start_date'],'due_date':row['due_date'],
          'customer':'DEMO customer - not actual acceptance','machine':row['machine'],'scope':scope,
          'custom_fields':fields,'responsibility':'Demo development: '+owner['username']+'; independent review: '+review['username'],
          'additional_information':NOTICE+'\n'+'\n'.join(row['notes']),'workflow_steps':steps,
          'workflow_assignees':{'requirements':owner['id'],'development':owner['id'],'validation':review['id'],'fat':review['id'],'closure':review['id']}})
        pid = p['id']
        with hub.db() as db: tasks = {r['step_id']:r['task_id'] for r in db.execute('SELECT * FROM wh_workflow_steps WHERE project_id=?',(pid,))}
        # Creation's relative step dates are planning conveniences. Use only
        # supplied historical boundaries in this requested demo.
        with hub.db(True) as db:
            db.execute('UPDATE items SET start_date=?,due_date=?,baseline_due=? WHERE project_id=?', (row['start_date'],row['due_date'],row['due_date'],pid))
            db.execute('UPDATE project_phases SET start_date=?,due_date=?,baseline_due=? WHERE project_id=?',(row['start_date'],row['due_date'],row['due_date'],pid))
        evidence = generated_file(owner,pid,'DEMO-ONLY-evidence.txt',(NOTICE+'\n'+scope+'\nSource status: '+row['status']+'\nFixture: scope reference retained; demonstration review and revision links checked.').encode())['id']
        workbook_file = generated_file(admin,pid,'sample.xlsx',source.read_bytes())['id']
        src = {'id':'EXCEL-ROW','type':'project_report','label':row['source_range'],'file_id':workbook_file,
               'text':json.dumps({k:row[k] for k in FIELDS})}
        fixture = {'id':'DEMO-FIXTURE','type':'manual_brief','label':'Fictional workflow fixture','file_id':evidence,'text':NOTICE}
        reqs = [
          {'id':'FR-001','title':'DEMO scope traceability','description':scope,'expected_behavior':'The demonstration record retains the supplied project identity and scope.',
           'acceptance_criteria':'The source project number and description are linked to this demo record.','source_ids':['EXCEL-ROW'],'mandatory':True},
          {'id':'FR-002','title':'DEMO review and evidence continuity','description':NOTICE,'expected_behavior':'The fictional reviewer checks the saved report revision and its demonstration evidence.',
           'acceptance_criteria':'Demo evidence and the exact saved report revision remain linked through review.','source_ids':['DEMO-FIXTURE'],'mandatory':True}]
        base = {'summary':NOTICE+'\n'+scope,'sources':[src,fixture],'file_ids':[evidence,workbook_file]}
        documents.draft(owner,pid,'frd',{**base,'purpose':NOTICE,'scope':scope,'requirements':reqs,
          'sections':[{'heading':'Deliverables','text':'DEMO evidence and source reference\nDEMO validation, FAT and handover records'},
                      {'heading':'Engineering boundary','text':'Exact machine sequences, safety functions and physical test results are not supplied. This FRD defines a demonstration of document traceability only.'}]})
        approve(pid,'frd',owner,review)
        documents.draft(owner,pid,'corrections',{**base,'sections':[{'heading':'Demonstration correction','text':NOTICE}],
          'changes':[{'id':'CN-001','summary':'DEMO check report evidence links','existing_behavior':'Fictional draft has an incomplete evidence description.',
                     'expected_behavior':'Demonstration report contains the source row and fixture reference.','impact':'Demo documents only.',
                     'before_evidence':NOTICE,'after_evidence':'DEMO-ONLY-evidence.txt','verification':'Review saved report links.',
                     'source_ids':['DEMO-FIXTURE'],'requirement_ids':['FR-002']}]})
        approve(pid,'corrections',owner,review)
        for kind in ('test','fat'):
            r = current(pid,kind);content = r['content'];prior_sources=content.get('sources',[])
            content.update(base);content['sources']=[*prior_sources,src,fixture]
            content['report_date'] = row['actual_delivery'] or row['planned_delivery'] or ''
            documents.save(owner,pid,kind,{'version':r['version'],'revision_id':r['id'],'content':content})
        documents.draft(owner,pid,'quality',base)
        documents.draft(owner,pid,'closure',{**base,'sections':[{'heading':'Final deliverables','text':NOTICE+'\nDemo source reference, FRD, validation and FAT records.'},
          {'heading':'Handover information','text':NOTICE+'\nOriginal Excel dates retained; no actual equipment handover is claimed.'}]})

        # Allocate reported totals over original dated weekdays for visualization.
        # Missing/contradictory values stay in source fields, never billed as fact.
        start = row['actual_start'] or row['planned_start']; end = row['actual_delivery'] or row['planned_delivery']
        minutes = round((row['engineer_hours'] if row['engineer_hours'] is not None else row['actual_hours'] or 0)*60)
        remaining = minutes
        if start and end and start <= end:
            d = date.fromisoformat(start); last = date.fromisoformat(end)
            while d <= last and remaining:
                key = (owner['id'],d.isoformat()); amount = min(remaining,max(0,480-allocated[key])) if d.weekday()<5 else 0
                if amount:
                    hub.add_update(owner,tasks['development'],{'body':NOTICE+' DEMO allocation of workbook total hours across original weekdays; not an original daily timesheet or billing approval.',
                      'work_date':d.isoformat(),'minutes':amount,'file_ids':[evidence]})
                    allocated[key] += amount;remaining -= amount
                d += timedelta(days=1)
        if remaining: hour_notes.append({'project':row['project_number'],'unallocated_hours':remaining/60,'reason':'Missing/conflicting dates or insufficient historical weekday capacity; source total retained.'})

        completed = row['status'].casefold() in {'completed','completed by customer'}
        validation = row['status'].casefold() == 'in-qc'
        transition(pid,'start')
        transition(tasks['requirements'],'start');transition(tasks['requirements'],'complete_development')
        transition(tasks['development'],'start')
        sprint = None
        if index < 8 and row['start_date'] and row['due_date'] and row['start_date'] <= row['due_date'] and (date.fromisoformat(row['due_date'])-date.fromisoformat(row['start_date'])).days <= 90:
            with hub.db(True) as db: db.execute("UPDATE items SET methodology='sprint' WHERE id=?",(pid,))
            planning.save_sprint(hub,admin,pid,{'title':'DEMO historical delivery sprint','goal':NOTICE,'owner_id':owner['id'],
              'start_date':row['start_date'],'due_date':row['due_date'],'status':'active'})
            with hub.db(True) as db:
                sprint = dict(db.execute('SELECT * FROM sprints WHERE project_id=?',(pid,)).fetchone())
                db.execute('UPDATE items SET sprint_id=? WHERE id IN (?,?)',(sprint['id'],tasks['requirements'],tasks['development']))
        if completed or validation:
            transition(tasks['development'],'complete_development')
            transition(pid,'complete_development',deliverables_complete=True,deliverable_file_ids=[evidence])
            for kind in ('test','fat'):
                for case in current(pid,kind)['content']['cases']:
                    r = current(pid,kind)
                    documents.execute(owner,pid,kind,{'version':r['version'],'revision_id':r['id'],'case_id':case['id'],
                      'outcome':'pass','actual':NOTICE+' Demonstration fixture satisfies: '+case['expected_result'],
                      'observations':NOTICE,'file_ids':[evidence]})
                if kind == 'fat':
                    r=current(pid,kind)
                    documents.acceptance(owner,pid,kind,{'version':r['version'],'revision_id':r['id'],'status':'accepted',
                      'customer':'FICTIONAL DEMO CUSTOMER','representative':'FICTIONAL DEMO REPRESENTATIVE','accepted_at':timestamp(),'file_ids':[evidence],'remarks':NOTICE})
                approve(pid,kind,owner,review,pending=validation)
                if completed and index == 4 and kind == 'test':
                    # A controlled rejection and revalidation example, without
                    # overwriting the first report or creating human sign-offs.
                    old=current(pid,kind)
                    service.new_revision(owner,pid,kind,{'revision_id':old['id'],'reason':NOTICE+' Demonstrate a corrected report revision.'})
                    action(pid,kind,'confirm',owner);action(pid,kind,'submit',owner);action(pid,kind,'request_corrections',review)
                    old=current(pid,kind)
                    service.new_revision(owner,pid,kind,{'revision_id':old['id'],'reason':NOTICE+' Revalidation after sample correction.'})
                    for case in current(pid,kind)['content']['cases']:
                        r=current(pid,kind)
                        documents.execute(owner,pid,kind,{'version':r['version'],'revision_id':r['id'],'case_id':case['id'],'outcome':'pass',
                          'actual':NOTICE+' Sample correction rechecked.','observations':NOTICE,'file_ids':[evidence]})
                    approve(pid,kind,owner,review)
            with hub.db(True) as db:
                d = qc.control(db,pid,'test'); attached.attach(db,hub.item(db,pid),owner,[{'document_id':d['document_id'],'revision_id':current(pid,'test')['id']}])
            transition(pid,'submit_quality',deliverables_complete=True,deliverable_file_ids=[evidence])
            if completed:
                for key in ('validation','fat'):
                    transition(tasks[key],'start');transition(tasks[key],'complete_development')
                with hub.db() as db: baseline=checks.baseline(db,hub.item(db,pid))
                documents.draft(owner,pid,'quality',base,baseline=baseline,generated_by='revision:demo-'+secrets.token_hex(8))
                approve(pid,'quality',owner,review)
                if item(pid)['stage']=='quality': transition(pid,'quality_pass')
                transition(pid,'approve_release',work_feedback={'quality':'none','problem_solving':'supported','response':'prompt',
                  'errors_corrected':1,'troubleshooting_cases':1,'solutions_shared':0,'colleagues_helped':0,'comment':NOTICE})
                transition(tasks['closure'],'start');transition(tasks['closure'],'complete_development')
                with hub.db() as db: baseline=checks.baseline(db,hub.item(db,pid),True)
                documents.draft(owner,pid,'closure',{**base,'sections':[{'heading':'Final deliverables','text':NOTICE},
                  {'heading':'Handover information','text':NOTICE+' Fictional handover complete; original source status: '+row['status']}]},baseline=baseline,generated_by='revision:demo-'+secrets.token_hex(8))
                approve(pid,'closure',owner,review)
                if sprint:
                    planning.save_sprint(hub,admin,pid,{**sprint,'status':'closed'},sprint['id'])
                transition(pid,'release',closure_checks={k:True for k in ('final_deliverables','handover','required_acceptance')})
        else:
            transition(pid,'block')
            with hub.db(True) as db:
                db.execute('UPDATE items SET exception_status=?,exception_reason=? WHERE id=?',
                  ('cancelled' if 'withdrawn' in row['status'].casefold() else 'on_hold',NOTICE+' Source status: '+row['status'],pid))
        with hub.db(True) as db:
            hub.event(db,hub.item(db,pid),admin,'excel_demo_created',{'notice':NOTICE,'source_range':row['source_range'],'original_status':row['status'],
              'original_dates':{k:row[k] for k in DATE_FIELDS},'dates_shifted':False,'human_signatures_generated':False})
            # Optional package-generation jobs are not required for this fixture.
            # Cancel before deployment so no queued work can rewrite demo drafts.
            db.execute("UPDATE pi_jobs SET status='cancelled',error='Demo prepared directly; optional package jobs not executed.' WHERE project_id=? AND status='queued'",(pid,))
        imported.append({'id':pid,'number':row['project_number'],'owner':owner['id'],'stage':item(pid)['stage'],'source_status':row['status'],'sprint':sprint['id'] if sprint else None})
        print('Prepared '+row['project_number']+' -> '+item(pid)['stage'],flush=True)

    # Work-scoring remains unchanged: sample projects only appear in an explicit
    # sample-project preview, never in real employee indices.
    with hub.db() as db: cfg=praxis.configuration(db)
    today=date.today().isoformat()
    praxis.save_configuration(admin,{'version':cfg['version'],'content':{**cfg['content'],
      'periods':[{'id':'demo-preview','name':'DEMO workflow preview (actions recorded now)','start':today,'end':today,'active':True},
                 {'id':'historical-excel','name':'Original Excel history 2023-2025','start':'2023-01-01','end':'2025-12-31','active':True}]}})

    def widget(key,kind,title,source='projects',metric='id',aggregation='count',filters=None,dimensions=None,**extra):
        return {'id':key,'type':kind,'title':title,'query':{'source':source,'dimensions':dimensions or [],'metrics':[{'field':metric,'aggregation':aggregation}],
          'filters':[{'field':'dataset','op':'eq','value':'Sample'},*(filters or [])],'limit':500},**extra}
    days=sorted({d for _,d in allocated});anchor=days[-1] if days else '2025-01-01';week=(date.fromisoformat(anchor)-timedelta(days=date.fromisoformat(anchor).weekday())).isoformat()
    widgets=[widget('notice','text','Demo data and original dates',text=NOTICE+' Daily and weekly hours are labelled demo allocations of workbook totals, not original daily timesheets. No dates were shifted. Missing dates/hours remain unknown. Select a sample project in Competency Hub for a fictional preview.'),
      widget('day','kpi','Demo hours | '+anchor,'time_entries','hours','sum',[{'field':'date','op':'eq','value':anchor}],appearance={'format':'hours','decimals':1}),
      widget('week','kpi','Demo hours | week of '+week,'time_entries','hours','sum',[{'field':'date','op':'gte','value':week},{'field':'date','op':'lte','value':anchor}],appearance={'format':'hours','decimals':1}),
      *[widget(key,'kpi',label,filters=[{'field':'delivery_group','op':'eq','value':label}]) for key,label in [('completed','Completed'),('ongoing','Ongoing'),('upcoming','Upcoming')]],
      widget('states','bar','Demo projects by delivery group',dimensions=[{'field':'delivery_group','grain':'value'}]),
      widget('daily','bar','Demo allocated hours by original day','time_entries','hours','sum',dimensions=[{'field':'date','grain':'day'}],appearance={'format':'hours','decimals':1}),
      widget('weekly','bar','Demo allocated hours by original week','time_entries','hours','sum',dimensions=[{'field':'date','grain':'week'}],appearance={'format':'hours','decimals':1})]
    layouts={}
    for bp,cols in [('desktop',12),('tablet',8),('mobile',4)]:
        if bp=='desktop':
            boxes=[(0,0,12,5),(0,5,6,3),(6,5,6,3),(0,8,4,3),(4,8,4,3),(8,8,4,3),
                   (0,11,12,7),(0,18,6,8),(6,18,6,8)]
            layouts[bp]=[dict(i=w['id'],x=x,y=y,w=width,h=h) for w,(x,y,width,h) in zip(widgets,boxes)]
            continue
        y=0;positions=[]
        for w in widgets:
            h=5 if w['type']=='text' else 3 if w['type']=='kpi' else 8
            width=cols if w['type']!='kpi' or bp=='mobile' else cols//2
            positions.append({'i':w['id'],'x':0,'y':y,'w':width,'h':h});y+=h
        layouts[bp]=positions
    dash=dashboards.save(admin,{'configuration':{'name':'DEMO MIS | Historical Excel','widgets':widgets,'layouts':layouts}})
    with hub.db(True) as db:
        db.execute('INSERT OR REPLACE INTO wh_dashboard_defaults VALUES(?,?)',(admin['id'],dash['id']))
        db.execute("UPDATE outbox SET status='disabled',detail='Fictional demo; in-app only.' WHERE status NOT IN ('sent','delivered')")
        db.executemany('INSERT OR IGNORE INTO reminders VALUES(?,?)',[(r[0],today) for r in db.execute('SELECT id FROM items')])
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    metrics={w['id']:queries.execute(admin,w['query']) for w in dash['configuration']['widgets'] if w['type']!='text'}
    result={'complete':True,'notice':NOTICE,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'stage':str(stage),'dates_shifted':False,
      'projects':imported,'project_count':len(imported),'users':[{k:u[k] for k in ('id','username')} for u in people.values()],
      'preserved_accounts':['Admin','built-in demo'],'dashboard':dash['id'],'metrics':metrics,'hour_warnings':hour_notes,
      'source_statuses':dict(Counter(r['status'] for r in rows))}
    completed_project=next((p for p in imported if p['stage']=='released'),None)
    if completed_project:
        preview=outcomes.profile(admin,completed_project['owner'],'demo-preview',completed_project['id'])
        assert preview['sample_preview'] and preview['competency_index'] is not None
        result['competency_preview']={'project_id':completed_project['id'],'subject_id':completed_project['owner'],'index':preview['competency_index'],'sample_preview':True}
    (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({'complete':True,'project_count':len(imported),'dashboard':dash['id'],'stage':str(stage)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=0,help='Prepare only the first N rows for an isolated pilot.')
    args=parser.parse_args();prepare(args.source.resolve(),args.folder.resolve(),args.limit)
