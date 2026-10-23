"""YBS F1/F0 read frames and the supplied sequential metadata dialect.

Widths and checksum are evidenced by the supplied captures. Offsets are derived
from worksheet order; mismatched groups remain mismatched, never auto-repaired.
"""
import math
import struct

WIRE_TYPES = {'UCHAR': ('USINT', 1, 'B'), 'USINT': ('UINT', 2, 'H'),
              'UINT': ('UDINT', 4, 'I'), 'FLOAT': ('REAL', 4, 'f')}


def checksum(data):
    result = 255
    for value in data:
        result ^= value
    return result


def byte_text(value):
    return 'Unavailable' if value is None else f'{value} (0x{value:02X})'


def request(machine_id, group):
    if type(machine_id) is not int or not 0 <= machine_id <= 255 or type(group) is not int or not 0 <= group <= 65535:
        raise ValueError('Invalid YBS machine ID or group code.')
    raw = bytes([241, machine_id, 1, 0, 9]) + group.to_bytes(2, 'big')
    return raw + bytes([checksum(raw), 240])


def parse_frame(raw, machine_id=None, group=None):
    raw = bytes(raw)
    length = int.from_bytes(raw[3:5], 'big') if len(raw) >= 5 else 0
    received_group = int.from_bytes(raw[5:7], 'big') if len(raw) >= 7 else None
    errors = []
    if len(raw) < 9: errors.append('YBS frame needs at least 9 bytes.')
    if not raw or raw[0] != 241: errors.append('YBS start marker must be F1.')
    if len(raw) != length: errors.append(f'YBS total length {len(raw)} differs from header {length}.')
    if not raw or raw[-1] != 240:
        errors.append(f'YBS end marker F0 is missing at byte {len(raw)-1}: expected {byte_text(240)}, received {byte_text(raw[-1] if raw else None)}.')
    if len(raw) >= 2 and checksum(raw[:-2]) != raw[-2]:
        errors.append(f'YBS checksum mismatch at byte {len(raw)-2}: expected {byte_text(checksum(raw[:-2]))}, received {byte_text(raw[-2])} (XOR seed FF).')
    if len(raw) >= 3 and raw[2] != 1: errors.append(f'Unsupported YBS function {raw[2]}.')
    if machine_id is not None and (len(raw) < 2 or raw[1] != machine_id): errors.append('YBS machine ID mismatch.')
    if group is not None and received_group != group: errors.append(f'YBS embedded GC {received_group} differs from requested GC {group}.')
    return {'success': not errors, 'error': ' '.join(errors) or None, 'errors': errors,
            'groupCode': received_group, 'dataLength': max(0, length-9), 'frameLength': length,
            'payload': raw[7:-2] if not errors else b'', 'resultCode': 0 if not errors else -1}


def frame_findings(raw, machine_id=None, group=None, metadata_bytes=None):
    """Explain observed frame faults; possible causes never substitute for byte checks."""
    raw=bytes(raw)
    parsed=parse_frame(raw,machine_id,group)
    checks=[]
    def check(name, expected, actual, passed, offset=None):
        checks.append(dict(name=name,expected=str(expected),actual=str(actual),passed=passed,offset=offset))
    check('Captured frame length',f'{parsed["frameLength"]} bytes from header',f'{len(raw)} bytes',len(raw)>=9 and parsed['frameLength']==len(raw))
    check('Start marker',byte_text(241),byte_text(raw[0] if raw else None),bool(raw) and raw[0]==241,0)
    check('Function','1 (read)',raw[2] if len(raw)>2 else 'Unavailable',len(raw)>2 and raw[2]==1,2)
    if machine_id is not None:
        check('Machine ID',machine_id,raw[1] if len(raw)>1 else 'Unavailable',len(raw)>1 and raw[1]==machine_id,1)
    if group is not None:
        check('Embedded group code',group,parsed['groupCode'],parsed['groupCode']==group,5)
    calculated=checksum(raw[:-2]) if len(raw)>=9 else None
    check('Checksum (XOR seed FF)',byte_text(calculated),byte_text(raw[-2] if len(raw)>=2 else None),len(raw)>=9 and raw[-2]==calculated,len(raw)-2)
    check('End marker',byte_text(240),byte_text(raw[-1] if raw else None),bool(raw) and raw[-1]==240,len(raw)-1)
    note=None
    if len(raw)>=9 and raw[-1]!=240 and checksum(raw[:-1])==raw[-1]:
        note=('The last byte matches the XOR checksum over the preceding bytes, but occupies the F0 end-marker position. '
              'A trailer index or send/read length error is possible; the capture alone cannot confirm its source.')
    actions=[] if parsed['success'] else [
        'Embedded C: verify checksum at frame[length - 2], F0 at frame[length - 1], and transmit exactly the advertised frame length.',
        *([f'Check the C payload size and any struct padding: this header declares {parsed["frameLength"]} bytes = 7 header + {parsed["dataLength"]} data + 2 trailer bytes.'] if parsed['frameLength']>=9 else []),
        'Go socket receiver: accumulate the advertised total length across TCP reads before checksum validation; log the complete raw frame.',
        'Compare GC-specific bytes before device send and after server receive. If transmit bytes are wrong, inspect C frame construction; if transmit is correct, inspect receiver framing and logging.',
    ]
    return dict(success=parsed['success'],groupCode=parsed['groupCode'],frameLength=parsed['frameLength'],capturedBytes=len(raw),
                dataLength=parsed['dataLength'],metadataBytes=metadata_bytes,checks=checks,error=parsed['error'],
                trailerNote=note,nextActions=actions,tail=list(raw[-8:]))


