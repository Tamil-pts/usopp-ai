"""Front-page rendering shared by the existing drawing export formats."""
from io import BytesIO
from html import escape

FIELDS=[('File name','fileName'),('Review version','reviewVersion'),('Review date','reviewDate'),('Reviewed by','reviewedBy'),
        ('Review sign-off','reviewSignature'),('Assigned to','assignedTo'),('Description','description'),
        ('Approved by','approvedBy'),('Approval date','approvalDate'),('Approval details','approvalDetails')]

def pdf(cover):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepInFrame
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    styles=getSampleStyleSheet();stream=BytesIO();rows=[]
    for label,key in FIELDS:
        rows.append([Paragraph(escape(label),styles['Heading5']),Paragraph(escape(cover.get(key) or '—').replace('\n','<br/>'),styles['BodyText'])])
    table=Table(rows,colWidths=[130,365]);table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#eaf3f8')),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#c9d8e5')),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story=[Paragraph('uSOPp.ai / e-design',styles['Heading2']),Paragraph('Drawing review',styles['Title']),Spacer(1,20),KeepInFrame(495,610,[table],mode='shrink')]
    SimpleDocTemplate(stream,title='Drawing review front page',leftMargin=50,rightMargin=50,topMargin=45,bottomMargin=45).build(story)
    stream.seek(0);return stream

def html(cover):
    return '<section class="review-cover" style="break-after:page;max-width:1000px;margin:0 auto 40px"><h2>uSOPp.ai / e-design</h2><h1>Drawing review</h1><table style="border-collapse:collapse;width:100%">'+''.join('<tr><th style="text-align:left;vertical-align:top;padding:12px;border:1px solid #ccd8e4;background:#eaf3f8">'+escape(label)+'</th><td style="padding:12px;border:1px solid #ccd8e4;white-space:pre-wrap;overflow-wrap:anywhere">'+escape(cover.get(key) or '—')+'</td></tr>' for label,key in FIELDS)+'</table></section>'

def docx(document,cover):
    document.add_heading('uSOPp.ai / e-design',1);document.add_heading('Drawing review',0)
    table=document.add_table(rows=0,cols=2);table.style='Table Grid'
    for label,key in FIELDS:
        cells=table.add_row().cells;cells[0].text=label;cells[1].text=cover.get(key) or '—'
    document.add_page_break()
