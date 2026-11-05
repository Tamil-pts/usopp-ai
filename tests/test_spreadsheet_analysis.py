"""Worksheet calculations, source fidelity, downloads and authenticated ownership."""
import csv
import io
import unittest
from datetime import date
from unittest.mock import patch

from openpyxl import Workbook,load_workbook
from tests import test_document_comparison as fixture
from backend.core import document_comparison as store

API='/api/assist/datasets'

def workbook(sheets):
    book=Workbook();book.remove(book.active)
    for name,rows in sheets.items():
        ws=book.create_sheet(name)
        for row in rows:ws.append(row)
    out=io.BytesIO();book.save(out);book.close();return out.getvalue()

class SpreadsheetTests(unittest.TestCase):
    setUpClass=classmethod(fixture.DocumentComparisonTests.setUpClass.__func__)
    setUp,tearDown,login=fixture.DocumentComparisonTests.setUp,fixture.DocumentComparisonTests.tearDown,fixture.DocumentComparisonTests.login

    def upload(self,name,body):
        response=self.client.post(API+'/uploads',files={'file':(name,body)});self.assertEqual(response.status_code,200,response.text[:500]);return response.json()
    def analyze(self,source,**options):
        payload={'id':source['id'],'sheet':source['sheets'][0]['name'],'header_row':1,**options}
        response=self.client.post(API+'/analyze',json=payload);self.assertEqual(response.status_code,200,response.text[:600]);return response.json()

    def test_profile_aggregates_iqr_missing_and_repeated_rows_from_actual_cells(self):
        source=self.upload('measurements.csv',b'Group,Value,Channel\nA,1,X\nA,2,X\nB,3,Y\nB,4,Y\nB,100,Y\nC,,Z\nA,1,X\n,,\n')
        result=self.analyze(source,group=0,metric=1,operation='sum')
        self.assertEqual((result['rows'],result['blank_cells'],result['duplicates'],result['empty_rows']),(7,1,1,1))
        self.assertEqual(result['value'],111);self.assertEqual(result['columns'][1]['mean'],18.5)
        self.assertEqual([(row['label'],row['value']) for row in result['categories']],[('A',4),('B',107),('C',None)])
        self.assertEqual(result['outlier_count'],1);self.assertEqual(result['outliers'][0]['cell'],'B6')
        self.assertEqual(result['issues'][0]['cells'],['B7'])
        self.assertTrue(any('not proven' in note for note in result['notes']))

    def test_worksheet_switching_and_later_header_never_mix_sheets(self):
        source=self.upload('two.xlsx',workbook({'First':[['Code','Value'],['A',10]],'Second':[['Report title'],['Code','Value'],['B',20],['C',30]]}))
        first=self.analyze(source,metric=1,operation='sum')
        second=self.analyze(source,sheet='Second',header_row=2,metric=1,operation='sum')
        self.assertEqual((first['rows'],first['value']),(1,10));self.assertEqual((second['rows'],second['value']),(2,50))
        self.assertEqual(second['preview'][0]['row'],3);self.assertEqual(second['source']['sheet'],'Second')

    def test_csv_numeric_identity_dates_and_precision_are_not_guessed(self):
        source=self.upload('types.csv',b'ID,Value,Date,Ambiguous,Precise\n001,-3,2026-11-01,"1,000",9007199254740993\n002,0.1,2026-11-02,10%,1e-999\n003,0.2,2026-11-03,=5+5,0\n')
        result=self.analyze(source,metric=1,operation='sum')
        self.assertEqual(result['value'],-2.7)
        self.assertEqual(result['columns'][0]['numeric'],0);self.assertEqual(result['columns'][2]['numeric'],0)
        self.assertEqual(result['columns'][3]['numeric'],0);self.assertEqual(result['columns'][4]['numeric'],1)
        self.assertEqual(result['preview'][0]['cells'][0],'001')

    def test_formulas_without_cached_results_are_errors_not_zero_or_evaluated(self):
        source=self.upload('formulas.xlsx',workbook({'Data':[['Value','Date','Bool'],['=1+2',date(2026,11,1),True],[5,date(2026,11,2),False]]}))
        result=self.analyze(source,metric=0,operation='sum')
        self.assertEqual(result['value'],5);self.assertEqual(result['error_cells'],1)
        self.assertEqual(result['preview'][0]['cells'][0],'[No stored formula result]')
        self.assertEqual(result['columns'][1]['numeric'],0);self.assertEqual(result['columns'][2]['numeric'],0)

    def test_pivot_count_sum_and_empty_intersections_preserve_missing_values(self):
        source=self.upload('pivot.csv',b'Area,Shift,Value\nA,Day,10\nA,Night,20\nB,Day,5\n')
        result=self.analyze(source,group=0,pivot=1,metric=2,operation='sum')
        self.assertEqual(result['pivot_table']['rows'][0]['values'],[10,20])
        self.assertEqual(result['pivot_table']['rows'][1]['values'],[5,None])
        result=self.analyze(source,group=0,pivot=1,operation='count')
        self.assertEqual(result['pivot_table']['rows'][1]['values'],[1,0])

    def test_chart_inspection_finds_source_rows_beyond_initial_preview(self):
        content='Group,Value\n'+''.join(f'{"B" if i>=120 else "A"},{i}\n' for i in range(130))
        source=self.upload('long.csv',content.encode());result=self.analyze(source,group=0)
        group=result['categories'][1];response=self.client.post(API+'/rows',json={'id':source['id'],'sheet':'CSV','group':0,'category_id':group['id']})
        self.assertEqual(response.status_code,200);rows=response.json()
        self.assertEqual(rows['total'],10);self.assertEqual(rows['rows'][0]['row'],122)

    def test_same_caption_empty_group_is_distinct_from_literal_blank_label(self):
        source=self.upload('blank.csv',b'Group,Value\n,1\n(blank),2\n')
        result=self.analyze(source,group=0,metric=1,operation='sum')
        self.assertEqual(result['group_count'],2);self.assertNotEqual(result['categories'][0]['id'],result['categories'][1]['id'])

    def test_downloads_retain_all_rows_and_guard_formula_like_source_text(self):
        raw=b'Name,Value\n"=HYPERLINK(""bad"")",-3\n"a,b",4\n'
        source=self.upload('safe.csv',raw);payload={'id':source['id'],'sheet':'CSV','header_row':1}
        response=self.client.post(API+'/export/csv',json=payload);self.assertEqual(response.status_code,200)
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertTrue(rows[1][0].startswith("'="));self.assertEqual(rows[1][1],'-3');self.assertEqual(rows[2][0],'a,b')
        response=self.client.post(API+'/export/xlsx',json=payload);self.assertEqual(response.status_code,200)
        book=load_workbook(io.BytesIO(response.content));self.assertNotEqual(book.active['A2'].data_type,'f');self.assertEqual(book.active.max_row,3);book.close()
        self.assertEqual(self.client.get(API+'/'+source['id']+'/source').content,raw)
        self.assertEqual(self.client.post(API+'/export/json',json=payload).json()['rows'],2)

    def test_accounts_anonymous_stale_source_and_invalid_settings(self):
        source=self.upload('data.csv',b'Name,Value\nA,10\n');payload={'id':source['id'],'sheet':'CSV','group':0}
        self.login(self.other)
        for route in ['/analyze','/export/csv','/rows']:
            response=self.client.post(API+route,json={**payload,'category_id':'x'});self.assertEqual(response.status_code,404)
        self.assertEqual(self.client.get(API+'/'+source['id']+'/source').status_code,404)
        self.client.cookies.clear();self.assertEqual(self.client.post(API+'/analyze',json=payload).status_code,401)
        self.login(self.user)
        for options in [{'sheet':'Missing'},{'group':True},{'metric':99},{'operation':'eval'},{'header_row':-1}]:
            self.assertEqual(self.client.post(API+'/analyze',json={**payload,**options}).status_code,400)
        path,_=store.source(self.user,source['id']);path.write_bytes(b'changed')
        self.assertEqual(self.client.post(API+'/analyze',json=payload).status_code,409)
        self.assertEqual(self.client.post(API+'/export/xlsx',json=payload).status_code,409)

    def test_empty_data_wide_sheet_and_non_numeric_measure_have_explicit_results(self):
        source=self.upload('empty.csv',b'Name,Value\n')
        result=self.analyze(source);self.assertEqual(result['rows'],0);self.assertEqual(result['value'],0)
        source=self.upload('text.csv',b'Name,Value\nA,not numeric\n')
        self.assertEqual(self.client.post(API+'/analyze',json={'id':source['id'],'sheet':'CSV','metric':1,'operation':'sum'}).status_code,422)
        source=self.upload('wide.xlsx',workbook({'Data':[['C'+str(i) for i in range(257)],[1]*257]}))
        self.assertEqual(self.client.post(API+'/analyze',json={'id':source['id'],'sheet':'Data'}).status_code,422)
        self.assertEqual(self.client.post(API+'/uploads',files={'file':('a.exe',b'bad')}).status_code,400)

    def test_standard_chat_attachment_accepts_generic_sheet_without_model(self):
        response=self.client.post('/api/assist/attachment',files={'file':('ordinary.xlsx',workbook({'First':[['Category','Cost'],['A',12]],'Notes':[['Note'],['Actual source note']]}))})
        self.assertEqual(response.status_code,200,response.text[:500]);data=response.json()
        self.assertEqual([s['name'] for s in data['dataset']['sheets']],['First','Notes'])
        self.assertTrue(data['readable'])

    def test_recognized_report_keeps_legacy_analysis_and_exact_header_row(self):
        from backend.core import report_analysis
        from backend.core import access
        from pathlib import Path
        raw=workbook({'Report':[['Production report'],[],['Machine','Date','Production Kg'],['M1',date(2026,11,1),10],['M2',date(2026,11,1),20]]})
        with patch.object(report_analysis,'WORK',Path(self.temp.name)/'reports'),patch.object(access,'WORK',Path(self.temp.name)):
            response=self.client.post('/api/assist/attachment',files={'file':('production.xlsx',raw)})
            self.assertEqual(response.status_code,200,response.text[:500]);data=response.json()
            self.assertIn('report',data);self.assertEqual(data['dataset']['header_rows']['Report'],3)
            dashboard=self.client.post('/api/assist/reports/dashboard',json={'reportIds':[data['report']['id']]})
            self.assertEqual(dashboard.status_code,200,dashboard.text[:400])

if __name__=='__main__':unittest.main()
