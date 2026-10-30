"""Question plans and source-proved output traces; no probabilistic PLC facts.

The persistent machine model remains project-wide. A question result is scoped
to actual writers and their dependencies. HMI references never prove a rung.
"""
from collections import deque
from pathlib import Path
import re

from backend.core.project_intelligence import connection
from python_engine.compare import decode_project_text, _ladder_networks
from python_engine.ladder_model import coil_condition
from python_engine.function_flow import _names

STOP = set('what which how why the a an are is does do before after required conditions start starts stop stops not on off turning turns moving motor output signal plc please explain trace show can'.split())


def words(value):
    value = re.sub(r'([a-z])([A-Z])', r'\1 \2', value)
    return set(re.findall(r'[a-z0-9]+', value.casefold()))


def plan(question, machine):
    from backend.core.engineering_analysis import broad_question
    if broad_question(question): return {'kind': 'whole-machine', 'candidates': []}
    if re.search(r'\bhmi\b|screen|binding|physical.*(?:io|i/o)|hardware.*mapping', question, re.I):
        kind = 'mapping'
    elif re.search(r'\b(?:sequence|flowchart|process)\b|explain.*\b(?:doffing|function)\b', question, re.I):
        kind = 'function-sequence'
    elif re.search(r'\b(?:why|fault|alarm|troubleshoot|not moving|not turning)\b', question, re.I):
        kind = 'troubleshooting'
    else: kind = 'output-trace'
    names = set(row['name'] for row in machine.get('signalWrites', []) if row.get('name'))
    identifiers = re.findall(r'\b[A-Za-z_]\w*(?:\.\w+)*\b', question)
    explicit = [name for name in names if name in identifiers]
    if not explicit:
        folded = {token.casefold() for token in identifiers if '_' in token or any(c.isdigit() for c in token)}
        explicit = [name for name in names if name.casefold() in folded]
    candidates = sorted(explicit)
    terms = words(question) - STOP
    if not candidates and kind in {'output-trace', 'troubleshooting'}:
        # Require every descriptive term. A generic motor question is ambiguous
        # across all writer-backed motor symbols, rather than a top-1 guess.
        terms.discard('changer' if 'changing' in terms else 'changing')
        wanted = terms or ({'motor'} if 'motor' in words(question) else set())
        candidates = sorted(name for name in names if wanted and wanted <= words(name))
        if 'motor' in words(question): candidates = [name for name in candidates if 'motor' in words(name)]
    resolution = None
    if len(candidates) > 1 and kind in {'output-trace', 'troubleshooting'}:
        physical = [name for name in candidates if any(h.get('variable', '').casefold() == name.casefold()
                    and h.get('ownership') == 'active configuration' and str(h.get('address', '')).startswith('%Q')
                    for h in machine.get('hardwareLinks', []))]
        if len(physical) == 1:
            resolution = {'basis': 'Unique output mapped to physical %Q in the active configuration',
                          'alternatives': [name for name in candidates if name != physical[0]]}
            candidates = physical
    if kind == 'mapping':
        candidates = sorted({row['signal'] for row in machine.get('hmiLinks', [])
                             if row.get('signal') and (row['signal'].casefold() in question.casefold() or
                                (terms and terms <= words(row['signal'])))})
    if kind == 'function-sequence': candidates = []
    return {'kind': kind, 'candidates': candidates, 'terms': sorted(terms),
            'ambiguous': len(candidates) > 1, 'resolution': resolution}


