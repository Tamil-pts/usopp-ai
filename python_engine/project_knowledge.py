"""Source-backed project retrieval for Chopper. No model or PLC execution required."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

from python_engine.compare import project_identity, walk_project, _ladder_networks, decode_bytes

SCHEMA = 7
EXTENSIONS = {'.st', '.ld', '.ab', '.src', '.var', '.typ', '.fun', '.c', '.h', '.txt',
              '.pgp', '.page', '.pages', '.layer', '.dso', '.algrp', '.txtgrp',
              '.iom', '.sw', '.osl', '.hw', '.hwl', '.cfg', '.per', '.apj', '.gdm', '.set'}
STOP = {'what', 'does', 'this', 'project', 'machine', 'function', 'explain', 'about',
        'logic', 'show', 'with', 'that', 'from', 'used', 'work', 'works', 'please',
        'the', 'and', 'how', 'are', 'for', 'can', 'all', 'its', 'tell', 'conditions',
        'cite', 'only', 'supplied', 'line', 'evidence', 'limit', 'answer', 'words', 'selected'}
OVERVIEW_WORDS = {'functions', 'operating', 'operation', 'sequence', 'source', 'files',
                  'ladder', 'networks', 'identify', 'active', 'tasks', 'inferred',
                  'behaviour', 'behavior', 'overview', 'understand', 'uploaded'}
EXECUTABLE = {'.st', '.ld', '.ab', '.src', '.c'}


def machine_question(question):
    """Route functional questions separately from settings and symbol lookups."""
    text = str(question)
    if re.search(r'\b(?:HMI|settings?|configuration|parameters?|datapoints?|declar\w*|where)\b', text, re.I):
        return False
    return bool(re.search(r'machine.*(?:function|operat|work)|(?:function|operat).*machine|'
                          r'operating sequence|(?:understand|explain).*project|project.*(?:function|overview)', text, re.I))


def ladder_behaviour(network):
    """Explain simple series rungs only; retain complex topology as evidence."""
    diagram = network['diagram']
    cells = diagram['cells']
    contacts = [c for c in cells if c['kind'] == 'contact']
    coils = [c for c in cells if c['kind'] == 'coil']
    simple = (diagram['rows'] == 1 and contacts and len(coils) == 1 and
              not any(c['or'] for c in cells) and
              all(c['kind'] in {'line', 'contact', 'coil'} for c in cells) and
              all(c['type'] in {'open', 'closed'} for c in contacts))
    if simple:
        condition = ' AND '.join(f"{c['name']} is {'TRUE' if c['type']=='open' else 'FALSE'}" for c in contacts)
        coil = coils[0]
        action = {'set': 'latches TRUE', 'reset': 'resets FALSE', 'open': 'follows this condition'}.get(coil['type'])
        if action:
            return [f"When {condition}, {coil['name']} {action}."]
    facts = []
    for c in contacts[:4]:
        if c['type'] in {'open', 'closed'}:
            facts.append(f"Contact {c['name']} conducts when {'TRUE' if c['type']=='open' else 'FALSE'}.")
    for c in coils[:3]:
        action = {'set': 'latches TRUE', 'reset': 'resets FALSE', 'open': 'follows rung continuity'}.get(c['type'])
        if action: facts.append(f"Coil {c['name']} {action} when its connected rung conducts.")
    if diagram['rows'] > 1 or any(c['or'] for c in cells):
        facts.append('Parallel paths must be followed in the ladder diagram; these contact facts are not a combined AND condition.')
    blocks = list(dict.fromkeys(c.get('instance') or c['name'] or c['type'] for c in cells
                               if c['kind'] in {'function', 'functionblock'}))
    if blocks: facts.append('Functions / blocks referenced: ' + ', '.join(blocks[:5]) + '; their internals are not established by this network alone.')
    return facts


def conditional_behaviour(text):
    """Extract direct IF assignments without treating comments as live code."""
    clean = re.sub(r'\(\*.*?\*\)|//[^\n]*', lambda m: '\n' * m.group().count('\n'), text, flags=re.S)
    pattern = r'\bIF\s+([^\n]*(?:\n[^\n]*)?)\s+THEN\s*\n?\s*([A-Za-z_]\w*(?:\.\w+|\[[^\]\n]+\])*)\s*(?::=|=(?!=))\s*([^;\n]+)'
    facts = []
    for match in re.finditer(pattern, clean, re.I):
        condition = ' '.join(match.group(1).split())
        if re.search(r'\b(?:THEN|ELSE|ENDIF|END_IF)\b', condition, re.I): continue
        facts.append({'text': f"When {condition}, the TRUE branch assigns {match.group(2)} = {match.group(3).strip()}.",
                      'offset': clean.count('\n', 0, match.start()),
                      'endOffset': clean.count('\n', 0, match.end())})
        if len(facts) >= 3: break
    return facts


def words(value):
    return set(re.findall(r'[a-z_][a-z0-9_]{2,}', str(value).casefold())) - STOP


def declarations(text):
    """Retain declaration expressions and array bounds; never guess a datatype."""
    return [{'name': m.group(1), 'declaration': m.group(2).strip(),
             'line': text.count('\n', 0, m.start()) + 1}
            for m in re.finditer(r'(?im)^\s*([A-Za-z_]\w*)\s*:\s*([^;\n]+);', text)
            if m.group(1).upper() not in {'ELSE', 'DEFAULT'}]


def category(path):
    suffix = path.suffix.casefold()
    if suffix in {'.var', '.typ', '.fun', '.pgp'}: return 'Declarations'
    if suffix in {'.page', '.pages', '.layer', '.dso', '.txtgrp'}: return 'HMI'
    if suffix == '.algrp': return 'Alarms'
    if suffix in {'.iom', '.hw', '.hwl'} or path.name.casefold()=='hw.cfg': return 'Hardware / I/O'
    if suffix in {'.sw', '.osl', '.cfg', '.per', '.apj', '.gdm', '.set'}: return 'Configuration'
    return 'Ladder' if suffix == '.ld' else 'Logic'


def source_files(root):
    identity = project_identity(root)
    candidates = list(walk_project(root, identity).values())
    legacy = str(identity.get('automation_studio_version') or '').startswith('2.')
    if legacy and identity.get('legacy_cpu_root'):
        # Keep shared legacy declarations/libraries without bypassing the
        # configuration and HMI selection made by the common discovery code.
        candidates += [p for p in root.iterdir() if p.is_file() and p.name.casefold()=='cpu.txt']
        library=next((p for p in root.iterdir() if p.is_dir() and p.name.casefold()=='library'),None)
        if library:
            candidates += [p for p in library.rglob('*') if p.is_file() and
                           not any(part.casefold() in {'temp','as','binaries','.git','diagnosis','__pycache__','dbk','ai_qc'}
                                   for part in p.relative_to(root).parts)]
    files = sorted({p for p in candidates if p.suffix.casefold() in EXTENSIONS}, key=lambda p: str(p).casefold())
    return identity, files, legacy


def build_index(root, cache_dir=None, progress=None):
    root = Path(root).resolve()
    if progress: progress('Discovering active configuration and project files')
    identity, files, legacy = source_files(root)
    manifest = [(p.relative_to(root).as_posix(), p.stat().st_size, p.stat().st_mtime_ns) for p in files]
    fingerprint = hashlib.sha256(json.dumps([SCHEMA, str(root), identity, manifest], sort_keys=True).encode()).hexdigest()
    cache = Path(cache_dir) / (fingerprint + '.json') if cache_dir else None
    if cache and cache.is_file():
        try:
            if progress: progress('Loading unchanged project knowledge', len(files), len(files))
            return json.loads(cache.read_text(encoding='utf-8'))
        except (ValueError, OSError): pass
    tasks = []
    for path in files:
        if path.name.casefold() != 'cpu.sw': continue
        try:
            tree = ET.fromstring(path.read_bytes())
            for node in tree.iter():
                if node.tag.rsplit('}', 1)[-1].casefold() == 'task':
                    tasks.append({'name': node.get('Name', ''), 'source': node.get('Source', ''),
                                  'file': path.relative_to(root).as_posix()})
        except (ET.ParseError, OSError): pass
    owners = {t['source'].removesuffix('.prg').replace('.', '/').casefold() for t in tasks if t['source']}
    chunks, symbols, inventory, notices, modules = [], [], [], [], []
    budget = 0
    for number, path in enumerate(files, 1):
        if progress: progress('Reading project files and extracting logic', number, len(files))
        rel = path.relative_to(root).as_posix()
        if not path.resolve().is_relative_to(root):
            notices.append(f'{rel}: skipped external linked source.'); continue
        if path.stat().st_size > 5 * 1024 * 1024 or budget + path.stat().st_size > 80 * 1024 * 1024:
            notices.append(f'{rel}: skipped because the project reading limit was reached.'); continue
        raw = path.read_bytes(); budget += len(raw)
        text = decode_bytes(raw).replace('\x00', '')
        text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f]', '', text)
        if not text.strip(): continue
        kind = category(path)
        active = any('/' + owner + '/' in '/' + rel.casefold() for owner in owners)
        ownership = 'active task' if active else 'configuration' if rel.startswith('Physical/') else 'shared / task ownership unconfirmed'
        inventory.append({'file': rel, 'category': kind, 'ownership': ownership,
                          'lines': len(text.splitlines())})
        if kind in {'Logic', 'Ladder'}:
            assignment = r'\b([A-Za-z_]\w*(?:\.\w+)*)\s*' + (r'=(?!=)' if path.suffix.casefold()=='.ab' else r':=')
            facts={'file': rel, 'ownership': ownership,
                            'conditions': len(re.findall(r'\b(?:IF|ELSIF|CASE)\b', text, re.I)),
                            'assignments': len(re.findall(assignment, text)),
                            'outputs': list(dict.fromkeys(re.findall(assignment, text)))[:15],
                            'functionBlocks': list(dict.fromkeys(re.findall(r'<functionblock\b[^>]*\btype="([^"]+)"', text)))[:12]}
            if kind=='Ladder':
                facts['conditions']=len(re.findall(r'<contact\b',text))
                facts['assignments']=len(re.findall(r'<coil\b',text))
                facts['outputs']=list(dict.fromkeys(re.findall(r'<coil\b[^>]*\bname="([^"]+)"',text)))[:15]
            facts['controlOutputs'] = len(set(name for name in
                (re.findall(r'<coil\b[^>]*\bname="([^"]+)"',text) if kind=='Ladder' else re.findall(assignment,text))
                if re.search(r'^(?:DO_|MC_ON|MC_OFF)|MOTOR.*(?:RUN|START|STOP)',name,re.I)))
            facts['countMeaning']='Extracted syntax counts, not complete runtime semantics.'
            modules.append(facts)
        if kind == 'Declarations' or path.suffix.casefold() == '.txt':
            symbols.extend({**s, 'file': rel} for s in declarations(text))
        networks = _ladder_networks(text) if path.suffix.casefold() == '.ld' else []
        if networks:
            network_offsets = [m.start() for m in re.finditer(r'<network\s', text)]
            for network in networks:
                enabled=not network.get('commented',False)
                snippet = '\n'.join([f"Network {network['index']}: {'enabled in source' if enabled else 'COMMENTED OUT - does not execute'}",
                                     network.get('comment', ''), network.get('summary', ''), network.get('layout', '')])
                chunks.append({'file': rel, 'line': text.count('\n', 0, network_offsets[network['index'] - 1]) + 1,
                               'network': network['index'], 'category': kind, 'ownership': ownership,
                               'enabled':enabled,'behaviour':ladder_behaviour(network),
                               'text': snippet[:10000], 'terms': sorted(words(rel + ' ' + snippet))})
        else:
            lines = text.splitlines()
            for start in range(0, len(lines), 60):
                snippet = '\n'.join(lines[start:start + 70])
                chunks.append({'file': rel, 'line': start + 1, 'category': kind, 'ownership': ownership,
                               'behaviour':conditional_behaviour(snippet) if path.suffix.casefold() in {'.st','.ab','.src'} else [],
                               'text': snippet[:10000], 'terms': sorted(words(rel + ' ' + snippet))})
    if not identity.get('active_configuration') and not legacy:
        notices.append('Active configuration unresolved: physical files are excluded; logical task ownership is unconfirmed.')
    if identity.get('scope_notice'): notices.append(identity['scope_notice'])
    result = {'schema': SCHEMA, 'fingerprint': fingerprint, 'identity': identity, 'tasks': tasks,
              'inventory': inventory, 'symbols': symbols, 'chunks': chunks, 'notices': notices, 'modules': modules,
              'counts': dict(Counter(item['category'] for item in inventory)),
              'coverage': 'Static source analysis; shared sources are not proof of active runtime behaviour.'}
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=cache.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream: json.dump(result, stream)
            os.replace(temporary, cache)
        finally:
            if Path(temporary).exists(): Path(temporary).unlink()
    return result


def retrieve(index, question, limit=14, characters=18000):
    query = words(question)
    overview = machine_question(question)
    if overview: query -= OVERVIEW_WORDS
    file_match=re.search(r'([\w.-]+\.(?:ld|st|ab|src|c|var|typ|page))\b',question,re.I)
    network_match=re.search(r'\bnetwork\s+(\d+)',question,re.I)
    candidates=index['chunks']
    if file_match and network_match:
        candidates=[c for c in candidates if Path(c['file']).name.casefold()==file_match.group(1).casefold()
                    and c.get('network')==int(network_match.group(1))]
    else:
        if file_match:
            candidates=[c for c in candidates if Path(c['file']).name.casefold()==file_match.group(1).casefold()]
        if not re.search(r'commented|disabled|inactive',question,re.I):
            candidates=[c for c in candidates if c.get('enabled',True)]
    if overview and not file_match:
        candidates=[c for c in candidates if c['category'] in {'Logic','Ladder'} and
                    Path(c['file']).suffix.casefold() in EXECUTABLE]
        # Empty initialization files and XML metadata cannot explain operation.
        candidates=[c for c in candidates if c.get('enabled',True)]
    def score(chunk):
        return sum(20 for word in query if word in chunk['file'].casefold()) + 4*len(query & set(chunk['terms']))
    modules = {m['file']:m for m in index.get('modules',[])}
    def operational_rank(chunk):
        module = modules.get(chunk['file'],{})
        return (chunk['ownership'] != 'active task',
                bool(re.search(r'(?:Init|Exit)\.', chunk['file'], re.I)),
                -score(chunk),
                -bool(module.get('controlOutputs')),
                -module.get('conditions',0),
                -bool(chunk.get('behaviour')),
                -len(re.findall(r'\b(?:DO_|MC_ON|MC_OFF|FEED|FAULT|START|STOP)\w*', chunk['text'], re.I)),
                chunk['file'], chunk['line'])
    ranked = sorted(candidates, key=operational_rank if overview else lambda c: (-score(c),
                    c['ownership'] != 'active task', c['category'] not in {'Logic', 'Ladder'}, c['file'], c['line']))
    chosen, seen_files, seen_tasks = [], set(), set()
    for chunk in ranked:
        if overview and Path(chunk['file']).parent.as_posix() in seen_tasks: continue
        if overview and chunk['file'] in seen_files: continue
        if not overview and query and not score(chunk): continue
        # A bounded sample across control tasks is more useful than one large XML page.
        excerpt = chunk['text'][:min(900 if overview else 1800, characters)]
        if not excerpt: break
        facts = chunk.get('behaviour', [])
        if not chunk.get('network'):
            facts = [f for f in facts if f.get('endOffset',f['offset']) < len(excerpt.splitlines())-1]
        chosen.append({k: chunk[k] for k in ('file', 'line', 'category', 'ownership', 'network', 'enabled') if k in chunk} |
                      {'excerpt': excerpt, 'behaviour': facts})
        seen_files.add(chunk['file']); seen_tasks.add(Path(chunk['file']).parent.as_posix()); characters -= len(excerpt)
        if len(chosen) >= limit or characters <= 0: break
    return chosen


def explanation_supported(answer, evidence, comparison=None):
    """Reject fabricated source names/locations; semantic claims still need review."""
    allowed={Path(e['file']).name.casefold() for e in evidence}
    if comparison:
        allowed.update(Path(r['file']).name.casefold() for rows in comparison['categories'].values() for r in rows)
    mentioned=re.findall(r'\b([A-Za-z_][\w.-]*\.(?:st|ld|ab|src|var|typ|page|layer|iom|sw|hwl|hw))\b',answer,re.I)
    if any(name.casefold() not in allowed for name in mentioned): return False
    ids=[number for group in re.findall(r'\[((?:S\d+[,;\s]*)+)\]',answer) for number in re.findall(r'S(\d+)',group)]
    if evidence and (not ids or any(not 1<=int(i)<=len(evidence) for i in ids)): return False
    if comparison and not mentioned: return False
    if evidence and all(not e.get('enabled',True) for e in evidence) and not re.search(r'commented|disabled|inactive|not.*execut',answer,re.I): return False
    for name, number in re.findall(r'([A-Za-z_][\w.-]*\.(?:st|ld|ab|src|var|typ))[^\n]{0,50}?(?:line\s+|:\s*)(\d+)',answer,re.I):
        ranges=[(e['line'],e['line']+(1 if e.get('network') else len(e['excerpt'].splitlines()))) for e in evidence
                if Path(e['file']).name.casefold()==name.casefold()]
        if not any(start<=int(number)<end for start,end in ranges): return False
    return True


def module_overview(index, question, limit=16):
    query = words(question)
    if machine_question(question):
        evidence = retrieve(index, question, limit=limit)
        selected = {e['file']: number for number,e in enumerate(evidence)}
        return sorted((m for m in index['modules'] if m['file'] in selected), key=lambda m: selected[m['file']])[:limit]
    return sorted(index['modules'], key=lambda m: (-len(query & words(m['file'] + ' ' + ' '.join(m['outputs']))),
                   m['ownership'] != 'active task', -m['conditions'], m['file']))[:limit]


def project_answer(index, evidence, question=''):
    identity = index['identity']
    lines = [f"Project knowledge: {identity.get('project_name', 'Uploaded project')}",
             f"Active configuration: {identity.get('active_configuration') or 'unresolved / legacy single configuration'}",
             'Source inventory: ' + ', '.join(f'{count} {kind} files' for kind, count in index['counts'].items()),
             f"{len(index['tasks'])} configured tasks; {len(index['symbols'])} extracted declarations.",
             '', 'Machine functions - confirmed control behaviour:' if machine_question(question) else 'Relevant logic and source evidence:']
    for item in evidence[:10]:
        source = f"{item['file']}:{item['line']}" + (f" / network {item['network']}" if item.get('network') else '')
        lines.append(f"\n{source} ({item['ownership']})")
        if not item.get('enabled',True):
            lines.append('- This network is commented out and does not execute.')
            continue
        facts = item.get('behaviour', [])
        # Include both input and output facts for complex rungs.
        displayed = facts if len(facts)<=4 else [facts[0],facts[1],
                    next((f for f in facts if isinstance(f,str) and f.startswith('Coil ')),facts[2]),facts[-1]]
        for fact in displayed:
            lines.append('- ' + (fact if isinstance(fact,str) else fact['text']))
        if not facts:
            lines.append('- No complete conditional action was extracted from this excerpt. Open the source to trace its connections and called functions.')
    lines.extend(['', 'Coverage: these are selected static control actions, not a complete simulated operating sequence. The order above is for reading, not PLC execution order. Shared sources are not confirmed active tasks. Machine purpose and function-block internals require further source review.', *index['notices']])
    return '\n'.join(lines)


def comparison_knowledge(result, work=None, question=''):
    groups = {name: [] for name in ('Variables', 'Logic', 'Ladder', 'HMI layout', 'HMI behaviour', 'Hardware / configuration')}
    totals = Counter()
    query=words(question)
    def add(group, row):
        totals[group] += 1
        groups[group].append(row)
        if len(groups[group])>35:
            groups[group].sort(key=lambda r:-len(query & words(json.dumps(r))))
            groups[group].pop()
    for entry in result.get('diffs', []):
        file = entry.get('new_relative_path') or entry.get('base_relative_path') or entry['path']
        base = entry.get('base_source', ''); new = entry.get('new_source', '')
        ext = Path(file).suffix.casefold()
        if ext in {'.var', '.typ', '.fun', '.pgp'}:
            b = {r['name']: r for r in declarations(base)}; n = {r['name']: r for r in declarations(new)}
            for name in sorted(set(b) | set(n)):
                before, after = b.get(name), n.get(name)
                if before and after and before['declaration'] == after['declaration']: continue
                add('Variables', {'file': file, 'name': name, 'status': 'added' if not before else 'removed' if not after else 'modified',
                                  'before': before, 'after': after})
        if entry.get('category') == 'logic' and ext not in {'.var', '.typ', '.fun'}:
            add('Ladder' if ext == '.ld' else 'Logic', {'file': file, 'status': entry['status'],
                'added': entry.get('logic_added', [])[:5], 'removed': entry.get('logic_removed', [])[:5],
                'networks': [{'name': c.get('name'), 'type': c.get('type')} for c in (entry.get('parsed_ladder') or {}).get('changes', [])][:15]})
        parsed = entry.get('parsed_screen')
        if not parsed and work and re.fullmatch(r'[a-f0-9]{64}', entry.get('screen_detail_id', '')):
            detail = Path(work) / 'hmi_details' / (entry['screen_detail_id'] + '.json')
            if detail.is_file(): parsed = json.loads(detail.read_text(encoding='utf-8'))
        if parsed:
            for control in parsed.get('controls', []):
                if control.get('status') in {'added', 'removed'}:
                    add('HMI behaviour', {'file': file, 'control': control['name'], 'status': control['status']})
                for change in control.get('changes', []):
                    prop = str(change.get('prop', ''))
                    layout = bool(re.search(r'left|top|width|height|position|alignment|zorder|color|font', prop, re.I))
                    add('HMI layout' if layout else 'HMI behaviour', {'file': file, 'control': control['name'], **change})
        elif entry.get('category') == 'screen':
            add('HMI behaviour', {'file': file, 'status': entry['status'], 'notice': 'File-level change; structured properties unavailable.'})
        if entry.get('category') in {'hardware', 'config'}:
            add('Hardware / configuration', {'file': file, 'status': entry['status'],
                'changes': (entry.get('parsed_hardware') or {}).get('changes', [])[:8]})
    projects=result.get('projects') or {}
    return {'base': result.get('baseName') or (projects.get('base') or {}).get('project_name','Base'),
            'developed': result.get('newName') or (projects.get('developed') or {}).get('project_name','Developed'), 'testId': result.get('testId'),
            'projects': result.get('projects'), 'summary': result.get('summary'),
            'categories': groups, 'counts': dict(totals),
            'coverage': 'Counts are extracted changes, not defect counts. Detail examples are bounded to 35 per category. Effects require source analysis; no runtime simulation.'}


def comparison_answer(knowledge):
    lines = [f"Major differences: {knowledge['base']} → {knowledge['developed']}"]
    summary=knowledge.get('summary') or {}
    if summary:
        lines.append(f"The comparison found {summary.get('modified',0)} modified files, {summary.get('added',0)} added files and {summary.get('removed',0)} removed files.")
    for name, rows in knowledge['categories'].items():
        lines.append(f"\n{name}: {knowledge['counts'].get(name, 0)} extracted changes")
        for row in rows[:5]:
            status=row.get('status','changed')
            if name=='Variables':
                before,after=row.get('before'),row.get('after')
                variable=row.get('name','Variable')
                if not before: description=f"Variable {variable} was added with declaration {after['declaration']}."
                elif not after: description=f"Variable {variable} was removed; its previous declaration was {before['declaration']}."
                else: description=f"Variable {variable} changed from {before['declaration']} to {after['declaration']}."
            elif row.get('prop'):
                description=f"Control {row.get('control','')} changed {row['prop']} from {row.get('from')} to {row.get('to')}."
            elif row.get('control'):
                description=f"HMI control {row['control']} was {status}."
            else:
                description=f"{'Ladder source' if name=='Ladder' else 'PLC logic source' if name=='Logic' else 'Hardware/configuration file'} was {status}."
                networks=row.get('networks') or []
                if networks: description+=' Network changes: '+', '.join(f"{n.get('name','network')} ({n.get('type','changed')})" for n in networks[:4])+'.'
                for action in ('added','removed'):
                    statements=row.get(action) or []
                    if statements: description+=f" {action.title()} source examples: "+' '.join(str(s)[:180] for s in statements[:2])
            lines.append(f"- {row['file']}: {description}")
    lines.extend(['', knowledge['coverage']])
    return '\n'.join(lines)
