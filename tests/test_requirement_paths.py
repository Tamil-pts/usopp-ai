import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from python_engine.structured_requirements import matching_files


class RequirementPaths(unittest.TestCase):
    def test_task_source_aliases_and_exact_project_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            names=['Logical/SpinConnect/mms_nw_r/mms_nw_rCyclic.st',
                   'Logical/Other/mms_nw_r/Cyclic.st',
                   'Logical/Other/not_mms_nw_r/Cyclic.st',
                   'Logical/C70/Pages/Process.page',
                   'Logical/T30/Pages/Process.page']
            files=[root/name for name in names]
            engine=SimpleNamespace(all_files=lambda _:files)
            cases={
                'mms_nw_rCyclic.st':files[:2],
                r'mms_nw_r\mms_nw_rCyclic.st':files[:2],
                r'mms_nw_r\Cyclic.st':files[:2],
                'MMS_NW_R/CYCLIC.ST':files[:2],
                './Logical/Other/mms_nw_r/Cyclic.st':[files[1]],
                'Logical/mms_nw_r/Cyclic.st':[],
                'wrong/Cyclic.st':[],
                '../Cyclic.st':[],
                'C70/Pages/Process.page':[files[3]],
                'Process.page':files[3:],
            }
            for pattern,expected in cases.items():
                with self.subTest(pattern=pattern):
                    self.assertEqual(matching_files(root,pattern,engine),expected)
