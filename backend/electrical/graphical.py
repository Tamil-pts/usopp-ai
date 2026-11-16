"""Independent vector tracing. Table assignments are never inputs to the tracer."""
import hashlib
import math
import re
from collections import defaultdict

TERMINAL = re.compile(r'^(-?[XM][A-Z]?\d+)[\-\xad\ufffd\u2010-\u2015]([A-Z0-9/]+)\(([^)]+)\)$', re.I)

def uid(*parts):
    return hashlib.sha256(repr(parts).encode()).hexdigest()[:24]

def trace(words, lines, page, digest, text, table=False):
    """Join segment endpoints only, never geometric crossings or cable outlines.

    Full terminal labels must uniquely anchor both ends of an unbranched chain.
    A graphical path is evidence of a candidate, never an engineer approval.
    """
    points = []; buckets = defaultdict(list); adjacency = defaultdict(list); segments = []
    tolerance = .5
    def vertex(p):
        cell = (math.floor(p[0]/tolerance), math.floor(p[1]/tolerance))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in buckets[(cell[0]+dx, cell[1]+dy)]:
                    if math.dist(points[i], p) <= tolerance:
                        return i
        i = len(points); points.append(list(p)); buckets[cell].append(i); return i
    for index, line in enumerate(lines):
        pts = line.get('pts')
        if not pts or len(pts) != 2 or math.dist(*pts) < 1:
            continue
        a, b = map(vertex, pts)
        if a == b:
            continue
        edge = len(segments)
        segments.append({'source_line': index, 'start': list(pts[0]), 'end': list(pts[1])})
        adjacency[a].append((b, edge)); adjacency[b].append((a, edge))
    visited = set(); paths = []
    for node in adjacency:
        if len(adjacency[node]) == 2:
            continue
        for neighbor, edge in adjacency[node]:
            if edge in visited:
                continue
            chain = [node]; edges = []; current = node
            while edge not in visited:
                visited.add(edge); edges.append(edge); chain.append(neighbor); current = neighbor
                if len(adjacency[current]) != 2:
                    break
                neighbor, edge = next((v, e) for v, e in adjacency[current] if e not in visited) if any(e not in visited for _, e in adjacency[current]) else (current, edge)
            paths.append({'id': uid(digest, page, edges), 'points': [points[n] for n in chain],
                          'source_lines': [segments[e]['source_line'] for e in edges],
                          'endpoint_degrees': [len(adjacency[chain[0]]), len(adjacency[chain[-1]])],
                          'status': 'unresolved', 'type': 'vector_path_candidate'})
    # Closed paths are kept as shapes, never as electrical nets.
    closed = [s['source_line'] for i, s in enumerate(segments) if i not in visited]
    labels = []
    if not table:
        for word in words:
            match = TERMINAL.fullmatch(word['text'])
            if match:
                labels.append({'designation': match[1].lstrip('-').upper(), 'pin': match[2].upper(),
                               'conductor': match[3], 'bbox': [word[k] for k in ('x0','top','x1','bottom')], 'text': word['text']})
    def distance(p, box):
        return math.hypot(max(box[0]-p[0], 0, p[0]-box[2]), max(box[1]-p[1], 0, p[1]-box[3]))
    anchors = defaultdict(list)
    for path in paths:
        for end in (0, -1):
            p = path['points'][end]
            if path['endpoint_degrees'][0 if end == 0 else 1] != 1:
                continue
            near = [label for label in labels if distance(p, label['bbox']) <= 6]
            if len(near) == 1:
                anchors[(near[0]['designation'], near[0]['pin'])].append((path['id'], end))
    connections = []
    for path in paths:
        ends = []
        for end in (0, -1):
            matches = [label for label in labels if anchors[(label['designation'], label['pin'])] == [(path['id'], end)]]
            if len(matches) == 1:
                ends.append(matches[0])
        if len(ends) != 2 or ends[0]['designation'] == ends[1]['designation']:
            continue
        box = [min(p[0] for p in path['points']), min(p[1] for p in path['points']),
               max(p[0] for p in path['points']), max(p[1] for p in path['points'])]
        connections.append({'id': path['id'], 'from': ends[0], 'to': ends[1], 'status': 'needs_review',
                            'method': 'independent_vector_endpoint_trace', 'path': path['points'],
                            'source_lines': path['source_lines'], 'source': {'page': page, 'sha256': digest, 'bbox': box}})
        path['status'] = 'needs_review'
    # Device captions and repeated numbered cells are source observations only.
    designations = sorted(set(re.findall(r'\bX[A-Z]?\d+\b', text, re.I)))
    refs = re.findall(r'REFER\s+TABLE\s*\d+', text, re.I)
    return {'page': page, 'sha256': digest, 'paths': paths, 'closed_shape_line_indices': closed,
            'connections': connections, 'device_designations': designations, 'table_references': refs,
            'line_count': len(segments), 'status': 'needs_review',
            'limitations': ['Endpoint snapping is geometric evidence, not electrical junction approval.',
                           'Crossings, curves, break symbols and cable bundles are not joined automatically.']}

def reconcile(graphics, tables):
    """Compare independent outputs; never populate graphics from table data."""
    def key(c, graphical=False):
        return tuple(sorted((e['designation'] if graphical else e['device'].rsplit('/',1)[-1], e['pin']) for e in (c['from'], c['to'])))
    graphical = defaultdict(list)
    for drawing in graphics:
        for connection in drawing['connections']:
            graphical[key(connection, True)].append(connection)
    records = []
    for assignment in tables:
        matches = [c for c in graphical[key(assignment)] if c['source']['page'] != assignment['source']['page']]
        expected=set(key(assignment));conflicts=[]
        for pair,candidates in graphical.items():
            if pair!=key(assignment) and expected & set(pair):
                conflicts.extend(c['id'] for c in candidates if c['source']['page']!=assignment['source']['page'])
        records.append({'table_connection_id': assignment['id'], 'table_page': assignment['source']['page'],
                        'graphical_connection_ids': [c['id'] for c in matches],
                        'conflicting_graphical_connection_ids':conflicts,
                        'status': 'conflict' if conflicts else 'corroborated' if matches else 'not_independently_recovered',
                        'approval_status': 'needs_review'})
    return records
