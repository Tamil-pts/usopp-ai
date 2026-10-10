"""Append-only engineering learning records used by Rule Assist.

These records capture evidence and engineer decisions. They never alter a
deterministic Rule Engine verdict or retrain a model automatically.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.runtime import BASE

LEARNING_DIR=BASE/'rules'/'learning'
LEARNING_FILE=LEARNING_DIR/'engineering_observations.jsonl'


def _clean(value: Any, limit: int=8000) -> str:
    return str(value or '').replace('\x00','').strip()[:limit]


def append_observation(payload: dict[str, Any], record_type: str='assist_observation') -> dict[str, Any]:
    """Store one bounded evidence record and return the saved record."""
    rule_id=_clean(payload.get('ruleId'),240)
    project_name=_clean(payload.get('projectName'),500)
    status=_clean(payload.get('resultStatus'),80)
    label=_clean(payload.get('label'),120)
    evidence=payload.get('evidence') if isinstance(payload.get('evidence'),list) else []
    evidence=evidence[:100]
    fingerprint_source=json.dumps({
        'type':record_type,'ruleId':rule_id,'projectName':project_name,
        'status':status,'label':label,'evidence':evidence,
    },ensure_ascii=False,sort_keys=True,default=str)
    record={
        'schemaVersion':'1.0',
        'id':hashlib.sha256(fingerprint_source.encode('utf-8')).hexdigest()[:20],
        'recordType':record_type,
        'createdAt':datetime.now(timezone.utc).isoformat(),
        'ruleId':rule_id,
        'ruleVersion':_clean(payload.get('ruleVersion'),80),
        'projectName':project_name,
        'resultStatus':status,
        'label':label,
        'machineDepartment':_clean(payload.get('machineDepartment'),120),
        'category':_clean(payload.get('category'),160),
        'scope':_clean(payload.get('scope'),120),
        'comment':_clean(payload.get('comment'),4000),
        'actual':_clean(payload.get('actual')),
        'expected':_clean(payload.get('expected')),
        'recommendations':payload.get('recommendations')[:20] if isinstance(payload.get('recommendations'),list) else [],
        'sourceFiles':payload.get('sourceFiles')[:100] if isinstance(payload.get('sourceFiles'),list) else [],
        'evidence':evidence,
    }
    LEARNING_DIR.mkdir(parents=True,exist_ok=True)
    with LEARNING_FILE.open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(record,ensure_ascii=False,default=str)+'\n')
    return record


def read_observations(rule_id: str='', project_name: str='', limit: int=500) -> list[dict[str, Any]]:
    if not LEARNING_FILE.exists():
        return []
    records=[]
    for line in LEARNING_FILE.read_text(encoding='utf-8',errors='ignore').splitlines():
        try: record=json.loads(line)
        except json.JSONDecodeError: continue
        if rule_id and record.get('ruleId')!=rule_id: continue
        if project_name and record.get('projectName')!=project_name: continue
        records.append(record)
    return records[-max(1,min(int(limit or 500),2000)):]


def search_observations(query: str, limit: int=20, approved_only: bool=True) -> list[dict[str, Any]]:
    """Retrieve relevant engineer knowledge without changing model weights."""
    tokens={token.casefold() for token in re.findall(r'[A-Za-z_][A-Za-z0-9_.-]{2,}',query or '')}
    ranked=[]
    for record in read_observations(limit=2000):
        label=str(record.get('label') or '')
        approved=label in {'Correct','Partially correct','Create rule from this'}
        if approved_only and not approved:
            continue
        searchable=' '.join(str(record.get(key) or '') for key in (
            'ruleId','projectName','machineDepartment','category','scope','resultStatus',
            'label','comment','actual','expected','recommendations','sourceFiles','evidence',
        )).casefold()
        score=sum(3 if '_' in token else 1 for token in tokens if token in searchable)
        if not tokens:
            score=1
        if score:
            ranked.append((score,record.get('createdAt',''),record))
    ranked.sort(key=lambda item:(item[0],item[1]),reverse=True)
    return [item[2] for item in ranked[:max(1,min(int(limit or 20),100))]]


def learning_summary() -> dict[str, Any]:
    records=read_observations(limit=2000)
    approved=sum(str(item.get('label') or '') in {'Correct','Partially correct','Create rule from this'} for item in records)
    reviewed=sum(bool(item.get('label')) for item in records)
    projects={str(item.get('projectName') or '').strip() for item in records if str(item.get('projectName') or '').strip()}
    rules={str(item.get('ruleId') or '').strip() for item in records if str(item.get('ruleId') or '').strip()}
    categories={str(item.get('category') or '').strip() for item in records if str(item.get('category') or '').strip()}
    return {
        'model':'Chopper Engineering Knowledge Model',
        'mode':'approved-evidence retrieval',
        'recordCount':len(records),
        'reviewedCount':reviewed,
        'approvedCount':approved,
        'projectCount':len(projects),
        'ruleCount':len(rules),
        'categories':sorted(categories),
        'fineTuningReady':approved>=50,
        'minimumApprovedExamples':50,
    }


def approved_training_examples() -> list[dict[str, Any]]:
    """Build a portable fine-tuning dataset from engineer-approved explanations."""
    examples=[]
    for record in read_observations(limit=2000):
        if record.get('label') not in {'Correct','Partially correct','Create rule from this'}:
            continue
        answer=str(record.get('comment') or '').strip()
        if not answer:
            continue
        prompt=(f"Rule {record.get('ruleId') or 'engineering finding'} is {record.get('resultStatus') or 'unclassified'}. "
                f"Expected: {record.get('expected') or 'not supplied'}. Actual: {record.get('actual') or 'not supplied'}. "
                "Explain the evidence, likely cause, impact, and corrective action.")
        examples.append({
            'messages':[
                {'role':'system','content':'You are Chopper, the uSOPp industrial PLC engineering assistant. Use only approved evidence.'},
                {'role':'user','content':prompt},
                {'role':'assistant','content':answer},
            ],
            'metadata':{
                'learningId':record.get('id'),'ruleId':record.get('ruleId'),
                'projectName':record.get('projectName'),'decision':record.get('label'),
            },
        })
    return examples
