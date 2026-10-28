"""Competency Hub PDF and Excel exports from the same approved-profile calculations."""
from collections import defaultdict
from datetime import datetime
from html import escape
from io import BytesIO
import math
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from . import service,store,insights

TYPES={'individual':'Individual Performance & Capability Report','matrix':'Competency Matrix Report',
       'development':'Development Progress Report','team':'Team Capability Report','gaps':'Department Skill Gap Report'}


def data(user,kind,subject,period_id='',department_id='',team_id='',role_id='',employee_id=None,project_id='',work_based=False):
    from . import outcomes
    profiles_service=outcomes if work_based else service
    if kind not in TYPES:raise HTTPException(400,'Choose a Competency Hub report type.')
    if kind in {'team','gaps'}:
        store.initialize()
        with store.hub.db() as db:store.manager(db,user)
        profiles=profiles_service.team(user,period_id,department_id,team_id,role_id,employee_id,project_id)['people']
    else:profiles=[outcomes.profile(user,subject,period_id,project_id) if work_based else service.profile(user,subject,period_id)]
    selected=insights.layout(user)
    for p in profiles:
        p['work_activity']=insights.work_activity(user,p['person']['id'])
        p['insight_values']=insights.values(p)
    return {'title':('SAMPLE PREVIEW - ' if any(p.get('sample_preview') for p in profiles) else '')+TYPES[kind],'kind':kind,'profiles':profiles,'insight_layout':selected,'work_based':work_based,
            'generated_at':datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(),
            'scope':'Project/task outcomes and workflow feedback. No separate assessment is required.' if work_based else 'Authorized employees and approved assessment revisions only. Development goals retain their recorded status.'}


def excel(value):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill
    book=Workbook();summary=book.active;summary.title='Summary'
    summary.append([value['title']]);summary.append(['Generated at',value['generated_at']]);summary.append(['Scope',value['scope']])
    summary.append(['Employee','Period','Role model','Performance Index','Competency Index','Competencies assessed','Development progress','Reviewer','Reviewed at','Revision','Department','Professional role','Teams','Reviewer designation'])
    matrix=book.create_sheet('Competency matrix');matrix.append(['Employee','Period','Competency','Category','Current level','Required level','Gap','Weight','Criteria','Notes','Work references'])
    performance=book.create_sheet('Performance');performance.append(['Employee','Period','KPI / KRA','Value','Weight','Not applicable','Criteria','Notes','Calculation','Work references'])
    development=book.create_sheet('Development');development.append(['Employee','Goal','Competency ID','Target level','Due','Status','Project ID','Task ID'])
    methodology=book.create_sheet('Methodology');methodology.append(['Employee','Period','Role model','Performance method','Competency method','Missing data','Reviewer comment'])
    insight_sheet=book.create_sheet('Insights');insight_sheet.append(['Employee','Section','Insight','Measurement','Recorded value','Unit','Personal note','Basis'])
    if value.get('work_based'):
        work_sheet=book.create_sheet('Project and task outcomes');work_sheet.append(['Employee','Project ID','Work item','Completed','Planned date','Quality accepted','Correction cycles'])
        feedback_sheet=book.create_sheet('Workflow feedback');feedback_sheet.append(['Employee','Work item','Reviewer','Recorded at','Field','Answer'])
    for profile in value['profiles']:
        who=profile['person']['username'];period=(profile['period'] or {}).get('name','Not configured');review=profile['review'] or {}
        team=profile['team_details']
        summary.append([who,period,profile['model'].get('name','Not configured'),profile['performance_index'],profile['competency_index'],profile['competencies_assessed'],profile['development_progress'],review.get('reviewer_name'),review.get('at'),profile['approved_revision'],team['department'],team['professional_role'],', '.join(team['teams']),review.get('reviewer_designation')])
        for row in profile['competencies']:
            matrix.append([who,period,row['name'],row['category'],row['current'],row['required'],row['gap'],row['weight'],row['criteria'],row['note'],'; '.join(r['kind']+': '+r['id'] for r in row['references'])])
        for row in profile['performance']:performance.append([who,period,row['name'],row['value'],row['weight'],row['not_applicable'],row['criteria'],row['note'],profile['methodology']['performance'],'; '.join(r['kind']+': '+r['id'] for r in row['references'])])
        for row in profile['development']:development.append([who,row['title'],row['competency_id'],row['target_level'],row['due_date'],row['status'],row['project_id'],row['task_id']])
        if value.get('work_based'):
            for row in profile['work_records']:work_sheet.append([who,row['project_id'],row['title'],row['completed_at'],row['due'],row['accepted'],row['correction_cycles']])
            for row in profile['work_feedback']:
                for key,answer in row['answers'].items():feedback_sheet.append([who,row['title'],row.get('reviewer_name',row['reviewer_id']),row['at'],key,answer])
        methodology.append([who,period,profile['model'].get('name','Not configured'),profile['methodology']['performance'],profile['methodology']['competency'],profile['methodology']['missing'],review.get('comment','')])
        for w in value.get('insight_layout',{}).get('widgets',[]):
            if w['enabled']:
                metric=insights.METRICS[w['metric']];recorded=profile.get('insight_values',{}).get(w['metric'])
                insight_sheet.append([who,w['view'],w['title'],metric[0],recorded if recorded is not None else ('Waiting for completed work' if value.get('work_based') else 'Not Assessed'),metric[2],w['note'],metric[1]])
    for sheet in book:
        header=4 if sheet.title=='Summary' else 1
        sheet.freeze_panes='A'+str(header+1);sheet.auto_filter.ref=f'A{header}:{sheet.cell(sheet.max_row,sheet.max_column).coordinate}'
        for cell in sheet[header]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='143B49')
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width=min(65,max(16,max(len(str(c.value or '')) for c in column)+2))
        for row in sheet:
            for cell in row:
                if isinstance(cell.value,str) and cell.value.startswith(('=','+','-','@')):cell.value="'"+cell.value
    output=BytesIO();book.save(output);return output.getvalue()


