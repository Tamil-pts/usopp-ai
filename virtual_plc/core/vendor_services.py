"""Documented B&R services backed entirely by bounded simulation state.

Reference interfaces: bundled AS help, libraries/{dvframe,astcp,dataobj,
asiomman,asarprof,brsystem,fileio,loopconr,visapi}/fbks. No sockets,
native libraries, host files or host CPU metrics are used.
"""
from copy import deepcopy
from collections import deque
from ipaddress import IPv4Address
import re
import struct
import math

from .vendor import MAX_BYTES, byte_fields
from .fieldbus_services import BLOCKS as FIELDBUS_BLOCKS,FieldbusRuntime
from .csv_services import CALLS as CSV_CALLS,BLOCKS as CSV_BLOCKS,CSVRuntime

CALLS = {'SYSRESET': (2, 2), 'TMP_ALLOC': (2,2), 'TMP_FREE': (2,2),
         'VA_LINE': (7,7), 'VA_REDRAW': (2,2), 'VA_SETUP': (2, 2), 'VA_SACCESS': (2, 2),
         'VA_SRELEASE': (2, 2), 'VA_SETBRIGHTNESS': (3, 3),
         'VA_SETCONTRAST': (3, 3), 'VA_GETBRIGHTNESS': (3, 3), 'VA_GETCONTRAST': (2, 2),
         'VA_GETEXALARMLIST':(7,7),'VA_GETALCURPOS':(4,4),'VA_STARTTOUCHCAL':(2,2),'VA_GETCALSTATUS':(2,2),
         'BRMFLOOR':(1,1),'BRMFMOD':(2,2),'RAND':(0,0)}
BLOCKS = {
    'IcmpPing':({'enable':'BOOL','pHost':'UDINT','timeout':'UINT'},{'status':'UINT'}),
    'AsArLogWrite':({'enable':'BOOL','ident':'UDINT','logLevel':'UDINT','errornr':'UDINT','mem':'UDINT','len':'UDINT','asciiString':'UDINT'},{'status':'UINT'}),
    'DirInfo':({'enable':'BOOL','pDevice':'UDINT','pPath':'UDINT'},{'status':'UINT','dirnum':'UDINT','filenum':'UDINT'}),
    'DirRead':({'enable':'BOOL','pDevice':'UDINT','pPath':'UDINT','entry':'UDINT','option':'USINT','pData':'UDINT','data_len':'UDINT'},{'status':'UINT'}),
    'UsbNodeListGet': ({'enable':'BOOL','pBuffer':'UDINT','bufferSize':'UDINT','filterInterfaceClass':'UINT','filterInterfaceSubClass':'UINT'},
                       {'status':'UINT','allNodes':'UDINT','listNodes':'UDINT','attachDetachCount':'UDINT'}),
    'UsbNodeGet': ({'enable':'BOOL','nodeId':'UDINT','pBuffer':'UDINT','bufferSize':'UDINT'}, {'status':'UINT'}),
    'UsbDescriptorGet': ({'enable':'BOOL','nodeId':'UDINT','requestType':'USINT','descriptorType':'USINT','descriptorIndex':'USINT','languageId':'UINT','pBuffer':'UDINT','bufferSize':'UINT'},
                         {'status':'UINT','actSize':'UINT'}),
    'FRM_xopen': ({'enable':'BOOL','device':'UDINT','mode':'UDINT','config':'UDINT'}, {'status':'UINT','ident':'UDINT'}),
    'FRM_gbuf': ({'enable':'BOOL','ident':'UDINT'}, {'status':'UINT','buffer':'UDINT','buflng':'UINT'}),
    'FRM_write': ({'enable':'BOOL','ident':'UDINT','buffer':'UDINT','buflng':'UINT'}, {'status':'UINT'}),
    'FRM_robuf': ({'enable':'BOOL','ident':'UDINT','buffer':'UDINT','buflng':'UINT'}, {'status':'UINT'}),
    'FRM_read': ({'enable':'BOOL','ident':'UDINT'}, {'status':'UINT','buffer':'UDINT','buflng':'UINT'}),
    'FRM_rbuf': ({'enable':'BOOL','ident':'UDINT','buffer':'UDINT','buflng':'UINT'}, {'status':'UINT'}),
    'FRM_close': ({'enable':'BOOL','ident':'UDINT'}, {'status':'UINT'}),
    'LCRLimScal': ({'x':'REAL','x1':'REAL','y1':'REAL','x2':'REAL','y2':'REAL'}, {'y':'REAL'}),
    'LogIdleShow': ({'enable':'BOOL','measurementPeriod':'UDINT','measurementLevel':'UDINT'},
                    {'status':'UINT','totalTime':'UDINT','idleTime':'UDINT','idleRate':'UDINT'}),
    'MEMxInfo': ({'enable':'BOOL','mem_typ':'UDINT'},
                 {'status':'UINT','MemSize':'UDINT','FreeMemSize':'UDINT','BiggestFreeBlockSize':'UDINT'}),
    'DevLink': ({'enable':'BOOL','pDevice':'UDINT','pParam':'UDINT'}, {'status':'UINT','handle':'UDINT'}),
    'DevUnlink': ({'enable':'BOOL','handle':'UDINT'}, {'status':'UINT'}),
    'AsIOMMCreate': ({'enable':'BOOL','pDataObject':'UDINT','pNewModule':'UDINT','moduleKind':'USINT','memType':'USINT'},
                     {'status':'UINT','errCode':'UINT'}),
    'AsIOMMRemove': ({'enable':'BOOL','pModuleName':'UDINT'}, {'status':'UINT','errCode':'UINT'}),
    'TcpOpen': ({'enable':'BOOL','pIfAddr':'UDINT','port':'UINT','options':'UDINT'}, {'status':'UINT','ident':'UDINT'}),
    'TcpClose': ({'enable':'BOOL','ident':'UDINT','how':'UDINT'}, {'status':'UINT'}),
    'TcpServer': ({'enable':'BOOL','ident':'UDINT','backlog':'UDINT','pIpAddr':'UDINT'},
                   {'status':'UINT','identclnt':'UDINT','portclnt':'UINT'}),
    'TcpClient': ({'enable':'BOOL','ident':'UDINT','pServer':'UDINT','portserv':'UINT'}, {'status':'UINT'}),
    'TcpRecv': ({'enable':'BOOL','ident':'UDINT','pData':'UDINT','datamax':'UDINT','flags':'UDINT'},
                 {'status':'UINT','recvlen':'UDINT'}),
    'TcpSend': ({'enable':'BOOL','ident':'UDINT','pData':'UDINT','datalen':'UDINT','flags':'UDINT'},
                 {'status':'UINT','sentlen':'UDINT'}),
    'TcpIoctl': ({'enable':'BOOL','ident':'UDINT','ioctl':'UDINT','pData':'UDINT','datalen':'UDINT'},
                  {'status':'UINT','outlen':'UDINT'}),
    'DatObjCreate': ({'enable':'BOOL','grp':'USINT','pName':'UDINT','len':'UDINT','MemType':'USINT','Option':'UDINT','pCpyData':'UDINT'},
                     {'status':'UINT','ident':'UDINT','pDatObjMem':'UDINT'}),
    'DatObjInfo': ({'enable':'BOOL','pName':'UDINT'},
                   {'status':'UINT','ident':'UDINT','pDatObjMem':'UDINT','len':'UDINT','MemType':'USINT','Option':'UDINT','ChangeDate':'DATE_AND_TIME'}),
    'DatObjRead': ({'enable':'BOOL','ident':'UDINT','Offset':'UDINT','pDestination':'UDINT','len':'UDINT'}, {'status':'UINT'}),
    'DatObjWrite': ({'enable':'BOOL','ident':'UDINT','Offset':'UDINT','pSource':'UDINT','len':'UDINT'}, {'status':'UINT'}),
    'DatObjDelete': ({'enable':'BOOL','ident':'UDINT'}, {'status':'UINT'}),
}


