"""Normalized callout geometry shared by visible drawing export formats."""
import math


def default_callout(box, aspect=1, occupied=()):
    """Place a readable label near its region while avoiding other markups."""
    x0,y0,x1,y1=box;gap=.025;w=.23;h=max(.05,min(.13,.055*aspect))
    starts=[(x1+gap,y0),(x0-w-gap,y0),(x0,y1+gap),(x0,y0-h-gap)]
    starts.extend((x,y) for y in (.025,.2,.4,.6,.8) for x in (.015,.38,.75))
    def clamp(x,y):
        x=max(.01,min(1-w-.01,x));y=max(.01,min(1-h-.01,y))
        return [x,y,x+w,y+h]
    def overlap(a,b):return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))/(w*h)
    def score(candidate,index):
        cx,cy=(candidate[0]+candidate[2])/2,(candidate[1]+candidate[3])/2
        return 100*overlap(candidate,box)+60*sum(overlap(candidate,r) for r in occupied)+math.hypot(cx-(x0+x1)/2,cy-(y0+y1)/2)*.35+index*.003
    candidates=[(clamp(x,y),index) for index,(x,y) in enumerate(starts)]
    return min(candidates,key=lambda item:score(*item))[0]


def boundary(box,towards):
    x0,y0,x1,y1=box;cx,cy=(x0+x1)/2,(y0+y1)/2;dx,dy=towards[0]-cx,towards[1]-cy
    scale=min((x1-x0)/2/abs(dx) if dx else float('inf'),(y1-y0)/2/abs(dy) if dy else float('inf'))
    return (cx+dx*scale,cy+dy*scale) if math.isfinite(scale) else (x1,cy)


def leader(mark):
    box,label=mark['box'],mark['callout'];center=lambda r:((r[0]+r[2])/2,(r[1]+r[3])/2)
    start=boundary(label,center(box));tip=boundary(box,center(label))
    knee=(tip[0],start[1]) if abs(tip[0]-start[0])>=abs(tip[1]-start[1]) else (start[0],tip[1])
    # Avoid a zero-length final segment so arrow orientation stays defined.
    if math.dist(knee,tip)<1e-7:return [start,tip]
    return [start,knee,tip]


def draw_callout(canvas,mark,width,height,part='all'):
    from reportlab.lib.colors import HexColor,Color
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from xml.sax.saxutils import escape
    from .edesign_style import color as mark_color
    label=mark.get('callout')
    if not label:return
    color=HexColor(mark_color(mark));canvas.saveState();canvas.setStrokeColor(color);canvas.setLineWidth(1.2)
    if part in {'all','leader'}:
        points=[(x*width,(1-y)*height) for x,y in leader(mark)]
        for a,b in zip(points,points[1:]):canvas.line(*a,*b)
        a,b=points[-2:];angle=math.atan2(b[1]-a[1],b[0]-a[0]);size=min(5,width*.006)
        for delta in (-.5,.5):canvas.line(*b,b[0]-size*math.cos(angle+delta),b[1]-size*math.sin(angle+delta))
    if part in {'all','label'}:
        x0,y0,x1,y1=label;x,y=x0*width,(1-y1)*height;w,h=(x1-x0)*width,(y1-y0)*height;pad=min(5,w*.035,h*.12)
        canvas.setFillColor(Color(.94+.06*color.red,.94+.06*color.green,.94+.06*color.blue))
        canvas.rect(x,y,w,h,stroke=1,fill=1)
        font=max(5,min(14,width*.013))
        while True:
            paragraph=Paragraph(escape(mark['body']).replace('\n','<br/>'),ParagraphStyle('callout',fontName='Helvetica',fontSize=font,leading=font*1.25,textColor=HexColor('#17202b'),splitLongWords=True))
            _,needed=paragraph.wrap(max(1,w-2*pad),max(1,h-2*pad))
            if needed<=h-2*pad or font<=4:break
            font=max(4,font-.5)
        canvas.saveState();clip=canvas.beginPath();clip.rect(x+pad,y+pad,max(1,w-2*pad),max(1,h-2*pad));canvas.clipPath(clip,stroke=0,fill=0)
        paragraph.drawOn(canvas,x+pad,y+h-pad-needed);canvas.restoreState()
    canvas.restoreState()
