"""Resolve numeric HMI limits from current PLC memory and explain their producers."""
import math
from .compiler import walk_ir


def limit_values(control, runtime):
    props=control.get('properties',{});result={}
    for key in ('min','max'):
        label=key.capitalize();binding=control.get(key+'Binding')
        configured=bool(binding) or props.get(label+'Datapoint') not in (None,'','None')
        raw=None;error=''
        try:
            raw=runtime.get_value(binding or '') if configured else props.get(label+'Value')
            if not configured and raw in (None,'','None'):continue
            if isinstance(raw,bool) or not isinstance(raw,(str,int,float)):raise ValueError('Limit is not numeric.')
            value=float(raw)
            if not math.isfinite(value):raise ValueError('Limit is not finite.')
        except (ValueError,TypeError,KeyError,IndexError) as problem:
            value=None;error=str(problem)
        result[key]={'value':value,'binding':binding or '', 'resolved':not bool(error),'error':error}
    return result


def producers(runtime,binding):
    cache=getattr(runtime,'_hmi_limit_producers',None)
    if cache is None:cache=runtime._hmi_limit_producers={}
    if binding not in cache:
        locations=[]
        try:
            record,_=runtime.value_reference(binding)
            for unit in runtime.units.values():
                for node in walk_ir(unit.get('sections',[])):
                    target=node.get('target',{}) if node.get('op')=='assign' else {}
                    if target.get('op')!='ref' or target.get('name')!=record['name']:continue
                    try:
                        if runtime.value_reference(target['name'],unit['scope'])[0]['id']!=record['id']:continue
                    except (ValueError,TypeError,KeyError):continue
                    row={'source':unit['source'],'line':node.get('line',1),'unitId':unit['id']}
                    if row not in locations:locations.append(row)
        except (ValueError,TypeError,KeyError):pass
        cache[binding]=locations[:24]
    return [{**row,'scheduled':row['unitId'] in runtime.active_units} for row in cache[binding]]


def numeric_status(control,runtime):
    result=limit_values(control,runtime)
    for limit in result.values():
        if limit['binding']:limit['producers']=producers(runtime,limit['binding'])
    minimum=result.get('min',{}).get('value');maximum=result.get('max',{}).get('value')
    restricted=minimum is not None and maximum is not None and maximum<=minimum
    preview=runtime.project.get('executionScope',{}).get('mode')=='hmi-preview'
    message=''
    if any(not limit['resolved'] for limit in result.values()):message='A configured input limit is unresolved. Inspect its source binding.'
    elif restricted:
        dynamic=any(limit.get('binding') for limit in result.values())
        message=('This range follows PLC memory. '+('The login preview excludes machine initialization; open the full project for process values.' if preview else 'Review the bound process setting and run its initialization task before entering a value.')) if dynamic else 'The source configures a fixed or reversed input range.'
    return {'limits':result,'message':message,'restricted':restricted,'loginPreview':preview,'initialized':runtime._initialized}


def require_numeric(control,runtime,value):
    for key,limit in limit_values(control,runtime).items():
        label='minimum' if key=='min' else 'maximum'
        if not limit['resolved']:raise ValueError('Configured HMI '+label+' is unresolved: '+(limit['binding'] or label)+'.')
        if (key=='min' and value<limit['value']) or (key=='max' and value>limit['value']):
            source=' from '+limit['binding'] if limit['binding'] else ''
            status=numeric_status(control,runtime)
            raise ValueError(f'Value {value:g} is outside the configured HMI {label} {limit["value"]:g}{source}. '+status['message'])
