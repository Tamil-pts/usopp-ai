"""Conservative field connections from selected I/O and compiled logic evidence."""
from collections import defaultdict
import hashlib
import re

from .components import binding_reference


def identity_parts(address):
    name=address.rsplit(':',1)[-1]
    name=re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',name).upper()
    name=re.sub(r'^(?:ED_)?D[IO]_', '',name)
    return re.sub(r'[^A-Z0-9]+','_',name).strip('_')


def role(address):
    text=identity_parts(address)
    endings=[('extended',r'(?:EXTENDED|EXTEND_FB|EXTEND_FEEDBACK|FORWARD_LIMIT)'),
             ('retracted',r'(?:RETRACTED|RETRACT_FB|RETRACT_FEEDBACK|HOME_LIMIT)'),
             ('extend',r'(?:EXTEND_CMD|EXTEND_COMMAND|EXTEND|FORWARD_SOLENOID)'),
             ('retract',r'(?:RETRACT_CMD|RETRACT_COMMAND|RETRACT|RETURN_SOLENOID)'),
             ('running',r'(?:RUNNING|RUN_FB|RUN_FEEDBACK|RUNNING_FB)'),
             ('ready',r'(?:READY|RDY)'),('fault',r'(?:FAULT|FLT)'),
             ('command',r'(?:RUN_CMD|RUN_COMMAND|START_CMD|START_COMMAND|COMMAND|CMD|START|RUN|ENABLE)')]
    for key,ending in endings:
        match=re.fullmatch(r'(.+)_'+ending,text)
        if match:return match[1],key
    return text,''


def discover(runtime,index):
    """Names suggest a role; hardware direction and a logic path establish a link.

    No generated feedback may replace a PLC writer or a manual component.
    Uncertain associations remain proposals, never live signal sources.
    """
    channels={}
    for channel in runtime.project.get('hardware',{}).get('channels',[]):
        try:
            address,record,spec=binding_reference(runtime,channel.get('variableId',''))
            if spec.get('kind')=='scalar':channels[address]=channel
        except (ValueError,TypeError,KeyError,IndexError):continue
    readers={value for edges in index.writers.values() for edge in edges for value in edge['inputs']}
    addresses=set(channels)|set(index.writers)|readers
    groups=defaultdict(lambda:defaultdict(list))
    for address in sorted(addresses):
        try:
            canonical,record,spec=binding_reference(runtime,address)
            if spec.get('type')!='BOOL' or spec.get('kind')!='scalar' or record.get('constant'):continue
            stem,key=role(canonical)
            if key:groups[(record['scope'],stem)][key].append(canonical)
        except (ValueError,TypeError,KeyError,IndexError):continue

    def linked(command,feedback):
        pending=[(command,0)];seen=set()
        while pending and len(seen)<256:
            target,depth=pending.pop()
            if target in seen:continue
            seen.add(target)
            if target==feedback:return True
            if depth<12:
                for edge in index.writers.get(target,[]):
                    pending.extend((value,depth+1) for value in edge['inputs'])
        return False

    proposals=[]
    for (_,stem),ports in sorted(groups.items()):
        kind='cylinder' if ports.get('extend') else 'vfd' if re.search(r'VFD|DRIVE|INVERTER',stem) else 'motor' if re.search(r'MOTOR|MTR',stem) else None
        if not kind:continue
        command_key='extend' if kind=='cylinder' else 'command'
        commands=[value for value in ports.get(command_key,[]) if value in index.writers and channels.get(value,{}).get('direction')!='input']
        if not commands:continue
        feedback_keys=('extended','retracted') if kind=='cylinder' else ('running','ready','fault')
        feedback={key:[value for value in ports.get(key,[]) if value in readers and value not in index.writers
                       and channels.get(value,{}).get('direction')!='output'] for key in feedback_keys}
        if not any(feedback.values()):continue
        unique=len(commands)==1 and all(len(values)<=1 for values in feedback.values())
        command=commands[0]
        bindings={('extend' if kind=='cylinder' else 'run' if kind=='vfd' else 'enable'):command}
        bindings.update({key:values[0] for key,values in feedback.items() if len(values)==1})
        if kind=='cylinder' and len(ports.get('retract',[]))==1:
            retract=ports['retract'][0]
            if retract in index.writers:bindings['retract']=retract
        selected=[address for key,address in bindings.items() if key in feedback_keys]
        wired=channels.get(command,{}).get('direction')=='output' and all(channels.get(address,{}).get('direction')=='input' for address in selected)
        related=bool(selected) and all(linked(command,address) for address in selected)
        strong=unique and wired and related
        edge=index.writers[command][0]
        evidence={'method':'Selected hardware I/O and compiled logic dependencies',
                  'source':edge['source'],'line':edge['line'],'command':command,
                  'confidence':'high' if strong else 'review','hardwareConfirmed':wired,'logicConfirmed':related,
                  'mappingSource':'automatic-analysis','feedback':', '.join(selected)}
        reason=('Unique command and external feedback have matching device identities, opposite selected hardware directions and a compiled logic dependency.'
                if strong else 'Confirm this association: '+('; '.join(note for condition,note in
                    [(not unique,'multiple candidate tags'),(not wired,'hardware direction is incomplete'),
                     (not related,'no verified logic dependency')] if condition)))
        identity='auto-'+hashlib.sha256((kind+':'+command).encode()).hexdigest()[:16]
        proposals.append({'id':identity,'name':stem.replace('_',' '),'kind':kind,'enabled':True,
                          'bindings':bindings,'links':{},'config':{'startDelayMs':150} if kind=='motor' else {},'evidence':evidence,
                          'assumptions':[reason,'Generic physical delays, stroke origin and units are editable model settings.'],
                          'automatic':strong,'reason':reason,
                          'candidates':{key:values for key,values in ports.items() if len(values)>1}})
    return proposals
