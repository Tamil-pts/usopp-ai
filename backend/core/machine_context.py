"""Owner-scoped shared decoding and publication of machine identity evidence."""
import hashlib
import json
import re
import os
import threading
from pathlib import Path
from python_engine.project_paths import project_files
from virtual_plc.core.machine_identity import VERSION, select, text_hash
from virtual_plc.core.machine_calls import add_help

_locks = {}
_guard = threading.Lock()


def check_index(index,hashes):
    from backend.core.project_intelligence import connection,metadata
    with connection(index.path) as db:
        if not (metadata(db,'state') or {}).get('ready'):
            raise ValueError('Finish project indexing before linking machine context.')
        changed=[row['path'] for row in db.execute("SELECT path,sha FROM files WHERE status='indexed'")
                 if row['path'] in hashes and row['sha']!=hashes[row['path']]]
    if changed:raise ValueError('Re-index changed project sources before combining machine context: '+', '.join(changed[:3]))


def signature(root):
    from virtual_plc.core.project import RELEVANT, EXCLUDED
    rows = []
    for path in project_files(root, EXCLUDED):
        if path.suffix.casefold() not in RELEVANT | {'.set'}:
            continue
        stat = path.stat()
        rows.append((path.relative_to(root).as_posix(), stat.st_size, stat.st_mtime_ns))
        if len(rows) > 15000:
            raise ValueError('Machine decoding exceeds the 15000 source-file budget.')
    return hashlib.sha256(json.dumps([VERSION, rows]).encode()).hexdigest()


def analyze(index):
    """Reuse Virtual PLC's read-only decoders; never run its scheduler or jig."""
    from virtual_plc.core.project import analyze_project
    with _guard:
        lock = _locks.setdefault(str(index.path), threading.Lock())
    with lock:
        stamp = signature(index.root)
        path = index.path.parent / 'machine_context.json'
        if path.is_file():
            cached = json.loads(path.read_text(encoding='utf-8'))
            if cached.get('signature') == stamp and cached.get('context', {}).get('version') == VERSION:
                check_index(index,cached['context'].get('indexedSourceHashes',{}))
                return cached['context']
        model = analyze_project(index.root)
        context = model['machineContext']
        context['indexedSourceHashes']={f['path']:f['sha256'] for f in model.get('files',[]) if f.get('sha256')}
        check_index(index,context['indexedSourceHashes'])
        if signature(index.root) != stamp:
            raise ValueError('Project changed during machine decoding. Retry with the current sources.')
        context['snapshotSignature'] = stamp
        context['coverage'] = {'files': len(model.get('files', [])), 'diagnostics': model.get('diagnosticCount', 0),
                               'excludedFiles': sum(f.get('status') != 'read' for f in model.get('files', []))}
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'signature': stamp, 'context': context}, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, path)
        return context


def view(index, question='', limit=60):
    return add_help(select(analyze(index), question, max(1, min(200, int(limit)))))


def decorate(reply, index, question, context):
    """Publish deterministic statements and the exact same graph shown in the UI."""
    if signature(index.root) != context.get('snapshotSignature'):
        return {**reply, 'machineContextNotice': 'Project sources changed during investigation; machine-context publication withheld.'}
    data = add_help(select(context, question, 40))
    evidence = list(reply.get('evidence', []))
    number = max([int(m[1]) for e in evidence if (m := re.fullmatch(r'S(\d+)', e.get('sourceId', '')))] or [0])
    citations = {}

    def cite(refs):
        nonlocal number
        ids = []
        for ref in refs:
            key = (ref.get('file'), ref.get('line'))
            if not key[0]:
                continue
            if key not in citations:
                path = (index.root / key[0]).resolve()
                if not path.is_relative_to(index.root) or path.is_symlink():
                    continue
                from python_engine.compare import decode_project_text
                text = decode_project_text(path, path.read_bytes())
                if ref.get('sourceHash') and text_hash(text) != ref['sourceHash']:
                    raise ValueError('Machine context source hash changed: ' + key[0])
                lines = text.splitlines(); first = max(1, key[1]); last = min(len(lines), first + 5)
                number += 1; identifier = 'S' + str(number); citations[key] = identifier
                evidence.append({'sourceId': identifier, 'file': key[0], 'line': first, 'endLine': last,
                                 'excerpt': '\n'.join(lines[first-1:last]), 'ownership': 'machine context source snapshot',
                                 'sourceType': 'project', 'type': 'machine identity/setting link'})
            ids.append('[' + citations[key] + ']')
        return ' '.join(dict.fromkeys(ids))

    statements = []
    for alias in data['aliases'][:4]:
        names = '; '.join('`' + c['label'] + '`' + (f" when `{c['selector']} = {c['value']}`" if c.get('selector') else '') for c in alias['choices'])
        refs = alias['sources'] + [s for c in alias['choices'] for s in c.get('sources', [])]
        statements.append(f"{cite(refs)} HMI names associated with `{alias['signal']}`: {names}. Association: {alias['association']}.")
    for route in data['hardware'][:4] if data['roots'] else []:
        statements.append(f"{cite(route['sources'])} In saved active configuration `{data['activeConfiguration']}`, `{route['name']}` maps to `{route['address']}`.")
    for control in data['controls'][:5] if data['roots'] else []:
        refs = {k: v for k, v in control['bindings'].items() if v and (k in {'minBinding', 'maxBinding', 'statusBinding', 'layerStatusBinding', 'lockingBinding'})}
        if refs:
            statements.append(f"{cite(control['sources'])} `{control['page']}/{control['name']}` has source bindings: " + ', '.join(k + '=' + v for k, v in refs.items()) + '. Their current values were not observed.')
    if data.get('callQuery'):
        for call in data['calls'][:6]:
            statements.append(f"{cite(call['sources'])} `{call['instance']}` calls `{call['name']}`: {call['kind']}; resolution: {call['resolution']}. Call conditions: "+(' AND '.join(call['conditions']) or 'no enclosing condition at this source position' if call['guardCoverage']=='parsed' else 'unresolved')+'.')
            if call.get('documentation'):
                statements.append('Matching installed B&R help: '+', '.join(d['title']+' ('+d['file']+')' for d in call['documentation'])+'. Documentation/version compatibility remains a separate check.')
    if statements:
        reply = {**reply, 'answer': '\n\n'.join(statements) + '\n\n' + reply.get('answer', '')}
    return {**reply, 'evidence': evidence, 'machineContext': data}
