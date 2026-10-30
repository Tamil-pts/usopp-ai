"""Automation Studio ladder geometry shared by MatchView and reports.

Functions/FBs occupy two logical columns. OR marks join the right boundary
of a cell. Header/body rows share a block by logical column, not XML index.
"""
from html import escape
from io import BytesIO
import hashlib
import math
import re
import textwrap
import xml.etree.ElementTree as ET

SCHEMA_VERSION = 3
RENDER_VERSION = 3
SUPPORTED = {'empty', 'line', 'contact', 'coil', 'analog', 'function', 'functionblock'}
BLOCKS = {'function', 'functionblock'}
COL_WIDTH, ROW_HEIGHT, LEFT = 180, 112, 36
COLORS = {'added': '#15803d', 'removed': '#dc2626', 'modified': '#b77900'}
FILLS = {'added': '#dcfce7', 'removed': '#fee2e2', 'modified': '#fef3c7'}


def _tag(node):
    return node.tag.rsplit('}', 1)[-1].casefold()


def _has_input(cell):
    if cell['position'] == 'header' or cell['kind'] == 'empty': return False
    if cell['kind'] in BLOCKS: return bool(cell['inputs'])
    return cell['kind'] != 'analog' or cell['type'].casefold() != 'input'


def _has_output(cell):
    if cell['position'] == 'header' or cell['kind'] == 'empty': return False
    if cell['kind'] in BLOCKS: return bool(cell['outputs'])
    return cell['kind'] != 'analog' or cell['type'].casefold() != 'output'


def _junction(cell):
    return cell['or'] or _has_output(cell)


def network_model(network, index):
    rows = [r for r in network if _tag(r) == 'row']
    cells, open_blocks, warnings = [], {}, []
    for ri, row in enumerate(rows):
        column = 0
        for ci, node in enumerate(row):
            kind = _tag(node)
            span = 2 if kind in BLOCKS else 1
            cell = {'id': f'{index}:{ri}:{ci}', 'row': ri, 'column': column,
                    'xmlColumn': ci, 'span': span, 'kind': kind,
                    'name': node.get('name', ''), 'type': node.get('type', ''),
                    'position': node.get('position', ''),
                    'or': node.get('or', '').casefold() == 'true',
                    'inputs': [p.get('name', '') for p in node if _tag(p) == 'input'],
                    'outputs': [p.get('name', '') for p in node if _tag(p) == 'output'],
                    'pins': [{'direction': _tag(p), **dict(p.attrib)} for p in node
                             if _tag(p) in {'input', 'output'}],
                    'attributes': dict(node.attrib)}
            if kind in BLOCKS:
                key = (column, kind)
                previous = open_blocks.get(key)
                position = cell['position']
                # Older AS XML puts the type on the top segment only. Recover
                # it on the same block column without merging distinct blocks.
                if previous and position in {'top','topbottom'} and previous['position']=='header' and not previous['type'] and cell['type']:
                    previous['type']=cell['type']
                if previous and position in {'top','topbottom','middle','bottom'} and not cell['type']:
                    cell['type']=previous['type']
                continuation = previous and previous['type'] == cell['type']
                if position == 'header' or (position in {'top', 'topbottom'}
                                            and not (continuation and previous['position'] == 'header')):
                    open_blocks[key] = cell
                owner = open_blocks.get(key)
                if owner is None or owner['type'] != cell['type']:
                    owner = cell
                    open_blocks[key] = owner
                    if position in {'middle', 'bottom'}:
                        warnings.append(f'Unmatched {cell["type"]} block segment at row {ri+1}, column {column+1}.')
                cell['instance'] = owner.get('name') or ''
                cell['blockId'] = owner['id']
                if position in {'bottom', 'topbottom'}: open_blocks.pop(key, None)
            if kind not in SUPPORTED:
                warnings.append(f'Unsupported XML element {kind} at row {ri+1}, column {column+1}.')
            cells.append(cell)
            column += span
    connections = []
    by_end = {(c['row'], c['column'] + c['span']): c for c in cells}
    for cell in cells:
        r, c = cell['row'], cell['column']
        left = by_end.get((r, c))
        if _has_input(cell) and left and _has_output(left):
            connections.append({'from': left['id'], 'to': cell['id'], 'kind': 'series', 'column': c})
        if cell['or']:
            boundary = c + cell['span']
            upper = next((by_end[(u, boundary)] for u in range(r-1, -1, -1)
                          if (u, boundary) in by_end and _junction(by_end[(u, boundary)])), None)
            if upper:
                connections.append({'from': upper['id'], 'to': cell['id'], 'kind': 'branch',
                                    'column': boundary, 'edge': 'right'})
            else: warnings.append(f'OR at row {r+1}, column {c+1} has no preceding wire junction.')
    return {'schemaVersion': SCHEMA_VERSION, 'network': index, 'rows': len(rows),
            'columns': max((c['column'] + c['span'] for c in cells), default=0),
            'label': network.get('label', ''), 'comment': network.get('comment', ''),
            'commented': network.get('commented', '0').casefold() in {'1', 'true'},
            'cells': cells, 'connections': connections, 'warnings': warnings}


