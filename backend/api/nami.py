"""Nami V1.5 API hosted by the uSOPp application."""
import copy
import ipaddress
import math
import platform
import re
import struct
import subprocess
import threading
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Body, HTTPException, Request
from backend.core import nami_transport as tcp
from backend.core.nami_profiles import frame_protocol
from backend.core.nami_simulator import DEFAULT_STATE, frame, payload
from backend.core.run_history import current_user, begin_run, record_run, read_record, RECORDS
from backend.core.runtime import _local_session
from backend.core.access import require_resource
import json

router = APIRouter(prefix='/api/nami', tags=['PLC Data'])
_state = copy.deepcopy(DEFAULT_STATE)
_state_lock = threading.Lock()
_user_states = {}

def is_ybs(data):
    try: return frame_protocol(data) == 'ybs'
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc

def user_state():
    identity=(current_user.get() or {}).get('id', 'local')
    return _user_states.setdefault(identity, copy.deepcopy(DEFAULT_STATE))

def start_inspect(data,operation):
    metadata=data.get('metadata') or []
    if not isinstance(metadata,list) or len(metadata)>30000 or any(not isinstance(row,dict) for row in metadata):
        raise HTTPException(400,'Metadata must contain at most 30,000 parameter records.')
    if any((row.get('protocol')=='ybs') != is_ybs(data) for row in metadata):
        raise HTTPException(400,'Select the matching request frame and metadata: Server to YBS uses YBS metadata; Server to B&R uses SpinConnect metadata.')
    ip,port,machine_id,timeout=target(data)
    supplied=data.get('plc') if isinstance(data.get('plc'),dict) else {}
    plc={key:supplied[key] for key in ('id','name','machineType','endianness','targetMode','frameProtocol') if key in supplied}
    plc['frameProtocol']='ybs' if is_ybs(data) else 'spinconnect'
    plc.update(ip=ip,port=port,machineId=machine_id,timeoutMs=timeout,isSimulated=bool(data.get('isSimulated')))
    plc.setdefault('id','archived-plc');plc.setdefault('name',ip or 'PLC simulator')
    plc.setdefault('machineType',data.get('machineType') or 'Custom');plc.setdefault('endianness','big' if is_ybs(data) else data.get('endianness','little'))
    sid,_=_local_session()
    identity={'sessionId':sid,'projectName':str(plc['name'])[:200], 'machineDepartment':str(plc['machineType'])[:100],
              'plc':plc,'metadata':metadata,'metadataSource':str(data.get('metadataSource') or '')[:500],
              'operation':operation,'groupCodes':data.get('groupCodes') or [data.get('groupCode',10)],
              'workhubCapture':data.get('workhubCapture') is not False}
    begin_run('datainspect',identity)
    return identity

def finish_inspect(identity,result):
    groups=result.get('results') or ([result] if 'groupCode' in result else [])
    summary={'totalGroups':len(groups),'passed':sum(bool(row.get('success')) for row in groups),
             'failed':sum(not row.get('success') and row.get('stage')!='not_sent' for row in groups),
             'skipped':sum(row.get('stage')=='not_sent' for row in groups)}
    data={**result,**identity,'summary':summary,'runStatus':'failed' if result.get('error') else 'completed'}
    record_run('datainspect',data)
    return data

@router.get('/server-status')
def server_status(request: Request):
    now = datetime.now().astimezone()
    return dict(serverTime=now.isoformat(), timezone=now.strftime('%Z'),
                applicationPort=request.scope.get('server', ('', None))[1])

def number(data, key, default, minimum, maximum):
    try:
        raw = data.get(key, default)
        numeric = float(raw)
        if isinstance(raw, bool) or not math.isfinite(numeric) or not numeric.is_integer():
            raise ValueError()
        value = int(numeric)
        if not minimum <= value <= maximum:
            raise ValueError()
        return value
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(400, f'{key} must be between {minimum} and {maximum}')

