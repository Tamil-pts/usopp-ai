"""Page-scoped text/reference and vector-path graph for electrical drawings.

Graph geometry is read from PDF primitives. A crossing is not a junction unless
there is an endpoint or explicit junction dot. Nearby labels supply candidate
terminal associations, not a certified electrical netlist.
"""
from collections import defaultdict, deque
import math
import re

from python_engine.circuit_visual import transform_box

TERMINAL = re.compile(r'(?<![A-Z0-9])(?:X[A-Z]*\d*|[MBKQSUY]\d+)[-:](?:\d+|[A-Z]+\d*)(?:\([^)]*\))?', re.I)
COMPONENT = re.compile(r'(?<![A-Z0-9])(?:X[A-Z]*\d+|[MBKQSUY]\d+)(?![A-Z0-9])', re.I)


def drawing_frame(page):
    """Detect the inner drawing frame from long PDF vector edges, not text."""
    w,h=page.width,page.height
    edges=page.edges
    vertical=[e for e in edges if e.get('orientation')=='v' and e['height']>.7*h]
    left=[e for e in vertical if e['x0']<.08*w];right=[e for e in vertical if e['x0']>.92*w]
    if not left or not right:return None
    l=max(left,key=lambda e:e['x0']);r=min(right,key=lambda e:e['x0'])
    if abs(l['top']-r['top'])>2 or abs(l['bottom']-r['bottom'])>2:return None
    bounds=[l['x0']/w,max(l['top'],r['top'])/h,r['x0']/w,min(l['bottom'],r['bottom'])/h]
    horizontal=[e for e in edges if e.get('orientation')=='h' and e['width']>.8*w]
    rulers=[e['top']/h for e in horizontal if bounds[1]+.007<e['top']/h<bounds[1]+.07]
    footers=[e['top']/h for e in horizontal if .82<e['top']/h<bounds[3]-.007]
    return {'bbox':bounds,'bodyTop':max(rulers)+.004 if rulers else bounds[1]+.004,
            'footerTop':min(footers)-.003 if footers else .90}


def _overlap(a,b,margin=0):
    return a[0]<=b[2]+margin and b[0]<=a[2]+margin and a[1]<=b[3]+margin and b[1]<=a[3]+margin


def _normal(bounds,w,h):return [bounds[0]/w,bounds[1]/h,bounds[2]/w,bounds[3]/h]


def _point_distance(point,a,b):
    vx,vy=b[0]-a[0],b[1]-a[1];den=vx*vx+vy*vy
    t=((point[0]-a[0])*vx+(point[1]-a[1])*vy)/den if den else 0
    closest=(a[0]+max(0,min(1,t))*vx,a[1]+max(0,min(1,t))*vy)
    return math.dist(point,closest),t


def _bbox_distance(point,bounds):
    x,y=point;return math.hypot(max(bounds[0]-x,0,x-bounds[2]),max(bounds[1]-y,0,y-bounds[3]))


