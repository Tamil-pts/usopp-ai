"""Scoped AS object trees preserve descriptor metadata and all source files."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from python_engine.project_tree import build_project_tree
from python_engine.compare import compare_projects, project_identity, walk_project


class ProjectTreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def tree(self):
        identity = project_identity(self.root)
        return build_project_tree(self.root, walk_project(self.root, identity), identity)

    def find(self, tree, key):
        for child in tree['children']:
            if child['key'] == key:
                return child
            found = self.find(child, key)
            if found:
                return found

    def test_package_order_type_description_and_namespaces(self):
        self.write('Demo.apj', '<Project/>')
        self.write('Logical/Global.var', 'VAR END_VAR')
        self.write('Logical/Global.typ', 'TYPE END_TYPE')
        self.write('Logical/run/IEC.prg', '<Program><Files><File>run.st</File></Files></Program>')
        self.write('Logical/run/run.st', 'PROGRAM _CYCLIC END_PROGRAM')
        self.write('Logical/Package.pkg', '<Package xmlns="urn:br"><Objects><Object Type="File">Global.typ</Object><Object Type="File" Description="Shared variables">Global.var</Object><Object Type="Program" Language="IEC" Description="Operating sequence">run</Object></Objects></Package>')
        tree = self.tree()
        self.assertEqual(tree['name'], 'Demo')
        self.assertEqual([node['name'] for node in tree['children'][:3]], ['Global.typ', 'Global.var', 'run'])
        program = self.find(tree, 'Logical/run')
        self.assertEqual(program['kind'], 'program')
        self.assertEqual(program['description'], 'Operating sequence')
        self.assertEqual(program['language'], 'IEC')
        self.assertEqual(self.find(tree, 'Logical/Global.var')['description'], 'Shared variables')

    def test_program_file_order_and_descriptors(self):
        self.write('Logical/run/IEC.prg', '<Program><Files><File>runCyclic.st</File><File>runInit.st</File><File Private="true">run.var</File></Files></Program>')
        for name in ['run.var', 'runInit.st', 'runCyclic.st']:
            self.write('Logical/run/' + name, 'source')
        program = self.find(self.tree(), 'Logical/run')
        self.assertEqual([child['name'] for child in program['children'][:3]], ['runCyclic.st', 'runInit.st', 'run.var'])
        self.assertEqual(len(program['children']),3)
        self.assertTrue(all(not child['descriptor'] for child in program['children']))

    def test_libraries_keep_interface_sources_and_description(self):
        self.write('Logical/Libraries/Package.pkg', '<Package><Objects><Object Type="Library" Description="Iyyappan V">GENERAL</Object></Objects></Package>')
        self.write('Logical/Libraries/GENERAL/IEC.lby', '<Library><Files><File>SHIFT_REPORT.ab</File><File>GENERAL.fun</File></Files></Library>')
        self.write('Logical/Libraries/GENERAL/GENERAL.fun', 'FUNCTION_BLOCK SHIFT_REPORT END_FUNCTION_BLOCK')
        self.write('Logical/Libraries/GENERAL/SHIFT_REPORT.ab', 'binary source reference')
        tree = self.tree()
        self.assertEqual(self.find(tree, 'Logical/Libraries')['kind'], 'libraries')
        library = self.find(tree, 'Logical/Libraries/GENERAL')
        self.assertEqual(library['kind'], 'library')
        self.assertEqual(library['description'], 'Iyyappan V')
        self.assertEqual([child['name'] for child in library['children'][:2]], ['SHIFT_REPORT.ab', 'GENERAL.fun'])

    def test_unlisted_objects_and_invalid_descriptors_survive(self):
        self.write('Logical/Package.pkg', '<Package broken')
        self.write('Logical/Unlisted/run.st', 'source')
        tree = self.tree()
        self.assertEqual(self.find(tree, 'Logical/Unlisted/run.st')['name'], 'run.st')
        self.assertEqual(self.find(tree, 'Logical/Unlisted')['description'], '')

    def test_references_cannot_add_files_outside_scope(self):
        package = self.write('Logical/Package.pkg', '<Package><Objects><Object Type="Program">Inactive</Object><Object Type="File">../../secret.var</Object></Objects></Package>')
        active = self.write('Logical/Active/run.st', 'source')
        self.write('Logical/Inactive/run.st', 'source')
        tree = build_project_tree(self.root, {'Logical/Package.pkg': package, 'Logical/Active/run.st': active}, {})
        self.assertIsNone(self.find(tree, 'Logical/Inactive'))
        self.assertEqual(tree['file_count'], 2)

    def test_target_canonical_keys_preserve_actual_names(self):
        path = self.write('Physical/Config7/PLC1/IoMap.iom', 'mapping')
        tree = build_project_tree(self.root, {'Physical/<ACTIVE>/PLC1/IoMap.iom': path}, {})
        target = self.find(tree, 'Physical/<ACTIVE>')
        self.assertEqual(target['name'], 'Config7')
        self.assertEqual(target['kind'], 'configuration')
        self.assertEqual(self.find(tree, 'Physical/<ACTIVE>/PLC1/IoMap.iom')['relative_path'], 'Physical/Config7/PLC1/IoMap.iom')

    def test_unchanged_library_text_is_openable_and_lazy(self):
        self.write('Logical/Libraries/GENERAL/SHIFT_REPORT.st', 'FUNCTION_BLOCK SHIFT_REPORT\nEND_FUNCTION_BLOCK')
        detail = self.root / 'details'
        with contextlib.redirect_stdout(io.StringIO()):
            result = compare_projects(self.root, self.root, detail_dir=detail)
        entry = next(item for item in result['same_project_files'] if item['path'].endswith('SHIFT_REPORT.st'))
        self.assertEqual(entry['category'], 'config')
        self.assertEqual(entry['status'], 'unchanged')
        self.assertTrue(entry['source_view_available'])
        self.assertNotIn('base_source', entry)
        loaded = json.loads((detail / (entry['project_detail_id'] + '.json')).read_text())
        self.assertIn('FUNCTION_BLOCK', loaded['base_source'])
        self.assertTrue(loaded['source_rows'])
        self.assertEqual(result['summary']['unchanged'], 1)
        self.assertEqual(result['knowledge']['base']['project_tree']['file_count'], 1)
        from backend.core.compare_exports import export_data
        exported = export_data(result)
        self.assertEqual(exported['projectTrees']['base']['file_count'], 1)
        self.assertIsNotNone(self.find(exported['projectTrees']['developed'], entry['path']))

    def test_descriptor_references_match_case_without_renaming_files(self):
        self.write('Logical/Global.var', 'VAR END_VAR')
        self.write('Logical/Package.pkg', '<Package><Objects><Object Type="File" Description="Shared variables">GLOBAL.VAR</Object></Objects></Package>')
        node = self.find(self.tree(), 'Logical/Global.var')
        self.assertEqual(node['name'], 'Global.var')
        self.assertEqual(node['description'], 'Shared variables')

    def test_binary_files_are_not_presented_as_text(self):
        path = self.write('Logical/Libraries/Foo/binary.lby', '')
        path.write_bytes(b'\x00\x01\x02')
        with contextlib.redirect_stdout(io.StringIO()):
            result = compare_projects(self.root, self.root)
        self.assertFalse(result['same_project_files'][0]['source_view_available'])


if __name__ == '__main__':
    unittest.main()