def target(data):
    if not isinstance(data.get('isSimulated', False), bool):
        raise HTTPException(400, 'isSimulated must be true or false')
    if not data.get('isSimulated') and not str(data.get('ip', '')).strip():
        raise HTTPException(400, 'Enter the controller IP address or hostname')
    return (str(data.get('ip', '')).strip(), number(data, 'port', 21010, 1, 65535),
            number(data, 'machineId', 0, 0, 255),
            number(data, 'timeoutMs', 5000, 100, 120000))

def simulated(group, machine_id):
    with _state_lock:
        state = copy.deepcopy(user_state())
    return dict(success=True, groupCode=group, rawBytes=list(frame(machine_id, payload(group, state))),
                sentBytes=list(tcp.read_request(machine_id, group)), rttMs=15, isSimulated=True)

@router.get('/health')
def health():
    return dict(status='ok', version='1.5', timestamp=datetime.now(timezone.utc).isoformat())

@router.get('/simulator/state')
def simulator_state():
    with _state_lock:
        return copy.deepcopy(user_state())

@router.post('/simulator/update')
def simulator_update(data: dict = Body(...)):
    updates = {}
    for key, value in data.items():
        if key not in DEFAULT_STATE:
            continue
        if key == 'alarms':
            if not isinstance(value, list) or len(value) != 17 or any(not isinstance(v, int) or not 0 <= v <= 255 for v in value):
                raise HTTPException(400, 'alarms must contain 17 bytes')
        elif key == 'lotName':
            if not isinstance(value, str):
                raise HTTPException(400, 'lotName must be text')
        elif not isinstance(value, (int, float)) or not math.isfinite(value):
            raise HTTPException(400, f'{key} must be a finite number')
        elif key in ('machineId', 'currentLength', 'totalCanLength', 'emptyCanLength', 'machineStatus', 'cylinderRpm', 'chutePressure'):
            lower, upper = (-32768, 32767) if key == 'chutePressure' else (0, 255 if key == 'machineId' else 65535)
            if value != int(value) or not lower <= value <= upper:
                raise HTTPException(400, f'{key} must be an integer between {lower} and {upper}')
            value = int(value)
        elif key != 'lotName' and key != 'alarms' and abs(value) > 3.4028234e38:
            raise HTTPException(400, f'{key} exceeds the PLC REAL range')
        updates[key] = value
    with _state_lock:
        user_state().update(updates)
        return dict(success=True, updatedState=copy.deepcopy(user_state()))

@router.post('/plc/read-multiple-groups')
def read_multiple(data: dict = Body(...)):
    if is_ybs(data) and data.get('isSimulated'):
        raise HTTPException(400, 'The data simulator uses SpinConnect frames. Use a YBS network target or offline received bytes.')
    groups = data.get('groupCodes')
    if not isinstance(groups, list) or not groups or len(groups) > 256:
        raise HTTPException(400, 'groupCodes must contain 1 to 256 group codes')
    groups = [number({'groupCode': g}, 'groupCode', 0, 0, 65535) for g in groups]
    groups = list(dict.fromkeys(g for g in groups if g != 11))
    if not groups:
        raise HTTPException(400, 'Select at least one data group; GC 11 is sent automatically at the end.')
    ip, port, machine_id, timeout = target(data)
    identity=start_inspect(dict(data,groupCodes=groups),data.get('_operation','read-multiple-groups'))
    started = time.monotonic()
    try:
        if data.get('isSimulated'):
            result = dict(results=[simulated(g, machine_id) for g in groups],
                          closeResult=dict(success=True, groupCode=11, sentBytes=list(tcp.read_request(machine_id, 11)),
                                           rawBytes=[], isSimulated=True, plcClosed=True, normalClose=True))
        else:
            result = tcp.sequence(ip, port, machine_id, groups, timeout, protocol='ybs' if is_ybs(data) else 'spinconnect')
            for item in result['results']:
                item['isSimulated'] = False
            if result['closeResult']:
                result['closeResult']['isSimulated'] = False
        return finish_inspect(identity,dict(result,totalDurationMs=round((time.monotonic()-started)*1000)))
    except Exception as error:
        finish_inspect(identity,{'results':[],'error':str(error)})
        raise

