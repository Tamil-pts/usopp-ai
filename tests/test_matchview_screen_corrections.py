from copy import deepcopy
from io import BytesIO
from pathlib import Path
from PIL import Image,ImageChops
from backend.core.compare_exports import _report_blocks,export_pdf,export_docx
from backend.core.compare_screen_notes import notes,views,options
from backend.core.compare_screen_preview import preview_png,preview_cache
from tests.test_compare_hmi_report import sample


def layered_sample():
    result=sample();diff=result['diffs'][0];parsed=diff['parsed_screen']
    for key in ('base','new'):
        layout=parsed['layouts'][key]
        layout['layers'].append({'id':'Diagnostics','name':'Diagnostics','left':0,'top':0,'hidden':True,'properties':{},'controls':[
          {'id':'Diagnostics/HiddenText','name':'HiddenText','class':'Text','status':'modified','left':210,'top':150,'width':90,'height':40,
           'properties':{'BackColor':'#ccffcc'},'effective_properties':{'BackColor':'#ccffcc'},'texts':{'en':'Diagnostic '+key},'datapoint':''}]})
    parsed['controls'].extend([
      {'name':'Diagnostics/HiddenText','class':'Text','status':'modified','base':{'properties':{'Text':'Diagnostic base'}},'new':{'properties':{'Text':'Diagnostic new'}}},
      {'name':'Default/Added','class':'Numeric','status':'added','base':None,'new':{'properties':{'ValueDatapoint':'Local.NewSignal'}}},
      {'name':'Default/Removed','class':'Button','status':'removed','base':{'properties':{'Text':'Removed button'}},'new':None}
    ])
    return result


def test_notes_have_stable_ids_names_layers_and_exact_direction():
    result=layered_sample();diff=result['diffs'][0];before=deepcopy(result)
    records,markers=notes(diff,_report_blocks(diff),1)
    assert records[0]['id']=='CN-001-001'
    assert records[0]['name']=='Numeric_1' and records[0]['layer']=='Default'
    row=records[0]['rows'][0];assert (row['label'],row['base'],row['developed'])==('Left','143','116')
    assert markers['Default/Numeric_1']=='1' and records[0]['marker']=='1'
    assert 'not present in Base' in next(r for r in records if r['status']=='added')['summary']
    assert 'removed from Developed' in next(r for r in records if r['status']=='removed')['summary']
    assert result==before


def test_layer_views_include_hidden_layer_without_mutating_source_visibility(tmp_path):
    result=layered_sample();diff=result['diffs'][0];before=deepcopy(diff)
    records,markers=notes(diff,_report_blocks(diff),1)
    token=preview_cache.set(tmp_path)
    try:
        named=views(diff,options(result),markers)
        assert [r['title'] for r in named]==['Normally visible layers','All layers / Default','All layers / Diagnostics']
        assert 'hidden in configuration' in named[2]['note']
        # The diagnostic control remains absent from the normal-view pixel area.
        normal=Image.open(BytesIO(named[0]['previews']['base']));hidden=Image.open(BytesIO(named[2]['previews']['base']))
        assert normal.getpixel((460,350))!=hidden.getpixel((460,350))
        result['reportSelection']['screenLayerViews']=['visible']
        assert len(views(diff,options(result),markers))==1
        result['reportSelection']['screenControlNames']=False
        unnamed=views(diff,options(result),markers)[0]['previews']['base']
        assert ImageChops.difference(Image.open(BytesIO(unnamed)),normal).getbbox()
        assert len(list(tmp_path.glob('*.png')))>=8
    finally:preview_cache.reset(token)
    assert diff==before


def test_pdf_and_word_explain_each_control_and_keep_both_layer_views(tmp_path):
    result=layered_sample();before=deepcopy(result)
    pdf=tmp_path/'corrections.pdf';word=tmp_path/'corrections.docx';logo=tmp_path/'missing.png'
    export_pdf(result,pdf,logo);export_docx(result,word,logo)
    from pypdf import PdfReader
    from docx import Document
    text='\n'.join(page.extract_text() for page in PdfReader(pdf).pages)
    document=Document(word);word_text='\n'.join([p.text for p in document.paragraphs]+[c.text for table in document.tables for row in table.rows for c in row.cells])
    for value in ['Correction notes / Base to Developed','CN-001-001','Numeric_1','Diagnostics','Normally visible layers','Before / Base','After / Developed','143','116','Local.NewSignal','Removed button']:
        assert value in text,value
        assert value in word_text,value
    assert len(document.inline_shapes)==6
    assert result==before


def test_a_single_normal_layer_is_not_duplicated_and_names_are_optional():
    result=sample();diff=result['diffs'][0];records,markers=notes(diff,_report_blocks(diff),1)
    rendered=views(diff,options(result),markers)
    assert len(rendered)==1 and 'single layer' in rendered[0]['title']
    layout=diff['parsed_screen']['layouts']['base']
    assert preview_png(layout)!=preview_png(layout,show_control_names=True,annotations=markers)


def test_long_correction_values_split_across_pdf_pages_without_truncation(tmp_path):
    result=sample();control=result['diffs'][0]['parsed_screen']['controls'][0]
    control['base']['properties']['Text']='Original description. '*500
    control['new']['properties']['Text']='Updated description. '*500+'END-OF-CORRECTION'
    path=tmp_path/'long.pdf';export_pdf(result,path,tmp_path/'none.png')
    from pypdf import PdfReader
    reader=PdfReader(path);assert len(reader.pages)>2
    assert 'END-OF-CORRECTION' in '\n'.join(p.extract_text() for p in reader.pages)
