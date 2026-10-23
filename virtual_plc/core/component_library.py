"""Account-owned component models and layouts. Vendor documents are references only."""
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import threading
import time
import uuid

from .components import CATALOG,validate_components
from .storage import atomic_json,bounded_json

MAX_REFERENCE=20*1024*1024
REFERENCE_TYPES={'.pdf','.dxf','.dwg','.edz','.elk','.zw1','.ema','.ems','.xml','.zip','.png','.jpg'}
PORT_TYPES={'AI','AO','DI','DO','COMM','POWER','OTHER'}


def text(value,name,limit,required=False):
    if not isinstance(value,str) or len(value)>limit or required and not value.strip():raise ValueError('Check '+name+'.')
    return value.strip()


def metadata(payload):
    result={name:text(payload.get(name,''),name,limit,name=='name') for name,limit in
            [('name',180),('manufacturer',120),('model',120),('description',4000)]}
    terminals=payload.get('terminals',[])
    if not isinstance(terminals,list) or len(terminals)>128:raise ValueError('Use at most 128 I/O or communication terminals.')
    result['terminals']=[]
    for terminal in terminals:
        if not isinstance(terminal,dict) or terminal.get('type') not in PORT_TYPES:raise ValueError('Select AI, AO, DI, DO, COMM, POWER or OTHER for each terminal.')
        result['terminals'].append({'type':terminal['type'],**{key:text(terminal.get(key,''),key,160) for key in ('terminal','signal','unit','protocol')}})
    return result


class ComponentLibrary:
    def __init__(self,root):self.root=Path(root);self.lock=threading.RLock()

    def folder(self,identity):
        if not isinstance(identity,str) or not re.fullmatch(r'[0-9a-f]{32}',identity):raise ValueError('Choose a saved component library item.')
        return self.root/identity

    def load(self,identity):
        try:
            path=self.folder(identity)/'item.json'
            if path.stat().st_size>5*1024*1024:raise ValueError('The library item exceeds its size limit.')
            return bounded_json(path)
        except FileNotFoundError:raise ValueError('This library item is unavailable for your account.') from None

    def list(self):
        result=[]
        if not self.root.exists():return result
        for path in self.root.glob('*/item.json'):
            try:
                item=self.load(path.parent.name)
                result.append({key:item[key] for key in ('id','name','manufacturer','model','description','terminals','updatedAt','references')}
                              |{'componentCount':len(item['components']),'layoutSaved':any('position' in component for component in item['components'])})
            except (OSError,ValueError,KeyError):continue
        return sorted(result,key=lambda item:item['updatedAt'],reverse=True)

    def save(self,payload,components,project=''):
        meta=metadata(payload)
        with self.lock:
            if len(self.list())>=500:raise ValueError('The component library has reached 500 saved items.')
            if not components:raise ValueError('Choose one or more existing components to save.')
            portable=deepcopy(components);selected={component['id'] for component in portable};hints={}
            for component in portable:
                hints[component['id']]=dict(component.get('bindings',{}))
                prior=component.get('evidence',{})
                component.update(enabled=False,bindings={},evidence={'mappingSource':'library-template','confidence':'review',
                                 **{key:prior[key] for key in ('manufacturer','model','libraryItem') if prior.get(key)}})
                component['links']={key:link for key,link in component.get('links',{}).items() if link['component'] in selected}
                if payload.get('includeLayout') is False:component.pop('position',None)
                component.pop('status',None);component.pop('ports',None);component.pop('current',None)
                if 'faultInjected' in component.get('config',{}):component['config']['faultInjected']=0
            portable=validate_components(portable)
            identity=uuid.uuid4().hex
            item={**meta,'id':identity,'schemaVersion':1,'createdAt':time.time(),'updatedAt':time.time(),
                  'components':portable,'bindingHints':hints,'sourceProject':str(project)[:180],'references':[]}
            atomic_json(self.folder(identity)/'item.json',item,5*1024*1024)
            return item

    def update(self,identity,payload):
        with self.lock:
            item=self.load(identity);item.update(metadata(payload),updatedAt=time.time())
            atomic_json(self.folder(identity)/'item.json',item,5*1024*1024);return item

    def instantiate(self,identity,runtime,match_exact=False,offset_x=0,offset_y=0):
        if type(match_exact) is not bool:raise ValueError('Choose whether to match exact PLC tags.')
        for value in (offset_x,offset_y):
            if type(value) not in {int,float} or not 0<=value<=12000:raise ValueError('Layout offsets must be in 0..12000.')
        item=self.load(identity);components=deepcopy(item['components'])
        ids={component['id']:'library-'+uuid.uuid4().hex[:24] for component in components}
        for component in components:
            original=component['id'];component['id']=ids[original]
            component['links']={key:{**link,'component':ids[link['component']]} for key,link in component.get('links',{}).items()}
            prior=component.get('evidence',{})
            component['evidence']={'mappingSource':'component-library','confidence':'review','libraryItem':identity,
                                   'manufacturer':prior.get('manufacturer') or item['manufacturer'],'model':prior.get('model') or item['model']}
            component['enabled']=False
            if 'position' in component:
                component['position']={'x':component['position']['x']+offset_x,'y':component['position']['y']+offset_y}
            if match_exact:
                ports={port['key']:port for model in CATALOG if model['kind']==component['kind'] for port in model['ports']}
                from .components import binding_reference
                for key,address in item.get('bindingHints',{}).get(original,{}).items():
                    try:
                        canonical,record,spec=binding_reference(runtime,address)
                        port=ports[key]
                        if spec.get('kind')=='scalar' and (spec.get('type')=='BOOL' if port['type']=='BOOL' else spec.get('type') in {'REAL','LREAL','BYTE','WORD','DWORD','USINT','UINT','UDINT','SINT','INT','DINT','TIME'}):
                            component['bindings'][key]=canonical
                    except (ValueError,KeyError,TypeError,IndexError):continue
        return validate_components(components,runtime)

    def attach(self,identity,filename,content):
        name=Path(str(filename).replace('\\','/')).name
        suffix=Path(name).suffix.casefold()
        if suffix not in REFERENCE_TYPES:raise ValueError('Choose a vendor PDF, drawing, EPLAN archive or image reference.')
        if not content or len(content)>MAX_REFERENCE:raise ValueError('Vendor references must be between 1 byte and 20 MB.')
        with self.lock:
            item=self.load(identity)
            if len(item['references'])>=5:raise ValueError('Keep at most five references per library item.')
            total=sum(reference['bytes'] for entry in self.list() for reference in entry['references'])
            if total+len(content)>250*1024*1024:raise ValueError('This account has reached the 250 MB library reference limit.')
            blob=uuid.uuid4().hex+suffix;folder=self.folder(identity)/'references';folder.mkdir(parents=True,exist_ok=True)
            (folder/blob).write_bytes(content)
            item['references'].append({'id':blob,'name':name[:200],'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),'use':'Reference only; confirm terminal and model data before applying it.'})
            item['updatedAt']=time.time();atomic_json(self.folder(identity)/'item.json',item,5*1024*1024)
            return item

    def reference(self,identity,reference_id):
        item=self.load(identity);reference=next((entry for entry in item['references'] if entry['id']==reference_id),None)
        if not reference:raise ValueError('Vendor reference not found.')
        return self.folder(identity)/'references'/reference['id'],reference['name']
