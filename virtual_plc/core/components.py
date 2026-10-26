"""Generic, deterministic virtual devices connected to explicit PLC identities.

These models neither execute vendor drive libraries nor connect to real hardware.
An input port reads a PLC command; an output port writes simulated PLC feedback.
Feedback is supplied at scan boundaries, with forcing taking precedence. Device
motion always restarts from configuration when a workspace is reopened or reset.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import re

from virtual_plc.core.memory import INTEGER_TYPES
from virtual_plc.core.libraries import block_member

MAX_COMPONENTS = 2048
MAX_CONFIGURATION = 4 * 1024 * 1024


def _port(key, label, direction, datatype='numeric', required=False):
    return {'key': key, 'label': label, 'direction': direction, 'type': datatype, 'required': required}


def _field(key, label, default, minimum, maximum, unit=None):
    item = {'key': key, 'label': label, 'default': default, 'min': minimum, 'max': maximum}
    if unit:
        item['unit'] = unit
    return item


CATALOG = [
    {'kind': 'pushbutton', 'label': 'Pushbutton', 'description': 'A momentary input pulse measured in virtual PLC time.',
     'ports': [_port('value', 'Contact to PLC', 'output', 'BOOL', True)],
     'configFields': [_field('releasedValue', 'Released contact (0/1)', 0, 0, 1),
                      _field('pulseMs', 'Press duration', 200, 1, 60000, 'ms')]},
    {'kind': 'digital_input', 'label': 'Digital input (DI)',
     'description': 'Configured virtual switch/contact signal into PLC memory.',
     'ports': [_port('value', 'Contact state to PLC', 'output', 'BOOL', True),
               _port('command', 'Actuator command from PLC', 'input', 'BOOL')],
     'configFields': [_field('value', 'Manual switch state (0/1)', 0, 0, 1),
                      _field('automatic', 'Automatic jig feedback (0/1)', 0, 0, 1),
                      _field('activeValue', 'Contact when actuator is on (0/1)', 1, 0, 1),
                      _field('delayOnMs', 'Actuator on delay', 150, 0, 60000, 'ms'),
                      _field('delayOffMs', 'Actuator off delay', 150, 0, 60000, 'ms')]},
    {'kind': 'digital_output', 'label': 'Digital output (DO)',
     'description': 'Virtual lamp/relay driven by a PLC BOOL command; optional feedback.',
     'ports': [_port('command', 'Command from PLC', 'input', 'BOOL', True),
               _port('feedback', 'Contact feedback to PLC', 'output', 'BOOL')], 'configFields': []},
    {'kind': 'motor', 'label': 'Generic motor',
     'description': 'Generic shaft-speed ramp for a virtual motor. No electrical or vendor motor model.',
     'ports': [_port('enable', 'Enable from PLC', 'input', 'BOOL', True),
               _port('targetSpeed', 'Requested speed from PLC', 'input'),
               _port('speed', 'Shaft speed to PLC', 'output'),
               _port('running', 'Running to PLC', 'output', 'BOOL')],
     'configFields': [_field('maximumSpeed', 'Maximum shaft speed', 3000, 1, 1e6, 'RPM'),
                      _field('rampRate', 'Speed ramp', 500, .01, 1e6, 'RPM/s'),
                      _field('startDelayMs', 'Motor start delay', 0, 0, 60000, 'ms'),
                      _field('faultInjected', 'Injected motor fault (0/1)', 0, 0, 1),
                      _field('nominalSpeed', 'Unbound speed reference', 1000, 0, 1e6, 'RPM')]},
    {'kind': 'analog_input', 'label': 'Analog input',
     'description': 'Generic configured signal into PLC memory. No physical sensor or network connection.',
     'ports': [_port('value', 'Sensor value to PLC', 'output', required=True),
               _port('enable','Actuator enable from PLC','input','BOOL'),
               _port('command','Process reference from PLC','input')],
     'configFields': [_field('minimum', 'Minimum', 0, -1e9, 1e9),
                      _field('maximum', 'Maximum', 100, -1e9, 1e9),
                      _field('value', 'Manual sensor value', 0, -1e9, 1e9),
                      _field('automatic','Automatic jig feedback (0/1)',0,0,1),
                      _field('onValue','Unbound operating value',50,-1e9,1e9),
                      _field('offValue','Stopped sensor value',0,-1e9,1e9),
                      _field('gain','Reference scaling',1,-1e6,1e6),
                      _field('offset','Reference offset',0,-1e9,1e9),
                      _field('slewPerSecond','Sensor response per second (0 = immediate)',50000,0,1e9)]},
    {'kind': 'analog_output', 'label': 'Analog output',
     'description': 'Generic clamped PLC output monitor with an optional rate limit and feedback signal.',
     'ports': [_port('command', 'Command from PLC', 'input', required=True),
               _port('feedback', 'Feedback to PLC', 'output')],
     'configFields': [_field('minimum', 'Minimum', 0, -1e9, 1e9),
                      _field('maximum', 'Maximum', 100, -1e9, 1e9),
                      _field('initialValue', 'Initial feedback', 0, -1e9, 1e9),
                      _field('slewPerSecond', 'Maximum change per second (0 = immediate)', 0, 0, 1e9)]},
    {'kind': 'servo', 'label': 'Generic servo drive',
     'description': 'Simplified position motion with travel, speed and acceleration limits. Not a vendor servo or safety model.',
     'ports': [_port('enable', 'Enable from PLC', 'input', 'BOOL', True),
               _port('target', 'Target position from PLC', 'input'),
               _port('reset', 'Reset fault from PLC', 'input', 'BOOL'),
               _port('position', 'Position to PLC', 'output'),
               _port('speed', 'Velocity to PLC', 'output'),
               _port('ready', 'Ready to PLC', 'output', 'BOOL'),
               _port('inPosition', 'In position to PLC', 'output', 'BOOL'),
               _port('fault', 'Fault to PLC', 'output', 'BOOL')],
     'configFields': [_field('minimumPosition', 'Minimum position', -10000, -1e9, 1e9),
                      _field('maximumPosition', 'Maximum position', 10000, -1e9, 1e9),
                      _field('initialPosition', 'Initial position', 0, -1e9, 1e9),
                      _field('maximumSpeed', 'Maximum speed', 100, .001, 1e6, 'units/s'),
                      _field('acceleration', 'Acceleration', 200, .001, 1e6, 'units/s²'),
                      _field('tolerance', 'In-position tolerance', .01, 0, 1e6),
                      _field('targetPosition', 'Unbound position reference', 100, -1e9, 1e9),
                      _field('faultInjected', 'Injected drive fault (0/1)', 0, 0, 1)]},
    {'kind': 'vfd', 'label': 'Generic VFD',
     'description': 'Generic frequency ramp and proportional RPM feedback. Does not emulate a drive protocol or motor dynamics.',
     'ports': [_port('run', 'Run from PLC', 'input', 'BOOL', True),
               _port('targetFrequency', 'Target frequency from PLC', 'input'),
               _port('reset', 'Reset fault from PLC', 'input', 'BOOL'),
               _port('frequency', 'Frequency to PLC', 'output'),
               _port('ready', 'Ready to PLC', 'output', 'BOOL'),
               _port('speed', 'Speed to PLC', 'output'),
               _port('running', 'Running to PLC', 'output', 'BOOL'),
               _port('fault', 'Fault to PLC', 'output', 'BOOL')],
     'configFields': [_field('maximumFrequency', 'Maximum frequency', 60, .001, 1000, 'Hz'),
                      _field('rampUp', 'Ramp up', 10, .001, 10000, 'Hz/s'),
                      _field('rampDown', 'Ramp down', 20, .001, 10000, 'Hz/s'),
                      _field('ratedFrequency', 'Rated frequency', 50, .001, 1000, 'Hz'),
                      _field('ratedSpeed', 'Speed at rated frequency', 1500, .001, 1e6, 'RPM'),
                      _field('referenceFrequency', 'Unbound frequency reference', 50, 0, 1000, 'Hz'),
                      _field('faultInjected', 'Injected drive fault (0/1)', 0, 0, 1)]},
    {'kind': 'encoder', 'label': 'Generic encoder',
     'description': 'Integrates the bound shaft speed in RPM into revolutions and a wrapping pulse count.',
     'ports': [_port('speed', 'Shaft speed from PLC', 'input', required=True),
               _port('reset', 'Reset count from PLC', 'input', 'BOOL'),
               _port('position', 'Position to PLC', 'output'),
               _port('count', 'Pulse count to PLC', 'output'),
               _port('channelA', 'Quadrature A to PLC', 'output', 'BOOL'),
               _port('channelB', 'Quadrature B to PLC', 'output', 'BOOL')],
     'configFields': [_field('initialPosition', 'Initial position', 0, -1e9, 1e9, 'rev'),
                      _field('countsPerRevolution', 'Counts per revolution', 1024, 1, 1e6),
                      _field('rollover', 'Pulse count rollover', 2147483648, 2, 4294967296)]},
]
CATALOG.append({'kind': 'velocity_servo', 'label': 'Velocity servo drive',
    'description': 'Rotary servo speed ramp in RPM with editable drive feedback.',
    'ports': [_port('enable','Enable from PLC','input','BOOL',True), _port('run','Start from PLC','input','BOOL'), _port('targetSpeed','Speed reference','input'),
              _port('reset','Fault reset','input','BOOL'), _port('speed','Shaft speed','output'),
              _port('ready','Drive ready','output','BOOL'), _port('running','Running','output','BOOL'), _port('fault','Drive fault','output','BOOL')],
    'configFields': [_field('maximumSpeed','Maximum speed',3000,1,1e6,'RPM'),
                     _field('nominalSpeed','Unbound speed reference',1000,0,1e6,'RPM'),
                     _field('rampRate','Acceleration',500,.01,1e6,'RPM/s'),
                     _field('faultInjected','Injected drive fault (0/1)',0,0,1)]})
CATALOG.append({'kind':'cylinder','label':'Pneumatic cylinder',
    'description':'A configurable virtual stroke with end-switch feedback, travel time and stuck-cylinder faults.',
    'ports':[_port('extend','Extend solenoid from PLC','input','BOOL',True),
             _port('retract','Retract solenoid from PLC','input','BOOL'),
             _port('extended','Extended limit to PLC','output','BOOL'),
             _port('retracted','Retracted limit to PLC','output','BOOL'),
             _port('position','Stroke fraction to PLC','output')],
    'configFields':[_field('travelMs','Full stroke travel time',1000,1,60000,'ms'),
                    _field('initialPosition','Initial stroke fraction',0,0,1),
                    _field('springReturn','Retract when extend is off (0/1)',1,0,1),
                    _field('faultInjected','Stuck cylinder fault (0/1)',0,0,1)]})
for _definition in CATALOG:
    if _definition['kind'] in {'vfd','motor','velocity_servo','servo'}:
        _unit='Hz/raw unit' if _definition['kind']=='vfd' else 'position/raw unit' if _definition['kind']=='servo' else 'RPM/raw unit'
        _definition['configFields'].extend([_field('referenceScale','PLC reference scale',1,-1e6,1e6,_unit),
                                           _field('referenceOffset','PLC reference offset',0,-1e9,1e9)])
_CATALOG = {entry['kind']: entry for entry in CATALOG}


def component_catalog():
    return deepcopy(CATALOG)


def binding_reference(runtime, identity):
    """Resolve an explicit scoped address and canonicalize its literal path."""
    if ':' not in identity:
        raise ValueError('Choose a scoped PLC identity, for example @global::Speed or task::Axis.Position.')
    record, reference = runtime.value_reference(identity)
    if record.get('ambiguous'):
        raise ValueError('Conflicting PLC declarations: ' + identity)
    specification = record['_spec']
    canonical = record['id']
    for segment in reference.get('path', []):
        if 'member' in segment:
            member = str(segment['member'])
            if specification.get('kind') == 'block':
                member = block_member(specification['type'], member)
            elif specification.get('kind') == 'struct':
                member = next(field['name'] for field in runtime.memory.fields(specification)
                              if field['name'].casefold() == member.casefold())
            canonical += '.' + member
            segment = {'member': member}
        else:
            index = segment['index']
            if index.get('op') != 'literal' or type(index.get('value')) is not int:
                raise ValueError('Device connections require literal integer indexes.')
            canonical += '[' + str(index['value']) + ']'
        specification = runtime.memory.reference_spec(
            {'name': record['id'], 'path': [segment]}, specification=specification)
    return canonical, record, specification


def validate_components(components, runtime=None):
    """Return a canonical configuration; reject ambiguous or unsafe bindings.

    Unbound disabled devices can be saved as drafts. Every bound port is checked
    immediately, and enabled devices require their mandatory signal bindings.
    Exact scoped scalars and literal array/structure members are supported,
    never expressions or guessed global/local names. Integer feedback is rounded.
    """
    if not isinstance(components, list) or len(components) > MAX_COMPONENTS:
        raise ValueError('Use at most 2048 virtual device components.')
    try:
        encoded = json.dumps(components, allow_nan=False)
    except (ValueError, TypeError):
        raise ValueError('Component configuration must contain finite JSON values.') from None
    if len(encoded.encode('utf-8')) > MAX_CONFIGURATION:
        raise ValueError('Component configuration exceeds 4 MiB.')
    identities, writers, result = set(), {}, []
    records = runtime.memory.records if runtime else None
    for original in components:
        if not isinstance(original, dict):
            raise ValueError('Each component needs an identity, kind and configuration.')
        identity = original.get('id')
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identity) or identity in identities:
            raise ValueError('Give each component a unique 1..80 character identity using letters, numbers, _ or -.')
        identities.add(identity)
        kind = original.get('kind')
        entry = _CATALOG.get(kind)
        if not entry:
            raise ValueError('Unsupported virtual device component kind: ' + str(kind)[:80])
        name = original.get('name', entry['label'])
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError('A component display name must be 1..120 characters.')
        enabled = original.get('enabled', False)
        if type(enabled) is not bool:
            raise ValueError('Component enabled must be true or false; it defaults to false.')
        evidence = original.get('evidence', {})
        assumptions = original.get('assumptions', [])
        if (not isinstance(evidence, dict) or len(evidence) > 24
                or any(not isinstance(key,str) or len(key)>80 or value is not None and
                       (type(value) not in {str,int,float,bool} or isinstance(value,str) and len(value)>2000)
                       for key,value in evidence.items())):
            raise ValueError(name + ': source evidence must contain bounded scalar fields.')
        if (not isinstance(assumptions,list) or len(assumptions)>30
                or any(not isinstance(value,str) or len(value)>2000 for value in assumptions)):
            raise ValueError(name + ': use up to 30 model assumption strings.')
        config, supplied = {}, original.get('config', {})
        if not isinstance(supplied, dict):
            raise ValueError('Device settings must be a configuration object.')
        fields = {field['key']: field for field in entry['configFields']}
        if set(supplied) - set(fields):
            raise ValueError('Unknown settings for ' + name + ': ' + ', '.join(sorted(set(supplied) - set(fields))))
        for key, field in fields.items():
            value = supplied.get(key, field['default'])
            if type(value) not in {int, float} or not math.isfinite(value) or not field['min'] <= value <= field['max']:
                raise ValueError(f"{name}: {field['label']} must be a finite number in {field['min']}..{field['max']}.")
            config[key] = value
        for binary in ('releasedValue', 'faultInjected', 'automatic', 'activeValue', 'springReturn'):
            if binary in config and config[binary] not in (0, 1):
                raise ValueError(name + ': ' + binary + ' must be 0 or 1.')
        if kind in {'analog_input', 'analog_output'}:
            if config['minimum'] >= config['maximum']:
                raise ValueError(name + ': minimum must be less than maximum.')
            value_key = 'value' if kind == 'analog_input' else 'initialValue'
            if not config['minimum'] <= config[value_key] <= config['maximum']:
                raise ValueError(name + ': initial signal must be within the configured range.')
        elif kind == 'digital_input' and config['value'] not in {0, 1}:
            raise ValueError(name + ': DI switch state must be 0 or 1.')
        elif kind == 'servo':
            if (config['minimumPosition'] >= config['maximumPosition'] or
                    not config['minimumPosition'] <= config['initialPosition'] <= config['maximumPosition']):
                raise ValueError(name + ': initial position must be within a nonempty travel range.')
        elif kind == 'vfd' and config['ratedFrequency'] > config['maximumFrequency']:
            raise ValueError(name + ': rated frequency must not exceed maximum frequency.')
        elif kind == 'encoder':
            for key in ('countsPerRevolution', 'rollover'):
                if config[key] != int(config[key]):
                    raise ValueError(name + ': encoder count settings must be integral.')
                config[key] = int(config[key])
        bindings = original.get('bindings', {})
        links = original.get('links', {})
        if not isinstance(links, dict): raise ValueError(name + ': device links must be an object.')
        if not isinstance(bindings, dict):
            raise ValueError(name + ': bindings must map port keys to exact PLC variable identities.')
        ports = {port['key']: port for port in entry['ports']}
        for key, link in links.items():
            if key not in ports or ports[key]['direction'] != 'input' or key in bindings and bindings[key]:
                raise ValueError(name + ': a command port accepts one PLC binding or one device link.')
            if not isinstance(link,dict) or set(link) != {'component','port'}:
                raise ValueError(name + ': a device link needs component and port.')
            if any(not isinstance(link[field],str) or not 1<=len(link[field])<=80 for field in ('component','port')):
                raise ValueError(name + ': device link identities must be 1..80 characters.')
        if set(bindings) - set(ports):
            raise ValueError(name + ': an unknown device port was supplied.')
        selected = {}
        for key, value in bindings.items():
            if value in (None, ''):
                continue
            if not isinstance(value, str) or len(value) > 400:
                raise ValueError(name + ': choose an exact PLC variable identity for ' + key + '.')
            port = ports[key]
            selected[key] = value
            if records is not None:
                try:
                    value, record, spec = binding_reference(runtime, value)
                except (ValueError, TypeError, KeyError, IndexError, StopIteration) as error:
                    raise ValueError(name + ': invalid PLC connection ' + value + ': ' + str(error)) from None
                selected[key] = value
                typename = str(spec.get('type', '')).upper()
                valid = (spec.get('kind') == 'scalar' and
                         (typename == 'BOOL' if port['type'] == 'BOOL' else typename in INTEGER_TYPES or typename in {'REAL', 'LREAL'}))
                if not valid:
                    raise ValueError(name + ': ' + port['label'] + ' requires a ' + port['type'] + ' scalar PLC variable.')
                if port['direction'] == 'output' and (record.get('constant') or record.get('mode') == 'VAR_CONSTANT'):
                    raise ValueError(name + ': feedback cannot write a constant PLC variable.')
                if port['direction'] == 'output':
                    _validate_output_range(name, kind, key, config, spec)
            if port['direction'] == 'output':
                writer_key = value
                if writer_key in writers:
                    raise ValueError(name + ': multiple device outputs cannot write ' + value + '; already bound to ' + writers[writer_key] + '.')
                writers[writer_key] = name + '/' + key
        if enabled:
            missing = [port['label'] for port in entry['ports'] if port.get('required') and port['key'] not in selected and port['key'] not in links]
            if missing:
                raise ValueError(name + ': bind required ports before enabling: ' + ', '.join(missing))
            if kind == 'digital_input' and config['automatic'] and not (selected.get('command') or links.get('command')):
                raise ValueError(name + ': automatic sensor feedback requires an actuator command.')
            if kind=='analog_input' and config['automatic'] and not any(selected.get(k) or links.get(k) for k in ('enable','command')):
                raise ValueError(name + ': automatic analog feedback requires an enable or process reference.')
        input_ids = {selected[port['key']] for port in entry['ports'] if port['direction'] == 'input' and port['key'] in selected}
        if any(selected[port['key']] in input_ids for port in entry['ports'] if port['direction'] == 'output' and port['key'] in selected):
            raise ValueError(name + ': a feedback output cannot overwrite this component\'s own command variable.')
        position = original.get('position')
        if position is not None and (not isinstance(position, dict) or set(position) != {'x', 'y'} or
                any(type(position[k]) not in {int, float} or not math.isfinite(position[k]) or not 0 <= position[k] <= 12000 for k in ('x', 'y'))):
            raise ValueError(name + ': topology coordinates must be finite values in 0..12000.')
        result.append({'id': identity, 'name': name.strip(), 'kind': kind, 'enabled': enabled,
                       'bindings': selected, 'config': config, 'links': deepcopy(links),
                       **{k:deepcopy(original[k]) for k in ('evidence','assumptions') if k in original},
                       **({'position': position} if position else {})})
    by_id = {item['id']: item for item in result}
    for item in result:
        for key, link in item['links'].items():
            peer = by_id.get(link['component'])
            source = next((p for p in _CATALOG[peer['kind']]['ports'] if p['key'] == link['port'] and p['direction'] == 'output'), None) if peer else None
            target = next(p for p in _CATALOG[item['kind']]['ports'] if p['key'] == key)
            if not source or source['type'] != target['type'] or peer['id'] == item['id']:
                raise ValueError(item['name'] + ': device link needs a compatible output from another component.')
            if item['enabled'] and not peer['enabled']:
                raise ValueError(item['name'] + ': enable the linked source component first.')
    return result


def _validate_output_range(name, kind, key, config, spec):
    """Fail early when the entire configured feedback range cannot fit an integer."""
    typename = spec.get('type')
    if typename not in INTEGER_TYPES:
        return
    low, high = INTEGER_TYPES[typename]
    bounds = None
    if kind in {'analog_input', 'analog_output'}:
        bounds = (config['minimum'], config['maximum'])
    elif kind == 'servo' and key == 'position':
        bounds = (config['minimumPosition'], config['maximumPosition'])
    elif kind == 'servo' and key == 'speed':
        bounds = (-config['maximumSpeed'], config['maximumSpeed'])
    elif kind == 'vfd' and key == 'frequency':
        bounds = (0, config['maximumFrequency'])
    elif kind == 'vfd' and key == 'speed':
        bounds = (0, config['maximumFrequency'] * config['ratedSpeed'] / config['ratedFrequency'])
    elif kind == 'encoder' and key == 'count':
        bounds = (0, config['rollover'] - 1)
    elif kind in {'motor','velocity_servo'} and key == 'speed':
        bounds = (-config['maximumSpeed'], config['maximumSpeed'])
    if bounds and (round(bounds[0]) < low or round(bounds[1]) > high):
        raise ValueError(name + ': configured feedback range does not fit ' + str(typename) + ' for port ' + key + '.')


def _towards(value, target, distance):
    return min(target, value + distance) if target > value else max(target, value - distance)


class DeviceComponents:
    """Per-workspace models, advanced only after complete supported PLC scans."""
    def __init__(self, components, runtime):
        self.runtime = runtime
        self.components = validate_components(components, runtime)
        self.bindings = {identity: binding_reference(runtime, identity)[1:]
                         for component in self.components for identity in component['bindings'].values()}
        self.binding_paths = {identity:runtime.value_reference(identity)[1].get('path', []) for identity in self.bindings}
        self.states = {}
        self.started = False
        self.active = True
        self.pending_signals = set()
        self.last_time_ms = float(runtime.time_ms)
        self.last_scan_count = runtime.scan_count
        for component in self.components:
            config, kind = component['config'], component['kind']
            state = {'error': None, 'current': {}, 'outputs': {}, 'updatedAtMs': None}
            if kind == 'pushbutton': state['current'] = {'value': bool(config['releasedValue'])}; state['pressedUntilMs'] = 0
            elif kind == 'analog_input': state['current'] = {'value': config['value']}
            elif kind == 'digital_input': state['current'] = {'value': bool(config['value'])}
            elif kind == 'digital_output': state['current'] = {'feedback': False}
            elif kind in {'motor','velocity_servo'}: state['current'] = {'speed': 0.0, 'running': False, 'ready': True, 'fault': False}
            elif kind == 'analog_output': state['current'] = {'feedback': config['initialValue']}
            elif kind == 'servo': state['current'] = {'position': config['initialPosition'], 'speed': 0.0, 'fault': False}
            elif kind == 'vfd': state['current'] = {'frequency': 0.0, 'speed': 0.0, 'fault': False}
            elif kind == 'cylinder':
                position=config['initialPosition']
                state['current']={'position':position,'extended':position>=1,'retracted':position<=0,'moving':False,'fault':False}
            elif kind == 'encoder': state['current'] = {'channelA': False, 'channelB': False, 'position': config['initialPosition'],
                                                       'count': math.floor(config['initialPosition'] * config['countsPerRevolution']) % config['rollover']}
            self.states[component['id']] = state

    def _read_binding(self, identity):
        record, _ = self.bindings[identity]
        value, _ = self.runtime.memory.member(record['value'], record['_spec'], self.binding_paths[identity], lambda index:index['value'])
        return value

    def _inputs(self, component):
        result = {}
        for port in _CATALOG[component['kind']]['ports']:
            if port['direction'] != 'input':
                continue
            variable = component['bindings'].get(port['key'])
            link = component.get('links', {}).get(port['key'])
            fallback = {'targetSpeed': component['config'].get('nominalSpeed', 0), 'targetFrequency': component['config'].get('referenceFrequency', 0), 'target': component['config'].get('targetPosition', 0)}.get(port['key'], False if port['type'] == 'BOOL' else 0.0)
            result[port['key']] = self.states[link['component']]['current'].get(link['port'], fallback) if link else self._read_binding(variable) if variable else fallback
            # PLC analog counts require explicit engineering scaling. Device
            # links and unbound model references already use engineering units.
            if variable and not link and port['key'] in {'targetSpeed','targetFrequency','target'} and component['kind'] in {'vfd','motor','velocity_servo','servo'}:
                result[port['key']]=result[port['key']]*component['config']['referenceScale']+component['config']['referenceOffset']
            if port['type'] == 'numeric' and (type(result[port['key']]) not in {int, float} or not math.isfinite(result[port['key']])):
                raise ValueError('Command contains a non-finite numeric value: ' + port['label'])
        return result

    def _compute(self, component, delta):
        state = self.states[component['id']]
        previous, cfg, kind = deepcopy(state['current']), component['config'], component['kind']
        inputs = self._inputs(component)
        if kind == 'pushbutton':
            held = state['pressedUntilMs'] is None
            pressed = held or self.runtime.time_ms < state['pressedUntilMs']
            return {'value': bool(cfg['releasedValue']) != pressed, 'held':held}
        if kind == 'analog_input':
            if cfg.get('automatic'):
                bound=component['bindings'];linked=component.get('links',{})
                target=inputs['command']*cfg['gain']+cfg['offset'] if bound.get('command') or linked.get('command') else cfg['onValue']
                if (bound.get('enable') or linked.get('enable')) and not inputs['enable']:target=cfg['offValue']
                target=max(cfg['minimum'],min(cfg['maximum'],target))
                return {'value':target if not cfg['slewPerSecond'] else _towards(previous['value'],target,cfg['slewPerSecond']*delta)}
            return {'value': cfg['value']}
        if kind == 'digital_input':
            if cfg.get('automatic'):
                command = bool(inputs['command'])
                desired = bool(cfg['activeValue']) if command else not bool(cfg['activeValue'])
                if state.get('desiredValue') != desired:
                    state['desiredValue'] = desired
                    state['dueMs'] = self.runtime.time_ms + cfg['delayOnMs' if command else 'delayOffMs']
                value = desired if self.runtime.time_ms >= state['dueMs'] else previous['value']
                return {'value': value}
            return {'value': bool(cfg['value'])}
        if kind == 'digital_output':
            return {'feedback': bool(inputs['command'])}
        if kind in {'motor','velocity_servo'}:
            fault = bool(cfg.get('faultInjected')) or (False if inputs.get('reset') else previous.get('fault', False))
            run = inputs.get('run', True) if 'run' in component.get('bindings', {}) or 'run' in component.get('links', {}) else True
            target = inputs['targetSpeed'] if inputs['enable'] and run and not fault else 0.0
            if kind=='motor':
                if not inputs['enable'] or fault:state.pop('startAtMs',None)
                else:
                    state.setdefault('startAtMs',self.runtime.time_ms)
                    if self.runtime.time_ms-state['startAtMs']<cfg['startDelayMs']:target=0.0
            if abs(target) > cfg['maximumSpeed']:
                raise ValueError('Requested motor speed exceeds the configured maximum')
            speed = _towards(previous['speed'], target, cfg['rampRate'] * delta)
            return {'speed': speed, 'running': abs(speed) > 1e-9, 'ready': not fault, 'fault': fault}
        if kind=='cylinder':
            conflict=bool(inputs['extend'] and inputs['retract'])
            fault=bool(cfg['faultInjected']) or conflict
            target=1.0 if inputs['extend'] else 0.0 if inputs['retract'] or cfg['springReturn'] else previous['position']
            position=previous['position'] if fault else _towards(previous['position'],target,delta*1000/cfg['travelMs'])
            return {'position':position,'extended':position>=1,'retracted':position<=0,
                    'moving':not fault and position!=target,'fault':fault,'conflictingCommands':conflict}
        if kind == 'analog_output':
            target = max(cfg['minimum'], min(cfg['maximum'], inputs['command']))
            feedback = target if cfg['slewPerSecond'] == 0 else _towards(previous['feedback'], target, cfg['slewPerSecond'] * delta)
            return {'feedback': feedback, 'command': inputs['command'], 'limited': target != inputs['command']}
        if kind == 'servo':
            fault = bool(cfg['faultInjected']) or (False if inputs['reset'] else previous['fault'])
            if inputs['enable'] and not cfg['minimumPosition'] <= inputs['target'] <= cfg['maximumPosition']:
                fault = True
            position, velocity = previous['position'], previous['speed']
            distance = inputs['target'] - position
            if not inputs['enable'] or fault:
                velocity = 0.0
            elif delta > 0:
                # Braking speed and acceleration bound a simple trapezoidal move.
                desired = math.copysign(min(cfg['maximumSpeed'], math.sqrt(2 * cfg['acceleration'] * abs(distance))), distance) if distance else 0.0
                velocity = _towards(velocity, desired, cfg['acceleration'] * delta)
                change = velocity * delta
                if abs(change) >= abs(distance) and change * distance >= 0:
                    position, velocity = inputs['target'], 0.0
                else:
                    position += change
                position = max(cfg['minimumPosition'], min(cfg['maximumPosition'], position))
                if position in (cfg['minimumPosition'], cfg['maximumPosition']) and abs(position - inputs['target']) > cfg['tolerance']:
                    velocity = 0.0
            return {'position': position, 'speed': velocity, 'fault': fault,
                    'ready': not fault,
                    'inPosition': bool(inputs['enable'] and not fault and abs(inputs['target'] - position) <= cfg['tolerance'])}
        if kind == 'vfd':
            fault = bool(cfg['faultInjected']) or (False if inputs['reset'] else previous['fault'])
            if inputs['run'] and not 0 <= inputs['targetFrequency'] <= cfg['maximumFrequency']:
                fault = True
            target = inputs['targetFrequency'] if inputs['run'] and not fault else 0.0
            rate = cfg['rampUp'] if target > previous['frequency'] else cfg['rampDown']
            frequency = _towards(previous['frequency'], target, rate * delta)
            return {'frequency': frequency, 'speed': frequency * cfg['ratedSpeed'] / cfg['ratedFrequency'],
                    'running': bool(frequency > 1e-9 and not fault), 'fault': fault, 'ready': not fault}
        if kind == 'encoder':
            position = cfg['initialPosition'] if inputs['reset'] else previous['position'] + inputs['speed'] * delta / 60.0
            if not math.isfinite(position) or abs(position) > 1e12:
                raise ValueError('Encoder position exceeded the supported ±1e12 revolution range.')
            phase = math.floor(position * cfg['countsPerRevolution'] * 4) % 4
            return {'channelA': phase in (1,2), 'channelB': phase in (2,3), 'position': position, 'count': math.floor(position * cfg['countsPerRevolution']) % cfg['rollover'],
                    'speed': inputs['speed']}
        raise ValueError('Unsupported component kind.')

    def _apply(self, component, current):
        pending = []
        for port in _CATALOG[component['kind']]['ports']:
            if port['direction'] != 'output':
                continue
            variable = component['bindings'].get(port['key'])
            if not variable:
                continue
            record, spec = self.bindings[variable]
            if record.get('forced'):
                continue
            value = current[port['key']]
            if spec.get('type') in INTEGER_TYPES and type(value) in {int, float}:
                value = round(value)
            # Validate every output first; one invalid signal cannot half-apply
            # the feedback set of this device. PLC memory retains its own rules.
            converted = self.runtime.memory.coerce(value, spec)
            pending.append((variable, converted))
        for variable, value in pending:
            record, _ = self.bindings[variable]
            if self._read_binding(variable) != value and not record.get('forced'):
                self.runtime.set_value(variable, value, return_snapshot=False)

    def prepare(self):
        """Publish enabled jig inputs; motion advances at completed scan boundaries."""
        if not self.active or not self.runtime.run_allowed or self.runtime.status == 'faulted':
            return
        if self.started:
            if self.runtime._pending is not None:
                return
            for component in self.components:
                if component['enabled'] and not component['config'].get('automatic') and (component['id'] in self.pending_signals or component['kind'] in {'digital_input','analog_input'}):
                    if (component['id'] not in self.pending_signals and component['kind'] in {'digital_input','analog_input'}
                            and self._read_binding(component['bindings']['value']) == component['config']['value']):
                        continue
                    current = self._compute(component, 0)
                    self._apply(component, current)
                    self.states[component['id']].update(current=current, updatedAtMs=float(self.runtime.time_ms))
            self.pending_signals.clear()
            return
        self.started = True
        self.pending_signals.clear()
        self._advance(0)

    def after_scan(self):
        # Instruction stepping and breakpoints do not advance device motion
        # until the pending complete scan has actually reached its boundary.
        if not self.active or not self.runtime.run_allowed or self.runtime.scan_count <= self.last_scan_count:
            if not self.active:
                self.last_time_ms = float(self.runtime.time_ms)
                self.last_scan_count = self.runtime.scan_count
            return
        delta_ms = float(self.runtime.time_ms) - self.last_time_ms
        if not math.isfinite(delta_ms) or not 0 <= delta_ms <= 60000:
            raise ValueError('Virtual component scan delta must be finite and within 0..60000 ms.')
        self.last_time_ms = float(self.runtime.time_ms)
        self.last_scan_count = self.runtime.scan_count
        self._advance(delta_ms / 1000.0)

    def _advance(self, delta):
        pending = []
        for component in self.components:
            state = self.states[component['id']]
            if not component['enabled'] or state['error']:
                continue
            if self.started and state['updatedAtMs'] is not None and component['kind'] in {'digital_input','analog_input'} and not component['config'].get('automatic') and component['id'] not in self.pending_signals:
                continue
            try:
                current = self._compute(component, delta)
                pending.append((component, current))
            except (ValueError, TypeError, ArithmeticError, KeyError, IndexError) as error:
                state['error'] = str(error)[:500]
        # Sample all commands before publishing feedback, so reordering cards
        # cannot change the result of linked device models within one scan.
        for component, current in pending:
            state = self.states[component['id']]
            try:
                self._apply(component, current)
                state.update(current=current, updatedAtMs=float(self.runtime.time_ms))
            except (ValueError, TypeError, ArithmeticError, KeyError, IndexError) as error:
                state['error'] = str(error)[:500]

    def snapshot(self):
        result = []
        consumers={(link['component'],link['port']) for component in self.components for link in component.get('links',{}).values()}
        for component in self.components:
            state = self.states[component['id']]
            ports, forced = [], False
            try:effective=self._inputs(component)
            except (ValueError,TypeError,KeyError,IndexError):effective={}
            for port in _CATALOG[component['kind']]['ports']:
                variable = component['bindings'].get(port['key'])
                record = self.bindings[variable][0] if variable else None
                is_forced = bool(record and record.get('forced'))
                forced = forced or (is_forced and port['direction'] == 'output')
                link = component.get('links', {}).get(port['key'])
                linked = self.states.get(link['component'], {}).get('current', {}).get(link['port']) if link else None
                ports.append({**port, 'variableId': variable, 'deviceLink': link,
                              'value': self._read_binding(variable) if record else linked if link else state['current'].get(port['key']), 'forced': is_forced,
                              'effectiveValue':effective.get(port['key'],state['current'].get(port['key'])),
                              'unit':'Hz' if port['key'] in {'frequency','targetFrequency'} else ('units/s' if component['kind']=='servo' else 'RPM') if port['key'] in {'speed','targetSpeed'} else 'rev' if component['kind']=='encoder' and port['key']=='position' else '',
                              'sourceKind':'plc' if variable else 'device' if link else 'model' if port['direction']=='input' and not port.get('required') else 'unconnected',
                              'feedsDevice':(component['id'],port['key']) in consumers})
            if not component['enabled']:
                status = {'state': 'disabled', 'message': 'Disabled. No simulated feedback is written.'}
            elif not self.active:
                status = {'state': 'jig-off', 'message': 'Simulation jig OFF. PLC can run; automatic sensor and drive feedback is frozen.'}
            elif not self.runtime.run_allowed:
                status = {'state': 'blocked', 'message': 'Supported PLC scans are required. Resolve execution blockers; device outputs remain unchanged.'}
            elif state['error']:
                status = {'state': 'error', 'message': state['error'] + ' Correct the bindings/configuration or reset the simulation.'}
            elif forced:
                status = {'state': 'forced', 'message': 'A feedback variable is forced. User forces take precedence over this generic device.'}
            elif state['current'].get('fault'):
                status={'state':'fault','message':'Conflicting cylinder solenoids are commanded.' if state['current'].get('conflictingCommands') else 'Injected or model fault prevents operation. Review the fault and model settings.'}
            elif self.runtime.status == 'running':
                command_ports=[port for port in ports if port['direction']=='input' and port['type']=='BOOL'
                               and port['key'] in {'enable','run','extend','retract','command'} and (port['variableId'] or port['deviceLink'])]
                if command_ports and not any(port['value'] for port in command_ports):
                    status={'state':'waiting','message':'Waiting for the PLC output command. Check the operator START event and the command logic inputs.'}
                elif component['kind'] in {'motor','vfd','servo','velocity_servo','cylinder'}:
                    operating=bool(state['current'].get('running') or state['current'].get('moving'))
                    status={'state':'running' if operating else 'waiting','message':'Physical model is responding to the PLC command.' if operating else 'PLC command received; waiting for the configured delay, ramp or end position.'}
                else:status = {'state': 'active', 'message': 'Generic model active at supported PLC scan boundaries.'}
            else:
                status = {'state': 'ready', 'message': 'Generic model ready. Explicit Run or Single scan is required; paused/stopped devices do not advance.'}
            missing=[port['label'] for port in ports if port.get('required') and not (port['variableId'] or port['deviceLink'])]
            feedback_missing=component['kind'] in {'motor','vfd','servo','velocity_servo','cylinder'} and not any(port['direction']=='output' and (port['variableId'] or port['feedsDevice']) for port in ports)
            action=('Connect required PLC signals: '+', '.join(missing) if missing else
                    'No PLC feedback tag is connected. Configure feedback if the PLC sequence requires it.' if feedback_missing else
                    status['message'] if status['state'] in {'error','blocked','fault'} else '')
            mode='manual' if component['kind']=='pushbutton' or component['kind'] in {'digital_input','analog_input'} and not component['config'].get('automatic') else 'automatic'
            result.append({**deepcopy(component), 'status': status, 'ports': ports, 'current': deepcopy(state['current']),
                           'mode':mode,'actionRequired':action,
                           'updatedAtMs': state['updatedAtMs'], 'faultSinceMs': state.get('faultSinceMs'), 'model': 'generic', 'physicalConnection': False})
        return result
