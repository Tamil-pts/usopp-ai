"""Shared dropdown mappings must round-trip without losing target differences."""
import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

from openpyxl import load_workbook
from tests.test_source_parsing import ENGINE


SHEET2_HEADERS = ['TAG_CODE', 'PLCVAL', 'SHOWNVAL', 'MACHINE VARIANT', 'IS_ALARM']
SYMBOLS = ['Sheet2TestEnergy', 'Sheet2TestHealth', 'Sheet2TestReason']


def write_project(root, targets):
    task = root / 'Logical' / 'SpinConnect' / 'mms_nw_r'
    task.mkdir(parents=True)
    (task / 'mms_nw_r.var').write_text('VAR\nnw_i : UINT;\n' + '\n'.join(
        f'{symbol} : {datatype};' for symbol, datatype in zip(SYMBOLS, ['BOOL', 'BOOL', 'USINT'])
    ) + '\nEND_VAR', encoding='utf-8')
    copies = '\n'.join(
        f'memcpy(ADR(nw_snd_buffer[nw_i]),ADR({symbol}),1);(*{symbol}*)\nnw_i := nw_i + 1;'
        for symbol in SYMBOLS
    )
    (task / 'Cyclic.st').write_text('''CASE nw_group_code OF
20:(*Default screen*)
nw_snd_buffer[2] := 0;
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 3;
nw_i := 5;
''' + copies + '''
nw_snd_buffer_length := ((nw_snd_buffer[3] * 256) + nw_snd_buffer[4] + 5);
nw_snd_response := TRUE;
END_CASE
''', encoding='utf-8')
    for target, labels_by_symbol in targets.items():
        pages = root / 'Logical' / target / 'Pages'
        groups = pages.parent / 'TextGroups'
        pages.mkdir(parents=True)
        groups.mkdir()
        for symbol, labels in labels_by_symbol.items():
            texts = ''.join(f'<Text ID="{value}" Value="{escape(label)}"/>' for value, label in labels.items())
            indices = ''.join(f'<Index ID="{value}" Value="{value}"/>' for value in labels)
            group = f'<TextGroup><TextLayer LanguageId="en-US">{texts}</TextLayer><IndexMap>{indices}</IndexMap></TextGroup>'
            embedded = symbol == SYMBOLS[2]
            if not embedded:
                (groups / f'{symbol}.txtgrp').write_text(group.replace('<TextGroup>', f'<TextGroup Name="{symbol}">', 1), encoding='utf-8')
            reference = 'Source[embedded].TextGroup' if embedded else f'Source[local].TextGroup[{symbol}]'
            (pages / f'{symbol}.page').write_text(f'''<Page>
<Controls><Control Name="Select_{symbol}" ClassId="0x00001018">
<Property Name="IndexDatapoint" Value="Source[global].Variable[Local.{symbol}]"/>
<Property Name="TextGroup" Value="{reference}"/>
</Control></Controls>{group if embedded else ''}</Page>''', encoding='utf-8')


