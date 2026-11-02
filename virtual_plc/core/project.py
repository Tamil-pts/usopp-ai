"""Read-only Virtual PLC adapter for the existing uSOPp B&R project parsers.

This module does not touch the v1.71 validator, build output or source files.
It enriches existing source symbols with runtime declarations and links the
actual CPU task assignments to their project descriptors. Execution support is
evaluated by the separate, fail-closed runtime compiler.
"""
from collections import Counter
from virtual_plc import __version__
import hashlib
import math
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET

from python_engine.project_paths import project_files, IGNORED_PROJECT_DIRS
from python_engine.project_info import local_project_details, read_active_project_hardware
from python_engine.project_knowledge import category, EXTENSIONS
from python_engine.project_analysis import _mask
from python_engine.compare import decode_project_text, parse_cpu_tasks, parse_permanent_variables
from python_engine.ladder_requirements import fragment
from python_engine.ladder_model import network_model
from backend.core.project_intelligence import Index
from .hardware import read_hardware, tag
from .hmi import read_hmi

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 80 * 1024 * 1024
MAX_FILES = 15000
MAX_DIAGNOSTICS = 1000
MAX_REFERENCES = 100000
EXCLUDED = IGNORED_PROJECT_DIRS | {'cache', 'generated', 'generatedcode', 'debug', 'release', 'dbk', '.idea', '.vs', '.vscode'}
RELEVANT = EXTENSIONS | {'.prg', '.pkg', '.vc', '.vcp', '.dob', '.dat', '.vcvk', '.vcr', '.vcs', '.fninfo'}
LANGUAGES = {'.st': 'st', '.ld': 'ld', '.ab': 'ab', '.src': 'ab', '.c': 'c', '.h': 'c', '.fun': 'st'}


def _check(cancel):
    if cancel is not None and cancel.is_set():
        raise InterruptedError('Virtual PLC project analysis cancelled.')


def _line(text, position):
    return text.count('\n', 0, position) + 1


def _pragmas(text):
    """B&R declaration attributes are not symbols; keep byte/line positions."""
    return re.sub(r'\{[^}]*\}', lambda match: ''.join('\n' if char == '\n' else ' ' for char in match[0]), text)


def _literal(value):
    value = value.strip()
    if value.casefold() in {'true', 'false'}:
        return value.casefold() == 'true'
    if re.fullmatch(r'[+-]?\d+', value):
        return int(value)
    if re.fullmatch(r'[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[Ee][+-]?\d+)?', value):
        number = float(value)
        if math.isfinite(number):
            return number
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    # Time literals, array initializers and expressions remain IEC source text.
    return value


def _type_spec(expression):
    expression = re.sub(r'\{[^}]*\}', '', expression).strip()
    array = re.fullmatch(r'ARRAY\s*\[([^]]+)\]\s+OF\s+(.+)', expression, re.I | re.S)
    if array:
        bounds = []
        for dimension in array[1].split(','):
            interval = re.fullmatch(r'\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*', dimension)
            if not interval:
                return {'kind': 'unresolved', 'declaration': expression,
                        'message': 'Symbolic array bounds require constant resolution.'}
            bounds.append([int(interval[1]), int(interval[2])])
        return {'kind': 'array', 'bounds': bounds, 'elementType': array[2].strip()}
    enum = re.fullmatch(r'\((.*)\)', expression, re.S)
    if enum:
        values, next_value = {}, 0
        for member in enum[1].split(','):
            match = re.fullmatch(r'\s*([A-Za-z_]\w*)\s*(?::=\s*(-?\d+))?\s*', member)
            if not match:
                return {'kind': 'unresolved', 'declaration': expression,
                        'message': 'Enum expression could not be resolved to integer values.'}
            next_value = int(match[2]) if match[2] is not None else next_value
            values[match[1]] = next_value
            next_value += 1
        return {'kind': 'enum', 'values': values}
    return {'kind': 'alias', 'type': expression}


