from pathlib import Path
import tempfile
import unittest
from backend.core.compare_report_selection import select_report
from backend.core.compare_exports import export_html,export_pdf,export_data,_changed_diffs
from python_engine.compare import walk_project

def sample():
    rows=[]
    for category,status,path in [('logic','modified','Logical/task/test.st'),('screen','added','Logical/HMI/Pages/test.page'),('config','removed','Logical/conf.dat'),('config','added','Logical/Package.pkg'),('logic','modified','Logical/task/IEC.PRG')]:
        rows.append({'path':path,'category':category,'status':status,'base_relative_path':path,'new_relative_path':path,
                     'removed_lines':[[1,'OLD := TRUE;']],'added_lines':[[1,'NEW := TRUE;']]})
    return {'baseName':'Base','newName':'Developed','summary':{'modified':9},'diffs':rows,'same_logic_files':[{'path':'Logical/task/same.st','category':'logic','status':'unchanged','source_rows':[{'base_line':1,'new_line':1,'base':'SAME := TRUE;','new':'SAME := TRUE;','status':'unchanged'}]}]}

class ReportSelectionTests(unittest.TestCase):
    def test_filters_and_preserves_original(self):
        original=sample();report=select_report(original,{'categories':['logic'],'statuses':['modified'],'includeKnowledge':False})
        self.assertEqual(len(report['diffs']),1)
        self.assertEqual(report['summary']['modified'],1)
        self.assertEqual(report['comparisonSummary']['modified'],9)
        self.assertEqual(len(original['diffs']),5)
        self.assertEqual(len(_changed_diffs(report)),1)
        self.assertFalse(export_data(report)['projectTrees'])
    def test_all_and_package_exclusion(self):
        report=select_report(sample(),{'statuses':['modified','added','removed','unchanged']})
        self.assertEqual(len(report['diffs']),4)
        self.assertEqual(report['summary']['unchanged'],1)
        self.assertFalse(any(item['path'].casefold().endswith(('.pkg','.prg')) for item in report['diffs']))
        self.assertEqual(len(_changed_diffs(report)),4)
    def test_project_category_is_exported(self):
        report=select_report(sample(),{'categories':['config'],'statuses':['removed'],'includeKnowledge':False})
        changes=next(section for section in export_data(report)['sections'] if section['category']=='config')['changes']
        self.assertEqual(len(changes),1)
    def test_html_pdf_contents_and_bookmarks(self):
        report=select_report(sample(),{'categories':['logic'],'statuses':['modified'],'includeKnowledge':False})
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);html=folder/'report.html';pdf=folder/'report.pdf'
            export_html(report,html,folder/'missing-logo.png');text=html.read_text(encoding='utf-8')
            self.assertIn('Table of contents',text);self.assertIn('href="#change-1"',text);self.assertIn('id="change-1"',text)
            self.assertNotIn('<h2>Project Knowledge Base',text)
            export_pdf(report,pdf,folder/'missing-logo.png')
            from pypdf import PdfReader
            reader=PdfReader(pdf);self.assertTrue(reader.outline)
            self.assertIn('Table of contents',''.join(page.extract_text() for page in reader.pages))
            links=[annotation.get_object() for page in reader.pages for annotation in page.get('/Annots',[])]
            self.assertTrue(any(link.get('/Subtype')=='/Link' for link in links))
            for outline in reader.outline:
                if not isinstance(outline,list):self.assertIsNotNone(reader.get_destination_page_number(outline))
    def test_walk_skips_pkg_but_keeps_logic(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'Logical').mkdir();(root/'Logical/Package.pkg').write_text('<Package/>');(root/'Logical/IEC.PRG').write_text('<Program/>');(root/'Logical/main.st').write_text('PROGRAM _CYCLIC END_PROGRAM')
            self.assertEqual(set(walk_project(root,{})),{'Logical/main.st'})

if __name__=='__main__':unittest.main()