def coil_condition(diagram, target):
    """Trace Boolean power to a coil using the shared AS wire geometry.

    OR marks join RIGHT boundaries; empty cells carry no horizontal power.
    Blocks and edge contacts are deliberately unresolved, rather than replaced
    by invented Boolean conditions. Side branches not feeding the coil do not
    alter its condition. The result is a source expression, never live values.
    """
    cells = diagram['cells']
    coil = next((c for c in cells if c['kind'] == 'coil' and c['name'] == target), None)
    if not coil or diagram.get('commented'):
        return {'resolved': False, 'reason': 'Coil absent or network disabled.'}
    if diagram.get('warnings'):
        return {'resolved': False, 'reason': '; '.join(diagram['warnings'])}
    parent = {}
    def root(point):
        parent.setdefault(point, point)
        if parent[point] != point: parent[point] = root(parent[point])
        return parent[point]
    def join(a, b): parent[root(b)] = root(a)
    by_id = {c['id']: c for c in cells}
    for edge in diagram['connections']:
        if edge['kind'] == 'branch':
            a, b = by_id[edge['from']], by_id[edge['to']]
            join((a['row'], a['column'] + a['span']), (b['row'], b['column'] + b['span']))
    incoming = {}
    for cell in cells:
        if cell['kind'] == 'empty' or cell.get('position') == 'header': continue
        left = root((cell['row'], cell['column']))
        right = root((cell['row'], cell['column'] + cell['span']))
        incoming.setdefault(right, []).append((left, cell))
    rails = {root((c['row'], 0)) for c in cells if c['column'] == 0 and c['kind'] != 'empty'}
    memo, visiting, used = {}, set(), {}
    def expression(point):
        point = root(point)
        if point in rails: return 'TRUE'
        if point in memo: return memo[point]
        if point in visiting or len(visiting) > 128: raise ValueError('Cyclic or oversized rung topology.')
        visiting.add(point); paths = []
        for left, cell in incoming.get(point, []):
            # The target coil does not feed its own input. Other coils or
            # function outputs in a path require explicit instruction semantics.
            prefix = expression(left)
            if prefix == 'FALSE': continue
            kind, instruction = cell['kind'], cell['type'].casefold()
            if kind == 'line': term = 'TRUE'
            elif kind == 'contact' and instruction in {'open', 'closed'}:
                term = cell['name'] if instruction == 'open' else 'NOT ' + cell['name']
                used[cell['id']] = cell
            else: raise ValueError('Unresolved upstream instruction: ' + (cell.get('instance') or cell['name'] or kind) + ' / ' + cell['type'])
            path = term if prefix == 'TRUE' else prefix if term == 'TRUE' else '(' + prefix + ' AND ' + term + ')'
            if path not in paths: paths.append(path)
        visiting.remove(point)
        value = 'FALSE' if not paths else paths[0] if len(paths) == 1 else '(' + ' OR '.join(paths) + ')'
        if len(value) > 16000: raise ValueError('Rung expression exceeds the bounded trace size.')
        memo[point] = value
        return value
    try:
        value = expression((coil['row'], coil['column']))
        if value == 'FALSE': raise ValueError('No connected left-rail path was established.')
        return {'resolved': True, 'expression': value, 'coilType': coil['type'],
                'inputs': list(dict.fromkeys(c['name'] for c in used.values())),
                'contacts': [{'name': c['name'], 'type': c['type'], 'row': c['row'], 'column': c['column']} for c in used.values()]}
    except ValueError as error:
        return {'resolved': False, 'reason': str(error), 'coilType': coil['type']}


