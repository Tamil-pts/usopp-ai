"""Geometry regression checks against the user's AS ladder references."""
import copy
import contextlib
import io
import json
import tempfile
from io import BytesIO
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from python_engine.compare import _ladder_networks, parse_ladder_diff, compare_projects
from python_engine.ladder_model import (network_model, normalized_model, primitives,
                                       render_svg, render_png, diagram_panels, LEFT, COL_WIDTH)

ROOT=Path(__file__).resolve().parents[2]


class LadderDiagramTests(unittest.TestCase):
    def sample(self, path, number):
        if not path.exists(): self.skipTest('Local ladder reference unavailable')
        return _ladder_networks(path.read_text(encoding='utf-8'))[number-1]

    def test_right_boundary_branches_do_not_bypass_preceding_contact(self):
        record=self.sample(ROOT/'LRJ9SXV16346_09092026/Logical/hs_flts/hs_fltsCyclic.ld',8)
        model=record['diagram']
        branch=next(c for c in model['connections'] if c['kind']=='branch')
        self.assertEqual((branch['column'],branch['edge']),(2,'right'))
        cid=branch['to']
        segments=[i for i in primitives(record)[2] if i['kind']=='line' and i['cell']==cid]
        self.assertEqual(len(segments),1)
        self.assertEqual(segments[0]['x1'],LEFT+2*COL_WIDTH)
        self.assertEqual(segments[0]['x1'],segments[0]['x2'])

    def test_parallel_ton_input_is_separate_from_pt_and_unused_outputs(self):
        record=self.sample(ROOT/'LRJ9SXV16346_09092026/Logical/hs_flts/hs_fltsCyclic.ld',15)
        width,height,items=primitives(record)
        self.assertEqual(1,len([i for i in items if i.get('block')]))
        upper=[c for c in record['diagram']['connections'] if c['kind']=='branch']
        self.assertEqual(1,upper[0]['column'])
        for cell in record['diagram']['cells']:
            if cell['kind']=='functionblock' and cell['outputs']:
                wires=[i for i in items if i['kind']=='line' and i['cell']==cell['id'] and i['x1']>LEFT+cell['column']*COL_WIDTH]
                self.assertTrue(all(i['x2']<width-LEFT for i in wires))
        self.assertGreater(height,250)

    def test_old_xml_inherits_block_type_and_retains_instance(self):
        source='<networks><network><row><empty/><functionblock position="header" name="FAULT_TIME"/></row><row><contact name="FAULT" type="open"/><functionblock position="top" type="CUMULATION"><input name="START"/><output name="ENABLED"/></functionblock></row><row><empty/><functionblock position="middle"><input name="RESET"/><output name="SECONDS"/></functionblock></row><row><empty/><functionblock position="bottom"><output name="HOURS"/></functionblock></row></network></networks>'
        record=_ladder_networks(source)[0]
        cells=[cell for cell in record['diagram']['cells'] if cell['kind']=='functionblock']
        self.assertEqual({'CUMULATION'},{cell['type'] for cell in cells})
        self.assertEqual({'FAULT_TIME'},{cell['instance'] for cell in cells})
        self.assertEqual(1,len({cell['blockId'] for cell in cells}))
        self.assertEqual(1,len([item for item in primitives(record)[2] if item.get('block')]))
        self.assertIn('FAULT_TIME',render_svg(record))
        old=copy.deepcopy(record)
        old['diagram']['schemaVersion']=2
        for cell in old['diagram']['cells']:
            cell['type']=cell['attributes'].get('type','')
            if cell['kind']=='functionblock':cell['blockId']=cell['id'];cell['instance']=''
        upgraded=normalized_model(old)
        self.assertEqual({'FAULT_TIME'},{cell['instance'] for cell in upgraded['cells'] if cell['kind']=='functionblock'})
        self.assertEqual(1,len([item for item in primitives(old)[2] if item.get('block')]))

    def test_compound_grid_groups_eq_and_or_and_rtrig(self):
        record=self.sample(Path(r'C:\Users\PTPL0241\Projects\Project 3\Logical\hs_mcseq\hs_mcseqCyclic.ld'),7)
        members=[c for c in record['diagram']['cells'] if c['kind'] in {'function','functionblock'}]
        self.assertEqual({1,3,8,10},{c['column'] for c in members})
        self.assertEqual(4,len({c['blockId'] for c in members}))
        self.assertEqual({'R3'},{c['instance'] for c in members if c['type']=='R_TRIG'})
        self.assertEqual([],record['diagram']['warnings'])
        values=[i['text'] for i in primitives(record)[2] if i['kind']=='text']
        self.assertNotIn('40',values)
        ET.fromstring(render_svg(record))
        items=primitives(record)[2]
        for panel in diagram_panels(record):
            right=panel['viewbox'][0]+panel['width']
            self.assertFalse(any(p['x']<right<p['x']+p['w'] for p in items if p.get('block')))

    def test_ton_shifted_xml_indices_and_conversion_are_one_block_each(self):
        record=self.sample(Path(r'C:\Users\PTPL0241\Projects\Project 3\Logical\hs_mcseq\hs_mcseqCyclic.ld'),11)
        ton=[c for c in record['diagram']['cells'] if c['type']=='TON']
        self.assertEqual({9},{c['column'] for c in ton})
        self.assertEqual({6,8,9},{c['xmlColumn'] for c in ton})
        self.assertEqual({'Y20_Tmr_T215'},{c['instance'] for c in ton})
        self.assertEqual(4,len([p for p in primitives(record)[2] if p.get('block')]))

    def test_topbottom_keeps_instance_and_legacy_results_upgrade(self):
        record=self.sample(ROOT/'LRJ9SXV16346_09092026/Logical/hs_flts/hs_fltsCyclic.ld',17)
        self.assertEqual({'R_TRIG_SYS_PRS'},{c['instance'] for c in record['diagram']['cells'] if c['kind']=='functionblock'})
        old=copy.deepcopy(record)
        old['diagram']['schemaVersion']=1
        for c in old['diagram']['cells']:
            c['column']=c['xmlColumn'];c.pop('span')
        upgraded=normalized_model(old)
        self.assertEqual(record['diagram']['cells'],upgraded['cells'])

    def test_reference_comparison_has_added_27_modified_28_and_green_added_diagram(self):
        base=(ROOT/'project 2/Logical/fault/faultCyclic.ld').read_text(encoding='utf-8')
        new=(ROOT/'project 1/Logical/fault/faultCyclic.ld').read_text(encoding='utf-8')
        comparison=parse_ladder_diff(base,new)
        added=next(c for c in comparison['controls'] if c['new'] and c['new']['index']==27)
        changed=next(c for c in comparison['controls'] if c['new'] and c['new']['index']==28)
        self.assertEqual('added',added['status'])
        self.assertEqual(('modified',28),(changed['status'],changed['base']['index']))
        self.assertIn('data-change="added"',render_svg(added['new'],None,'developed'))
        self.assertIn('#15803d',render_svg(added['new'],None,'developed'))
        self.assertIn('data-change="modified"',render_svg(changed['new'],changed['base'],'developed'))

    def test_continuations_and_png_do_not_create_new_networks(self):
        from PIL import Image
        record=self.sample(ROOT/'LRJ9SXV16346_09092026/Logical/hs_flts/hs_fltsCyclic.ld',83)
        panels=diagram_panels(record)
        self.assertGreater(len(panels),1)
        self.assertEqual(83,record['diagram']['network'])
        self.assertAlmostEqual(primitives(record)[1],sum(p['height'] for p in panels if p['column']==0))
        for panel in panels: ET.fromstring(panel['svg'])
        with Image.open(BytesIO(render_png(record))) as image:
            self.assertLessEqual(max(image.size),4800)

    def test_whitespace_and_attribute_order_do_not_change_logic(self):
        a='<networks><network label="" commented="0"><row><contact type="open" name="START"/><coil name="RUN" type="set"/></row></network></networks>'
        b='<networks>\n<network commented="0" label=""><row>\n<contact name="START" type="open"/>\n<coil type="set" name="RUN"/>\n</row></network></networks>'
        result=parse_ladder_diff(a,b)
        self.assertEqual('unchanged',result['controls'][0]['status'])

    def test_unchanged_ladder_is_parsed_and_lazy_with_declared_types(self):
        source='PROGRAM _CYCLIC\n<networks><network><row><analog type="input" name="SPEED"/><function position="topbottom" type="UINT_TO_REAL"><input name="IN"/><output name="OUT"/></function><analog type="output" name="RESULT"/></row></network></networks>\nEND_PROGRAM'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=root/'Logical/task';task.mkdir(parents=True)
            (task/'same.ld').write_text(source)
            (task/'task.var').write_text('VAR\nSPEED : UINT;\nRESULT : REAL;\nEND_VAR')
            (task/'IEC.prg').write_text('<Program><Files><File>same.ld</File></Files></Program>')
            with contextlib.redirect_stdout(io.StringIO()):
                result=compare_projects(root,root,detail_dir=root/'details')
            entry=next(item for item in result['same_logic_files'] if item['path'].endswith('.ld'))
            self.assertTrue(entry['ladder_structured_available'])
            self.assertNotIn('parsed_ladder',entry)
            self.assertFalse(any(item['path'].casefold().endswith(('.prg','.pkg')) for item in result['same_logic_files']))
            parsed=json.loads((root/'details'/f"{entry['ladder_detail_id']}.json").read_text())
            self.assertEqual(parsed['controls'][0]['status'],'unchanged')
            cell=next(c for c in parsed['controls'][0]['base']['diagram']['cells'] if c['name']=='SPEED')
            self.assertEqual(cell['datatype'],'UINT')
            self.assertEqual(cell['declarationFile'],'Logical/task/task.var')

    def test_older_unchanged_result_rebuilds_and_caches_diagram(self):
        from backend.api.comparison import _ladder_detail
        from fastapi import HTTPException
        source='<networks><network><row><contact name="START" type="open"/><coil name="RUN" type="set"/></row></network></networks>'
        entry={'path':'Logical/task/same.ld','category':'logic','status':'unchanged','base_source':source,'new_source':source}
        result={'same_logic_files':[entry,{'path':'Logical/task/task.var','base_source':'START : BOOL;','new_source':'START : BOOL;'}]}
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);parsed=_ladder_detail(result,work,entry['path'])
            self.assertEqual(parsed['controls'][0]['base']['diagram']['cells'][0]['datatype'],'BOOL')
            self.assertEqual(parsed['controls'][0]['base']['diagram']['cells'][0]['declarationFile'],'Logical/task/task.var')
            entry.pop('base_source');entry.pop('new_source')
            self.assertEqual(_ladder_detail(result,work,entry['path']),parsed)
            with self.assertRaises(HTTPException) as error:_ladder_detail(result,work,'../../secret.ld')
            self.assertEqual(error.exception.status_code,404)

    def test_unchanged_ladder_is_graphical_in_selected_export(self):
        from backend.core.compare_report_selection import select_report
        from backend.core.compare_exports import export_html,export_pdf,export_docx
        source='<networks><network><row><contact name="START" type="open"/><coil name="RUN" type="set"/></row></network></networks>'
        report=select_report({'baseName':'Base','newName':'New','same_logic_files':[{'path':'Logical/task/same.ld','category':'logic','status':'unchanged','parsed_ladder':parse_ladder_diff(source,source)}]},
            {'categories':['logic'],'statuses':['unchanged'],'includeKnowledge':False})
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            for suffix,writer in [('html',export_html),('pdf',export_pdf),('docx',export_docx)]:
                writer(report,work/f'report.{suffix}',work/'missing.png')
            self.assertIn('<svg',(work/'report.html').read_text(encoding='utf-8'))
            from pypdf import PdfReader
            self.assertTrue(PdfReader(work/'report.pdf').pages)
            from docx import Document
            self.assertTrue(Document(work/'report.docx').inline_shapes)


if __name__=='__main__': unittest.main()
