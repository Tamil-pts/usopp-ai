"""Project-derived field bench, with explicit assumptions and source traceability.

Hardware mappings establish direction and identity. Names suggest generic
mechanical models; they never establish real machine dynamics or contact polarity.
The original compiled logic remains responsible for interlocks and alarms.
"""
from collections import defaultdict, deque
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from .components import CATALOG, MAX_COMPONENTS, binding_reference, validate_components
from .memory import INTEGER_TYPES

DEFINITIONS = {entry['kind']: entry for entry in CATALOG}


def reference_text(node):
    if not isinstance(node, dict) or node.get('op') != 'ref': return ''
    text = node['name']
    for part in node.get('path', []):
        if 'member' in part: text += '.'+part['member']
        elif 'bit' in part: text += '.'+str(part['bit'])
        elif part.get('index', {}).get('op') == 'literal': text += '['+str(part['index']['value'])+']'
        else: return text+'[*]'
    return text


def scoped(runtime, address, scope=None):
    """Resolve only declared, unambiguous addresses, including HMI task prefixes."""
    try:
        record, ref = runtime.value_reference(address, scope)
        suffix = reference_text(ref)[len(ref['name']):]
        return record['id']+suffix
    except (ValueError, KeyError, TypeError):
        if '.' not in address: return None
        prefix, suffix = address.split('.', 1)
        name = re.split(r'[.\[]', suffix, 1)[0]
        matches = [v for v in runtime.memory.records.values() if v['name'] == name
                   and str(v['scope']).rsplit('/', 1)[-1].casefold() == prefix.casefold()]
        if len(matches) == 1:
            try:
                identity = matches[0]['id']+suffix[len(name):]
                runtime.value_reference(identity)
                return identity
            except (ValueError, KeyError, TypeError): pass
    return None


def ast_references(runtime, value, scope):
    result = set()
    def visit(item):
        if isinstance(item, dict):
            if item.get('op') == 'ref':
                text = reference_text(item)
                if '[*]' not in text:
                    identity = scoped(runtime, text, scope)
                    if identity: result.add(identity)
            else:
                for nested in item.values(): visit(nested)
        elif isinstance(item, list):
            for nested in item: visit(nested)
    visit(value)
    return result


