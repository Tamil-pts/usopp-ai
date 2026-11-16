import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from python_engine.compare import hmi_screen_layout, parse_structured_hmi_diff, compare_projects
from backend.core.compare_screen_preview import preview_png


class HmiBitmapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'Logical/C70'
        self.write(self.target / 'VCObject.vc', '<VCObject/>')
        self.path = self.target / 'TouchPads/Alpha.tpr'
        self.text = '<TouchPad Name="Alpha"><Property Name="Width" Value="40"/><Property Name="Height" Value="20"/><Property Name="NumLevel" Value="2"/><Property Name="BitmapSource" Value="MultipleBitmaps"/><Property Name="BitmapGroup" Value="Source[local].BitmapGroup[Alpha]"/><Property Name="BitmapOffset" Value="12"/><Property Name="BitmapIndex" Value="None"/><Property Name="PressedBitmapSource" Value="SingleBitmap"/><Property Name="PressedBitmap" Value="Source[local].Bitmap[Pressed]"/><Controls><Control Name="Grid" ClassId="0x00000500"><Property Name="Width" Value="40"/><Property Name="Height" Value="20"/></Control></Controls></TouchPad>'
        self.write(self.path, self.text)
        self.write(self.target / 'BitmapGroups/Alpha.bmgrp', '<BitmapGroup><BitmapLayer LanguageId="neutral"><BitmapRef ID="417" Value="Source[local].Bitmap[Released]"/><BitmapRef ID="423" Value="Source[local].Bitmap[Other]"/></BitmapLayer><IndexMap><Index ID="417" Value="12"/><Index ID="423" Value="13"/></IndexMap></BitmapGroup>')
        self.image(self.target, 'Released', '#ff0000')
        self.image(self.target, 'Other', '#00ff00')
        self.image(self.target, 'Pressed', '#0000ff')

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def image(self, home, name, color):
        self.write(home / f'Bitmaps/{name}.bminfo', f'<Bitmap Name="{name}"><Property Name="File" Value="{name}.bmp"/></Bitmap>')
        Image.new('RGB', (40, 20), color).save(home / f'Bitmaps/{name}.bmp')

    def layout(self, text=None):
        return hmi_screen_layout(text or self.text, self.path)

    def test_offset_resolves_index_map_id_and_bitmap_file(self):
        layout = self.layout()
        variants = layout['bitmaps']['released']['variants']
        self.assertEqual([(item['index'], item['name']) for item in variants], [(12, 'Released'), (13, 'Other')])
        self.assertEqual(layout['properties']['ResolvedBitmapName'], 'Released')
        self.assertEqual(layout['properties']['ResolvedBitmapFile'], 'Released.bmp')
        self.assertEqual(layout['properties']['ResolvedBitmapIndex'], '12')
        self.assertEqual(layout['properties']['ResolvedPressedBitmapName'], 'Pressed')
        self.assertEqual(len(layout['bitmap_assets']), 3)
        json.dumps(layout)

    def test_global_group_local_bitmap_uses_shared_owner(self):
        shared = self.root / 'Logical/VCShared'
        self.image(shared, 'Shared', '#00ffff')
        self.write(shared / 'BitmapGroups/Alpha.bmgrp', '<BitmapGroup><BitmapLayer LanguageId="neutral"><BitmapRef ID="9" Value="Source[local].Bitmap[Shared]"/></BitmapLayer><IndexMap><Index ID="9" Value="12"/></IndexMap></BitmapGroup>')
        layout = self.layout(self.text.replace('Source[local].BitmapGroup', 'Source[global].BitmapGroup'))
        self.assertEqual(layout['properties']['ResolvedBitmapName'], 'Shared')
        self.assertEqual(layout['bitmaps']['released']['variants'][0]['status'], 'resolved')

    def test_control_single_bitmap_and_missing_file_keep_reference(self):
        text = '<Page><Controls><Control Name="Button" ClassId="0x00001002"><Property Name="BitmapSource" Value="SingleBitmap"/><Property Name="Bitmap" Value="Source[local].Bitmap[Released]"/><Property Name="Width" Value="40"/><Property Name="Height" Value="20"/></Control></Controls></Page>'
        control = self.layout(text)['layers'][0]['controls'][0]
        self.assertEqual(control['effective_properties']['ResolvedBitmapName'], 'Released')
        (self.target / 'Bitmaps/Released.bmp').unlink()
        layout = self.layout(text)
        variant = layout['layers'][0]['controls'][0]['bitmaps']['released']['variants'][0]
        self.assertEqual(variant['status'], 'unresolved')
        self.assertEqual(variant['name'], 'Released')
        self.assertEqual(variant['file'], 'Released.bmp')
        self.assertIn('unavailable', variant['message'])

    def test_preview_renders_image_and_keeps_touch_grid_transparent(self):
        layout = self.layout()
        self.assertEqual(layout['layers'][0]['controls'][0]['class'], 'TouchPadGrid')
        png = preview_png(layout)
        image = Image.open(io.BytesIO(png)).convert('RGB')
        self.assertEqual(image.getpixel((20, 10)), (255, 0, 0))

    def test_dynamic_index_is_explicit_and_none_source_disabled(self):
        layout = self.layout(self.text.replace('Name="BitmapIndex" Value="None"', 'Name="BitmapIndex" Value="Source[global].Variable[Index]"'))
        self.assertTrue(layout['bitmaps']['released']['dynamic'])
        self.assertIn('Live index', layout['properties']['ResolvedBitmapIndexNote'])
        layout = self.layout(self.text.replace('Value="MultipleBitmaps"', 'Value="None"'))
        self.assertNotIn('released', layout['bitmaps'])

    def test_other_level_image_changes_are_detected(self):
        base = self.root / 'Base'
        developed = self.root / 'Developed'
        import shutil
        shutil.copytree(self.root / 'Logical', base / 'Logical')
        shutil.copytree(self.root / 'Logical', developed / 'Logical')
        Image.new('RGB', (40, 20), '#ffff00').save(developed / 'Logical/C70/Bitmaps/Other.bmp')
        with contextlib.redirect_stdout(io.StringIO()):
            result = compare_projects(base, developed)
        entry = next(item for item in result['diffs'] if item['path'].endswith('Alpha.tpr'))
        self.assertEqual(entry['status'], 'modified')
        changes = entry['parsed_screen']['changes']
        self.assertTrue(any('SHA256Level1' in change['prop'] for item in changes for change in item.get('changes', [])))

    def test_traversal_is_rejected(self):
        escaped = self.layout(self.text.replace('BitmapGroup[Alpha]', 'BitmapGroup[../../Secret]'))
        self.assertEqual(escaped['bitmaps']['released']['variants'][0]['status'], 'unresolved')
        self.write(self.target / 'Bitmaps/Released.bminfo', '<Bitmap><Property Name="File" Value="../../outside.png"/></Bitmap>')
        layout = self.layout()
        self.assertEqual(layout['bitmaps']['released']['variants'][0]['status'], 'unresolved')
        self.assertIn('leaves', layout['bitmaps']['released']['variants'][0]['message'])

    def test_local_missing_does_not_use_other_visualization(self):
        other = self.root / 'Logical/T30'
        self.image(other, 'Released', '#ffff00')
        (self.target / 'Bitmaps/Released.bmp').unlink()
        self.assertEqual(self.layout()['bitmaps']['released']['variants'][0]['status'], 'unresolved')

    def test_shared_run_cache_preserves_assets_and_target_isolation(self):
        from unittest.mock import patch
        from python_engine.hmi_bitmaps import BitmapResolver
        cache = {}
        first = BitmapResolver(self.target, cache)
        record = first.bitmap('Source[local].Bitmap[Released]')
        second = BitmapResolver(self.target, cache)
        with patch.object(Path, 'resolve', side_effect=AssertionError('repeat filesystem resolution')):
            self.assertEqual(record, second.bitmap('Source[local].Bitmap[Released]'))
        self.assertEqual(first.assets, second.assets)
        other = self.root / 'Logical/T30'
        self.image(other, 'Released', '#00ffff')
        third = BitmapResolver(other, cache)
        self.assertNotEqual(record['sha256'], third.bitmap('Source[local].Bitmap[Released]')['sha256'])
        # Cache belongs to one run; a fresh run must observe a changed image.
        self.image(self.target, 'Released', '#ffffff')
        self.assertNotEqual(record['sha256'], BitmapResolver(self.target, {}).bitmap('Source[local].Bitmap[Released]')['sha256'])

    def test_missing_index_and_invalid_image_leave_readable_evidence(self):
        layout = self.layout(self.text.replace('Name="BitmapOffset" Value="12"', 'Name="BitmapOffset" Value="99"'))
        self.assertIn('99', layout['properties']['ResolvedBitmapNote'])
        (self.target / 'Bitmaps/Released.bmp').write_bytes(b'not an image')
        layout = self.layout()
        self.assertEqual(layout['properties']['ResolvedBitmapStatus'], 'unresolved')
        self.assertEqual(layout['properties']['ResolvedBitmapName'], 'Released')


if __name__ == '__main__':
    unittest.main()
