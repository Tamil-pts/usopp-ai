"""Offline CAN, CANopen and Modbus models using documented public interfaces.

No physical telegrams are sent. Unconfigured remote nodes return the actual
no-data/timeout statuses. Tests or commissioning components may configure
virtual nodes explicitly; successful reads then return their real stored bytes.
References: bundled libraries/{can_lib,ascanopen,drv_mbus}/fbks and gen/err*.
"""
from collections import deque
from copy import deepcopy

BLOCKS={
 'CANopen':({'enable':'BOOL','baud_rate':'USINT','cob_anz':'UINT','error_adr':'UDINT','device':'UDINT','info':'UINT'},{'us_ident':'UDINT','status':'UINT'}),
 'CANread':({'enable':'BOOL','us_ident':'UDINT','can_id':'UDINT','data_adr':'UDINT'},{'data_lng':'USINT','status':'UINT'}),
 'CANwrite':({'enable':'BOOL','us_ident':'UDINT','can_id':'UDINT','data_adr':'UDINT','data_lng':'USINT'},{'status':'UINT'}),
 'CANopenNMT':({'enable':'BOOL','pDevice':'UDINT','node':'USINT','state':'UINT'},{'status':'UINT','error':'UINT'}),
 'CANopenSDORead8':({'enable':'BOOL','pDevice':'UDINT','node':'USINT','index':'UINT','subindex':'USINT'},
     {'status':'UINT','error':'UINT','errorinfo':'UDINT',**{'data'+str(i):'USINT' for i in range(8)},'datalen':'USINT'}),
 'CANopenSDOWrite8':({'enable':'BOOL','pDevice':'UDINT','node':'USINT','index':'UINT','subindex':'USINT',**{'data'+str(i):'USINT' for i in range(8)},'datalen':'USINT'},
     {'status':'UINT','error':'UINT','errorinfo':'UDINT'}),
 'MBMOpen':({'enable':'BOOL','pDevice':'UDINT','pMode':'UDINT','pConfig':'UDINT','timeout':'UINT','ascii':'USINT'},{'status':'UINT','ident':'UDINT'}),
 'MBMaster':({'enable':'BOOL','ident':'UDINT'},{'status':'UINT','execute':'BOOL','recordnum':'UINT'}),
 'MBMCmd':({'enable':'BOOL','ident':'UDINT','mfc':'USINT','node':'USINT','data':'UDINT','offset':'UINT','len':'UINT'},{'status':'UINT'}),
 'MBMClose':({'enable':'BOOL','ident':'UDINT'},{'status':'UINT'}),
}


class FieldbusRuntime:
    def __init__(self,services):
        self.services=services;self.runtime=services.runtime
        self.ports={};self.can_nodes={};self.modbus_nodes={};self.waiting={}
        self.outbox=deque(maxlen=1000);self.inbox=deque(maxlen=1000)

    def configure_can_node(self,device,node,objects):
        if not 1<=node<=127:raise ValueError('CANopen node must be 1..127')
        self.can_nodes[(device,node)]={key:bytes(value) for key,value in objects.items()}

    def block(self,kind,key,block):
        b=deepcopy(block);vendor=self.runtime.vendor
        if not b['enable']:self.waiting.pop(key,None);b['status']=65534;return b
        if kind in {'CANopen','MBMOpen'}:
            try:device=vendor.string(b['device'] if kind=='CANopen' else b['pDevice'])
            except ValueError:device=''
            if not device:raise ValueError(kind+' requires a valid declared virtual interface string')
            if kind=='MBMOpen' and (b['timeout']<250 or b['timeout']%10 or b['ascii'] not in (0,1)):
                b['status']=20220;return b
            ident=next((i for i,p in self.ports.items() if p['key']==key),None)
            if ident is None:
                ident=self.services.ident();self.ports[ident]={'device':device,'key':key,'timeout':b.get('timeout',1000),'kind':kind}
            b['us_ident' if kind=='CANopen' else 'ident']=ident;b['status']=0;return b
        if kind.startswith('CANopen'):
            device=vendor.string(b['pDevice']);node=self.can_nodes.get((device,b['node']))
            if key not in self.waiting:self.waiting[key]=self.runtime.scan_count;b['status']=65535;return b
            if self.waiting[key]==self.runtime.scan_count:b['status']=65535;return b
            self.waiting.pop(key,None)
            if node is None:
                b.update(status=30811,error=30811)
                if 'errorinfo' in b:b['errorinfo']=0x05040000
                return b
            if kind=='CANopenNMT':
                self.outbox.append({'device':device,'node':b['node'],'nmt':b['state']});b.update(status=0,error=0);return b
            address=(b['index'],b['subindex'])
            if kind=='CANopenSDORead8':
                data=node.get(address)
                if data is None:b.update(status=30811,error=30811,errorinfo=0x06020000);return b
                if len(data)>8:raise ValueError('CANopenSDORead8 object exceeds 8 bytes')
                for i in range(8):b['data'+str(i)]=data[i] if i<len(data) else 0
                b['datalen']=len(data)
            else:
                if not 1<=b['datalen']<=8:raise ValueError('CANopenSDOWrite8 requires 1..8 bytes')
                node[address]=bytes(b['data'+str(i)] for i in range(b['datalen']))
            b.update(status=0,error=0,errorinfo=0);return b
        ident=b.get('us_ident',b.get('ident'));port=self.ports.get(ident)
        if port is None:b['status']=8805 if kind.startswith('CAN') else 20210;return b
        if kind=='CANread':
            frame=next((f for f in self.inbox if f['device']==port['device'] and f['id']==b['can_id']),None)
            if frame is None:b['status']=8877;return b
            vendor.write(b['data_adr'],frame['data']);b.update(status=0,data_lng=len(frame['data']));self.inbox.remove(frame);return b
        if kind=='CANwrite':
            if not 0<=b['data_lng']<=8:raise ValueError('CAN frames cannot exceed 8 bytes')
            self.outbox.append({'device':port['device'],'id':b['can_id'],'data':vendor.read(b['data_adr'],b['data_lng'])});b['status']=0;return b
        if kind=='MBMClose':self.ports.pop(ident);b['status']=0;return b
        start=self.waiting.setdefault(key,self.runtime.time_ms)
        if kind=='MBMCmd':
            node=self.modbus_nodes.get((port['device'],b['node']))
            if node is not None:
                offset,count=b['offset'],b['len'];function=b['mfc']
                if function in {3,4}:
                    if any(offset+i not in node for i in range(count)):raise ValueError('Requested Modbus register is absent from the configured virtual node')
                    raw=b''.join(int(node[offset+i]).to_bytes(2,'little') for i in range(count));vendor.write(b['data'],raw)
                elif function in {6,16}:
                    raw=vendor.read(b['data'],count*2)
                    for i in range(count):node[offset+i]=int.from_bytes(raw[2*i:2*i+2],'little')
                else:raise ValueError('Virtual MBMCmd supports register functions 3,4,6,16')
                b['status']=0;self.waiting.pop(key,None);return b
        b['status']=20220 if self.runtime.time_ms-start>=port['timeout'] else 65535
        if kind=='MBMaster':b['execute']=False
        if b['status']==20220:self.waiting.pop(key,None)
        return b

    def reset(self):
        self.ports.clear();self.waiting.clear();self.outbox.clear();self.inbox.clear()
