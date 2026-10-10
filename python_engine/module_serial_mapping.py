"""Trace physical SerialNumber datapoints into each Group 420 packet path."""
import importlib.util
from pathlib import Path
import re
import sys
import uuid
import xml.etree.ElementTree as ET
import fnmatch
from python_engine.project_info import local_project_details

EXPECTED = 'Every controller and electronic remote module has a unique SerialNumber datapoint binding; its four-byte integer variable or array element is transmitted exactly once on each applicable GC 420 path, with matching payload length and response setup.'
CROSS_REFERENCES = [
    {'name': 'Hardware inventory', 'scope': 'Hardware.hw in the active configuration', 'requirement': 'Identify the active controller and electronic remote modules. Exclude passive terminals, bases and inactive configurations.'},
    {'name': 'SerialNumber I/O bindings', 'scope': 'IoMap.iom / IOMap.iom', 'requirement': 'Every inventoried module has one SerialNumber binding. Different modules must not own the same scalar or array element.'},
    {'name': 'PLC declarations', 'scope': 'Project declarations (.var / .typ / AS 2.7 CPU.txt)', 'requirement': 'Resolve each bound scalar or array element to an accepted four-byte integer type. Array indices and bulk-copy ranges must fit its declared bounds.'},
    {'name': 'Packet task ownership', 'scope': 'Active configuration Cpu.sw and the matching mms_nw_r source', 'requirement': 'Use LastUser.set to select the active configuration, or the single AS 2.7 configuration. Report unresolved selection instead of checking inactive targets.'},
]


def normalize_configuration(rule):
    value=dict(rule)
    value.update({'kind':'module_serial_mapping','groupCode':420})
    value.setdefault('name','Module serial no mapping')
    value['category']=value.get('category') or 'Hardware / I/O'
    value['featureId']='hardware_io'
    value['featureName']=value.get('featureName') or 'Hardware / I/O'
    if value['featureName']=='Unassigned': value['featureName']='Hardware / I/O'
    value['sourceFile']=value.get('sourceFile') or value.get('subroutine') or 'mms_nw_rCyclic.st'
    value['subroutine']=value['sourceFile']
    value['allowedDatatypes']=value.get('allowedDatatypes') or ['UDINT','DINT','DWORD']
    value['expected']=value.get('expected') or EXPECTED
    value['description']=value.get('description') or value['expected']
    value['machineScope']=value.get('machineScope') or ['All']
    options=value.get('serialMapping') if isinstance(value.get('serialMapping'),dict) else {}
    value['serialMapping']={key:options.get(key) or [] for key in ('ioMappingFiles','hardwareFiles','declarationFiles')}
    value['serialCrossReferences']=CROSS_REFERENCES
    # This validator discovers variables and validates semantic requirements;
    # an empty generic source snippet must not disable its dedicated checks.
    for key in ('checks','needsLogicConfiguration','needsRuleConfiguration','configurationIssues','configurationFormat'):
        value.pop(key,None)
    return value


def configuration_errors(rule):
    errors=[]
    if not str(rule.get('name') or '').strip(): errors.append('Enter the rule name.')
    if not str(rule.get('sourceFile') or rule.get('subroutine') or '').strip(): errors.append('Enter the packet source file.')
    if rule.get('groupCode',420)!=420: errors.append('Module serial no mapping checks Group Code 420.')
    types=rule.get('allowedDatatypes') or ['UDINT','DINT','DWORD']
    if not isinstance(types,list) or any(t not in {'UDINT','DINT','DWORD'} for t in types): errors.append('Serial numbers require UDINT, DINT or DWORD (four bytes).')
    options=rule.get('serialMapping') or {}
    if not isinstance(options,dict): return errors+['Serial cross-reference scope must be an object.']
    for key in ('ioMappingFiles','hardwareFiles','declarationFiles'):
        paths=options.get(key) or []
        if not isinstance(paths,list): errors.append(f'{key} must contain a list of project-relative file patterns.');continue
        for path in paths:
            if not isinstance(path,str) or not path.strip() or ':' in path or path.startswith(('/','\\')) or '..' in path.replace('\\','/').split('/'):
                errors.append(f'{key}: use project-relative paths or filename patterns.')
    source=str(rule.get('sourceFile') or rule.get('subroutine') or '')
    if ':' in source or source.startswith(('/','\\')) or '..' in source.replace('\\','/').split('/'):
        errors.append('Packet source must be relative to the selected project.')
    return errors


def _matches(path,root,patterns):
    relative=path.relative_to(root).as_posix().casefold()
    return not patterns or any(fnmatch.fnmatchcase(relative,str(p).replace('\\','/').casefold()) or '/' not in str(p).replace('\\','/') and fnmatch.fnmatchcase(path.name.casefold(),str(p).casefold()) for p in patterns)


