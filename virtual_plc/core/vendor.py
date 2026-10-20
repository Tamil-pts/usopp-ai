"""Bounded virtual implementations of documented B&R AsString and FileIO calls.

Addresses are handles into typed PLC memory, never native pointers. File devices
are in-memory simulation stores; no host file, USB device or network is opened.
The source specifications live in knowledge/br_help/AS12/Help-en/Data/libraries.
"""
from copy import deepcopy
import math
import re
import struct
from .cpu import rtc_fields

CALLS = {'ADR': (1, 1), 'SIZEOF': (1, 1), 'STRCPY': (2, 2), 'STRCAT': (2, 2),
         'STRLEN': (1, 1), 'STRCMP': (2, 2), 'ITOA': (2, 2), 'FTOA': (2, 2),
         'ATOI': (1, 1), 'ATOF': (1, 1), 'MEMCPY': (3, 3), 'MEMMOVE': (3, 3),
         'MEMSET': (3, 3), 'MEMCMP': (3, 3), 'FILEIOGETSYSERROR': (0, 0)}
ALIASES = {('BRS' + name): name for name in CALLS if name not in {'ADR', 'SIZEOF', 'FILEIOGETSYSERROR'}}
ALIASES['BRSMEMCOPY'] = 'MEMCPY'
FILE_BLOCKS = {
    'FILEOPEN': ({'enable': 'BOOL', 'pDevice': 'UDINT', 'pFile': 'UDINT', 'mode': 'USINT'},
                 {'status': 'UINT', 'ident': 'UDINT', 'filelen': 'UDINT'}),
    'FILECREATE': ({'enable': 'BOOL', 'pDevice': 'UDINT', 'pFile': 'UDINT'}, {'status': 'UINT', 'ident': 'UDINT'}),
    'FILEWRITE': ({'enable': 'BOOL', 'ident': 'UDINT', 'offset': 'UDINT', 'pSrc': 'UDINT', 'len': 'UDINT'}, {'status': 'UINT'}),
    'FILEREAD': ({'enable': 'BOOL', 'ident': 'UDINT', 'offset': 'UDINT', 'pDest': 'UDINT', 'len': 'UDINT'}, {'status': 'UINT'}),
    'FILECLOSE': ({'enable': 'BOOL', 'ident': 'UDINT'}, {'status': 'UINT'}),
    'FILEDELETE': ({'enable': 'BOOL', 'pDevice': 'UDINT', 'pName': 'UDINT'}, {'status': 'UINT'}),
}
FORMATS = {'BOOL': '?', 'SINT': 'b', 'USINT': 'B', 'BYTE': 'B', 'INT': 'h', 'UINT': 'H', 'WORD': 'H',
           'DINT': 'i', 'UDINT': 'I', 'DWORD': 'I', 'LINT': 'q', 'ULINT': 'Q', 'LWORD': 'Q',
           'REAL': 'f', 'LREAL': 'd', 'TIME': 'I', 'DATE_AND_TIME':'I', 'DT':'I'}
MAX_BYTES = 4 * 1024 * 1024


def byte_fields(spec):
    """Only explicitly documented B&R byte layouts; never infer arbitrary ABI."""
    fields = rtc_fields(spec)
    if fields:
        return fields
    fields = spec.get('fields', [])
    if isinstance(fields, dict):
        fields = [dict(name=k, type=v) if isinstance(v, str) else dict(name=k, **v) for k, v in fields.items()]
    expected = [('idle', 'UINT'), ('delimc', 'UINT'), ('delim', 'ARRAY[0..1] OF USINT'),
                ('tx_cnt', 'UINT'), ('rx_cnt', 'UINT'), ('tx_len', 'UINT'), ('rx_len', 'UINT'),
                ('argc', 'UINT'), ('argv', 'UDINT')]
    normalized = [(f.get('name'), re.sub(r'\s+', '', f.get('type', '')).upper()) for f in fields if isinstance(f.get('type'), str)]
    wanted = [(n, re.sub(r'\s+', '', t).upper()) for n, t in expected]
    return fields if spec.get('kind') == 'struct' and normalized == wanted else None