def normalized_model(record):
    """Upgrade saved results from before the logical-column correction."""
    model = record.get('diagram') or record
    if model.get('schemaVersion') == SCHEMA_VERSION: return model
    node = ET.Element('network', {key: str(record.get(key, model.get(key, '')))
                                 for key in ('label', 'comment')})
    node.set('commented', '1' if record.get('commented', model.get('commented')) else '0')
    old = {c['id']: c for c in model.get('cells', [])}
    for ri in range(model.get('rows', 0)):
        row = ET.SubElement(node, 'row')
        for cell in sorted((c for c in old.values() if c['row'] == ri), key=lambda c: c['column']):
            attrs = dict(cell.get('attributes') or {})
            for key in ('name', 'type', 'position'):
                if cell.get(key): attrs[key] = cell[key]
            if cell.get('or'): attrs['or'] = 'true'
            element = ET.SubElement(row, cell['kind'], attrs)
            if cell.get('pins'):
                for pin in cell['pins']:
                    ET.SubElement(element,pin['direction'],{k:v for k,v in pin.items() if k!='direction'})
            else:
                for direction in ('input', 'output'):
                    for name in cell.get(direction + 's', []): ET.SubElement(element, direction, {'name': name})
    upgraded = network_model(node, model.get('network', record.get('index', 1)))
    for cell in upgraded['cells']:
        for key in ('datatype', 'description', 'sourceFile', 'sourceLine', 'declarationFile', 'declarationLine'):
            if key in old.get(cell['id'], {}): cell[key] = old[cell['id']][key]
    return upgraded


def _signature(cell):
    return tuple(str(cell.get(k, '')) for k in
                 ('kind', 'name', 'type', 'position', 'or', 'inputs', 'outputs', 'instance', 'datatype'))


def _datatype(cell):
    if cell.get('datatype'): return cell['datatype']
    if cell['kind'] in {'contact', 'coil'}: return 'BOOL'
    if re.match(r'(?i)^(T|TIME|LTIME)#', cell['name']): return 'TIME'
    match = re.match(r'(?i)^(BOOL|BYTE|WORD|DWORD|LWORD|S?INT|USINT|UINT|UDINT|DINT|REAL|LREAL)#', cell['name'])
    return match[1].upper() if match else ''


