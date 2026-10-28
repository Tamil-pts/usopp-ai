"""A layout projects native document fields; it does not replace their identities."""
from copy import deepcopy
import hashlib,json
from . import schema

TABLES={
 'requirements':[('id','ID'),('title','Requirement'),('description','Description'),('expected_behavior','Expected behavior'),('acceptance_criteria','Acceptance criteria')],
 'cases':[('id','ID'),('requirement_ids','Requirements'),('objective','Objective'),('procedure','Procedure'),('expected_result','Expected result'),('acceptance_criteria','Acceptance criteria'),('actual_result','Recorded actual result'),('result','Recorded outcome')],
 'changes':[('id','ID'),('requirement_ids','Requirements'),('summary','Correction'),('existing_behavior','Existing behavior'),('expected_behavior','Expected behavior'),('verification','Verification')],
 'participants':[('text','Participant')],
 'discussion_summary':[('topic','Topic'),('text','Discussion'),('decision','Decision'),('responsible','Responsible person')],
 'decisions':[('text','Decision')],
 'actions':[('text','Action'),('responsible','Assigned to'),('target_date','Target date'),('status','Status')],
 'clarifications':[('question','Clarification')],
 'next_meeting_items':[('text','Follow-up item')],
 'engineering_requirements':[('text','Requirement proposal')],
 'sections':[('heading','Section'),('text','Content')],
}
TEXT={'summary','purpose','scope','acceptance_summary','na_reason','meeting_subject','meeting_date','meeting_mode','location','agenda','follow_up','project_name'}

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def b(key,typ,data,style=None):return {'id':key,'type':typ,'data':data,'style':style or {}}
def text_value(content,binding):
    if binding in TEXT:return str(content.get(binding) or '')
    if binding.startswith('section:'):
        _,key,field=binding.split(':',2)
        if field not in {'text','heading'}:schema.fail('Choose a native document section field.')
        row=next((r for i,r in enumerate(content.get('sections',[])) if str(r.get('id',i))==key),None)
        if row is None:return ''
        return str(row.get(field) or '')
    schema.fail('Choose a native document text field.')

def synchronize(content):
    """Keep native edits and page edits compatible, retaining custom blocks."""
    if not content.get('studio'):return content
    result=deepcopy(content);studio=schema.normalize(content['studio']);groups={}
    for b in studio['blocks']:
        if b['type']=='native_text':groups.setdefault(b['data']['binding'],[]).append(b)
    removed=set()
    for binding,blocks in groups.items():
        current=text_value(result,binding);projected=''.join(schema.plain(b['data']['runs']) for b in blocks)
        if projected!=current:
            # Another compatible editor updated the native field. Keep its full
            # content and leave custom inserted elements in their saved order.
            blocks[0]['data']['runs']=[{'text':current}]
            removed.update(b['id'] for b in blocks[1:])
        for b in blocks:b['data']['source_hash']=digest(current)
    studio['blocks']=[b for b in studio['blocks'] if b['id'] not in removed]
    result['studio']=studio
    return result

def seed(content,kind):
    result={'schema':1,'page':deepcopy(schema.PAGE),'header':{'variants':{'default':{'items':[
      {'id':'company-logo','type':'logo','source':'company','x':0,'y':0,'width':12,'height':11},
      {'id':'company-name','type':'field','field':'company','x':15,'y':1,'width':58,'height':5,'font_size':10,'bold':True},
      {'id':'document-number','type':'field','field':'document_number','x':72,'y':1,'width':28,'height':5,'align':'right','font_size':8},
      {'id':'header-label','type':'text','text':'Controlled document','x':15,'y':6,'width':58,'height':4,'font_size':8},
    ]}}},'footer':{'variants':{'default':{'items':[
      {'id':'footer-id','type':'field','field':'document_number','x':0,'y':2,'width':55,'height':5,'font_size':8},
      {'id':'footer-rev','type':'field','field':'revision','x':55,'y':2,'width':15,'height':5,'font_size':8},
      {'id':'footer-page','type':'text','text':'Page {page} of {pages}','x':72,'y':2,'width':28,'height':5,'font_size':8,'align':'right'},
    ]}}},'blocks':[b('document-title','field',{'field':'document_title'},{'font_size':19,'bold':True,'color':'#235789','space_after':6}),b('project-title','field',{'field':'project_name'},{'font_size':14,'space_after':8}),b('document-metadata','metadata',{})]}
    def heading(key,title):result['blocks'].append(b('heading-'+key,'heading',{'runs':[{'text':title}],'level':2},{'font_size':13,'bold':True,'color':'#235789','space_before':5}))
    def text(key,title):
        heading(key.replace(':','-'),title)
        result['blocks'].append(b('native-'+key.replace(':','-'),'native_text',{'binding':key,'runs':[{'text':text_value(content,key)}],'source_hash':digest(text_value(content,key))}))
    def table(key,title):heading(key,title);result['blocks'].append(b('native-'+key,'native_table',{'binding':key},{'font_size':9}))
    if kind=='mom':
        for key,title in [('meeting_subject','Meeting title'),('meeting_date','Meeting date'),('meeting_mode','Meeting mode'),('location','Location / platform'),('agenda','Meeting agenda')]:text(key,title)
        for key,title in [('participants','Participants'),('discussion_summary','Discussion and decisions'),('decisions','Decisions'),('actions','Action items'),('clarifications','Open clarifications')]:table(key,title)
        text('follow_up','Follow-up plan')
    else:
        for key in ('summary','purpose','scope'):
            if content.get(key) or key=='purpose' and kind=='frd':text(key,key.title())
        if kind=='frd':table('requirements','Functional requirements')
        if kind=='corrections':table('changes','Correction notes')
        if kind in {'test','fat'}:table('cases','Validation test cases' if kind=='test' else 'Factory acceptance tests')
        if content.get('flowchart') or kind=='flowchart':heading('flowchart','Functional flowchart');result['blocks'].append(b('native-flowchart','native_flowchart',{}))
        for i,section in enumerate(content.get('sections',[])):text('section:'+str(section.get('id',i))+':text',section.get('heading') or 'Section')
    heading('approval','Review and approval');result['blocks'].append(b('recorded-approval','approval',{'label':'Recorded document approval','runs':[]}))
    return schema.normalize(result)

