"""Isolated page-editor, revision, protection and export contracts."""
import copy,io,json,tempfile,unittest,zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from pypdf import PdfReader
from docx import Document
from backend.core import accounts,workhub_document_spaces
from backend.core.workhub import store as hub
from backend.core.workhub_quality import authoring,documents,service as qc
from backend.core.workhub_studio import service,store,schema,bindings,compare,reviews,connections,library,quality,exporting,builder,html_renderer,docx_renderer,render_common

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.stack=ExitStack();root=Path(self.temp.name)
        self.stack.enter_context(patch.object(accounts,'store',accounts.AccountStore(root/'accounts.sqlite3')))
        self.stack.enter_context(patch.object(hub,'root',root/'workhub'));self.stack.enter_context(patch.object(hub,'ready',False))
        self.admin=next(u for u in accounts.store.list_users() if u['username']=='Admin')
        self.reviewer=accounts.store.register('studio_reviewer','Fixture.Preview.2026','Reviewer','Fixture')
        self.other=accounts.store.register('studio_other','Fixture.Preview.2026','Other','Fixture')
        self.project=hub.create(self.admin,{'title':'Isolated Studio delivery','owner_id':self.admin['id'],'quality_id':self.reviewer['id'],'release_id':self.reviewer['id']})
        made=authoring.create(self.admin,self.project['id'],{'stage':'frd'})
        with hub.db() as db:self.did=db.execute('SELECT document_id FROM qc_documents WHERE id=?',(made['control_id'],)).fetchone()[0]
        self.control=made['control_id'];self.pid=self.project['id'];self.data=service.get(self.admin,self.pid,self.did)
    def tearDown(self):self.stack.close();self.temp.cleanup()
    def save(self,change=None,layout=None):
        d=self.data;c=copy.deepcopy(d['revision']['content'])
        if change:c.update(change)
        self.data=service.save(self.admin,self.pid,self.did,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'etag':d['revision']['etag'],'content':c,'layout':layout or d['layout']});return self.data
    def populated(self):return self.save({'purpose':'Verify the requested machine behavior.','requirements':[{'id':'FR-001','title':'Motor trip alarm','description':'Indicate the existing trip feedback.','expected_behavior':'Alarm is shown.','acceptance_criteria':'Verify the displayed alarm.','source_ids':[],'mandatory':True,'change':'new'}]})
    def approve(self):
        rev=self.data['revision'];qc.action(self.admin,self.pid,self.control,{'revision_id':rev['id'],'version':rev['version'],'action':'confirm'})
        d=service.get(self.admin,self.pid,self.did);qc.action(self.admin,self.pid,self.control,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'action':'submit'})
        d=service.get(self.reviewer,self.pid,self.did);qc.action(self.reviewer,self.pid,self.control,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'action':'approve','comment':'Reviewed the original requirement and document layout.'})
        self.data=service.get(self.admin,self.pid,self.did);return self.data
    def test_page_content_persists_through_original_save_route(self):
        self.populated();layout=copy.deepcopy(self.data['layout']);layout['page']['accent']='#145b77';layout['blocks'].insert(2,{'id':'custom-note','type':'panel','style':{},'data':{'title':'Design note','runs':[{'text':'Retain the reset guard.','bold':True}]}})
        self.save(layout=layout);d=self.data
        result=documents.save(self.admin,self.pid,self.control,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'content':{**d['revision']['content'],'purpose':'Edited through existing native API.'}})
        current=service.get(self.admin,self.pid,self.did);self.assertEqual('#145b77',current['layout']['page']['accent']);self.assertTrue(any(b['id']=='custom-note' for b in current['layout']['blocks']))
        self.assertEqual('Edited through existing native API.',bindings.text_value(current['revision']['content'],'purpose'))

    def test_guided_builder_retains_existing_and_retired_requirement_identities(self):
        self.populated();original=copy.deepcopy(self.data['revision']['content']['requirements'][0])
        self.save({'requirements':[original,{**original,'id':'FR-010','title':'Retired item'}]});self.save({'requirements':[original]})
        d=self.data
        value=builder.guided(self.admin,self.pid,self.did,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'goal':'Reset permission','behavior':'Allow reset only after the trip clears.','acceptance':'Verify reset remains blocked while trip feedback is present.'})
        rows=value['revision']['content']['requirements'];self.assertEqual(original,rows[0]);self.assertEqual('FR-011',rows[1]['id'])
        self.assertTrue(value['revision']['content']['sources'][-1]['text'].startswith('Reset permission'))

    def test_chopper_retains_original_mom_actions_and_bilingual_source(self):
        from types import SimpleNamespace
        from backend.core.workhub_intelligence import processing
        original={'meeting_subject':'Review','actions':[{'id':'existing-action','text':'Confirm reset behavior','responsible':'Human reviewer','target_date':'2026-11-01','source_ids':[]}],'sources':[]}
        with hub.db(True) as db:
            doc,rev=store.pi.create_document(db,self.admin,self.pid,'mom','Review',original)
        brief='Tamil-English meeting notes: '+chr(0x0BAE)+chr(0x0BBF)+chr(0x0BA9)+chr(0x0BCD)+' alarm reset remains pending.'
        payload={'document_id':doc['id'],'revision_id':rev['id'],'base_hash':bindings.digest(rev['content']),'kind':'mom','brief':brief,'language':'ta','file_ids':[],'request_id':'bilingual-fixture','instruction':''}
        job=SimpleNamespace(row={'project_id':self.pid,'payload':payload},check=lambda:None,progress=lambda *a:None)
        with patch.object(processing,'source_model',return_value={'actions':[{'text':'Review the alarm reset','source_ids':['BRIEF-bilingual-fixture']}]}):value=builder.process(job,self.admin)
        self.assertEqual(original['actions'][0],value['proposal']['actions'][0]);self.assertEqual(brief,value['proposal']['sources'][-1]['text']);self.assertIsNone(value['proposal']['actions'][1]['responsible'])

    def test_document_content_lock_includes_header_text_but_allows_color_changes(self):
        self.populated();d=self.data
        self.data=service.lock(self.admin,self.pid,self.did,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'element_id':'document','kind':'content','locked':True,'reason':'Protect all reviewed wording.'})
        l=copy.deepcopy(self.data['layout']);l['header']['variants']['default']['items'][3]['text']='Altered wording'
        with self.assertRaises(HTTPException) as e:self.save(layout=l)
        self.assertEqual(423,e.exception.status_code)
        l=copy.deepcopy(self.data['layout']);l['header']['variants']['default']['items'][3]['color']='#112233';self.save(layout=l)

    def test_metadata_is_readonly_and_standalone_flowchart_remains_connected(self):
        l=bindings.seed({'nodes':[{'id':'start','position':{'x':0,'y':0},'data':{'label':'Start'}}],'edges':[]},'flowchart')
        self.assertTrue(any(b['type']=='native_flowchart' for b in l['blocks']))
        material=bindings.materialize({},self.data['layout'],self.data['fields'])
        self.assertTrue(all(c['native_readonly'] for b in material['blocks'] if b['id']=='document-metadata' for c in b['data']['cells']))

    def test_mixed_paper_sections_and_resized_elements_export(self):
        self.populated();l=copy.deepcopy(self.data['layout']);l['blocks'].append({'id':'landscape-section','type':'section_break','data':{'title':'Landscape appendix','page':{**l['page'],'size':'A3','orientation':'landscape'},'header':l['header'],'footer':l['footer']},'style':{}})
        l['blocks'].append({'id':'resized-note','type':'panel','data':{'title':'Appendix','runs':[{'text':'Landscape section content.'}]},'style':{'height':30,'width':80}});self.save(layout=l)
        with hub.db() as db:
            p,doc,rev,control=store.document(db,self.admin,self.pid,self.did);context=render_common.context(db,p,doc,rev,control)
        raw=exporting.render_pdf(context);reader=PdfReader(io.BytesIO(raw));self.assertGreaterEqual(len(reader.pages),2)
        self.assertAlmostEqual(420,float(reader.pages[-1].mediabox.width)*25.4/72,delta=.5);self.assertIn('Landscape section content.',reader.pages[-1].extract_text())
        d=Document(io.BytesIO(docx_renderer.render(context)));self.assertEqual(2,len(d.sections));self.assertAlmostEqual(420,d.sections[-1].page_width.mm,delta=.5)
        self.assertTrue(any(r.height and r.height.mm>=29 for t in d.tables for r in t.rows))

    def test_long_diagram_labels_and_word_logos_retain_their_geometry(self):
        from PIL import Image
        import base64,hashlib,re
        from lxml import etree
        label='Review the motor alarm behavior and document the reset conditions before approving the proposed requirement.'
        block={'type':'flowchart','data':{'nodes':[{'id':'step','label':label,'kind':'process','x':0,'y':0}],'edges':[]}}
        svg=render_common.diagram_svg(block);self.assertGreater(float(re.search(r'height="([0-9.]+)"',svg)[1]),56)
        raw=render_common.raster(block);self.assertTrue(raw.startswith(b'\x89PNG'))
        self.populated()
        with hub.db() as db:
            p,doc,rev,control=store.document(db,self.admin,self.pid,self.did);value=render_common.context(db,p,doc,rev,control)
        stream=io.BytesIO();Image.new('RGB',(120,40),'blue').save(stream,'PNG');image=stream.getvalue()
        value['assets']['company']={'data':base64.b64encode(image).decode(),'sha256':hashlib.sha256(image).hexdigest()}
        data=docx_renderer.render(value)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml=etree.fromstring(z.read('word/header1.xml'));shape=xml.xpath('//*[local-name()="imagedata"]/..')[0]
            style=shape.get('style');w=float(re.search(r'width:([0-9.]+)pt',style)[1]);h=float(re.search(r'height:([0-9.]+)pt',style)[1]);self.assertAlmostEqual(3,w/h,delta=.01)
    def test_locks_apply_to_native_api_and_require_explicit_authorized_unlock(self):
        self.populated();d=self.data
        self.data=service.lock(self.admin,self.pid,self.did,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'element_id':'native-requirements','kind':'content','locked':True,'reason':'Reviewed requirement wording.'})
        c=copy.deepcopy(self.data['revision']['content']);c['requirements'][0]['title']='Unexpected change'
        with self.assertRaises(HTTPException) as e:documents.save(self.admin,self.pid,self.control,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'content':c})
        self.assertEqual(423,e.exception.status_code)
        with self.assertRaises(HTTPException):service.lock(self.reviewer,self.pid,self.did,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'element_id':'native-requirements','kind':'content','locked':False,'reason':'Not the lock owner'})
        self.data=service.lock(self.admin,self.pid,self.did,{'revision_id':d['revision']['id'],'version':d['revision']['version'],'element_id':'native-requirements','kind':'content','locked':False,'reason':'Prepare the verified correction.'})
        self.save({'requirements':c['requirements']});self.assertEqual('Unexpected change',self.data['revision']['content']['requirements'][0]['title'])
    def test_review_anchors_and_unresolved_correction_gate_submission(self):
        self.populated();rev=self.data['revision'];quote='Verify'
        r=reviews.add(self.reviewer,self.pid,self.did,{'revision_id':rev['id'],'block_id':'native-purpose','start_offset':0,'end_offset':len(quote),'quote':quote,'kind':'correction','body':'Clarify the acceptance wording.','assignee_id':self.admin['id']})
        with self.assertRaises(HTTPException):qc.action(self.admin,self.pid,self.control,{'revision_id':rev['id'],'version':rev['version'],'action':'confirm'})
        reviews.update(self.reviewer,self.pid,self.did,r['id'],{'version':1,'action':'resolve','body':'The clarified requirement was verified.'})
        qc.action(self.admin,self.pid,self.control,{'revision_id':rev['id'],'version':rev['version'],'action':'confirm'})
        self.assertEqual('resolved',reviews.list_comments(self.admin,self.pid,self.did)['items'][0]['status'])
    def test_comparison_identifies_requirement_cell_and_layout_changes(self):
        self.populated();approved=self.approve();left=approved['revision']['id']
        self.data=service.revision(self.admin,self.pid,self.did,{'revision_id':left,'reason':'Revise the reviewed behavior.'})
        rows=copy.deepcopy(self.data['revision']['content']['requirements']);rows[0]['acceptance_criteria']='Verify the displayed alarm and reset permission.';self.save({'requirements':rows})
        value=compare.compare(self.reviewer,self.pid,self.did,left,self.data['revision']['id'])
        changed=next(r for r in value['changes'] if r['id']=='native-requirements');self.assertEqual('modified',changed['state']);self.assertIn('FR-001:acceptance_criteria',[c['id'] for c in changed['cells']])
        self.assertTrue(any(s['type']=='added' for c in changed['cells'] for s in c['spans']))
    def test_connected_drafts_expose_requirement_change_impact(self):
        self.populated();self.approve();frd_rev=self.data['revision']['id']
        with hub.db() as db:target=db.execute("SELECT n.id FROM qc_documents q JOIN pi_documents n ON n.id=q.document_id WHERE q.project_id=? AND q.stage='fat'",(self.pid,)).fetchone()[0]
        graph=connections.graph(self.admin,self.pid,self.did);self.assertTrue(graph['links']);self.assertFalse(any(l['requires_review'] for l in graph['links'] if l['source_revision_id']==frd_rev))
        self.data=service.revision(self.admin,self.pid,self.did,{'revision_id':frd_rev,'reason':'Change trip behavior.'});r=copy.deepcopy(self.data['revision']['content']['requirements']);r[0]['expected_behavior']='Alarm is shown until reset.';self.save({'requirements':r})
        self.assertTrue(any(l['requires_review'] for l in connections.graph(self.reviewer,self.pid,self.did)['links']))
    def test_templates_preserve_every_content_block_and_native_field(self):
        self.populated();d=self.data;l=copy.deepcopy(d['layout']);l['blocks'].append({'id':'bespoke','type':'paragraph','data':{'runs':[{'text':'Keep this customer-specific note.'}]},'style':{}});self.save(layout=l)
        template=library.save_template(self.admin,self.pid,self.did,{'revision_id':self.data['revision']['id'],'name':'Blue professional layout','layout':self.data['layout'],'shared':True,'version':0})
        before=copy.deepcopy(self.data['revision']['content']['requirements']);result=library.apply_template(self.admin,self.pid,self.did,template['id'],{'revision_id':self.data['revision']['id'],'version':self.data['revision']['version']})
        self.assertEqual(before,result['revision']['content']['requirements']);self.assertEqual('Keep this customer-specific note.',next(b for b in result['layout']['blocks'] if b['id']=='bespoke')['data']['runs'][0]['text'])
        library.lock_template(self.admin,template['id'],{'version':1,'locked':True,'reason':'Publish the controlled layout.'})
        with self.assertRaises(HTTPException):library.save_template(self.admin,self.pid,self.did,{'id':template['id'],'revision_id':self.data['revision']['id'],'name':'Overwrite','version':2})
    def test_approved_library_content_requires_approval_and_cannot_copy_signatures(self):
        self.populated()
        with self.assertRaises(HTTPException):library.save_snippet(self.admin,self.pid,self.did,{'revision_id':self.data['revision']['id'],'title':'Not approved','block_ids':['native-purpose']})
        self.approve();key=library.save_snippet(self.admin,self.pid,self.did,{'revision_id':self.data['revision']['id'],'title':'Approved purpose','block_ids':['native-purpose'],'shared':True})['id']
        with self.assertRaises(HTTPException):library.save_snippet(self.admin,self.pid,self.did,{'revision_id':self.data['revision']['id'],'title':'No signature reuse','block_ids':['recorded-approval']})
        old=self.data['revision']['id'];self.data=service.revision(self.admin,self.pid,self.did,{'revision_id':old,'reason':'Reuse the approved standard clause.'})
        result=library.insert_snippet(self.admin,self.pid,self.did,key,{'revision_id':self.data['revision']['id'],'version':self.data['revision']['version']})
        self.assertTrue(any(b['type']=='paragraph' and schema.plain(b['data'].get('runs',[]))=='Verify the requested machine behavior.' for b in result['layout']['blocks']))
    def test_invalid_layout_and_external_image_references_are_rejected(self):
        for change in ({'font_size':float('nan')},{'size':'Remote paper'},{'columns':0}):
            with self.assertRaises(HTTPException):schema.page(change)
        layout=copy.deepcopy(self.data['layout']);layout['blocks'].append({'id':'remote-image','type':'image','style':{},'data':{'source':'file','file_id':'https://example.com/private.png','caption':'','alt':''}})
        with self.assertRaises(HTTPException):self.save(layout=layout)
        with self.assertRaises(HTTPException):schema.table({'rows':2,'columns':2,'cells':[{'id':'bad','row':0,'col':0,'rowspan':2,'colspan':2,'runs':[]},{'id':'overlap','row':1,'col':1,'runs':[]}]})
    def test_private_independent_documents_retain_access_control(self):
        created=workhub_document_spaces.create(self.admin,{'stage':'frd','title':'Private standalone draft'})
        with hub.db() as db:did=db.execute('SELECT id FROM pi_documents WHERE project_id=?',(created['scope_id'],)).fetchone()[0]
        with self.assertRaises(HTTPException) as e:service.get(self.other,created['scope_id'],did)
        self.assertEqual(403,e.exception.status_code)
    def test_pdf_docx_snapshot_is_stable_and_contains_page_fields(self):
        self.populated();self.approve();rid=self.data['revision']['id']
        pdf,_,_=exporting.export(self.admin,self.pid,self.did,rid,'pdf');docx,_,_=exporting.export(self.admin,self.pid,self.did,rid,'docx')
        reader=PdfReader(io.BytesIO(pdf));self.assertEqual(1,len(reader.pages));body=reader.pages[0].extract_text();self.assertIn('Page 1 of 1',body);self.assertIn('Motor trip alarm',body);self.assertIn('Reviewed by',body)
        self.assertAlmostEqual(210,float(reader.pages[0].mediabox.width)*25.4/72,delta=.5)
        d=Document(io.BytesIO(docx));self.assertTrue(d.tables)
        with zipfile.ZipFile(io.BytesIO(docx)) as z:
            footer=''.join(z.read(name).decode() for name in z.namelist() if name.startswith('word/footer'))
            self.assertIn('PAGE',footer);self.assertIn('NUMPAGES',footer)
        self.assertEqual(pdf,exporting.export(self.reviewer,self.pid,self.did,rid,'pdf')[0]);self.assertEqual(docx,exporting.export(self.reviewer,self.pid,self.did,rid,'docx')[0])
        with self.assertRaises(HTTPException):self.save({'purpose':'Cannot modify an approved revision.'})

if __name__=='__main__':unittest.main()