class Sheet2VariantTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        # openpyxl's eager workbook reader can retain cyclic objects until GC.
        # Release them before TemporaryDirectory removes files on Windows.
        self.addCleanup(gc.collect)
        self.root = Path(self.directory.name)
        for name, value in {
            'KNOWLEDGE_MASTER_FILE': self.root / 'no-parameter-mappings.json',
            'KNOWLEDGE_MASTER_DROPDOWN_FILE': self.root / 'no-dropdown-mappings.json',
            'BOOL_METADATA_MODE': 'BOOL',
            'ACTIVE_MACHINE_DEPARTMENT': 'All',
        }.items():
            self.enterContext(patch.object(ENGINE, name, value))

    def generate(self, targets):
        write_project(self.root, targets)
        ENGINE.initialize_project_context(self.root)
        output = self.root / 'generated.xlsx'
        data = ENGINE.generate_metadata_workbook(output)
        return output, data

    def test_single_target_round_trip_keeps_schema_and_uses_both(self):
        labels = {SYMBOLS[0]: {0: 'Disabled', 1: 'Enabled'},
                  SYMBOLS[1]: {0: 'Disabled', 1: 'Enabled'},
                  SYMBOLS[2]: {0: 'Unassigned', 1: 'Electrical Maintenance'}}
        output, data = self.generate({'C70_7': labels})
        self.assertEqual(6, data['sheet2Rows'])
        self.assertEqual({'BOTH'}, {row['MACHINE VARIANT'] for row in data['sheet2Records']})
        workbook = load_workbook(output, read_only=True, data_only=True)
        try:
            rows = list(workbook['Sheet2'].values)
            self.assertEqual(SHEET2_HEADERS, list(rows[0]))
            self.assertEqual([list(row.values()) for row in data['sheet2Records']], [list(row) for row in rows[1:]])
            self.assertEqual(4, workbook.worksheets[0].max_row)
        finally:
            workbook.close()
        report = ENGINE.run_engine_json(self.root, metadata_file=output, output_excel_path=self.root / 'report.xlsx')
        controls = report['dropdownValidation']['controls']
        self.assertEqual(3, len(controls))
        self.assertTrue(all(row['status'] == 'Matching' for row in controls), controls)
        self.assertEqual({'C70_7'}, {row['family'] for row in controls})

    def test_common_values_collapse_but_different_target_labels_remain(self):
        output, data = self.generate({
            'C70_7': {SYMBOLS[0]: {0: 'Disabled', 1: 'Enabled'}},
            'T30': {SYMBOLS[0]: {0: 'Disabled', 1: 'Connected'}},
        })
        rows = data['sheet2Records']
        self.assertEqual(3, len(rows))
        self.assertEqual([('0', 'Disabled', 'BOTH'), ('1', 'Enabled', 'C70_7'), ('1', 'Connected', 'T30')],
                         [(r['PLCVAL'], r['SHOWNVAL'], r['MACHINE VARIANT']) for r in rows])
        report = ENGINE.run_engine_json(self.root, metadata_file=output, output_excel_path=self.root / 'report.xlsx')
        controls = report['dropdownValidation']['controls']
        self.assertEqual(2, len(controls))
        self.assertTrue(all(row['status'] == 'Matching' for row in controls), controls)
        self.assertEqual({'C70_7', 'T30'}, {row['family'] for row in controls})

    def test_identical_mappings_across_targets_are_written_once(self):
        labels = {SYMBOLS[0]: {0: 'Disabled', 1: 'Enabled'}}
        _, data = self.generate({'C70_7': labels, 'T30': labels})
        self.assertEqual(2, data['sheet2Rows'])
        self.assertEqual({'BOTH'}, {r['MACHINE VARIANT'] for r in data['sheet2Records']})

    def test_value_absent_from_one_target_is_not_promoted_to_both(self):
        _, data = self.generate({
            'C70_7': {SYMBOLS[0]: {0: 'Disabled', 1: 'Enabled'}},
            'T30': {SYMBOLS[0]: {0: 'Disabled'}},
        })
        self.assertEqual([('0', 'BOTH'), ('1', 'C70_7')],
                         [(r['PLCVAL'], r['MACHINE VARIANT']) for r in data['sheet2Records']])

    def test_punctuation_difference_does_not_merge_distinct_labels(self):
        _, data = self.generate({
            'C70_7': {SYMBOLS[0]: {0: 'Mode A-B'}},
            'T30': {SYMBOLS[0]: {0: 'Mode AB'}},
        })
        self.assertEqual({'C70_7', 'T30'}, {r['MACHINE VARIANT'] for r in data['sheet2Records']})

    def test_target_with_no_dropdowns_does_not_imply_shared_mapping(self):
        write_project(self.root, {'C70_7': {SYMBOLS[0]: {0: 'Disabled'}}, 'T30': {}})
        (self.root / 'Logical' / 'T30' / 'Pages' / 'Overview.page').write_text('<Page><Controls/></Page>')
        ENGINE.initialize_project_context(self.root)
        data = ENGINE.generate_metadata_workbook(self.root / 'generated.xlsx')
        self.assertEqual(['C70_7'], [r['MACHINE VARIANT'] for r in data['sheet2Records']])

    def test_same_target_conflict_is_reported_and_not_promoted(self):
        labels = {SYMBOLS[0]: {0: 'Disabled'}}
        write_project(self.root, {'C70_7': labels})
        page = self.root / 'Logical' / 'C70_7' / 'Pages' / f'{SYMBOLS[0]}.page'
        other = page.with_name('other.page')
        other.write_text(page.read_text().replace(f'TextGroup[{SYMBOLS[0]}]', 'TextGroup[Alternative]'))
        groups = page.parent.parent / 'TextGroups'
        (groups / 'Alternative.txtgrp').write_text(
            (groups / f'{SYMBOLS[0]}.txtgrp').read_text().replace(SYMBOLS[0], 'Alternative').replace('Disabled', 'Inactive'))
        ENGINE.initialize_project_context(self.root)
        data = ENGINE.generate_metadata_workbook(self.root / 'generated.xlsx')
        self.assertEqual(1, len(data['metadataMappingWarnings']))
        self.assertEqual(['C70_7'], [r['MACHINE VARIANT'] for r in data['sheet2Records']])

    def test_converted_bool_shared_mapping_is_recognized_on_validation(self):
        write_project(self.root, {'C70_7': {SYMBOLS[0]: {0: 'Disabled', 1: 'Enabled'}}})
        ENGINE.initialize_project_context(self.root)
        ENGINE.BOOL_METADATA_MODE = 'USINT'
        output = self.root / 'generated.xlsx'
        ENGINE.generate_metadata_workbook(output)
        report = ENGINE.run_engine_json(self.root, metadata_file=output, output_excel_path=self.root / 'report.xlsx', bool_metadata_mode='USINT')
        checks = report['dropdownValidation']['boolChecks']
        self.assertEqual(2, len(checks))
        self.assertTrue(all(row['status'] == 'PASS' for row in checks), checks)

    def test_shared_scope_aliases_are_normalized_consistently(self):
        for value in ['', None, 'BOTH', 'both', 'ALL', 'all variants', '*']:
            self.assertEqual('both', ENGINE.sheet2_variant_key(value))
        self.assertEqual('c707', ENGINE.sheet2_variant_key('C70_7'))


if __name__ == '__main__':
    unittest.main()
