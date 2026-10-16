"""Metadata-driven synthetic textile data, served through the PLC TCP protocol."""
import json
import math
import re
import socketserver
import struct
import threading
import time
from datetime import datetime
from backend.core import persistent_store as storage, accounts
from backend.core.live_collection import validate_config, metadata_width, FORMATS
from backend.core.nami_simulator import frame

LOCK = threading.RLock()
SERVERS = {}
# Illustrative values only. Operators can override every source parameter.
DEPARTMENTS = {
    'Carding': (285, .128, 90, 12), 'Finisher': (500, .12, 7, 10),
    'Breaker': (400, .12, 6, 10), 'Comber': (300, .15, 90, 14),
    'Lapformer': (120, .15, 2, 9), 'Ring Frame': (18, 40, 35, 25),
    'Speed Frame': (30, 1.2, 10, 15), 'Blow Room': (450, .12, 2, 30),
    'Auto Winder': (1100, 40, 1, 8), 'RAP': (200, .12, 6, 12),
    'Custom': (100, 1, 5, 10),
}


def initialize():
    with storage.db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS data_simulators
            (user_id INTEGER NOT NULL,target_id TEXT NOT NULL,config TEXT NOT NULL,PRIMARY KEY(user_id,target_id))''')


def key(row): return f"{row['groupCode']}:{row['tagCode']}"


def words(value):
    return re.sub(r'[^a-z0-9]+', ' ', re.sub(r'([a-z])([A-Z])', r'\1 \2', str(value)).lower()).strip()


def validate(data):
    target = validate_config({'plc': {**data.get('plc', {}), 'liveEnabled': False, 'isSimulated': False}, 'metadata': data.get('metadata')})
    plc = target['plc']
    if plc['ip'] not in ('127.0.0.1', 'localhost'):
        raise ValueError('The data simulator listens on 127.0.0.1 on the uSOPp server. Use this address for this target.')
    if not 1024 <= plc['port'] <= 65535:
        raise ValueError('Choose a simulator TCP port from 1024 to 65535.')
    rows = target['metadata']
    if not rows: raise ValueError('Upload or select metadata before starting the data simulator.')
    occupied, seen = {}, set()
    for row in rows:
        if key(row) in seen: raise ValueError(f'Duplicate metadata identity {key(row)}.')
        seen.add(key(row))
        if row['groupCode'] == 11: raise ValueError('GC 11 is reserved for closing a session.')
        kind = row['dataType'].upper().split('[')[0]
        if kind not in FORMATS and kind != 'STRING': raise ValueError(f'Unsupported simulator datatype {kind}.')
        end = row['offset'] + metadata_width(row)
        for start, previous_end in occupied.setdefault(row['groupCode'], []):
            if row['offset'] < previous_end and end > start:
                raise ValueError(f"Overlapping metadata bytes in GC {row['groupCode']} near Tag {row['tagCode']}. Resolve the layout before simulating.")
        occupied[row['groupCode']].append((row['offset'], end))
    settings = data.get('settings') or {}
    if not isinstance(settings, dict): raise ValueError('Invalid simulation settings.')
    cleaned = {}
    for name, default, low, high in [('timeScale', 1, .1, 120), ('cycleSeconds', 300, 30, 86400),
                                   ('startingRunSeconds', 3600, 0, 8640000), ('programVersion', 5.296, 0, 9999)]:
        value = settings.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{name} must be from {low} to {high}.')
        cleaned[name] = value
    if type(settings.get('autoStart', False)) is not bool: raise ValueError('autoStart must be true or false.')
    cleaned['autoStart'] = settings.get('autoStart', False)
    overrides = data.get('overrides') or {}
    if not isinstance(overrides, dict) or len(overrides) > 10000: raise ValueError('Invalid parameter overrides.')
    for identity, override in overrides.items():
        if identity not in seen or not isinstance(override, dict) or override.get('mode') not in ('auto', 'constant', 'wave', 'counter'):
            raise ValueError('An override must identify an available metadata parameter and a supported behavior.')
        for name in ('minimum', 'maximum', 'value', 'period'):
            value = override.get(name, 60 if name == 'period' else 0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value)>1e15:
                raise ValueError(f'Invalid override {name}.')
        if override.get('minimum', 0)>override.get('maximum', 0) or override.get('period', 60)<=0:
            raise ValueError('Override limits and period must be valid.')
    return {'plc': dict(plc, targetMode='data-simulator', isSimulated=False), 'metadata': rows,
            'metadataSource': str(data.get('metadataSource') or '')[:500], 'settings': cleaned, 'overrides': overrides}


class Generator:
    def __init__(self, config):
        self.config = config
        self.started = time.monotonic()
        self.clock_offset = 0
        self.groups = {}
        for row in config['metadata']: self.groups.setdefault(row['groupCode'], []).append(row)

    def reading(self, row, elapsed):
        name = words(row['parameter']); tokens = set(name.split())
        unit = words(row.get('units', '')); department = self.config['plc']['machineType']
        speed, hank, draft, power = DEPARTMENTS.get(department, DEPARTMENTS['Custom'])
        cycle = self.config['settings']['cycleSeconds']; duration = elapsed + self.config['settings']['startingRunSeconds']
        full = math.floor(duration/cycle); phase = duration % cycle; running = phase < cycle*.85
        run = full*cycle*.85 + min(phase, cycle*.85); stopped = duration-run
        wave = lambda mean, proportion=.025: mean*(1+proportion*math.sin(elapsed/8 + row['tagCode']*.47))
        override = self.config['overrides'].get(key(row), {})
        mode = override.get('mode', 'auto')
        if mode == 'constant': return override.get('value', 0), 'Constant override'
        if mode == 'wave':
            low, high = override.get('minimum', 0), override.get('maximum', 100)
            return low + (high-low)*(1+math.sin(elapsed/override.get('period', 60)*2*math.pi))/2, 'Wave override'
        if mode == 'counter':
            low, high = override.get('minimum', 0), override.get('maximum', 100)
            return min(high, low+elapsed/override.get('period',60)), 'Counter override'
        now = datetime.fromtimestamp(time.time()+self.clock_offset)
        if row['dataType'].upper().startswith('STRING'):
            if 'hms' in tokens or ('time' in tokens and 'lot' not in tokens):
                return f'{int(run)//3600:02}:{int(run)//60%60:02}:{int(run)%60:02}', 'Run time H:M:S'
            if tokens & {'date','clock','timestamp','rtc'}: return now.strftime('%Y-%m-%d %H:%M:%S'), 'Synthetic calendar / RTC text'
            return f'{department.upper().replace(" ","-")}-LOT-{full+1:03}', 'Synthetic lot identifier'
        if 'version' in tokens: return self.config['settings']['programVersion'], 'Configured PLC program version'
        if ('humidity' in tokens or 'rh' in tokens): return wave(58,.06), 'Humidification: relative humidity'
        if tokens & {'temperature', 'temp'}: return wave(27,.03), 'Humidification: temperature'
        if tokens & {'pressure', 'suction'}: return wave(150,.07), 'Air / humidification pressure'
        if tokens & {'date','clock','rtc','year','month','day'} or row['groupCode']==150:
            for names,value in [(('year',),now.year),(('month',),now.month),(('day','date'),now.day),(('hour','hours'),now.hour),(('minute','minutes'),now.minute),(('second','seconds'),now.second)]:
                if tokens.intersection(names): return value, 'Calendar / RTC component'
        time_words={'hour','hours','hr','hrs','minute','minutes','min','mins','second','seconds','sec','secs','time','runtime','hms'}
        if tokens & time_words:
            total = stopped if tokens & {'idle','doff','stop','stoppage','powerfail','powerfailure'} or 'power fail' in name else run
            if tokens & {'hour','hours','hr','hrs'}: value = math.floor(total/3600)
            elif tokens & {'minute','minutes','min','mins'}: value = math.floor(total/60) % 60 if 'total' not in tokens else total/60
            elif tokens & {'second','seconds','sec','secs'}: value = math.floor(total)%60 if 'total' not in tokens else total
            elif unit in ('min','mins','minutes'): value=total/60
            elif unit in ('h','hr','hrs','hours'): value=total/3600
            else: value=total
            return value, 'Accumulated stopped time' if total==stopped else 'Accumulated run time'
        if 'shift' in tokens and tokens & {'number','no'}: return now.hour//8+1, 'Synthetic eight-hour shift number'
        if 'power' in tokens and 'factor' in tokens:return wave(.92,.005), 'Synthetic power factor'
        if 'frequency' in tokens or 'hz' in tokens:return wave(50,.001), 'Supply frequency'
        if tokens & {'kwh','energy'}: return 100+(run*power+stopped*power*.1)/3600, 'Cumulative synthetic energy (kWh)'
        if tokens & {'power','kw'}: return wave(power) if running else power*.1, 'Synthetic active power'
        if tokens & {'voltage','volt'}: return wave(415,.006), 'Supply voltage'
        if tokens & {'current','amp','amps'} and not tokens & {'length','shift','date','day','month','year'}: return wave(power*1.7), 'Supply current'
        if 'delivery' in tokens and 'hanks' in tokens:return run/60*5, 'Accumulated synthetic delivery hanks'
        if tokens & {'hank','hanks'}: return wave(hank,.008), 'Yarn / sliver hank'
        if tokens & {'cv','cvpercent','cvpct'}: return wave(2.1,.12), 'Coefficient of variation (%)'
        if tokens & {'u','upercent','upct'}: return wave(1.4,.1), 'Unevenness (%)'
        if tokens & {'tpi','twist'}: return wave(18 if department=='Ring Frame' else 1.2,.01), 'Twist per inch'
        if tokens & {'draft','drafting'}: return wave(draft,.01), 'Draft ratio'
        if tokens & {'doff','doffs','doffing'}: return full, 'Completed synthetic doff cycles'
        if tokens & {'efficiency','utilization','utilisation'}: return run/max(duration,1)*100, 'Run share (%)'
        if tokens & {'production','produced','kg'}: return run/3600*(90 if department!='Ring Frame' else 35), 'Accumulated production (kg)'
        if tokens & {'status','state','running','run','enable','enabled'}:
            for option in row.get('dropdownOptions') or []:
                label=words(option.get('label',''))
                if (running and ('running' in label or label=='run')) or (not running and ('stop' in label or label=='idle')):
                    try:return float(option['value']), 'Synthetic state from metadata dropdown'
                    except (TypeError,ValueError):pass
            return (8 if running else 0) if row['dataType'].upper()!='BOOL' else running, 'Synthetic running / stopped state'
        if 'rpm' in tokens or tokens & {'spindle','cylinder'}: return wave(14000 if department=='Ring Frame' else 580,.015) if running else 0, 'Rotational speed'
        if 'speed' in tokens: return wave(speed) if running else 0, 'Delivery speed'
        if 'length' in tokens: return phase/cycle*5000, 'Length progress within the cycle'
        if tokens & {'count','counter','pieces','cans'}: return math.floor(run/10), 'Cumulative counter'
        # Unknown fields remain visibly generic; metadata limits are not invented acceptance criteria.
        return 10+5*math.sin(elapsed/10+row['tagCode']), 'Generic changing value; configure an override'

    def value(self, row, elapsed):
        value, behavior = self.reading(row, elapsed)
        kind = row['dataType'].upper().split('[')[0]
        if kind == 'STRING': return value, behavior
        if kind == 'BOOL':
            if behavior.startswith('Generic changing'):return (int(elapsed/5)+row['tagCode'])%2==0, 'Alternating synthetic Boolean'
            return bool(value), behavior
        bounds={'BYTE':(0,255),'USINT':(0,255),'SINT':(-128,127),'UINT':(0,65535),'INT':(-32768,32767),'DINT':(-2147483648,2147483647),'UDINT':(0,4294967295)}
        if kind in bounds:
            low,high=bounds[kind]; value=max(low,min(high,int(round(value))))
        return value, behavior

    def packet(self, group):
        rows = self.groups.get(group)
        if not rows:
            return frame(self.config['plc']['machineId'], struct.pack('<f' if self.config['plc']['endianness']=='little' else '>f',self.config['settings']['programVersion'])) if group==10 else frame(self.config['plc']['machineId'],result=14)
        data=bytearray(max(row['offset']+metadata_width(row) for row in rows))
        elapsed=(time.monotonic()-self.started)*self.config['settings']['timeScale']
        for row in rows:
            value,_=self.value(row,elapsed);kind=row['dataType'].upper().split('[')[0]
            width=metadata_width(row)
            if kind=='STRING':
                text=str(value).encode('ascii','replace')[:max(0,width-1)];data[row['offset']:row['offset']+len(text)]=text
            else:
                size=struct.calcsize(FORMATS[kind]);count=width//size
                for index in range(count):struct.pack_into(('<' if self.config['plc']['endianness']=='little' else '>')+FORMATS[kind],data,row['offset']+size*index,value)
        return frame(self.config['plc']['machineId'],bytes(data))


class PLCServer(socketserver.ThreadingTCPServer):
    daemon_threads=True
    allow_reuse_address=False
    request_queue_size=8
    def __init__(self,config):
        self.generator=Generator(config);self.connections=threading.BoundedSemaphore(8);self.requests=0;self.last_request=None;self.stopping=threading.Event()
        super().__init__(('127.0.0.1',config['plc']['port']),Handler)
    def process_request(self,request,address):
        if not self.connections.acquire(blocking=False):request.close();return
        try:super().process_request(request,address)
        except Exception:self.connections.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.connections.release()


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            for _ in range(256):
                if self.server.stopping.is_set():return
                raw=b''
                while len(raw)<5:
                    part=self.request.recv(5-len(raw))
                    if not part:return
                    raw+=part
                length=int.from_bytes(raw[3:5],'big')+7
                while len(raw)<length:
                    part=self.request.recv(length-len(raw))
                    if not part:return
                    raw+=part
                checksum=0
                if self.server.stopping.is_set():return
                for byte in raw[:-2]:checksum^=byte
                machine=self.server.generator.config['plc']['machineId']
                if raw[0]!=3 or raw[-1]!=2 or raw[1]!=machine or checksum!=raw[-2]:
                    self.request.sendall(frame(machine,result=11));return
                if raw[2]==1 and len(raw)>=9:
                    group=int.from_bytes(raw[5:7],'big')
                    if group==11:return
                    if len(raw)==30:
                        try:self.server.generator.clock_offset=datetime.strptime(raw[9:28].decode('ascii'),'%Y-%m-%d %H:%M:%S').timestamp()-time.time()
                        except (ValueError,UnicodeError):self.request.sendall(frame(machine,result=13));continue
                    response=self.server.generator.packet(group)
                elif raw[2]==2:
                    try:self.server.generator.clock_offset=datetime.strptime(raw[5:-2].decode('ascii'),'%Y-%m-%d %H:%M:%S').timestamp()-time.time();response=frame(machine)
                    except (ValueError,UnicodeError):response=frame(machine,result=13)
                else:response=frame(machine,result=12)
                self.server.requests+=1;self.server.last_request=time.time()*1000
                self.request.sendall(response)
        except OSError:return


def configuration(user_id,target_id):
    with storage.db() as db:row=db.execute('SELECT config FROM data_simulators WHERE user_id=? AND target_id=?',(user_id,target_id)).fetchone()
    return json.loads(row[0]) if row else None


def configure(user_id,data):
    config=validate(data)
    with LOCK:
        if (user_id,config['plc']['id']) in SERVERS:raise ValueError('Stop the data simulator before changing its configuration.')
        with storage.db() as db:db.execute('INSERT OR REPLACE INTO data_simulators VALUES (?,?,?)',(user_id,config['plc']['id'],json.dumps(config,allow_nan=False)))
    return status(user_id,config['plc']['id'])


def status(user_id,target_id):
    with LOCK:
        server=SERVERS.get((user_id,target_id));config=server.generator.config if server else configuration(user_id,target_id)
        return {'running':bool(server),'config':config,'requests':server.requests if server else 0,
                'lastRequest':server.last_request if server else None,'address':f"127.0.0.1:{config['plc']['port']}" if config else None}


def start(user_id,data):
    config=validate(data);identity=(user_id,config['plc']['id'])
    with LOCK:
        old=SERVERS.get(identity)
        if old:
            if old.generator.config==config:return status(*identity)
            raise ValueError('Stop this simulator before applying a different configuration.')
        if len(SERVERS)>=16:raise ValueError('At most 16 data simulators can run on this server.')
        try:server=PLCServer(config)
        except OSError as error:raise ValueError(f"Cannot open 127.0.0.1:{config['plc']['port']}. Choose a free TCP port.") from error
        try:
            with storage.db() as db:db.execute('INSERT OR REPLACE INTO data_simulators VALUES (?,?,?)',(*identity,json.dumps(config,allow_nan=False)))
        except Exception:server.server_close();raise
        SERVERS[identity]=server
        threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.1},name='virtual-plc',daemon=True).start()
    return status(*identity)


def stop(user_id,target_id):
    with LOCK:server=SERVERS.pop((user_id,target_id),None)
    if server:server.stopping.set();server.shutdown();server.server_close()
    return status(user_id,target_id)


def remove_user(user_id):
    for identity in list(SERVERS):
        if identity[0]==user_id:stop(*identity)
    initialize()
    with storage.db() as db:db.execute('DELETE FROM data_simulators WHERE user_id=?',(user_id,))


def reconcile(user_id,plcs):
    """A removed target or a new real/ARsim mode must not leave a synthetic listener running."""
    allowed={plc['id']:plc for plc in plcs if plc.get('targetMode')=='data-simulator'}
    with storage.db() as db:rows=db.execute('SELECT target_id,config FROM data_simulators WHERE user_id=?',(user_id,)).fetchall()
    for row in rows:
        config=json.loads(row['config']);target=allowed.get(row['target_id'])
        if not target or any(target.get(key)!=config['plc'].get(key) for key in ('ip','port','machineId','endianness','machineType')):
            stop(user_id,row['target_id']);config['settings']['autoStart']=False
            with storage.db() as db:db.execute('UPDATE data_simulators SET config=? WHERE user_id=? AND target_id=?',(json.dumps(config),user_id,row['target_id']))


def autostart():
    initialize()
    eligible={user['id'] for user in accounts.store.list_users() if user['active'] and user['approved']}
    with storage.db() as db:rows=db.execute('SELECT user_id,config FROM data_simulators').fetchall()
    for row in rows:
        data=json.loads(row['config'])
        if row['user_id'] in eligible and data['settings'].get('autoStart'):
            try:start(row['user_id'],data)
            except ValueError:__import__('logging').getLogger('usopp.simulator').exception('Data simulator could not restart')


def shutdown():
    for identity in list(SERVERS):stop(*identity)
