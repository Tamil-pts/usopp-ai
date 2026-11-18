"""Positioned PDF text differences. Page counters never identify PLC operands."""
from __future__ import annotations

import io
import re
import threading
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from itertools import zip_longest
from uuid import uuid4

from fastapi import HTTPException

RENDER_LOCK = threading.Lock()
COLORS = {'added': '#17a673', 'removed': '#e44d61', 'modified': '#efb52e', 'unresolved': '#d48a20'}


def page_counter(text, box, width, height, page, total):
    """Only complete counter labels in the outer margins may be omitted."""
    if not (box[3] <= height * .075 or box[1] >= height * .925):
        return False
    text = text.strip()
    match = re.fullmatch(r'(?:page\s*)?(\d+)\s*(?:/|of)\s*(\d+)', text, re.I)
    if match:
        return int(match[1]) == page and int(match[2]) == total
    match = re.fullmatch(r'page\s+(\d+)', text, re.I)
    # Bare numbers remain evidence: a footer-positioned operand is not proof of pagination.
    return bool(match and int(match[1]) == page)


def extract(path, ignore_page_numbers):
    import pdfplumber
    units, pages, ignored, notices = [], [], [], []
    characters = 0
    with pdfplumber.open(path) as document:
        if len(document.pages) > 250:
            raise HTTPException(422, 'PDF comparison supports up to 250 pages per file.')
        for number, original in enumerate(document.pages, 1):
            # Match the visible CropBox used by PDFium and PDF readers.
            bounds = original.bbox
            if original.cropbox:
                bounds = (max(bounds[0], original.cropbox[0]), max(bounds[1], original.cropbox[1]),
                          min(bounds[2], original.cropbox[2]), min(bounds[3], original.cropbox[3]))
            page = original.crop(bounds) if tuple(bounds) != tuple(original.bbox) else original
            width, height = page.width, page.height
            pages.append({'number': number, 'width': width, 'height': height})
            lines = page.extract_text_lines(return_chars=True)
            for index, line in enumerate(lines, 1):
                text = line['text'].strip()
                if not text:
                    continue
                box = [line['x0'] - bounds[0], line['top'] - bounds[1], line['x1'] - bounds[0], line['bottom'] - bounds[1]]
                # Text extraction may infer spaces absent from PDF character objects.
                # Map the extractor's words back to their characters, preserving its text.
                chars = [(letter, char) for char in line['chars'] for letter in unicodedata.normalize('NFKC', char['text']) if not letter.isspace()]
                tokens = text.split(); words = []; cursor = 0
                if ''.join(c[0] for c in chars) == ''.join(unicodedata.normalize('NFKC', token) for token in tokens):
                    for token in tokens:
                        size = len(unicodedata.normalize('NFKC', token)); group = [c[1] for c in chars[cursor:cursor+size]]; cursor += size
                        words.append({'text': token, 'bbox': [min(c['x0'] for c in group)-bounds[0], min(c['top'] for c in group)-bounds[1],
                                                             max(c['x1'] for c in group)-bounds[0], max(c['bottom'] for c in group)-bounds[1]]})
                else:
                    words = [{'text': text, 'bbox': box}]
                if ignore_page_numbers and page_counter(text, box, width, height, number, len(document.pages)):
                    ignored.append({'page': number, 'text': text})
                    continue
                characters += len(text)
                if len(units) >= 10000 or characters > 1000000:
                    raise HTTPException(422, 'Extracted text exceeds 10,000 lines or one million characters. Split the document.')
                units.append({'value': text, 'ref': f'Page {number} / line {index}', 'page': number,
                              'bbox': box, 'words': words})
            if not lines and page.images:
                units.append({'value': '[No extractable text; OCR required]', 'ref': f'Page {number}',
                              'page': number, 'bbox': [0, 0, width, height], 'words': [], 'unknown': True})
                notices.append(f'Page {number} has no extractable text. Its content needs OCR review.')
            original.close()
    if not units:
        raise HTTPException(422, 'No comparable text remains after excluding page counters.')
    return units, pages, ignored, notices


def normalize(value, options):
    if options.get('ignore_whitespace'):
        value = ' '.join(value.split())
    return value.casefold() if options.get('ignore_case') else value


