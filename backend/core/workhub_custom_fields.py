"""Typed project fields shared by creation templates, portfolio and exports."""
import hashlib
import json
import math
import unicodedata
from datetime import date
from fastapi import HTTPException
from .workhub import text,encode


def schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS wh_project_fields(project_id TEXT PRIMARY KEY,fields TEXT NOT NULL DEFAULT '[]')")


def clean(rows):
    if not isinstance(rows,list) or len(rows)>40:raise HTTPException(400,'Use up to 40 custom project fields.')
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):raise HTTPException(400,'Provide structured custom fields.')
        label=text(row.get('label',''),80,True);kind=row.get('type','text')
        if kind not in {'text','number','date','boolean'}:raise HTTPException(400,'Choose text, number, date or checkbox.')
        normalized=unicodedata.normalize('NFKC',label).strip().casefold()
        key='custom_'+hashlib.sha256((normalized+':'+kind).encode()).hexdigest()[:20]
        if key in seen:raise HTTPException(400,'Use unique custom field names and types.')
        seen.add(key);value=row.get('value','')
        if value is None:value=''
        if kind=='text':value=text(value,4000)
        elif value!='':
            if kind=='number' and (type(value) not in (float,int) or not math.isfinite(value) or abs(value)>1e15):raise HTTPException(400,'Enter a finite numeric field value.')
            if kind=='boolean' and type(value) is not bool:raise HTTPException(400,'Choose a checkbox value.')
            if kind=='date':
                try:
                    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:raise ValueError()
                except ValueError:raise HTTPException(400,'Enter dates as YYYY-MM-DD.') from None
        required=row.get('required',False)
        if type(required) is not bool:raise HTTPException(400,'Choose whether the field is required.')
        if required and value=='':raise HTTPException(400,'Complete the custom field: '+label)
        result.append({'id':key,'label':label,'type':kind,'required':required,'value':value})
    return result


def read(db,pid):
    row=db.execute('SELECT fields FROM wh_project_fields WHERE project_id=?',(pid,)).fetchone()
    return json.loads(row[0]) if row else []


def save(db,pid,rows):
    fields=clean(rows)
    db.execute('INSERT INTO wh_project_fields VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET fields=excluded.fields',(pid,encode(fields)))
    return fields
