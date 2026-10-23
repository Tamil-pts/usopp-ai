"""Single-value edits carried in a source-mapped, complete SpinConnect group."""
from decimal import Decimal, InvalidOperation
import math
import struct
from backend.core.nami_simulator import frame

FORMATS={'BOOL':'B','USINT':'B','SINT':'b','BYTE':'B','UINT':'H','INT':'h','WORD':'H',
         'UDINT':'I','DINT':'i','DWORD':'I','REAL':'f','LREAL':'d','TIME':'I'}
RESULTS={10:'Invalid end marker',11:'Checksum error',12:'Unsupported function',13:'Incomplete frame',
         14:'Unsupported group',16:'PLC rejected one or more parameter values; earlier fields may have been applied',
         18:'Machine state does not permit settings writes'}


def integer(value, label, minimum=0, maximum=65535):
    if type(value) is not int or not minimum<=value<=maximum: raise ValueError(f'Invalid {label}.')
    return value


def select_field(mapping, row, variant_id):
    if not isinstance(mapping,dict) or len(str(mapping))>2_000_000: raise ValueError('Load the generated write_mapping.json (up to 2 MB).')
    doc=mapping.get('dataInspect',{})
    if not isinstance(doc,dict) or doc.get('schema')!=1: raise ValueError('Generate a new write mapping in ByteMap; this file has no DataInspect edit layout.')
    if row.get('isWritable') is not True: raise ValueError('This parameter is not marked IS_WRITABLE = YES.')
    gc=integer(row.get('groupCode'),'group code');offset=integer(row.get('offset'),'metadata offset')
    if gc in (10,11): raise ValueError('Protocol control groups cannot be edited as settings.')
    groups=doc.get('groups')
    if not isinstance(groups,list) or any(not isinstance(g,dict) for g in groups):raise ValueError('Invalid mapped groups.')
    group=next((g for g in groups if g.get('code')==gc),None)
    if not group: raise ValueError(f'The write mapping does not include GC {gc}.')
    variants=group.get('variants')
    if not isinstance(variants,list) or any(not isinstance(v,dict) for v in variants):raise ValueError('Invalid layout variants.')
    variant=next((v for v in variants if v.get('id')==variant_id),None)
    if not variant: raise ValueError('Select the write layout matching the machine configuration.')
    if variant.get('issues'): raise ValueError('Resolve the source layout findings: '+'; '.join(variant['issues']))
    size=integer(variant.get('payloadBytes'),'write payload size',1,60000)
    read_size=integer(variant.get('readPayloadBytes'),'read payload size',1,60000)
    fields=variant.get('fields')
    if not isinstance(fields,list) or not 1<=len(fields)<=3000: raise ValueError('Invalid write fields.')
    occupied=set()
    for field in fields:
        if not isinstance(field,dict) or not isinstance(field.get('sourceSlots'),list) or any(not isinstance(s,dict) for s in field['sourceSlots']):raise ValueError('Invalid source field mapping.')
        width=integer(field.get('size'),'field width',1,60000)
        w=integer(field.get('writeOffset'),'write offset');r=integer(field.get('readOffset'),'read offset')
        if w+width>size or r+width>read_size or field.get('readPayloadBytes')!=read_size: raise ValueError('The field crosses its group payload boundary.')
        indexes=set(range(w,w+width))
        if occupied & indexes: raise ValueError('Write fields overlap.')
        occupied.update(indexes)
    if occupied!=set(range(size)): raise ValueError('The complete group write layout is required; gaps cannot be zero-filled.')
    kind=str(row.get('dataType','')).upper()
    width=struct.calcsize(FORMATS[kind]) if kind in FORMATS else None
    # Match numeric identity/offset to the project's read-service source slots.
    candidates=[f for f in fields if f.get('writable') is True and any(s.get('offset')==offset and s.get('size')==width for s in f.get('sourceSlots',[]))]
    if len(candidates)!=1: raise ValueError('This metadata offset has no unique writable source field. Check the workbook and selected project layout.')
    field=candidates[0]
    if row.get('arraySize') not in (None,0,1) or field['type'] not in FORMATS:
        raise ValueError('This editor supports scalar numeric and Boolean parameters. Use the project tool for strings or arrays.')
    if struct.calcsize(FORMATS[field['type']])!=field['size']: raise ValueError('The source datatype width does not match its copy size.')
    return variant,field


