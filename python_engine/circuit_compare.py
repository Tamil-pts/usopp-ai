"""Source-linked electrical PDF comparison. Does not infer electrical connectivity.

Text/table extraction and tolerant raster comparison are independent evidence
channels. A changed drawing is not an electrical safety or continuity verdict.
PDFium calls are serialized: the underlying library is not thread-safe.
"""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import json
import math
import re
import threading
import time
import unicodedata

import numpy as np
from PIL import Image, ImageFilter
import pdfplumber
import pypdfium2 as pdfium
from pypdf import PdfReader
from python_engine.circuit_pdf import extraction_copy
from python_engine.circuit_visual import compare_visual, visible_text_change
from python_engine.circuit_objects import build_scene, uncovered_lines

ENGINE_VERSION = '2.1'
MAX_PAGES = 200
MAX_WORDS = 40000
MAX_CELLS = 20000
RENDER_WIDTH = 1600
PDFIUM_LOCK = threading.RLock()
CATEGORIES = ('Connections', 'Components', 'Cable specifications', 'Terminal mapping',
              'BOM', 'Drawing / annotations', 'Revision information')
IMPACTS = {
    'Connections': ('A printed connection or destination entry changed. This may affect the intended wire destination.',
                    'Verify both terminal references, pin numbers and continuity against the drawing and installation.'),
    'Components': ('A component reference or description changed. Its role or replacement needs checking.',
                   'Check the component specification, rating, pinout and associated references.'),
    'Cable specifications': ('A cable size, length or shielding annotation changed.',
                            'Check conductor count, cross-section, routing length, shielding and terminations.'),
    'Terminal mapping': ('A printed terminal or pin annotation changed; PDF text alone does not prove a net connection.',
                         'Follow the drawn wire to both ends and verify the terminal and pin assignments.'),
    'BOM': ('A material-list cell changed. Procurement or assembly instructions may be affected.',
            'Verify the material number, quantity and drawing callout against the released BOM.'),
    'Drawing / annotations': ('Drawing text or geometry changed. The electrical effect is not established by pixel comparison.',
                               'Inspect the highlighted symbols, wires, junctions and annotations in both drawings.'),
    'Revision information': ('A drawing identity, revision or date annotation changed.',
                             'Check the revision register, drawing number and applicability before release.'),
}


def normalized(text):
    text = unicodedata.normalize('NFKC', str(text or ''))
    text = text.translate(str.maketrans({'\u00ad': '-', '\u2010': '-', '\u2011': '-', '\u2012': '-',
                                       '\u2013': '-', '\u2014': '-', '\u2212': '-', '\xa0': ' ', '×': 'x'}))
    return re.sub(r'\s+', ' ', text).strip()


def key(text):
    value = normalized(text).casefold()
    try:
        return str(Decimal(value).normalize()) if re.fullmatch(r'[-+]?\d+(?:\.\d+)?', value) else re.sub(r'\s+', '', value)
    except InvalidOperation:
        return re.sub(r'\s+', '', value)


def uncertain_text(text):
    return bool(re.search(r'[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]|\(cid:\d+\)', str(text)))


def box(value, width, height):
    x0, y0, x1, y1 = value
    return [round(max(0, min(1, x0 / width)), 6), round(max(0, min(1, y0 / height)), 6),
            round(max(0, min(1, x1 / width)), 6), round(max(0, min(1, y1 / height)), 6)]


def union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def distance(a, b):
    return math.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2)


def intersects(a, b, margin=0):
    return a[0] <= b[2] + margin and b[0] <= a[2] + margin and a[1] <= b[3] + margin and b[1] <= a[3] + margin


def source(page, text, bbox, **extra):
    return {'page': page, 'text': text, 'bbox': bbox, **extra}