def _chart(profile):
    from reportlab.graphics.shapes import Drawing,Rect,Line,String,Polygon
    from reportlab.lib import colors
    drawing=Drawing(500,175);rows=[r for r in profile['competencies'] if r['current'] is not None][:6]
    if not rows:
        drawing.add(String(10,120,'Waiting for completed work' if profile.get('work_based') else 'Not Assessed - no approved competency levels',fontSize=10));return drawing
    # Native vector chart: current/required levels; no invented zero scores.
    drawing.add(String(10,160,'Current and required proficiency (1-5)',fontSize=10))
    for i,row in enumerate(rows):
        y=135-i*20;drawing.add(String(10,y,row['name'][:28],fontSize=8))
        drawing.add(Rect(165,y-2,row['required']*35,7,fillColor=colors.HexColor('#d9e6ed'),strokeColor=None))
        drawing.add(Rect(165,y-2,row['current']*35,4,fillColor=colors.HexColor('#14987d'),strokeColor=None))
        drawing.add(String(350,y,f"{row['current']} / {row['required']}",fontSize=8))
    return drawing


def _trend(profile):
    from reportlab.graphics.shapes import Drawing,Line,String,Circle
    from reportlab.lib import colors
    points=[r for r in profile['history'] if r['competency_index'] is not None][-12:]
    drawing=Drawing(500,115);drawing.add(String(10,101,'Work outcome trend' if profile.get('work_based') else 'Approved competency development trend',fontSize=10))
    if not points:drawing.add(String(10,65,'Insufficient Data',fontSize=9));return drawing
    drawing.add(Line(25,20,460,20,strokeColor=colors.lightgrey));last=None
    for i,point in enumerate(points):
        x=25+i*425/max(1,len(points)-1);y=20+point['competency_index']*.65
        if last:drawing.add(Line(*last,x,y,strokeColor=colors.HexColor('#14987d')))
        drawing.add(Circle(x,y,2,fillColor=colors.HexColor('#14987d')))
        drawing.add(String(x-8,7,point['at'][:10],fontSize=6));last=(x,y)
    return drawing


