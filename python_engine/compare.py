#!/usr/bin/env python3
"""
uSOPp Project Comparison Engine v2.0
Compares two B&R Automation Studio projects (Base vs Developed) and
produces a structured JSON knowledge base of all changes.

Usage:
  python compare.py \
      --base  /path/to/BaseProject \
      --new   /path/to/DevelopedProject \
      --output /path/to/compare_results.json
"""

import sys, os, json, re, difflib, argparse, time, hashlib
import xml.etree.ElementTree as ET
try:
    from python_engine.source_compare import source_diff
    from python_engine.project_info import local_project_details
except ModuleNotFoundError:
    from source_compare import source_diff
    from project_info import local_project_details
from pathlib import Path
from typing import Dict, List, Tuple
try:
    from python_engine.project_paths import IGNORED_PROJECT_DIRS, project_files
except ModuleNotFoundError:
    from project_paths import IGNORED_PROJECT_DIRS, project_files

# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------
LOGIC_EXTS    = {'.st', '.src', '.var', '.typ', '.fun', '.fb', '.prg', '.idc', '.ab', '.c', '.h'}
LADDER_EXTS   = {'.ld'}
SCREEN_EXTS   = {'.page', '.pages', '.layer', '.txtgrp', '.algrp', '.tpr', '.dso'}
HARDWARE_EXTS = {'.hwl', '.iom', '.sw', '.per', '.osl'}
SKIP_DIRS = IGNORED_PROJECT_DIRS
SKIP_EXTS     = {
    '.pkg', '.prg',
    '.bmp', '.png', '.jpg', '.jpeg', '.gif', '.ico',
    '.zip', '.dll', '.exe', '.lib', '.obj', '.pdb',
    '.tsbuildinfo',
}

LOGIC_PATTERNS = [
    r'\bIF\b', r'\bELSIF\b', r'\bELSE\b', r'\bEND_IF\b',
    r'\bCASE\b', r'\bOF\b', r'\bEND_CASE\b',
    r'\bFOR\b', r'\bTO\b', r'\bBY\b', r'\bEND_FOR\b',
    r'\bWHILE\b', r'\bEND_WHILE\b',
    r'\bREPEAT\b', r'\bUNTIL\b',
    r':=', r'\bCALL\b', r'\bRETURN\b', r'\bEXIT\b',
    r'\bTON\b', r'\bTOF\b', r'\bTP\b', r'\bRS\b', r'\bSR\b',
    r'\bCTU\b', r'\bCTD\b', r'\bCTUD\b',
    r'\bMOVE\b', r'\bADD\b', r'\bSUB\b', r'\bMUL\b', r'\bDIV\b',
]


def categorize(rel_path: str) -> str:
    p = Path(rel_path)
    ext = p.suffix.lower()
    if any(part.casefold() in {'libraries','library'} for part in p.parts): return 'config'
    parts_lower = [pt.lower() for pt in p.parts]
    if ext in HARDWARE_EXTS or any(pt in ('cpu.hw', 'hardware') for pt in parts_lower) or p.name.casefold()=='hw.cfg' and parts_lower[0]=='physical':
        return 'hardware'
    if ext in SCREEN_EXTS or any(pt in ('pages', 'hmi', 'visual', 'visualization', 'screen') for pt in parts_lower):
        return 'screen'
    if ext in LOGIC_EXTS or ext in LADDER_EXTS:
        return 'logic'
    return 'config'


def _comparison_file_family(rel_path: str):
    """Return a safe cross-project matching family for a source file."""
    path = Path(rel_path)
    extension = path.suffix.casefold()
    category = categorize(rel_path)
    if category == 'logic' and extension in {'.src', '.st', '.ld'}:
        # AS 2.7 PGS source/ladder containers and AS 4.x ST/XML ladder files
        # are alternate encodings of executable PLC logic.
        return category, 'plc-implementation'
    if category in {'logic', 'screen', 'hardware'}:
        return category, extension
    return None


def _comparison_name_key(rel_path: str):
    family = _comparison_file_family(rel_path)
    if family is None:
        return None
    stem = Path(rel_path).stem.casefold()
    if family == ('logic', 'plc-implementation'):
        # AS 4.x commonly names the main task *Cyclic.st*, while the legacy
        # AS 2.7 source uses the program name without that suffix.
        stem = re.sub(r'cyclic$', '', stem, flags=re.I)
    return (*family, stem)


def align_project_files(base_files: Dict[str, Path], new_files: Dict[str, Path]):
    """Pair exact paths first, then unique compatible filenames across layouts.

    Ambiguous same-name candidates stay as additions/removals. This avoids
    silently comparing unrelated local variables, screens or PLC routines.
    Each row is (display_path, base_relative_path, new_relative_path, method).
    """
    base_by_casefold = {path.casefold(): path for path in base_files}
    new_by_casefold = {path.casefold(): path for path in new_files}
    pairs = []
    matched_base = set()
    matched_new = set()

    for folded in sorted(set(base_by_casefold) & set(new_by_casefold)):
        base_rel, new_rel = base_by_casefold[folded], new_by_casefold[folded]
        pairs.append((new_rel, base_rel, new_rel, 'same relative path'))
        matched_base.add(base_rel)
        matched_new.add(new_rel)

    def candidates(files, already_matched):
        grouped = {}
        for rel in files:
            if rel in already_matched:
                continue
            key = _comparison_name_key(rel)
            if key is not None:
                grouped.setdefault(key, []).append(rel)
        return grouped

    base_names = candidates(base_files, matched_base)
    new_names = candidates(new_files, matched_new)
    for key in sorted(set(base_names) & set(new_names)):
        base_rows, new_rows = base_names[key], new_names[key]
        if len(base_rows) != 1 or len(new_rows) != 1:
            continue
        base_rel, new_rel = base_rows[0], new_rows[0]
        pairs.append((new_rel, base_rel, new_rel, 'same unique filename'))
        matched_base.add(base_rel)
        matched_new.add(new_rel)

    for rel in base_files:
        if rel not in matched_base:
            pairs.append((rel, rel, None, 'base only'))
    for rel in new_files:
        if rel not in matched_new:
            pairs.append((rel, None, rel, 'developed only'))
    return sorted(pairs, key=lambda row: row[0].casefold())


def project_identity(root: Path, selected_hmi: str = '') -> dict:
    """Read identity from project descriptors without using build output."""
    details=local_project_details(root)
    active=details.get('activeConfiguration')
    version=details.get('automationStudioVersion')
    descriptor = next((p for p in root.iterdir() if p.is_file() and p.suffix.casefold() in {'.apj', '.gdm'}), None)
    hmi_objects=details.get('configuredHmiObjects',[])
    screen_folders=details.get('screenFolders',[])
    requested = str(selected_hmi or '').strip()
    available = {name.casefold(): name for name in screen_folders}
    hmi_object = available.get(requested.casefold()) if requested else None
    if hmi_object is None:
        hmi_object = next((available[name.casefold()] for name in hmi_objects if name.casefold() in available), None)
    hmi_object = hmi_object or details.get('screenFolder') or (screen_folders[0] if len(screen_folders)==1 else None)
    return {'project_name': descriptor.stem if descriptor else root.name,
            'automation_studio_version': version,
            'active_configuration': active,
            'plc_type': details.get('plcType'),
            'screen_type': details.get('screenType') if hmi_object==details.get('screenFolder') else None,
            'screen_hardware_file': details.get('screenHardwareFile') if hmi_object==details.get('screenFolder') else None,
            'configured_hmi_objects': hmi_objects,
            'screen_folders': sorted(screen_folders,key=str.casefold),
            'active_hmi': hmi_object,
            'legacy_cpu_root': details.get('legacyCpuRoot'),
            'scope_notice': details.get('logicScopeMessage') or (details.get('configurationMessage','') if not active else '')}


def subroutine_from_path(rel_path: str) -> str:
    """Extract the task/object name from the relative path."""
    parts = Path(rel_path).parts
    # AS 2.7 places task source files together in pgm/<project>/CPU.
    if len(parts)>=4 and parts[0].casefold()=='pgm' and parts[2].casefold()=='cpu':
        return '/'.join((*parts[:3],Path(parts[-1]).stem))
    # B&R structure: Logical/<Task>/<file>  or  Physical/<Config>/<file>
    if len(parts) >= 3:
        return '/'.join(parts[:2])
    if len(parts) == 2:
        return parts[0]
    return '.'


