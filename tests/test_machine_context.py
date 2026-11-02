from copy import deepcopy
from pathlib import Path
import json

import pytest

from virtual_plc.core.machine_identity import build, select
from virtual_plc.core.machine_calls import add_help


@pytest.fixture
def project():
    names={'Fan':'BOOL','LampColor':'USINT','Mode':'BOOL','Setpoint':'REAL','Lower':'REAL','Upper':'REAL',
           'Hide':'UINT','State':'UINT','Timer':'Delay'}
    variables=[{'id':'@global:'+n,'name':n,'type':t,'scope':'@global','source':'Logical/Global.var','line':i+2} for i,(n,t) in enumerate(names.items())]
    code='''PROGRAM _CYCLIC
IF Fan THEN
LampColor := 10;
ELSE
LampColor := 51;
END_IF;
IF Mode THEN
Timer(IN := Fan);
END_IF;
CASE State OF
0:
IF Mode THEN
State := 10;
END_IF;
10:
IF NOT Mode THEN
State := 0;
END_IF;
END_CASE;
END_PROGRAM'''
    file='Logical/Drive/Cyclic.st'
    sources={file:code,'Logical/Global.var':'VAR_GLOBAL\n'+''.join(n+' : '+t+';\n' for n,t in names.items())+'END_VAR',
             'Logical/Lib/Delay.fun':'FUNCTION_BLOCK Delay\nVAR_INPUT\nIN : BOOL;\nEND_VAR\nEND_FUNCTION_BLOCK',
             'Logical/Panel/Pages/IO.page':'<Page><Control Name="Label"/><Control Name="Lamp"/></Page>',
             'Logical/Panel/TextGroups/Names.txtgrp':'<TextGroup><Text Value="Fan motor"/></TextGroup>',
             'Physical/CFG/PLC/IoMap.iom':'Cyclic#1.Fan AT %QX."DO1".DigitalOutput02;',
             'Physical/OTHER/PLC/IoMap.iom':'Fan AT %QX."WRONG".DigitalOutput03;',
             'Physical/CFG/Hardware.hw':'<Hardware><Module Name="IF23" Type="4PP065.IF23-1"><Connection TargetConnector="SS1"/><Connector Name="IF2"><Parameter ID="DeviceType" Value="RS485"/></Connector><Connector Name="IF3"><Parameter ID="Mode" Value="CANOPEN"/></Connector></Module></Hardware>'}
    def control(name,kind,x,y,**extra):
        return {'id':name,'name':name,'kind':kind,'x':x,'y':y,'width':170 if kind=='text' else 15,'height':15,
                'layer':'Default','source':'Logical/Panel/Pages/IO.page','properties':{},**extra}
    objects=[control('Label','text',10,80,textGroup='Logical/Panel/TextGroups/Names.txtgrp',textIndexBinding='@global:Mode',properties={'TextSource':'MultipleTexts','TextIndexOffset':'0'}),
             control('Lamp','shape',200,81,properties={'ColorDatapoint':'Source[global].Variable[Local.LampColor]'}),
             control('Setting','numeric',20,120,binding='@global:Setpoint',minBinding='@global:Lower',maxBinding='@global:Upper',statusBinding='@global:Hide',layerState={'statusBinding':'@global:Mode'},properties={'MinDatapoint':'Source[global].Variable[Local.Lower]'})]
    model={'projectInfo':{'activeConfiguration':'CFG','configuredHmiObjects':['Panel']},'variables':variables,
           'programs':[{'id':file,'name':'Drive','source':file,'scope':'logical/drive','code':code,'kind':'program'}],
           'functions':[],'interfaces':[{'name':'Delay','kind':'function_block','source':'Logical/Lib/Delay.fun','line':1}],
           'tasks':[{'name':'Cyclic#1','enabled':True,'programs':[file]}],
           'hmi':{'pages':[{'name':'IO','source':'Logical/Panel/Pages/IO.page','objects':objects}],
                  'textGroups':{'Logical/Panel/TextGroups/Names.txtgrp':{'0':{'en':'Fan motor'},'1':{'en':'Not Used'}}}}}
    return model,sources


