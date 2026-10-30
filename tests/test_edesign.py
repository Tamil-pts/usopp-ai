from io import BytesIO
import hashlib
import sqlite3
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas


def pdf_bytes():
    data=BytesIO();c=Canvas(data,pagesize=(600,400),invariant=1)
    for i in (1,2):
        c.drawString(70,300,f'Circuit drawing page {i} / X13 / MOTOR M1')
        c.line(80,160,450,160);c.rect(160,170,60,80);c.showPage()
    c.save();writer=PdfWriter();writer.append(PdfReader(BytesIO(data.getvalue())))
    writer.pages[1].cropbox.lower_left=(40,30);writer.pages[1].cropbox.upper_right=(550,370);writer.pages[1].rotate(90)
    output=BytesIO();writer.write(output);return output.getvalue()


@pytest.fixture
def api(tmp_path,monkeypatch):
    from backend.api import edesign as module
    from backend.core.run_history import current_user
    monkeypatch.setattr(module,'WORK',tmp_path)
    monkeypatch.setattr(module,'claim_resource',lambda *args:None)
    monkeypatch.setattr(module.accounts.store,'list_users',lambda:[{'id':i,'username':f'Engineer {i}','designation':'Engineer','active':True,'approved':True} for i in (1,2,3)])
    app=FastAPI();app.include_router(module.router)
    @app.middleware('http')
    async def identity(request,call_next):
        uid=int(request.headers.get('x-user','1'))
        token=current_user.set({'id':uid,'username':f'Engineer {uid}','role':'user'} if uid else None)
        try:return await call_next(request)
        finally:current_user.reset(token)
    with TestClient(app) as client:yield client,module


def upload(client):
    response=client.post('/api/e-design',files={'file':('Circuit.pdf',pdf_bytes(),'application/pdf')})
    assert response.status_code==200,response.text
    return response.json()


def mark(**overrides):
    return {'page':1,'kind':'modify','shape':'cloud','box':[.2,.3,.4,.5],'body':'Move X13 connector; verify pin 2.','status':'open','version':0,**overrides}


def test_upload_review_edit_conflict_exports_and_immutable_source(api):
    client,module=api;review=upload(client);prefix='/api/e-design/'+review['id']
    folder=module.WORK/review['id'];before=hashlib.sha256((folder/'source.pdf').read_bytes()).hexdigest()
    assert len(review['pages'])==2 and review['pages'][1]['width']==340
    assert client.get(prefix+'/page/1').content.startswith(b'\x89PNG')
    assert client.get(prefix+'/page/999').status_code==404
    assert client.get(prefix+'/original').content==pdf_bytes()
    created=client.post(prefix+'/marks',json=mark()).json();assert created['version']==1
    updated=client.put(prefix+'/marks/'+created['id'],json=mark(version=1,body='Change X13 location',box=[.3,.4,.55,.65])).json()
    assert updated['version']==2 and updated['body']=='Change X13 location'
    assert client.put(prefix+'/marks/'+created['id'],json=mark(version=1)).status_code==409
    assert client.delete(prefix+'/marks/'+created['id']+'?version=1').status_code==409
    assert client.post(prefix+'/marks',json=mark(page=2,kind='remove',shape='rectangle',body='Remove this device')).status_code==200
    assert client.post(prefix+'/marks',json=mark(shape='arrow',kind='add',reverseX=True,body='Add a terminal here')).status_code==200
    assert len(client.get(prefix).json()['marks'])==3
    assert client.get('/api/e-design').json()['reviews'][0]['open']==3
    exported=client.get(prefix+'/export/pdf');assert exported.status_code==200
    pdf=PdfReader(BytesIO(exported.content));assert len(pdf.pages)==2
    assert any(a.get_object().get('/Contents')=='Change X13 location' for a in pdf.pages[0]['/Annots'])
    report=PdfReader(BytesIO(client.get(prefix+'/export/report').content))
    assert len(report.pages)>=3 and 'Change X13 location' in '\n'.join(p.extract_text() for p in report.pages)
    docx=client.get(prefix+'/export/docx');assert docx.status_code==200
    with zipfile.ZipFile(BytesIO(docx.content)) as archive:assert b'Change X13 location' in archive.read('word/document.xml')
    assert 'Change X13 location' in client.get(prefix+'/export/csv').content.decode('utf-8-sig')
    html=client.get(prefix+'/export/html');assert html.status_code==200
    assert 'Change X13 location' in html.text and 'data:image/png;base64,' in html.text
    assert client.get(prefix+'/export/html',headers={'x-user':'2'}).status_code==403
    assert not list(folder.glob('export-*'))  # response cleanup, not growing caches
    assert hashlib.sha256((folder/'source.pdf').read_bytes()).hexdigest()==before==review['sourceHash']
    assert client.delete(prefix+'/marks/'+created['id']+'?version=2').status_code==200
    assert len(client.get(prefix).json()['marks'])==2
    with sqlite3.connect(folder/'review.sqlite3') as db:assert db.execute("SELECT count(*) FROM events WHERE action='delete'").fetchone()[0]==1


