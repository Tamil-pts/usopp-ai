from __future__ import annotations
import hashlib
import os
import tempfile
from threading import RLock
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from backend.core.runtime import (
    KNOWLEDGE,
    MASTER_PARAM_FILE,
    csv,
    io,
    json,
    log,
    project_kb_file,
)

from backend.core.runtime import _local_path, _local_session

router = APIRouter(tags=['Knowledge Base'])
_master_lock = RLock()


@router.get('/api/knowledge/data-model-rules')
def data_model_rules(request:Request):
    from backend.core.data_model_rules import load_rules
    data,revision=load_rules(KNOWLEDGE/'master/data_model_rules.json')
    return {**data,'revision':revision,'canEdit':request.state.user.get('role')=='admin'}


@router.put('/api/knowledge/data-model-rules')
def save_data_model_rules(payload:dict,request:Request):
    if request.state.user.get('role')!='admin':raise HTTPException(403,'Only Admin can change shared reference rules.')
    from backend.core.data_model_rules import load_rules,validate_rules
    from backend.core.run_history import write_json
    try:config=validate_rules(payload)
    except ValueError as error:raise HTTPException(400,str(error))
    if len(json.dumps(config).encode())>262144:raise HTTPException(400,'Reference rules must be smaller than 256 KB.')
    path=KNOWLEDGE/'master/data_model_rules.json'
    with _master_lock:
        _,revision=load_rules(path)
        if payload.get('revision')!=revision:raise HTTPException(409,'Reference rules changed elsewhere. Reopen the editor.')
        write_json(path,config)
    return data_model_rules(request)


@router.get('/api/knowledge/units')
def get_unit_rules():
    from python_engine.unit_rules import load_unit_rules
    data, revision = load_unit_rules(KNOWLEDGE/'master'/'unit_rules.json')
    return {**data, 'revision': revision}


@router.put('/api/knowledge/units')
def save_unit_rules(payload: dict, request: Request):
    from python_engine.unit_rules import load_unit_rules, validate_unit_rules
    if request.state.user.get('role') != 'admin':
        raise HTTPException(403, 'Only Admin can change shared metadata unit rules.')
    try:
        data = validate_unit_rules(payload)
    except ValueError as error:
        raise HTTPException(400, str(error))
    path = KNOWLEDGE/'master'/'unit_rules.json'
    with _master_lock:
        _, revision = load_unit_rules(path)
        if revision != payload.get('revision'):
            raise HTTPException(409, 'Unit rules changed elsewhere. Reload before saving.')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
                temporary = stream.name
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary): os.unlink(temporary)
    return get_unit_rules()


@router.post('/api/knowledge/units/preview')
def preview_unit_rule(payload: dict):
    from python_engine.unit_rules import validate_unit_rules, resolve_unit
    try:
        config = validate_unit_rules(payload)
        name = payload.get('parameter')
        if not isinstance(name, str) or not name.strip() or len(name) > 300:
            raise ValueError('Enter a parameter name of at most 300 characters.')
        return resolve_unit(config, name, str(payload.get('department') or 'All'), payload.get('existingUnit'))
    except ValueError as error:
        raise HTTPException(400, str(error))

def _read_master(path=None):
    path = path or MASTER_PARAM_FILE
    raw = path.read_bytes() if path.exists() else b'{"version":"1.0","mappings":[]}'
    data = json.loads(raw.decode('utf-8-sig'))
    if isinstance(data, list):
        data = {'version': '1.0', 'mappings': data}
    for row in data.get('mappings', []):
        if isinstance(row, dict):
            row['machine_department'] = str(row.get('machine_department') or 'All').strip() or 'All'
    return data, hashlib.sha256(raw).hexdigest()

def _write_master(data, revision, path=None):
    path = path or MASTER_PARAM_FILE
    with _master_lock:
        _, current = _read_master(path)
        if revision != current:
            raise HTTPException(409, 'Mappings changed elsewhere. Reload the table before saving.')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
                temporary = stream.name
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        saved, revision = _read_master(path)
        return {**saved, 'revision': revision}

