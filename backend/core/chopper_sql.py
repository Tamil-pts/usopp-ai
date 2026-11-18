"""Read-only SQL over one account-owned uploaded worksheet, never application DBs."""
import hashlib
import json
import math
import re
import sqlite3
import time
from backend.core import spreadsheet_analysis as sheets

MAX_ROWS = 50000
MAX_RESULT = 200
FUNCTIONS = {'count','sum','avg','min','max','round','abs','length','lower','upper',
             'coalesce','ifnull','nullif','trim','substr','substring','date','strftime','typeof'}


def worksheet(user, payload):
    path, info, sheet, header, columns, rows, blanks = sheets.read(user, payload)
    if len(rows) > MAX_ROWS:
        raise ValueError('Select a worksheet with at most 50,000 data rows.')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    scope = {'id':payload['id'], 'sheet':sheet, 'header_row':header, 'sha256':digest}
    schema = [{'sql':f'c{c["index"]}', 'name':c['name'], 'excelColumn':c['letter']} for c in columns]
    return path, scope, schema, rows, blanks


def execute(user, payload, sql, expected_scope=None, *, worksheet_loader=None):
    sql = str(sql).strip()
    if not sql or len(sql)>8000 or not re.match(r'^(?:SELECT|WITH)\b', sql, re.I):
        raise ValueError('Only one read-only SELECT query is allowed.')
    path, scope, schema, rows, blanks = (worksheet_loader or worksheet)(user, payload)
    if expected_scope is not None and scope != expected_scope:
        raise ValueError('Worksheet or source bytes changed. Prepare and review a new query.')
    db = sqlite3.connect(':memory:')
    try:
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1000000)
        db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 8000)
        db.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 30)
        db.execute('CREATE TABLE data (_source_row INTEGER,'+','.join(f'c{i}' for i in range(len(schema)))+')')
        unknown = 0
        values = []
        for row_number, cells in rows:
            output = [row_number]
            for cell in cells:
                if cell.get('unknown') or cell['type'] in {'error','blank'}:
                    output.append(None)
                    unknown += int(bool(cell.get('unknown') or cell['type']=='error'))
                else:
                    numeric = sheets.numeric(cell)
                    output.append(float(numeric) if numeric is not None else cell['value'])
            values.append(output)
        db.executemany('INSERT INTO data VALUES ('+','.join('?' for _ in range(len(schema)+1))+')', values)
        db.commit()
        db.execute('PRAGMA query_only=ON')
        def authorize(action, first, second, database, trigger):
            if action == sqlite3.SQLITE_SELECT:return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and first == 'data':return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and str(second or first).lower() in FUNCTIONS:return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        db.set_authorizer(authorize)
        started=time.monotonic()
        ticks=0
        def progress():
            nonlocal ticks
            ticks+=1
            return int(ticks>5000 or time.monotonic()-started>2)
        db.set_progress_handler(progress,1000)
        try:
            cursor=db.execute(sql)
            result=cursor.fetchmany(MAX_RESULT+1)
        except sqlite3.Error as error:
            raise ValueError('Query rejected or exceeded its read-only execution limits: '+str(error)[:160]) from None
        names=[c[0] for c in cursor.description]
        result=result[:MAX_RESULT] if len(result)>MAX_RESULT else result
        if any(isinstance(v,float) and not math.isfinite(v) for row in result for v in row):
            raise ValueError('Query produced a non-finite number. Review the numeric operation.')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=scope['sha256']:
            raise ValueError('Worksheet source changed during execution. Prepare a new query.')
        return {'sql':sql,'columns':names,'rows':result,'scope':scope,'inputRows':len(rows),
                'resultLimit':MAX_RESULT,'possiblyTruncated':len(result)==MAX_RESULT,'blankRowsOmitted':blanks,
                'unknownCellsAsNull':unknown,'schema':schema,'readOnly':True,
                'notice':'Results use saved worksheet cells. Unknown/error cells are NULL; numeric aggregates use SQLite floating-point arithmetic. No application database was queried.'}
    finally:db.close()


def simple_plan(question, schema):
    """A narrow deterministic fallback; never guess a measure or grouping column."""
    q=question.casefold().strip().rstrip('?.').strip()
    if re.fullmatch(r'(?:count(?: all)?(?: the)? rows|how many (?:data )?rows(?: are there)?|number of (?:data )?rows)',q):
        return 'SELECT COUNT(*) AS row_count FROM data'
    plans=[]
    for column in schema:
        name=column['name'].casefold().strip()
        if not name:continue
        for words,op in [('average|mean','AVG'),('total|sum','SUM'),('maximum|highest','MAX'),('minimum|lowest','MIN')]:
            if re.fullmatch(r'(?:what is (?:the )?)?(?:'+words+r')(?: of)? '+re.escape(name),q):
                plans.append(f'SELECT {op}({column["sql"]}) AS value FROM data')
    if len(plans)==1:return plans[0]
    raise ValueError('A reliable SQL plan could not be determined. Enable the planner model or enter a SELECT query using the displayed c0/c1 column names.')
