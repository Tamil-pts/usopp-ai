"""Private Q&A drafts and Admin-reviewed exports, separate from model weights."""
from datetime import datetime, timezone
import hashlib
import json
import threading
import uuid
from backend.core.persistent_store import db
from backend.core.runtime import RESOURCE_ROOT

LOCK = threading.RLock()
READY = False
PLAYBOOK = RESOURCE_ROOT / 'knowledge' / 'chopper' / 'engineering_tasks.json'


def _initialize():
    global READY
    with LOCK:
        if READY: return
        with db() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS assist_training_examples (
                    id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', revision INTEGER NOT NULL DEFAULT 1,
                    record_json TEXT NOT NULL, reviewed_by INTEGER, reviewed_at TEXT);
                CREATE INDEX IF NOT EXISTS assist_training_owner ON assist_training_examples(owner_id, created_at DESC);
            ''')
        READY = True


def playbook():
    return json.loads(PLAYBOOK.read_text(encoding='utf-8'))


def task_guidance(intent):
    data = playbook()
    return {'intent': intent, 'steps': data['tasks'].get(intent, data['tasks']['source lookup']),
            'responseStyle': data['responseStyle'], 'status': 'Backend task guidance; weight training is recorded separately in run manifests.'}


def capture(user, question, result, project_name):
    verification = result.get('engineeringVerification')
    if verification is not None and not verification.get('trainingEligible', False): return None
    if verification is None and (result.get('machineAnalysis') or result.get('semanticReviewRequired') or result.get('review')):
        return None
    evidence = result.get('evidence') or []
    if not user or not user.get('id') or not evidence or not result.get('answer'): return None
    _initialize()
    source = [{'file': e['file'], 'line': e.get('line', 1), 'excerpt': e.get('excerpt', ''),
               'sourceId': e.get('sourceId', f'S{n}'), 'ownership': e.get('ownership', 'unconfirmed'),
               **{k: e[k] for k in ('network', 'enabled') if k in e}} for n, e in enumerate(evidence, 1)]
    fingerprint = (result.get('projectAnalysis') or {}).get('sourceFingerprint')
    snapshot = json.dumps(source, ensure_ascii=False, sort_keys=True)
    record = {'id': uuid.uuid4().hex, 'question': str(question)[:20000], 'answer': str(result['answer'])[:30000],
              'projectName': str(project_name)[:200], 'projectFingerprint': fingerprint,
              'evidenceDigest': hashlib.sha256(snapshot.encode()).hexdigest(),
              'evidence': source, 'helpEvidence': result.get('helpEvidence') or [],
              'intent': (result.get('projectAnalysis') or {}).get('intent', 'source lookup'),
              'answerSource': result.get('source'), 'weightTrainingPerformed': False}
    encoded = json.dumps(record, ensure_ascii=False)
    if len(encoded.encode('utf-8')) > 160000: return None
    with db() as connection:
        connection.execute('INSERT INTO assist_training_examples (id,owner_id,created_at,record_json) VALUES (?,?,?,?)',
                           (record['id'], user['id'], datetime.now(timezone.utc).isoformat(), encoded))
    return record['id']


def records(user, limit=80):
    _initialize()
    with db() as connection:
        rows = connection.execute('SELECT * FROM assist_training_examples ' +
                                  ('' if user['role'] == 'admin' else 'WHERE owner_id=? ') + 'ORDER BY created_at DESC LIMIT ?',
                                  ((min(limit, 200),) if user['role'] == 'admin' else (user['id'], min(limit, 200)))).fetchall()
    return [{**json.loads(r['record_json']), 'ownerId': r['owner_id'], 'createdAt': r['created_at'],
             'status': r['status'], 'revision': r['revision'], 'reviewedBy': r['reviewed_by']} for r in rows]


def review(identifier, user, revision, status, answer):
    if status not in {'approved', 'rejected', 'pending'}: raise ValueError('Choose approved, rejected or pending.')
    answer = str(answer).strip()
    if not answer or len(answer) > 30000: raise ValueError('Enter a reviewed answer of at most 30,000 characters.')
    _initialize()
    with db() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT * FROM assist_training_examples WHERE id=?', (identifier,)).fetchone()
        if not row: raise LookupError('Training example not found.')
        if row['revision'] != revision: raise RuntimeError('Another reviewer changed this example. Reload before saving.')
        record = json.loads(row['record_json']); record['answer'] = answer
        if status == 'approved':
            from python_engine.project_knowledge import explanation_reference_issue
            issue = explanation_reference_issue(answer, record['evidence'], help_evidence=record['helpEvidence'])
            if issue: raise ValueError('Correct the source citations before approval: ' + issue + '. Cite supplied [S1] / [H1] IDs.')
        connection.execute('UPDATE assist_training_examples SET status=?,revision=revision+1,record_json=?,reviewed_by=?,reviewed_at=? WHERE id=?',
                           (status, json.dumps(record, ensure_ascii=False), user['id'], datetime.now(timezone.utc).isoformat(), identifier))


def summary(user):
    _initialize()
    with db() as connection:
        rows = connection.execute('SELECT status,count(*) FROM assist_training_examples ' +
                                  ('' if user['role'] == 'admin' else 'WHERE owner_id=? ') + 'GROUP BY status',
                                  (() if user['role'] == 'admin' else (user['id'],))).fetchall()
    counts = dict(rows)
    return {'counts': counts, 'weightsTrained': False, 'mode': 'Task analysis + source retrieval + reviewed training drafts',
            'notice': 'Approval saves a training example. It does not run training or replace the installed model.',
            'tasks': list(playbook()['tasks']), 'baseModel': 'Qwen/Qwen2.5-Coder-1.5B-Instruct'}


def export_examples():
    _initialize()
    seen = set()
    system = playbook()['trainingSystem']
    cursor = ''
    while True:
        # Close each connection before yielding: StreamingResponse may resume
        # this synchronous generator on another worker thread.
        with db() as connection:
            rows = connection.execute("SELECT * FROM assist_training_examples WHERE status='approved' AND id>? ORDER BY id LIMIT 80", (cursor,)).fetchall()
        if not rows: return
        cursor = rows[-1]['id']
        for row in rows:
            record = json.loads(row['record_json'])
            project_name = record.get('projectName', '').strip().casefold()
            group = hashlib.sha256(project_name.encode()).hexdigest() if project_name else record.get('projectFingerprint') or record['evidenceDigest']
            key = hashlib.sha256(json.dumps([group, record['question'].casefold().strip(), record['answer']]).encode()).hexdigest()
            if key in seen: continue
            seen.add(key)
            context = {'projectEvidence': record['evidence'], 'brHelpEvidence': record['helpEvidence']}
            yield {'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': 'Context:\n'+json.dumps(context, ensure_ascii=False)+'\nQuestion: '+record['question']},
                {'role': 'assistant', 'content': record['answer']}],
                'metadata': {'id': record['id'], 'ownerId': row['owner_id'], 'reviewedBy': row['reviewed_by'],
                             'reviewed': True, 'splitGroup': group, 'intent': record['intent'], 'evidenceDigest': record['evidenceDigest']}}