@router.put('/api/knowledge/master')
def knowledge_master_save(payload: dict):
    rows = payload.get('mappings')
    if not isinstance(rows, list):
        raise HTTPException(400, 'Mappings must be a list.')
    with _master_lock:
        data, _ = _read_master()
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise HTTPException(400, f'Row {index}: mapping must be an object.')
            if any(not isinstance(row.get(key), str) or not row[key].strip() for key in ('plc_parameter', 'metadata_parameter')):
                # Keep untouched legacy entries; require names for new or edited rows.
                if row not in data.get('mappings', []):
                    raise HTTPException(400, f'Row {index}: PLC Parameter and Metadata Parameter are required.')
        data['mappings'] = rows
        result = _write_master(data, payload.get('revision'))
    log.info('KNOWLEDGE_MASTER_TABLE_SAVED rows=%d', len(rows))
    return result

@router.post('/api/local/knowledge/master/csv')
async def local_knowledge_master_csv(payload:dict):
    path=_local_path(payload.get('path',''),True,False)
    if not path.is_file() or path.suffix.lower()!='.csv': raise HTTPException(400,'Select a CSV mapping file.')
    upload=UploadFile(filename=path.name,file=io.BytesIO(path.read_bytes()))
    result=await knowledge_master_csv(upload,mode=payload.get('mode','merge'),revision=payload.get('revision'))
    return {**result,'localMode':True}
@router.get('/api/knowledge/master')
def knowledge_master():
    try:
        data, revision = _read_master()
        return {**data, 'revision': revision}
    except Exception:
        log.exception('KNOWLEDGE_MASTER_READ_ERROR')
        raise HTTPException(500,'Master knowledge configuration could not be loaded.')
@router.post('/api/knowledge/master/csv')
async def knowledge_master_csv(file: UploadFile = File(...),mode: str = Form('merge'),revision: str | None = Form(None)):
    """Replace/add global parameter mappings from a simple CSV template.

    Required columns are PLC_PARAMETER, PLC_TAG, METADATA_PARAMETER.
    Mappings with the same parameter, tag and metadata identity are updated.
    """
    if mode not in {'merge','replace'}:raise HTTPException(400,'Choose merge or replace import mode.')
    name=(file.filename or '').lower()
    if not name.endswith('.csv'):
        raise HTTPException(400,'Please upload a CSV mapping file.')
    raw=await file.read()
    try:
        text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text=raw.decode('utf-8',errors='replace')
    reader=csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400,'CSV is empty or has no header row.')
    normalized={str(h).strip().upper():h for h in reader.fieldnames if h is not None}
    required={'PLC_PARAMETER','PLC_TAG','METADATA_PARAMETER'}
    missing=required-set(normalized)
    if missing:
        raise HTTPException(400,'Missing CSV columns: '+', '.join(sorted(missing)))
    data, current_revision = _read_master()
    if mode=='replace' and revision!=current_revision:raise HTTPException(409,'Reload the table before replacing mappings.')
    if isinstance(data,list): data={'version':'1.0','mappings':data}
    mappings=[] if mode=='replace' else data.setdefault('mappings',[])
    imported=0
    for line,row in enumerate(reader,2):
        plc_parameter=str(row.get(normalized['PLC_PARAMETER'],'') or '').strip()
        plc_tag=str(row.get(normalized['PLC_TAG'],'') or '').strip()
        metadata_parameter=str(row.get(normalized['METADATA_PARAMETER'],'') or '').strip()
        if not plc_parameter or not metadata_parameter:
            if mode=='replace':raise HTTPException(400,f'CSV row {line}: PLC Parameter and Metadata Parameter are required. Nothing was replaced.')
            continue
        machine=str(row.get(normalized.get('MACHINE_DEPARTMENT',''),'') or 'All').strip() or 'All'
        found=next((m for m in mappings if all(str(m.get(key,'') or '').strip().casefold()==value.casefold() for key,value in [('plc_parameter',plc_parameter),('plc_tag',plc_tag),('metadata_parameter',metadata_parameter),('machine_department',machine)])),None)
        item={'plc_parameter':plc_parameter,'plc_tag':plc_tag,'metadata_parameter':metadata_parameter,'machine_department':machine,'status':'configured'}
        for src,dst in [('UNITS','units'),('MIN','MIN'),('MAX','MAX'),('OFFSET_FACTOR','offset_factor'),('SCALE_FACTOR','scale_factor'),('IS_VISIBLE','is_visible'),('IS_WRITABLE','is_writable'),('STATUS','status')]:
            if normalized.get(src):
                item[dst]=str(row.get(normalized[src]) or '').strip() or None
        if mode=='merge' and found: found.update(item)
        else: mappings.append(item)
        imported+=1
    if not imported:raise HTTPException(400,'CSV contains no valid mapping rows. Nothing was changed.')
    data['mappings']=mappings
    result = _write_master(data, current_revision)
    log.info('KNOWLEDGE_MASTER_CSV_IMPORTED filename=%r imported=%d',file.filename,imported)
    return {**result,'status':'ok','imported':imported,'mode':mode}
