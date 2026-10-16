"""Build explicit Lapformer reference rules from supplied AS projects.

This is an offline authoring tool. Validation uses the saved requirements;
it never learns expected logic from the project being validated. References
remain separate, disabled drafts for an engineer to review in KnowHub.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python_engine.function_flow import _text_flow
from python_engine.ladder_requirements import fragment
from python_engine.project_paths import project_files
from python_engine import rule_engine_v4_30 as engine
from python_engine.structured_requirements import normalize_check, configuration
from python_engine.rule_references import check_hash


APP = Path(__file__).resolve().parents[1]
FEATURE_NAMES = {
    'mms_nw_r': 'Read server, packet groups and responses',
    'mms_nw_w': 'Write server, parameter updates and acknowledgements',
    'mms_nw_2': 'SpinConnect communication supervision',
    'mms_ms': 'Machine identity, stoppage reason and doff step timing',
    'mms_pms': 'PMS machine identity, stoppage reason and doff step timing',
    'password': 'Login levels and access permissions',
    'ip_add': 'IP address, subnet, gateway and network configuration',
    'icmp_ping': 'Ping request, destination and result handling',
    'mms_rtc_auto': 'Server clock decoding and PLC RTC synchronization',
    'fltmode': 'Energy communication, scaling and shift accumulation',
    'ap31x1': 'Energy module communication and enabling',
    'd_report': 'Doff energy and production report capture',
    'shift': 'Run, idle, doff timers and shift report function block',
    'dofflog': 'Doff event, weight, length and history sequencing',
    'doff_rst': 'Doff reset conditions and counters',
    'doffalam': 'Doff fault conditions and alarm interlocks',
    'alarm': 'Machine alarm generation and history',
    'crlfault': 'Creel fault generation and history',
    'ala_help': 'Alarm assistance and display selection',
    'autodrft': 'Automatic draft, target weight and levelling control',
    'draft': 'Draft calculation and output conversion',
    'draftent': 'Draft entry interlocks',
    'cv_calc': 'Lap weight statistics and coefficient of variation',
    'loadcell': 'Load cell scaling, zero and lap weight capture',
    'load_cell_calib': 'Load cell calibration inputs and results',
    'cal_roll': 'Calendar roller measurement and weight control',
    'del_rate': 'Delivery speed measurement and conversion',
    'encoder': 'Encoder pulse scaling and length measurement',
    'lap_time': 'Lap build timer, exclusions and reset',
    'creelsen': 'Creel sensor monitoring and associated interlocks',
    'crel_dyn': 'Creel dynamic monitoring and measurement',
    'prg1': 'Machine start, servo enable and safety interlocks',
    'prg2': 'Machine sequence and auxiliary interlocks',
    'prg3': 'Machine drive and sequence control',
    'prg4': 'Guide head, spool changer and lap transfer sequence',
    'prg5': 'Doff actuators, trolley and sequence interlocks',
    'prg6': 'Machine run sequence and output interlocks',
    'prg7': 'Auxiliary sequence and actuator conditions',
    'lub': 'Lubrication intervals, run conditions and acknowledgement',
    'pfail': 'Power failure recovery and retained values',
    'gen': 'General machine calculation and supervisory conditions',
    'genera': 'General machine state and operator conditions',
    'set_log': 'Machine and process setting change detection',
    'hms_comm': 'HMS communication state and packet handling',
    'hms_scale': 'HMS values, scaling and display outputs',
    'hms_nw_0': 'HMS network supervision',
    'rdspress': 'Air pressure and consumption processing',
    'mh_usb': 'Machine history USB records and transfer',
    'ah_usb': 'Alarm history USB records and transfer',
    'usb_val': 'USB record formatting and values',
    'usb_transfer': 'USB transfer trigger and completion',
    'warnings_clear': 'Warning acknowledgement and reset',
    'cpu_temp': 'PLC temperature processing',
    'cpu_usage': 'PLC CPU usage processing',
    'cpu_log': 'PLC CPU log lifecycle',
    'scrnlock': 'Operator screen locking conditions',
    'loginout': 'Login and logout conditions',
    'modrtu': 'Modbus RTU requests, responses and status',
    'modinv': 'Drive command conversion and Modbus interface',
    'rs485': 'Servo RS485 communication and drive data',
    'fault_code': 'Servo fault code interpretation',
    'ltsctrl': 'Lap transport interface and sequence',
    'lts_opcua': 'Lap transport OPC UA interface',
    'batch_creeling': 'Batch creeling data and sequence',
    'cots_batch': 'Cots batch data and sequence',
}


def symbol(value):
    return re.split(r'[.\[]', str(value).strip(), 1)[0].casefold()


def compact(source):
    """Preserve executable tokens, string literals and order; omit comments."""
    source = engine._strip_plc_comments(source)
    return '\n'.join(line.strip() for line in source.splitlines() if line.strip())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')


class Reference:
    def __init__(self, root):
        self.root = root.resolve()
        self.files = sorted(project_files(self.root), key=lambda p:p.as_posix().casefold())
        self.texts = {}
        self.hashes = {}
        self.declarations = defaultdict(list)
        self.writers = defaultdict(list)
        self.routines = []
        self.notices = []
        self.bindings = defaultdict(list)
        self.io = defaultdict(list)
        self.functions = defaultdict(list)
        self.primary_checks = {}
        self.definitions = {}
        self.evidence = {}
        self._declarations()
        self._routines()
        self._hmi()
        self._io()

    def text(self, path):
        if path not in self.texts:
            self.texts[path] = path.read_text(encoding='utf-8-sig', errors='replace')
        return self.texts[path]

    def relative(self, path):
        return path.relative_to(self.root).as_posix()

    def proof(self, path, line=1, end=None, role='Reference logic', **extra):
        if path not in self.hashes:self.hashes[path]=hashlib.sha256(path.read_bytes()).hexdigest()
        return {'file':self.relative(path), 'line':line, 'endLine':end or line,
                'role':role, 'sha256':self.hashes[path], **extra}

    def logic(self, path, source, line=1, end=None, name='PLC logic'):
        check = {'type':'logic', 'name':name, 'file':self.relative(path),
                 'groupMode':'none', 'groupCodes':[], 'alternatives':[compact(source)],
                 'referenceEvidence':self.proof(path, line, end)}
        return check

    def _declarations(self):
        for path in self.files:
            if path.suffix.casefold() not in {'.var','.typ','.fun','.st','.ab'}:
                continue
            text = self.text(path)
            # Ignore implementation comments; do not infer scope from names.
            clean = engine._strip_plc_comments(text)
            for match in re.finditer(r'\bFUNCTION(?:_BLOCK)?\s+([A-Za-z_]\w*)\b',clean,re.I):
                self.functions[match[1].casefold()].append(path)
            if path.suffix.casefold() != '.var':
                continue
            local = any(path.parent.glob('*.prg'))
            for block in re.finditer(r'\b(VAR(?:_GLOBAL|_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL)?)([^\r\n]*)[\r\n]+(.*?)\bEND_VAR\b', clean, re.I|re.S):
                for match in re.finditer(r'(?m)^\s*([A-Za-z_]\w*)\s*(?:AT\s+[^:]+)?\s*:\s*([^;]+);',block[3]):
                    name, dtype = match[1], match[2].split(':=',1)[0].strip()
                    line = clean.count('\n',0,block.start(3)+match.start())+1
                    self.declarations[name.casefold()].append({'name':name,'datatype':dtype,'path':path,
                       'local':local and block[1].upper()!='VAR_GLOBAL', 'line':line,
                       'qualifiers':re.findall(r'\b(?:RETAIN|NON_RETAIN|PERSISTENT)\b',block[2],re.I),
                       'retain':'RETAIN' in block[2].upper() and 'NON_RETAIN' not in block[2].upper()})

    def declaration(self, name, path):
        rows = self.declarations.get(symbol(name), [])
        local = [row for row in rows if row['local'] and row['path'].parent==path.parent]
        rows = local or [row for row in rows if not row['local']]
        # A duplicate declaration is a reference finding, never a guessed binding.
        return rows[0] if len(rows)==1 else None

    def _routines(self):
        for path in self.files:
            relative = self.relative(path)
            if path.suffix.casefold() not in {'.st','.ab','.ld'} or not relative.casefold().startswith('logical/') or '/libraries/' in relative.casefold():
                continue
            text = self.text(path)
            if not re.search(r'\bPROGRAM\s+_(?:CYCLIC|INIT|EXIT)\b', text, re.I):
                continue
            if path.suffix.casefold()=='.ld':
                self._ladder(path,text)
                continue
            sections, variables, calls, notices = _text_flow(text, relative, path.suffix.casefold()=='.ab')
            self.notices.extend({'file':relative,'message':message} for message in notices)
            active_source=engine._strip_plc_comments(text)
            # Include calls inside conditions and nested expressions, which a
            # statement-only flow listing can omit. Strings are never calls.
            call_source=re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"",lambda match:''.join(char if char in '\r\n' else ' ' for char in match[0]),active_source)
            call_index={(call['name'].casefold(),call['line']):call for call in calls}
            for match in re.finditer(r'\b([A-Za-z_]\w*)\s*\(',call_source):
                if match[1].upper() in {'IF','ELSIF','WHILE','UNTIL','CASE','EXITIF','AND','OR','NOT','XOR'}:continue
                line=call_source.count('\n',0,match.start())+1
                call_index.setdefault((match[1].casefold(),line),{'name':match[1],'instance':match[1],'line':line})
            calls=list(call_index.values())
            for match in re.finditer(r'(Temp_nw_snd_buffer\d*)\s*\[[^]]+\]\s*:=\s*BIT_SET\s*\(\s*(Temp_nw_snd_buffer\d*)\s*\[',active_source,re.I):
                if match[1].casefold()!=match[2].casefold():
                    self.notices.append({'file':relative,'line':active_source.count('\n',0,match.start())+1,
                        'severity':'source_concern','variable':match[1],
                        'message':f'Alarm buffer destination {match[1]} differs from the BIT_SET input {match[2]}. Review the doff/creel alarm buffer assignment before approving this reference.',
                        'proposedDestination':match[2]})
            source = compact(text)
            if not re.sub(r'\b(?:PROGRAM|END_PROGRAM|_INIT|_CYCLIC|_EXIT)\b|;', '', source, flags=re.I).strip():
                continue
            check = self.logic(path,text,1,len(text.splitlines()))
            self.primary_checks[path] = check
            self.routines.append({'path':path,'check':check,'variables':variables,'calls':calls})
            lines = text.splitlines()
            # Keep the outer condition/CASE with the writer. An assignment on
            # its own would discard the interlocks and branch that execute it.
            blocks = [node for section in sections for node in section['nodes']]
            for variable in variables:
                for line in variable.get('writes',[]):
                    matches=[node for node in blocks if node['line']<=line<=node.get('endLine',node['line'])]
                    if notices or not matches:
                        # A legacy parser notice cannot establish a reliable
                        # enclosing branch. Require the full source program.
                        self.writers[symbol(variable['name'])].append({'path':path,'line':1,'endLine':len(lines),
                            'check':self.logic(path,text,1,len(lines),'Complete producing program for '+variable['name'])})
                        continue
                    node=matches[0];end=node.get('endLine',node['line'])
                    source='\n'.join(lines[node['line']-1:end])
                    self.writers[symbol(variable['name'])].append({'path':path,'line':node['line'],'endLine':end,
                        'check':self.logic(path,source,node['line'],end,'Producing logic for '+variable['name'])})

    def _ladder(self,path,text):
        networks=fragment(text)
        originals=list(re.finditer(r'<network\b[^>]*>.*?</network\s*>',text,re.I|re.S))
        expected=[];calls=[];variables=defaultdict(lambda:{'reads':set(),'writes':set()})
        for number,network in enumerate(networks,1):
            if network.get('commented','0').casefold() in {'1','true'}:
                continue
            if not any(node.tag.rsplit('}',1)[-1].casefold() in {'contact','coil','functionblock','function','analog'} for node in network.iter()):
                continue
            match=originals[number-1];line=text.count('\n',0,match.start())+1;end=line+match[0].count('\n')
            item={'id':f'network-{number}','label':network.get('comment') or network.get('label') or f'Network {number}',
                  'mode':'exact','xml':ET.tostring(network,encoding='unicode'),
                  'relation':'after' if expected else 'presence','relativeTo':expected[-1]['id'] if expected else ''}
            expected.append(item)
            for node in network.iter():
                kind=node.tag.rsplit('}',1)[-1].casefold()
                if kind in {'function','functionblock'} and node.get('type'):
                    calls.append({'name':node.get('type'),'instance':node.get('name') or node.get('type'),'line':line})
            # Exact XML preserves branches, negation, contacts, coils, FB pins
            # and connections. Ignore disabled rungs when collecting writers.
            for node in network.iter():
                kind=node.tag.rsplit('}',1)[-1].casefold();name=node.get('name','')
                if not re.fullmatch(r'[A-Za-z_]\w*(?:\.\w+|\[[^]]+\])*',name):
                    continue
                if kind not in {'contact','coil','analog','functionblock'}:
                    continue
                write=kind=='coil' or kind=='analog' and node.get('type','').casefold()=='output' or kind=='functionblock' and node.get('position')=='header'
                variables[name]['writes' if write else 'reads'].add(line)
                if write:
                    self.writers[symbol(name)].append({'path':path,'line':line,'endLine':end,
                        'check':{'type':'ladder','name':'Producing network for '+name,'file':self.relative(path),
                                 'networks':[{**item,'relation':'presence','relativeTo':''}],
                                 'referenceEvidence':self.proof(path,line,end,'Producing ladder network',network=number)}})
        if not expected:
            return
        check={'type':'ladder','name':'Active ladder networks and their order','file':self.relative(path),
               'networks':expected,'referenceEvidence':self.proof(path,1,len(text.splitlines()),'Ladder reference')}
        self.primary_checks[path]=check
        self.routines.append({'path':path,'check':check,'calls':calls,
             'variables':[{'name':name,'reads':sorted(rows['reads']),'writes':sorted(rows['writes'])} for name,rows in variables.items()]})

    def _hmi(self):
        datapoints=defaultdict(list)
        for path in self.files:
            if path.suffix.casefold()!='.dso':continue
            try:document=ET.fromstring(self.text(path))
            except ET.ParseError:continue
            parents={child:parent for parent in document.iter() for child in parent}
            for node in document.iter():
                if node.tag.rsplit('}',1)[-1]!='DataPoint':continue
                folders=[];parent=parents.get(node)
                while parent is not None:
                    if parent.tag.rsplit('}',1)[-1]=='Folder':folders.insert(0,parent.get('Name',''))
                    parent=parents.get(parent)
                name='.'.join([*folders,node.get('Name','')]);props={child.get('Name'):child.get('Value','') for child in node if child.tag.rsplit('}',1)[-1]=='Property'}
                check={'type':'hmi','name':'HMI datasource '+name,'file':self.relative(path),
                       'variants':[{'entity':'DataPoint','name':node.get('Name',''),'nameMatch':'exact',
                       'ancestorFolders':folders,'properties':{key:props[key] for key in ('PLCType','StringLength','VCType','UpdateTime','ConnectingVisus') if key in props}}],
                       'referenceEvidence':self.proof(path,role='HMI datasource',variable=name)}
                datapoints[(path.stem.casefold(),name.casefold())].append((check,props))
        for path in self.files:
            if path.suffix.casefold() not in {'.page','.layer'}:
                continue
            text=self.text(path)
            try:document=ET.fromstring(text.lstrip('\ufeff'))
            except ET.ParseError:
                self.notices.append({'file':self.relative(path),'message':'XML reference could not be parsed.'});continue
            for node in document.iter():
                kind=node.tag.rsplit('}',1)[-1]
                if kind!='Control':
                    continue
                props={child.get('Name'):child.get('Value','') for child in node if child.tag.rsplit('}',1)[-1]=='Property'}
                for prop in ('ValueDatapoint','IndexDatapoint','StatusDatapoint'):
                    binding=props.get(prop,'');match=re.fullmatch(r'Source\[[^]]+\]\.Variable\[([^.]+)\.(.*)\]',binding,re.I)
                    if not match:
                        continue
                    datasource,variable=match[1],match[2]
                    target=path.relative_to(self.root).parts[1]
                    candidates=[(check,properties) for check,properties in datapoints.get((datasource.casefold(),variable.casefold()),[])
                                if not properties.get('ConnectingVisus') or target.casefold() in {v.strip().casefold() for v in properties['ConnectingVisus'].split(',')}]
                    if len(candidates)!=1:
                        self.notices.append({'file':self.relative(path),'variable':variable,'message':'HMI binding has no unique target-specific datasource definition.'})
                        continue
                    dso_check,_=candidates[0]
                    variable_parts=variable.split('.')
                    if symbol(variable) not in self.declarations and len(variable_parts)>1:
                        # A .dso Folder can represent a global variable package.
                        # Remove it only when the remaining symbol is declared
                        # under that exact Logical package, not by suffix guess.
                        remaining='.'.join(variable_parts[1:]);rows=self.declarations.get(symbol(remaining),[])
                        if any(not row['local'] and row['path'].relative_to(self.root).parts[1].casefold()==variable_parts[0].casefold() for row in rows):variable=remaining
                    check={'type':'hmi','name':f'{node.get("Name")} / {prop} / {variable}',
                        'file':self.relative(path),'variants':[{'entity':'Control','name':node.get('Name',''),
                        'nameMatch':'exact','classId':node.get('ClassId',''),'properties':{prop:binding}}],
                        'crossChecks':[dso_check]}
                    line=next((i for i,value in enumerate(text.splitlines(),1) if '<Control ' in value and f'Name="{node.get("Name")}"' in value),1)
                    check['referenceEvidence']=self.proof(path,line,role='HMI binding',variable=variable)
                    self.bindings[symbol(variable)].append(check)

    def _io(self):
        for path in self.files:
            if path.suffix.casefold()!='.iom':continue
            for line,source in enumerate(self.text(path).splitlines(),1):
                match=re.search(r'([A-Za-z_]\w*(?:\[\d+\])?)\s+AT\s+(%[IQ][^;\r\n]+);',source)
                if match:
                    check=self.logic(path,source,line,line,'I/O channel for '+match[1])
                    check['referenceEvidence']=self.proof(path,line,role='Physical I/O binding',variable=match[1],address=match[2])
                    self.io[symbol(match[1])].append(check)

    def cross_references(self,path,variables,calls):
        checks=[];proofs=[];unresolved=[];seen=set()
        def add(check,identity,proof):
            if identity in seen:return
            seen.add(identity);checks.append(check);proofs.append(proof)
        call_bindings=[]
        for call in calls:
            declaration=self.declaration(call['name'],path)
            function_name=declaration['datatype'] if declaration else call['name']
            definitions=list(dict.fromkeys(self.functions.get(function_name.casefold(),[])))
            call_bindings.append({**call,'functionType':function_name,
                'definitionFiles':[self.relative(source) for source in definitions],
                'resolution':'resolved' if len(definitions)==1 else 'ambiguous' if definitions else 'definition not supplied'})
            if len(definitions)==1:
                source=definitions[0]
                if source!=path:
                    proof=self.proof(source,1,len(self.text(source).splitlines()),'Called function definition',variable=function_name)
                    add(self.logic(source,self.text(source),name='Called function '+function_name),('function',self.relative(source)),proof)
            else:
                identity=('unresolved-call',function_name.casefold())
                if identity not in seen:
                    seen.add(identity)
                    unresolved.append({'file':self.relative(path),'line':call['line'],'variable':function_name,
                        'reason':'Multiple function definitions need explicit selection.' if definitions else 'Function implementation/signature is not supplied as readable source. The call remains checked in its complete source block; library behavior is not inferred.'})
        for variable in variables:
            name=variable['name'];key=symbol(name)
            if key in {'true','false'}:continue
            declaration=self.declaration(name,path)
            if not declaration:
                unresolved.append({'variable':name,'reason':'No unique declaration in the source task or global declarations.'})
                continue
            dp=declaration['path'];dtype=declaration['datatype']
            requirement={'variable':declaration['name'],'datatype':dtype,'retain':declaration['retain']}
            check={'type':'logic','name':'Declaration of '+declaration['name'],'file':self.relative(dp),
                   'declarationText':declaration['name']+' : '+dtype+' / '+('local' if declaration['local'] else 'global')+''.join(' / '+qualifier.upper() for qualifier in declaration['qualifiers']),
                   'declarations':[requirement],'declarationFile':self.relative(dp),'groupMode':'none','groupCodes':[]}
            proof=self.proof(dp,declaration['line'],role='Declaration',variable=name,datatype=dtype)
            check['referenceEvidence']=proof
            add(check,('decl',self.relative(dp),key),proof)
            function_paths=list(dict.fromkeys(self.functions.get(dtype.casefold(),[])))
            if len(function_paths)>1:
                unresolved.append({'variable':name,'reason':'Multiple function block definitions need explicit selection: '+', '.join(self.relative(source) for source in function_paths)})
            for function_path in function_paths if len(function_paths)==1 else []:
                if function_path==path:continue
                proof=self.proof(function_path,1,len(self.text(function_path).splitlines()),'Function block definition',variable=name,datatype=dtype)
                add(self.logic(function_path,self.text(function_path),name='Function block '+dtype),('function',self.relative(function_path)),proof)
            if declaration['local']:
                continue
            if variable.get('reads'):
                producers=[]
                for writer in self.writers.get(key,[]):
                    wp=writer['path']
                    if wp==path:continue
                    resolved=self.declaration(key,wp)
                    if resolved is None or resolved['path']!=dp:
                        continue
                    proof=self.proof(wp,writer['line'],writer['endLine'],'Producing logic',variable=name)
                    add(writer['check'],('producer',self.relative(wp),writer['line'],writer['endLine']),proof)
                    producers.append(self.relative(wp))
                if not producers:
                    unresolved.append({'variable':name,'reason':'No other executable producer resolved; may be initialized locally, supplied by an HMI, I/O or a function block.'})
            for binding in self.bindings.get(key,[]):
                proof=binding['referenceEvidence']
                add(binding,('hmi',binding['file'],binding['name']),proof)
            for binding in self.io.get(key,[]):
                proof=binding['referenceEvidence']
                add(binding,('io',binding['file'],proof['line']),proof)
        # Check each declaration file once with all of this routine's required
        # declarations. Preserve every datatype rather than repeating file work.
        grouped={};merged=[]
        for check in checks:
            if check.get('declarationText') and not check.get('alternatives'):
                key=check['file']
                if key not in grouped:
                    grouped[key]={**check,'name':'Required declarations in '+key};merged.append(grouped[key])
                else:grouped[key]['declarationText']+='\n'+check['declarationText']
            else:merged.append(check)
        return merged,proofs,unresolved,call_bindings

    def saved_reference(self,check,profile_id):
        definition={key:value for key,value in check.items() if key not in {'name','referenceEvidence'}}
        if definition.get('crossChecks'):
            definition['crossChecks']=[self.saved_reference(child,profile_id) for child in definition['crossChecks']]
        definition=normalize_check(definition)
        # Keep only checking fields, without redundant empty editor defaults.
        definition={key:value for key,value in definition.items() if value not in (None,'',[],{})}
        digest=check_hash(definition);identifier='C-'+digest[:24]
        self.definitions[identifier]=definition
        proof=check.get('referenceEvidence') or {}
        return {'type':'reference','name':check.get('name') or proof.get('role') or 'Saved reference',
                'file':check['file'],'referenceFile':'LAPFORMER-'+profile_id+'_v1.0.json',
                'checkId':identifier,'referenceHash':digest,'line':proof.get('line',1)}

    def rules(self,profile_id):
        result=[]
        for routine in self.routines:
            path=routine['path'];relative=self.relative(path)
            task=path.parent.name.casefold();title=FEATURE_NAMES.get(task,task.replace('_',' ').title()+' logic')
            if not re.search(r'\bPROGRAM\s+_CYCLIC\b',self.text(path),re.I):title+=' / initialization or shutdown'
            rid='LP-'+profile_id+'-'+hashlib.sha256(relative.casefold().encode()).hexdigest()[:10].upper()
            crosses,proofs,unresolved,call_bindings=self.cross_references(path,routine['variables'],routine['calls'])
            references=[self.saved_reference(check,profile_id) for check in crosses]
            # One full producing block can satisfy several shared variables.
            # It remains required once, with its complete branch or rung intact.
            crosses=list({check['checkId']:check for check in references}.values())
            primary={**routine['check'],'name':title,'crossChecks':crosses,'crossCheckMode':'all'}
            groups=engine._parse_case_group_branches(self.text(path)) if path.suffix.casefold()!='.ld' else []
            primary=normalize_check(primary)
            result.append({'id':rid,'name':title+' / '+self.root.name,'kind':'structured_requirements',
                'category':'Logic traceability in various subroutines','version':'1.0',
                'machineDepartment':'Lapformer','machineScope':['Lapformer'],'machineModels':[self.root.name],
                'featureId':'lapformer_'+profile_id.casefold(),'featureName':'Lapformer / '+self.root.name,
                'enabled':False,'reviewStatus':'Source reference draft - engineer review required',
                'needsRuleConfiguration':False,'configurationFormat':'grouped-v1',
                'description':f'Reference requirement for {title.lower()} in {self.root.name}. Compare the complete active source logic or ordered ladder networks, its declared tags, and resolved producing logic and HMI bindings. This is a project reference baseline; review it before using it as an engineering acceptance requirement.',
                'expected':'All configured reference logic and cross references must match in the same selected Lapformer project.',
                'checks':[primary],
                'referenceProfile':{'id':profile_id,'project':self.root.name,
                    'sourceFile':relative,'sourceSha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'basis':'Supplied project implementation; engineering acceptance review pending',
                    'groupCodes':sorted({group['groupCode'] for group in groups}),
                    'crossReferenceCount':len(crosses)},
                'sourceEvidence':[self.proof(path,1,len(self.text(path).splitlines()),'Primary logic')],
                'functionCalls':call_bindings,
                'referenceFindings':[{**notice,'reason':notice['message']} for notice in self.notices if notice.get('file')==relative and notice.get('severity')=='source_concern']+unresolved+[{**notice,'reason':notice['message']} for notice in self.notices if notice.get('file')==relative and notice.get('severity')!='source_concern']})
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',action='append',required=True,metavar='ID=PROJECT_PATH')
    parser.add_argument('--output',type=Path,default=APP/'rules/modules')
    parser.add_argument('--knowledge',type=Path,default=APP/'knowledge/lapformer')
    args=parser.parse_args();catalog_path=args.knowledge/'catalog.json'
    previous_catalog=json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.exists() else {}
    catalog={profile['id']:profile for profile in previous_catalog.get('profiles',[])}
    for supplied in args.reference:
        profile_id,raw_path=supplied.split('=',1)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',profile_id):raise ValueError('Use a short profile ID.')
        root=Path(raw_path)
        if not (root/'Logical').is_dir() or not any(root.glob('*.apj')):
            raise ValueError('Select an Automation Studio project root: '+str(root))
        reference=Reference(root);rules=reference.rules(profile_id)
        for rule in rules:
            normalized=configuration({**rule,'ruleId':rule['id']})['rules'][0]
            if normalized.get('needsRuleConfiguration'):
                raise ValueError('Incomplete reference requirement: '+rule['name'])
        module={'id':'LAPFORMER-'+profile_id,'name':'Lapformer / '+root.name,'version':'1.0',
                'machineScope':['Lapformer'],'enabled':False,'rules':rules}
        path=args.output/('LAPFORMER-'+profile_id+'_v1.0.json')
        # Rebuilding must not overwrite hand-edited module configurations.
        previous=args.knowledge/(profile_id+'.json')
        reference_path=args.output.parent/'references'/path.name
        if path.exists():
            saved=json.loads(previous.read_text(encoding='utf-8')) if previous.exists() else {}
            if saved.get('moduleSha256')!=hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError('Reference module has been edited; preserve it and choose a new profile ID: '+str(path))
            if reference_path.exists() and saved.get('referenceSha256') and saved['referenceSha256']!=hashlib.sha256(reference_path.read_bytes()).hexdigest():
                raise ValueError('Reference definitions have been edited; choose a new profile ID: '+str(reference_path))
        write_json(path,module)
        write_json(reference_path,{'schemaVersion':1,'profile':profile_id,'checks':reference.definitions})
        info={'id':profile_id,'project':root.name,'rules':len(rules),
              'module':path.name,'moduleSha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'referenceSha256':hashlib.sha256(reference_path.read_bytes()).hexdigest(),
              'referenceFileCount':len(reference.routines),
              'crossReferences':sum(rule['referenceProfile']['crossReferenceCount'] for rule in rules),
              'savedReferenceDefinitions':len(reference.definitions),
              'groupCodes':sorted({code for rule in rules for code in rule['referenceProfile']['groupCodes']}),
              'referenceFiles':[{'file':reference.relative(row['path']),'ruleId':rule['id']} for row,rule in zip(reference.routines,rules)],
              'parserNotices':reference.notices,
              'sourceConcerns':[notice for notice in reference.notices if notice.get('severity')=='source_concern'],
              'reviewStatus':'Source reference draft - engineer review required'}
        write_json(previous,info);catalog[profile_id]=info
        print(json.dumps({key:info[key] for key in ['id','project','rules','crossReferences','groupCodes']}))
    write_json(catalog_path,{'schemaVersion':1,'profiles':list(catalog.values())})


if __name__=='__main__':
    main()
