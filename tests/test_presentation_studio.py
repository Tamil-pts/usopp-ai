import io
import json
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.core import accounts,presentation_studio as studio,visual_content as visual

@pytest.fixture
def client(tmp_path,monkeypatch):
    store=accounts.AccountStore(tmp_path/'accounts.sqlite3')
    monkeypatch.setattr(accounts,'store',store)
    monkeypatch.setattr(accounts,'password_hash',lambda p:'fixture')
    monkeypatch.setattr(studio,'WORK',tmp_path/'work')
    owner=store.register('studio_owner','x','Engineer','Fixture')
    other=store.register('studio_other','x','Engineer','Fixture')
    c=TestClient(app);c.cookies.set(accounts.COOKIE,store.new_session(owner['id']))
    yield c,store,owner,other
    c.close()

def generate(c,**kw):
    payload={'prompt':'Engineering review presentation','count':4,'mode':'manual',**kw}
    return c.post('/api/assist/presentations/generate',json=payload)

def test_draft_persistence_edit_conflicts_and_exports(client):
    c,store,owner,other=client
    row=generate(c).json();key=row['id'];assert row['generation']=='manual'
    assert len(row['deck']['slides'])==4
    deck=row['deck'];deck['slides'][0]['elements'][0]['text']='Reviewed engineering draft'
    result=c.post(f'/api/assist/presentations/{key}',json={'revision':1,'deck':deck})
    assert result.status_code==200,result.text
    assert result.json()['revision']==2
    assert c.post(f'/api/assist/presentations/{key}',json={'revision':1,'deck':deck}).status_code==409
    assert c.get(f'/api/assist/presentations/{key}/export/pdf?revision=1').status_code==409
    assert c.get('/api/assist/presentations').json()['items'][0]['revision']==2
    exported={}
    for kind in ('pptx','pdf','svg','png','json'):
        response=c.get(f'/api/assist/presentations/{key}/export/{kind}?revision=2')
        assert response.status_code==200,response.text[:200];exported[kind]=response.content
    from pptx import Presentation
    prs=Presentation(io.BytesIO(exported['pptx']));assert len(prs.slides)==4
    assert prs.slides[0].shapes[0].text=='Reviewed engineering draft'
    assert prs.slides[0].shapes[0].has_text_frame
    from pypdf import PdfReader
    pdf=PdfReader(io.BytesIO(exported['pdf']));assert len(pdf.pages)==4
    assert 'Reviewed engineering draft' in pdf.pages[0].extract_text()
    for kind in ('png','svg'):
        with zipfile.ZipFile(io.BytesIO(exported[kind])) as z:assert len(z.namelist())==4
    c.cookies.clear();c.cookies.set(accounts.COOKIE,store.new_session(other['id']))
    assert c.get(f'/api/assist/presentations/{key}').status_code==404
    assert c.get('/api/assist/presentations').json()['items']==[]
    assert c.post(f'/api/assist/presentations/{key}',json={'revision':2,'deck':deck}).status_code==404
    assert c.get(f'/api/assist/presentations/{key}/export/pdf?revision=2').status_code==404

def test_grounded_model_selection_keeps_exact_sources_and_notes(client,monkeypatch):
    c,*_=client
    text='The validation report records 17 warnings. The 5-byte header precedes the payload.'
    source=c.post('/api/assist/presentations/sources',files={'file':('report.txt',text.encode())}).json()
    def model(instruction,payload):
        assert payload['evidence'][0]['text']=='The validation report records 17 warnings.'
        return {'slides':[{'title':'Review','layout':'cards','bullets':[],'source_ids':['S1']},{'title':'Packet','layout':'timeline','bullets':[],'source_ids':['S2']}]}
    monkeypatch.setattr(studio.local_ai,'llm_json',model)
    row=generate(c,mode='ai',count=2,sources=[source]).json()
    assert row['generation']=='local_llm'
    assert row['deck']['slides'][0]['elements'][1]['text']=='The validation report records 17 warnings.'
    assert '[S1] report.txt' in row['deck']['slides'][0]['notes']
    from pptx import Presentation
    from backend.core.presentation_exports import pptx
    prs=Presentation(io.BytesIO(pptx(row['deck'])))
    assert '17 warnings' in prs.slides[0].notes_slide.notes_text_frame.text

@pytest.mark.parametrize('bad',[{'title':'Unknown','source_ids':['invented']},{'title':'Missing references','bullets':['All tests passed.']}])
def test_rejects_fabricated_source_claims(client,monkeypatch,bad):
    c,*_=client
    source=c.post('/api/assist/presentations/sources',files={'file':('evidence.csv',b'tag,value\n653,missing')}).json()
    monkeypatch.setattr(studio.local_ai,'llm_json',lambda *args:{'slides':[bad,bad]})
    assert generate(c,mode='ai',count=2,sources=[source]).status_code==422
    assert c.get('/api/assist/presentations').json()['items']==[]