class LogicIndex:
    """Bounded dependency index from the exact compiled programs in this runtime."""
    def __init__(self, runtime):
        self.runtime, self.writers = runtime, defaultdict(list)
        self.edge_count = 0
        for unit in runtime.units.values():
            if unit['id'] not in runtime.active_units: continue
            for section in unit.get('sections', []):
                self.walk(section.get('instructions', []), unit['scope'], unit['source'], set())

    def add(self, target, inputs, source, line):
        if not target or self.edge_count >= 100000: return
        edge = {'inputs': sorted(set(inputs)-{target}), 'source': source, 'line': line}
        if edge not in self.writers[target] and len(self.writers[target]) < 64:
            self.writers[target].append(edge); self.edge_count += 1

    def walk(self, nodes, scope, source, conditions):
        for node in nodes:
            if not isinstance(node, dict): continue
            op, line = node.get('op'), node.get('line', 1)
            if op == 'ladder' and not node.get('plan'):
                from .ladder_dataflow import compile_plan
                from .compiler import ladder_expression
                # Ordinary contact/coil networks use the same junction graph as
                # FB networks. Compile a read-only dependency plan for them too.
                plan = compile_plan(node['network'], source, ladder_expression)
                self.walk([{**node, 'plan':plan}], scope, source, conditions)
                continue
            if op == 'assign':
                self.add(scoped(self.runtime, reference_text(node['target']), scope),
                         conditions | ast_references(self.runtime, node.get('value'), scope), source, line)
            elif op in {'if','case'}:
                inherited = conditions | ast_references(self.runtime, node.get('value'), scope)
                all_conditions = set(inherited)
                for branch in node.get('cases', []):
                    reads = ast_references(self.runtime, branch.get('condition', branch.get('labels', [])), scope)
                    all_conditions |= reads
                    self.walk(branch.get('body', []), scope, source, inherited | reads)
                self.walk(node.get('else', []), scope, source, all_conditions)
            elif 'plan' in node:
                plan = node['plan']; operations = plan['operations']
                def upstream(wire, seen=None):
                    seen = set() if seen is None else seen
                    result = set()
                    for producer in plan['producers'].get(wire, []):
                        key = producer['operation']
                        if key in seen: continue
                        seen.add(key); item = operations[key]
                        result |= ast_references(self.runtime, item.get('expression'), scope)
                        if item.get('wire') is not None: result |= upstream(item['wire'], seen)
                        for pin in item.get('inputs', []): result |= upstream(pin['wire'], seen)
                    return result
                for item in operations.values():
                    if item.get('target'):
                        self.add(scoped(self.runtime, reference_text(item['target']), scope),
                                 conditions | upstream(item['wire']), source, item.get('line', line))
                    if item.get('kind') == 'functionblock':
                        target = scoped(self.runtime, item.get('name',''), scope)
                        inputs = set()
                        for pin in item.get('inputs', []): inputs |= upstream(pin['wire'])
                        self.add(target, inputs | conditions, source, item.get('line',line))
            elif op in {'call','reference_statement'}:
                expression = node.get('expression', {})
                name = expression.get('name') if expression.get('op') == 'call' else reference_text(expression)
                target = scoped(self.runtime, name or '', scope)
                if target:
                    reads = ast_references(self.runtime, expression.get('args',[]), scope)
                    for member in ('IN','CLK','CU','CD','R','RESET','PT'):
                        candidate = target+'.'+member
                        try:
                            self.runtime.value_reference(candidate); reads.add(candidate)
                        except (ValueError,TypeError,KeyError): pass
                    self.add(target, reads | conditions, source, line)
            else:
                nested_conditions = conditions | ast_references(self.runtime, node.get('condition'), scope)
                self.walk(node.get('body', []), scope, source, nested_conditions)

    def dependencies(self, identity, physical, limit=32):
        queue, seen, inputs, locations = deque([(identity,0)]), set(), [], []
        while queue and len(seen) < 128:
            current, depth = queue.popleft()
            if current in seen: continue
            seen.add(current)
            edges = self.writers.get(current, [])
            if not edges:
                parent = re.split(r'[.\[]', current, 1)[0]
                edges = self.writers.get(parent, [])
            if current in physical or not edges:
                try:
                    value = self.runtime.get_value(current)
                    if type(value) in (bool,int,float) and current != identity:
                        inputs.append({'variable': current, 'value': value, 'component': physical.get(current)})
                except (ValueError,TypeError,KeyError): pass
            for edge in edges:
                location = {'source':edge['source'],'line':edge['line']}
                if location not in locations and len(locations) < 8: locations.append(location)
                if depth < 10:
                    queue.extend((value,depth+1) for value in edge['inputs'])
        return inputs[:limit], locations, bool(queue) or len(inputs)>limit


def axis_tokens(name):
    tokens = set(re.findall(r'[A-Z]+\d*|\d+THROLL', name.upper()))
    tokens -= {'DI','DO','D','Q','START','STOP','ENABLE','READY','RDY','FLT','FAULT','SIGNAL','SERVO','DRIVE','MOTOR','RUN','FEEDBACK','SPEED'}
    return {t for t in tokens if not re.fullmatch(r'[IQ]\d+', t)}


def pair_score(command, feedback):
    def stem(name):
        name = re.sub(r'^(?:ED_)?D[IO]_', '', name.upper())
        name = re.sub(r'^(?:START|ENABLE)_TO_', '', name)
        return re.sub(r'_(?:READY|RDY|FAULT|FLT)$', '', name)
    if stem(command) == stem(feedback): return 100
    a,b = axis_tokens(command),axis_tokens(feedback)
    common = a & b
    explicit_axis = any(re.fullmatch(r'U\d+', token) for token in common)
    if not explicit_axis and (len(common)<2 or not common & {'HS','TS','RRL','RHS','LHS','FR','FEED','4THROLL'}): return 0
    return len(common)*4-len(a^b)+ (30 if explicit_axis else 0)


def bench_profile(runtime):
    """Select reviewed defaults by configuration and exact source fingerprints."""
    directory = Path(__file__).resolve().parents[1] / 'examples'
    sources = {unit['source']:unit.get('originalCode',unit.get('code','')) for unit in runtime.project.get('programs',[])}
    for path in sorted(directory.glob('*-field-bench.json')):
        profile = json.loads(path.read_text(encoding='utf-8'))
        if (profile.get('schemaVersion') != 1 or profile.get('project') != runtime.project.get('name')
                or profile.get('configuration') != runtime.project.get('projectInfo',{}).get('activeConfiguration')):
            continue
        signatures = profile.get('sourceSignatures',{})
        if signatures and all(hashlib.sha256(sources.get(name,'').encode()).hexdigest()==digest for name,digest in signatures.items()):
            return profile
    return None