class Trace:
    def __init__(self, index, machine):
        self.index, self.machine = index, machine
        self.sources, self.files, self.networks = [], {}, {}
        self.proofs, self.unresolved = [], []
        with connection(index.path) as db:
            self.declarations = [dict(row) for row in db.execute('SELECT display,scope,file,datatype FROM symbols WHERE kind IN (\'variable\',\'instance\')')]
            self.write_refs = [dict(row) for row in db.execute("SELECT DISTINCT name,file,line FROM refs WHERE kind='write'")]

    def text(self, file):
        if file not in self.files:
            check = self.index.source_excerpt(file, 1, 0)
            if check['freshness'] != 'matches indexed source':
                # Compare explicit hashes: freshness is user-facing prose.
                if check.get('indexedSha') != check.get('currentSha'):
                    raise ValueError('Source changed since indexing: ' + file)
            path = self.index.root / file
            self.files[file] = decode_project_text(path, path.read_bytes()).replace('\r\n', '\n').replace('\r', '')
        return self.files[file]

    def source(self, file, first, last, kind='controlling source'):
        text = self.text(file); lines = text.splitlines()
        first, last = max(1, first), min(len(lines), last)
        existing = next((item for item in self.sources if item['file'] == file and item['line'] == first and item['endLine'] == last), None)
        if existing: return existing['sourceId']
        item = {'id': 'Q' + str(len(self.sources) + 1), 'sourceId': 'S' + str(len(self.sources) + 1),
                'file': file, 'line': first, 'endLine': last, 'excerpt': '\n'.join(lines[first-1:last]),
                'type': kind, 'ownership': 'question-relevant indexed source', 'status': 'verified source location',
                'completeSection': True, 'sourceType': 'project'}
        self.sources.append(item)
        return item['sourceId']

    def writers(self, name, origin=None):
        rows = [row for row in self.machine.get('signalWrites', []) if row['name'] == name]
        # Do not merge same-spelled local symbols across programs/libraries.
        def scope_for(file):
            folder = str(Path(file).parent).replace('\\', '/').casefold()
            local = [row['scope'] for row in self.declarations if row['display'] == name and not row['scope'].startswith('@global/')
                     and (folder == row['scope'] or folder.startswith(row['scope'] + '/'))]
            return max(local, key=len) if local else '@global'
        if origin:
            scope = scope_for(origin)
            rows = [row for row in rows if scope_for(row['file']) == scope]
        elif len({scope_for(row['file']) for row in rows}) > 1:
            self.unresolved.append(name + ': same-named writers in different local/global scopes; select a routine.')
            return []
        return rows

    def writer(self, row, depth):
        file, line, name = row['file'], row['line'], row['name']
        result = {**row, 'depth': depth, 'resolved': False, 'inputs': []}
        try:
            text = self.text(file)
            if row.get('network'):
                if file not in self.networks: self.networks[file] = _ladder_networks(text)
                network = next(n for n in self.networks[file] if n['index'] == row['network'])
                matches = list(re.finditer(r'<network\b[^>]*>.*?</network\s*>', text, re.I | re.S))
                raw = matches[row['network']-1]; first = text.count('\n', 0, raw.start())+1
                last = first + raw[0].count('\n')
                result.update(coil_condition(network['diagram'], name))
                result['sourceId'] = self.source(file, first, last, 'complete ladder network')
                result['line'], result['endLine'] = first, last
                coil = re.search(r'<coil\b[^>]*\bname=[\"\']' + re.escape(name) + r'[\"\']', raw[0])
                result['coilLine'] = first + raw[0][:coil.start()].count('\n') if coil else first
            else:
                # Guards are from the common whole-file ST/AB/C IR, not a
                # context window. Match the actual assignment before using it.
                from python_engine.working_sequence import records, ASSIGNMENT
                if Path(file).suffix.casefold() == '.c':
                    from python_engine.c_control_flow import c_flow
                    parts, _, _, notices = c_flow(text, file)
                else:
                    from python_engine.function_flow import _text_flow
                    parts, _, _, notices = _text_flow(text, file, Path(file).suffix.casefold() == '.ab')
                found = None
                for part in parts:
                    for record in records(part['nodes']):
                        assignment = ASSIGNMENT.match(record['row']['code'])
                        if assignment and assignment[1] == name and record['row']['line'] == line and assignment[2].strip() == str(row.get('value', '')).strip() and record['guards'] == row.get('guards', []):
                            found = record; break
                    if found: break
                if not found: raise ValueError('Assignment could not be re-established by the whole-file parser.')
                guards = found['guards']; value = row.get('value')
                first = min([line, *found.get('guardLines', [])]); last = found['row'].get('endLine', line)
                # ELSE/ELSIF guards include negated preceding branches. Include
                # their controlling node, not an excerpt starting at ELSE.
                ancestors = [node for node in part['nodes'] if node['line'] <= line <= node.get('endLine', node['line'])]
                if ancestors:
                    first = min(first, *(node['line'] for node in ancestors))
                    last = max(last, *(node.get('endLine', node['line']) for node in ancestors))
                result.update(resolved=not notices, expression=' AND '.join('(' + guard + ')' for guard in guards) or 'TRUE',
                              inputs=list(dict.fromkeys(_names(' '.join([*guards, str(value)])))),
                              sourceId=self.source(file, first, last, 'assignment and enclosing conditions'),
                              reason='; '.join(notices) if notices else '', section=part['name'])
            if not result['resolved']: self.unresolved.append(f"{name} at {file}:{line}: {result.get('reason', 'condition unresolved')}")
        except (OSError, ValueError, KeyError, StopIteration) as error:
            result['reason'] = str(error); self.unresolved.append(f'{name} at {file}:{line}: {error}')
        self.proofs.append(result)
        return result

    def walk(self, name):
        pending = deque([(name, None, 0)]); seen = set()
        while pending and len(self.proofs) < 128:
            signal, origin, depth = pending.popleft(); key = (signal, origin)
            if key in seen: continue
            seen.add(key); rows = self.writers(signal, origin)
            if not rows:
                mapped = any(item.get('variable', '').casefold() == signal.casefold() for item in self.machine.get('hardwareLinks', []))
                self.unresolved.append(signal + (': hardware-mapped input; live value not supplied.' if mapped else ': no resolved PLC writer; external/HMI/library origin or symbol scope needs verification.'))
                continue
            for row in rows:
                identity = repr((row['name'], row['file'], row['line'], row.get('network'), row.get('value'), row.get('guards')))
                if any(p.get('writerIdentity') == identity for p in self.proofs): continue
                proof = self.writer(row, depth)
                proof['writerIdentity'] = identity
                if row.get('ownership') != 'active task':
                    self.unresolved.append(f"{signal}: task ownership is {row.get('ownership', 'unresolved')} at {row['file']}.")
                # Stop at a declared dependency boundary, never call a bounded
                # trace whole-project execution coverage.
                for dependency in proof.get('inputs', []):
                    if dependency == signal or dependency.upper() in {'TRUE', 'FALSE'}: continue
                    if depth < 2: pending.append((dependency, row['file'], depth+1))
                    else: self.unresolved.append(dependency + ': upstream dependency beyond this trace depth.')
        if pending: self.unresolved.append(f'{len(pending)} dependency entries deferred by the 128-writer resource limit.')
        writer_files = {row['file'] for row in self.writers(name)}
        for ref in self.write_refs:
            if ref['name'] == name.casefold() and ref['file'] not in writer_files:
                self.unresolved.append(f"{name}: indexed write reference at {ref['file']}:{ref['line']} is not a resolved active writer.")


