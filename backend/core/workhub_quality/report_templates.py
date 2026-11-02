"""Default Validation/FAT forms and explicit, project-scoped source imports."""
from datetime import date
from fastapi import HTTPException
from . import store
from .store import hub,pi,text

def clean(db,pid,content,result):
    result['report_type']=content.get('report_type','')
    for key in ('purpose','scope','conclusion'):result[key]=text(content.get(key) or '',12000)
    value=content.get('report_date') or ''
    if value:
        try:date.fromisoformat(value)
        except (ValueError,TypeError):raise HTTPException(400,'Use an ISO report date.') from None
    result['report_date']=value
    from .documents import _list,file_ids
    references=[];seen=set()
    for i,r in enumerate(_list(content.get('references',[]),200)):
        if not isinstance(r,dict):raise HTTPException(400,'Provide structured reference documents.')
        key=text(r.get('id') or 'REF-'+str(i+1).zfill(3),80,True)
        if key in seen:raise HTTPException(400,'Reference documents need unique IDs.')
        seen.add(key);row={'id':key,**{k:text(r.get(k) or '',500) for k in ('title','number','revision','date')}}
        if r.get('control_id'):
            control=store.control(db,pid,r['control_id']);revision=store.revision(db,control['id'],r.get('revision_id'))
            row.update(control_id=control['id'],revision_id=revision['id'],number=control['number'],revision=revision['label'],date=revision['created_at'][:10])
        if r.get('file_id'):row['file_id']=file_ids(db,pid,[r['file_id']])[0]
        references.append(row)
    result['references']=references;issues=[];seen=set()
    for i,r in enumerate(_list(content.get('report_issues',[]),500)):
        if not isinstance(r,dict):raise HTTPException(400,'Provide structured issue and correction rows.')
        key=text(r.get('id') or 'ISS-'+str(i+1).zfill(3),80,True)
        if key in seen:raise HTTPException(400,'Report issues need unique IDs.')
        seen.add(key)
        status=r.get('status','open')
        if status not in {'open','corrected','retest_pending','closed'}:raise HTTPException(400,'Choose a valid report issue status.')
        issues.append({'id':key,**{k:text(r.get(k) or '',8000) for k in ('description','correction','retest_result')},'status':status})
    result['report_issues']=issues
    return result

def seed_frd(db,pid,stage,content,required=False):
    from . import checks
    raw=db.execute("SELECT * FROM qc_documents WHERE project_id=? AND stage='frd'",(pid,)).fetchone()
    doc=dict(raw) if raw else None;rid=store.native(db,doc)['approved_revision'] if doc else None
    if not rid:
        if required:raise HTTPException(409,'Approve the project FRD before importing its requirements.')
        return None,0
    rev=store.revision(db,doc['id'],rid);frd=pi.revision(db,rid,doc['document_id'])['content']
    source='FRD-'+rid
    if not any(s['id']==source for s in content.get('sources',[])):
        content.setdefault('sources',[]).append({'id':source,'type':'frd_revision','label':doc['number']+' / '+rev['label'],'text':'Source SHA-256 '+rev['content_hash'],'revision_id':rid,'sha256':rev['content_hash']})
    reference={'id':source,'title':'Functional Requirements Document (FRD)','number':doc['number'],'revision':rev['label'],'date':rev['created_at'][:10],'control_id':doc['id'],'revision_id':rid}
    if not any(r.get('id')==source for r in content.get('references',[])):content.setdefault('references',[]).append(reference)
    for related_stage in (['test'] if stage=='fat' else ['corrections']):
        raw=db.execute('SELECT * FROM qc_documents WHERE project_id=? AND stage=?',(pid,related_stage)).fetchone()
        if not raw:continue
        related=dict(raw);related_id=store.native(db,related)['approved_revision']
        if not related_id:continue
        related_rev=store.revision(db,related['id'],related_id);ref_id='DOC-'+related_id
        if not any(r.get('id')==ref_id for r in content.get('references',[])):
            content['references'].append({'id':ref_id,'title':'Validation Test Report' if related_stage=='test' else 'Correction Notes','number':related['number'],'revision':related_rev['label'],'date':related_rev['created_at'][:10],'control_id':related['id'],'revision_id':related_id})
    content['purpose']=content.get('purpose') or frd.get('purpose') or frd.get('summary') or ''
    content['scope']=content.get('scope') or frd.get('scope') or ''
    cases=content.setdefault('cases',[]);linked={key for c in cases for key in c.get('requirement_ids',[])};added=0
    for r in frd.get('requirements',[]):
        if r.get('change')=='removed_proposed' or r['id'] in linked:continue
        prefix='FAT-' if stage=='fat' else 'TC-';used={c['id'] for c in cases};n=1
        while prefix+str(n).zfill(3) in used:n+=1
        cases.append({'id':prefix+str(n).zfill(3),'objective':r.get('title') or r['id'],
            'procedure':r.get('description') or '', 'expected_result':r.get('expected_behavior') or r.get('acceptance_criteria') or '',
            'acceptance_criteria':r.get('acceptance_criteria') or '', 'requirement_ids':[r['id']],'source_ids':[source],'mandatory':r.get('mandatory',True)})
        linked.add(r['id']);added+=1
    return rid,added

