"""Engineer-entered requirements. XML is parsed by object, never matched as raw text."""
import fnmatch
import re
import uuid
import xml.etree.ElementTree as ET
try: from python_engine.source_resolution import source_pattern_matches
except ModuleNotFoundError: from source_resolution import source_pattern_matches

def tag(node):
    return node.tag.rsplit('}',1)[-1]

def properties(node):
    return {child.get('Name'):child.get('Value','') for child in node if tag(child)=='Property'}


def selected_nodes(document, variant):
    """Keep identically named datasource points in their explicit folders."""
    entity=variant.get('entity','Control');name=variant.get('name','')
    nodes=[node for node in document.iter() if tag(node)==entity
           and (not name or (node.get('Name','').casefold().startswith(name.casefold()) if variant.get('nameMatch')=='prefix' else node.get('Name','').casefold()==name.casefold()))
           and (not variant.get('classId') or node.get('ClassId')==variant['classId'])]
    if 'ancestorFolders' not in variant:
        return nodes
    parents={child:parent for parent in document.iter() for child in parent}
    def folders(node):
        names=[];parent=parents.get(node)
        while parent is not None:
            if tag(parent)=='Folder':names.insert(0,parent.get('Name','').casefold())
            parent=parents.get(parent)
        return names
    expected=[str(value).casefold() for value in variant['ancestorFolders']]
    return [node for node in nodes if folders(node)==expected]

def property_name(value):
    aliases={'Runtime/ControlID':'ControlID','Runtime/ControllD':'ControlID','Runtime/StatusDatapoint':'StatusDatapoint',
             'Completion/Datapoint':'CompletionDatapoint','Completion/Value':'CompletionValue','Completion/Locking':'Locking'}
    return aliases.get(value.strip(),value.strip())

def property_value(value):
    text=str(value).strip()
    if text.casefold() in {'<none>','none'}: return 'None'
    # Unwrap the complete resource expression, preserving array indices inside.
    match=re.fullmatch(r'Source\[[^]]+\]\.\w+\[(.*)\]',text,re.S)
    return match.group(1) if match else text

def equal_property(actual,expected):
    if actual is None: return False
    if str(expected).strip().casefold()=='<empty>': return actual==''
    if str(expected).startswith('Source['): return actual==expected
    return property_value(actual)==property_value(expected)

def parse_properties(text):
    result={}
    for line in str(text or '').splitlines():
        if not line.strip(): continue
        if '=' not in line: raise ValueError('Use Property = Value, one per line: '+line)
        key,value=line.split('=',1)
        if key.strip() and value.strip(): result[property_name(key)]=value.strip()
    return result

def codes(value):
    if isinstance(value,list): value=','.join(map(str,value))
    value=str(value or '').strip()
    if not value: return []
    if not re.fullmatch(r'\d+(?:\s*[,;]\s*\d+)*',value): raise ValueError('Enter Group Codes separated by commas, such as 140, 40, 50.')
    return list(dict.fromkeys(int(x) for x in re.split(r'[,;]',value)))

def parse_declarations(text):
    result=[]
    for line in str(text or '').splitlines():
        if not line.strip(): continue
        parts=[x.strip() for x in line.split('/')]
        flags={x.casefold() for x in parts[1:]}
        if {'local','global'}<=flags or {'retain','non_retain'}<=flags:
            raise ValueError('Conflicting declaration qualifiers: '+line)
        match=re.fullmatch(r'([A-Za-z_]\w*)\s*:\s*(.+?)\s*;?',parts[0])
        if not match: raise ValueError('Use Variable : datatype / RETAIN / global or local: '+line)
        item={'variable':match.group(1),'datatype':match.group(2).rstrip(';').strip()}
        for option in parts[1:]:
            if option.casefold() in {'global','local'}: item['scope']=option.casefold()
            elif option.upper() in {'RETAIN','NON_RETAIN','PERSISTENT'}: item['retention']=option.upper()
            elif option: raise ValueError('Unknown declaration qualifier: '+option)
        result.append(item)
    return result

