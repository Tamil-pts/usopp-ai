"""Validate actual collected driver assets, rather than matching build-script text."""
from importlib.util import find_spec
from pathlib import Path
import runpy
import unittest


@unittest.skipUnless(find_spec('PyInstaller') and find_spec('playwright'), 'Windows build dependencies are optional here')
class WindowsDriverCollectionTests(unittest.TestCase):
    def test_both_playwright_apis_retain_driver_without_forbidden_source(self):
        root=Path(__file__).resolve().parents[1]/'deploy/pyinstaller/hooks'
        for api in ('async_api','sync_api'):
            with self.subTest(api=api):
                rows=runpy.run_path(str(root/('hook-playwright.'+api+'.py')))['datas']
                sources=[Path(source) for source,_ in rows]
                self.assertTrue(sources)
                self.assertFalse([p for p in sources if p.suffix.lower() in {'.py','.pyw','.ts','.tsx','.map'}])
                self.assertTrue(any(p.name in {'node','node.exe'} for p in sources))
                self.assertTrue(any(p.name=='cli.js' for p in sources))


if __name__=='__main__':unittest.main()