def _segments(words, width, height):
    """Group horizontal words by baseline and nearby spacing, not PDF content order."""
    # CAD exporters may store a rotated label either as rotated glyphs or as
    # separate upright glyphs in a vertical stack. Compare the same reading
    # direction in both, retaining a warning rather than inventing a new tag.
    words = [dict(w) for w in words]
    consumed = set()
    vertical = []
    singles = [(i, w) for i, w in enumerate(words) if len(w['text']) == 1]
    for index, word in singles:
        if index in consumed: continue
        column = [(i, w) for i, w in singles if i not in consumed
                  and abs((w['x0'] + w['x1'] - word['x0'] - word['x1']) / 2) < 1.5
                  and abs(w['top'] - word['top']) < 45]
        column.sort(key=lambda v: v[1]['top'])
        group = []
        for item in column:
            if group and item[1]['top'] - group[-1][1]['bottom'] > 2: break
            group.append(item)
        rotated_digits = group and all(w['text'].isdigit() and (w['x1']-w['x0']) > 1.2*(w['bottom']-w['top']) for _,w in group)
        if len(group) >= 2 and (rotated_digits or any(re.search('[A-Za-z]', w['text']) for _, w in group)):
            bounds = union([[w['x0'], w['top'], w['x1'], w['bottom']] for _, w in group])
            vertical.append({'text': ''.join(w['text'] for _, w in group), 'x0': bounds[0], 'top': bounds[1],
                             'x1': bounds[2], 'bottom': bounds[3], 'upright': False})
            consumed.update(i for i, _ in group)
    words = [w for i, w in enumerate(words) if i not in consumed] + vertical
    lines = []
    for word in sorted(words, key=lambda w: (round(w['top'], 1), w['x0'])):
        if not word.get('upright', True):
            lines.append([word])
            continue
        target = next((line for line in reversed(lines[-8:]) if abs(line[0]['top'] - word['top']) < 2.1
                       and line[0].get('upright', True)), None)
        if target is None:
            lines.append([word])
        else:
            target.append(word)
    segments = []
    for line in lines:
        groups = [[]]
        for word in sorted(line, key=lambda w: w['x0']):
            if groups[-1] and word['x0'] - groups[-1][-1]['x1'] > max(12, word['bottom'] - word['top']) :
                groups.append([])
            groups[-1].append(word)
        for group in groups:
            raw = ' '.join(w['text'] for w in group)
            bounds = union([[w['x0'], w['top'], w['x1'], w['bottom']] for w in group])
            segments.append({'text': normalized(raw), 'bbox': box(bounds, width, height),
                             'uncertain': uncertain_text(raw) or not group[0].get('upright', True)
                                          or (raw.isdigit() and bounds[2]-bounds[0]>1.2*(bounds[3]-bounds[1]))
                                          or (len(raw)>1 and not re.search(r'\s',raw) and bounds[2]-bounds[0]<.8*(bounds[3]-bounds[1])),
                             'tokens':[{'text':normalized(w['text']),'bbox':box((w['x0'],w['top'],w['x1'],w['bottom']),width,height),
                                        'uncertain':uncertain_text(w['text']) or not w.get('upright',True)} for w in group]})
    return segments


def _category(text):
    value = normalized(text)
    if re.search(r'\b(?:REV(?:ISION)?|ALTERATION|DRAWING\s*(?:NO|NUMBER)|DRG|DATED|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b', value, re.I):
        return 'Revision information'
    if re.search(r'\b(?:\d+\s*[xX]\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:SQMM|mm2|mm²|mm|m)\b|SHIELD)', value, re.I):
        return 'Cable specifications'
    if re.search(r'\b(?:X[A-Z]*\d*|[MBKSQUY]\d+)[-:]\w+(?:\([^)]*\))?', value, re.I):
        return 'Terminal mapping'
    if re.search(r'\b(?:FROM|TO)\s+(?:X[A-Z]*\d+|[MBKSQUY]\d+)', value, re.I):
        # Explicit printed destination/caption, not a reconstructed wire/net.
        return 'Connections'
    if re.search(r'\b(?:[MBKSQUY]\d+|X[A-Z]*\d+|MOTOR|SENSOR|RELAY|CONNECTOR|SWITCH)\b', value, re.I):
        return 'Components'
    return 'Drawing / annotations'


