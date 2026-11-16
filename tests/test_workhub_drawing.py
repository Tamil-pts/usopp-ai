"""Drawing persistence, source provenance and export boundaries."""
import io,json,unittest
from copy import deepcopy
from pathlib import Path
import pytest
from fastapi import HTTPException
from pypdf import PdfReader
from backend.core.workhub_intelligence import store,documents
from backend.core import workhub_drawing as drawing
from tests import test_workhub_independent_diagrams as fixtures

def content():
    return {'diagram_type':'flowchart','workspace':{'schema_version':2,'pages':[{'id':'p1','name':'Control','paper':'A4','orientation':'landscape','background':'#ffffff'},{'id':'p2','name':'Handover','paper':'A3','orientation':'portrait','background':'#ffffff'}],
        'layers':[{'id':'main','name':'Drawing','visible':True,'locked':False},{'id':'notes','name':'Notes','visible':False,'locked':True}],'grid':True,'snap':True,'snap_objects':True,'rulers':False,'units':'mm'},
        'nodes':[{'id':'start','width':360,'height':120,'position':{'x':80,'y':100},'data':{'kind':'process','page_id':'p1','layer_id':'main','label':'Control review','group_id':'g1','appearance':{'fill':'#cceeff','stroke':'#123456','font':'Arial','font_size':18,'bold':True,'dash':'dashed','rotation':30,'opacity':.8},'symbol':{'id':'relay','library_id':'custom','version':'1','source':'Original engineer drawing','license':'Author content','asset':{'shape':'path','path':'M0 50 H30 M70 50 H100'},'ports':[{'id':'in','x':0,'y':.5,'direction':'input','domain':'signal'},{'id':'out','x':1,'y':.5,'direction':'output','domain':'signal'}]}}},
        {'id':'hidden','position':{'x':20,'y':20},'data':{'kind':'note','label':'Hidden internal note','page_id':'p1','layer_id':'notes'}},
        {'id':'next','position':{'x':30,'y':60},'data':{'kind':'end','label':'Handover accepted','page_id':'p2','layer_id':'main'}}],'edges':[]}

def test_styles_pages_and_hidden_layers_export_with_original_geometry():
    c=content();c['nodes'][0]['data']['symbol']['asset']={'shape':'rect'};store.validate_content('flowchart',c);pages=drawing.svg_pages(c)
    assert len(pages)==2
    assert 'width="1123" height="794"' in pages[0][1]
    assert 'width="1123" height="1587"' in pages[1][1]
    assert 'Hidden internal note' not in pages[0][1]
    for token in ['#cceeff','#123456','rotate(30)','font-size="18"','Control review']:
        assert token in pages[0][1]
    assert 'Handover accepted' in drawing.svg(c)
    from svglib.svglib import svg2rlg
    assert svg2rlg(io.BytesIO(pages[0][1].encode())).width==1123

@pytest.mark.parametrize('modify',[
    lambda c:c['workspace'].update(schema_version=999),
    lambda c:c['workspace']['pages'].append(c['workspace']['pages'][0]),
    lambda c:c['nodes'][0]['data'].update(page_id='missing'),
    lambda c:c['nodes'][0]['data']['appearance'].update(fill='url(https://example.com/a)'),
    lambda c:c['nodes'][0]['data']['appearance'].update(rotation=float('nan')),
    lambda c:c['nodes'][0]['data']['appearance'].update(backgroundImage='url(file:///C:/secret)'),
    lambda c:c['nodes'][0]['data']['symbol']['asset'].update(path='M0 0 <script/>'),
    lambda c:c['nodes'][0]['data']['symbol']['asset'].update(path='M1e99 0'),
    lambda c:c['edges'].append({'id':'cross','source':'start','target':'next'}),
])
def test_malformed_or_external_drawing_content_is_rejected(modify):
    c=content();modify(c)
    with pytest.raises(HTTPException):store.validate_content('flowchart',c)

def test_catalogue_has_traceable_assets_for_all_twelve_groups():
    root=Path(__file__).resolve().parents[1]
    cat=json.loads((root/'knowledge/master/drawing_libraries.json').read_text())
    assert len(cat['groups'])==12
    ids=[]
    for group in cat['groups']:
        for lib in group['libraries']:
            assert all(lib.get(k) for k in ('source','license','version'))
            assert lib['symbols']
            for s in lib['symbols']:drawing.asset(s['asset']);ids.append(s['id'])
    assert len(ids)==279 and len(set(ids))==279

class DrawingPersistenceTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.IndependentDiagramTests.setUpClass.__func__)
    setUp=fixtures.IndependentDiagramTests.setUp
    tearDown=fixtures.IndependentDiagramTests.tearDown
    login=fixtures.IndependentDiagramTests.login
    request=fixtures.IndependentDiagramTests.request
    create=fixtures.IndependentDiagramTests.create
    def test_saved_version_two_reopens_with_review_and_multipage_exports(self):
        made=self.create();pid=made['scope_id'];did=made['document_id'];path=f'/projects/{pid}/intelligence/documents/{did}'
        saved=self.request('PUT',path,{'version':made['revision_id'],'content':content()});rid=saved['revision']['id']
        loaded=self.request('GET',path)['revisions'][0]
        assert loaded['content']['nodes'][0]['data']['symbol']['source']=='Original engineer drawing'
        assert loaded['content']['workspace']['pages'][1]['paper']=='A3'
        for extension in ('svg','pdf','json'):
            response=self.client.get('/api/workhub'+path+'/export/'+extension+'?revision_id='+rid)
            assert response.status_code==200,response.text[:300] if response.status_code!=200 else ''
            if extension=='pdf':
                text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(response.content)).pages)
                assert 'Control review' in text and 'Handover accepted' in text
                assert 'Hidden internal note' not in text
            elif extension=='json':assert response.json()['revision']['content']['nodes'][0]['width']==360
        self.login(self.outsider);self.request('GET',path,expected=403)
    def test_page_exports_select_exact_saved_page_and_require_access(self):
        made=self.create();pid=made['scope_id'];did=made['document_id'];path=f'/projects/{pid}/intelligence/documents/{did}'
        saved=self.request('PUT',path,{'version':made['revision_id'],'content':content()});rid=saved['revision']['id']
        base='/api/workhub'+path+'/export/'
        one=self.client.get(base+'svg',params={'revision_id':rid,'page_id':'p2'})
        assert one.status_code==200 and 'Handover accepted' in one.text and 'Control review' not in one.text
        one_pdf=self.client.get(base+'pdf',params={'revision_id':rid,'page_id':'p2'})
        assert one_pdf.status_code==200 and len(PdfReader(io.BytesIO(one_pdf.content)).pages)==1
        all_pdf=self.client.get(base+'pdf',params={'revision_id':rid,'page_id':'all'})
        assert all_pdf.status_code==200 and len(PdfReader(io.BytesIO(all_pdf.content)).pages)==2
        assert self.client.get(base+'svg',params={'page_id':'missing'}).status_code==404
        self.login(self.outsider)
        assert self.client.get(base+'pdf',params={'page_id':'all'}).status_code==403