def _types(text, source):
    clean = _mask(text)
    result = {}
    struct_ranges = []
    for match in re.finditer(r'(?im)^\s*([A-Za-z_]\w*)\s*:\s*STRUCT\b(.*?)\bEND_STRUCT\s*;', clean, re.S):
        fields = []
        for field in re.finditer(r'([A-Za-z_]\w*)\s*:\s*([^;]+);', match[2]):
            expression, _, initial = field[2].partition(':=')
            record = {'name': field[1], 'type': re.sub(r'\{[^}]*\}', '', expression).strip()}
            if initial:
                record['initial'] = _literal(initial)
            fields.append(record)
        result[match[1]] = {'kind': 'struct', 'fields': fields, 'source': source,
                            'line': _line(clean, match.start(1))}
        struct_ranges.append((match.start(), match.end()))
    for match in re.finditer(r'(?im)^\s*([A-Za-z_]\w*)\s*:\s*([^;]+);', clean):
        if any(first <= match.start() < last for first, last in struct_ranges):
            continue
        result[match[1]] = {**_type_spec(match[2]), 'source': source, 'line': _line(clean, match.start(1))}
    return result


def _declaration_metadata(text, line, name, context=None):
    """Enrich a symbol already extracted by Index.parse; do not re-decode it."""
    lines = context['lines'] if context else _mask(text).splitlines()
    declaration = lines[line - 1] if 0 < line <= len(lines) else ''
    initial_match = re.search(r':=\s*(.+?);', declaration)
    result = {'initial': _literal(initial_match[1]) if initial_match else None,
              'retain': False, 'constant': False, 'direction': 'local'}
    block = context['blocks'].get(line) if context else None
    if context is None:
        blocks = list(re.finditer(r'\b(VAR(?:_GLOBAL|_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL)?|END_VAR)\b([^\n]*)', '\n'.join(lines[:line]), re.I))
        block = (blocks[-1][1], blocks[-1][2]) if blocks else None
    if block and block[0].upper() != 'END_VAR':
        result['retain'] = bool(re.search(r'\bRETAIN\b', block[1], re.I))
        result['constant'] = bool(re.search(r'\bCONSTANT\b', block[1], re.I))
        result['direction'] = {'VAR_INPUT': 'input', 'VAR_OUTPUT': 'output', 'VAR_IN_OUT': 'inout',
                               'VAR_EXTERNAL': 'external', 'VAR_TEMP': 'temporary'}.get(block[0].upper(), 'local')
    address = re.search(r'\b' + re.escape(name) + r'\s+AT\s+([^:;]+)', declaration, re.I)
    if address:
        result['address'] = address[1].strip()
    return result


def _declaration_context(text):
    lines = _mask(text).splitlines()
    blocks, current = {}, None
    for number, line in enumerate(lines, 1):
        match = re.search(r'\b(VAR(?:_GLOBAL|_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL)?|END_VAR)\b(.*)', line, re.I)
        if match:
            current = (match[1], match[2])
        blocks[number] = current
    return {'lines': lines, 'blocks': blocks}


