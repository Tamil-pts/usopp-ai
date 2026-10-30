"""Accuracy fixtures: re-export invariance, glyph recovery and circuit topology."""
from io import BytesIO
from pathlib import Path

import pdfplumber
import pytest
import reportlab
from fontTools.ttLib import TTFont
from PIL import Image,ImageDraw
from pypdf import PdfReader,PdfWriter
from pypdf.generic import ArrayObject,DictionaryObject,NameObject,NumberObject,TextStringObject,DecodedStreamObject
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from python_engine.circuit_pdf import extraction_copy
from python_engine.circuit_objects import build_scene,uncovered_lines
from python_engine.circuit_compare import compare_drawings,_segments,compare_annotations


def _stream(data):
    value=DecodedStreamObject();value.set_data(data);return value


def cid_pdf(path,with_unicode=False):
    font_path=Path(reportlab.__file__).parent/'fonts'/'Vera.ttf'
    raw=font_path.read_bytes()
    with TTFont(BytesIO(raw)) as font:
        cmap=font.getBestCmap();text='SHRINK X1-1 ≥7.3';gids=[font.getGlyphID(cmap[ord(c)]) for c in text]
    writer=PdfWriter();page=writer.add_blank_page(width=500,height=300)
    descriptor=DictionaryObject({NameObject('/Type'):NameObject('/FontDescriptor'),NameObject('/FontName'):NameObject('/Vera'),
        NameObject('/Flags'):NumberObject(4),NameObject('/FontBBox'):ArrayObject([NumberObject(-1000),NumberObject(-1000),NumberObject(2000),NumberObject(2000)]),
        NameObject('/ItalicAngle'):NumberObject(0),NameObject('/Ascent'):NumberObject(900),NameObject('/Descent'):NumberObject(-200),
        NameObject('/CapHeight'):NumberObject(700),NameObject('/StemV'):NumberObject(80),NameObject('/FontFile2'):writer._add_object(_stream(raw))})
    cid=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/CIDFontType2'),NameObject('/BaseFont'):NameObject('/Vera'),
        NameObject('/CIDSystemInfo'):DictionaryObject({NameObject('/Registry'):TextStringObject('Adobe'),NameObject('/Ordering'):TextStringObject('Identity'),NameObject('/Supplement'):NumberObject(0)}),
        NameObject('/FontDescriptor'):writer._add_object(descriptor),NameObject('/CIDToGIDMap'):NameObject('/Identity'),NameObject('/DW'):NumberObject(600)})
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type0'),NameObject('/BaseFont'):NameObject('/Vera'),
        NameObject('/Encoding'):NameObject('/Identity-H'),NameObject('/DescendantFonts'):ArrayObject([writer._add_object(cid)])})
    if with_unicode:
        rows='\n'.join(f'<{gid:04x}> <{c.encode("utf-16-be").hex()}>' for gid,c in dict(zip(gids,text)).items())
        count=len(dict(zip(gids,text)))
        font[NameObject('/ToUnicode')]=writer._add_object(_stream((f'/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n1 begincodespacerange <0000> <ffff> endcodespacerange\n{count} beginbfchar\n{rows}\nendbfchar endcmap end end').encode('ascii')))
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    page[NameObject('/Contents')]=writer._add_object(_stream(('BT /F1 14 Tf 40 220 Td <'+''.join(f'{n:04x}' for n in gids)+'> Tj ET').encode('ascii')))
    with path.open('wb') as f:writer.write(f)
    return path


def test_missing_unicode_is_recovered_from_its_own_embedded_font(tmp_path):
    path=cid_pdf(tmp_path/'missing.pdf')
    original=path.read_bytes();copy,info=extraction_copy(PdfReader(path))
    with pdfplumber.open(copy) as doc:assert 'SHRINK X1-1 ≥7.3' in doc.pages[0].extract_text()
    assert info['recoveredFonts'] and not info['originalModified']
    assert path.read_bytes()==original


def test_equal_render_with_and_without_unicode_map_has_no_differences(tmp_path):
    a=cid_pdf(tmp_path/'a.pdf',True);b=cid_pdf(tmp_path/'b.pdf')
    result=compare_drawings(a,b,tmp_path/'out')
    assert result['summary']['changes']==0
    assert result['pairs'][0]['status']=='unchanged'


def export_pdf(path,scale=1,shift=(0,0),stroke=.8,quality=95):
    c=canvas.Canvas(str(path),pagesize=(842,595));c.translate(*shift);c.scale(scale,scale);c.setLineWidth(stroke)
    c.rect(15,20,812,555);c.line(15,540,827,540);c.line(15,65,827,65)
    c.setFont('Helvetica',10);c.drawString(70,480,'M1 MAIN MOTOR / X1-1 / X2-1');c.drawString(90,330,'4 x 1.5 SQMM');c.drawString(90,300,'Length 3.0m')
    c.line(100,400,400,400);c.line(400,400,400,360)
    image=Image.new('RGB',(200,100),'#e6d2ad');draw=ImageDraw.Draw(image);draw.ellipse((10,10,95,90),fill='#126f72');draw.rectangle((105,20,180,80),fill='#bc3026')
    encoded=BytesIO();image.save(encoded,format='JPEG',quality=quality);encoded.seek(0);c.drawImage(ImageReader(encoded),500,250,200,100)
    c.showPage();c.save();return path