@router.post('/api/knowledge/master')
def knowledge_master_add(payload:dict):
    machine=str(payload.get('machine_department') or 'All').strip() or 'All'
    plc_parameter=str(payload.get('plc_parameter','')).strip(); plc_tag=str(payload.get('plc_tag','')).strip(); metadata_parameter=str(payload.get('metadata_parameter','')).strip()
    if not plc_parameter or not metadata_parameter: raise HTTPException(400,'PLC Parameter and Metadata Parameter are required.')
    data, revision = _read_master()
    if isinstance(data,list): data={'version':'1.0','mappings':data}
    mappings=data.setdefault('mappings',[])
    for m in mappings:
        if m.get('plc_parameter','').strip().casefold()==plc_parameter.casefold() and m.get('metadata_parameter','').strip().casefold()==metadata_parameter.casefold() and m.get('plc_tag','').strip().casefold()==plc_tag.casefold() and m.get('machine_department','All').casefold()==machine.casefold():
            m.update({'plc_tag':plc_tag,'status':'configured'})
            for src,dst in [('units','units'),('offset_factor','offset_factor'),('scale_factor','scale_factor'),('is_visible','is_visible'),('is_writable','is_writable')]:
                if payload.get(src) not in (None,''): m[dst]=payload.get(src)
            break
    else:
        item={'plc_parameter':plc_parameter,'plc_tag':plc_tag,'metadata_parameter':metadata_parameter,'machine_department':machine,'status':'configured'}
        for src in ('units','offset_factor','scale_factor','is_visible','is_writable'):
            if payload.get(src) not in (None,''): item[src]=payload.get(src)
        mappings.append(item)
    result = _write_master(data, revision)
    log.info('KNOWLEDGE_MASTER_SAVED plc_parameter=%r plc_tag=%r metadata_parameter=%r',plc_parameter,plc_tag,metadata_parameter)
    return result
@router.get('/api/knowledge/master/dropdown')
def knowledge_master_dropdown():
    try:
        data, revision = _read_master(KNOWLEDGE/'master'/'dropdown_mappings.json')
        return {**data,'revision':revision}
    except Exception:
        log.exception('DROPDOWN_MASTER_READ_ERROR')
        raise HTTPException(500,'Dropdown mappings could not be loaded.')