@router.post('/plc/read-group')
def read_group(data: dict = Body(...)):
    group = number(data, 'groupCode', -1, 0, 65535)
    if group == 11:
        raise HTTPException(400, 'Group 11 is the automatic close command')
    result = read_multiple(dict(data, groupCodes=[group],_operation=data.get('_operation','read-group')))
    item = result['results'][0] if result['results'] else dict(success=False, groupCode=group,
        rawBytes=[], sentBytes=[], rttMs=0, error=result.get('error'), isSimulated=False)
    return dict(item, closeResult=result.get('closeResult'), sessionDurationMs=result['totalDurationMs'],
                **{key:result[key] for key in ('testId','historyId','sessionId')})

@router.post('/plc/test-connection')
def test_connection(data: dict = Body(...)):
    result = read_group(dict(data, groupCode=10,_operation='test-connection'))
    version = None
    version_warning = None
    version_offset = number(data, 'programVersionOffset', 0, 0, 65531)
    raw = result['rawBytes']
    if result['success'] and is_ybs(data):
        from python_engine.ybs import parse_frame
        parsed = parse_frame(raw, number(data, 'machineId', 0, 0, 255), 10)
        if parsed['success'] and len(parsed['payload']) >= 4:
            version = int.from_bytes(parsed['payload'][:4], 'big') / 1000
        else:
            result.update(success=False, error=parsed['error'] or 'Missing YBS program version.')
    elif result['success']:
        checksum = 0
        for byte in raw[:-2]:
            checksum ^= byte
        expected_id = number(data, 'machineId', 0, 0, 255)
        issue = ('Invalid PLC response frame' if len(raw) < 7 or raw[0] != 3 or raw[-1] != 2
                 else 'PLC response Machine ID does not match the configured target' if raw[1] != expected_id
                 else 'PLC response checksum does not match' if checksum != raw[-2]
                 else f'PLC returned result code {raw[2]}' if raw[2] != 0 else '')
        if issue:
            result.update(success=False, error=issue)
    if result['success'] and not is_ybs(data):
        if int.from_bytes(bytes(raw[3:5]), 'big') >= version_offset + 4:
            start = 5 + version_offset
            version = struct.unpack('>f' if data.get('endianness') == 'big' else '<f', bytes(raw[start:start + 4]))[0]
            if not math.isfinite(version):
                version = None
                version_warning = 'Group 10 version is invalid; check the metadata offset and byte order.'
        else:
            version_warning = f'Group 10 responded, but no complete REAL program version exists at payload offset {version_offset}. Check the metadata mapping.'
    formatted = f'{version:.3f}' if version is not None else None
    result=dict(result, programVersion=version, programVersionStr=formatted, versionWarning=version_warning,
                message=(version_warning or f'Connected: Program Version v{formatted} verified on Group 10 (Machine ID: {data.get("machineId", 0)})') if result['success'] else result.get('error'))
    record=read_record(result['historyId'])
    previous=json.loads((RECORDS/record['id']/'result.json').read_text(encoding='utf-8'))
    finish_inspect({key:previous[key] for key in ('sessionId','historyId','testId','projectName','machineDepartment','plc','metadata','metadataSource','operation','groupCodes')},result)
    return result

@router.post('/plc/ping')
def ping_ip(data: dict = Body(...)):
    """Run one OS ICMP echo request; this does not open a PLC protocol connection."""
    raw_ip = data.get('ip')
    try:
        address = ipaddress.ip_address(str(raw_ip or '').strip())
    except ValueError as exc:
        raise HTTPException(400, 'Enter a valid IPv4 address to ping.') from exc
    if address.version != 4:
        raise HTTPException(400, 'Ping currently supports IPv4 addresses only.')
    if not (address.is_private or address.is_loopback or address.is_link_local):
        raise HTTPException(400, 'Ping is limited to private, loopback, or link-local addresses.')
    timeout_ms = number(data, 'timeoutMs', 2000, 100, 10000)
    if platform.system().lower() == 'windows':
        command = ['ping', '-n', '1', '-w', str(timeout_ms), str(address)]
    else:
        command = ['ping', '-n', '-c', '1', '-W', str(max(1, math.ceil(timeout_ms / 1000))), str(address)]
    started = time.monotonic()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_ms / 1000 + 2, check=False)
    except FileNotFoundError as exc:
        raise HTTPException(503, 'The system ping utility is not installed on this server.') from exc
    except subprocess.TimeoutExpired:
        return dict(success=False, ip=str(address), rttMs=None, message=f'Ping to {address} timed out.', protocolRequestSent=False)
    elapsed_ms = round((time.monotonic() - started) * 1000)
    success = completed.returncode == 0
    message = (f'{address} replied to ICMP ping.' if success else f'No ICMP ping reply from {address}.')
    return dict(success=success, ip=str(address), rttMs=elapsed_ms if success else None,
                message=message, protocolRequestSent=False)

