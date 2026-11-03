"""Unified PDF layout, source preservation, isolation and saved-layout conflicts."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader,PdfWriter
from PIL import Image
import pytest
from reportlab.pdfgen import canvas

from backend.core import virtual_electrical as engine
from backend.api import virtual_electrical as api
from backend.core.run_history import current_user


@pytest.fixture
def drawing(tmp_path):
    raw=BytesIO();pdf=canvas.Canvas(raw,pagesize=(600,400))
    for number in (1,2):
        pdf.drawString(35,365,f'SHEET {number} OF 2 - MOTOR CIRCUIT')
        pdf.drawString(90,270,'K1');pdf.drawString(250,270,'X1:1')
        pdf.line(90,240,250,240);pdf.line(250,240,250,180)
        pdf.rect(85,215,30,40);pdf.drawString(35,80,'POWER FEED' if number==1 else 'CONTROL RETURN')
        pdf.showPage()
    pdf.save();path=tmp_path/'circuit.pdf';path.write_bytes(raw.getvalue());return path


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(api,'WORK',tmp_path/'work');api.WORK.mkdir()
    monkeypatch.setattr(api,'claim_resource',lambda *args:None)
    app=FastAPI();app.include_router(api.router)
    @app.middleware('http')
    async def account(request,call_next):
        identity=request.headers.get('test-user','1')
        user={'id':int(identity),'username':'Engineer '+identity,'role':'user','workspaceModules':[] if request.headers.get('no-electrical') else ['edesign']} if identity else None
        token=current_user.set(user)
        try:return await call_next(request)
        finally:current_user.reset(token)
    with TestClient(app) as value:yield value


def ready(client,identity):
    for _ in range(200):
        response=client.get('/api/virtual-electrical/projects/'+identity)
        assert response.status_code==200,response.text
        value=response.json()
        if value['status']!='analyzing':
            assert value['status']=='ready',value
            return value
        time.sleep(.05)
    pytest.fail('Drawing worker did not finish.')


def test_one_artboard_saved_positions_one_page_export_and_unchanged_source(tmp_path,drawing):
    folder=tmp_path/'workspace';folder.mkdir();shutil.copyfile(drawing,folder/'source.pdf');before=sha256(drawing.read_bytes()).hexdigest()
    data=engine.decode(folder)
    assert data['pageCount']==2 and not data['netlistVerified']
    assert next(r for r in data['references'] if r['reference']=='K1')['occurrences'][1]['page']==2
    positions=engine.layout(data['pages'],'horizontal');positions[0]['x']=-120
    result=engine.update_layout(folder,{'version':1,'mode':'custom','positions':positions})
    assert result['version']==2 and result['positions'][0]['x']==-120
    engine.export_pdf(folder,folder/'unified.pdf');exported=PdfReader(folder/'unified.pdf')
    assert len(exported.pages)==1
    text=exported.pages[0].extract_text();assert 'POWER FEED' in text and 'CONTROL RETURN' in text
    assert sha256((folder/'source.pdf').read_bytes()).hexdigest()==before
    assert len(PdfReader(drawing).pages)==2


def test_upload_owner_isolation_layout_versions_and_page_bounds(client,drawing):
    response=client.post('/api/virtual-electrical/projects',files={'file':('Motor.pdf',drawing.read_bytes(),'application/pdf')})
    assert response.status_code==200,response.text
    key=response.json()['id'];value=ready(client,key);base='/api/virtual-electrical/projects/'+key
    assert len(value['pages'])==2 and len(value['layout']['positions'])==2
    assert client.get(base,headers={'test-user':'2'}).status_code==403
    assert not client.get('/api/virtual-electrical/projects',headers={'test-user':'2'}).json()['projects']
    assert client.get(base,headers={'test-user':''}).status_code==401
    assert client.get(base,headers={'no-electrical':'1'}).status_code==403
    for url in ('/page/1','/scene/1','/original','/export'):
        assert client.get(base+url,headers={'test-user':'2'}).status_code==403
    assert client.get(base+'/page/0').status_code==404
    assert client.get(base+'/scene/3').status_code==404
    update=client.put(base+'/layout',json={'version':1,'mode':'vertical'})
    assert update.status_code==200,update.text
    assert update.json()['version']==2
    assert client.put(base+'/layout',json={'version':1,'mode':'grid'}).status_code==409
    assert client.put(base+'/layout',json={'version':2,'mode':'custom','positions':[{'page':1,'x':0,'y':0}]*2}).status_code==400
    assert client.put(base+'/layout',json={'version':2,'mode':'custom','positions':[{'page':1,'x':True,'y':0},{'page':2,'x':0,'y':0}]}).status_code==400
    assert client.get(base+'/original').content==drawing.read_bytes()
    exported=client.get(base+'/export');assert exported.status_code==200,exported.text
    assert len(PdfReader(BytesIO(exported.content)).pages)==1
    assert client.get(base+'/scene/1').json()['coverage']['netlistVerified'] is False
    thumbnail=client.get(base+'/page/1?thumbnail=true')
    assert thumbnail.status_code==200 and max(Image.open(BytesIO(thumbnail.content)).size)<=480


def test_invalid_upload_releases_worker_slot_and_rotation_survives_export(client,drawing,tmp_path):
    for _ in range(3):
        assert client.post('/api/virtual-electrical/projects',files={'file':('invalid.pdf',b'not a pdf')}).status_code==400
    writer=PdfWriter();reader=PdfReader(drawing)
    writer.add_page(reader.pages[0]);writer.add_page(reader.pages[1]).rotate(90)
    content=BytesIO();writer.write(content)
    response=client.post('/api/virtual-electrical/projects',files={'file':('Rotated.pdf',content.getvalue(),'application/pdf')})
    key=response.json()['id'];value=ready(client,key)
    assert value['pages'][1]['width']==400 and value['pages'][1]['height']==600
    result=client.get('/api/virtual-electrical/projects/'+key+'/export')
    assert result.status_code==200 and len(PdfReader(BytesIO(result.content)).pages)==1
    assert client.get('/api/virtual-electrical/projects/'+key+'/original').content==content.getvalue()


def test_from_review_checks_source_access_and_keeps_review_source(client,drawing,monkeypatch):
    from backend.api import edesign
    monkeypatch.setattr(edesign,'WORK',api.WORK)
    key='edesign_'+'a'*32;folder=api.WORK/key;folder.mkdir();shutil.copyfile(drawing,folder/'source.pdf')
    token=current_user.set({'id':1,'username':'Engineer 1','role':'user'})
    try:edesign.create_review(folder,key,'Existing circuit.pdf',current_user.get())
    finally:current_user.reset(token)
    original=(folder/'source.pdf').read_bytes()
    response=client.post('/api/virtual-electrical/projects/from-review',json={'reviewId':key},headers={'test-user':'2'})
    assert response.status_code==403,response.text
    response=client.post('/api/virtual-electrical/projects/from-review',json={'reviewId':key})
    assert response.status_code==200,response.text
    ready(client,response.json()['id'])
    assert (folder/'source.pdf').read_bytes()==original


def test_interrupted_analysis_is_reported_instead_of_polling_forever(client,drawing):
    response=client.post('/api/virtual-electrical/projects',files={'file':('Circuit.pdf',drawing.read_bytes(),'application/pdf')})
    key=response.json()['id'];ready(client,key)
    engine.write(api.WORK/key/'status.json',{'status':'analyzing','processId':-1,'phase':'Opening drawing'})
    result=client.get('/api/virtual-electrical/projects/'+key).json()
    assert result['status']=='failed' and 'restart' in result['error']
    assert client.get('/api/virtual-electrical/projects/'+key+'/export').status_code==409
