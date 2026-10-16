import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import package_container, package_container_build, package_downloads


class ContainerPackagingTests(unittest.TestCase):
    def write(self, root, name, text='fixture'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
        return target

    def runtime_fixture(self, root):
        for name in ('backend/__init__.py', 'backend/app.py',
                     'python_engine/__init__.py', 'python_engine/engine.py',
                     'scripts/container_bootstrap.py', 'scripts/container_maintenance.py'):
            self.write(root, name, 'VALUE = 1\n')
        for name in ('dist/index.html', 'dist/nami/index.html', 'rules/default.json', 'rules/references/lapformer.json',
                     'knowledge/master/default.json', 'knowledge/data_models/default.json',
                     'knowledge/dashboard_layouts/catalog.json', 'knowledge/lapformer/catalog.json',
                     'knowledge/chopper/engineering_tasks.json',
                     'knowledge/help_index/project_guide.json',
                     'knowledge/help_index/BR_PROJECT_HELP.md',
                     'src/usopp_logo.png', 'src/petrus_logo.png',
                     'local_ai/MODEL_LICENSE.txt', 'local_ai/MODEL_CARD.md'):
            self.write(root, name)
        self.write(root, 'package.json', json.dumps({'name': 'fixture', 'version': '1.2.3',
                                                   'scripts': {'dev': 'private-build-command'}}))

    def test_runtime_compiles_application_and_preserves_only_runtime_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'source'
            self.runtime_fixture(root)
            for name in ('rules/learning/private.json', 'rules/feedback/private.json',
                         'rules/archive/private.json', 'knowledge/projects/private.json',
                         'knowledge/br_help/private.html', 'knowledge/help_index/br_help.sqlite3',
                         'knowledge/dashboard_layouts/users/1/private.json',
                         'local_ai/models/private.gguf', '.env', 'accounts.sqlite3'):
                self.write(root, name)
            output = base / 'runtime'
            with patch.object(package_container, 'ROOT', root):
                package_container.stage(output)
            self.assertTrue((output / 'backend/app.pyc').is_file())
            self.assertTrue((output / 'python_engine/engine.pyc').is_file())
            self.assertTrue((output / 'container_bootstrap.pyc').is_file())
            self.assertTrue((output / 'container_maintenance.pyc').is_file())
            self.assertTrue((output / 'knowledge/chopper/engineering_tasks.json').is_file())
            self.assertTrue((output / 'knowledge/master/default.json').is_file())
            self.assertTrue((output / 'knowledge/data_models/default.json').is_file())
            self.assertTrue((output / 'knowledge/dashboard_layouts/catalog.json').is_file())
            self.assertTrue((output / 'knowledge/lapformer/catalog.json').is_file())
            self.assertTrue((output / 'rules/references/lapformer.json').is_file())
            self.assertEqual(sorted(p.name for p in (output / 'knowledge/help_index').iterdir()),
                             ['BR_PROJECT_HELP.md', 'project_guide.json'])
            paths = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            self.assertFalse(any(Path(p).suffix in package_container.SOURCE_SUFFIXES for p in paths))
            self.assertFalse(any('private' in p for p in paths))
            self.assertEqual(json.loads((output / 'package.json').read_text(encoding='utf-8')),
                             {'name': 'fixture', 'version': '1.2.3'})

    def test_runtime_rejects_raw_source_accidentally_added_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.runtime_fixture(base / 'source')
            self.write(base / 'source', 'knowledge/chopper/accidental.py', 'VALUE = 1\n')
            with patch.object(package_container, 'ROOT', base / 'source'):
                with self.assertRaisesRegex(ValueError, 'Raw application source found'):
                    package_container.stage(base / 'runtime')

    def test_private_source_bundle_excludes_private_runtime_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in package_container_build.ROOT_FILES | set(package_container_build.EXTRA_FILES):
                self.write(root, name)
            for name in package_container_build.DIRECTORIES:
                self.write(root, name + '/default.json')
            self.write(root, 'backend/app.py', 'VALUE = 1\n')
            private = ('backend/.env', 'nami/node_modules/private.js',
                       'knowledge/help_index/br_help.sqlite3', 'knowledge/projects/private.json',
                       'local_ai/models/private.gguf', 'local_ai/training/private.jsonl',
                       'rules/learning/private.json', 'rules/feedback/private.json',
                       'rules/archive/private.json', 'backend/private.key',
                       'backend/accounts.sqlite3', 'backend/accounts.sqlite3-wal')
            for name in private:
                self.write(root, name)
            with patch.object(package_container_build, 'ROOT', root):
                paths = {p.relative_to(root).as_posix() for p in package_container_build.files_to_pack()}
            self.assertIn('backend/app.py', paths)
            self.assertIn('Dockerfile', paths)
            self.assertIn('scripts/package_container.py', paths)
            self.assertFalse(set(private) & paths)

    def test_download_zip_rejects_original_application_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.write(root, 'engine.py', 'VALUE = 1\n')
            with self.assertRaisesRegex(ValueError, 'Raw application source'):
                package_downloads.write_zip(root / 'release.zip', [(source, 'engine.py')])

    def test_launcher_zip_omits_private_build_source_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, 'package.json', '{"version":"1.2.3"}')
            for name in ('README.md', 'LAN_SERVER.md', 'compose.yaml',
                         'usopp-container.ps1', 'usopp-container.sh',
                         'uSOPp_AI_1.2.3_Container_Build_Source.tar.gz'):
                self.write(root, 'distribution/' + name)
            output = root / 'release'
            with patch.object(package_downloads, 'ROOT', root), patch('sys.argv',
                    ['package_downloads.py', '--output', str(output)]):
                package_downloads.main()
            with zipfile.ZipFile(output / 'uSOPp_AI_1.2.3_Container_Launchers.zip') as archive:
                self.assertEqual(set(archive.namelist()), {'README.md', 'LAN_SERVER.md',
                    'compose.yaml', 'usopp-container.ps1', 'usopp-container.sh'})


if __name__ == '__main__':
    unittest.main()