def _tables(page):
    tables = []
    count = 0
    for table in page.find_tables(table_settings={'snap_tolerance': 3, 'join_tolerance': 3}):
        values = table.extract(x_tolerance=2, y_tolerance=2)
        if not values or len(values) < 2 or max(map(len, values)) < 3:
            continue
        header = ' '.join(str(cell or '') for row in values[:6] for cell in row)
        is_bom = bool(re.search(r'BOM|MATERIAL|DESIGNATION|CABLE\s*DRAWING|PART\s*(?:NO|NUMBER)', header, re.I))
        is_connections = bool(re.search(r'TERMINAL|DESTINATION|SIDE\s*[- ]?[AB]|WIRE\s*(?:NO|NUMBER)|FROM', header, re.I))
        if not (is_bom or is_connections):
            continue
        serial_rows = [i for i, row in enumerate(values) if row and re.fullmatch(r'\d{1,4}', normalized(row[0]))]
        if not serial_rows:
            continue
        start = serial_rows[0]
        headings = []
        for col in range(max(map(len, values))):
            pieces = [normalized(row[col]) for row in values[:start] if col < len(row) and row[col]]
            headings.append(' / '.join(dict.fromkeys(pieces)) or f'Column {col + 1}')
        rows = []
        serial_counts = Counter(normalized(values[i][0]) for i in serial_rows)
        occurrences = Counter()
        for row_index in serial_rows:
            row = values[row_index]
            cells = []
            for col, text in enumerate(row):
                cell_box = table.rows[row_index].cells[col]
                if cell_box is not None:
                    cells.append({'column': col, 'label': headings[col], 'text': normalized(text),
                                  'bbox': box(cell_box, page.width, page.height), 'uncertain': uncertain_text(text)})
                    count += 1
                    if count > MAX_CELLS:
                        raise ValueError(f'A page exceeds the {MAX_CELLS:,}-cell extraction limit. Split the drawing set.')
            identity = normalized(row[0]); occurrences[identity] += 1
            if serial_counts[identity] > 1:
                identity += f' (occurrence {occurrences[identity]})'
                for cell in cells: cell['uncertain'] = True
            rows.append({'identity': identity, 'cells': cells})
        headers = []
        for col, heading in enumerate(headings):
            body_cell = next((c for r in rows for c in r['cells'] if c['column'] == col), None)
            if body_cell:
                headers.append({'column': col, 'label': heading, 'text': heading,
                                'bbox': [body_cell['bbox'][0], table.bbox[1] / page.height, body_cell['bbox'][2], rows[0]['cells'][0]['bbox'][1]],
                                'uncertain': uncertain_text(heading)})
        tables.append({'bbox': box(table.bbox, page.width, page.height), 'category': 'BOM' if is_bom else 'Connections',
                       'headings': headings, 'headers': headers, 'rows': rows})
    return tables


def extract_pdf(path, side, output, progress=lambda *_: None):
    # pypdf validates encryption/page limits before either extraction/rendering.
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError('Password-protected drawings are not supported. Export an unlocked PDF first.')
    if not 0 < len(reader.pages) <= MAX_PAGES:
        raise ValueError(f'Use a PDF containing 1–{MAX_PAGES} pages.')
    pages = []
    repaired, font_recovery = extraction_copy(reader)
    with pdfplumber.open(repaired or path) as document:
        for i, page in enumerate(document.pages):
            progress(f'Extracting {side} drawing', i + 1, len(document.pages))
            words = page.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False)
            if len(words) > MAX_WORDS:
                raise ValueError(f'Page {i + 1} exceeds the {MAX_WORDS:,}-word extraction limit. Split the drawing set.')
            segments = _segments(words, page.width, page.height)
            text = '\n'.join(s['text'] for s in segments)
            tables = _tables(page)
            scene = build_scene(page, segments, tables)
            scene.update(page=i+1, side=side)
            (output / f'scene-{side}-{i+1}.json').write_text(json.dumps(scene,ensure_ascii=False),encoding='utf-8')
            # Some CAD exports encode no space glyphs at all. Character n-grams
            # retain content identity when word tokenization differs by exporter.
            compact = key(text)
            tokens = Counter(compact[n:n + 3] for n in range(max(0, len(compact) - 2)))
            sheet = re.search(r'\bSHEET\s*[:#]?\s*(\d+)\s*(?:of|/)\s*\d+', text, re.I)
            titles = re.findall(r'^(?:S\.?[ \t]*No\.?[ \t]*\d+[^\r\n]*|TABLE[ \t]+\d+[^\r\n]*)', text, re.I | re.M)
            notices = []
            if not words:
                notices.append('No selectable text. Visual comparison only; component, terminal and BOM extraction require OCR or a source export.')
            if any(uncertain_text(s['text']) for s in segments):
                notices.append('Some PDF glyphs could not be decoded reliably. Inspect the original drawing for affected text.')
            routine_ids = sorted(set(re.findall(r'S\.?\s*No\.?\s*(\d+)', text, re.I)))
            fallback_title = next((s['text'] for s in segments if s['bbox'][1] < .25 and len(s['text']) > 20), '')
            title = ' · '.join(titles[:3])[:220] or fallback_title[:180] or (f'Sheet {sheet.group(1)}' if sheet else f'Page {i + 1}')
            pages.append({'number': i + 1, 'width': page.width, 'height': page.height, 'text': text,
                          'fontRecovery': font_recovery,
                          'scene': scene,
                          'images': [{'bbox': box((image['x0'], image['top'], image['x1'], image['bottom']), page.width, page.height)} for image in page.images],
                          'routineIds': routine_ids,
                          'segments': segments, 'tables': tables, 'tokens': dict(tokens), 'sheet': sheet.group(1) if sheet else '',
                          'title': title,
                          'notices': notices, 'textWords': len(words), 'image': f'{side}-{i + 1}.png'})
            page.close()
    # Serialize every PDFium call, including close operations, across jobs.
    with PDFIUM_LOCK:
        with pdfium.PdfDocument(str(path)) as document:
            for i, info in enumerate(pages):
                progress(f'Rendering {side} drawing', i + 1, len(pages))
                page = document[i]
                try:
                    bitmap = page.render(scale=min(RENDER_WIDTH / page.get_width(), 2400 / page.get_height()))
                    try:
                        bitmap.to_pil().convert('RGB').save(output / info['image'])
                    finally:
                        bitmap.close()
                finally:
                    page.close()
    return pages


