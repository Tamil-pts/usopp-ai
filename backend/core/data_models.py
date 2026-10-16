"""Development-team data models and case-insensitive PLC metadata checks."""
from io import BytesIO
from pathlib import Path
import hashlib
import json
import re

SERVER_NAMES={'shed id','unit id','asset id','business id','tenant id','adjusted time stamp','time stamp actual'}
SERVICES={'PMS':'Production monitoring service','QMS':'Quality monitoring service','CMS':'Condition monitoring service'}
# SQL/storage types such as TIMESTAMP and INTEGER do not identify the PLC wire
# representation. Keep them unresolved unless a PLC datatype is supplied.
PLC_TYPES={'BOOL','SINT','USINT','BYTE','INT','UINT','WORD','DINT','UDINT','DWORD',
           'LINT','ULINT','LWORD','REAL','LREAL','STRING','WSTRING','TIME','LTIME',
           'DATE','TIME_OF_DAY','TOD','DATE_AND_TIME','DT'}
NUMERIC_WIRE_TYPES={'SINT','USINT','BYTE','INT','UINT','WORD','DINT','UDINT','DWORD','LINT','ULINT','LWORD','REAL','LREAL'}


def value_type_matches(requirement,actual):
    actual=plc_type(actual)
    if requirement.get('dataTypeRole')=='value' and requirement.get('numericValueType'):
        return actual in NUMERIC_WIRE_TYPES
    return actual==requirement['plcType']


def requirement_names(row):return list(dict.fromkeys(name_key(value) for value in [row['name'],*row.get('aliases',[])]))


def machine_key(value):
    key=re.sub(r'[^a-z]','',str(value or '').casefold())
    return {'finisher':'drawframefinisher','breaker':'drawframebreaker'}.get(key,key)


def header(value):
    return re.sub(r'[^a-z0-9]','',str(value or '').casefold())


def clean(value):
    return '' if value is None or str(value).strip().casefold() in {'null','none','<null>'} else str(value).strip()


def name_key(value):
    # Case is cosmetic; punctuation, words and word spacing remain significant.
    return clean(value).casefold()


def plc_type(value):
    value=clean(value).upper()
    root=re.split(r'[\[(]',value)[0].strip()
    return {'FLOAT':'REAL','NCHAR':'STRING','NVARCHAR':'STRING','VARCHAR':'STRING','CHAR':'STRING','USINT':'BYTE'}.get(root,root)


def groups(value):
    if isinstance(value,(int,float)) and int(value)==value:return [int(value)]
    text=clean(value)
    if re.fullmatch(r'\d+(?:\s*[,;/]\s*\d+)*',text):return [int(part) for part in re.split(r'[,;/]',text)]
    return []


def entry(name,dtype,group,formula,source,sheet,row,required=True):
    name=clean(name);formula=clean(formula)
    normalized=' '.join(name.casefold().split())
    kind='server' if normalized in SERVER_NAMES else 'formula' if formula else 'plc'
    return {'name':name,'dataType':clean(dtype),'plcType':plc_type(dtype),'groupCodes':groups(group),
            'groupCodeSource':clean(group),'formula':formula,'kind':kind,'required':required is not False,
            'source':source,'sheet':sheet,'row':row}


