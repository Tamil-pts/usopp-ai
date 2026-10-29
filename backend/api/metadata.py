"""Read and edit workbook copies without overwriting the selected source workbook."""
from __future__ import annotations
import io
import json
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.encoders import jsonable_encoder
from backend.core.runtime import WORK, EXPORTS, _local_metadata_path, _local_session, safe_name
from python_engine.workbook_bounds import value_bounds, value_rows
from python_engine.metadata_cells import metadata_numeric_value, is_numeric_metadata_header, normalize_metadata_workbook

router=APIRouter(tags=['Metadata Workbooks'])
DUPLICATE_FILL='E4D7FF'
DUPLICATE_FORMULA='N("uSOPp duplicate row")=0'
OFFSET_FORMULA='N("uSOPp offset verification")=0'

def normalized_header(value):
    return re.sub(r'[^a-z0-9]+','',str(value or '').strip().lower())

def metadata_duplicate_rows(ws):
    """Return duplicate Parameter rows, scoped independently to each Group Code."""
    last_row, last_column = value_bounds(ws)
    headers={normalized_header(ws.cell(1,column).value):column for column in range(1,last_column+1)}
    group_column=next((headers[key] for key in ('groupcode','group','groupid') if key in headers),None)
    parameter_column=next((headers[key] for key in ('parameters','parameter','parametername') if key in headers),None)
    if group_column is None or parameter_column is None:return set()
    buckets={}
    for row in range(2,last_row+1):
        group=str(ws.cell(row,group_column).value or '').strip().casefold()
        parameter=re.sub(r'\s+',' ',str(ws.cell(row,parameter_column).value or '').strip()).casefold()
        if group and parameter:buckets.setdefault((group,parameter),[]).append(row)
    return {row for matches in buckets.values() if len(matches)>1 for row in matches}

def apply_duplicate_highlights(wb):
    """Mark group-local duplicate rows without replacing existing cell styles."""
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import PatternFill
    from openpyxl.utils import get_column_letter
    purple=PatternFill(fill_type='solid',fgColor=DUPLICATE_FILL)
    for ws in wb.worksheets:
        # Remove only conditional-formatting rules owned by this feature. This
        # clears stale duplicate marks while preserving original cell fills.
        for conditional,rules in list(ws.conditional_formatting._cf_rules.items()):
            retained=[rule for rule in rules if DUPLICATE_FORMULA not in (getattr(rule,'formula',None) or [])]
            if retained:ws.conditional_formatting._cf_rules[conditional]=retained
            else:del ws.conditional_formatting._cf_rules[conditional]
        if normalized_header(ws.title)=='sheet2':continue
        duplicate_rows=metadata_duplicate_rows(ws)
        # Only metadata-shaped sheets are eligible. Sheet2 is explicitly
        # excluded even when a customer workbook gives it similar headers.
        _, data_columns = value_bounds(ws)
        headers={normalized_header(ws.cell(1,column).value) for column in range(1,data_columns+1)}
        metadata_shaped=bool(headers.intersection({'groupcode','group','groupid'})) and bool(headers.intersection({'parameters','parameter','parametername'}))
        if not metadata_shaped:continue
        last_column=get_column_letter(data_columns)
        for row in sorted(duplicate_rows):
            ws.conditional_formatting.add(
                f'A{row}:{last_column}{row}',
                FormulaRule(formula=[DUPLICATE_FORMULA],fill=purple,stopIfTrue=False),
            )

