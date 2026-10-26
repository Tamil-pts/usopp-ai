"""VC4 input and visibility rules over virtual memory, never original PLC files.

Reference: controls/ref-commonproperty_statusdatapoint.html and
ref-commonproperty_locking.html in the bundled B&R help. Bit 0 hides, bit 1
locks. Editor VisibilityMode has no effect during runtime.
"""
import math
import re
import hmac
from pathlib import PurePosixPath
from .hmi_text import expand_text


def navigation_page(pages,current,name):
    exact=[p for p in pages if p.get('id')==name or p.get('source')==name]
    if len(exact)==1:return exact[0]
    choices=[p for p in pages if p.get('name')==name]
    parent=PurePosixPath(current.get('source','')).parent
    local=[p for p in choices if PurePosixPath(p.get('source','')).parent==parent]
    if len(local)==1:return local[0]
    if len(choices)==1:return choices[0]
    raise ValueError('HMI navigation target is missing or ambiguous for this HMI target: '+str(name))


def control_state(control, runtime):
    visible, reasons, visibility_reasons, words = True, [], [], {}
    for key, item in (('layer', control.get('layerState', {})), ('control', control)):
        if not item.get('statusConfigured') and not item.get('statusBinding'): continue
        try:
            raw = runtime.get_value(item.get('statusBinding') or '')
            if not isinstance(raw, (int, bool)) or not -32768 <= raw <= 65535:
                raise ValueError('Status word must be a 16-bit integer')
            word = int(raw) & 0xffff
            words[key] = word
            visible = visible and not bool(word & 1)
            if word & 1: visibility_reasons.append(key.capitalize() + ' status bit 0 hides this item.')
            if word & 2: reasons.append(key.capitalize() + ' status bit 1 locks input.')
        except (ValueError, KeyError, TypeError, IndexError):
            reasons.append(key.capitalize() + ' status binding is unresolved.')
    props = control.get('properties', {})
    mode = str(props.get('Locking') or 'Never').casefold().replace(' ', '')
    if mode != 'never':
        try:
            level = runtime.get_value(control.get('lockingBinding') or '')
            threshold = float(props.get('LockingLevel', 0))
            if not isinstance(level, (int, float)) or not math.isfinite(level) or not math.isfinite(threshold):
                raise ValueError('Unresolved login level')
            if mode == 'datapoint<level': locked = level < threshold
            elif mode == 'datapoint>=level': locked = level >= threshold
            elif mode == 'datapoint=0': locked = level == 0
            else: raise ValueError('Unsupported locking mode')
            if locked: reasons.append(f'Input locked by {props.get("Locking")}; current value {level}, required level {threshold:g}.')
        except (ValueError, KeyError, TypeError, IndexError):
            reasons.append('Login/locking binding or mode is unresolved.')
    return {'visible': visible, 'locked': bool(reasons), 'reason': ' '.join(reasons),
            'visibilityReason': ' '.join(visibility_reasons) or 'Shown by the current source status.', 'statusWords': words}


def covering_control(page, control, runtime):
    # Recheck overlays when confirming a keypad opened earlier. A newly visible
    # login hotspot must also block a stale input dialog.
    objects = page.get('objects', [])
    index = next(i for i, item in enumerate(objects) if item['id'] == control['id'])
    def overlaps(a, b):
        return (a['x'] < b['x'] + b['width'] and b['x'] < a['x'] + a['width']
                and a['y'] < b['y'] + b['height'] and b['y'] < a['y'] + a['height'])
    for cover in objects[index+1:]:
        props=cover.get('properties',{})
        opaque_shape=(cover.get('kind')=='shape' and str(props.get('FillStyle','')).lower()!='transparent'
                      and props.get('BackColor') not in (None,'','None','Transparent'))
        if (cover.get('kind') == 'hotspot' or opaque_shape) and overlaps(control, cover) and control_state(cover, runtime)['visible']:
            return cover
    # Layer BackColor belongs to the editor display, not the runtime surface.
    # See VC4 layer/ref-layer_backcolor.html. Only actual visible controls can
    # cover an input; do not invent a full-screen input barrier for a layer.


def require_input(page, control, runtime):
    state = control_state(control, runtime)
    if not state['visible']: raise ValueError('This HMI control or layer is currently hidden. '+state['visibilityReason'])
    if state['locked']: raise ValueError(state['reason'])
    cover=covering_control(page,control,runtime)
    if cover:raise ValueError('Input is covered by '+cover.get('layer','')+' / '+cover.get('name','HMI overlay')+'. Inspect its status and source key in Layers & controls.')


