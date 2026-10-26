"""A runtime-facing adapter over the existing, resource-aware HMI layout parser."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from python_engine.compare import hmi_screen_layout, _hmi_entities


def binding(value):
    source = re.search(r'Source\[([^\]]+)\]', str(value or ''), re.I)
    if source and source[1].casefold() != 'global':
        # Named/local VC data sources require their .dso scope mapping. Never
        # substitute an unrelated global PLC variable with the same name.
        return None
    match = re.search(r'Variable\[(.*)\]$', str(value or ''), re.I)
    if not match:
        return None
    # VC global Local.* addresses refer to the PLC data source, not an IEC Local struct.
    return re.sub(r'^Local\.', '', match[1], flags=re.I)


def read_hmi(root, sources, diagnostics, cancel=None, variables=None):
    pages, groups, cache, assets, alarms, snippets = [], {}, {}, {}, [], {}
    aliases = {};inherited_aliases={}
    by_name = {}
    program_scopes={str(v.get('scope','')).replace('\\','/').rsplit('/',1)[-1].casefold() for v in variables or [] if v.get('scope')!='@global'}
    for variable in variables or []:
        by_name.setdefault(variable.get('name', ''), []).append(variable)
    for path, content in sources.items():
        if Path(path).suffix.lower() != '.dso': continue
        try:
            doc = ET.fromstring(content)
        except ET.ParseError:
            continue
        datasource = doc.get('Name', Path(path).stem)
        def visit(node, names=(), program=None, variable_path=()):
            kind = node.tag.rsplit('}', 1)[-1].lower()
            if kind == 'folder':
                props = {p.get('Name'): p.get('Value') for p in node if p.tag.rsplit('}', 1)[-1].lower() == 'property'}
                name = node.get('Name', '')
                names = (*names, name)
                if props.get('FolderType') == 'Program':
                    program, variable_path = name, ()
                else:
                    variable_path = (*variable_path, name)
            if kind == 'datapoint':
                inherited_note=None
                name = node.get('Name', '')
                variable = '.'.join((*variable_path, name))
                candidates = [v for v in by_name.get(variable.split('.')[0], [])
                              if (str(v.get('scope', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold() == str(program).casefold() if program
                                   else str(v.get('scope', '')).casefold() in {'', 'global', '@global'})]
                # A program can reference an inherited global without a local
                # declaration. Resolve only an exact declared global of the
                # source DSO type, and report this stale program-folder alias.
                if not candidates and program and str(program).casefold() in program_scopes:
                    datatype=next((p.get('Value') for p in node if p.get('Name')=='PLCType'),None)
                    inherited=[v for v in by_name.get(variable,[]) if v.get('scope')=='@global' and str(v.get('type','')).casefold()==str(datatype).casefold()]
                    if len(inherited)==1:
                        candidates=inherited
                        diagnostics.append({'severity':'warning','code':'hmi-dso-inherited-global','source':path,
                            'message':f'{datasource}.{program}.{variable} has no local declaration; connected to exact declared global {inherited[0]["id"]} ({datatype}). Review the source DSO program-folder alias.'})
                        inherited_note=diagnostics[-1]['message']
                if len(candidates) == 1:
                    suffix = variable.partition('.')[2]
                    resolved = candidates[0]['id'] + ('.' + suffix if suffix else '')
                    alias = '.'.join((datasource, *names, name))
                    aliases[alias] = resolved
                    if datasource.casefold() == 'local': aliases['.'.join((*names, name))] = resolved
                    if inherited_note:
                        inherited_aliases[alias]=inherited_note
                        if datasource.casefold()=='local':inherited_aliases['.'.join((*names,name))]=inherited_note
            for child in node:
                if child.tag.rsplit('}', 1)[-1].lower() not in {'property'}: visit(child, names, program, variable_path)
        visit(doc)
    def resolve_binding(value):
        raw = binding(value)
        if raw in aliases: return aliases[raw]
        choices = [v for v in by_name.get(str(raw).split('.', 1)[0], []) if v.get('scope') == '@global']
        if len(choices) == 1:
            suffix = str(raw).partition('.')[2]
            return choices[0]['id'] + ('.' + suffix if suffix else '')
        return raw

    def group_path(raw, source):
        match = re.search(r'TextGroup\[([^\]]+)\]', str(raw or ''))
        if not match: return None
        name = match[1] + '.txtgrp'
        folder = Path(source).parent.parent
        # Resolve the current HMI target before shared resources. No cross-target basename guessing.
        for path in (folder / 'TextGroups' / name, Path('Logical/VCShared/TextGroups') / name):
            if path.as_posix() in sources: return path.as_posix()
        return None
    targets = {}
    for source in sorted({*sources, *(str(Path(p).parent.parent / 'Package.vcp').replace('\\', '/') for p in sources if p.lower().endswith('.page'))}):
        if not source.lower().endswith('.vcp'): continue
        try:
            text = sources.get(source)
            path = (Path(root) / source).resolve()
            if not path.is_relative_to(Path(root).resolve()): continue
            doc = ET.fromstring(text if text is not None else path.read_bytes())
            props = {n.get('Name'): n.get('Value', '') for n in doc if n.tag.rsplit('}', 1)[-1].lower() == 'property'}
            targets[Path(source).parent.as_posix()] = {'source': source, 'properties': props,
                'currentPageBinding': resolve_binding(props.get('PageCurrentDatapoint')),
                'changePageBinding': resolve_binding(props.get('PageChangeDatapoint'))}
        except (OSError, ET.ParseError): continue
    local_keys = {}
    def layer_keys(source, layer_id):
        """VC4 local keys belong to the active owning layer, never another page.

        See bundled help keys_keyactions_local/global.html. A central key with
        actions is global; a central empty definition delegates to local mapping.
        """
        key = (source, layer_id)
        if key in local_keys: return local_keys[key]
        result = {}
        local_keys[key] = result
        path = Path(source)
        reference = re.fullmatch(r'Source\[(local|global)\]\.Layer\[([^\]]+)\]', layer_id, re.I)
        if reference:
            home = path.parent.parent if reference[1].lower() == 'local' else path.parent.parent.parent / 'VCShared'
            folder = home / 'Layers'
            path = folder / (reference[2] + '.layer')
            if not (Path(root) / path).resolve().is_relative_to((Path(root) / folder).resolve()): return result
        try:
            text = sources.get(path.as_posix())
            doc = ET.fromstring(text if text is not None else (Path(root) / path).read_bytes())
        except (ET.ParseError, OSError): return result
        tag = lambda n: n.tag.rsplit('}', 1)[-1].lower()
        if not reference:
            doc = next((n for n in doc.iter() if tag(n) == 'layer' and n.get('Name') == layer_id), doc)
        for mapping in doc:
            if tag(mapping) != 'keymapping': continue
            for node in mapping:
                if tag(node) != 'virtualkey' or not node.get('Name'): continue
                actions = []
                for action in node.iter():
                    if tag(action) != 'keyaction': continue
                    props = {n.get('Name'): n.get('Value', '') for n in action if tag(n) == 'property'}
                    class_id = str(action.get('ClassId', '')).upper()
                    actions.append({**props, 'ClassId': class_id,
                                    'Type': 'Change' if class_id == '0X00000160' else 'Key action'})
                result[node.get('Name').casefold()] = {'name': node.get('Name'), 'actions': actions, 'source': path.as_posix()}
        return result
    for source, text in sources.items():
        if cancel is not None and cancel.is_set():
            raise InterruptedError('Project analysis cancelled.')
        suffix = Path(source).suffix.casefold()
        if suffix == '.algrp':
            try:
                doc = ET.fromstring(text)
                props = {n.get('Name'): n.get('Value', '') for n in doc if n.tag.rsplit('}', 1)[-1].lower() == 'property'}
                image = resolve_binding(props.get('AlarmImage'))
                index_map = {n.get('ID'): n.get('Value') for n in doc.iter() if n.tag.rsplit('}', 1)[-1].lower() == 'index'}
                captions = {}
                for layer in doc.iter():
                    if layer.tag.rsplit('}', 1)[-1].lower() == 'textlayer':
                        for item in layer:
                            index = index_map.get(item.get('ID'))
                            if index is not None: captions.setdefault(index, {})[layer.get('LanguageId', 'en')] = item.get('Value', '')
                offset = int(props.get('ImageOffset', 0))
                items = [{'index': int(n.get('Index')), 'binding': f'{image}[{int(n.get("Index"))+offset}]' if image else None,
                          'text': captions.get(n.get('Index'), {}).get('en') or next(iter(captions.get(n.get('Index'), {}).values()), 'Alarm ' + n.get('Index', '?'))}
                         for n in doc.iter() if n.tag.rsplit('}', 1)[-1].lower() == 'alarm' and n.get('Index', '').isdigit()]
                alarms.append({'name': doc.get('Name', Path(source).stem), 'index': int(props['Index']) if str(props.get('Index','')).isdigit() else None, 'source': source, 'binding': image, 'items': items,
                               'limitation': 'Live AlarmImage states only; vendor history, latching and acknowledgement are not emulated.'})
            except (ValueError, ET.ParseError) as error:
                diagnostics.append({'severity': 'warning', 'code': 'hmi-alarm-unresolved', 'source': source, 'message': str(error)})
        if suffix == '.txtgrp':
            _, records = _hmi_entities(text, suffix)
            groups[source] = {record['index']: {
                key.removeprefix('Language: '): value
                for key, value in record['properties'].items() if key.startswith('Language: ')}
                for record in records.values()}
            doc = ET.fromstring(text)
            snippets[source] = {}
            for node in doc.iter():
                if node.tag.rsplit('}', 1)[-1].lower() != 'textsnippet': continue
                props = {n.get('Name'): n.get('Value', '') for n in node if n.tag.rsplit('}', 1)[-1].lower() == 'property'}
                snippets[source][node.get('Name', '')] = {'classId': node.get('ClassId'),
                    'binding': resolve_binding(props.get('Datapoint')), 'properties': props}
        if suffix != '.page':
            continue
        layout = hmi_screen_layout(text, Path(root) / source, cache)
        if not layout:
            diagnostics.append({'severity': 'warning', 'code': 'hmi-unresolved', 'source': source,
                                'message': 'HMI page could not be decoded by the existing page parser.'})
            continue
        for identity, asset in layout.get('bitmap_assets', {}).items():
            if identity not in assets and sum(len(a.get('data_uri', '')) for a in assets.values()) + len(asset.get('data_uri', '')) <= 16*1024*1024:
                assets[identity] = asset
        objects = []
        layers = []
        for layer in sorted(layout.get('layers', []), key=lambda item: item.get('order', 0)):
            layer_props = layer.get('properties', {})
            layer_state = {'id': layer['id'], 'name': layer['name'], 'properties': layer_props, 'order': layer.get('order', 0),
                           'statusBinding': resolve_binding(layer_props.get('StatusDatapoint')),
                           'statusConfigured': 'Variable[' in layer_props.get('StatusDatapoint', '')}
            layers.append(layer_state)
            for control in layer.get('controls', []):
                props = dict(control.get('effective_properties', {}))
                own_binding = resolve_binding(props.get('ValueDatapoint'))
                completion = resolve_binding(props.get('CompletionDatapoint'))
                action = None
                actions = []
                virtual_key = control.get('virtual_key') or {}
                key_match = re.search(r'VirtualKey\[([^\]]+)\]', props.get('VirtualKey', ''), re.I)
                if key_match and not virtual_key.get('actions'):
                    virtual_key = layer_keys(source, layer['id']).get(key_match[1].casefold(), virtual_key)
                key_source = virtual_key.get('source') or control.get('virtual_key_source', '')
                if key_source:
                    key_path=Path(key_source)
                    if key_path.is_absolute():
                        key_source=key_path.resolve().relative_to(Path(root).resolve()).as_posix() if key_path.resolve().is_relative_to(Path(root).resolve()) else ''
                    else:key_source=key_path.as_posix()
                if key_source:
                    props['Resolved VirtualKey source'] = key_source
                for index, operation in enumerate(virtual_key.get('actions', []), 1):
                    for name, value in operation.items(): props[f'VirtualKey action {index} / {name}'] = value
                key_actions = virtual_key.get('actions', [])
                if completion and props.get('CompletionValue') is not None:
                    completion_action = {'kind': 'write', 'variable': completion, 'value': props['CompletionValue']}
                else:
                    completion_action = None
                for operation in key_actions:
                    before = len(actions)
                    operation_binding = resolve_binding(operation.get('ValueDatapoint'))
                    class_id = str(operation.get('ClassId', '')).upper()
                    if class_id in {'0X00000161', '0X0000016A', '0X0000016B'} and operation_binding:
                        actions.append({'kind': {'0X00000161': 'write', '0X0000016A': 'toggle', '0X0000016B': 'momentary'}[class_id],
                                        'variable': operation_binding, 'value': operation.get('SetValue', operation.get('Value', '1')),
                                        'resetValue': operation.get('ResetValue', '0'), 'classId': class_id})
                    page = re.search(r'Page\[([^\]]+)\]', operation.get('Page', ''), re.I)
                    if class_id == '0X00000160' and page:
                        actions.append({'kind': 'navigate', 'page': page[1], 'classId': class_id})
                    elif class_id == '0X00000160' and operation.get('Target') == 'Back':
                        actions.append({'kind': 'back', 'classId': class_id})
                    elif class_id == '0X0000016E':
                        actions.append({'kind': 'control', 'control': operation.get('Control'),
                                        'command': operation.get('Action'), 'classId': class_id})
                    if len(actions) == before:
                        actions.append({'kind': 'unsupported', 'classId': class_id,
                                        'reason': 'This source key function is not simulated.'})
                    actions[-1]['properties'] = operation
                    actions[-1]['function'] = {'0X00000160':'Change page','0X00000161':'Set datapoint',
                        '0X00000164':'Help','0X00000165':'Unicode character','0X00000166':'Input control',
                        '0X00000167':'Move cursor','0X00000168':'Up/down datapoint','0X00000169':'Focus dependent',
                        '0X0000016A':'Toggle datapoint','0X0000016B':'Momentary datapoint','0X0000016C':'Change language',
                        '0X0000016E':'Control dependent','0X0000016F':'Clipboard'}.get(class_id,'Source key function '+class_id)
                    actions[-1]['lockingBinding'] = resolve_binding(operation.get('LockingDatapoint'))
                    completion_binding=resolve_binding(operation.get('CompletionDatapoint'))
                    if completion_binding:actions[-1]['completion']={'variable':completion_binding,'value':operation.get('CompletionValue','0')}
                action = actions[0] if actions else None
                kind = control['class'].casefold()
                kind = {'0x00001005': 'bitmap', '0x00001009': 'alarm', '0x0000100d': 'line',
                        '0x0000100a': 'datetime', '0x00001008': 'listbox', '0x0000100c': 'password'}.get(str(control.get('class_id', '')).lower(), kind)
                if kind == 'dropdown' and not own_binding:
                    own_binding = resolve_binding(props.get('IndexDatapoint'))
                supported = kind in {'button', 'hotspot', 'text', 'numeric', 'string', 'shape', 'dropdown', 'bitmap', 'line', 'datetime', 'alarm', 'listbox', 'password'}
                texts = control.get('texts', {})
                label = texts.get('en') or next(iter(texts.values()), None) or props.get('Text', '')
                obj = {'id': f'{source}:{control["id"]}', 'name': control['name'], 'kind': kind,
                       'x': layer.get('left', 0) + control['left'],
                       'y': layer.get('top', 0) + control['top'],
                       'width': control['width'], 'height': control['height'], 'text': label,
                       'texts': texts, 'binding': own_binding, 'action': action, 'actions': actions, 'completion': completion_action,
                       'keySource': key_source,
                       'textBinding': resolve_binding(props.get('TextDatapoint')),
                       'textIndexBinding': resolve_binding(props.get('TextIndexDatapoint') or props.get('IndexDatapoint')),
                       'textGroup': group_path(props.get('TextGroup'), source),
                       'bindingNotices':sorted({inherited_aliases[binding(raw)] for raw in props.values() if binding(raw) in inherited_aliases}),
                       'lockingBinding': resolve_binding(props.get('LockingDatapoint')),
                       'passwordLevelBinding': resolve_binding(props.get('LevelDatapoint')),
                       'bitmaps': control.get('bitmaps', {}),
                       'bitmapIndexBinding': resolve_binding(props.get('BitmapIndexDatapoint') or props.get('IndexDatapoint')),
                       'minBinding': resolve_binding(props.get('MinDatapoint')), 'maxBinding': resolve_binding(props.get('MaxDatapoint')),
                       'input': props.get('Input', '').casefold() == 'true',
                       # VisibilityMode and EditingMode are editor settings, not runtime permission bits.
                       'visible': True, 'layerState': layer_state,
                       'visibilityBinding': resolve_binding(props.get('VisibilityDatapoint')),
                       'properties': props, 'source': source, 'supported': supported,
                       'classId': control.get('class_id'), 'layer': layer['name']}
                if not supported:
                    obj['limitation'] = 'Proprietary HMI control: displayed as a labeled placeholder.'
                if kind in {'button', 'hotspot'} and action is None:
                    obj['limitation'] = ('This active source hotspot covers input without issuing a command. Inspect its status tag and PLC writers.'
                                         if kind=='hotspot' else 'No source command or navigation action is configured. Inspect the virtual key.')
                unresolved = [key for key, value in props.items()
                              if key.endswith('Datapoint') and 'Variable[' in str(value)
                              and resolve_binding(value) is None]
                if unresolved:
                    diagnostics.append({'severity': 'warning', 'code': 'hmi-datasource-unresolved',
                                        'source': source, 'message':
                                        f'{control["name"]}: unresolved data source for {", ".join(unresolved)}; '
                                        'the binding is not connected to virtual memory.'})
                obj['statusBinding'] = resolve_binding(props.get('StatusDatapoint'))
                obj['statusConfigured'] = 'Variable[' in props.get('StatusDatapoint', '')
                objects.append(obj)
        target = Path(source).parent.parent.as_posix()
        pages.append({'id': source, 'name': layout['name'], 'source': source, 'target': target,
                      'runtimeBindings': targets.get(target, {}),
                      'width': layout['width'], 'height': layout['height'], 'objects': objects, 'layers': layers,
                      'properties': layout.get('properties', {}), 'palette': layout.get('palette', {}),
                      'warnings': layout.get('warnings', [])})
        diagnostics.extend({'severity': 'warning', 'code': 'hmi-resource-unresolved', 'source': source,
                            'message': message} for message in layout.get('warnings', []))
    from .hmi_keys import target_control
    for page in pages:
        for control in page['objects']:
            for action in control.get('actions',[]):
                if action['kind']!='control':continue
                try:target_control(page,action)
                except ValueError as error:
                    action['kind']='unsupported';action['reason']=str(error)
    from .hmi_data import read_data_objects
    data_objects=read_data_objects(root,sources,diagnostics)
    return {'pages': pages, 'targets': targets, 'textGroups': groups, 'textSnippets': snippets,
            'bitmapAssets': assets, 'alarmGroups': alarms, 'dataObjects':data_objects, 'adapterVersion': 7}
