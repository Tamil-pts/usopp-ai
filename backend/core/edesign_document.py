"""Editable, revision-checked review-cover details; no approval is inferred."""
from datetime import datetime,timezone
import json,time
from pydantic import BaseModel,Field
from fastapi import HTTPException

class Cover(BaseModel):
    fileName:str=Field(max_length=200)
    reviewVersion:str=Field(default='R01',min_length=1,max_length=40)
    reviewDate:str=Field(default='',max_length=30)
    reviewedBy:str=Field(default='',max_length=200)
    reviewSignature:str=Field(default='',max_length=250)
    assignedTo:str=Field(default='',max_length=500)
    description:str=Field(default='',max_length=2000)
    approvedBy:str=Field(default='',max_length=200)
    approvalDate:str=Field(default='',max_length=30)
    approvalDetails:str=Field(default='',max_length=2000)

class CoverUpdate(BaseModel):
    version:int=Field(ge=0)
    details:Cover

def details(db,meta,who,assignees=()):
    saved=db.execute('SELECT * FROM document_covers ORDER BY version DESC LIMIT 1').fetchone()
    if saved:return json.loads(saved['payload']),saved['version']
    return Cover(fileName=meta['name'],reviewDate=datetime.now(timezone.utc).date().isoformat(),reviewedBy=who['username'],
                 assignedTo=', '.join(assignees),description=f'Drawing review: {meta["name"]} ({len(meta["pages"])} pages).').model_dump(),0

def save(db,payload,who):
    version=db.execute('SELECT COALESCE(MAX(version),0) FROM document_covers').fetchone()[0]
    if payload.version!=version:raise HTTPException(409,'The front page changed in another window. Refresh before saving.')
    db.execute('INSERT INTO document_covers VALUES (?,?,?,?)',(version+1,payload.details.model_dump_json(),who['username'],time.time()))
    return version+1