def primitives(record, other=None, side='base'):
    model = normalized_model(record)
    peer = normalized_model(other) if other is not None else {}
    cells = model.get('cells', [])
    others = {(c['row'], c['column']): c for c in peer.get('cells', [])}
    used = lambda values: max((c['column'] + c.get('span', 1) for c in values
                              if c['kind'] != 'empty' or c['or']), default=1)
    columns = max(used(cells), used(peer.get('cells', [])))
    # Unused FB outputs stop at a stub, never at the power rail. AS reserves
    # a blank column to the right of a final block.
    if any(c['kind'] in BLOCKS and c['column']+c['span']==columns
           for c in cells+peer.get('cells',[])):
        columns += 1
    width = max(480, LEFT * 2 + columns * COL_WIDTH)
    items, cells_by_id = [], {c['id']: c for c in cells}
    comparison_status = record.get('comparisonStatus', '')
    def state(cell):
        if comparison_status in {'added', 'removed'} and other is None: return comparison_status
        if other is None or (cell['kind'] == 'empty' and not cell['or']): return ''
        counterpart = others.get((cell['row'], cell['column']))
        if counterpart is None or (counterpart['kind'] == 'empty' and not counterpart['or']):
            return 'removed' if side == 'base' else 'added'
        return 'modified' if _signature(cell) != _signature(counterpart) else ''
    def item(kind, cell='', **props):
        value = cells_by_id.get(cell)
        items.append({'kind': kind, 'cell': cell, 'state': state(value) if value else '', **props})
    def line(x1, y1, x2, y2, color='#111827', cell=''):
        item('line', cell, x1=x1, y1=y1, x2=x2, y2=y2, stroke=color)
    def text(x, y, value, cell='', color='#172033', size=12, anchor='start'):
        if value != '': item('text', cell, x=x, y=y, text=str(value), fill=color, size=size, anchor=anchor)
    comment = record.get('comment', model.get('comment', ''))
    comment_lines = [part for value in str(comment).splitlines()
                     for part in textwrap.wrap(value, max(32, int((width-72)/7)))]
    text(LEFT, 22, f'{model.get("network", record.get("index", 1)):04d}',color=COLORS.get(comparison_status,'#172033'))
    if comparison_status in COLORS:
        text(LEFT+62,22,comparison_status.title(),color=COLORS[comparison_status],size=11)
    for i, value in enumerate(comment_lines): text(LEFT, 42+i*15, value, color='#087e27', size=11)
    peer_comment = str((other or {}).get('comment',peer.get('comment','')))
    peer_lines = [part for value in peer_comment.splitlines()
                  for part in textwrap.wrap(value,max(32,int((width-72)/7)))]
    caption_height = 45 + max(len(comment_lines),len(peer_lines))*15
    commented = record.get('commented', model.get('commented', False))
    if commented:
        text(LEFT, caption_height+12, 'Commented network — not executed', color='#64748b')
    if commented or (other or {}).get('commented', peer.get('commented', False)):
        caption_height += 24
    y_rows, y = {}, caption_height + 76
    for r in range(max(model.get('rows', 0), peer.get('rows', 0))):
        y_rows[r] = y
        meaningful = [c for c in cells + peer.get('cells', []) if c['row'] == r
                      and c['kind'] != 'empty' and c['position'] != 'header']
        if meaningful or any(c['row'] == r and c['or'] for c in cells + peer.get('cells', [])): y += ROW_HEIGHT
    height = max(170, y-ROW_HEIGHT+48)
    rail_color = COLORS.get(comparison_status, '#111827') if other is None else '#111827'
    line(LEFT, caption_height+4, LEFT, height-20, rail_color)
    line(width-LEFT, caption_height+4, width-LEFT, height-20, rail_color)
    by_end = {(c['row'], c['column'] + c['span']): c for c in cells}
    groups = {}
    for cell in cells:
        if cell['kind'] in BLOCKS: groups.setdefault(cell['blockId'], []).append(cell)
    for members in groups.values():
        body = [c for c in members if c['position'] != 'header']
        if not body: continue
        first, last = body[0], body[-1]
        x = LEFT + first['column'] * COL_WIDTH
        top, bottom = y_rows[first['row']] - 58, y_rows[last['row']] + 31
        states = {state(c) for c in members} - {''}
        block_state = 'modified' if 'modified' in states else next(iter(states), '')
        color, owner = COLORS.get(block_state, '#111827'), members[0]
        item('rect', owner['id'], x=x+4, y=top, w=first['span']*COL_WIDTH-8,
             h=bottom-top, fill=FILLS.get(block_state, '#fff'), stroke=color, block=True)
        line(x+4, top+22, x+first['span']*COL_WIDTH-4, top+22, color, owner['id'])
        text(x+first['span']*COL_WIDTH/2, top+16, first['type'], owner['id'], color, anchor='middle')
        instance = owner.get('instance') or owner['name']
        if instance and instance != first['type']:
            text(x+first['span']*COL_WIDTH/2, top-8, instance, owner['id'], color, anchor='middle')
    for cell in cells:
        kind, cid = cell['kind'], cell['id']
        if (kind == 'empty' and not cell['or']) or cell['position'] == 'header': continue
        r, c, span = cell['row'], cell['column'], cell['span']
        x, y = LEFT+c*COL_WIDTH, y_rows[r]
        end, cx = x+span*COL_WIDTH, x+COL_WIDTH/2
        cell_state = state(cell)
        color = COLORS.get(cell_state, '#111827')
        if cell_state and kind not in BLOCKS and kind != 'empty':
            item('rect', cid, x=x+3, y=y-70, w=COL_WIDTH-6, h=99, fill=FILLS[cell_state], stroke='none')
        if cell['or']:
            boundary = c + span
            upper = next((by_end[(u, boundary)] for u in range(r-1, -1, -1)
                          if (u, boundary) in by_end and _junction(by_end[(u, boundary)])), None)
            if upper: line(end, y_rows[upper['row']], end, y, color, cid)
        if kind == 'empty': continue
        typ = cell['type'].casefold()
        if kind in BLOCKS:
            for i, pin in enumerate(cell['inputs']):
                text(x+11, y+4+i*16, pin, cid, color, size=11)
                line(x, y+i*16, x+4, y+i*16, color, cid)
            for i, pin in enumerate(cell['outputs']):
                label = pin if pin and not pin.isdigit() else ''
                text(end-11, y+4+i*16, label, cid, color, size=11, anchor='end')
                line(end-4, y+i*16, end, y+i*16, color, cid)
        elif kind == 'line': line(x, y, end, y, color, cid)
        elif kind == 'contact':
            line(x, y, cx-12, y, color, cid); line(cx+12, y, end, y, color, cid)
            line(cx-12, y-14, cx-12, y+14, color, cid); line(cx+12, y-14, cx+12, y+14, color, cid)
            if typ in {'closed', 'normally closed', 'normallyclosed', 'nc', 'negated'}:
                line(cx-18, y+18, cx+18, y-18, color, cid)
            elif typ in {'positive', 'negative'} or 'transition' in typ:
                text(cx, y+4, 'P' if 'positive' in typ else 'N', cid, color, anchor='middle')
        elif kind == 'coil':
            line(x, y, cx-20, y, color, cid); line(cx+20, y, end, y, color, cid)
            for direction in (-1, 1):
                points = [(cx+direction*(13+7*math.cos(t)), y+18*math.sin(t))
                          for t in [-math.pi/2+j*math.pi/16 for j in range(17)]]
                item('polyline', cid, points=points, stroke=color)
            text(cx, y+4, {'set': 'S', 'reset': 'R', 'negated': '/', 'closed': '/',
                          'positive': 'P', 'negative': 'N'}.get(typ, ''), cid, color, anchor='middle')
            if not any(p['row'] == r and p['column'] >= c+span and p['kind'] != 'empty' for p in cells):
                line(end, y, width-LEFT, y, color, cid)
        elif kind == 'analog':
            if typ == 'output': line(x, y, cx, y, color, cid)
            else: line(cx, y, end, y, color, cid)
        else:
            item('rect', cid, x=x+8, y=y-24, w=COL_WIDTH-16, h=48, fill='#fff', stroke='#dc2626')
            text(cx, y+4, kind, cid, '#dc2626', anchor='middle')
        if kind not in BLOCKS and kind != 'line':
            name_lines = textwrap.wrap(cell['name'], 25, break_long_words=True, break_on_hyphens=False) or ['']
            for i, value in enumerate(name_lines):
                text(cx, y-34-(len(name_lines)-i-1)*14, value, cid,COLORS.get(cell_state,'#172033') if cell_state in {'added','removed'} else '#172033',anchor='middle')
            text(cx, y-19, _datatype(cell), cid, COLORS.get(cell_state,'#bc20bc') if cell_state in {'added','removed'} else '#bc20bc', size=10, anchor='middle')
    return width, height, items


