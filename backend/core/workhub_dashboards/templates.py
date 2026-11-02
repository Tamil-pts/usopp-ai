"""Editable starter designs; values always come from authorized live records."""
from . import schema

KEY='engineering-overview'
NAME='Engineering project overview'
DESCRIPTION='Project delivery, reviewed work, scheduled tasks, validation activity and current documents. Every widget is editable.'
OVERVIEW_KEY='workhub-overview'
OVERVIEW_NAME='WorkHub overview'


def configuration():
    def widget(key,kind,title,source,dimensions=None,metric='id',aggregation='count',filters=None,columns=None,appearance=None):
        return {'id':key,'type':kind,'title':title,'columns':columns or [],
            'query':{'source':source,'dimensions':dimensions or [],'metrics':[{'field':metric,'aggregation':aggregation}],
                'filters':filters or [],'sort':'dimension','limit':100},
            'appearance':{'colors':['#16a394','#164c63','#5271d3','#c89536','#ae6a91'],'legend':True,'axes':True,**(appearance or {})}}
    dim=lambda field,grain='value':{'field':field,'grain':grain}
    eq=lambda field,value:{'field':field,'op':'eq','value':value}
    widgets=[
        widget('active_projects','kpi','Active projects','projects',filters=[{'field':'status','op':'ne','value':'released'}]),
        widget('completed_tasks','kpi','Completed development tasks','tasks',filters=[eq('completed',1),eq('phase','development')]),
        widget('pending_reviews','kpi','Pending workflow reviews','approvals',filters=[eq('status','pending')]),
        widget('reviewed_work','kpi','Reviewed contributions','contributions'),
        widget('project_progress','bar','Project completion','projects',[dim('title')],metric='progress',aggregation='avg',appearance={'horizontal':True,'format':'percent','legend':False}),
        widget('delivery_stages','donut','Projects by delivery stage','projects',[dim('status')]),
        widget('scheduled_work','gantt','Project work schedule','tasks',columns=['title','project','engineer','start','end','progress']),
        widget('pending_work','table','Work needing attention','tasks',filters=[{'field':'status','op':'in','value':['quality','release_approval','ready_release','blocked']}],columns=['title','project','engineer','status','end']),
        widget('validation_activity','heatmap','Validation activity · run counts','validation',[dim('date','day'),dim('tool')],appearance={'legend':False,'x_label':'Recorded date','y_label':'Engineering tool'}),
        widget('project_documents','documents','Project documents & approved deliveries','documents',columns=['title','project','kind','engineer','date'])]
    desktop=[(0,0,3,3),(3,0,3,3),(6,0,3,3),(9,0,3,3),(0,3,8,7),(8,3,4,7),(0,10,12,7),(0,17,6,7),(6,17,6,7),(0,24,12,5)]
    tablet=[(0,0,4,3),(4,0,4,3),(0,3,4,3),(4,3,4,3),(0,6,8,7),(0,13,8,6),(0,19,8,7),(0,26,8,7),(0,33,8,7),(0,40,8,5)]
    mobile=[];y=0
    for w in widgets:
        h=3 if w['type']=='kpi' else 7 if w['type'] in {'bar','gantt','table','heatmap'} else 6
        mobile.append((0,y,4,h));y+=h
    layouts={bp:[dict(i=w['id'],x=x,y=y,w=width,h=height) for w,(x,y,width,height) in zip(widgets,positions)] for bp,positions in [('desktop',desktop),('tablet',tablet),('mobile',mobile)]}
    return schema.dashboard({'name':NAME,'widgets':widgets,'layouts':layouts,'appearance':{'theme':'inherit','background':'plain','density':'comfortable','accent':'#16a394'}})


def overview_configuration():
    entries=[
        ('work','workhub_shortcut','My work','Your current responsibilities','blue'),
        ('projects','workhub_shortcut','Projects','Open the project portfolio','green'),
        ('approvals','workhub_shortcut','Approvals','Documents, workflow and time','amber'),
        ('team','workhub_shortcut','Team Management','Plan resources and availability','purple'),
        ('actions','workhub_list','My next actions','','blue'),
        ('milestones','workhub_list','Milestones & due dates','','amber'),
        ('recent','workhub_list','Recently updated projects','','green'),
        ('links','workhub_list','Team & documents','','purple')]
    widgets=[{'id':'overview_'+key,'type':kind,'title':title,
        'overview':{'content':key,'caption':caption,'tone':tone,'limit':4}} for key,kind,title,caption,tone in entries]
    layouts={}
    for bp,cols in schema.COLS.items():
        positions=[];y=0
        for i,w in enumerate(widgets):
            shortcut=i<4
            if bp=='desktop':x=(i%4)*3 if shortcut else (i%2)*6;top=0 if shortcut else 4+((i-4)//2)*8;width=3 if shortcut else 6;height=4 if shortcut else 8
            elif bp=='tablet':x=(i%2)*4 if shortcut else 0;top=(i//2)*3 if shortcut else 6+(i-4)*8;width=4 if shortcut else 8;height=3 if shortcut else 8
            else:x=0;top=y;width=cols;height=3 if shortcut else 8;y+=height
            positions.append(dict(i=w['id'],x=x,y=top,w=width,h=height))
        layouts[bp]=positions
    return schema.dashboard({'name':OVERVIEW_NAME,'widgets':widgets,'layouts':layouts,
        'appearance':{'theme':'inherit','background':'plain','density':'comfortable','accent':'#119773'}})


def catalog():
    return {'items':[
        {'id':OVERVIEW_KEY,'name':OVERVIEW_NAME,'description':'Your live WorkHub shortcuts and lists. Resize, rearrange or add any widget.','version':1,'configuration':overview_configuration()},
        {'id':KEY,'name':NAME,'description':DESCRIPTION,'version':1,'configuration':configuration()}]}