def changed_boxes(left, right, status, options):
    if not left or status == 'unchanged':
        return []
    if not right or status in {'added', 'removed', 'unresolved'}:
        return [w['bbox'] for w in left['words']] or [left['bbox']]
    a, b = left['words'], right['words']
    boxes = []
    for tag, start, end, _, _ in SequenceMatcher(None, [normalize(w['text'], options) for w in a],
                                                [normalize(w['text'], options) for w in b], autojunk=False).get_opcodes():
        if tag != 'equal':
            boxes.extend(w['bbox'] for w in a[start:end])
    return boxes


def align_pages(rows, a_pages, b_pages):
    """Monotone maximum-evidence pairing; inserted pages don't shift every pair."""
    votes = Counter()
    for row in rows:
        a, b = row.get('base_location'), row.get('compared_location')
        if a and b:
            # Shared body text outweighs unrelated replacement runs.
            shared = SequenceMatcher(None, row['base'].split(), row['compared'].split(), autojunk=False)
            votes[a['page'], b['page']] += sum(block.size for block in shared.get_matching_blocks())
    n, m = len(a_pages), len(b_pages)
    scores = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            scores[i][j] = max(scores[i-1][j], scores[i][j-1], scores[i-1][j-1] + votes[i, j])
    pairs, i, j = [], n, m
    while i or j:
        if i and j and votes[i, j] and scores[i][j] == scores[i-1][j-1] + votes[i, j]:
            pairs.append({'base': i, 'compared': j}); i -= 1; j -= 1
        elif i and (not j or scores[i-1][j] >= scores[i][j-1]):
            pairs.append({'base': i, 'compared': None}); i -= 1
        else:
            pairs.append({'base': None, 'compared': j}); j -= 1
    pairs.reverse()
    lookup = defaultdict(set)
    for row in rows:
        for side in ('base', 'compared'):
            if row.get(side + '_location'):
                lookup[side, row[side + '_location']['page']].add(row['id'])
    for index, pair in enumerate(pairs, 1):
        ids = lookup['base', pair['base']] | lookup['compared', pair['compared']]
        counts = Counter(rows[r-1]['status'] for r in ids)
        pair.update(id=index, counts=dict(counts), change_count=sum(counts[s] for s in COLORS))
    return pairs


def compare(files, options):
    extracted = [extract(path, options.get('ignore_page_numbers', True)) for path in files]
    a, b = [value[0] for value in extracted]
    keys = [[f'__unreadable_{side}_{i}__' if unit.get('unknown') else normalize(unit['value'], options)
             for i, unit in enumerate(units)] for side, units in enumerate((a, b))]
    rows = []
    for tag, i, j, k, l in SequenceMatcher(None, *keys, autojunk=False).get_opcodes():
        for left, right in zip_longest(a[i:j], b[k:l]):
            status = ('unresolved' if any(u and u.get('unknown') for u in (left, right)) else
                      'added' if left is None else 'removed' if right is None else
                      'unchanged' if tag == 'equal' else 'modified')
            row = {'id': len(rows) + 1, 'status': status, 'base': left['value'] if left else '',
                   'compared': right['value'] if right else '', 'base_ref': left['ref'] if left else '',
                   'compared_ref': right['ref'] if right else ''}
            for side, unit, other in [('base', left, right), ('compared', right, left)]:
                row[side + '_location'] = ({'page': unit['page'], 'bbox': unit['bbox'],
                                           'highlights': changed_boxes(unit, other, status, options)} if unit else None)
            rows.append(row)
    pages = {side: value[1] for side, value in zip(('base', 'compared'), extracted)}
    ignored = {side: value[2] for side, value in zip(('base', 'compared'), extracted)}
    notices = ['Original PDF pages are retained. Highlights identify extracted text changes; ladder wiring and graphics are not compared.',
               'Pages are paired by shared text in source order. Text may continue onto a neighbouring page.']
    for side, value in zip(('Base', 'Compared'), extracted):
        notices.extend(side + ': ' + notice for notice in value[3])
    if options.get('ignore_page_numbers', True):
        notices.append(f"Printed page counters ignored: Base {len(ignored['base'])}, Compared {len(ignored['compared'])}. Numbers in program text remain compared.")
    return rows, [], notices, {'pages': pages, 'pairs': align_pages(rows, pages['base'], pages['compared']),
                              'ignore_page_numbers': options.get('ignore_page_numbers', True), 'ignored_page_numbers': ignored}


