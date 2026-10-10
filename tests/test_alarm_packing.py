import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.test_source_parsing import ENGINE
from tests.test_packet_response_controls import FINALIZE


def packing(array, buffer, low, high, suffix=''):
    return f"""byte_len{suffix} := 1;
bit_pos{suffix} := 0;
FOR alarm_len{suffix} := {low} TO {high} BY 1 DO
IF ({array}[alarm_len{suffix}] = 1) THEN
{buffer}[byte_len{suffix}] := BIT_SET({buffer}[byte_len{suffix}],bit_pos{suffix});
END_IF
bit_pos{suffix} := bit_pos{suffix} + 1;
IF bit_pos{suffix} = 8 THEN
byte_len{suffix} := byte_len{suffix} + 1;
bit_pos{suffix} := 0;
END_IF
END_FOR
"""


def write_alarm_project(root, broken=False):
    task=root/'Logical'/'SpinConnect'/'mms_nw_r'
    task.mkdir(parents=True)
    declarations='''VAR
nw_i : UINT;
LH15_ALARM : ARRAY[0..193] OF BOOL;
LH20_CREEL_ALARM : ARRAY[0..103] OF BOOL;
LH20_DOFF_ALARM_HISTORY : ARRAY[0..68] OF BOOL;
Temp_nw_snd_buffer : ARRAY[0..49] OF BYTE;
Temp_nw_snd_buffer1 : ARRAY[0..49] OF BYTE;
Temp_nw_snd_buffer2 : ARRAY[0..49] OF BYTE;
END_VAR
'''
    (task/'mms_nw_r.var').write_text(declarations,encoding='utf-8')
    source=packing('LH15_ALARM','Temp_nw_snd_buffer',0,193)
    source+=packing('LH20_CREEL_ALARM','Temp_nw_snd_buffer1',48,103,'1')
    source+=packing('LH20_DOFF_ALARM_HISTORY','Temp_nw_snd_buffer2',0,68,'2')
    source+='''CASE nw_group_code OF
30:(*Current Fault History*)
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 41;
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Temp_nw_snd_buffer[1]),25);
nw_i := nw_i + 25;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Temp_nw_snd_buffer1[1]),7);
nw_i := nw_i + 7;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Temp_nw_snd_buffer2[1]),9);
nw_i := nw_i + 9;
'''+FINALIZE+'END_CASE\n'
    if broken:
        source=source.replace('TO 193','TO 200')
        source=source.replace('Temp_nw_snd_buffer2[byte_len2] :=','Temp_nw_snd_buffer1[byte_len2] :=')
        source=source.replace('ADR(Temp_nw_snd_buffer[1]),25','ADR(Temp_nw_snd_buffer[0]),25')
    path=task/'Cyclic.st'
    path.write_text(source,encoding='utf-8')
    groups=root/'Logical'/'VCShared'/'AlarmGroups'
    groups.mkdir(parents=True)
    for name,array,index,description in [('Main','LH15_ALARM',193,'Main final alarm'),('Creel','LH20_CREEL_ALARM',48,'Creel first alarm'),('Doff','LH20_DOFF_ALARM_HISTORY',68,'Doff final alarm')]:
        (groups/f'{name}.algrp').write_text(f'''<AlarmGroup>
<Property Name="AlarmImage" Value="Source[global].Variable[Local.GLOBAL.{array}]"/>
<TextGroup><TextLayer LanguageId="en"><Text ID="1" Value="{description}"/></TextLayer>
<IndexMap><Index ID="1" Value="{index}"/></IndexMap></TextGroup></AlarmGroup>''',encoding='utf-8')
    return path


