from io import BytesIO
import pytest
from reportlab.pdfgen import canvas
from backend.api import virtual_electrical as api
from backend.electrical.reconstruction import table_connections,validate
from tests.test_virtual_electrical import client,ready

def sample():
    raw=BytesIO();pdf=canvas.Canvas(raw,pagesize=(600,400))
    pdf.drawString(20,370,'TABLE 4 SL.NO DESCRIPTION SIDE-A SIDE-B')
    pdf.line(290,340,480,340)
    for i in range(1,4):
        pdf.drawString(300,340-i*30,f'X9-{i}({i})');pdf.drawString(390,340-i*30,f'X13-{i}({i})')
    pdf.showPage();pdf.drawString(30,350,'MOTOR CIRCUIT K1');pdf.line(50,300,400,300);pdf.showPage();pdf.save();return raw.getvalue()

def test_industrial_import_review_compile_conflicts_and_owner(client):
    response=client.post('/api/virtual-electrical/projects?mode=industrial',files={'file':('drawing.pdf',sample(),'application/pdf')});assert response.status_code==200
    key=response.json()['id'];ready(client,key);path='/api/virtual-electrical/projects/'+key+'/reconstruction'
    model=client.get(path).json();assert len(model['pages'])==2 and len(model['connections'])==3
    assert model['pages'][0]['classification']=='connection_table'
    assert client.get(path+'/pages/1').json()['lines'] is not None
    preview=client.get(path+'/pages/1/preview');assert preview.status_code==200 and preview.content.startswith(b'\x89PNG')
    assert client.post(path+'/compile',json={'page':1}).status_code==409
    first=model['connections'][0]['id'];revision=model['revision']
    assert client.post(path+'/review',json={'revision':revision,'connection_id':first,'status':'verified','comment':'ok'}).status_code==400
    for c in model['connections']:
        response=client.post(path+'/review',json={'revision':model['revision'],'connection_id':c['id'],'status':'verified','comment':'Checked against original terminal table'})
        assert response.status_code==200,response.text
        model=response.json()
    assert client.post(path+'/review',json={'revision':revision,'connection_id':first,'status':'verified','comment':'Stale review'}).status_code==409
    assert client.post(path+'/compile',json={'page':1}).status_code==409
    approval=client.post(path+'/review-page',json={'revision':model['revision'],'page':1,'comment':'Reviewed table boundaries; no unresolved graphical wiring on this page'})
    assert approval.status_code==200,approval.text
    model=approval.json()
    compiled=client.post(path+'/compile',json={'page':1});assert compiled.status_code==200
    assert compiled.json()['kind']=='continuity_only' and compiled.json()['simulation_ready'] is False
    assert client.get(path+'/validate').json()['status']=='unresolved'
    assert client.get(path+'/pages/2/graphical').status_code==200
    assert client.get(path+'/pages/2/graphical',headers={'test-user':'2'}).status_code==403
    assert client.post(path+'/validate-scope',json={'pages':[1,2]}).json()['status']=='unresolved'
    assert client.post(path+'/validate-scope',json={'pages':[True]}).status_code==400
    assert client.post(path+'/validate-scope',headers={'test-user':'2'},json={'pages':[1]}).status_code==403
    assert client.post(path+'/review-page',json={'revision':model['revision'],'page':2,'comment':'Cannot resolve wiring'}).status_code==409
    assert client.post(path+'/review-page',headers={'test-user':'2'},json={'revision':model['revision'],'page':1,'comment':'Reviewed source'}).status_code==403
    assert model['review_history'][0]['actor_id']==1
    for suffix in ('','/pages/1','/validate'):
        assert client.get(path+suffix,headers={'test-user':'2'}).status_code==403
    assert client.post(path+'/compile',headers={'test-user':'2'},json={'page':1}).status_code==403
    with (api.WORK/key/'source.pdf').open('ab') as stream:stream.write(b'changed')
    assert client.get(path).status_code==409

def test_label_proximity_alone_does_not_create_connection():
    words=[{'text':'X9-1(1)','x0':0,'x1':30,'top':10,'bottom':20},{'text':'X13-1(1)','x0':50,'x1':90,'top':10,'bottom':20}]
    assert table_connections(words,1,'digest','Cable assembly')[0]==[]
    words[1]['top']=50
    assert table_connections(words,1,'digest','TABLE SIDE-A SIDE-B')[0]==[]

def test_independent_trace_requires_real_unbranched_path_and_unique_terminal_anchors():
    from backend.electrical.graphical import trace,reconcile
    words=[{'text':'X9-1(1)','x0':5,'x1':29,'top':45,'bottom':55},
           {'text':'X13-1(1)','x0':131,'x1':170,'top':45,'bottom':55}]
    lines=[{'pts':[(30,50),(80,50)]},{'pts':[(80,50),(130,50)]}]
    traced=trace(words,lines,6,'hash','X9 X13')
    assert len(traced['connections'])==1
    assert traced['connections'][0]['source_lines']==[0,1]
    assert trace(words,[],6,'hash','X9 X13')['connections']==[]
    assert trace(words,lines,16,'hash','TABLE SIDE-A SIDE-B',table=True)['connections']==[]
    # A branch makes the terminal-to-terminal path ambiguous; touching is not a net.
    assert trace(words,lines+[{'pts':[(80,50),(80,90)]}],6,'hash','X9 X13')['connections']==[]
    # Crossing segment interiors do not become junctions.
    crossing=trace(words,[{'pts':[(30,50),(80,50)]},{'pts':[(80,30),(80,70)]},{'pts':[(80,70),(130,50)]}],6,'hash','X9 X13')
    assert crossing['connections']==[]
    assignment={'id':'table','source':{'page':16},'from':{'device':'table/X9','pin':'1'},'to':{'device':'table/X13','pin':'1'}}
    agreement=reconcile([traced],[assignment])[0]
    assert agreement['status']=='corroborated' and agreement['approval_status']=='needs_review'
    assignment['to']['pin']='2'
    assert reconcile([traced],[assignment])[0]['status']=='conflict'

def test_project_scope_cannot_skip_graphical_dependencies_or_empty_wiring_pages():
    model={'source':{'sha256':'hash'},'devices':[{'id':'table/X9','designation':'X9','pins':['1'],'page':16},{'id':'table/X13','designation':'X13','pins':['1'],'page':16}],
           'connections':[{'id':'c','from':{'device':'table/X9','pin':'1'},'to':{'device':'table/X13','pin':'1'},'status':'verified','source':{'page':16}}],
           'issues':[{'page':6,'status':'unresolved','message':'Unresolved cable bundle wiring.'}],
           'graphical_pages':[{'page':6,'device_designations':['X9','X13']}]}
    assert validate(model,16)['status']=='verified'
    scope=validate(model,pages=[16])
    assert scope['status']=='unresolved' and scope['missing_dependency_pages']==[6]
    assert validate(model,6)['status']=='unresolved'
    assert validate(model,pages=[6,16])['status']=='unresolved'
    model['issues']=[{'page':16,'status':'unresolved','code':'graphical_review_required','message':'Review graphics.'}]
    assert validate(model,16)['status']=='unresolved'
    model['page_reviews']=[{'page':16,'source_sha256':'hash'}]
    assert validate(model,16)['status']=='verified'
