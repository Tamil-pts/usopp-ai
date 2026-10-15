"""Engineer-entered PLC and HMI requirements, independent of XML formatting."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

def tag(node):
    return node.tag.split('}')[-1]

def properties(node):
    return {child.get('Name'):child.get('Value','') for child in node if tag(child)=='Property'}

def property_name(value):
    aliases={'Runtime/ControlID':'ControlID','Runtime/ControllD':'ControlID',
             'Runtime/StatusDatapoint':'StatusDatapoint','Completion/Datapoint':'CompletionDatapoint',
             'Completion/Value':'CompletionValue','Completion/Locking':'Locking'}
    return aliases.get(value.strip(),value.strip())

def short_reference(value):
    value=str(value).strip()
    if value.casefold() in {'none','<none>'}: return 'None'
    match=re.fullmatch(r'Source\[[^]]+\]\.\w+\[(.*)\]',value,re.S)
    return match.group(1) if match else value

def equal_property(actual,expected):
    if actual is None: return False
    expected=str(expected).strip()
    if expected.casefold()=='<empty>': return actual==''
    # Fully qualified references retain their namespace; short entries omit wrappers only.
    if expected.startswith('Source['): return actual==expected
    return short_reference(actual)==short_reference(expected)

def parse_properties(text):
    result={}
    for line in str(text or '').splitlines():
        if not line.strip(): continue
        if '=' not in line: raise ValueError('Use Property = Value, one property per line: '+line)
        name,value=line.split('=',1)
        if value.strip(): result[property_name(name)]=value.strip()
    return result

def parse_declarations(text):
    declarations=[]
    for line in str(text or '').splitlines():
        if not line.strip(): continue
        match=re.fullmatch(r'\s*([\w.]+(?:\[.*?\])?)\s*:\s*([^/]+?)(?:\s*/\s*(.*))?\s*',line)
        if not match: raise ValueError('Use Variable : datatype / RETAIN / global or local: '+line)
        flags=[x.strip().casefold() for x in (match[3] or '').split('/') if x.strip()]
        if any(x not in {'retain','non_retain','non-retain','global','local'} for x in flags):
            raise ValueError('Declaration qualifiers must be RETAIN, NON_RETAIN, global or local: '+line)
        if {'global','local'}<=set(flags) or ('retain' in flags and any(x in flags for x in ['non_retain','non-retain'])):
            raise ValueError('Conflicting declaration qualifiers: '+line)
        declarations.append({'variable':match[1],'datatype':match[2].strip().rstrip(';'),
                             'scope':'global' if 'global' in flags else 'local' if 'local' in flags else '',
                             'retain':True if 'retain' in flags else False if any(x in flags for x in ['non_retain','non-retain']) else None})
    return declarations

def group_codes(value):
    if isinstance(value,list): value=','.join(str(x) for x in value)
    if not str(value or '').strip(): return []
    if not re.fullmatch(r'\s*\d+(?:\s*[,;]\s*\d+)*\s*',str(value)):
        raise ValueError('Enter Group Codes separated by commas, for example 140, 40, 50.')
    return list(dict.fromkeys(int(x) for x in re.split('[,;]',str(value))))

def configuration_errors(checks):
    errors=[]
    if not checks: return ['Add at least one PLC, HMI or text-group check.']
    for i,check in enumerate(checks):
        variants=check.get('variants') or []
        if not variants: errors.append(f'Check {i+1}: add a requirement.')
        for j,v in enumerate(variants):
            label=f'Check {i+1}, version {j+1}'
            if not str(v.get('file') or '').strip(): errors.append(label+': choose a file.')
            if check.get('domain')=='plc':
                if not (v.get('logic','').strip() or v.get('declarations','').strip()): errors.append(label+': add logic or declarations.')
                parse_declarations(v.get('declarations'))
                if v.get('groupMode','none') not in {'none','selected','all','exclude'}: errors.append(label+': choose a valid Group Code scope.')
                codes=group_codes(v.get('groupCodes'))
                if v.get('groupMode') in {'selected','exclude'} and not codes: errors.append(label+': enter Group Codes.')
            elif check.get('domain') in {'hmi','textgroup'}:
                if not (v.get('name') or v.get('properties') or v.get('propertyText') or v.get('textRows') or v.get('snippets')): errors.append(label+': add a control name, property or text requirement.')
                parse_properties(v.get('propertyText'))
                parse_properties(v.get('snippets'))
                for line in str(v.get('textRows') or '').splitlines():
                    if line.strip() and not re.match(r'^\s*\d+\s*\|\s*[^|]+\|',line):
                        raise ValueError('Use Index | Language | Text for text-group values: '+line)
            else: errors.append(label+': choose PLC, HMI or text group.')
    return errors

def file_matches(root,path,value,mode='exact'):
    value=str(value or '').replace('\\','/').strip().casefold()
    relative=path.relative_to(root).as_posix().casefold()
    if not value: return False
    if mode=='prefix':
        name=Path(value).stem
        return path.stem.casefold().startswith(name) and ('/' not in value or relative.startswith(str(Path(value).parent).replace('\\','/').casefold()+'/'))
    return relative==value if '/' in value else path.name.casefold()==value

def target_of(root,path):
    parts=path.relative_to(root).parts
    for i,part in enumerate(parts[:-1]):
        if part.casefold()=='logical' and i+1<len(parts)-1: return parts[i+1]
    return ''

def declared_types(root,paths,expected,e):
    rows=[]
    for requirement in parse_declarations(expected):
        found=[]
        for path in paths:
            text=e._strip_plc_comments(e.read_text(path))
            for block in re.finditer(r'\b(VAR(?:_GLOBAL|_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL)?)([^\r\n]*)[\r\n]+(.*?)\bEND_VAR\b',text,re.I|re.S):
                header=(block[1]+block[2]).upper()
                for decl in re.finditer(r'\b'+re.escape(requirement['variable'])+r'\s*(?:AT\s+[^:]+)?\s*:\s*([^;]+);',block[3],re.I):
                    dtype=decl[1].split(':=',1)[0].strip()
                    # Program descriptors establish local scope in B&R; VAR_GLOBAL is explicit IEC scope.
                    scope='global' if 'VAR_GLOBAL' in header else 'local' if any(path.parent.glob('*.prg')) else 'global' if path.suffix.lower()=='.var' else 'local'
                    retain='RETAIN' in header and 'NON_RETAIN' not in header
                    canonical=lambda v:re.sub(r'\s+','',v).upper().replace('STRING[','STRING(').replace(']',' )') if v.upper().startswith('STRING[') else re.sub(r'\s+','',v).upper()
                    wanted=re.sub(r'STRING\[(\d+)\]',r'STRING(\1)',requirement['datatype'],flags=re.I)
                    ok=(re.sub(r'\s+','',dtype).casefold()==re.sub(r'\s+','',wanted).casefold() and
                        (not requirement['scope'] or scope==requirement['scope']) and
                        (requirement['retain'] is None or retain==requirement['retain']))
                    found.append({'check':'Variable declaration','expected':requirement,'actual':{'datatype':dtype,'scope':scope,'retain':retain},'file':path.relative_to(root).as_posix(),'status':'PASS' if ok else 'FAIL'})
        rows.append(next((x for x in found if x['status']=='PASS'),found[0] if found else {'check':'Variable declaration','expected':requirement,'actual':'Declaration not found','status':'FAIL'}))
    return rows

def text_group_rows(group,v,file):
    rows=[]; index={n.get('ID'):n.get('Value') for n in group.iter() if tag(n)=='Index'}
    entries={(index.get(n.get('ID'),n.get('ID')),layer.get('LanguageId')):n.get('Value','') for layer in group.iter() if tag(layer)=='TextLayer' for n in layer if tag(n)=='Text'}
    snippets={n.get('Name'):properties(n) for n in group.iter() if tag(n)=='TextSnippet'}
    selected=[]
    for line in str(v.get('textRows') or '').splitlines():
        if not line.strip(): continue
        number,language,text=[x.strip() for x in line.split('|',2)]
        actual=entries.get((number,language));selected.append(text)
        rows.append({'check':f'Text index {number} / {language}','expected':text,'actual':actual,'status':'PASS' if actual==text else 'FAIL','file':file})
    for name,value in parse_properties(v.get('snippets')).items():
        actual=snippets.get(name,{}).get('Datapoint')
        rows.append({'check':f'Text snippet {name} datapoint','expected':value,'actual':actual,'status':'PASS' if equal_property(actual,value) else 'FAIL','file':file})
    # Preserve the literal {name}; resolve it to its actual snippet and datapoint.
    for name in sorted({n for text in selected or entries.values() for n in re.findall(r'\{([^{}]+)\}',text)}):
        actual=snippets.get(name,{}).get('Datapoint')
        rows.append({'check':f'{{{name}}} snippet reference','expected':'Defined snippet with an assigned datapoint','actual':actual,'status':'PASS' if actual and short_reference(actual)!='None' else 'FAIL','file':file})
    return rows

def hmi_variant(root,path,v,all_paths,e):
    relative=path.relative_to(root).as_posix()
    try: document=ET.fromstring(e.read_text(path))
    except ET.ParseError as error: return [{'check':'XML source','status':'FAIL','actual':str(error),'file':relative}]
    expected={**(v.get('properties') or {}),**parse_properties(v.get('propertyText'))}
    expected={property_name(k):str(val).strip() for k,val in expected.items() if str(val).strip()}
    name=str(v.get('name') or expected.pop('Name','')).strip()
    expected.pop('File',None)
    object_type=v.get('objectType') or ('TextGroup' if path.suffix.lower()=='.txtgrp' else 'Control')
    parents={child:parent for parent in document.iter() for child in parent}
    candidates=[]
    for node in document.iter():
        if tag(node)!=object_type: continue
        props={**node.attrib,**properties(node)}
        actual_name=props.get('Name','')
        matches=actual_name.casefold().startswith(name.casefold()) if v.get('nameMatch')=='prefix' else actual_name.casefold()==name.casefold()
        if name and not matches: continue
        rows=[{'check':f'{actual_name or object_type} / {key}','control':actual_name,'expected':value,'actual':props.get(key),
               'status':'PASS' if equal_property(props.get(key),value) else 'FAIL','file':relative} for key,value in expected.items()]
        if not rows: rows=[{'check':f'{object_type} presence','expected':name or object_type,'actual':actual_name,'status':'PASS','file':relative}]
        if v.get('textRows') or v.get('snippets') or object_type=='TextGroup':
            group=node if object_type=='TextGroup' else None
            group_file=relative
            if group is None and 'embedded' in props.get('TextGroup','').lower():
                parent=parents.get(node)
                while parent is not None:
                    group=next((c for c in parent if tag(c)=='TextGroup'),None)
                    if group is not None: break
                    parent=parents.get(parent)
            if group is None:
                reference=props.get('TextGroup',''); group_name=short_reference(reference)
                target=target_of(root,path)
                target_name='VCShared' if reference.startswith('Source[global]') else target
                matches=[p for p in all_paths if p.suffix.lower()=='.txtgrp' and p.stem==group_name and target_of(root,p).casefold()==target_name.casefold()]
                if len(matches)==1:
                    group=ET.fromstring(e.read_text(matches[0]));group_file=matches[0].relative_to(root).as_posix()
            if group is None: rows.append({'check':'Referenced text group','expected':props.get('TextGroup'),'actual':'Text group missing or ambiguous in this target','status':'FAIL','file':relative})
            else: rows.extend(text_group_rows(group,v,group_file))
        candidates.append(rows)
    return next((rows for rows in candidates if all(r['status']=='PASS' for r in rows)),min(candidates,key=lambda rows:sum(r['status']!='PASS' for r in rows)) if candidates else [{'check':f'{object_type} presence','expected':name,'actual':'No matching object in this file','file':relative,'status':'FAIL'}])

def evaluate(root,rule,e):
    checks=rule.get('checks') or []; errors=configuration_errors(checks)
    if errors: return e.result(rule['id'],rule['name'],'FAIL',rule.get('expected',''),'; '.join(errors))
    paths=list(e.all_files(root)); evidence=[]
    for index,check in enumerate(checks):
        variants=check['variants'];domain=check['domain'];primary=variants[0]
        candidates=[p for p in paths if any(file_matches(root,p,v['file'],v.get('fileMatch')) for v in variants)]
        if domain=='plc':
            groups=group_codes(primary.get('groupCodes'));mode=primary.get('groupMode','none')
            discovered={b['groupCode'] for p in candidates for b in e._parse_case_group_branches(e.read_text(p))}
            groups=sorted(discovered-set(groups)) if mode=='exclude' else sorted(discovered) if mode=='all' else groups if mode=='selected' else [None]
            if not groups: groups=['No group branches found']
            for group in groups:
                attempts=[]
                for v in variants:
                    for p in candidates:
                        if not file_matches(root,p,v['file'],v.get('fileMatch')): continue
                        text=e.read_text(p); branches=e._parse_case_group_branches(text) if group is not None else []
                        segments=[b['segment'] for b in branches if b['groupCode']==group] if group is not None else [text]
                        if not segments: continue
                        declaration_files=[p] if p.suffix.lower() in {'.var','.typ'} else [f for f in paths if f.suffix.lower()=='.var' and (f.parent==p.parent or not any(f.parent.glob('*.prg')))]
                        rows=declared_types(root,declaration_files,v.get('declarations'),e)
                        if v.get('logic','').strip():
                            for segment in segments:
                                hit=e._logic_match(segment,v['logic'])
                                rows.append({'check':'PLC logic','expected':v['logic'],'actual':segment[hit[0]:hit[1]] if hit else 'Complete logic block not found','file':p.relative_to(root).as_posix(),'status':'PASS' if hit else 'FAIL','groupCode':group})
                        attempts.append(rows)
                chosen=next((rows for rows in attempts if rows and all(r['status']=='PASS' for r in rows)),attempts[0] if attempts else [{'check':'PLC source / Group Code','expected':primary['file'],'actual':'File or selected group not found','status':'FAIL','groupCode':group}])
                evidence.extend({**row,'requirement':check.get('name') or f'Check {index+1}'} for row in chosen)
        else:
            targets=[x.strip() for x in str(primary.get('targets') or '').split(',') if x.strip()] or sorted({target_of(root,p) for p in candidates}) or ['']
            for target in targets:
                attempts=[hmi_variant(root,p,v,paths,e) for v in variants for p in candidates if target_of(root,p).casefold()==target.casefold() and file_matches(root,p,v['file'],v.get('fileMatch'))]
                chosen=next((rows for rows in attempts if all(r['status']=='PASS' for r in rows)),min(attempts,key=lambda rows:sum(r['status']!='PASS' for r in rows)) if attempts else [{'check':'HMI file / target','expected':primary['file'],'actual':'No matching file for target '+target,'status':'FAIL'}])
                evidence.extend({**row,'target':target,'requirement':check.get('name') or f'Check {index+1}'} for row in chosen)
    failed=[r for r in evidence if r['status']!='PASS']
    output=e.result(rule['id'],rule['name'],'FAIL' if failed else 'PASS',rule.get('expected',''),f'{len(evidence)-len(failed)} requirements passed; {len(failed)} failed.',evidence,
                    ['Review each failed property, declaration or Group Code below.'] if failed else [],sorted({r['file'] for r in evidence if r.get('file')}))
    output['structuredChecks']=evidence
    return output
