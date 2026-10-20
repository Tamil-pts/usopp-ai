import struct
import unittest

from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.core.vendor_services import BLOCKS
from virtual_plc.tests.test_runtime import project, variable


def instance(kind, **values):
    inputs, outputs = BLOCKS[kind]
    return {**{k:False if t=='BOOL' else 0 for k,t in {**inputs,**outputs}.items()},'enable':True,**values}


class VendorServicesTests(unittest.TestCase):
    def test_addressed_array_inside_opaque_holder_keeps_full_extent_and_captured_offset(self):
        model = project('''Index := 1;
Pointer := ADR(Holder.Data[Index]);
Index := 4;
memcpy(Pointer,ADR(Value),2);
memcpy(ADR(Holder.Data[Index]),ADR(Value),2);''',
            [variable('Holder','Holder_typ',None),variable('Index','UINT'),
             variable('Pointer','UDINT'),variable('Value','UINT',513)],
            types={'Holder_typ':{'kind':'struct','source':'Logical/Holder.typ',
                                 'fields':{'Opaque':'TON','Data':'ARRAY[0..7] OF USINT'}}})
        runtime = VirtualRuntime(model)
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        runtime.command('scan')
        self.assertEqual('paused',runtime.status,runtime.diagnostics)
        self.assertEqual([0,1,2,0,1,2,0,0],runtime.get_value('Holder.Data'))
        member_regions = [r for r in runtime.vendor.regions if r.get('reference',{}).get('name')=='Main::Holder']
        self.assertEqual(1,len(member_regions))
        self.assertEqual(8,member_regions[0]['size'])
        # Preserve the actual declared boundary: a two-byte write at the final
        # element remains an error instead of silently truncating or padding.
        pointer=runtime.vendor.address({'op':'ref','name':'Holder','path':[
            {'member':'Data'},{'index':{'op':'literal','value':7}}]},'Main',None)
        with self.assertRaises(ValueError):runtime.vendor.write(pointer,b'\1\2')

    def test_opaque_array_prefix_index_is_captured_before_addressable_member(self):
        model = project('''ObjectIndex := 1;
Pointer := ADR(Objects[ObjectIndex].Data[1]);
ObjectIndex := 0;
memcpy(Pointer,ADR(Value),2);''',
            [variable('Objects','ARRAY[0..1] OF Holder_typ',None),variable('ObjectIndex','UINT'),
             variable('Pointer','UDINT'),variable('Value','UINT',513)],
            types={'Holder_typ':{'kind':'struct','source':'Logical/Holder.typ',
                                 'fields':{'Opaque':'TON','Data':'ARRAY[0..3] OF USINT'}}})
        runtime = VirtualRuntime(model)
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        runtime.command('scan')
        self.assertEqual('paused',runtime.status,runtime.diagnostics)
        self.assertEqual([0,0,0,0],runtime.get_value('Objects[0].Data'))
        self.assertEqual([0,1,2,0],runtime.get_value('Objects[1].Data'))

    def runtime(self):
        return VirtualRuntime(project('A := A;', [variable('A')]))

    def async_block(self, runtime, kind, key, value):
        result = runtime.services.block(kind,key,value)
        self.assertEqual(65535,result['status'])
        runtime.scan_count += 1
        result = runtime.services.block(kind,key,value)
        return result

    def test_real_scaling_handles_reverse_limits_and_zero_range(self):
        code = 'Scale(x:=Input,x1:=10.0,y1:=100.0,x2:=0.0,y2:=0.0); Output := Scale.y;'
        runtime = VirtualRuntime(project(code,[variable('Scale','LCRLimScal',None),variable('Input','REAL',5),variable('Output','REAL')]))
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        runtime.command('scan')
        self.assertEqual(50,runtime.get_value('Output'))
        runtime.set_value('Input',30,return_snapshot=False)
        runtime.command('scan')
        self.assertEqual(100,runtime.get_value('Output'))
        result = runtime.services.block('LCRLimScal','zero',dict(x=2,x1=1,x2=1,y1=3,y2=5,y=7))
        self.assertEqual(0,result['y'])

    def test_serial_buffer_ownership_send_receive_release_and_absent_data(self):
        runtime = self.runtime()
        vendor,service = runtime.vendor,runtime.services
        device = vendor.allocate('device',7,b'IF1.ST1')
        # Strings require a bounded terminator.
        device = vendor.allocate('deviceString',8,b'IF1.ST1\0')
        mode = b'/BD=19200 /PA=N /DB=8 /SB=1\0'
        modeptr = vendor.allocate('mode',len(mode),mode)
        opened = service.block('FRM_xopen','open',instance('FRM_xopen',device=device,mode=modeptr))
        self.assertEqual(0,opened['status'])
        ident = opened['ident']
        lease = service.block('FRM_gbuf','get',instance('FRM_gbuf',ident=ident))
        self.assertEqual(256,lease['buflng'])
        vendor.write(lease['buffer'],b'hello')
        sent = service.block('FRM_write','write',instance('FRM_write',ident=ident,buffer=lease['buffer'],buflng=5))
        self.assertEqual(0,sent['status'])
        self.assertEqual(b'hello',service.frames[ident]['sent'][0])
        with self.assertRaises(ValueError):vendor.read(lease['buffer'],1)
        result = service.block('FRM_read','receive',instance('FRM_read',ident=ident))
        self.assertEqual(60,result['status'])
        service.inject_serial(ident,b'reply')
        result = service.block('FRM_read','receive',instance('FRM_read',ident=ident))
        self.assertEqual(0,result['status'])
        self.assertEqual(b'reply',vendor.read(result['buffer'],result['buflng']))
        released = service.block('FRM_rbuf','release',instance('FRM_rbuf',ident=ident,buffer=result['buffer'],buflng=result['buflng']))
        self.assertEqual(0,released['status'])
        closed = service.block('FRM_close','close',instance('FRM_close',ident=ident))
        self.assertEqual(0,closed['status'])
        self.assertEqual(8251,service.block('FRM_read','receive',instance('FRM_read',ident=ident))['status'])

    def test_xopen_documented_config_layout(self):
        fields = {'idle':'UINT','delimc':'UINT','delim':'ARRAY[0..1] OF USINT','tx_cnt':'UINT','rx_cnt':'UINT',
                  'tx_len':'UINT','rx_len':'UINT','argc':'UINT','argv':'UDINT'}
        code = "Port(enable:=TRUE,device:=ADR('IF1.ST1'),mode:=ADR('/BD=9600 /PA=N /DB=8 /SB=1'),config:=ADR(Config));"
        runtime = VirtualRuntime(project(code,[variable('Port','FRM_xopen',None),variable('Config','XOPENCONFIG',None)],
                                         types={'XOPENCONFIG':{'kind':'struct','fields':fields}}))
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        runtime.command('scan')
        self.assertEqual(0,runtime.get_value('Port.status'))
        self.assertEqual(20,runtime.vendor.size(runtime.memory.spec('XOPENCONFIG')))

    def test_dataobjects_change_bytes_and_validate_ranges(self):
        runtime = self.runtime()
        vendor,service = runtime.vendor,runtime.services
        name = vendor.allocate('name',7,b'Object\0')
        source = vendor.allocate('source',4,b'\1\2\3\4')
        result = service.block('DatObjCreate','create',instance('DatObjCreate',pName=name,len=4,MemType=3,pCpyData=source))
        self.assertEqual(0,result['status'])
        ident = result['ident']
        vendor.write(source,b'ABCD')
        written = service.block('DatObjWrite','write',instance('DatObjWrite',ident=ident,pSource=source,len=3,Offset=1))
        self.assertEqual(0,written['status'])
        self.assertEqual(b'\1ABC',vendor.read(result['pDatObjMem'],4))
        read = service.block('DatObjRead','read',instance('DatObjRead',ident=ident,pDestination=source,len=4,Offset=1))
        self.assertEqual(20608,read['status'])
        self.assertEqual(20601,service.block('DatObjCreate','dup',instance('DatObjCreate',pName=name,len=4,MemType=3))['status'])
        service.reset(cold=False)
        self.assertIn(ident,service.objects)
        service.reset(cold=True)
        self.assertNotIn(ident,service.objects)

    def test_meminfo_and_idle_are_virtual_metrics(self):
        runtime = self.runtime()
        runtime.vendor.allocate('used',100)
        value = self.async_block(runtime,'MEMxInfo','memory',instance('MEMxInfo'))
        self.assertEqual(4*1024*1024,value['MemSize'])
        self.assertEqual(value['MemSize']-100,value['FreeMemSize'])
        value = runtime.services.block('LogIdleShow','idle',instance('LogIdleShow',measurementPeriod=1000,measurementLevel=1))
        self.assertEqual(65535,value['status'])
        runtime.time_ms += 1000
        runtime._sequence += 50000
        value = runtime.services.block('LogIdleShow','idle',instance('LogIdleShow',measurementPeriod=1000,measurementLevel=1))
        self.assertEqual(95,value['idleRate'])
        self.assertEqual(950000,value['idleTime'])

    def test_tcp_waits_for_peer_then_moves_only_virtual_bytes(self):
        runtime = self.runtime()
        vendor = runtime.vendor
        listener = self.async_block(runtime,'TcpOpen','listener',instance('TcpOpen',port=2000))['ident']
        result = self.async_block(runtime,'TcpServer','accept',instance('TcpServer',ident=listener,backlog=2))
        self.assertEqual(32613,result['status'])
        client = self.async_block(runtime,'TcpOpen','client',instance('TcpOpen',port=2001))['ident']
        ip = vendor.allocate('ip',10,b'127.0.0.1\0')
        result = self.async_block(runtime,'TcpClient','connect',instance('TcpClient',ident=client,pServer=ip,portserv=2000))
        self.assertEqual(0,result['status'])
        result = self.async_block(runtime,'TcpServer','accept',instance('TcpServer',ident=listener,backlog=2))
        self.assertEqual(0,result['status'])
        accepted = result['identclnt']
        outgoing = vendor.allocate('outgoing',5,b'bytes')
        received = vendor.allocate('received',5)
        result = self.async_block(runtime,'TcpSend','send',instance('TcpSend',ident=client,pData=outgoing,datalen=5))
        self.assertEqual(5,result['sentlen'])
        result = self.async_block(runtime,'TcpRecv','recv',instance('TcpRecv',ident=accepted,pData=received,datamax=5))
        self.assertEqual(5,result['recvlen'])
        self.assertEqual(b'bytes',vendor.read(received,5))

    def test_usb_absent_is_explicit_and_configured_nodes_fill_real_buffers(self):
        runtime = self.runtime()
        vendor = runtime.vendor
        address = vendor.allocate('usbIds',128)
        request = instance('UsbNodeListGet',pBuffer=address,bufferSize=128,filterInterfaceClass=8,filterInterfaceSubClass=6)
        value = self.async_block(runtime,'UsbNodeListGet','list',request)
        self.assertEqual(32900,value['status'])
        self.assertEqual(0,value['allNodes'])
        runtime.services.configure_usb([{'id':42,'ifName':'VIRTUAL.USB1','vendorId':1234}])
        value = self.async_block(runtime,'UsbNodeListGet','list',request)
        self.assertEqual(0,value['status'])
        self.assertEqual(42,struct.unpack('<I',vendor.read(address,4))[0])
        buffer = vendor.allocate('usbNode',140)
        value = self.async_block(runtime,'UsbNodeGet','node',instance('UsbNodeGet',nodeId=42,pBuffer=buffer,bufferSize=140))
        self.assertEqual(0,value['status'])
        self.assertEqual(1234,struct.unpack('<6H',vendor.read(buffer,12))[3])
        self.assertEqual(b'VIRTUAL.USB1',vendor.read(buffer+12,128).split(b'\0')[0])

    def test_temporary_memory_and_visualization_state_are_real_bounded_resources(self):
        runtime = VirtualRuntime(project("Status := TMP_alloc(20,ADR(Pointer));",[variable('Pointer','UDINT'),variable('Status','UINT')]))
        self.assertTrue(runtime.run_allowed,runtime.diagnostics)
        runtime.command('scan')
        address = runtime.get_value('Pointer')
        self.assertEqual(bytes(20),runtime.vendor.read(address,20))
        args = lambda *values:[{'value':{'op':'literal','value':v}} for v in values]
        handle = runtime.services.call('VA_SETUP',args(True,'T30_5'),'Main',None)
        self.assertEqual(7110,runtime.services.call('VA_SETBRIGHTNESS',args(True,handle,75),'Main',None))
        self.assertEqual(0,runtime.services.call('VA_SACCESS',args(True,handle),'Main',None))
        self.assertEqual(0,runtime.services.call('VA_SETBRIGHTNESS',args(True,handle,75),'Main',None))
        self.assertEqual(75,runtime.services.visualizations[handle]['brightness'])
        self.assertEqual(0,runtime.services.call('VA_LINE',args(True,handle,10,20,30,40,248),'Main',None))
        self.assertEqual(0,runtime.services.call('VA_REDRAW',args(True,handle),'Main',None))
        self.assertEqual(1,len(runtime.services.visualizations[handle]['displayedDrawing']))
        self.assertEqual(0,runtime.services.call('TMP_FREE',args(20,address),'Main',None))
        with self.assertRaises(ValueError):runtime.vendor.read(address,1)

    def test_iomm_mutates_virtual_modules_only_with_actual_dataobjects(self):
        runtime = self.runtime()
        vendor = runtime.vendor
        object_name = vendor.allocate('dataName',5,b'Data\0')
        module_name = vendor.allocate('moduleName',6,b'iomap\0')
        request = instance('AsIOMMCreate',pDataObject=object_name,pNewModule=module_name,moduleKind=1,memType=2)
        result = self.async_block(runtime,'AsIOMMCreate','install',request)
        self.assertEqual(30174,result['status'])
        runtime.services.block('DatObjCreate','create',instance('DatObjCreate',pName=object_name,len=4,MemType=3))
        result = self.async_block(runtime,'AsIOMMCreate','install',request)
        self.assertEqual(0,result['status'])
        self.assertIn('iomap',runtime.services.modules)
        result = self.async_block(runtime,'AsIOMMRemove','remove',instance('AsIOMMRemove',pModuleName=module_name))
        self.assertEqual(0,result['status'])
        self.assertNotIn('iomap',runtime.services.modules)


if __name__=='__main__':
    unittest.main()
