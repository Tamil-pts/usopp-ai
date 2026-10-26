"""Source virtual key validation and live alarm-list cursor operations."""
import re
from .hmi_runtime import control_state

ALARM_COMMANDS={'Line Down','Line Up','Page Down','Page Up','Goto Document End','Goto Document Start'}


def target_control(page,action):
    match=re.fullmatch(r'Source\[local\]\.Layer\[([^\]]+)\]\.Control\[([^\]]+)\]',str(action.get('control') or ''),re.I)
    if not match:raise ValueError('The source virtual key has no resolved local control target.')
    choices=[c for c in page.get('objects',[]) if c['name']==match[2] and c.get('layer')==match[1]]
    if len(choices)!=1:raise ValueError('The source virtual key control target is missing or ambiguous.')
    control=choices[0]
    if control.get('kind')!='alarm' or action.get('command') not in ALARM_COMMANDS:
        raise ValueError('This control-dependent function is not simulated: '+str(action.get('command')))
    return control


def validate_actions(page,control,runtime):
    actions=control.get('actions',[])
    if not actions:raise ValueError('No source action is configured. Inspect the virtual key and active overlay.')
    from .hmi_runtime import writable
    for action in actions:
        state=control_state(action,runtime)
        if state['locked']:raise ValueError('Virtual key: '+state['reason'])
        kind=action['kind']
        if kind=='unsupported':raise ValueError(action.get('reason','Unsupported source key action.')+' '+str(action.get('classId','')))
        if kind=='control':
            target=target_control(page,action);state=control_state(target,runtime)
            if not state['visible'] or state['locked']:raise ValueError('The target alarm control is hidden or locked.')
        if kind in {'write','toggle','momentary'}:
            reference=writable(runtime,action.get('variable'));spec=runtime.memory.reference_spec(reference)
            runtime.memory.coerce(action.get('value','1'),spec)
            if kind in {'toggle','momentary'}:runtime.memory.coerce(action.get('resetValue','0'),spec)
        if action.get('completion'):
            completion=action['completion'];reference=writable(runtime,completion['variable'])
            runtime.memory.coerce(completion['value'],runtime.memory.reference_spec(reference))
    return actions


def active_alarms(model,runtime,page=None):
    rows=[]
    for group in model.get('hmi',{}).get('alarmGroups',[]):
        if page and not group.get('source','').startswith(page.get('target','')+'/') and '/VCShared/' not in group.get('source',''):continue
        for alarm in group.get('items',[]):
            try:active=runtime.get_value(alarm.get('binding')) in (True,1)
            except (ValueError,KeyError,TypeError,IndexError):continue
            if active:rows.append({**alarm,'group':group['name'],'groupIndex':group.get('index'),'source':group['source'],'id':group['source']+':'+str(alarm['index'])})
    return rows


def move_alarm(model,runtime,page,action):
    control=target_control(page,action)
    if not hasattr(runtime,'_hmi_alarm_cursors'):runtime._hmi_alarm_cursors={}
    rows=active_alarms(model,runtime,page);ids=[a['id'] for a in rows]
    previous=runtime._hmi_alarm_cursors.get(control['id'])
    index=ids.index(previous) if previous in ids else 0
    command=action['command']
    index=({'Line Down':index+1,'Line Up':index-1,'Page Down':index+5,'Page Up':index-5,
            'Goto Document Start':0,'Goto Document End':len(rows)-1})[command]
    runtime._hmi_alarm_cursors[control['id']]=ids[max(0,min(len(ids)-1,index))] if ids else None


def selected_alarm(model,runtime,target_name):
    """VA_GetAlCurPos uses the first visible alarm control in source Z order."""
    from pathlib import PurePosixPath
    states=getattr(runtime,'_hmi_pages',{})
    pages=model.get('hmi',{}).get('pages',[])
    for target,state in states.items():
        if PurePosixPath(target).name!=target_name:continue
        page=next((p for p in pages if p['id']==state['pageId']),None)
        if not page:return None
        control=next((c for c in page.get('objects',[]) if c.get('kind')=='alarm' and control_state(c,runtime)['visible']),None)
        if not control:return None
        rows=active_alarms(model,runtime,page)
        cursor=getattr(runtime,'_hmi_alarm_cursors',{}).get(control['id'])
        return next((a for a in rows if a['id']==cursor),rows[0] if rows else None)
    return None


def diagnostics(model,runtime,page,control=None):
    from .hmi_limits import producers
    from .hmi_runtime import covering_control
    bindings=set()
    for layer in page.get('layers',[]):
        if layer.get('statusBinding'):bindings.add(layer['statusBinding'])
    if control:
        for key in ('binding','statusBinding','lockingBinding','textIndexBinding','passwordLevelBinding'):
            if control.get(key):bindings.add(control[key])
        bindings.update(a['variable'] for a in control.get('actions',[]) if a.get('variable'))
        cover=covering_control(page,control,runtime)
        if cover and cover.get('statusBinding'):bindings.add(cover['statusBinding'])
    result={}
    for binding in sorted(bindings):
        try:
            value=runtime.get_value(binding)
            result[binding]={'value':value if type(value) in (bool,int,float) else None,'producers':producers(runtime,binding)}
        except (ValueError,KeyError,TypeError,IndexError):result[binding]={'error':'Unresolved source binding.'}
    return {'bindings':result}
