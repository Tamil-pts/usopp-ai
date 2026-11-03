from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import zipfile
from python_engine.source_compare import source_diff,source_windows
from backend.core.compare_exports import _blocks_for_diff,_html_block,export_html,export_pdf,export_docx


class SourceContextTests(unittest.TestCase):
    def sample(self):
        left=[f'Tag{i:02} := {i};' for i in range(1,71)]
        right=[('Tag15 := 150;' if i==15 else line) for i,line in enumerate(left,1) if i!=50]
        right.insert(34,'AddedTag := TRUE;')
        diff=source_diff('\n'.join(left),'\n'.join(right))
        return {'path':'Logical/Task/main.st','category':'logic','status':'modified',**diff}

    def test_replacement_insertion_and_deletion_remain_distinct_with_five_context_lines(self):
        diff=self.sample();windows=source_windows(diff['source_rows'])
        self.assertEqual(3,len(windows))
        for start,end in windows:
            rows=diff['source_rows'][start:end]
            self.assertEqual(11,len(rows))
            self.assertTrue(all(r['status']=='unchanged' for r in rows[:5]+rows[-5:]))
        self.assertEqual({'modified','added','removed'},{r['status'] for r in diff['source_rows'] if r['status']!='unchanged'})

    def test_report_keeps_surrounding_source_and_empty_alignment_cells(self):
        diff=self.sample();before=deepcopy(diff);blocks=_blocks_for_diff(diff)
        self.assertEqual(3,len(blocks));self.assertEqual(33,sum(len(b['rows']) for b in blocks))
        self.assertEqual(diff,before)
        added=next(row for block in blocks for row in block['rows'] if row['state']=='added')
        self.assertEqual('',added['base_ref']);self.assertEqual('',added['base'])
        html=''.join(_html_block(block,'Base','Developed') for block in blocks)
        self.assertNotIn('Not configured',html);self.assertNotIn('Source line',html)
        self.assertIn('Tag10 := 10;',html);self.assertIn('Tag20 := 20;',html)

    def test_context_bounds_and_nearby_changes_merge(self):
        diff=source_diff('A\nB\nC\nD','AA\nB\nCC\nD')
        self.assertEqual([[0,4]],source_windows(diff['source_rows']))
        self.assertEqual([],source_windows(source_diff('Same','Same')['source_rows']))

    def test_clean_exports_preserve_source_evidence_in_html_pdf_and_word(self):
        result={'baseName':'Base','newName':'Developed','summary':{'modified':1},'diffs':[self.sample()],
                'reportSelection':{'categories':['logic'],'statuses':['modified'],'includeKnowledge':False}}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);logo=root/'none.png'
            export_html(result,root/'report.html',logo)
            html=(root/'report.html').read_text(encoding='utf8')
            self.assertIn('border-top:0;min-height:25px',html)
            self.assertNotIn('border-top:1px solid rgba(148,163,184,.25)',html)
            export_pdf(result,root/'report.pdf',logo)
            from pypdf import PdfReader
            text='\n'.join(page.extract_text() for page in PdfReader(root/'report.pdf').pages)
            self.assertIn('Tag10',text);self.assertIn('AddedTag',text)
            export_docx(result,root/'report.docx',logo)
            with zipfile.ZipFile(root/'report.docx') as doc:
                xml=doc.read('word/document.xml').decode()
                self.assertNotIn('w:val="TableGrid"',xml);self.assertIn('AddedTag',xml)
