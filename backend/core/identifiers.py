"""Stable public rule IDs and unique engineering run/export names."""
from datetime import datetime, timedelta, timezone
import re
import sqlite3
from contextlib import closing
from uuid import uuid4
from backend.core.runtime import EXPORTS

def rule_id(existing=None):
    EXPORTS.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(EXPORTS/'identifiers.sqlite3',timeout=30)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS rule_identity (number INTEGER PRIMARY KEY AUTOINCREMENT, legacy TEXT UNIQUE)')
        db.execute('BEGIN IMMEDIATE')
        if existing and re.fullmatch(r'BndR_ID_\d{6,12}',existing):
            db.execute('INSERT OR IGNORE INTO rule_identity(number,legacy) VALUES (?,?)',(int(existing.split('_')[-1]),existing))
            return existing
        if existing:
            found=db.execute('SELECT number FROM rule_identity WHERE legacy=?',(existing,)).fetchone()
            if found: return f'BndR_ID_{found[0]:06d}'
        cursor=db.execute('INSERT INTO rule_identity(legacy) VALUES (?)',(existing or 'reserved:'+uuid4().hex,))
        return f'BndR_ID_{cursor.lastrowid:06d}'

def filename_part(value,limit=180):
    return re.sub(r'[^A-Za-z0-9_.-]+','_',str(value or 'All')).strip('._')[:limit] or 'All'

def run_identity(project,department='All'):
    time=datetime.now(timezone(timedelta(hours=5,minutes=30)))
    return f'{filename_part(project,48)}_{filename_part(department,24)}_TEST_{time:%Y%m%d_%H%M%S}_{uuid4().hex[:10]}'

def identify_result(data,kind,department=None):
    department=department or data.get('machineDepartment') or 'All'
    data.setdefault('machineDepartment',department)
    data.setdefault('testId',run_identity(data.get('projectName') or 'Project',department))
    data.setdefault('runKind',kind)
    for row in data.get('results') or []:
        if isinstance(row,dict) and row.get('id'): row['standardId']=rule_id(str(row['id']))
    return data