@router.put('/api/knowledge/master/dropdown')
def save_master_dropdown(payload:dict):
    rows=payload.get('mappings')
    if not isinstance(rows,list): raise HTTPException(400,'Mappings must be a list.')
    for index,row in enumerate(rows,1):
        if not isinstance(row,dict) or any(not isinstance(row.get(k),str) or not row[k].strip() for k in ('plc_parameter','metadata_parameter')):
            raise HTTPException(400,f'Row {index}: PLC parameter and metadata parameter are required.')
        optional_tag=row.get('allow_missing_plc_tag',False)
        if not isinstance(optional_tag,bool): raise HTTPException(400,f'Row {index}: allow_missing_plc_tag must be true or false.')
        tag=row.get('plc_tag')
        if (tag is not None and not isinstance(tag,str)) or (not str(tag or '').strip() and not optional_tag):
            raise HTTPException(400,f'Row {index}: enter a PLC tag or enable Allow missing PLC tag.')
        department=str(row.get('machine_department') or 'All').strip() or 'All'
        if optional_tag and department.casefold()=='all':
            raise HTTPException(400,f'Row {index}: choose a specific department when allowing a missing PLC tag.')
        pairs=row.get('mapping')
        if not isinstance(row.get('allowed'),bool) or not isinstance(pairs,list) or not pairs:
            raise HTTPException(400,f'Row {index}: approval and at least one dropdown value are required.')
        values=set()
        for pair in pairs:
            if not isinstance(pair,dict) or not isinstance(pair.get('PLCVAL'),(str,int,float)) or isinstance(pair.get('PLCVAL'),bool) or not str(pair['PLCVAL']).strip() or not isinstance(pair.get('SHOWNVAL'),str) or not pair['SHOWNVAL'].strip():
                raise HTTPException(400,f'Row {index}: every dropdown value needs PLCVAL and SHOWNVAL.')
            value=str(pair['PLCVAL']).strip()
            try: value=str(float(value))
            except ValueError: pass
            if value in values: raise HTTPException(400,f'Row {index}: repeated PLC value {value}.')
            values.add(value)
    path=KNOWLEDGE/'master'/'dropdown_mappings.json'
    with _master_lock:
        data,_=_read_master(path);data['mappings']=rows
        return _write_master(data,payload.get('revision'),path)

@router.post('/api/knowledge/master/dropdown/csv')
async def dropdown_csv(file: UploadFile = File(...)):
    if not (file.filename or '').lower().endswith('.csv'):
        raise HTTPException(400,'Select a CSV dropdown mapping file.')
    try:
        text=(await file.read()).decode('utf-8-sig')
    except UnicodeDecodeError:
        raise HTTPException(400,'Save the CSV using UTF-8 encoding.')
    reader=csv.DictReader(io.StringIO(text))
    headers={str(h).strip().upper():h for h in (reader.fieldnames or []) if h is not None}
    required={'PLC_PARAMETER','PLC_TAG','METADATA_PARAMETER','PLCVAL','SHOWNVAL'}
    if required-set(headers): raise HTTPException(400,'Missing CSV columns: '+', '.join(sorted(required-set(headers))))
    path=KNOWLEDGE/'master'/'dropdown_mappings.json'
    with _master_lock:
        data,revision=_read_master(path)
        mappings=data.setdefault('mappings',[])
        imported={}
        for line,source in enumerate(reader,2):
            if not any(str(v or '').strip() for v in source.values()): continue
            row={key:str(source.get(original) or '').strip() for key,original in headers.items()}
            if any(not row.get(key) for key in required-{'PLC_TAG'}): raise HTTPException(400,f'CSV line {line}: PLC parameter, metadata parameter, PLCVAL and SHOWNVAL are required.')
            machine=(row.get('MACHINE_DEPARTMENT') or 'All').strip() or 'All'
            identity=tuple(row[key].casefold() for key in ('PLC_PARAMETER','PLC_TAG','METADATA_PARAMETER'))+(machine.casefold(),)
            if identity not in imported:
                existing=next((m for m in mappings if tuple(str(m.get(k) or '').strip().casefold() for k in ('plc_parameter','plc_tag','metadata_parameter'))+(str(m.get('machine_department') or 'All').strip().casefold(),)==identity),None)
                item={**(existing or {}),'plc_parameter':row['PLC_PARAMETER'],'plc_tag':row['PLC_TAG'],'metadata_parameter':row['METADATA_PARAMETER'],'machine_department':machine,'mapping':[]}
                item.setdefault('allowed',True)
                imported[identity]=item
            item=imported[identity]
            for key in ('PLC_TYPE','METADATA_TYPE','REASON'):
                if key in headers:
                    value=row[key]
                    if item['mapping'] and item.get(key.lower(),'') != value: raise HTTPException(400,f'CSV line {line}: conflicting {key} for the same mapping.')
                    item[key.lower()]=value
            if 'ALLOWED' in headers:
                flag=row['ALLOWED'].casefold()
                if flag not in ('true','false','yes','no','1','0'): raise HTTPException(400,f'CSV line {line}: ALLOWED must be true/false or yes/no.')
                value=flag in ('true','yes','1')
                if item['mapping'] and item['allowed'] != value: raise HTTPException(400,f'CSV line {line}: conflicting ALLOWED values.')
                item['allowed']=value
            if 'ALLOW_MISSING_PLC_TAG' in headers:
                flag=row['ALLOW_MISSING_PLC_TAG'].casefold()
                if flag not in ('true','false','yes','no','1','0'): raise HTTPException(400,f'CSV line {line}: ALLOW_MISSING_PLC_TAG must be true/false or yes/no.')
                value=flag in ('true','yes','1')
                if item['mapping'] and item.get('allow_missing_plc_tag',False)!=value: raise HTTPException(400,f'CSV line {line}: conflicting ALLOW_MISSING_PLC_TAG values.')
                item['allow_missing_plc_tag']=value
            item['mapping'].append({'PLCVAL':row['PLCVAL'],'SHOWNVAL':row['SHOWNVAL']})
        if not imported: raise HTTPException(400,'CSV contains no dropdown values. Fill the template before importing.')
        for identity,item in imported.items():
            index=next((i for i,m in enumerate(mappings) if tuple(str(m.get(k) or '').strip().casefold() for k in ('plc_parameter','plc_tag','metadata_parameter'))+(str(m.get('machine_department') or 'All').strip().casefold(),)==identity),None)
            if index is None: mappings.append(item)
            else: mappings[index]=item
        result=save_master_dropdown({'revision':revision,'mappings':mappings})
        return {**result,'imported':len(imported)}

