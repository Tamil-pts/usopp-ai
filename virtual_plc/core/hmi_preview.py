"""Select actual credential/visibility writers for an explicit HMI preview."""
from copy import deepcopy
from .compiler import walk_ir


def preview_model(model,runtime,page_id,parent_id):
    page=next((p for p in model.get('hmi',{}).get('pages',[]) if p['id']==page_id),None)
    if not page:raise ValueError('Choose an analyzed HMI page.')
    credentials,levels,statuses=set(),set(),set()
    for control in page.get('objects',[]):
        statuses.update(v for v in [control.get('statusBinding'),(control.get('layerState') or {}).get('statusBinding')] if v)
        if control.get('kind')!='password':continue
        if control.get('passwordLevelBinding'):levels.add(control['passwordLevelBinding'])
        snippets=model.get('hmi',{}).get('textSnippets',{}).get(control.get('textGroup'),{})
        credentials.update(s['binding'] for s in snippets.values() if s.get('binding') and s.get('classId','').lower()=='0x00002002')
    # Visibility controls often live on other pages of this same HMI target.
    prefix=page['source'].rsplit('/Pages/',1)[0]+'/'
    for other in model.get('hmi',{}).get('pages',[]):
        if not other.get('source','').startswith(prefix):continue
        for c in other.get('objects',[]):
            statuses.update(c[k] for k in ('statusBinding','lockingBinding') if c.get(k))
    def identity(name,scope=None):
        try:return runtime.memory.resolve(name,scope)['id']
        except ValueError:return name
    credentials={identity(n) for n in credentials};levels={identity(n) for n in levels};statuses={identity(n) for n in statuses}
    assigned={p for t in model.get('tasks',[]) if t.get('enabled',True) for p in t.get('programs',[])}
    selected=[]
    for program in model.get('programs',[]):
        if program['id'] not in assigned or program.get('kind')!='program' or program.get('entry')!='cyclic':continue
        unit=runtime.units.get(program['id'],{});writes,reads=set(),set()
        pure_flags=True
        for node in walk_ir(unit.get('sections',[])):
            if node['op']=='ref':reads.add(identity(node['name'],program['scope']))
            if node['op']=='call':pure_flags=False
            if node['op']=='assign':
                target=node.get('target',{})
                if target.get('op')!='ref' or target.get('path'):pure_flags=False;continue
                writes.add(identity(target['name'],program['scope']))
                value=node.get('value',{})
                if value.get('op')!='literal' or value.get('value') not in (0,1,False,True):pure_flags=False
        local={v['id'] for v in model.get('variables',[]) if v.get('scope')==program['scope']}
        if writes&credentials or (reads&levels and writes&statuses and (writes <= statuses|local or pure_flags)):selected.append(program)
    if not selected:raise ValueError('No assigned source program could be linked to this page\'s password/login bindings.')
    ids={p['id'] for p in selected};scopes={p['scope'] for p in selected}
    by_id={p['id']:p for p in model.get('programs',[])}
    result=deepcopy(model);result['tasks']=[]
    for task in model.get('tasks',[]):
        programs=[p for p in task.get('programs',[]) if p in ids]
        if not programs:continue
        row=deepcopy(task);row['programs']=programs
        row['assignments']=[a for a in row.get('assignments',[]) if any(p in ids for p in a.get('programs',[]))]
        for key in ('initializationPrograms','exitPrograms'):
            row[key]=[p for p in row.get(key,[]) if by_id.get(p,{}).get('scope') in scopes]
        result['tasks'].append(row)
    result['initializationPrograms']=[];result['exitPrograms']=[]
    task_codes={'program-unresolved','task-interval-unresolved','tasks-unresolved'}
    result['diagnostics']=[d for d in result.get('diagnostics',[]) if d.get('code') not in task_codes]
    result.pop('compatibility',None)
    result['executionScope']={'mode':'hmi-preview','parentProjectId':parent_id,'pageId':page_id,
        'programIds':[p['id'] for p in selected],'completeMachineExecution':False,
        'notice':'Only the source programs linked to HMI credentials and login visibility execute. Other machine tasks are excluded.',
        'excludedProgramCount':len(assigned-ids)}
    result['name']=model.get('name','PLC')+' - HMI login preview'
    return result