def normalize_check(check):
    check=dict(check)
    if check.get('type')=='reference':
        if not check.get('referenceFile') or not check.get('checkId'):
            raise ValueError('A reference check needs its saved definition file and check ID.')
        return check
    check['file']=str(check.get('file') or '').strip().replace('\\','/')
    check['groupCodes']=codes(check.get('groupCodes'))
    if check.get('type') not in {'logic','hmi','ladder'}: raise ValueError('Choose a PLC or HMI requirement.')
    if check.get('groupMode','none') not in {'none','selected','all','exclude'}: raise ValueError('Choose a valid Group Code scope.')
    check['declarations']=parse_declarations(check.get('declarationText',''))
    if check.get('type')=='hmi':
        def normalize_variant(value):
            variant=dict(value)
            if 'ancestorFolders' in variant and (not isinstance(variant['ancestorFolders'],list) or any(not isinstance(name,str) or not name for name in variant['ancestorFolders'])):
                raise ValueError('Datasource folder paths must be a list of folder names.')
            props={property_name(k):str(v).strip() for k,v in (variant.get('properties') or {}).items() if str(v).strip()}
            props.update(parse_properties(variant.get('propertyText','')))
            variant['name']=str(props.pop('Name',variant.get('name',''))).strip()
            variant['nameMatch']=str(props.pop('Name matching',variant.get('nameMatch','exact'))).lower()
            variant['properties']=props
            if variant['nameMatch'] not in {'exact','prefix'}: raise ValueError('Name matching must be Exact or Prefix.')
            for row in variant.get('texts') or []:
                if not str(row.get('index','')).isdigit() or not row.get('language'): raise ValueError('Each text value needs a numeric index and language, for example 0 / en.')
            for row in variant.get('snippets') or []:
                if not row.get('name') or not row.get('datapoint'): raise ValueError('Each snippet needs its name and expected datapoint.')
            if (variant.get('texts') or variant.get('snippets')) and variant.get('entity','Control')!='TextGroup' and not variant.get('textGroupFile'):
                raise ValueError('Enter the referenced text group file, or choose TextGroup as the object type.')
            for reference in variant.get('referenceChecks') or []:
                if reference.get('kind') not in {'touchpad','textgroup'}: raise ValueError('Choose touchpad or text group cross reference.')
                if reference.get('shiftLevels','all') not in {'all','unshifted'}: raise ValueError('Choose valid Shift levels.')
                if reference.get('characterRequirement','uppercase') not in {'uppercase','any'}: raise ValueError('Choose a valid character requirement.')
                for row in reference.get('texts') or []:
                    if not str(row.get('index','')).isdigit() or not row.get('language'): raise ValueError('Text group entries need an index and language.')
            return variant
        legacy=[normalize_variant(variant) for variant in check.get('variants') or []]
        accepted=[]
        for item in check.get('acceptedHmiAlternatives') or []:
            if isinstance(item,dict) and isinstance(item.get('variant'),dict):
                accepted.append({'file':str(item.get('file') or '').strip().replace('\\','/'),'variant':normalize_variant(item['variant'])})
        if len(legacy)>1:
            accepted=[{'file':check['file'],'variant':variant} for variant in legacy[1:]]+accepted
        check['variants']=legacy[:1]
        check['acceptedHmiAlternatives']=accepted
    else:
        legacy=[str(x) for x in check.get('alternatives') or [] if str(x).strip()]
        accepted=[]
        for item in check.get('acceptedLogicAlternatives') or []:
            if not isinstance(item,dict): continue
            accepted.append({'file':str(item.get('file') or '').strip().replace('\\','/'),
                             'logic':str(item.get('logic') or ''),
                             'declarationText':str(item.get('declarationText') or ''),
                             'declarationFile':str(item.get('declarationFile') or '').strip().replace('\\','/'),
                             'declarations':parse_declarations(item.get('declarationText',''))})
        if len(legacy)>1:
            accepted=[{'file':check['file'],'logic':logic,'declarationText':check.get('declarationText',''),
                       'declarationFile':check.get('declarationFile',''),'declarations':check['declarations']} for logic in legacy[1:]]+accepted
        check['alternatives']=legacy[:1]
        check['acceptedLogicAlternatives']=accepted
    if check.get('type')=='ladder':
        try: from python_engine.ladder_requirements import errors
        except ModuleNotFoundError: from ladder_requirements import errors
        ladder_alternatives=[]
        for variant in check.get('ladderAlternatives') or []:
            if isinstance(variant,list):
                ladder_alternatives.append({'file':check['file'],'networks':list(variant)})
            elif isinstance(variant,dict):
                ladder_alternatives.append({'file':str(variant.get('file') or '').strip().replace('\\','/'),'networks':list(variant.get('networks') or [])})
        check['ladderAlternatives']=ladder_alternatives
        check['configurationIssues']=errors(check)
    check['crossChecks']=[normalize_check(x) for x in check.get('crossChecks') or []]
    check['crossCheckMode']=str(check.get('crossCheckMode') or 'all').lower()
    if check['crossCheckMode'] not in {'all','any'}:
        raise ValueError('Cross references must use AND (all) or OR (any).')
    return check

def configuration(answers):
    checks=[normalize_check(x) for x in answers.get('checks') or []]
    def complete(c):
        if c.get('type')=='reference':return bool(c.get('referenceFile') and c.get('checkId'))
        if not c['file']: return False
        if c.get('groupMode') in {'selected','exclude'} and not c['groupCodes']: return False
        if c.get('type')=='hmi':
            accepted=c.get('acceptedHmiAlternatives') or []
            valid=bool(c.get('variants')) and all(v.get('name') or v.get('properties') or v.get('texts') or v.get('snippets') for v in c['variants']) and all(item.get('file') and (item['variant'].get('name') or item['variant'].get('properties') or item['variant'].get('texts') or item['variant'].get('snippets')) for item in accepted)
        elif c.get('type')=='ladder': valid=not c.get('configurationIssues')
        else:
            accepted=c.get('acceptedLogicAlternatives') or []
            valid=bool(c.get('alternatives') or c.get('declarations')) and all(item.get('file') and (str(item.get('logic') or '').strip() or item.get('declarations')) for item in accepted)
        return valid and all(complete(x) for x in c['crossChecks'])
    rule={'id':answers.get('ruleId') or 'R-'+uuid.uuid4().hex.upper(),'name':str(answers.get('name') or '').strip(),
          'kind':'structured_requirements','category':answers.get('category') or '', 'description':answers.get('description',''),
          'expected':answers.get('description') or 'All configured requirements must pass.',
          'featureName':answers.get('featureName') or 'Unassigned','featureId':re.sub(r'[^a-z0-9_-]+','_',str(answers.get('featureName') or 'Unassigned').lower()).strip('_'),'machineScope':[answers.get('machineDepartment') or 'All'],
          'machineModels':[answers.get('machineModel') or 'All'],'checks':checks,'version':'1.0','enabled':False,
          'reviewStatus':'Needs engineer review','configurationFormat':'grouped-v1'}
    rule['needsRuleConfiguration']=not rule['name'] or not rule['category'] or not checks or not all(complete(c) for c in checks)
    return {'version':'4.60.3','configurationFormat':'grouped-v1','rules':[rule]}

