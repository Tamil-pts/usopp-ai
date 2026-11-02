"""Scoped project-management exports; engineering reports have their own register."""
import csv
import hashlib
import io
import json
from fastapi import HTTPException
from fastapi.responses import Response
from .workhub import store as hub,identity,timestamp,text,encode,day
from . import workhub_portfolio as portfolio
from .workhub_quality import store as quality
from .workhub_custom_fields import read as fields

COLUMNS={'title':'Project Name','number':'Project Number','customer':'Customer','reference':'Customer Reference','team':'Team','owner':'Owner','status':'Status','stage':'Workflow Stage','progress':'Completion %','tasks':'Tasks','phases':'Phases','issues':'Open Issues','start':'Start Date','due':'End Date','billing':'Billing Hours (Approved Time)','type':'Project Type','updated':'Last Updated'}
DEFAULT=['title','number','owner','status','progress','start','due','billing']


def initialize():
    quality.initialize()
    from .workhub_organization import initialize as org_init
    org_init()
    with hub.db(True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS wh_project_export_views(id TEXT PRIMARY KEY,owner_id INTEGER NOT NULL,name TEXT NOT NULL,config TEXT NOT NULL,created_at TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS wh_project_export_history(id TEXT PRIMARY KEY,owner_id INTEGER NOT NULL,config TEXT NOT NULL,row_count INTEGER NOT NULL,sha256 TEXT NOT NULL,created_at TEXT NOT NULL)')


def source(user,role=''):
    initialize();hub.actor(user)
    return portfolio.snapshot(user,role=role)


def catalog(user,role=''):
    value=source(user,role);columns=dict(COLUMNS)
    with hub.db() as db:
        for p in value['projects']:
            for f in fields(db,p['id']):columns[f['id']]=f['label']
        teams=[dict(r) for r in db.execute("SELECT id,name FROM wh_org_units WHERE kind='team' AND active=1 ORDER BY name")]
        views=[{**dict(r),'config':json.loads(r['config'])} for r in db.execute('SELECT * FROM wh_project_export_views WHERE owner_id=? ORDER BY created_at DESC',(user['id'],))]
        history=[{**dict(r),'config':json.loads(r['config'])} for r in db.execute('SELECT * FROM wh_project_export_history WHERE owner_id=? ORDER BY created_at DESC LIMIT 50',(user['id'],))]
    people={m['id']:m['name'] for p in value['projects'] for m in p['assigned_team']}
    return {'columns':[{'id':k,'label':v} for k,v in columns.items()],'defaults':DEFAULT,'people':[{'id':k,'name':v} for k,v in sorted(people.items())],'teams':teams,'projects':value['options']['projects'],'views':views,'history':history,'role':value['role'],'roles':value['roles']}


def config(user,payload):
    if not isinstance(payload,dict):raise HTTPException(400,'Provide export settings.')
    cat=catalog(user,payload.get('role',''));allowed={c['id'] for c in cat['columns']}
    columns=payload.get('columns',DEFAULT)
    if not isinstance(columns,list) or not columns or len(columns)>60 or any(not isinstance(c,str) or c not in allowed for c in columns) or len(set(columns))!=len(columns):raise HTTPException(400,'Choose unique available export columns.')
    if 'title' not in columns:raise HTTPException(400,'Keep the Project Name column in the export.')
    fmt=payload.get('format','xlsx')
    if fmt not in {'xlsx','csv','pdf','json'}:raise HTTPException(400,'Choose XLSX, CSV, PDF or JSON.')
    status=payload.get('status','')
    if not isinstance(status,str) or status not in {'','ongoing','completed','on_hold','cancelled'}:raise HTTPException(400,'Choose a supported project status.')
    member=payload.get('member','');team=payload.get('team','');pid=payload.get('project','')
    if not isinstance(team,str) or not isinstance(pid,str):raise HTTPException(400,'Choose a team and project from the available options.')
    if member and (type(member) is not int or member not in {m['id'] for m in cat['people']}):raise HTTPException(400,'Choose an available team member.')
    if team and team not in {t['id'] for t in cat['teams']}:raise HTTPException(400,'Choose an available team.')
    if pid and pid not in {p['id'] for p in cat['projects']}:raise HTTPException(403,'This project is outside your selected reporting scope.')
    start=day(payload.get('from_date',''));end=day(payload.get('to_date',''))
    if start and end and start>end:raise HTTPException(400,'The delivery date range is reversed.')
    files=payload.get('files',False)
    if type(files) is not bool:raise HTTPException(400,'Choose whether to include file information.')
    return {'columns':columns,'format':fmt,'role':cat['role'],'status':status,'member':member,'team':team,'project':pid,'from_date':start,'to_date':end,'files':files,'search':text(payload.get('search',''),180)}


def save_view(user,payload):
    name=text(payload.get('name',''),120,True);settings=config(user,payload.get('config'))
    with hub.db(True) as db:
        if db.execute('SELECT count(*) FROM wh_project_export_views WHERE owner_id=?',(user['id'],)).fetchone()[0]>=50:raise HTTPException(400,'Use up to 50 saved export views.')
        key=identity();db.execute('INSERT INTO wh_project_export_views VALUES(?,?,?,?,?)',(key,user['id'],name,encode(settings),timestamp()))
    return {'id':key,'name':name}


def delete_view(user,key):
    initialize()
    with hub.db(True) as db:
        if not db.execute('DELETE FROM wh_project_export_views WHERE id=? AND owner_id=?',(key,user['id'])).rowcount:raise HTTPException(404,'Saved view not found.')
    return {'deleted':True}


def dataset(user,settings):
    snap=source(user,settings['role']);columns=dict(COLUMNS);rows=[]
    from .workhub_billing import approved_hours
    with hub.db() as db:
        billing=approved_hours(db);people={u['id']:u['username'] for u in hub.users()}
        team_members={r[0] for r in db.execute('SELECT user_id FROM wh_org_members WHERE team_id=?',(settings['team'],))} if settings['team'] else set()
        for p in snap['projects']:
            for f in fields(db,p['id']):columns[f['id']]=f['label']
            raw=hub.item(db,p['id']);members={m['id'] for m in p['assigned_team']};status='completed' if p['stage']=='released' else raw.get('exception_status') or 'ongoing'
            if settings['project'] and p['id']!=settings['project'] or settings['status'] and status!=settings['status'] or settings['member'] and settings['member'] not in members or settings['team'] and not members.intersection(team_members):continue
            if settings['from_date'] and (not raw['due_date'] or raw['due_date']<settings['from_date']) or settings['to_date'] and (not raw['due_date'] or raw['due_date']>settings['to_date']):continue
            ctx=db.execute('SELECT context FROM qc_projects WHERE project_id=?',(p['id'],)).fetchone();ctx=json.loads(ctx[0]) if ctx else {}
            if settings['search'].casefold() not in ' '.join(str(v or '') for v in [p['title'],raw.get('project_number'),ctx.get('customer')]).casefold():continue
            row={'title':p['title'],'number':raw.get('project_number',''),'customer':ctx.get('customer',''),'reference':ctx.get('customer_project_reference',''),'team':', '.join(m['name'] for m in p['assigned_team']),'owner':people.get(raw['owner_id'],'Account unavailable'),'status':status.replace('_',' ').title(),'stage':raw['stage'].replace('_',' ').title(),'progress':p.get('progress'),'tasks':db.execute("SELECT count(*) FROM items WHERE project_id=? AND type='task'",(p['id'],)).fetchone()[0],'phases':db.execute('SELECT count(*) FROM project_phases WHERE project_id=?',(p['id'],)).fetchone()[0],'issues':p['open_issues'],'start':raw['start_date'],'due':raw['due_date'],'billing':round(billing.get(p['id'],0),2),'type':raw['kind'],'updated':raw['updated_at']}
            for f in fields(db,p['id']):columns[f['id']]=f['label'];row[f['id']]=f['value']
            if settings['files']:row['files']='; '.join(r[0] for r in db.execute('SELECT name FROM files WHERE project_id=? ORDER BY created_at',(p['id'],)))
            rows.append(row)
    selected=settings['columns']+(['files'] if settings['files'] else []);columns['files']='File Information'
    if any(k not in columns for k in selected):raise HTTPException(409,'Custom columns changed. Reload export options.')
    return [columns[k] for k in selected],[[r.get(k,'') for k in selected] for r in rows]


def safe(value):
    return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value


def export(user,payload):
    settings=config(user,payload);headers,rows=dataset(user,settings);fmt=settings['format']
    if fmt=='csv':
        out=io.StringIO();writer=csv.writer(out);writer.writerow(headers);writer.writerows([[safe(v) for v in row] for row in rows]);body=('\ufeff'+out.getvalue()).encode('utf-8');mime='text/csv'
    elif fmt=='xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font,PatternFill
        wb=Workbook();ws=wb.active;ws.title='Projects';ws.append(headers)
        for row in rows:ws.append([safe(v) for v in row])
        for c in ws[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='0B6B67')
        for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=min(65,max(18,max(len(str(c.value or '')) for c in col)+2))
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions;out=io.BytesIO();wb.save(out);body=out.getvalue();mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt=='json':body=json.dumps({'generated_at':timestamp(),'columns':headers,'rows':rows,'filters':settings},ensure_ascii=False,allow_nan=False).encode();mime='application/json'
    else:
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,TableStyle,PageBreak
        from reportlab.lib.pagesizes import A4,landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        from xml.sax.saxutils import escape
        out=io.BytesIO();styles=getSampleStyleSheet();story=[]
        # Split wide custom views into readable column groups, repeating project name.
        title_index=settings['columns'].index('title');others=[i for i in range(len(headers)) if i!=title_index]
        for offset in range(0,max(1,len(others)),6):
            idx=[title_index,*others[offset:offset+6]]
            if offset:story.append(PageBreak())
            story.extend([Paragraph('uSOPp.ai | Project Portfolio Report',styles['Heading1']),Paragraph(escape(timestamp()+' | '+str(len(rows))+' projects'),styles['Normal']),Spacer(1,12)])
            table=LongTable([[Paragraph(escape(str(row[i] if row[i] is not None else '')),styles['BodyText']) for i in idx] for row in [headers,*rows]],repeatRows=1,colWidths=[(landscape(A4)[0]-56)/len(idx)]*len(idx))
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DDF3ED')),('GRID',(0,0),(-1,-1),.3,colors.lightgrey),('VALIGN',(0,0),(-1,-1),'TOP')]))
            story.append(table)
        SimpleDocTemplate(out,pagesize=landscape(A4),leftMargin=28,rightMargin=28,topMargin=28,bottomMargin=28).build(story);body=out.getvalue();mime='application/pdf'
    with hub.db(True) as db:db.execute('INSERT INTO wh_project_export_history VALUES(?,?,?,?,?,?)',(identity(),user['id'],encode(settings),len(rows),hashlib.sha256(body).hexdigest(),timestamp()))
    return Response(body,media_type=mime,headers={'Content-Disposition':'attachment; filename="uSOPp_Project_Report.'+fmt+'"'})
