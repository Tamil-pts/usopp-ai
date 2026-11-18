"""Metamorphic regressions: print noise must not hide actual source edits."""
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from reportlab.pdfgen.canvas import Canvas
from backend.core import plc_pdf_comparison as plc
from tests.test_plc_pdf_comparison import program


def run(a, b, **options):
    with tempfile.TemporaryDirectory() as folder:
        files=[Path(folder)/name for name in ('before.pdf','after.pdf')]
        for path, content in zip(files,(a,b)):path.write_bytes(content)
        return plc.compare(files, options)[0]


def test_identical_source_fingerprints_skip_raster_comparison():
    content=program([[(1,'SM0.0 MOV_W MW30')]])
    with patch.object(plc,'pixel_diff') as raster:
        rows=run(content,content)
    raster.assert_not_called()
    assert all(r['status']=='unchanged' for r in rows)
    assert all(r['assessment']['source_corroborated'] for r in rows)


@pytest.mark.parametrize('before,after',[
    ('IF Ready THEN Motor := TRUE; END_IF;', 'IF Ready THEN Motor := FALSE; END_IF;'),
    ('Speed := 100;', 'Speed := 101;'),
    ("Name := 'A B';", "Name := 'AB';"),
    ('A := B; B := C;', 'B := C; A := B;'),
    ('V120.0 MOV_W +0 MW30','V120.1 MOV_W +0 MW30'),
])
def test_st_and_ladder_operand_edits_survive_repeated_comparisons(before,after):
    results=[run(program([[(1,before)]]),program([[(1,after)]])) for _ in range(2)]
    assert results[0]==results[1]
    assert results[0][-1]['status']=='modified'
    assert results[0][-1]['text_changed']


def drawing(offset=0,wire=False):
    out=io.BytesIO();c=Canvas(out,pagesize=(612,792))
    c.drawString(180,760,'PROJECT / MOTOR (SBR20)');c.drawString(50,730,'Block: MOTOR')
    c.drawString(50,680,'Network 1');c.drawString(90,610,'SM0.0 MOV_W MW30')
    c.line(70,590,450,590);c.rect(250,550+offset,100,70)
    if wire:c.line(170,590,170,530)
    c.save();return out.getvalue()


def test_equal_text_moved_geometry_requires_review_not_guessed_logic_change():
    row=run(drawing(),drawing(offset=20))[-1]
    assert row['status']=='unresolved'
    assert not row['text_changed']
    assert row['pixels']['changed_pixels']>0


def test_equal_text_added_wire_is_detected_from_both_geometry_and_pixels():
    row=run(drawing(),drawing(wire=True))[-1]
    assert row['status']=='modified'
    assert not row['text_changed']
    assert not row['assessment']['source_corroborated']


def test_print_precision_with_translation_and_rail_extension_is_corroborated():
    def printed(scale,shift,bottom):
        out=io.BytesIO();c=Canvas(out,pagesize=(612,792))
        c.drawString(180,760,'PROJECT / MOTOR');c.drawString(50,730,'Block: MOTOR')
        c.drawString(50,680,'Network 1')
        c.saveState();c.translate(shift,0);c.scale(scale,scale)
        c.drawString(90,610,'SM0.0 MOV_W MW30')
        c.line(70,650,70,bottom);c.line(70,590,450,590);c.rect(250,550,100,70)
        c.restoreState();c.drawString(50,450,'Network 2');c.drawString(90,420,'M1');c.save()
        return out.getvalue()
    original=plc.pixel_diff
    def noisy(*args,**kwargs):
        metric,image=original(*args,**kwargs);metric['changed_pixels']=1;return metric,image
    with patch.object(plc,'pixel_diff',side_effect=noisy):
        row=run(printed(1,0,475),printed(1.0001,15,480))[1]
    assert row['status']=='unchanged',row['assessment']
    assert row['assessment']['source_corroborated']


