"""Identify calls using source instance types and callable declarations."""
from pathlib import PurePosixPath
import re
from python_engine.engineering_model.decoder import decode
from python_engine.working_sequence import records
from python_engine.function_flow import STRINGS

# Parenthesized Boolean expressions are not callable invocations.
EXPRESSION_OPERATORS = {'NOT', 'AND', 'OR', 'XOR', 'MOD'}


def argument_parts(code, call_name=None):
    """Split the outer call without cutting nested ADR/array expressions."""
    masked=STRINGS.sub(lambda m:' '*len(m[0]),code)
    match=re.search(r'(?<!\w)'+re.escape(call_name)+r'\s*\(',masked,re.I) if call_name else None
    first=match.end()-1 if match else code.find('(') if not call_name else -1
    if first<0:return []
    nesting=0;last=None
    for pos in range(first,len(masked)):
        if masked[pos]=='(':nesting+=1
        elif masked[pos]==')':
            nesting-=1
            if nesting==0:last=pos;break
    if last is None:return []
    value=code[first+1:last];parts=[];start=0;depth=0;quote=None;i=0
    while i<len(value):
        char=value[i]
        if quote:
            if char==quote:
                if i+1<len(value) and value[i+1]==quote:i+=1
                else:quote=None
        elif char in "'\"":quote=char
        elif char in '([':depth+=1
        elif char in ')]':depth-=1
        elif char==',' and depth==0:parts.append(value[start:i].strip());start=i+1
        i+=1
    if value[start:].strip():parts.append(value[start:].strip())
    return parts


def decode_calls(model, sources, resolve, active, ref):
    variables = {v['id']: v for v in model.get('variables', [])}
    declarations = {}
    for d in model.get('interfaces', []) + model.get('functions', []):
        declarations.setdefault(d['name'].casefold(), []).append(d)
    result = []
    for p in model.get('programs', []):
        file, text = p['source'], sources.get(p['source'], p.get('originalCode', p.get('code', '')))
        try:
            decoded = decode(file, text)
            calls = decoded['calls']
            guards = {r['row']['line']: r['guards'] for s in decoded['sections'] for r in records(s.get('nodes', []))}
        except (ValueError, KeyError, TypeError, IndexError):
            continue
        for call in calls:
            if call['name'].upper() in EXPRESSION_OPERATORS:
                continue
            instance = call.get('instance') or call['name']
            variable = variables.get(resolve(instance, p.get('scope')), {})
            name = variable.get('type') or call['name']
            # Explicit AB `Instance FUB Type(...)` supplies the type.
            explicit = re.search(r'\b\w+\s+FUB\s+(\w+)\s*\(', call.get('code', ''), re.I)
            if explicit:
                name = explicit[1]
            found = declarations.get(name.casefold(), [])
            unique = {(d.get('source'), d.get('line')): d for d in found}
            declaration = next(iter(unique.values())) if len(unique) == 1 else None
            implementations = [f for f in model.get('functions', []) if f['name'].casefold() == name.casefold()]
            if not declaration and len(implementations) == 1 and len(found) <= 2:
                declaration = implementations[0]
            kind = 'instance call' if variable or explicit else 'function' if declaration else 'unresolved call'
            if declaration and 'block' in str(declaration.get('kind', '')):
                kind = 'function_block'
            if explicit:kind='function_block'
            ports=[];role=None
            declaration_text=declaration.get('declaration','') if declaration else ''
            for row in declaration_text.splitlines():
                section=re.search(r'\bVAR_(INPUT|OUTPUT|IN_OUT)\b',row)
                if section:role=section[1].lower()
                if 'END_VAR' in row:role=None
                field=re.match(r'\s*([A-Za-z_]\w*)\s*:\s*([^;]+)',row)
                if role and field:ports.append({'name':field[1],'type':field[2],'direction':role})
            code = call.get('code', '')
            # AB inputs are often assigned on preceding lines, not inline.
            rows = text.splitlines()
            first = max(0, call['line'] - 14)
            preceding = '\n'.join(rows[first:call['line']])
            prefix = re.escape(instance) + r'\.'
            fields = {m[1]: m[2].strip() for m in re.finditer(prefix + r'(\w+)\s*:?=\s*([^\r\n]+)', preceding)}
            positional=[]
            for part in argument_parts(code,call['name']):
                m=re.match(r'^(\w+)\s*(:=|=>)\s*(.*)$',part,re.S)
                if m:fields[m[1]]=m[3].strip()
                else:positional.append(part)
            source_refs = [ref(file, call['line'])]
            if declaration:
                source_refs.append(ref(declaration['source'], declaration.get('line', 1)))
            result.append({'id': file + ':' + str(call['line']) + ':' + instance, 'routine': p['id'],
                           'instanceSignal':resolve(instance,p.get('scope')),
                           'instance': instance, 'name': name, 'kind': kind, 'active': p['id'] in active and not call.get('disabled'),
                           'disabled':bool(call.get('disabled')),
                           'arguments': fields, 'positionalArguments':positional,'code': code[:1000], 'sources': source_refs,
                           'implementation': (implementations[0]['source'] if len(implementations) == 1 else declaration.get('implementationSource')) if declaration else None,
                           'declaration': declaration.get('source') if declaration else None,
                           'ports':ports,
                           'library':PurePosixPath(declaration['source']).parent.name if declaration and '/Libraries/' in declaration['source'] else None,
                           'resolution': 'source declaration' if declaration else 'type referenced; implementation unresolved' if variable or explicit else 'unresolved',
                           'conditions': guards.get(call['line'], []),
                           'guardCoverage': 'unresolved' if decoded['notices'] or call['line'] not in guards else 'parsed',
                           'documentation': [], 'argumentMeaning': 'Source expressions and nearby field assignments. Reaching assignments and positional/complex argument binding remain unresolved.'})
    return result


def add_help(view, lookup=None):
    """Exact callable mentions in installed vendor help, separate from project proof."""
    if lookup is None:
        from backend.core.br_help import search
        lookup = search
    cache = {}
    for call in view.get('calls', []):
        name = call['name']
        if name not in cache:
            try:
                hits = lookup(name, 'libraries', 8)
                cache[name] = [{'id': h['id'], 'title': h['title'], 'file': h['file'],
                                'library': h.get('library'), 'excerpt': h.get('excerpt', '')[:1000],
                                'versionStatus': 'Check against the project library version; help does not prove execution.'}
                               for h in hits if h.get('kind') == 'vendor' and re.search(
                                   r'(?<!\w)' + re.escape(name) + r'(?!\w)', h.get('title', '') + ' ' + PurePosixPath(h.get('file','')).stem,re.I)][:2]
            except (OSError, ValueError, KeyError):
                cache[name] = []
        call['documentation'] = cache[name]
    return view