def upgrade_symbol_model(model, sources):
    """Restore case-distinct declarations from the private source snapshot.

    No original project writes, source changes, task changes or reindexing.
    Return an explicit old identity -> new identity map for saved UI bindings.
    """
    if model.get('symbolCaseSensitive') is True:
        return {}
    root = Path(model['root'])
    parser = object.__new__(Index)
    parser.root = root
    variables, declared, notices = [], {}, []
    old = {(v['scope'], v['name']): v for v in model.get('variables', [])}
    remap = {}
    for source, text in sources.items():
        if not _configuration_path(source, model.get('projectInfo', {}).get('activeConfiguration')):
            continue
        suffix = Path(source).suffix.casefold()
        if suffix not in {'.var', '.st', '.ab', '.src', '.c', '.h', '.ld', '.prg'}:
            continue
        parsed = _pragmas(text) if suffix in {'.var', '.fun', '.st', '.ab', '.src'} else text
        _, symbols, _, _, _, _ = parser.parse(root / source, parsed)
        context = _declaration_context(text)
        for _, name, kind, dtype, _, line, scope in symbols:
            if kind != 'variable':
                continue
            if scope.startswith('@global/'):
                scope = '@global'
            identity = f'{scope}:{name}'
            if identity in declared:
                first = declared[identity]
                first['ambiguous'] = True
                notices.append({'severity': 'error', 'code': 'variable-conflict', 'source': source, 'line': line,
                                'message': f'Duplicate exact declaration {name}: {first["source"]}:{first["line"]} and {source}:{line}.'})
                continue
            item = {'id': identity, 'name': name, 'type': re.sub(r'\{[^}]*\}', '', dtype).strip(),
                    'scope': scope, 'source': source, 'line': line, **_declaration_metadata(text, line, name, context)}
            previous = old.get((scope, name))
            if previous:
                remap[previous['id']] = identity
                for field in ('retain', 'address'):
                    if field in previous: item[field] = previous[field]
            variables.append(item)
            declared[identity] = item
    if not variables and model.get('variables'):
        raise ValueError('Cached declarations are incomplete; refresh the original project before upgrading symbol identities.')
    model['variables'] = variables
    model['symbolCaseSensitive'] = True
    model['diagnostics'] = [d for d in model.get('diagnostics', []) if d.get('code') != 'variable-conflict'] + notices
    model.setdefault('statistics', {})['variables'] = len(variables)
    lookup = {v['name']: v for v in variables if v['scope'] == '@global'}
    for channel in model.get('hardware', {}).get('channels', []):
        variable = lookup.get(channel.get('variable', '').split('.', 1)[0])
        if variable: channel.update(variableId=variable['id'], type=variable['type'])
    return remap


def _entry(source, text):
    clean = _mask(text)
    if re.search(r'\b(?:PROGRAM\s+_?CYCLIC|void\s+_CYCLIC)\b', clean, re.I):
        # A combined source can hold every lifecycle section. Keep its cyclic
        # entry discoverable while the task adapter preserves the other phases.
        return 'cyclic'
    match = re.search(r'(?im)^\s*(?:PROGRAM|void\s+_?(?:INIT|CYCLIC|EXIT))\s*([A-Za-z_]\w*)?', clean)
    identity = ' '.join([Path(source).stem, match[0] if match else '']).casefold()
    if re.search(r'(?:_init\b|init$)', identity):
        return 'init'
    if re.search(r'(?:_exit\b|exit$)', identity):
        return 'exit'
    return 'cyclic'


def _entries(source,text):
    names=re.findall(r'\b(?:PROGRAM\s+|void\s+)(_?(?:INIT|CYCLIC|EXIT))\b',_mask(text),re.I)
    return list(dict.fromkeys(name.lstrip('_').lower() for name in names)) or [_entry(source,text)]


def upgrade_lifecycle(model):
    from .lifecycle import schedule_entries
    phases={}
    for program in model.get('programs',[]):
        entries=_entries(program.get('source',''),program.get('code',''))
        program['entryPoints']=entries
        program['entry']='cyclic' if 'cyclic' in entries else entries[0]
        phases[program['id']]=entries
    for task in model.get('tasks',[]):schedule_entries(task,phases)
    model['lifecycleAdapterVersion']=1


def _configuration_path(source, selected):
    parts = Path(source).parts
    if not parts or parts[0].casefold() != 'physical':
        return True
    return len(parts) > 1 and selected is not None and parts[1].casefold() == str(selected).casefold()


