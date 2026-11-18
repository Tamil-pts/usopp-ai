"""Independent source evidence for printed PLC comparisons; no execution claims."""
import hashlib
import json

MAX_PAGES = 2000
MAX_BYTES = 100 * 1024**2


def fingerprint(page, region, lines, masks):
    """Retain source geometry, independently of the rasterizer and ink threshold.

    Coordinates are normalized by one translation only. Never reposition a
    contact, branch or operand independently to make two drawings agree.
    Unsupported/clipped curves prevent corroboration rather than imply equality.
    """
    x0, y0, x1, y1 = region
    px, py = page.bbox[:2]
    records, shapes, complete = [], [], not bool(page.images)
    def masked(box):
        return any(box[0] < m[2] and box[2] > m[0] and box[1] < m[3] and box[3] > m[1] for m in masks)
    for line in lines:
        for c in line.get('chars', []):
            box = [c['x0']-px, c['top']-py, c['x1']-px, c['bottom']-py]
            if not masked(box):
                records.append(('text', c['text'], c.get('fontname', ''), repr(c.get('non_stroking_color')), round(c.get('size', 0), 3), box))
    for kind in ('lines', 'rects', 'curves'):
        for obj in getattr(page, kind):
            box = [obj['x0']-px, obj['top']-py, obj['x1']-px, obj['bottom']-py]
            if box[2] < x0 or box[0] > x1 or box[3] < y0 or box[1] > y1:
                continue
            if masked(box):
                # The raster masks may cut a path. Do not certify partial paths.
                complete = False
                continue
            # pdfplumber already converts paths to top-origin coordinates.
            pts = [(float(x-px), float(y-py)) for x, y in obj.get('pts', [])]
            if not pts:
                complete = False
                continue
            # Include all Bezier control points, not just curve endpoints.
            path = obj.get('path') or []
            controls = [(float(v[0]-px), float(v[1]-py)) for cmd in path for v in cmd[1:] if isinstance(v, (tuple, list)) and len(v) == 2]
            if box[1] < y0 or box[3] > y1:
                if kind == 'lines' and (box[0] == box[2] or box[1] == box[3]):
                    pts = [(max(x0, min(x1, x)), max(y0, min(y1, y))) for x, y in pts]
                    controls = []
                else:
                    complete = False
            shapes.append((kind, round(obj.get('linewidth', 0), 3), bool(obj.get('stroke')), bool(obj.get('fill')),
                           repr((obj.get('stroking_color'), obj.get('non_stroking_color'), obj.get('dash'))),
                           tuple(cmd[0] for cmd in path), pts + controls))
    points = [(r[-1][0], r[-1][1]) for r in records] + [p for s in shapes for p in s[-1]]
    ox = min((p[0] for p in points), default=0)
    oy = min((p[1] for p in points), default=0)
    # Printers extend the left power rail into blank page space. Trim only
    # extensions outside every other object; retain a rail ending inside a rung.
    rails = [i for i,s in enumerate(shapes) if s[0]=='lines' and s[-1] and
             all(abs(x-ox)<.1 for x,y in s[-1]) and
             max(y for x,y in s[-1])-min(y for x,y in s[-1])>(y1-y0)*.75]
    occupied = [v for r in records for v in (r[-1][1],r[-1][3])] + [y for i,s in enumerate(shapes) if i not in rails for x,y in s[-1]]
    if occupied:
        for i in rails:
            s=shapes[i]
            shapes[i]=(*s[:-1],[(x,max(min(occupied),min(max(occupied),y))) for x,y in s[-1]])
    def digest(values):
        return hashlib.sha256(json.dumps(sorted(values, key=repr), separators=(',', ':')).encode()).hexdigest()
    text = [(*r[:-1], [round(r[-1][i]-(ox if i%2 == 0 else oy), 3) for i in range(4)]) for r in records]
    geometry = [(*s[:-1], [(round(x-ox, 3), round(y-oy, 3)) for x, y in s[-1]]) for s in shapes]
    return dict(complete=complete, text=digest(text), geometry=digest(geometry), primitives=len(shapes), glyphs=len(records),
                labels=digest([r[:-2] for r in records]+[(s[0],*s[2:-1]) for s in shapes]),
                positions=[v for r in text for v in [r[-2], *r[-1]]] + [v for s in geometry for p in s[-1] for v in p] + [s[1] for s in shapes])


def judge(left, right, text_equal, metric):
    """Bounded retrieve/check decision, backed by independently extracted evidence."""
    a, b = left.get('source_evidence', []), right.get('source_evidence', [])
    corroborated = bool(a and len(a) == len(b) and all(x['complete'] and y['complete'] and x == y for x, y in zip(a, b)))
    raw = metric['changed_pixels'] if metric else None
    # A small residual alone is insufficient. Require identical source labels,
    # path/style counts and every coordinate to agree within PDF print precision.
    # At 1000 px per page, 0.25 pt is less than half a raster pixel on A4/Letter.
    print_agreement = False
    if raw is not None and raw <= 8 and a and len(a) == len(b):
        print_agreement = all(x['complete'] and y['complete'] and x['labels']==y['labels'] and
            len(x['positions'])==len(y['positions']) and
            all(abs(u-v)<=.25 for u,v in zip(x['positions'],y['positions'])) for x,y in zip(a,b))
    if not text_equal:
        status, reason = 'modified', 'Source text changed; review the Before and After content.'
    elif (corroborated and (raw is None or raw <= 8)) or print_agreement:
        status, reason = 'unchanged', 'Source text positions and vector primitives agree after a single translation. Raster differences are rendering noise.'
    elif raw == 0:
        status, reason = 'unchanged', 'Source text and aligned drawing ink agree within the stated raster tolerance.'
    elif metric is None:
        status, reason = 'unchanged', 'Source text agrees. Drawing geometry was not compared.'
    elif a and b and sum(x['primitives'] for x in a) != sum(x['primitives'] for x in b):
        status, reason = 'modified', 'Drawing primitive count and rendered ink changed. Review the highlighted wiring or symbols.'
    else:
        status, reason = 'unresolved', 'Text agrees but drawing evidence differs. Position, font or wiring changes need review; pixels alone cannot decide.'
    return dict(status=status, reason=reason, source_corroborated=corroborated or print_agreement,
                source_tolerance_points=.25 if print_agreement and not corroborated else 0,
                raw_changed_pixels=raw, checks=['source_text', 'source_geometry', 'aligned_raster'] if metric else ['source_text'], passes=2)
