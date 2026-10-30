"""Reference electrical PDFs with known changes, independently of production data."""
from io import BytesIO
from pathlib import Path
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from python_engine.circuit_compare import compare_drawings, analysis, normalized, key
from python_engine.circuit_report import build_report


def drawing(path, version='base', pages=('drive', 'bom'), portrait=False):
    size = (595, 842) if portrait else (842, 595)
    c = canvas.Canvas(str(path), pagesize=size)
    for kind in pages:
        c.setFont('Helvetica', 12)
        if kind == 'drive':
            c.drawString(40, size[1] - 45, 'DRIVE MOTOR CONTROL / Drawing EL-100')
            c.drawString(40, size[1] - 70, 'Revision: ' + ('01' if version == 'new' else '00'))
            c.drawString(40, size[1] - 120, 'Cable: ' + ('4 x 2.5 SQMM, 5.0m' if version == 'new' else '4 x 1.5 SQMM, 3.0m'))
            c.drawString(40, size[1] - 165, 'X10-' + ('2(1)' if version == 'new' else '1(1)'))
            c.drawString(40, size[1] - 215, 'M2 fan motor' if version == 'new' else 'K1 control relay')
            if version == 'new': c.drawString(450, size[1] - 250, 'B4 proximity sensor added')
            else: c.drawString(450, size[1] - 350, 'S7 maintenance switch removed')
            c.line(70, 250, 400, 250)
            if version == 'new': c.line(400, 250, 400, 320)
            c.drawString(40, 30, 'SHEET 1 of 2')
        elif kind == 'bom':
            c.drawString(40, size[1] - 45, 'BOM / MATERIAL LIST / EL-200')
            data = [['S.No', 'Designation', 'Material number', 'Quantity'],
                    ['1', 'Drive cable', '409211590' if version == 'new' else '449211590', '3' if version == 'new' else '2'],
                    ['2', 'Switch', 'AB-122', '1']]
            table = Table(data, colWidths=[45, 130, 130, 75], rowHeights=30)
            table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), .5, colors.black)]))
            table.wrapOn(c, 500, 400); table.drawOn(c, 40, size[1] - 180)
            c.drawString(40, 30, 'SHEET 2 of 2')
        elif kind == 'extra':
            c.drawString(40, 500, 'PNEUMATIC VALVE BANK / Drawing EL-999 / NEW SHEET')
            c.drawString(40, 450, 'Y34 compressed air manifold and PNEUMATIC ISOLATION ASSEMBLY')
        elif kind == 'scan':
            image = Image.new('RGB', (500, 300), 'white'); d = ImageDraw.Draw(image); d.line((30, 50, 350, 50), fill='black', width=4)
            if version == 'new': d.line((350, 50, 350, 250), fill='black', width=4)
            from reportlab.lib.utils import ImageReader
            c.drawImage(ImageReader(image), 50, 100, 500, 300)
        c.showPage()
    c.save(); return path


@pytest.fixture(scope='module')
def reference(tmp_path_factory):
    root = tmp_path_factory.mktemp('circuits')
    base = drawing(root / 'base.pdf'); new = drawing(root / 'new.pdf', 'new')
    output = root / 'result'
    return root, base, new, compare_drawings(base, new, output)


def test_source_linked_engineering_changes_and_bom(reference):
    _, _, _, result = reference
    assert result['summary']['matchedPages'] == 2
    changes = result['changes']
    for category in ('Revision information', 'Cable specifications', 'Terminal mapping', 'Components', 'BOM'):
        assert any(c['category'] == category for c in changes), category
    assert any(c['status'] == 'added' and 'B4' in (c['after'] or {}).get('text', '') for c in changes)
    assert any(c['status'] == 'removed' and 'S7' in (c['before'] or {}).get('text', '') for c in changes)
    material = next(c for c in changes if c['category'] == 'BOM' and c['before']['text'] == '449211590')
    assert material['after']['text'] == '409211590' and material['before']['page'] == material['after']['page'] == 2
    assert any(c['category'] == 'BOM' and c['before']['text'] == '2' and c['after']['text'] == '3' for c in changes)
    assert all(c['review'] == 'pending' for c in changes)
    for c in changes:
        for ref in (c['before'], c['after']):
            if ref:
                assert 0 <= ref['bbox'][0] <= ref['bbox'][2] <= 1 and 0 <= ref['bbox'][1] <= ref['bbox'][3] <= 1
    findings = analysis(result)
    assert set(x for a in findings['areas'] for x in a['sourceIds']) == {c['id'] for c in changes}
    assert 'not been established' in findings['summary']


