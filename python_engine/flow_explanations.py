"""Explain routine calls using local declarations, implementations and B&R help.

This is static analysis. Documentation describes the block contract; the parsed
project determines the actual conditions, arguments and subsequent actions.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path
import re
import sqlite3

from python_engine.br_help_index import read_text
from python_engine.function_flow import _mask_comments, STRINGS
from python_engine.working_sequence import records, operation, call_step

MAX_BYTES = 5 * 1024 * 1024
CASTS = set('BOOL SINT INT DINT LINT USINT UINT UDINT ULINT REAL LREAL BYTE WORD DWORD LWORD STRING TIME DATE DT'.split())


def compact(value):
    return ' '.join(str(value).replace('\ufeff', '').split())


class HelpTables(HTMLParser):
    """Keep table cells together, including descriptions containing sub-tables."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.tables = [], []

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.stack.append({'rows': [], 'row': None, 'cell': None})
        elif self.stack:
            if tag == 'tr': self.stack[-1]['row'] = []
            elif tag in {'td', 'th'}: self.stack[-1]['cell'] = []
            elif tag in {'br', 'p', 'div'}:
                for table in self.stack:
                    if table['cell'] is not None: table['cell'].append(' ')

    def handle_data(self, data):
        for table in self.stack:
            if table['cell'] is not None: table['cell'].append(data)

    def handle_endtag(self, tag):
        if not self.stack: return
        table = self.stack[-1]
        if tag in {'td', 'th'} and table['cell'] is not None:
            if table['row'] is not None: table['row'].append(compact(''.join(table['cell'])))
            table['cell'] = None
        elif tag == 'tr' and table['row'] is not None:
            table['rows'].append(table['row'])
            table['row'] = None
        elif tag == 'table':
            self.tables.append(self.stack.pop()['rows'])