def test_names_keep_dynamic_selector_boolean_producer_and_active_hardware(project):
    model,sources=project;before=deepcopy(model);context=build(model,sources);view=select(context,'explain fan motor sequence')
    assert model==before
    assert view['roots']==['@global:Fan']
    alias=view['aliases'][0]
    assert alias['displaySignal']=='@global:LampColor'
    assert [(c['label'],c['value'],c['selector']) for c in alias['choices']]==[('Fan motor',0,'@global:Mode'),('Not Used',1,'@global:Mode')]
    assert 'needs review' in alias['association']
    assert len(view['hardware'])==1 and 'DO1' in view['hardware'][0]['address']
    assert {i['device'] for i in view['interfaces']}=={'SS1.IF2','SS1.IF3'}
    assert not view['completeMachineSequence']


def test_setting_limits_parent_visibility_and_ambiguous_labels(project):
    model,sources=project
    setting=next(c for c in build(model,sources)['controls'] if c['name']=='Setting')
    assert setting['bindings']['minBinding']=='@global:Lower'
    assert setting['bindings']['maxBinding']=='@global:Upper'
    assert setting['bindings']['layerStatusBinding']=='@global:Mode'
    model['hmi']['pages'][0]['objects'].append(deepcopy(model['hmi']['pages'][0]['objects'][0]))
    assert not select(build(model,sources),'fan motor')['roots']


def test_inactive_hmi_private_scope_and_unresolved_producers_do_not_supply_alias(project):
    model,sources=project
    model['projectInfo']['configuredHmiObjects']=['OtherPanel']
    assert not select(build(model,sources),'fan motor')['roots']
    model['projectInfo']['configuredHmiObjects']=['Panel']
    model['variables'].append({'id':'logical/private:Fan','name':'Fan','type':'BOOL','scope':'logical/private','source':'Logical/Private/Local.var'})
    assert select(build(model,sources),'fan motor')['roots']==['@global:Fan']
    model['tasks'][0]['enabled']=False
    assert not select(build(model,sources),'fan motor')['roots']


def test_state_arrows_are_guarded_assignments_and_calls_have_source_types(project):
    model,sources=project;context=build(model,sources)
    assert {(t['from'],t['to']) for t in context['transitions']}=={('0','10'),('10','0')}
    assert all(t['conditions'] and t['sources'] for t in context['transitions'])
    call=next(c for c in context['calls'] if c['instance']=='Timer')
    assert call['name']=='Delay' and call['kind']=='function_block'
    assert call['conditions']==['Mode'] and call['declaration']=='Logical/Lib/Delay.fun'
    assert call['arguments']['IN']=='Fan'
    view=select(context,'Fan')
    view=add_help(view,lambda *args:[{'id':'v1','kind':'vendor','title':'Delay','file':'Delay.html','excerpt':'Delay(IN)'},
                                  {'id':'g1','kind':'guide','title':'Delay','file':'guide','excerpt':'Delay'},
                                  {'id':'v2','kind':'vendor','title':'OtherDelay','file':'other','excerpt':'OtherDelay'}])
    assert [h['id'] for h in view['calls'][0]['documentation']]==['v1']


def test_parser_failure_is_not_an_unconditional_status_alias(project):
    model,sources=project;file=model['programs'][0]['source'];sources[file]='IF Fan THEN\nLampColor := 10;\n'
    assert not select(build(model,sources),'fan motor')['roots']


def test_active_configuration_unresolved_does_not_choose_first_hardware(project):
    model,sources=project;model['projectInfo']['activeConfiguration']=None
    context=build(model,sources)
    assert not context['hardware'] and not context['interfaces']


def test_publication_has_source_links_and_rejects_changed_project(project,tmp_path):
    from types import SimpleNamespace
    from backend.core.machine_context import decorate,signature
    model,sources=project
    for name,text in sources.items():
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    context=build(model,sources);context['snapshotSignature']=signature(tmp_path)
    index=SimpleNamespace(root=tmp_path)
    result=decorate({'answer':'Original checked trace.','evidence':[]},index,'fan motor',context)
    assert 'Fan motor' in result['answer'] and 'Mode' in result['answer']
    assert result['evidence'] and all(e['sourceId'] in result['answer'] for e in result['evidence'])
    assert result['machineContext']['roots']==['@global:Fan']
    (tmp_path/'Logical/Global.var').write_text('VAR_GLOBAL\nChanged : BOOL;\nEND_VAR',encoding='utf-8')
    rejected=decorate({'answer':'Original checked trace.'},index,'fan motor',context)
    assert rejected['answer']=='Original checked trace.' and 'machineContext' not in rejected
    assert 'withheld' in rejected['machineContextNotice']