def test_same_pdf_has_no_changes(reference, tmp_path):
    _, base, _, _ = reference
    result = compare_drawings(base, base, tmp_path)
    assert result['summary']['changes'] == 0
    assert all(p['status'] == 'unchanged' for p in result['pairs'])


def test_content_matching_reorders_added_and_removed_pages(reference, tmp_path):
    _, base, _, _ = reference
    developed = drawing(tmp_path / 'reordered.pdf', pages=('bom', 'drive', 'extra'))
    result = compare_drawings(base, developed, tmp_path / 'reordered')
    assert [(p['base'], p['developed']) for p in result['pairs']] == [(1, 2), (2, 1), (None, 3)]
    assert result['summary']['reorderedPages'] == 2
    assert result['pairs'][-1]['status'] == 'added'
    reverse = compare_drawings(developed, base, tmp_path / 'reverse')
    assert any(p['base'] == 3 and p['developed'] is None and p['status'] == 'removed' for p in reverse['pairs'])


def test_scans_are_visual_only_and_page_match_is_unverified(tmp_path):
    base = drawing(tmp_path / 'a.pdf', pages=('scan',))
    new = drawing(tmp_path / 'b.pdf', 'new', pages=('scan',))
    result = compare_drawings(base, new, tmp_path / 'out')
    assert result['pairs'][0]['matchReview']
    assert result['changes'] and all(c['evidenceKind'] == 'visual' for c in result['changes'])
    assert all(c['extraction'] == 'needs verification' for c in result['changes'])
    assert 'No selectable text' in result['basePages'][0]['notices'][0]


def test_actual_pdf_field_values_are_not_reformatted_or_numeric_noise():
    assert key('3.150') == key('3.15')
    assert key('X10\u00ad1(1)') == key('X10-1(1)')
    assert normalized('449211590') != normalized('409211590')


def test_bom_columns_match_by_heading_and_duplicate_serials_are_not_lost():
    from python_engine.circuit_compare import compare_tables
    def cell(col, label, text): return {'column': col, 'label': label, 'text': text, 'bbox': [.1, .1, .2, .2], 'uncertain': False}
    a = {'number': 1, 'tables': [{'bbox': [0, 0, 1, 1], 'category': 'BOM', 'rows': [
        {'identity': '1', 'cells': [cell(0, 'S.No', '1'), cell(1, 'Material', 'AB-1'), cell(2, 'Quantity', '2')]}]}]}
    b = {'number': 2, 'tables': [{'bbox': [0, 0, 1, 1], 'category': 'BOM', 'rows': [
        {'identity': '1', 'cells': [cell(0, 'S.No', '1'), cell(1, 'Quantity', '3'), cell(2, 'Material', 'AB-1')]}]}]}
    changes = compare_tables(a, b)
    assert len(changes) == 1 and changes[0]['label'] == 'Item 1 · Quantity'
    assert changes[0]['before']['text'] == '2' and changes[0]['after']['text'] == '3'


def test_corrupted_unit_header_does_not_steal_exact_mass_column():
    from python_engine.circuit_compare import _column_pairs, uncertain_text
    a = [{'column': i, 'label': text} for i, text in enumerate(['Resistance (Ω/km)', 'For specified length (mΩ)', 'For specified length (kg)'])]
    b = [{'column': i, 'label': text} for i, text in enumerate(['Resistance (cid:159)', 'For specified length (cid:11)', 'For specified length (kg)'])]
    assert {(x['column'], y['column']) for x, y in _column_pairs(a, b)} == {(0, 0), (1, 1), (2, 2)}
    assert uncertain_text('(cid:159)')


def test_report_contains_change_ids_sources_and_review(reference, tmp_path):
    root, _, _, result = reference
    change = next(c for c in result['changes'] if c['category'] == 'BOM')
    change['review'] = 'confirmed'; change['note'] = 'Material replacement checked against source.'
    report = build_report(result, root / 'result', tmp_path / 'report.pdf')
    pages = PdfReader(report).pages
    text = '\n'.join(p.extract_text() for p in pages)
    assert len(pages) >= 3
    assert '449211590' in text and '409211590' in text
    assert change['id'] in text and 'Material replacement checked' in text
    assert 'electrical continuity' in text and 'Source-linked change register' in text


