"""Build source-proven engineering blocks and links without invoking an LLM."""
from collections import defaultdict
from contextlib import closing
from bisect import bisect_right
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3

from .decoder import decode, lexical_tokens, section_ranges, SUPPORTED, EXECUTABLE
from python_engine.compare import decode_project_text
from python_engine.function_flow import _names
from python_engine.working_sequence import records, ASSIGNMENT, branch_guard
from python_engine.ladder_model import coil_condition
from python_engine.project_analysis import _mask

VERSION = 1


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:32]


def read_index(index,include_records=True):
    with closing(sqlite3.connect(index.path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        data = {name: [dict(row) for row in db.execute('SELECT * FROM '+name)]
                for name in (('files', 'symbols', 'tasks', 'edges') if include_records else ('files','tasks'))}
        data['meta'] = {row['key']: json.loads(row['value']) for row in db.execute('SELECT * FROM meta')}
    return data


def fingerprint(data):
    here = Path(__file__).parent
    parsers = [*here.glob('*.py'), here.parent/'function_flow.py', here.parent/'c_control_flow.py',
               here.parent/'ladder_model.py', here.parent/'working_sequence.py']
    versions = [(p.name, hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(parsers)]
    rows = sorted((row['path'], row['sha'], row['size'], row['mtime'], row['status']) for row in data['files'])
    return identity(VERSION, versions, rows, data['tasks'], data['meta'].get('identity'))


class Builder:
    def __init__(self, index, data, db):
        self.index, self.data, self.db = index, data, db
        self.blocks, self.links, self.issues = {}, {}, {}
        self.parsed, self.text, self.routines = {}, {}, defaultdict(list)
        self.declarations, self.callables = defaultdict(list), defaultdict(list)
        self.folded_declarations, self.resolved = defaultdict(list), {}
        self.declaration_modes = {}
        self.programs, self.private_files, self.task_blocks = {}, {}, []
        self.project = self.block('project', index.root.name, scope='project', layer='project', props={'indexKey': index.key})
        self.active = str((data['meta'].get('identity') or {}).get('activeConfiguration') or '')

    def block(self, kind, name, file='', first=1, last=None, scope='', language='', layer='logic', status='source', props=None, key=None):
        identifier = identity(kind, file, scope, key if key is not None else name)
        if identifier not in self.blocks:
            self.blocks[identifier] = {'id': identifier, 'kind': kind, 'name': name, 'file': file, 'first': first,
                'last': last or first, 'scope': scope, 'language': language, 'layer': layer, 'status': status, 'props': props or {}}
        return identifier

    def link(self, source, target, kind, file='', first=1, last=None, status='source', **props):
        identifier = identity(source, target, kind, file, first, props)
        self.links[identifier] = {'id': identifier, 'source': source, 'target': target, 'kind': kind,
            'file': file, 'first': first, 'last': last or first, 'status': status, 'props': props}
        return identifier

    def issue(self, code, message, file='', block='', severity='warning'):
        identifier = identity(code, message, file, block)
        self.issues[identifier] = {'id': identifier, 'code': code, 'message': message, 'file': file, 'block': block, 'severity': severity}

    def inventory(self):
        from backend.core.project_intelligence import EXCLUDED
        indexed = {row['path']: row for row in self.data['files']}
        inventory = []
        def scan(folder, excluded=False):
            for path in sorted(folder.iterdir()):
                relative = path.relative_to(self.index.root).as_posix()
                if path.is_symlink():
                    inventory.append((relative, 'excluded-link', '', 0, 0, '', '{}')); continue
                if path.is_dir():
                    try: scan(path, excluded or path.name.casefold() in EXCLUDED)
                    except PermissionError: self.issue('UNREADABLE_FOLDER', 'Cannot enumerate directory.', relative)
                    continue
                info = path.stat(); row = indexed.get(relative)
                suffix = path.suffix.casefold()
                if excluded: status = 'excluded-generated'
                elif not row: status = 'pending' if suffix in SUPPORTED else 'unsupported'
                elif row['status'] != 'indexed': status = 'index-failed'
                elif suffix not in SUPPORTED: status = 'unsupported'
                elif not info.st_size: status = 'empty'
                else: status = 'pending'
                sha = ''
                if status == 'pending':
                    if info.st_size > 8*1024*1024: status = 'size-limit'
                    else:
                        raw = path.read_bytes(); sha = hashlib.sha256(raw).hexdigest()
                        if row and sha != row['sha']: raise ValueError('Refresh the index before building; source changed: '+relative)
                        text = decode_project_text(path, raw).replace('\r\n', '\n').replace('\r', '')
                        if '\x00' in text: status = 'unsupported-binary'
                        else:
                            self.text[relative] = text
                            parsed = decode(relative, text); self.parsed[relative] = parsed; status = parsed['status']
                            if suffix in EXECUTABLE:
                                tokens = ((relative, *item) for item in lexical_tokens(relative, text))
                                self.db.executemany('INSERT INTO tokens VALUES (?,?,?,?,?,?)', tokens)
                            for notice in parsed['notices']: self.issue('PARSER_NOTICE', notice, relative)
                if status=='empty' and suffix in EXECUTABLE:
                    self.text[relative]='';self.parsed[relative]=decode(relative,'')
                props = {'indexStatus': row['status'] if row else None, 'sourceBasis':'existing index' if row else 'foundation scan', 'decoding': status,
                         'lineCount':max(1,len(self.text[relative].splitlines())) if relative in self.text else None}
                inventory.append((relative, status, sha or (row or {}).get('sha', ''), info.st_size, info.st_mtime_ns,
                                  (self.parsed.get(relative) or {}).get('language', ''), json.dumps(props)))
                if status in {'not-indexed','index-failed','size-limit','unsupported-binary'}:
                    self.issue('SOURCE_COVERAGE_GAP', status, relative)
                bid = self.block('source', path.name, relative, last=max(1, len(self.text.get(relative, '').splitlines())),
                                 layer='inventory', status=status, props=props)
                self.link(self.project, bid, 'CONTAINS', relative)
        scan(self.index.root)
        self.db.executemany('INSERT INTO files VALUES (?,?,?,?,?,?,?)', inventory)

    def configurations(self):
        selection=self.parsed.get('LastUser.set',{}).get('tree')
        if selection is not None:
            selected=[e.get('ActiveConfigurationName') for e in selection.iter() if e.get('ActiveConfigurationName')]
            if len(set(selected))==1:self.active=selected[0]
        for file, parsed in self.parsed.items():
            tree = parsed['tree']
            if tree is None: continue
            suffix = Path(file).suffix.casefold()
            if suffix == '.prg':
                folder = str(PurePosixPath(file).parent)
                program = self.block('program', PurePosixPath(folder).name, file, scope=folder, layer='execution',
                                     props={'manifest': file, 'fileOrderMeaning': 'manifest membership, not cross-task execution order'})
                self.programs[folder] = program
                self.link(self.project, program, 'CONTAINS', file)
                for element in tree.iter():
                    if element.tag.rsplit('}',1)[-1].casefold() != 'file' or not element.text: continue
                    member = (PurePosixPath(folder)/element.text.strip()).as_posix()
                    if '..' in PurePosixPath(member).parts: self.issue('UNSAFE_REFERENCE','Parent-directory manifest reference requires resolution.',file,program);continue
                    if element.get('Private','').casefold() == 'true': self.private_files[member] = folder
                    self.blocks[program]['props'].setdefault('members', []).append(member)
            if Path(file).name.casefold() != 'cpu.sw': continue
            parts = PurePosixPath(file).parts; configuration = parts[1] if len(parts)>1 else ''
            cfg = self.block('configuration', configuration, file, layer='execution',
                             props={'active': bool(self.active and configuration.casefold()==self.active.casefold())})
            self.link(self.project, cfg, 'CONFIGURATION', file)
            def tasks(element, task_class='', timing=None):
                tag = element.tag.rsplit('}',1)[-1].casefold(); timing = dict(timing or {})
                if tag=='taskclass': task_class = element.get('Name','')
                for key,value in element.attrib.items():
                    if any(word in key.casefold() for word in ('cycle','period','priority','interval','watchdog')): timing[key]=value
                if tag=='task':
                    name, source = element.get('Name',''), element.get('Source','')
                    disabled = element.get('Disabled','false').casefold() in {'true','1'} or element.get('Enabled','true').casefold() in {'false','0'}
                    row = next((row for row in self.data['tasks'] if row['file']==file and row['name']==name), {})
                    bid = self.block('task', name, file, row.get('line',1), scope=configuration+'/'+task_class, layer='execution',
                        props={'configuration':configuration,'active':self.blocks[cfg]['props']['active'], 'enabled':not disabled,
                               'source':source,'taskClass':task_class,'timing':timing,'executionContextsAreSeparate':True})
                    self.link(cfg,bid,'DECLARES_TASK',file,row.get('line',1)); self.task_blocks.append(bid)
                for child in element: tasks(child,task_class,timing)
            tasks(tree)

    def routine_blocks(self):
        declaration_ordinals=defaultdict(int)
        for file, parsed in self.parsed.items():
            sections=section_ranges(self.text[file], parsed['sections'])
            if not sections and Path(file).suffix.casefold() in EXECUTABLE:
                sections=[{'name':Path(file).stem,'nodes':[],'first':1,'last':max(1,len(self.text[file].splitlines())),
                           'declaredKind':'routine','phase':'unresolved','ordinal':0}]
            for section in sections:
                name = section['name'].split(':')[0].strip()
                scope = str(PurePosixPath(file).parent)+'/'+name
                kind = 'function_block' if section['declaredKind']=='function_block' else 'function' if section['declaredKind']=='function' else 'routine'
                bid = self.block(kind,name,file,section['first'],section['last'],scope,parsed['language'], status='partial' if parsed['notices'] else 'source',
                    key=section['ordinal'],props={'phase':section['phase'],'declaration':section['declaredKind'], 'ir':section['nodes'],
                        'parserNotices':parsed['notices'],'executionSimulated':False,'conceptTokens':[kind,section['phase'],parsed['language']]})
                self.routines[file].append((section,bid)); self.link(self.project,bid,'CONTAINS',file,section['first'])
                if kind in {'function','function_block'}: self.callables[name.split()[0]].append(bid)
                for folder, program in self.programs.items():
                    if file in self.blocks[program]['props'].get('members',[]): self.link(program,bid,'CONTAINS',file,section['first'])
        # Declarations are distinct blocks from callable implementations.
        for row in self.data['symbols']:
            file, name, kind = row['file'],row['display'],row['kind']
            if file not in self.text: continue
            if kind in {'function','function_block'}:
                bid = self.block('callable_declaration',name,file,row['line'],scope=row['scope'],layer='declarations',
                                 props={'declaredKind':kind,'datatype':row['datatype']})
                if not self.callables.get(name): self.callables[name].append(bid)
                continue
            if kind not in {'variable','data_type'}: continue
            scope = row['scope']; in_routine = next(((section,bid) for section,bid in self.routines[file] if section['first']<=row['line']<=section['last']),None)
            if file in self.private_files: scope = 'program:'+self.private_files[file]
            elif Path(file).suffix.casefold()=='.typ': scope = 'type:'+scope
            elif Path(file).suffix.casefold()=='.fun':
                headers = list(re.finditer(r'(?im)^\s*(?:FUNCTION_BLOCK|FUNCTION)\s+([A-Za-z_]\w*)',self.text[file]))
                preceding = [h for h in headers if self.text[file].count('\n',0,h.start())+1 <= row['line']]
                if preceding: scope = 'callable:'+preceding[-1][1]
            elif in_routine and not scope.startswith('@global/'):
                scope = 'routine:'+in_routine[1]
            declaration_key=(file,scope,name);ordinal=declaration_ordinals[declaration_key];declaration_ordinals[declaration_key]+=1
            if file not in self.declaration_modes:
                clean=_mask(self.text[file],strings=True)
                self.declaration_modes[file]=[(clean.count('\n',0,m.start())+1,m[1].upper()) for m in re.finditer(r'\b(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR_GLOBAL|VAR|END_VAR)\b',clean,re.I)]
            modes=self.declaration_modes[file];position=bisect_right([m[0] for m in modes],row['line'])-1
            mode=modes[position][1] if position>=0 else ''
            role={'VAR_INPUT':'input','VAR_OUTPUT':'output','VAR_IN_OUT':'in_out','VAR_GLOBAL':'global','VAR':'local'}.get(mode,'unspecified')
            if scope.startswith('type:'):role='type field'
            bid = self.block('data_type' if kind=='data_type' else 'variable',name,file,row['line'],scope=scope,layer='symbols',
                props={'datatype':row['datatype'],'indexScope':row['scope'],'declarationRole':role,'declarationOnly':True},key=(name,ordinal))
            self.declarations[name].append(bid)
            self.folded_declarations[name.casefold()].append(bid)
        # Link task SOURCE to actual manifest membership, not to a file named main.
        for task in self.task_blocks:
            item=self.blocks[task]; source=item['props']['source']
            logical='Logical/'+re.sub(r'\.prg$','',source,flags=re.I).replace('.','/').strip('/')
            targets=[program for folder,program in self.programs.items() if folder.casefold()==logical.casefold()]
            if len(targets)==1:
                program=targets[0]; self.link(task,program,'EXECUTES',item['file'],item['first'],phase='configured program')
                for edge in list(self.links.values()):
                    if edge['source']==program and edge['kind']=='CONTAINS':
                        routine=edge['target']; self.link(routine,task,'EXECUTES_IN',item['file'],item['first'],
                            active=item['props']['active'],enabled=item['props']['enabled'],phase=self.blocks[routine]['props']['phase'])
            else:
                self.issue('TASK_ENTRY_UNRESOLVED','Configured source has no unique program manifest: '+source,item['file'],task)

    def resolve(self, name, routine, file, line):
        key=(name,routine)
        if key not in self.resolved:self.resolved[key]=self._resolve(name,routine,file,line)
        return self.resolved[key]

    def _resolve(self, name, routine, file, line):
        name=re.sub(r'\s+','',name)
        base=re.split(r'[.\[]',name,1)[0]
        r=self.blocks[routine]; folder=str(PurePosixPath(file).parent)
        exact=self.declarations.get(base,[])
        if not exact:
            exact=self.folded_declarations.get(base.casefold(),[])
            if len({self.blocks[bid]['name'] for bid in exact})>1: exact=[]
        tiers=[['routine:'+routine],['callable:'+r['name'].split()[0]],['program:'+folder]]
        selected=[]
        for scopes in tiers:
            selected=[bid for bid in exact if self.blocks[bid]['scope'] in scopes]
            if selected: break
        if not selected: selected=[bid for bid in exact if self.blocks[bid]['scope'].startswith('@global/') and not self.blocks[bid]['scope'].startswith('type:')]
        # Never bind private library/template fields to same-named project globals.
        if not selected:
            selected=[bid for bid in exact if self.blocks[bid]['scope']==folder.casefold()]
        if len(selected)==1:
            resolved=selected[0]
            if name==base: return resolved,'source'
            member=self.block('member_access',name,file,line,scope=resolved,layer='symbols',status='partial',props={'base':base,'path':name,'memberTypeResolution':'not established'})
            self.link(member,resolved,'MEMBER_OF',file,line,status='partial')
            self.issue('MEMBER_TYPE_UNRESOLVED','Base declaration found; member/index type and bounds remain unresolved: '+name,file,member)
            return member,'partial'
        bid=self.block('unresolved_symbol',name,file,line,scope='routine:'+routine,layer='symbols',status='unresolved',
                       props={'candidates':selected,'reason':'ambiguous declaration' if selected else 'no declaration in this scope'})
        self.issue('SYMBOL_UNRESOLVED',('Ambiguous' if selected else 'Missing')+' declaration: '+name,file,bid)
        return bid,'unresolved'

    def logic(self):
        for file, routines in self.routines.items():
            parsed=self.parsed[file]
            for section,routine in routines:
                controls={};operations={}; ordinal=0
                def nodes(rows,parent,guards=()):
                    nonlocal ordinal
                    previous=None
                    for node in rows:
                        ordinal+=1; kind=node['kind']; first=node['line']; last=node.get('endLine',first)
                        nid=self.block('network' if kind=='network' else 'condition' if kind in {'condition','case','loop'} else 'operation',
                            node.get('label') or kind,file,first,last,scope=routine,language=parsed['language'],status=self.blocks[routine]['status'],
                            key=ordinal,props={'kind':kind,'code':node.get('code',''),'condition':node.get('condition'),
                                               'guards':list(guards),'disabled':node.get('disabled',False)})
                        self.link(parent,nid,'CONTAINS',file,first,last)
                        if previous:self.link(previous,nid,'NEXT_IN_SOURCE',file,first,status=self.blocks[routine]['status'],meaning='source progression within this branch, not runtime task scheduling')
                        previous=nid
                        if parent!=routine:self.link(parent,nid,'CONTROLS',file,first,last,status=self.blocks[routine]['status'],guards=list(guards))
                        controls[node['id']]=nid
                        for position,statement in enumerate(node.get('statements',[])):
                            op=self.block('assignment' if ASSIGNMENT.match(statement['code']) else 'statement',statement['code'][:100],
                                file,statement['line'],statement.get('endLine'),scope=routine,language=parsed['language'],
                                status=self.blocks[routine]['status'],key=(ordinal,position),props={'code':statement['code'],'guards':list(guards)})
                            operations[id(statement)]=op;self.link(nid,op,'CONTAINS',file,statement['line'])
                            for guard in guards:self.link(nid,op,'CONTROLS',file,statement['line'],status=self.blocks[routine]['status'],condition=guard)
                        for branch_index,branch in enumerate(node.get('branches',[])):
                            nodes(branch['nodes'],nid,(*guards,branch_guard(node,branch_index)))
                        nodes(node.get('children',[]),nid,(*guards,node['condition']) if kind=='loop' else guards)
                nodes(section['nodes'],routine)
                for record in records(section['nodes']):
                    row=record['row']; op=operations[id(row)]; match=ASSIGNMENT.match(row['code'])
                    expression=match[2] if match else row['code']
                    if match:
                        target,status=self.resolve(match[1],routine,file,row['line'])
                        self.link(op,target,'WRITES',file,row['line'],status=status,value=match[2],guards=record['guards'],routine=routine)
                    # Named input labels are not variable reads. Output arrows
                    # are explicit writes; positional argument binding stays open.
                    expression=re.sub(r'\b\w+\s*(?::=|=>)','',expression)
                    for name in _names(expression):
                        target,status=self.resolve(name,routine,file,row['line']);self.link(op,target,'READS',file,row['line'],status=status,routine=routine)
                    for condition in record['guards']:
                        condition=re.sub(r'\bmatches\b.*$','',condition)
                        for name in _names(condition):
                            if name in {'Other','CASE','values','of','Otherwise'}:continue
                            target,status=self.resolve(name,routine,file,row['line']);self.link(op,target,'READS',file,row['line'],status=status,role='guard',routine=routine)
                for node in section['nodes']:
                    # Full nested control structure is already retained as IR.
                    self.networks_and_states(node,routine,file,controls)
                for call in parsed['calls']:
                    if not section['first']<=call['line']<=section['last'] or call.get('disabled'):continue
                    self.call(call,routine,file)

    def networks_and_states(self,node,routine,file,controls):
        nid=controls[node['id']]
        if node['kind']=='network' and not node.get('disabled'):
            diagram=node['network']['diagram']
            self.blocks[nid]['props']['diagram']=diagram
            for cell in diagram['cells']:
                if cell['kind'] not in {'contact','coil','analog'} or not cell['name']:continue
                variable,status=self.resolve(cell['name'],routine,file,node['line'])
                writing=cell['kind']=='coil' or cell['kind']=='analog' and cell['type']=='output'
                self.link(nid,variable,'WRITES' if writing else 'READS',file,node['line'],node['endLine'],status=status,
                          instruction=cell['type'],row=cell['row'],column=cell['column'],routine=routine)
                if cell['kind']=='coil':
                    condition=coil_condition(diagram,cell['name'])
                    self.blocks[nid]['props'].setdefault('coilConditions',{})[cell['name']]=condition
                    if not condition['resolved']:self.issue('LADDER_SEMANTICS_UNRESOLVED',condition.get('reason','Unknown coil condition'),file,nid)
                    else:
                        for name in condition['inputs']:
                            source,source_status=self.resolve(name,routine,file,node['line'])
                            self.link(source,variable,'CONTROLS',file,node['line'],node['endLine'],status='source' if status==source_status=='source' else 'partial',
                                      expression=condition['expression'],coilType=cell['type'],network=nid,routine=routine)
        if node['kind']=='case':
            selector,status=self.resolve(node['condition'],routine,file,node['line'])
            for branch in node['branches']:
                state=self.block('state',branch['label'],file,branch['line'],scope=selector,layer='state',props={'selector':selector})
                self.link(selector,state,'HAS_STATE',file,branch['line'],status=status)
                for record in records(branch['nodes'],(branch_guard(node,node['branches'].index(branch)),)):
                    match=ASSIGNMENT.match(record['row']['code'])
                    if match and match[1]==node['condition']:
                        target=self.block('state',match[2],file,record['row']['line'],scope=selector,layer='state',props={'selector':selector,'assignedExpression':match[2]})
                        self.link(state,target,'TRANSITIONS',file,record['row']['line'],status=self.blocks[routine]['status'],
                                  conditions=record['guards'],routine=routine,execution='static assignment, not an observed transition')
        for branch in node.get('branches',[]):
            for child in branch['nodes']:self.networks_and_states(child,routine,file,controls)
        for child in node.get('children',[]):self.networks_and_states(child,routine,file,controls)

    def call(self,call,routine,file):
        name=call['name'];instance=call.get('instance') or name; targets=self.callables.get(name,[])
        if not targets or instance!=name:
            variable,status=self.resolve(instance,routine,file,call['line'])
            datatype=self.blocks[variable]['props'].get('datatype','').split()[0] if self.blocks[variable]['props'].get('datatype') else ''
            if not targets:targets=self.callables.get(datatype,[])
        else: variable=None
        if len(targets)!=1:
            target=self.block('unresolved_call',name,file,call['line'],scope=routine,layer='calls',status='unresolved',props={'candidates':targets})
            self.issue('CALL_UNRESOLVED','No unique implementation/declaration for '+name,file,target)
        else: target=targets[0]
        if variable and self.blocks[variable]['kind']=='variable':
            instance_id=self.block('function_block_instance',instance,file,call['line'],scope=routine,layer='calls',
                                   props={'datatype':self.blocks[variable]['props'].get('datatype'),'declaration':variable})
            self.link(instance_id,target,'INSTANCE_OF',file,call['line'],status='source' if len(targets)==1 else 'unresolved')
            target=instance_id
        self.link(routine,target,'CALLS',file,call['line'],status='source' if len(targets)==1 else 'unresolved',
                  instance=instance,code=call.get('code',''),conditionalInvocation='consult caller IR')
        if self.blocks[target]['kind']=='callable_declaration':self.issue('LIBRARY_BODY_MISSING','Call resolves only to a declaration: '+name,file,target)
        labels=list(re.finditer(r'\b([A-Za-z_]\w*)\s*(:=|=>)',call.get('code','')))
        bindings=list(re.finditer(r'\b([A-Za-z_]\w*)\s*(:=|=>)\s*([A-Za-z_]\w*(?:\.\w+)*)\s*(?=,|\))',call.get('code','')))
        if len(bindings)!=len(labels):self.issue('ARGUMENT_BINDING_UNRESOLVED','Complex/positional argument expression requires typed binding analysis: '+call.get('code',''),file,target)
        for binding in bindings:
            portname,operator,value=binding.groups()
            port=self.block('instance_port',portname,file,call['line'],scope=target,layer='calls',props={'direction':'input' if operator==':=' else 'output','instance':target})
            self.link(target,port,'HAS_PORT',file,call['line'])
            if value.upper() in {'TRUE','FALSE'}:
                self.blocks[port]['props']['literalArgument']=value;continue
            actual,actual_status=self.resolve(value,routine,file,call['line'])
            self.link(actual if operator==':=' else port,port if operator==':=' else actual,'BINDS_INPUT' if operator==':=' else 'BINDS_OUTPUT',file,call['line'],status=actual_status,formal=portname,actual=value,instance=instance)

    def cross_layers(self):
        for row in self.data['edges']:
            if row['kind'] not in {'hmi-binding','io-binding'} or row['file'] not in self.text:continue
            file=row['file'];parts=PurePosixPath(file).parts
            target_routine=self.block('binding_context',str(PurePosixPath(file).parent),file,scope=row['scope'],layer='configuration')
            self.blocks[target_routine]['props']['declarationScope']=row['scope']
            target_name=row['b'] if row['kind']=='hmi-binding' else row['a']
            # Index names are normalized. Require a unique case/scope candidate;
            # never bind an HMI Local.X to an arbitrary global X.
            candidates=[bid for name,bids in self.declarations.items() if name.casefold()==target_name.casefold() for bid in bids]
            if row['kind']=='hmi-binding':
                local=re.search(r'(?i)Variable\[([^\]]+)\]',row['detail'])
                reference=local[1] if local else target_name
                if reference.startswith('Local.'):
                    candidates=[bid for bid in candidates if str(PurePosixPath(self.blocks[bid]['file']).parent).casefold()==str(PurePosixPath(file).parent).casefold()]
                else:candidates=[bid for bid in candidates if self.blocks[bid]['scope'].startswith('@global/')]
                kind,name,layer='hmi_control',row['a'],'hmi'
                props={'binding':row['detail'],'hmiProject':parts[1] if len(parts)>1 else '', 'access':'binding direction/writability not established'}
            else:
                candidates=[bid for bid in candidates if self.blocks[bid]['scope'].startswith('@global/')]
                address=re.search(r'\bAT\s+(%[^;\r\n]+)',row['detail'],re.I)
                actual_address=address[1].strip() if address else None
                kind,name,layer='io_channel',actual_address or row['b'],'hardware'
                props={'mapping':row['detail'],'configuration':parts[1] if len(parts)>1 else '',
                       'active':bool(len(parts)>1 and parts[1].casefold()==self.active.casefold()),'logicalAddress':actual_address}
            context=self.block(kind,name,file,row['line'],scope=row['scope'],layer=layer,props=props,key=(row['line'],row['a'],row['b']))
            if len(candidates)==1: target=candidates[0];status='source'
            else:
                target=self.block('unresolved_symbol',target_name,file,row['line'],scope=row['scope'],layer='symbols',status='unresolved',props={'candidates':candidates})
                status='unresolved';self.issue('BINDING_UNRESOLVED','Binding target is not uniquely scoped: '+target_name,file,context)
            if kind=='io_channel' and not props['logicalAddress']:
                status='partial';self.issue('IO_ADDRESS_UNRESOLVED','Full physical I/O address was not decoded from its source mapping.',file,context)
            self.link(context,target,'BINDS_TO' if kind=='hmi_control' else 'MAPS_TO',file,row['line'],status=status,**props)

    def persist(self):
        # Compact routine interfaces link to scoped symbol blocks. They do not
        # rename every subroutine into an IEC FUNCTION_BLOCK or merge instances.
        interfaces=defaultdict(lambda:{'inputs':set(),'outputs':set(),'locals':set(),'tasks':set(),'states':set()})
        for edge in self.links.values():
            routine=edge['props'].get('routine')
            if routine and edge['kind'] in {'READS','WRITES'}:
                interfaces[routine]['inputs' if edge['kind']=='READS' else 'outputs'].add(edge['target'])
            if edge['kind']=='EXECUTES_IN':interfaces[edge['source']]['tasks'].add(edge['target'])
        for file,routines in self.routines.items():
            for section,routine in routines:
                local_scopes={'routine:'+routine,'callable:'+self.blocks[routine]['name'],'program:'+str(PurePosixPath(file).parent)}
                for bids in self.declarations.values():
                    for bid in bids:
                        if self.blocks[bid]['scope'] in local_scopes:interfaces[routine]['locals'].add(bid)
                interface={k:sorted(v) for k,v in interfaces[routine].items()}
                interface['declaredPorts']=[bid for bid in interface['locals'] if self.blocks[bid]['props'].get('declarationRole') in {'input','output','in_out'}]
                self.blocks[routine]['props']['interface']=interface
                self.blocks[routine]['props']['conceptTokens']=sorted(set(self.blocks[routine]['props'].get('conceptTokens',[])) |
                    {word.casefold() for word in re.findall(r'[A-Za-z][a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|\d+',self.blocks[routine]['name'].replace('_',' '))})
        self.db.executemany('INSERT INTO blocks VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            [(b['id'],b['kind'],b['name'],b['file'],b['first'],b['last'],b['scope'],b['language'],b['layer'],b['status'],json.dumps(b['props'])) for b in self.blocks.values()])
        self.db.executemany('INSERT INTO relations VALUES (?,?,?,?,?,?,?,?,?)',
            [(e['id'],e['source'],e['target'],e['kind'],e['file'],e['first'],e['last'],e['status'],json.dumps(e['props'])) for e in self.links.values()])
        self.db.executemany('INSERT INTO issues VALUES (?,?,?,?,?,?)',
            [(i['id'],i['code'],i['severity'],i['file'],i['block'],i['message']) for i in self.issues.values()])