@router.post('/history/{run_id}/decoded')
def save_decoded(run_id:str,data:dict=Body(...)):
    try:
        record=read_record(run_id)
    except (ValueError,OSError): raise HTTPException(404,'DataInspect run not found.')
    require_resource(RECORDS/run_id)
    if record['kind']!='datainspect': raise HTTPException(400,'This is not a DataInspect run.')
    groups=data.get('groupResponses')
    if not isinstance(groups,dict) or len(groups)>256: raise HTTPException(400,'Invalid decoded group results.')
    stored=json.loads((RECORDS/run_id/'result.json').read_text(encoding='utf-8'))
    transport=stored.get('results') or ([stored] if 'groupCode' in stored else [])
    expected={str(row['groupCode']):row.get('rawBytes',[]) for row in transport}
    if any(key not in expected or not isinstance(row,dict) or row.get('rawBytes',[])!=expected[key] for key,row in groups.items()):
        raise HTTPException(400,'Decoded results must refer to the bytes saved for this test.')
    stored.update(groupResponses=groups,dataModelCheck=data.get('dataModelCheck'),
                  dataModelReferenceSource=data.get('dataModelReferenceSource'),decoder='DataInspect browser decoder')
    stored['summary']={'totalGroups':len(groups),'passed':sum(bool(row.get('success') and row.get('lengthMatch')) for row in groups.values()),
                       'failed':sum(not row.get('success') and row.get('stage')!='not_sent' for row in groups.values()),
                       'mismatch':sum(bool(row.get('success') and not row.get('lengthMatch')) for row in groups.values()),
                       'skipped':sum(row.get('stage')=='not_sent' for row in groups.values()),
                       'failedParameters':sum(not value.get('isInRange',True) for row in groups.values() for value in row.get('parsedValues',[]))}
    record_run('datainspect',stored)
    return {'historyId':run_id,'testId':stored['testId'],'status':'saved'}

@router.post('/history/manual')
def save_manual(data:dict=Body(...)):
    groups=data.get('groupResponses')
    if not isinstance(groups,dict) or not groups or len(groups)>256 or any(not isinstance(row,dict) for row in groups.values()):
        raise HTTPException(400,'Supply decoded manual group data.')
    for key,row in groups.items():
        if not str(key).isdigit() or row.get('groupCode')!=int(key): raise HTTPException(400,'Manual group codes must match their result keys.')
        raw=row.get('rawBytes')
        if not isinstance(raw,list) or len(raw)>65542 or any(not isinstance(byte,int) or not 0<=byte<=255 for byte in raw):
            raise HTTPException(400,'Manual rawBytes must contain valid packet bytes.')
    plc=data.get('plc') or {}
    identity=start_inspect({**data,**{key:plc.get(key) for key in ('ip','port','machineId','timeoutMs','isSimulated','endianness')}},'manual-decode')
    result=finish_inspect(identity,{'groupResponses':groups,'source':'manual','results':list(groups.values())})
    return {'historyId':result['historyId'],'testId':result['testId'],'sessionId':result['sessionId']}

