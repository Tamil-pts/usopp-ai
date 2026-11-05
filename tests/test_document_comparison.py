"""Real uploads and production HTTP handlers with isolated account-owned storage."""
import csv
import io
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from openpyxl import Workbook
from backend.app import app
from backend.core import accounts,document_comparison as comparison
from backend.core.workhub import store as hub


def xlsx(rows):
    book=Workbook();sheet=book.active;sheet.title='Data'
    for row in rows:sheet.append(row)
    out=io.BytesIO();book.save(out);book.close();return out.getvalue()


class DocumentComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.hash=accounts.password_hash('Comparison.Fixture.2026')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.stack=ExitStack()
        self.stack.enter_context(patch.object(comparison,'WORK',Path(self.temp.name)/'work'))
        self.store=accounts.AccountStore(Path(self.temp.name)/'accounts.sqlite3')
        self.stack.enter_context(patch.object(accounts,'store',self.store))
        self.stack.enter_context(patch.object(accounts,'password_hash',return_value=self.hash))
        self.stack.enter_context(patch.object(hub,'root',Path(self.temp.name)/'hub'))
        self.user=self.store.register('compare_owner','x','Engineer','Fixture')
        self.other=self.store.register('compare_other','x','Engineer','Fixture')
        self.client=TestClient(app);self.login(self.user)

    def tearDown(self):
        self.client.close();self.stack.close();self.temp.cleanup()

    def login(self,user):
        self.client.cookies.clear();self.client.cookies.set(accounts.COOKIE,self.store.new_session(user['id']))

    def upload(self,name,body,status=200):
        response=self.client.post('/api/assist/document-comparisons/uploads',files={'file':(name,body)})
        self.assertEqual(response.status_code,status,response.text[:700]);return response.json()

    def run_pair(self,a,b,**options):
        payload={'base':{'id':a['id'],'sheet':a['sheets'][0]['name'] if a['sheets'] else '', 'header_row':1},'compared':{'id':b['id'],'sheet':b['sheets'][0]['name'] if b['sheets'] else '', 'header_row':1},**options}
        return self.client.post('/api/assist/document-comparisons/run',json=payload)

    def test_selected_columns_key_alignment_and_source_cells(self):
        a=self.upload('old.xlsx',xlsx([['ID','Value','Ignored'],[1,10,'a'],[2,20,'b'],[3,30,'c']]))
        b=self.upload('new.xlsx',xlsx([['Key','Ignored','Result'],[3,'changed',30],[1,'changed',11],[4,'new',40]]))
        schema=self.client.get(f"/api/assist/document-comparisons/uploads/{a['id']}/columns",params={'sheet':'Data','header_row':1}).json()
        self.assertEqual([c['name'] for c in schema['columns']],['ID','Value','Ignored'])
        response=self.run_pair(a,b,columns=[{'base':0,'compared':0},{'base':1,'compared':2}],keys=[0],match_by='key');self.assertEqual(response.status_code,200,response.text)
        data=response.json();self.assertEqual(data['summary'],{'added':1,'removed':1,'modified':1,'unchanged':1,'unresolved':0})
        modified=next(r for r in data['rows'] if r['status']=='modified')
        self.assertEqual(modified['key'],'1');self.assertEqual(modified['cells'][1]['base']['ref'],'Data!B2');self.assertEqual(modified['cells'][1]['compared']['ref'],'Data!C3')
        self.assertEqual(modified['cells'][1]['compared']['value'],'11')

    def test_csv_xlsx_cross_format_and_optional_type_comparison(self):
        a=self.upload('old.csv',b'ID;Value\r\n1;10\r\n2;20\r\n')
        b=self.upload('new.xlsx',xlsx([['ID','Value'],[1,10],[2,20]]))
        opts={'columns':[{'base':0,'compared':0},{'base':1,'compared':1}], 'keys':[0],'match_by':'key'}
        data=self.run_pair(a,b,**opts).json();self.assertEqual(data['summary']['unchanged'],2)
        opts.update(match_by='row',compare_types=True)
        data=self.run_pair(a,b,**opts).json();self.assertEqual(data['summary']['modified'],2)

    def test_duplicate_and_blank_keys_are_not_guessed(self):
        a=self.upload('keys.csv',b'Key,Sub,Value\n1,A,10\n1,B,20\n')
        b=self.upload('other.csv',b'Key,Sub,Value\n1,B,20\n1,A,10\n')
        opts={'columns':[{'base':0,'compared':0},{'base':1,'compared':1},{'base':2,'compared':2}],'keys':[0],'match_by':'key'}
        response=self.run_pair(a,b,**opts);self.assertEqual(response.status_code,422);self.assertIn('duplicate key',response.json()['detail'])
        opts['keys']=[0,1];self.assertEqual(self.run_pair(a,b,**opts).json()['summary']['unchanged'],2)
        c=self.upload('missing.csv',b'Key,Sub,Value\n,A,10\n')
        self.assertIn('blank',self.run_pair(a,c,**opts).json()['detail'])

    def test_formula_cache_missing_is_unresolved_and_formula_text_is_explicit(self):
        raw=xlsx([['ID','Value'],[1,'=1+2']]);a=self.upload('a.xlsx',raw);b=self.upload('b.xlsx',raw)
        opts={'columns':[{'base':1,'compared':1}]}
        data=self.run_pair(a,b,**opts).json();self.assertEqual(data['summary']['unresolved'],1);self.assertEqual(data['summary']['unchanged'],0)
        data=self.run_pair(a,b,**opts,value_mode='formulas').json();self.assertEqual(data['summary']['unchanged'],1)
        c=self.upload('c.csv',b'ID,Value\n1,=1+2\n')
        self.assertEqual(self.run_pair(a,c,**opts,value_mode='formulas').status_code,400)

    def test_header_selection_and_ignore_options(self):
        a=self.upload('a.csv',b'Report\nName,Code\n Motor   speed ,001\n')
        b=self.upload('b.csv',b'Report\nName,Code\nmotor speed,001\n')
        payload={'base':{'id':a['id'],'sheet':'CSV','header_row':2},'compared':{'id':b['id'],'sheet':'CSV','header_row':2},'columns':[{'base':0,'compared':0}],'ignore_case':True,'ignore_whitespace':True}
        response=self.client.post('/api/assist/document-comparisons/run',json=payload);self.assertEqual(response.json()['summary']['unchanged'],1)
        response=self.client.get(f"/api/assist/document-comparisons/uploads/{a['id']}/columns",params={'sheet':'CSV','header_row':2});self.assertEqual(response.json()['columns'][0]['name'],'Name')

    def test_blank_header_column_with_later_data_is_selectable(self):
        rows=[['ID',None,None],*[['',None,None] for _ in range(15)],[1,None,'Late value']]
        a=self.upload('late.xlsx',xlsx(rows));b=self.upload('same.xlsx',xlsx(rows))
        schema=self.client.get(f"/api/assist/document-comparisons/uploads/{a['id']}/columns",params={'sheet':'Data','header_row':1}).json()
        self.assertIn(2,[c['index'] for c in schema['columns']])
        data=self.run_pair(a,b,columns=[{'base':2,'compared':2}]).json();self.assertEqual(data['summary']['unchanged'],1)
        self.assertEqual(self.client.get(f"/api/assist/document-comparisons/uploads/{a['id']}/columns",params={'sheet':'Data','header_row':99}).status_code,400)

    def test_partial_scanned_pdf_does_not_publish_an_unchanged_result(self):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.utils import ImageReader
        from PIL import Image
        out=io.BytesIO();c=Canvas(out);c.drawString(50,700,'Readable page');c.showPage();c.drawImage(ImageReader(Image.new('RGB',(20,20),'white')),50,50,100,100);c.save()
        a=self.upload('partial.pdf',out.getvalue());b=self.upload('same.pdf',out.getvalue())
        data=self.run_pair(a,b).json();self.assertGreater(data['summary']['unresolved'],0);self.assertTrue(any('OCR' in note for note in data['notices']))

    def test_pagination_export_scope_and_csv_formula_escaping(self):
        a=self.upload('a.csv',('ID,Value\n'+''.join(f'{i},same\n' for i in range(205))).encode())
        b=self.upload('b.csv',('ID,Value\n'+''.join(f'{i},=unsafe\n' for i in range(205))).encode())
        data=self.run_pair(a,b,columns=[{'base':1,'compared':1}]).json();key=data['id'];self.assertEqual(data['total'],205);self.assertEqual(len(data['rows']),100)
        more=self.client.get(f'/api/assist/document-comparisons/results/{key}',params={'offset':200,'limit':100}).json();self.assertEqual(len(more['rows']),5)
        export=self.client.get(f'/api/assist/document-comparisons/results/{key}/export.csv');self.assertEqual(export.status_code,200);self.assertIn(a['sha256'],export.text)
        parsed=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))));self.assertTrue(any("'=unsafe" in row for row in parsed))
        self.assertEqual(self.client.get(f'/api/assist/document-comparisons/results/{key}',params={'status':'bad'}).status_code,400)

    def test_pdf_word_text_comparison_order_and_five_line_context(self):
        from reportlab.pdfgen.canvas import Canvas
        from docx import Document
        pdf=io.BytesIO();canvas=Canvas(pdf)
        for n in range(1,31):canvas.drawString(50,800-n*20,f'Line {n}: '+('old motor' if n==15 else 'same'))
        canvas.save()
        doc=Document()
        for n in range(1,31):doc.add_paragraph(f'Line {n}: '+('new motor' if n==15 else 'same'))
        word=io.BytesIO();doc.save(word)
        a=self.upload('base.pdf',pdf.getvalue());b=self.upload('compared.docx',word.getvalue())
        data=self.run_pair(a,b).json();self.assertEqual(data['summary']['modified'],1);self.assertEqual(data['summary']['unchanged'],29)
        self.assertEqual(len(data['rows']),11);change=next(r for r in data['rows'] if r['status']=='modified');self.assertIn('Page 1',change['base_ref']);self.assertIn('Paragraph 15',change['compared_ref'])

    def test_docx_tables_remain_between_their_paragraphs(self):
        from docx import Document
        doc=Document();doc.add_paragraph('Before');doc.add_table(rows=1,cols=1).cell(0,0).text='Middle';doc.add_paragraph('After')
        stream=io.BytesIO();doc.save(stream);a=self.upload('order.docx',stream.getvalue())
        path,_=comparison.source(self.user,a['id']);units,_=comparison.text_units(path)
        self.assertEqual([u['value'] for u in units],['Before','Middle','After'])

    def test_scanned_pdf_and_corrupt_or_unsupported_files_are_actionable(self):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.utils import ImageReader
        from PIL import Image
        out=io.BytesIO();c=Canvas(out);c.drawImage(ImageReader(Image.new('RGB',(20,20),'white')),50,50,100,100);c.save()
        self.assertIn('OCR',self.upload('scan.pdf',out.getvalue(),422)['detail'])
        self.upload('bad.xlsx',b'not an Excel file',422);self.upload('bad.exe',b'no',400);self.upload('empty.csv',b'',400)

    def test_oversized_text_is_rejected_instead_of_silently_truncated(self):
        response=self.upload('too-many-lines.txt',b'line\n'*10001,422)
        self.assertIn('10,000 lines',response['detail'])

    def test_account_isolation_hash_check_and_input_validation(self):
        a=self.upload('../../name.csv',b'ID,Value\n1,a\n');self.assertEqual(a['name'],'name.csv')
        b=self.upload('b.csv',b'ID,Value\n1,b\n');data=self.run_pair(a,b,columns=[{'base':1,'compared':1}]).json()
        self.login(self.other)
        self.assertEqual(self.run_pair(a,b,columns=[{'base':1,'compared':1}]).status_code,404)
        for suffix in ('','/export.csv'):self.assertEqual(self.client.get('/api/assist/document-comparisons/results/'+data['id']+suffix).status_code,404)
        self.login(self.user)
        self.assertEqual(self.run_pair(a,b,columns=[{'base':True,'compared':1}]).status_code,400)
        self.assertEqual(self.run_pair(a,b,columns=[{'base':1,'compared':1},{'base':1,'compared':0}]).status_code,400)
        path,_=comparison.source(self.user,a['id']);path.write_bytes(b'changed')
        self.assertEqual(self.run_pair(a,b,columns=[{'base':1,'compared':1}]).status_code,409)
        self.client.cookies.clear();self.assertEqual(self.client.get('/api/assist/document-comparisons/results/'+data['id']).status_code,401)

    def view_fixture(self,count=205):
        a=self.upload('many.csv',('ID,Value\n'+''.join(f'{i},old\n' for i in range(count))).encode())
        b=self.upload('changed.csv',('ID,Value\n'+''.join(f'{i},new\n' for i in range(count))).encode())
        return self.run_pair(a,b,columns=[{'base':0,'compared':0},{'base':1,'compared':1}],keys=[0],match_by='key').json()['id']

    def test_header_filters_cover_all_pages_and_filtered_export(self):
        key=self.view_fixture();url='/api/assist/document-comparisons/results/'+key
        payload={'status':'all','column_filters':[{'side':'base','column':0,'mode':'include','values':['150','200']}],'sort':{'side':'base','column':0,'direction':'desc'}}
        r=self.client.post(url+'/query',json=payload);self.assertEqual(r.status_code,200,r.text);data=r.json()
        self.assertEqual(data['total'],2);self.assertEqual([r['key'] for r in data['rows']],['200','150']);self.assertEqual(data['summary']['modified'],205)
        payload.update(offset=1,limit=1);self.assertEqual(self.client.post(url+'/query',json=payload).json()['rows'][0]['key'],'150')
        export=self.client.post(url+'/export.csv',json=payload);self.assertEqual(export.status_code,200)
        rows=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))));header=next(i for i,r in enumerate(rows) if r and r[0]=='Status');cells=rows[header+1:]
        self.assertEqual(len(cells),4);self.assertEqual(cells[0][3],'CSV!A202');self.assertEqual(cells[2][3],'CSV!A152')

    def test_header_value_lists_combine_other_columns_and_keep_current_values(self):
        a=self.upload('a.csv',b'ID,Name,Value\n1,Motor,10\n2,Drive,20\n3,Motor,30\n')
        b=self.upload('b.csv',b'ID,Name,Value\n3,Motor,31\n2,Drive,21\n1,Motor,11\n')
        key=self.run_pair(a,b,columns=[{'base':i,'compared':i} for i in range(3)],keys=[0],match_by='key').json()['id'];url='/api/assist/document-comparisons/results/'+key
        rule={'side':'base','column':1,'mode':'include','values':['Motor']}
        values=self.client.post(url+'/values',json={'side':'base','column':1,'status':'all','column_filters':[rule]}).json()
        self.assertEqual({i['label']:i['count'] for i in values['items']},{'Drive':1,'Motor':2})
        other={'side':'compared','column':2,'mode':'include','values':['11']}
        data=self.client.post(url+'/query',json={'status':'all','column_filters':[rule,other]}).json();self.assertEqual([r['key'] for r in data['rows']],['1']);self.assertEqual(data['rows'][0]['cells'][2]['compared']['ref'],'CSV!C4')
        values=self.client.post(url+'/values',json={'side':'base','column':1,'status':'all','column_filters':[rule,other]}).json();self.assertEqual(values['items'],[{'value':'Motor','label':'Motor','count':1}])

    def test_blank_cells_and_absent_rows_are_separate_filter_values(self):
        a=self.upload('a.csv',b'ID,Value\n1,\n2,A\n');b=self.upload('b.csv',b'ID,Value\n3,B\n1,\n')
        key=self.run_pair(a,b,columns=[{'base':0,'compared':0},{'base':1,'compared':1}],keys=[0],match_by='key').json()['id'];url='/api/assist/document-comparisons/results/'+key
        values=self.client.post(url+'/values',json={'side':'base','column':1,'status':'all'}).json();self.assertEqual({v['value'] for v in values['items']},{'',None,'A'})
        for selected,expected in [([None],['3']),([''],['1'])]:
            data=self.client.post(url+'/query',json={'status':'all','column_filters':[{'side':'base','column':1,'mode':'include','values':selected}]}).json();self.assertEqual([r['key'] for r in data['rows']],expected)
        data=self.client.post(url+'/query',json={'status':'all','column_filters':[{'side':'base','column':1,'mode':'exclude','values':[None,'']}]}).json();self.assertEqual([r['key'] for r in data['rows']],['2'])

    def test_numeric_sorting_preserves_file_pairs_and_saved_order(self):
        raw=b'ID,Value\n1,x\n2,x\n10,x\n3,x\n20,x\n';a=self.upload('a.csv',raw);b=self.upload('b.csv',raw)
        key=self.run_pair(a,b,columns=[{'base':0,'compared':0},{'base':1,'compared':1}]).json()['id'];url='/api/assist/document-comparisons/results/'+key
        path,_=comparison.record(self.user,key,'results');before=(path/'record.json').read_bytes()
        for direction,expected in [('asc',['1','2','3','10','20']),('desc',['20','10','3','2','1'])]:
            data=self.client.post(url+'/query',json={'status':'all','sort':{'side':'base','column':0,'direction':direction}}).json()
            self.assertEqual([r['cells'][0]['base']['value'] for r in data['rows']],expected)
            self.assertTrue(all(r['cells'][0]['base']['value']==r['cells'][0]['compared']['value'] for r in data['rows']))
        self.assertEqual((path/'record.json').read_bytes(),before)
        self.assertEqual([r['cells'][0]['base']['value'] for r in self.client.get(url,params={'status':'all'}).json()['rows']],['1','2','10','3','20'])

    def test_header_values_search_paging_and_account_isolation(self):
        key=self.view_fixture();url='/api/assist/document-comparisons/results/'+key
        data=self.client.post(url+'/values',json={'status':'all','side':'base','column':0,'offset':100}).json();self.assertEqual(data['total'],205);self.assertEqual(len(data['items']),100);self.assertEqual(data['items'][0]['value'],'100')
        data=self.client.post(url+'/values',json={'status':'all','side':'base','column':0,'search':'20'}).json();self.assertEqual(data['total'],7)
        self.login(self.other)
        for endpoint in ('query','values','export.csv'):self.assertEqual(self.client.post(url+'/'+endpoint,json={}).status_code,404)

    def test_header_filter_request_validation(self):
        key=self.view_fixture(3);url='/api/assist/document-comparisons/results/'+key
        invalid=[{'status':{}},{'column_filters':[{'side':{},'column':0,'mode':'include','values':[]}]},{'column_filters':[{'side':'base','column':True,'mode':'include','values':[]}]},{'column_filters':[{'side':'base','column':0,'mode':[],'values':[]}]},{'column_filters':[{'side':'base','column':0,'mode':'include','values':[{}]}]},{'sort':{'side':'base','column':0,'direction':[]}}]
        for payload in invalid:self.assertEqual(self.client.post(url+'/query',json=payload).status_code,400,payload)
        self.assertEqual(self.client.post(url+'/values',json={'side':'base','column':0,'limit':201}).status_code,400)
        self.assertEqual(self.client.post(url+'/values',json={'side':'base','column':0,'search':'x'*201}).status_code,400)

    def test_empty_selection_and_clearing_header_filters_restore_all_rows(self):
        key=self.view_fixture(3);url='/api/assist/document-comparisons/results/'+key
        empty={'status':'all','column_filters':[{'side':'base','column':0,'mode':'include','values':[]}]}
        self.assertEqual(self.client.post(url+'/query',json=empty).json()['total'],0)
        restored=self.client.post(url+'/query',json={'status':'all','column_filters':[],'sort':None}).json();original=self.client.get(url,params={'status':'all'}).json()
        self.assertEqual(restored['rows'],original['rows']);self.assertEqual(restored['total'],3)


if __name__=='__main__':unittest.main()