def _svg(width, height, items, record, viewbox=None):
    view = viewbox or (0, 0, width, height)
    clip_id='ladderClip'+hashlib.sha256(repr(view).encode()).hexdigest()[:12]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(str(v) for v in view)}" '
           f'width="{view[2]}" height="{view[3]}" role="img" aria-label="Ladder network" '
           f'data-render-version="{RENDER_VERSION}"><rect x="{view[0]}" y="{view[1]}" '
           f'width="{view[2]}" height="{view[3]}" fill="white"/>',
           f'<defs><clipPath id="{clip_id}"><rect x="{view[0]}" y="{view[1]}" width="{view[2]}" height="{view[3]}"/></clipPath></defs><g clip-path="url(#{clip_id})">']
    model = normalized_model(record)
    cells = {c['id']: c for c in model.get('cells', [])}
    for part in items:
        cid, cell = part.get('cell', ''), cells.get(part.get('cell', ''), {})
        title = (f'Network {model.get("network", "")} / Row {cell.get("row", 0)+1} / '
                 f'Column {cell.get("column", 0)+1}: {cell.get("kind", "")} '
                 f'{cell.get("name") or cell.get("instance", "")} {cell.get("type", "")}')
        if cell.get('datatype'): title+=' / '+cell['datatype']
        if cell.get('description'): title+=' / Comment: '+cell['description']
        out.append(f'<g data-cell-id="{escape(cid, quote=True)}" data-change="{part.get("state", "")}"><title>{escape(title)}</title>')
        stroke, kind = part.get('stroke', '#111827'), part['kind']
        if kind == 'line':
            out.append(f'<line x1="{part["x1"]}" y1="{part["y1"]}" x2="{part["x2"]}" y2="{part["y2"]}" stroke="{stroke}" stroke-width="1.8"/>')
        elif kind == 'rect':
            out.append(f'<rect x="{part["x"]}" y="{part["y"]}" width="{part["w"]}" height="{part["h"]}" fill="{part["fill"]}" stroke="{stroke}"/>')
        elif kind == 'polyline':
            out.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in part["points"])}" fill="none" stroke="{stroke}" stroke-width="1.8"/>')
        elif kind == 'text':
            out.append(f'<text x="{part["x"]}" y="{part["y"]}" text-anchor="{part.get("anchor", "start")}" font-family="Arial,sans-serif" font-size="{part.get("size", 12)}" fill="{part["fill"]}">{escape(part["text"])}</text>')
        out.append('</g>')
    out.append('</g></svg>')
    return ''.join(out)