def _similarity(a, b):
    x, y = Counter(a['tokens']), Counter(b['tokens'])
    total = sum(x.values()) + sum(y.values())
    return 2 * sum((x & y).values()) / total if total else 0


def match_pages(base, developed):
    """One-to-one content matching; use printed sheet IDs only with corroborating content."""
    remaining_a, remaining_b = set(range(len(base))), set(range(len(developed)))
    pairs = []
    candidates = []
    for i, a in enumerate(base):
        for j, b in enumerate(developed):
            sim = _similarity(a, b)
            unique_sheet = bool(a['sheet'] and a['sheet'] == b['sheet']
                                and sum(p['sheet'] == a['sheet'] for p in base) == 1
                                and sum(p['sheet'] == b['sheet'] for p in developed) == 1)
            same_titles = bool(a.get('routineIds') and a['routineIds'] == b.get('routineIds'))
            score = sim + (0.3 if (unique_sheet or same_titles) and sim > 0.18 else 0)
            if sim > 0.38 or (unique_sheet and sim > 0.18):
                candidates.append((score, sim, i, j, unique_sheet))
    for _, sim, i, j, sheet in sorted(candidates, key=lambda v: (-v[0], abs(v[2] - v[3]), v[2], v[3])):
        if i not in remaining_a or j not in remaining_b:
            continue
        remaining_a.remove(i); remaining_b.remove(j)
        pairs.append({'base': i + 1, 'developed': j + 1, 'match': 'printed sheet and content' if sheet else 'text content',
                      'similarity': round(sim, 4), 'matchReview': sim < 0.6})
    # Scans / completely redrawn pages cannot be matched confidently using text.
    # Keep positional candidates visibly unverified rather than inventing identity.
    for i, j in list(zip(sorted(remaining_a), sorted(remaining_b))):
        if i == j and (not base[i]['textWords'] or not developed[j]['textWords']):
            remaining_a.remove(i); remaining_b.remove(j)
            pairs.append({'base': i + 1, 'developed': j + 1, 'match': 'position only — verify page identity',
                          'similarity': 0, 'matchReview': True})
    pairs.extend({'base': i + 1, 'developed': None, 'match': 'removed page', 'similarity': 0, 'matchReview': False} for i in remaining_a)
    pairs.extend({'base': None, 'developed': j + 1, 'match': 'added page', 'similarity': 0, 'matchReview': False} for j in remaining_b)
    return sorted(pairs, key=lambda v: (v['base'] if v['base'] is not None else len(base) + v['developed']))


def _change(category, before, after, label='', kind='text', **extra):
    status = 'modified' if before and after else 'added' if after else 'removed'
    impact, check = IMPACTS[category]
    uncertain = kind == 'visual' or any(s and s.get('uncertain') for s in (before, after))
    return {'category': category, 'status': status, 'label': label or category, 'before': before, 'after': after,
            'evidenceKind': kind, 'extraction': 'needs verification' if uncertain else 'extracted vector geometry' if kind=='vector' else 'extracted text',
            'review': 'pending', 'note': '', 'possibleImpact': impact, 'verification': check, **extra}