def initialize_bench(runtime, components, reserved_ids=(), reserved_outputs=()):
    """Apply defaults on explicit jig preparation or to newly generated devices."""
    profile = bench_profile(runtime)
    if profile:
        modeled=set()
        for definition in profile.get('devices',[]):
            identity='field-'+hashlib.sha256((definition['kind']+':'+definition['name']).encode()).hexdigest()[:16]
            component=next((c for c in components if c['id']==identity),None)
            if component is None:
                outputs={definition.get('bindings',{}).get(p['key']) for p in DEFINITIONS[definition['kind']]['ports'] if p['direction']=='output'}
                if identity in reserved_ids or outputs.intersection(reserved_outputs):continue
                component={'id':identity,'name':definition['name'],'kind':definition['kind'],'enabled':True,
                           'bindings':{},'links':{},'config':{f['key']:f['default'] for f in DEFINITIONS[definition['kind']]['configFields']},
                           'evidence':definition.get('evidence',{}),'assumptions':[]}
                components.append(component)
            modeled.add(identity)
            component['bindings'].update(definition.get('bindings',{}))
            component['links'].update(definition.get('links',{}))
            component['config'].update(definition.get('config',{}))
            if definition['reason'] not in component['assumptions']:component['assumptions'].append(definition['reason'])
        for component in components:
            component.setdefault('assumptions',[])
            component.setdefault('evidence',{})
            name = component['name']
            if component['kind'] in {'pushbutton','digital_input'} and component.get('bindings',{}).get('value'):
                try:name=runtime.value_reference(component['bindings']['value'])[0]['name']
                except (ValueError,KeyError,TypeError):pass
            if name in profile.get('contacts',{}) and component['kind'] in {'pushbutton','digital_input'}:
                key = 'releasedValue' if component['kind']=='pushbutton' else 'value'
                component['config'][key] = profile['contacts'][name]
                component['evidence']['initializationProfile'] = profile['id']
                for assumption in profile.get('assumptions',[])[:2]:
                    if assumption not in component['assumptions']:component['assumptions'].append(assumption)
        feedback = set()
        for override in profile.get('deviceOverrides', []):
            identity='field-'+hashlib.sha256((override['kind']+':'+override['name']).encode()).hexdigest()[:16]
            matches = [c for c in components if c['kind'] == override['kind'] and (c['name'] == override['name'] or c['id']==identity)]
            if len(matches) != 1: continue
            component = matches[0]
            modeled.add(component['id'])
            component['bindings'].update(override.get('bindings', {}))
            component.setdefault('links',{}).update(override.get('links', {}))
            component['config'].update(override.get('config', {}))
            prior=component['evidence']
            obsolete=set(override.get('replacesAssumptions',[]))
            if prior.get('jigProfileId')==profile['id'] and prior.get('jigProfileReason')!=override['reason']:
                obsolete.add(prior.get('jigProfileReason'))
            component['assumptions']=[reason for reason in component['assumptions'] if reason not in obsolete]
            component['evidence'].update(jigProfileId=profile['id'],jigProfileVersion=profile.get('version',1),jigProfileReason=override['reason'])
            if override['reason'] not in component['assumptions']:component['assumptions'].append(override['reason'])
        for component in components:
            if component['id'] in modeled:
                feedback.update(component['bindings'][p['key']] for p in DEFINITIONS[component['kind']]['ports']
                                if p['direction']=='output' and component['bindings'].get(p['key']))
        # A modeled counter/sensor owns its input; keep only one feedback writer.
        components[:] = [c for c in components if not (c['id'] not in modeled and c['kind'] in {'digital_input','analog_input'}
                         and c['bindings'].get('value') in feedback)]
        return {key:profile[key] for key in ('id','name','version','reference','assumptions','statusSignals') if key in profile}
    return None


