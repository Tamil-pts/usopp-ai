"""Native redraws, model review boundaries and real ngspice numerical checks."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import math
import xml.etree.ElementTree as ET

from fastapi import HTTPException
import pytest
from reportlab.pdfgen import canvas

from backend.core import electrical_native as native
from backend.core.electrical_library import example,pin
from backend.core.electrical_simulation import solve,topology,executable
from backend.core import virtual_electrical as engine
from tests.test_virtual_electrical import client,ready


def require_solver():
    if not executable():pytest.skip('Install ngspice to run real solver checks.')


def test_actual_voltage_divider_matches_ohms_law_and_wire_current():
    require_solver();result=solve(example('divider'))
    assert result['status']=='complete',result
    assert result['measurements']['r1']['current'][0]==pytest.approx(.003,rel=1e-8)
    assert result['measurements']['r2']['voltage'][0]==pytest.approx(6,rel=1e-8)
    assert result['measurements']['v']['current'][0]==pytest.approx(-.003,rel=1e-8)
    assert abs(result['measurements']['w1']['current'][0])==pytest.approx(.003,rel=1e-8)
    assert result['physicalController'] is False


def test_actual_rc_transient_matches_known_time_constant():
    require_solver();document=example('rc');document['elements'][0]['params'].update(period=.1,width=.05)
    result=solve(document,{'mode':'tran','duration':.005,'step':.00001})
    assert result['status']=='complete',result
    time=result['time'];at=min(range(len(time)),key=lambda i:abs(time[i]-.001))
    # R=1k, C=1uF: 63.2 percent of a 9 V step after one millisecond.
    assert result['measurements']['r2']['voltage'][at]==pytest.approx(9*(1-math.exp(-time[at]/.001)),abs=.04)
    assert len(time)>100


def test_actual_relay_starter_seals_in_then_stops():
    require_solver();document=example('starter');previous=None
    for start,stop,energized in [(False,True,False),(True,True,True),(False,True,True),(False,False,False)]:
        next(e for e in document['elements'] if e['id']=='start')['params']['closed']=start
        next(e for e in document['elements'] if e['id']=='stop')['params']['closed']=stop
        previous=solve(document,previous=previous)
        assert previous['status']=='complete',previous
        assert previous['coils']['coil'] is energized


def test_unknown_outlines_and_oversized_topology_block_before_solver():
    document=example();document['elements'].append({'id':'outline','kind':'drawing','x':10,'y':10,'paths':['M0 0L1 1'],'source':{'page':1},'reviewed':False})
    assert any('outline' in issue for issue in solve(document)['issues'])
    document['elements'][-1]['reviewed']=True
    document['elements'] += [{'id':'extra'+str(i),'kind':'wire','x':0,'y':0,'points':[[i,j] for j in range(256)],'reviewed':True} for i in range(4)]
    assert any('800' in issue for issue in solve(document)['issues'])


def test_imported_unreviewed_objects_missing_ground_and_unknown_models_block():
    document=example();document['elements'][0]['reviewed']=False
    assert solve(document)['status']=='blocked'
    document=example();document['elements']=[e for e in document['elements'] if e['kind']!='ground']
    # Remove the dangling ground attachment before topology inspection.
    for e in document['elements']:
        if e.get('to',{}).get('id')=='g':e.pop('to')
    assert any('ground' in e for e in solve(document)['issues'])
    document=example();document['elements'][1]['kind']='motor'
    assert solve(document)['status']=='blocked'


def test_plain_crossing_does_not_join_but_endpoint_tee_does():
    a={'id':'a','kind':'wire','x':0,'y':0,'points':[[-50,0],[50,0]],'reviewed':True}
    b={'id':'b','kind':'wire','x':0,'y':0,'points':[[0,-50],[0,50]],'reviewed':True}
    graph=topology([a,b]);va=graph['wireVertices']['a'][0];vb=graph['wireVertices']['b'][0]
    assert graph['nodes'][va]!=graph['nodes'][vb]
    b['points']=[[0,-50],[0,0]];graph=topology([a,b]);va=graph['wireVertices']['a'][0];vb=graph['wireVertices']['b'][0]
    assert graph['nodes'][va]==graph['nodes'][vb]


def test_saved_move_preserves_connected_pin_and_rejects_invalid_geometry(tmp_path):
    engine.write(tmp_path/'circuit.json',example())
    document=example();source=next(e for e in document['elements'] if e['id']=='v');source['x']+=25
    moved=native.save(tmp_path,document)
    wire=next(e for e in moved['elements'] if e['id']=='w1')
    assert wire['points'][0]==pin(source,'p')
    assert moved['version']==2
    with pytest.raises(HTTPException):native.save(tmp_path,document)
    invalid=deepcopy(moved);invalid['elements'][0]['x']=float('nan')
    with pytest.raises(HTTPException):native.save(tmp_path,invalid)
    invalid=deepcopy(moved);invalid['elements'][0]['params']['value']='9\n.control\nshell malicious'
    with pytest.raises(HTTPException):native.save(tmp_path,invalid)


def test_native_svg_has_wires_symbols_and_no_pdf_or_image():
    result=native.svg(example());root=ET.fromstring(result)
    assert not any(n.tag.endswith('image') for n in root.iter())
    assert any(n.tag.endswith('polyline') for n in root.iter())
    assert any(n.tag.endswith('path') for n in root.iter())
    assert b'R1' in result and b'R2' in result


def test_cable_kit_and_terminal_bom_pages_are_excluded(tmp_path):
    content=BytesIO();pdf=canvas.Canvas(content,pagesize=(600,400))
    for title in ['CABLE KIT ASSEMBLY','BILL OF MATERIALS','TERMINAL SCHEDULE']:
        pdf.drawString(30,360,title);pdf.line(50,250,450,250);pdf.showPage()
    pdf.save();(tmp_path/'source.pdf').write_bytes(content.getvalue());before=sha256(content.getvalue()).hexdigest()
    engine.decode(tmp_path);document=native.build(tmp_path)
    assert not document['elements']
    assert len(document['sources'])==3 and all(s['excluded'] for s in document['sources'])
    assert sha256((tmp_path/'source.pdf').read_bytes()).hexdigest()==before


def test_vector_import_reconstructs_objects_instead_of_embedded_pages(tmp_path):
    content=BytesIO();pdf=canvas.Canvas(content,pagesize=(600,400))
    pdf.drawString(30,360,'CONTROL CIRCUIT SCHEMATIC');pdf.drawString(290,230,'R1')
    pdf.rect(280,180,40,12);pdf.line(150,186,280,186);pdf.line(320,186,450,186);pdf.showPage();pdf.save()
    (tmp_path/'source.pdf').write_bytes(content.getvalue());engine.decode(tmp_path);doc=native.build(tmp_path)
    assert any(e['kind']=='wire' for e in doc['elements'])
    assert any(e['kind'] in {'drawing','unknown','resistor'} for e in doc['elements'])
    assert not any(e['kind'] in {'image','pdf','page'} for e in doc['elements'])
    assert solve(doc)['status']=='blocked'


def test_native_api_save_simulate_export_and_other_account_denial(client):
    require_solver();created=client.post('/api/virtual-electrical/projects/native',json={'example':'divider'})
    assert created.status_code==200,created.text
    key=created.json()['id'];base='/api/virtual-electrical/projects/'+key
    document=client.get(base+'/circuit').json();assert len(document['elements'])==8
    assert client.get(base+'/circuit',headers={'test-user':'2'}).status_code==403
    assert client.post(base+'/simulate',json={'version':1},headers={'test-user':'2'}).status_code==403
    result=client.post(base+'/simulate',json={'version':1}).json();assert result['status']=='complete',result
    assert result['measurements']['r2']['voltage'][0]==pytest.approx(6)
    document['elements'][1]['params']['value']=2000
    saved=client.put(base+'/circuit',json=document);assert saved.status_code==200,saved.text
    assert client.post(base+'/simulate',json={'version':1}).status_code==409
    svg=client.get(base+'/circuit/export?format=svg');assert svg.status_code==200
    assert b'<image' not in svg.content and b'<path' in svg.content
    assert client.get(base+'/circuit/export?format=json').json()['version']==2
    assert client.get(base+'/original').status_code==404