def metadata_rows(rows, sheet='Sheet1'):
    rows = iter(rows)
    header = [str(v or '').strip().casefold() for v in next(rows)]
    required = ['parameter', 'tag_data_type', 'group code', 'divison factor', 'multiplication factor']
    if any(name not in header for name in required):
        raise ValueError('Not a YBS sequential metadata worksheet.')
    indexes = {name: header.index(name) for name in required}
    clean = lambda value: '' if value is None or str(value).strip().casefold() == '<null>' else str(value).strip()
    def numeric(value, default=None):
        text = clean(value)
        if not text: return default
        number = float(text)
        if not math.isfinite(number): raise ValueError('YBS factors/limits must be finite numbers.')
        return number
    offsets, result = {}, []
    for row_number, cells in enumerate(rows, 2):
        if not any(clean(v) for v in cells): continue
        row = dict(zip(header, cells))
        wire = clean(row['tag_data_type']).upper()
        if wire not in WIRE_TYPES: raise ValueError(f'YBS {sheet}:{row_number}: unsupported type {wire}.')
        group_value = numeric(row['group code'])
        if group_value is None or not group_value.is_integer() or not 0 <= group_value <= 65535:
            raise ValueError(f'YBS {sheet}:{row_number}: invalid group code.')
        group = int(group_value)
        divide, multiply = numeric(row['divison factor'], 1), numeric(row['multiplication factor'], 1)
        if divide <= 0: raise ValueError(f'YBS {sheet}:{row_number}: division factor must be positive.')
        canonical, width, _ = WIRE_TYPES[wire]
        bits = [{'bit': bit, 'label': clean(row.get(f'bit: {bit}'))} for bit in range(width*8) if clean(row.get(f'bit: {bit}'))]
        item = {'sNo': row_number-1, 'tagCode': row_number-1, 'screenName': clean(row.get('screenname')), 'machineVariants': 'YBS',
                'parameter': clean(row['parameter']), 'units': clean(row.get('units')), 'min': numeric(row.get('min')), 'max': numeric(row.get('max')),
                'groupCode': group, 'offset': offsets.get(group, 0), 'dataType': canonical, 'wireDataType': wire,
                'protocol': 'ybs', 'divideFactor': divide, 'multiplyFactor': multiply, 'offsetFactor': 1, 'scaleFactor': 1,
                'isVisible': clean(row.get('is_visible')).casefold() == 'yes', 'isWritable': clean(row.get('is_writable')).casefold() == 'yes',
                'isShownValueDifferent': clean(row.get('is shown value is different')).casefold() == 'yes', 'bitDefinitions': bits,
                'fromVersion': '', 'toVersion': '', 'sourceRow': row_number, 'sourceSheet': sheet, 'layoutInferred': True}
        if not item['parameter']: raise ValueError(f'YBS {sheet}:{row_number}: missing parameter name.')
        offsets[group] = item['offset'] + width
        result.append(item)
    return result


def decode_values(payload, items):
    formats = {'USINT': ('B', 1), 'UINT': ('H', 2), 'UDINT': ('I', 4), 'REAL': ('f', 4)}
    result = []
    for item in items:
        kind, width = formats[item['dataType']]
        offset = item['offset']
        raw = actual = None
        issue = None
        if offset + width > len(payload):
            issue = f'Field ends at payload byte {offset+width}; received {len(payload)}.'
        else:
            raw = struct.unpack_from('>'+kind, payload, offset)[0]
            actual = raw / item['divideFactor'] * item['multiplyFactor']
            if not math.isfinite(raw) or not math.isfinite(actual):
                issue = 'Nonfinite YBS value.'; raw = actual = None
            elif (item['min'] is not None and actual < item['min']) or (item['max'] is not None and actual > item['max']):
                issue = 'Actual value is outside the metadata limits.'
        active = [f'Bit {entry["bit"]}: {entry["label"]}' for entry in item.get('bitDefinitions', []) if isinstance(raw, int) and raw & (1 << entry['bit'])]
        result.append({**item, 'rawValue': raw, 'actualValue': actual, 'rawHex': payload[offset:offset+width].hex(' '),
                       'formattedValue': 'Unavailable' if actual is None else str(round(actual, 6)), 'qualityIssue': issue, 'isInRange': issue is None,
                       'dropdownText': ' | '.join(active) or None})
    return result