def build_plan(runtime, existing=()):
    components = deepcopy(list(existing)); existing_ids = {c['id'] for c in components}
    occupied = {value for c in components for value in c.get('bindings',{}).values()}
    inputs, outputs, unresolved, cpu_managed = [], [], [], []
    for channel in runtime.project.get('hardware',{}).get('channels', []):
        identity = channel.get('variableId')
        try:
            if not identity: raise ValueError('I/O tag has no unambiguous declaration')
            canonical, record, spec = binding_reference(runtime, identity)
            if channel.get('name') == 'SerialNumber':
                cpu_managed.append({'variable':canonical, 'service':'CPU services / serial numbers'})
                continue
            if spec.get('kind') != 'scalar' or spec.get('type') not in {*INTEGER_TYPES,'REAL','LREAL','BOOL'}:
                raise ValueError('Choose a scalar field for this hardware channel')
            entry = {'identity':canonical,'record':record,'spec':spec,'channel':channel}
            (inputs if channel.get('direction')=='input' else outputs).append(entry)
        except (ValueError,KeyError,TypeError) as error:
            unresolved.append({'variable':channel.get('variable'),'source':channel.get('source'),'line':channel.get('line'), 'reason':str(error)})
    added, assumptions = [], []
    def add(kind, name, bindings=None, links=None, evidence=None):
        identity = 'field-'+hashlib.sha256((kind+':'+name).encode()).hexdigest()[:16]
        if identity in existing_ids or len(components)+len(added)>=MAX_COMPONENTS: return None
        existing_ids.add(identity)
        item = {'id':identity,'name':name[:120], 'kind':kind,'enabled':True,
                'bindings':bindings or {},'links':links or {},
                'config':{f['key']:f['default'] for f in DEFINITIONS[kind]['configFields']},
                'evidence':evidence or {},'assumptions':[]}
        added.append(item); return item
    feedback_used = set()
    grouped_commands = set()
    for entry in outputs:
        record, key = entry['record'], entry['identity']; name = record['name']
        if key in occupied | grouped_commands or entry['spec'].get('type') != 'BOOL': continue
        if not re.search(r'MOTOR|MTR|DRIVE|SERVO|INVERTER|VFD',name,re.I) or re.search(r'BRAKE|RESET|FAULT|ALARM|LAMP|STOP|CONTROL',name,re.I): continue
        kind = 'velocity_servo' if 'SERVO' in name.upper() else 'vfd' if re.search(r'DRIVE|VFD|INVERTER',name,re.I) else 'motor'
        run_port = 'run' if kind == 'vfd' else 'enable'
        drive = add(kind, name, {run_port:key}, evidence={'source':entry['channel'].get('source'),'line':entry['channel'].get('line'),'command':key,'method':'Output mapping; mechanical model suggested from PLC tag'})
        if not drive: continue
        grouped_commands.add(key)
        if kind == 'velocity_servo':
            peer_name = name.replace('ENABLE_TO_', 'START_TO_') if 'ENABLE_TO_' in name else name.replace('START_TO_', 'ENABLE_TO_')
            peers = [e for e in outputs if e['record']['name'] == peer_name and peer_name != name and e['identity'] not in occupied]
            if len(peers) == 1:
                peer = peers[0]; grouped_commands.add(peer['identity'])
                drive['bindings']['run' if 'ENABLE_TO_' in name else 'enable'] = peer['identity']
                if 'START_TO_' in name: drive['bindings']['run'] = key
                drive['assumptions'].append('Enable and Start are separate exact output mappings for the same named drive.')
        drive['assumptions'].append('Generic speed/ramp defaults; confirm the drive type, units and operating reference in Configure.')
        for port, pattern in (('ready',r'RDY|READY'),('fault',r'FLT|FAULT')):
            if kind == 'motor': continue
            candidates = [(pair_score(name,e['record']['name']),e) for e in inputs if e['spec'].get('type')=='BOOL'
                          and e['identity'] not in occupied|feedback_used and re.search(pattern,e['record']['name'],re.I)]
            candidates.sort(key=lambda pair:pair[0],reverse=True)
            if candidates and candidates[0][0]>=8 and (len(candidates)==1 or candidates[0][0]>candidates[1][0]):
                candidate=candidates[0][1]; drive['bindings'][port]=candidate['identity']; feedback_used.add(candidate['identity'])
                drive['assumptions'].append(port+' feedback paired by unique axis tokens: '+candidate['record']['name']+'. Review this inferred connection.')
        if kind in {'vfd','velocity_servo'}:
            motor=add('motor',name+' / shaft', links={'enable':{'component':drive['id'],'port':'running'},'targetSpeed':{'component':drive['id'],'port':'speed'}},evidence=deepcopy(drive['evidence']))
            if motor:
                encoder=add('encoder',name+' / encoder',links={'speed':{'component':motor['id'],'port':'speed'}},evidence=deepcopy(drive['evidence']))
                if encoder: encoder['assumptions'].append('Encoder resolution is an editable model default; connect a documented PLC counter/feedback port in Configure.')
    seen = set(occupied)|feedback_used
    for entry in inputs+outputs:
        key, record, spec, channel = entry['identity'],entry['record'],entry['spec'],entry['channel']
        if key in seen: continue
        seen.add(key); is_input = channel.get('direction')=='input'; boolean=spec['type']=='BOOL'
        button = is_input and boolean and bool(re.search(r'START|PUSH|BUTTON|MACHINE_ON|MACHINE_OFF|MAIN_MOTOR_(?:SLOW|FAST)$|RESET.?PB|\bPB\b',record['name'],re.I))
        kind = 'pushbutton' if button else 'digital_input' if is_input and boolean else 'digital_output' if boolean else 'analog_input' if is_input else 'analog_output'
        port = 'value' if is_input else 'command'
        item=add(kind,record['name'],{port:key}, evidence={'source':channel.get('source'),'line':channel.get('line'),'address':channel.get('address'),'declaration':record.get('source'),'declarationLine':record.get('line'),'variable':key,'method':'Exact selected-configuration I/O mapping'})
        if not item: continue
        value=runtime.get_value(key)
        if kind=='pushbutton':
            item['config'].update(releasedValue=int(bool(value)),pulseMs=200)
            item['assumptions'].append('Released contact comes from current PLC memory. Confirm contact polarity before operating.')
        elif kind=='digital_input':
            item['config']['value']=1 if channel.get('name') == 'ModuleOk' else int(bool(value))
            if channel.get('name') == 'ModuleOk':
                item['assumptions'].append('Virtual module is present (ModuleOk = 1). Toggle this contact to simulate a missing module.')
        elif kind in {'analog_input','analog_output'}:
            low,high=INTEGER_TYPES.get(spec['type'],(-1000000,1000000))
            low,high=max(low,-1e9),min(high,1e9)
            item['config'].update(minimum=low, maximum=high)
            item['config']['value' if is_input else 'initialValue']=max(low,min(high,value))
            item['assumptions'].append('Numeric range reflects the datatype, not the physical sensor engineering range. Edit units and limits.')
    order = {'pushbutton':0,'vfd':1,'velocity_servo':1,'motor':2,'encoder':2}
    added.sort(key=lambda c:order.get(c['kind'],3))
    reserved_outputs={c['bindings'][p['key']] for c in components for p in DEFINITIONS[c['kind']]['ports']
                      if p['direction']=='output' and c['bindings'].get(p['key'])}
    initialization = initialize_bench(runtime, added, {c['id'] for c in components}, reserved_outputs)
    configured=validate_components(components+added,runtime)
    return {'components':configured,'added':len(added),'unresolved':unresolved[:1000],
            'cpuManaged':cpu_managed, 'initializationProfile': initialization,
            'summary':{'mappedChannels':len(inputs)+len(outputs)+len(cpu_managed),'cpuManagedChannels':len(cpu_managed),'unresolvedChannels':len(unresolved),
                       'components':len(configured),'alarms':sum(len(g.get('items',[])) for g in runtime.project.get('hmi',{}).get('alarmGroups',[]))},
            'assumptions':['Mechanical associations from names are suggestions. Review each component source and assumptions.',
                           'PLC interlocks, alarm logic and timers execute unchanged. Input polarity and process feedback require the configured plant or operator input.',
                           'Drive-to-shaft-to-encoder links use the preceding completed model step. Quadrature is sampled; a high-speed counter binding is preferred.']}


def alarm_rows(runtime):
    rows=[]
    for group in runtime.project.get('hmi',{}).get('alarmGroups',[]):
        for item in group.get('items',[]):
            rows.append({'id':group['name']+':'+str(item['index']), 'group':group['name'], 'text':item.get('text'),
                         'binding':item.get('binding'), 'source':group.get('source'),
                         'variable':scoped(runtime,item.get('binding') or '')})
    return rows
