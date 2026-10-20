"""Offline CPU services over typed PLC memory and the virtual scan clock.

Interfaces follow the bundled sys_lib, AsTime, AsARCfg and BRSystem help.
The RTC can read the PC local clock. Writes affect only the virtual CPU;
network, battery and identity remain simulated.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address, IPv4Network
import re

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
RTC_FIELDS = [('year','UINT'), ('month','USINT'), ('day','USINT'), ('reserve','USINT'),
              ('hour','USINT'), ('minute','USINT'), ('second','USINT'),
              ('millisec','UINT'), ('microsec','UINT')]
CALLS = {'RTC_GETTIME': (1,1), 'RTC_SETTIME': (1,1), 'SYS_BATTERY': (1,1)}
BLOCKS = {
    'DTGetTime': ({'enable':'BOOL'}, {'status':'UINT','DT1':'DATE_AND_TIME'}),
    'DTSetTime': ({'enable':'BOOL','DT1':'DATE_AND_TIME'}, {'status':'UINT'}),
    'BatteryInfo': ({'enable':'BOOL','pDevice':'UDINT'}, {'status':'UINT','state':'USINT'}),
    'SysInfo': ({'enable':'BOOL'}, {'init_reason':'USINT','init_count':'USINT','tick_count':'UDINT','version':'UDINT'}),
    'RTInfo': ({'enable':'BOOL'}, {'status':'UINT','cycle_time':'UDINT','init_reason':'SINT','task_class':'SINT'}),
}
for suffix, pointer in [('IPAddr','pIPAddr'),('SubnetMask','pSubnetMask'),('DefaultGateway','pGateway')]:
    BLOCKS['CfgGet'+suffix] = ({'enable':'BOOL','pDevice':'UDINT',pointer:'UDINT','Len':'USINT'}, {'status':'UINT'})
    BLOCKS['CfgSet'+suffix] = ({'enable':'BOOL','pDevice':'UDINT',pointer:'UDINT','Option':'UDINT'}, {'status':'UINT'})


def rtc_fields(spec):
    fields = spec.get('fields', [])
    if isinstance(fields, dict):
        fields = [dict(name=k,type=v) if isinstance(v,str) else dict(name=k,**v) for k,v in fields.items()]
    return fields if (spec.get('kind')=='struct' and all(isinstance(f.get('type'),str) for f in fields)
                      and [(f['name'],f['type'].upper()) for f in fields]==RTC_FIELDS) else None


def register_types(types, case_sensitive=False):
    for name, (inputs,outputs) in BLOCKS.items():
        types[name] = {'kind':'struct','cpuBlock':name,'fields':{**inputs,**outputs}}
        types[name+'_typ']=types[name]
    if not any(str(k).lower()=='rtctime_typ' for k in types):
        types['RTCtime_typ'] = {'kind':'struct','fields':[{'name':n,'type':t} for n,t in RTC_FIELDS]}


def configuration(value=None):
    value = value or {}
    if not isinstance(value,dict) or set(value)-{'dateTime','clockMode','interfaces','battery','serialNumbers'}:
        raise ValueError('Invalid virtual CPU configuration.')
    mode = value.get('clockMode', 'manual' if 'dateTime' in value else 'pc')
    if mode not in {'pc','manual'}: raise ValueError('Choose PC clock or custom virtual RTC.')
    date = datetime.fromisoformat(str(value.get('dateTime',datetime.now().astimezone().isoformat())).replace('Z','+00:00'))
    date = date.replace(tzinfo=datetime.now().astimezone().tzinfo) if date.tzinfo is None else date
    if not 1990 <= date.year <= 2089: raise ValueError('Virtual RTC year must be 1990..2089.')
    interfaces = value.get('interfaces', {'IF2':{'ipAddress':'192.0.2.10','subnetMask':'255.255.255.0','gateway':'192.0.2.1'}})
    if not isinstance(interfaces,dict) or len(interfaces)>32: raise ValueError('Use at most 32 virtual Ethernet interfaces.')
    result = {}
    for name, settings in interfaces.items():
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,80}',name) or not isinstance(settings,dict):
            raise ValueError('Use a declared interface name such as IF2.')
        if set(settings)!={'ipAddress','subnetMask','gateway'}: raise ValueError('Provide IP address, subnet mask and gateway.')
        item = {key:str(IPv4Address(settings[key])) for key in ('ipAddress','subnetMask','gateway')}
        IPv4Network('0.0.0.0/'+item['subnetMask'])
        result[name.upper()] = item
    battery = value.get('battery',{'LOCAL.BATT1':1,'LOCAL.BATT2':1})
    if not isinstance(battery,dict) or set(battery)-{'LOCAL.BATT1','LOCAL.BATT2'} or any(type(v) is not int or v not in range(4) for v in battery.values()):
        raise ValueError('Battery states: 0 low, 1 OK, 2 not testable, 3 missing.')
    serials = value.get('serialNumbers',{})
    if not isinstance(serials,dict) or len(serials)>256 or any(not isinstance(k,str) or len(k)>180 or type(v) is not int or not 0<=v<=4294967295 for k,v in serials.items()):
        raise ValueError('Serial numbers must be explicit virtual UDINT values.')
    return {'dateTime':date.isoformat(), 'clockMode':mode, 'interfaces':result, 'battery':dict(battery), 'serialNumbers':dict(serials)}


class CPURuntime:
    def __init__(self,runtime):
        self.runtime = runtime
        self.seed = configuration(runtime.project.get('cpuServices'))
        self.configure(self.seed)

    def configure(self, settings):
        prepared = configuration(settings)
        self.seed = deepcopy(prepared)
        self.base = datetime.fromisoformat(prepared['dateTime'])
        self.base_ms = self.runtime.time_ms
        self.interfaces = deepcopy(prepared['interfaces'])
        self.nonvolatile = deepcopy(prepared['interfaces'])
        self.pending = {}

    def now(self):
        if self.seed['clockMode'] == 'pc': return datetime.now().astimezone()
        return self.base + timedelta(milliseconds=self.runtime.time_ms-self.base_ms)

    def set_time(self,date):
        if not 1990<=date.year<=2089: return 25091
        self.base,self.base_ms = date,self.runtime.time_ms
        self.seed.update(clockMode='manual',dateTime=date.isoformat())
        return 0

    def call(self,name,args,scope,frame):
        values = [self.runtime._eval(arg['value'],scope,frame) for arg in args]
        if name=='SYS_BATTERY':
            result = 0
            for i,key in enumerate(('LOCAL.BATT2','LOCAL.BATT1')):
                state = self.seed['battery'].get(key,3)
                result |= (1<<i) if state==0 else (1<<(i+2)) if state==3 else (1<<(i+4)) if state==2 else 0
            return result
        region,offset = self.runtime.vendor.region(values[0],12)
        if offset or not rtc_fields(region['spec']): raise ValueError('RTC requires ADR of the declared RTCtime_typ structure.')
        if name=='RTC_GETTIME':
            now = self.now()
            data = {k:getattr(now,k) for k in ('year','month','day','hour','minute','second')}
            data.update(reserve=0,millisec=now.microsecond//1000,microsec=0)
            self.runtime.vendor.write(values[0],self.runtime.vendor.encode(data,region['spec']))
            return 0
        data = self.runtime.vendor.decode(self.runtime.vendor.read(values[0],12),region['spec'])
        try:
            date = datetime(*(data[k] for k in ('year','month','day','hour','minute','second')),
                            microsecond=data['millisec']*1000+data['microsec'],tzinfo=timezone.utc)
            if data['millisec']>999 or data['microsec']>999: return 25091
            return self.set_time(date)
        except (ValueError,OverflowError): return 25091

    def block(self,kind,key,block):
        block = deepcopy(block)
        if not block['enable']:
            self.pending.pop(key,None)
            if 'status' in block:block['status']=65534
            return block
        if kind=='DTGetTime': block.update(status=0,DT1=int((self.now()-EPOCH).total_seconds()))
        elif kind=='DTSetTime':
            try:block['status']=self.set_time(EPOCH+timedelta(seconds=block['DT1']))
            except (ValueError,OverflowError):block['status']=25091
        elif kind=='BatteryInfo':
            try:device = self.runtime.vendor.string(block['pDevice']).upper()
            except ValueError:block.update(status=27250,state=3);return block
            block.update(status=0 if device in self.seed['battery'] else 27250,state=self.seed['battery'].get(device,3))
        elif kind=='SysInfo':block.update(init_reason=2,init_count=0,tick_count=int(self.runtime.time_ms/10)%4294967296,version=0)
        elif kind=='RTInfo':
            task = next((t for t in self.runtime.tasks if t['name']==self.runtime._context.get('task')),None)
            block.update(status=0,cycle_time=int((task or {}).get('intervalMs',self.runtime.quantum_ms)*1000),
                         init_reason=2,task_class=int((task or {}).get('priority') or 0))
        elif kind.startswith('Cfg'):
            return self.network(kind,key,block)
        return block

    def network(self,kind,key,block):
        if key not in self.pending:
            self.pending[key] = (self.runtime.scan_count,deepcopy(block))
            block['status']=65535
            return block
        count,request = self.pending[key]
        if count==self.runtime.scan_count:
            block['status']=65535
            return block
        self.pending.pop(key)
        block['status']=0
        try:device=self.runtime.vendor.string(request['pDevice']).upper()
        except ValueError:block['status']=29001;return block
        if device not in self.interfaces:block['status']=29000;return block
        suffix=kind[6:]
        field,pointer = {'IPAddr':('ipAddress','pIPAddr'),'SubnetMask':('subnetMask','pSubnetMask'),
                         'DefaultGateway':('gateway','pGateway')}[suffix]
        if kind.startswith('CfgGet'):
            value=self.interfaces[device][field]
            if field=='gateway' and value=='0.0.0.0':block['status']=29009;return block
            if request['Len']<1:block['status']=29003;return block
            raw=value.encode('ascii')[:max(0,request['Len']-1)]+b'\0'
            try:self.runtime.vendor.write(request[pointer],raw)
            except ValueError:block['status']=29003
        else:
            if request['Option'] not in (0,1):block['status']=29002;return block
            try:
                value=str(IPv4Address(self.runtime.vendor.string(request[pointer])))
                if field=='subnetMask':IPv4Network('0.0.0.0/'+value)
                elif int(value.split('.')[0])>247:raise ValueError('Invalid IP range')
            except ValueError:block['status']=29003;return block
            self.interfaces[device][field]=value
            if request['Option']==1:self.nonvolatile[device][field]=value
        return block

    def publish_io(self):
        for channel in self.runtime.project.get('hardware',{}).get('channels',[]):
            if channel.get('direction')!='input' or channel.get('name')!='SerialNumber':continue
            value = self.seed['serialNumbers'].get(channel['moduleId'],0)
            try:
                record=self.runtime.memory.resolve(channel.get('variableId') or channel.get('variable'))
                if not record.get('forced') and not record.get('constant'):
                    record['value']=self.runtime.memory.coerce(value,record['_spec'])
            except ValueError:continue

    def reset(self):
        self.configure(self.seed)

    def summary(self):
        return {'virtualOnly':True,'dateTime':self.now().isoformat(),'configuration':deepcopy(self.seed),
                'interfaces':deepcopy(self.interfaces),'battery':deepcopy(self.seed['battery']),
                'serialNumbers':deepcopy(self.seed['serialNumbers']),
                'clockMode':self.seed['clockMode'],
                'note':'RTC follows the PC local clock.' if self.seed['clockMode']=='pc' else 'Custom RTC advances with PLC simulation time.'}