def layout(content,kind):return synchronize(content)['studio'] if content.get('studio') else seed(content,kind)

def native_table(content,binding):
    columns=TABLES[binding];rows=[]
    for i,raw in enumerate(content.get(binding,[])):
        row={'text':raw} if isinstance(raw,str) else raw
        cells=[]
        for field,label in columns:
            value=(row.get('execution') or {}).get('actual','Not recorded') if field=='actual_result' else (row.get('execution') or {}).get('outcome','Not tested') if field=='result' else row.get(field)
            if isinstance(value,list):value=', '.join(str(x) for x in value)
            cells.append('' if value is None else str(value))
        rows.append({'id':str(row.get('id',i)),'cells':cells,'execution':row.get('execution')})
    return {'columns':[{'field':key,'label':label} for key,label in columns],'rows':rows}

def materialize(content,studio,fields):
    result=deepcopy(studio)
    for b in result['blocks']:
        typ=b['type'];data=b['data']
        if typ=='native_text':b['type']='paragraph'
        elif typ=='native_table':
            table=native_table(content,data['binding']);cells=[];headers=[c['label'] for c in table['columns']]
            allrows=[headers]+[r['cells'] for r in table['rows']]
            for y,row in enumerate(allrows):
                for x,value in enumerate(row):
                    cell={'id':f'{b["id"]}-{y}-{x}','row':y,'col':x,'rowspan':1,'colspan':1,'runs':[{'text':value}],'style':schema.style({**b['style'],'bold':y==0,'background':data['header_background'] if y==0 else 'transparent'})}
                    if y:cell.update(id=table['rows'][y-1]['id']+':'+table['columns'][x]['field'],native_row=table['rows'][y-1]['id'],native_field=table['columns'][x]['field'],native_index=y-1,native_readonly=table['columns'][x]['field'] in {'id','requirement_ids','actual_result','result'})
                    cells.append(cell)
            n=len(headers);b.update(type='table',data={**data,'rows':len(allrows),'columns':n,'header_rows':1,'widths':data.get('widths') if len(data.get('widths',[]))==n else [100/n]*n,'cells':cells})
        elif typ=='native_flowchart':
            flow=content.get('flowchart') or content
            b.update(type='flowchart',data={'nodes':[{'id':n['id'],'label':n.get('data',{}).get('label',''),'kind':n.get('data',{}).get('kind','process'),'x':n.get('position',{}).get('x',0),'y':n.get('position',{}).get('y',0)} for n in flow.get('nodes',[])],'edges':flow.get('edges',[])})
        elif typ=='field':b.update(type='paragraph',data={'runs':[{'text':str(fields.get(data['field'],'Not recorded')),'field':data['field']}]})
        elif typ=='metadata':
            rows=[('Document number',fields.get('document_number','')),('Project',fields.get('project_name','')),('Project number',fields.get('project_number','')),('Customer / Client',fields.get('customer','')),('Revision',fields.get('revision','')),('Status',fields.get('status','')),('Prepared by',fields.get('prepared_by',''))]
            b.update(type='table',data={'rows':len(rows),'columns':2,'header_rows':0,'widths':[33,67],'border_color':'#e0e7ef','border_width':0.3,'header_background':'#edf3f9','highlight':False,'cells':[{'id':f'meta-{y}-{x}','row':y,'col':x,'rowspan':1,'colspan':1,'native_readonly':True,'runs':[{'text':str(value)}],'style':schema.style({'font_size':9,'bold':x==0})} for y,row in enumerate(rows) for x,value in enumerate(row)]})
        if typ=='approval':
            b['data']['recorded']=[{'label':label,'name':fields.get(key,'Pending'),'date':fields.get('approval_date','') if key=='approved_by' else ''} for label,key in [('Prepared by','prepared_by'),('Reviewed by','reviewed_by'),('Approved by','approved_by')]]
    return result