def test_export_scale_translation_line_weight_and_jpeg_noise_are_not_engineering_changes(tmp_path):
    a=export_pdf(tmp_path/'a.pdf');b=export_pdf(tmp_path/'b.pdf',scale=.995,shift=(2,1.5),stroke=.65,quality=65)
    result=compare_drawings(a,b,tmp_path/'out')
    assert result['summary']['changes']==0
    assert result['pairs'][0]['visual']['registration']['method']=='matched inner drawing-frame vectors'
    assert result['pairs'][0]['visual']['equivalentPhotos']==1
    for issue in result['uncertainFindings']:
        if issue['evidenceKind']=='visual':
            bounds=(issue['before'] or issue['after'])['bbox']
            assert (bounds[2]-bounds[0])*(bounds[3]-bounds[1])<.12


def _scene(path,kind):
    c=canvas.Canvas(str(path),pagesize=(500,500));c.setFont('Helvetica',8)
    c.line(100,250,350,250)
    c.drawString(82,247,'X1-1');c.drawString(353,247,'X2-1')
    if kind=='ambiguous':c.line(100,247,350,247)
    if kind=='assembly':c.drawString(40,420,'S.No 1 CABLE KIT 4 x 1.5 SQMM')
    if kind=='cycle':
        c.line(180,250,180,300);c.line(180,300,280,300);c.line(280,300,280,250)
    if kind in ('crossing','dot','tee'):
        c.line(220,250 if kind=='tee' else 130,220,370)
        if kind=='dot':c.circle(220,250,1.2,stroke=0,fill=1)
    c.showPage();c.save()
    with pdfplumber.open(path) as pdf:
        page=pdf.pages[0];segments=_segments(page.extract_words(),page.width,page.height)
        return build_scene(page,segments,[])


def test_terminal_labels_have_an_inspectable_continuous_candidate_path(tmp_path):
    graph=_scene(tmp_path/'simple.pdf','simple')
    assert {v['reference'] for v in graph['terminals']}=={'X1-1','X2-1'}
    assert graph['connections'] and {graph['connections'][0]['from'],graph['connections'][0]['to']}=={'X1-1','X2-1'}
    assert graph['connections'][0]['lineIds'] and graph['connections'][0]['path']
    assert graph['coverage']['netlistVerified'] is False


def test_crossing_is_not_a_junction_but_endpoint_and_dot_are(tmp_path):
    crossing=_scene(tmp_path/'cross.pdf','crossing')
    dot=_scene(tmp_path/'dot.pdf','dot');tee=_scene(tmp_path/'tee.pdf','tee')
    assert crossing['crossings'] and not any(n['degree']>=3 for n in crossing['vertices'])
    assert not dot['crossings'] and any(n['degree']==4 for n in dot['vertices'])
    assert not tee['crossings'] and any(n['degree']==3 for n in tee['vertices'])


def test_split_collinear_primitives_have_equal_line_coverage():
    source=[{'id':'W1','points':[[.1,.5],[.9,.5]]}]
    target=[{'id':'A','points':[[.1,.5],[.5,.5]]},{'id':'B','points':[[.5,.5],[.9,.5]]}]
    assert uncovered_lines(source,target,[1,1,0,0],1000,1000)==[]


def test_ambiguous_nearby_terminal_associations_do_not_create_connections(tmp_path):
    graph=_scene(tmp_path/'ambiguous.pdf','ambiguous')
    assert not graph['connections'] and not graph['terminalAssociations']


def test_cable_assembly_and_cyclic_outlines_are_not_electrical_connections(tmp_path):
    for kind in ('assembly','cycle'):
        graph=_scene(tmp_path/f'{kind}.pdf',kind)
        assert not graph['connections'] and graph['geometricPaths']
        assert 'not' in graph['geometricPaths'][0]['status']


def test_explicit_connection_table_is_separate_from_proximity(tmp_path):
    path=tmp_path/'table.pdf';c=canvas.Canvas(str(path),pagesize=(500,500));c.showPage();c.save()
    table={'category':'Connections','bbox':[.1,.1,.9,.5],'rows':[{'identity':'1','cells':[
        {'label':'SIDE-A / source','text':'X1-1','bbox':[.1,.1,.3,.2]},
        {'label':'SIDE-B / destination','text':'X2-4','bbox':[.5,.1,.8,.2]}]}]}
    with pdfplumber.open(path) as pdf:graph=build_scene(pdf.pages[0],[],[table])
    assert len(graph['connections'])==1 and graph['connections'][0]['from']=='X1-1' and graph['connections'][0]['to']=='X2-4'
    assert 'Explicit printed' in graph['connections'][0]['status']


def test_moved_equal_labels_and_split_pin_numbers_are_not_removed_and_added():
    a={'number':1,'tables':[],'segments':[{'text':'M1','bbox':[.1,.1,.15,.12]},
       {'text':'6 14','bbox':[.1,.3,.2,.32],'tokens':[{'text':'6','bbox':[.1,.3,.12,.32]},{'text':'14','bbox':[.18,.3,.2,.32]}]}]}
    b={'number':1,'tables':[],'segments':[{'text':'M1','bbox':[.7,.7,.75,.72]},
       {'text':'6','bbox':[.7,.3,.72,.32]},{'text':'14','bbox':[.78,.3,.8,.32]}]}
    assert compare_annotations(a,b)==[]


def test_changed_moved_cable_spec_is_one_modified_field():
    a={'number':1,'tables':[],'segments':[{'text':'16 x 0.75 Sq.mm','bbox':[.1,.1,.3,.12]}]}
    b={'number':1,'tables':[],'segments':[{'text':'12x0.75Sq.mm','bbox':[.7,.7,.9,.72]}]}
    changes=compare_annotations(a,b)
    assert len(changes)==1 and changes[0]['status']=='modified' and changes[0]['category']=='Cable specifications'
