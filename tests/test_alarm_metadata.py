"""Alarm metadata regression checks for shared AS 2.7 alarm groups."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_source_parsing import ENGINE


class AlarmMetadataTests(unittest.TestCase):
    def test_explicit_bit_set_uses_shared_captions_and_reports_shared_bit(self):
        from tests.test_packet_response_controls import FINALIZE
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / 'Logical' / 'SpinConnect' / 'mms_nw_r'
            task.mkdir(parents=True)
            (root / 'Logical' / 'C70' / 'Pages').mkdir(parents=True)
            (root / 'Logical' / 'C70' / 'AlarmGroups').mkdir()
            (task / 'mms_nw_r.var').write_text('''VAR
nw_i : UINT;
MBO_ALARM : ARRAY[0..50] OF BOOL;
Temp_nw_snd_buffer : ARRAY[0..49] OF USINT;
END_VAR''', encoding='utf-8')
            assignments = []
            for index in range(22):
                position = index if index < 14 else index - 1
                byte, bit = 1 + position // 8, position % 8
                assignments.append(f'''IF (MBO_ALARM[{index}] = 1) THEN
Temp_nw_snd_buffer[{byte}] := BIT_SET(Temp_nw_snd_buffer[{byte}],{bit});
END_IF''')
            (task / 'mms_nw_r.st').write_text('\n'.join(assignments) + '''
CASE nw_group_code OF
30:(*Fault History*)
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 3;
nw_i := 5;
memcpy(ADR(nw_snd_buffer[nw_i]),ADR(Temp_nw_snd_buffer[1]),3);
nw_i := nw_i + 3;
''' + FINALIZE + 'END_CASE', encoding='utf-8')
            shared = root / 'Logical' / 'VCShared' / 'AlarmGroups'
            shared.mkdir(parents=True)
            texts = ''.join(f'<Text ID="{100 + index}" Value="Alarm caption {index}"/>' for index in reversed(range(22)))
            indices = ''.join(f'<Index ID="{100 + index}" Value="{index}"/>' for index in reversed(range(22)))
            (shared / 'MBO_Alarm.algrp').write_text(f'''<AlarmGroup xmlns="http://br-automation.co.at/AS/VC/Project">
<Property Name="AlarmImage" Value="Source[global].Variable[Local.MBO_ALARM]"/>
<TextGroup><TextLayer LanguageId="en-US">{texts}</TextLayer><IndexMap>{indices}</IndexMap></TextGroup>
</AlarmGroup>''', encoding='utf-8')
            ENGINE.initialize_project_context(root)
            bits = ENGINE.extract_group30_alarm_bits(include_buffer=True)
            self.assertEqual(22, len(bits))
            self.assertIn(('Temp_nw_snd_buffer', 2, 5, 'Alarm caption 14'), [row[:4] for row in bits])
            result = ENGINE.generate_metadata_workbook(root / 'metadata.xlsx')
            collisions = [issue for issue in result['alarmWarnings'] if issue['validation_type'] == 'Alarm Bit Collision']
            self.assertEqual(1, len(collisions))
            self.assertIn('MBO_ALARM[13]', collisions[0]['actual'])
            self.assertIn('MBO_ALARM[14]', collisions[0]['actual'])
            self.assertTrue(collisions[0]['line_number'])
            self.assertFalse(any(issue['validation_type'] == 'Alarm Packing Sequence' for issue in result['alarmWarnings']))
            tags = [row['tag_code'] for row in result['records'] if row['group_code'] == 30]
            workbook = load_workbook(root / 'metadata.xlsx', read_only=True, data_only=True)
            try:
                alarms = [row for row in list(workbook['Sheet2'].values)[1:] if row[4] == 'YES']
                self.assertEqual(24, len(alarms))
                self.assertEqual(24, len({row[:2] for row in alarms}))
                shared_caption = next(row[2] for row in alarms if row[:2] == (tags[1], 5))
                self.assertIn('Alarm caption 13', shared_caption)
                self.assertIn('Alarm caption 14', shared_caption)
                self.assertEqual(['NA1', 'NA2', 'NA3'], [row[2] for row in alarms if row[2].startswith('NA')])
                self.assertTrue(all(row['datatype'] == 'BYTE' for row in result['records'] if row['group_code'] == 30))
            finally:
                workbook.close()

    def test_direct_assignments_keep_buffers_offsets_and_positive_branches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'mms_nw_r.src'
            source.write_text('''IF Connected THEN
IF (MainAlarm[4] = TRUE) THEN
Temp_nw_snd_buffer[3] := BIT_SET(Temp_nw_snd_buffer[3],7);
ELSE
Temp_nw_snd_buffer[3] := BIT_SET(Temp_nw_snd_buffer[3],6);
END_IF
IF NOT MainAlarm[5] THEN
Temp_nw_snd_buffer[3] := BIT_SET(Temp_nw_snd_buffer[3],5);
END_IF
(* IF MainAlarm[6] THEN
Temp_nw_snd_buffer[3] := BIT_SET(Temp_nw_snd_buffer[3],4);
END_IF *)
IF MainAlarm[8] = 0 THEN
Temp_nw_snd_buffer[3] := BIT_SET(Temp_nw_snd_buffer[3],3);
END_IF
IF MainAlarm[7] THEN
Temp_nw_snd_buffer[3] := BIT_SET(Temp_nw_snd_buffer1[3],2);
END_IF
IF CreelAlarm[12] <> FALSE THEN
Temp_nw_snd_buffer1[9] := BIT_SET(Temp_nw_snd_buffer1[9],1);
END_IF
END_IF''', encoding='utf-8')
            groups = root / 'Logical' / 'VCShared' / 'AlarmGroups'
            groups.mkdir(parents=True)
            for name, array, offset, index, caption in [('Main', 'MainAlarm', 2, 2, 'Main caption'), ('Creel', 'CreelAlarm', 10, 2, 'Creel caption'), ('Wrong', 'UnknownAlarm', 0, 4, 'Must not guess')]:
                (groups / f'{name}.algrp').write_text(f'''<AlarmGroup>
<Property Name="AlarmImage" Value="Source[global].Variable[Local.{array}]"/>
<Property Name="ImageOffset" Value="{offset}"/>
<TextGroup><TextLayer LanguageId="en"><Text ID="1" Value="{caption}"/></TextLayer>
<IndexMap><Index ID="1" Value="{index}"/></IndexMap></TextGroup></AlarmGroup>''', encoding='utf-8')
            with patch.multiple(ENGINE, ROOT=root, LOGICAL_ROOT=root / 'Logical', HMI_PAGE_ROOTS=[], PLC_PACKET_FILE=source):
                packings = ENGINE.extract_alarm_packings()
                self.assertEqual([2, 1], [len(item['entries']) for item in packings])
                bits = ENGINE.extract_group30_alarm_bits(include_buffer=True)
                self.assertEqual({('Temp_nw_snd_buffer', 3, 7, 'Main caption'), ('Temp_nw_snd_buffer1', 9, 1, 'Creel caption')}, {row[:4] for row in bits})
                issues = ENGINE.validate_alarm_packings(packings, [])
                self.assertIn('Alarm Buffer Mismatch', {issue.validation_type for issue in issues})
                self.assertIn('Alarm Packing Ambiguous', {issue.validation_type for issue in issues})

    def test_generated_excel_uses_active_hmi_shared_groups_and_keeps_byte(self):
        from tests.test_alarm_packing import write_alarm_project
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            write_alarm_project(root)
            for screen in ('C70','T30'):
                (root/'Logical'/screen/'Pages').mkdir(parents=True)
                (root/'Logical'/screen/'AlarmGroups').mkdir()
                cpu=root/'Physical'/('Config_'+screen)/'PLC1'
                cpu.mkdir(parents=True)
                (cpu/'Cpu.sw').write_text(f'<SwConfiguration><VcDataObject Name="{screen}"/></SwConfiguration>',encoding='utf-8')
            (root/'LastUser.set').write_text('<ProjectSettings><ConfigurationManager ActiveConfigurationName="Config_C70"/></ProjectSettings>',encoding='utf-8')
            (root/'Logical'/'T30'/'AlarmGroups'/'Inactive.algrp').write_text('<AlarmGroup/>',encoding='utf-8')
            ENGINE.initialize_project_context(root)
            self.assertEqual('C70',ENGINE.HMI_TARGET_NAME)
            self.assertEqual(3,len(ENGINE.discover_alarm_group_files()))
            output=root/'metadata.xlsx'
            result=ENGINE.generate_metadata_workbook(output)
            self.assertTrue(all(row['datatype']=='BYTE' for row in result['records'] if row['group_code']==30))
            wb=load_workbook(output,read_only=True,data_only=True)
            try:
                rows=list(wb.worksheets[0].values);headers={value:i for i,value in enumerate(rows[0])}
                self.assertTrue(all(row[headers['TAG_DATA_TYPE']]=='BYTE' for row in rows[1:] if row[headers['GROUP_CODE']]==30))
                captions={row[2] for row in wb['Sheet2'].values if len(row)>4 and row[4]=='YES'}
                self.assertTrue({'Main final alarm','Creel first alarm','Doff final alarm'}<=captions)
            finally:
                wb.close()

    def test_empty_active_alarm_folder_falls_back_to_multiple_shared_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logical = root / 'Logical'
            active = logical / 'C70'
            (active / 'AlarmGroups').mkdir(parents=True)
            shared = logical / 'VCShared' / 'AlarmGroups'
            shared.mkdir(parents=True)
            inactive = logical / 'T30' / 'AlarmGroups'
            inactive.mkdir(parents=True)
            source = root / 'mms_nw_r.src'
            source.write_text('byte_len := 1;\nbit_pos := 0;\nFOR alarm_len := 0 TO 23 BY 1 DO\nIF (Alarms[alarm_len] = 1) THEN\nTemp_nw_snd_buffer[byte_len] := BIT_SET(Temp_nw_snd_buffer[byte_len],bit_pos);\nEND_IF\nEND_FOR', encoding='utf-8')
            for folder, name, index in [(shared,'Main',0),(shared,'Creel',8),(shared,'Doff',16),(shared,'SystemAlarms',3),(inactive,'Inactive',1)]:
                (folder / (name + '.algrp')).write_text(f'<AlarmGroup><Property Name="AlarmImage" Value="Source[global].Variable[Local.Alarms]"/><TextGroup><TextLayer LanguageId="en"><Text ID="1" Value="{name} alarm"/></TextLayer><IndexMap><Index ID="1" Value="{index}"/></IndexMap></TextGroup></AlarmGroup>',encoding='utf-8')
            (shared/'AlarmSystem.alcfg').write_text('not an alarm group')
            with patch.multiple(ENGINE, ROOT=root, LOGICAL_ROOT=logical, HMI_PAGE_ROOTS=[active], PLC_PACKET_FILE=source):
                self.assertEqual({'Main.algrp','Creel.algrp','Doff.algrp'}, {p.name for p in ENGINE.discover_alarm_group_files()})
                bits=ENGINE.extract_group30_alarm_bits()
            self.assertEqual({(1,0,'Main alarm'),(2,0,'Creel alarm'),(3,0,'Doff alarm')},{row[:3] for row in bits})

    def test_multiple_shared_groups_keep_configured_indices_and_exclude_system_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logical = root / "Logical"
            groups = logical / "VCShared" / "AlarmGroups"
            groups.mkdir(parents=True)
            source = root / "mms_nw_r.src"
            source.write_text("""
                byte_len := 1;
                FOR alarm_len := 0 TO 23 BY 1 DO
                    IF (PacketAlarms[alarm_len] = 1) THEN
                        Temp_nw_snd_buffer[byte_len] := BIT_SET(Temp_nw_snd_buffer[byte_len], bit_pos);
                    END_IF
                END_FOR
            """, encoding="utf-8")

            def write_group(path, label, index, offset=0):
                path.write_text(f"""<AlarmGroup xmlns="http://br-automation.co.at/AS/VC/Project">
                <Property Name="AlarmImage" Value="Source[global].Variable[Local.GLOBAL.LegacyAlarms]"/>
                <Property Name="ImageOffset" Value="{offset}"/>
                <TextGroup>
                  <TextLayer LanguageId="en"><Text ID="55" Value="{label}"/><Text ID="56" Value="Group heading"/></TextLayer>
                  <IndexMap><Index ID="55" Value="{index}"/><Index ID="56" Value="Group"/></IndexMap>
                </TextGroup></AlarmGroup>""", encoding="utf-8")

            write_group(groups / "Machine.algrp", "Emergency stop", 7)
            write_group(groups / "Drive.ALGRP", "Drive trip", 1, 8)
            write_group(groups / "Sensor.algrp", "Sensor fault", 2, 16)
            write_group(groups / "SystemAlarms.algrp", "SYSTEM MUST BE EXCLUDED", 0)
            write_group(groups / "AlarmSystem.alcfg", "CONFIG MUST BE EXCLUDED", 0)
            generated = logical / "Temp" / "AlarmGroups"
            generated.mkdir(parents=True)
            write_group(generated / "Stale.algrp", "STALE MUST BE EXCLUDED", 0)
            with patch.multiple(ENGINE, ROOT=root, LOGICAL_ROOT=logical, PLC_PACKET_FILE=source), patch.object(ENGINE, "extract_dropdown_rows", return_value={}):
                self.assertEqual(3, len(ENGINE.discover_alarm_group_files()))
                bits = ENGINE.extract_group30_alarm_bits()
                self.assertEqual([(1, 7, "Emergency stop"), (2, 1, "Drive trip"), (3, 2, "Sensor fault")],
                                 [row[:3] for row in bits])
                descriptions = ENGINE.extract_alarm_descriptions()
                self.assertFalse(any("EXCLUDED" in row[1] for row in descriptions))
                sheet = ENGINE._build_generated_sheet2([], alarm_byte_tags={1:50, 2:51, 3:52})
            rows = sheet[1:]
            self.assertEqual(24, len(rows))
            self.assertEqual("Emergency stop", next(row[2] for row in rows if row[:2] == [50,7]))
            self.assertEqual("Drive trip", next(row[2] for row in rows if row[:2] == [51,1]))
            self.assertEqual("Sensor fault", next(row[2] for row in rows if row[:2] == [52,2]))
            self.assertTrue(all(row[4] == "YES" for row in rows))
            self.assertEqual([f"NA{i}" for i in range(1,22)], [row[2] for row in rows if row[2].startswith("NA")])
            self.assertEqual(sorted((row[0], row[1]) for row in rows), [(row[0], row[1]) for row in rows])

    def test_real_as27_shared_file_is_not_rejected_for_different_alarm_image_name(self):
        project = Path(__file__).resolve().parents[2] / "Project in AS2.7" / "LD_22120.pgp"
        if not project.exists():
            self.skipTest("Local AS 2.7 reference project is unavailable")
        source = project / "pgm" / "TRIAL_01" / "CPU" / "mms_nw_r.src"
        with patch.multiple(ENGINE, ROOT=project, LOGICAL_ROOT=project / "Logical", PLC_PACKET_FILE=source):
            self.assertEqual(("Drawframe_Alarms",159,1), ENGINE.extract_group30_alarm_transport())
            bits = ENGINE.extract_group30_alarm_bits()
        self.assertEqual(28, len(bits))
        self.assertEqual((1,0,"EMERGENCY STOP"), bits[0][:3])
        self.assertEqual((1,1,"INCH PUSH BUTTON STRUCK UP"), bits[1][:3])
        self.assertTrue(all("LD2_Alarm.algrp" in row[3] for row in bits))


if __name__ == "__main__":
    unittest.main()
