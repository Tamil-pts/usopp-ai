"""Complete rule-run exports, including evidence from every pipeline stage."""
import base64
import json
import re
from html import escape
from pathlib import Path
from backend.core.report_cover import COVER_CSS, cover_html, cover_pdf_story


def text(value):
    if isinstance(value, dict):
        value = '\n\n'.join(re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', str(key)).replace('_', ' ').capitalize() + ':\n' + text(entry)
                            for key, entry in value.items())
    elif isinstance(value, list):
        value = '\n\n'.join((f'Finding {index + 1}\n' if isinstance(entry, dict) else '') + text(entry)
                            for index, entry in enumerate(value))
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value if value is not None else ''))


def ordered_results(result):
    def natural(value):
        return tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in re.split(r'(\d+)', str(value)))
    return sorted(result.get('results') or [], key=lambda item: (natural(item.get('name') or item.get('id', '')), natural(item.get('id', ''))))


def sections(item):
    # Include all remaining structured data so no configured alternative,
    # comparison, source location or finding is dropped from the report.
    for key, label in [('expected', 'Expected'), ('actual', 'Actual result'),
                       ('evidence', 'Findings / evidence'), ('recommendations', 'Recommendations'),
                       ('sourceFiles', 'Source files'), ('logicComparisons', 'Expected logic / actual source / differences'),
                       ('structuredRequirements', 'Requirements'), ('ruleDefinition', 'Rule configuration')]:
        if item.get(key) is not None:
            yield label, text(item[key])
    extra = {key: value for key, value in item.items() if key not in {'id', 'name', 'status', 'expected', 'actual', 'evidence', 'recommendations', 'sourceFiles', 'logicComparisons', 'structuredRequirements', 'ruleDefinition'}}
    if extra:
        yield 'Stage and additional evidence', text(extra)


def export_html(result: dict, path: Path, cover: dict, logo: Path):
    items = ordered_results(result)
    logo_html = '<img alt="uSOPp.ai" width="76" src="data:image/png;base64,' + base64.b64encode(logo.read_bytes()).decode('ascii') + '">' if logo.is_file() else ''
    summary = {key: value for key, value in result.items() if key != 'results'}
    rows = ''.join(f'<tr><td>{i}</td><td>{escape(text(item.get("name") or item.get("id")))}</td><td>{escape(text(item.get("standardId") or item.get("id")))}</td><td>{escape(text(item.get("status")))}</td></tr>' for i, item in enumerate(items, 1))
    details = ''.join(f'<section class="rule"><h2>{i}. {escape(text(item.get("name") or item.get("id")))}</h2><p><b>{escape(text(item.get("standardId") or item.get("id")))} · {escape(text(item.get("status")))}</b></p>' + ''.join(f'<h3>{label}</h3><pre>{escape(value)}</pre>' for label, value in sections(item)) + '</section>' for i, item in enumerate(items, 1))
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>LogicScan / ResultView</title><style>
    {COVER_CSS}body{{font:14px/1.5 Segoe UI,Arial,sans-serif;color:#172033;background:#fff;max-width:1100px;margin:auto;padding:24px}}h1,h2,h3{{color:#143759}}table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border:1px solid #ccd7e3;text-align:left;overflow-wrap:anywhere}}th{{background:#edf3f8}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7fb;border:1px solid #d9e2eb;padding:12px;font-size:12px}}.rule{{margin-top:30px;border-top:3px solid #143759}}@page{{size:A4;margin:16mm}}@media print{{body{{padding:0;max-width:none}}h2,h3{{break-after:avoid}}thead{{display:table-header-group}}}}
    </style></head><body>{logo_html}{cover_html(cover, 'LogicScan — Complete validation result')}<h1>ResultView / LogicScan</h1><p>{len(items)} rule checks · All outcomes and evidence from this run</p><table><thead><tr><th>No.</th><th>Rule name</th><th>Rule ID</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table><h2>Run summary and flow outcomes</h2><pre>{escape(text(summary))}</pre>{details}</body></html>'''
    path.write_text(html, encoding='utf-8')


def export_pdf(result: dict, path: Path, cover: dict):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak
    heading = ParagraphStyle('RuleHeading', fontName='Helvetica-Bold', fontSize=15, leading=20, textColor=colors.HexColor('#143759'), spaceBefore=12, spaceAfter=8)
    label_style = ParagraphStyle('RuleLabel', fontName='Helvetica-Bold', fontSize=10, leading=14, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle('RuleBody', fontName='Helvetica', fontSize=9, leading=13, spaceAfter=3)
    code = ParagraphStyle('RuleEvidence', fontName='Courier', fontSize=8, leading=11, spaceAfter=2)
    story = cover_pdf_story(cover, 'LogicScan - Complete validation result')

    def add_text(value, style=code):
        for line in text(value).splitlines() or ['']:
            # Bound each flowable; very long source lines still wrap safely.
            for start in range(0, max(1, len(line)), 240):
                story.append(Paragraph(escape(line[start:start + 240]).replace(' ', '&#160;') or '&#160;', style))

    items = ordered_results(result)
    story.append(Paragraph(f'ResultView / LogicScan - {len(items)} checks', heading))
    for index, item in enumerate(items, 1):
        add_text(f'{index}. {item.get("name") or item.get("id")} | {item.get("standardId") or item.get("standardId") or item.get("id", "")} | {item.get("status", "")}', body)
    story.append(Paragraph('Run summary and flow outcomes', heading))
    add_text({key: value for key, value in result.items() if key != 'results'})
    for index, item in enumerate(items, 1):
        story.extend([PageBreak(), Paragraph(escape(f'{index}. {text(item.get("name") or item.get("id"))}'), heading)])
        add_text(f'{item.get("standardId") or item.get("standardId") or item.get("id", "")} | {item.get("status", "")}', body)
        for label, value in sections(item):
            story.append(Paragraph(label, label_style))
            add_text(value)
        story.append(Spacer(1, 8))

    def footer(canvas, doc):
        canvas.saveState(); canvas.setFont('Helvetica', 8); canvas.setFillColor(colors.HexColor('#52647b'))
        canvas.drawString(40, 22, 'uSOPp.ai / ResultView / LogicScan')
        canvas.drawRightString(A4[0] - 40, 22, f'Page {doc.page}'); canvas.restoreState()
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40, title='LogicScan complete validation result').build(story, onFirstPage=footer, onLaterPages=footer)