def answer(index, question, machine, selected):
    """Return None for plans handled by the iterative function/machine engine."""
    kind, candidates = selected['kind'], selected['candidates']
    if kind in {'whole-machine', 'function-sequence'}: return None
    if not candidates and not re.search(r'\bmotor\b|\boutput\b|\bhmi\b|binding', question, re.I): return None
    trace = Trace(index, machine)
    target = candidates[0] if len(candidates) == 1 else None
    lines = []
    if not target:
        lines.append('The PLC output is ambiguous. Select the intended symbol: ' + ', '.join('`'+c+'`' for c in candidates) if candidates else 'The output writer could not be resolved from this question. Supply the PLC output tag or its routine.')
        trace.unresolved.append('Output identity is unresolved; no start-condition claim was generated.')
    else:
        lines.append(f'Static {"binding and " if kind == "mapping" else ""}writer trace for `{target}`. No live PLC values were supplied.')
        if kind == 'mapping':
            for binding in machine.get('hmiLinks', []):
                if binding.get('signal') == target:
                    ref = trace.source(binding['file'], binding['line'], binding['line'], 'HMI binding')
                    lines.append(f"[{ref}] `{binding.get('control')}` binds `{target}` in {binding['file']}:{binding['line']} ({binding.get('hmiProject', 'target unresolved')}). A binding does not prove that the HMI writes this signal.")
            matches = sorted({row['name'] for row in machine.get('signalWrites', []) if row['name'].casefold() == target.casefold()})
            if len(matches) == 1: target = matches[0]
            elif len(matches) > 1:
                trace.unresolved.append('Case-distinct PLC declarations match this HMI binding: ' + ', '.join(matches)); target = None
        if target:
            for mapping in machine.get('hardwareLinks', []):
                if mapping.get('variable', '').casefold() == target.casefold() and mapping.get('ownership') == 'active configuration':
                    ref = trace.source(mapping['file'], mapping['line'], mapping['line'], 'active hardware mapping')
                    lines.append(f"[{ref}] Output identity: `{target}` maps to `{mapping['address']}` in active configuration `{mapping.get('configuration')}`.")
            if selected.get('resolution'):
                lines.append('Selected by the active physical-output mapping. Other name matches: ' + ', '.join('`'+s+'`' for s in selected['resolution']['alternatives']) + '. They are not substituted for this mapped output.')
            trace.walk(target)
        primary = [p for p in trace.proofs if p['depth'] == 0]
        tasks = {p.get('task') for p in primary if p.get('task')}
        for task in index.snapshot().get('taskHierarchy', []):
            if task.get('name') not in tasks or not task.get('activeConfiguration') or not task.get('enabled'): continue
            try:
                ref = trace.source(task['file'], task['line'], task['line'], 'active task assignment')
                lines.append(f"[{ref}] Active configuration assigns `{task['source']}` to task `{task['name']}`. Task periods, preemption and actual invocation must be checked separately.")
            except (OSError, ValueError, PermissionError) as error:
                trace.unresolved.append('Task assignment source could not be verified: ' + str(error))
        lines.append(f'{len(primary)} parsed writer(s) for this symbol are listed below, including any initialization, set/reset or alternate assignments found. Instruction types are not initial or observed states.')
        rendered = [p for p in trace.proofs if p['depth'] <= 1]
        for proof in rendered:
            ref = '[' + proof['sourceId'] + ']' if proof.get('sourceId') else '[source unresolved]'
            where = f"{proof['file']}:{proof.get('coilLine', proof['line'])}"
            if proof.get('network'):
                action = f"coil `{proof.get('coilType', proof.get('value'))}` in network {proof['network']}"
            else: action = f"assigns `{proof.get('value')}` in `{proof.get('section', 'routine')}`"
            expression = '`' + proof['expression'] + '`' if proof.get('resolved') else 'unresolved: ' + proof.get('reason', 'complete conditions unavailable')
            prefix = 'Output writer' if proof['depth'] == 0 else 'Upstream writer'
            lines.append(f"{ref} **{prefix}: `{proof['name']}`** — {where} {action}. Power/guard condition: {expression}.")
        if len(rendered) < len(trace.proofs):
            lines.append(f'{len(trace.proofs)-len(rendered)} additional upstream writer proofs and unresolved paths are available in the focused Machine Analysis panel.')
        lines.append('AND joins series conditions; OR joins parallel paths; NOT is a normally closed contact. An ordinary open coil follows rung power when that network executes. Set/reset coils change latched state only when their rung has power. Other instruction types and missing block implementations remain unresolved. Source order does not establish cross-task scheduling or actual motor motion.')
    unresolved = list(dict.fromkeys(trace.unresolved))
    if unresolved: lines.append('Unresolved dependencies and execution checks:\n' + '\n'.join('- ' + item for item in unresolved[:12]) +
                                (f'\n- {len(unresolved)-12} more are listed in Analysis coverage.' if len(unresolved)>12 else ''))
    if unresolved: lines.append('This is an incomplete upstream execution trace; the verified direct rung does not establish every upstream state or the current reason for a stop.')
    if target and not trace.proofs: unresolved.append('No assignment/rung proof is available for the selected symbol.')
    primary = [p for p in trace.proofs if p['depth'] == 0]
    verified = bool(primary) and all(p['resolved'] for p in primary)
    files = {p['file'] for p in trace.proofs}; parsed = {p['file'] for p in trace.proofs if p['resolved']}
    functions = [f for f in machine.get('functions', []) if f['file'] in files]
    state = index.snapshot(); coverage = machine.get('coverage', {})
    solved_sections = {p['sourceId'] for p in trace.proofs if p.get('sourceId') and p['resolved']}
    solved_sections -= {p['sourceId'] for p in trace.proofs if p.get('sourceId') and not p['resolved']}
    solved_sections.update(e['sourceId'] for e in trace.sources if e['type'] in {'active hardware mapping','active task assignment','HMI binding'})
    counts = {'discoveredFiles': state.get('totalFiles'), 'eligibleFiles': state.get('eligibleFiles'), 'indexedFiles': state.get('indexedFiles'),
              'semanticallyParsedFiles': coverage.get('parsedSourceFiles'), 'parsedFilesWithNotices': coverage.get('parsedFilesWithNotices'),
              'retrievedFiles': len({e['file'] for e in trace.sources}), 'retrievedSections': len(trace.sources),
              'modelSuppliedFiles': 0, 'modelSuppliedSections': 0,
              'analyzedFiles': len({e['file'] for e in trace.sources if e['sourceId'] in solved_sections}), 'analyzedLogicFiles': len(parsed),
              'analyzedSections': len(solved_sections), 'analyzedWriterProofs': sum(p['resolved'] for p in trace.proofs),
              'remainingSections': len(trace.sources)-len(solved_sections),
              'relevantFunctionsDiscovered': len(functions), 'relevantFunctionsAnalyzed': sum(f['file'] in parsed for f in functions),
              'unresolvedDependencies': len(unresolved), 'analysisPasses': 0, 'complete': verified and not unresolved}
    verification = {'status': 'verified-static' if verified and not unresolved else 'partial' if verified else 'unresolved',
                    'writerResolved': bool(primary), 'conditionsEstablished': verified, 'runtimeObserved': False,
                    'trainingEligible': verified and not unresolved, 'unresolved': unresolved,
                    'proofs': trace.proofs, 'plan': kind, 'target': target, 'candidates': candidates}
    evidence = [{**e, 'chatSourceId': e['sourceId']} for e in trace.sources]
    view = {'project': machine.get('project'), 'analysisMode': 'question-specific', 'questionPlan': selected,
            'traceTarget': target, 'writerTrace': trace.proofs, 'executionSimulated': False, 'detailLimited': False,
            'functions': functions, 'signalWrites': trace.proofs, 'stateMachines': [],
            'hmiLinks': [h for h in machine.get('hmiLinks', []) if h.get('signal', '').casefold() == str(target).casefold()],
            'hardwareLinks': [h for h in machine.get('hardwareLinks', []) if h.get('variable', '').casefold() == str(target).casefold()],
            'evidence': evidence, 'coverage': {**coverage, 'parsedFilePaths': sorted(parsed),
                                             'parsingIssues': [p for p in coverage.get('parsingIssues', []) if p.get('file') in files],
                                             'notices': unresolved}}
    return {'answer': '\n\n'.join(lines), 'source': 'source-verified-trace', 'model': None, 'review': True,
            'evidence': evidence, 'engineeringVerification': verification, 'modelNotice': 'Answered from parsed writer and wire proofs; no LLM interpretation was used.',
            'retrieval': {'coverage': counts, 'analysisPlan': selected, 'files': evidence, 'filesSent': [], 'notices': unresolved, 'unvisitedFunctions': []},
            'contextUsage': None, 'machineAnalysis': view, 'machineAnalysisProjectId': index.key}
