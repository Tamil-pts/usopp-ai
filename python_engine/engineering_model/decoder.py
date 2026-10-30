"""Adapters to the existing language parsers; Python data, never executable PLC translation."""
from bisect import bisect_right
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from python_engine.function_flow import _text_flow, _ladder_flow, _mask_comments, TOKEN, BASIC_TOKEN
from python_engine.c_control_flow import c_flow, TOKEN as C_TOKEN
from python_engine.project_analysis import _mask

EXECUTABLE = {'.st', '.ab', '.ld', '.src', '.c'}
XML = {'.prg', '.pkg', '.apj', '.sw', '.page', '.layer', '.txtgrp', '.hw', '.xml'}
SUPPORTED = EXECUTABLE | XML | {'.var', '.typ', '.fun', '.h', '.iom', '.dso', '.set', '.lby'}
LANGUAGES = {'.st': 'ST', '.src': 'ST', '.ab': 'AB', '.ld': 'Ladder', '.c': 'C'}


def decode(file, text):
    suffix = Path(file).suffix.casefold()
    language = LANGUAGES.get(suffix, 'XML' if suffix in XML else 'declaration/configuration')
    notices, sections, calls = [], [], []
    if suffix == '.c': sections, _, calls, notices = c_flow(text, file)
    elif suffix == '.ld': sections, _, calls, notices = _ladder_flow(text, file)
    elif suffix in {'.st', '.src', '.ab'}: sections, _, calls, notices = _text_flow(text, file, suffix == '.ab')
    tree = None
    if suffix in XML or text.lstrip().startswith('<?xml'):
        try: tree = ET.fromstring(text)
        except ET.ParseError as error: notices.append('XML structure unresolved: ' + str(error))
    if suffix in {'.h', '.fun', '.var', '.typ', '.iom', '.dso', '.lby', '.set'}:
        # Declarations, bindings and types are supplied by the existing index.
        # Their presence is not a claim that a C header/library was executed.
        status = 'indexed-fields'
    elif suffix in XML: status = 'structured' if tree is not None else 'partial'
    elif suffix in EXECUTABLE: status = 'partial' if notices else 'parsed'
    else: status = 'unsupported'
    return {'language': language, 'sections': sections, 'calls': calls, 'notices': notices,
            'status': status, 'tree': tree}


def lexical_tokens(file, text):
    """Source tokens, distinct from LLM subword tokens and later concept tags."""
    suffix = Path(file).suffix.casefold()
    clean = _mask(text) if suffix in {'.c', '.h'} else _mask_comments(text, suffix == '.ab')
    lexer = C_TOKEN if suffix in {'.c', '.h'} else BASIC_TOKEN if suffix == '.ab' else TOKEN
    newlines = [m.start() for m in re.finditer('\n', text)]
    for number, match in enumerate(lexer.finditer(clean)):
        value = match[0]
        if not value.strip(): continue
        row = bisect_right(newlines, match.start()) + 1
        previous = newlines[row-2] if row > 1 else -1
        kind = 'identifier' if re.fullmatch(r'[A-Za-z_]\w*', value) else 'literal' if value[:1] in {'\"', "'"} or value[:1].isdigit() else 'syntax'
        yield number, row, match.start()-previous, kind, value


def section_ranges(text, sections):
    """Use explicit wrappers/C function positions to partition a physical file."""
    headers = list(re.finditer(r'(?im)^\s*(PROGRAM|FUNCTION_BLOCK|FUNCTION)\s+([A-Za-z_]\w*)[^\n]*', _mask(text)))
    result = []
    for index, section in enumerate(sections):
        matching_header=any(h[2]==section['name'].split()[0].split(':')[0] for h in headers)
        if not section.get('nodes') and not matching_header and not (len(sections)==1 and len(headers)==1) and section.get('kind')!='function':continue
        start = section.get('line') or min((n['line'] for n in section['nodes']),default=1)
        finish = max((n.get('endLine', n['line']) for n in section['nodes']),default=start)
        header = next((h for h in headers if h[2] == section['name'].split()[0].split(':')[0] and text.count('\n', 0, h.start())+1 <= start), None)
        if header is None and len(headers)==1 and all(node['kind']=='network' for node in section['nodes']): header=headers[0]
        declared_kind = header[1].casefold() if header else 'function' if section.get('kind') == 'function' else 'routine'
        if header:
            start = text.count('\n', 0, header.start())+1
            end = re.search(r'\bEND_' + header[1] + r'\b', text[header.end():], re.I)
            if end: finish = text.count('\n', 0, header.end()+end.end())+1
        name = header[2] if header else section['name'].split(':')[0].strip()
        phase = {'_INIT': 'initialization', '_CYCLIC': 'cyclic', '_EXIT': 'exit'}.get(name.upper(), 'unresolved')
        result.append({**section, 'name':name, 'first': start, 'last': finish, 'declaredKind': declared_kind,
                       'phase': phase, 'ordinal': index})
    return result