def support_catalog():
    from .cpu import CALLS as CPU_CALLS, BLOCKS as CPU_BLOCKS
    from .vendor_services import CALLS as SERVICE_CALLS, BLOCKS as SERVICE_BLOCKS
    prefix = 'knowledge/br_help/AS12/Help-en/Data/'
    from .catalog import load_catalog
    from pathlib import Path
    registry=load_catalog(Path(__file__).resolve().parents[2]/'knowledge/virtual_plc/br_catalog.json')
    return {'mode': 'bounded virtual implementations', 'nativeLibrariesLoaded': False,
            'registry':{'schemaVersion':registry['schemaVersion'],'documentedEntries':registry['entryCount'],'implementedInterfaces':len(registry['implementations']),'path':'knowledge/virtual_plc/br_catalog.json','api':'/api/virtual-plc/library-reference'},
            'functions': [{'name': name, 'arguments': list(arity),
                           'reference': prefix + ('libraries/fileio/fbks/fileiogetsyserror.html' if name == 'FILEIOGETSYSERROR' else
                                                  'libraries/asstring/fbks/' + name.lower() + '.html')}
                          for name, arity in CALLS.items() if name not in {'ADR', 'SIZEOF'}],
            'blocks': [{'name': name, 'inputs': list(inputs), 'outputs': list(outputs),
                        'reference': prefix + 'libraries/fileio/fbks/' + name.lower() + '.html'}
                       for name, (inputs, outputs) in FILE_BLOCKS.items()],
            'cpuFunctions': [{'name': name, 'arguments': list(arity), 'reference': prefix+'libraries/sys_lib/fbks/'+name.lower()+'.html'} for name,arity in CPU_CALLS.items()],
            'cpuBlocks': [{'name': name, 'inputs': list(inputs), 'outputs': list(outputs),
                          'reference': prefix+'libraries/'+('asarcfg' if name.startswith('Cfg') else 'astime' if name.startswith('DT') else 'brsystem')+'/fbks/'+name.lower()+'.html'} for name,(inputs,outputs) in CPU_BLOCKS.items()],
            'serviceFunctions': [{'name':name,'arguments':list(arity)} for name,arity in SERVICE_CALLS.items()],
            'serviceBlocks': [{'name':name,'inputs':list(inputs),'outputs':list(outputs)} for name,(inputs,outputs) in SERVICE_BLOCKS.items()],
            'serviceReference': 'virtual_plc/SERVICE_SUPPORT.md',
            'limitations': ['No host filesystem, USB, network or native library access.',
                            'CPU services use workspace RTC, Ethernet, battery and explicitly mapped virtual serial values. Reset/reopen restores configured seeds.',
                            'ADR/SIZEOF support declared scalars, fixed arrays, bounded STRINGs, SG4 IEC/C natural structure alignment and exact documented device records. Native FB internal byte layouts and custom packing remain opaque.',
                            'Virtual FileIO uses a one-scan busy handshake; it does not reproduce hardware I/O timing.',
                            'FTOA uses IEEE REAL and seven significant decimal digits; exact vendor CSV formatting is not asserted.']}


def register_types(types, case_sensitive=False):
    for kind, (inputs, outputs) in FILE_BLOCKS.items():
        canonical = {'FILEOPEN': 'FileOpen', 'FILECREATE': 'FileCreate', 'FILEWRITE': 'FileWrite',
                     'FILEREAD': 'FileRead', 'FILECLOSE': 'FileClose', 'FILEDELETE': 'FileDelete'}[kind]
        specification={'kind':'struct','libraryBlock':kind,'fields':{**inputs,**outputs}}
        types[canonical if case_sensitive else kind]=specification
        types[canonical+'_typ']=specification


def call_name(name):
    name = str(name).upper()
    return ALIASES.get(name, name)


