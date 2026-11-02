"""Visible bubble leaders/text survive edits, history and ordinary PDF handoff."""
from io import BytesIO
import json
import pytest
from pypdf import PdfReader,PdfWriter
from pypdf.generic import NameObject,TextStringObject,ArrayObject,FloatObject
from test_edesign import api,upload,mark,pdf_bytes
from python_engine.edesign_pdf import read_review,ATTACHMENT

LABEL=[.48,.32,.78,.46]


def test_new_region_defaults_include_visible_arrow_and_text(api):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    for shape in ('cloud','rectangle'):
        saved=client.post(prefix+'/marks',json=mark(shape=shape,reverseX=True,reverseY=True)).json()
        assert saved['callout'] and len(saved['callout'])==4
        a,b,c,d=saved['callout'];assert 0<=a<c<=1 and 0<=b<d<=1
        assert saved['body']==mark()['body']
    exported=client.get(prefix+'/export/pdf').content
    pdf=PdfReader(BytesIO(exported))
    assert len([a for a in pdf.pages[0]['/Annots'] if str(a.get_object().get('/NM','')).startswith('edesign-callout:')])==2
    returned=client.post(prefix+'/import',files={'file':('unchanged.pdf',exported,'application/pdf')})
    assert returned.status_code==200,returned.text
    assert returned.json()['importSummary']['updated']==0
    assert all(m['reverseX'] and m['reverseY'] and m['version']==1 for m in returned.json()['marks'])


def test_existing_region_setup_preserves_comments_and_is_one_undoable_change(api):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    first=client.post(prefix+'/marks',json=mark(callout=None)).json()
    second=client.post(prefix+'/marks',json=mark(shape='rectangle',box=[.42,.3,.6,.45],callout=None,body='Add the missing terminal.')).json()
    custom=client.post(prefix+'/marks',json=mark(callout=LABEL,body='Keep this placement.')).json()
    assert client.get(prefix).json()['calloutSetupNeeded']
    prepared=client.post(prefix+'/callouts',json={'versions':{first['id']:1,second['id']:1}})
    assert prepared.status_code==200,prepared.text
    value=prepared.json();assert value['calloutsPrepared']==2 and not value['calloutSetupNeeded']
    marks={m['id']:m for m in value['marks']}
    assert marks[custom['id']]['callout']==LABEL and marks[custom['id']]['version']==1
    for original in (first,second):
        actual=marks[original['id']]
        assert actual['version']==2 and actual['callout']
        for key in ('body','box','kind','status','author','author_id','created'):assert actual[key]==original[key]
    again=client.post(prefix+'/callouts',json={'versions':{key:marks[key]['version'] for key in (first['id'],second['id'])}}).json()
    assert again['calloutsPrepared']==0
    undone=client.post(prefix+'/history/undo',json={'commandId':value['commands']['undo']['id']}).json()
    assert all(m['callout'] is None for m in undone['marks'] if m['id']!=custom['id'])
    assert not client.get(prefix).json()['calloutSetupNeeded']  # Opening must respect explicit Undo.
    redone=client.post(prefix+'/history/redo',json={'commandId':undone['commands']['redo']['id']}).json()
    assert all(m['callout'] for m in redone['marks'])


def test_existing_setup_rejects_stale_versions_and_view_only_users(api):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    first=client.post(prefix+'/marks',json=mark(callout=None)).json()
    second=client.post(prefix+'/marks',json=mark(callout=None)).json()
    client.put(prefix+'/marks/'+second['id'],json=mark(version=1,callout=None,body='Changed by reviewer'))
    response=client.post(prefix+'/callouts',json={'versions':{first['id']:1,second['id']:1}})
    assert response.status_code==409
    assert all(m['callout'] is None for m in client.get(prefix).json()['marks'])
    client.post(prefix+'/share',json={'userId':2,'access':'view'})
    assert client.post(prefix+'/callouts',headers={'x-user':'2'},json={'versions':{first['id']:1}}).status_code==403


def test_callout_persistence_conflicts_and_history(api):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    first=client.post(prefix+'/marks',json=mark(callout=LABEL)).json()
    assert first['callout']==LABEL
    shifted=[.55,.4,.85,.54]
    second=client.put(prefix+'/marks/'+first['id'],json=mark(version=1,callout=shifted,body='Check terminal clearance.')).json()
    assert client.get(prefix).json()['marks'][0]['callout']==shifted
    assert client.put(prefix+'/marks/'+first['id'],json=mark(version=1,callout=LABEL)).status_code==409
    undo=client.post(prefix+'/history/undo',json={'commandId':second['commands']['undo']['id']}).json()
    assert undo['marks'][0]['callout']==LABEL
    redo=client.post(prefix+'/history/redo',json={'commandId':undo['commands']['redo']['id']}).json()
    assert redo['marks'][0]['callout']==shifted
    # Older callers do not silently erase the new on-drawing text placement.
    old=client.put(prefix+'/marks/'+first['id'],json=mark(version=redo['marks'][0]['version'],body='Legacy client edit')).json()
    assert old['callout']==shifted
    hidden=client.put(prefix+'/marks/'+first['id'],json=mark(version=old['version'],callout=None)).json()
    assert hidden['callout'] is None
    history=client.get(prefix+'/marks/'+first['id']+'/history').json()['revisions']
    assert history[-1]['snapshot']['callout']==LABEL