def is_logic_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith('(*') or stripped.startswith('//') or stripped.startswith('//'):
        return False
    return any(re.search(p, stripped, re.I) for p in LOGIC_PATTERNS)


def diff_text(base: str, new: str, max_hunks: int = 80, context: int = 5) -> dict:
    return source_diff(base,new,max_hunks,context)


def _ladder_networks(text: str, symbols=None, source_file='') -> List[dict]:
    """Parse B&R .ld XML networks into compact engineering records.

    Automation Studio wraps the XML with ``PROGRAM`` / ``END_PROGRAM`` text,
    so only the networks element is passed to ElementTree.
    """
    match = re.search(r'(<networks\b.*?</networks>)', text or '', re.I | re.S)
    if not match:
        return []
    try:
        root = ET.fromstring(match.group(1))
    except Exception:
        return []
    records: List[dict] = []
    interesting = {'contact', 'coil', 'analog', 'function', 'functionblock'}
    for index, network in enumerate(
        (node for node in list(root) if node.tag.split('}')[-1].casefold() == 'network'),
        start=1,
    ):
        try: from python_engine.ladder_model import network_model
        except ModuleNotFoundError: from ladder_model import network_model
        diagram=network_model(network,index)
        if symbols or source_file:
            try: from python_engine.ladder_model import apply_symbols
            except ModuleNotFoundError: from ladder_model import apply_symbols
            apply_symbols(diagram,symbols or {},source_file)
        elements = []
        for cell in diagram['cells']:
            kind = cell['kind']
            if kind not in interesting:
                continue
            pins = [f'INPUT:{name}' for name in cell['inputs']]+[f'OUTPUT:{name}' for name in cell['outputs']]
            element = {
                'kind': 'Function block' if kind == 'functionblock' else kind.title(),
                'name': cell['name'] or cell.get('instance',''),
                'type': cell['type'],
                'position': cell['position'],
                'row':cell['row']+1,'column':cell['column']+1,'cellId':cell['id'],
                'branch': 'OR' if cell['or'] else '',
                'pins': pins,
            }
            elements.append(element)
        descriptions = []
        for element in elements:
            identity = element['name'] or element['type'] or 'Unnamed'
            qualifier = element['type'] if element['name'] and element['type'] else ''
            text_value = f"{element['kind']}: {identity}"
            if qualifier:
                text_value += f" [{qualifier}]"
            if element['position']:
                text_value += f" @{element['position']}"
            if element['branch']:
                text_value += f" ({element['branch']})"
            if element['pins']:
                text_value += " {" + ', '.join(element['pins']) + "}"
            descriptions.append(text_value)
        summary = ' -> '.join(descriptions[:18])
        if len(descriptions) > 18:
            summary += f" -> ... (+{len(descriptions) - 18} elements)"
        layout_rows = []
        row_nodes = [child for child in list(network) if child.tag.split('}')[-1].casefold() == 'row']
        for row_index, row in enumerate(row_nodes, start=1):
            tokens = []
            for node in list(row):
                kind = node.tag.split('}')[-1].casefold()
                identity = node.attrib.get('name') or node.attrib.get('type') or kind
                token = f"{kind}:{identity}"
                if str(node.attrib.get('or', '')).casefold() == 'true':
                    token += ':OR'
                tokens.append(token)
            layout_rows.append(f"Row {row_index}: " + ' | '.join(tokens))
        layout = ' / '.join(layout_rows)
        raw = ET.tostring(network, encoding='unicode')
        signature = json.dumps({'label':network.get('label',''), 'comment':network.get('comment',''),
                                'commented':network.get('commented','0'),
                                'cells':[{k:cell.get(k) for k in ('kind','row','column','span','name','type','position','or','pins')}
                                         for cell in diagram['cells'] if cell['kind']!='empty' or cell['or']]},sort_keys=True)
        records.append({
            'index': index,
            'label': network.attrib.get('label', ''),
            'comment': network.attrib.get('comment', ''),
            'commented': str(network.attrib.get('commented', '0')) in {'1', 'true', 'True'},
            'rows': len(row_nodes),
            'diagram':diagram,
            'elements': elements,
            'summary': summary or 'Empty ladder network',
            'layout': layout or 'No row layout',
            '_signature': signature,
        })
    return records


def _aligned_ladder_pairs(base, new):
    """Monotone alignment with stable identities and a small index preference.

    Parameter changes do not rename a network. The index preference resolves
    duplicate timer rungs like an inserted copy preceding a modified copy.
    """
    def identity(record):
        return frozenset((c['kind'], c.get('instance') or c['name'] or c['type'])
                         for c in record['diagram']['cells']
                         if c['kind'] in {'contact','coil','function','functionblock'}
                         or c['kind']=='analog' and c['type'].casefold()=='output')
    left, right = [identity(r) for r in base], [identity(r) for r in new]
    n, m = len(base), len(new)
    if n*m > 1_000_000:
        matcher = difflib.SequenceMatcher(None,[r['_signature'] for r in base],[r['_signature'] for r in new],autojunk=False)
        pairs=[]
        for tag,i1,i2,j1,j2 in matcher.get_opcodes():
            paired=min(i2-i1,j2-j1) if tag in {'equal','replace'} else 0
            pairs.extend((i1+k,j1+k) for k in range(paired))
            pairs.extend((k,None) for k in range(i1+paired,i2))
            pairs.extend((None,k) for k in range(j1+paired,j2))
        return pairs
    previous = list(range(m+1))
    directions = [bytearray([2]*(m+1))]
    for i in range(1,n+1):
        current, direction = [float(i)]+[0.0]*m, bytearray(m+1)
        direction[0]=1
        for j in range(1,m+1):
            a,b=left[i-1],right[j-1]
            union=a|b
            match_cost=0 if a==b else 1.9*(1-len(a&b)/max(1,len(union)))
            match_cost += min(.35,abs(i-j)*.004)
            options=(previous[j-1]+match_cost,previous[j]+1,current[j-1]+1)
            choice=min(range(3),key=lambda k:options[k])
            current[j],direction[j]=options[choice],choice
        previous=current;directions.append(direction)
    pairs=[];i,j=n,m
    while i or j:
        choice=directions[i][j]
        if choice==0:pairs.append((i-1,j-1));i-=1;j-=1
        elif choice==1:pairs.append((i-1,None));i-=1
        else:pairs.append((None,j-1));j-=1
    return list(reversed(pairs))


def parse_ladder_diff(base_text: str, new_text: str, base_symbols=None, new_symbols=None, source_file='') -> dict:
    """Align B&R ladder networks and expose readable Base/Developed changes."""
    base = _ladder_networks(base_text,base_symbols,source_file)
    new = _ladder_networks(new_text,new_symbols,source_file)
    controls: List[dict] = []
    changes: List[dict] = []

    def public(record: dict | None) -> dict | None:
        if record is None:
            return None
        return {key: value for key, value in record.items() if key != '_signature'}

    def append_record(status: str, base_record: dict | None, new_record: dict | None):
        b = public(base_record)
        n = public(new_record)
        for record in (b,n):
            if record is not None: record['comparisonStatus']=status
        b_index = b.get('index') if b else None
        n_index = n.get('index') if n else None
        name = f"Network {b_index}" if b_index is not None else f"Network {n_index}"
        if b_index is not None and n_index is not None and b_index != n_index:
            name = f"Network {b_index} -> {n_index}"
        property_changes = []
        if status == 'modified' and b and n:
            for prop, label in (('label', 'Label'), ('comment', 'Comment'), ('commented', 'Commented'), ('rows', 'Rows'), ('summary', 'Ladder logic'), ('layout', 'Network layout')):
                if b.get(prop) != n.get(prop):
                    property_changes.append({'prop': label, 'group': 'Ladder network', 'from': b.get(prop, ''), 'to': n.get(prop, '')})
        control = {'id': f"{status}:{b_index or 0}:{n_index or 0}:{len(controls) + 1}", 'name': name, 'status': status, 'class': 'Ladder network', 'base': b, 'new': n, 'changes': property_changes}
        controls.append(control)
        if status != 'unchanged':
            changes.append({
                'type': f'network_{status}',
                'name': name,
                'class': 'Ladder network',
                'changes': property_changes,
            })

    for bi,ni in _aligned_ladder_pairs(base,new):
        b=base[bi] if bi is not None else None
        n=new[ni] if ni is not None else None
        status='added' if b is None else 'removed' if n is None else 'unchanged' if b['_signature']==n['_signature'] else 'modified'
        append_record(status,b,n)

    return {
        'parsed': bool(base or new),
        'entity_label': 'Ladder networks',
        'base_network_count': len(base),
        'new_network_count': len(new),
        'controls': controls,
        'changes': changes,
    }


