"""Create editable department/service/sheet dashboard templates from source Excel."""
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.core.data_models import clean,header,parse_model
from scripts.build_data_model_knowledge import write_json
from openpyxl import load_workbook
from backend.core.dashboard_definitions import enrich
from backend.core.data_models import machine_key


def view_name(sheet):
    value=sheet.casefold()
    for token,label in [('shift_live','LIVE'),('doff','Doff'),('shift','Shift'),('hour','Hourly'),
                        ('minut','Minute trend'),('raw_data','Raw data'),('speed_pattern','Speed pattern'),
                        ('event','Events'),('stoppage','Stoppages'),('fault','Faults')]:
        if token in value:return label
    return sheet


def build():
    destination=ROOT/'knowledge/dashboard_layouts';catalog=[]
    source=ROOT/'knowledge/data_models/reference_sources'
    models=json.loads((ROOT/'knowledge/data_models/catalog.json').read_text(encoding='utf-8'))['models']
    rules=json.loads((ROOT/'knowledge/master/data_model_rules.json').read_text(encoding='utf-8'))
    for path in sorted(source.rglob('*Key_Definitions_and_Source_Mapping.xlsx')):
        service=path.parent.name.upper()
        model=parse_model(path.read_bytes(),path.name,service)
        keys={};book=load_workbook(path,read_only=True,data_only=True)
        try:
            for sheet in book:
                columns=None
                for number,row in enumerate(sheet.values,1):
                    if columns is None:
                        if number>25:break
                        names={header(v):i for i,v in enumerate(row) if v is not None}
                        if 'datatype' in names and 'groupcode' in names:columns=names
                        continue
                    values=lambda token:[clean(row[i]) for name,i in columns.items() if token in name and i<len(row) and clean(row[i])]
                    cell=lambda name:clean(row[columns[name]]) if name in columns and columns[name]<len(row) else ''
                    keys[(sheet.title,number)]={'keys':values('keyname'),'unit':next(iter(values('unit')),''),
                        'tdEngineKey':cell('keynametdengine'),'mongoKey':cell('keynamerequiredinmongodb')}
        finally:book.close()
        by_sheet=defaultdict(list)
        for row in model['parameters']:by_sheet[row['sheet']].append(row)
        for sheet,rows in by_sheet.items():
            slug=re.sub('[^a-z0-9]+','-',sheet.casefold()).strip('-')
            ident=f'{service.lower()}-{model["machine"].lower()}-{slug}'
            parameters=[];excluded=[]
            for row in rows:
                extra=keys.get((sheet,row['row']),{'keys':[],'unit':''})
                if not row['name'] or row['kind']=='server':
                    excluded.append({'row':row['row'],'name':row['name'],'reason':'Server/context field' if row['kind']=='server' else 'Unnamed workbook row'})
                    continue
                parameters.append({'id':f'row-{row["row"]}', 'name':row['name'], 'dataType':row['plcType'],
                    'groupCodes':row['groupCodes'],'kind':row['kind'],'formula':row['formula'],**extra,
                    'source':{'workbook':path.relative_to(source).as_posix(),'sheet':sheet,'row':row['row']}})
            # Retain nonnumeric definitions in the template audit, but do not
            # pretend the numeric calculation engine can render text values.
            numeric=[p for p in parameters if p['kind']=='formula' or p['dataType'] in
                     {'BOOL','BYTE','SINT','USINT','INT','UINT','DINT','UDINT','REAL','LREAL'}]
            for p in parameters:
                if p not in numeric:excluded.append({'row':p['source']['row'],'name':p['name'],'reason':'Text, date or unresolved PLC datatype; retained in parameters for review'})
            priorities={'PMS':r'production|efficiency|utilization|delivery|doff|run time',
                        'QMS':r'cv|sliver|thick|hank|quality|^u[% ]',
                        'CMS':r'energy|temperature|power|pressure|current|voltage|humidity'}
            featured=[];featured_names=set()
            for p in numeric:
                if re.search(priorities[service],p['name'],re.I) and p['name'].casefold() not in featured_names:
                    featured.append(p);featured_names.add(p['name'].casefold())
                if len(featured)==6:break
            widgets=[{'title':p['name'][:80],'widget':'value','span':1,'parameterIds':[p['id']]} for p in featured]
            if featured:widgets.append({'title':featured[0]['name'][:65]+' trend','widget':'line','span':3,'parameterIds':[featured[0]['id']]})
            for start in range(0,len(numeric),12):
                widgets.append({'title':f'{view_name(sheet)} readings {start//12+1}','widget':'table','span':3,
                                'parameterIds':[p['id'] for p in numeric[start:start+12]]})
            template={'format':'usopp-dashboard-template','schemaVersion':1,'id':ident,
                'name':f'{service} / {model["machine"]} / {view_name(sheet)}'[:80],
                'service':service,'machine':model['machine'],'view':view_name(sheet),
                'mode':'live' if view_name(sheet) in {'LIVE','Raw data'} else 'report','columns':3,
                'source':{'workbook':path.relative_to(source).as_posix(),'sheet':sheet,
                          'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},
                'parameters':parameters,'excluded':excluded,'widgets':widgets}
            definition=next((item for item in models if item['service']==service and machine_key(item['machine'])==machine_key(model['machine'])),{})
            enrich(template,definition,view_name,rules)
            if len(widgets)>32:raise ValueError(f'{ident}: split this sheet into multiple layouts (32 widget limit).')
            file=Path(service)/model['machine']/f'{slug}.json'
            write_json(destination/file,template)
            catalog.append({key:template[key] for key in ('id','name','service','machine','view','mode','source')}|
                {'file':file.as_posix(),'parameterCount':len(parameters),'displayCount':len(numeric),'widgetCount':len(widgets),'excludedCount':len(excluded)})
    write_json(destination/'catalog.json',{'schemaVersion':1,'templates':catalog})
    print(f'Created {len(catalog)} sheet layouts from {len(set(t["source"]["workbook"] for t in catalog))} workbooks.')


if __name__=='__main__':build()
