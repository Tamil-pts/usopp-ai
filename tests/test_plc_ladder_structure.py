"""Known contact/coil graph changes, including small but meaningful marks."""
import io
from reportlab.pdfgen.canvas import Canvas
from tests.test_plc_comparison_evidence import run


def diagram(nc=False,parallel=False,dx=0,dy=0,tag='A',gap=0,unsupported=False,coil=True,second=True,glyph_nc=False):
    output=io.BytesIO();c=Canvas(output,pagesize=(612,792));c.setFont('Helvetica',9)
    c.drawString(180,760,'PROJECT / CONTROL');c.drawString(50,730,'Block: CONTROL')
    c.drawString(50,680,'Network 1');c.saveState();c.translate(dx,dy)
    def contact(x,y,label,closed=False):
        c.drawString(x-2,y+20,label);c.line(x,y-8,x,y+8);c.line(x+20,y-8,x+20,y+8)
        if closed:
            if glyph_nc:c.drawString(x+8,y-3,'/')
            else:c.line(x+7,y-6,x+13,y+6)
    c.line(60,530,60,640);c.line(60,600,90,600);contact(90,600,tag,nc)
    if parallel:
        c.line(110,600,230,600);c.line(60,550,90,550);contact(90,550,'B')
        c.line(110,550,180,550);c.line(180,550,180,600)
    elif second:
        c.line(110,600,150,600);contact(150,600,'B')
        if gap:
            c.line(170,600,195,600);c.line(195+gap,600,230,600)
        else:c.line(170,600,230,600)
    else:c.line(110,600,230,600)
    if coil:
        c.drawString(235,620,'M1')
        for x,side in ((230,1),(260,-1)):
            p=c.beginPath();p.moveTo(x+side*4,608)
            p.curveTo(x+side,606,x,603,x,600)
            p.curveTo(x,597,x+side,594,x+side*4,592)
            c.drawPath(p)
    if unsupported:
        c.rect(330,550,70,40);c.drawString(340,570,'TON')
    c.restoreState();c.save();return output.getvalue()


def network(a,b):return run(a,b)[-1]


def test_recognizes_contacts_and_coil_on_complete_network():
    row=network(diagram(),diagram())
    assert row['structure']['supported'],row['structure']
    assert row['structure']['base_symbols']==[('A','NO'),('B','NO'),('M1','coil')]
    assert row['structure']['same']


def test_small_diagonal_changes_no_to_nc_even_when_raster_is_inconclusive():
    from unittest.mock import patch
    from backend.core import plc_pdf_comparison as plc
    original=plc.pixel_diff
    def blank(*args,**kwargs):
        metric,image=original(*args,**kwargs);metric['changed_pixels']=0;return metric,image
    with patch.object(plc,'pixel_diff',side_effect=blank):row=network(diagram(),diagram(nc=True))
    assert row['status']=='modified',row
    assert row['structure']['changes']==[{'operand':'A','before':'NO','after':'NC'}]
    assert 'A: NO -> NC' in row['assessment']['reason']


def test_series_to_parallel_changes_connections_with_same_operands():
    row=network(diagram(),diagram(parallel=True))
    assert row['structure']['supported'],row['structure']
    assert row['structure']['connections_changed']
    assert row['status']=='modified'


def test_moved_supported_network_retains_connections():
    row=network(diagram(),diagram(dx=25,dy=-22))
    assert row['structure']['supported'],row['structure']
    assert row['structure']['same']
    assert row['status']=='unchanged'


def test_operand_rename_is_retained():
    row=network(diagram(),diagram(tag='X1'))
    assert row['status']=='modified'
    assert row['structure']['changes']


def test_nc_contact_mark_printed_as_glyph_is_recognized():
    row=network(diagram(),diagram(nc=True,glyph_nc=True))
    assert row['structure']['supported'],row['structure']
    assert row['structure']['changes']==[{'operand':'A','before':'NO','after':'NC'}]


def test_added_and_removed_contact_keep_explicit_identity():
    for a,b,before,after in ((diagram(second=False),diagram(),None,'NO'),
                             (diagram(),diagram(second=False),'NO',None)):
        row=network(a,b)
        assert row['structure']['supported'],row['structure']
        assert row['status']=='modified'
        assert row['structure']['changes']==[{'operand':'B','before':before,'after':after}]


def test_small_wire_gap_is_not_closed_by_terminal_tolerance():
    row=network(diagram(),diagram(gap=.5))
    assert not row['structure']['supported']
    assert not row['structure']['same']
    assert row['status']!='unchanged'


def test_unknown_timer_box_cannot_authorize_structural_equivalence():
    row=network(diagram(unsupported=True),diagram(dx=10,unsupported=True))
    assert not row['structure']['supported']
    assert row['structure']['open_checks']


def test_missing_coil_does_not_become_complete_network():
    row=network(diagram(),diagram(coil=False))
    assert not row['structure']['supported']
    assert row['status']!='unchanged'


def test_repeated_operands_are_not_merged_into_one_instance():
    row=network(diagram(tag='B'),diagram(tag='B',dx=12))
    assert not row['structure']['supported']
    assert 'Repeated operands require explicit instance matching.' in row['structure']['open_checks']


def test_timer_literal_edit_still_uses_source_comparison():
    from tests.test_plc_pdf_comparison import program
    row=network(program([[(1,'Timer1(IN := Ready, PT := T#5s);')]]),
                program([[(1,'Timer1(IN := Ready, PT := T#10s);')]]))
    assert row['status']=='modified'
    assert not row['structure']['supported']
    assert 'T#5s' in row['base'] and 'T#10s' in row['compared']


def test_unsupported_recognition_format_falls_back_without_losing_source_changes():
    from unittest.mock import patch
    from backend.core import plc_pdf_comparison as plc
    with patch.object(plc.ladder,'recognize',side_effect=ValueError('Unsupported fixture profile')):
        row=network(diagram(),diagram(tag='X1'))
    assert row['status']=='modified'
    assert not row['structure']['supported']
    assert row['structure']['open_checks']


def test_windows_concurrent_cache_publisher_reuses_only_identical_complete_bytes(tmp_path):
    from pathlib import Path
    from unittest.mock import patch
    from backend.core.document_pdf_comparison import save_cache
    target=tmp_path/'network.png';target.write_bytes(b'complete immutable image')
    with patch.object(Path,'replace',side_effect=PermissionError('Windows sharing violation')):
        save_cache(target,b'complete immutable image')
    assert target.read_bytes()==b'complete immutable image'
    assert list(tmp_path.glob('*.tmp'))==[]
