import json
from io import BytesIO
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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

    def test_database_only_type_needs_wire_definition_not_a_plc_failure(self):
        raw={'controleCode':'DRAWFRAMEFINISHER','keysList':{'cms_DRAWFRAMEFINISHER_hours':[
            {'tagName':'Production in kg','dataType':'TIMESTAMP','groupCode':'40'}]}}
        model=parse_model(json.dumps(raw).encode(),'DRAWFRAMEFINISHER.json','CMS')
        row=validate_model(model,self.metadata('Production in kg'))['rows'][0]
        self.assertEqual(row['status'],'UNRESOLVED')
        self.assertEqual(row['reasonCodes'],['REFERENCE_TYPE_UNSUPPORTED'])
        raw['keysList']['cms_DRAWFRAMEFINISHER_hours'][0]['plcDataType']='REAL'
        explicit=parse_model(json.dumps(raw).encode(),'DRAWFRAMEFINISHER.json','CMS')
        self.assertEqual(explicit['parameters'][0]['dataType'],'TIMESTAMP')
        self.assertEqual(validate_model(explicit,self.metadata('Production in kg'))['rows'][0]['status'],'PASS')

    def test_builder_preserves_conflicting_originals_and_cross_references_types(self):
        from scripts.build_data_model_knowledge import build
        with TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';cms=source/'CMS';cms.mkdir(parents=True)
            original={'controleCode':'DRAWFRAMEFINISHER','keysList':{'cms_DRAWFRAMEFINISHER_hours':[
                {'tagName':'Production in kg','dataType':'TIMESTAMP','groupCode':'40'},
                {'tagName':'Valid value','dataType':'FLOAT','groupCode':'40'}]}}
            raw=json.dumps(original).encode();(cms/'DRAWFRAMEFINISHER.json').write_bytes(raw)
            book=Workbook();sheet=book.active;sheet.title='cms_DFFinisher_hourwise'
            sheet.append(['Name(Only Reference)','Data Type','Group Code'])
            sheet.append(['Production in kg','FLOAT',40]);sheet.append(['Valid value','FLOAT',40])
            book.save(cms/'CMS_DrawFrameFinisher_Key_Definitions.xlsx')
            models,issues=build(source,root/'output')
            self.assertFalse(issues);self.assertEqual(len(models),1)
            model=models[0];requirement=model['parameters'][0]
            self.assertEqual((cms/'DRAWFRAMEFINISHER.json').read_bytes(),raw)
            self.assertEqual(model['databaseModel'],original)
            self.assertEqual(requirement['dataType'],'TIMESTAMP')
            self.assertEqual(requirement['suggestedPlcType'],'REAL')
            self.assertEqual(requirement['excelReferences'][0]['dataType'],'FLOAT')
            self.assertEqual(requirement['excelReferences'][0]['row'],2)
            metadata=self.metadata('Production in kg')+self.metadata('Valid value',dtype='INT')
            result=validate_model(model,metadata)
            self.assertEqual(result['rows'][0]['status'],'UNRESOLVED')
            self.assertIn('REFERENCE_CONFLICT',result['rows'][0]['reasonCodes'])
            self.assertEqual(result['rows'][1]['status'],'FAIL')
            self.assertIn('TYPE_DIFFERS',result['rows'][1]['reasonCodes'])

    def test_real_finisher_screenshot_reference_conflict(self):
        catalog=Path(__file__).resolve().parents[1]/'knowledge/data_models/catalog.json'
        models=json.loads(catalog.read_text(encoding='utf-8'))['models']
        model=next(value for value in models if value['machine']=='DRAWFRAMEFINISHER' and value['service']=='CMS')
        rows=validate_model(model,self.metadata('Production in kg'))['rows']
        current=next(row for row in rows if row['name']=='Production in kg' and row['groupCodes']==[40])
        self.assertEqual(current['status'],'UNRESOLVED')
        self.assertEqual(current['dataType'],'TIMESTAMP')
        self.assertEqual({row['dataType'] for row in current['excelReferences']},{'FLOAT'})
        self.assertEqual({row['row'] for row in current['excelReferences']},{54,98,121})
        previous=next(row for row in rows if row['name']=='Production in kg' and row['groupCodes']==[50])
        self.assertEqual(previous['reasonCodes'],['GROUP_DIFFERS'])

if __name__=='__main__':unittest.main()
