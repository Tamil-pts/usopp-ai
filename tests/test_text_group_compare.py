"""Text-group translations and snippets remain separate, complete and comparable."""
import unittest
from python_engine.compare import parse_structured_hmi_diff
from backend.core.compare_exports import _control_blocks

def group(snippets='',texts='<Text ID="10" Value="{name}"/>',indexes='<Index ID="10" Value="2"/>'):
    return f'<TextGroup xmlns="urn:br" Name="Passwords"><TextSnippets>{snippets}</TextSnippets><TextLayer LanguageId="en">{texts}</TextLayer><IndexMap>{indexes}</IndexMap></TextGroup>'

def snippet(kind='0x00002002',datapoint='Local.name',extra=''):
    return f'<TextSnippet Name="name" ClassId="{kind}"><Property Name="Datapoint" Value="{datapoint}"/><Property Name="StyleClass" Value="default"/>{extra}</TextSnippet>'

class TextGroupCompareTests(unittest.TestCase):
    def compare(self,base,new):return parse_structured_hmi_diff(base,new,'.txtgrp')

    def test_values_use_index_identity_and_keep_all_languages(self):
        text=group().replace('</TextLayer>','</TextLayer><TextLayer LanguageId="vi"><Text ID="10" Value="Tên"/></TextLayer>')
        parsed=self.compare(text,text)
        self.assertEqual(parsed['controls'][0]['name'],'Value 2')
        self.assertEqual(parsed['controls'][0]['base']['index'],'2')
        self.assertEqual(parsed['text_group']['languages'],['en','vi'])
        self.assertEqual(parsed['controls'][0]['new']['properties']['Language: vi'],'Tên')

    def test_empty_indexes_are_preserved(self):
        text=group(indexes='<Index ID="10" Value="2"/><Index ID="11" Value="11"/>')
        parsed=self.compare(text,text)
        blank=next(item for item in parsed['controls'] if item['name']=='Value 11')
        self.assertEqual(blank['status'],'unchanged')
        self.assertNotIn('Language: en',blank['base']['properties'])

    def test_snippet_only_binding_change_is_detected(self):
        parsed=self.compare(group(snippet()),group(snippet(datapoint='Local.new_name')))
        self.assertEqual(parsed['controls'][0]['status'],'unchanged')
        changed=parsed['text_group']['snippets'][0]
        self.assertEqual(changed['status'],'modified')
        self.assertEqual(changed['changes'][0]['prop'],'Datapoint')
        self.assertEqual(parsed['changes'][0]['type'],'text_snippet_modified')

    def test_snippet_type_change_is_detected(self):
        parsed=self.compare(group(snippet()),group(snippet('0x00002001')))
        self.assertEqual(parsed['text_group']['snippets'][0]['new']['class'],'Numeric')
        self.assertEqual(parsed['text_group']['snippets'][0]['changes'][0]['prop'],'Control Type')

    def test_snippet_only_file_and_unknown_properties_are_preserved(self):
        parsed=self.compare('',group(snippet('0x00999999',extra='<Property Name="Custom" Value="Kept"/>'),texts='',indexes=''))
        self.assertTrue(parsed['parsed'])
        self.assertEqual(parsed['text_group']['snippets'][0]['status'],'added')
        self.assertEqual(parsed['text_group']['snippets'][0]['new']['properties']['Custom'],'Kept')
        self.assertEqual(parsed['text_group']['snippets'][0]['new']['class'],'0x00999999')

    def test_removed_snippet_and_export_evidence(self):
        parsed=self.compare(group(snippet()),group())
        self.assertEqual(parsed['text_group']['snippets'][0]['status'],'removed')
        block=next(block for block in _control_blocks(parsed,'screen') if block['title']=='Text snippet: name')
        self.assertTrue(any(row['label']=='Datapoint' and row['base']=='Local.name' for row in block['rows']))

    def test_missing_translation_differs_from_explicit_empty(self):
        parsed=self.compare(group(texts=''),group(texts='<Text ID="10" Value=""/>'))
        self.assertEqual(parsed['controls'][0]['status'],'modified')

    def test_valid_empty_group_is_viewable_but_invalid_xml_is_not(self):
        self.assertTrue(self.compare(group(texts='',indexes=''),group(texts='',indexes=''))['parsed'])
        self.assertFalse(self.compare('broken','broken')['parsed'])

if __name__=='__main__':unittest.main()