def result_sources(user, key):
    from backend.core import document_comparison as core
    path, result = core.record(user, key, 'results')
    if not result.get('pdf'):
        core.fail('This comparison does not contain two PDF sources.', 400)
    files = {side: core.source(user, result[side]['id'])[0] for side in ('base', 'compared')}
    return path, result, files


def pair_detail(user, key, pair_id):
    from backend.core import document_comparison as core
    _, result, _ = result_sources(user, key)
    pairs = result['pdf']['pairs']
    if not 1 <= pair_id <= len(pairs):
        core.fail('Choose a valid PDF page pair.', 400)
    pair = pairs[pair_id - 1]
    detail = {**pair, 'rows': [], 'base_highlights': [], 'compared_highlights': []}
    for row in result['rows']:
        present = False
        for side in ('base', 'compared'):
            location = row.get(side + '_location')
            if location and location['page'] == pair[side]:
                present = True
                detail[side + '_highlights'].extend({'row_id': row['id'], 'status': row['status'], 'bbox': box}
                                                    for box in location['highlights'])
        if present and row['status'] != 'unchanged':
            detail['rows'].append(row)
    return detail


def render_png(file, page_number, width=1200):
    import pypdfium2 as pdfium
    with RENDER_LOCK:
        document = pdfium.PdfDocument(str(file))
        try:
            page = document[page_number - 1]
            try:
                w, h = page.get_size()
                scale = min(width / w, (4000000 / (w * h)) ** .5, 3)
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil().convert('RGB')
                    try:
                        output = io.BytesIO(); image.save(output, format='PNG'); return output.getvalue()
                    finally: image.close()
                finally: bitmap.close()
            finally: page.close()
        finally: document.close()


def page_image(user, key, side, number):
    from backend.core import document_comparison as core
    path, result, files = result_sources(user, key)
    if side not in files or not 1 <= number <= len(result['pdf']['pages'].get(side, [])):
        core.fail('Choose a valid PDF source page.', 400)
    cache = path / f'page-v1-{side}-{number}.png'
    if cache.is_file():
        return cache.read_bytes()
    data = render_png(files[side], number)
    result_sources(user, key)
    save_cache(cache, data)
    return data


def save_cache(path, data):
    import time
    temporary = path.with_suffix('.' + uuid4().hex + '.tmp')
    try:
        temporary.write_bytes(data)
        for attempt in range(4):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                # Windows can deny replacement while another immutable preview
                # is being read or published. Reuse only an identical complete
                # cache entry; never accept a mismatched or partial winner.
                try:
                    if path.read_bytes()==data:return
                except (PermissionError,FileNotFoundError):pass
                if attempt==3:raise
                time.sleep(.02)
    finally:
        temporary.unlink(missing_ok=True)