def _xml_controls(text: str) -> Dict[str, dict]:
    """Parse B&R Automation Studio VC .page XML into engineering-friendly
    control records. Property values live in nested <Property Name= Value=>
    elements, not on the Control element itself."""
    if not text.strip():
        return {}
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)
    except Exception:
        return {}

    controls: Dict[str, dict] = {}
    for el in root.iter():
        tag = el.tag.split('}')[-1]
        if tag.lower() not in ('control', 'element', 'widget'):
            continue
        name = el.attrib.get('Name') or el.attrib.get('name') or el.attrib.get('Id') or el.attrib.get('id')
        if not name:
            continue
        props = {}
        for child in list(el):
            ctag = child.tag.split('}')[-1]
            if ctag.lower() == 'property' and child.attrib.get('Name') is not None:
                props[str(child.attrib['Name'])] = str(child.attrib.get('Value', ''))
        class_id = el.attrib.get('ClassId', '')
        type_map = {
            '0x00001002': 'Button',
            '0x00001003': 'HotSpot',
            '0x00001004': 'Text',
            '0x00001007': 'Numeric',
            '0x0000100B': 'String',
        }
        control_type = type_map.get(class_id, tag)
        controls[str(name)] = {
            'name': str(name),
            'class': control_type,
            'class_id': class_id,
            'properties': props,
        }
    return controls


def _hmi_prop_group(prop: str) -> str:
    """Map B&R .page properties into the engineering-oriented groups shown in
    the Automation Studio-style HMI property sheet. Keep the requested groups
    explicit so users can scan Name, StyleClass, Value, Text Group, Runtime,
    Input, Completion, Locking and Appearance without reading raw XML."""
    p = prop.strip().lower().replace(' ', '').replace('_', '')
    if p in {'name', 'id', 'controlname'}:
        return 'Identity'
    if 'bitmap' in p:
        return 'Bitmap / ' + ('Pressed' if 'pressed' in p else 'Released')
    if p in {'styleclass', 'border', 'forecolor', 'backcolor', 'lockedbackcolor',
              'editbackcolor', 'font', 'colormap', 'colordatapoint'} or 'color' in p or p == 'appearance':
        return 'Appearance'
    if p in {'value', 'valuedatapoint', 'minvalue', 'maxvalue', 'mindatapoint',
              'maxdatapoint', 'teachdatapoint', 'simulationvalue', 'unittext'} or p.startswith('value'):
        return 'Value'
    if 'textgroup' in p or p.startswith('text') or p in {'textdatapoint', 'textid', 'languageid'}:
        return 'Text Group'
    if p.startswith('runtime') or p in {'statusdatapoint', 'controlstatus', 'simulation', 'simulationindex', 'simulationvalue', 'eventtrigger', 'onclick', 'controlid'} or 'statusdatapoint' in p:
        return 'Runtime'
    if p.startswith('input') or p in {'input', 'inputmode', 'inputtype', 'inputenabled'}:
        return 'Input'
    if p.startswith('completion') or p in {'completion', 'completiondatapoint', 'oncomplete', 'complete'}:
        return 'Completion'
    if p.startswith('virtualkey') or 'target' in p:
        return 'Navigation / Virtual Key'
    if p.startswith('lock') or p in {'locking', 'lockingdatapoint', 'locked'}:
        return 'Locking'
    if p in {'left','top','width','height','zorder','z-order'}:
        return 'Position'
    if any(x in p for x in ('alignment','fraction','integerdigits','decimaldigits','format')):
        return 'Value'
    if 'description' in p:
        return 'Text Group'
    return 'Other'

def _page_properties(text: str) -> dict:
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)
    except Exception:
        return {}
    props = {}
    for child in list(root):
        if child.tag.split('}')[-1].lower() == 'property' and child.attrib.get('Name'):
            props[str(child.attrib['Name'])] = str(child.attrib.get('Value',''))
    return props


def _structured_hmi_controls(base: Dict[str, dict], new: Dict[str, dict]) -> dict:
    names = sorted(set(base) | set(new))
    controls = []
    changes = []
    for name in names:
        b, n = base.get(name), new.get(name)
        if b is None:
            controls.append({'name':name,'status':'added','class':n.get('class',''),'class_id':n.get('class_id',''),'base':None,'new':n})
            changes.append({'type':'control_added','name':name,'class':n.get('class',''),'class_id':n.get('class_id','')})
            continue
        if n is None:
            controls.append({'name':name,'status':'removed','class':b.get('class',''),'class_id':b.get('class_id',''),'base':b,'new':None})
            changes.append({'type':'control_removed','name':name,'class':b.get('class',''),'class_id':b.get('class_id','')})
            continue
        bp, np = b.get('properties',{}), n.get('properties',{})
        props=[]
        for key in sorted(set(bp)|set(np)):
            bv, nv = bp.get(key), np.get(key)
            equal = bv == nv
            if key == 'ConnectingVisus' and bv is not None and nv is not None:
                equal = {v.strip().casefold() for v in bv.split(',')} == {v.strip().casefold() for v in nv.split(',')}
            if not equal:
                props.append({'prop':key,'group':_hmi_prop_group(key),'from':bv if bv is not None else '—','to':nv if nv is not None else '—'})
        class_changed = b.get('class') != n.get('class') or b.get('class_id') != n.get('class_id')
        if class_changed:
            props.insert(0, {'prop':'Control Type','group':'Identity','from':b.get('class_id') or b.get('class'),'to':n.get('class_id') or n.get('class')})
        status='modified' if props else 'unchanged'
        controls.append({'name':name,'status':status,'class':n.get('class',''),'class_id':n.get('class_id',''),'base':b,'new':n,'changes':props})
        if props:
            changes.append({'type':'control_modified','name':name,'class':n.get('class',''),'class_id':n.get('class_id',''),'changes':props})
    return {'controls':controls,'changes':changes}


def parse_screen_diff(base_text: str, new_text: str) -> dict:
    base = _xml_controls(base_text)
    new = _xml_controls(new_text)
    structured = _structured_hmi_controls(base, new)
    return {
        'parsed': bool(base or new),
        'base_controls': base,
        'new_controls': new,
        'controls': structured['controls'],
        'changes': structured['changes'],
        'base_page_properties': _page_properties(base_text),
        'new_page_properties': _page_properties(new_text),
    }

def parse_hmi_page_diff(base_text: str, new_text: str) -> dict:
    # Compatibility alias used by older compare code.
    return parse_screen_diff(base_text, new_text)


def _element_properties(element) -> Dict[str, str]:
    return {str(child.attrib.get('Name')): str(child.attrib.get('Value', ''))
            for child in list(element)
            if child.tag.split('}')[-1].casefold() == 'property' and child.attrib.get('Name')}


def hmi_xml_equivalent(base_text: str, new_text: str) -> bool:
    """Ignore XML formatting, attribute order and property order, never geometry.

    Preserve control/layer order (stacking), IDs, text values and all properties.
    Line numbers remain source evidence and are not part of HMI identity.
    """
    def canonical(node):
        props, children = [], []
        for child in node:
            value = canonical(child)
            (props if child.tag.split('}')[-1] == 'Property' else children).append(value)
        return (node.tag, tuple(sorted(node.attrib.items())),
                node.text if node.text and node.text.strip() else '',
                tuple(sorted(props)), tuple(children),
                node.tail if node.tail and node.tail.strip() else '')
    try:
        return canonical(ET.fromstring(base_text)) == canonical(ET.fromstring(new_text))
    except ET.ParseError:
        return False