def _column_pairs(ca, cb):
    """Reserve all exact headings before matching damaged/changed PDF headers.

    A greedy fuzzy match can otherwise pair resistance with mass merely because
    both headers contain 'specified length'. Positional fallbacks are explicit
    uncertain correspondences and never displace an exact heading match.
    """
    free_a, free_b = set(range(len(ca))), set(range(len(cb)))
    matched = []
    for i, x in enumerate(ca):
        heading_key = lambda text: re.sub(r'[^\w]', '', key(text))
        exact = [j for j in free_b if heading_key(cb[j]['label']) == heading_key(x['label'])]
        if exact:
            j = min(exact, key=lambda j: abs(cb[j]['column'] - x['column']))
            matched.append((x, cb[j])); free_a.remove(i); free_b.remove(j)
    for i in sorted(free_a):
        x = ca[i]
        same_position = next((j for j in free_b if cb[j]['column'] == x['column']), None)
        if same_position is not None:
            j = same_position
        else:
            near = [(SequenceMatcher(None, key(x['label']), key(cb[j]['label'])).ratio(), j) for j in free_b]
            score, candidate = max(near, default=(0, -1))
            j = candidate if score >= .85 else None
        if j is None:
            matched.append((x, None))
        else:
            free_b.remove(j); matched.append((x, cb[j]))
    matched.extend((None, cb[j]) for j in sorted(free_b))
    return matched


def compare_tables(a, b):
    changes = []
    tables_a, tables_b = a['tables'], b['tables']
    used_b = set()
    for ta in tables_a:
        options = [(distance(ta['bbox'], tb['bbox']), i, tb) for i, tb in enumerate(tables_b)
                   if i not in used_b and tb['category'] == ta['category']]
        tb = None
        if options:
            _, index, tb = min(options, key=lambda v: v[0]); used_b.add(index)
        if tb:
            for x, y in _column_pairs(ta.get('headers', []), tb.get('headers', [])):
                if re.sub(r'[^\w]', '', key((x or {}).get('text'))) == re.sub(r'[^\w]', '', key((y or {}).get('text'))): continue
                changes.append(_change(ta['category'], source(a['number'], x['text'], x['bbox'], uncertain=x['uncertain']) if x else None,
                                       source(b['number'], y['text'], y['bbox'], uncertain=y['uncertain']) if y else None,
                                       'Table column heading — verify correspondence'))
        before_rows = {r['identity']: r for r in ta['rows']}
        after_rows = {r['identity']: r for r in tb['rows']} if tb else {}
        for identity in dict.fromkeys([*before_rows, *after_rows]):
            ra, rb = before_rows.get(identity), after_rows.get(identity)
            if not ra or not rb:
                row = ra or rb
                text = ' | '.join(c['text'] for c in row['cells'])
                ref = source(a['number'] if ra else b['number'], text, union([c['bbox'] for c in row['cells']]))
                changes.append(_change(ta['category'], ref if ra else None, ref if rb else None, f'Item {identity}'))
                continue
            ca, cb = ra['cells'], rb['cells']
            for x, y in _column_pairs(ca, cb):
                if key((x or {}).get('text')) == key((y or {}).get('text')):
                    continue
                label = (y or x)['label']
                fuzzy = bool(x and y and re.sub(r'[^\w]','',key(x['label'])) != re.sub(r'[^\w]','',key(y['label'])))
                before = source(a['number'], x['text'], x['bbox'], uncertain=x['uncertain'] or fuzzy) if x else None
                after = source(b['number'], y['text'], y['bbox'], uncertain=y['uncertain'] or fuzzy) if y else None
                changes.append(_change(ta['category'], before, after, f'Item {identity} · {label}', row=identity, column=(y or x)['column'] + 1))
    for i, tb in enumerate(tables_b):
        if i not in used_b:
            for row in tb['rows']:
                ref = source(b['number'], ' | '.join(c['text'] for c in row['cells']), union([c['bbox'] for c in row['cells']]))
                changes.append(_change(tb['category'], None, ref, f"Item {row['identity']}"))
    return changes


