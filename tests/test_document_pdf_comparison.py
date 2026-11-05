"""Positioned PDF comparisons through the authenticated production HTTP API."""
import io
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas

from backend.core import document_comparison as core
from backend.core.document_pdf_comparison import page_counter
from tests import test_document_comparison as fixture


def pdf(pages, footer=True):
    output = io.BytesIO(); canvas = Canvas(output, pagesize=(612, 792))
    for number, lines in enumerate(pages, 1):
        for line, text in enumerate(lines):
            canvas.drawString(70, 680 - line * 22, text)
        if footer:
            canvas.drawString(290, 24, f'{number} / {len(pages)}')
        canvas.showPage()
    canvas.save(); return output.getvalue()


class PDFDocumentComparisonTests(unittest.TestCase):
    setUpClass = classmethod(fixture.DocumentComparisonTests.setUpClass.__func__)
    setUp, tearDown, login = fixture.DocumentComparisonTests.setUp, fixture.DocumentComparisonTests.tearDown, fixture.DocumentComparisonTests.login
    upload, run_pair = fixture.DocumentComparisonTests.upload, fixture.DocumentComparisonTests.run_pair

    def compare(self, left, right, **options):
        a = self.upload('before.pdf', left); b = self.upload('after.pdf', right)
        response = self.run_pair(a, b, **options)
        self.assertEqual(response.status_code, 200, response.text[:800])
        return response.json()

    def test_page_counters_excluded_but_added_program_numbers_retained(self):
        data = self.compare(pdf([['Network 1', 'Motor 100'], ['Network 3', 'Timer 200']]),
                            pdf([['Network 1', 'Motor 100'], ['Network 2', 'Servo 120'], ['Network 3', 'Timer 200']]))
        self.assertEqual([p['compared'] for p in data['pdf']['pairs'] if p['base'] == 2], [3])
        self.assertIn({'base': None, 'compared': 2}, [{k:p[k] for k in ('base','compared')} for p in data['pdf']['pairs']])
        self.assertEqual(data['summary']['modified'], 0)
        self.assertEqual(data['summary']['added'], 2)
        self.assertEqual(len(data['pdf']['ignored_page_numbers']['base']), 2)
        all_rows = self.client.get(f"/api/assist/document-comparisons/results/{data['id']}?status=all").json()['rows']
        self.assertFalse(any(' / 3' in r['compared'] for r in all_rows))
        self.assertTrue(any(r['compared']=='Servo 120' and r['status']=='added' for r in all_rows))

    def test_ignore_can_be_disabled_and_operands_and_headers_are_compared(self):
        data = self.compare(pdf([['Project 9444', '100']]), pdf([['Project 9445', '101'], ['New page']]), ignore_page_numbers=False)
        self.assertFalse(data['pdf']['ignored_page_numbers']['base'])
        self.assertTrue(any(r['base']=='100' and r['compared']=='101' for r in data['rows']))
        self.assertTrue(any(r['base']=='Project 9444' and r['compared']=='Project 9445' for r in data['rows']))
        self.assertTrue(any(r['base']=='1 / 1' for r in data['rows']))
        self.assertFalse(page_counter('1 / 181',[290,300,340,310],612,792,1,181))
        self.assertFalse(page_counter('VW100 / 181',[290,751,340,760],612,792,1,181))
        self.assertFalse(page_counter('1 / 182',[290,751,340,760],612,792,1,181))
        self.assertFalse(page_counter('1',[290,765,300,775],612,792,1,181))
        self.assertTrue(page_counter('Page 1',[290,751,340,760],612,792,1,181))

    def test_only_changed_words_have_exact_page_highlights(self):
        data = self.compare(pdf([['START Motor 100', 'Same line']]), pdf([['START Motor 200', 'Same line']]))
        row = next(row for row in data['rows'] if row['status']=='modified')
        self.assertEqual(len(row['base_location']['highlights']), 1)
        self.assertGreater(row['base_location']['highlights'][0][0], row['base_location']['bbox'][0])
        self.assertEqual(row['base_location']['page'], 1)
        url = f"/api/assist/document-comparisons/results/{data['id']}"
        detail = self.client.get(url+'/pdf-pairs/1').json()
        self.assertEqual([m['row_id'] for m in detail['base_highlights']], [row['id']])
        self.assertEqual(len(detail['rows']), 1)
        response = self.client.get(url+'/pdf-pages/base/1.png')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'\x89PNG'))
        self.assertIn('no-store', response.headers['cache-control'])

    def test_all_pdf_exports_retain_source_pages_and_before_after_notes(self):
        data = self.compare(pdf([['Motor 100']]), pdf([['Motor 200']]))
        url = f"/api/assist/document-comparisons/results/{data['id']}"
        for side in ('base','compared'):
            response = self.client.get(url+f'/highlighted-{side}.pdf')
            self.assertEqual(response.status_code,200,response.text[:100] if response.status_code!=200 else '')
            document = PdfReader(io.BytesIO(response.content))
            self.assertEqual(len(document.pages),1)
            annotations = document.pages[0]['/Annots']
            self.assertEqual(len(annotations),1)
            self.assertIn('Before: Motor 100', annotations[0].get_object()['/Contents'])
            self.assertIn('After: Motor 200', annotations[0].get_object()['/Contents'])
        response = self.client.get(url+'/report.pdf');self.assertEqual(response.status_code,200)
        report = PdfReader(io.BytesIO(response.content))
        self.assertGreaterEqual(len(report.pages),2)
        text='\n'.join(p.extract_text() for p in report.pages)
        for expected in ('Before','After','Motor 100','Motor 200','SHA256','Pair 1'):
            self.assertIn(expected,text)
        response=self.client.get(url+'/report.html');self.assertEqual(response.status_code,200)
        self.assertIn('Motor 100',response.text);self.assertIn(data['base']['sha256'],response.text)

    def test_crop_and_rotation_preserve_highlight_geometry(self):
        sources=[]
        for text in ('Motor 100','Motor 200'):
            reader=PdfReader(io.BytesIO(pdf([[text]])))
            page=reader.pages[0];page.cropbox.lower_left=(35,35);page.cropbox.upper_right=(575,750);page.rotate(90)
            writer=PdfWriter();writer.add_page(page);out=io.BytesIO();writer.write(out);sources.append(out.getvalue())
        data=self.compare(*sources)
        url=f"/api/assist/document-comparisons/results/{data['id']}"
        for side in ('base','compared'):
            report=PdfReader(io.BytesIO(self.client.get(url+f'/highlighted-{side}.pdf').content))
            page=report.pages[0]
            self.assertEqual(page.rotation,0)
            annotation=page['/Annots'][0].get_object();rect=annotation['/Rect']
            self.assertGreaterEqual(rect[0],page.cropbox.left);self.assertLessEqual(rect[2],page.cropbox.right)
            self.assertGreaterEqual(rect[1],page.cropbox.bottom);self.assertLessEqual(rect[3],page.cropbox.top)
            self.assertEqual(self.client.get(url+f'/pdf-pages/{side}/1.png').status_code,200)

    def test_source_changes_block_visual_review_and_exports(self):
        data=self.compare(pdf([['a']]),pdf([['b']]))
        url=f"/api/assist/document-comparisons/results/{data['id']}"
        for suffix in ('/pdf-pages/base/1.png','/highlighted-compared.pdf','/report.pdf'):
            self.assertEqual(self.client.get(url+suffix).status_code,200)
        path,_=core.source(self.user,data['base']['id']);path.write_bytes(b'changed')
        url=f"/api/assist/document-comparisons/results/{data['id']}"
        for suffix in ('/pdf-pairs/1','/pdf-pages/base/1.png','/highlighted-compared.pdf','/report.pdf','/report.html'):
            self.assertEqual(self.client.get(url+suffix).status_code,409,suffix)

    def test_source_change_during_page_render_prevents_publication(self):
        from backend.core import document_pdf_comparison as positioned
        data=self.compare(pdf([['a']]),pdf([['b']]))
        path,_=core.source(self.user,data['base']['id'])
        render=positioned.render_png
        def changed(file,page):
            result=render(file,page);path.write_bytes(b'changed during render');return result
        with patch.object(positioned,'render_png',side_effect=changed):
            self.assertEqual(self.client.get(f"/api/assist/document-comparisons/results/{data['id']}/pdf-pages/base/1.png").status_code,409)

    def test_pdf_sources_and_exports_are_account_owned_and_inputs_validated(self):
        data=self.compare(pdf([['a']]),pdf([['b']]))
        url=f"/api/assist/document-comparisons/results/{data['id']}"
        for suffix in ('/pdf-pairs/0','/pdf-pages/base/0.png','/pdf-pages/other/1.png','/highlighted-other.pdf'):
            self.assertEqual(self.client.get(url+suffix).status_code,400,suffix)
        self.login(self.other)
        for suffix in ('/pdf-pairs/1','/pdf-pages/base/1.png','/highlighted-base.pdf','/report.pdf','/report.html'):
            self.assertEqual(self.client.get(url+suffix).status_code,404,suffix)
        self.client.cookies.clear();self.assertEqual(self.client.get(url+'/report.pdf').status_code,401)

    def test_scanned_pages_stay_unresolved_in_visual_comparison(self):
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        output=io.BytesIO();canvas=Canvas(output);canvas.drawString(70,680,'Readable');canvas.showPage()
        canvas.drawImage(ImageReader(Image.new('RGB',(20,20),'white')),40,40,200,200);canvas.save()
        data=self.compare(output.getvalue(),output.getvalue())
        self.assertGreater(data['summary']['unresolved'],0)
        self.assertTrue(any('OCR' in n for n in data['notices']))

    def test_html_notes_escape_pdf_text(self):
        data=self.compare(pdf([['<script>alert(1)</script>']]),pdf([['<img src=x onerror=alert(2)>']]))
        result=self.client.get(f"/api/assist/document-comparisons/results/{data['id']}/report.html")
        self.assertNotIn('<script>',result.text);self.assertIn('&lt;script&gt;',result.text)
        self.assertIn("default-src 'none'",result.headers['content-security-policy'])


if __name__=='__main__':unittest.main()
