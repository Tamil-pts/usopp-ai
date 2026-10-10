import json
from io import BytesIO
import unittest
from openpyxl import Workbook
from backend.core.data_models import parse_model,validate_model,plc_type,groups

class DataModelTests(unittest.TestCase):
    def model(self,rows):
        book=Workbook();sheet=book.active;sheet.title='shift'
        sheet.append([' Name(Only Reference)','Data Type','Group Code','Mongo_Formula_Name'])
        for row in rows:sheet.append(row)
        doff=book.create_sheet('doff');doff.append(['Actual Tag Name','Data Type','Group Code']);doff.append(['No of Doffs','FLOAT',40])
        stream=BytesIO();book.save(stream)
        return parse_model(stream.getvalue(),'PMS_Carding.xlsx','PMS')
    def metadata(self,name='Delivery Speed',group=40,dtype='REAL'):
        return [{'parameter':name,'groupCode':group,'dataType':dtype,'tagCode':10}]
    def test_workbook_sheets_source_and_aliases(self):
        model=self.model([['Delivery Speed','FLOAT',40],['Lot Name','NCHAR(40)',20]])
        self.assertEqual(model['machine'],'Carding')
        self.assertEqual([row['plcType'] for row in model['parameters']],['REAL','STRING','REAL'])
        self.assertEqual(model['parameters'][0]['row'],2)
        self.assertEqual(model['parameters'][2]['sheet'],'doff')
    def test_exact_name_and_group(self):
        model=self.model([['Delivery Speed','FLOAT',40]])
        self.assertEqual(validate_model(model,self.metadata())['rows'][0]['status'],'PASS')
        result=validate_model(model,self.metadata('delivery speed'))['rows'][0]
        self.assertEqual(result['status'],'PASS');self.assertIn('ignoring case',result['detail'])
        result=validate_model(model,self.metadata(group=20))['rows'][0]
        self.assertIn('missing from GC 40',result['detail'])
    def test_type_duplicate_and_missing(self):
        model=self.model([['Delivery Speed','FLOAT',40]])
        self.assertEqual(validate_model(model,self.metadata(dtype='INT'))['rows'][0]['status'],'FAIL')
        self.assertIn('Duplicate',validate_model(model,self.metadata()*2)['rows'][0]['detail'])
        self.assertEqual(validate_model(model,[])['rows'][0]['status'],'FAIL')
    def test_server_skips_and_formulas_and_incomplete(self):
        names=['Shed Id','Unit Id','Asset Id','Business Id','Tenant Id','Adjusted Time Stamp','Time Stamp Actual']
        model=self.model([[name,None,None] for name in names]+[['Air CFM','FLOAT',None,'air_volume / 60'],['GPSS',None,None]])
        result=validate_model(model,[])
        self.assertTrue(all(row['status']=='SKIPPED' for row in result['rows'][:7]))
        self.assertEqual(result['rows'][7]['status'],'DERIVED')
        self.assertEqual(result['rows'][8]['status'],'UNRESOLVED')
        self.assertEqual(result['rows'][7]['formula'],'air_volume / 60')
    def test_json_and_round_trip(self):
        raw={'controleCode':'CARDING','keysList':{'pms_CARDING_shift':[{'tagName':'Delivery Speed','dataType':'FLOAT','groupCode':'40','formula':None,'isRequired':True}]}}
        model=parse_model(json.dumps(raw).encode(),'CARDING.json','PMS')
        self.assertEqual(validate_model(model,self.metadata())['status'],'PASS')
        saved=parse_model(json.dumps(model).encode(),'saved.json')
        self.assertEqual(saved['parameters'][0]['groupCodes'],[40])
        self.assertEqual(saved['machine'],'CARDING')
    def test_optional_and_multiple_groups(self):
        raw={'controleCode':'CARDING','keysList':{'shift':[{'tagName':'Speed','dataType':'FLOAT','groupCode':'40,50','isRequired':False}]}}
        model=parse_model(json.dumps(raw).encode(),'CARDING.json','PMS')
        self.assertEqual(validate_model(model,[])['rows'][0]['status'],'OPTIONAL')
        self.assertEqual(groups('40, 50'),[40,50]);self.assertEqual(groups('formula'),[])
        self.assertEqual(plc_type('USINT'),'BYTE')

    def test_identical_reference_files_keep_separate_source_identities(self):
        raw=json.dumps({'controleCode':'DRAWFRAMEFINISHER','keysList':{'shift':[{'tagName':'Speed','dataType':'FLOAT','groupCode':'40'}]}}).encode()
        breaker=parse_model(raw,'DRAWFRAMEBREAKER.json','QMS')
        finisher=parse_model(raw,'DRAWFRAMEFINISHER.json','QMS')
        self.assertNotEqual(breaker['id'],finisher['id'])
        self.assertEqual(breaker['sourceSha256'],finisher['sourceSha256'])
        self.assertEqual(breaker['id'],parse_model(raw,'DRAWFRAMEBREAKER.json','QMS')['id'])

if __name__=='__main__':unittest.main()
