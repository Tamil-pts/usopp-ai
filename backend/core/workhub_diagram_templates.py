"""Editable starter diagrams. Examples carry no project facts or approval."""
from copy import deepcopy
from fastapi import HTTPException


def graph(kind,steps,connections):
    nodes=[{'id':key,'type':'engineering','width':240,'height':120 if shape=='decision' else 90,
            'position':{'x':x,'y':y},'data':{'kind':shape,'label':label,'source_ids':[],'requirement_ids':[]}}
           for key,shape,label,x,y in steps]
    edges=[{'id':'edge-'+str(i+1),'source':a,'target':b,'label':label,'type':'smoothstep',
            'sourceHandle':'bottom' if a!=b and next(n for n in nodes if n['id']==a)['position']['y']<next(n for n in nodes if n['id']==b)['position']['y'] else 'out',
            'targetHandle':'top','markerEnd':{'type':'arrowclosed'}} for i,(a,b,label) in enumerate(connections)]
    return {'diagram_type':kind,'nodes':nodes,'edges':edges,'sources':[],
            'notice':'Starter example. Replace the sample steps and verify connections before review.'}


CATALOG=[
 {'id':'programming','name':'Programming flowchart','description':'Inputs, a decision, processing and an output.','kind':'flowchart',
  'content':graph('flowchart',[
   ('start','start','Start',300,0),('input','io','Read inputs',300,160),('condition','decision','Condition met?',300,320),
   ('process','process','Perform calculation',0,510),('output','io','Write output',0,670),('end','end','End',300,850)],
   [('start','input',''),('input','condition',''),('condition','process','Yes'),('condition','end','No'),('process','output',''),('output','end','')])},
 {'id':'process','name':'Process flowchart','description':'A request, work steps, review and a correction loop.','kind':'flowchart',
  'content':graph('flowchart',[
   ('start','start','Request received',300,0),('prepare','process','Check requirements',300,170),('work','process','Perform the task',300,340),
   ('review','decision','Result acceptable?',300,510),('correct','process','Correct the result',660,340),('end','end','Complete and hand over',300,710)],
   [('start','prepare',''),('prepare','work',''),('work','review',''),('review','end','Yes'),('review','correct','No'),('correct','work','Recheck')])},
 {'id':'system','name':'System flowchart','description':'User input, application services, stored data and response.','kind':'flowchart',
  'content':graph('flowchart',[
   ('user','io','User request',280,0),('interface','process','Application interface',280,170),('service','subprocess','Processing service',280,340),
   ('data','document','Read or write data',620,510),('response','io','Return the result',280,680)],
   [('user','interface','Input'),('interface','service','Request'),('service','data','Data'),('data','response','Result'),('service','response','Response')])},
 {'id':'navigation','name':'Navigation flowchart','description':'Entry page, sign-in, workspace and destination pages.','kind':'flowchart',
  'content':graph('flowchart',[
   ('home','start','Home page',300,0),('signin','process','Sign in',300,170),('workspace','process','Workspace',300,340),
   ('projects','process','Projects',0,530),('settings','process','Settings',620,530),('detail','document','Project details',0,700)],
   [('home','signin',''),('signin','workspace',''),('workspace','projects','Open projects'),('workspace','settings','Open settings'),('projects','detail','Select project')])},
 {'id':'planning-map','name':'Project planning map','description':'A central topic with scope, people, milestones and risks.','kind':'mindmap',
  'content':graph('mindmap',[
   ('central','topic','Project topic',300,280),('scope','subtopic','Scope and goals',0,0),('people','subtopic','People and roles',650,0),
   ('milestones','subtopic','Milestones',0,560),('risks','subtopic','Risks and questions',650,560)],
   [('central','scope',''),('central','people',''),('central','milestones',''),('central','risks','')])}
]


def catalog():
    return {'items':deepcopy(CATALOG)}


def content(key,kind):
    item=next((r for r in CATALOG if r['id']==key and r['kind']==kind),None)
    if not item:raise HTTPException(400,'Choose a starter template for this diagram type.')
    return {**deepcopy(item['content']),'starter_template':item['id']}
