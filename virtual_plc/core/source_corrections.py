"""Auditable changes to an in-memory program copy, guarded by source hashes.

Never writes imported files. Every correction records its original expression,
replacement, reason and exact source fingerprint in the exported workspace.
"""
import hashlib
from copy import deepcopy


def merge_reviewed(model, existing, reviewed):
    """Add newly reviewed defaults on explicit jig restore; retain custom edits."""
    result=deepcopy(existing or {'schemaVersion':1,'corrections':[]})
    known={(row.get('source'),row.get('original')) for row in result.get('corrections',[])}
    sources={row['source']:row.get('originalCode',row.get('code','')) for row in model.get('programs',[])}
    defaults={(row.get('source'),row.get('original')) for row in reviewed.get('corrections',[])}
    custom_sources={source for source,original in known if (source,original) not in defaults}
    for row in reviewed.get('corrections',[]):
        token=(row.get('source'),row.get('original'))
        if token in known or token[0] in custom_sources:continue
        if hashlib.sha256(sources.get(token[0],'').encode()).hexdigest()!=row.get('codeSha256'):continue
        result.setdefault('corrections',[]).append(deepcopy(row));known.add(token)
    return result


def apply_corrections(model,document):
    if not isinstance(document,dict) or document.get('schemaVersion')!=1:raise ValueError('Unsupported source correction schema')
    corrections=document.get('corrections',[])
    if not isinstance(corrections,list) or len(corrections)>100:raise ValueError('Use at most 100 explicit source corrections')
    prepared={}
    diagnostics=[]
    if not isinstance(model.get('diagnostics',[]),list):raise ValueError('Source correction diagnostics must be a list')
    for item in corrections:
        if not isinstance(item,dict):raise ValueError('Every source correction must be an object')
        programs=[p for p in model.get('programs',[]) if p.get('source')==item.get('source')]
        if len(programs)!=1:raise ValueError('Correction source is missing or ambiguous: '+str(item.get('source')))
        program=programs[0]
        source=program['source']
        if source not in prepared:
            code=program.get('code','')
            if not isinstance(code,str):raise ValueError('Correction source code must be text: '+str(source))
            prepared[source]={'program':program,'originalCode':code,'code':code,'items':[],'spans':[]}
        staged=prepared[source]
        # All guards identify the original source received by this operation,
        # while replacements compose against its staged in-memory copy.
        code=staged['originalCode']
        if hashlib.sha256(code.encode('utf-8')).hexdigest()!=item.get('codeSha256'):raise ValueError('Source changed; review the correction again: '+item['source'])
        original,replacement=item.get('original'),item.get('replacement')
        if (not isinstance(original,str) or not original or not isinstance(replacement,str) or not replacement
                or code.count(original)!=1 or staged['code'].count(original)!=1
                or original.count('\n')!=replacement.count('\n')):
            raise ValueError('A correction must identify one exact expression and preserve source lines')
        start=code.index(original);end=start+len(original)
        if any(start<previous_end and previous_start<end for previous_start,previous_end in staged['spans']):
            raise ValueError('Source correction expressions overlap or repeat: '+str(source))
        if not isinstance(item.get('reason'),str) or not item['reason'].strip():raise ValueError('A source correction must include a reason')
        line=item.get('line',1)
        if type(line) is not int or line<1:raise ValueError('A source correction line must be a positive integer')
        staged['spans'].append((start,end))
        staged['code']=staged['code'].replace(original,replacement,1)
        staged['items'].append(deepcopy(item))
        diagnostics.append({'severity':'warning','code':'SIMULATION_SOURCE_CORRECTION','source':source,'line':line,
                            'message':item['reason']+' Original PLC file remains unchanged.',
                            'original':original,'replacement':replacement})
    audit=deepcopy(document)
    # Commit only after every source, hash, exact expression and audit record
    # has validated. A later failure leaves the entire caller model unchanged.
    for staged in prepared.values():
        program=staged['program']
        program.setdefault('originalCode',staged['originalCode'])
        program['code']=staged['code']
        history=deepcopy(program.get('simulationCorrections',[]))
        if not history and program.get('simulationCorrection'):history.append(deepcopy(program['simulationCorrection']))
        program['simulationCorrections']=history+staged['items']
        program['simulationCorrection']=deepcopy(staged['items'][-1])
    model.setdefault('diagnostics',[]).extend(diagnostics)
    model['sourceCorrections']=audit
    return model
