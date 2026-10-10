"""Build fixed service/department JSON models from the supplied database keys.

Excel workbooks are retained as source clarification. Database JSON definitions
take precedence; workbooks supply a model only when no matching JSON exists.
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
from backend.core.data_models import SERVICES,clean,header,machine_key,name_key,parse_model


def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
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
        archived.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,archived)
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
    catalog=[]
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
                locations.setdefault(key,[]).append({'source':filename,'sheet':row['sheet'],'row':row['row']})
        for row in model['parameters']:
            row['excelReferences']=locations.get((name_key(row['name']),tuple(row['groupCodes'])),[])
        catalog.append(model)
    old=output/'catalog.json';legacy=output/'legacy_catalog.json'
    if old.is_file() and not legacy.exists():
        previous=json.loads(old.read_text(encoding='utf-8'))
        if any(not model.get('fixed') for model in previous.get('models',[])):write_json(legacy,previous)
    manifest={'schemaVersion':1,'selection':'Own-service database JSON; other-service JSON collections; workbook fallback.',
              'sources':sources,'sourceIssues':issues,'fixedModels':[{'service':model['service'],'department':model['machine'],
                  'file':model['sourceRelativePath'],'originalSource':model['originalSource'],'parameters':len(model['parameters'])} for model in catalog]}
    write_json(output/'source_manifest.json',manifest)
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
