"""Real worksheet fixtures, generated SELECTs and source ownership regressions."""
import io,json,time
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests import test_document_comparison as fixture
from backend.core import spreadsheet_bi as core,spreadsheet_bi_export as exports,document_comparison as files

USER={'id':1,'createdAt':'one','role':'admin'}
OTHER={'id':2,'createdAt':'two','role':'admin'}
@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(files,'WORK',tmp_path/'work')
    yield

def upload(body=None):
    value=files.upload(USER,'source.csv',body or b'Date,Line,Production,Hours\n2026-01-01,A,10,2\n2026-01-02,B,20,4\n2026-02-01,A,30,6\n2026-02-02,B,40,8\n')
    return {'id':value['id'],'sheet':'CSV','header_row':1}

def test_auto_profiles_decimal_kpis_chart_rules_and_cache():
    p=upload();r=core.build(USER,p)
    assert r['rows']==4 and r['columns'][2]['sum']==100 and r['columns'][3]['mean']==5
    assert [c['spec']['chart'] for c in r['charts']]==['line','bar','scatter','histogram','donut']
    assert r['charts'][2]['correlation']==pytest.approx(1)
    assert sum(v['y'] for v in r['charts'][3]['points'])==4
    with patch.object(core,'prepare_columns',side_effect=AssertionError('Cached profile rebuilt')):
        assert core.build(USER,p)['cached'] is True

def test_monthly_trends_keep_series_and_aggregate_all_rows():
    p=upload();r=core.answer(USER,{**p,'question':'show monthly Production by Line'})
    assert r['kind']=='chart' and r['plannedBy']=='deterministic'
    assert [(p['x'][:7],p['series'],p['y']) for p in r['chart']['points']]==[('2026-01','A',10),('2026-01','B',20),('2026-02','A',30),('2026-02','B',40)]
    assert 'A 2026-01' in r['answer'] and 'B 2026-01' in r['answer']
    r=core.answer(USER,{**p,'question':'Show monthly Production'})
    assert [p['y'] for p in r['chart']['points']]==[30,70]

@pytest.mark.parametrize('value',[{'chart':'bar','x':100,'y':2},{'chart':'bar','x':True,'y':2},{'chart':'bar','y':1},
 {'chart':'line','x':1,'y':2},{'chart':'scatter','x':1,'y':2},{'chart':'bar','y':2,'sql':"SELECT * FROM read_csv('/secret')"},
 {'chart':'bar','y':2,'python':'import os'},{'chart':'bar','y':2,'time_bucket':'month'},{'chart':'pie','y':2}])
def test_invalid_specs_never_execute(value):
    p=upload();columns=core.build(USER,p)['columns']
    with pytest.raises(ValueError):core.validate_spec(value,columns)

def test_filters_are_not_silently_ignored_or_delegated_to_math_model():
    p=upload()
    with patch('backend.core.assist_model.chat_model',side_effect=AssertionError('Unsupported filter reached model')):
        for q in ['total Production by Line for A','show monthly Production only A','count failed rows','sum Production where Line=A']:
            assert core.answer(USER,{**p,'question':q})['kind']=='clarification'

def test_decimal_values_identifiers_ambiguous_dates_missing_errors_and_outliers():
    p=upload(b'ID,Local date,Value\n001,01/02/2026,0.1\n002,02/02/2026,0.2\n003,03/02/2026,100\n004,04/02/2026,0.3\n005,05/02/2026,0.4\n006,06/02/2026,\n')
    r=core.build(USER,p)
    assert r['columns'][0]['kind']=='category' and r['columns'][1]['kind']=='category'
    assert r['columns'][2]['sum']==101 and r['columns'][2]['missingCells']==['C7'] and r['columns'][2]['outliers']==1
    assert r['charts'][0]['spec']['chart']=='bar' # No guessed date trend.

def test_model_receives_only_profile_and_can_propose_but_not_calculate():
    p=upload(b'Team,Hours\nCONFIDENTIAL_A,10\nCONFIDENTIAL_B,20\n')
    seen=[]
    def model(system,prompt,**kw):
        seen.append(prompt);return {'answer':'{"chart":"bar","x":0,"y":1}'}
    with patch('backend.core.assist_model.configuration',return_value={'provider':'api','baseUrl':'http://127.0.0.1:8202/v1'}),patch('backend.core.assist_model.chat_model',side_effect=model):
        r=core.answer(USER,{**p,'question':'Make a useful comparison'})
    assert r['plannedBy']=='local_model_proposal' and [p['y'] for p in r['chart']['points']]==[20,10]
    assert 'CONFIDENTIAL' not in seen[0] and 'schema' not in seen[0] # Profile only; no cells or samples.
    with patch('backend.core.assist_model.configuration',return_value={'provider':'api','baseUrl':'https://remote.invalid/v1'}),patch('backend.core.assist_model.chat_model',side_effect=AssertionError('Remote call')):
        assert core.answer(USER,{**p,'question':'Make a useful comparison'})['kind']=='clarification'

def test_duckdb_has_no_external_access_or_extension_autoload():
    p=upload();_,columns,rows,_=core.read(USER,p);columns=core.prepare_columns(columns,rows)
    with core.connection(columns,rows) as db:
        assert db.execute("select current_setting('enable_external_access')").fetchone()[0] is False
        with pytest.raises(Exception):db.execute("select * from read_csv('C:/Windows/win.ini')")
        with pytest.raises(Exception):db.execute("INSTALL httpfs")

