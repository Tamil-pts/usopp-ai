"""Portable HMI report data preserves paired evidence and safe print fallback."""
from copy import deepcopy
import json
from pathlib import Path
import re

from backend.core.compare_exports import export_html,export_pdf,export_docx
from backend.core.hmi_difference_filter import filter_screen_properties


def sample():
    def record(left):
        return {'name':'Numeric_1','class':'Numeric','class_id':'0x1007','properties':{'Left':str(left),'Top':'51','Width':'70','Height':'21','ValueDatapoint':'Local.PRG0[1]','BackColor':'#ffffaa'}}
    def layout(left,extra=False):
        c={'id':'Default/Numeric_1',**record(left),'left':left,'top':51,'width':70,'height':21,'status':'modified','effective_properties':record(left)['properties'],'texts':{},'datapoint':'Local.PRG0[1]'}
        controls=[c,{'id':'Default/Same','name':'Same','class':'Text','class_id':'0x1004','left':10,'top':10,'width':90,'height':20,'status':'unchanged','properties':{},'effective_properties':{},'texts':{'en':'Unchanged caption'},'datapoint':''}]
        if extra:controls.append({**c,'id':'Default/Added','name':'Added','left':10,'top':80,'status':'added','texts':{'en':'New field'}})
        return {'name':'Process0_1','width':320,'height':240,'properties':{'BackColor':'#ffffbb'},'palette':{},'warnings':[],
                'layers':[{'id':'Default','name':'Default','left':0,'top':0,'hidden':False,'properties':{},'controls':controls}]}
    diff={'path':'Logical/HMI/Pages/Process0_1.page','category':'screen','status':'modified','base_relative_path':'Logical/HMI/Pages/Process0_1.page','new_relative_path':'Logical/HMI/Pages/Process0_1.page',
          'parsed_screen':{'controls':[{'name':'Default/Numeric_1','class':'Numeric','status':'modified','base':record(143),'new':record(116),'changes':[{'prop':'Left','base':'143','new':'116','group':'Position'}]}],
                           'layouts':{'base':layout(143),'new':layout(116,True)}}}
    return {'baseName':'LR9SXV6318','newName':'LR9SXV6319','summary':{'modified':1},'diffs':[diff],
            'reportSelection':{'categories':['screen'],'statuses':['modified'],'includeKnowledge':False}}


def payload(text):
    return json.loads(re.search(r'<script type="application/json" data-hmi-data>(.*?)</script>',text,re.S)[1])


def test_interactive_data_keeps_all_controls_and_printable_evidence(tmp_path):
    result=sample();original=deepcopy(result);target=tmp_path/'report.html'
    export_html(result,target,tmp_path/'missing.png');text=target.read_text(encoding='utf-8');data=payload(text)
    assert result==original
    assert data['baseLabel']=='LR9SXV6318' and data['newLabel']=='LR9SXV6319'
    base=data['screen']['layouts']['base']['layers'][0]['controls'];new=data['screen']['layouts']['new']['layers'][0]['controls']
    assert base[0]['id']==new[0]['id']=='Default/Numeric_1'
    assert base[0]['effective_properties']['Left']=='143' and new[0]['effective_properties']['Left']=='116'
    assert any(c['status']=='unchanged' for c in base) and any(c['status']=='added' for c in new)
    assert 'class="report-hmi-static"' in text and 'base static HMI preview' in text
    assert 'detail-row modified' in text and '143' in text and '116' in text


def test_report_escapes_untrusted_screen_text_and_retains_skip_layout_choice(tmp_path):
    result=sample();result['diffs'][0]['parsed_screen']['layouts']['base']['layers'][0]['controls'][0]['texts']['en']='</script><script>alert("unsafe")</script>'
    # Keep a non-layout difference so this screen remains included after filtering.
    control=result['diffs'][0]['parsed_screen']['controls'][0]
    control['new']['properties']['ValueDatapoint']='Local.NewValue'
    control['changes'].append({'prop':'ValueDatapoint','base':'Local.PRG0[1]','new':'Local.NewValue'})
    result['diffs'][0]['parsed_screen']['changes']=[{'type':'control_modified','name':control['name'],'changes':deepcopy(control['changes'])}]
    target=tmp_path/'report.html';export_html(filter_screen_properties(result),target,tmp_path/'missing.png');text=target.read_text(encoding='utf-8');data=payload(text)
    assert data['skipLayout'] is True
    assert '</script><script>alert(' not in text
    assert data['screen']['layouts']['base']['layers'][0]['controls'][0]['texts']['en']=='</script><script>alert("unsafe")</script>'
    assert data['screen']['layouts']['base']['layers'][0]['controls'][0]['left']==143  # Geometry stays real.


def test_screens_without_layouts_and_print_exports_keep_existing_details(tmp_path):
    result=sample();result['diffs'][0]['parsed_screen'].pop('layouts')
    target=tmp_path/'static.html';export_html(result,target,tmp_path/'missing.png')
    text=target.read_text(encoding='utf-8');assert 'data-hmi-report' not in text and 'Default/Numeric_1' in text
    result=sample()
    for kind,exporter in [('pdf',export_pdf),('docx',export_docx)]:
        target=tmp_path/('report.'+kind);exporter(result,target,tmp_path/'missing.png');assert target.stat().st_size>1000
    from pypdf import PdfReader
    assert '143' in '\n'.join(page.extract_text() for page in PdfReader(tmp_path/'report.pdf').pages)
    from docx import Document
    doc=Document(tmp_path/'report.docx');assert any('143' in cell.text for table in doc.tables for row in table.rows for cell in row.cells)
