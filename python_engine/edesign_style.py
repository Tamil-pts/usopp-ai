COLOURS={'modify':'#bb8100','add':'#008152','remove':'#d12b45','comment':'#2369b3'}
def color(mark):return mark.get('color') or COLOURS[mark['kind']]
def opacity(mark):return mark.get('opacity') if mark.get('opacity') is not None else (.28 if mark['shape']=='highlight' else .7 if mark['shape']=='marker' else 1)
def reference(mark,index=0):return mark.get('reference') or f'R{mark.get("referenceNo") or index:03}'
def reference_color(mark):
    ink=color(mark);r,g,b=(int(ink[i:i+2],16) for i in (1,3,5))
    return '#334155' if r*.299+g*.587+b*.114>175 else ink
