"""Portable comparison report containing the complete change register and image evidence."""
from pathlib import Path
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether

from python_engine.circuit_compare import analysis


def build_report(result, folder, target):
    folder, target = Path(folder), Path(target)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('CircuitSmall', fontSize=8, leading=10, spaceAfter=4, alignment=TA_LEFT, wordWrap='CJK'))
    styles.add(ParagraphStyle('CircuitCell', fontSize=7, leading=9, wordWrap='CJK'))
    def p(value, small=False):
        # Retain the full original text in JSON/original PDF. Helvetica lacks
        # arbitrary CAD glyphs; readable substitutions here avoid black squares.
        text = str(value or '—').replace('→', ' -> ').replace('·', ' / ').replace('–', '-').replace('—', '-')
        return Paragraph(escape(text).replace('\n', '<br/>'), styles['CircuitCell' if small else 'CircuitSmall'])
    def marked_image(info, marks):
        if not marks:return Image(str(folder / info['image']),width=370,height=230,kind='proportional')
        from PIL import Image as PILImage, ImageDraw
        palette={'blue':'#2275d7','red':'#d22e42','amber':'#c48a00','green':'#00875e','purple':'#9552b3'}
        picture=PILImage.open(folder / info['image']).convert('RGBA');layer=PILImage.new('RGBA',picture.size);draw=ImageDraw.Draw(layer)
        w,h=picture.size
        for mark in marks:
            x0,y0,x1,y1=mark['box'];box=(int(x0*w),int(y0*h),int(x1*w),int(y1*h));color=palette[mark['color']]
            if mark['shape']=='arrow':
                import math
                sx,ex=(box[2],box[0]) if mark.get('reverseX') else (box[0],box[2])
                sy,ey=(box[3],box[1]) if mark.get('reverseY') else (box[1],box[3])
                dx,dy=ex-sx,ey-sy;length=math.hypot(dx,dy) or 1;ux,uy=dx/length,dy/length
                draw.line((sx,sy,ex,ey),fill=color,width=4)
                draw.line((ex-ux*15-uy*7,ey-uy*15+ux*7,ex,ey,ex-ux*15+uy*7,ey-uy*15-ux*7),fill=color,width=4)
            else:
                draw.rectangle(box,fill=(*bytes.fromhex(color[1:]),45),outline=color,width=3)
                if mark['shape']=='cloud':
                    radius=max(3,min(12,int(min(box[2]-box[0],box[3]-box[1])/5)))
                    for x in range(box[0],box[2],radius*2):
                        draw.arc((x,box[1]-radius,x+radius*2,box[1]+radius),180,360,fill=color,width=3)
                        draw.arc((x,box[3]-radius,x+radius*2,box[3]+radius),0,180,fill=color,width=3)
                    for y in range(box[1],box[3],radius*2):
                        draw.arc((box[0]-radius,y,box[0]+radius,y+radius*2),90,270,fill=color,width=3)
                        draw.arc((box[2]-radius,y,box[2]+radius,y+radius*2),270,90,fill=color,width=3)
            draw.text((box[0]+3,box[1]+3),mark['id'][:6],fill=color,stroke_width=1,stroke_fill='white')
        output=BytesIO();PILImage.alpha_composite(picture,layer).convert('RGB').save(output,format='PNG');output.seek(0)
        return Image(output,width=370,height=230,kind='proportional')
    story = [Paragraph('MatchView / Circuit Compare', styles['Title']),
             p('Base: ' + result['baseName']), p('Developed: ' + result['developedName']),
             p('Session: ' + result.get('sessionId', 'local comparison')),
             p(f"{len(result['basePages'])} base pages / {len(result['developedPages'])} developed pages / "
               f"{result['summary']['changes']} source-object changes / {result['summary']['changedPages']} changed page pairs"),
             p(f"{result['summary'].get('uncertainFindings',0)} uncertain extraction/geometry checks are separate from the change count. Full details are retained in the JSON export and object inspector."),
             p('Detected differences require engineering review. This report does not certify electrical continuity, safety or functional equivalence.')]
    findings = analysis(result)
    for area in findings['areas']:
        story.extend([Paragraph(area['category'], styles['Heading2']), p(f"{area['count']} findings. {area['possibleImpact']}"), p(area['verify'])])
    story.append(Paragraph('Extraction and comparison limits', styles['Heading2']))
    story.extend(p(v) for v in result['limitations'])
    for pair in result['pairs']:
        story.extend([PageBreak(), Paragraph(f"{pair['id']} / Base {pair['base'] or '-'} : Developed {pair['developed'] or '-'}", styles['Heading1']),
                      p(pair['title']), p(f"Page match: {pair['match']}. {'Verify page identity.' if pair['matchReview'] else ''}"),
                      p(f"Page status: {pair['status']}. {pair['changeCount']} detected changes. {pair.get('uncertainCount',0)} separate uncertain checks.")])
        columns = []
        for side, number in [('base', pair['base']), ('developed', pair['developed'])]:
            if number:
                pages = result['basePages'] if side == 'base' else result['developedPages']
                info = pages[number - 1]
                image = marked_image(info,[mark for mark in result.get('markups',[]) if mark['pairId']==pair['id'] and mark['side']==side])
                columns.append([p(f'{side.title()} / page {number}'), image])
            else:
                columns.append([p('Page absent')])
        story.append(Table([[columns[0], columns[1]]], colWidths=[385, 385], style=[('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        marks=[mark for mark in result.get('markups',[]) if mark['pairId']==pair['id']]
        if marks:
            story.append(Paragraph('Engineer markups', styles['Heading2']))
            for mark in marks:
                story.append(p(f"{mark['id'][:6]} / {mark['side'].title()} page {mark['page']} / {mark['shape']} / {mark['status']} / {mark['author']}: {mark['text']}"))
        if pair.get('overlay'):
            info = result['basePages'][pair['base'] - 1]
            story.extend([p('Diagnostic local pixel overlay: red = removed pixels; green = added pixels. Uncorroborated render residuals are not engineering change findings.'),
                          Image(str(folder / pair['overlay']), width=580, height=340, kind='proportional')])
        for side, number in [('base', pair['base']), ('developed', pair['developed'])]:
            if number:
                pages = result['basePages'] if side == 'base' else result['developedPages']
                story.extend(p(f'{side.title()} page {number}: {notice}') for notice in pages[number - 1]['notices'])
        for side,number in [('base',pair['base']),('developed',pair['developed'])]:
            if not number:continue
            info=result['basePages' if side=='base' else 'developedPages'][number-1];objects=info.get('objects') or {}
            if objects:
                story.append(p(f"{side.title()} objects: {objects.get('textLabels',0)} labels, {objects.get('componentReferences',0)} component references, "
                               f"{objects.get('terminalReferences',0)} terminal labels, {objects.get('drawnLines',0)} drawn lines, "
                               f"{objects.get('candidateConnections',0)} connection candidates and {objects.get('geometricPaths',0)} geometric-only paths. "
                               'Cable/symbol outlines are not electrical nets. Endpoint/dot joins only; proximity-based terminal associations require verification.'))
        entries = [c for c in result['changes'] if c['pairId'] == pair['id']]
        if entries:
            story.append(Paragraph('Source-linked change register', styles['Heading2']))
            data = [[p(h, True) for h in ['ID / category', 'Base value / page', 'Developed value / page', 'Review / check']]]
            for item in entries:
                def ref(value):
                    if not value: return 'Absent'
                    return f"Page {value['page']} / {value['text']}\nBox: {', '.join(f'{n:.3f}' for n in value['bbox'])}"
                data.append([p(f"{item['id']} / {item['status']}\n{item['category']}\n{item['label']}", True),
                             p(ref(item['before']), True), p(ref(item['after']), True),
                             p(f"{item['review']} / {item['extraction']}\n{item['verification']}\n{item.get('note', '')}", True)])
            table = Table(data, colWidths=[135, 205, 205, 225], repeatRows=1, hAlign='LEFT', splitInRow=1)
            table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e7eef3')),
                                       ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('GRID', (0, 0), (-1, -1), .25, colors.HexColor('#c6d2db')),
                                       ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5)]))
            story.append(table)
        else:
            story.append(p('No corroborated source-object differences detected. This does not resolve any separately listed extraction or connection-interpretation checks.'))
    def footer(canvas, doc):
        canvas.saveState(); canvas.setFont('Helvetica', 8)
        canvas.drawString(28, 18, 'uSOPp.ai / MatchView / Circuit comparison / Engineer review required')
        canvas.drawRightString(813, 18, f'Page {doc.page}'); canvas.restoreState()
    SimpleDocTemplate(str(target), pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=32,
                      title='Circuit comparison / ' + result['developedName'], author='uSOPp.ai MatchView').build(story, onFirstPage=footer, onLaterPages=footer)
    return target
