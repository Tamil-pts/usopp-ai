"""VC4 selection indices, captions and PLC types use one mapping."""
import math
from .hmi_text import expand_text


def selection_options(model,control,runtime):
    props=control.get('properties',{})
    offset=int(props.get('TextIndexOffset') or 0)
    mode=props.get('TextSource','MultipleTexts')
    path=control.get('textGroup')
    if mode=='MultipleTexts':
        group=model.get('hmi',{}).get('textGroups',{}).get(path)
        if group is None:raise ValueError('Selection text group is unresolved for this HMI target.')
        entries=[]
        for index,captions in group.items():
            label=captions.get('en',next(iter(captions.values()),'')) if isinstance(captions,dict) else str(captions)
            entries.append((int(index),expand_text(label,model.get('hmi',{}).get('textSnippets',{}).get(path,{}),runtime)))
    elif mode=='MultipleStrings':
        values=runtime.get_value(control.get('textBinding') or '')
        if not isinstance(values,list) or not all(isinstance(v,str) for v in values):raise ValueError('Selection STRING array is unresolved.')
        entries=list(enumerate(values[:4096]))
    else:raise ValueError('Selection text source is unsupported.')
    _,reference=runtime.value_reference(control.get('binding') or '')
    spec=runtime.memory.reference_spec(reference)
    bounds={}
    for label in ('Min','Max'):
        bound=control.get(label.lower()+'Binding')
        configured=props.get(label+'Datapoint') not in (None,'','None')
        value=runtime.get_value(bound or '') if configured else props.get(label+'Index')
        if value in (None,'','None'):continue
        number=float(value)
        if not math.isfinite(number) or number!=int(number):raise ValueError('Selection index bound is unresolved.')
        bounds[label]=int(number)
    if bounds.get('Min',-math.inf)>bounds.get('Max',math.inf):raise ValueError('Selection index bounds are reversed.')
    result=[]
    for index,label in sorted(entries):
        value=index-offset
        if not bounds.get('Min',-math.inf)<=value<=bounds.get('Max',math.inf):continue
        try:converted=runtime.memory.coerce(value,spec)
        except ValueError:continue
        if type(converted) not in (bool,int) or int(converted)!=value:continue
        result.append({'value':value,'text':label,'textIndex':index})
    if not result:raise ValueError('No configured selection index can be written to this PLC field.')
    return result


def selection_value(model,control,runtime,value):
    _,reference=runtime.value_reference(control.get('binding') or '')
    converted=runtime.memory.coerce(value,runtime.memory.reference_spec(reference))
    if type(converted) not in (bool,int):raise ValueError('Select a configured integral index.')
    if int(converted) not in {row['value'] for row in selection_options(model,control,runtime)}:
        raise ValueError('Select one of the configured HMI choices within its current limits.')
    return converted
