"""Aligned original source with formatting-only line changes ignored."""
import difflib
import re

def line_key(line):
    # Whitespace inside quoted strings remains significant.
    return tuple(re.findall(r"'(?:[^']|'')*'|\"(?:[^\"\\]|\\.)*\"|[A-Za-z_]\w*|\d+(?:\.\d+)?|:=|<=|>=|<>|\S", line))

def aligned_source(base, developed):
    left=base.splitlines(); right=developed.splitlines()
    a=[(i,line_key(line)) for i,line in enumerate(left) if line.strip()]
    b=[(i,line_key(line)) for i,line in enumerate(right) if line.strip()]
    matcher=difflib.SequenceMatcher(None,[key for _,key in a],[key for _,key in b],autojunk=False)
    rows=[]; li=ri=0
    def append(l,r,state):
        rows.append({'base_line':l+1 if l is not None else None,'new_line':r+1 if r is not None else None,
                     'base':left[l] if l is not None else None,'new':right[r] if r is not None else None,'status':state})
    def blanks(lend,rend):
        nonlocal li,ri
        while li<lend or ri<rend:
            append(li if li<lend else None,ri if ri<rend else None,'unchanged')
            li=min(li+1,lend);ri=min(ri+1,rend)
    for tag,i1,i2,j1,j2 in matcher.get_opcodes():
        for k in range(max(i2-i1,j2-j1)):
            l=a[i1+k][0] if i1+k<i2 else None
            r=b[j1+k][0] if j1+k<j2 else None
            blanks(l if l is not None else li,r if r is not None else ri)
            append(l,r,'unchanged' if tag=='equal' else 'modified' if l is not None and r is not None else 'removed' if l is not None else 'added')
            if l is not None:li=l+1
            if r is not None:ri=r+1
    blanks(len(left),len(right))
    return rows

def source_windows(rows, context=5):
    changed=[i for i,row in enumerate(rows) if row['status']!='unchanged']
    spans=[]
    for i in changed:
        start=max(0,i-context);end=min(len(rows),i+context+1)
        if spans and start<=spans[-1][1]:spans[-1][1]=end
        else:spans.append([start,end])
    return spans

def source_diff(base, developed, max_hunks=80, context=5):
    rows=aligned_source(base,developed)
    spans=source_windows(rows,context)
    hunks=[]
    for start,end in spans[:max_hunks]:
        lines=[]
        for row in rows[start:end]:
            if row['status']=='unchanged':
                lines.append({'t':'ctx','bl':row['base_line'],'nl':row['new_line'],'text':row['base'] if row['base'] is not None else row['new']})
            else:
                if row['base'] is not None:lines.append({'t':'del','bl':row['base_line'],'nl':None,'text':row['base'],'status':row['status']})
                if row['new'] is not None:lines.append({'t':'add','bl':None,'nl':row['new_line'],'text':row['new'],'status':row['status']})
        hunks.append({'tag':'replace','base_start':next((r['base_line'] for r in rows[start:end] if r['base_line']),0),
                      'new_start':next((r['new_line'] for r in rows[start:end] if r['new_line']),0),'lines':lines})
    return {'base_lines':len(base.splitlines()),'new_lines':len(developed.splitlines()),'source_rows':rows,'hunks':hunks,
            'added':[(r['new_line'],r['new']) for r in rows if r['status'] in {'added','modified'} and r['new'] is not None],
            'removed':[(r['base_line'],r['base']) for r in rows if r['status'] in {'removed','modified'} and r['base'] is not None]}
