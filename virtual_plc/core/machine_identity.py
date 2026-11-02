"""Source-derived machine names and dependencies, shared with Chopper.

This is inspection metadata. It never creates a device, writes PLC memory or
turns a data dependency/source listing into a physical operating timeline.
"""
from collections import defaultdict, deque
import hashlib
import re
from pathlib import PurePosixPath
import xml.etree.ElementTree as ET

from python_engine.function_flow import _names, _text_flow
from python_engine.compare import _ladder_networks
from python_engine.source_operations import collect_operations
from .machine_calls import decode_calls

VERSION = 5


def text_hash(text):
    return hashlib.sha256(text.replace('\r\n','\n').replace('\r','\n').replace('\x00','').encode()).hexdigest()


def words(text):
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(text))
    return set(re.findall(r'[a-z0-9]+', text.casefold()))


def build(model, sources):
    variables = model.get('variables', [])
    by_name = defaultdict(list)
    by_id = {v['id']: v for v in variables}
    for v in variables:
        by_name[v['name']].append(v)
    active = {p for t in model.get('tasks', []) if t.get('enabled', True) for p in t.get('programs', [])}
    selected = str(model.get('projectInfo', {}).get('activeConfiguration') or '')
    hmis = model.get('projectInfo', {}).get('configuredHmiObjects') or []
    if not hmis and model.get('projectInfo', {}).get('screenFolder'):
        hmis = [model['projectInfo']['screenFolder']]
    hashes = {p: text_hash(t) for p, t in sources.items()}

    def ref(file, line=1):
        return {'file': file, 'line': max(1, line), 'sourceHash': hashes.get(file)}

    def line(file, needle):
        text = sources.get(file, '')
        pos = text.find(needle)
        return text.count('\n', 0, pos) + 1 if pos >= 0 else 1

    def resolve(name, scope=None):
        if name in by_id:
            return name
        candidates = by_name.get(str(name), [])
        if scope:
            local = [v for v in candidates if v.get('scope') == scope]
            if local:
                candidates = local
            else:
                candidates = [v for v in candidates if v.get('scope') == '@global']
        else:
            candidates = [v for v in candidates if v.get('scope') == '@global']
        return candidates[0]['id'] if len(candidates) == 1 and not candidates[0].get('ambiguous') else None

    operations, functions, transitions, issues = [], [], [], []
    unresolved_operations=0
    for program in model.get('programs', []):
        file, scope = program['source'], program.get('scope')
        code = sources.get(file, program.get('originalCode', program.get('code', '')))
        assigned = program['id'] in active
        functions.append({'id': program['id'], 'name': program['name'], 'file': file,
                          'active': assigned, 'kind': program.get('kind'), 'scope': scope,
                          'tasks': [t['name'] for t in model.get('tasks', []) if program['id'] in t.get('programs', [])],
                          'sources': [ref(file)]})
        suffix = PurePosixPath(file).suffix.lower()
        try:
            networks = _ladder_networks(code) if suffix == '.ld' else []
            facts = collect_operations(file, code, 'Ladder' if networks else 'Logic',
                                       'active task' if assigned else 'unassigned routine', networks)
        except (ValueError, KeyError, IndexError, TypeError) as error:
            issues.append({'file': file, 'message': 'Operation extraction incomplete: ' + str(error)[:150]})
            facts = []
        for fact in facts:
            output = resolve(fact['name'], scope)
            if not output:
                unresolved_operations+=1
                if len(issues)<200:issues.append({'file':file,'line':fact['eventLine'],'message':'Scoped target/member unresolved: '+fact['name']})
                continue
            guards = fact.get('guards', [])
            reads = set(fact.get('reads', [])) | set(_names(' '.join(guards)))
            inputs = sorted({value for n in reads if (value := resolve(n, scope))})
            first = fact['eventLine']
            op = {'id': file + ':' + str(first) + ':' + output, 'routine': program['id'],
                  'output': output, 'inputs': inputs, 'expression': fact.get('value'),
                  'guards': guards, 'guardCoverage': fact.get('guardCoverage', 'unresolved'),
                  'active': assigned, 'kind': fact['kind'], 'sources': [ref(file, first)],
                  'network': fact.get('network')}
            operations.append(op)
            # A transition is a source assignment inside an explicit CASE branch.
            # Preserve the selector identity, branch guards and the source task.
            for guard in guards if op['guardCoverage'] == 'parsed' else []:
                match = re.fullmatch(r'([A-Za-z_]\w*(?:\.\w+)*) matches (.+)', guard)
                if match and resolve(match[1], scope) == output:
                    transitions.append({'id': op['id'], 'selector': output, 'from': match[2],
                                        'to': str(op['expression']), 'conditions': guards,
                                        'routine': program['id'], 'active': assigned, 'sources': op['sources']})
    calls = decode_calls(model, sources, resolve, active, ref)
    direct_active = set(active)
    for _ in range(20):
        additions = {c['implementation'] for c in calls if c['routine'] in active and not c.get('disabled') and c.get('implementation')} - active
        if not additions:break
        active.update(additions)
    for collection in (functions, calls, operations, transitions):
        for item in collection:
            routine = item['id'] if collection is functions else item['routine']
            item['active'] = routine in active and not item.get('disabled')
            item['executionContext'] = 'configured task' if routine in direct_active else 'reachable call; invocation conditions must hold' if routine in active else 'unassigned'
    writers = defaultdict(list)
    for op in operations:
        writers[op['output']].append(op)

    controls, aliases = [], []
    for page in model.get('hmi', {}).get('pages', []):
        target = PurePosixPath(page['source']).parent.parent.name
        target_active = bool(hmis and target in hmis)
        objects = page.get('objects', [])

        def captions(control):
            group = control.get('textGroup')
            entries = model.get('hmi', {}).get('textGroups', {}).get(group, {})
            props = control.get('properties', {})
            dynamic = bool(control.get('textIndexBinding'))
            offset = props.get('TextIndexOffset', props.get('TextIndex', '0'))
            try:
                offset = int(offset or 0)
            except (ValueError, TypeError):
                return [], group
            choices = []
            for index, texts in entries.items():
                try:
                    value = int(index) - offset
                except (ValueError, TypeError):
                    continue
                if not dynamic and value != 0:
                    continue
                label = texts.get('en', next(iter(texts.values()), '')) if isinstance(texts, dict) else str(texts)
                if label:
                    choices.append({'value': value if dynamic else None, 'label': label,
                                    'selector': control.get('textIndexBinding') if dynamic else None,
                                    'sources': [ref(group, line(group, 'Value="' + label + '"'))] if group else []})
            if not choices and control.get('text'):
                choices = [{'value': None, 'label': control['text'], 'selector': None, 'sources': []}]
            return choices, group

        for control in objects:
            if control.get('kind') == 'password':
                continue
            props = control.get('properties', {})
            bindings = {k: resolve(control[k]) for k in ('binding', 'textIndexBinding', 'statusBinding',
                        'minBinding', 'maxBinding', 'lockingBinding', 'visibilityBinding') if control.get(k)}
            layer = control.get('layerState', {})
            if layer.get('statusBinding'):
                bindings['layerStatusBinding'] = resolve(layer['statusBinding'])
            color = re.search(r'Variable\[Local\.([^\]]+)\]', str(props.get('ColorDatapoint', '')))
            display = resolve(color[1]) if color and str(props['ColorDatapoint']).startswith('Source[global]') else None
            if display:
                bindings['colorBinding'] = display
            choices, group = captions(control)
            file = control.get('source', page['source'])
            row = {'id': control['id'], 'page': page['name'], 'target': target, 'active': target_active,
                   'name': control['name'], 'kind': control['kind'], 'bindings': bindings,
                   'choices': choices, 'properties': {k: v for k, v in props.items() if k.endswith('Datapoint') or k in
                     {'TextGroup', 'TextIndexOffset', 'MinValue', 'MaxValue', 'Input', 'Unit', 'Locking', 'TextSource'}},
                   'sources': [ref(file, line(file, 'Name="' + control['name'] + '"'))]}
            controls.append(row)
            signal = bindings.get('binding')
            association = 'control text'
            label_control = control
            nearby = [c for c in objects if c.get('kind') == 'text' and c.get('layer') == control.get('layer')
                      and c.get('x', 0) + c.get('width', 0) <= control.get('x', 0) + 2
                      and abs((c.get('y', 0) + c.get('height', 0) / 2) -
                              (control.get('y', 0) + control.get('height', 0) / 2)) <= 4]
            display_name=None
            if signal and len(nearby)==1:
                name_choices,_=captions(nearby[0])
                if len(name_choices)==1 and name_choices[0]['selector'] is None:
                    display_name=name_choices[0]['label'];label_control=nearby[0]
                    association='unique same-row setting label; association needs review'
                    if not choices:choices=name_choices
            if display:
                # Labels are candidates only when uniquely aligned within this owning layer.
                if len(nearby) != 1:
                    continue
                label_control = nearby[0]
                choices, group = captions(label_control)
                producers = [o for o in writers[display] if o['active']]
                dependencies = {v for o in producers for v in o['inputs'] if by_id.get(v, {}).get('type') == 'BOOL'}
                # Require all two-way status writers to use a single Boolean dependency.
                if len(dependencies) != 1 or not producers or any(o['guardCoverage'] != 'parsed' for o in producers):
                    continue
                signal = next(iter(dependencies))
                association = 'unique same-row text; Boolean producer traced; label association needs review'
            if signal and choices:
                aliases.append({'id': row['id'], 'signal': signal, 'displaySignal': display,
                                'page': row['page'], 'target': target, 'active': target_active,
                                'association': association, 'choices': choices,
                                'displayName':display_name,
                                'statusBindings': {k: v for k, v in bindings.items() if 'Status' in k or k == 'statusBinding'},
                                'sources': row['sources'] + [ref(page['source'], line(page['source'], 'Name="' + label_control['name'] + '"'))] +
                                           [s for o in writers.get(display, []) for s in o['sources']]})
    from .machine_routes import routes
    hardware, interfaces = routes(model, sources, resolve, ref)
    for call in calls:
        args=call['arguments'];device=args.get('pDevice',args.get('device',''))
        candidates=[i for i in interfaces if i['device'] and re.search(r"['\"]"+re.escape(i['device'])+r"['\"]",device)]
        if len(candidates)==1:
            call['communication']={'device':candidates[0]['device'],'mode':candidates[0]['mode'],
                                   'node':args.get('node'),'index':args.get('index'),'subindex':args.get('subindex'),
                                   'sources':candidates[0]['sources'],
                                   'driveIdentity':'Requires configured node/address and payload mapping; interface presence alone is insufficient.'}
    return {'version': VERSION, 'activeConfiguration': selected or None, 'selectedHmi': hmis,
            'variables': [{'id': v['id'], 'name': v['name'], 'scope': v.get('scope'), 'type': v.get('type'),
                           'retain': v.get('retain', False), 'sources': [ref(v['source'], v.get('line', 1))]} for v in variables],
            'aliases': aliases, 'controls': controls, 'operations': operations, 'functions': functions,
            'transitions': transitions, 'hardware': hardware, 'interfaces': interfaces, 'calls': calls,
            'sourceHashes': hashes, 'issues': issues, 'completeMachineSequence': False,
            'unresolvedOperations':unresolved_operations,
            'meaning': 'Source conditions, state assignments and data dependencies; no physical timeline or device feedback inferred.'}