def writable(runtime, name):
    if not name: raise ValueError('This HMI binding is unresolved.')
    record, reference = runtime.value_reference(name)
    if record.get('forced'): raise ValueError('Release the force before editing this PLC value.')
    if record.get('constant') or record.get('ambiguous'): raise ValueError('This HMI binding is constant or ambiguous.')
    return reference


def write_value(runtime, name, value):
    reference = writable(runtime, name)
    spec = runtime.memory.reference_spec(reference)
    runtime.set_value(name, runtime.memory.coerce(value, spec), return_snapshot=False)


def _password_entries(model, control, runtime):
    """Resolve authentication values privately; callers must never serialize entries."""
    props = control.get('properties', {})
    maximum = int(props.get('MaxLevel') or 0)
    if not 0 <= maximum <= 256: raise ValueError('Password levels must be within 0..256.')
    limit = maximum or 256
    source = props.get('TextSource', '')
    entries, problems, bindings = {}, [], set()
    if source == 'MultipleTexts':
        path = control.get('textGroup')
        group = model.get('hmi', {}).get('textGroups', {}).get(path)
        if group is None: raise ValueError('Password text group is unresolved for this HMI target.')
        offset = int(props.get('TextIndexOffset') or 0)
        snippets = model.get('hmi', {}).get('textSnippets', {}).get(path, {})
        for level in range(1, limit+1):
            captions = group.get(str(level + offset))
            if not captions: continue
            text = captions.get('en', next(iter(captions.values()), ''))
            bindings.update(snippets[name].get('binding') for name in re.findall(r'\{([^{}]+)\}', text)
                            if name in snippets and snippets[name].get('binding'))
            try:
                entries[level] = expand_text(text,snippets,runtime,require_initialized=True)
            except (ValueError, KeyError, TypeError, IndexError) as error:
                problems.append({'level': level, 'state': 'waiting' if str(error) == 'STRING snippet is uninitialized.' else 'unresolved'})
    elif source == 'MultipleStrings':
        items = runtime.get_value(control.get('textBinding') or '')
        bindings.add(control.get('textBinding'))
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            raise ValueError('Password STRING array is unresolved.')
        offset = int(runtime.get_value(control['textIndexBinding'])) if control.get('textIndexBinding') else -1
        for level in range(1, limit+1):
            index = level + offset
            if 0 <= index < len(items):
                if items[index]: entries[level] = items[index]
                else: problems.append({'level': level, 'state': 'waiting'})
    else:
        raise ValueError('Unsupported password text source.')
    return entries, problems, bindings


def password_source_status(model, control, runtime):
    """Only readiness and source locations are public, never authentication values."""
    try:
        entries, problems, bindings = _password_entries(model, control, runtime)
    except (ValueError, KeyError, TypeError, IndexError):
        return {'readyLevels': 0, 'waitingLevels': [], 'message': 'Password source is unresolved. Inspect this control and its text group.', 'producers': []}
    from .compiler import walk_ir
    cache = getattr(runtime, '_hmi_password_producers', None)
    if cache is None: cache = runtime._hmi_password_producers = {}
    producers = []
    for binding in sorted(filter(None, bindings)):
        if binding not in cache:
            found = []
            try:
                record, _ = runtime.value_reference(binding)
                for unit in runtime.units.values():
                    if unit['id'] not in runtime.active_units: continue
                    for section in unit.get('sections', []):
                        for node in walk_ir(section.get('instructions', [])):
                            target = node.get('target', {}) if node.get('op') == 'assign' else {}
                            if target.get('op') != 'ref' or target.get('name') != record['name']: continue
                            try:
                                if runtime.value_reference(target['name'], unit['scope'])[0]['id'] != record['id']: continue
                            except (ValueError, KeyError, TypeError): continue
                            location = {'source': unit['source'], 'line': node.get('line'), 'unitId': unit['id']}
                            if location not in found: found.append(location)
            except (ValueError, KeyError, TypeError): pass
            cache[binding] = found
        for location in cache[binding]:
            for task in runtime.tasks:
                phases=[phase for phase,key in (('cyclic','programs'),('init','initializationPrograms')) if location['unitId'] in task.get(key,[])]
                if not phases:continue
                item = {k: v for k, v in location.items() if k != 'unitId'}
                item.update(task=task['name'],taskId=task['id'],phases=phases,intervalMs=task.get('intervalMs'),
                            nextDueMs=task.get('nextDueMs'),executionCount=task['executionCount'])
                if item not in producers: producers.append(item)
    waiting = [p['level'] for p in problems if p['state'] == 'waiting']
    unresolved = [p['level'] for p in problems if p['state'] == 'unresolved']
    message = (f'{len(waiting)} password source level(s) are waiting for PLC initialization. ' if waiting else '')
    message += (f'{len(unresolved)} level(s) have unresolved snippet formatting or bindings. ' if unresolved else '')
    if not message: message = 'Configured password sources are initialized.' if entries else 'No nonempty password source is configured.'
    return {'readyLevels': sum(bool(v) for v in entries.values()), 'waitingLevels': waiting,
            'unresolvedLevels': unresolved,'configuredLevels':sorted(set(entries)|{p['level'] for p in problems}),
            'levelBinding':control.get('passwordLevelBinding'),'message': message.strip(), 'producers': producers[:24], 'timeMs': runtime.time_ms}


