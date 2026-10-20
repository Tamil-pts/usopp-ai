from copy import deepcopy
import pytest

from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.core.hmi_runtime import control_state, input_value, navigation_page, require_input
from virtual_plc.core.hmi_text import expand_text
from virtual_plc.core.hmi_preview import preview_model
from virtual_plc.core.c_declarations import merge
from virtual_plc.tests.test_runtime import project, variable


def test_iec_not_preserves_unsigned_width_and_boolean_type():
    runtime = VirtualRuntime(project('Flag := NOT Flag; Ready := NOT Ready; Signed := NOT Signed;',
        [variable('Flag','USINT'),variable('Ready','BOOL',False),variable('Signed','INT')]))
    runtime.command('scan')
    assert runtime.status == 'paused'
    assert runtime.get_value('Flag') == 255
    assert runtime.get_value('Ready') is True
    assert runtime.get_value('Signed') == -1
    runtime.command('scan')
    assert runtime.get_value('Flag') == 0
    assert runtime.get_value('Signed') == 0


def test_password_snippets_use_source_initialization_and_numeric_formatting():
    runtime = VirtualRuntime(project("IF Secret = '' THEN Secret := 'qa1'; END_IF;",
        [variable('Secret','STRING[8]',''),variable('Year','UINT',2026),variable('Level','USINT')]))
    snippets={'role':{'classId':'0x00002002','binding':'Secret','properties':{'MinChars':'1','MaxChars':'8'}},
              'year':{'classId':'0x00002001','binding':'Year','properties':{'MinIntegerDigits':'4'}}}
    model={'hmi':{'textGroups':{'passwords':{'1':{'en':'{role}'},'11':{'en':'X{year}'}}},'textSnippets':{'passwords':snippets}}}
    control={'id':'password','kind':'password','passwordLevelBinding':'Level','textGroup':'passwords',
             'properties':{'TextSource':'MultipleTexts','MaxLevel':'15','MaxChars':'8'}}
    page={'objects':[control]}
    with pytest.raises(ValueError,match='initialization'):input_value(model,page,control,runtime,'qa1')
    runtime.command('scan')
    assert input_value(model,page,control,runtime,'qa1') == {'loginLevel':1}
    assert input_value(model,page,control,runtime,'X2026') == {'loginLevel':11}
    assert input_value(model,page,control,runtime,'wrong') == {'loginLevel':0}
    assert runtime.get_value('Level') == 0
    assert expand_text('{year}',snippets,runtime) == '2026'


def test_runtime_status_and_hidden_hotspots_gate_input():
    runtime=VirtualRuntime(project('',[variable('Layer','INT',1),variable('Cover','USINT'),variable('Value')]))
    layer={'id':'popup','statusBinding':'Layer','statusConfigured':True}
    field={'id':'value','kind':'numeric','input':True,'binding':'Value','x':0,'y':0,'width':40,'height':20}
    hotspot={**field,'id':'cover','kind':'hotspot','statusBinding':'Cover','statusConfigured':True}
    page={'objects':[field,hotspot]}
    assert not control_state({'layerState':layer},runtime)['visible']
    with pytest.raises(ValueError,match='covered'):require_input(page,field,runtime)
    runtime.set_value('Cover',1,return_snapshot=False)
    require_input(page,field,runtime)
    for word,visible,locked in [(0,True,False),(1,False,False),(2,True,True),(3,False,True)]:
        runtime.set_value('Layer',word,return_snapshot=False)
        state=control_state({'layerState':layer},runtime)
        assert (state['visible'],state['locked'])==(visible,locked)
    # Editor Hidden is not the runtime status word.
    assert control_state({'layerState':{'properties':{'VisibilityMode':'Hidden'}}},runtime)['visible']
    # A layer's editor background must not cover runtime controls.
    page['layers']=[{'id':'base'}, {'id':'decoration','properties':{
        'BackColor':'9','Left':'0','Top':'0','Width':'640','Height':'480'}}]
    field['layerState']={'id':'base'}
    require_input(page,field,runtime)
    page['objects'].append({**field,'id':'popup-background','name':'Popup shape','kind':'shape',
                            'properties':{'BackColor':'225','FillStyle':'Solid'}})
    with pytest.raises(ValueError,match='Popup shape'):require_input(page,field,runtime)


