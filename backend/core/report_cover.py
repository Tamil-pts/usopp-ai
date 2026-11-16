"""Cover metadata shared by human-readable engineering reports."""
from datetime import date
from html import escape
from pydantic import BaseModel, Field, field_validator


class ReportCover(BaseModel):
    projectName: str = Field(min_length=1, max_length=200)
    projectId: str = Field(default='', max_length=200)
    department: str = Field(default='', max_length=200)
    base: str = Field(default='', max_length=200)
    developed: str = Field(default='', max_length=200)
    objectiveScope: str = Field(default='', max_length=2000)
    reviewedBy: str = Field(default='', max_length=200)
    description: str = Field(default='', max_length=2000)
    validatedBy: str = Field(default='', max_length=200)
    validationDetails: str = Field(default='', max_length=4000)
    approvedBy: str = Field(default='', max_length=200)
    date: date

    @field_validator('projectName')
    @classmethod
    def project_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Enter a project name')
        return value.strip()

    @field_validator('projectName', 'projectId', 'department', 'base', 'developed', 'objectiveScope', 'reviewedBy', 'description', 'validatedBy', 'validationDetails', 'approvedBy')
    @classmethod
    def valid_text(cls, value):
        if any(ord(char) < 32 and char not in '\n\r\t' for char in value):
            raise ValueError('Report details contain unsupported control characters')
        return value


LABELS = [('projectName', 'Project name'), ('projectId','Project ID'), ('department','Department'),
          ('base','Base / reference'), ('developed','Developed / compare'), ('description', 'Description'),
          ('objectiveScope','Objective / scope'), ('reviewedBy','Reviewed by'),
          ('validatedBy', 'Validated by'), ('validationDetails', 'Validation details'),
          ('approvedBy', 'Approved by'), ('date', 'Date')]
COVER_CSS = '''.report-cover{padding:32px;min-height:85vh;border-top:6px solid #143759;break-after:page;page-break-after:always}.report-cover h1{font-size:30px;color:#143759}.report-cover h2{font-size:22px}.report-cover dl{margin-top:30px}.report-cover dt{font-weight:bold;color:#52647b;margin-top:20px}.report-cover dd{margin:6px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}.report-cover small{color:#52647b}@media print{.report-cover{min-height:auto;padding:12px}}'''


def cover_html(cover: dict, title: str, compact=False) -> str:
    rows = ''.join(f'<dt>{label}</dt><dd>{escape(str(cover.get(key) or "Not provided"))}</dd>' for key, label in cover_fields(cover,include_empty_core=not compact))
    return f'<section class="report-cover"><h1>uSOPp.ai / ResultView</h1><h2>{escape(title)}</h2><dl>{rows}</dl><p><small>Cover details are supplied by the engineer. Approval is not inferred from validation results.</small></p></section>'


def cover_fields(cover,include_empty_core=False):
    core={'projectName','description','validatedBy','validationDetails','approvedBy','date'}
    return [(key,label) for key,label in LABELS if str(cover.get(key) or '').strip() or include_empty_core and key in core]


def cover_pdf_story(cover: dict, title: str, compact=False):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer, PageBreak
    heading = ParagraphStyle('CoverHeading', fontName='Helvetica-Bold', fontSize=23, leading=29, textColor=colors.HexColor('#143759'), spaceAfter=14)
    label_style = ParagraphStyle('CoverLabel', fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.HexColor('#52647b'), spaceBefore=10, spaceAfter=3)
    value_style = ParagraphStyle('CoverValue', fontName='Helvetica', fontSize=11, leading=16, spaceAfter=5)
    story = [Paragraph('uSOPp.ai / ResultView', heading), Paragraph(escape(title), heading), Spacer(1, 12)]
    if compact:
        from reportlab.platypus import Table,TableStyle
        rows=[[Paragraph(label,label_style),Paragraph(escape(str(cover[key])).replace('\n','<br/>'),value_style)] for key,label in cover_fields(cover)]
        if rows:
            table=Table(rows,colWidths=[140,380],hAlign='LEFT')
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#edf3f8'))]))
            story.append(table)
        story.extend([Spacer(1,12),Paragraph('Cover details are supplied by the engineer. Approval is not inferred from validation results.',label_style),PageBreak()])
        return story
    # Separate paragraphs allow long engineer descriptions to flow over pages.
    for key, label in cover_fields(cover,include_empty_core=True):
        story.append(Paragraph(label, label_style))
        value = str(cover.get(key) or 'Not provided')
        for line in value.splitlines() or ['']:
            story.append(Paragraph(escape(line) or '&#160;', value_style))
    story.extend([Spacer(1, 12), Paragraph('Cover details are supplied by the engineer. Approval is not inferred from validation results.', label_style), PageBreak()])
    return story
