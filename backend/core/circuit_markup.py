"""Manual drawing markups for a single owned circuit comparison session."""
import csv
import io
import json
import math
import re
import time
import uuid
from xml.etree import ElementTree as ET
from fastapi import HTTPException

KINDS={'cloud','rectangle','arrow','note'}
COLORS={'blue','red','amber','green','purple'}

def load(folder):
    path=folder/'circuit_markups.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []

def validate(data,result):
    pair=next((p for p in result['pairs'] if p['id']==data.get('pairId')),None)
    side=data.get('side');shape=data.get('shape');color=data.get('color');box=data.get('box');text=data.get('text');status=data.get('status','open')
    if not pair or side not in ('base','developed') or not pair.get(side):raise HTTPException(400,'Choose an existing drawing page.')
    if shape not in KINDS or color not in COLORS or status not in ('open','resolved'):raise HTTPException(400,'Choose a valid markup, color and status.')
    if not isinstance(text,str) or not text.strip() or len(text)>2000 or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]',text):raise HTTPException(400,'Enter a valid comment of up to 2000 characters.')
    if not isinstance(box,list) or len(box)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in box):raise HTTPException(400,'Markup coordinates must be within the drawing.')
    if box[2]-box[0]<.003 or box[3]-box[1]<.003:raise HTTPException(400,'Draw a larger markup area.')
    if not isinstance(data.get('reverseX',False),bool) or not isinstance(data.get('reverseY',False),bool):raise HTTPException(400,'Invalid arrow direction.')
    return dict(pairId=pair['id'],side=side,page=pair[side],shape=shape,color=color,box=box,text=text.strip(),status=status,reverseX=data.get('reverseX',False),reverseY=data.get('reverseY',False))

def new(data,result,actor):
    now=time.time();return dict(id=uuid.uuid4().hex,**validate(data,result),author=actor,created=now,updated=now,version=1)

def update(existing,data,result,actor):
    if data.get('version')!=existing['version']:raise HTTPException(409,'This markup changed. Reload it before saving.')
    return dict(existing,**validate(data,result),updated=time.time(),updatedBy=actor,version=existing['version']+1)

def safe_csv(value):
    value=str(value or '')
    return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value

def csv_summary(marks):
    out=io.StringIO(newline='');writer=csv.writer(out);columns=['id','pairId','side','page','shape','color','text','status','author','version','box']
    writer.writerow(columns)
    for item in marks:writer.writerow([safe_csv(json.dumps(item.get(k)) if k=='box' else item.get(k)) for k in columns])
    return '\ufeff'+out.getvalue()

def xml_summary(marks):
    root=ET.Element('circuit-markups',version='1')
    for item in marks:
        child=ET.SubElement(root,'markup')
        for key in ('id','pairId','side','page','shape','color','text','status','author','version','box'):
            ET.SubElement(child,key).text=json.dumps(item.get(key)) if key=='box' else str(item.get(key,''))
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