def render_svg(record, other=None, side='base'):
    return _svg(*primitives(record, other, side), record)


def _png(width, height, items, viewbox=None):
    from PIL import Image, ImageDraw, ImageFont
    vx, vy, width, height = viewbox or (0, 0, width, height)
    scale = min(2, 4800/max(width, height))
    image = Image.new('RGB', (max(1, int(width*scale)), max(1, int(height*scale))), 'white')
    draw, fonts = ImageDraw.Draw(image), {}
    def point(x, y): return ((x-vx)*scale, (y-vy)*scale)
    for part in items:
        kind, color = part['kind'], part.get('stroke', '#111827')
        if kind == 'line': draw.line([point(part['x1'], part['y1']), point(part['x2'], part['y2'])], fill=color, width=max(1, int(1.8*scale)))
        elif kind == 'rect':
            draw.rectangle([point(part['x'], part['y']), point(part['x']+part['w'], part['y']+part['h'])],
                           fill=part['fill'], outline=None if color == 'none' else color, width=max(1, int(scale)))
        elif kind == 'polyline': draw.line([point(x, y) for x,y in part['points']], fill=color, width=max(1, int(1.8*scale)))
        elif kind == 'text':
            size = max(8, int(part.get('size', 12)*scale))
            if size not in fonts:
                try: fonts[size] = ImageFont.truetype('arial.ttf', size)
                except OSError: fonts[size] = ImageFont.load_default()
            x, y = point(part['x'], part['y'])
            length = draw.textlength(part['text'], font=fonts[size])
            if part.get('anchor') == 'middle': x -= length/2
            elif part.get('anchor') == 'end': x -= length
            draw.text((x, y-size), part['text'], font=fonts[size], fill=part['fill'])
    out = BytesIO(); image.save(out, format='PNG')
    return out.getvalue()


def render_png(record, other=None, side='base'):
    return _png(*primitives(record, other, side))