def hmi_screen_layout(text: str, source_path=None, cache=None) -> dict:
    """Static VC layout. Resolve resources only within this visualization/shared folder."""
    cache = cache if cache is not None else {}
    def tag(node):
        return node.tag.split('}')[-1].lower()
    def number(value, default=0):
        try:
            result = float(value)
            return result if abs(result) <= 100000 else default
        except (ValueError, TypeError):
            return default
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {}
    if tag(root) not in {'page', 'pages', 'layer', 'touchpad'}:
        return {}
    target = None
    if source_path:
        for parent in Path(source_path).parents:
            if (parent / 'VCObject.vc').is_file() or (parent / 'Palette.vcr').is_file():
                target = parent
                break
            if parent.name.casefold() == 'logical':
                break
    virtual_keys = {}
    virtual_key_source = None
    if target:
        candidates = [target/'VirtualKeys.vcvk', target/'VirtualKey.vcvk',
                      target/'VCShared'/'VirtualKeys.vcvk', target.parent/'VCShared'/'VirtualKeys.vcvk']
        virtual_key_source = next((path for path in candidates if path.is_file()), None)
        if virtual_key_source:
            key = 'virtual_keys:' + str(virtual_key_source.resolve())
            if key not in cache:
                try:
                    vk_root = ET.fromstring(read_safe(virtual_key_source))
                    definitions = {}
                    for node in vk_root.iter():
                        if tag(node) != 'virtualkey' or not node.get('Name'): continue
                        vk_props = _element_properties(node)
                        actions = []
                        for action in node.iter():
                            if tag(action) != 'keyaction': continue
                            action_props = _element_properties(action)
                            class_id = str(action.get('ClassId') or '').upper()
                            action_type = {'0X00000160':'Change','0X0000016B':'Set datapoint'}.get(class_id, 'Key action')
                            record = {'Type':action_type,'ClassId':class_id,**action_props}
                            for prop,kind in (('Page','Page'),('ValueDatapoint','Variable'),('CompletionDatapoint','Variable')):
                                match = re.search(rf'{kind}\[([^\]]+)\]',record.get(prop,'') or '',re.I)
                                if match: record[prop+' target'] = match.group(1)
                            actions.append(record)
                        definitions[str(node.get('Name')).casefold()]={'name':node.get('Name'),'properties':vk_props,'actions':actions}
                    cache[key]=definitions
                except (ET.ParseError,OSError):
                    cache[key]={}
            virtual_keys=cache[key]
    def resource(path):
        if not path:
            return None
        key = str(path)
        if key not in cache:
            try:
                cache[key] = ET.fromstring(read_safe(path))
            except (ET.ParseError, OSError):
                cache[key] = None
        return cache[key]
    def reference(value, kind, folder, suffix):
        match = re.search(r'Source\[(local|global)\]\.' + kind + r'\[([^\]]+)\]', value or '', re.I)
        if not target or not match:
            return None
        home = target if match[1].lower() == 'local' else target.parent / 'VCShared'
        path = (home / folder / (match[2] + suffix)).resolve()
        # XML references cannot escape their own resource directory.
        if not path.is_relative_to((home / folder).resolve()):
            return None
        return resource(path)
    palette_root = resource(target / 'Palette.vcr') if target else None
    palette = {n.get('Index'): n.get('Value') for n in palette_root.iter()
               if tag(n) == 'palettecolor'} if palette_root is not None else {}
    styles_root = resource(target / 'StyleSheets' / 'Color.vcs') if target else None
    styles = {}
    if styles_root is not None:
        for group in styles_root:
            for style in group:
                if tag(style) == 'styleclass':
                    styles[(group.get('ClassId', '').upper(), style.get('Name'))] = _element_properties(style)
    try:
        from python_engine.hmi_bitmaps import BitmapResolver
    except ModuleNotFoundError:
        from hmi_bitmaps import BitmapResolver
    bitmap_resolver = BitmapResolver(target, cache, source_path)
    def texts(group, index):
        if group is None:
            return {}
        ids = {n.get('Value'): n.get('ID') for n in group.iter() if tag(n) == 'index'}
        text_id = ids.get(str(index))
        if text_id is None:
            return {}
        return {layer.get('LanguageId', 'unknown'): n.get('Value', '')
                for layer in group.iter() if tag(layer) == 'textlayer'
                for n in layer if tag(n) == 'text' and n.get('ID') == text_id}
    layers, warnings = [], []
    type_map = {'0X00001001': 'Shape', '0X00001002': 'Button', '0X00001003': 'HotSpot',
                '0X00001004': 'Text', '0X00001007': 'Numeric', '0X0000100B': 'String',
                '0X00000500': 'TouchPadGrid', '0X0000100E': 'TouchPadEdit', '0X00001018': 'Dropdown'}
    def add_layer(node, key, overrides=None):
        lp = {**_element_properties(node), **(overrides or {})}
        embedded = next((n for n in node if tag(n) == 'textgroup'), None)
        if embedded is None:
            embedded = next((n for n in root if tag(n) == 'textgroup'), None)
        controls = []
        for el in node.iter():
            if tag(el) != 'control':
                continue
            name, cid = el.get('Name', 'Control'), el.get('ClassId', '')
            own = _element_properties(el)
            style = re.search(r'StyleClass\[([^\]]+)\]', own.get('StyleClass', ''))
            inherited = styles.get((cid.upper(), style[1]), {}) if style else {}
            props = {**inherited, **own}
            bitmaps = bitmap_resolver.resolve(props)
            props.update(bitmap_resolver.resolved_properties(bitmaps))
            virtual_key_match = re.search(r'VirtualKey\[([^\]]+)\]', props.get('VirtualKey',''), re.I)
            virtual_key = virtual_keys.get(virtual_key_match.group(1).casefold()) if virtual_key_match else None
            if virtual_key:
                for prop,value in virtual_key.get('properties',{}).items():
                    props['VirtualKey / '+prop]=value
                for action_index,action in enumerate(virtual_key.get('actions',[]),start=1):
                    for prop,value in action.items():
                        props[f'VirtualKey action {action_index} / {prop}']=value
                props['Resolved VirtualKey']=virtual_key.get('name','')
            group = embedded if 'embedded' in props.get('TextGroup', '').lower() else reference(props.get('TextGroup'), 'TextGroup', 'TextGroups', '.txtgrp')
            # Buttons use TextIndex; text/numeric controls often use TextIndexOffset.
            # An explicit value must take precedence over a stylesheet default.
            text_index = own.get('TextIndex', own.get('TextIndexOffset',
                             props.get('TextIndex', props.get('TextIndexOffset'))))
            labels = texts(group, text_index) if text_index is not None and props.get('TextSource', '').lower() != 'none' else {}
            font_root = reference(props.get('Font'), 'Font', 'Fonts', '.fninfo')
            fonts = {n.get('LanguageId', 'en'): _element_properties(n) for n in font_root
                     if tag(n) == 'fontmapping'} if font_root is not None else {}
            binding = re.search(r'Variable\[(.*)\]$', props.get('ValueDatapoint', ''))
            control_id = key + '/' + name
            controls.append({'id': control_id, 'name': name, 'class': type_map.get(cid.upper(), 'Control'),
                             'class_id': cid, 'properties': own, 'effective_properties': props,
                             'virtual_key': virtual_key, 'virtual_key_source': str(virtual_key_source) if virtual_key else '',
                             'bitmaps': bitmaps,
                             'texts': labels, 'fonts': fonts, 'datapoint': binding[1] if binding else props.get('ValueDatapoint', ''),
                             'left': number(props.get('Left')), 'top': number(props.get('Top')),
                             'width': max(0, number(props.get('Width'))), 'height': max(0, number(props.get('Height')))})
        layers.append({'id': key, 'name': node.get('Name', key), 'properties': lp,
                       'left': number(lp.get('Left')), 'top': number(lp.get('Top')),
                       'hidden': lp.get('VisibilityMode', '').lower() == 'hidden',
                       'order': number(lp.get('Z-Order')), 'controls': controls})
    layer_nodes = [n for n in root.iter() if tag(n) in {'layer', 'layerref'}]
    for index, node in enumerate(layer_nodes):
        if tag(node) == 'layer':
            add_layer(node, node.get('Name', f'Layer {index + 1}'))
        else:
            ref = node.get('Source', '')
            resolved = reference(ref, 'Layer', 'Layers', '.layer')
            if resolved is not None:
                add_layer(resolved, ref, _element_properties(node))
            else:
                warnings.append('Unresolved layer: ' + ref)
    if not layers:
        add_layer(root, root.get('Name', 'Default'))
    props = _element_properties(root)
    bitmaps = bitmap_resolver.resolve(props, int(number(props.get('NumLevel'), 1)) if tag(root) == 'touchpad' else 1)
    props.update(bitmap_resolver.resolved_properties(bitmaps))
    return {'name': root.get('Name', Path(source_path).stem if source_path else 'Screen'),
            'width': max(1, number(props.get('Width'), 640)),
            'height': max(1, number(props.get('Height'), 480)),
            'properties': props, 'palette': palette, 'bitmaps': bitmaps, 'bitmap_assets': bitmap_resolver.assets,
            'touchpad_levels': int(number(props.get('NumLevel'), 1)) if tag(root) == 'touchpad' else 1,
            'virtual_key_source':str(virtual_key_source) if virtual_key_source else '', 'layers': sorted(layers, key=lambda l: l['order']),
            'warnings': warnings}