def parse_model(content,filename,service='',machine=''):
    suffix=Path(filename).suffix.casefold();records=[];warnings=[];database_model=None
    inferred=next((key for key in SERVICES if re.search(r'(?i)(?:^|[^a-z])'+key+r'(?:[^a-z]|$)',filename)),None)
    service=(service or inferred or '').upper()
    if suffix=='.xlsx':
        from openpyxl import load_workbook
        workbook=load_workbook(BytesIO(content),read_only=True,data_only=True)
        try:
            for sheet in workbook:
                columns=None
                for number,row in enumerate(sheet.values,start=1):
                    if number>25000:raise ValueError('Data model sheet exceeds 25,000 rows.')
                    if columns is None:
                        if number>25:break
                        names={header(value):index for index,value in enumerate(row) if value is not None}
                        name_key=next((key for key in ('nameonlyreference','actualtagname','tagname','parametername') if key in names),None)
                        if name_key and 'datatype' in names and 'groupcode' in names:
                            columns={'name':names[name_key],'dtype':names['datatype'],'group':names['groupcode'],
                                     'formula':next((index for key,index in names.items() if 'formula' in key),None)}
                        continue
                    cell=lambda key:row[columns[key]] if columns[key] is not None and columns[key]<len(row) else None
                    if not any(clean(cell(key)) for key in ('name','dtype','group','formula')):continue
                    name=cell('name')
                    if clean(name).casefold().startswith('note:'):continue
                    records.append(entry(name,cell('dtype'),cell('group'),cell('formula'),filename,sheet.title,number))
        finally:workbook.close()
    elif suffix=='.json':
        data=json.loads(content.decode('utf-8-sig'))
        if isinstance(data,dict):
            declared=clean(data.get('machine') if data.get('schemaVersion')==1 else data.get('controleCode') or data.get('controllerCode'))
            if machine and declared and machine_key(machine)!=machine_key(declared):
                raise ValueError(f'Data model declares {declared}, but the selected department is {machine}. Choose the matching department.')
        if isinstance(data,dict) and data.get('schemaVersion')==1 and isinstance(data.get('parameters'),list):
            database_model=data.get('databaseModel')
            for record in data['parameters']:
                row=entry(record.get('name'),record.get('dataType'),','.join(map(str,record.get('groupCodes') or [])),record.get('formula'),filename,record.get('sheet','Parameters'),record.get('row',0),record.get('required',True))
                if record.get('kind') in {'server','formula'}:row['kind']=record['kind']
                for key in ('excelReferences','referenceIssues','suggestedPlcType','dataTypeRole','numericValueType','aliases','canonicalName','mappingSource','referenceCorrections','ignoreNameSeparators'):
                    if key in record:row[key]=record[key]
                if record.get('plcDataType'):
                    row['plcDataType']=clean(record['plcDataType']);row['plcType']=plc_type(record['plcDataType'])
                records.append(row)
            service=service or data.get('service','');machine=machine or data.get('machine','')
        elif isinstance(data,dict) and isinstance(data.get('keysList'),dict):
            database_model=data
            collection_services={sheet.split('_')[0].upper() for sheet in data['keysList'] if sheet.split('_')[0].upper() in SERVICES}
            if not service and len(collection_services)==1:service=next(iter(collection_services))
            machine=machine or clean(data.get('controleCode') or data.get('controllerCode'))
            for sheet,items in data['keysList'].items():
                if not isinstance(items,list):continue
                prefix=sheet.split('_')[0].upper()
                if prefix in SERVICES and service and prefix!=service:continue
                for number,record in enumerate(items,start=1):
                    if not isinstance(record,dict):continue
                    row=entry(record.get('tagName'),record.get('dataType'),record.get('groupCode'),record.get('formula'),filename,sheet,number,record.get('isRequired',True))
                    if record.get('plcDataType'):
                        row['plcDataType']=clean(record['plcDataType']);row['plcType']=plc_type(record['plcDataType'])
                    if record.get('isHost') is True:row['kind']='server'
                    elif record.get('isAutoCalc') is True or clean(record.get('groupCode')).casefold()=='formula':row['kind']='formula'
                    evidence=record.get('excelReference')
                    if isinstance(evidence,dict):row['excelReferences']=[evidence]
                    for key in ('dataTypeRole','numericValueType','aliases','canonicalName','mappingSource','referenceCorrections','ignoreNameSeparators'):
                        if key in record:row[key]=record[key]
                    records.append(row)
        else:raise ValueError('JSON must contain keysList collections or a saved uSOPp data model.')
    else:raise ValueError('Attach an XLSX workbook or JSON data model.')
    if not records:raise ValueError('No data model rows found. Required columns: Name(Only Reference), Data Type, Group Code.')
    if len(records)>30000:raise ValueError('Data model exceeds 30,000 parameters.')
    service=service.upper()
    if service not in SERVICES:raise ValueError('Choose PMS, QMS or CMS for this model.')
    if not machine:
        machine=next((value for value in ['DrawFrameFinisher','DrawFrameBreaker','RingFrame','SpeedFrame','LapFormer','Carding','BlowRoom','Comber'] if value.casefold() in re.sub(r'[^a-z]','',filename.casefold())),'Unspecified')
    for record in records:
        if record['kind']=='plc' and (not record['name'] or not record['groupCodes'] or not record['plcType']):
            warnings.append(f'{record["sheet"]}:{record["row"]}: incomplete PLC requirement; name, datatype and group code are required.')
    model={'schemaVersion':1,'id':hashlib.sha256(content+b'\0'+filename.encode()+b'\0'+service.encode()+b'\0'+machine.encode()).hexdigest(),
            'source':filename,'sourceSha256':hashlib.sha256(content).hexdigest(),'service':service,'serviceName':SERVICES[service],
            'machine':machine,'parameters':records,'warnings':warnings}
    if database_model is not None:model['databaseModel']=database_model
    return model