def test_account_scoping_sharing_author_permissions_and_revocation(api):
    client,_=api;review=upload(client);prefix='/api/e-design/'+review['id']
    assert client.get(prefix,headers={'x-user':'2'}).status_code==403
    assert client.get('/api/e-design',headers={'x-user':'2'}).json()['reviews']==[]
    assert client.get(prefix,headers={'x-user':'0'}).status_code==401
    mine=client.post(prefix+'/marks',json=mark()).json()
    assert client.post(prefix+'/share',json={'userId':2,'access':'review'}).status_code==200
    assert client.post(prefix+'/share',json={'userId':3,'access':'view'}).status_code==200
    assert client.get(prefix,headers={'x-user':'2'}).json()['access']=='review'
    assert client.get(prefix+'/page/1',headers={'x-user':'3'}).status_code==200
    assert client.post(prefix+'/marks',headers={'x-user':'3'},json=mark()).status_code==403
    assert client.put(prefix+'/marks/'+mine['id'],headers={'x-user':'2'},json=mark(version=1,body='Shared reviewer edit')).status_code==200
    assert client.get(prefix+'/marks/'+mine['id']+'/history').json()['revisions'][0]['actor']=='Engineer 2'
    theirs=client.post(prefix+'/marks',headers={'x-user':'2'},json=mark(body='Reviewer comment')).json()
    assert client.put(prefix+'/marks/'+theirs['id'],headers={'x-user':'2'},json=mark(version=1,status='resolved')).json()['status']=='resolved'
    assert client.post(prefix+'/share',headers={'x-user':'2'},json={'userId':3,'access':'review'}).status_code==403
    assert client.post(prefix+'/share',json={'userId':2,'access':'remove'}).status_code==200
    assert client.get(prefix,headers={'x-user':'2'}).status_code==403
    assert client.get(prefix+'/export/pdf',headers={'x-user':'2'}).status_code==403
    assert client.get(prefix+'/original',headers={'x-user':'2'}).status_code==403


def test_invalid_pdf_bounds_blank_comments_and_missing_revision_rejected(api):
    client,module=api
    assert client.post('/api/e-design',files={'file':('bad.pdf',b'not pdf')}).status_code==400
    assert not list(module.WORK.glob('edesign_*'))
    review=upload(client);prefix='/api/e-design/'+review['id']
    for change in ({'box':[-.1,.2,.3,.4]},{'box':[.8,.2,.3,.4]},{'body':'   '},{'box':[0,0,0,.2]}):
        assert client.post(prefix+'/marks',json=mark(**change)).status_code==422
    assert client.post(prefix+'/marks',json=mark(page=9)).status_code==400
    assert client.get('/api/e-design/edesign_invalid').status_code==404
    saved=client.post(prefix+'/marks',json=mark()).json()
    assert client.put(prefix+'/marks/'+saved['id'],json=mark()).status_code==409


def test_rotated_cropped_pdf_markup_coordinates_match_preview(api):
    import pypdfium2 as pdfium
    import numpy as np
    client,_=api;review=upload(client);prefix='/api/e-design/'+review['id']
    client.post(prefix+'/marks',json=mark(page=2,kind='remove',shape='rectangle'))
    data=client.get(prefix+'/export/pdf').content
    with pdfium.PdfDocument(data) as pdf:
        page=pdf[1];bitmap=page.render(scale=1)
        try:
            image=np.array(bitmap.to_pil().convert('RGB'))
            h,w=image.shape[:2];red=(image[:,:,0]>120)&(image[:,:,1]<100)&(image[:,:,2]<120)
            assert red[int(.3*h)-3:int(.3*h)+4,int(.2*w):int(.4*w)].sum()>20
            assert red[int(.3*h):int(.5*h),int(.2*w)-3:int(.2*w)+4].sum()>20
        finally:bitmap.close();page.close()