def _hmi_entities(text: str, extension: str) -> Tuple[str, Dict[str, dict]]:
    """Convert B&R HMI XML into records that engineers can review by name."""
    if not text.strip():
        return 'Items', {}
    try:
        root = ET.fromstring(text)
    except Exception:
        return 'Items', {}
    extension = extension.casefold()
    if extension in {'.page', '.pages', '.layer', '.tpr'}:
        label = 'Screen controls' if extension in {'.page', '.pages'} else ('Layer controls' if extension == '.layer' else 'Touch pad controls')
        return label, _xml_controls(text)
    records: Dict[str, dict] = {}
    if extension == '.txtgrp':
        index_by_id = {node.attrib.get('ID', ''): node.attrib.get('Value', '') for node in root.iter()
                       if node.tag.split('}')[-1].casefold() == 'index'}
        # IndexMap also contains intentionally empty rows; preserve their identities.
        for text_id, index in index_by_id.items():
            key = f"Value {index}"
            records[key] = {'name': key, 'index': index, 'class': 'Text value', 'class_id': '',
                            'properties': {'Text ID': text_id}}
        for layer in root.iter():
            if layer.tag.split('}')[-1].casefold() != 'textlayer':
                continue
            language = layer.attrib.get('LanguageId', 'unknown')
            for node in list(layer):
                if node.tag.split('}')[-1].casefold() != 'text':
                    continue
                text_id = node.attrib.get('ID', '')
                key = f"Value {index_by_id.get(text_id, text_id)}"
                record = records.setdefault(key, {'name': key, 'index': index_by_id.get(text_id, text_id), 'class': 'Text value', 'class_id': '', 'properties': {'Text ID': text_id}})
                record['properties'][f'Language: {language}'] = node.attrib.get('Value', '')
        return 'Text group values', records
    element_name = 'alarm' if extension == '.algrp' else 'datapoint'
    label = 'Alarm definitions' if extension == '.algrp' else 'HMI data points'
    for node in root.iter():
        if node.tag.split('}')[-1].casefold() != element_name:
            continue
        identity = node.attrib.get('Index') if extension == '.algrp' else node.attrib.get('Name')
        if identity is None:
            continue
        key = f"Alarm {identity}" if extension == '.algrp' else str(identity)
        props = _element_properties(node)
        for attr, value in node.attrib.items():
            if attr not in {'Index', 'Name'}:
                props[f'Attribute: {attr}'] = str(value)
        records[key] = {'name': key, 'class': 'Alarm' if extension == '.algrp' else 'Data point',
                        'class_id': '', 'properties': props}
    return label, records


