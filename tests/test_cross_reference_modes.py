import tempfile
import unittest
from pathlib import Path
from python_engine import rule_engine_v4_30 as engine
from python_engine import structured_requirements as requirements
from backend.core.rule_exports import text


class CrossReferenceModes(unittest.TestCase):
    def test_or_and_cross_references_for_st_ab_hmi_and_ladder(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            files={
                'Logical/Main/Main.st':'ready := TRUE;',
                'Logical/Other/Accepted.st':'enabled := TRUE;',
                'Logical/Other/Accepted.ab':'enabled = 1',
                'Logical/HMI/Pages/Accepted.page':'<Page><Control Name="Input"><Property Name="ValueDatapoint" Value="Local.GLOBAL.Mode"/></Control></Page>',
                'Logical/Other/Accepted.ld':'<networks><network><row><contact type="normallyopen" name="Ready"/></row></network></networks>',
            }
            for name,source in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source,encoding='utf-8')
            alternatives=[
                {'type':'logic','file':'Logical/Other/Accepted.st','alternatives':['enabled := TRUE;']},
                {'type':'logic','file':'Logical/Other/Accepted.ab','alternatives':['enabled = 1']},
                {'type':'hmi','file':'Logical/HMI/Pages/Accepted.page','variants':[{'name':'Input','properties':{'ValueDatapoint':'Local.GLOBAL.Mode'}}]},
                {'type':'ladder','file':'Logical/Other/Accepted.ld','networks':[{'id':'n1','mode':'exact','xml':'<network><row><contact type="normallyopen" name="Ready"/></row></network>'}]},
            ]
            for candidate in alternatives:
                with self.subTest(type=candidate['type'],file=candidate['file']):
                    check={'type':'logic','file':'Logical/Main/Main.st','alternatives':['ready := TRUE;'],
                           'crossChecks':[{'type':'logic','file':'Logical/Missing.st','alternatives':['missing := TRUE;']},candidate]}
                    rule={'id':'R-test','name':'Cross reference test','category':'PLC logic + HMI','kind':'structured_requirements','checks':[check]}
                    self.assertEqual('FAIL',requirements.evaluate(root,rule,engine)['status'])
                    check['crossCheckMode']='any'
                    result=requirements.evaluate(root,rule,engine)
                    self.assertEqual('PASS',result['status'],result)
                    self.assertTrue(any(row['status']=='NOT_REQUIRED' for row in result['evidence']))
                    self.assertTrue(any(row['file']==candidate['file'] and row['status']=='PASS' for row in result['evidence']))
                    # An OR match must still satisfy the complete chosen check.
                    if candidate['type']=='hmi':
                        candidate['variants'][0]['properties']['InputTouchpad']='MissingPad'
                        self.assertEqual('FAIL',requirements.evaluate(root,rule,engine)['status'])

    def test_legacy_cross_reference_or_preserves_default_and(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'Accepted.ab').write_text('enabled = 1',encoding='utf-8')
            rule={'crossFunctionChecks':[
                {'name':'Older file','sourceFiles':['Missing.st'],'logicAlternatives':['enabled := TRUE;']},
                {'name':'Other format','sourceFiles':['Accepted.ab'],'logicAlternatives':['enabled = 1']},
            ]}
            _,failures=engine._cross_function_logic_checks(root,rule)
            self.assertEqual(['Older file'],failures)
            rule['crossFunctionMode']='any'
            evidence,failures=engine._cross_function_logic_checks(root,rule)
            self.assertEqual([],failures)
            self.assertEqual(['NOT_REQUIRED','PASS'],[row['status'] for row in evidence])

    def test_export_evidence_has_readable_labels_and_source_lines(self):
        rendered=text([{'check':'Requirement 1','file':'Logical/Main.st','line':23,'actual':'ready := TRUE;\nvalue := 2;','expected':['ready := TRUE;\nvalue := 2;']}])
        self.assertIn('Check:\nRequirement 1',rendered)
        self.assertIn('Line:\n23',rendered)
        self.assertIn('ready := TRUE;\nvalue := 2;',rendered)
        self.assertNotIn('"check":',rendered)
        self.assertNotIn('\\n',rendered)

if __name__=='__main__': unittest.main()