def test_donut_many_categories_negative_measure_and_sparse_data_are_explicit():
    p=upload(('Group,Value\n'+''.join(f'{i},-{i+1}\n' for i in range(8))).encode());r=core.build(USER,p)
    assert not any(c['spec']['chart']=='donut' for c in r['charts'])
    with pytest.raises(ValueError):core.validate_spec({'chart':'donut','x':0,'y':1},r['columns'])
    p=upload(b'Group,Value\nA,-1\nB,2\n');r=core.build(USER,p)
    with core.connection(r['columns'],core.read(USER,p)[2]) as db:
        with pytest.raises(ValueError):core.compute(db,{'chart':'donut','x':0,'y':1},r['columns'])
    assert core.build(USER,upload(b'Name,Value\n'))['rows']==0

def test_saved_snapshot_owner_isolation_source_changes_and_recreated_identity():
    p=upload();r=core.build(USER,p);saved=core.save(USER,{**p,'title':'Weekly review'})
    assert core.saved(USER,saved['id'])['snapshot'] is True
    for other in [OTHER,{**USER,'createdAt':'recreated'}]:
        with pytest.raises(HTTPException):core.saved(other,saved['id'])
    path,_=files.source(USER,p['id']);path.write_bytes(b'changed')
    with pytest.raises(HTTPException) as error:core.build(USER,p)
    assert error.value.status_code==409
    assert core.saved(USER,saved['id'])['dashboard']['source']['sha256']==r['source']['sha256']

def test_background_profile_job_is_owner_bound():
    p=upload();job=core.start(USER,p)['jobId']
    with pytest.raises(HTTPException):core.job(OTHER,job)
    for _ in range(200):
        value=core.job(USER,job)
        if value['status']!='running':break
        time.sleep(.03)
    assert value['status']=='ready',value

def test_portable_exports_include_same_source_and_values_without_active_html():
    p=upload();html=exports.export(USER,{**p,'title':'<script>alert(1)</script>'},'html').decode()
    assert '&lt;script&gt;' in html and '<script>' not in html and 'source.csv' in html and '100.0' in html
    pdf=exports.export(USER,p,'pdf');assert pdf.startswith(b'%PDF')
    import fitz
    doc=fitz.open(stream=pdf,filetype='pdf');text=''.join(page.get_text() for page in doc);doc.close()
    assert 'source.csv' in text and 'Production' in text and '100.0' in text

class TestAPI(fixture.DocumentComparisonTests):
    def test_actual_handlers_complete_start_query_save_and_exports(self):
        source=self.upload('data.csv',b'Team,Hours\nA,2\nB,3\n');p={'id':source['id'],'sheet':'CSV','header_row':1}
        api='/api/assist/datasets/bi'
        key=self.client.post(api+'/start',json=p).json()['jobId']
        for _ in range(200):
            r=self.client.get(api+'/jobs/'+key).json()
            if r['status']!='running':break
            time.sleep(.03)
        assert r['status']=='ready',r
        r=self.client.post(api+'/question',json={**p,'question':'total Hours by Team'});assert r.status_code==200,r.text
        assert [p['y'] for p in r.json()['chart']['points']]==[3,2]
        saved=self.client.post(api+'/dashboards',json={**p,'title':'Demo'}).json();assert 'id' in saved
        assert self.client.get(api+'/dashboards').json()['dashboards'][0]['title']=='Demo'
        assert self.client.post(api+'/export/pdf',json=p).content.startswith(b'%PDF')
        self.login(self.other)
        assert self.client.get(api+'/dashboards/'+saved['id']).status_code==404
        assert self.client.get(api+'/jobs/'+key).status_code==404


def test_explicit_filters_are_parameterized_and_pin_recomputes_not_trusts_points():
    p=upload();spec={'chart':'bar','x':1,'y':2,'filters':[{'column':1,'value':'A'}]}
    result=core.answer(USER,{**p,'question':'Explicit chart selection','spec':spec})
    assert sum(v['y'] for v in result['chart']['points'])==40
    assert result['chart']['parameters']==['A']
    spec['filters'][0]['value']="A' OR 1=1 --"
    result=core.answer(USER,{**p,'question':'Explicit chart selection','spec':spec})
    assert result['chart']['points']==[] and "A' OR" not in result['chart']['sql']
    spec['filters'][0]['value']='A'
    saved=core.save(USER,{**p,'title':'Pinned','specs':[spec]})
    chart=core.saved(USER,saved['id'])['dashboard']['charts'][-1]
    assert sum(v['y'] for v in chart['points'])==40
    assert b'WHERE' not in exports.export(USER,{**p,'dashboardId':saved['id']},'pdf')


def test_summary_rejects_unknown_ids_and_new_claims_and_returns_computed_words():
    p=upload()
    with patch('backend.core.assist_model.configuration',return_value={'provider':'ollama','baseUrl':'http://127.0.0.1:11434'}):
        for text in ['{"insightIds":["made-up"]}','{"insightIds":["I1"],"text":"total 999"}','{"insightIds":["I1","I1"]}']:
            with patch('backend.core.assist_model.chat_model',return_value={'answer':text}):assert core.summarize(USER,p)['modelUsed'] is False
        with patch('backend.core.assist_model.chat_model',return_value={'answer':'{"insightIds":["I1"]}'}):
            result=core.summarize(USER,p)
            assert result['modelUsed'] is True and result['insights']==[core.build(USER,p)['insights'][0]]


def test_default_profile_cache_is_separate_for_workbook_sheets():
    from openpyxl import Workbook
    book=Workbook();book.active.title='One';book.active.append(['Value']);book.active.append([10]);two=book.create_sheet('Two');two.append(['Value']);two.append([20]);out=io.BytesIO();book.save(out);book.close()
    file=files.upload(USER,'two.xlsx',out.getvalue())
    one=core.build(USER,{'id':file['id'],'sheet':'One','header_row':1})
    two=core.build(USER,{'id':file['id'],'sheet':'Two','header_row':1})
    assert one['columns'][0]['sum']==10 and two['columns'][0]['sum']==20