def _text_group_snippets(text: str) -> Dict[str, dict]:
    """Keep all snippet properties and their declared kind, scoped to this file."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {}
    kinds = {'0x00002001': 'Numeric', '0x00002002': 'String', '0x00002003': 'Text group'}
    records = {}
    for node in root.iter():
        if node.tag.split('}')[-1].casefold() != 'textsnippet' or not node.get('Name'):
            continue
        name, class_id = node.get('Name'), node.get('ClassId', '')
        props = _element_properties(node)
        for attr, value in node.attrib.items():
            if attr not in {'Name', 'ClassId'}:
                props['Attribute: ' + attr] = value
        records[name] = {'name': name, 'class': kinds.get(class_id.casefold(), node.get('Type') or class_id or 'Unknown'),
                         'class_id': class_id, 'properties': props}
    return records


def parse_structured_hmi_diff(base_text: str, new_text: str, extension: str,
                              base_path=None, new_path=None, cache=None, base_target=None, new_target=None) -> dict:
    base_label, base = _hmi_entities(base_text, extension)
    new_label, new = _hmi_entities(new_text, extension)
    layouts = {}
    if extension.lower() in {'.page', '.pages', '.layer', '.tpr'}:
        layouts = {'base': hmi_screen_layout(base_text, base_path, cache),
                   'new': hmi_screen_layout(new_text, new_path, cache)}
        def records(layout):
            if not layout:
                return {}
            result = {'@page': _record('Screen properties', 'Screen', layout['properties'])}
            for layer in layout['layers']:
                result['@layer/' + layer['id']] = _record(layer['name'], 'Layer', layer['properties'])
                for control in layer['controls']:
                    props = dict(control['effective_properties'])
                    props.update({'Text: ' + lang: value for lang, value in control['texts'].items()})
                    for key in ('ForeColor', 'BackColor'):
                        if props.get(key) in layout['palette']:
                            props['Resolved ' + key] = layout['palette'][props[key]]
                    result[control['id']] = {**control, 'properties': props}
            return result
        base = records(layouts['base']) if layouts['base'] else base
        new = records(layouts['new']) if layouts['new'] else new
    availability=[]
    if extension.lower()=='.dso':
        for side,records,target in [('base',base,base_target),('developed',new,new_target)]:
            for name,record in records.items():
                props=record['properties']
                connections={value.strip().casefold() for value in str(props.get('ConnectingVisus','')).split(',') if value.strip()}
                available=target is not None and target.casefold() in connections
                record['mapping_target']=target
                record['mapping_status']='available' if available else 'missing' if target else 'target_unknown'
                props['Active HMI mapping']='Available' if available else 'Missing in local data source' if target else 'Active HMI selection required'
                availability.append({'side':side,'name':name,'target':target,'status':record['mapping_status'], 'connectingVisus':props.get('ConnectingVisus','')})
                # Target membership is a set: ordering is not a configuration change.

    structured = _structured_hmi_controls(base, new)
    text_group = None
    if extension.casefold() == '.txtgrp':
        snippets = _structured_hmi_controls(_text_group_snippets(base_text), _text_group_snippets(new_text))
        languages = list(dict.fromkeys(key.removeprefix('Language: ') for records in (base, new)
                                      for record in records.values() for key in record['properties']
                                      if key.startswith('Language: ')))
        text_group = {'schemaVersion': 1, 'languages': languages, 'snippets': snippets['controls']}
        structured['changes'].extend({**change, 'type': change['type'].replace('control_', 'text_snippet_')}
                                     for change in snippets['changes'])
    if extension.lower()=='.dso':
        for control in structured['controls']:
            b,n=control.get('base') or {},control.get('new') or {}
            if b.get('mapping_status')=='available' and n.get('mapping_status')=='missing': control['status']='removed'
            elif b.get('mapping_status')=='missing' and n.get('mapping_status')=='available': control['status']='added'
            elif b.get('mapping_status')=='missing' or n.get('mapping_status')=='missing': control['status']='modified'
        if any(item['status']=='missing' for item in availability): structured['changes'].append({'type':'missing_active_hmi_mapping','items':availability})
    statuses = {c['name']: c['status'] for c in structured['controls']}
    for layout in layouts.values():
        for layer in layout.get('layers', []):
            for control in layer['controls']:
                control['status'] = statuses.get(control['id'], 'unchanged')
    try:
        root = ET.fromstring(new_text or base_text)
        object_name = root.attrib.get('Name', '')
        empty_text_group = extension.casefold() == '.txtgrp' and root.tag.split('}')[-1].casefold() == 'textgroup'
    except Exception:
        object_name = ''
        empty_text_group = False
    return {'parsed': bool(base or new or empty_text_group or (text_group and text_group['snippets'])), 'entity_label': new_label or base_label,
            'object_name': object_name, 'controls': structured['controls'],
            'changes': structured['changes'],
            **({'text_group': text_group} if text_group is not None else {}),
            'layouts': layouts,'datasource_availability':availability,
            'base_page_properties': _page_properties(base_text),
            'new_page_properties': _page_properties(new_text)}


def _record(name: str, kind: str, properties: Dict[str, str]) -> dict:
    return {'name': name, 'class': kind, 'class_id': '', 'properties': properties}


def parse_cpu_tasks(text: str) -> Dict[str, dict]:
    records: Dict[str, dict] = {}
    try:
        root = ET.fromstring(text)
    except Exception:
        return records
    for task_class in root.iter():
        if task_class.tag.split('}')[-1].casefold() != 'taskclass':
            continue
        class_name = task_class.attrib.get('Name', '')
        for task in list(task_class):
            if task.tag.split('}')[-1].casefold() != 'task':
                continue
            name = task.attrib.get('Name', '')
            if name:
                records[name] = _record(name, 'Cyclic task', {
                    'Task class': class_name, 'Source': task.attrib.get('Source', ''),
                    'Language': task.attrib.get('Language', ''), 'Memory': task.attrib.get('Memory', ''),
                    'Version': task.attrib.get('Version', ''), 'Disabled': task.attrib.get('Disabled', 'false')})
    return records


def parse_active_objects(text: str) -> Dict[str, dict]:
    records: Dict[str, dict] = {}
    try:
        root = ET.fromstring(text)
    except Exception:
        return records
    for node in root.iter():
        if node.tag.split('}')[-1].casefold() == 'object' and node.attrib.get('Name'):
            name = node.attrib['Name']
            records[name] = _record(name, 'Active object', {'Enabled': node.attrib.get('Enable', ''), 'Memory': node.attrib.get('Memory', '')})
    return records


def parse_permanent_variables(text: str) -> Dict[str, dict]:
    records: Dict[str, dict] = {}
    for match in re.finditer(r'^\s*([A-Za-z_][\w.]*)\s+AT\s+(%M(?:X|B|W|D)?\d+)\s*;', text, re.I | re.M):
        name, address = match.groups()
        records[name] = _record(name, 'Permanent variable', {'Address': address.upper()})
    return records


def _station_number(name: str) -> str:
    match = re.match(r'^(\d+)(?:_|$)', name)
    return match.group(1) if match else ''


def parse_hardware_modules(text: str) -> Dict[str, dict]:
    records: Dict[str, dict] = {}
    try:
        root = ET.fromstring(text)
    except Exception:
        return records
    order = 0
    for node in root.iter():
        if node.tag.split('}')[-1].casefold() != 'module':
            continue
        name, module_type = node.attrib.get('Name', ''), node.attrib.get('Type', '')
        support_identity = re.sub(r'[^A-Z0-9]', '', f'{module_type} {name}'.upper())
        if not name or support_identity.startswith(('X20TB', 'X20BM')) or any(code in support_identity for code in ('X20TB', 'X20BM')):
            continue
        order += 1
        station = _station_number(name)
        key = f'Station {station}' if station else name
        records[key] = _record(key, 'Hardware module', {
            'Station': station, 'Order': str(order), 'Object name': name, 'Module type': module_type,
            'X': node.attrib.get('X', ''), 'Y': node.attrib.get('Y', '')})
    return records


def parse_io_mappings(text: str) -> Dict[str, dict]:
    records: Dict[str, dict] = {}
    pattern = re.compile(r'^\s*(.+?)\s+AT\s+(%[IQ][A-Z]?\."([^"]+)"\.([^;]+))\s*;', re.I | re.M)
    for match in pattern.finditer(text):
        plc_tag, address, module, channel = (part.strip() for part in match.groups())
        station = _station_number(module)
        key = f'{station or module}.{channel}'
        records[key] = _record(key, 'I/O channel', {
            'Station': station, 'Module': module, 'Channel': channel,
            'PLC tag': plc_tag, 'Address': address,
            'Direction': 'Input' if address.upper().startswith('%I') else 'Output'})
    return records


def parse_physical_records(text: str, extension: str) -> Tuple[str, Dict[str, dict]]:
    parsers = {
        '.sw': ('Cyclic task assignments', parse_cpu_tasks),
        '.osl': ('Active software objects', parse_active_objects),
        '.per': ('Permanent variables', parse_permanent_variables),
        '.hwl': ('Hardware modules', parse_hardware_modules),
        '.iom': ('I/O channel mappings', parse_io_mappings),
    }
    title, parser = parsers.get(extension.casefold(), ('Physical configuration', lambda value: {}))
    return title, parser(text)


def parse_hardware_diff(base_text: str, new_text: str, extension: str) -> dict:
    base_title, base = parse_physical_records(base_text, extension)
    new_title, new = parse_physical_records(new_text, extension)
    structured = _structured_hmi_controls(base, new)
    return {'parsed': bool(base or new), 'entity_label': new_title or base_title,
            'controls': structured['controls'], 'changes': structured['changes']}

def walk_project(root: Path, identity: dict) -> Dict[str, Path]:
    result: Dict[str, Path] = {}
    # Build/cache output is not engineering source and can contain very large
    # generated VCShared files. Exclude it from the comparison.
    for p in project_files(root, SKIP_DIRS):
        if not p.is_file():
            continue
        try:
            rel_parts = p.relative_to(root).parts
        except ValueError:
            continue
        if any(part.lower() in SKIP_DIRS for part in rel_parts):
            continue
        if p.suffix.lower() in SKIP_EXTS:
            continue
        # Use the active Physical configuration and its Logical HMI, plus the
        # uniquely resolved legacy CPU folder when this is an AS 2.7 project.
        top = rel_parts[0].casefold() if rel_parts else ''
        if top == 'logical':
            hmi_object = str(identity.get('active_hmi') or '')
            screen_folders = {str(name).casefold() for name in identity.get('screen_folders', [])}
            if len(rel_parts) >= 2 and rel_parts[1].casefold() in screen_folders and rel_parts[1].casefold() != hmi_object.casefold():
                continue
        elif top == 'physical':
            active = str(identity.get('active_configuration') or '')
            if len(rel_parts) < 2 or not active or rel_parts[1].casefold() != active.casefold():
                continue
        elif top == 'pgm':
            legacy_cpu=tuple(str(identity.get('legacy_cpu_root') or '').casefold().split('/'))
            if not identity.get('legacy_cpu_root') or tuple(part.casefold() for part in rel_parts[:3])!=legacy_cpu:
                continue
            if p.suffix.casefold() not in LOGIC_EXTS | LADDER_EXTS | HARDWARE_EXTS:
                continue
        elif len(rel_parts) == 1 and (p.suffix.casefold() in {'.apj', '.gdm'} or p.name.casefold() == 'lastuser.set'):
            pass
        else:
            continue
        rel = str(p.relative_to(root)).replace('\\', '/')
        if top == 'logical' and len(rel_parts) >= 2 and hmi_object and rel_parts[1].casefold() == hmi_object.casefold():
            rel = '/'.join(('Logical', '<HMI>', *rel_parts[2:]))
        if top == 'physical' and len(rel_parts) >= 2:
            # Canonicalize the configuration name so Config1 can be compared
            # directly with a differently named active configuration.
            rel = '/'.join(('Physical', '<ACTIVE>', *rel_parts[2:]))
        result[rel] = p
    return result


def read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return ''


def build_knowledge(root: Path, files: Dict[str, Path], identity: dict) -> dict:
    try:
        from python_engine.project_tree import build_project_tree
    except ModuleNotFoundError:
        from project_tree import build_project_tree
    logic   = sorted(f for f in files if Path(f).suffix.lower() in LOGIC_EXTS | LADDER_EXTS)
    screens = sorted(f for f in files if Path(f).suffix.lower() in SCREEN_EXTS)
    hw      = sorted(f for f in files if Path(f).suffix.lower() in HARDWARE_EXTS or
                     Path(f).name.casefold()=='hw.cfg' and Path(f).parts[0].casefold()=='physical')

    subroutines: Dict[str, List[str]] = {}
    for f in logic:
        sub = subroutine_from_path(f)
        subroutines.setdefault(sub, []).append(Path(f).name)

    screen_names = [Path(f).stem for f in screens]
    hw_files = [Path(f).name for f in hw]

    # Count variables declared (rough)
    var_count = 0
    for f in logic:
        if Path(f).suffix.lower() == '.var':
            text = read_safe(files[f])
            var_count += text.count('VAR')

    def records_for(extension: str, parser) -> List[dict]:
        path = next((files[name] for name in files if Path(name).suffix.casefold() == extension), None)
        records = parser(read_safe(path)) if path else {}
        return [{'name': record['name'], **record.get('properties', {})} for record in records.values()]

    task_assignments = records_for('.sw', parse_cpu_tasks)
    active_objects = records_for('.osl', parse_active_objects)
    permanent_variables = records_for('.per', parse_permanent_variables)
    hardware_modules = records_for('.hwl', parse_hardware_modules)
    io_mappings = records_for('.iom', parse_io_mappings)
    for module in hardware_modules:
        module['name'] = module.get('Object name') or module['name']
    hardware_modules.sort(key=lambda item: (int(item['Station']) if str(item.get('Station', '')).isdigit() else -1,
                                            int(item.get('Order', 0))))
    io_mappings.sort(key=lambda item: (int(item['Station']) if str(item.get('Station', '')).isdigit() else -1,
                                       str(item.get('Module', '')), str(item.get('Channel', ''))))

    return {
        **identity,
        'total_files': len(files),
        'logic_files': len(logic),
        'screen_count': len(screens),
        'hardware_files': len(hw),
        'subroutines': [
            {'path': sub, 'files': flist}
            for sub, flist in sorted(subroutines.items())
        ],
        'screens': screen_names[:200],
        'hardware': hw_files,
        'variable_sections': var_count,
        'task_assignments': task_assignments,
        'active_objects': active_objects,
        'permanent_variables': permanent_variables,
        'hardware_modules': hardware_modules,
        'io_mappings': io_mappings,
        'project_tree': build_project_tree(root, files, identity),
    }


def emit_progress(event: str, **payload) -> None:
    """Emit machine-readable progress without buffering, so the local UI can stream it."""
    msg = {'event': event, **payload}
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def file_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except Exception:
        return b''


def decode_bytes(data: bytes) -> str:
    return data.decode('utf-8', errors='replace')


def decode_project_text(path: Path, data: bytes = None) -> str:
    """Decode readable source text from AS 2.7 binary PGS containers."""
    path = Path(path)
    data = path.read_bytes() if data is None else data
    if path.suffix.casefold() not in {'.src', '.ld'} or not data.startswith(b'B&R') or b'\x00' not in data:
        return decode_bytes(data)

    decoded = data.decode('utf-8', errors='ignore')
    source_markers = [
        r'\(\*\s*PROGRAM\b',
        r'\(\*\s*(?:CYCLIC|INIT)\s+PROGRAM\b',
        r'\b(?:IF|ELSIF|CASE|FOR|WHILE|REPEAT)\s*\(',
        r'\b(?:LDN?|STN?|ANDN?|ORN?|XOR|CAL|RET|JMP|EQ|NE|GT|GE|LT|LE|ADD|SUB|MUL|DIV)\s+\S',
        r'(?m)^\s*[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s*:=',
    ]
    matches = [match for pattern in source_markers
               if (match := re.search(pattern, decoded, re.I)) is not None]
    if matches:
        decoded = decoded[min(match.start() for match in matches):]
    lines = decoded.splitlines()
    printable = [''.join(char for char in line if char == '\t' or char.isprintable()) for line in lines]
    return '\n'.join(printable)


def compare_projects(base_root: Path, new_root: Path, base_hmi: str = '', new_hmi: str = '', detail_dir=None) -> dict:
    started = time.time()
    emit_progress('phase', message='Scanning Base project', phase='scan_base')
    base_identity = project_identity(base_root, base_hmi)
    base_files = walk_project(base_root, base_identity)
    emit_progress('phase', message=f'Base project scanned: {len(base_files):,} files', phase='scan_new')
    new_identity = project_identity(new_root, new_hmi)
    new_files  = walk_project(new_root, new_identity)
    emit_progress('phase', message=f'Developed project scanned: {len(new_files):,} files', phase='compare')

    file_pairs = align_project_files(base_files, new_files)
    total = len(file_pairs)
    counts = {'added': 0, 'removed': 0, 'modified': 0, 'unchanged': 0}
    by_cat = {'logic': 0, 'screen': 0, 'hardware': 0, 'config': 0}
    diffs: List[dict] = []
    same_logic_files: List[dict] = []
    same_screen_files: List[dict] = []
    same_project_files: List[dict] = []
    hmi_resource_cache = {}
    if detail_dir is not None:
        detail_dir = Path(detail_dir)
        detail_dir.mkdir(parents=True, exist_ok=True)
    last_emit = 0.0

    for idx, (rel, base_rel, new_rel, match_method) in enumerate(file_pairs, 1):
        in_base = base_rel is not None
        in_new  = new_rel is not None
        cat = categorize(new_rel or base_rel)
        sub = subroutine_from_path(new_rel or base_rel)
        base_path = base_files.get(base_rel) if base_rel else None
        new_path = new_files.get(new_rel) if new_rel else None

        emit_now = (idx == 1 or idx == total or idx % max(1, total // 100) == 0 or time.time()-last_emit >= 1.0)
        if emit_now:
            emit_progress('progress', current=idx, total=total, percent=round(idx*100/total, 1) if total else 100,
                          category=cat, path=rel, base_path=base_rel or '', new_path=new_rel or '')
            last_emit = time.time()

        if in_base and in_new:
            # Exact byte comparison avoids expensive text decoding for unchanged files.
            bdata = file_bytes(base_path)
            ndata = file_bytes(new_path)
            if bdata == ndata and cat not in {'screen','logic'} and Path(rel).suffix.casefold() not in LADDER_EXTS:
                counts['unchanged'] += 1
                entry = {
                    'path': rel, 'category': cat, 'status': 'unchanged', 'subroutine': sub,
                    'file_name': Path(rel).name,
                    'base_file_name': base_path.name, 'new_file_name': new_path.name,
                    'base_relative_path': base_path.relative_to(base_root).as_posix(),
                    'new_relative_path': new_path.relative_to(new_root).as_posix(),
                    'path_match_method': match_method,
                    'base_lines': 0, 'new_lines': 0, 'added_lines': [], 'removed_lines': [],
                    'hunks': [], 'logic_added': [], 'logic_removed': [],
                    'source_view_available': b'\x00' not in bdata and b'\xef\xbf\xbd' not in bdata,
                }
                if entry['source_view_available']:
                    text = decode_bytes(bdata)
                    payload = {'base_source': text, 'new_source': text,
                               'source_rows': source_diff(text, text)['source_rows']}
                    entry['base_lines'] = entry['new_lines'] = len(text.splitlines())
                    if detail_dir is None:
                        entry.update(payload)
                    else:
                        detail_id = hashlib.sha256(('project:' + rel).encode('utf-8')).hexdigest()
                        with (detail_dir / (detail_id + '.json')).open('w', encoding='utf-8') as stream:
                            json.dump(payload, stream, ensure_ascii=False, separators=(',', ':'))
                        entry['project_detail_id'] = detail_id
                same_project_files.append(entry)
                continue
            base_text = decode_project_text(base_path, bdata)
            new_text  = decode_project_text(new_path, ndata)
            logic_diff = source_diff(base_text,new_text) if cat=='logic' else None
            status = 'unchanged' if bdata == ndata or logic_diff is not None and not logic_diff['hunks'] else 'modified'
        elif in_new:
            status = 'added'
            new_text = decode_project_text(new_path, file_bytes(new_path))
            base_text = ''
        else:
            status = 'removed'
            base_text = decode_project_text(base_path, file_bytes(base_path))
            new_text = ''

        if cat=='logic' and not (in_base and in_new):
            logic_diff = source_diff(base_text,new_text)
        parsed_screen = None
        if cat == 'screen':
            screen_extension = Path(new_rel or base_rel).suffix.lower()
            parsed_screen = parse_structured_hmi_diff(base_text, new_text, screen_extension,
                                                       base_path, new_path, hmi_resource_cache, base_identity.get('active_hmi'), new_identity.get('active_hmi'))
            if in_base and in_new and (screen_extension=='.dso' or base_text == new_text or hmi_xml_equivalent(base_text, new_text)):
                status = 'modified' if parsed_screen['changes'] else 'unchanged'

        counts[status] += 1
        if cat in by_cat and status != 'unchanged':
            by_cat[cat] += 1

        entry: dict = {
            'path': rel, 'category': cat, 'status': status, 'subroutine': sub,
            'file_name': Path(rel).name, 'base_lines': 0, 'new_lines': 0,
            'base_file_name': base_path.name if base_path else None,
            'new_file_name': new_path.name if new_path else None,
            'base_relative_path': str(base_path.relative_to(base_root)).replace('\\','/') if base_path else None,
            'new_relative_path': str(new_path.relative_to(new_root)).replace('\\','/') if new_path else None,
            'path_match_method': match_method,
            'added_lines': [], 'removed_lines': [], 'hunks': [],
            'logic_added': [], 'logic_removed': [],
            'source_view_available': Path(rel).suffix.lower() in LOGIC_EXTS | LADDER_EXTS,
            'ladder_source_only': Path(rel).suffix.lower() in LADDER_EXTS,
        }
        if cat=='logic':
            entry['source_rows']=logic_diff['source_rows']
        if parsed_screen is not None:
            if detail_dir is None:
                entry['parsed_screen'] = parsed_screen
            else:
                detail_id = hashlib.sha256(rel.encode('utf-8')).hexdigest()
                with (detail_dir / (detail_id + '.json')).open('w', encoding='utf-8') as stream:
                    json.dump(parsed_screen, stream, ensure_ascii=False, separators=(',', ':'))
                entry['screen_detail_id'] = detail_id
        # Unchanged ladder files need the same network model as changed files.
        if (base_path and new_path and Path(base_rel).suffix.casefold() in LADDER_EXTS
                and Path(new_rel).suffix.casefold() in LADDER_EXTS):
            try:
                try: from python_engine.ladder_model import declaration_symbols
                except ModuleNotFoundError: from ladder_model import declaration_symbols
                parsed_ladder = parse_ladder_diff(base_text, new_text,
                    declaration_symbols(base_files,base_rel),declaration_symbols(new_files,new_rel),rel)
                entry['ladder_structured_available'] = bool(parsed_ladder.get('parsed'))
                if status == 'unchanged' and detail_dir is not None:
                    detail_id = hashlib.sha256(('ladder:' + rel).encode('utf-8')).hexdigest()
                    with (detail_dir / (detail_id + '.json')).open('w', encoding='utf-8') as stream:
                        json.dump(parsed_ladder, stream, ensure_ascii=False, separators=(',', ':'))
                    entry['ladder_detail_id'] = detail_id
                else:
                    entry['parsed_ladder'] = parsed_ladder
                ladder_changes = parsed_ladder.get('changes') or []
                entry['logic_added'] = [f"{change.get('name')}: added ladder network"
                    for change in ladder_changes if change.get('type') == 'network_added'][:60]
                entry['logic_removed'] = [f"{change.get('name')}: removed ladder network"
                    for change in ladder_changes if change.get('type') == 'network_removed'][:60]
            except Exception as error:
                entry['ladder_parse_error'] = str(error)
        if status == 'unchanged':
            entry['base_lines'] = len(base_text.splitlines())
            entry['new_lines'] = len(new_text.splitlines())
            if cat=='logic':
                entry.update(base_source=base_text,new_source=new_text,source_rows=logic_diff['source_rows'])
                same_logic_files.append(entry)
            elif cat=='screen': same_screen_files.append(entry)
            else:
                entry.update(base_source=base_text,new_source=new_text,source_rows=source_diff(base_text,new_text)['source_rows'])
                same_project_files.append(entry)
            continue

        if status == 'modified':
            # Keep detailed SequenceMatcher diffs for engineering logic. Configuration,
            # generated and unusually large files use a bounded sample so one file cannot
            # hold the whole comparison at a high percentage for minutes.
            base_line_count = len(base_text.splitlines())
            new_line_count = len(new_text.splitlines())
            if entry['source_view_available']:
                entry['base_source'] = base_text
                entry['new_source'] = new_text
            detailed_limit = 20000 if cat == 'logic' else 5000
            if cat == 'screen' and parsed_screen and parsed_screen.get('parsed'):
                entry['base_lines'] = base_line_count
                entry['new_lines'] = new_line_count
                entry['diff_note'] = 'HMI changes are compared by properties; select the file to load details.'
            elif max(base_line_count, new_line_count) > detailed_limit:
                entry['base_lines'] = base_line_count
                entry['new_lines'] = new_line_count
                entry['large_file'] = True
                base_lines = base_text.splitlines()
                new_lines = new_text.splitlines()
                entry['added_lines'] = [[i+1, l] for i,l in enumerate(new_lines[:80])]
                entry['removed_lines'] = [[i+1, l] for i,l in enumerate(base_lines[:80])]
                entry['hunks'] = []
                entry['diff_note'] = f'Large {cat} file: detailed diff bounded to keep comparison responsive.'
            else:
                emit_progress('detail', message=f'Detailed diff: {rel}', phase='diff', category=cat, path=rel)
                d = logic_diff if cat=='logic' else diff_text(base_text, new_text)
                entry['base_lines'] = d['base_lines']; entry['new_lines'] = d['new_lines']
                entry['added_lines'] = [[ln, l] for ln, l in d['added']]
                entry['removed_lines'] = [[ln, l] for ln, l in d['removed']]
                entry['hunks'] = d['hunks']
                # Structured XML summaries for HMI and hardware files
                ext = Path(rel).suffix.lower()
                if cat == 'hardware' and ext in HARDWARE_EXTS:
                    ph = parse_hardware_diff(base_text, new_text, ext)
                    if ph: entry['parsed_hardware'] = ph
            if cat == 'logic':
                entry['logic_added'] = [l for _, l in entry['added_lines'] if is_logic_line(l)][:60]
                entry['logic_removed'] = [l for _, l in entry['removed_lines'] if is_logic_line(l)][:60]

        elif status == 'added':
            lines = new_text.splitlines()
            entry['new_lines'] = len(lines)
            entry['added_lines'] = [[i + 1, l] for i, l in enumerate(lines[:300])]
            if entry['source_view_available']:
                entry['base_source'] = ''
                entry['new_source'] = new_text
            if cat == 'logic': entry['logic_added'] = [l for l in lines if is_logic_line(l)][:60]

        elif status == 'removed':
            lines = base_text.splitlines()
            entry['base_lines'] = len(lines)
            entry['removed_lines'] = [[i + 1, l] for i, l in enumerate(lines[:300])]
            if entry['source_view_available']:
                entry['base_source'] = base_text
                entry['new_source'] = ''
            if cat == 'logic': entry['logic_removed'] = [l for l in lines if is_logic_line(l)][:60]

        # Structured parsed changes for screen and hardware files
        if entry['status'] == 'modified':
            if cat == 'hardware' and in_base and in_new:
                try:
                    bt = read_safe(base_path); nt = read_safe(new_path)
                    entry['parsed_hardware'] = parse_hardware_diff(bt, nt, Path(rel).suffix.lower())
                except Exception: pass
        elif entry['status'] == 'added' and cat == 'hardware' and in_new:
            try:
                entry['parsed_hardware'] = parse_hardware_diff('', read_safe(new_path), Path(rel).suffix.lower())
            except Exception: pass
        elif entry['status'] == 'removed' and cat == 'hardware' and in_base:
            try:
                entry['parsed_hardware'] = parse_hardware_diff(read_safe(base_path), '', Path(rel).suffix.lower())
            except Exception: pass

        diffs.append(entry)

    elapsed = round(time.time() - started, 2)
    emit_progress('complete', current=total, total=total, percent=100, elapsed=elapsed,
                  message=f'Comparison complete in {elapsed:.1f}s')
    return {
        'status': 'success',
        'summary': {'total_in_base': len(base_files), 'total_in_new': len(new_files),
                    'added': counts['added'], 'removed': counts['removed'],
                    'modified': counts['modified'], 'unchanged': counts['unchanged'],
                    'by_category': by_cat, 'elapsed_seconds': elapsed},
        'projects': {'base': base_identity, 'developed': new_identity},
        'knowledge': {'base': build_knowledge(base_root, base_files, base_identity),
                      'developed': build_knowledge(new_root, new_files, new_identity)},
        'same_logic_files': same_logic_files,
        'same_screen_files': same_screen_files,
        'same_project_files': same_project_files,
        'diffs': diffs,
    }


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='uSOPp Project Comparison Engine v2.0')
    ap.add_argument('--base',   required=True, help='Base project root folder')
    ap.add_argument('--new',    required=True, help='Developed project root folder')
    ap.add_argument('--output', required=True, help='Output JSON file path')
    ap.add_argument('--base-hmi', default='', help='Selected Base visualization folder')
    ap.add_argument('--new-hmi', default='', help='Selected Developed visualization folder')
    args = ap.parse_args()

    base_root = Path(args.base)
    new_root  = Path(args.new)

    if not base_root.exists():
        sys.exit(json.dumps({'status': 'error', 'message': f'Base project not found: {args.base}'}))
    if not new_root.exists():
        sys.exit(json.dumps({'status': 'error', 'message': f'Developed project not found: {args.new}'}))

    result = compare_projects(base_root, new_root, args.base_hmi, args.new_hmi,
                              Path(args.output).parent / 'hmi_details')
    with Path(args.output).open('w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, separators=(',', ':'))
    # Brief summary to stdout for the server to capture
    print(json.dumps({
        'status':   result['status'],
        'modified': result['summary']['modified'],
        'added':    result['summary']['added'],
        'removed':  result['summary']['removed'],
        'unchanged':result['summary']['unchanged'],
    }))