def import_cases(user,pid,key,payload):
    from . import documents,checks
    store.initialize()
    with hub.db(True) as db:
        doc=store.control(db,pid,key);rev=store.revision(db,doc['id'],payload.get('revision_id'))
        store.editable(db,doc,rev,user,payload.get('version'))
        if doc['stage'] not in {'test','fat'}:raise HTTPException(400,'Import test cases into Validation or FAT reports.')
        content=pi.revision(db,rev['id'],doc['document_id'])['content'];source=payload.get('source','frd');added=0
        if source=='frd':
            raw=db.execute("SELECT * FROM qc_documents WHERE project_id=? AND stage='frd'",(pid,)).fetchone()
            current=store.native(db,dict(raw))['approved_revision'] if raw else None
            if rev['frd_revision_id'] and current!=rev['frd_revision_id']:raise HTTPException(409,'Create a new report revision for the updated approved FRD.')
            rid,added=seed_frd(db,pid,doc['stage'],content,True)
            db.execute('UPDATE qc_revisions SET frd_revision_id=? WHERE id=?',(rid,rev['id']))
        elif source=='validation':
            raw=db.execute('SELECT * FROM engineering_runs WHERE project_id=? AND run_id=?',(pid,payload.get('run_id'))).fetchone()
            if not raw:raise HTTPException(404,'Choose a validation run linked to this project.')
            run=dict(raw)
            if run['status'] not in {'completed','complete','succeeded','success','done','failed','error'}:raise HTTPException(409,'Finish the validation run before importing its results.')
            if not any(c.get('native_run_id')==run['run_id'] for c in content.get('cases',[])):
                prefix='FAT-' if doc['stage']=='fat' else 'TC-';used={c['id'] for c in content.get('cases',[])};n=1
                while prefix+str(n).zfill(3) in used:n+=1
                content.setdefault('cases',[]).append({'id':prefix+str(n).zfill(3),'objective':run['kind']+' validation / '+run['run_id'],
                    'procedure':'Review the linked validation output and verify its applicability to this project.',
                    'expected_result':'The linked validation has no failing findings.','acceptance_criteria':'Confirm the validation scope and requirement links.',
                    'requirement_ids':[],'source_ids':[],'mandatory':True,'native_run_id':run['run_id']});added=1
        else:raise HTTPException(400,'Choose approved FRD or project validation results.')
        content=documents.clean_content(db,pid,doc['stage'],content)
        result=documents._save(db,user,hub.item(db,pid),doc,rev,content,payload.get('version'))
        store.audit(db,user,pid,'report_cases_imported',{'source':source,'added':added},doc['id'],rev['id'])
        return {**result,'added':added,'notices':[str(added)+' test case(s) imported. Review their scope and requirement links.']}