def matching_files(root,pattern,engine):
    pattern=str(pattern or '').strip().replace('\\','/').casefold()
    while pattern.startswith('./'):
        pattern=pattern[2:]
    if not pattern or pattern.startswith('/') or ':' in pattern or '..' in pattern.split('/'):
        return []
    indexed=getattr(engine,'reference_path_index',None)
    if indexed is not None and root.resolve()==engine.reference_project_root and pattern.split('/')[0] in {'logical','physical','configuration','configurations'} and not any(char in pattern for char in '*?['):
        return list(indexed.get(pattern,[]))
    def matches(path):
        relative=path.relative_to(root).as_posix().casefold()
        if source_pattern_matches(relative,pattern):
            return True
        if '/' not in pattern:
            return fnmatch.fnmatchcase(path.name.casefold(),pattern)
        if fnmatch.fnmatchcase(relative,pattern):
            return True
        # Full project paths stay anchored; shorter paths can start at a
        # subroutine or HMI folder, always on a complete directory boundary.
        if pattern.split('/')[0] in {'logical','physical','configuration','configurations'}:
            return False
        parts=relative.split('/')
        return any(fnmatch.fnmatchcase('/'.join(parts[index:]),pattern) for index in range(1,len(parts)))
    return [p for p in engine.all_files(root) if matches(p)]

def matching_hmi_files(root,pattern,engine,variants):
    """Screen names support both B&R page extensions and explicit contains search."""
    pattern=str(pattern or '').strip().replace('\\','/')
    directory,separator,name=pattern.rpartition('/')
    prefix=directory+separator
    if name.endswith('#'):
        word=name[:-1].strip()
        if not word: return []
        patterns=[prefix+'*'+word+'*']
        allowed={'.page','.pages','.layer','.txtgrp'}
    elif re.search(r'\.pages?$',name,re.I):
        stem=re.sub(r'\.pages?$','',name,flags=re.I)
        patterns=[prefix+stem+'.page',prefix+stem+'.pages']
        allowed={'.page','.pages'}
    elif '.' not in name:
        extensions=['.txtgrp'] if variants and all(v.get('entity') in {'TextGroup','TextSnippet'} for v in variants) else ['.page','.pages']
        patterns=[pattern+extension for extension in extensions]
        allowed=set(extensions)
    else:
        patterns=[pattern]
        allowed={'.page','.pages','.layer','.txtgrp'}
        if variants and all(variant.get('entity')=='DataPoint' for variant in variants):
            allowed.add('.dso')
    found=set()
    for item in patterns:
        found.update(path for path in matching_files(root,item,engine) if path.suffix.casefold() in allowed)
    return sorted(found,key=lambda p:p.as_posix().casefold())


def text_requirements(group,variant):
    """IndexMap is the stable dropdown index; XML Text ID is only a lookup key."""
    rows=[]
    indexes={n.get('ID'):n.get('Value') for n in group.iter() if tag(n)=='Index'}
    entries={(layer.get('LanguageId'),indexes.get(n.get('ID'),n.get('ID'))):n.get('Value','') for layer in group.iter() if tag(layer)=='TextLayer' for n in layer if tag(n)=='Text'}
    snippets={n.get('Name'):n for n in group.iter() if tag(n)=='TextSnippet'}
    checked_texts=[]
    for expected in variant.get('texts') or []:
        if not str(expected.get('index','')).strip(): continue
        key=(expected.get('language') or 'en',str(expected['index']))
        actual=entries.get(key)
        checked_texts.append(actual or '')
        rows.append({'property':f'Text {key[0]} index {key[1]}','expected':expected.get('value',''),'actual':actual,'status':'PASS' if actual==expected.get('value','') else 'FAIL'})
    for name in sorted({name for text in checked_texts or entries.values() for name in re.findall(r'\{([^{}]+)\}',text)}):
        node=snippets.get(name)
        value=properties(node).get('Datapoint') if node is not None else None
        rows.append({'property':'Snippet {'+name+'} datapoint','expected':'Declared snippet with mapped datapoint','actual':value,'status':'PASS' if value and property_value(value)!='None' else 'FAIL'})
    for expected in variant.get('snippets') or []:
        name=expected.get('name','')
        if not name: continue
        node=snippets.get(name)
        values=properties(node) if node is not None else {}
        required={'Datapoint':expected.get('datapoint',''),**(expected.get('properties') or {})}
        if expected.get('classId'): required['ClassId']=expected['classId']
        if node is not None: values['ClassId']=node.get('ClassId')
        if not any(str(v).strip() for v in required.values()): required={'Name':name};values['Name']=node.get('Name') if node is not None else None
        for key,value in required.items():
            if not str(value).strip(): continue
            actual=values.get(key)
            rows.append({'property':f'Snippet {name} / {key}','expected':value,'actual':actual,'status':'PASS' if equal_property(actual,value) else 'FAIL'})
    return rows

