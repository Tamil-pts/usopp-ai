"""Cross-project runtime and portable service registry contracts."""
import json
from pathlib import Path
import struct

import pytest

from virtual_plc.core.c_declarations import merge
from virtual_plc.core.catalog import implementation_index,load_catalog
from virtual_plc.core.runtime import VirtualRuntime
from virtual_plc.tests.test_runtime import project,variable


def test_c_declarations_pointer_heap_cast_size_and_string_decay():
    code='''typedef struct { UINT n; USINT flag; } pair_typ;
_GLOBAL pair_typ *p;
_GLOBAL UINT Result;
_GLOBAL STRING Text[20];
void _INIT Init(void) { TMP_alloc(sizeof(pair_typ)*2,(void**)&p); }
void _CYCLIC Cyclic(void) { p[1].n = (UINT)65535; Result=p[1].n; strcpy(Text,"ABC"); }
'''
    model=project(code,[],'c');merge(model,{model['programs'][0]['source']:code})
    runtime=VirtualRuntime(model)
    assert runtime.run_allowed,runtime.diagnostics
    runtime.command('scan')
    assert runtime.status=='paused',runtime.diagnostics
    assert runtime.get_value('Result')==65535
    assert runtime.get_value('Text')=='ABC'
    assert runtime.vendor.size(runtime.memory.spec('pair_typ'))==4


def test_basic_nested_case_step_variable_and_integer_string_assignments():
    code='''CASE Choice OF
ACTION 1:
 CASE Second OF
 ACTION 2:
  Step = 10
  Word = 62991
  Text = "Enter IP Address"
 ENDACTION
 ENDCASE
ENDACTION
ENDCASE'''
    runtime=VirtualRuntime(project(code,[variable('Choice',initial=1),variable('Second',initial=2),variable('Step'),variable('Word','INT'),variable('Text','STRING[15]','')],'ab'))
    assert runtime.run_allowed,runtime.diagnostics
    runtime.command('scan')
    assert runtime.get_value('Step')==10
    assert runtime.get_value('Word')==-2545
    assert runtime.get_value('Text')=='Enter IP Addres'
    with pytest.raises(ValueError):runtime.set_value('Word',62991,return_snapshot=False)
    with pytest.raises(ValueError):runtime.set_value('Text','Enter IP Address',return_snapshot=False)


def test_bit_reads_and_writes_share_original_integer():
    runtime=VirtualRuntime(project('Byte.7 := TRUE; Seen := Byte.7; Byte.0 := FALSE;', [variable('Byte','USINT',1),variable('Seen','BOOL',False)]))
    assert runtime.run_allowed,runtime.diagnostics
    runtime.command('scan')
    assert runtime.get_value('Byte')==128 and runtime.get_value('Seen') is True


def test_nested_tcp_instances_have_independent_state():
    runtime=VirtualRuntime(project('Net.Open(enable:=TRUE,port:=502); Status:=Net.Open.status;',[variable('Net','Network',None),variable('Status','UINT')],types={'Network':{'kind':'struct','fields':{'Open':'TcpOpen'}}}))
    assert runtime.run_allowed,runtime.diagnostics
    runtime.command('scan');runtime.command('scan')
    assert runtime.status=='paused',runtime.diagnostics
    assert runtime.get_value('Status')==0


def test_source_provided_sg4_layout_and_member_pointer():
    model=project('Pointer:=ADR(Data.Value); Size:=SIZEOF(Data);',[variable('Data','Record',None),variable('Pointer','UDINT'),variable('Size','UDINT')],
                  types={'Record':{'kind':'struct','source':'Logical/Types.typ','fields':[{'name':'Flag','type':'BOOL'},{'name':'Count','type':'INT'},{'name':'Value','type':'REAL'},{'name':'End','type':'UINT'}]}})
    runtime=VirtualRuntime(model);assert runtime.run_allowed,runtime.diagnostics
    runtime.command('scan');assert runtime.get_value('Size')==12
    runtime.vendor.write(runtime.get_value('Pointer'),struct.pack('<f',3.5))
    assert runtime.get_value('Data')['Value']==3.5


