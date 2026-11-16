from pathlib import Path
import tempfile
from pypdf import PdfReader
from docx import Document
from backend.core.report_cover import ReportCover
from backend.core.compare_exports import export_html,export_pdf,export_docx
import test_compare_context_exports as context_tests

def test_folder_cover_fields_survive_all_human_readable_exports():
    cover=ReportCover(projectName='Comber review',projectId='PRJ-104',department='Automation',
        base='Base release',developed='Developed release',description='Review PLC changes',
        objectiveScope='Compare source, HMI and hardware',reviewedBy='Independent Reviewer',
        approvedBy='Release Approver',date='2026-11-14').model_dump(mode='json')
    result={'baseName':'Base','newName':'Developed','summary':{'modified':1},
            'diffs':[context_tests.SourceContextTests().sample()],'reportCover':cover,
            'reportSelection':{'categories':['logic'],'statuses':['modified'],'includeKnowledge':False}}
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);logo=root/'none.png'
        export_html(result,root/'report.html',logo);export_pdf(result,root/'report.pdf',logo);export_docx(result,root/'report.docx',logo)
        html=(root/'report.html').read_text(encoding='utf-8')
        pdf=PdfReader(root/'report.pdf');first_page=pdf.pages[0].extract_text()
        doc=Document(root/'report.docx');word='\n'.join(cell.text for row in doc.tables[0].rows for cell in row.cells)
        assert doc.paragraphs[0].text=='Project and review details'
        for key in ('projectName','projectId','department','base','developed','description','objectiveScope','reviewedBy','approvedBy'):
            assert cover[key] in html
            assert cover[key] in first_page
            assert cover[key] in word
        assert 'Tag15' not in first_page