def resolve_workbook(payload):
    raw=payload.get('workbookPath') or payload.get('path')
    if raw: return _local_metadata_path(WORK,str(raw))
    sid=str(payload.get('sessionId') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',sid): raise HTTPException(400,'Select or generate a metadata workbook first.')
    manifest=WORK/sid/'inputs.json'
    source='generated' if payload.get('source')=='generated' else 'uploaded'
    if manifest.is_file():
        path=json.loads(manifest.read_text(encoding='utf-8')).get(source)
        if path: return _local_metadata_path(WORK,path)
    if source=='generated':
        matches=list((EXPORTS/'metadata').glob(f'*Generated_Metadata*_{sid}.xlsx'))
        if len(matches)==1: return matches[0]
    raise HTTPException(404,'Metadata workbook not found. Select the input workbook or generate it again.')

def sheet_data(name,values):
    if not values: return {'name':name,'headers':[],'rows':[]}
    keys=[]
    for index,value in enumerate(values[0]):
        key=str(value) if value not in (None,'') else f'Column {index+1}'
        original=key; count=2
        while key in keys: key=f'{original} ({count})'; count+=1
        keys.append(key)
    return {'name':name,'headers':keys,'rows':[
        {key:(row[i] if i<len(row) and row[i] is not None else '') for i,key in enumerate(keys)}
        for row in values[1:]]}

def read_sheets(path):
    if path.suffix.lower()=='.xlsx':
        from openpyxl import load_workbook
        wb=load_workbook(path,data_only=False)
        try: return [sheet_data(ws.title,value_rows(ws)) for ws in wb.worksheets]
        finally: wb.close()
    import xlrd
    book=xlrd.open_workbook(str(path),on_demand=True)
    try: return [sheet_data(ws.name,[ws.row_values(i) for i in range(ws.nrows)]) for ws in book.sheets()]
    finally: book.release_resources()

def quality_reference(payload, path):
    sid=str(payload.get('referenceSessionId') or '')
    if not sid:return []
    from backend.core.access import require_session
    folder=require_session(sid)
    generated=payload.get('source')=='generated'
    reference_file=folder/('generated_metadata.json' if generated else 'validation_results.json')
    if not reference_file.is_file():return []
    if not generated:
        manifest_file=folder/'inputs.json'
        manifest=json.loads(manifest_file.read_text(encoding='utf-8')) if manifest_file.is_file() else {}
        original=manifest.get('uploaded')
        if not original or Path(original).resolve()!=path.resolve():return []
    from python_engine.metadata_quality import source_fields
    return source_fields(json.loads(reference_file.read_text(encoding='utf-8')), 'generated' if generated else 'uploaded')

def workbook_quality(payload, path):
    from python_engine.metadata_quality import inspect_workbook
    sheets=payload.get('sheets') if 'sheets' in payload else read_sheets(path)
    report=inspect_workbook(sheets,quality_reference(payload,path))
    metadata=report.pop('metadata')
    model_id=payload.get('modelId')
    model_stage={'id':'dataModel','status':'PENDING','checked':0,'issues':[],
                 'detail':'Choose a department and Data Model to check the required parameters.'}
    if model_id:
        from backend.api.data_models import model_for
        from backend.core.data_models import validate_model,machine_key
        model=model_for(str(model_id))
        department=payload.get('machineDepartment')
        if department and machine_key(department)!=machine_key(model['machine']):
            raise HTTPException(400,'The Data Model does not match the selected machine / department.')
        result=validate_model(model,metadata)
        issues=[{'parameter':row['name'],'groupCode':', '.join(map(str,row['groupCodes'])),
                 'check':'Data Model parameter','expected':row.get('plcType',''),
                 'actual':row['detail'],'status':'FAIL' if row['status']=='FAIL' else 'REVIEW'}
                for row in result['rows'] if row['status'] in {'FAIL','UNRESOLVED'}]
        checked=sum(result['summary'][state] for state in ('PASS','FAIL','OPTIONAL','UNRESOLVED'))
        model_stage={'id':'dataModel','status':result['status'] if checked else 'REVIEW','checked':checked,
                     'issues':issues,'modelId':model['id'],
                     'detail':f"{model['service']} / {model['machine']}: {result['summary']['PASS']} passed, {result['summary']['FAIL']} failed, {result['summary']['UNRESOLVED']} need review. Optional and server-generated fields do not block readiness."}
    report['stages'].append(model_stage)
    report['ready']=all(stage['status'] in {'PASS','NOT_APPLICABLE'} for stage in report['stages'])
    return report

@router.post('/api/metadata/view/quality')
def check_workbook_quality(payload:dict):
    path=resolve_workbook(payload)
    try:return jsonable_encoder(workbook_quality(payload,path))
    except (ValueError,TypeError,KeyError) as exc:raise HTTPException(400,f'Cannot check metadata quality: {exc}') from exc

def apply_offset_highlights(wb, issues):
    """Highlight existing offset cells only; preserve every row and column."""
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import PatternFill
    for ws in wb.worksheets:
        for conditional,rules in list(ws.conditional_formatting._cf_rules.items()):
            retained=[rule for rule in rules if OFFSET_FORMULA not in (getattr(rule,'formula',None) or [])]
            if retained:ws.conditional_formatting._cf_rules[conditional]=retained
            else:del ws.conditional_formatting._cf_rules[conditional]
    locations={}
    for issue in issues:
        key=(issue.get('sheet'),issue.get('row'))
        if key not in locations or issue['status']=='FAIL':locations[key]=issue['status']
    for (name,row),status in locations.items():
        if name not in wb.sheetnames or not isinstance(row,int) or row<2:continue
        ws=wb[name]
        columns={normalized_header(cell.value):cell.column for cell in ws[1]}
        column=next((columns[key] for key in ('offsetfromthestartofthegroupinbytes','offset','byteoffset','offsetinbytes') if key in columns),None)
        if column is None:continue
        for rules in ws.conditional_formatting._cf_rules.values():
            for rule in rules:rule.priority=(rule.priority or 1)+1
        cell=ws.cell(row,column).coordinate
        rule=FormulaRule(formula=[OFFSET_FORMULA],fill=PatternFill(fill_type='solid',fgColor='FEE2E2' if status=='FAIL' else 'FEF3C7'),stopIfTrue=True)
        rule.priority=1
        ws.conditional_formatting.add(cell,rule)

@router.post('/api/metadata/view/sheets')
def view_sheets(payload:dict):
    path=resolve_workbook(payload)
    try: return jsonable_encoder({'file':path.name,'workbookPath':str(path),'sheets':read_sheets(path)})
    except Exception as exc: raise HTTPException(400,f'Cannot read metadata workbook: {exc}') from exc

def save_copy(payload):
    from openpyxl import Workbook,load_workbook
    source=resolve_workbook(payload)
    if source.suffix.lower()=='.xlsx': wb=load_workbook(io.BytesIO(source.read_bytes()))
    else:
        wb=Workbook(); wb.remove(wb.active)
        for sheet in read_sheets(source):
            ws=wb.create_sheet(sheet['name']); ws.append(sheet['headers'])
            for row in sheet['rows']: ws.append([row[h] for h in sheet['headers']])
    sheets=payload.get('sheets') or [{'name':payload.get('sheetName'),'headers':payload.get('headers',[]),'rows':payload.get('rows',[])}]
    try:
        for sheet in sheets:
            name=sheet.get('name')
            if name not in wb.sheetnames: raise HTTPException(400,f'Worksheet not found: {name}')
            ws=wb[name]; headers=sheet.get('headers',[]); rows=sheet.get('rows',[])
            if not headers and not rows: continue
            data_rows, data_columns = value_bounds(ws)
            if len(headers)!=data_columns or len(rows)!=max(0,data_rows-1):
                raise HTTPException(400,'Workbook shape changed. Reload the workbook before saving.')
            for ri,row in enumerate(rows,2):
                for ci,key in enumerate(headers,1):
                    cell=ws.cell(ri,ci); value=row.get(key,'')
                    if is_numeric_metadata_header(key):
                        value=metadata_numeric_value(value)
                    if cell.value == value and type(cell.value) is type(value): continue
                    if value=='': value=None
                    elif isinstance(cell.value,(float,int)) and not isinstance(cell.value,bool) and isinstance(value,str):
                        try: value=float(value) if any(c in value.lower() for c in '.e') else int(value)
                        except ValueError: pass
                    cell.value=value
        # Omit the generated trace sheet when exporting an older workbook copy.
        if 'Alarm Sources' in wb.sheetnames and len(wb.worksheets)>1:
            alarm_sheet=wb['Alarm Sources']
            alarm_headers={cell.value for cell in alarm_sheet[1]}
            if {'ALARM_GROUP','ALARM_IMAGE','CAPTION','PACKING_SOURCE'}<=alarm_headers:
                wb.remove(alarm_sheet)
        apply_duplicate_highlights(wb)
        from python_engine.metadata_quality import inspect_workbook
        offset_report=inspect_workbook(sheets,quality_reference(payload,source))
        apply_offset_highlights(wb,offset_report['stages'][0]['issues'])
        issues=normalize_metadata_workbook(wb)
        if issues: raise HTTPException(400,{'message':'MIN/MAX and scale/offset factors must be numeric or null for SpinConnect.', 'cells':issues[:100]})
        sid,_=_local_session()
        from backend.core.identifiers import run_identity
        identity=source.stem.split('_Generated_Metadata_')[0].split('_Edited_')[0] if '_TEST_' in source.stem else run_identity(payload.get('projectName') or source.stem,payload.get('machineDepartment') or 'All')
        out=EXPORTS/'metadata'/f'{identity}_Edited_{sid}.xlsx'
        wb.save(out)
        from backend.core.access import claim_resource
        claim_resource(out)
        return {'status':'saved','sessionId':sid,'workbookPath':str(out),'fileName':out.name,
                'downloadUrl':f'/api/metadata/view/download/{sid}/{out.name}'}
    finally: wb.close()

@router.post('/api/metadata/view/save')
@router.post('/api/metadata/view/export')
def save_workbook(payload:dict):
    try: return save_copy(payload)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(400,f'Cannot save workbook copy: {exc}') from exc

@router.get('/api/metadata/view/download/{sid}/{name}')
def download(sid:str,name:str):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',sid) or Path(name).name!=name or '\\' in name:
        raise HTTPException(400,'Invalid metadata download path.')
    path=EXPORTS/'metadata'/name
    if not path.is_file() or not name.endswith(f'_{sid}.xlsx'): raise HTTPException(404,'Workbook copy not found.')
    return FileResponse(path,filename=name)

@router.get('/api/local/metadata/download/{sid}')
def generated_download(sid:str):
    path=resolve_workbook({'sessionId':sid,'source':'generated'})
    return FileResponse(path,filename=path.name)