def test_csv_allocation_edit_save_open_and_truncation():
    runtime=VirtualRuntime(project('A:=A;',[variable('A')]))
    csv=runtime.services.csv
    ident=csv.call('BRSE_CSV_ALLOC',[3,2,5,'',','])
    def execute(kind,key,**fields):
        from virtual_plc.core.csv_services import BLOCKS
        inputs,outputs=BLOCKS[kind]
        block={name:False if dtype=='BOOL' else '' if dtype.startswith('STRING') else 0 for name,dtype in {**inputs,**outputs}.items()}
        block.update(AllocIdent=ident,**fields)
        assert csv.block(kind,key,block)['Busy']
        runtime.scan_count+=1
        result=csv.block(kind,key,block)
        assert result['Done'] and not result['Error'],result
        return result
    execute('BRSE_CSV_New','new',Rows=2,Columns=2)
    text=runtime.vendor.allocate('csv-test-string',8,b'ABCDEFG\0')
    assert csv.call('BRSE_CSV_SETCELL',[ident,0,0,text])==255
    assert csv.call('BRSE_CSV_SETCELLASDINT',[ident,1,1,42])==1
    execute('BRSE_CSV_Save','save',FileDevice='HD',FileName='data.csv')
    assert b'ABCDE' in runtime.vendor.files[('HD','data.csv')]
    execute('BRSE_CSV_New','clear',Rows=2,Columns=2)
    execute('BRSE_CSV_Open','open',FileDevice='HD',FileName='data.csv')
    assert csv.call('BRSE_CSV_GETCELLASDINT',[ident,1,1])==42
    assert csv.call('BRSE_CSV_FREE',[ident]) is True


def test_portable_registry_matches_executable_interfaces():
    path=Path(__file__).resolve().parents[2]/'knowledge/virtual_plc/br_catalog.json'
    catalog=load_catalog(path)
    assert catalog['implementations']==json.loads(json.dumps(implementation_index()))
    assert catalog['entryCount']>2000
    assert any(not row['implemented'] for row in catalog['entries'])


def test_explicit_profile_is_resettable_and_original_declarations_stay_intact():
    model=project('Result:=100/Divisor;',[variable('Divisor'),variable('Result')],simulationProfile={'schemaVersion':1,'name':'Test only','values':{'Divisor':4}})
    runtime=VirtualRuntime(model);assert runtime.run_allowed,runtime.diagnostics
    runtime.command('scan');assert runtime.get_value('Result')==25
    runtime.set_value('Divisor',5,return_snapshot=False);runtime.command('reset')
    assert runtime.get_value('Divisor')==4
    assert model['variables'][0]['initial']==0


def test_public_python_library_runs_functions_and_independent_instances():
    from virtual_plc.br_library import BRLibrarySession
    library=BRLibrarySession([{'name':'Message','type':'STRING[20]','initial':'ABC'}])
    assert library.call('strlen',library.address('Message'))==3
    assert library.sizeof('Message')==21
    assert library.block('LCRLimScal','speed',x=5,x1=0,y1=0,x2=10,y2=100)['y']==50
    assert library.block('TON','timer',IN=True,PT=20)['Q'] is False
    library.scan(2)
    assert library.block('TON','timer',IN=True,PT=20)['Q'] is True
    assert library.block('TON','other',IN=True,PT=20)['Q'] is False
    with pytest.raises(ValueError):library.block('UnimplementedDrive')


def test_source_copy_correction_is_hash_guarded_and_audited():
    import hashlib
    from virtual_plc.core.source_corrections import apply_corrections
    model=project('A:=1;',[variable('A')]);code=model['programs'][0]['code']
    doc={'schemaVersion':1,'corrections':[{'source':model['programs'][0]['source'],'codeSha256':hashlib.sha256(code.encode()).hexdigest(),'original':'A:=1;','replacement':'A:=2;','reason':'Explicit simulation fixture correction'}]}
    apply_corrections(model,doc)
    assert model['programs'][0]['originalCode']=='A:=1;'
    assert model['programs'][0]['code']=='A:=2;'
    assert model['diagnostics'][-1]['code']=='SIMULATION_SOURCE_CORRECTION'
    with pytest.raises(ValueError):apply_corrections(model,doc)


def test_qualified_canopen_storage_and_no_peer_status_are_real():
    from virtual_plc.br_library import BRLibrarySession
    plc=BRLibrarySession();driver=plc.runtime.services.fieldbus
    device=plc.buffer(4,b'IF1\0')
    waiting=plc.block('CANopenSDORead8','missing',enable=True,pDevice=device,node=2,index=0x2000,subindex=0)
    assert waiting['status']==65535
    plc.scan()
    assert plc.block('CANopenSDORead8','missing')['status']==30811
    driver.configure_can_node('IF1',2,{(0x2000,0):b'\x12\x34'})
    plc.block('CANopenSDORead8','actual',enable=True,pDevice=device,node=2,index=0x2000,subindex=0)
    plc.scan()
    actual=plc.block('CANopenSDORead8','actual')
    assert actual['status']==0 and actual['datalen']==2
    assert (actual['data0'],actual['data1'])==(0x12,0x34)


def test_library_catalog_lookup_uses_authenticated_owner():
    from starlette.requests import Request
    from fastapi import HTTPException
    from virtual_plc.api import library_reference
    request=Request({'type':'http','headers':[]})
    with pytest.raises(HTTPException):library_reference(request,name='IcmpPing')
    request.state.user={'id':'1'}
    found=library_reference(request,name='IcmpPing',library='asicmp')
    assert found['total']==1 and found['entries'][0]['implemented']