def select(context, question='', limit=60):
    """Return a bounded connected subgraph. Match labels without discarding selectors."""
    stop = set('the a an and or for of in to what which how why is does explain show trace generate create draw machine function functions block blocks call calls sequence flow working operation settings setting start stop starts stops please conditions condition prevent prevents from this that output on off not turning running linked connected controls doing'.split())
    wanted = words(question) - stop
    variables = {v['id']: v for v in context['variables']}
    explicit = {v['id'] for v in context['variables'] if re.search(r'(?<!\w)' + re.escape(v['name']) + r'(?!\w)', question)}
    aliases = [a for a in context['aliases'] if a['active'] and
               (not wanted or a['signal'] in explicit or (wanted and
                (wanted <= words(a.get('displayName','')) or any(wanted <= words(c['label']) for c in a['choices']))))]
    roots = explicit or ({a['signal'] for a in aliases} if wanted else set())
    # Avoid interpreting a broad question as an arbitrary first motor.
    if len(roots) > 12:
        roots = set()
    related = set(roots)
    for alias in aliases:
        related.update(c['selector'] for c in alias['choices'] if c.get('selector') in variables)
        related.update(v for v in alias.get('statusBindings',{}).values() if v in variables)
        if alias.get('displaySignal') in variables:related.add(alias['displaySignal'])
    for control in context['controls']:
        if control['active'] and any(control['bindings'].get(k) in roots for k in ('binding','textIndexBinding','colorBinding')):
            related.update(v for v in control['bindings'].values() if v in variables)
    distance={v:(0 if v in roots else 1) for v in related}
    selected_ops = {}
    for _ in range(5):
        found = [o for o in context['operations'] if o['active'] and
                 (o['output'] in related or set(o['inputs']) & related)]
        for o in found:
            selected_ops[o['id']] = o
            rank=min((distance[v] for v in [o['output'],*o['inputs']] if v in distance),default=0)+1
            for v in [o['output'],*o['inputs']]:distance.setdefault(v,rank)
        additions = {v for o in found for v in [o['output'], *o['inputs']]} - related
        if len(related | additions) > 400:
            break
        related.update(additions)
    if not roots:selected_ops={o['id']:o for o in context['operations'] if o['active']}
    def operation_rank(o):
        if o['output'] in roots:return (0,0)
        if set(o['inputs']) & roots:return (1,0)
        return (2,min((distance.get(v,99) for v in [o['output'],*o['inputs']]),default=99))
    ops = sorted(selected_ops.values(),key=operation_rank)[:limit]
    routines = {o['routine'] for o in ops}
    functions = [f for f in context['functions'] if f['active'] and
                 (not roots or f['id'] in routines)]
    matches=lambda c:bool(wanted and wanted <= words(c['name']+' '+c['instance']+' '+str(c.get('library') or '')+' '+c.get('communication',{}).get('mode','')))
    call_matches=[c for c in context['calls'] if c['active'] and matches(c)]
    calls = [c for c in context['calls'] if c['active'] and (c['routine'] in routines or c.get('instanceSignal') in roots or matches(c) or (not roots and not call_matches))]
    if not roots and call_matches:calls=call_matches
    controls = [c for c in context['controls'] if c['active'] and (not roots or set(c['bindings'].values()) & related)]
    transitions = [t for t in context['transitions'] if t['active'] and (not roots or t['selector'] in related)]
    hardware=[h for h in context['hardware'] if not roots or h.get('signal') in related]
    return {**{k: context[k] for k in ('version', 'activeConfiguration', 'selectedHmi', 'meaning', 'completeMachineSequence')},
            'query': question, 'roots': sorted(roots), 'ambiguous': len(roots) > 1,
            'callQuery':bool(call_matches and (not roots or any(c.get('instanceSignal') in roots for c in call_matches))),
            'aliases': aliases[:limit], 'variables': [variables[v] for v in sorted(related) if v in variables][:400],
            'controls': controls[:limit], 'operations': ops, 'functions': functions[:limit],
            'transitions': transitions[:limit], 'calls': calls[:limit],
            'hardware':hardware[:limit],
            'interfaces': context['interfaces'], 'issues': context['issues'][:30],
            'counts': {k: len(context[k]) for k in ('aliases', 'controls', 'operations', 'functions', 'transitions', 'calls')},
            'unresolvedOperations':context.get('unresolvedOperations',0),
            'truncated': any(len(rows) > limit for rows in (aliases,controls,selected_ops,functions,transitions,calls,hardware))}
