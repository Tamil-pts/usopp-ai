"""Stable Python entry point for the reusable offline B&R library.

Addresses belong exclusively to this session's bounded memory. No host device,
network, process or file is accessed by library calls. See SERVICE_SUPPORT.md.
"""
from copy import deepcopy
from pathlib import Path

from .core.catalog import load_catalog
from .core.runtime import VirtualRuntime,MAX_INSTRUCTIONS_PER_SCAN
from .core.compiler import IEC_BLOCKS
from .core.vendor import FILE_BLOCKS
from .core.cpu import BLOCKS as CPU_BLOCKS
from .core.vendor_services import BLOCKS as SERVICE_BLOCKS


def catalog():
    return load_catalog(Path(__file__).resolve().parents[1]/'knowledge/virtual_plc/br_catalog.json')


class BRLibrarySession:
    def __init__(self,variables=(),types=None,cpu=None):
        definitions=[dict(v,id=v.get('id','Library::'+v['name']),scope='Library') for v in variables]
        model={'name':'Python B&R library session','variables':definitions,'types':types or {},
               'programs':[{'id':'library-cycle','name':'Library','scope':'Library','source':'Library.st','language':'st','code':'PROGRAM _CYCLIC END_PROGRAM'}],
               'tasks':[{'id':'cycle','name':'Library cycle','intervalMs':10,'programs':['library-cycle']}]}
        if cpu:model['cpuServices']=cpu
        self.runtime=VirtualRuntime(model)
        if not self.runtime.run_allowed:raise ValueError('Invalid library session declarations: '+str(self.runtime.diagnostics))
        self.instances={};self._buffers=0

    def read(self,binding):return self.runtime.get_value(binding,'Library')

    def write(self,binding,value):
        self.runtime.set_value(binding,value,scope='Library',return_snapshot=False)

    def address(self,binding):
        record,ref=self.runtime.value_reference(binding,'Library')
        self.runtime._budget=MAX_INSTRUCTIONS_PER_SCAN
        return self.runtime.vendor.address(ref,record['scope'],None)

    def sizeof(self,binding):
        record,ref=self.runtime.value_reference(binding,'Library')
        return self.runtime.vendor.size(self.runtime.vendor.specification(ref,record['scope']))

    def buffer(self,size,data=None):
        self._buffers+=1
        return self.runtime.vendor.allocate(('python-session',self._buffers),size,data)

    def read_bytes(self,address,count):return self.runtime.vendor.read(address,count)

    def write_bytes(self,address,data):self.runtime.vendor.write(address,bytes(data))

    def call(self,name,*values):
        self.runtime._budget=MAX_INSTRUCTIONS_PER_SCAN
        return self.runtime._call({'op':'call','name':name,'args':[{'name':None,'output':False,'value':{'op':'literal','value':value}} for value in values]},'Library')

    def block(self,kind,instance='default',**inputs):
        kinds={str(k).casefold():k for k in list(IEC_BLOCKS)+list(FILE_BLOCKS)+list(CPU_BLOCKS)+list(SERVICE_BLOCKS)}
        if kind.casefold() not in kinds:raise ValueError('Function block has no Python implementation: '+kind)
        canonical=kinds[kind.casefold()];identity=(canonical,str(instance))
        if identity not in self.instances:
            name='_library_fb_'+str(len(self.instances)+1)
            if canonical in FILE_BLOCKS:
                typename={'FILEOPEN':'FileOpen','FILECREATE':'FileCreate','FILEREAD':'FileRead','FILEWRITE':'FileWrite','FILECLOSE':'FileClose','FILEDELETE':'FileDelete'}[canonical]
            else:typename=canonical
            self.runtime.memory.add({'id':'Library::'+name,'scope':'Library','name':name,'type':typename})
            self.instances[identity]=name
        name=self.instances[identity]
        self.runtime._budget=MAX_INSTRUCTIONS_PER_SCAN
        self.runtime._call({'op':'call','name':name,'args':[{'name':key,'output':False,'value':{'op':'literal','value':value}} for key,value in inputs.items()]},'Library')
        value=self.runtime.get_value(name,'Library')
        return {key:deepcopy(value) for key,value in value.items() if not key.startswith('_')}

    def scan(self,count=1):
        if type(count) is not int or not 1<=count<=10000:raise ValueError('Advance 1..10000 virtual scans')
        self.runtime.status='running'
        for _ in range(count):self.runtime.tick()
        self.runtime.status='paused'
        return self.runtime.time_ms

    def reset(self,cold=False):self.runtime.command('cold-reset' if cold else 'reset')