def referenced_hmi_requirements(path,node,variant):
    """Follow resources on this exact control within its HMI target."""
    rows=[]
    for check in variant.get('referenceChecks') or []:
        touch=check['kind']=='touchpad'
        prop='InputTouchpad' if touch else 'TextGroup'
        raw=properties(node).get(prop,'')
        name=property_value(raw)
        override=str(check.get('nameOverride') or '').strip()
        expected_name=property_value(override) if override else name
        prefix=f'{prop} cross reference'
        def add(field,expected,actual,passed):
            rows.append({'property':prefix+' / '+field,'expected':expected,'actual':actual,'status':'PASS' if passed else 'FAIL'})
        if not name or name=='None':
            add('binding','Assigned resource',raw or 'Missing',False);continue
        if override and expected_name!=name:
            add('binding',expected_name,name,False);continue
        # Embedded text groups belong to the matched control.
        embedded=raw.startswith('Source[embedded].') and not touch
        resource=None;source=str(path)
        if embedded:
            groups=[child for child in node if tag(child)=='TextGroup']
            if len(groups)==1: resource=groups[0]
        else:
            target=next((parent.parent for parent in path.parents if parent.name.casefold() in {'pages','layers'}),None)
            suffix='.tpr' if touch else '.txtgrp'
            folder='TouchPads' if touch else 'TextGroups'
            paths=[] if target is None else [p for p in target.rglob('*') if p.is_file() and p.suffix.casefold()==suffix and p.stem.casefold()==expected_name.casefold() and p.parent.name.casefold()==folder.casefold()]
            if len(paths)!=1:
                add('file',expected_name+suffix,f'{len(paths)} matching files in this HMI target',False);continue
            source=str(paths[0])
            try: resource=ET.parse(paths[0]).getroot()
            except (ET.ParseError,OSError) as error:
                add('file','Readable XML',str(error),False);continue
        if resource is None:
            add('file','One embedded text group','Missing or ambiguous',False);continue
        add('file','Resolved referenced resource',source,True)
        if touch:
            lower=[];letters=set();keys=0;pairs=[]
            for panel in resource.iter():
                if tag(panel)!='PanelItem': continue
                panel_letters=[]
                for key in panel.iter():
                    if tag(key)!='KeyLevel': continue
                    level=key.get('Level','');v=key.get('VirtualKey','')
                    if check.get('shiftLevels','all')=='unshifted' and level not in {'0','2','4'}: continue
                    keys+=1
                    small=re.fullmatch(r'TP_ALPHA_s([a-z])',v)
                    upper=re.fullmatch(r'TP_ALPHA_([A-Z])',v)
                    if small: lower.append(small[1]);letters.add(small[1].upper());panel_letters.append(small[1])
                    if upper: letters.add(upper[1]);panel_letters.append(upper[1])
                if panel_letters:
                    pairs.append(f'Panel {panel.get("Index")}: '+ ' / '.join(panel_letters))
            add('alphabetic keys','At least one alphabetic key',f'{len(letters)} distinct letters; {keys} key mappings checked',bool(letters))
            add('decoded letters','Letter case for each configured key level','; '.join(pairs) or 'No alphabetic mappings',bool(letters))
            if check.get('characterRequirement','uppercase')=='uppercase':
                add('character requirement','Uppercase letters only', 'Lowercase letters found: '+ ' '.join(sorted(set(lower))) if lower else 'All alphabetic mappings are uppercase',not lower)
        else:
            rows.extend({**row,'property':prefix+' / '+row['property']} for row in text_requirements(resource,check))
    return rows

