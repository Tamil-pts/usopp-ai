import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from python_engine.structured_requirements import referenced_hmi_requirements


class TouchpadLetters(unittest.TestCase):
    def test_actual_letters_preserve_case(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'Logical/HMI'
            (root/'Pages').mkdir(parents=True)
            (root/'TouchPads').mkdir()
            (root/'TouchPads/Alpha.tpr').write_text('<TouchPad><PanelItem Index="1"><KeyLevel Level="2" VirtualKey="TP_ALPHA_A"/><KeyLevel Level="4" VirtualKey="TP_ALPHA_A"/></PanelItem><PanelItem Index="2"><KeyLevel Level="2" VirtualKey="TP_ALPHA_B"/><KeyLevel Level="4" VirtualKey="TP_ALPHA_sb"/></PanelItem></TouchPad>')
            node=ET.fromstring('<Control><Property Name="InputTouchpad" Value="Alpha"/></Control>')
            rows=referenced_hmi_requirements(root/'Pages/Main.page',node,{'referenceChecks':[{'kind':'touchpad','characterRequirement':'uppercase'}]})
            decoded=next(row for row in rows if row['property'].endswith('decoded letters'))
            self.assertIn('A / A',decoded['actual'])
            self.assertIn('B / b',decoded['actual'])
            self.assertNotIn('TP_ALPHA',decoded['actual'])
            requirement=next(row for row in rows if row['property'].endswith('character requirement'))
            self.assertEqual('FAIL',requirement['status'])
            self.assertEqual('Lowercase letters found: b',requirement['actual'])

if __name__=='__main__': unittest.main()