@router.post('/plc/send-raw')
def send_raw(data: dict = Body(...)):
    raw = data.get('rawBytes')
    if not isinstance(raw, list) or not raw or len(raw) > 65542:
        raise HTTPException(400, 'rawBytes must be a nonempty byte array')
    try:
        request = bytes(int(b) & 255 for b in raw)
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(400, 'rawBytes must contain numbers')
    if not is_ybs(data) and request[0]==241:
        raise HTTPException(400, 'Select Server to YBS before sending an F1 request frame.')
    if is_ybs(data):
        from python_engine.ybs import parse_frame
        if data.get('isSimulated'): raise HTTPException(400, 'YBS is not supported by the SpinConnect simulator.')
        parsed = parse_frame(request)
        if not parsed['success']: raise HTTPException(400, parsed['error'])
    ip, port, machine_id, timeout = target(data)
    group = (request[5] << 8 | request[6]) if len(request) >= 7 else 10
    identity=start_inspect(dict(data,groupCode=group),'send-raw')
    try:
        if data.get('isSimulated'):
            result = simulated(group, request[1] if len(request)>1 else machine_id)
            result['sentBytes'] = list(request)
        else:
            result = dict(tcp.raw_exchange(ip, port, request, timeout), isSimulated=False)
        result=dict(result, groupCode=group, message='Frame sent successfully.' if result['success'] else result.get('error'))
        return finish_inspect(identity,result)
    except Exception as error:
        finish_inspect(identity,{'results':[],'error':str(error)})
        raise

@router.post('/plc/send-rtc')
def send_rtc(data: dict = Body(...)):
    if is_ybs(data): raise HTTPException(400, 'YBS RTC writes require its device specification. SpinConnect RTC frames are not sent to YBS.')
    text = data.get('asciiPayload')
    if not isinstance(text, str) or not text or len(text) > 65535 or not text.isascii():
        raise HTTPException(400, 'asciiPayload must be nonempty ASCII text')
    ip, port, machine_id, timeout = target(data)
    layout = data.get('rtcLayout', 'spinconnect')
    if layout not in ('spinconnect', 'legacy'):
        raise HTTPException(400, 'rtcLayout must be spinconnect or legacy')
    function = number(data, 'functionCode', 1 if layout == 'spinconnect' else 2, 1, 4)
    group = number(data, 'groupCode', 10, 0, 65535)
    if layout == 'spinconnect':
        if group == 11:
            raise HTTPException(400, 'GC 11 is reserved for session closure, not RTC transmission')
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', text):
                raise ValueError()
            datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            raise HTTPException(400, 'SpinConnect RTC requires a valid YYYY-MM-DD HH:MM:SS timestamp (19 ASCII bytes at indices 9..27)')
        body = group.to_bytes(2, 'big') + b'\x00\x00' + text.encode('ascii')
    else:
        body = text.encode('ascii')
    request = frame(machine_id, body, function)
    identity=start_inspect(dict(data,groupCode=group),'send-rtc')
    try:
        if data.get('isSimulated'):
            result = dict(success=True, rawBytes=list(frame(machine_id)), sentBytes=list(request), rttMs=20, isSimulated=True,
                          closeResult=dict(sentBytes=list(tcp.read_request(machine_id, 11)), plcClosed=True, isSimulated=True))
        else:
            result = dict(tcp.raw_exchange(ip, port, request, timeout, close_session=True), isSimulated=False)
        code = result['rawBytes'][2] if len(result['rawBytes']) >= 7 else None
        if result['success'] and code != 0:
            result.update(success=False, error={10:'Invalid ETX',11:'Checksum error',12:'Invalid function',13:'Incomplete frame',14:'Invalid group'}.get(code, f'PLC result code {code}'))
        message = ('Simulated RTC exchange; no physical PLC clock was changed.' if data.get('isSimulated')
                   else f'RTC timestamp ({text}) sent; PLC response received. Clock application is not confirmed. Read PLC RTC and check its update conditions.')
        result=dict(result, resultCode=code, functionCode=function, asciiPayload=text, rtcLayout=layout,
                    groupCode=group if layout == 'spinconnect' else None, timestampOffset=9 if layout == 'spinconnect' else 5,
                    clockApplied=None, message=message if result['success'] else result.get('error'))
        return finish_inspect(identity,result)
    except Exception as error:
        finish_inspect(identity,{'results':[],'error':str(error)})
        raise