def test_portrait_report_fits(tmp_path):
    a = drawing(tmp_path / 'a.pdf', pages=('drive',), portrait=True)
    b = drawing(tmp_path / 'b.pdf', 'new', pages=('drive',), portrait=True)
    result = compare_drawings(a, b, tmp_path / 'out')
    build_report(result, tmp_path / 'out', tmp_path / 'portrait.pdf')
    assert PdfReader(tmp_path / 'portrait.pdf').pages


def test_invalid_and_encrypted_pdfs_fail_explicitly(reference, tmp_path):
    _, base, _, _ = reference
    writer = PdfWriter(); writer.append(base); writer.encrypt('password')
    with (tmp_path / 'locked.pdf').open('wb') as f: writer.write(f)
    with pytest.raises(ValueError, match='Password-protected'):
        compare_drawings(tmp_path / 'locked.pdf', base, tmp_path / 'locked')


@pytest.fixture
def api(tmp_path, monkeypatch):
    from backend.api import circuit_compare as module
    from backend.core.run_history import current_user
    monkeypatch.setattr(module, 'WORK', tmp_path)
    owners = {}
    def claim(path): owners[path.name] = current_user.get()['id']
    def require(sid):
        from fastapi import HTTPException
        if sid not in owners: raise HTTPException(404, 'Unknown session')
        if owners[sid] != current_user.get()['id']: raise HTTPException(403, 'Other user')
        return tmp_path / sid
    monkeypatch.setattr(module, 'claim_resource', claim); monkeypatch.setattr(module, 'require_session', require)
    app = FastAPI(); app.include_router(module.router)
    @app.middleware('http')
    async def identity(request, call_next):
        token = current_user.set({'id': request.headers.get('x-user', 'alice'), 'username': 'Alice'})
        try: return await call_next(request)
        finally: current_user.reset(token)
    with TestClient(app) as client: yield client, module


def test_actual_upload_status_result_assets_review_and_report(api, reference):
    client, module = api
    _, base, new, _ = reference
    response = client.post('/api/circuit-compare/start', files={'base': ('base.pdf', base.read_bytes(), 'application/pdf'), 'developed': ('new.pdf', new.read_bytes(), 'application/pdf')})
    assert response.status_code == 200
    sid = response.json()['sessionId']; prefix = f'/api/circuit-compare/{sid}'
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status = client.get(prefix + '/status').json()
        if status['status'] != 'running': break
        time.sleep(.05)
    assert status['status'] == 'complete', status
    data = client.get(prefix + '/result').json()
    assert data['summary']['changes'] > 0
    assert client.get(prefix + '/result', headers={'x-user': 'bob'}).status_code == 403
    assert client.get(prefix + '/image/base-1.png').headers['content-type'] == 'image/png'
    assert client.get(prefix + '/image/not-owned.png').status_code == 404
    assert client.get(prefix + '/original/base').content.startswith(b'%PDF-')
    graph=client.get(prefix+'/graph/base/1')
    assert graph.status_code==200 and graph.json()['labels'] and graph.json()['coverage']['netlistVerified'] is False
    assert client.get(prefix+'/graph/base/1',headers={'x-user':'bob'}).status_code==403
    assert client.get(prefix+'/graph/base/999').status_code==404
    change = data['changes'][0]
    saved = client.post(prefix + '/review/' + change['id'], json={'review': 'confirmed', 'note': 'Source drawing verified.'})
    assert saved.status_code == 200 and saved.json()['review'] == 'confirmed'
    assert client.get(prefix + '/result').json()['summary']['pendingReview'] == data['summary']['pendingReview'] - 1
    assert client.post(prefix + '/review/' + change['id'], json={'review': 'approved'}).status_code == 400
    assert client.get(prefix + '/analysis').json()['areas']
    monkey = pytest.MonkeyPatch()
    monkey.setattr('backend.core.assist_model.chat_model', lambda *a, **kw: None)
    try:
        prose = client.post(prefix + '/explain', json={'changeIds': [change['id']]}).json()
        assert prose['scope'] == [change['id']] and 'not enabled' in prose['notice']
    finally: monkey.undo()
    exported = client.get(prefix + '/report')
    assert exported.status_code == 200 and len(PdfReader(BytesIO(exported.content)).pages) >= 3
    assert client.get(prefix + '/export').json()['comparisonType'] == 'circuit'
    module._jobs.pop(sid)
    assert client.get(prefix + '/status').json()['status'] == 'complete'  # survives process-local cache loss
    repeated=client.post(prefix+'/recompare')
    assert repeated.status_code==200 and repeated.json()['sessionId']!=sid
    other=f"/api/circuit-compare/{repeated.json()['sessionId']}"
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        state=client.get(other+'/status').json()
        if state['status']!='running':break
        time.sleep(.05)
    assert state['status']=='complete'
    new=client.get(other+'/result').json()
    assert new['fingerprints']==data['fingerprints'] and all(c['review']=='pending' for c in new['changes'])
    assert next(c for c in client.get(prefix+'/result').json()['changes'] if c['id']==change['id'])['review']=='confirmed'