def annotated_pdf(user, key, side, status='differences'):
    from backend.core import document_comparison as core
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Highlight
    from pypdf.generic import ArrayObject, FloatObject, NameObject, TextStringObject
    path, result, files = result_sources(user, key)
    if side not in files:
        core.fail('Choose Base or Compared PDF.', 400)
    if result.get('pdf',{}).get('mode')=='plc_networks':
        status=core.plc_status_filter(status)
        rows=core.filtered(result,status)
    else:
        rows=result['rows']
    cache = path / (f'highlighted-v2-{side}-{status}.pdf' if result.get('pdf',{}).get('mode')=='plc_networks' else f'highlighted-v1-{side}.pdf')
    if cache.is_file():
        return cache.read_bytes()
    writer = PdfWriter()
    for page in PdfReader(files[side]).pages:
        page.transfer_rotation_to_content()
        writer.add_page(page)
    for row in rows:
        location = row.get(side + '_location')
        if not location or row['status'] == 'unchanged':
            continue
        locations = ([{'page':segment['page'],'highlights':[segment['bbox']]} for segment in row[side+'_segments']]
                     if row.get(side+'_segments') else [location])
        binding_changes=(row.get('structure') or {}).get('binding_changes',[])
        if binding_changes:
            locations=[{'page':change[side+'_page'],'highlights':[change[side+'_bbox']]} for change in binding_changes]
        summary=f"Change {row['id']} - {row['status']}"
        if binding_changes:
            from backend.core.plc_pdf_engineering import describe
            summary+='\n'+describe(row)
        for location in locations:
          page = writer.pages[location['page'] - 1]
          width, height = float(page.cropbox.width), float(page.cropbox.height)
          meta = result['pdf']['pages'][side][location['page'] - 1]
          for box in location['highlights']:
            x0, top, x1, bottom = box
            x0 = float(page.cropbox.left) + x0 * width / meta['width']
            x1 = float(page.cropbox.left) + x1 * width / meta['width']
            y0 = float(page.cropbox.top) - bottom * height / meta['height']
            y1 = float(page.cropbox.top) - top * height / meta['height']
            annotation = Highlight(rect=(x0, y0, x1, y1), quad_points=ArrayObject([
                FloatObject(v) for v in (x0, y1, x1, y1, x0, y0, x1, y0)]),
                highlight_color=COLORS[row['status']].lstrip('#'), printing=True)
            annotation[NameObject('/Contents')] = TextStringObject(
                f"{summary}\nBefore: {row['base']}\nAfter: {row['compared']}")
            writer.add_annotation(location['page'] - 1, annotation)
    writer.add_metadata({'/Title': f"{result[side]['name']} - highlighted text comparison", '/Subject': key})
    output = io.BytesIO(); writer.write(output); data = output.getvalue()
    result_sources(user, key)
    save_cache(cache, data)
    return data


def export_pdf(user, key):
    """A printable change log followed by paired, vector-quality original pages."""
    from html import escape
    from pypdf import PdfReader, PdfWriter, Transformation
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.pdfbase import pdfmetrics
    from backend.core.workhub_quality.packages import _pdf_font
    path, result, files = result_sources(user, key)
    cache = path / 'comparison-report-v2.pdf'
    if cache.is_file():
        return cache.read_bytes()
    output, notes = io.BytesIO(), io.BytesIO()
    styles = getSampleStyleSheet()
    text = '\n'.join([result['base']['name'], result['compared']['name'], *result['notices'],
                      *(row[side] for row in result['rows'] for side in ('base', 'compared'))])
    font = _pdf_font(text)
    if font != 'Helvetica':
        pdfmetrics.registerFontFamily(font, normal=font, bold=font, italic=font, boldItalic=font)
    for paragraph_style in styles.byName.values():
        paragraph_style.fontName = font
    style = ParagraphStyle('Comparison text', parent=styles['BodyText'], fontSize=9, leading=13,
                           alignment=TA_LEFT, splitLongWords=True)
    story = [Paragraph('PDF text comparison', styles['Title']),
             Paragraph(escape(result['base']['name']) + ' &gt; ' + escape(result['compared']['name']), styles['Heading2'])]
    story += [Paragraph(escape(note), style) for note in result['notices']]
    story += [Spacer(1, 12), Paragraph('All changed text · Before and After', styles['Heading2'])]
    for side in ('base', 'compared'):
        story.append(Paragraph(f"{side.title()} SHA256: {result[side]['sha256']}", style))
    for row in result['rows']:
        if row['status'] == 'unchanged':
            continue
        story.append(Paragraph(f"Change {row['id']} · {row['status'].title()}", styles['Heading3']))
        for side, label in [('base', 'Before'), ('compared', 'After')]:
            story.append(Paragraph(f"<b>{label} · {escape(row[side + '_ref']) or 'No corresponding text'}</b><br/>"
                                   + escape(row[side] or '(No text)').replace('\n', '<br/>'), style))
    if all(row['status'] == 'unchanged' for row in result['rows']):
        story.append(Paragraph('No extracted text differences. Original pages follow.', style))
    SimpleDocTemplate(notes, title='PDF text comparison', leftMargin=35, rightMargin=35).build(story)
    writer = PdfWriter()
    writer.append(PdfReader(notes))
    readers = {side: PdfReader(path) for side, path in files.items()}
    marks = defaultdict(list)
    for row in result['rows']:
        for side in ('base', 'compared'):
            location = row.get(side + '_location')
            if location:
                marks[side, location['page']].extend((row['status'], box) for box in location['highlights'])
    sheet_width, sheet_height = landscape(A3)
    for pair in result['pdf']['pairs']:
        header = io.BytesIO(); canvas = Canvas(header, pagesize=(sheet_width, sheet_height))
        canvas.setFont('Helvetica-Bold', 13); canvas.drawString(24, sheet_height - 25, f"Original PDF pages · Pair {pair['id']}")
        for index, side in enumerate(('base', 'compared')):
            label = f"{side.title()} · Page {pair[side]}" if pair[side] else f"{side.title()} · No paired page"
            canvas.setFont('Helvetica-Bold', 10); canvas.drawString(24 + index * (sheet_width / 2), sheet_height - 46, label)
        canvas.setFont('Helvetica', 9); canvas.drawString(24, 22, 'Green: added text   Red: removed text   Yellow: modified text. Change notes precede these original pages.')
        canvas.save(); target = PdfReader(header).pages[0]
        for index, side in enumerate(('base', 'compared')):
            number = pair[side]
            if not number:
                continue
            page = readers[side].pages[number - 1]
            page.transfer_rotation_to_content()
            width, height = float(page.cropbox.width), float(page.cropbox.height)
            meta = result['pdf']['pages'][side][number - 1]
            overlay = io.BytesIO(); draw = Canvas(overlay, pagesize=(float(page.mediabox.width), float(page.mediabox.height)))
            for status, box in marks[side, number]:
                draw.setFillColor(colors.HexColor(COLORS[status])); draw.setStrokeColor(colors.HexColor(COLORS[status]))
                draw.setFillAlpha(.28); draw.setStrokeAlpha(.65)
                x0, top, x1, bottom = box
                draw.rect(float(page.cropbox.left) + x0 * width / meta['width'],
                          float(page.cropbox.top) - bottom * height / meta['height'],
                          (x1-x0) * width / meta['width'], (bottom-top) * height / meta['height'], fill=1, stroke=1)
            draw.save(); page.merge_page(PdfReader(overlay).pages[0])
            scale = min((sheet_width/2 - 40)/width, (sheet_height - 110)/height)
            x, y = 24 + index * (sheet_width/2), 50
            target.merge_transformed_page(page, Transformation().scale(scale).translate(
                x - float(page.cropbox.left)*scale, y - float(page.cropbox.bottom)*scale))
        writer.add_page(target)
    writer.add_metadata({'/Title': 'PDF text comparison report', '/Subject': key})
    writer.write(output); data = output.getvalue()
    result_sources(user, key)
    save_cache(cache, data)
    return data


