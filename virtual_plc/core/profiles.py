"""Explicit simulation initialization, separate from original declarations."""
from copy import deepcopy


def apply_profile(runtime,profile):
    if not isinstance(profile,dict) or profile.get('schemaVersion')!=1:raise ValueError('Unsupported simulation profile schema')
    if profile.get('project') and profile['project']!=runtime.project.get('name'):raise ValueError('Simulation profile belongs to another project')
    if profile.get('configuration') and profile['configuration']!=runtime.project.get('projectInfo',{}).get('activeConfiguration'):raise ValueError('Simulation profile belongs to another hardware configuration')
    values=profile.get('values',{})
    if not isinstance(values,dict) or len(values)>1024:raise ValueError('Use up to 1024 explicit initial values')
    prepared=[]
    for name,value in values.items():
        record,reference=runtime.value_reference(name)
        if reference.get('path'):raise ValueError('Initial profiles currently require complete declared variables')
        if record.get('constant') or record.get('ambiguous'):raise ValueError('Cannot initialize a constant or ambiguous variable')
        prepared.append((record,runtime.memory.coerce(value,record['_spec'])))
    for record,value in prepared:
        record['value']=deepcopy(value);record['_initial']=deepcopy(value);record['previous']=deepcopy(value)
        record['simulationInitialValue']=True
    return {'id':profile.get('id'),'name':profile.get('name'),'reference':profile.get('reference'),'variables':[record['id'] for record,value in prepared]}