@router.post('/api/local/knowledge/master/dropdown/csv')
async def local_dropdown_csv(payload:dict):
    path=_local_path(payload.get('path',''),True,False)
    if not path.is_file() or path.suffix.lower()!='.csv': raise HTTPException(400,'Select a CSV mapping file.')
    return await dropdown_csv(UploadFile(filename=path.name,file=io.BytesIO(path.read_bytes())))

@router.get('/api/knowledge/project')
def knowledge_project(project_name:str=''):
    try:
        return json.loads(project_kb_file(project_name).read_text(encoding='utf-8'))
    except Exception:
        log.exception('KNOWLEDGE_PROJECT_READ_ERROR project=%s',project_name)
        raise HTTPException(500,'Project knowledge configuration could not be loaded.')
@router.post('/api/knowledge/project')
def knowledge_project_add(payload:dict):
    project_name=str(payload.get('project_name','')).strip()
    plc_parameter=str(payload.get('plc_parameter','')).strip()
    plc_tag=str(payload.get('plc_tag','')).strip()
    metadata_parameter=str(payload.get('metadata_parameter','')).strip()
    if not project_name or not plc_parameter or not metadata_parameter:
        raise HTTPException(400,'Project name, PLC Parameter and Metadata Parameter are required.')
    path=project_kb_file(project_name)
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':'1.0','project':project_name,'mappings':[]}
    if isinstance(data,list): data={'version':'1.0','mappings':data}
    data['project']=project_name
    mappings=data.setdefault('mappings',[])
    found=False
    for m in mappings:
        if m.get('plc_parameter','').strip().casefold()==plc_parameter.casefold():
            m.update({'plc_parameter':plc_parameter,'plc_tag':plc_tag,'metadata_parameter':metadata_parameter,'status':'accepted'})
            found=True
            break
    if not found:
        mappings.append({'plc_parameter':plc_parameter,'plc_tag':plc_tag,'metadata_parameter':metadata_parameter,'status':'accepted'})
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    log.info('KNOWLEDGE_PROJECT_SAVED project=%r plc_parameter=%r plc_tag=%r metadata_parameter=%r',project_name,plc_parameter,plc_tag,metadata_parameter)
    return data
