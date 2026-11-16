"""PLC block/network evidence, visual-only edits and account-owned HTTP exports."""
import io
import unittest
from unittest.mock import patch

from reportlab.pdfgen.canvas import Canvas
from pypdf import PdfReader
from docx import Document
from tests import test_document_pdf_comparison as fixture
from backend.core import document_comparison as core

API='/api/local/compare/plc-pdf'

def program(pages,revision='9444',wire=False):
    out=io.BytesIO();canvas=Canvas(out,pagesize=(612,792))
    for number,networks in enumerate(pages,1):
        canvas.setFont('Helvetica',10);canvas.drawString(180,760,f'LR6AX_TSV{revision} / MOTOR (SBR20)')
        if number==1:canvas.drawString(50,730,'Block: MOTOR')
        for index,(network,text) in enumerate(networks):
            y=680-index*160
            if network is not None:canvas.drawString(50,y,f'Network {network}')
            canvas.drawString(90,y-35,text)
            canvas.line(70,y-60,500,y-60)
            if wire:canvas.line(240,y-60,240,y-90)
        canvas.drawString(290,24,f'{number} / {len(pages)}');canvas.showPage()
    canvas.save();return out.getvalue()


class PLCPDFTests(unittest.TestCase):
    setUpClass=classmethod(fixture.PDFDocumentComparisonTests.setUpClass.__func__)
    setUp,tearDown,login=fixture.PDFDocumentComparisonTests.setUp,fixture.PDFDocumentComparisonTests.tearDown,fixture.PDFDocumentComparisonTests.login

    def upload(self,name,content):
        response=self.client.post(API+'/uploads',files={'file':(name,content)});self.assertEqual(response.status_code,200,response.text[:500]);return response.json()
    def compare(self,a,b,**options):
        left,right=self.upload('before.pdf',a),self.upload('after.pdf',b)
        response=self.client.post(API+'/run',json={'base':{'id':left['id']},'compared':{'id':right['id']},**options})
        self.assertEqual(response.status_code,200,response.text[:1000])
        data=response.json();return self.client.get(API+f"/results/{data['id']}?status=all&limit=200").json()

    def test_running_block_without_address_keeps_continuation_networks(self):
        # These are explicit project / block headers, as in the supplied STEP7 PDFs.
        out=io.BytesIO();c=Canvas(out,pagesize=(612,792))
        for page in range(2):
            c.drawString(180,760,'PROJECT / MOTOR')
            if page==0:c.drawString(50,730,'Block: MOTOR')
            c.drawString(50,680,f'Network {page+1}')
            c.drawString(90,640,'SM0.0 MOV_W MW30');c.line(70,620,500,620)
            c.showPage()
        c.save()
        data=self.compare(out.getvalue(),out.getvalue())
        self.assertEqual(data['summary']['unresolved'],0)
        self.assertEqual(data['summary']['unchanged'],3)
        self.assertEqual([r['base_network'] for r in data['rows'] if r['unit']=='network'],[1,2])

    def test_network_translation_does_not_become_a_logic_change(self):
        def shifted(dx,dy,operand='MW30',wire=False):
            out=io.BytesIO();c=Canvas(out,pagesize=(612,792));c.setFont('Helvetica',10)
            c.drawString(180,760,'PROJECT / MOTOR (SBR20)');c.drawString(50,730,'Block: MOTOR')
            c.drawString(50,680,'Network 1')
            c.saveState();c.translate(dx,dy)
            c.drawString(90,610,'SM0.0 MOV_W '+operand)
            c.line(70,650,70,480);c.line(70,590,450,590)
            c.rect(250,550,100,70)
            if wire:c.line(180,590,180,530)
            c.restoreState();c.save();return out.getvalue()
        original=shifted(0,0)
        data=self.compare(original,shifted(18,-27))
        row=next(r for r in data['rows'] if r['unit']=='network')
        self.assertEqual(row['status'],'unchanged',row['pixels'])
        self.assertEqual(row['pixels']['changed_pixels'],0)
        self.assertIn('registration',row['pixels'])
        # Registration must retain operand changes and a new connected wire.
        for operand,wire in [('MW31',False),('MW30',True)]:
            data=self.compare(original,shifted(18,-27,operand,wire))
            row=next(r for r in data['rows'] if r['unit']=='network')
            self.assertEqual(row['status'],'modified')
            self.assertGreater(row['pixels']['changed_pixels'],0)

    def test_optional_metadata_and_comments_apply_to_text_and_pixels(self):
        def printed(author,created,modified,comment,operand='M1'):
            out=io.BytesIO();c=Canvas(out,pagesize=(612,792));c.setFont('Helvetica',10)
            c.drawString(180,760,'PROJECT / MOTOR (SBR20)');c.drawString(50,730,'Block: MOTOR')
            for y,label,value in [(710,'Author',author),(690,'Created',created),(670,'Last Modified',modified)]:c.drawString(50,y,label+': '+value)
            c.drawString(50,630,'Network 1');c.setFillColorRGB(0,.5,0);c.drawString(70,610,comment)
            c.setFillColorRGB(0,0,0);c.drawString(90,575,operand);c.line(70,550,500,550);c.save();return out.getvalue()
        a,b=printed('Alice','2000','2024','Old comment'),printed('Bob','2001','2026','New comment')
        skipped={k:False for k in ('compare_author','compare_created','compare_modified','compare_comments')}
        data=self.compare(a,b,**skipped)
        self.assertEqual(data['pdf']['comparison_version'],4)
        self.assertEqual(data['summary']['modified'],0)
        self.assertTrue(all(not row['pixels']['changed_pixels'] for row in data['rows']))
        for field in skipped:
            changed=self.compare(a,b,**{**skipped,field:True})
            self.assertGreater(changed['summary']['modified'],0,field)
        # Excluding comments must retain real logic changes.
        changed=self.compare(a,printed('Bob','2001','2026','New comment','M2'),**skipped)
        self.assertEqual(changed['rows'][-1]['status'],'modified')
        self.assertIn('M2',changed['rows'][-1]['compared'])
        response=self.client.get(API+f"/results/{data['id']}/report.html")
        self.assertIn('Excluded from text and rendered pixel comparison',response.text)

    def test_green_network_title_cannot_remove_network_identity_or_operand_spaces(self):
        def printed(title):
            out=io.BytesIO();c=Canvas(out,pagesize=(612,792));c.setFont('Helvetica',10)
            c.drawString(180,760,'PROJECT / MOTOR (SBR20)');c.drawString(50,730,'Block: MOTOR')
            c.drawString(50,680,'Network 3');c.setFillColorRGB(0,.5,0);c.drawString(110,680,title)
            c.setFillColorRGB(0,0,0);c.drawString(90,640,'VW4008 SUB_I +4');c.line(70,620,500,620);c.save();return out.getvalue()
        data=self.compare(printed('Old title'),printed('New title'),compare_comments=False)
        self.assertEqual(data['summary']['unchanged'],2)
        self.assertEqual(data['rows'][-1]['base_network'],3)
        self.assertIn('VW4008 SUB_I +4',data['rows'][-1]['base'])

    def test_identical_networks_and_changed_project_header_are_not_logic_changes(self):
        data=self.compare(program([[(1,'VW4008 SUB_I +4')]]),program([[(1,'VW4008 SUB_I +4')]],revision='9445'))
        self.assertEqual(data['summary']['modified'],0)
        self.assertEqual(data['summary']['unchanged'],2)
        self.assertTrue(data['pdf']['pixel_compare'])

    def test_visual_only_wire_edit_is_modified_with_equal_text(self):
        data=self.compare(program([[(1,'VW4008 SUB_I +4')]]),program([[(1,'VW4008 SUB_I +4')]],wire=True))
        row=next(row for row in data['rows'] if row['unit']=='network')
        self.assertEqual(row['status'],'modified');self.assertFalse(row['text_changed']);self.assertGreater(row['pixels']['changed_pixels'],0)
        response=self.client.get(API+f"/results/{data['id']}/networks/{row['id']}/compared.png?overlay=true")
        self.assertEqual(response.status_code,200);self.assertTrue(response.content.startswith(b'\x89PNG'))
        self.assertEqual(self.client.get(API+f"/results/{data['id']}/networks/{row['id']}/base.png?overlay=true").status_code,400)
        data=self.compare(program([[(1,'VW4008 SUB_I +4')]]),program([[(1,'VW4008 SUB_I +4')]],wire=True),pixel_compare=False)
        self.assertEqual(data['summary']['modified'],0);self.assertIsNone(data['rows'][-1]['pixels'])

    def test_status_highlights_preserve_unchanged_pixels_and_original_crops(self):
        from PIL import Image,ImageChops
        data=self.compare(program([[(1,'VW4008 SUB_I +4')]]),program([[(1,'VW4008 SUB_I +4')]],wire=True))
        row=next(row for row in data['rows'] if row['unit']=='network')
        url=API+f"/results/{data['id']}/networks/{row['id']}"
        for side in ('base','compared'):
            original=self.client.get(url+f'/{side}.png')
            marked=self.client.get(url+f'/{side}.png?highlight=true')
            self.assertEqual(marked.status_code,200)
            with Image.open(io.BytesIO(original.content)) as a,Image.open(io.BytesIO(marked.content)) as b:
                # Aligned previews may gain white padding, but only observed raster
                # differences and their small halos are tinted yellow.
                padded=Image.new('RGB',b.size,'white');padded.paste(a,(0,0))
                delta=ImageChops.difference(padded,b).convert('L')
                changed=sum(count for value,count in enumerate(delta.histogram()) if value)
                self.assertGreater(changed,0);self.assertLess(changed,b.width*b.height*.15)
                padded.close();delta.close()
            self.assertEqual(self.client.get(url+f'/{side}.png').content,original.content)
        unchanged=next(row for row in data['rows'] if row['status']=='unchanged')
        url=API+f"/results/{data['id']}/networks/{unchanged['id']}/base.png"
        self.assertEqual(self.client.get(url).content,self.client.get(url+'?highlight=true').content)

    def test_added_removed_and_text_only_networks_have_status_colours(self):
        from PIL import Image
        data=self.compare(program([[(1,'OLD M1')],[(7,'REMOVE M7')]]),program([[(1,'NEW M1')],[(20,'ADD M20')]]),pixel_compare=False)
        for status,side in [('modified','compared'),('added','compared'),('removed','base')]:
            row=next(row for row in data['rows'] if row['unit']=='network' and row['status']==status)
            url=API+f"/results/{data['id']}/networks/{row['id']}/{side}.png"
            plain=self.client.get(url);marked=self.client.get(url+'?highlight=true')
            self.assertEqual(marked.status_code,200)
            with Image.open(io.BytesIO(plain.content)) as a,Image.open(io.BytesIO(marked.content)) as b:
                self.assertEqual(a.size,b.size);self.assertNotEqual(a.tobytes(),b.tobytes())
                # White background tint is green, red or yellow according to status.
                color=b.getpixel((b.width-1,b.height-1))
                self.assertGreater(color[1] if status=='added' else color[0],color[0] if status=='added' else color[2])
            self.assertEqual(self.client.get(url+'?overlay=true').status_code,400)

    def test_inserted_network_and_renumbering_preserve_exact_text_anchors(self):
        data=self.compare(program([[(1,'START M1'),(2,'STOP M2')]]),program([[(1,'NEW M3'),(2,'START M1'),(3,'STOP M2')]]),pixel_compare=False)
        rows=[row for row in data['rows'] if row['unit']=='network']
        self.assertEqual([row['status'] for row in rows],['added','unchanged','unchanged'])
        self.assertEqual((rows[-1]['base_network'],rows[-1]['compared_network']),(2,3))

    def test_continued_network_keeps_all_segments_and_annotations(self):
        data=self.compare(program([[(1,'START M1')],[(None,'STOP M2')]]),program([[(1,'START M1')],[(None,'STOP M3')]]),pixel_compare=False)
        row=next(row for row in data['rows'] if row['unit']=='network')
        self.assertEqual([s['page'] for s in row['base_segments']],[1,2]);self.assertIn('STOP M3',row['compared'])
        response=self.client.get(API+f"/results/{data['id']}/highlighted-compared.pdf")
        self.assertEqual(response.status_code,200)
        book=PdfReader(io.BytesIO(response.content));self.assertTrue(all(page.get('/Annots') for page in book.pages))

    def test_duplicate_network_identity_needs_review(self):
        data=self.compare(program([[(1,'M1'),(1,'M2')]]),program([[(1,'M1'),(1,'M2')]]))
        self.assertEqual(data['summary']['unresolved'],2)

    def test_unrelated_network_numbers_are_added_and_removed_not_invented_pairs(self):
        data=self.compare(program([[(1,'M1')]]),program([[(20,'OTHER M2')]]),pixel_compare=False)
        rows=[row for row in data['rows'] if row['unit']=='network']
        self.assertEqual([row['status'] for row in rows],['removed','added'])

    def test_conflicting_block_headings_and_unassigned_content_need_review(self):
        output=io.BytesIO();canvas=Canvas(output,pagesize=(612,792))
        canvas.drawString(100,760,'PROJECT / MOTOR (SBR20)');canvas.drawString(50,730,'Block: DIFFERENT')
        canvas.drawString(50,680,'Network 1');canvas.drawString(90,650,'M1')
        canvas.save()
        data=self.compare(output.getvalue(),output.getvalue())
        self.assertEqual(data['summary']['unchanged'],0)
        self.assertEqual(data['summary']['unresolved'],2)
        self.assertTrue(any('disagree' in note for note in data['notices']))

    def test_unrecognised_pdf_is_rejected_without_invented_blocks(self):
        from tests.test_document_pdf_comparison import pdf
        a=self.upload('a.pdf',pdf([['Motor 100']]))
        response=self.client.post(API+'/run',json={'base':{'id':a['id']},'compared':{'id':a['id']}})
        self.assertEqual(response.status_code,422);self.assertIn('No explicit PLC',response.json()['detail'])

    def test_exports_have_before_after_network_crops_and_snapshots(self):
        data=self.compare(program([[(1,'VW4008 SUB_I +4')]]),program([[(1,'VW4008 SUB_I +8')]]))
        url=API+f"/results/{data['id']}"
        for extension in ('html','pdf','docx'):
            response=self.client.get(url+'/report.'+extension);self.assertEqual(response.status_code,200,response.text[:400] if response.status_code!=200 else '')
            if extension=='html':
                text=response.text;self.assertIn('data:image/png;base64,',text)
            elif extension=='pdf':text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
            else:
                document=Document(io.BytesIO(response.content));text='\n'.join(p.text for p in document.paragraphs)+'\n'+'\n'.join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
                self.assertTrue(document.inline_shapes)
            for word in ('Before','After','MOTOR','VW4008'):self.assertIn(word,text)
            if extension!='pdf':self.assertIn('SHA256',text)
        self.assertEqual(self.client.get(url+'/export.csv').status_code,200)

    def test_export_status_selection_filters_every_format_and_highlighted_source(self):
        data=self.compare(program([[(1,'M1'),(2,'UNCHANGED'),(3,'REMOVED')]]),
                          program([[(1,'M2'),(2,'UNCHANGED'),(4,'ADDED')]]),pixel_compare=False)
        url=API+f"/results/{data['id']}"
        for status,expected,excluded in [('all',('Network 1','Network 2','Network 3','Network 4'),()),
                ('differences',('Network 1','Network 3','Network 4'),('Network 2',)),
                ('modified',('Network 1',),('Network 2','Network 3','Network 4')),
                ('added',('Network 4',),('Network 1','Network 2','Network 3')),
                ('removed',('Network 3',),('Network 1','Network 2','Network 4'))]:
            response=self.client.get(url+f'/report.html?status={status}')
            self.assertEqual(response.status_code,200)
            for value in expected:self.assertIn(value,response.text)
            for value in excluded:self.assertNotIn(value,response.text)
            csv_response=self.client.get(url+f'/export.csv?status={status}')
            self.assertEqual(csv_response.status_code,200)
            self.assertIn(f'Filter,{status}',csv_response.text)
        for extension in ('pdf','docx'):
            response=self.client.get(url+f'/report.{extension}?status=modified')
            self.assertEqual(response.status_code,200,response.text[:300] if extension=='docx' else '')
            if extension=='pdf':
                report_text='\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(response.content)).pages)
            else:
                document=Document(io.BytesIO(response.content))
                report_text='\n'.join(p.text for p in document.paragraphs)+'\n'+'\n'.join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
            self.assertIn('Network 1',report_text)
            self.assertNotIn('Network 4',report_text)
            if extension=='pdf':
                self.assertIn('Before',report_text)
                self.assertIn('After',report_text)
                self.assertIn('Added content',report_text)
                self.assertIn('Removed content',report_text)
                self.assertIn('M1',report_text)
        detail_response=self.client.get(url+'/report.pdf',params={'status':'modified','project_name':'Comber Line','project_id':'PRJ-104','department':'Automation','base':'TSV9444.pdf','description':'PLC logic revision review','approved_by':'A. Reviewer','objective_scope':'Compare block and network logic','developed':'TSV9445.pdf','reviewed_by':'B. Engineer'})
        self.assertEqual(detail_response.status_code,200)
        detail_pages=PdfReader(io.BytesIO(detail_response.content)).pages
        cover_text=detail_pages[0].extract_text() or ''
        details_text='\n'.join(page.extract_text() or '' for page in detail_pages)
        self.assertIn('Project and approval details',cover_text)
        self.assertNotIn('Networks are matched',cover_text)
        self.assertNotIn('Base SHA256',cover_text)
        for value in ('Project and approval details','Comber Line','PRJ-104','Automation','TSV9444.pdf','PLC logic revision review','A. Reviewer','Compare block and network logic','TSV9445.pdf','B. Engineer'):
            self.assertIn(value,details_text)
        base=self.client.get(url+'/highlighted-base.pdf?status=added')
        compared=self.client.get(url+'/highlighted-compared.pdf?status=added')
        self.assertEqual(base.status_code,200);self.assertEqual(compared.status_code,200)
        self.assertEqual(len(PdfReader(io.BytesIO(base.content)).pages[0].get('/Annots',[])),0)
        self.assertEqual(len(PdfReader(io.BytesIO(compared.content)).pages[0].get('/Annots',[])),1)
        invalid=self.client.get(url+'/report.html?status=unknown')
        self.assertEqual(invalid.status_code,400)

    def test_owner_isolation_stale_sources_and_invalid_options(self):
        data=self.compare(program([[(1,'M1')]]),program([[(1,'M2')]]))
        url=API+f"/results/{data['id']}"
        paths=['','/networks/2/base.png','/networks/2/base.png?highlight=true','/report.pdf','/report.html','/report.docx','/highlighted-base.pdf','/export.csv']
        self.assertEqual(self.client.get(url+'/networks/2/base.png?highlight=true').status_code,200)
        self.login(self.other)
        for suffix in paths:self.assertEqual(self.client.get(url+suffix).status_code,404,suffix)
        self.login(self.user)
        path,_=core.source(self.user,data['base']['id']);path.write_bytes(b'changed')
        for suffix in paths:self.assertEqual(self.client.get(url+suffix).status_code,409,suffix)
        a=self.upload('a.pdf',program([[(1,'M1')]]))
        response=self.client.post(API+'/run',json={'base':{'id':a['id']},'compared':{'id':a['id']},'pixel_compare':'false'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.post(API+'/uploads',files={'file':('a.txt',b'Network 1')}).status_code,400)

    def test_word_and_html_keep_the_entered_report_details(self):
        result=self.compare(program([[(1,'M1')]]),program([[(1,'M2')]]))
        params={'project_name':'Comber review','project_id':'PRJ-104','department':'Automation',
                'base':'Reference version','developed':'Changed version','reviewed_by':'Review Engineer',
                'approved_by':'Approver','objective_scope':'Check PLC network changes',
                'description':'A detailed engineering review. '*25,'status':'modified'}
        for kind in ('html','docx'):
            response=self.client.get(API+f"/results/{result['id']}/report.{kind}",params=params)
            self.assertEqual(response.status_code,200,response.text[:100])
            if kind=='html':text=response.text
            else:
                document=Document(io.BytesIO(response.content))
                text='\n'.join(c.text for row in document.tables[0].rows for c in row.cells)
            for key,value in params.items():
                if key!='status':self.assertIn(value.strip(),text)


if __name__=='__main__':unittest.main()
