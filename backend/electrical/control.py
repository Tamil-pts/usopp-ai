"""Bounded discrete DC relay-control simulation of explicit terminal connectivity.

No analog, motor mechanics, PLC execution or PDF-geometry inference is performed.
"""
import math
from fastapi import HTTPException

KINDS={'supply':('plus','minus'),'contact_no':('in','out'),'contact_nc':('in','out'),'coil':('a1','a2'),'lamp':('a1','a2')}

def simulate(payload):
    devices=payload.get('devices');wires=payload.get('wires');inputs=payload.get('inputs',{});previous=payload.get('previous',{})
    def fail(message):raise HTTPException(400,message)
    if not isinstance(devices,list) or not 1<=len(devices)<=100 or not isinstance(wires,list) or len(wires)>300:fail('Use 1-100 devices and at most 300 wires.')
    if not isinstance(inputs,dict) or not isinstance(previous,dict) or len(inputs)>200 or len(previous)>100 or any(type(v) is not bool for v in [*inputs.values(),*previous.values()]):fail('Inputs and previous coil states must be bounded boolean maps.')
    ports=set();ids=set();coils=set();supplies=[]
    for d in devices:
        if not isinstance(d,dict):fail('Invalid device.')
        name=d.get('id');kind=d.get('kind')
        if not isinstance(name,str) or not name or ':' in name or len(name)>60 or name in ids or not isinstance(kind,str) or kind not in KINDS:fail('Device IDs must be unique and device kinds supported.')
        if kind.startswith('contact_') and not isinstance(d.get('control'),str):fail('Each contact needs a control reference.')
        ids.add(name);ports.update(name+':'+p for p in KINDS[kind])
        if kind=='coil':coils.add(name)
        if kind=='supply':
            voltage=d.get('voltage',24)
            if type(voltage) not in (float,int) or not math.isfinite(voltage) or not 0<voltage<=48:fail('This discrete control model supports DC supplies up to 48 V.')
            supplies.append(d)
    if len(supplies)!=1:fail('Use exactly one DC control supply.')
    controls={d.get('control') for d in devices if d['kind'].startswith('contact_')}
    if any(not isinstance(c,str) or c not in coils and c not in inputs for c in controls):fail('Each contact must reference an existing coil or explicit external input.')
    if any(c in inputs for c in coils) or any(c not in coils for c in previous):fail('Coils cannot be forced through external inputs; previous state must name existing coils.')
    links=[];wired=set()
    for w in wires:
        if not isinstance(w,dict) or not isinstance(w.get('from'),str) or not isinstance(w.get('to'),str) or w.get('from') not in ports or w.get('to') not in ports:fail('Wire endpoints must reference existing named terminals.')
        if w['from']==w['to']:fail('A wire cannot connect a terminal to itself.')
        links.append((w['from'],w['to']));wired.update((w['from'],w['to']))
    missing=sorted(ports-wired)
    if missing:fail('Unconnected terminals: '+', '.join(missing))
    states={c:previous.get(c,False) for c in coils};history=set();supply=supplies[0]['id']
    for iteration in range(32):
        signature=tuple(sorted(states.items()))
        if signature in history:raise HTTPException(409,'Relay feedback oscillates; no stable discrete state. Check interlocks and contact assignments.')
        history.add(signature);parent={p:p for p in ports}
        def root(p):
            while parent[p]!=p:parent[p]=parent[parent[p]];p=parent[p]
            return p
        def join(a,b):parent[root(a)]=root(b)
        for a,b in links:join(a,b)
        closed={}
        for d in devices:
            if d['kind'].startswith('contact_'):
                operated=states[d['control']] if d['control'] in coils else inputs[d['control']]
                closed[d['id']]=operated if d['kind']=='contact_no' else not operated
                if closed[d['id']]:join(d['id']+':in',d['id']+':out')
        positive=root(supply+':plus');negative=root(supply+':minus')
        if positive==negative:raise HTTPException(409,'Control supply short circuit detected. Simulation stopped.')
        energized={}
        for d in devices:
            if d['kind'] in {'coil','lamp'}:
                energized[d['id']]=root(d['id']+':a1')==positive and root(d['id']+':a2')==negative
        next_states={c:energized[c] for c in coils}
        if next_states==states:
            return {'status':'stable','engine':'discrete_dc_relay','iterations':iteration+1,'coils':states,'loads':energized,'contacts':closed,
                    'energized_wires':[i for i,w in enumerate(wires) if root(w['from'])==positive],
                    'notice':'Logical DC contact/coil states only. No current, motor speed, safety certification or imported drawing semantics inferred.'}
        states=next_states
    raise HTTPException(409,'No stable relay state within 32 iterations.')
