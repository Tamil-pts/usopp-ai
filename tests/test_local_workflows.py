"""Regression checks for orchestration. Engine behavior is exercised separately on real projects."""
import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from openpyxl import Workbook,load_workbook
from backend.app import app
from backend.core import runtime, accounts, access, run_history
from backend.api import validation,metadata,comparison,rules,knowledge,system,history


class LocalWorkflows(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.temp=Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='usopp paths ')))
        self.work=self.temp/'work';self.work.mkdir()
        self.exports=self.temp/'exports';(self.exports/'metadata').mkdir(parents=True)
        for module in [runtime,validation,metadata,comparison,rules,system,access,run_history,history]:
            if hasattr(module,'WORK'):self.stack.enter_context(patch.object(module,'WORK',self.work))
            if hasattr(module,'EXPORTS'):self.stack.enter_context(patch.object(module,'EXPORTS',self.exports))
        self.stack.enter_context(patch.object(run_history,'RECORDS',self.exports/'history'))
        self.stack.enter_context(patch.object(run_history,'SNAPSHOTS',self.work/'history'))
        self.stack.enter_context(patch.object(comparison,'COMPARE_WORK_DIR',self.work/'compare'))
        self.stack.enter_context(patch.object(runtime,'PROJECT_KB',self.temp/'knowledge'))
        self.master=self.temp/'master.json';self.master.write_text(json.dumps({'version':'1.0','mappings':[{'plc_parameter':'Existing','metadata_parameter':'Keep'}]}))
        self.stack.enter_context(patch.object(knowledge,'MASTER_PARAM_FILE',self.master))
        self.project=self.temp/'PLC project & spaces';(self.project/'Logical').mkdir(parents=True)
        (self.project/'Machine.apj').write_text('<Project/>')
        self.book=self.temp/'Reference metadata.xlsx'
        wb=Workbook();ws=wb.active;ws.title='Parameters';ws.append(['TAG_CODE','Parameter','Formula']);ws.append([1,'Speed','=A2+1']);ws.append([None,None,None]);ws.append([2,'Length',None]);ws.freeze_panes='A2'
        sh=wb.create_sheet('Sheet2');sh.append(['PLCVAL','SHOWNVAL']);sh.append([0,'Off']);wb.save(self.book);wb.close()
        self.stack.enter_context(patch.object(accounts,'store',accounts.AccountStore(self.temp/'accounts.sqlite3')))
        # These mocked orchestration checks do not use MCP. Its process-owned
        # session manager has a single lifespan, exercised by the live server
        # checks rather than restarted for every unit-test fixture.
        self.client=TestClient(app)
        self.stack.callback(self.client.close)
        response=self.client.post('/api/auth/login',json={'username':'Admin','password':'usopp.2026'})
        self.assertEqual(response.status_code,200,response.text)
        self.calls=[]
        def engine(args,cwd):
            self.calls.append(args)
            output=Path(args[args.index('--output-json')+1])
            output.write_text(json.dumps({'summary':{'totalGroups':1},'groups':[],'totalParameters':2,'moduleReports':[]}))
            if '--output-excel' in args:
                Path(args[args.index('--output-excel')+1]).write_bytes(self.book.read_bytes())
        self.stack.enter_context(patch.object(validation,'run_engine',engine))
        self.stack.enter_context(patch.object(rules,'run_engine',engine))

    def post(self,url,data):
        response=self.client.post(url,json=data)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_paths_accept_quotes_uri_apj_and_spaces(self):
        for path in [f'"{self.project}"',self.project.as_uri(),str(self.project/'Machine.apj')]:
            result=self.post('/api/local/path/check',{'kind':'folder','path':path})
            self.assertEqual(Path(result['path']),self.project)

    def test_parameter_import_preserves_legacy_all_and_separates_departments(self):
        csv='PLC_PARAMETER,PLC_TAG,METADATA_PARAMETER,MACHINE_DEPARTMENT\nExisting,,Keep,All\nExisting,,Keep,Carding\n'
        for _ in range(2):
            response=self.client.post('/api/knowledge/master/csv',files={'file':('scoped.csv',csv,'text/csv')})
            self.assertEqual(200,response.status_code,response.text)
        rows=response.json()['mappings']
        self.assertEqual(2,len(rows))
        self.assertEqual({'All','Carding'},{row['machine_department'] for row in rows})

    def test_dropdown_import_keeps_machine_value_lists_separate(self):
        folder=self.temp/'dropdown_knowledge';(folder/'master').mkdir(parents=True)
        with patch.object(knowledge,'KNOWLEDGE',folder):
            csv='PLC_PARAMETER,PLC_TAG,METADATA_PARAMETER,MACHINE_DEPARTMENT,PLCVAL,SHOWNVAL\nMode,mode,Mode,All,0,Off\nMode,mode,Mode,Carding,0,Stopped\n'
            for _ in range(2):
                response=self.client.post('/api/knowledge/master/dropdown/csv',files={'file':('scoped.csv',csv,'text/csv')})
                self.assertEqual(200,response.status_code,response.text)
            rows=response.json()['mappings']
            self.assertEqual(2,len(rows))
            self.assertEqual({'All':'Off','Carding':'Stopped'},{r['machine_department']:r['mapping'][0]['SHOWNVAL'] for r in rows})

    def test_validation_and_generation_forward_machine_scope(self):
        for route in ('validate','generate-metadata'):
            result=self.post('/api/local/'+route,{'project_path':str(self.project),'machine_department':'Carding'})
            args=self.calls[-1]
            self.assertEqual('Carding',args[args.index('--machine-department')+1])
            self.assertEqual('Carding',result['machineDepartment'])

    def test_project_details_show_studio_version_and_active_configuration(self):
        (self.project/'Machine.apj').write_text('<?AutomationStudio Version="4.10.3.12 SP"?><Project/>')
        (self.project/'LastUser.set').write_text('<Settings><ConfigurationManager ActiveConfigurationName="Production"/></Settings>')
        result=self.post('/api/local/project/details',{'project_path':str(self.project)})
        self.assertEqual(result['automationStudioVersion'],'4.10')
        self.assertEqual(result['activeConfiguration'],'Production')

    def test_bad_and_ambiguous_paths_return_actionable_errors(self):
        for path in [r'C:\fakepath\PLC',str(self.temp/'missing')]:
            response=self.client.post('/api/local/validate',json={'project_path':path})
            self.assertIn(response.status_code,[400,404])
        (self.temp/'Other'/'Logical').mkdir(parents=True)
        response=self.client.post('/api/local/path/check',json={'kind':'folder','path':str(self.temp)})
        self.assertEqual(response.status_code,400)
        self.assertIn('Multiple PLC projects',response.text)

    def test_local_validation_uses_selected_metadata_and_manifest(self):
        data=self.post('/api/local/validate',{'project_path':str(self.project),'metadata_path':str(self.book)})
        self.assertIn(str(self.book),self.calls[-1])
        self.assertEqual(data['metadataPath'],str(self.book))
        sheets=self.post('/api/metadata/view/sheets',{'sessionId':data['sessionId'],'source':'uploaded'})
        self.assertEqual(sheets['file'],self.book.name)
        self.assertEqual(self.client.get(data['downloadExcelUrl']).status_code,200)

    def test_local_generation_persists_workbook(self):
        data=self.post('/api/local/generate-metadata',{'project_path':str(self.project)})
        self.assertTrue(Path(data['workbookPath']).is_file())
        sheets=self.post('/api/metadata/view/sheets',{'sessionId':data['sessionId'],'source':'generated'})
        self.assertEqual(len(sheets['sheets']),2)
        self.assertEqual(self.client.get(data['downloadExcelUrl']).status_code,200)

    def test_upload_generation_uses_same_persistent_viewer(self):
        response=self.client.post('/api/generate-metadata',files=[('project_files',('Demo/Machine.apj',b'<Project/>'))])
        self.assertEqual(response.status_code,200,response.text)
        data=response.json()
        self.assertTrue(Path(data['workbookPath']).is_file())
        self.post('/api/metadata/view/sheets',{'sessionId':data['sessionId'],'source':'generated'})

    def test_large_browser_project_is_staged_in_reliable_chunks(self):
        total=2933
        started=self.post('/api/project-upload/start',{'project_name':'Demo','total_files':total})
        sid=started['sessionId']
        received=0
        while received<total:
            count=min(200,total-received)
            files=[]
            for index in range(received,received+count):
                name='Demo/Machine.apj' if index==0 else f'Demo/Logical/chunk/file_{index:04d}.st'
                files.append(('project_files',(name,b'x')))
            response=self.client.post('/api/project-upload/chunk',data={'session_id':sid},files=files)
            self.assertEqual(response.status_code,200,response.text)
            received=response.json()['receivedFiles']
        finished=self.post('/api/project-upload/finish',{'session_id':sid})
        self.assertEqual(finished['uploadedFiles'],total)
        self.assertEqual(sum(1 for path in (self.work/sid/'source').rglob('*') if path.is_file()),total)
        self.assertEqual(Path(finished['projectPath']).name,'Demo')

    def test_local_project_with_uploaded_metadata(self):
        response=self.client.post('/api/metadata/upload',files={'metadata':('metadata.xlsx',self.book.read_bytes())})
        self.assertEqual(response.status_code,200,response.text)
        path=response.json()['path']
        self.post('/api/local/validate',{'project_path':str(self.project),'metadata_path':path})
        self.assertIn(path,self.calls[-1])

    def test_uploaded_project_with_local_metadata(self):
        response=self.client.post('/api/validate',data={'metadata_path':str(self.book)},files=[('project_files',('Demo/Machine.apj',b'<Project/>'))])
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn(str(self.book),self.calls[-1])

    def test_edits_across_sheets_preserve_source_formulas_types_and_blanks(self):
        original=self.book.read_bytes()
        data=self.post('/api/metadata/view/sheets',{'path':str(self.book)})
        data['sheets'][0]['rows'][0]['Parameter']='Edited speed'
        data['sheets'][0]['rows'][2]['TAG_CODE']='42'
        data['sheets'][1]['rows'][0]['SHOWNVAL']='Disabled'
        result=self.post('/api/metadata/view/save',{'workbookPath':str(self.book),'sheets':data['sheets']})
        self.assertEqual(self.book.read_bytes(),original)
        wb=load_workbook(io.BytesIO(Path(result['workbookPath']).read_bytes()))
        try:
            self.assertEqual(wb['Parameters']['B2'].value,'Edited speed')
            self.assertEqual(wb['Parameters']['C2'].value,'=A2+1')
            self.assertIsNone(wb['Parameters']['A3'].value)
            self.assertEqual(wb['Parameters']['A4'].value,42)
            self.assertEqual(wb['Sheet2']['B2'].value,'Disabled')
            self.assertEqual(wb['Parameters'].freeze_panes,'A2')
        finally:wb.close()
        self.assertEqual(self.client.get(result['downloadUrl']).status_code,200)

    def test_export_retains_all_sheets(self):
        data=self.post('/api/metadata/view/sheets',{'path':str(self.book)})
        exported=self.post('/api/metadata/view/export',{'workbookPath':str(self.book),'sheets':data['sheets']})
        wb=load_workbook(io.BytesIO(Path(exported['workbookPath']).read_bytes()));self.assertEqual(wb.sheetnames,['Parameters','Sheet2']);wb.close()

    def test_export_highlights_duplicates_only_inside_same_group_code(self):
        duplicate_book=self.temp/'duplicates.xlsx'
        wb=Workbook();ws=wb.active;ws.title='Metadata'
        ws.append(['S NO.','GROUP_CODE','Parameters'])
        ws.append([1,20,'Speed']);ws.append([2,20,' speed ']);ws.append([3,30,'Speed']);ws.append([4,20,'Other'])
        from openpyxl.styles import PatternFill
        ws['A2'].fill=PatternFill(fill_type='solid',fgColor='FFF2CC')
        sheet2=wb.create_sheet('Sheet2');sheet2.append(['GROUP_CODE','Parameters']);sheet2.append([20,'Same']);sheet2.append([20,'Same'])
        wb.save(duplicate_book);wb.close()
        data=self.post('/api/metadata/view/sheets',{'path':str(duplicate_book)})
        exported=self.post('/api/metadata/view/export',{'workbookPath':str(duplicate_book),'sheets':data['sheets']})
        wb=load_workbook(io.BytesIO(Path(exported['workbookPath']).read_bytes()))
        try:
            def duplicate_ranges(sheet):
                return {str(rule_range.sqref) for rule_range,rules in sheet.conditional_formatting._cf_rules.items() for rule in rules if metadata.DUPLICATE_FORMULA in (rule.formula or [])}
            self.assertEqual(duplicate_ranges(wb['Metadata']),{'A2:C2','A3:C3'})
            self.assertEqual(duplicate_ranges(wb['Sheet2']),set())
            self.assertEqual(wb['Metadata']['A2'].fill.fgColor.rgb[-6:],'FFF2CC')
        finally:wb.close()
        # Resolve one duplicate and save the highlighted copy again. The
        # exporter must remove its stale purple marker from the former pair.
        data=self.post('/api/metadata/view/sheets',{'path':exported['workbookPath']})
        data['sheets'][0]['rows'][1]['Parameters']='Unique speed'
        resolved=self.post('/api/metadata/view/save',{'workbookPath':exported['workbookPath'],'sheets':data['sheets']})
        wb=load_workbook(io.BytesIO(Path(resolved['workbookPath']).read_bytes()))
        try:
            owned=[rule for rules in wb['Metadata'].conditional_formatting._cf_rules.values() for rule in rules if metadata.DUPLICATE_FORMULA in (rule.formula or [])]
            self.assertEqual(owned,[])
            self.assertEqual(wb['Metadata']['A2'].fill.fgColor.rgb[-6:],'FFF2CC')
        finally:wb.close()

    def test_rules_and_compare_local_routes_resolve_paths(self):
        self.post('/api/local/rules/validate',{'project_path':str(self.project),'rules':{'rules':[]}})
        with patch.object(comparison,'_compare_worker'):
            data=self.post('/api/local/compare/start',{'base_path':str(self.project),'new_path':str(self.project)})
        self.assertEqual(data['status'],'started')

    def test_local_csv_merges_and_keeps_dictionary_schema(self):
        path=self.temp/'mapping.csv';path.write_text('PLC_PARAMETER,PLC_TAG,METADATA_PARAMETER\nSpeed,SpeedTag,Speed reference\n')
        self.post('/api/local/knowledge/master/csv',{'path':str(path)})
        data=json.loads(self.master.read_text());self.assertIsInstance(data,dict);self.assertEqual(len(data['mappings']),2)

    def test_no_automatic_report_deletion_and_cache_clear_preserves_reports(self):
        path=self.work/'session';path.mkdir();(path/'report.xlsx').write_bytes(b'report')
        self.post('/api/cache/clear',{})
        self.assertTrue((path/'report.xlsx').exists())

    def test_upload_traversal_and_invalid_download_are_rejected(self):
        response=self.client.post('/api/generate-metadata',files=[('project_files',('../escape.apj',b'bad'))])
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/api/download/../package.json').status_code,404)

    def test_browse_returns_parent_and_filters_extensions(self):
        response=self.client.get('/api/local/browse',params={'path':str(self.temp),'files':'true','ext':'.xlsx'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['parent'],str(self.temp.parent))
        self.assertIn(self.book.name,[e['name'] for e in response.json()['entries']])

    def test_long_windows_upload_path_is_staged(self):
        relative='Demo/Logical/'+'/'.join(['nested_'+'x'*65]*3)+'/source.st'
        response=self.client.post('/api/generate-metadata',files=[
            ('project_files',('Demo/Machine.apj',b'<Project/>')),
            ('project_files',(relative,b'PROGRAM _CYCLIC END_PROGRAM')),
        ])
        self.assertEqual(response.status_code,200,response.text)
        target=self.work/response.json()['sessionId']/'source'/relative
        import os
        disk=Path('\\\\?\\'+str(target)) if os.name=='nt' else target
        self.assertEqual(disk.read_bytes(),b'PROGRAM _CYCLIC END_PROGRAM')
        # Remove the long fixture path explicitly before TemporaryDirectory cleanup.
        disk.unlink()
        for _ in range(3):
            disk=disk.parent;disk.rmdir()

if __name__=='__main__':unittest.main()