class AlarmPackingTests(unittest.TestCase):
    def test_three_buffers_inclusive_nonzero_ranges_and_sheet2_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            write_alarm_project(root)
            ENGINE.initialize_project_context(root)
            loops=ENGINE.extract_alarm_packings()
            self.assertEqual([194,56,69],[loop['count'] for loop in loops])
            self.assertEqual([25,7,9],[loop['bytes'] for loop in loops])
            groups,issues,_,_=ENGINE.build_group_results(metadata_compare_enabled=False)
            self.assertEqual('PASS',groups[0].overall_status,issues)
            bits=ENGINE.extract_group30_alarm_bits(include_buffer=True)
            self.assertIn(('Temp_nw_snd_buffer',25,1,'Main final alarm'),[row[:4] for row in bits])
            self.assertIn(('Temp_nw_snd_buffer1',1,0,'Creel first alarm'),[row[:4] for row in bits])
            self.assertIn(('Temp_nw_snd_buffer2',9,4,'Doff final alarm'),[row[:4] for row in bits])
            tags={};tag=0
            for loop in loops:
                for byte in range(1,loop['bytes']+1):
                    tag+=1;tags[(loop['buffer'].casefold(),byte)]=tag
            with patch.object(ENGINE,'extract_dropdown_rows',return_value={}):
                rows=ENGINE._build_generated_sheet2(groups,{},set(),tags)[1:]
            self.assertEqual(41*8,len(rows))
            self.assertIn([26,0,'Creel first alarm','BOTH','YES'],rows)
            self.assertIn([41,4,'Doff final alarm','BOTH','YES'],rows)
            self.assertEqual(325,sum(str(row[2]).startswith('NA') for row in rows))
            self.assertEqual(sorted((row[0],row[1]) for row in rows),[(row[0],row[1]) for row in rows])

    def test_bounds_wrong_buffer_start_and_size_are_actionable_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            write_alarm_project(root,broken=True)
            ENGINE.initialize_project_context(root)
            groups,issues,_,_=ENGINE.build_group_results(metadata_compare_enabled=False)
            types={issue.validation_type for issue in issues}
            self.assertTrue({'Alarm Array Bounds','Alarm Buffer Mismatch','Alarm Copy Start','Alarm Copy Size'}.issubset(types))
            self.assertEqual('FAIL',groups[0].overall_status)
            self.assertTrue(all(issue.line_number and issue.suggested_fix for issue in issues if issue.validation_type.startswith('Alarm ')))

    def test_zero_to_fifty_is_51_bits_and_capacity_is_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            path=write_alarm_project(root)
            path.write_text(packing('LH15_ALARM','Temp_nw_snd_buffer',0,50)+'CASE nw_group_code OF\n30:(*Faults*)\nnw_snd_buffer[3]:=0;\nnw_snd_buffer[4]:=7;\nnw_i:=5;\nmemcpy(ADR(nw_snd_buffer[nw_i]),ADR(Temp_nw_snd_buffer[1]),7);\nnw_i:=nw_i+7;\n'+FINALIZE+'END_CASE',encoding='utf-8')
            var=path.parent/'mms_nw_r.var'
            var.write_text(var.read_text(encoding='utf-8').replace('Temp_nw_snd_buffer : ARRAY[0..49]','Temp_nw_snd_buffer : ARRAY[0..6]'),encoding='utf-8')
            ENGINE.initialize_project_context(root)
            loops=ENGINE.extract_alarm_packings()
            self.assertEqual((51,7),(loops[0]['count'],loops[0]['bytes']))
            _,issues,_,_=ENGINE.build_group_results(metadata_compare_enabled=False)
            self.assertIn('Alarm Buffer Capacity',{issue.validation_type for issue in issues})

    def test_multiple_arrays_do_not_guess_an_unknown_alarm_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            write_alarm_project(root)
            group=root/'Logical'/'VCShared'/'AlarmGroups'/'Creel.algrp'
            group.write_text(group.read_text(encoding='utf-8').replace('Local.GLOBAL.LH20_CREEL_ALARM','Local.GLOBAL.UnmappedAlarm'),encoding='utf-8')
            ENGINE.initialize_project_context(root)
            _,issues,_,_=ENGINE.build_group_results(metadata_compare_enabled=False)
            self.assertIn('Alarm Packing Ambiguous',{issue.validation_type for issue in issues})
            bits=ENGINE.extract_group30_alarm_bits(include_buffer=True)
            self.assertNotIn('Creel first alarm',[row[3] for row in bits])

if __name__=='__main__': unittest.main()