def summary(content):
    cases=content.get('cases',[]);outcomes=[(c.get('execution') or {}).get('outcome') or c.get('outcome') or 'not_run' for c in cases]
    passed=outcomes.count('pass');failed=outcomes.count('fail');excluded=outcomes.count('not_applicable')
    return {'total':len(cases),'passed':passed,'failed':failed,'pending':len(cases)-passed-failed-excluded,'not_applicable':excluded}

def blocks(content,stage,acceptance=None,report_label=None):
    fat=stage=='fat';label=report_label or ('FAT' if fat else 'Validation');result=[]
    def add(key,title,body='',columns=None,rows=None):
        result.append({'key':key,'title':title,'text':body,'columns':columns or [],'rows':rows or [],'svg':''})
    old={r['heading']:r['text'] for r in content.get('sections',[])}
    add('purpose','3. '+label+' Objective & Scope',columns=['Field','Detail'],rows=[
        ['Objective',content.get('purpose') or old.get('FAT objective' if fat else 'Validation objective') or ''],
        ['Scope',content.get('scope') or old.get('Test scope' if fat else 'Validation scope') or '']])
    add('scope','4. Reference Documents',old.get('Reference documents',''),['Document Name','Document No.','Revision','Date'],[
        [r.get(k,'') for k in ('title','number','revision','date')] for r in content.get('references',[])])
    rows=[]
    for c in content.get('cases',[]):
        ex=c.get('execution') or {};native=c.get('source_result') or {}
        actual=ex.get('actual') or ('Linked validation '+native.get('run_id','')+' / '+native.get('outcome','') if native else '')
        rows.append([c['id'],', '.join(c.get('requirement_ids',[])),c.get('objective',''),c.get('expected_result',''),actual,
            (ex.get('outcome') or c.get('outcome') or 'not_run').replace('_',' ').title(),ex.get('observations','')])
    add('cases','5. '+('Test Results' if label=='Test' else label+' Test Results'),columns=['Test Case','Requirement ID','Description','Expected Result','Actual Result','Status','Remarks'],rows=rows)
    add('sections','6. '+('Issues & Observations' if fat else 'Issues & Corrections'),columns=['Issue','Description','Action / Correction','Retest Result','Status'],rows=[
        [r.get(k,'') for k in ('id','description','correction','retest_result','status')] for r in content.get('report_issues',[])])
    counts=summary(content)
    add('details','7. '+label+' Summary',columns=['Total','Passed','Failed','Pending','Not Applicable'],rows=[[counts[k] for k in ('total','passed','failed','pending','not_applicable')]])
    if fat:
        a=acceptance or {}
        add('details','8. Final Acceptance',columns=['Decision','Customer','Representative','Date','Remarks'],rows=[[
            {'accepted':'Accepted','conditional':'Conditionally Accepted','rejected':'Rejected'}.get(a.get('status'),'Not recorded'),a.get('customer',''),a.get('representative',''),a.get('accepted_at',''),a.get('remarks','')]])
    else:
        outcome='Not tested' if not counts['total'] else 'Fail' if counts['failed'] else 'Pending' if counts['pending'] else 'Pass' if counts['passed'] else 'Not applicable'
        add('details','8. Conclusion',label+' result: '+outcome+'\n'+(content.get('conclusion') or old.get('Conclusion') or ''))
    extras=[r for r in content.get('sections',[]) if r.get('text') and r['heading'] not in {'FAT objective','Validation objective','Test scope','Validation scope','Reference documents','Conclusion'}]
    if content.get('summary') or extras:add('sections','Additional report information',content.get('summary',''),['Section','Content'],[[r['heading'],r['text']] for r in extras])
    return result