def evaluate(root,rule,engine):
    original_engine=engine
    project_paths=list(engine.all_files(root))
    project_texts={}
    class ProjectEngine:
        reference_project_root=root.resolve()
        reference_path_index={path.relative_to(root).as_posix().casefold():[path] for path in project_paths}
        def __getattr__(self,name):return getattr(original_engine,name)
        def read_text(self,path):
            if path not in project_texts:project_texts[path]=original_engine.read_text(path)
            return project_texts[path]
        def all_files(self,folder,suffix=None):
            folder=folder.resolve()
            return (path for path in project_paths if path.resolve().is_relative_to(folder) and (suffix is None or path.suffix.casefold()==suffix.casefold()))
    engine=ProjectEngine()
    normalized=configuration({**rule,'ruleId':rule.get('id'),'machineDepartment':(rule.get('machineScope') or ['All'])[0]})['rules'][0]
    if normalized['needsRuleConfiguration']:
        return engine.result(rule['id'],rule.get('name',rule['id']),'FAIL',rule.get('expected',''),'Complete the grouped requirements before validation.')
    rule={**rule,'checks':normalized['checks']}
    evidence=[]
    reference_cache={};reference_stack=set()
    hmi_scope=None
    def record(label,file,status,**extra):
        evidence.append({'check':label,'file':file,'status':status,**extra})
    def logic_candidate(candidate,scope_check,label,configuration_index):
        rows=[];paths=matching_files(root,candidate.get('file',''),engine)
        def add(check_name,file,status,**extra):
            rows.append({'check':check_name,'file':file,'status':status,'acceptedConfiguration':configuration_index,**extra})
        if not paths:
            add(label,candidate.get('file',''),'FAIL',actual='Configured PLC file was not found.')
            return False,rows
        for path in paths:
            relative=path.relative_to(root).as_posix();source=engine.read_text(path)
            mode=scope_check.get('groupMode','none')
            if mode=='none': segments=[(None,source,1)]
            else:
                branches=engine._parse_case_group_branches(source);wanted=set(scope_check.get('groupCodes',[]))
                groups=wanted if mode=='selected' else {branch['groupCode'] for branch in branches}-(wanted if mode=='exclude' else set())
                segments=[(branch['groupCode'],branch['segment'],branch['line']) for branch in branches if branch['groupCode'] in groups]
                for code in groups-{branch['groupCode'] for branch in branches}: add(label,relative,'FAIL',groupCode=code,actual='Required Group Code missing')
                if not groups: add(label,relative,'FAIL',actual='No Group Codes found in selected scope')
            alternatives=candidate.get('alternatives') or []
            for code,segment,line in segments:
                if not alternatives: continue
                hit=None
                for alternative_index,logic in enumerate(alternatives):
                    location=engine._logic_match(segment,logic)
                    if location: hit=(alternative_index,location);break
                evidence_line=line+segment.count('\n',0,hit[1][0]) if hit else line
                add(label,relative,'PASS' if hit else 'FAIL',groupCode=code,line=evidence_line,expected=alternatives,actual=segment[hit[1][0]:hit[1][1]] if hit else 'No complete accepted source block found',matchedAlternative=configuration_index if hit else None)
            for declaration in candidate.get('declarations') or []:
                requested=candidate.get('declarationFile') or (candidate['file'] if path.suffix.lower() in {'.var','.typ'} else '')
                declaration_paths=matching_files(root,requested,engine) if requested else list(engine.all_files(root,'.var'))
                if declaration.get('scope')=='local': declaration_paths=[item for item in declaration_paths if item.parent==path.parent]
                matches=[]
                for declaration_path in declaration_paths:
                    text=engine._strip_plc_comments(engine.read_text(declaration_path))
                    for block in re.finditer(r'\b(VAR(?:_GLOBAL|_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL)?)([ \t]*(?:(?:RETAIN|NON_RETAIN|PERSISTENT|CONSTANT)\b[ \t]*)*)(.*?)\bEND_VAR\b',text,re.I|re.S):
                        scope='global' if block.group(1).upper()=='VAR_GLOBAL' else 'local' if any(declaration_path.parent.glob('*.prg')) or declaration_path.parent==path.parent and path.suffix.lower() not in {'.var','.typ'} else 'global'
                        if declaration.get('scope') and declaration['scope']!=scope: continue
                        found=re.search(r'\b'+re.escape(declaration['variable'])+r'\s*:\s*([^;]+);',block.group(3),re.I)
                        if found:
                            actual=found.group(1).split(':=')[0].strip()
                            normalize=lambda value:re.sub(r'\s+','',value).upper().replace('STRING[','STRING(').replace(']',')') if value.upper().startswith('STRING') else re.sub(r'\s+','',value).upper()
                            ok=normalize(actual)==normalize(declaration['datatype']) and (not declaration.get('retention') or re.search(r'\b'+declaration['retention']+r'\b',block.group(2),re.I) is not None)
                            matches.append({'file':declaration_path.relative_to(root).as_posix(),'datatype':actual,'qualifiers':block.group(2).strip(),'status':'PASS' if ok else 'FAIL'})
                add(label+' declaration '+declaration['variable'],relative,'PASS' if any(item['status']=='PASS' for item in matches) else 'FAIL',expected=declaration,actual=matches or 'Declaration not found in required scope')
        return bool(rows) and all(row['status']=='PASS' for row in rows),rows
    def hmi_candidate_path(path,variant,label,configuration_index):
        relative=path.relative_to(root).as_posix();source=engine.read_text(path)
        try: xml=ET.fromstring(source)
        except ET.ParseError as error:
            return {'check':label,'file':relative,'status':'FAIL','acceptedConfiguration':configuration_index,'actual':'Invalid XML: '+str(error)}
        entity=variant.get('entity','Control');name=variant.get('name','')
        nodes=selected_nodes(xml,variant)
        attempts=[]
        if not nodes:
            available=[node for node in xml.iter() if tag(node)==entity]
            selection=f'{entity} name {variant.get("nameMatch","exact")} {name!r}'
            if variant.get('classId'): selection+=f' / ClassId {variant["classId"]}'
            attempts.append({'alternative':configuration_index,'control':'No matching object','status':'FAIL','reason':f'No object matches {selection}. Searched {len(available)} {entity} objects in this file.','availableObjects':[{'name':node.get('Name',''),'classId':node.get('ClassId','')} for node in available],'properties':[{'property':'Object selector','expected':selection,'actual':'No matching object','status':'FAIL'}]})
        for node in nodes:
            actual=properties(node);details=referenced_hmi_requirements(path,node,variant)
            for key,value in variant.get('properties',{}).items():
                got=actual.get(key);details.append({'property':key,'expected':value,'actual':got,'status':'PASS' if equal_property(got,value) else 'FAIL'})
            if entity=='TextGroup': details+=text_requirements(node,variant)
            if variant.get('textGroupFile'):
                target=path.parent.parent;group_paths=matching_files(target,variant['textGroupFile'],engine)
                if len(group_paths)!=1: details.append({'property':'Text group file','expected':variant['textGroupFile'],'actual':f'{len(group_paths)} matches in this target','status':'FAIL'})
                else:
                    group=ET.parse(group_paths[0]).getroot();binding=property_value(actual.get('TextGroup',''))
                    details.append({'property':'TextGroup binding','expected':group.get('Name'),'actual':binding,'status':'PASS' if binding==group.get('Name') else 'FAIL'});details+=text_requirements(group,variant)
            attempts.append({'alternative':configuration_index,'control':node.get('Name'),'properties':details,'status':'PASS' if all(detail['status']=='PASS' for detail in details) else 'FAIL'})
        chosen=next((attempt for attempt in attempts if attempt['status']=='PASS'),None)
        if chosen:
            return {'check':label,'file':relative,'status':'PASS','acceptedConfiguration':configuration_index,**{key:value for key,value in chosen.items() if key!='status'},'actual':'All required properties matched on the same object.'}
        reasons=[]
        for attempt in attempts:
            if attempt.get('reason'): reasons.append(attempt['reason'])
            else: reasons.append(f'{attempt["control"]}: '+'; '.join(f'{detail["property"]}: expected {detail.get("expected")!r}, actual {detail.get("actual")!r}' for detail in attempt['properties'] if detail['status']!='PASS'))
        return {'check':label,'file':relative,'status':'FAIL','acceptedConfiguration':configuration_index,'actual':'\n'.join(reasons) or 'No control requirement was configured.','attempts':attempts,'expected':variant}
    def hmi_roots():
        """Return resolved HMI roots, or every discovered root when project settings are absent."""
        screen=hmi_scope.get('screenFolder')
        folders=[screen] if screen else list(hmi_scope.get('screenFolders') or [])
        return [(name,(root/'Logical'/name).resolve()) for name in folders]
    def paths_in_hmi_scope(paths):
        roots=hmi_roots()
        return [path for path in paths if any(folder_root in path.resolve().parents for _,folder_root in roots)]
    def evaluate_cross_checks(check,label):
        crosses=check.get('crossChecks') or []
        if not crosses: return
        if check.get('crossCheckMode','all')=='all':
            for i,cross in enumerate(crosses): evaluate_check(cross,label+f' / cross reference {i+1}')
            return
        attempts=[];matched=False
        for i,cross in enumerate(crosses):
            start=len(evidence)
            evaluate_check(cross,label+f' / cross reference {i+1}')
            rows=evidence[start:]
            del evidence[start:]
            if rows and all(row['status'] in {'PASS','NOT_REQUIRED'} for row in rows):
                evidence.extend(rows);matched=True;break
            attempts.extend(rows)
        if matched:
            for row in attempts:
                row.update(alternativeStatus=row['status'],status='NOT_REQUIRED',
                           notRequiredReason='Another complete OR cross reference passed; this alternative is not required.')
        evidence.extend(attempts)
    def evaluate_check(check,label):
        nonlocal hmi_scope
        variants=list(check.get('variants') or [])+[item.get('variant',{}) for item in check.get('acceptedHmiAlternatives') or []]
        datasource_check=check.get('type')=='hmi' and bool(variants) and all(variant.get('entity')=='DataPoint' for variant in variants)
        if check.get('type')=='reference':
            key=(check['referenceFile'],check['checkId'],check.get('referenceHash',''))
            if key in reference_stack:
                record(label,check.get('file',''),'FAIL',actual='Circular saved reference.',referenceFile=key[0],checkId=key[1]);return
            if key not in reference_cache:
                start=len(evidence)
                try:
                    try:from python_engine.rule_references import load_reference
                    except ModuleNotFoundError:from rule_references import load_reference
                    definition=normalize_check(load_reference(check));reference_stack.add(key)
                    evaluate_check(definition,check.get('name') or label)
                    rows=evidence[start:];del evidence[start:]
                    reference_cache[key]=rows
                except (ValueError,OSError,KeyError,TypeError) as error:
                    del evidence[start:];reference_cache[key]=[{'status':'FAIL','actual':str(error),'file':check.get('file','')}]
                finally:reference_stack.discard(key)
            rows=reference_cache[key];failures=[row for row in rows if row.get('status') not in {'PASS','NOT_REQUIRED'}]
            record(label,check.get('file',''),'PASS' if rows and not failures else 'FAIL',
                   actual=f'{len(rows)-len(failures)} of {len(rows)} saved reference checks matched.',
                   referenceFile=key[0],checkId=key[1],referenceHash=key[2],
                   line=check.get('line'),referenceFailures=failures)
            return
        if check.get('type')=='ladder':
            try: from python_engine.ladder_requirements import evaluate as evaluate_ladder
            except ModuleNotFoundError: from ladder_requirements import evaluate as evaluate_ladder
            arrangements=[{'file':check.get('file',''),'networks':check.get('networks') or []}]+list(check.get('ladderAlternatives') or [])
            failed_details=[];searched=[];matched=None
            for alternative,arrangement in enumerate(arrangements,1):
                configured_file=str(arrangement.get('file') or '')
                alternative_paths=matching_files(root,configured_file,engine)
                if not alternative_paths:
                    failed_details.append({'ladderAlternative':alternative,'sourceFile':configured_file,'actual':'Configured ladder file was not found.','matchingNetworks':[]})
                    continue
                for path in alternative_paths:
                    relative=path.relative_to(root).as_posix();searched.append(relative)
                    passed,details=evaluate_ladder(engine.read_text(path),{'networks':arrangement.get('networks') or []})
                    for row in details:
                        if isinstance(row,dict):
                            row['ladderAlternative']=alternative;row['sourceFile']=relative
                            if passed: row['matchedAlternative']=alternative
                    if passed:
                        matched=(alternative,relative,details)
                        break
                    failed_details.extend(details)
                if matched: break
            expected_ladder=arrangements
            if matched:
                alternative,relative,details=matched
                record(label,relative,'PASS',expected=expected_ladder,ladderNetworks=details,matchedAlternative=alternative,actual=f'Accepted ladder alternative {alternative} matched in {relative}.')
            else:
                configured=', '.join(str(item.get('file') or '') for item in arrangements)
                record(label,', '.join(dict.fromkeys(searched)) or configured,'FAIL',expected=expected_ladder,ladderNetworks=failed_details,actual='No accepted ladder alternative matched in its configured ladder file.')
            evaluate_cross_checks(check,label)
            return
        if check.get('type')=='hmi' and check.get('acceptedHmiAlternatives'):
            if not datasource_check and hmi_scope is None:
                try: from python_engine.project_info import local_project_details
                except ModuleNotFoundError: from project_info import local_project_details
                hmi_scope=local_project_details(root)
            roots=[] if datasource_check else hmi_roots();candidates=[{'file':check.get('file',''),'variant':(check.get('variants') or [{}])[0]}]+list(check.get('acceptedHmiAlternatives') or [])
            failed=[];chosen=None
            if not datasource_check and not roots:
                evidence.append({'check':label,'file':check.get('file',''),'status':'FAIL','actual':'No HMI screen folder containing a Pages directory was found. '+hmi_scope.get('configurationMessage','')})
            else:
                for configuration_index,candidate in enumerate(candidates,1):
                    paths=matching_hmi_files(root,candidate.get('file',''),engine,[candidate['variant']])
                    if not datasource_check:paths=paths_in_hmi_scope(paths)
                    if not paths:
                        searched='configured datasource file' if datasource_check else ', '.join(f'Logical/{name}' for name,_ in roots)
                        rows=[{'check':label,'file':candidate.get('file',''),'status':'FAIL','acceptedConfiguration':configuration_index,'expected':candidate['variant'],'actual':f'Configured HMI file was not found in the checked HMI folder(s): {searched}.'}]
                    else: rows=[hmi_candidate_path(path,candidate['variant'],label,configuration_index) for path in paths]
                    if rows and all(row['status']=='PASS' for row in rows): chosen=rows;break
                    failed.extend(rows)
                evidence.extend(chosen or failed)
            evaluate_cross_checks(check,label)
            return
        if check.get('type')=='logic' and check.get('acceptedLogicAlternatives'):
            candidates=[{'file':check.get('file',''),'alternatives':check.get('alternatives') or [],'declarations':check.get('declarations') or [],'declarationFile':check.get('declarationFile','')}]
            candidates.extend({'file':item.get('file',''),'alternatives':[item.get('logic','')] if str(item.get('logic') or '').strip() else [],'declarations':item.get('declarations') or [],'declarationFile':item.get('declarationFile','')} for item in check.get('acceptedLogicAlternatives') or [])
            failed=[];chosen=None
            for configuration_index,candidate in enumerate(candidates,1):
                passed,rows=logic_candidate(candidate,check,label,configuration_index)
                if passed: chosen=rows;break
                failed.extend(rows)
            evidence.extend(chosen or failed)
            evaluate_cross_checks(check,label)
            return
        paths=(matching_hmi_files(root,check.get('file',''),engine,check.get('variants',[]))
               if check.get('type')=='hmi' else matching_files(root,check.get('file',''),engine))
        if check.get('type')=='hmi' and not datasource_check:
            if hmi_scope is None:
                try: from python_engine.project_info import local_project_details
                except ModuleNotFoundError: from project_info import local_project_details
                hmi_scope=local_project_details(root)
            roots=hmi_roots()
            if not roots:
                record(label,check.get('file',''),'FAIL',actual='No HMI screen folder containing a Pages directory was found. '+hmi_scope.get('configurationMessage',''))
                return
            paths=paths_in_hmi_scope(paths)
            if not paths:
                searched=', '.join(f'Logical/{name}' for name,_ in roots)
                record(label,check.get('file',''),'FAIL',expected='Configured file exists in a checked HMI folder',actual=f'Configured HMI file was not found in: {searched}.')
                return
        if not paths: record(label,check.get('file',''),'FAIL',expected='Configured file exists',actual='File not found')
        for path in paths:
            relative=path.relative_to(root).as_posix()
            source=engine.read_text(path)
            if check.get('type')=='hmi':
                try: xml=ET.fromstring(source)
                except ET.ParseError as error:
                    record(label,relative,'FAIL',actual='Invalid XML: '+str(error));continue
                attempts=[]
                for index,variant in enumerate(check.get('variants') or []):
                    entity=variant.get('entity','Control')
                    name=variant.get('name','')
                    nodes=selected_nodes(xml,variant)
                    if not nodes:
                        available=[n for n in xml.iter() if tag(n)==entity]
                        selection=f'{entity} name {variant.get("nameMatch","exact")} {name!r}'
                        if variant.get('classId'): selection+=f' / ClassId {variant["classId"]}'
                        attempts.append({'alternative':index+1,'control':'No matching object','status':'FAIL',
                            'reason':f'No object matches {selection}. Searched {len(available)} {entity} objects in this file. Required properties could not be checked.',
                            'availableObjects':[{'name':n.get('Name',''),'classId':n.get('ClassId','')} for n in available],
                            'properties':[{'property':'Object selector','expected':selection,'actual':'No matching object','status':'FAIL'}]})
                    for node in nodes:
                        actual=properties(node);details=referenced_hmi_requirements(path,node,variant)
                        for key,value in variant.get('properties',{}).items():
                            got=actual.get(key)
                            details.append({'property':key,'expected':value,'actual':got,'status':'PASS' if equal_property(got,value) else 'FAIL'})
                        if entity=='TextGroup': details+=text_requirements(node,variant)
                        if variant.get('textGroupFile'):
                            # Resolve relative to this HMI target, never another target's group.
                            target=path.parent.parent
                            group_paths=matching_files(target,variant['textGroupFile'],engine)
                            if len(group_paths)!=1: details.append({'property':'Text group file','expected':variant['textGroupFile'],'actual':f'{len(group_paths)} matches in this target','status':'FAIL'})
                            else:
                                group=ET.parse(group_paths[0]).getroot()
                                binding=property_value(actual.get('TextGroup',''))
                                details.append({'property':'TextGroup binding','expected':group.get('Name'),'actual':binding,'status':'PASS' if binding==group.get('Name') else 'FAIL'})
                                details+=text_requirements(group,variant)
                        attempts.append({'alternative':index+1,'control':node.get('Name'),'properties':details,'status':'PASS' if all(d['status']=='PASS' for d in details) else 'FAIL'})
                chosen=next((a for a in attempts if a['status']=='PASS'),None)
                if chosen: record(label,relative,'PASS',**{k:v for k,v in chosen.items() if k!='status'},actual='All required properties matched on the same object.')
                else:
                    reasons=[]
                    for attempt in attempts:
                        if attempt.get('reason'):
                            reasons.append(f'Alternative {attempt["alternative"]}: {attempt["reason"]}')
                        else:
                            differences=[f'{d["property"]}: expected {d.get("expected")!r}, actual {d.get("actual")!r}' for d in attempt['properties'] if d['status']!='PASS']
                            reasons.append(f'{attempt["control"]} / alternative {attempt["alternative"]}: '+ '; '.join(differences))
                    record(label,relative,'FAIL',actual='\n'.join(reasons) or 'No control alternatives were configured.',attempts=attempts,expected=check.get('variants'))
            else:
                mode=check.get('groupMode','none')
                if mode=='none': segments=[(None,source,1)]
                else:
                    branches=engine._parse_case_group_branches(source)
                    wanted=set(check.get('groupCodes',[]))
                    groups=wanted if mode=='selected' else {b['groupCode'] for b in branches}-(wanted if mode=='exclude' else set())
                    segments=[(b['groupCode'],b['segment'],b['line']) for b in branches if b['groupCode'] in groups]
                    for code in groups-{b['groupCode'] for b in branches}: record(label,relative,'FAIL',groupCode=code,actual='Required Group Code missing')
                    if not groups: record(label,relative,'FAIL',actual='No Group Codes found in selected scope')
                alternatives=check.get('alternatives') or []
                for code,segment,line in segments:
                    if not alternatives: continue
                    hit=None
                    for alternative_index,block in enumerate(alternatives):
                        location=engine._logic_match(segment,block)
                        if location:
                            hit=(alternative_index,location)
                            break
                    evidence_line=line + segment.count('\n',0,hit[1][0]) if hit else line
                    record(label,relative,'PASS' if hit else 'FAIL',groupCode=code,line=evidence_line,expected=alternatives,actual=segment[hit[1][0]:hit[1][1]] if hit else 'No complete accepted source block found',matchedAlternative=hit[0]+1 if hit else None)
                for declaration in check.get('declarations') or []:
                    requested=check.get('declarationFile') or (check['file'] if path.suffix.lower() in {'.var','.typ'} else '')
                    decl_paths=matching_files(root,requested,engine) if requested else list(engine.all_files(root,'.var'))
                    if declaration.get('scope')=='local': decl_paths=[p for p in decl_paths if p.parent==path.parent]
                    matches=[]
                    for dp in decl_paths:
                        text=engine._strip_plc_comments(engine.read_text(dp))
                        for block in re.finditer(r'\b(VAR(?:_GLOBAL|_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL)?)([ \t]*(?:(?:RETAIN|NON_RETAIN|PERSISTENT|CONSTANT)\b[ \t]*)*)(.*?)\bEND_VAR\b',text,re.I|re.S):
                            scope='global' if block.group(1).upper()=='VAR_GLOBAL' else 'local' if any(dp.parent.glob('*.prg')) or dp.parent==path.parent and path.suffix.lower() not in {'.var','.typ'} else 'global'
                            if declaration.get('scope') and declaration['scope']!=scope: continue
                            found=re.search(r'\b'+re.escape(declaration['variable'])+r'\s*:\s*([^;]+);',block.group(3),re.I)
                            if found:
                                actual=found.group(1).split(':=')[0].strip()
                                normalize=lambda x:re.sub(r'\s+','',x).upper().replace('STRING[','STRING(').replace(']',')') if x.upper().startswith('STRING') else re.sub(r'\s+','',x).upper()
                                ok=normalize(actual)==normalize(declaration['datatype']) and (not declaration.get('retention') or re.search(r'\b'+declaration['retention']+r'\b',block.group(2),re.I) is not None)
                                matches.append({'file':dp.relative_to(root).as_posix(),'datatype':actual,'qualifiers':block.group(2).strip(),'status':'PASS' if ok else 'FAIL'})
                    record(label+' declaration '+declaration['variable'],relative,'PASS' if any(m['status']=='PASS' for m in matches) else 'FAIL',expected=declaration,actual=matches or 'Declaration not found in required scope')
        evaluate_cross_checks(check,label)
    for i,check in enumerate(rule.get('checks') or []): evaluate_check(check,check.get('name') or f'Requirement {i+1}')
    failures=[row for row in evidence if row['status'] not in {'PASS','NOT_REQUIRED'}]
    required=[row for row in evidence if row['status']!='NOT_REQUIRED']
    output=engine.result(rule['id'],rule.get('name',rule['id']),'PASS' if evidence and not failures else 'FAIL',rule.get('expected',''),
                         f'{len(required)} required checks: {len(required)-len(failures)} passed, {len(failures)} failed.' + (f' {len(evidence)-len(required)} OR alternative finding(s) were not required.' if len(evidence)>len(required) else ''),evidence,['Review the expected and actual properties for each failed object.'] if failures else [],sorted({e['file'] for e in evidence}))
    output['structuredRequirements']=evidence
    if hmi_scope is not None:
        output['hmiScope']={key:hmi_scope.get(key) for key in ('activeConfiguration','plcType','screenFolder','screenFolders','configurationStatus','configurationMessage')}
    return output