def pdf(value):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    styles=getSampleStyleSheet();output=BytesIO();document=SimpleDocTemplate(output,pagesize=A4,rightMargin=35,leftMargin=35,topMargin=35,bottomMargin=35)
    def paragraph(text,style='BodyText'):return Paragraph(escape(str(text)),styles[style])
    story=[paragraph('uSOPp.ai / WorkHub / Competency Hub','Title'),paragraph(value['title'],'Heading1'),paragraph('Generated: '+value['generated_at']),paragraph(value['scope']),Spacer(1,15)]
    if not value['profiles']:story.append(paragraph('No authorized employees match these filters.'))
    for i,profile in enumerate(value['profiles']):
        if i:story.append(PageBreak())
        period=profile['period'] or {};review=profile['review'] or {}
        story += [paragraph(profile['person']['username'],'Heading1'),paragraph('Period: '+period.get('name','Not configured')+' / '+period.get('start','')+' to '+period.get('end','')),
                  paragraph('Role model: '+profile['model'].get('name','Not configured')),
                  paragraph('Department: '+profile['team_details']['department']+' / Role: '+profile['team_details']['professional_role']),
                  paragraph('Performance Index: '+(str(profile['performance_index']) if profile['performance_index'] is not None else profile['performance_status'])),
                  paragraph('Competency Index: '+(str(profile['competency_index']) if profile['competency_index'] is not None else profile['competency_status'])),Spacer(1,10)]
        if value['kind']!='development':
            story.extend([_chart(profile),_trend(profile)])
            rows=[[paragraph(x) for x in ('Competency','Current','Required','Gap')]]
            for r in profile['competencies']:rows.append([paragraph(r['name']),paragraph(r['current'] if r['current'] is not None else ('Waiting for completed work' if value.get('work_based') else 'Not Assessed')),paragraph(r['required']),paragraph(r['gap'] if r['gap'] is not None else '-')])
            table=Table(rows,colWidths=[260,70,70,60],repeatRows=1);table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f2f5')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.lightgrey),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.append(table)
        if value['kind'] in {'individual','team'}:
            story.append(paragraph('Performance KPIs and KRAs','Heading2'))
            for row in profile['performance']:
                label='Not applicable' if row['not_applicable'] else str(row['value']) if row['value'] is not None else ('Waiting for completed work' if value.get('work_based') else 'Not Assessed')
                story.extend([paragraph(row['name']+' / '+label+' / Weight '+str(row['weight']),'Heading3'),paragraph(row['criteria']),paragraph(row['note'])])
                for source in row['references']:story.append(paragraph('Work reference: '+source['kind']+' / '+source['title']+' / '+source['id']))
        if value['kind'] in {'development','individual'}:
            story.append(paragraph('Development goals','Heading2'))
            for goal in profile['development']:story.append(paragraph(goal['title']+' / '+goal['status']+' / Due '+(goal['due_date'] or 'Not scheduled')))
            if not profile['development']:story.append(paragraph('No development goals recorded.'))
        story += [Spacer(1,12),paragraph('Calculation and review','Heading2'),paragraph('Performance: '+profile['methodology']['performance']),paragraph('Competency: '+profile['methodology']['competency']),paragraph(profile['methodology']['missing']),paragraph('Reviewer: '+review.get('reviewer_name','Not reviewed')+' / '+review.get('reviewer_designation','')+' / '+review.get('at','')),paragraph('Reviewer comments: '+review.get('comment','Not reviewed'))]
        for row in profile['competencies']:
            story += [paragraph(row['name']+' - criteria','Heading3'),paragraph(row['criteria']),paragraph('Weight: '+str(row['weight']))]
            if row['note']:story.append(paragraph(row['note']))
            for source in row['references']:story.append(paragraph('Work reference: '+source['kind']+' / '+source['title']+' / '+source['id']))
        story.append(paragraph('Customized insights','Heading2'))
        if value.get('work_based'):
            story.append(paragraph('Workflow feedback and contributions','Heading2'))
            for feedback in profile['work_feedback']:
                story.append(paragraph(feedback['title']+' / '+feedback.get('reviewer_name',str(feedback['reviewer_id']))+' / '+feedback['at'],'Heading3'))
                for key,answer in feedback['answers'].items():story.append(paragraph(key.replace('_',' ')+': '+str(answer).replace('_',' ')))
        for w in value.get('insight_layout',{}).get('widgets',[]):
            if w['enabled']:
                recorded=profile.get('insight_values',{}).get(w['metric']);metric=insights.METRICS[w['metric']]
                story.extend([paragraph(w['title']+': '+(('Waiting for completed work' if value.get('work_based') else 'Not Assessed') if recorded is None else str(recorded)+' '+metric[2]),'Heading3'),paragraph(metric[1])])
                if w['note']:story.append(paragraph('Personal note: '+w['note']))
    document.build(story);return output.getvalue()
