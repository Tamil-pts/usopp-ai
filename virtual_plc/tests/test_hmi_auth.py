"""Source-scheduled HMI login initialization, without exposing source credentials."""
import json

import pytest

from virtual_plc.core.hmi_auth import prepare_password_sources
from virtual_plc.core.hmi_runtime import input_value, password_needs_initialization, password_source_status
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.tests.test_runtime import project, variable


def login_fixture(secret='', other=False):
    model=project("IF Secret = '' THEN Secret := '400'; END_IF;\n"
                  "IF Level = 4 THEN Caption := '4th level'; ELSE Caption := 'Logged out'; END_IF;",
                  [variable('Secret','STRING[16]',secret,retain=True),variable('Level','USINT'),
                   variable('Caption','STRING[32]',''),variable('Other','STRING[16]','')])
    model['tasks'][0]['intervalMs']=1000
    control={'id':'password','kind':'password','passwordLevelBinding':'Level','textGroup':'passwords',
             'properties':{'TextSource':'MultipleTexts','MaxLevel':'15','MaxChars':'16'}}
    snippets={'role':{'classId':'0x00002002','binding':'Secret','properties':{'MinChars':'1'}}}
    group={'4':{'en':'{role}'}}
    if other:
        snippets['other']={'classId':'0x00002002','binding':'Other'}
        group['5']={'en':'{other}'}
    page={'id':'login','objects':[control]}
    model['hmi']={'pages':[page],'textGroups':{'passwords':group},'textSnippets':{'passwords':snippets}}
    return model,page,control,VirtualRuntime(model)


def test_scheduled_startup_then_login_refreshes_source_display_and_pauses():
    model,page,control,runtime=login_fixture()
    assert password_source_status(model,control,runtime)['waitingLevels']==[4]
    result=prepare_password_sources(runtime,model,control,runtime.tick,password='400')
    assert result['waitingLevels']==[]
    assert runtime.time_ms>=1000 and runtime.tasks[0]['executionCount']==1
    assert runtime.status=='paused'
    assert input_value(model,page,control,runtime,'400')=={'loginLevel':4}
    prepare_password_sources(runtime,model,control,runtime.tick,refresh=True)
    assert runtime.get_value('Level')==4
    assert runtime.get_value('Caption')=='4th level'
    assert runtime.status=='paused'
    assert '400' not in json.dumps(result)
    assert not any('400' in event.get('message','') for event in runtime.trace)


def test_retained_custom_password_is_preserved_and_wrong_password_logs_out():
    model,page,control,runtime=login_fixture('retained-test')
    assert not password_needs_initialization(model,control,runtime,'400')
    assert input_value(model,page,control,runtime,'retained-test')['loginLevel']==4
    prepare_password_sources(runtime,model,control,runtime.tick,refresh=True)
    assert runtime.get_value('Secret')=='retained-test'
    assert input_value(model,page,control,runtime,'400')['loginLevel']==0
    prepare_password_sources(runtime,model,control,runtime.tick,refresh=True)
    assert runtime.get_value('Caption')=='Logged out'
    assert input_value(model,page,control,runtime,'')['loginLevel']==0


def test_matching_source_does_not_wait_for_unrelated_empty_role():
    model,page,control,runtime=login_fixture(other=True)
    prepare_password_sources(runtime,model,control,runtime.tick,password='400')
    assert password_source_status(model,control,runtime)['waitingLevels']==[5]
    assert not password_needs_initialization(model,control,runtime,'400')
    assert input_value(model,page,control,runtime,'400')['loginLevel']==4
    prepare_password_sources(runtime,model,control,runtime.tick,refresh=True)
    assert runtime.get_value('Caption')=='4th level'


def test_levels_one_through_eleven_follow_text_group_indices():
    model,page,control,runtime=login_fixture()
    model['hmi']['textGroups']['passwords']={str(i):{'en':'test-role-'+str(i)} for i in range(1,12)}
    for level in range(1,12):
        assert input_value(model,page,control,runtime,'test-role-'+str(level))['loginLevel']==level
        assert runtime.get_value('Level')==level
    assert password_source_status(model,control,runtime)['configuredLevels']==list(range(1,12))
    assert input_value(model,page,control,runtime,'unknown-role')['loginLevel']==0


def test_initialization_preserves_running_state_and_source_breakpoints():
    model,page,control,runtime=login_fixture()
    runtime.command('run',return_snapshot=False)
    prepare_password_sources(runtime,model,control,runtime.tick,password='400')
    assert runtime.status=='running'
    model,page,control,runtime=login_fixture()
    runtime.set_breakpoint('Logical/Main/Main.st',1)
    with pytest.raises(ValueError,match='breakpoint'):
        prepare_password_sources(runtime,model,control,runtime.tick,password='400')
    assert runtime.status=='paused' and runtime.get_value('Level')==0
    assert runtime.get_value('Secret')==''


def test_refresh_reports_breakpoint_instead_of_claiming_display_is_updated():
    model,page,control,runtime=login_fixture('retained-test')
    runtime.set_breakpoint('Logical/Main/Main.st',1)
    with pytest.raises(ValueError,match='display update is pending'):
        prepare_password_sources(runtime,model,control,runtime.tick,refresh=True)
    assert runtime.status=='paused'


def test_missing_or_faulted_source_never_fabricates_a_password():
    model,page,control,runtime=login_fixture()
    runtime.active_units.clear()
    with pytest.raises(ValueError,match='no assigned source writer'):
        prepare_password_sources(runtime,model,control,runtime.tick,password='400')
    assert runtime.get_value('Secret')==''
    model,page,control,runtime=login_fixture()
    runtime.status='faulted'
    with pytest.raises(ValueError,match='Reset the PLC source fault'):
        prepare_password_sources(runtime,model,control,runtime.tick,password='400')