def test_upload_validation_releases_job_slot(api, reference):
    client, _ = api
    _, base, _, _ = reference
    for _ in range(3):
        response = client.post('/api/circuit-compare/start', files={'base': ('bad.pdf', b'not pdf'), 'developed': ('base.pdf', base.read_bytes())})
        assert response.status_code == 400


def test_explanation_rejects_invented_source_ids(api, reference, monkeypatch):
    client, module = api
    _, _, _, result = reference
    # Seed only this test's owned session through the same upload ownership hook.
    from backend.core.run_history import current_user
    token = current_user.set({'id': 'alice'})
    folder = module.WORK / 'circuit_test'; folder.mkdir(); module.claim_resource(folder); current_user.reset(token)
    (folder / 'circuit_manifest.json').write_text('{}')
    (folder / 'circuit_result.json').write_text(json.dumps(result))
    monkeypatch.setattr('backend.core.assist_model.chat_model', lambda *a, **kw: {'answer': '{"paragraphs":[{"text":"Unknown claim","sourceIds":["FAKE"]}]}', 'sentEvidence': kw['evidence']})
    response = client.post('/api/circuit-compare/circuit_test/explain', json={}).json()
    assert not response['paragraphs'] and 'valid source references' in response['notice']


def test_circuit_explanation_uses_actual_chat_model_return_interface():
    from backend.api.circuit_compare import _cited_paragraphs
    # chat_model returns verified, converted prose, not the original JSON body.
    result = _cited_paragraphs('[C00352] Material 449211590 changed to 409211590.\n\n[C00352] Verify the replacement specification.', {'C00352'})
    assert len(result) == 2 and result[0]['sourceIds'] == ['C00352']
    with pytest.raises(ValueError, match='valid source references'):
        _cited_paragraphs('[C99999] Unsupported claim.', {'C00352'})
    with pytest.raises(ValueError, match='valid source references'):
        _cited_paragraphs('Prose without citations.', {'C00352'})

def test_circuit_markup_review_and_exports(api, reference):
    import shutil
    from xml.etree import ElementTree
    from backend.core.run_history import current_user
    client,module=api
    root,base,developed,result=reference
    token=current_user.set({'id':'alice','username':'Alice'})
    folder=module.WORK/'circuit_markups';folder.mkdir();module.claim_resource(folder);current_user.reset(token)
    (folder/'circuit_manifest.json').write_text('{}',encoding='utf-8')
    (folder/'circuit_result.json').write_text(json.dumps(result),encoding='utf-8')
    shutil.copyfile(base,folder/'base.pdf');shutil.copyfile(developed,folder/'developed.pdf')
    for image in (root/'result').glob('*.png'):shutil.copyfile(image,folder/image.name)
    path='/api/circuit-compare/circuit_markups/markups'
    payload={'pairId':result['pairs'][0]['id'],'side':'base','shape':'cloud','color':'blue','box':[.1,.2,.3,.4],'text':'Check the terminal connection','status':'open'}
    created=client.post(path,json=payload);assert created.status_code==200,created.text
    mark=created.json();assert mark['author']=='Alice' and mark['page']==result['pairs'][0]['base']
    second=client.post(path,json={**payload,'side':'developed','shape':'arrow','color':'red','text':'=verify this change'});assert second.status_code==200
    assert client.get(path,headers={'x-user':'bob'}).status_code==403
    assert client.post(path,json={**payload,'box':[0,0,2,1]}).status_code==400
    updated=client.put(path+'/'+mark['id'],json={**mark,'status':'resolved','text':'Reviewed connection'});assert updated.status_code==200
    assert updated.json()['version']==2
    assert client.put(path+'/'+mark['id'],json=mark).status_code==409
    csv_text=client.get('/api/circuit-compare/circuit_markups/markups-export/csv').text
    assert "'=verify this change" in csv_text and 'Reviewed connection' in csv_text
    xml=client.get('/api/circuit-compare/circuit_markups/markups-export/xml');assert ElementTree.fromstring(xml.content).tag=='circuit-markups'
    report=client.get('/api/circuit-compare/circuit_markups/report');assert report.status_code==200
    rendered=' '.join(page.extract_text() or '' for page in PdfReader(BytesIO(report.content)).pages)
    assert 'Reviewed connection' in rendered and '=verify this change' in rendered
    editable=client.get('/api/circuit-compare/circuit_markups/editable-pdf');assert editable.status_code==200
    pdf=PdfReader(BytesIO(editable.content));assert len(pdf.pages)==4
    comments=[str(a.get_object().get('/Contents','')) for page in pdf.pages for a in page.get('/Annots',[])]
    assert 'Reviewed connection' in comments and '=verify this change' in comments
    html_report=client.get('/api/circuit-compare/circuit_markups/html');assert html_report.status_code==200
    assert 'data:image/png;base64,' in html_report.text and 'Reviewed connection' in html_report.text
    assert client.get('/api/circuit-compare/circuit_markups/editable-pdf',headers={'x-user':'bob'}).status_code==403
    assert client.get('/api/circuit-compare/circuit_markups/report?inline=1').headers['content-disposition'].startswith('inline;')
    assert client.delete(path+'/'+mark['id']+'?version=1').status_code==409
    assert client.delete(path+'/'+mark['id']+'?version=2').status_code==200
    assert len(client.get(path).json()['markups'])==1
    assert json.loads((folder/'circuit_result.json').read_text(encoding='utf-8'))==result