def test_small_unexplained_raster_change_is_not_silently_accepted():
    # Tiny counts alone must never be a pass threshold.
    from backend.core.plc_comparison_evidence import judge
    unit={'source_evidence':[]}
    assert judge(unit,unit,True,{'changed_pixels':1})['status']=='unresolved'


def test_curve_control_point_change_cannot_be_hidden_by_equal_endpoints():
    def curve(bend):
        out=io.BytesIO();c=Canvas(out,pagesize=(612,792))
        c.drawString(180,760,'PROJECT / MOTOR');c.drawString(50,730,'Block: MOTOR')
        c.drawString(50,680,'Network 1');c.drawString(90,610,'M1')
        c.bezier(200,550,210,550+bend,230,550+bend,240,550)
        c.save();return out.getvalue()
    row=run(curve(15),curve(-15))[-1]
    assert row['status']!='unchanged'
    assert not row['assessment']['source_corroborated']


def test_dash_style_change_cannot_be_certified_as_equal_vector_evidence():
    def dash(pattern):
        out=io.BytesIO();c=Canvas(out,pagesize=(612,792))
        c.drawString(180,760,'PROJECT / MOTOR');c.drawString(50,730,'Block: MOTOR')
        c.drawString(50,680,'Network 1');c.drawString(90,610,'M1')
        c.setDash(pattern);c.line(70,590,450,590);c.save();return out.getvalue()
    assert run(dash([]),dash([4,4]))[-1]['status']!='unchanged'


def test_native_st_keeps_control_flow_order_and_literal_changes():
    from python_engine.source_compare import source_diff
    before='IF Ready THEN\n Motor := TRUE;\nEND_IF;'
    for after in ('IF Ready THEN\n Motor := FALSE;\nEND_IF;',
                  'IF NOT Ready THEN\n Motor := TRUE;\nEND_IF;'):
        first=source_diff(before,after)
        assert first==source_diff(before,after)
        assert any(row['status']=='modified' for row in first['source_rows'])


def test_1001_pages_compare_with_last_page_change_and_pixels_enabled():
    pages=[[(i+1,'Motor := TRUE;') ] for i in range(1001)]
    before=program(pages)
    pages[-1]=[(1001,'Motor := FALSE;')]
    rows=run(before,program(pages),pixel_compare=True)
    assert len(rows)==1002
    assert rows[-1]['base_network']==1001
    assert rows[-1]['status']=='modified'
    assert all(r['status']=='unchanged' for r in rows[:-1])


def test_plc_page_limit_is_bounded():
    from fastapi import HTTPException
    with patch.object(plc.evidence,'MAX_PAGES',1):
        with pytest.raises(HTTPException,match='2,000 pages'):
            run(program([[(1,'A')],[(2,'B')]]),program([[(1,'A')]]))


def test_extraction_cache_respects_source_profile_and_account(tmp_path):
    files=[tmp_path/name for name in ('a.pdf','b.pdf')]
    for file,contents in zip(files,(program([[(1,'M1')]]),program([[(1,'M2')]]))):
        file.write_bytes(contents)
    cache=tmp_path/'first-account'
    original,*_,info=plc.compare(files,{},cache)
    assert info['extraction_cache_hits']==0
    with patch.object(plc,'extract',wraps=plc.extract) as extraction:
        repeated,*_,info=plc.compare(files,{},cache)
        assert info['extraction_cache_hits']==2 and extraction.call_count==0
        assert [row['assessment'] for row in original]==[row['assessment'] for row in repeated]
        assert plc.compare(files,{'compare_comments':False},cache)[-1]['extraction_cache_hits']==0
        assert plc.compare(files,{},tmp_path/'second-account')[-1]['extraction_cache_hits']==0
        files[-1].write_bytes(program([[(1,'M3')]]))
        assert plc.compare(files,{},cache)[-1]['extraction_cache_hits']==1
