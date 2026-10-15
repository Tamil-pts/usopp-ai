import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from backend.api.comparison import _function_flow_detail, export_compare_function_flow


class FunctionFlowApiTests(unittest.TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.work=Path(self.folder.name)
        self.path='Logical/ip_add/ip_addCyclic.ab'
        self.entry={'path':self.path,'category':'logic','base_file_name':'ip_add.src','new_file_name':'ip_addCyclic.ab',
                    'base_relative_path':'pgm/Trial/CPU/ip_add.src','new_relative_path':self.path,
                    'base_source':'IF getip = 1 THEN\ngetip = 0\nENDIF',
                    'new_source':'IF getip = 1 THEN\ngetip = 0\nENDIF'}
        self.result={'diffs':[self.entry]}

    def test_cross_version_pair_retains_side_specific_paths_and_line_basis(self):
        flows=_function_flow_detail(self.result,self.work,self.path)
        self.assertEqual(flows['base']['sourceFile'],'pgm/Trial/CPU/ip_add.src')
        self.assertEqual(flows['base']['lineBasis'],'Saved decoded source view')
        self.assertEqual(flows['developed']['sourceFile'],self.path)
        self.assertEqual(flows['developed']['sections'][0]['nodes'][0]['line'],1)

    def test_flow_reads_saved_detail_without_opening_a_live_project(self):
        self.entry.pop('new_source')
        self.entry.pop('base_source')
        self.entry['project_detail_id']='b'*64
        (self.work/'hmi_details').mkdir()
        (self.work/'hmi_details'/('b'*64+'.json')).write_text(json.dumps({'new_source':'PROGRAM _INIT\nout = 1\nEND_PROGRAM','base_source':''}),encoding='utf-8')
        flows=_function_flow_detail(self.result,self.work,self.path)
        self.assertEqual(flows['developed']['sections'][0]['name'],'_INIT')
        self.assertEqual(flows['developed']['variables'][0]['name'],'out')

    def test_absent_side_is_not_presented_as_an_empty_program(self):
        self.entry['base_file_name']=None
        flows=_function_flow_detail(self.result,self.work,self.path)
        self.assertIsNone(flows['base'])

    def test_unknown_paths_and_old_binary_saved_source_are_rejected(self):
        with self.assertRaises(HTTPException) as error:
            _function_flow_detail(self.result,self.work,'../../secret.st')
        self.assertEqual(error.exception.status_code,404)
        self.entry['base_source']='B&R\x00binary'
        with self.assertRaises(HTTPException) as error:
            _function_flow_detail(self.result,self.work,self.path)
        self.assertEqual(error.exception.status_code,409)

    def test_html_export_uses_the_selected_side_and_returns_an_attachment(self):
        with patch('backend.api.comparison._comparison_result_for_export',return_value=(self.result,self.work)):
            response=export_compare_function_flow('owned-session',self.path,'base')
        self.assertIn('ip_add_base_Function_Flow.html',response.headers['content-disposition'])
        self.assertIn('pgm/Trial/CPU/ip_add.src',response.body.decode())
        with self.assertRaises(HTTPException):export_compare_function_flow('owned-session',self.path,'unknown')


if __name__=='__main__':unittest.main()