class HelpParagraphs(HTMLParser):
    """Read explanatory paragraphs without treating a table header as a section."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section, self.heading, self.paragraph = '', None, None
        self.table_depth, self.hidden = 0, 0
        self.paragraphs = []

    def flush(self):
        if self.paragraph is not None:
            text = compact(''.join(self.paragraph))
            if text: self.paragraphs.append((self.section, text))
        self.paragraph = None

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}: self.hidden += 1
        if tag == 'table':
            self.flush()
            self.table_depth += 1
        if self.table_depth or self.hidden: return
        if tag in {'h1', 'h2', 'h3'}:
            self.flush()
            self.heading = []
        elif tag == 'p':
            self.flush()
            self.paragraph = []
        elif tag in {'br', 'div', 'li'} and self.paragraph is not None:
            self.paragraph.append(' ')

    def handle_data(self, data):
        if self.table_depth or self.hidden: return
        if self.heading is not None: self.heading.append(data)
        elif self.paragraph is not None: self.paragraph.append(data)

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}: self.hidden = max(0, self.hidden - 1)
        if tag == 'table': self.table_depth = max(0, self.table_depth - 1)
        if self.table_depth or self.hidden: return
        if tag in {'h1', 'h2', 'h3'} and self.heading is not None:
            self.section = compact(''.join(self.heading)).casefold()
            self.heading = None
        elif tag == 'p': self.flush()


class HelpContracts:
    def __init__(self, database, knowledge_root, libraries=()):
        self.database, self.root = Path(database), Path(knowledge_root).resolve()
        self.libraries = {name.casefold() for name in libraries}
        self.cache = {}

    def lookup(self, name, library_hint=''):
        key = name.casefold()
        cache_key = (key, library_hint.casefold())
        if cache_key in self.cache: return self.cache[cache_key]
        result = {'name': name, 'kind': 'Function call', 'purpose': '', 'behavior': [],
                  'parameters': [], 'statuses': [], 'references': [], 'notes': []}
        self.cache[cache_key] = result
        if name.upper() in CASTS:
            result.update(kind='Type conversion', purpose=f'Convert the expression to {name.upper()}.',
                          parameters=[{'direction': 'IN', 'name': 'expression', 'dataType': 'Expression', 'description': 'Value supplied to the conversion.'},
                                      {'direction': 'OUT', 'name': 'result', 'dataType': name.upper(), 'description': 'Converted value used by the enclosing expression or assignment.'}])
            return result
        if key in {'adr', 'sizeof'}:
            result.update(kind='Language operator', purpose='Return the memory address of the supplied variable or literal.' if key == 'adr'
                          else 'Return the size of the supplied value or type in bytes.',
                          parameters=[{'direction': 'IN', 'name': 'value', 'dataType': 'Variable / literal / type', 'description': 'Argument from this call.'},
                                      {'direction': 'OUT', 'name': 'result', 'dataType': 'Address' if key == 'adr' else 'Byte count', 'description': 'Value returned to the enclosing expression.'}])
            return result
        if not re.fullmatch(r'[A-Za-z_]\w*', name) or not self.database.is_file():
            result['notes'] = ['No matching local B&R help topic is available.']
            return result
        try:
            with closing(sqlite3.connect(f'file:{self.database.resolve().as_posix()}?mode=ro', uri=True)) as db:
                db.row_factory = sqlite3.Row
                rows = [dict(row) for row in db.execute(
                    "SELECT title,file,text,library FROM documents WHERE kind='vendor' AND "
                    "(lower(file) LIKE ? OR lower(file) LIKE ?) ORDER BY file",
                    ('%/' + key + '.html', '%/' + key + '.htm'))]
        except (OSError, sqlite3.Error):
            result['notes'] = ['The local B&R help index could not be read.']
            return result
        rows = [row for row in rows if '/libraries/' in row['file'].casefold() and '/fbks/' in row['file'].casefold()]
        preferred = [row for row in rows if row['library'].casefold() in self.libraries]
        if preferred: rows = preferred
        bound = [row for row in rows if library_hint and row['library'].casefold() == library_hint.casefold()]
        if bound: rows = bound
        # Duplicate copies of a topic are equivalent; different libraries are not.
        libraries = {row['library'].casefold() for row in rows}
        if len(libraries) > 1:
            result['notes'] = ['More than one library documents this name: ' + ', '.join(sorted(libraries)) + '. The project library binding is unresolved.']
            return result
        if not rows:
            result['notes'] = ['No exact function topic was found in the supplied B&R help.']
            return result
        row = rows[0]
        lines = [compact(line) for line in row['text'].splitlines() if compact(line)]
        heading = next((i for i, line in enumerate(lines) if re.fullmatch(re.escape(name) + r'\s*\(\s*\)', line, re.I)), -1)
        if heading >= 0:
            purpose = []
            for line in lines[heading + 1:]:
                if re.search(r'redundancy|^Parameters$|^Call syntax', line, re.I): break
                purpose.append(line)
            result['purpose'] = compact(' '.join(purpose))
        result['library'] = row['library']
        result['references'] = [{'title': row['title'], 'file': row['file']}]
        path = (self.root / row['file']).resolve()
        if path.is_relative_to(self.root) and path.is_file() and path.stat().st_size <= MAX_BYTES:
            parser = HelpTables()
            html = read_text(path.read_bytes())
            parser.feed(html)
            paragraphs = HelpParagraphs()
            paragraphs.feed(html)
            paragraphs.flush()
            result['behavior'] = [text for section, text in paragraphs.paragraphs
                                  if section in {'description', 'notes', 'comment'} and text != result['purpose'] and not re.search(r'redundancy', text, re.I)]
            for table in parser.tables:
                for cells in table:
                    if len(cells) >= 4 and cells[0].upper() in {'IN', 'OUT', 'IN_OUT', 'IN/OUT'}:
                        result['parameters'].append({'direction': cells[0].upper(), 'name': cells[1],
                                                     'dataType': cells[2], 'description': ' '.join(cells[3:])})
                header = next((cells for cells in table if any(re.search(r'error number|constant|^value$', c, re.I) for c in cells)), None)
                if header:
                    for cells in table:
                        number = next((cell for cell in cells if re.fullmatch(r'\d+', cell)), None)
                        constant = next((cell for cell in cells if re.fullmatch(r'[A-Za-z_]\w*', cell) and 'ERR' in cell.upper()), None)
                        if number and constant:
                            meaning = [cell for cell in cells if cell and cell not in {number, constant}]
                            result['statuses'].append({'value': number, 'name': constant, 'description': ' '.join(meaning)})
        # Assignment-return syntax identifies a function despite generic
        # redundancy boilerplate sometimes calling every library entry a block.
        syntax = re.search(r'Call syntax[^\n]*\n+([^\n]+)', row['text'], re.I)
        result['kind'] = 'Function' if syntax and re.search(r'\w+\s*=', syntax[1]) else ('Function block' if re.search(r'function block', result['purpose'], re.I) else 'Function')
        result['notes'].append('Behavior from the supplied B&R help; verify the installed library and Automation Runtime version before changing PLC code.')
        return result


def declarations(text, file):
    clean = _mask_comments(text, Path(file).suffix.casefold() == '.ab')
    scope, direction = '', 'LOCAL'
    result = []
    for line_number, line in enumerate(clean.splitlines(), 1):
        header = re.match(r'\s*(?:\{[^}]*\}\s*)*(FUNCTION_BLOCK|FUNCTION|PROGRAM)\s+(\w+)\s*(?::\s*(\w+))?', line, re.I)
        if header: scope = header[2]
        if header and header[1].upper() == 'FUNCTION' and header[3]:
            result.append({'name': header[2], 'type': header[3], 'direction': 'OUTPUT', 'scope': scope, 'file': file, 'line': line_number, 'returnValue': True})
        if re.match(r'\s*END_(FUNCTION_BLOCK|FUNCTION|PROGRAM)\b', line, re.I): scope = ''
        section = re.match(r'\s*VAR(?:_(INPUT|OUTPUT|IN_OUT|GLOBAL))?\b', line, re.I)
        if section: direction = (section[1] or 'LOCAL').upper()
        match = re.match(r'\s*((?:\w+\s*,\s*)*\w+)\s*:\s*(\w+)(?:\s*\[[^\]]*\])?', line)
        if match:
            for name in match[1].split(','):
                result.append({'name': name.strip(), 'type': match[2], 'direction': direction,
                               'scope': scope, 'file': file, 'line': line_number})
    return result


def arguments(code, name):
    """Split arguments without splitting nested functions, arrays or strings."""
    match = re.search(r'\b' + re.escape(name) + r'\s*\(', code, re.I)
    if not match: return []
    start, depth, quote, result = match.end(), 0, '', []
    for i in range(start, len(code)):
        char = code[i]
        if quote:
            if char == quote and (i == 0 or code[i - 1] != '$'): quote = ''
        elif char in "'\"": quote = char
        elif char in '([': depth += 1
        elif char in ')]':
            if depth == 0:
                tail = code[start:i].strip()
                if tail: result.append(tail)
                break
            depth -= 1
        elif char == ',' and depth == 0:
            result.append(code[start:i].strip())
            start = i + 1
    return result


def connected_condition(target, diagram):
    """Recover a single series input path; retain ambiguous branches as diagrams."""
    by_id = {cell['id']: cell for cell in diagram['cells']}
    incoming = defaultdict(list)
    branches = set()
    for edge in diagram['connections']:
        if edge['kind'] == 'series': incoming[edge['to']].append(edge['from'])
        else: branches.update((edge['from'], edge['to']))
    current, visited, parts = target, set(), []
    while incoming.get(current['id']):
        parents = incoming[current['id']]
        if len(parents) != 1 or parents[0] in visited or current['id'] in branches: return None
        visited.add(parents[0])
        current = by_id[parents[0]]
        if current['id'] in branches: return None
        if current['kind'] == 'contact':
            value = {'open': f'{current["name"]} is TRUE', 'closed': f'{current["name"]} is FALSE',
                     'positive transition': f'Rising edge of {current["name"]}',
                     'negative transition': f'Falling edge of {current["name"]}'}.get(current['type'])
            if not value: return None
            parts.insert(0, value)
        elif current['kind'] in {'function', 'functionblock'}:
            header = next((cell for cell in diagram['cells'] if cell.get('blockId') == current['blockId'] and cell.get('instance')), current)
            outputs = current.get('outputs', [])
            if len(outputs) != 1: return None
            parts.insert(0, f'{header.get("instance") or header.get("name") or header["type"]}.{outputs[0]} is TRUE')
            break
        elif current['kind'] != 'line': return None
    return ' AND '.join(parts) if parts else None


class FlowExplainer:
    def __init__(self, files, loader, help_database, knowledge_root):
        self.files, self.loader = files, loader
        self.decls, self.implementations = [], defaultdict(list)
        self.bindings = defaultdict(set)
        self.read_notices, self.loaded, self.steps = [], 0, 0
        libraries = set()
        for relative, path in files.items():
            parts = Path(relative).parts
            lowered = [part.casefold() for part in parts]
            if 'libraries' in lowered:
                i = lowered.index('libraries') + 1
                if i < len(parts): libraries.add(parts[i])
            if Path(relative).suffix.casefold() not in {'.var', '.fun', '.typ', '.ab', '.st'}: continue
            try:
                if path.stat().st_size > MAX_BYTES: continue
                raw = path.read_bytes()
                text = raw.decode('utf-16') if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else read_text(raw)
                if '\x00' in text: continue
            except (OSError, UnicodeError):
                self.read_notices.append(f'Could not read declarations or implementation in {relative}.')
                continue
            self.decls.extend(declarations(text, relative))
            if Path(relative).suffix.casefold() == '.fun' and 'libraries' in lowered:
                library = parts[lowered.index('libraries') + 1]
                for name in re.findall(r'^\s*(?:\{[^}]*\}\s*)*(?:FUNCTION_BLOCK|FUNCTION)\s+(\w+)', _mask_comments(text, False), re.I | re.M):
                    self.bindings[name.casefold()].add(library)
            if Path(relative).suffix.casefold() in {'.ab', '.st'}:
                clean = _mask_comments(text, Path(relative).suffix.casefold() == '.ab')
                for kind, name in re.findall(r'^\s*(FUNCTION_BLOCK|FUNCTION)\s+(\w+)', clean, re.I | re.M):
                    self.implementations[name.casefold()].append({'file': relative, 'kind': kind})
        self.help = HelpContracts(help_database, knowledge_root, libraries)

    def resolve(self, instance, flow, section):
        scope = section['name'].split(':', 1)[0].strip()
        values = [row for row in self.decls if not row.get('returnValue') and row['name'].casefold() == instance.casefold() and
                  (row['file'] == flow['sourceFile'] or
                   Path(row['file']).parent == Path(flow['sourceFile']).parent and (not row['scope'] or row['scope'].casefold() == scope.casefold()) or
                   row['direction'] == 'GLOBAL')]
        if not values: return None
        local = [row for row in values if row['direction'] != 'GLOBAL']
        if local: values = local
        return values[0] if len({row['type'].casefold() for row in values}) == 1 else None

    def implementation(self, name, source_file):
        candidates = self.implementations.get(name.casefold(), [])
        local = [entry for entry in candidates if Path(entry['file']).parent == Path(source_file).parent]
        if local: candidates = local
        return candidates[0] if len(candidates) == 1 else None

    def explain(self, call, code, settings, flow, section, chain, depth):
        declared = self.resolve(call['instance'], flow, section)
        name = declared['type'] if declared and call['name'] == call['instance'] else call['name']
        implementation = self.implementation(name, flow['sourceFile'])
        result = {'instance': call['instance'], 'name': name, 'line': call['line'], 'sourceFile': flow['sourceFile']}
        if implementation:
            result.update(kind='Project function block' if implementation['kind'] == 'FUNCTION_BLOCK' else 'Project function',
                          purpose=f'Run the project implementation of {name}.', behavior=[], parameters=[], statuses=[],
                          references=[{'title': name + ' project implementation', 'file': implementation['file']}], notes=[])
            interface = [row for row in self.decls if row['scope'].casefold() == name.casefold() and row['direction'] in {'INPUT', 'OUTPUT', 'IN_OUT'}
                         and Path(row['file']).parent == Path(implementation['file']).parent]
            result['parameters'] = [{'name': row['name'], 'direction': 'IN' if row['direction'] == 'INPUT' else 'OUT' if row['direction'] == 'OUTPUT' else 'IN_OUT',
                                     'dataType': row['type'], 'description': f'Declared {row["direction"].lower()} in {row["file"]}:{row["line"]}.'} for row in interface]
            target = implementation['file']
            if target in chain:
                result['notes'].append('Recursive call: expansion stops at this call; the recursion is not simulated.')
            elif depth >= 5 or self.loaded >= 32 or self.steps >= 1500:
                result['notes'].append('Call expansion limit reached. Open this routine separately to see its remaining sequence.')
            else:
                try:
                    self.loaded += 1
                    nested = self.enrich(self.loader(target), (*chain, target), depth + 1)
                    result['sequences'] = [{'program': part['name'], **lane} for part in nested['sections'] for lane in part['sequences']]
                    titles = [step['title'] for lane in result['sequences'] for step in lane['steps']]
                    if titles and len(titles) <= 6:
                        result['purpose'] = f'{name} runs this sequence: ' + ' → '.join(titles) + '.'
                    result['notes'].extend(nested['notices'])
                except (OSError, ValueError) as error:
                    result['notes'].append(f'The project implementation could not be decoded ({type(error).__name__}).')
        else:
            bindings = self.bindings.get(name.casefold(), set())
            result.update(self.help.lookup(name, next(iter(bindings)) if len(bindings) == 1 else ''))
            result['name'] = name
        if declared:
            result['declaration'] = f'{declared["file"]}:{declared["line"]}'
            # A resolved named instance has persistent state even if a help
            # topic describes it using a positional Automation Basic syntax.
            if result['kind'] == 'Function': result['kind'] = 'Function block'
        values = {item['name'].casefold(): item['value'] for item in settings}
        supplied = arguments(code, call['name'])
        positional = [arg for arg in supplied if not re.match(r'\w+\s*(?::=|=>)', arg)]
        inputs = [param for param in result['parameters'] if param['direction'] in {'IN', 'IN_OUT'}]
        for index, value in enumerate(positional):
            if index < len(inputs): values.setdefault(inputs[index]['name'].casefold(), value)
        for arg in supplied:
            match = re.match(r'(\w+)\s*(?::=|=>)\s*(.*)', arg)
            if match: values.setdefault(match[1].casefold(), match[2])
        result['parameters'] = [{**param, **({'value': values[param['name'].casefold()]} if param['name'].casefold() in values else {})}
                                for param in result['parameters']]
        if result['kind'].endswith('block'):
            result['behavior'] = ['This named instance retains its internal state between calls. Its inputs and outputs belong to ' + call['instance'] + '.', *result['behavior']]
        if name.upper() == 'TON' and any(re.search(r'\bNOT\s+' + re.escape(call['instance']) + r'\.Q\b', value, re.I) for value in values.values()):
            result['behavior'].append(f'In this routine, IN uses NOT {call["instance"]}.Q. After Q becomes TRUE, the next executing call makes IN FALSE and resets Q and ET. A later executing call starts the delay again.')
        if name.upper() == 'TON' and result.get('references') and any(param.get('value') for param in result['parameters']):
            result['behavior'].append('The timer is updated when this call executes. A false surrounding IF condition skips the call; this is different from calling the timer with IN = FALSE.')
        result['handling'] = []
        from python_engine.working_sequence import walk
        for node in walk(section['nodes']):
            condition = node.get('condition', '')
            if re.search(r'\b' + re.escape(call['instance']) + r'\.', condition, re.I):
                for status in result['statuses']:
                    if re.search(r'\b(?:' + re.escape(status['name']) + '|' + re.escape(status['value']) + r')\b', condition):
                        result['handling'].append({'condition': condition, **status})
        return result

    def enrich(self, flow, chain=None, depth=0):
        chain = chain or (flow['sourceFile'],)
        for section in flow['sections']:
            # Resolve ST block instances before rebuilding timer-specific steps.
            for record in records(section['nodes']):
                row = record['row']
                call = operation(row)
                if call:
                    declaration = self.resolve(call['instance'], flow, section)
                    if declaration and declaration['type'].upper() in {'TON', 'TOF', 'TP'}:
                        row['resolvedCall'] = {**call, 'name': declaration['type']}
                elif re.fullmatch(r'(?:CALL\s+|GOSUB\s+)?[A-Za-z_]\w*', row['code'], re.I):
                    name = row['code'].split()[-1]
                    if self.implementation(name, flow['sourceFile']):
                        row['resolvedCall'] = {'name': name, 'instance': name, 'line': row['line']}
            from python_engine.working_sequence import build_working_sequence
            section['sequences'] = build_working_sequence(section)
            calls = list(flow['calls'])
            for record in records(section['nodes']):
                call = operation(record['row'])
                if call and not any(item['instance'].casefold() == call['instance'].casefold() and item['line'] == call['line'] for item in calls):
                    calls.append({**call, 'code': record['row']['code']})
            from python_engine.working_sequence import walk
            for node in walk(section['nodes']):
                condition = node.get('condition', '')
                for name in re.findall(r'\b([A-Za-z_]\w*)\s*\(', STRINGS.sub(' ', condition)):
                    if name.upper() not in {'IF', 'AND', 'OR', 'NOT', 'XOR', 'WHILE'}:
                        calls.append({'name': name, 'instance': name, 'line': node['line'], 'code': condition})
            for lane in section['sequences']:
                self.steps += len(lane['steps'])
                for step in lane['steps']:
                    explanations = []
                    seen = set()
                    for call in calls:
                        if call['line'] not in step['evidenceLines'] and not step['line'] <= call['line'] <= step['endLine']: continue
                        key = (call['name'].casefold(), call['instance'].casefold(), call['line'], call.get('blockId'))
                        if key in seen: continue
                        seen.add(key)
                        settings = step.get('settings', []) if step.get('call', {}).get('instance') == call['instance'] else []
                        # Embedded calls and calls in branch bodies also have
                        # preceding instance settings in the parsed action group.
                        record = next((record for record in records(section['nodes']) if record['row']['line'] == call['line'] and operation(record['row'])
                                       and operation(record['row'])['instance'].casefold() == call['instance'].casefold()), None)
                        if record and not settings: settings = call_step(record)['settings']
                        info = self.explain(call, call['code'], settings, flow, section, chain, depth)
                        call['resolvedName'] = info['name']
                        if step.get('network'):
                            cells = step['network']['diagram']['cells']
                            matching = [cell for cell in cells if cell['kind'] in {'function', 'functionblock'} and
                                        (cell['blockId'] == call['blockId'] if call.get('blockId') else
                                         cell['type'].casefold() == call['name'].casefold() and
                                         (cell.get('instance') or cell.get('name') or cell['type']).casefold() == call['instance'].casefold())]
                            block_ids = {cell['blockId'] for cell in matching}
                            connected = [cell for cell in cells if cell.get('blockId') in block_ids and cell['kind'] in {'function', 'functionblock'}]
                            by_id = {cell['id']: cell for cell in cells}
                            values = {}
                            for edge in step['network']['diagram']['connections']:
                                target, source = by_id[edge['to']], by_id[edge['from']]
                                if target in connected and source['kind'] == 'analog':
                                    for pin in target.get('inputs', []): values[pin.casefold()] = source['name']
                            for cell in connected:
                                condition = connected_condition(cell, step['network']['diagram'])
                                if condition:
                                    for pin in cell.get('inputs', []): values.setdefault(pin.casefold(), condition)
                            if step.get('call', {}).get('instance') == call['instance']:
                                values.update({item['name'].casefold(): item['value'] for item in settings})
                            info['parameters'] = [{**param, **({'value': values[param['name'].casefold()]} if param['name'].casefold() in values else {})}
                                                   for param in info['parameters']]
                        explanations.append(info)
                        if step.get('call', {}).get('instance') == call['instance']:
                            step['call']['name'] = info['name']
                            if info['purpose']:
                                for item in step['actions']:
                                    if item['line'] == call['line'] and item['text'].startswith(('Call ', 'Evaluate ')):
                                        item['text'] = f'{call["instance"]}: {info["purpose"]}'
                            if info['name'].upper() in {'TON', 'TOF', 'TP'}: step['title'] = f'Run {call["instance"]} · {info["name"]} timer'
                    if explanations: step['explanations'] = explanations
            for call in calls:
                if call.get('resolvedName'):
                    call['name'] = call.pop('resolvedName')
                if call not in flow['calls']:
                    flow['calls'].append(call)
        scope = next((part['name'].split(':', 1)[0].strip() for part in flow['sections'] if any(row['scope'].casefold() == part['name'].split(':', 1)[0].strip().casefold() for row in self.decls)), '')
        flow['routineInterface'] = [row for row in self.decls if scope and row['scope'].casefold() == scope.casefold()
                                    and row['direction'] in {'INPUT', 'OUTPUT', 'IN_OUT'} and Path(row['file']).parent == Path(flow['sourceFile']).parent]
        flow['notices'] = list(dict.fromkeys(flow['notices'] + self.read_notices))
        flow['schemaVersion'] = 4
        flow['notice'] = 'Steps follow the selected routine’s source order and preserve its conditions. Called project implementations are expanded where their binding is unambiguous. B&R help explains library behavior; live PLC values and physical execution are not simulated.'
        from python_engine.flow_narrative import add_flow_narrative
        return add_flow_narrative(flow)
