import unittest
from datetime import datetime,timezone
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.core.cpu import configuration
from virtual_plc.tests.test_runtime import project,variable


class CPUServicesTests(unittest.TestCase):
    def test_rtc_pointer_layout_and_set_get_share_virtual_clock(self):
        code='''IF Apply THEN Status := RTC_settime(ADR(Clock)); Apply := FALSE; END_IF;
Status := RTC_gettime(ADR(ReadClock));
memcpy(ADR(YearBytes),ADR(ReadClock.year),2);'''
        model=project(code,[variable('Apply','BOOL',True),variable('Clock','RTCtime_typ',None),
             variable('ReadClock','RTCtime_typ',None),variable('Status','UINT'),
             variable('YearBytes','ARRAY[0..1] OF USINT',[0,0])])
        runtime=VirtualRuntime(model)
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        for name,value in [('year',2026),('month',10),('day',17),('hour',12),('minute',34),('second',50)]:
            runtime.set_value('Clock.'+name,value,return_snapshot=False)
        runtime.command('scan')
        self.assertEqual(2026,runtime.get_value('ReadClock.year'))
        self.assertEqual([234,7],runtime.get_value('YearBytes'))
        self.assertEqual(0,runtime.get_value('Status'))
        for _ in range(100):runtime.command('scan')
        self.assertEqual(51,runtime.get_value('ReadClock.second'))
        self.assertEqual('2026-10-17T12:34:51+00:00',runtime.cpu.summary()['dateTime'])

    def test_network_async_buffer_and_settings_are_virtual(self):
        code='''Getter.enable := TRUE; Getter.pDevice := ADR('IF2');
Getter.pIPAddr := ADR(Address); Getter.Len := 16; Getter();'''
        runtime=VirtualRuntime(project(code,[variable('Getter','CfgGetIPAddr',None),variable('Address','ARRAY[0..15] OF USINT',[0]*16)]))
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        runtime.command('scan');self.assertEqual(65535,runtime.get_value('Getter.status'))
        runtime.command('scan');self.assertEqual(0,runtime.get_value('Getter.status'))
        self.assertEqual('192.0.2.10',bytes(runtime.get_value('Address')).split(b'\0')[0].decode())
        self.assertTrue(runtime.cpu.summary()['virtualOnly'])

    def test_dt_type_and_zeroed_timer(self):
        runtime=VirtualRuntime(project('Reader(enable:=TRUE); Value := Reader.DT1; Timer(IN:=TRUE,PT:=T#10ms);',
            [variable('Reader','DTGetTime',None),variable('Value','DATE_AND_TIME'),variable('Timer','TON','(0)')]))
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        before=int(datetime.now(timezone.utc).timestamp())
        runtime.command('scan')
        self.assertLessEqual(before,runtime.get_value('Value'))
        self.assertLessEqual(runtime.get_value('Value'),int(datetime.now(timezone.utc).timestamp()))

    def test_basic_ip_source_forms_include_trailing_comments_and_loops(self):
        code='''Getter.enable = TRUE
Getter.pDevice = ADR("IF2") // interface
Getter.pIPAddr = ADR(Address)
Getter.Len = 16
Getter FUB CfgGetIPAddr()
LOOP Index = 0 TO 3 DO
Value = Value + 1
EXITIF (Index = 1)
ENDLOOP'''
        runtime=VirtualRuntime(project(code,[variable('Getter','CfgGetIPAddr',None),variable('Address','ARRAY[0..15] OF USINT',[0]*16),variable('Index'),variable('Value')],'ab'))
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        runtime.command('scan');self.assertEqual(2,runtime.get_value('Value'))

    def test_serial_number_uses_source_iomap_and_respects_force(self):
        model=project('A := Serial;', [variable('A'),variable('Serial','UDINT')],
            hardware={'channels':[{'name':'SerialNumber','moduleId':'CPU:DI','direction':'input','variable':'Serial'}]},
            cpuServices={'serialNumbers':{'CPU:DI':123456}})
        runtime=VirtualRuntime(model)
        runtime.command('scan');self.assertEqual(123456,runtime.get_value('A'))
        runtime.set_value('Serial',99,force=True,return_snapshot=False)
        runtime.command('scan');self.assertEqual(99,runtime.get_value('A'))

    def test_invalid_configuration_and_unknown_struct_abi_remain_explicit(self):
        with self.assertRaises(ValueError):configuration({'interfaces':{'IF2':{}}})
        with self.assertRaises(ValueError):configuration({'dateTime':'2089-02-30T00:00:00'})
        runtime=VirtualRuntime(project('P := ADR(Data);',[variable('P','UDINT'),variable('Data','Custom',None)],
            types={'Custom':{'kind':'struct','fields':{'A':'DINT'}}}))
        self.assertFalse(runtime.run_allowed)

    def test_battery_encodings_and_invalid_network_pointer_are_bounded(self):
        runtime=VirtualRuntime(project("Flags := SYS_battery(0); Battery(enable:=TRUE,pDevice:=ADR('LOCAL.BATT2')); Getter(enable:=TRUE,pDevice:=ADR('IF2'),pIPAddr:=1,Len:=16);",
            [variable('Flags','USINT'),variable('Battery','BatteryInfo',None),variable('Getter','CfgGetIPAddr',None)],
            cpuServices={'battery':{'LOCAL.BATT1':1,'LOCAL.BATT2':0}}))
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        runtime.command('scan');runtime.command('scan')
        self.assertEqual('paused',runtime.status)
        self.assertEqual(1,runtime.get_value('Flags'))
        self.assertEqual(0,runtime.get_value('Battery.state'))
        self.assertEqual(29003,runtime.get_value('Getter.status'))


if __name__=='__main__':unittest.main()