def database_json(model):
    """Export the supplied database schema, preserving its database keys."""
    if isinstance(model.get('databaseModel'),dict):return model['databaseModel']
    collections={}
    for row in model['parameters']:
        collections.setdefault(row['sheet'],[]).append({
            'tagName':row['name'],'dataType':row['dataType'] or None,
            'groupCode':row.get('groupCodeSource') or None,'tdEngineKey':None,'mongoKey':None,
            'formula':row['formula'] or None,'type':None,'isRequired':row.get('required',True)})
    return {'controleCode':model['machine'],'keysList':collections}


def validate_model(model,metadata):
    indexed={};by_name={};rows=[]
    for item in metadata:
        name=clean(item.get('parameter'));group=groups(item.get('groupCode'))
        if not group:continue
        indexed.setdefault((name_key(name),group[0]),[]).append(item);by_name.setdefault(name_key(name),[]).append(item)
    for requirement in model['parameters']:
        names=requirement_names(requirement)
        if requirement.get('ignoreNameSeparators'):
            compact={re.sub(r'[\s_]+','',name) for name in names}
            names=list(dict.fromkeys(names+[name_key(item.get('parameter')) for item in metadata if re.sub(r'[\s_]+','',name_key(item.get('parameter'))) in compact]))
        named=[item for name in names for item in by_name.get(name,[])]
        result={**requirement,'actual':[],'reasonCodes':[]}
        if requirement['kind']=='server':result.update(status='SKIPPED',detail='Generated by server/host; no PLC parameter required.')
        elif requirement['kind']=='formula':result.update(status='DERIVED',actual=named,detail='Calculated field; formula is shown for review, not evaluated against PLC values.')
        elif not requirement['name'] or not requirement['groupCodes'] or not requirement['plcType']:
            result.update(status='UNRESOLVED',actual=named,reasonCodes=['REFERENCE_INCOMPLETE'],detail='Development-team model is missing a name, datatype or group code. No requirement was inferred.')
        elif requirement.get('referenceIssues') or requirement['plcType'] not in PLC_TYPES and not (requirement.get('dataTypeRole')=='value' and requirement.get('numericValueType')):
            actual=[item for group in requirement['groupCodes'] for item in indexed.get((name_key(requirement['name']),group),[])]
            reasons=[];details=[]
            if requirement.get('referenceIssues'):
                reasons.append('REFERENCE_CONFLICT')
                details.extend(issue['detail'] for issue in requirement['referenceIssues'])
            if requirement['plcType'] not in PLC_TYPES:
                reasons.append('REFERENCE_TYPE_UNSUPPORTED')
                details.append(f'Database datatype {requirement["dataType"]} does not define a supported PLC datatype. Specify the PLC wire datatype before checking it.')
            result.update(status='UNRESOLVED',actual=actual,reasonCodes=reasons,detail=' '.join(details))
        else:
            failures=[];reasons=[]
            for group in requirement['groupCodes']:
                matches=[item for name in names for item in indexed.get((name,group),[])]
                if not matches:
                    elsewhere=named
                    if elsewhere:
                        reasons.append('GROUP_DIFFERS')
                        failures.append(f'Parameter name exists in GC {", ".join(str(item["groupCode"]) for item in elsewhere)}, but is missing from GC {group}.')
                    else:
                        near=[item for item in metadata if groups(item.get('groupCode'))==[group] and header(item.get('parameter'))==header(requirement['name'])]
                        reasons.append('NAME_DIFFERS' if near else 'MISSING_PARAMETER')
                        failures.append(f'{requirement["name"]} is missing from GC {group}.'+(' Name differs: '+', '.join(clean(item.get('parameter')) for item in near[:3])+'.' if near else ''))
                        for item in near:
                            if not value_type_matches(requirement,item.get('dataType')):
                                reasons.append('TYPE_DIFFERS')
                                failures.append(f'GC {group}: reference {requirement["name"]} expects {requirement["plcType"]}; actual {item.get("parameter")} is {item.get("dataType")}.')
                        elsewhere=near
                    result['actual'].extend(item for item in elsewhere if item not in result['actual'])
                    continue
                result['actual'].extend(item for item in matches if item not in result['actual'])
                if len(matches)>1:
                    reasons.append('DUPLICATE_PARAMETER');failures.append(f'Duplicate parameter name in GC {group} ({len(matches)} rows, ignoring case).')
                for match in matches:
                    if name_key(match.get('parameter'))!=name_key(requirement['name']):reasons.append('NAME_MAPPED')
                    if not value_type_matches(requirement,match.get('dataType')):
                        reasons.append('TYPE_DIFFERS')
                        failures.append(f'GC {group}: expected {requirement["plcType"]}, actual {match.get("dataType")}.')
                    elif plc_type(match.get('dataType'))!=requirement['plcType']:reasons.append('NUMERIC_VALUE_MAPPED')
            detail='Parameter name (ignoring case), group code and datatype match.'
            if 'NUMERIC_VALUE_MAPPED' in reasons:detail='Numeric database value is mapped to the PLC datatype declared in machine metadata. This checks value compatibility; it does not independently verify the wire datatype.'
            if 'NAME_MAPPED' in reasons:detail+=' Parameter name uses the configured department and Group Code alias.'
            result.update(status='FAIL' if failures and requirement['required'] else 'OPTIONAL' if failures else 'PASS',
                          reasonCodes=list(dict.fromkeys(reasons)),detail=' '.join(failures) or detail)
        rows.append(result)
    summary={status:sum(row['status']==status for row in rows) for status in ('PASS','FAIL','OPTIONAL','UNRESOLVED','SKIPPED','DERIVED')}
    return {'schemaVersion':1,'modelId':model['id'],'source':model['source'],'service':model['service'],'machine':model['machine'],
            'summary':summary,'status':'FAIL' if summary['FAIL'] else 'REVIEW' if summary['UNRESOLVED'] else 'PASS','rows':rows,
            'mappingRulesRevision':model.get('mappingRulesRevision')}


def import_folder(folder,destination):
    catalog=[];issues=[]
    for path in sorted(Path(folder).rglob('*')):
        if path.suffix.casefold() not in {'.xlsx','.json'} or path.name.startswith('~$') or not path.is_file():continue
        service=next((part.upper() for part in path.relative_to(folder).parts if part.upper() in SERVICES),'')
        if not service:continue
        try:
            model=parse_model(path.read_bytes(),path.name,service)
            model['sourceRelativePath']=path.relative_to(folder).as_posix()
            catalog.append(model)
        except Exception as error:issues.append({'source':path.relative_to(folder).as_posix(),'error':str(error)})
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps({'schemaVersion':1,'models':catalog,'importIssues':issues},ensure_ascii=False,indent=2),encoding='utf-8')
    return catalog,issues