BLOCKS.update(FIELDBUS_BLOCKS)
BLOCKS.update(CSV_BLOCKS)
CALLS.update(CSV_CALLS)

def register_types(types, case_sensitive=False):
    for name, (inputs, outputs) in BLOCKS.items():
        key = next((k for k in types if (k == name if case_sensitive else k.casefold() == name.casefold())), name)
        # The public interface is authoritative. Internal native instance bytes
        # are deliberately absent because execution is provided by this model.
        types[key] = {'kind':'struct', 'serviceBlock':name, 'fields':{**inputs, **outputs}}
        alias = name+'_typ'
        types[alias] = {'kind':'struct', 'serviceBlock':name, 'fields':{**inputs, **outputs}}


class ServiceRuntime:
    def __init__(self, runtime):
        self.runtime = runtime
        self.pending, self.frames, self.sockets = {}, {}, {}
        self.objects, self.modules, self.devices, self.visualizations = {}, {}, {}, {}
        self.next_ident = 10000
        self.temporary, self.usb, self.usb_changes = {}, {}, 0
        self.pings,self.network_hosts,self.logger={},{},deque(maxlen=1000)
        self.random_state=1
        self.alarm_history=deque(maxlen=1000)
        self.fieldbus=FieldbusRuntime(self)
        self.csv=CSVRuntime(self)

    @property
    def vendor(self):
        return self.runtime.vendor

    def ident(self):
        self.next_ident += 1
        return self.next_ident

    def asynchronous(self, kind, key, block):
        """Capture a request and complete on a later scan, preserving its inputs."""
        signature = tuple((n, block[n]) for n in BLOCKS[kind][0])
        saved = self.pending.get(key)
        if saved is None or saved[2] != signature:
            self.pending[key] = (self.runtime.scan_count, deepcopy(block), signature)
            block['status'] = 65535
            return None
        if saved[0] == self.runtime.scan_count:
            block['status'] = 65535
            return None
        self.pending.pop(key)
        return saved[1]

    def call(self, name, args, scope, frame):
        values = [self.runtime._eval(arg['value'], scope, frame) for arg in args]
        if name in CSV_CALLS:return self.csv.call(name,values)
        if name=='BRMFLOOR':return float(math.floor(values[0]))
        if name=='BRMFMOD':return math.fmod(*values)
        if name=='RAND':
            # Stable virtual ANSI-C PRNG; never presented as the native libc sequence.
            self.random_state=(1103515245*self.random_state+12345)&0x7fffffff
            return (self.random_state>>16)&0x7fff
        if name=='TMP_ALLOC':
            count,destination = values
            if type(count) is not int or not 1<=count<=MAX_BYTES:
                raise ValueError('TMP_alloc size exceeds the bounded virtual memory pool')
            ident = self.ident()
            key = ('temporary',ident)
            address = self.vendor.allocate(key,count)
            try:
                self.vendor.write(destination,struct.pack('<I',address))
            except ValueError:
                self.vendor.release(key)
                raise
            self.temporary[address] = {'key':key,'size':count}
            return 0
        if name=='TMP_FREE':
            count,address = values
            allocation = self.temporary.get(address)
            if allocation is None or allocation['size']!=count:
                raise ValueError('TMP_free pointer or length does not match an allocated virtual temporary region')
            self.vendor.release(allocation['key'])
            self.temporary.pop(address)
            return 0
        if name == 'SYSRESET':
            if not values[0]:
                return 65534
            if values[1] not in (1, 2, 17, 18, 32, 64):
                return 27251
            self.runtime.request_reset(values[1])
            return 0
        if name == 'VA_SETUP':
            if not values[0]:
                return 0
            project = values[1]
            # Project names are explicit source values, not host window names.
            if not isinstance(project, str) or not project or len(project)>80:
                return 0
            for ident, item in self.visualizations.items():
                if item['name'] == project:
                    return ident
            ident = self.ident()
            self.visualizations[ident] = {'name':project, 'brightness':50, 'contrast':50, 'access':False,
                                         'drawing':[], 'displayedDrawing':[], 'redrawCount':0}
            return ident
        if not values[0]:
            return 65534
        item = self.visualizations.get(values[1])
        if item is None:
            return 100  # vaERR_VISAPI_NOT_INITIALIZED
        if name == 'VA_SACCESS':
            if item['access']:
                return 7000
            item['access'] = True
            return 0
        if name == 'VA_SRELEASE':
            if not item['access']:
                return 7110
            item['access'] = False
            return 0
        if not item['access']:
            return 7110
        if name=='VA_STARTTOUCHCAL':item['calibrationStatus']=1;return 0
        if name=='VA_GETCALSTATUS':return item.get('calibrationStatus',0)
        if name=='VA_GETALCURPOS':
            if not self.alarm_history:return 245
            alarm=self.alarm_history[-1]
            self.vendor.write(values[2],bytes([alarm['group']&255]));self.vendor.write(values[3],bytes([alarm['number']&255]));return 0
        if name=='VA_GETEXALARMLIST':
            if not self.alarm_history:return 248
            cursor=item.get('alarmCursor',-1);action=values[4]
            cursor=0 if action==1 else len(self.alarm_history)-1 if action==8 else cursor+1 if action==2 else cursor-1 if action==4 else cursor
            if not 0<=cursor<len(self.alarm_history):return 240
            alarm=self.alarm_history[cursor];separator=chr(values[5]);text=separator.join([alarm.get('time',''),str(alarm['group']),str(alarm['number']),alarm['text'],'A' if alarm.get('acknowledged') else 'nA','1' if alarm['active'] else '0'])
            capacity=struct.unpack('<i',self.vendor.read(values[3],4))[0]
            if not 0<=capacity<=4096:return 7090
            raw=text.encode('latin-1',errors='replace')[:capacity];self.vendor.write(values[2],raw+b'\0');self.vendor.write(values[3],struct.pack('<i',len(raw)));item['alarmCursor']=cursor;return 0
        if name=='VA_LINE':
            if any(type(n) is not int or not 0<=n<=65535 for n in values[2:]):
                return 7090
            if len(item['drawing'])>=8192:
                return 7120
            item['drawing'].append({'kind':'line','x1':values[2],'y1':values[3],'x2':values[4],'y2':values[5],'color':values[6]})
            return 0
        if name=='VA_REDRAW':
            item['displayedDrawing'] = deepcopy(item['drawing'])
            item['drawing'].clear()
            item['redrawCount'] += 1
            return 0
        field = 'brightness' if 'BRIGHTNESS' in name else 'contrast'
        if name.startswith('VA_SET'):
            if type(values[2]) is not int or not 0<=values[2]<=100:
                return 7090
            item[field] = values[2]
            return 0
        if name == 'VA_GETBRIGHTNESS':
            try:
                self.vendor.write(values[2], struct.pack('<I', item[field]))
            except ValueError:
                return 7090
            return 0
        return item[field]

    def block(self, kind, key, block):
        if kind in CSV_BLOCKS:return self.csv.block(kind,key,block)
        if kind in FIELDBUS_BLOCKS:return self.fieldbus.block(kind,key,block)
        block = deepcopy(block)
        if kind == 'LCRLimScal':
            x, x1, x2, y1, y2 = (block[n] for n in ('x','x1','x2','y1','y2'))
            y = 0 if x1 == x2 else y1+(max(min(x1,x2), min(max(x1,x2), x))-x1)*(y2-y1)/(x2-x1)
            block['y'] = y
            return block
        if not block['enable']:
            self.pending.pop(key, None)
            block['status'] = 65534
            return block
        if kind=='IcmpPing':
            try:host=self.vendor.string(block['pHost'])
            except ValueError:block['status']=32751;return block
            if not host or len(host)>255:block['status']=32751;return block
            start=self.pings.setdefault(key,self.runtime.time_ms)
            timeout=max(1,block['timeout'])*10
            if host in self.network_hosts:
                block['status']=0 if self.network_hosts[host] else 32750;self.pings.pop(key,None)
            elif self.runtime.time_ms-start>=timeout:block['status']=32750;self.pings.pop(key,None)
            else:block['status']=65535
            return block
        if kind=='AsArLogWrite':
            try:
                raw=self.vendor.read(block['mem'],block['len']) if block['mem'] and block['len'] else b''
                message=self.vendor.string(block['asciiString']) if block['asciiString'] else ''
                self.logger.append({'timeMs':self.runtime.time_ms,'ident':block['ident'],'level':block['logLevel'],'error':block['errornr'],'message':message,'data':list(raw)})
                block['status']=0
            except ValueError:block['status']=33308
            return block
        if kind in {'DirInfo','DirRead'}:
            try:
                device=self.vendor.string(block['pDevice']);path=self.vendor.string(block['pPath']).strip('/') if block['pPath'] else ''
                entries=[(name,data) for (dev,name),data in sorted(self.vendor.files.items()) if dev==device and str(__import__('pathlib').PurePosixPath(name).parent).strip('.')==path]
                if kind=='DirInfo':block.update(status=0,dirnum=0,filenum=len(entries));return block
                if block['entry']>=len(entries):block['status']=20711;return block
                region,offset=self.vendor.region(block['pData'],block['data_len']);spec=region['spec']
                if offset or spec.get('kind')!='struct':raise ValueError('DirRead requires a declared directory entry record')
                name,data=entries[block['entry']];value=self.runtime.memory.default(spec)
                for field in self.runtime.memory.fields(spec):
                    keyname=field['name'].casefold()
                    if keyname in {'filename','name'}:value[field['name']]=name
                    elif keyname in {'filelength','filelen','length','size'}:value[field['name']]=len(data)
                self.vendor.write(block['pData'],self.vendor.encode(value,spec));block['status']=0
            except ValueError:block['status']=20719
            return block
        if kind.startswith('FRM_'):
            return self.frame(kind, key, block)
        if kind == 'LogIdleShow':
            period = block['measurementPeriod'] if 100<=block['measurementPeriod']<=60000 else 100
            start = self.pending.get(key)
            if start is None:
                self.pending[key] = (self.runtime.time_ms, self.runtime._sequence)
                block['status'] = 65535
            elif self.runtime.time_ms-start[0] < period:
                block['status'] = 65535
            else:
                total = int((self.runtime.time_ms-start[0])*1000)
                # Deterministic virtual CPU budget: one executed IR event per
                # microsecond. This explicitly does not measure host CPU use.
                busy = min(total, max(0, self.runtime._sequence-start[1]))
                block.update(status=0,totalTime=total,idleTime=total-busy,idleRate=int(100*(total-busy)/total))
                self.pending.pop(key)
            return block
        if kind.startswith('DatObj'):
            return self.data_object(kind, block)
        request = self.asynchronous(kind, key, block)
        if request is None:
            return block
        block['status'] = 0
        if kind.startswith('Usb'):
            return self.usb_block(kind,request,block)
        if kind == 'MEMxInfo':
            if request['mem_typ'] not in range(4):
                block['status'] = 27251
            elif request['mem_typ'] != 0:
                block.update(MemSize=4294967295,FreeMemSize=4294967295,BiggestFreeBlockSize=4294967295)
            else:
                free = MAX_BYTES-sum(r['size'] for r in self.vendor.regions)
                block.update(MemSize=MAX_BYTES,FreeMemSize=free,BiggestFreeBlockSize=free)
        elif kind.startswith('Tcp'):
            return self.tcp(kind, request, block)
        elif kind.startswith('AsIOMM'):
            return self.mapping(kind, request, block)
        elif kind == 'DevLink':
            try:
                name, parameters = self.vendor.string(request['pDevice']), self.vendor.string(request['pParam'])
                if (not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', name) or
                    not parameters.startswith('/DEVICE=') or not parameters[8:].strip() or len(parameters)>2048):
                    block['status'] = 20729
                elif any(v['name']==name for v in self.devices.values()):
                    block['status'] = 20730
                elif len(self.devices)>=64:
                    block['status'] = 20710
                else:
                    ident = self.ident()
                    self.devices[ident] = {'name':name, 'parameters':parameters}
                    block['handle'] = ident
            except ValueError:
                block['status'] = 20729
        elif kind == 'DevUnlink':
            device = self.devices.get(request['handle'])
            if device is None:
                block['status'] = 20731
            elif any(path[0]==device['name'] for path, mode in self.vendor.handles.values()):
                block['status'] = 20706
            else:
                self.devices.pop(request['handle'])
        return block

    def configure_usb(self, nodes):
        """Attach explicit virtual USB nodes; never enumerate host USB devices."""
        if not isinstance(nodes,list) or len(nodes)>32:
            raise ValueError('At most 32 virtual USB nodes may be configured')
        prepared = {}
        for index,node in enumerate(nodes):
            if not isinstance(node,dict) or set(node)-{'id','interfaceClass','interfaceSubClass','interfaceProtocol','vendorId','productId','bcdDevice','ifName'}:
                raise ValueError('Invalid virtual USB node properties')
            identity = node.get('id',index+1)
            if type(identity) is not int or not 1<=identity<=4294967295 or identity in prepared:
                raise ValueError('Virtual USB node identity must be unique and nonzero')
            value = {n:node.get(n,default) for n,default in [('interfaceClass',8),('interfaceSubClass',6),('interfaceProtocol',80),('vendorId',0),('productId',0),('bcdDevice',256)]}
            if any(type(v) is not int or not 0<=v<=65535 for v in value.values()):
                raise ValueError('Virtual USB numeric fields must fit UINT')
            name = node.get('ifName','VIRTUAL.USB'+str(identity))
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,127}',name):
                raise ValueError('Virtual USB interface name is invalid')
            prepared[identity] = {**value,'ifName':name}
        self.usb = prepared
        self.usb_changes = (self.usb_changes+1)%4294967296

    def usb_block(self, kind, request, block):
        if not request['pBuffer']:
            block['status'] = 32902
            return block
        if kind=='UsbNodeListGet':
            nodes = [i for i,v in self.usb.items() if
                     (not request['filterInterfaceClass'] or v['interfaceClass']==request['filterInterfaceClass']) and
                     (not request['filterInterfaceSubClass'] or v['interfaceSubClass']==request['filterInterfaceSubClass'])]
            block.update(allNodes=len(self.usb),listNodes=0,attachDetachCount=self.usb_changes)
            if not nodes:
                block['status'] = 32900
                return block
            capacity = request['bufferSize']//4
            if capacity<len(nodes):
                block['status'] = 32901
                return block
            try:
                self.vendor.write(request['pBuffer'],b''.join(struct.pack('<I',i) for i in nodes))
                block['listNodes'] = len(nodes)
            except ValueError:
                block['status'] = 32901
            return block
        node = self.usb.get(request['nodeId'])
        if node is None:
            block['status'] = 32900
            return block
        if kind=='UsbNodeGet':
            raw = struct.pack('<6H',*(node[n] for n in ('interfaceClass','interfaceSubClass','interfaceProtocol','vendorId','productId','bcdDevice')))
            raw += node['ifName'].encode('ascii').ljust(128,b'\0')
        elif request['requestType']!=0 or request['descriptorType']!=1 or request['descriptorIndex']!=0:
            block['status'] = 32900
            return block
        else:
            raw = struct.pack('<BBHBBBBHHHBBBB',18,1,512,0,0,0,64,node['vendorId'],node['productId'],node['bcdDevice'],0,0,0,1)
        if request['bufferSize']<len(raw):
            block['status'] = 32901
        else:
            try:
                self.vendor.write(request['pBuffer'],raw)
                if kind=='UsbDescriptorGet':
                    block['actSize'] = len(raw)
            except ValueError:
                block['status'] = 32901
        return block

    def frame(self, kind, key, block):
        block['status'] = 0
        if kind == 'FRM_xopen':
            try:
                device, mode = self.vendor.string(block['device']), self.vendor.string(block['mode'])
            except ValueError:
                block['status'] = 8252
                return block
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', device):
                block['status'] = 8252
                return block
            tokens = dict(re.findall(r'/([A-Z0-9]+)=([^\s]+)', mode))
            if (re.sub(r'/[A-Z0-9]+=[^\s]+', '', mode).strip() or
                set(tokens)-{'BD','PA','DB','SB','PHY','RIT','TIT','CCHAR1','CCHAR2','CCHAR3','CCHAR4','FCCTS','FCSW','RTSTX','TEMTS'} or
                ('BD' in tokens and (not tokens['BD'].isdigit() or not 300<=int(tokens['BD'])<=115200)) or
                ('PA' in tokens and tokens['PA'] not in {'N','E','O','H','L'}) or
                ('DB' in tokens and tokens['DB'] not in {'7','8'}) or
                ('SB' in tokens and tokens['SB'] not in {'1','2'}) or
                ('PHY' in tokens and tokens['PHY'] not in {'RS232','RS422','RS485','TTY','RS422BUS'}) or
                any(n in tokens and tokens[n] not in {'0','1'} for n in ('FCCTS','FCSW','RTSTX','TEMTS')) or
                any(n in tokens and (not tokens[n].isdigit() or not 1<=int(tokens[n])<=65535) for n in ('RIT','TIT'))):
                block['status'] = 8253
                return block
            if set(tokens)&{'PA','DB','SB'} and not {'PA','DB','SB'}<=set(tokens):
                block['status'] = 8256
                return block
            config = dict(tx_cnt=2,rx_cnt=2,tx_len=256,rx_len=256)
            if block['config']:
                try:
                    region, offset = self.vendor.region(block['config'])
                    if offset or not isinstance(region['spec'],dict) or not byte_fields(region['spec']):
                        raise ValueError('FRM config needs documented XOPENCONFIG')
                    config.update(self.vendor.decode(self.vendor.read(block['config'],region['size']),region['spec']))
                except (ValueError, KeyError):
                    block['status'] = 8253
                    return block
            for n, default in [('tx_cnt',2),('rx_cnt',2),('tx_len',256),('rx_len',256)]:
                config[n] = config[n] or default
            if not 1<=config['tx_cnt']<=8 or not 1<=config['rx_cnt']<=8 or not 1<=config['tx_len']<=65535 or not 1<=config['rx_len']<=65535:
                block['status'] = 8253
                return block
            if config.get('argc'):
                block['status'] = 8253  # No unimplemented extension arguments accepted.
                return block
            existing = next((i for i,v in self.frames.items() if v['key']==key and v['device']==device),None)
            if existing:
                block['ident'] = existing
                return block
            if len(self.frames)>=32:
                block['status'] = 8254
                return block
            ident = self.ident()
            self.frames[ident] = {'key':key,'device':device,'mode':mode,'config':config,'tx':{},'rx':{},'incoming':deque(maxlen=64),'sent':deque(maxlen=256)}
            block['ident'] = ident
            return block
        item = self.frames.get(block['ident'])
        if item is None:
            block['status'] = 8251
            return block
        if kind == 'FRM_close':
            for lease in list(item['tx'].values())+list(item['rx'].values()):
                self.vendor.release(lease['key'])
            self.frames.pop(block['ident'])
        elif kind == 'FRM_gbuf':
            if len(item['tx'])>=item['config']['tx_cnt']:
                block['status'] = 8071
            else:
                lease_key = ('serial',block['ident'],'tx',self.ident())
                try:
                    address = self.vendor.allocate(lease_key,item['config']['tx_len'])
                    item['tx'][address] = {'key':lease_key,'size':item['config']['tx_len']}
                    block.update(buffer=address,buflng=item['config']['tx_len'])
                except ValueError:
                    block['status'] = 8071
        elif kind in {'FRM_write','FRM_robuf','FRM_rbuf'}:
            leases = item['rx'] if kind=='FRM_rbuf' else item['tx']
            lease = leases.get(block['buffer'])
            if not lease or not 0<=block['buflng']<=lease['size']:
                block['status'] = 8072
            else:
                if kind=='FRM_write':
                    item['sent'].append(self.vendor.read(block['buffer'],block['buflng']))
                self.vendor.release(lease['key'])
                leases.pop(block['buffer'])
        elif kind == 'FRM_read':
            if not item['incoming'] or len(item['rx'])>=item['config']['rx_cnt']:
                block.update(status=60,buffer=0,buflng=0)
            else:
                raw = item['incoming'].popleft()
                lease_key = ('serial',block['ident'],'rx',self.ident())
                try:
                    address = self.vendor.allocate(lease_key,len(raw),raw)
                    item['rx'][address] = {'key':lease_key,'size':len(raw)}
                    block.update(buffer=address,buflng=len(raw))
                except ValueError:
                    block['status'] = 8071
        return block

    def inject_serial(self, ident, raw):
        item = self.frames.get(ident)
        raw = bytes(raw)
        if item is None or not 1<=len(raw)<=item['config']['rx_len'] or len(item['incoming'])>=64:
            raise ValueError('Virtual serial input is invalid or its bounded queue is full')
        item['incoming'].append(raw)

    def data_object(self, kind, block):
        block['status'] = 0
        if kind in {'DatObjCreate','DatObjInfo'}:
            try:
                name = self.vendor.string(block['pName'])
            except ValueError:
                block['status'] = 20600
                return block
            if not name or len(name)>10:
                block['status'] = 20613 if len(name)>10 else 20600
                return block
            ident = next((i for i,v in self.objects.items() if v['name']==name),None)
            if kind=='DatObjInfo':
                if ident is None:
                    block['status'] = 20609
                else:
                    item = self.objects[ident]
                    block.update(ident=ident,pDatObjMem=item['address'],len=item['length'],MemType=item['memType'],Option=item['option'],ChangeDate=item['date'])
            elif ident is not None:
                block['status'] = 20601
            elif block['grp'] or block['Option'] not in {0,1}:
                block['status'] = 20600
            elif block['MemType'] not in {1,2,3,4,5,65}:
                block['status'] = 20602
            elif not 1<=block['len']<=MAX_BYTES:
                block['status'] = 20608
            else:
                ident = self.ident()
                try:
                    raw = self.vendor.read(block['pCpyData'],block['len']) if block['pCpyData'] else bytes(block['len'])
                    address = self.vendor.allocate(('object',ident),block['len'],raw)
                except ValueError:
                    block['status'] = 20603 if not block['pCpyData'] else 20600
                    return block
                self.objects[ident] = {'name':name,'address':address,'length':block['len'],'memType':block['MemType'],'option':block['Option'],'date':self.date()}
                block.update(ident=ident,pDatObjMem=address)
            return block
        item = self.objects.get(block['ident'])
        if item is None:
            block['status'] = 20605
        elif kind=='DatObjDelete':
            self.vendor.release(('object',block['ident']))
            self.objects.pop(block['ident'])
        elif block['Offset']>item['length']:
            block['status'] = 20607
        elif block['len']>item['length']-block['Offset']:
            block['status'] = 20608
        else:
            try:
                address = item['address']+block['Offset']
                if kind=='DatObjRead':
                    self.vendor.write(block['pDestination'],self.vendor.read(address,block['len']))
                else:
                    self.vendor.write(address,self.vendor.read(block['pSource'],block['len']))
                    item['date'] = self.date()
            except ValueError:
                block['status'] = 20600
        return block

    def date(self):
        from .cpu import EPOCH
        return int((self.runtime.cpu.now()-EPOCH).total_seconds())

    def mapping(self, kind, request, block):
        try:
            name = self.vendor.string(request['pModuleName' if kind=='AsIOMMRemove' else 'pNewModule'])
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,9}',name):
                block['status'] = 30176
            elif kind=='AsIOMMRemove':
                if name not in self.modules:
                    block['status'] = 30174
                else:
                    self.modules.pop(name)
            elif name in self.modules:
                block['status'] = 30177
            elif request['moduleKind'] not in {1,2}:
                block['status'] = 30175
            else:
                source = self.vendor.string(request['pDataObject'])
                item = next((v for v in self.objects.values() if v['name']==source),None)
                if item is None:
                    block['status'] = 30174
                else:
                    self.modules[name] = {'kind':request['moduleKind'],'source':source,
                                          'data':self.vendor.read(item['address'],item['length'])}
        except ValueError:
            block['status'] = 30176
        block['errCode'] = block['status'] if block['status'] else 0
        return block

    def tcp(self, kind, request, block):
        if kind=='TcpOpen':
            try:
                interface = str(IPv4Address(self.vendor.string(request['pIfAddr']))) if request['pIfAddr'] else '0.0.0.0'
            except ValueError:
                block['status'] = 32612
                return block
            port = request['port']
            if not port:
                port = next((p for p in range(49152,65536) if not any(v['port']==p for v in self.sockets.values())),None)
            if request['options'] & ~1:
                block['status'] = 32603
            elif port is None:
                block['status'] = 32601
            elif any(v['port']==port and v['address']==interface for v in self.sockets.values()) and not request['options']&1:
                block['status'] = 32602
            elif len(self.sockets)>=64:
                block['status'] = 32601
            else:
                ident = self.ident()
                self.sockets[ident] = {'address':interface,'port':port,'peer':None,'incoming':bytearray(),'outgoing':deque(maxlen=256),'accepted':deque(),'options':{}}
                block['ident'] = ident
            return block
        item = self.sockets.get(request['ident'])
        if item is None:
            block['status'] = 32600
            return block
        if kind=='TcpClose':
            if request['how'] not in {0,1,2,3}:
                block['status'] = 32603
            else:
                self.sockets.pop(request['ident'])
                peer = self.sockets.get(item['peer'])
                if peer is not None:
                    peer['peer'] = None
        elif kind=='TcpServer':
            if not 1<=request['backlog']<=64:
                block['status'] = 32603
            elif not item['accepted']:
                item['listening'] = True
                item['backlog'] = request['backlog']
                block.update(status=32613,identclnt=0,portclnt=0)
            else:
                peer = item['accepted'][0]
                try:
                    if request['pIpAddr']:
                        self.vendor.write(request['pIpAddr'],self.sockets[peer]['address'].encode('ascii')+b'\0')
                    item['accepted'].popleft()
                    block.update(identclnt=peer,portclnt=self.sockets[peer]['port'])
                except ValueError:
                    block['status'] = 32603
        elif kind=='TcpClient':
            try:
                server = str(IPv4Address(self.vendor.string(request['pServer'])))
            except ValueError:
                block['status'] = 32603
                return block
            listener = next((v for v in self.sockets.values() if v.get('listening') and v['port']==request['portserv'] and v['address'] in {'0.0.0.0',server}),None)
            if item['peer'] is not None:
                block['status'] = 32610
            elif listener is None:
                block['status'] = 32609
            elif len(listener['accepted'])>=listener.get('backlog',1):
                block['status'] = 32607
            elif len(self.sockets)>=64:
                block['status'] = 32601
            else:
                ident = self.ident()
                accepted = {'address':item['address'],'port':item['port'],'peer':request['ident'],'incoming':bytearray(),'outgoing':deque(maxlen=256),'options':{}}
                self.sockets[ident] = accepted
                item['peer'] = ident
                listener['accepted'].append(ident)
        elif kind in {'TcpSend','TcpRecv'}:
            if item['peer'] is None:
                block['status'] = 32609
            elif request['flags'] & ~(4 if kind=='TcpSend' else 2):
                block['status'] = 32603
            elif kind=='TcpSend':
                count = request['datalen']
                peer = self.sockets.get(item['peer'])
                if not 0<=count<=MAX_BYTES or (peer and len(peer['incoming'])+count>MAX_BYTES):
                    block['status'] = 32607
                else:
                    try:
                        raw = self.vendor.read(request['pData'],count)
                        if peer is not None:
                            peer['incoming'].extend(raw)
                        item['outgoing'].append(raw)
                        block['sentlen'] = count
                    except ValueError:
                        block['status'] = 32603
            elif not item['incoming']:
                block.update(status=32605,recvlen=0)
            elif not 1<=request['datamax']<=MAX_BYTES:
                block['status'] = 32603
            else:
                raw = bytes(item['incoming'][:request['datamax']])
                try:
                    self.vendor.write(request['pData'],raw)
                    if not request['flags']&2:
                        del item['incoming'][:len(raw)]
                    block['recvlen'] = len(raw)
                except ValueError:
                    block['status'] = 32603
        elif kind=='TcpIoctl':
            code = request['ioctl']
            setters = {1001,1003,1005,1007,1009,1012,2001,2003,2005,2007}
            getters = {1002:1001,1004:1003,1006:1005,1008:1007,1010:1009,1013:1012,2002:2001,2004:2003,2006:2005,2008:2007}
            if code in setters and request['datalen']==4:
                try:
                    item['options'][code] = struct.unpack('<I',self.vendor.read(request['pData'],4))[0]
                    block['outlen'] = 0
                except ValueError:
                    block['status'] = 32603
            elif code in getters and request['datalen']>=4:
                try:
                    self.vendor.write(request['pData'],struct.pack('<I',item['options'].get(getters[code],0)))
                    block['outlen'] = 4
                except ValueError:
                    block['status'] = 32603
            else:
                block['status'] = 32604
        return block

    def reset(self, cold=False):
        self.fieldbus.reset()
        self.csv.reset()
        for ident, item in self.frames.items():
            for lease in list(item['tx'].values())+list(item['rx'].values()):
                self.vendor.release(lease['key'])
        self.frames.clear()
        self.sockets.clear()
        self.devices.clear()
        self.pending.clear()
        self.visualizations.clear()
        for item in self.temporary.values():
            self.vendor.release(item['key'])
        self.temporary.clear()
        for ident,item in list(self.objects.items()):
            if cold or item['memType']==65:
                self.vendor.release(('object',ident))
                self.objects.pop(ident)
        if cold:
            self.modules.clear()

    def summary(self):
        return {'virtualOnly':True,'hostIO':False,
                'serial':[{'ident':i,'device':v['device'],'sentFrames':len(v['sent']),'queuedInputFrames':len(v['incoming'])} for i,v in self.frames.items()],
                'sockets':[{'ident':i,'address':v['address'],'port':v['port'],'connected':v['peer'] is not None,'queuedInputBytes':len(v['incoming'])} for i,v in self.sockets.items()],
                'objects':[{'ident':i,'name':v['name'],'bytes':v['length']} for i,v in self.objects.items()],
                'modules':[{'name':n,'kind':v['kind'],'source':v['source']} for n,v in self.modules.items()],
                'visualizations':deepcopy(self.visualizations),
                'usbNodes':len(self.usb),'temporaryAllocations':len(self.temporary),
                'measurement':'LogIdleShow counts one virtual microsecond per IR trace event; MEMxInfo DRAM reports the 4 MiB virtual byte pool. Neither describes host CPU or RAM.'}
