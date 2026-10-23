"""Account-owned, opt-in PLC sampling. No controller writes and no browser dependency."""
import hashlib
import json
import logging
import math
import re
import struct
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from backend.core import persistent_store as storage, accounts, nami_transport as tcp
from backend.core.nami_profiles import frame_protocol
from backend.core.nami_simulator import DEFAULT_STATE, frame, payload

log = logging.getLogger('usopp.live')
_guard = threading.RLock()
_latest = {}
_busy = set()
_due = {}
_stop = threading.Event()
_thread = None
FORMATS = {'REAL': 'f', 'LREAL': 'd', 'DINT': 'i', 'UDINT': 'I', 'INT': 'h',
           'UINT': 'H', 'BYTE': 'B', 'USINT': 'B', 'SINT': 'b', 'BOOL': 'B'}


def initialize():
    with storage.db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS live_versions (user_id INTEGER PRIMARY KEY, revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS live_targets (
                user_id INTEGER NOT NULL, target_id TEXT NOT NULL, config TEXT NOT NULL,
                PRIMARY KEY(user_id,target_id));
            CREATE TABLE IF NOT EXISTS live_metadata (
                user_id INTEGER NOT NULL, target_id TEXT NOT NULL, hash TEXT NOT NULL, snapshot TEXT NOT NULL,
                PRIMARY KEY(user_id,target_id,hash));
            CREATE TABLE IF NOT EXISTS live_samples (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, target_id TEXT NOT NULL,
                captured_at REAL NOT NULL, expires_at REAL NOT NULL, metadata_hash TEXT NOT NULL, result TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS live_sample_time ON live_samples(user_id,target_id,captured_at);
            CREATE INDEX IF NOT EXISTS live_sample_expiry ON live_samples(expires_at);
        ''')
        # Retire the old fixed-layout internal simulator without starting a socket.
        for row in db.execute("SELECT user_id,target_id,config FROM live_targets WHERE json_extract(config,'$.plc.isSimulated')=1").fetchall():
            old=json.loads(row['config']);old['plc'].update(isSimulated=False,targetMode='data-simulator',ip='127.0.0.1',liveEnabled=False,storeLiveData=False)
            updated=validate_config(old)
            db.execute('UPDATE live_targets SET config=? WHERE user_id=? AND target_id=?',(json.dumps(updated),row['user_id'],row['target_id']))
            db.execute('INSERT OR IGNORE INTO live_metadata VALUES (?,?,?,?)',(row['user_id'],row['target_id'],updated['hash'],json.dumps(updated)))
            db.execute('UPDATE live_versions SET revision=revision+1 WHERE user_id=?',(row['user_id'],))


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer from {low} to {high}.')
    return value


def metadata_width(item):
    match = re.fullmatch(r'([A-Z]+)(?:\[(\d+)\])?', item['dataType'].upper())
    kind, declared = match.groups() if match else ('', None)
    count = item.get('arraySize') or int(declared or 1)
    return (count if item.get('arraySize') or declared else 50) if kind == 'STRING' else struct.calcsize(FORMATS.get(kind, 'B')) * count


def validate_config(item):
    if not isinstance(item, dict) or not isinstance(item.get('plc'), dict):
        raise ValueError('Supply a PLC configuration for each live target.')
    plc = item['plc']
    target_id = plc.get('id')
    if not isinstance(target_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', target_id):
        raise ValueError('Invalid target ID.')
    for key in ('liveEnabled', 'storeLiveData', 'isSimulated'):
        if type(plc.get(key, False)) is not bool:
            raise ValueError(f'{key} must be true or false.')
    safe = {key: str(plc.get(key) or '')[:200] for key in ('id', 'name', 'machineType', 'ip')}
    safe.update(port=integer(plc.get('port'), 'Port', 1, 65535),
                machineId=integer(plc.get('machineId'), 'Machine ID', 0, 255),
                timeoutMs=integer(plc.get('timeoutMs', 5000), 'Timeout', 100, 30000 if plc.get('liveEnabled') else 120000),
                liveIntervalSeconds=integer(plc.get('liveIntervalSeconds', 10), 'Sample interval', 5, 3600),
                retentionDays=integer(plc.get('retentionDays', 30), 'Retention', 1, 30),
                liveEnabled=plc.get('liveEnabled', False), storeLiveData=plc.get('storeLiveData', False),
                isSimulated=plc.get('isSimulated', False), endianness=plc.get('endianness', 'little'))
    safe['targetMode']=plc.get('targetMode','plc')
    if safe['targetMode'] not in ('plc','automation-studio','data-simulator'):
        raise ValueError('Choose a supported target mode.')
    if safe['endianness'] not in ('little', 'big') or not safe['name'].strip() or (not safe['isSimulated'] and not safe['ip'].strip()):
        raise ValueError('Each target needs a name, address and valid byte order.')
    safe['frameProtocol']=frame_protocol(plc)
    if safe['frameProtocol']=='ybs':
        safe['endianness']='big'
        if safe['isSimulated'] or safe['targetMode']=='data-simulator':raise ValueError('Use a network YBS target; its simulator profile is not installed.')
    rows = item.get('metadata', [])
    if not isinstance(rows, list) or len(rows) > 30000:
        raise ValueError('Live metadata supports at most 30,000 rows per target.')
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('parameter'), str) or len(row['parameter']) > 500:
            raise ValueError('Invalid live metadata parameter.')
        integer(row.get('groupCode'), 'Metadata group code', 0, 65535)
        integer(row.get('tagCode'), 'Metadata tag code', 0, 65535)
        integer(row.get('offset'), 'Metadata offset', 0, 65534)
        if not isinstance(row.get('dataType'), str) or not re.fullmatch(r'[A-Za-z]+(?:\[\d{1,5}\])?', row['dataType']):
            raise ValueError('Invalid live metadata datatype.')
        if (row.get('protocol')=='ybs') != (safe['frameProtocol']=='ybs'):
            raise ValueError('YBS targets require YBS metadata; SpinConnect targets require SpinConnect metadata.')
        if safe['frameProtocol']=='ybs':
            if row['dataType'] not in ('USINT','UINT','UDINT','REAL'):
                raise ValueError('Unsupported YBS canonical datatype.')
            for factor in ('divideFactor','multiplyFactor'):
                value=row.get(factor)
                if type(value) not in (int,float) or not math.isfinite(value) or factor=='divideFactor' and value<=0:
                    raise ValueError('Invalid YBS division or multiplication factor.')
        if row.get('arraySize') is not None:
            integer(row['arraySize'], 'Array size', 1, 65535)
        if row['offset'] + metadata_width(row) > 65535:
            raise ValueError('Live metadata exceeds the PLC payload size.')
    groups = plc.get('liveGroupCodes', [])
    if not isinstance(groups, list) or len(groups) > 32:
        raise ValueError('Select at most 32 live group codes.')
    groups = list(dict.fromkeys(integer(g, 'Group code', 0, 65535) for g in groups))
    if 11 in groups:
        raise ValueError('GC 11 is sent automatically to close each collection cycle.')
    available = {row['groupCode'] for row in rows}
    if safe['liveEnabled'] and (not groups or any(g not in available for g in groups)):
        raise ValueError('Select live group codes present in this target\'s metadata.')
    safe['liveGroupCodes'] = groups
    snapshot = {'plc': safe, 'metadata': rows}
    encoded = json.dumps(snapshot, sort_keys=True, allow_nan=False, separators=(',', ':'))
    if len(encoded.encode()) > (16 if safe['frameProtocol']=='ybs' else 4) * 1024 * 1024:
        raise ValueError('Live target metadata exceeds its size limit.')
    # Include physical identity so replacing a machine never reuses its old latest values.
    snapshot['hash'] = hashlib.sha256(encoded.encode()).hexdigest()
    return snapshot


def configurations(user_id):
    with storage.db() as db:
        rows = db.execute('SELECT config FROM live_targets WHERE user_id=?', (user_id,)).fetchall()
        revision = db.execute('SELECT revision FROM live_versions WHERE user_id=?', (user_id,)).fetchone()
    return [json.loads(row[0]) for row in rows], revision[0] if revision else 0


def remove_user(user_id):
    initialize()
    with _guard, storage.db() as db:
        for table in ('live_targets', 'live_metadata', 'live_samples', 'live_versions'):
            db.execute(f'DELETE FROM {table} WHERE user_id=?', (user_id,))
        for key in list(_latest):
            if key[0] == user_id: _latest.pop(key, None)


def replace_configurations(user_id, items, revision):
    if not isinstance(items, list) or len(items) > 16:
        raise ValueError('Configure at most 16 live targets per account.')
    configs = [validate_config(item) for item in items]
    if len({item['plc']['id'] for item in configs}) != len(configs):
        raise ValueError('Target IDs must be unique.')
    with _guard, storage.db() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT revision FROM live_versions WHERE user_id=?', (user_id,)).fetchone()
        if revision != (current[0] if current else 0):
            raise storage.SettingsConflict('Live targets changed in another window. Reload DataInspect before saving.')
        db.execute('DELETE FROM live_targets WHERE user_id=?', (user_id,))
        for config in configs:
            target_id = config['plc']['id']
            db.execute('INSERT INTO live_targets VALUES (?,?,?)', (user_id, target_id, json.dumps(config, allow_nan=False)))
            db.execute('INSERT OR IGNORE INTO live_metadata VALUES (?,?,?,?)',
                       (user_id, target_id, config['hash'], json.dumps(config, allow_nan=False)))
            db.execute('UPDATE live_samples SET expires_at=MIN(expires_at,captured_at+?) WHERE user_id=? AND target_id=?',
                       (config['plc']['retentionDays'] * 86400, user_id, target_id))
        db.execute('INSERT OR REPLACE INTO live_versions VALUES (?,?)', (user_id, revision + 1))
        for key in list(_latest):
            if key[0] == user_id:
                _latest.pop(key, None)
                _due.pop(key, None)
    purge()
    return revision + 1


def decode_cycle(config, transport):
    """Decode scalar numbers exactly at payload-relative metadata offsets; retain failed groups."""
    plc = config['plc']
    groups = {}
    for response in transport['results']:
        group = response['groupCode']
        rows = [r for r in config['metadata'] if r['groupCode'] == group]
        raw = bytes(response.get('rawBytes') or [])
        length = int.from_bytes(raw[3:5], 'big') if len(raw) >= 7 else 0
        is_ybs = frame_protocol(plc) == 'ybs'
        checksum = 0
        for byte in raw[:-2]: checksum ^= byte
        valid = (response.get('success') and len(raw) == length + 7 and raw[0] == 3 and
                 raw[-1] == 2 and raw[1] == plc['machineId'] and checksum == raw[-2] and raw[2] == 0)
        if is_ybs:
            from python_engine.ybs import parse_frame
            parsed = parse_frame(raw, plc['machineId'], group)
            valid = bool(response.get('success') and parsed['success'])
            length = parsed['dataLength']
        expected = max((r['offset'] + metadata_width(r) for r in rows), default=0)
        values = []
        if valid and is_ybs:
            from python_engine.ybs import decode_values
            values = decode_values(parsed['payload'], rows)
        elif valid:
            for item in rows:
                kind = item['dataType'].upper()
                if kind not in FORMATS or (item.get('arraySize') or 1) > 1:
                    continue
                size = struct.calcsize(FORMATS[kind])
                value, issue = None, ''
                if item['offset'] + size > length:
                    issue = 'Parameter exceeds the received payload.'
                else:
                    value = struct.unpack_from(('<' if plc['endianness'] == 'little' else '>') + FORMATS[kind], raw, 5 + item['offset'])[0]
                    if kind == 'BOOL': value = bool(value)
                    if not math.isfinite(value): value, issue = None, 'Nonfinite PLC value.'
                    elif abs(value) >= 1e21: issue = 'Positive-exponent scientific value. Check datatype, byte order, offset and scale factor.'
                values.append({**{k: item.get(k) for k in ('tagCode', 'parameter', 'screenName', 'groupCode', 'offset', 'dataType', 'units', 'min', 'max', 'scaleFactor', 'offsetFactor')},
                               'rawValue': value, 'formattedValue': str(value), 'rawHex': '',
                               'isInRange': not bool(issue), 'qualityIssue': issue or None})
        groups[str(group)] = dict(groupCode=group, success=bool(valid), resultCode=(0 if valid else -1) if is_ybs else raw[2] if len(raw)>2 else -1,
            dataLength=length, expectedLength=expected, lengthMatch=length == expected if is_ybs else length >= expected, parsedValues=values,
            rawBytes=[], rawHex='', rttMs=response.get('rttMs', 0), timestamp='',
            completedAt=response.get('completedAt', time.time()*1000), source='plc', stage=response.get('stage'),
            error=response.get('error') or (None if valid else 'No valid PLC frame received.'))
    error = transport.get('error') or next((group.get('error') for group in groups.values() if not group['success']), None)
    return {'groups': groups, 'error': error, 'simulated': plc['isSimulated']}


def collect(user_id, config):
    key = user_id, config['plc']['id']
    try:
        plc = config['plc']
        if plc['isSimulated']:
            results = [dict(success=True, groupCode=g, rawBytes=list(frame(plc['machineId'], payload(g, DEFAULT_STATE))),
                            completedAt=time.time()*1000) for g in plc['liveGroupCodes']]
            transport = {'results': results}
        else:
            transport = tcp.sequence(plc['ip'], plc['port'], plc['machineId'], plc['liveGroupCodes'], plc['timeoutMs'], stop_event=_stop, max_duration=60, protocol='ybs' if frame_protocol(plc)=='ybs' else 'spinconnect')
        result = decode_cycle(config, transport)
        captured = time.time()
        sample = dict(result, capturedAt=captured*1000, metadataHash=config['hash'])
        with _guard, storage.db() as db:
            current = db.execute('SELECT config FROM live_targets WHERE user_id=? AND target_id=?', key).fetchone()
            if not current or json.loads(current[0])['hash'] != config['hash']:
                return  # A disabled/reconfigured target cannot write a late capture.
            _latest[key] = sample
            if plc['storeLiveData']:
                db.execute('INSERT INTO live_samples(user_id,target_id,captured_at,expires_at,metadata_hash,result) VALUES (?,?,?,?,?,?)',
                    (*key, captured, captured + plc['retentionDays']*86400, config['hash'], zlib.compress(json.dumps(sample, allow_nan=False).encode(), 3)))
    except Exception:
        log.exception('Live collection failed for account %s target %s', *key)
        with _guard, storage.db() as db:
            current=db.execute('SELECT config FROM live_targets WHERE user_id=? AND target_id=?',key).fetchone()
            if current and json.loads(current[0])['hash']==config['hash']:
                _latest[key] = {'capturedAt': time.time()*1000, 'metadataHash': config['hash'], 'groups': {}, 'error': 'Collection failed. See the server log.'}
    finally:
        with _guard, storage.db() as db:
            _busy.discard(key)
            current=db.execute('SELECT config FROM live_targets WHERE user_id=? AND target_id=?',key).fetchone()
            if current and json.loads(current[0])['hash']==config['hash']:
                _due[key] = time.monotonic() + config['plc']['liveIntervalSeconds']
            else:_due.pop(key,None)


def purge():
    with storage.db() as db:
        db.execute('DELETE FROM live_samples WHERE expires_at<=? OR captured_at<?', (time.time(), time.time()-30*86400))
        db.execute('''DELETE FROM live_metadata WHERE NOT EXISTS
            (SELECT 1 FROM live_samples s WHERE s.user_id=live_metadata.user_id AND s.target_id=live_metadata.target_id AND s.metadata_hash=live_metadata.hash)
            AND NOT EXISTS (SELECT 1 FROM live_targets t WHERE t.user_id=live_metadata.user_id AND t.target_id=live_metadata.target_id AND json_extract(t.config,'$.hash')=live_metadata.hash)''')


def scheduler():
    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='plc-sample')
    last_purge = 0
    try:
        while not _stop.wait(1):
            try:
                eligible = {u['id'] for u in accounts.store.list_users() if u.get('active') and u.get('approved') and not u.get('isDemo')}
                with storage.db() as db:
                    rows = db.execute('SELECT user_id,config FROM live_targets').fetchall()
                for row in rows:
                    config = json.loads(row['config']); key = row['user_id'], config['plc']['id']
                    if row['user_id'] not in eligible or not config['plc']['liveEnabled']:
                        with _guard: _latest.pop(key, None)
                        continue
                    with _guard:
                        if key in _busy or len(_busy) >= 8 or _due.get(key, 0) > time.monotonic(): continue
                        _busy.add(key)
                    pool.submit(collect, row['user_id'], config)
                if time.monotonic()-last_purge > 60:
                    purge(); last_purge = time.monotonic()
            except Exception: log.exception('Live collection scheduler error')
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def start():
    global _thread
    initialize()
    if _thread and _thread.is_alive(): return
    _stop.clear()
    _thread = threading.Thread(target=scheduler, name='plc-collector', daemon=True)
    _thread.start()


def shutdown():
    _stop.set()
    if _thread: _thread.join(timeout=2)


def overview(user_id):
    configs, revision = configurations(user_id)
    with _guard:
        targets = [dict(plc=c['plc'], metadataRows=len(c['metadata']),
            lastCapturedAt=(_latest.get((user_id,c['plc']['id'])) or {}).get('capturedAt'),
            error=(_latest.get((user_id,c['plc']['id'])) or {}).get('error'),
            collecting=(user_id,c['plc']['id']) in _busy) for c in configs]
    return {'accountId': user_id, 'revision': revision, 'targets': targets}


def latest(user_id, target_id):
    configs, _ = configurations(user_id)
    config = next((c for c in configs if c['plc']['id'] == target_id), None)
    if config is None: raise KeyError(target_id)
    with _guard: sample = _latest.get((user_id, target_id))
    if sample and sample['metadataHash'] != config['hash']: sample = None
    return {'plc': config['plc'], 'metadata': config['metadata'], 'sample': sample}


def history(user_id, target_id, start_ms, end_ms, limit=300):
    if not math.isfinite(start_ms) or not math.isfinite(end_ms) or not 0 < end_ms-start_ms <= 30*86400000:
        raise ValueError('Choose a report period of up to 30 days.')
    low, high = max(start_ms/1000, time.time()-30*86400), min(end_ms/1000, time.time())
    with storage.db() as db:
        conditions = (user_id, target_id, low, high, time.time())
        count = db.execute('SELECT COUNT(*) FROM live_samples WHERE user_id=? AND target_id=? AND captured_at BETWEEN ? AND ? AND expires_at>?', conditions).fetchone()[0]
        # Bound large metadata reports by reading count as well as capture count.
        largest = db.execute('''SELECT MAX(json_array_length(snapshot,'$.metadata')) FROM live_metadata
            WHERE user_id=? AND target_id=?''', (user_id,target_id)).fetchone()[0] or 1
        limit = min(limit, max(2, 30000 // largest))
        if count <= limit:
            rows = db.execute('''SELECT result,metadata_hash FROM live_samples WHERE user_id=? AND target_id=?
                AND captured_at BETWEEN ? AND ? AND expires_at>? ORDER BY captured_at,id''', conditions).fetchall()
        else:
            first,last = db.execute('''SELECT MIN(captured_at),MAX(captured_at) FROM live_samples
                WHERE user_id=? AND target_id=? AND captured_at BETWEEN ? AND ? AND expires_at>?''',conditions).fetchone()
            bucket = max((last-first)/limit, .001)
            rows = db.execute('''SELECT result,metadata_hash FROM live_samples WHERE id IN
                (SELECT MAX(id) FROM live_samples WHERE user_id=? AND target_id=? AND captured_at BETWEEN ? AND ? AND expires_at>?
                 GROUP BY MIN(?,CAST((captured_at-?)/? AS INTEGER))) ORDER BY captured_at,id LIMIT ?''',
                (*conditions, limit-1, first, bucket, limit)).fetchall()
        hashes = list({row['metadata_hash'] for row in rows})
        snapshots = {row['hash']: json.loads(row['snapshot']) for row in db.execute(
            'SELECT hash,snapshot FROM live_metadata WHERE user_id=? AND target_id=? AND hash IN ('+','.join('?' for _ in hashes)+')',
            (user_id, target_id, *hashes))} if hashes else {}
    return {'samples': [json.loads(zlib.decompress(row['result']) if isinstance(row['result'],bytes) else row['result']) for row in rows], 'snapshots': snapshots, 'totalSamples': count,
            'returnedSamples': len(rows), 'sampled': count>len(rows), 'start': low*1000, 'end': high*1000}
