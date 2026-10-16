"""Editable, scoped interpretation of reference value types and parameter names."""
import hashlib
import json
from backend.core.data_models import PLC_TYPES,machine_key,name_key,plc_type,entry


def load_rules(path):
    raw=path.read_bytes() if path.is_file() else b'{"schemaVersion":1,"numericValueTypes":[],"aliases":[],"formulaOverrides":[]}'
    return json.loads(raw),hashlib.sha256(raw).hexdigest()


def validate_rules(data):
    if not isinstance(data,dict) or data.get('schemaVersion')!=1:raise ValueError('Use reference rules schemaVersion 1.')
    if not isinstance(data.get('numericValueTypes'),list) or len(data['numericValueTypes'])>20 or any(not isinstance(value,str) or len(value)>40 for value in data['numericValueTypes']):raise ValueError('List the numeric database value types.')
    if not isinstance(data.get('aliases'),list) or len(data['aliases'])>1000:raise ValueError('Use at most 1,000 scoped name mappings.')
    if 'ignoreNameSeparators' in data and type(data['ignoreNameSeparators']) is not bool:raise ValueError('ignoreNameSeparators must be true or false.')
    for row in data['aliases']:
        if not isinstance(row,dict) or row.get('service') not in {'PMS','QMS','CMS'} or type(row.get('groupCode')) is not int or not 0<=row['groupCode']<=65535:raise ValueError('Each mapping needs a service and numeric Group Code.')
        for key in ('departments','names'):
            if not isinstance(row.get(key),list) or not 1<=len(row[key])<=40 or any(not isinstance(value,str) or not value.strip() or len(value)>300 for value in row[key]):raise ValueError('Each mapping needs department names and parameter names.')
        if not isinstance(row.get('canonicalName'),str) or not row['canonicalName'].strip() or len(row['canonicalName'])>300:raise ValueError('Give each mapping a canonical name.')
        if row.get('plcDataType') and plc_type(row['plcDataType']) not in PLC_TYPES:raise ValueError('Choose a supported explicit PLC wire datatype.')
        if 'enabled' in row and type(row['enabled']) is not bool:raise ValueError('A mapping enabled value must be true or false.')
    if not isinstance(data.get('formulaOverrides',[]),list) or len(data.get('formulaOverrides',[]))>500:raise ValueError('Use at most 500 formula overrides.')
    for row in data.get('formulaOverrides',[]):
        if not isinstance(row,dict) or row.get('service') not in {'PMS','QMS','CMS'} or any(not isinstance(row.get(key),str) or not row[key].strip() or len(row[key])>400 for key in ('machine','view','parameter','expression')):raise ValueError('A formula override needs service, machine, view, parameter and expression (up to 400 characters).')
        if 'enabled' in row and type(row['enabled']) is not bool:raise ValueError('A formula enabled value must be true or false.')
    return {key:value for key,value in data.items() if key not in {'revision','canEdit'}}


def apply_parameter(row,service,machine,rules):
    if row.get('mappingSource')=='knowledge/master/data_model_rules.json':
        row.pop('aliases',None);row.pop('canonicalName',None)
    if 'sourceAliases' in row:row['aliases']=row['sourceAliases'][:]
    row['ignoreNameSeparators']=rules.get('ignoreNameSeparators') is True
    if row.get('dataTypeRole')=='value':row['numericValueType']=row.get('dataType','').strip().upper() in rules.get('numericValueTypes',[])
    for rule in rules.get('aliases',[]):
        if rule.get('enabled') is False:continue
        if service!=rule['service'] or machine_key(machine) not in {machine_key(value) for value in rule['departments']} or row.get('groupCodes')!=[rule['groupCode']]:continue
        if name_key(row.get('name')) not in {name_key(value) for value in rule['names']}:continue
        row.update(aliases=list(dict.fromkeys([*row.get('aliases',[]),*rule['names']])),canonicalName=rule['canonicalName'],mappingSource='knowledge/master/data_model_rules.json')
        if rule.get('plcDataType'):
            row.update(dataTypeRole='wire',plcType=plc_type(rule['plcDataType']),numericValueType=False)
            if 'keys' in row:row['dataType']=row['plcType']
            row['configuredPlcDataType']=row['plcType']
            if row.get('referenceIssues'):
                row['resolvedReferenceIssues']=row.pop('referenceIssues')
    return row


def apply_model(model,rules):
    for row in model['parameters']:apply_parameter(row,model['service'],model['machine'],rules)
    resolved={(row['sheet'],row['row']) for row in model['parameters'] if row.get('referenceCorrections') or row.get('resolvedReferenceIssues')}
    model['warnings']=[warning for warning in model.get('warnings',[]) if not any(warning.startswith(f'{sheet}:{number}:') for sheet,number in resolved)]
    definitions={(name_key(row['name']),tuple(row['groupCodes']),row['kind']):row for row in model['parameters']}
    for sheet,items in model.get('databaseModel',{}).get('keysList',{}).items():
        for record in items:
            parsed=entry(record.get('tagName'),record.get('dataType'),record.get('groupCode'),record.get('formula'),'','',0)
            if record.get('isHost'):parsed['kind']='server'
            elif record.get('isAutoCalc'):parsed['kind']='formula'
            definition=definitions.get((name_key(parsed['name']),tuple(parsed['groupCodes']),parsed['kind']))
            if not definition:continue
            for key in ('dataTypeRole','numericValueType','ignoreNameSeparators','aliases','canonicalName','mappingSource'):
                if key in definition:record[key]=definition[key]
                else:record.pop(key,None)
            if definition.get('configuredPlcDataType'):record['plcDataType']=definition['configuredPlcDataType']
    return model


def apply_starter(template,rules):
    for row in template['parameters']:
        apply_parameter(row,template['service'],template['machine'],rules)
        for override in rules.get('formulaOverrides',[]):
            if override.get('enabled') is False:continue
            if override['service']==template['service'] and machine_key(override['machine'])==machine_key(template['machine']) and override['view'].casefold()==template['view'].casefold() and override['parameter'].casefold() in {row['name'].casefold(),row['id'].casefold()}:
                row.update(kind='formula',formula=override['expression'])
                row['definitionSource']={'workbook':'knowledge/master/data_model_rules.json','sheet':'formulaOverrides','row':rules['formulaOverrides'].index(override)+1}
    return template