@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_editable_circuit_pdf_preserves_original_comments_and_rotated_positions(tmp_path,rotation):
    import hashlib
    from pypdf.generic import DictionaryObject,NameObject,ArrayObject,FloatObject,TextStringObject
    from python_engine.circuit_markup_export import editable_pdf
    from python_engine.edesign_pdf import read_review
    writer=PdfWriter();page=writer.add_blank_page(width=600,height=400);page.cropbox.lower_left=(40,30);page.cropbox.upper_right=(550,370);page.rotate(rotation)
    writer.add_annotation(0,DictionaryObject({NameObject('/Subtype'):NameObject('/Text'),NameObject('/Rect'):ArrayObject([FloatObject(60),FloatObject(60),FloatObject(80),FloatObject(80)]),NameObject('/Contents'):TextStringObject('Original drawing comment')}))
    for name in ('base.pdf','developed.pdf'):
        with (tmp_path/name).open('wb') as stream:writer.write(stream)
    before=hashlib.sha256((tmp_path/'base.pdf').read_bytes()).hexdigest()
    box=[.2,.3,.5,.65]
    marks=[{'id':'a'*32,'side':'base','page':1,'shape':'cloud','color':'blue','box':box,'text':'Review motor','status':'open','author':'Engineer','reverseX':False,'reverseY':False},
           {'id':'b'*32,'side':'developed','page':1,'shape':'arrow','color':'red','box':box,'text':'Move connector','status':'resolved','author':'Engineer','reverseX':True,'reverseY':False}]
    output=tmp_path/'editable.pdf';editable_pdf(tmp_path,{'developedName':'Test'},marks,output)
    parsed=read_review(output);a=next(item for item in parsed['marks'] if item['body']=='Review motor');b=next(item for item in parsed['marks'] if item['body']=='Move connector')
    assert len(parsed['marks'])==4 and a['page']==1 and b['page']==2
    assert all(abs(x-y)<.0001 for x,y in zip(a['box'],box)) and all(abs(x-y)<.0001 for x,y in zip(b['box'],box))
    assert b['reverseX'] and not b['reverseY'] and b['status']=='resolved'
    import pypdfium2 as pdfium
    from PIL import ImageChops
    with pdfium.PdfDocument(str(output)) as doc:
        page=doc[0]
        try:
            plain_bitmap=page.render(scale=1,draw_annots=False);marked_bitmap=page.render(scale=1,draw_annots=True)
            try:
                left,top,right,bottom=box;width,height=plain_bitmap.width,plain_bitmap.height
                area=(int(left*width),int(top*height),int(right*width),int(bottom*height))
                assert ImageChops.difference(plain_bitmap.to_pil().convert('RGB').crop(area),marked_bitmap.to_pil().convert('RGB').crop(area)).getbbox()
            finally:plain_bitmap.close();marked_bitmap.close()
        finally:page.close()
    assert hashlib.sha256((tmp_path/'base.pdf').read_bytes()).hexdigest()==before