def test_page_navigation_stays_in_current_hmi_target():
    pages=[{'id':p,'name':'Main','source':p} for p in ['Logical/HMI1/Pages/Main.page','Logical/HMI2/Pages/Main.page']]
    assert navigation_page(pages,{'source':'Logical/HMI2/Pages/Login.page'},'Main') == pages[1]
    with pytest.raises(ValueError,match='ambiguous'):navigation_page(pages,{'source':'Unknown'},'Main')


def test_preview_selects_source_credential_and_visibility_writers():
    model=project("IF Secret = '' THEN Secret := 'qa1'; END_IF;",[
        variable('Secret','STRING[8]',''),variable('Level','USINT'),variable('Visible','USINT'),variable('Extra','USINT')])
    model['programs'][0].update(kind='program',entry='cyclic')
    model['programs'].append({**model['programs'][0],'id':'roles','source':'Roles.ab','code':'IF Level = 1 THEN Visible := 1; Extra := 0; ELSE Visible := 0; Extra := 1; END_IF;'})
    model['tasks'][0]['programs'].append('roles')
    model['hmi']={'pages':[{'id':'login','source':'Logical/HMI/Pages/Login.page','objects':[
        {'kind':'password','passwordLevelBinding':'Level','textGroup':'passwords','statusBinding':'Visible'}]}],
        'textSnippets':{'passwords':{'role':{'classId':'0x00002002','binding':'Secret'}}}}
    original=deepcopy(model)
    result=preview_model(model,VirtualRuntime(model),'login','parent')
    assert result['executionScope']['programIds']==['main','roles']
    assert result['executionScope']['completeMachineExecution'] is False
    assert model==original
    assert VirtualRuntime(result).run_allowed


def test_c_global_declarations_are_explicit_and_configuration_scoped():
    model={'variables':[],'projectInfo':{'activeConfiguration':'One'}}
    sources={'Logical/Trend/Main.c':'_GLOBAL UINT Screen, Year;\n_GLOBAL USINT Month, Day;\n_GLOBAL UINT *ptr;\n',
             'Logical/Other/Main.c':'_GLOBAL UINT Year;',
             'Physical/Two/Main.c':'_GLOBAL UINT Wrong;'}
    merge(model,sources)
    assert {v['name'] for v in model['variables']} == {'Screen','Year','Month','Day','ptr'}
    assert next(v for v in model['variables'] if v['name']=='ptr')['type']=='UINT*'
    merge(model,sources)
    assert len(model['variables'])==5
    merge(model,{'Logical/Bad/Main.c':'_GLOBAL DINT Year;'})
    assert next(v for v in model['variables'] if v['name']=='Year')['ambiguous']


def test_ladder_scalar_conversion_uses_the_same_variable_memory():
    xml='''<networks><network><row><analog type="input" name="Delay"/>
    <function position="topbottom" type="UDINT_TO_TIME"><input name="IN"/><output name="12"/></function>
    <analog type="output" name="Preset"/></row></network></networks>'''
    runtime=VirtualRuntime(project(xml,[variable('Delay','UDINT',1200),variable('Preset','TIME')],'ld'))
    assert runtime.run_allowed, runtime.diagnostics
    runtime.command('scan')
    assert runtime.get_value('Preset')==1200
    # A parallel branch cannot OR a BOOL contact with scalar conversion data.
    blocked=VirtualRuntime(project(xml.replace('</network>','<row><contact name="Other" or="true"/></row></network>'),
        [variable('Delay','UDINT'),variable('Preset','TIME'),variable('Other','BOOL',False)],'ld'))
    assert not blocked.run_allowed
    assert any(d['code']=='LADDER_SIGNAL_TYPE' for d in blocked.diagnostics)