def build_scene(page, segments, tables):
    w,h=page.width,page.height;frame=drawing_frame(page)
    labels=[]; terminals=[]; components={}; label_ids={}
    for i,s in enumerate(segments):
        label={'id':f'L{i+1}', 'kind':'label','text':s['text'],'bbox':s['bbox'],'uncertain':s.get('uncertain',False)}
        labels.append(label);value=s['text'].upper()
        # Some CAD exports store rotated references in top-to-bottom glyph order.
        if re.fullmatch(r'\d+[A-Z]+',value) and re.fullmatch(r'X[A-Z]*\d+|[MBKQSUY]\d+',value[::-1]):value=value[::-1]
        for match in TERMINAL.finditer(value):
            ref=match.group();node={**label,'id':f'T{len(terminals)+1}','kind':'terminal','reference':ref,
                                   'standalone':re.sub(r'\s+','',value)==ref,'sourceLabel':label['id']}
            terminals.append(node)
        for match in COMPONENT.finditer(value):
            ref=match.group()
            if ref not in components or len(value)<len(components[ref]['text']):
                components[ref]={**label,'id':'R'+ref,'kind':'component','reference':ref,'sourceLabel':label['id']}
    images=[_normal((i['x0'],i['top'],i['x1'],i['bottom']),w,h) for i in page.images]
    exclusions=[t['bbox'] for t in tables]+images
    text_boxes=[s['bbox'] for s in segments]
    lines=[];shapes=[];dots=[]
    def add_line(a,b):
        if math.dist(a,b)<8:return
        bounds=_normal((min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])),w,h)
        if bounds[0]<.025 or bounds[2]>.975 or bounds[1]<(frame['bodyTop'] if frame else .025) or bounds[3]>(frame['footerTop'] if frame else .90):return
        if any(_overlap(bounds,x,.001) for x in exclusions):return
        midpoint=((a[0]+b[0])/2/w,(a[1]+b[1])/2/h)
        if any(x[0]-.002<=midpoint[0]<=x[2]+.002 and x[1]-.002<=midpoint[1]<=x[3]+.002 for x in text_boxes):return
        points=[[round(a[0]/w,6),round(a[1]/h,6)],[round(b[0]/w,6),round(b[1]/h,6)]]
        signature=tuple(sorted(tuple(round(v,4) for v in p) for p in points))
        if signature in label_ids:return
        label_ids[signature]=True
        lines.append({'id':f'W{len(lines)+1}','kind':'drawn_line','points':points,'bbox':bounds})
    for item in page.lines:
        pts=item.get('pts') or []
        if len(pts)==2:add_line(pts[0],pts[1])
    for item in [*page.rects,*page.curves]:
        bounds=_normal((item['x0'],item['top'],item['x1'],item['bottom']),w,h)
        if bounds[0]<.025 or bounds[2]>.975 or bounds[1]<(frame['bodyTop'] if frame else .025) or bounds[3]>(frame['footerTop'] if frame else .90):continue
        if any(_overlap(bounds,x,.001) for x in exclusions):continue
        iw,ih=item['width'],item['height'];path=item.get('path') or []
        # A filled, thin rectangle can be a re-exported stroked line.
        if item.get('fill') and min(iw,ih)<1.7 and max(iw,ih)>=8:
            if iw>ih:add_line((item['x0'],(item['top']+item['bottom'])/2),(item['x1'],(item['top']+item['bottom'])/2))
            else:add_line(((item['x0']+item['x1'])/2,item['top']),((item['x0']+item['x1'])/2,item['bottom']))
        elif len(path)<=4 and all(p[0] in {'m','l'} for p in path):
            for first,last in zip(path,path[1:]):
                if first[0] in {'m','l'} and last[0]=='l':add_line(first[1],last[1])
        elif .5<=iw<=4 and .5<=ih<=4 and abs(iw-ih)<.6 and item.get('fill') and any(p[0]=='c' for p in path):
            dots.append(((item['x0']+item['x1'])/2,(item['top']+item['bottom'])/2))
        elif 6<iw<110 and 6<ih<110 and (item.get('object_type')=='rect' or any(p[0]=='c' for p in path)):
            if not any(_overlap(bounds,x,.001) for x in text_boxes):
                shapes.append({'id':f'S{len(shapes)+1}','kind':'symbol_shape','bbox':bounds,
                               'shape':'rectangle' if item.get('object_type')=='rect' else 'curved symbol',
                               'interpretation':'Unclassified drawn symbol; physical function requires verification.'})
    partial=len(lines)>2000
    graph_lines=lines[:2000]
    absolute=[([(x*w,y*h) for x,y in edge['points']],edge['id']) for edge in graph_lines]
    vertices=[];buckets=defaultdict(list)
    def vertex(point):
        cell=(int(point[0]),int(point[1]))
        for ox in (-1,0,1):
            for oy in (-1,0,1):
                for i in buckets[(cell[0]+ox,cell[1]+oy)]:
                    if math.dist(vertices[i],point)<=.7:return i
        i=len(vertices);vertices.append(point);buckets[cell].append(i);return i
    for points,_ in absolute:
        for point in points:vertex(point)
    for dot in dots:vertex(dot)
    adjacency=defaultdict(set);edge_refs=defaultdict(set)
    for (a,b),edge_id in absolute:
        cut=[]
        for i,p in enumerate(vertices):
            distance,t=_point_distance(p,a,b)
            if distance<=.7 and -.001<=t<=1.001:cut.append((max(0,min(1,t)),i))
        cut.sort()
        for (_,u),(_,v) in zip(cut,cut[1:]):
            if u!=v:adjacency[u].add(v);adjacency[v].add(u);edge_refs[(min(u,v),max(u,v))].add(edge_id)
    crossings=[]
    for i,((a,b),aid) in enumerate(absolute):
        for (c,d),bid in absolute[i+1:]:
            den=(b[0]-a[0])*(d[1]-c[1])-(b[1]-a[1])*(d[0]-c[0])
            if abs(den)<1e-7:continue
            t=((c[0]-a[0])*(d[1]-c[1])-(c[1]-a[1])*(d[0]-c[0]))/den
            u=((c[0]-a[0])*(b[1]-a[1])-(c[1]-a[1])*(b[0]-a[0]))/den
            if 0<t<1 and 0<u<1:
                point=(a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]))
                if not any(math.dist(point,p)<.8 for p in vertices):
                    crossings.append({'lines':[aid,bid],'point':[point[0]/w,point[1]/h],
                                      'status':'No endpoint or explicit dot: not joined.'})
    associations=[]
    for terminal in terminals:
        if not terminal['standalone']:continue
        x0,y0,x1,y1=terminal['bbox'];bounds=x0*w,y0*h,x1*w,y1*h
        candidates=sorted((_bbox_distance(point,bounds),i) for i,point in enumerate(vertices) if len(adjacency[i])==1)
        if candidates and candidates[0][0]<=8 and (len(candidates)==1 or candidates[1][0]-candidates[0][0]>=2):
            associations.append({'terminal':terminal['id'],'reference':terminal['reference'],'vertex':candidates[0][1],
                                 'distancePoints':round(candidates[0][0],2),'status':'inferred proximity; verify terminal-to-wire binding'})
    compact_text=re.sub(r'\s+','', ' '.join(s['text'] for s in segments)).upper()
    assembly = 'CABLEKIT' in compact_text or ('S.NO' in compact_text and ('SQMM' in compact_text or 'SQ.MM' in compact_text))
    drawing_kind='cable assembly / manufacturing drawing' if assembly else 'unclassified engineering drawing'
    connections=[];geometric_paths=[]
    for index,start in enumerate(associations):
        queue=deque([start['vertex']]);seen={start['vertex']};parents={}
        while queue:
            u=queue.popleft()
            for v in adjacency[u]:
                if v not in seen:seen.add(v);parents[v]=u;queue.append(v)
        for end in associations[index+1:]:
            if end['vertex'] not in seen or start['reference']==end['reference']:continue
            ids=set();v=end['vertex'];points=[vertices[v]]
            while v!=start['vertex']:
                u=parents[v];ids.update(edge_refs[(min(u,v),max(u,v))]);v=u;points.append(vertices[v])
            item={'from':start['reference'],'to':end['reference'],'lineIds':sorted(ids),
                  'path':[[x/w,y/h] for x,y in reversed(points)]}
            has_cycle=sum(len(adjacency[i]) for i in seen)//2>=len(seen)
            if assembly or has_cycle:
                item['status']='Geometric path only: cable/symbol outlines or cyclic drawing contours do not establish electrical connectivity.'
                geometric_paths.append(item)
            else:
                item['status']='continuous drawn path; terminal associations require verification'
                connections.append(item)
    # Explicit connection tables are a stronger source than proximity. Only
    # accept a single fully printed terminal reference on each named side.
    for table in tables:
        if table['category']!='Connections':continue
        for row in table['rows']:
            left=[c for c in row['cells'] if re.search(r'SIDE\s*[- ]?A|\bFROM\b|SOURCE',c['label'],re.I)]
            right=[c for c in row['cells'] if re.search(r'SIDE\s*[- ]?B|\bTO\b|DESTINATION',c['label'],re.I)]
            if len(left)!=1 or len(right)!=1:continue
            aa,bb=TERMINAL.findall(left[0]['text']),TERMINAL.findall(right[0]['text'])
            if len(aa)==len(bb)==1:
                connections.append({'from':aa[0],'to':bb[0],'lineIds':[],
                    'sourceCells':[{'text':c['text'],'bbox':c['bbox']} for c in (left[0],right[0])],
                    'status':'Explicit printed connection-table mapping; verify drawing applicability.'})
    return {'schemaVersion':'1.1','frame':frame,'labels':labels,'terminals':terminals,'components':list(components.values()),
            'symbols':shapes,'lines':lines,'vertices':[{'id':f'N{i}','point':[p[0]/w,p[1]/h],'degree':len(adjacency[i])} for i,p in enumerate(vertices)],
            'drawingKind':drawing_kind,'crossings':crossings,'terminalAssociations':associations,'connections':connections,'geometricPaths':geometric_paths,
            'coverage':{'textLabels':len(labels),'componentReferences':len(components),'terminalReferences':len(terminals),
                        'symbolShapes':len(shapes),'drawnLines':len(lines),'candidateConnections':len(connections),'geometricPaths':len(geometric_paths),
                        'unjoinedCrossings':len(crossings),'graphPartial':partial,
                        'netlistVerified':False,'method':'PDF text objects, vector endpoints, explicit dots and bounded path traversal'},
            'limitations':['Component references are printed labels, not proof of installed equipment.',
                           'Cable-assembly outlines and cyclic contours are geometric paths, never automatically treated as electrical nets.',
                           'Only clear endpoint/dot joins are traversed. A plain crossing is not a junction.',
                           'Terminal-to-wire proximity is inferred. Verify every candidate connection against pin/symbol semantics.',
                           'Unclassified symbols and non-selectable text remain unresolved; no electrical netlist or safety approval is claimed.']}