def diagram_panels(record, other=None, side='base', max_height=780, max_width=1152):
    """Tile at grid boundaries, keeping symbols and short blocks together.

    A tall block can continue on another sheet. Both comparison panes use
    the same cuts so that a continuation never shifts the paired diagram.
    """
    width, height, items = primitives(record, other, side)
    peer_items = primitives(other, record, 'developed' if side == 'base' else 'base')[2] if other else []
    combined = items + peer_items
    blocks = [p for p in combined if p.get('block')]
    def cuts(total, target, candidates, intervals):
        edges = [0]
        safe = [v for v in candidates if 0 < v < total
                and not any(a < v < b for a,b in intervals)]
        while total - edges[-1] > target:
            available = [v for v in safe if edges[-1] < v <= edges[-1]+target]
            if available:
                stop = max(available)
            else:
                following = [v for v in safe if v > edges[-1]+target]
                if not following: break
                stop = min(following)
            edges.append(stop)
        return edges + [total]
    horizontal = [LEFT+c*COL_WIDTH for c in range(1, int(width/COL_WIDTH)+1)]
    xs = cuts(width, max_width, horizontal, [(p['x'], p['x']+p['w']) for p in blocks])
    # Every wire row has a 112-unit pitch. Cut in its blank lower margin,
    # after symbol labels and before the following row's labels.
    rails = [p for p in combined if p['kind']=='line' and p['x1']==LEFT and p['x2']==LEFT]
    start = min((p['y1'] for p in rails), default=49) + 72
    vertical = [start+r*ROW_HEIGHT+36 for r in range(int(height/ROW_HEIGHT)+1)]
    # Long function blocks retain their identity across continuation sheets.
    ys = cuts(height, max_height, vertical,
              [(p['y'],p['y']+p['h']) for p in blocks if p['h'] < max_height-ROW_HEIGHT])
    nx, ny = len(xs)-1, len(ys)-1
    panels = []
    for row in range(ny):
        for column in range(nx):
            box = (xs[column], ys[row], xs[column+1]-xs[column], ys[row+1]-ys[row])
            panels.append({'column': column, 'row': row, 'columns': nx, 'rows': ny,
                           'width': box[2], 'height': box[3], 'viewbox': box,
                           'svg': _svg(width, height, items, record, box)})
    return panels


def panel_png(record, panel, other=None, side='base'):
    return _png(*primitives(record, other, side), viewbox=panel['viewbox'])


def declaration_symbols(files, source_path, read_text=None):
    """Local program declarations override shared global declarations.

    Other program-local files are excluded to avoid assigning their types to
    an identically named variable in this ladder program.
    """
    from pathlib import Path
    parent = Path(source_path).parent.as_posix().casefold()
    symbols = {}
    candidates = []
    for relative,path in files.items():
        rel=Path(relative)
        if rel.suffix.casefold()!='.var': continue
        local=rel.parent.as_posix().casefold()==parent
        if local or rel.name.casefold()=='global.var' and rel.parent.as_posix().casefold() in {'logical','.'}:
            candidates.append((local,str(relative),path))
    for local,relative,path in sorted(candidates):
        try:
            raw_text=read_text(path) if read_text else Path(path).read_text(encoding='utf-8',errors='replace')
        except OSError: continue
        text=re.sub(r'\(\*.*?\*\)',lambda m:'\n'*m.group().count('\n'),raw_text,flags=re.S)
        raw_lines=raw_text.splitlines()
        for match in re.finditer(r'(?m)^\s*([A-Za-z_]\w*)\s*:\s*([^;\n]+);',text):
            declaration=match.group(2).split(':=',1)[0].strip()
            line=text.count('\n',0,match.start(1))+1
            comments=re.findall(r'\(\*(.*?)\*\)',raw_lines[line-1]) if line<=len(raw_lines) else []
            symbols[match.group(1).casefold()]={'datatype':declaration,'sourceFile':relative,
                                               'sourceLine':line,'description':' '.join(comments).strip()}
    return symbols


def apply_symbols(model, symbols, source_file=''):
    for cell in model['cells']:
        if source_file: cell['sourceFile']=source_file
        symbol=symbols.get(cell['name'].casefold())
        if symbol:
            cell['datatype']=symbol['datatype']
            cell['description']=symbol.get('description','')
            cell['declarationFile']=symbol['sourceFile']
            cell['declarationLine']=symbol['sourceLine']
