"""Portable static worksheet dashboard exports; no browser or remote BI dependency."""
import html,io,math
from xml.sax.saxutils import escape
from backend.core import spreadsheet_bi as bi

COLORS=['#11917e','#4d7df0','#edb344','#9764ca','#d86f86','#369eb5']

def svg(chart):
    points=chart['points'][:100];kind=chart['spec']['chart'];w,h=640,280
    nums=[float(p['y']) for p in points if p.get('y') is not None];low=min([0]+nums);high=max([0]+nums);span=high-low or 1
    labels=list(dict.fromkeys(str(p['x']) for p in points))
    fy=lambda value:230-(float(value)-low)/span*190
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(chart["title"],quote=True)}"><rect width="640" height="280" fill="white"/><line x1="45" y1="{fy(0):.2f}" x2="620" y2="{fy(0):.2f}" stroke="#98a7b5"/>']
    for i,p in enumerate(points):
        if p.get('y') is None:continue
        x=50+(i+.5)*560/max(1,len(points));y=fy(p['y'])
        if kind=='line':
            x=50+(labels.index(str(p['x']))+.5)*560/max(1,len(labels))
            series=p.get('series','');same=[(j,q) for j,q in enumerate(points[:i]) if q.get('series','')==series and q.get('y') is not None]
            if same:
                j,q=same[-1];px=50+(labels.index(str(q['x']))+.5)*560/max(1,len(labels))
                parts.append(f'<line x1="{px:.2f}" y1="{fy(q["y"]):.2f}" x2="{x:.2f}" y2="{y:.2f}" stroke="{COLORS[sorted(set(q.get("series","") for q in points)).index(series)%6]}" stroke-width="2"/>')
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{COLORS[0]}"/>')
        elif kind=='donut':
            total=sum(nums);start=sum(float(q.get('y') or 0) for q in points[:i])/total*360 if total else 0
            fraction=float(p['y'])/total if total else 0
            parts.append(f'<circle cx="320" cy="135" r="85" fill="none" stroke="{COLORS[i%6]}" stroke-width="40" stroke-dasharray="{fraction*534.071:.3f} 534.071" transform="rotate({start-90:.2f} 320 135)"/>')
        elif kind=='scatter':
            xs=[float(q['x']) for q in points];x=50+(float(p['x'])-min(xs))/(max(xs)-min(xs) or 1)*560
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{COLORS[0]}"/>')
        else:
            width=max(1,540/max(1,len(points)));height=abs(fy(0)-y)
            parts.append(f'<rect x="{x-width/2:.2f}" y="{min(y,fy(0)):.2f}" width="{width:.2f}" height="{height:.2f}" fill="{COLORS[i%6]}"/>')
        if i%max(1,len(points)//6)==0:parts.append(f'<text x="{x:.2f}" y="255" text-anchor="middle" font-size="10" fill="#334155">{escape(str(p["x"])[:14])}</text>')
    parts.append('</svg>');return ''.join(parts)


def export(user,payload,format):
    if payload.get('dashboardId'):record=bi.saved(user,payload['dashboardId']);value=record['dashboard'];title=record['title']+' (saved snapshot)'
    else:value=bi.selected_dashboard(user,payload);title=str(payload.get('title','Chopper worksheet dashboard'))[:120]
    source=value['source'];reference=f'{source["file"]} / {source["sheet"]} / header row {source["header_row"]} / SHA256 {source["sha256"]}'
    if format=='html':
        sections=[]
        for chart in value['charts']:
            rows=''.join('<tr><td>'+html.escape(str(p.get('series',''))+' '+str(p['x']))+'</td><td>'+html.escape(str(p['y']))+'</td></tr>' for p in chart['points'][:100])
            sections.append('<article><h2>'+html.escape(chart['title'])+'</h2>'+svg(chart)+'<p>'+html.escape(chart['caption'])+'</p><details><summary>Computed values (first 100)</summary><table><tr><th>Group / X</th><th>Value / Y</th></tr>'+rows+'</table></details></article>')
        output='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>body{font:16px system-ui;background:#f3f6fa;color:#162e3b;max-width:1200px;margin:auto;padding:24px}article,header{padding:20px;border-radius:14px;background:white;margin:16px 0}svg{width:100%;max-height:350px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:6px;border-bottom:1px solid #ddd}p{overflow-wrap:anywhere}@media print{details{display:block}article{break-inside:avoid}}</style><header><h1>'+html.escape(title)+'</h1><p>'+html.escape(reference)+'</p>'+''.join('<p>'+html.escape(i['text'])+'</p>' for i in value['insights'])+'</header>'+''.join(sections)+'<footer>'+''.join('<p>'+html.escape(n)+'</p>' for n in value['notes'])+'<p>Portable chart views retain the selected chart type. First 100 points per export chart; use the source download for complete data.</p></footer></html>'
        return output.encode('utf-8')
    if format!='pdf':raise ValueError('Choose HTML or PDF.')
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Table,TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg
    output=io.BytesIO();doc=SimpleDocTemplate(output,pagesize=landscape(A4),rightMargin=36,leftMargin=36,topMargin=32,bottomMargin=32);styles=getSampleStyleSheet();story=[Paragraph(escape(title),styles['Title']),Paragraph(escape(reference),styles['BodyText']),Spacer(1,12)]
    story.extend(Paragraph(escape(i['text']),styles['BodyText']) for i in value['insights'])
    for chart in value['charts']:
        story.extend([PageBreak(),Paragraph(escape(chart['title']),styles['Heading1']),Paragraph(escape(chart['caption']),styles['BodyText'])])
        drawing=svg2rlg(io.BytesIO(svg(chart).encode()));drawing.scale(.95,.95);drawing.width*=.95;drawing.height*=.95;story.append(drawing)
        table=Table([['Group / X','Value / Y']]+[[Paragraph(escape(str(p.get('series',''))+' '+str(p['x'])),styles['BodyText']),str(p['y'])] for p in chart['points'][:12]],colWidths=[430,180])
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf4f2')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.append(table)
    story.extend([Spacer(1,10),Paragraph('Charts show the first 100 points; table excerpts show the first 12. Use source downloads for complete data.',styles['BodyText'])]);story.extend(Paragraph(escape(n),styles['BodyText']) for n in value['notes']);doc.build(story);return output.getvalue()
