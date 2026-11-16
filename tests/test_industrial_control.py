from copy import deepcopy
import pytest
from fastapi import HTTPException
from backend.electrical.control import simulate
from tests.test_virtual_electrical import client

def starter():
    devices=[{'id':'PS1','kind':'supply','voltage':24},{'id':'STOP','kind':'contact_nc','control':'STOP'},{'id':'OL1','kind':'contact_nc','control':'OVERLOAD'},{'id':'START','kind':'contact_no','control':'START'},{'id':'K1','kind':'coil'},{'id':'K1_AUX','kind':'contact_no','control':'K1'},{'id':'H1','kind':'lamp'}]
    pairs=[('PS1:plus','STOP:in'),('STOP:out','OL1:in'),('OL1:out','START:in'),('START:out','K1:a1'),('K1:a2','PS1:minus'),('OL1:out','K1_AUX:in'),('K1_AUX:out','START:out'),('START:out','H1:a1'),('H1:a2','PS1:minus')]
    return {'devices':devices,'wires':[{'from':a,'to':b} for a,b in pairs],'inputs':{'START':False,'STOP':False,'OVERLOAD':False}}

def test_start_hold_stop_overload_and_no_automatic_restart():
    p=starter();assert simulate(p)['coils']=={'K1':False}
    p['inputs']['START']=True;r=simulate(p);assert r['coils']['K1'] and r['loads']['H1']
    p['previous']=r['coils'];p['inputs']['START']=False;r=simulate(p);assert r['coils']['K1']
    p['inputs']['STOP']=True;r=simulate(p);assert not r['coils']['K1'] and not r['loads']['H1']
    p['previous']=r['coils'];p['inputs']['STOP']=False;assert not simulate(p)['coils']['K1']
    p['inputs']['START']=True;r=simulate(p);p['previous']=r['coils'];p['inputs'].update(START=False,OVERLOAD=True)
    r=simulate(p);assert not r['coils']['K1'];p['previous']=r['coils'];p['inputs']['OVERLOAD']=False;assert not simulate(p)['coils']['K1']

@pytest.mark.parametrize('damage',['short','missing','kind','endpoint','control','force','nan','multi_supply','cycle'])
def test_unsafe_or_unsupported_models_are_blocked(damage):
    p=starter()
    if damage=='short':p['wires'].append({'from':'PS1:plus','to':'PS1:minus'})
    if damage=='missing':p['wires']=p['wires'][:-1]
    if damage=='kind':p['devices'][0]['kind']=['supply']
    if damage=='endpoint':p['wires'][0]['from']=[]
    if damage=='control':p['devices'][1]['control']=[]
    if damage=='force':p['inputs']['K1']=True
    if damage=='nan':p['devices'][0]['voltage']=float('nan')
    if damage=='multi_supply':p['devices'].append({'id':'PS2','kind':'supply'})
    if damage=='cycle':
        p['devices']=[{'id':'PS1','kind':'supply'},{'id':'K1','kind':'coil'},{'id':'C1','kind':'contact_nc','control':'K1'}]
        p['wires']=[{'from':a,'to':b} for a,b in [('PS1:plus','C1:in'),('C1:out','K1:a1'),('K1:a2','PS1:minus')]]
    with pytest.raises(HTTPException) as error:simulate(p)
    assert error.value.status_code in (400,409)

def test_simulation_api_permissions_and_result(client):
    route='/api/virtual-electrical/control/simulate'
    r=client.post(route,json=starter());assert r.status_code==200 and r.json()['engine']=='discrete_dc_relay'
    assert client.post(route,json=starter(),headers={'test-user':''}).status_code==401
    assert client.post(route,json=starter(),headers={'no-electrical':'1'}).status_code==403