class VendorRuntime:
    def __init__(self, runtime):
        self.runtime = runtime
        self.regions, self.by_key, self.next_address = [], {}, 65536
        self.files, self.handles, self.pending = {}, {}, {}
        self.next_handle, self.sys_error = 1, 0

    def array(self, spec):
        bounds = spec['bounds']
        if bounds and isinstance(bounds[0], (int, float)):
            bounds = [bounds]
        nested = {**spec, 'bounds': bounds[1:]} if len(bounds) > 1 else self.runtime.memory.spec(spec.get('elementType', spec.get('element')))
        return int(bounds[0][0]), int(bounds[0][1]) - int(bounds[0][0]) + 1, nested

    def size(self, spec):
        kind = spec.get('kind')
        if self.structured(spec):return self.c_layout(spec)[2]
        fields = byte_fields(spec)
        if fields: return sum(self.size(self.runtime.memory.spec(f['type'])) for f in fields)
        if kind == 'scalar' and spec.get('type') in FORMATS:
            return struct.calcsize('<' + FORMATS[spec['type']])
        if kind == 'string': return int(spec.get('length', 80)) + 1
        if kind == 'array':
            _, count, nested = self.array(spec)
            result = count * self.size(nested)
            if result > MAX_BYTES: raise ValueError('Virtual byte region exceeds 4 MiB')
            return result
        raise ValueError('Byte layout is unsupported for this type; structure packing is not guessed')

    def alignment(self,spec):
        if self.structured(spec):return self.c_layout(spec)[1]
        if spec.get('kind')=='array':return self.alignment(self.array(spec)[2])
        if spec.get('kind')=='string':return 1
        if byte_fields(spec):return max(self.alignment(self.runtime.memory.spec(f['type'])) for f in byte_fields(spec))
        return min(4,self.size(spec))

    def structured(self,spec):
        # SG4 IEC structures use the same natural 2/4-byte alignment as C.
        # See programming/mixiecandansic/...restrictions_pragma_pack.html.
        # Native FB internal layouts remain opaque.
        return bool(spec.get('cLayout') or (spec.get('kind')=='struct' and str(spec.get('source','')).lower().endswith('.typ') and not any(spec.get(k) for k in ('serviceBlock','cpuBlock','libraryBlock','functionBlock'))))

    def c_layout(self,spec):
        if spec.get('cLayout') and spec['cLayout']!={'pack':4,'pointerBytes':4,'byteOrder':'little'}:
            raise ValueError('Unsupported virtual C ABI')
        offset,alignment,fields=0,1,[]
        for field in self.runtime.memory.fields(spec):
            dtype=self.runtime.memory.spec(field['type']);align=self.alignment(dtype)
            offset=(offset+align-1)//align*align;alignment=max(alignment,align)
            fields.append((field['name'],offset,dtype));offset+=self.size(dtype)
        return fields,alignment,(offset+alignment-1)//alignment*alignment

    def field_offset(self,spec,member):
        if self.structured(spec):
            fields=self.c_layout(spec)[0]
        elif byte_fields(spec):
            offset,fields=0,[]
            for f in byte_fields(spec):
                dtype=self.runtime.memory.spec(f['type']);fields.append((f['name'],offset,dtype));offset+=self.size(dtype)
        else:raise ValueError('Structure has no explicit supported byte layout')
        found=next((f for f in fields if self.runtime.symbol_key(f[0])==self.runtime.symbol_key(member)),None)
        if not found:raise ValueError('Unknown byte-layout member: '+member)
        return found[1],found[2]

    def encode(self, value, spec):
        if self.structured(spec):
            fields,_,size=self.c_layout(spec);raw=bytearray(size)
            for name,offset,dtype in fields:raw[offset:offset+self.size(dtype)]=self.encode(value[name],dtype)
            return bytes(raw)
        fields = byte_fields(spec)
        if fields:return b''.join(self.encode(value[f['name']],self.runtime.memory.spec(f['type'])) for f in fields)
        if spec['kind'] == 'array':
            _, _, nested = self.array(spec)
            return b''.join(self.encode(item, nested) for item in value)
        if spec['kind'] == 'string':
            raw = value.encode('latin-1', errors='strict')
            return (raw + b'\0').ljust(self.size(spec), b'\0')
        if spec['kind'] == 'enum': return struct.pack('<i', int(value))
        value = int(value) if spec.get('type') == 'TIME' else value
        return struct.pack('<' + FORMATS[spec['type']], value)

    def decode(self, raw, spec):
        if self.structured(spec):
            return {name:self.decode(raw[offset:offset+self.size(dtype)],dtype) for name,offset,dtype in self.c_layout(spec)[0]}
        fields = byte_fields(spec)
        if fields:
            result,offset={},0
            for f in fields:
                member=self.runtime.memory.spec(f['type']);size=self.size(member)
                result[f['name']]=self.decode(raw[offset:offset+size],member);offset+=size
            return result
        if spec['kind'] == 'array':
            _, count, nested = self.array(spec)
            width = self.size(nested)
            return [self.decode(raw[i*width:(i+1)*width], nested) for i in range(count)]
        if spec['kind'] == 'string':
            if b'\0' not in raw: raise ValueError('Virtual STRING write has no terminator within its capacity')
            return raw.split(b'\0', 1)[0].decode('latin-1')
        if spec['kind'] == 'enum': return struct.unpack('<i', raw)[0]
        return struct.unpack('<' + FORMATS[spec['type']], raw)[0]

    def specification(self, expression, scope, frame=None):
        if expression.get('op') == 'ref':
            if frame and self.runtime.symbol_key(expression['name']) in frame['specs']:
                return self.runtime.memory.reference_spec(expression, scope, frame['specs'][self.runtime.symbol_key(expression['name'])])
            return self.runtime.memory.reference_spec(expression, scope)
        if expression.get('op') == 'literal' and isinstance(expression.get('value'), str):
            return {'kind': 'string', 'length': len(expression['value'])}
        raise ValueError('ADR/SIZEOF requires a declared value or a string literal')

    def address(self, expression, scope, frame):
        memory = self.runtime.memory
        if expression.get('op')=='ref':
            pointer=self.runtime._pointer_reference(expression,scope,frame)
            if pointer:return pointer[0]
        if expression.get('op') == 'literal':
            spec = self.specification(expression, scope, frame)
            key = ('literal', expression['value'])
            reference, constant = None, True
            raw = self.encode(expression['value'], spec)
            offset = 0
        else:
            local=frame and self.runtime.symbol_key(expression['name']) in frame['values']
            if local:
                key=('frame',frame['instance_path'],self.runtime.symbol_key(expression['name']))
                reference={'op':'ref','name':expression['name'],'path':[]}
                constant,spec=False,frame['specs'][self.runtime.symbol_key(expression['name'])]
            else:
                record = memory.resolve(expression['name'], scope)
                key, reference = record['id'], {'op': 'ref', 'name': record['id'], 'path': []}
                constant, spec = record.get('constant', False), record['_spec']
            raw, offset = None, 0
            remaining = expression.get('path', [])
            try:self.size(spec)
            except ValueError:
                # An opaque FB elsewhere in a containing structure cannot
                # define native offsets. Allocate the first independently
                # addressable typed subtree, preserving an array's full extent
                # so memcpy at ADR(array[index]) may span adjacent elements.
                # Prefix indexes are captured now: a later PLC index edit must
                # never retarget a pointer that has already been returned.
                if not expression.get('path'):raise
                prefix = []
                original_error = None
                for index, segment in enumerate(expression['path']):
                    frozen = {'index':{'op':'literal','value':self.runtime._eval(segment['index'],scope,frame)}} if 'index' in segment else deepcopy(segment)
                    prefix.append(frozen)
                    candidate = {**expression,'path':prefix}
                    try:
                        candidate_spec = self.specification(candidate,scope,frame)
                        self.size(candidate_spec)
                    except ValueError as error:
                        original_error = error
                        continue
                    reference={**reference,'path':deepcopy(prefix)}
                    spec=candidate_spec
                    key=(key,'member',repr(prefix))
                    remaining=expression['path'][index+1:]
                    break
                else:
                    raise original_error or ValueError('ADR has no supported typed byte region')
            current = spec
            for segment in remaining:
                if 'member' in segment:
                    delta,current=self.field_offset(current,segment['member']);offset+=delta
                    continue
                low, count, nested = self.array(current)
                index = self.runtime._eval(segment['index'], scope, frame)
                if type(index) is not int or not low <= index < low + count:
                    raise ValueError('ADR array index is out of bounds or non-integral')
                offset += (index - low) * self.size(nested)
                current = nested
        if key not in self.by_key:
            size = self.size(spec)
            if len(self.regions) >= 4096 or sum(row['size'] for row in self.regions) + size > MAX_BYTES:
                raise ValueError('Virtual address capacity exceeded')
            region = {'base': self.next_address, 'size': size, 'spec': spec, 'reference': reference,
                      'scope': scope, 'raw': raw, 'constant': constant,'frame':frame if expression.get('op')!='literal' and local else None}
            self.next_address += size + 16
            self.regions.append(region)
            self.by_key[key] = region
        if expression.get('op')!='literal' and local:self.by_key[key]['frame']=frame
        return self.by_key[key]['base'] + offset

    def frame_backing(self,frame,reference):
        backing=frame.get('backing')
        if not backing:return None
        parent=backing['reference']
        path=parent.get('path',[])+([] if backing.get('whole') else [{'member':reference['name']}])+reference.get('path',[])
        target={'op':'ref','name':parent['name'],'path':path}
        if backing.get('frame'):return self.frame_backing(backing['frame'],target)
        return target,backing['scope']

    def region_reference(self,region):
        frame=region.get('frame')
        if frame and frame.get('active') is False:
            backing=self.frame_backing(frame,region['reference'])
            if not backing:raise ValueError('Pointer to a completed function frame is no longer valid')
            return backing[0],backing[1],None
        return region['reference'],region['scope'],frame

    def region(self, address, count=0):
        if type(address) is not int or type(count) is not int or not 0 <= count <= MAX_BYTES:
            raise ValueError('Virtual pointer and byte length must be bounded integers')
        for region in self.regions:
            offset = address - region['base']
            if 0 <= offset < region['size'] and offset + count <= region['size']:
                return region, offset
        raise ValueError('Pointer is outside allocated PLC memory')

    def allocate(self, key, count, raw=None):
        """Allocate a bounded library-owned byte region, separate from PLC ADR."""
        if type(count) is not int or not 1 <= count <= MAX_BYTES:
            raise ValueError('Virtual library buffer length is out of range')
        identity = ('library', key)
        if identity in self.by_key:
            region = self.by_key[identity]
            if region['size'] != count:
                raise ValueError('A live virtual library buffer cannot change capacity')
            return region['base']
        if len(self.regions) >= 4096 or sum(r['size'] for r in self.regions) + count > MAX_BYTES:
            raise ValueError('Virtual address capacity exceeded')
        data = bytes(count) if raw is None else bytes(raw)
        if len(data) != count:
            raise ValueError('Initial virtual byte buffer has the wrong length')
        region = {'base': self.next_address, 'size': count, 'spec': None, 'reference': None,
                  'scope': '', 'raw': data, 'constant': False, 'libraryOwned': True}
        self.next_address += count + 16
        self.regions.append(region)
        self.by_key[identity] = region
        return region['base']

    def release(self, key):
        region = self.by_key.pop(('library', key), None)
        if region is not None:
            self.regions.remove(region)

    def read(self, address, count):
        region, offset = self.region(address, count)
        raw = region['raw'] if region['reference'] is None else self.encode(self.runtime._read(*self.region_reference(region)), region['spec'])
        return raw[offset:offset+count]

    def write(self, address, raw):
        region, offset = self.region(address, len(raw))
        if region['constant']: raise ValueError('Cannot write a constant or string literal through ADR')
        current = bytearray(self.read(region['base'], region['size']))
        current[offset:offset+len(raw)] = raw
        if region.get('libraryOwned'):
            region['raw'] = bytes(current)
            return
        value = self.decode(current, region['spec'])
        reference,scope,frame=self.region_reference(region)
        self.runtime._write(reference,value,scope,frame)

    def string(self, address):
        region, offset = self.region(address)
        raw = self.read(address, region['size']-offset)
        if b'\0' not in raw: raise ValueError('Virtual string pointer has no bounded terminator')
        return raw.split(b'\0', 1)[0].decode('latin-1')

    def call(self, name, args, scope, frame, language='st'):
        brs = str(name).upper().startswith('BRS')
        name = call_name(name)
        if not CALLS[name][0] <= len(args) <= CALLS[name][1] or any(arg.get('name') or arg.get('output') for arg in args):
            raise ValueError(name + ' has an unsupported argument interface')
        if name == 'ADR': return self.address(args[0]['value'], scope, frame)
        if name == 'SIZEOF': return self.size(self.specification(args[0]['value'], scope, frame))
        pointer_arguments={'STRCPY':{0,1},'STRCAT':{0,1},'STRCMP':{0,1},'MEMCMP':{0,1},'MEMCPY':{0,1},'MEMMOVE':{0,1},'STRLEN':{0},'ATOI':{0},'ATOF':{0},'MEMSET':{0},'ITOA':{1},'FTOA':{1}}
        values=[]
        for index,arg in enumerate(args):
            expression=arg['value'];decay=False
            if index in pointer_arguments.get(name,set()) and (expression.get('op')=='literal' or (language=='c' and expression.get('op')=='ref')):
                try:decay=self.specification(expression,scope,frame).get('kind') in {'string','array'}
                except ValueError:pass
            values.append(self.address(expression,scope,frame) if decay else self.runtime._eval(expression,scope,frame))
        if name == 'FILEIOGETSYSERROR': return self.sys_error
        if name in {'STRCPY', 'STRCAT'}:
            raw = ((self.string(values[0]) if name == 'STRCAT' else '') + self.string(values[1])).encode('latin-1')
            self.write(values[0], raw + b'\0')
            return values[0] if language == 'c' and not brs else values[0] + len(raw)
        if name in {'ITOA', 'FTOA'}:
            if not isinstance(values[0], (int, float)) or not math.isfinite(values[0]): raise ValueError('Conversion requires a finite number')
            if name == 'FTOA':
                real = struct.unpack('<f', struct.pack('<f', values[0]))[0]
                raw = format(real, '.7g').encode('ascii')
                self.write(values[1], raw+b'\0')
                return len(raw)
            if values[0] != int(values[0]) or not -2147483648 <= values[0] <= 2147483647: raise ValueError('ITOA requires a DINT')
            raw = str(int(values[0])).encode('ascii'); self.write(values[1], raw+b'\0'); return len(raw)
        if name == 'STRLEN': return len(self.string(values[0]))
        if name == 'STRCMP':
            left, right = self.string(values[0]), self.string(values[1]); return (left > right) - (left < right)
        if name in {'ATOI', 'ATOF'}:
            pattern = r'\s*([+-]?\d+)' if name == 'ATOI' else r'\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)'
            match = re.match(pattern, self.string(values[0])); return (int if name == 'ATOI' else float)(match[1]) if match else 0
        dest, value, count = values
        self.region(dest, count)
        if name == 'MEMCMP':
            left, right = self.read(dest, count), self.read(value, count); return (left > right) - (left < right)
        if name == 'MEMSET':
            if type(value) is not int or not 0 <= value <= 255: raise ValueError('MEMSET requires a USINT fill value')
            raw = bytes([value])*count
        else:
            self.region(value, count)
            if name == 'MEMCPY' and count and max(dest, value) < min(dest+count, value+count):
                raise ValueError('MEMCPY regions overlap; use MEMMOVE')
            raw = self.read(value, count)
        self.write(dest, raw)
        return dest + count if name == 'MEMMOVE' or (name == 'MEMCPY' and (language != 'c' or brs)) or (name == 'MEMSET' and brs) else dest

    def file_block(self, kind, key, block):
        """One-scan busy handshake and bounded virtual files, never host I/O."""
        block = deepcopy(block)
        if not block['enable'] and key not in self.pending:
            self.pending.pop(key, None); block['status'] = 65534; return block
        if key not in self.pending:
            self.pending[key] = self.runtime.scan_count
            block['status'] = 65535
            return block
        if self.pending[key] == self.runtime.scan_count:
            block['status'] = 65535; return block
        self.pending.pop(key, None)
        block['status'] = 0
        if kind in {'FILEOPEN', 'FILECREATE', 'FILEDELETE'}:
            try:
                device = self.string(block['pDevice'])
            except ValueError:
                block['status'] = 20709; return block
            try:
                filename = self.string(block['pName'] if kind == 'FILEDELETE' else block['pFile']).replace('\\', '/')
            except ValueError:
                block['status'] = 20700; return block
            if not device or len(device) > 80: block['status'] = 20709; return block
            if not filename or len(filename) > 255 or filename.startswith('/') or ':' in filename or '..' in filename.split('/'):
                block['status'] = 20700; return block
            path = (device, filename.casefold())
            if kind == 'FILEDELETE':
                if path not in self.files: block['status'] = 20708
                elif any(handle[0] == path for handle in self.handles.values()): block['status'] = 20706
                else: self.files.pop(path)
                return block
            if len(self.handles) >= 64: block['status'] = 20702; return block
            if kind == 'FILECREATE':
                if path in self.files: block['status'] = 20705; return block
                if len(self.files) >= 128: block['status'] = 20710; return block
                self.files[path] = bytearray()
            elif path not in self.files:
                block['status'] = 20708; return block
            # Access-mode numeric values vary with old library constants. Only
            # the declared modes used by the project may establish permissions.
            mode = block.get('mode')
            if kind == 'FILEOPEN' and mode not in {0, 1, 2}:
                block['status'] = 20707; return block
            handle = self.next_handle; self.next_handle += 1
            self.handles[handle] = (path, mode if kind == 'FILEOPEN' else 2)
            block['ident'] = handle
            if 'filelen' in block: block['filelen'] = len(self.files[path])
        else:
            handle = self.handles.get(block['ident'])
            if not handle: block['status'] = 20721; return block
            path, mode = handle
            if kind == 'FILECLOSE': self.handles.pop(block['ident']); return block
            offset, count = int(block['offset']), int(block['len'])
            if offset < 0 or offset+count > MAX_BYTES: block['status'] = 20711; return block
            if kind == 'FILEWRITE':
                if mode == 0: block['status'] = 20706; return block
                try:
                    raw = self.read(block['pSrc'], count)
                except ValueError:
                    block['status'] = 20719; return block
                target = self.files[path]
                growth = max(0, offset + count - len(target))
                if sum(map(len, self.files.values())) + growth > 16*1024*1024: block['status'] = 20710; return block
                target.extend(b'\0'*growth); target[offset:offset+count] = raw
            elif kind == 'FILEREAD':
                if mode == 1: block['status'] = 20706; return block
                raw = self.files[path][offset:offset+count]
                if len(raw) != count: block['status'] = 20711; return block
                try:
                    self.write(block['pDest'], raw)
                except ValueError:
                    block['status'] = 20719; return block
        return block

    def reset(self, cold=False):
        # PLC record identities/layouts survive warm reset. Keep their address
        # mapping so a retained UDINT cannot silently select a different record.
        if cold:
            self.regions.clear(); self.by_key.clear(); self.next_address = 65536
        self.pending.clear(); self.handles.clear()
        if cold: self.files.clear()

    def summary(self):
        return {'mode': 'virtual memory files', 'hostIO': False,
                'files': [{'device': key[0], 'name': key[1], 'bytes': len(value)} for key, value in self.files.items()],
                'openHandles': len(self.handles)}