def compare_annotations(a, b):
    def outside_tables(page):
        values=[]
        for s in page['segments']:
            if any(intersects(s['bbox'], t['bbox']) for t in page['tables']):continue
            if s['bbox'][1]>.83 and key(s['text']).strip(':') in {'alteration','sign','date','drawn','checked','approved','replacedby','replacementfor'}:continue
            if re.fullmatch(r'\d+(?:\s+\d+)+',s['text']) and s.get('tokens'):
                values.extend(s['tokens'])
            else:values.append(s)
        return values
    aa, bb = outside_tables(a), outside_tables(b)
    used_a, used_b = set(), set()
    # Match repeated equal labels at the nearest location, suppressing font/space/hyphen re-export noise.
    matches = sorted((distance(x['bbox'], y['bbox']), i, j) for i, x in enumerate(aa) for j, y in enumerate(bb)
                     if key(x['text']) == key(y['text']))
    for d, i, j in matches:
        if i not in used_a and j not in used_b:
            used_a.add(i); used_b.add(j)
    # PDF exporters split/merge labels differently. Match equal content across
    # up to three neighboring text fragments before declaring words changed.
    for source_entries, target_entries, source_used, target_used in ((aa,bb,used_a,used_b),(bb,aa,used_b,used_a)):
        for i, item in enumerate(source_entries):
            if i in source_used: continue
            nearby = sorted([(j,t) for j,t in enumerate(target_entries) if j not in target_used
                             and intersects(item['bbox'],t['bbox'],.008) and abs(item['bbox'][1]-t['bbox'][1]) < .014], key=lambda x:x[1]['bbox'][0])
            found = False
            for start in range(len(nearby)):
                for length in (2,3):
                    group = nearby[start:start+length]
                    if len(group)==length and key(''.join(t['text'] for _,t in group))==key(item['text']):
                        source_used.add(i);target_used.update(j for j,_ in group);found=True;break
                if found:break
    # A unique cable specification remains the same field after a diagram moves.
    # Match its property pattern, rather than reporting a removed and added field.
    def cable_signature(text):
        value=key(text)
        return re.sub(r'\d+(?:\.\d+)?','#',value) if re.search(r'\d+[xX]\d',value) else None
    signatures={cable_signature(x['text']) for i,x in enumerate(aa) if i not in used_a}
    cable_pairs=[]
    for signature in signatures-{None}:
        left=[i for i,x in enumerate(aa) if i not in used_a and cable_signature(x['text'])==signature]
        right=[j for j,y in enumerate(bb) if j not in used_b and cable_signature(y['text'])==signature]
        if len(left)==len(right)==1:cable_pairs.append((left[0],right[0]))
    candidates = []
    for i, x in enumerate(aa):
        if i in used_a: continue
        for j, y in enumerate(bb):
            if j in used_b: continue
            d = distance(x['bbox'], y['bbox'])
            sim = SequenceMatcher(None, key(x['text']), key(y['text'])).ratio()
            same_category = _category(x['text']) == _category(y['text'])
            if d < 0.035 and (sim > 0.30 or (same_category and d < 0.012)):
                candidates.append((d + (1 - sim) * 0.018, i, j))
    changes = []
    for i,j in cable_pairs:
        used_a.add(i);used_b.add(j);x,y=aa[i],bb[j]
        changes.append(_change('Cable specifications',source(a['number'],**{k:v for k,v in x.items() if k!='tokens'}),
                               source(b['number'],**{k:v for k,v in y.items() if k!='tokens'}),'Cable conductor / cross-section specification'))
    for _, i, j in sorted(candidates):
        if i in used_a or j in used_b: continue
        used_a.add(i); used_b.add(j)
        x, y = aa[i], bb[j]
        changes.append(_change(_category(y['text']), source(a['number'], **{k:v for k,v in x.items() if k!='tokens'}), source(b['number'], **{k:v for k,v in y.items() if k!='tokens'})))
    for entries, used, page, is_base in ((aa, used_a, a, True), (bb, used_b, b, False)):
        for i, item in enumerate(entries):
            if i not in used and item['text']:
                ref = source(page['number'], **{k:v for k,v in item.items() if k!='tokens'})
                changes.append(_change(_category(item['text']), ref if is_base else None, None if is_base else ref))
    return changes