def test_action_source_with_final_newline_has_no_one_past_eof_ranges():
    from python_engine.engineering_model.decoder import decode,section_ranges
    text='ACTION Power:\nIF Start THEN\nMotor := TRUE;\nEND_IF;\nEND_ACTION\n'
    data=decode('Power.st',text)
    count=len(text.splitlines())
    for part in section_ranges(text,data['sections']):
        assert part['last']<=count
    def nodes(rows):
        for n in rows:
            assert n.get('endLine',n['line'])<=count
            nodes(n.get('children',[]))
            for branch in n.get('branches',[]):nodes(branch['nodes'])
    for part in data['sections']:nodes(part['nodes'])


def test_nested_call_arguments_preserve_device_and_index_expressions():
    from virtual_plc.core.machine_calls import argument_parts
    value="CANopenSDORead8(enable := TRUE, pDevice := ADR('SS1.IF3'), index := (24575 - P[I]), node := 4)"
    assert argument_parts(value)==['enable := TRUE',"pDevice := ADR('SS1.IF3')",'index := (24575 - P[I])','node := 4']
    assert argument_parts(value,'ADR')==["'SS1.IF3'"]
    assert argument_parts('Value := First(1) + Second(2, Nested(3));','Second')==['2','Nested(3)']


def test_call_queries_by_type_and_instance_and_default_browsing(project):
    model,sources=project;context=build(model,sources)
    for question in ['Explain Delay function block','Explain Timer']:
        view=select(context,question)
        assert view['callQuery']
        assert view['calls'][0]['name']=='Delay'
        assert view['calls'][0]['instanceSignal']=='@global:Timer'
    browse=select(context)
    assert browse['aliases'] and browse['operations'] and not browse['roots']


def test_boolean_parentheses_are_not_calls_and_declarations_ignore_case(project):
    model,sources=project;file=model['programs'][0]['source']
    sources[file]='PROGRAM _CYCLIC\nFan := NOT(Mode);\ndelay(IN := Fan);\nEND_PROGRAM'
    calls=build(model,sources)['calls']
    assert [c['name'] for c in calls]==['delay']
    assert calls[0]['kind']=='function_block' and calls[0]['declaration']=='Logical/Lib/Delay.fun'


def test_small_result_budget_keeps_the_questioned_output_first(project):
    model,sources=project;file=model['programs'][0]['source']
    sources[file]='PROGRAM _CYCLIC\nState := 10;\nLampColor := 51;\nFan := Mode;\nEND_PROGRAM'
    view=select(build(model,sources),'Fan',limit=1)
    assert view['roots']==['@global:Fan']
    assert view['operations'][0]['output']=='@global:Fan'
    assert view['truncated']


def test_commented_ladder_call_does_not_make_implementation_reachable(project):
    model,sources=project;file='Logical/Drive/Cyclic.ld';implementation='Logical/Lib/Delay.st'
    sources[file]='''<networks><network commented="1"><row><empty/><functionblock position="header" name="Timer" type="Delay"/></row>
<row><contact name="Fan"/><functionblock position="topbottom" type="Delay"><input name="IN"/><output name="Q"/></functionblock></row></network></networks>'''
    sources[implementation]='FUNCTION_BLOCK Delay\nQ := IN;\nEND_FUNCTION_BLOCK'
    model['programs'][0].update(id=file,source=file,code=sources[file])
    model['tasks'][0]['programs']=[file]
    model['functions']=[{'name':'Delay','source':implementation,'line':1,'kind':'function_block'}]
    model['programs'].append({'id':implementation,'source':implementation,'scope':'logical/lib','name':'Delay','kind':'function_block','code':sources[implementation]})
    context=build(model,sources);call=next(c for c in context['calls'] if c['instance']=='Timer')
    assert call['disabled'] and not call['active']
    assert not next(f for f in context['functions'] if f['id']==implementation)['active']