@pytest.mark.parametrize('label',[[.8,.2,.5,.4],[0,0,2,.3],[.2,.2,.2,.5],[.1,.2,.3],['wrong',.2,.5,.6]])
def test_callout_geometry_is_validated(api,label):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    assert client.post(prefix+'/marks',json=mark(callout=label)).status_code==422
    assert client.get(prefix).json()['marks']==[]


def test_pdf_visible_group_roundtrip_and_offline_text_box_edits(api,tmp_path):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    saved=client.post(prefix+'/marks',json=mark(callout=LABEL,body='Verify door clearance.')).json()
    response=client.get(prefix+'/export/pdf');assert response.status_code==200,response.text if response.status_code!=200 else ''
    reader=PdfReader(BytesIO(response.content));annots=[a.get_object() for a in reader.pages[0]['/Annots']]
    label=next(a for a in annots if str(a.get('/NM','')).startswith('edesign-callout:'))
    leader=next(a for a in annots if str(a.get('/NM','')).startswith('edesign-leader:'))
    assert label['/Subtype']=='/FreeText' and label['/Contents']=='Verify door clearance.' and '/AP' in label
    assert leader['/Subtype']=='/Line' and leader['/LE'][-1]=='/OpenArrow'
    assert label['/RT']=='/Group' and label['/IRT']['/NM']=='edesign:'+saved['id']
    assert json.loads(reader.attachments[ATTACHMENT][0])['marks'][0]['callout']==LABEL
    path=tmp_path/'callout.pdf';path.write_bytes(response.content)
    parsed=read_review(path);assert len(parsed['marks'])==1;assert parsed['marks'][0]['callout']==LABEL
    same=client.post(prefix+'/import',files={'file':('same.pdf',response.content,'application/pdf')})
    assert same.status_code==200 and same.json()['importSummary']['updated']==0
    # PDFium independently renders both text and leader without opening a popup.
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(response.content) as pdf:
        bitmap=pdf[0].render(scale=2,draw_annots=True)
        try:
            image=bitmap.to_pil().convert('RGB');crop=image.crop((int(.49*image.width),int(.33*image.height),int(.77*image.width),int(.45*image.height)))
            assert sum(max(rgb)<150 for rgb in crop.get_flattened_data())>20
        finally:bitmap.close()
    writer=PdfWriter();writer.clone_document_from_reader(reader)
    label=next(a.get_object() for a in writer.pages[0]['/Annots'] if str(a.get_object().get('/NM','')).startswith('edesign-callout:'))
    label[NameObject('/Contents')]=TextStringObject('Offline visible label changed.')
    label[NameObject('/Rect')]=ArrayObject([FloatObject(float(v)+30 if i in (0,2) else float(v)) for i,v in enumerate(label['/Rect'])])
    stream=BytesIO();writer.write(stream)
    result=client.post(prefix+'/import',files={'file':('feedback.pdf',stream.getvalue(),'application/pdf')})
    assert result.status_code==200,result.text
    actual=result.json()['marks'][0];assert actual['body']=='Offline visible label changed.'
    assert actual['callout']==pytest.approx([.53,.32,.83,.46])
    assert len(result.json()['marks'])==1
    assert client.get(prefix+'/original').content==pdf_bytes()


def test_rotated_callouts_report_html_and_view_only_permissions(api,tmp_path):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    saved=client.post(prefix+'/marks',json=mark(page=2,callout=LABEL,body='Inspect motor <M1> clearance.')).json()
    path=tmp_path/'rotated.pdf';path.write_bytes(client.get(prefix+'/export/pdf').content)
    parsed=read_review(path);assert len(parsed['marks'])==1
    assert parsed['marks'][0]['box']==mark()['box'];assert parsed['marks'][0]['callout']==LABEL
    report=PdfReader(BytesIO(client.get(prefix+'/export/report').content))
    assert 'Inspect motor <M1> clearance.' in report.pages[1].extract_text()
    html=client.get(prefix+'/export/html').text
    assert 'class="callout"' in html and 'Inspect motor &lt;M1&gt; clearance.' in html and '<polyline' in html
    client.post(prefix+'/share',json={'userId':2,'access':'view'})
    assert client.get(prefix,headers={'x-user':'2'}).json()['marks'][0]['callout']==LABEL
    assert client.put(prefix+'/marks/'+saved['id'],headers={'x-user':'2'},json=mark(page=2,callout=LABEL,version=1)).status_code==403
