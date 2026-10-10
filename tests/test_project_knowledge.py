import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

from python_engine.project_knowledge import build_index, retrieve, comparison_knowledge, explanation_supported
from python_engine.ladder_model import network_model, primitives, render_svg


class ProjectKnowledgeTests(unittest.TestCase):
    def test_model_citations_must_match_retrieved_evidence(self):
        evidence=[{'file':'Logical/motor/motorCyclic.st','line':10,'excerpt':'IF START THEN\n MOTOR_RUN := TRUE;\nEND_IF'}]
        self.assertTrue(explanation_supported('START sets MOTOR_RUN [S1].',evidence))
        self.assertFalse(explanation_supported('motorInit.ld starts the motor [S1].',evidence))
        self.assertFalse(explanation_supported('START sets MOTOR_RUN [S9].',evidence))
        self.assertFalse(explanation_supported('motorCyclic.st line 500 starts the motor [S1].',evidence))
        self.assertFalse(explanation_supported('The motor starts automatically.',evidence))

    def test_disabled_networks_are_not_presented_as_running_logic(self):
        chunks=[
            {'file':'Logical/motor.ld','line':10,'category':'Ladder','ownership':'active task','network':1,'enabled':False,'text':'START MOTOR disabled','terms':['start','motor']},
            {'file':'Logical/motor.ld','line':20,'category':'Ladder','ownership':'active task','network':2,'enabled':True,'text':'START MOTOR enabled','terms':['start','motor']},
        ]
        found=retrieve({'chunks':chunks},'Explain motor START')
        self.assertEqual([e['network'] for e in found],[2])
        disabled=retrieve({'chunks':chunks},'Explain motor.ld network 1')
        self.assertEqual(disabled[0]['enabled'],False)
        self.assertFalse(explanation_supported('START runs MOTOR [S1].',disabled))
        self.assertTrue(explanation_supported('This network is commented out and does not execute [S1].',disabled))

    def test_active_scope_cache_and_variable_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'project'; root.mkdir()
            (root/'LastUser.set').write_text('<ProjectSettings><ConfigurationManager ActiveConfigurationName="Active"/></ProjectSettings>')
            (root/'Machine.apj').write_text('<Project/>')
            active=root/'Physical/Active/PLC1'; active.mkdir(parents=True)
            (active/'Cpu.sw').write_text('<SwConfiguration><Task Source="motor.prg" Name="Motor"/></SwConfiguration>')
            inactive=root/'Physical/Other/PLC1'; inactive.mkdir(parents=True)
            (inactive/'IoMap.iom').write_text('INACTIVE_SERIAL AT %ID.Remote.SerialNumber;')
            motor=root/'Logical/motor'; motor.mkdir(parents=True)
            (motor/'motorCyclic.st').write_text('IF START AND NOT STOP THEN\n MOTOR_RUN := TRUE;\nEND_IF;')
            (motor/'motor.var').write_text('MOTOR_RUN : BOOL;')
            cache=Path(temporary)/'cache'
            first=build_index(root,cache)
            self.assertEqual(first['identity']['active_configuration'],'Active')
            self.assertFalse(any('Other' in item['file'] for item in first['inventory']))
            self.assertTrue(any(c['ownership']=='active task' for c in first['chunks'] if c['category']=='Logic'))
            evidence=retrieve(first,'Where is MOTOR_RUN declared and assigned?')
            self.assertTrue(any(e['file'].endswith('.var') for e in evidence))
            self.assertTrue(any(e['file'].endswith('.st') for e in evidence))
            self.assertEqual(build_index(root,cache)['fingerprint'],first['fingerprint'])
            (motor/'motorCyclic.st').write_text('MOTOR_RUN := FALSE; // changed')
            self.assertNotEqual(build_index(root,cache)['fingerprint'],first['fingerprint'])

    def test_comparison_categories_and_exact_before_after(self):
        result={'baseName':'A','newName':'B','diffs':[
            {'path':'Global.var','category':'logic','status':'modified','base_source':'Speed : UINT;','new_source':'Speed : REAL;\nEnable : BOOL;'},
            {'path':'Screen.page','category':'screen','status':'modified','parsed_screen':{'controls':[
                {'name':'Button','status':'modified','changes':[{'prop':'Left','from':'10','to':'20'},
                 {'prop':'ValueDatapoint','from':'Old','to':'New'}]}]}},
            {'path':'Motor.ld','category':'logic','status':'modified','parsed_ladder':{'changes':[{'name':'Network 1','type':'modified'}]}}
        ]}
        knowledge=comparison_knowledge(result)
        self.assertEqual(knowledge['counts']['Variables'],2)
        self.assertEqual(knowledge['counts']['HMI layout'],1)
        self.assertEqual(knowledge['counts']['HMI behaviour'],1)
        self.assertEqual(knowledge['counts']['Ladder'],1)
        speed=next(r for r in knowledge['categories']['Variables'] if r['name']=='Speed')
        self.assertEqual(speed['before']['declaration'],'UINT')
        self.assertEqual(speed['after']['declaration'],'REAL')

    def test_ladder_branch_and_single_cell_conversion(self):
        xml='''<network><row><contact name="START" type="open"/><contact name="STOP" type="closed" or="true"/><coil name="A" type="open"/></row>
        <row><empty or="true"/><contact name="A" type="open"/><empty or="true"/></row></network>'''
        model=network_model(ET.fromstring(xml),1)
        width,height,items=primitives(model)
        vertical=[i for i in items if i['kind']=='line' and i['x1']==i['x2'] and abs(i['y2']-i['y1'])>=80]
        self.assertTrue(vertical)
        svg=render_svg(model)
        ET.fromstring(svg)
        self.assertIn('START',svg)
        model=network_model(ET.fromstring('<network><row><analog name="YEAR" type="input"/><function type="UINT_TO_REAL" position="topbottom"><input name="IN"/><output name="1"/></function><analog name="REAL_YEAR" type="output"/></row></network>'),1)
        svg=render_svg(model)
        self.assertIn('UINT_TO_REAL',svg)
        rectangles=[i for i in primitives(model)[2] if i['kind']=='rect']
        self.assertEqual(len(rectangles),1)

    def test_function_block_has_one_continuous_body(self):
        model=network_model(ET.fromstring('''<network><row><empty/><functionblock name="DELAY" type="TON" position="header"/></row>
        <row><contact name="START" type="open"/><functionblock type="TON" position="top"><input name="IN"/><output name="Q"/></functionblock></row>
        <row><analog name="T#5s" type="input"/><functionblock type="TON" position="bottom"><input name="PT"/><output name="ET"/></functionblock></row></network>'''),1)
        rects=[i for i in primitives(model)[2] if i['kind']=='rect']
        self.assertEqual(len(rects),1)
        self.assertGreater(rects[0]['h'],160)
        self.assertIn('DELAY',render_svg(model))


if __name__=='__main__': unittest.main()
