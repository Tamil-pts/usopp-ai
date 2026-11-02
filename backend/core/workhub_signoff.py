"""Authenticated review attestations over exact work/document and evidence snapshots."""
import hashlib
import json
import unicodedata
from fastapi import HTTPException
from .workhub import identity,timestamp,text


def history(db,subject_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='wh_review_stamps'").fetchone():return []
    return [{**dict(r),'evidence':json.loads(r['evidence'])} for r in db.execute(
        'SELECT * FROM wh_review_stamps WHERE subject_id=? ORDER BY recorded_at,id',(subject_id,))]


def record(db,user,payload,*,project_id,subject_id,subject_type,decision,role,basis,documents=()):
    raw=payload.get('sign_off')
    # Existing API integrations remain ordinary review records. Only this explicit
    # attestation protocol creates a sign-off stamp; none is inferred or fabricated.
    if raw is None:return None
    if decision not in {'approve','request_changes','reject'}:raise HTTPException(400,'Sign-off applies to a review decision.')
    if not isinstance(raw,dict):raise HTTPException(400,'Provide structured sign-off confirmation.')
    name=text(raw.get('name',''),160)
    normalize=lambda value:unicodedata.normalize('NFKC',value).strip().casefold()
    if decision=='approve':
        if normalize(name)!=normalize(user['username']):raise HTTPException(400,'Confirm the signed-in account name exactly.')
        if raw.get('acknowledged') is not True:raise HTTPException(400,'Confirm that you reviewed the selected evidence before signing.')
    comment=text(payload.get('comment',''),4000)
    if decision!='approve' and not comment.strip():raise HTTPException(400,'Review remarks are required for changes or rejection.')
    ids=raw.get('issue_ids',[])
    if not isinstance(ids,list) or len(ids)>200 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):raise HTTPException(400,'Select distinct project issue IDs.')
    references=raw.get('documents',[])
    if not isinstance(references,list) or len(references)>200:raise HTTPException(400,'Select up to 200 exact document revisions.')
    selected=list(documents);seen={(d['document_id'],d['revision_id']) for d in selected}
    from .workhub_approval_documents import document
    from .workhub_quality.store import project
    for ref in references:
        if not isinstance(ref,dict) or not isinstance(ref.get('document_id'),str) or not isinstance(ref.get('revision_id'),str):raise HTTPException(400,'Select a document and its revision.')
        d=document(db,ref['document_id'],ref['revision_id'])
        if project_id not in {d['scope_id'],d['linked_project_id']}:raise HTTPException(400,'Select evidence belonging or linked to this project.')
        project(db,d['scope_id'],user)
        key=(d['document_id'],d['revision_id'])
        if key not in seen:selected.append(d);seen.add(key)
    issues=[]
    for key in ids:
        row=db.execute('SELECT * FROM issues WHERE id=? AND project_id=?',(key,project_id)).fetchone()
        if not row:raise HTTPException(400,'Select issues belonging to this project.')
        issues.append(dict(row))
    evidence={'documents':selected,'issues':issues,'basis':basis}
    encoded=json.dumps(evidence,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    db.execute('''CREATE TABLE IF NOT EXISTS wh_review_stamps(
        id TEXT PRIMARY KEY,project_id TEXT NOT NULL,subject_id TEXT NOT NULL,subject_type TEXT NOT NULL,
        actor_id INTEGER NOT NULL,account_name TEXT NOT NULL,confirmed_name TEXT NOT NULL,designated_role TEXT NOT NULL,
        decision TEXT NOT NULL,remarks TEXT NOT NULL,acknowledged INTEGER NOT NULL,evidence TEXT NOT NULL,
        evidence_hash TEXT NOT NULL,recorded_at TEXT NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS wh_review_stamp_subject ON wh_review_stamps(subject_id,recorded_at)')
    key=identity();now=timestamp()
    db.execute('INSERT INTO wh_review_stamps VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (key,project_id,subject_id,subject_type,user['id'],user['username'],name if decision=='approve' else user['username'],role,
         decision,comment,int(decision=='approve'),encoded,hashlib.sha256(encoded.encode()).hexdigest(),now))
    return {'id':key,'actor_id':user['id'],'account_name':user['username'],'decision':decision,'recorded_at':now}