def compare_drawings(base_path, developed_path, output, names=None, progress=lambda *_: None):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    base = extract_pdf(base_path, 'base', output, progress)
    developed = extract_pdf(developed_path, 'developed', output, progress)
    pairs = match_pages(base, developed)
    changes = []; issues = []; render_diagnostics = []
    for index, pair in enumerate(pairs):
        progress('Comparing matched sheets', index + 1, len(pairs))
        pair['id'] = f'P{index + 1:03}'
        a = base[pair['base'] - 1] if pair['base'] else None
        b = developed[pair['developed'] - 1] if pair['developed'] else None
        pair['title'] = (a or b)['title']
        page_changes = []; page_issues = []; page_diagnostics = []
        if a and b:
            text_candidates = compare_tables(a, b) + compare_annotations(a, b)
            regions, overlay, stats, raster = compare_visual(output / a['image'], output / b['image'], a, b)
            overlay.save(output / f"overlay-{index + 1}.png")
            pair.update(visual=stats, overlay=f'overlay-{index + 1}.png')
            for change in text_candidates:
                uncertain = any(ref and ref.get('uncertain') for ref in (change['before'],change['after']))
                texts=[ref['text'] for ref in (change['before'],change['after']) if ref]
                if any(re.fullmatch(r'[^\w\s]+',text) for text in texts):uncertain=True
                if len(texts)==2 and all(re.fullmatch(r'[A-Za-z/\s-]{4,}',text) for text in texts) and re.sub(r'[^a-z]','',texts[0].casefold())==re.sub(r'[^a-z]','',texts[1].casefold()):uncertain=True
                if uncertain:
                    change.update(issue='Uncertain text extraction',assessment='uncertain')
                    page_issues.append(change)
                elif not visible_text_change(change,raster):
                    change.update(issue='Text layer differs but visible marks match',assessment='suppressed-render-artifact')
                    page_diagnostics.append(change)
                else:
                    change.update(assessment='source-difference',method='decoded text/table object with visible source support')
                    page_changes.append(change)
            # Compare actual PDF centerline coverage, independently of antialias
            # pixels and primitive splitting. These are drawn-line changes, not
            # asserted electrical net changes.
            transform = raster['transform']
            line_changes = []; geometry_candidates = []
            for own,peer,inverse in ((a,b,False),(b,a,True)):
                residuals=uncovered_lines(own['scene']['lines'],peer['scene']['lines'],transform,own['width'],own['height'],inverse)
                for residual in residuals:
                    ref=source(own['number'],f"Drawn line {residual['sourceLine']}",residual['bbox'],points=residual['points'])
                    candidate=_change('Drawing / annotations',ref if own is a else None,ref if own is b else None,
                                      'Drawn line geometry', 'vector',assessment='source-difference',method='PDF vector centerline coverage')
                    candidate['verification']='Verify whether this changed line is wiring, a dimension or a symbol edge. Geometry alone does not establish an electrical net.'
                    if visible_text_change(candidate,raster):geometry_candidates.append(candidate)
            # A PDF export may reroute or re-segment an entire drawing. Until
            # terminal/symbol association is verified, those line pieces are
            # geometry checks, not hundreds of claimed added/removed wires.
            # Localize and aggregate them; retain the full source line inventory
            # and topology in the inspectable scene graph.
            grouped = {}
            for candidate in geometry_candidates:
                ref=candidate['before'] or candidate['after'];bounds=ref['bbox']
                cell=(int((bounds[0]+bounds[2])/2/.15),int((bounds[1]+bounds[3])/2/.15))
                entry=grouped.setdefault(cell,{'before':[],'after':[],'lines':[]})
                for side in ('before','after'):
                    if candidate[side]:entry[side].append(candidate[side])
                entry['lines'].append(ref['text'])
            for entry in grouped.values():
                def grouped_source(refs):
                    if not refs:return None
                    return source(refs[0]['page'],f"{len(refs)} drawn-line pieces; inspect the source paths",union([r['bbox'] for r in refs]),
                                  sourceLines=[r['text'] for r in refs],paths=[r['points'] for r in refs])
                candidate=_change('Drawing / annotations',grouped_source(entry['before']),grouped_source(entry['after']),
                                  'Drawing geometry / layout check','vector',assessment='uncertain',
                                  issue='Geometric line differences do not establish changed electrical connections')
                candidate['verification']='Inspect the source lines and terminal graph. Re-exported primitives or a moved drawing can produce geometry changes without changing wiring.'
                page_issues.append(candidate)
            page_changes.extend(line_changes)
            residual_groups={}
            for region in regions:
                if any(intersects(region['bbox'], (c['before'] or c['after'])['bbox'], .006)
                       and (region['bbox'][2] - region['bbox'][0]) * (region['bbox'][3] - region['bbox'][1]) < .008 for c in page_changes):
                    continue
                before = source(a['number'], 'Removed or altered drawing geometry', region['bbox']) if region['removedPixels'] else None
                after = source(b['number'], 'Added or altered drawing geometry', region['developedBox']) if region['addedPixels'] else None
                candidate=_change('Drawing / annotations', before, after, 'Local raster difference', 'visual', **region)
                if not a['textWords'] or not b['textWords']:
                    candidate.update(assessment='visual-difference',method='scanned-page raster evidence');page_changes.append(candidate)
                else:
                    bounds=region['bbox'];cell=(int((bounds[0]+bounds[2])/2/.18),int((bounds[1]+bounds[3])/2/.18))
                    residual_groups.setdefault(cell,[]).append(candidate)
            for group in residual_groups.values():
                def raster_source(side):
                    refs=[c[side] for c in group if c[side]]
                    if not refs:return None
                    return source(refs[0]['page'],f'{len(refs)} local render residuals; no confirmed circuit-object change',
                                  union([ref['bbox'] for ref in refs]),regions=[ref['bbox'] for ref in refs])
                page_issues.append(_change('Drawing / annotations',raster_source('before'),raster_source('after'),
                    'Unverified local appearance','visual',assessment='uncertain',
                    issue='Raster residual without a corroborating changed drawing object'))
            pair['status'] = 'modified' if page_changes else 'unchanged'
            pair['objectComparison']={'base':a['scene']['coverage'],'developed':b['scene']['coverage'],
                                      'geometryPiecesForReview':len(geometry_candidates)}
            if a['number'] != b['number']:
                pair['reordered'] = True
        else:
            ref = source((a or b)['number'], (a or b)['title'], [0, 0, 1, 1])
            pair['status'] = 'removed' if a else 'added'
            page_changes = [_change('Drawing / annotations', ref if a else None, ref if b else None, 'Entire drawing page', 'visual')]
        pair['changeCount'] = len(page_changes)
        pair['uncertainCount'] = len(page_issues)
        pair['suppressedRenderArtifacts'] = len(page_diagnostics)
        for change in page_changes:
            change.update(id=f'C{len(changes) + 1:05}', pairId=pair['id'])
            changes.append(change)
        for issue in page_issues:
            issue.update(id=f'U{len(issues)+1:05}',pairId=pair['id']);issues.append(issue)
        for diagnostic in page_diagnostics:
            diagnostic.update(pairId=pair['id']);render_diagnostics.append(diagnostic)
    def public_pages(pages):
        return [{k: p[k] for k in ('number', 'width', 'height', 'title', 'notices', 'textWords', 'image')}
                | {'tables': len(p['tables']),'objects':p['scene']['coverage'],'fontRecovery':p['fontRecovery']} for p in pages]
    summary = {status: sum(c['status'] == status for c in changes) for status in ('added', 'removed', 'modified')}
    summary.update(changes=len(changes), uncertainFindings=len(issues), suppressedRenderArtifacts=len(render_diagnostics),pendingReview=len(changes), changedPages=sum(p['status'] != 'unchanged' for p in pairs),
                   matchedPages=sum(bool(p['base'] and p['developed']) for p in pairs),
                   reorderedPages=sum(bool(p.get('reordered')) for p in pairs))
    result = {'comparisonType': 'circuit', 'engineVersion': ENGINE_VERSION, 'createdAt': time.time(),
              'baseName': (names or {}).get('base', Path(base_path).name), 'developedName': (names or {}).get('developed', Path(developed_path).name),
              'basePages': public_pages(base), 'developedPages': public_pages(developed), 'pairs': pairs,
              'changes': changes, 'uncertainFindings':issues, 'renderDiagnostics':render_diagnostics, 'summary': summary, 'elapsedSeconds': round(time.monotonic() - started, 2),
              'limitations': ['Text and table values are extracted from the PDF; verify changed values against the original drawing.',
                             'Text, references, symbol shapes and drawn-line geometry are separate source objects. Terminal-to-wire associations remain inferred unless engineer-verified.',
                             'Plain crossings are not joined. Continuous drawn paths do not certify electrical connectivity, pin semantics or functional equivalence.',
                             'Uncertain extraction and uncorroborated raster residuals are reported separately from detected source-object changes.',
                             'No OCR is applied to scanned pages. Missing or undecodable text is explicitly reported.',
                             'Font rendering and PDF export differences can leave graphical findings that require manual review.'],
              'fingerprints': {side: hashlib.sha256(Path(path).read_bytes()).hexdigest() for side, path in [('base', base_path), ('developed', developed_path)]}}
    (output / 'circuit_result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return result


def analysis(result):
    """Deterministic Chopper findings: impacts are questions to verify, not invented behavior."""
    areas = []
    for category in CATEGORIES:
        entries = [c for c in result['changes'] if c['category'] == category and c['review'] != 'dismissed']
        if not entries: continue
        areas.append({'category': category, 'count': len(entries), 'sourceIds': [c['id'] for c in entries],
                      'possibleImpact': IMPACTS[category][0], 'verify': IMPACTS[category][1]})
    return {'mode': 'source-based engineering checks', 'areas': areas,
            'summary': f"{result['summary']['changes']} detected source-object changes across {result['summary']['changedPages']} drawing page pairs. "
                       f"{result['summary'].get('uncertainFindings',0)} uncertain extraction or geometry checks are separate and are not counted as engineering changes. "
                       'Possible impacts are review prompts; actual electrical and machine behavior has not been established.',
            'limitations': result['limitations']}
