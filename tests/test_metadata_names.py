import copy
import unittest

from python_engine.metadata_names import resolve_name_collisions


def candidate(source, tag, alias=None):
    return {
        'plc_parameter': source,
        'plc_tag': tag,
        'parameter': alias if alias is not None else source,
        'mapping_source': 'master' if alias is not None else 'PLC',
        'source_file': 'mms_nw_rCyclic.st',
        'line_number': 498,
    }


class MetadataNameTests(unittest.TestCase):
    def test_wrong_alias_cannot_replace_different_parameter(self):
        candidates = [
            candidate('Delivery Stoppage Time Minute', 'SHIFT[30]', 'Sliver Monitor Stops'),
            candidate('Sliver Monitor Stops', 'SHIFT[32]'),
        ]
        original = copy.deepcopy(candidates)
        rows, warnings = resolve_name_collisions(candidates)
        self.assertEqual([r['parameter'] for r in rows],
                         ['Delivery Stoppage Time Minute', 'Sliver Monitor Stops'])
        self.assertEqual([r['plc_tag'] for r in rows], ['SHIFT[30]', 'SHIFT[32]'])
        self.assertEqual(candidates, original)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]['rejectedName'], 'Sliver Monitor Stops')
        self.assertEqual(warnings[0]['conflictingTags'], ['SHIFT[32]'])
        self.assertEqual(warnings[0]['lineNumber'], 498)

    def test_actual_repeated_plc_captions_remain_visible(self):
        candidates = [candidate('Length', 'hmi_current_length'),
                      candidate('Length', 'Thick_Place_LENGTH')]
        rows, warnings = resolve_name_collisions(candidates)
        self.assertEqual(rows, candidates)
        self.assertEqual(warnings, [])

    def test_distinct_legitimate_aliases_are_preserved(self):
        candidates = [candidate('Previous_Shift_Web_Guide_stops', 'SHIFT[27]', 'Web guide Stoppage'),
                      candidate('Previous_Shift_Coilerstops', 'SHIFT[28]', 'Coiler Stoppage')]
        rows, warnings = resolve_name_collisions(candidates)
        self.assertEqual(rows, candidates)
        self.assertEqual(warnings, [])

    def test_reverted_alias_collision_is_checked_again(self):
        candidates = [candidate('Alpha', 'a', 'Beta'),
                      candidate('Beta', 'b'),
                      candidate('Gamma', 'c', 'Alpha')]
        rows, warnings = resolve_name_collisions(candidates)
        self.assertEqual([r['parameter'] for r in rows], ['Alpha', 'Beta', 'Gamma'])
        self.assertEqual(len(warnings), 2)

    def test_punctuation_and_case_do_not_hide_a_collision(self):
        candidates = [candidate('Delivery minutes', 'a', 'sliver_monitor-stops'),
                      candidate('Sliver Monitor Stops', 'b')]
        rows, warnings = resolve_name_collisions(candidates)
        self.assertEqual(rows[0]['parameter'], 'Delivery minutes')
        self.assertEqual(len(warnings), 1)

    def test_groups_are_resolved_independently(self):
        first, warnings = resolve_name_collisions([candidate('Delivery minutes', 'a', 'Stops')])
        second, other_warnings = resolve_name_collisions([candidate('Stops', 'b')])
        self.assertEqual(first[0]['parameter'], 'Stops')
        self.assertEqual(second[0]['parameter'], 'Stops')
        self.assertEqual(warnings + other_warnings, [])


if __name__ == '__main__':
    unittest.main()