def active_mapping_scope(root, files):
    """Resolve configuration before applying optional rule scopes."""
    details=local_project_details(root)
    settings=details.get('settingsFile')
    active=details.get('activeConfiguration')
    physical=next((p for p in root.iterdir() if p.is_dir() and p.name.casefold()=='physical'),None)
    if details.get('logicScopeMessage'):
        return [],None,active or '',details['logicScopeMessage']
    if active:
        if active in {'.','..'} or '/' in active or '\\' in active or ':' in active:
            return [],None,'','Invalid active configuration name in LastUser.set.'
        selected=next((p for p in physical.iterdir() if p.is_dir() and p.name.casefold()==active.casefold()),None) if physical else None
        if selected is None: return [],None,active,'The active physical configuration recorded in LastUser.set was not found.'
        if details.get('legacyCpuRoot'):
            cpu=root/details['legacyCpuRoot']
            legacy=[p for p in files if p.is_relative_to(cpu)]
            if legacy:
                return legacy,cpu,active+' / '+details['legacyCpuRoot']+' (AS 2.7 single configuration)',''
        return [p for p in files if p.is_relative_to(selected)],selected,active,''
    if settings:
        return [],None,'',details.get('configurationMessage') or 'The active configuration could not be resolved from LastUser.set.'
    # Legacy AS 2.7 keeps its single CPU configuration under pgm, rather than
    # selecting a Physical folder in LastUser.set.
    legacy=[p for p in files if p.relative_to(root).parts[0].casefold()=='pgm']
    if str(details.get('automationStudioVersion') or '').startswith('2.') or legacy and len(legacy)==len(files):
        configs={p.parent.parent for p in legacy}
        if len(configs)==1:
            selected=next(iter(configs))
            return legacy,selected,selected.relative_to(root).as_posix()+' (AS 2.7 single configuration)',''
        return [],None,'','The AS 2.7 project does not contain exactly one resolvable CPU configuration.'
    configs=[p for p in physical.iterdir() if p.is_dir()] if physical else []
    if len(configs)==1:
        selected=configs[0]
        return [p for p in files if p.is_relative_to(selected)],selected,selected.name+' (only configuration)',''
    return [],None,'','Active configuration is unknown. Include the project LastUser.set; inactive configurations were not checked.'