def unpack(raw, field, byte_order):
    value=struct.unpack_from(('<' if byte_order=='little' else '>')+FORMATS[field['type']],raw,field['readOffset'])[0]
    if not math.isfinite(value): raise ValueError('The current PLC value is not finite. Check the metadata and byte order.')
    return value


def encode(value, field, byte_order, row):
    if isinstance(value,bool) or value is None or not str(value).strip() or len(str(value))>100: raise ValueError('Enter a finite PLC value (up to 100 characters).')
    try: numeric=Decimal(str(value))
    except InvalidOperation as exc: raise ValueError('Enter a valid number.') from exc
    if not numeric.is_finite(): raise ValueError('Enter a finite PLC value.')
    if field['type'] not in ('REAL','LREAL') and numeric!=numeric.to_integral_value(): raise ValueError('This PLC datatype requires an integer.')
    if field['type']=='BOOL' and numeric not in (0,1): raise ValueError('BOOL accepts only 0 or 1.')
    # Source-generated limits are already in native PLC units. Dynamic HMI
    # expressions stay enforced by the generated PLC code, never evaluated here.
    for lo,hi in ((field.get('min'),field.get('max')),(row.get('min'),row.get('max'))):
        for limit,operator in ((lo,'min'),(hi,'max')):
            if limit is None: continue
            try: bound=Decimal(str(limit))
            except InvalidOperation: continue
            if not bound.is_finite(): raise ValueError('The parameter limits are invalid.')
            if operator=='min' and numeric<bound: raise ValueError(f'Value must be at least {bound} PLC units.')
            if operator=='max' and numeric>bound: raise ValueError(f'Value must be at most {bound} PLC units.')
    try:
        raw=struct.pack(('<' if byte_order=='little' else '>')+FORMATS[field['type']],float(numeric) if field['type'] in ('REAL','LREAL') else int(numeric))
        represented=struct.unpack(('<' if byte_order=='little' else '>')+FORMATS[field['type']],raw)[0]
        if not math.isfinite(represented): raise ValueError('Value exceeds the PLC datatype range.')
        return raw,represented
    except (OverflowError,struct.error) as exc: raise ValueError('Value exceeds the PLC datatype range.') from exc


def build_write(machine_id, group, baseline, variant, selected, replacement):
    if len(baseline)!=variant['readPayloadBytes']: raise ValueError('The write-port read length does not match the reviewed mapping.')
    result=bytearray(variant['payloadBytes'])
    for field in variant['fields']:
        w,r,width=field['writeOffset'],field['readOffset'],field['size']
        result[w:w+width]=baseline[r:r+width]
    start=selected['writeOffset']
    result[start:start+selected['size']]=replacement
    return frame(machine_id,group.to_bytes(2,'big')+result,2)


def checked_payload(result, expected_size=None):
    if not result.get('success'): raise ValueError(result.get('error') or 'No valid PLC response.')
    raw=bytes(result.get('rawBytes',[]))
    if len(raw)<7 or raw[2]!=0: raise ValueError(RESULTS.get(raw[2] if len(raw)>2 else -1,'PLC rejected the request.'))
    size=int.from_bytes(raw[3:5],'big')
    if len(raw)!=size+7 or (expected_size is not None and size!=expected_size):
        raise ValueError(f'PLC returned {size} payload bytes; the reviewed write-port layout requires {expected_size}. Check the installed program version.')
    return raw[5:-2]