def test_model_prose_is_discarded_in_grounded_deck(client,monkeypatch):
    c,*_=client
    source=c.post('/api/assist/presentations/sources',files={'file':('source.txt',b'Test result: failed.')}).json()
    monkeypatch.setattr(studio.local_ai,'llm_json',lambda *args:{'slides':[{'title':'Results','source_ids':['S1'],'bullets':['All tests passed.']},{'title':'Review','source_ids':['S1'],'bullets':[{'text':'Invented summary'}]}]})
    row=generate(c,mode='ai',count=2,sources=[source]).json()
    assert row['deck']['slides'][0]['elements'][1]['text']=='Test result: failed.'
    assert any('discarded' in n for n in row['notices'])

def test_sources_are_private_and_invalid_geometry_rejected(client):
    c,store,owner,other=client
    assert c.post('/api/assist/presentations/sources',files={'file':('run.exe',b'abcd')}).status_code==422
    source=c.post('/api/assist/presentations/sources',files={'file':('source.txt',b'Engineering evidence')}).json()
    assert c.get('/api/assist/presentations/sources/'+source['id']+'/original').content==b'Engineering evidence'
    c.cookies.clear();c.cookies.set(accounts.COOKIE,store.new_session(other['id']))
    assert c.get('/api/assist/presentations/sources/'+source['id']+'/original').status_code==404
    assert generate(c,sources=[source]).status_code==404
    row=generate(c).json();deck=row['deck'];deck['slides'][0]['elements'][0]['x']=1279
    assert c.post('/api/assist/presentations/'+row['id'],json={'revision':1,'deck':deck}).status_code==422
    assert generate(c,count=99).status_code==422
    assert generate(c,font='external-url').status_code==422

def test_local_failure_has_no_silent_cloud_or_fake_ai_fallback(client,monkeypatch):
    c,*_=client
    def offline(*args):raise studio.local_ai.ServiceUnavailable('Local model offline')
    monkeypatch.setattr(studio.local_ai,'llm_json',offline)
    assert generate(c,mode='ai').status_code==503
    assert c.get('/api/assist/presentations').json()['items']==[]
    assert generate(c).json()['generation']=='manual'

def test_prompt_planner_accepts_validated_card_layout(client,monkeypatch):
    c,*_=client
    monkeypatch.setattr(studio.local_ai,'llm_json',lambda *args:{'slides':[{'title':'Introduction','bullets':['Review source inputs']},{'title':'Next steps','layout':'cards','cards':[{'title':'Review','description':'Discuss the findings'}]}]})
    row=generate(c,mode='ai',count=2).json()
    assert row['generation']=='local_llm'
    assert row['deck']['slides'][1]['elements'][1]['text']=='Review: Discuss the findings'
    assert any('not verified' in notice for notice in row['notices'])

def test_layout_diagnostics_detect_overflow_overlap_and_low_contrast():
    deck=visual.layout('Review',[{'title':'Draft','bullets':['Check results']}])
    e=deck['slides'][0]['elements'][1];e.update(text='Long content '*100,color='#ffffff',fill='#ffffff',y=64)
    warnings=visual.diagnostics(deck)
    assert any('overflow' in w for w in warnings)
    assert any('overlaps' in w for w in warnings)
    assert any('contrast' in w for w in warnings)

def test_pdf_bold_heading_preserves_the_selected_font_family():
    from backend.core.presentation_exports import pdf
    from pypdf import PdfReader
    deck=visual.layout('Review',[{'title':'Engineering review','bullets':['Source evidence']}],font='Arial')
    document=PdfReader(io.BytesIO(pdf(deck)))
    fonts=[str(value.get_object().get('/BaseFont','')) for value in document.pages[0]['/Resources']['/Font'].values()]
    assert not any('Courier' in name for name in fonts),fonts

def test_missing_assistant_permission_denied(client,monkeypatch):
    c,*_=client
    with pytest.raises(Exception) as error:studio.home({'id':99,'role':'engineer','workspaceModules':['workhub']})
    assert error.value.status_code==403

@pytest.mark.parametrize('kind',['xlsx','docx','pdf','csv'])
def test_document_formats_retain_readable_source_text(client,kind):
    c,*_=client;data=io.BytesIO()
    if kind=='xlsx':
        from openpyxl import Workbook
        book=Workbook();book.active.append(['TAG_CODE','Finding']);book.active.append([653,'Missing reference']);book.save(data);book.close()
    elif kind=='docx':
        from docx import Document
        doc=Document();doc.add_paragraph('TAG_CODE 653: Missing reference');doc.save(data)
    elif kind=='pdf':
        from reportlab.pdfgen.canvas import Canvas
        canvas=Canvas(data);canvas.drawString(50,700,'TAG_CODE 653: Missing reference');canvas.save()
    else:data.write(b'TAG_CODE,Finding\n653,Missing reference')
    response=c.post('/api/assist/presentations/sources',files={'file':('report.'+kind,data.getvalue())})
    assert response.status_code==200,response.text
    result=generate(c,count=2,sources=[response.json()]).json()
    assert '653' in ' '.join(row['text'] for row in result['evidence'])
