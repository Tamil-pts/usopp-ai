from io import BytesIO
import hashlib,json
from pathlib import Path
import pytest
from pypdf import PdfReader
from test_edesign import api,upload,mark,pdf_bytes
from python_engine.edesign_pdf import read_review,ATTACHMENT


def test_coloured_tools_stable_references_and_editable_pdf_roundtrip(api,tmp_path):
    client,_=api;review=upload(client);url='/api/e-design/'+review['id'];saved=[]
    for shape in ('cloud-only','highlight','underline','marker'):
        payload=mark(shape=shape,body='',color='#a12BeF',opacity=.4)
        if shape=='marker':payload['points']=[[.2,.3],[.28,.44],[.4,.5]]
        response=client.post(url+'/marks',json=payload);assert response.status_code==200,response.text;saved.append(response.json())
    assert [m['reference'] for m in saved]==['R001','R002','R003','R004']
    assert all(m['color']=='#a12bef' for m in saved)
    assert saved[0]['callout'] is None and saved[1]['callout']
    changed=client.put(url+'/marks/'+saved[1]['id'],json=mark(shape='highlight',version=1,body='Check the highlighted area.',callout=saved[1]['callout'])).json()
    assert changed['reference']=='R002' and changed['color']=='#a12bef' and changed['opacity']==.4
    assert client.delete(url+'/marks/'+saved[0]['id']+'?version=1').status_code==200
    new=client.post(url+'/marks',json=mark(shape='cloud-only',body='')).json();assert new['reference']=='R005'
    assert [m['reference'] for m in client.get(url).json()['marks']]==['R002','R003','R004','R005']
    response=client.get(url+'/export/pdf');assert response.status_code==200,response.text
    reader=PdfReader(BytesIO(response.content));roots=[a.get_object() for p in reader.pages for a in p.get('/Annots',[]) if str(a.get_object().get('/NM','')).startswith('edesign:')]
    assert {a['/Subtype'] for a in roots}=={'/Highlight','/Underline','/Ink','/Square'}
    target=tmp_path/'tools.pdf';target.write_bytes(response.content);parsed=read_review(target)
    assert len(parsed['marks'])==4 and {m['referenceNo'] for m in parsed['marks']}=={2,3,4,5}
    assert next(m for m in parsed['marks'] if m['shape']=='marker')['points']==[[.2,.3],[.28,.44],[.4,.5]]
    returned=client.post(url+'/import',files={'file':('tools.pdf',response.content,'application/pdf')});assert returned.status_code==200,returned.text
    assert returned.json()['importSummary']['updated']==0
    csv=client.get(url+'/export/csv').content.decode('utf-8-sig');assert 'R005' in csv and 'R001' not in csv


def test_front_page_defaults_save_conflicts_permissions_and_cover_roundtrip(api,tmp_path):
    client,module=api;review=upload(client);url='/api/e-design/'+review['id'];source=module.WORK/review['id']/'source.pdf';digest=hashlib.sha256(source.read_bytes()).hexdigest()
    client.post(url+'/share',json={'userId':2,'access':'review'})
    review=client.get(url).json();assert review['cover']['reviewedBy']=='Engineer 1';assert review['cover']['assignedTo']=='Engineer 2'
    assert review['cover']['approvedBy']=='' and review['cover']['reviewSignature']==''
    cover={**review['cover'],'fileName':'Control drawing.pdf','reviewVersion':'R03','description':'Review the cable routing.','reviewSignature':'Engineer 1 / reviewed','approvedBy':'Customer reviewer','approvalDetails':'Accepted with the recorded comments.','approvalDate':'2026-11-02'}
    response=client.put(url+'/cover',json={'version':0,'details':cover});assert response.status_code==200,response.text
    assert response.json()['coverVersion']==1
    assert client.put(url+'/cover',json={'version':0,'details':cover}).status_code==409
    client.post(url+'/share',json={'userId':3,'access':'view'})
    assert client.put(url+'/cover',headers={'x-user':'3'},json={'version':1,'details':cover}).status_code==403
    client.post(url+'/marks',json=mark(page=2,shape='cloud-only',body=''))
    exported=client.get(url+'/export/pdf?include_cover=true');assert exported.status_code==200,exported.text
    pdf=PdfReader(BytesIO(exported.content));assert len(pdf.pages)==3
    text=pdf.pages[0].extract_text();assert all(value in text for value in ['Control drawing.pdf','R03','Engineer 2','Customer reviewer','Engineer 1 / reviewed'])
    envelope=json.loads(pdf.attachments[ATTACHMENT][0]);assert envelope['drawingPageOffset']==1 and envelope['pageCount']==2
    target=tmp_path/'covered.pdf';target.write_bytes(exported.content);parsed=read_review(target)
    assert parsed['pages']==2 and parsed['marks'][0]['page']==2 and parsed['marks'][0]['shape']=='cloud-only'
    same=client.post(url+'/import',files={'file':('covered.pdf',exported.content,'application/pdf')});assert same.status_code==200,same.text;assert same.json()['importSummary']['updated']==0
    uploaded=client.post('/api/e-design',files={'file':('returned.pdf',exported.content,'application/pdf')});assert uploaded.status_code==200,uploaded.text
    copy=uploaded.json();assert len(copy['pages'])==2 and copy['cover']['reviewVersion']=='R03' and copy['marks'][0]['reference']=='R001'
    again=client.get('/api/e-design/'+copy['id']+'/export/pdf?include_cover=true');assert len(PdfReader(BytesIO(again.content)).pages)==3
    html=client.get(url+'/export/html?include_cover=true');assert 'review-cover' in html.text and 'R03' in html.text
    report=PdfReader(BytesIO(client.get(url+'/export/report?include_cover=true').content));assert 'R03' in report.pages[0].extract_text()
    from docx import Document
    document=Document(BytesIO(client.get(url+'/export/docx?include_cover=true').content));assert any('R03' in c.text for t in document.tables for r in t.rows for c in r.cells)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest


@pytest.mark.parametrize('change',[{'color':'red'},{'opacity':2},{'points':[[.2,.3],[2,.4]]}])
def test_invalid_style_rejected(api,change):
    client,_=api;url='/api/e-design/'+upload(client)['id']
    assert client.post(url+'/marks',json=mark(shape='marker',**change)).status_code==422
