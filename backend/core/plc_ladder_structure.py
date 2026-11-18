"""Conservative vector-PDF recognition of contact/coil networks.

Only fully covered, unambiguous diagrams can corroborate layout-only changes.
Unsupported instructions, crossings and symbols remain review evidence.
"""
import re
from collections import Counter
from math import hypot

TOL = 1.0  # PDF points; terminal matching only, never an image-noise threshold.
TAG = re.compile(r'[A-Za-z_%][\w%]*(?:\.[\w]+)*(?:\[\d+\])*\Z')


def recognize(page, region, lines, masks):
    import pdfplumber
    px,py=page.bbox[:2];x0,y0,x1,y1=region
    unknown=[];segments=[];curves=[]
    def masked(box):
        return any(box[0]<m[2] and box[2]>m[0] and box[1]<m[3] and box[3]>m[1] for m in masks)
    chars=[c for line in lines for c in line.get('chars',[]) if not masked([c['x0']-px,c['top']-py,c['x1']-px,c['bottom']-py])]
    words=pdfplumber.utils.extract_words(chars,x_tolerance=1,y_tolerance=2)
    words=[dict(text=w['text'],box=[w['x0']-px,w['top']-py,w['x1']-px,w['bottom']-py]) for w in words]
    for kind in ('lines','curves','rects'):
        for obj in getattr(page,kind):
            box=[obj['x0']-px,obj['top']-py,obj['x1']-px,obj['bottom']-py]
            if box[2]<x0 or box[0]>x1 or box[3]<y0 or box[1]>y1:continue
            if masked(box):unknown.append('A drawing path intersects excluded content.');continue
            if obj.get('dash') or obj.get('fill') or not obj.get('stroke'):
                unknown.append('Unsupported drawing style.');continue
            pts=[(x-px,y-py) for x,y in obj.get('pts',[])]
            if kind=='lines' and len(pts)==2:
                a,b=pts
                # Only axis-aligned lines may be clipped at page/network edges.
                if a[0]==b[0] or a[1]==b[1]:
                    a=tuple(max(lo,min(hi,v)) for v,lo,hi in zip(a,(x0,y0),(x1,y1)))
                    b=tuple(max(lo,min(hi,v)) for v,lo,hi in zip(b,(x0,y0),(x1,y1)))
                elif box[1]<y0 or box[3]>y1:unknown.append('Clipped diagonal.');continue
                segments.append((a,b))
            elif kind=='curves' and y0<=box[1] and box[3]<=y1:
                curves.append(dict(box=box,points=pts,path=obj.get('path',[])))
            else:unknown.append('Unsupported or clipped drawing object.')
    if len(segments)>400 or len(curves)>100 or len(words)>300:
        return dict(complete=False,symbols=[],nets=[],open_checks=['Network exceeds structural-recognition bounds.'])
    used=set();used_curves=set();used_words=set();symbols=[]
    def axis(line):
        a,b=line
        return 'v' if abs(a[0]-b[0])<.01 else 'h' if abs(a[1]-b[1])<.01 else 'd'
    def near(a,b):return hypot(a[0]-b[0],a[1]-b[1])<=TOL
    def attached(point,direction):
        return any(axis(s)=='h' and any(near(p,point) and (s[1-j][0]-point[0])*direction>2 for j,p in enumerate(s)) for s in segments)
    def operand(box):
        cx=(box[0]+box[2])/2
        candidates=[(i,w) for i,w in enumerate(words) if TAG.fullmatch(w['text']) and
                    -.5<=box[1]-w['box'][3]<=24 and abs((w['box'][0]+w['box'][2])/2-cx)<max(12,(box[2]-box[0])*.6)]
        candidates.sort(key=lambda pair:abs((pair[1]['box'][0]+pair[1]['box'][2])/2-cx)+max(0,box[1]-pair[1]['box'][3]))
        if not candidates:return None
        # More than one equally close label is not a verified operand assignment.
        if len(candidates)>1:
            scores=[abs((w['box'][0]+w['box'][2])/2-cx)+max(0,box[1]-w['box'][3]) for _,w in candidates[:2]]
            if scores[1]-scores[0]<2:return None
        i,w=candidates[0]
        if i in used_words:return None
        used_words.add(i);return w['text']
    vertical=[(i,s) for i,s in enumerate(segments) if axis(s)=='v' and 4<=abs(s[1][1]-s[0][1])<=40]
    for i,left in vertical:
        if i in used:continue
        lx=left[0][0];top,bottom=sorted(p[1] for p in left);height=bottom-top;cy=(top+bottom)/2
        candidates=[]
        for j,right in vertical:
            if i==j or j in used:continue
            rx=right[0][0];rt,rb=sorted(p[1] for p in right)
            if .5*height<rx-lx<3*height and abs(rt-top)<.6 and abs(rb-bottom)<.6:
                # Box boundaries (e.g. MOV_W) are not contact bars.
                border=any(axis(s)=='h' and min(p[0] for p in s)<=lx+TOL and max(p[0] for p in s)>=rx-TOL and
                           min(abs(s[0][1]-top),abs(s[0][1]-bottom))<TOL for s in segments)
                if not border and attached((lx,cy),-1) and attached((rx,cy),1):candidates.append((j,rx))
        if len(candidates)!=1:continue
        j,rx=candidates[0];box=[lx,top,rx,bottom];tag=operand(box)
        if not tag:continue
        slashes=[k for k,s in enumerate(segments) if axis(s)=='d' and
                 all(lx-TOL<=x<=rx+TOL and top-TOL<=y<=bottom+TOL for x,y in s) and
                 abs(s[1][1]-s[0][1])>=height*.4 and abs(s[1][0]-s[0][0])>1]
        slash_words=[k for k,w in enumerate(words) if w['text']=='/' and
                     lx<=w['box'][0]<=rx and top-TOL<=w['box'][1]<=bottom]
        if len(slashes)+len(slash_words)>1:unknown.append('Ambiguous contact mark.')
        used.update((i,j,*slashes));used_words.update(slash_words)
        symbols.append(dict(kind='NC' if slashes or slash_words else 'NO',operand=tag,box=box,ports=[(lx,cy),(rx,cy)]))
    # Two outward-facing arcs, with an incoming wire and an operand above,
    # are the supported ordinary coil profile. No timer/FB semantics are guessed.
    def arc(curve,side):
        pts=curve['points'];box=curve['box'];h=box[3]-box[1];w=box[2]-box[0]
        if len(pts)<3 or not 4<=h<=40 or not .08*h<=w<=.6*h:return False
        if any(cmd[0] not in {'m','c'} for cmd in curve['path']):return False
        endx=box[2] if side=='left' else box[0]
        return abs(pts[0][0]-endx)<.6 and abs(pts[-1][0]-endx)<.6
    for i,left in enumerate(curves):
        if i in used_curves or not arc(left,'left'):continue
        lb=left['box'];h=lb[3]-lb[1];cy=(lb[1]+lb[3])/2
        candidates=[(j,r) for j,r in enumerate(curves) if j not in used_curves and j!=i and arc(r,'right') and
                    abs(r['box'][1]-lb[1])<.6 and abs(r['box'][3]-lb[3])<.6 and .5*h<r['box'][0]-lb[2]<3*h]
        if len(candidates)!=1 or not attached((lb[0],cy),-1):continue
        j,right=candidates[0];box=[lb[0],lb[1],right['box'][2],lb[3]];tag=operand(box)
        if not tag:continue
        used_curves.update((i,j))
        symbols.append(dict(kind='coil',operand=tag,box=box,ports=[(box[0],cy),(box[2],cy)]))
    if len(used_curves)!=len(curves):unknown.append('Unrecognized curve or symbol.')
    if len(used_words)!=len(words):unknown.append('Unassigned text, instruction or operand.')
    if page.images:unknown.append('Page contains raster content.')
    counts=Counter(s['operand'] for s in symbols)
    if any(n>1 for n in counts.values()):unknown.append('Repeated operands require explicit instance matching.')
    wires=[s for i,s in enumerate(segments) if i not in used]
    if any(axis(s)=='d' for s in wires):unknown.append('Unrecognized diagonal.')
    wires=[s for s in wires if axis(s)!='d']
    parents=list(range(len(wires)))
    def root(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    def on(point,line,tol=.05):
        a,b=line
        return (min(a[0],b[0])-tol<=point[0]<=max(a[0],b[0])+tol and
                min(a[1],b[1])-tol<=point[1]<=max(a[1],b[1])+tol and
                (abs(point[0]-a[0])<=tol if axis(line)=='v' else abs(point[1]-a[1])<=tol))
    for i,s in enumerate(wires):
        for j,t in enumerate(wires[:i]):
            connected=any(on(p,t) for p in s) or any(on(p,s) for p in t)
            if connected:parents[root(i)]=root(j)
            elif axis(s)!=axis(t):
                v,h=(s,t) if axis(s)=='v' else (t,s);cross=(v[0][0],h[0][1])
                if on(cross,v) and on(cross,h):unknown.append('Unmarked four-way crossing.')
    nets={}
    for symbol in symbols:
        for port,point in zip(('in','out'),symbol['ports']):
            attached_roots={root(i) for i,w in enumerate(wires) if on(point,w,TOL)}
            if len(attached_roots)>1:unknown.append('Ambiguous terminal attachment.')
            if attached_roots:
                net=next(iter(attached_roots));nets.setdefault(net,[]).append((symbol['operand'],port))
            elif not(symbol['kind']=='coil' and port=='out'):unknown.append('Unconnected symbol terminal.')
    assigned=set(nets)
    if any(root(i) not in assigned for i in range(len(wires))):unknown.append('Unassigned wire component.')
    min_x=min((p[0] for w in wires for p in w),default=0)
    ports=[p for symbol in symbols for p in symbol['ports']]
    for i,w in enumerate(wires):
        rail=axis(w)=='v' and abs(w[0][0]-min_x)<.05 and abs(w[1][1]-w[0][1])>40
        for point in w:
            if rail or any(near(point,p) for p in ports):continue
            if not any(j!=i and on(point,other) for j,other in enumerate(wires)):
                unknown.append('Unterminated conductor or broken wire.')
    if not symbols:unknown.append('No supported contact/coil network recognized.')
    # Reachability is connectivity evidence only, not PLC execution/scan timing.
    return dict(complete=not unknown,symbols=symbols,nets=sorted(sorted(v) for v in nets.values()),
                open_checks=sorted(set(unknown)),tolerance_points=TOL)


def compare(left,right):
    a=left.get('ladder_parts',[]);b=right.get('ladder_parts',[])
    covered_a=bool(a and all(p['complete'] for p in a))
    covered_b=bool(b and all(p['complete'] for p in b))
    supported=covered_a and covered_b and len(a)==len(b)
    symbols=lambda parts:sorted((s['operand'],s['kind']) for p in parts for s in p['symbols'])
    sa,sb=symbols(a),symbols(b)
    changes=[]
    if supported:
        aa,bb=dict(sa),dict(sb)
        for tag in sorted(aa.keys()|bb.keys()):
            if aa.get(tag)!=bb.get(tag):changes.append(dict(operand=tag,before=aa.get(tag),after=bb.get(tag)))
    same=supported and sa==sb and all(x['nets']==y['nets'] for x,y in zip(a,b))
    return dict(supported=supported,same=same,changes=changes,
                base_complete=covered_a,compared_complete=covered_b,
                # Partial candidates on both sides cannot overrule the existing
                # source/raster engine. A newly incomplete formerly covered
                # network must not be certified by raster agreement alone.
                review_required=covered_a!=covered_b,
                connections_changed=supported and any(x['nets']!=y['nets'] for x,y in zip(a,b)),
                base_symbols=sa,compared_symbols=sb,
                base_elements=[dict(page=p['page'],**s) for p in a for s in p['symbols']],
                compared_elements=[dict(page=p['page'],**s) for p in b for s in p['symbols']],
                base_nets=[dict(page=p['page'],nets=p['nets']) for p in a],
                compared_nets=[dict(page=p['page'],nets=p['nets']) for p in b],
                open_checks=sorted(set(c for p in a+b for c in p['open_checks'])))