def password_needs_initialization(model,control,runtime,password):
    """A ready source may authenticate without waiting for unrelated empty sources."""
    entries,problems,_=_password_entries(model,control,runtime)
    return any(p['state']=='waiting' for p in problems) and not any(expected and password and
        hmac.compare_digest(str(password).encode('utf-8'),expected.encode('utf-8')) for expected in entries.values())


def _password_level(model, control, runtime, password):
    """Compare locally. Authentication values never enter responses, traces or errors."""
    entries, problems, _ = _password_entries(model, control, runtime)
    # An empty uninitialized PLC password must never authenticate an empty entry.
    matched = next((level for level, expected in sorted(entries.items()) if expected and password and
                    hmac.compare_digest(password.encode('utf-8'), expected.encode('utf-8'))), 0)
    if not matched and problems:
        ready = sum(bool(v) for v in entries.values())
        waiting = sum(p['state'] == 'waiting' for p in problems)
        raise ValueError(f'Password not accepted by the {ready} initialized source level(s). '
                         + (f'{waiting} other level(s) are waiting for the scheduled PLC login program.' if waiting
                            else 'Other levels have unresolved snippet formatting or bindings. Inspect the password source.'))
    return matched


def input_value(model, page, control, runtime, value):
    require_input(page, control, runtime)
    kind, props = control.get('kind'), control.get('properties', {})
    if kind not in {'numeric', 'string', 'dropdown', 'password'}:
        raise ValueError('This control has no supported value input.')
    if kind != 'password' and not control.get('input') and kind != 'dropdown':
        raise ValueError('This HMI field is display-only.')
    if kind == 'password':
        if not isinstance(value, str) or len(value) > min(4096, int(props.get('MaxChars') or 4096)):
            raise ValueError('Password input exceeds the configured character limit.')
        writable(runtime, control.get('passwordLevelBinding'))
        try:
            level = _password_level(model, control, runtime, value)
        except (ValueError, KeyError, TypeError, IndexError):
            write_value(runtime, control.get('passwordLevelBinding'), 0)
            raise
        write_value(runtime, control.get('passwordLevelBinding'), level)
        return {'loginLevel': level}
    if kind == 'numeric':
        if type(value) not in {float, int} or not math.isfinite(value): raise ValueError('Enter a finite numeric value.')
        from .hmi_limits import require_numeric
        require_numeric(control,runtime,value)
    if kind=='dropdown':
        from .hmi_selection import selection_value
        value=selection_value(model,control,runtime,value)
    if kind == 'string' and (not isinstance(value, str) or len(value) > int(props.get('MaxChars') or 4096)):
        raise ValueError('Input exceeds the configured character limit.')
    completion = control.get('completion') or {}
    # Validate both writes before applying either, including forces and leaf types.
    assignments = [(control.get('binding'), value)]
    if completion.get('variable'): assignments.append((completion['variable'], completion['value']))
    converted = [(name, runtime.memory.coerce(raw, runtime.memory.reference_spec(writable(runtime, name))))
                 for name, raw in assignments]
    for name, raw in converted: runtime.set_value(name, raw, return_snapshot=False)
    return {}
