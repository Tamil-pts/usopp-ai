"""Preserve all lifecycle entries and CPU assignment order of combined sources."""
PHASE_KEYS={'cyclic':'programs','init':'initializationPrograms','exit':'exitPrograms'}

def section_phase(section, default='cyclic'):
    if section.get('kind') in {'function','function_block','action'}:return None
    name=section.get('name','').upper().lstrip('_')
    return {'INIT':'init','CYCLIC':'cyclic','EXIT':'exit'}.get(name,default)

def unit_phases(unit):
    phases=list(dict.fromkeys(section_phase(s,unit.get('entry','cyclic')) for s in unit.get('sections',[])))
    return [p for p in phases if p] or [unit.get('entry','cyclic')]

def schedule_entries(task, phases):
    original={key:list(task.get(key,[])) for key in PHASE_KEYS.values()}
    declared=list(dict.fromkeys(p for rows in original.values() for p in rows))
    ordered=[]
    if not task.get('assignmentSource'):
        for assignment in task.get('assignments',[]):
            if assignment.get('enabled',True) and assignment.get('executable',True):
                ordered.extend(p for p in assignment.get('programs',[]) if p in declared)
    ordered=list(dict.fromkeys(ordered+declared))
    for phase,key in PHASE_KEYS.items():
        task[key]=[p for p in ordered if phase in phases.get(p,[name for name,k in PHASE_KEYS.items() if p in original[k]])]