def uncovered_lines(source,target,transform,width,height,inverse=False):
    """Compare line coverage, so one line and two collinear segments are equal."""
    peers=[]
    for item in target:
        pts=[]
        for x,y in item['points']:
            point=transform_box([x,y,x,y],transform,inverse=inverse)
            pts.append((point[0]*width,point[1]*height))
        peers.append(pts)
    residuals=[]
    for item in source:
        a,b=[(x*width,y*height) for x,y in item['points']];length=math.dist(a,b)
        if length<1:continue
        intervals=[]
        for c,d in peers:
            dc,tc=_point_distance(c,a,b);dd,td=_point_distance(d,a,b)
            vx,vy=b[0]-a[0],b[1]-a[1]
            # Infinite-line perpendicular distance is independent of projection.
            pc=abs((c[0]-a[0])*vy-(c[1]-a[1])*vx)/length
            pd=abs((d[0]-a[0])*vy-(d[1]-a[1])*vx)/length
            if max(pc,pd)<=1.5 and max(tc,td)>=0 and min(tc,td)<=1:
                intervals.append((max(0,min(tc,td)),min(1,max(tc,td))))
        cursor=0;gaps=[]
        for start,end in sorted(intervals):
            if start>cursor:gaps.append((cursor,start))
            cursor=max(cursor,end)
        if cursor<1:gaps.append((cursor,1))
        for start,end in gaps:
            if (end-start)*length<2.5:continue
            p=[a[0]+start*(b[0]-a[0]),a[1]+start*(b[1]-a[1])]
            q=[a[0]+end*(b[0]-a[0]),a[1]+end*(b[1]-a[1])]
            residuals.append({'sourceLine':item['id'],'points':[[p[0]/width,p[1]/height],[q[0]/width,q[1]/height]],
                              'bbox':[min(p[0],q[0])/width,min(p[1],q[1])/height,max(p[0],q[0])/width,max(p[1],q[1])/height]})
    return residuals