def _resolve_programs(name, task_source, descriptors, programs):
    if not str(task_source).strip():
        return []  # An empty configuration slot must never select unrelated code.
    source_folder = task_source.removesuffix('.prg').replace('.', '/').strip('/').casefold()
    expected = 'logical/' + source_folder
    choices = [path for path in descriptors if Path(path).parent.as_posix().casefold() == expected]
    if not choices:
        # An IEC.prg descriptor lives in the source object's folder. No global
        # basename fallback: duplicate task names in different packages are common.
        choices = [path for path in descriptors if Path(path).as_posix().casefold() == 'logical/' + task_source.casefold()]
    ids = []
    if len(choices) == 1:
        ids = descriptors[choices[0]]
    elif not choices:
        ids = [p['id'] for p in programs if p['scope'] == expected and p.get('kind') == 'program']
        if not ids:
            ids = [p['id'] for p in programs if p['source'].casefold() == 'logical/' + task_source.casefold()]
    return ids


def _tasks(sources, configuration, descriptors, programs, hardware, diagnostics):
    tasks = []
    by_id = {p['id']: p for p in programs}
    for source, text in sources.items():
        if Path(source).name.casefold() != 'cpu.sw' or not _configuration_path(source, configuration):
            continue
        try:
            tree = ET.fromstring(text)
        except ET.ParseError as error:
            diagnostics.append({'severity': 'error', 'code': 'tasks-unresolved', 'source': source, 'message': str(error)})
            continue
        decoded = parse_cpu_tasks(text)
        for node in tree.iter():
            if tag(node) != 'taskclass':
                continue
            class_name = node.get('Name', '')
            cyclic = bool(re.match(r'^Cyclic#\d+$', class_name, re.I))
            controller_name = Path(source).parent.name.casefold()
            controller_intervals = hardware.get('taskIntervalsByController', {}).get(controller_name)
            if controller_intervals is None and len(hardware.get('controllers', [])) == 1:
                controller_intervals = hardware.get('taskIntervals', {})
            interval = (controller_intervals or {}).get(class_name.casefold())
            # Explicit task-class timing attributes are accepted only with units.
            if interval is None and node.get('CycleTime'):
                value = node.get('CycleTime', '')
                unit = node.get('Unit', '').casefold()
                try:
                    interval = float(value) * {'us': .001, 'ms': 1, 's': 1000}[unit]
                except (KeyError, ValueError):
                    pass
            task = {'id': f'{source}:{class_name}', 'name': class_name,
                    'kind': 'cyclic' if cyclic else 'event', 'intervalMs': interval,
                    'priority': int(class_name.split('#')[1]) if cyclic else None,
                    'programs': [], 'initializationPrograms': [], 'exitPrograms': [],
                    'assignments': [], 'enabled': True, 'source': source,
                    'configuration': configuration, 'controller': Path(source).parent.name,
                    'line': next((n for n, line in enumerate(text.splitlines(), 1)
                                                                if '<TaskClass ' in line and f'Name="{class_name}"' in line), 1)}
            for index, child in enumerate(node):
                if tag(child) != 'task':
                    continue
                name = child.get('Name', '')
                properties = decoded.get(name, {}).get('properties', {})
                enabled = properties.get('Disabled', child.get('Disabled', 'false')).casefold() != 'true'
                task_source = properties.get('Source', child.get('Source', ''))
                resolved = _resolve_programs(name, task_source, descriptors, programs)
                assignment = {'name': name, 'source': task_source, 'order': index, 'enabled': enabled,
                              'programs': resolved, 'resolved': bool(resolved),
                              'line': next((n for n, line in enumerate(text.splitlines(), 1)
                                            if '<Task ' in line and f'Name="{name}"' in line), task['line'])}
                placeholder = not str(task_source).strip() and not resolved
                if placeholder:
                    assignment.update(placeholder=True, executable=False,
                                      skipReason='Unassigned task slot: Source is explicitly empty in this configuration.')
                task['assignments'].append(assignment)
                if placeholder and enabled:
                    diagnostics.append({'severity': 'info', 'code': 'task-placeholder', 'source': source,
                                        'line': assignment['line'], 'message': f'{class_name}: {name} is an unassigned task slot (empty Source); no code is scheduled.'})
                if not resolved and enabled and not placeholder:
                    diagnostics.append({'severity': 'error', 'code': 'program-unresolved', 'source': source,
                                        'line': assignment['line'], 'message': f'{class_name}: {name} source {task_source} could not be resolved uniquely.'})
                if enabled:
                    for program_id in resolved:
                        program = by_id[program_id]
                        program.setdefault('tasks', []).append(task['id'])
                        for entry in _entries(program['source'],program.get('code','')):
                            key = {'init': 'initializationPrograms', 'exit': 'exitPrograms'}.get(entry, 'programs')
                            task[key].append(program_id)
            if task['assignments'] and cyclic and interval is None:
                diagnostics.append({'severity': 'error', 'code': 'task-interval-unresolved', 'source': source,
                                    'line': task['line'], 'message': f'{class_name}: cycle interval is absent from selected hardware; execution requires an explicit correction.'})
            tasks.append(task)
    if not tasks:
        diagnostics.append({'severity': 'error', 'code': 'tasks-unresolved',
                            'message': 'No active CPU.sw task configuration was resolved. Program ownership and scheduling remain unavailable.'})
    return tasks


