"""Portable performance reports generated only from server-calculated records."""
from io import BytesIO, StringIO
import csv
from html import escape
import json


def display(value, unit=''):
    if value is None:
        return 'Not available'
    return f'{value:,.2f}' + (f' {unit}' if unit else '')


def export_dashboard(data, format):
    if format == 'json':
        return json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8'), 'application/json'
    if format == 'csv':
        output = StringIO(newline='')
        writer = csv.writer(output)
        query = data.get('query')
        if query and query.get('section') != 'overview':
            safe = lambda cell: "'"+str(cell) if isinstance(cell, str) and cell.lstrip().startswith(('=', '+', '-', '@')) else cell
            writer.writerow(['Question', safe(query['question'])])
            for table in query.get('tables', []):
                writer.writerow([])
                writer.writerow([safe(table['title'])])
                writer.writerow([safe(cell) for cell in table['headers']])
                writer.writerows([[safe(cell) for cell in row] for row in table['rows']])
            if not query.get('tables'):
                writer.writerow([safe(query.get('message', 'No matching report calculation.'))])
            return ('\ufeff'+output.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8'
        keys = [m['key'] for m in data['metrics'] if m['available'] and m['key'] not in {'daily_output', 'stop_events'}]
        labels = {m['key']: m['label'] + ' (' + m['unit'] + ')' for m in data['metrics']}
        production = any(s['kind'] == 'production' for s in data['sources'])
        stoppage = any(s['kind'] == 'stoppage' for s in data['sources'])
        writer.writerow(['Machine', *[labels[key] for key in keys], *(['Recorded run time (hours)'] if production else []), *(['Leading recorded stoppage reason'] if stoppage else [])])
        for machine in data['machines']:
            # Escape formula-like text in spreadsheets; numeric cells stay numeric.
            safe = lambda text: "'" + str(text) if str(text).lstrip().startswith(('=', '+', '-', '@')) else text
            writer.writerow([safe(machine['machine']), *[machine['values'].get(key) for key in keys],
                             *([machine.get('runtimeSeconds') / 3600 if machine.get('runtimeSeconds') is not None else ''] if production else []),
                             *([safe(machine.get('leadingReason', ''))] if stoppage else [])])
        return ('\ufeff' + output.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8'
    return _pdf(data), 'application/pdf'


def _pdf(data):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    from reportlab.graphics.shapes import Drawing, Rect, String, Line
    stream = BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(stream, pagesize=page, rightMargin=32, leftMargin=32, topMargin=35, bottomMargin=32,
                            title='Chopper performance analysis', author='uSOPp.ai')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('ReportTitle', fontName='Helvetica-Bold', fontSize=23, leading=28, textColor=colors.HexColor('#123d68'), spaceAfter=12))
    styles.add(ParagraphStyle('SectionTitle', fontName='Helvetica-Bold', fontSize=13, leading=18, textColor=colors.HexColor('#123d68'), spaceBefore=16, spaceAfter=9))
    styles.add(ParagraphStyle('SmallReport', fontSize=8, leading=11, textColor=colors.HexColor('#33465d')))
    width = page[0] - 64
    def p(value, style='SmallReport'):
        # ReportLab markup never receives raw workbook text.
        text = str(value).replace('≤', '<=').replace('≥', '>=').replace('³', '3').replace('→', 'to')
        return Paragraph(escape(text), styles[style])
    def table(headers, rows, widths=None):
        result = Table([[p(h) for h in headers], *[[p(cell) for cell in row] for row in rows]], colWidths=widths, repeatRows=1, hAlign='LEFT')
        result.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e6eff8')),
                                   ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f8fc')]),
                                   ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#d4dfeb')),
                                   ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 7),
                                   ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
        return result
    period, baseline = data['period'], data['comparison']
    query = data.get('query')
    if query and query.get('section') != 'overview':
        story = [p('uSOPp.ai / Chopper', 'ReportTitle'), p('Report question', 'ReportTitle'),
                 p(query['question'], 'SectionTitle'), p(f'{period["from"]} to {period["to"]}')]
        for item in query.get('tables', []):
            story.extend([p(item['title'], 'SectionTitle'), table(item['headers'], item['rows'], [width/len(item['headers'])]*len(item['headers']))])
        if not query.get('tables'):
            story.append(p(query.get('message', 'No matching report calculation.')))
        story.extend([p('Result notes', 'SectionTitle'), *[p('- '+note) for note in query.get('notes', [])]])
        for source in query.get('sources', []):
            story.extend([p(source['file']+' / '+source['sheet'], 'SectionTitle'),
                          p(f'Header row {source["headerRow"]}; {source["records"]} selected records; columns {", ".join(source.get("columns", []))}; summary rows excluded.')])
        def question_footer(canvas, doc):
            canvas.setFont('Helvetica', 8)
            canvas.drawString(32, 18, 'uSOPp.ai | Requested report columns | Historical records')
            canvas.drawRightString(page[0]-32, 18, str(doc.page))
        doc.build(story, onFirstPage=question_footer, onLaterPages=question_footer)
        return stream.getvalue()
    story = [p('uSOPp.ai / Chopper', 'ReportTitle'), p('Performance analysis', 'ReportTitle'),
             p(f'{period["from"] or "Undated"} to {period["to"] or "Undated"} | {data["machineCount"]} machines | {data["recordCount"]:,} detail records'),
             p(f'Comparison: {baseline["from"]} to {baseline["to"]}' if baseline else 'Comparison: disabled'),
             Spacer(1, 12), p('1. Executive summary', 'SectionTitle')]
    available = [m for m in data['metrics'] if m['value'] is not None]
    rows = []
    for metric in available:
        change = metric['change']
        difference = (display(change['absolute'], change['unit']) + (f' / {change["percent"]:+.2f}%' if change['percent'] is not None and change['unit'] != 'percentage points' else '')) if change else 'Not comparable'
        rows.append([metric['label'], display(metric['value'], metric['unit']), display(metric['previous'], metric['unit']), difference])
    story.append(table(['KPI', 'Selected period', 'Comparison period', 'Change'], rows, [width*.32, width*.23, width*.23, width*.22]))
    story.append(p('Change requires matched calendar-day and machine/shift coverage. Means are unweighted record means. Missing data is not zero.'))
    labels = {m['key']: m['label']+' ('+m['unit']+')' for m in data['metrics']}
    daily_keys = [m['key'] for m in data['metrics'] if m['available'] and m['key'] != 'daily_output']
    if any(source['kind'] == 'production' for source in data['sources']):
        story.extend([PageBreak(), p('Daily production and utilization', 'SectionTitle')])
        days = [d for d in data['daily'] if d.get('production') is not None]
        if days:
            chart_days = days[-31:]
            drawing = Drawing(width, 170)
            maximum = max(d['production'] for d in chart_days) or 1
            bar_width = (width-55)/len(chart_days)
            drawing.add(Line(35, 28, width-5, 28, strokeColor=colors.HexColor('#b9c8d7')))
            for index, day in enumerate(chart_days):
                height = day['production']/maximum * 115
                x = 37 + index*bar_width
                drawing.add(Rect(x, 29, max(2,bar_width-5), height, fillColor=colors.HexColor('#16a88c'), strokeColor=None))
                if len(chart_days) <= 14 or index % 3 == 0:
                    drawing.add(String(x, 14, day['date'][5:], fontSize=7, fillColor=colors.HexColor('#33465d')))
            drawing.add(String(35, 155, 'Production (kg); latest 31 dates shown', fontSize=9))
            story.append(drawing)
    # Keep tables readable and limited to the selected report families.
    for offset in range(0, len(daily_keys), 5):
        keys = daily_keys[offset:offset+5]
        story.extend([p('Daily measurements', 'SectionTitle'),
                      table(['Date', *[labels[key] for key in keys]],
                            [[d['date'], *[display(d.get(key)) for key in keys]] for d in data['daily']], [width/(len(keys)+1)]*(len(keys)+1))])
    if any(source['kind'] == 'stoppage' for source in data['sources']):
        story.extend([p('Stoppage analysis', 'SectionTitle'), table(['Recorded reason', 'Events', 'Duration (min)', 'Share %'],
                       [[r['reason'], r['events'], display(r['minutes']), display(r['share'])] for r in data['reasons']], [width*.61,width*.12,width*.15,width*.12])])
    story.extend([PageBreak(), p('Machine performance', 'SectionTitle')])
    machine_keys = [key for key in daily_keys if key != 'stop_events']
    for offset in range(0, len(machine_keys), 5):
        keys = machine_keys[offset:offset+5]
        story.append(table(['Machine', *[labels[key] for key in keys], 'KPI breaches'],
                           [[m['machine'], *[display(m['values'].get(key)) for key in keys], len(m['violations'])] for m in data['machines']],
                           [width/(len(keys)+2)]*(len(keys)+2)))
    if data['topMachines']:
        story.append(p('Top production: ' + ', '.join(data['topMachines'])))
        story.append(p('Lowest recorded production: ' + ', '.join(data['bottomMachines'])))
    story.extend([p('5. KPI compliance', 'SectionTitle'), table(['KPI', 'Measured', 'User target', 'Daily aggregates passing', 'Machines outside target', 'Status'],
                  [[m['label'], display(m['value'], m['unit']), (('<= ' if m['target']['operator']=='lte' else '>= ')+display(m['target']['value'], m['unit'])) if m['target'] else 'Not configured',
                    f'{m["daysPassing"]}/{m["daysMeasured"]}' if m['daysPassing'] is not None else 'Not assessed',
                    m['flaggedMachines'] if m['target'] else 'Not assessed', m['status']] for m in data['compliance']],
                  [width*.26,width*.16,width*.17,width*.16,width*.15,width*.10])])
    story.extend([PageBreak(), p('6. Key findings', 'SectionTitle')])
    for item in data['findings']:
        story.append(KeepTogether([p(item['title'], 'Heading3'), p(item['detail']), Spacer(1, 8)]))
    story.extend([p('7. Suggested action priority matrix', 'SectionTitle'), table(['Priority', 'Suggested action', 'Evidence', 'Owner / due date'],
                  [[a['priority'], a['action'], a['evidence'], a['owner']+' / '+a['due']] for a in data['actions']], [width*.09,width*.45,width*.27,width*.19])])
    story.extend([p('8. Coverage and calculation notes', 'SectionTitle'), *[p('- '+note) for note in data['notes']],
                  p('9. Worksheet provenance', 'SectionTitle')])
    for source in data['sources']:
        columns = ', '.join(c['column']+': '+c['label'] for c in source['columns'])
        selected_rows = source['rows']
        story.extend([p(source['file']+' / '+source['sheet'], 'Heading3'),
                      p(f'Header row {source["headerRow"]}; {source["records"]} selected detail records; {source["summaryRowsExcluded"]} summary rows excluded. Selected row span: {min(selected_rows) if selected_rows else "none"} to {max(selected_rows) if selected_rows else "none"}; rows inside this span may be excluded.'),
                      p(columns), p('SHA256: '+source['digest'])])
    def footer(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(32, 18, 'uSOPp.ai | Calculated from uploaded records | Historical data')
        canvas.drawRightString(page[0]-32, 18, str(doc.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