def export_html(user, key):
    from html import escape
    _, result, _ = result_sources(user, key)
    heading = escape(result['base']['name']) + ' &rarr; ' + escape(result['compared']['name'])
    notes = ''.join('<p>' + escape(n) + '</p>' for n in result['notices'])
    body = []
    for row in result['rows']:
        if row['status'] != 'unchanged':
            body.append(f"<tr class='{row['status']}'><td>{row['id']}<br>{row['status']}</td>" + ''.join(
                f"<td><small>{escape(row[side + '_ref']) or 'No corresponding text'}</small><pre>{escape(row[side])}</pre></td>"
                for side in ('base', 'compared')) + '</tr>')
    snapshots = ''.join(f"<p>{side.title()} SHA256: {escape(result[side]['sha256'])}</p>" for side in ('base', 'compared'))
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>PDF text comparison</title><style>body{{font:14px system-ui;margin:28px;color:#182b37}}table{{width:100%;table-layout:fixed;border-collapse:collapse}}'
            'th,td{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #dde4e9}th:first-child{width:90px}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 monospace}.modified{background:#fff5d0}.added{background:#ddf9ec}.removed{background:#ffe8ed}'
            'small{color:#526877}p{overflow-wrap:anywhere}@media print{thead{display:table-header-group}tr{break-inside:avoid}}</style>'
            f'<h1>PDF text comparison</h1><h2>{heading}</h2><p>Comparison {key} · {escape(result["created_at"])}</p>{notes}'
            '<p>Before and After list every changed text line. Download the highlighted Base and Compared PDFs for their original page layouts.</p>'
            f'{snapshots}<table><thead><tr><th>Change</th><th>Before · Base</th><th>After · Compared</th></tr></thead><tbody>{"".join(body)}</tbody></table></html>').encode('utf8')