def upgrade_task_slots(model):
    placeholders = set()
    for task in model.get('tasks', []):
        for assignment in task.get('assignments', []):
            if not str(assignment.get('source') or '').strip() and not assignment.get('programs'):
                assignment.update(placeholder=True, executable=False, skipReason='Unassigned task slot: empty Source in this configuration.')
                placeholders.add((task.get('source'), assignment.get('line'), assignment.get('name')))
    for diagnostic in model.get('diagnostics', []):
        if diagnostic.get('code') == 'program-unresolved' and any(diagnostic.get('source') == source and diagnostic.get('line') == line and name in diagnostic.get('message','') for source,line,name in placeholders):
            diagnostic.update(severity='info',code='task-placeholder',message='Unassigned task slot: Source is empty in this configuration; no code is scheduled.')
    model['taskAdapterVersion'] = 2


def analyze_project(root, progress=None, cancel=None, configuration=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('Select an existing project directory.')
    started = time.monotonic()
    _check(cancel)
    details = local_project_details(root)
    diagnostics = []
    if configuration is not None:
        if configuration in {'.', '..'} or any(char in str(configuration) for char in '/\\:'):
            raise ValueError('Configuration must be a project configuration name.')
        configured = root / 'Physical' / str(configuration)
        if not configured.is_dir():
            raise ValueError('The requested physical configuration does not exist in this project.')
        details.update(activeConfiguration=configuration, configurationStatus='selected',
                       **read_active_project_hardware(root, str(configuration)))
    selected = details.get('activeConfiguration')
    if not selected:
        diagnostics.append({'severity': 'error', 'code': 'configuration-unresolved',
                            'message': details.get('configurationMessage', 'Active physical configuration is unknown.')})
    def publish(stage, current=0, total=0):
        if progress:
            progress({'stage': stage, 'percentage': int(current * 100 / total) if total else None,
                      'totalFiles': total, 'indexedFiles': current,
                      'failedFiles': len({d.get('source') for d in diagnostics
                                          if d.get('source') and d.get('code') in {'source-bound', 'source-unreadable', 'resource-parse-failed'}}),
                      'elapsedSeconds': round(time.monotonic() - started, 2)})
    publish('Discovering supported project resources')
    candidates = []
    discovered = 0
    for path in project_files(root, EXCLUDED):
        _check(cancel)
        discovered += 1
        if path.suffix.casefold() in RELEVANT:
            candidates.append(path)
            if len(candidates) > MAX_FILES:
                raise ValueError(f'Project has more than {MAX_FILES} relevant source files; split the project before simulation.')
    candidates.sort(key=lambda path: path.relative_to(root).as_posix().casefold())
    sources, manifest, budget = {}, [], 0
    for number, path in enumerate(candidates, 1):
        _check(cancel)
        relative = path.relative_to(root).as_posix()
        try:
            size = path.stat().st_size
            if size > MAX_FILE_BYTES or budget + size > MAX_SOURCE_BYTES:
                diagnostics.append({'severity': 'error', 'code': 'source-bound', 'source': relative,
                                    'message': 'Source exceeds the bounded project memory budget; it was excluded from execution.'})
                manifest.append({'path': relative, 'kind': category(path), 'language': LANGUAGES.get(path.suffix.casefold()),
                                 'size': size, 'sha256': None, 'status': 'excluded-size'})
                continue
            raw = path.read_bytes()
            budget += len(raw)
            text = raw.decode('latin-1') if path.suffix.casefold()=='.dat' else decode_project_text(path, raw).replace('\x00', '')
            manifest.append({'path': relative, 'kind': category(path), 'language': LANGUAGES.get(path.suffix.casefold()),
                             'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'status': 'read'})
            # Preserve nonselected paths in explorer; never mix physical targets.
            if _configuration_path(relative, selected):
                sources[relative] = text
        except (OSError, UnicodeError, ValueError) as error:
            diagnostics.append({'severity': 'error', 'code': 'source-unreadable', 'source': relative, 'message': str(error)})
        if number == 1 or number % 50 == 0 or number == len(candidates):
            publish('Reading source files', number, len(candidates))
    _check(cancel)
    hardware = read_hardware(sources, selected, diagnostics)
    if len(hardware['controllers']) == 1:
        # The shared identity reader can encounter an empty .hwl editor sidecar
        # first; retain its identity fields and enrich its CPU from real .hw XML.
        details['plcType'] = hardware['controllers'][0]['model']
    programs, variables, types, interfaces, dependencies, references = [], [], {}, [], [], []
    # Index.parse is the existing stateless extraction stage. Construct no
    # second database and do not invoke Index.build or any validation engine.
    parser = object.__new__(Index)
    parser.root = root
    descriptors = {}
    declared = {}
    for number, (source, text) in enumerate(sources.items(), 1):
        _check(cancel)
        suffix = Path(source).suffix.casefold()
        path = root / source
        scope = Path(source).parent.as_posix().casefold()
        try:
            if suffix in {'.var', '.typ', '.fun', '.st', '.ab', '.src', '.c', '.h', '.ld', '.prg'}:
                parse_text = _pragmas(text) if suffix in {'.fun', '.var', '.typ', '.st', '.ab', '.src'} else text
                _, symbols, refs, edges, _, notices = parser.parse(path, parse_text)
                declaration_context = _declaration_context(text)
                for notice in notices:
                    diagnostics.append({'severity': 'warning', 'code': 'source-analysis-bound', 'source': source, 'message': notice})
                if len(references) < MAX_REFERENCES:
                    references.extend({'name': row[0], 'source': row[1], 'line': row[2], 'role': row[3], 'scope': row[4]}
                                      for row in refs[:MAX_REFERENCES-len(references)])
                if len(dependencies) < MAX_REFERENCES:
                    dependencies.extend({'from': row[0], 'to': row[1], 'kind': row[2], 'source': row[3],
                                         'line': row[4], 'scope': row[5], 'detail': row[6]}
                                        for row in edges[:MAX_REFERENCES-len(dependencies)])
                if suffix not in {'.typ', '.fun'}:
                    for _, name, kind, dtype, _, line, symbol_scope in symbols:
                        if kind != 'variable':
                            continue
                        if symbol_scope.startswith('@global/'):
                            symbol_scope = '@global'
                        # Automation Studio compliance list 2-1: aBcD != ABcD.
                        identity = f'{symbol_scope}:{name}'
                        if identity in declared:
                            declared[identity]['ambiguous'] = True
                            declared[identity].setdefault('conflictingDeclarations', []).append(
                                {'name': name, 'type': re.sub(r'\{[^}]*\}', '', dtype).strip(),
                                 'source': source, 'line': line})
                            first = declared[identity]
                            diagnostics.append({'severity': 'error', 'code': 'variable-conflict', 'source': source,
                                                'line': line, 'related': [{'source': first['source'], 'line': first['line'], 'type': first['type']}],
                                                'message': f'Duplicate exact declaration of {name} in {symbol_scope}: '
                                                f'{first["type"]} at {first["source"]}:{first["line"]}; {dtype} at {source}:{line}.'})
                            continue
                        dtype = re.sub(r'\{[^}]*\}', '', dtype).strip()
                        variable = {'id': identity, 'name': name, 'type': dtype, 'scope': symbol_scope,
                                    'source': source, 'line': line, **_declaration_metadata(text, line, name, declaration_context)}
                        variables.append(variable)
                        declared[identity] = variable
            if suffix == '.typ':
                for name, spec in _types(text, source).items():
                    # Scoped types retain their qualified identity as well as a
                    # unique short alias. Duplicate short names become unresolved.
                    qualified = f'{scope}:{name}'
                    types[qualified] = spec
                    if name in types and types[name] != spec:
                        types[name] = {'kind': 'unresolved', 'message': 'Multiple scoped definitions require qualified type selection.'}
                    else:
                        types[name] = spec
            if suffix in {'.st', '.ab', '.src', '.c', '.ld'}:
                header = re.search(r'(?im)^\s*(FUNCTION_BLOCK|FUNCTION)\s+([A-Za-z_]\w*)', _mask(_pragmas(text)))
                programs.append({'id': source, 'name': header[2] if header else path.stem,
                                 'scope': scope + '/' + header[2].casefold() if header else scope, 'language': LANGUAGES[suffix], 'source': source, 'code': text,
                                 'kind': {'FUNCTION': 'function', 'FUNCTION_BLOCK': 'functionblock'}.get(header[1].upper(), 'program') if header else 'program',
                                 'entry': _entry(source, text), 'line': 1,
                                 **({'networks': [network_model(node, index) for index, node in enumerate(fragment(text), 1)]} if suffix == '.ld' else {})})
            if suffix == '.fun':
                clean = _mask(_pragmas(text))
                for match in re.finditer(r'(?im)^\s*(FUNCTION_BLOCK|FUNCTION)\s+([A-Za-z_]\w*)\b', clean):
                    end = re.search(r'\bEND_' + match[1] + r'\b', clean[match.end():], re.I)
                    last = match.end() + end.end() if end else len(text)
                    body = text[match.start():last]
                    interfaces.append({'name': match[2], 'kind': match[1].casefold(), 'source': source,
                                       'line': _line(text, match.start()), 'declaration': body,
                                       'scope': scope + '/' + match[2].casefold(),
                                       'implemented': False})
            if suffix == '.prg' and text.lstrip().startswith('<'):
                tree = ET.fromstring(text)
                listed = []
                for node in tree.iter():
                    if tag(node) != 'file' or not (node.text or '').strip():
                        continue
                    target = (path.parent / node.text.strip()).resolve()
                    if not target.is_relative_to(root):
                        diagnostics.append({'severity': 'error', 'code': 'external-source', 'source': source,
                                            'message': 'Program descriptor references a file outside the imported project.'})
                        continue
                    relative = target.relative_to(root).as_posix()
                    if target.suffix.casefold() in LANGUAGES and target.suffix.casefold() not in {'.h', '.fun'}:
                        if relative in sources:
                            listed.append(relative)
                        else:
                            diagnostics.append({'severity': 'error', 'code': 'program-file-missing', 'source': source,
                                                'message': f'Program descriptor source {relative} is absent or excluded.'})
                descriptors[source] = listed
        except (ET.ParseError, ValueError, KeyError, TypeError) as error:
            diagnostics.append({'severity': 'error', 'code': 'resource-parse-failed', 'source': source, 'message': str(error)})
        if number == 1 or number % 50 == 0 or number == len(sources):
            publish('Linking declarations and executable resources', number, len(sources))
    from .c_declarations import merge as merge_c_declarations
    declaration_model={'variables':variables,'types':types,'diagnostics':diagnostics,'projectInfo':{'activeConfiguration':selected}}
    merge_c_declarations(declaration_model,sources)
    for program in programs:
        if program['kind'] not in {'function', 'functionblock'}:
            continue
        choices = [interface for interface in interfaces
                   if interface['name'].casefold() == program['name'].casefold()
                   and Path(interface['source']).parent == Path(program['source']).parent]
        if len(choices) == 1:
            program['interface'] = choices[0]
            choices[0]['implemented'] = True
            choices[0]['implementationSource'] = program['source']
    # .per carries retention independently of the declaration's VAR block.
    retained = {name: record['properties']['Address'] for source, text in sources.items()
                if Path(source).suffix.casefold() == '.per' for name, record in parse_permanent_variables(text).items()}
    for variable in variables:
        if variable['scope'] == '@global' and variable['name'] in retained:
            variable.update(retain=True, address=retained[variable['name']])
    task_rows = _tasks(sources, selected, descriptors, programs, hardware, diagnostics)
    from .io_bindings import connect_io
    connect_io(hardware, variables, task_rows)
    publish('Resolving HMI pages against PLC memory')
    hmi = read_hmi(root, sources, diagnostics, cancel, variables=variables)
    if len(references) >= MAX_REFERENCES or len(dependencies) >= MAX_REFERENCES:
        diagnostics.append({'severity': 'warning', 'code': 'references-bound',
                            'message': 'Model reference preview is bounded; complete references remain in the existing SQLite project intelligence index.'})
    model = {'schemaVersion': 1, 'moduleVersion': __version__, 'symbolCaseSensitive': True,
             'declarationAdapterVersion': 4, 'taskAdapterVersion': 2, 'name': details.get('projectName', root.name),
             'root': str(root), 'projectInfo': details, 'files': manifest, 'hardware': hardware,
             'tasks': task_rows, 'variables': variables, 'types': types, 'programs': programs,
             'interfaces': interfaces, 'functions': [p for p in programs if p['kind'] in {'function', 'functionblock'}],
             'hmi': hmi, 'dependencies': dependencies, 'references': references,
             'diagnostics': diagnostics[:MAX_DIAGNOSTICS],
             'diagnosticCount': len(diagnostics), 'diagnosticsTruncated': len(diagnostics) > MAX_DIAGNOSTICS,
             'statistics': {'discoveredFiles': discovered, 'relevantFiles': len(manifest), 'readBytes': budget,
                            'programs': len(programs), 'variables': len(variables), 'types': len(types),
                            'tasks': len(task_rows), 'hmiPages': len(hmi['pages']),
                            'interfaces': len(interfaces),
                            'sourceKinds': dict(Counter(item['kind'] for item in manifest)),
                            'elapsedSeconds': round(time.monotonic() - started, 3)},
             'readOnlySource': True,
             'reuse': ['python_engine.project_info.local_project_details', 'python_engine.project_paths.project_files',
                       'backend.core.project_intelligence.Index.parse', 'python_engine.compare.parse_cpu_tasks',
                       'python_engine.compare.parse_hardware_modules', 'python_engine.compare.parse_io_mappings',
                       'python_engine.compare.hmi_screen_layout', 'python_engine.ladder_model.network_model']}
    publish('Linking machine names, settings, drive calls and source sequences')
    from .machine_identity import build as build_machine_identity
    model['machineContext'] = build_machine_identity(model, sources)
    publish('Project model ready for compatibility compilation', len(sources), len(sources))
    return model