def evaluate(root, rule, engine):
    root=Path(root).resolve()
    errors=configuration_errors(rule)
    if errors: return engine.result(rule['id'],rule.get('name','Module serial no mapping'),'NOT FOUND',rule.get('expected',EXPECTED),'; '.join(errors),recommendations=errors)
    rule=normalize_configuration(rule)
    scope=rule['serialMapping']
    all_project_files=list(engine.all_files(root))
    mappings,active_root,active_name,selection_error=active_mapping_scope(root,[p for p in all_project_files if p.suffix.casefold()=='.iom'])
    if selection_error:
        row={'check':'Active configuration selection','file':'LastUser.set' if (root/'LastUser.set').exists() else '', 'line':1,'groupCode':420,'status':'FAIL','expected':'One active configuration (single configuration for AS 2.7)','actual':selection_error,'suggestedFix':'Include the current project settings that identify the active configuration.'}
        output=engine.result(rule['id'],rule['name'],'FAIL',rule['expected'],selection_error,[row],[row['suggestedFix']])
        output['structuredRequirements']=[row]
        return output
    mappings=[p for p in mappings if _matches(p,root,scope['ioMappingFiles'])]
    evidence=[]
    def add(check,file,line,expected,actual,passed,target='',condition=''):
        evidence.append({'check':check,'file':file,'line':line,'groupCode':420,'target':target,'condition':condition,
                         'expected':expected,'actual':actual,'status':'PASS' if passed else 'FAIL',
                         'suggestedFix':'' if passed else 'Bind this module SerialNumber to the intended four-byte integer variable or array element and transmit that exact element in every applicable GC 420 path. Recalculate the payload header and nw_i increments.'})
    module_name='_serial_packet_'+uuid.uuid4().hex
    packet_file=Path(__file__).with_name('packet_validation_report_uSOPp_v1.71_final.py')
    if not packet_file.exists(): packet_file=packet_file.with_suffix('.pyc')
    spec=importlib.util.spec_from_file_location(module_name,packet_file)
    packet=importlib.util.module_from_spec(spec)
    sys.modules[module_name]=packet
    try:
        spec.loader.exec_module(packet)
        packet.initialize_project_context(root)
        paths=engine.packet_source_files(root,rule.get('sourceFile','mms_nw_rCyclic.st'))
        variants={}
        for path in paths:
            text=engine.read_text(path)
            for branch in engine._parse_case_group_branches(text):
                if branch['groupCode']!=420: continue
                # Packet parsing retains separate conditional layouts and resolves SIZEOF.
                parsed=packet.parse_group(path,420,branch.get('description','Module serial numbers'),branch['line'],branch['line']+len(branch['originalSegment'].splitlines())-1,include_variants=True,validate_response_setup=True)
                variants.setdefault(path,[]).extend(parsed[-1])
        if not mappings:
            add('Physical serial mappings','',1,'Active configuration IoMap.iom with controller/module SerialNumber bindings','No I/O mapping files found in the active configuration and configured scope',False,active_name)
        for iom in mappings:
            target=iom.parent.relative_to(root).as_posix()
            config=iom.parent.parent
            candidates=[p for p in all_project_files if p.name.casefold()=='hardware.hw' and p.is_relative_to(active_root) and _matches(p,root,scope['hardwareFiles'])]
            local=[p for p in candidates if p.parent==config]
            hardware=local[0] if len(local)==1 else candidates[0] if scope['hardwareFiles'] and len(candidates)==1 else None
            bindings=[]
            text=engine.read_text(iom)
            text=re.sub(r'\(\*.*?\*\)|//[^\n]*',lambda m:'\n'*m[0].count('\n'),text,flags=re.S)
            pattern=r'([\w#]+(?:\.[\w#]+)*(?:\s*\[\s*\d+\s*\])?)\s+AT\s+%ID\."([^"]+)"\.SerialNumber\s*;'
            for match in re.finditer(pattern,text,re.I):
                bindings.append((match[2],re.sub(r'\s+','',match[1]),text[:match.start()].count('\n')+1))
            inventory=[]
            if hardware:
                tree=ET.parse(hardware).getroot()
                controllers=[]
                for node in tree.iter():
                    if node.tag.rsplit('}',1)[-1]!='Module': continue
                    name=node.get('Name','');typ=node.get('Type','')
                    # Terminal/bus bases and passive connectors are not electronic devices.
                    if re.match(r'X20(?:TB|BM|BB)|X67TB',typ,re.I): continue
                    if re.match(r'X20|X67|X90|[45]PP|[45]PC|[45]PPC|APC|PPC',typ,re.I):
                        inventory.append(name)
                    if re.match(r'X20CP|[45]PP|[45]PC|[45]PPC|APC|PPC',typ,re.I): controllers.append(name)
                if len(controllers)>1:
                    add('PLC target ownership',hardware.relative_to(root).as_posix(),1,'One controller or explicit per-controller module ownership',f'{len(controllers)} controllers in shared hardware; target mapping required',False,target)
                    continue
            else:
                add('Physical module inventory',iom.relative_to(root).as_posix(),1,'Hardware.hw to verify controller and remote-module coverage','Inventory unavailable; cannot confirm every module is mapped',False,target)
            by_module={}
            if not bindings:
                add('SerialNumber I/O bindings',iom.relative_to(root).as_posix(),1,'At least one controller/module SerialNumber binding','No supported SerialNumber bindings found in this I/O mapping file',False,target)
            for module,variable,line in bindings: by_module.setdefault(module.casefold(),[]).append((module,variable,line))
            for module in inventory:
                rows=by_module.get(module.casefold(),[])
                if len(rows)!=1:
                    add('Module SerialNumber binding',iom.relative_to(root).as_posix(),rows[0][2] if rows else 1,f'One SerialNumber binding for {module}',f'{len(rows)} bindings found',False,target)
            selected=list(variants)
            sw=next((p for p in iom.parent.iterdir() if p.name.casefold()=='cpu.sw'),None)
            if sw:
                sources=[node.get('Source','') for node in ET.parse(sw).getroot().iter() if node.tag.rsplit('}',1)[-1]=='Task' and 'mms_nw_r' in (node.get('Name','')+' '+node.get('Source','')).casefold()]
                matched=[path for path in selected if any(source.removesuffix('.prg').replace('.','/').casefold() in path.relative_to(root).as_posix().casefold() for source in sources if source)]
                selected=matched
            if len(selected)!=1:
                add('GC 420 source scope',iom.relative_to(root).as_posix(),1,'One matching packet task for this PLC configuration',f'{len(selected)} candidate packet tasks',False,target)
                continue
            packet_path=selected[0]
            for variant in variants[packet_path]:
                condition=variant.get('condition','Unconditional')
                fields=variant.get('parameters',[])
                copied=[]
                serial_bases={variable.split('.')[-1].split('[')[0].casefold() for _,variable,_ in bindings}
                for field in fields:
                    expression=field.get('parameter','')
                    size=field.get('size')
                    match=re.fullmatch(r'([\w.]+)(?:\[(\d+)\])?',expression)
                    if not match or size is None: continue
                    base=match[1].split('.')[-1].casefold();start=int(match[2]) if match[2] else None
                    info=packet.resolve_type_info(expression)
                    type_name=packet.format_type_info(info).upper() if info else ''
                    count=size//4 if start is not None and size%4==0 else 1
                    copied.append((base,start,count,size,type_name,field))
                    if base in serial_bases and start is not None:
                        declared=packet.resolve_type_info(match[1])
                        bounds=packet.dereference_type(declared).array_range if declared else None
                        fits=bool(bounds and size>0 and size%4==0 and bounds[0]<=start and start+size//4-1<=bounds[1])
                        add('GC 420 serial array copy bounds',field.get('sourceFile',packet_path.relative_to(root).as_posix()),field.get('lineNumber',1),
                            'The complete four-byte array copy fits its declared range',f'{expression}: {size} bytes; element range {start}..{start+size//4-1}; declared {bounds or "unresolved"}',fits,target,condition)
                seen={}
                for module,variable,line in bindings:
                    leaf=variable.split('.')[-1]
                    match=re.fullmatch(r'(\w+)(?:\[(\d+)\])?',leaf)
                    if not match: continue
                    base=match[1].casefold();index=int(match[2]) if match[2] else None
                    symbol=next((item for name,item in packet.VARIABLES.items() if name.casefold()==base),None)
                    declaration_path=root/str(symbol.source_file) if symbol else None
                    declared_type=packet.resolve_type_info(match[1])
                    resolved=packet.dereference_type(declared_type) if declared_type else None
                    element=packet.dereference_type_name(resolved.base) if resolved and resolved.kind=='array' and resolved.base else resolved
                    declared_ok=bool(symbol and element and element.name.upper() in rule['allowedDatatypes'] and declaration_path and _matches(declaration_path,root,scope['declarationFiles']))
                    add('Serial declaration cross reference',str(symbol.source_file) if symbol else iom.relative_to(root).as_posix(),1,
                        f'{leaf}: accepted four-byte integer declaration in the configured scope',
                        f"{leaf}: {packet.format_type_info(declared_type) if declared_type else 'unresolved'}; declaration {symbol.source_file if symbol else 'not found'}",declared_ok,target,condition)
                    if index is not None:
                        declared=packet.resolve_type_info(match[1])
                        bounds=packet.dereference_type(declared).array_range if declared else None
                        add('Serial array element bounds',iom.relative_to(root).as_posix(),line,'An element inside the declared serial array',
                            f'{leaf}; declared range {bounds or "unresolved"}',bool(bounds and bounds[0]<=index<=bounds[1]),target,condition)
                    matches=[row for row in copied if row[0]==base and (index is None and row[1] is None and row[3]==4 or index is not None and row[1] is not None and row[1]<=index<row[1]+row[2])]
                    integer=matches and all(row[4].split('[')[0] in rule['allowedDatatypes'] for row in matches)
                    actual=f'{variable}: '+('; '.join(f"{row[5]['sourceFile']}:{row[5]['lineNumber']} ({row[3]} bytes from {row[5]['parameter']})" for row in matches) or 'Not transmitted')
                    add('SerialNumber -> GC 420',iom.relative_to(root).as_posix(),line,f'{module}: {variable}, four-byte integer, transmitted once',actual,len(matches)==1 and bool(integer),target,condition)
                    seen.setdefault(leaf.casefold(),[]).append(module)
                for variable,modules in seen.items():
                    if len(modules)>1: add('Serial variable ownership',iom.relative_to(root).as_posix(),1,'Distinct variable/array element for each module',f'{variable} is assigned to '+', '.join(modules),False,target,condition)
                for issue in variant.get('issues',[]):
                    if issue.get('severity')=='FAIL':
                        add(issue.get('validationType','Packet layout'),issue.get('sourceFile',''),issue.get('lineNumber',1),issue.get('expected'),issue.get('actual'),False,target,condition)
                add('GC 420 payload length',packet_path.relative_to(root).as_posix(),fields[0].get('lineNumber',1) if fields else 1,
                    variant.get('calculatedByOffset'),variant.get('configuredBytes'),variant.get('configuredBytes')==variant.get('calculatedByOffset') and bool(fields),target,condition)
        failed=sum(row['status']=='FAIL' for row in evidence)
        result=engine.result(rule['id'],rule['name'],'FAIL' if failed or not evidence else 'PASS',rule.get('expected',''),
            f'{len(evidence)} checks; {failed} failed. Active configuration: {active_name}. Inactive configurations excluded.',evidence,
            ['Review the module, I/O binding, datatype and GC 420 source shown for each failed check.'] if failed else [],sorted({row['file'] for row in evidence if row['file']}))
        result['structuredRequirements']=evidence
        result['activeConfiguration']=active_name
        result['logicConfiguration']='Trace hardware module -> SerialNumber datapoint -> scalar or array element -> GC 420 copy, datatype, byte count and response setup.'
        return result
    finally:
        sys.modules.pop(module_name,None)
