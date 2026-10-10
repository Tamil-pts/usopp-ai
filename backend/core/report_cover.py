"""Cover metadata shared by human-readable engineering reports."""
from datetime import date
from html import escape
from pydantic import BaseModel, Field, field_validator


class ReportCover(BaseModel):
    projectName: str = Field(min_length=1, max_length=200)
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

    @field_validator('projectName', 'description', 'validatedBy', 'validationDetails', 'approvedBy')
    @classmethod
    def valid_text(cls, value):
        if any(ord(char) < 32 and char not in '\n\r\t' for char in value):
            raise ValueError('Report details contain unsupported control characters')
        return value


LABELS = [('projectName', 'Project name'), ('description', 'Description'),
          ('validatedBy', 'Validated by'), ('validationDetails', 'Validation details'),
          ('approvedBy', 'Approved by'), ('date', 'Date')]
COVER_CSS = '''.report-cover{padding:32px;min-height:85vh;border-top:6px solid #143759;break-after:page;page-break-after:always}.report-cover h1{font-size:30px;color:#143759}.report-cover h2{font-size:22px}.report-cover dl{margin-top:30px}.report-cover dt{font-weight:bold;color:#52647b;margin-top:20px}.report-cover dd{margin:6px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}.report-cover small{color:#52647b}@media print{.report-cover{min-height:auto;padding:12px}}'''


def cover_html(cover: dict, title: str) -> str:
    rows = ''.join(f'<dt>{label}</dt><dd>{escape(str(cover.get(key) or "Not provided"))}</dd>' for key, label in LABELS)
    return f'<section class="report-cover"><h1>uSOPp.ai / ResultView</h1><h2>{escape(title)}</h2><dl>{rows}</dl><p><small>Cover details are supplied by the engineer. Approval is not inferred from validation results.</small></p></section>'


def cover_pdf_story(cover: dict, title: str):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer, PageBreak
    heading = ParagraphStyle('CoverHeading', fontName='Helvetica-Bold', fontSize=23, leading=29, textColor=colors.HexColor('#143759'), spaceAfter=14)
    label_style = ParagraphStyle('CoverLabel', fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.HexColor('#52647b'), spaceBefore=10, spaceAfter=3)
    value_style = ParagraphStyle('CoverValue', fontName='Helvetica', fontSize=11, leading=16, spaceAfter=5)
    story = [Paragraph('uSOPp.ai / ResultView', heading), Paragraph(escape(title), heading), Spacer(1, 12)]
    # Separate paragraphs allow long engineer descriptions to flow over pages.
    for key, label in LABELS:
        story.append(Paragraph(label, label_style))
        value = str(cover.get(key) or 'Not provided')
        for line in value.splitlines() or ['']:
            story.append(Paragraph(escape(line) or '&#160;', value_style))
    story.extend([Spacer(1, 12), Paragraph('Cover details are supplied by the engineer. Approval is not inferred from validation results.', label_style), PageBreak()])
    return story
