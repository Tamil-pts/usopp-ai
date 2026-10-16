"""Build fixed service/department JSON models from the supplied database keys.

Database JSON definitions retain their keys. Workbook-only parameters are added
with their sheet/row evidence so that older JSON cannot hide Excel requirements.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

APP_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP_ROOT))
from backend.core.data_models import SERVICES,PLC_TYPES,clean,header,machine_key,name_key,parse_model


def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    ending='\r\n' if path.is_file() and b'\r\n' in path.read_bytes() else '\n'
    with temporary.open('w',encoding='utf-8',newline=ending) as stream:
        stream.write(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def workbook_data(path,service):
    from openpyxl import load_workbook
    model=parse_model(path.read_bytes(),path.name,service)
    values={};book=load_workbook(path,read_only=True,data_only=True)
    try:
        for sheet in book:
            columns=None
            for number,row in enumerate(sheet.values,1):
                if columns is None:
                    if number>25:break
                    names={header(value):index for index,value in enumerate(row) if value is not None}
                    name=next((key for key in ('nameonlyreference','actualtagname','tagname','parametername') if key in names),None)
                    if name and 'datatype' in names and 'groupcode' in names:columns=names
                    continue
                get=lambda key:row[columns[key]] if key in columns and columns[key]<len(row) else None
                values[(sheet.title,number)]={'tdEngineKey':get('keynametdengine'),'mongoKey':get('keynamerequiredinmongodb')}
    finally:book.close()
    collections={}
    for row in model['parameters']:
        if not row['name']:continue
        keys=values.get((row['sheet'],row['row']),{})
        row.update(keys)
        collections.setdefault(row['sheet'],[]).append({
            'tagName':row['name'],'dataType':row['dataType'] or None,'groupCode':row['groupCodeSource'] or None,
            'tdEngineKey':keys.get('tdEngineKey'),'mongoKey':keys.get('mongoKey'),
            'formula':row['formula'] or None,'type':None,'isRequired':row['required']})
    return model,{'controleCode':model['machine'].upper(),'keysList':collections}


def build(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if not source.is_dir():raise ValueError(f'Data Modelling folder not found: {source}')
    if output==source or source in output.parents:raise ValueError('Knowledge output must be outside the source folder.')
    choices={};workbooks={};issues=[];sources=[]
    for service in SERVICES:(output/service).mkdir(parents=True,exist_ok=True)
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.name.startswith('~$') or path.suffix.casefold() not in {'.json','.xlsx'}:continue
        relative=path.relative_to(source)
        own_service=next((part.upper() for part in relative.parts if part.upper() in SERVICES),'')
        if not own_service:continue
        archived=output/'reference_sources'/relative
        archived.parent.mkdir(parents=True,exist_ok=True)
        if path.resolve()!=archived.resolve():shutil.copy2(path,archived)
        sources.append({'source':relative.as_posix(),'archive':archived.relative_to(output).as_posix(),
                        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        try:
            if path.suffix.casefold()=='.json':
                raw=json.loads(path.read_text(encoding='utf-8-sig'))
                if not isinstance(raw,dict) or not isinstance(raw.get('keysList'),dict):raise ValueError('Expected controleCode / keysList database JSON.')
                department=clean(raw.get('controleCode') or raw.get('controllerCode'))
                if not department:raise ValueError('Database JSON does not identify its department.')
                if not re.fullmatch(r'[A-Za-z0-9_-]+',department):raise ValueError('Department must be a simple filename.')
                if machine_key(path.stem)!=machine_key(department):
                    raise ValueError(f'Filename department {path.stem} differs from controleCode {department}; excluded from fixed requirements.')
                for service in SERVICES:
                    collections={key:rows for key,rows in raw['keysList'].items() if key.split('_')[0].upper()==service}
                    if not collections:continue
                    candidate={**raw,'keysList':collections}
                    priority=100 if service==own_service else 50
                    key=(service,machine_key(department))
                    if key not in choices or priority>choices[key]['priority']:
                        choices[key]={'raw':candidate,'department':department.upper(),'source':relative.as_posix(),
                                      'priority':priority,'sourceType':'database-json'}
            elif 'Key_Definitions' in path.name:
                model,raw=workbook_data(path,own_service)
                key=(own_service,machine_key(model['machine']))
                workbooks.setdefault(key,[]).append((model,relative.as_posix()))
                if key not in choices:
                    choices[key]={'raw':raw,'department':raw['controleCode'],'source':relative.as_posix(),
                                  'priority':10,'sourceType':'workbook'}
        except Exception as error:issues.append({'source':relative.as_posix(),'error':str(error)})
    catalog=[];coverage=[];corrections=[]
    rules_path=APP_ROOT/'knowledge/master/data_model_rules.json'
    mapping_rules=json.loads(rules_path.read_text(encoding='utf-8')) if rules_path.exists() else {}
    for (service,department_key),choice in sorted(choices.items()):
        department=choice['department'];path=output/service/(department+'.json')
        write_json(path,choice['raw'])
        model=parse_model(path.read_bytes(),path.name,service,department)
        model.update(fixed=True,sourceType=choice['sourceType'],sourceRelativePath=f'{service}/{department}.json',
                     originalSource=choice['source'],referenceWorkbooks=[filename for _,filename in workbooks.get((service,department_key),[])])
        for issue in issues:
            if issue['source'].split('/')[0].upper()==service and machine_key(Path(issue['source']).stem)==department_key:
                model['warnings'].append(issue['source']+': '+issue['error']+' Using '+choice['source']+'.')
        locations={}
        for workbook,filename in workbooks.get((service,department_key),[]):
            for row in workbook['parameters']:
                key=(name_key(row['name']),tuple(row['groupCodes']))
                locations.setdefault(key,[]).append({'source':filename,'sheet':row['sheet'],'row':row['row'],
                    'name':row['name'],'dataType':row['dataType'],'plcType':row['plcType'],'kind':row['kind']})
        for row in model['parameters']:
            references=locations.get((name_key(row['name']),tuple(row['groupCodes'])),[])
            row['excelReferences']=[{key:value[key] for key in ('source','sheet','row','dataType')} for value in references]
            if row['kind']!='plc':continue
            conflicts=[value for value in references if value['kind']=='plc' and value['plcType'] and value['plcType']!=row['plcType']]
            if conflicts:
                expected=', '.join(sorted({value['dataType'] for value in conflicts}))
                row['referenceIssues']=[{'code':'REFERENCE_TYPE_CONFLICT',
                    'detail':f'Reference sources disagree: JSON declares {row["dataType"]}; the matching Excel reference declares {expected} for the same name and Group Code. Confirm the PLC wire datatype; this is not a PLC failure.'}]
                types={value['plcType'] for value in references if value['kind']=='plc' and value['plcType'] in PLC_TYPES}
                if len(types)==1:row['suggestedPlcType']=next(iter(types))
                model['warnings'].append(f'{row["sheet"]}:{row["row"]}: '+row['referenceIssues'][0]['detail'])
            elif row['plcType'] not in PLC_TYPES:
                model['warnings'].append(f'{row["sheet"]}:{row["row"]}: Database datatype {row["dataType"]} has no declared PLC wire datatype; requirement needs review.')
        # A database schema may lag the Excel specification. Add omitted rows,
        # preserving existing definitions and keeping type conflicts reviewable.
        identity=lambda row:(name_key(row['name']),tuple(row['groupCodes']),row['kind'])
        present={identity(row) for row in model['parameters']}
        additions=[];named=0
        for workbook,filename in workbooks.get((service,department_key),[]):
            for original in workbook['parameters']:
                if not original['name']:continue
                named+=1;key=identity(original)
                if key in present:continue
                references=locations.get((name_key(original['name']),tuple(original['groupCodes'])),[])
                row={**original,'excelReferences':[{field:value[field] for field in ('source','sheet','row','dataType')} for value in references],
                     'referenceOrigin':'workbook-supplement'}
                wire_types={value['plcType'] for value in references if value['kind']==row['kind'] and value['plcType']}
                if row['kind']=='plc' and len(wire_types)>1:
                    row['referenceIssues']=[{'code':'REFERENCE_TYPE_CONFLICT','detail':'Excel worksheets disagree on the PLC datatype for the same name and Group Code: '+', '.join(sorted(wire_types))+'. Confirm the reference; this is not a PLC failure.'}]
                model['parameters'].append(row);present.add(key)
                collections=choice['raw']['keysList']
                suffix=re.search(r'_(shift_live|shift|doff|hours?|hourwise|minutes?.*|raw_data|events|stoppages|faults|speed_pattern)$',row['sheet'],re.I)
                target=next((sheet for sheet in collections if suffix and sheet.casefold().endswith(suffix[0].casefold())),row['sheet'])
                collections.setdefault(target,[]).append({'tagName':row['name'],'dataType':row['dataType'] or None,
                    'groupCode':row['groupCodeSource'] or None,'formula':row['formula'] or None,
                    'tdEngineKey':row.get('tdEngineKey'),'mongoKey':row.get('mongoKey'),
                    'isRequired':row['required'],'isHost':row['kind']=='server','isAutoCalc':row['kind']=='formula',
                    'excelReference':{'source':filename,'sheet':row['sheet'],'row':row['row']}})
                additions.append({'name':row['name'],'groupCodes':row['groupCodes'],'kind':row['kind'],
                    'source':filename,'sheet':row['sheet'],'row':row['row']})
        write_json(path,choice['raw']);model['databaseModel']=choice['raw']
        model['sourceSha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        # Retain the selected source model's ID when adding workbook evidence,
        # so saved model selections keep pointing to the refreshed definition.
        model['workbookCoverage']={'namedRows':named,'addedRequirements':len(additions)}
        for row in model['parameters']:
            row['dataTypeRole']='wire' if row.get('plcDataType') else 'value'
            row['ignoreNameSeparators']=mapping_rules.get('ignoreNameSeparators') is True
            row['numericValueType']=row['dataType'].strip().upper() in mapping_rules.get('numericValueTypes',[])
            for rule in mapping_rules.get('aliases',[]):
                if service==rule['service'] and department_key in {machine_key(value) for value in rule['departments']} and row['groupCodes']==[rule['groupCode']] and name_key(row['name']) in {name_key(value) for value in rule['names']}:
                    row.update(aliases=rule['names'],canonicalName=rule['canonicalName'],mappingSource='knowledge/master/data_model_rules.json')
            # A single consistent workbook numeric definition clarifies legacy
            # database mistakes such as TIMESTAMP on a production-weight field.
            references=locations.get((name_key(row['name']),tuple(row['groupCodes'])),[])
            supported={value['plcType'] for value in references if value['kind']=='plc' and value['plcType']}
            if row.get('referenceIssues') and len(supported)==1 and next(iter(supported)) in {'REAL','LREAL'} and row['plcType'] not in {'REAL','LREAL'} and not row.get('plcDataType'):
                previous=row['dataType'];row['referenceCorrections']=[{'field':'dataType','previous':previous,'value':next(iter(supported)),'source':'Consistent numeric Excel definition for the same name and Group Code.'}]
                row.update(dataType=next(iter(supported)),plcType=next(iter(supported)),numericValueType=True)
                row.pop('referenceIssues',None)
        model['mappingRulesSource']='knowledge/master/data_model_rules.json'
        corrected={(row['sheet'],row['row']) for row in model['parameters'] if row.get('referenceCorrections')}
        model['warnings']=[warning for warning in model['warnings'] if not any(warning.startswith(f'{sheet}:{number}:') for sheet,number in corrected)]
        corrections.extend({'service':service,'machine':department,'name':row['name'],'groupCodes':row['groupCodes'],
            'changes':row['referenceCorrections'],'excelReferences':row.get('excelReferences',[])} for row in model['parameters'] if row.get('referenceCorrections'))
        definitions={(name_key(row['name']),tuple(row['groupCodes']),row['kind']):row for row in model['parameters']}
        for collection,items in choice['raw']['keysList'].items():
            for record in items:
                parsed=parse_model(json.dumps({'controleCode':department,'keysList':{collection:[record]}}).encode(),path.name,service,department)['parameters'][0]
                definition=definitions.get(identity(parsed))
                if not definition:continue
                for field in ('dataTypeRole','numericValueType','aliases','canonicalName','mappingSource','referenceCorrections','ignoreNameSeparators'):
                    if field in definition:record[field]=definition[field]
                if definition.get('referenceCorrections'):
                    record['originalDataType']=record.get('dataType');record['dataType']=definition['dataType']
        write_json(path,choice['raw']);model['sourceSha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        coverage.append({'service':service,'machine':department,'namedWorkbookRows':named,'added':additions})
        catalog.append(model)
    old=output/'catalog.json';legacy=output/'legacy_catalog.json'
    if old.is_file() and not legacy.exists():
        previous=json.loads(old.read_text(encoding='utf-8'))
        if any(not model.get('fixed') for model in previous.get('models',[])):write_json(legacy,previous)
    manifest={'schemaVersion':1,'selection':'Database JSON plus all named workbook requirements; original definitions and conflicts retained.',
              'sources':sources,'sourceIssues':issues,'fixedModels':[{'service':model['service'],'department':model['machine'],
                  'file':model['sourceRelativePath'],'originalSource':model['originalSource'],'parameters':len(model['parameters'])} for model in catalog]}
    write_json(output/'source_manifest.json',manifest)
    write_json(output/'workbook_coverage.json',{'schemaVersion':1,'models':coverage})
    write_json(output/'reference_corrections.json',{'schemaVersion':1,'corrections':corrections})
    write_json(output/'catalog.json',{'schemaVersion':1,'fixedReferences':True,'models':catalog,'importIssues':issues})
    return catalog,issues


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=APP_ROOT.parent/'Data Modelling')
    parser.add_argument('--output',type=Path,default=APP_ROOT/'knowledge/data_models')
    args=parser.parse_args()
    models,issues=build(args.source,args.output)
    print(f'Created {len(models)} fixed service/department models in {args.output}.')
    for issue in issues:print(f'Source issue: {issue["source"]}: {issue["error"]}')
