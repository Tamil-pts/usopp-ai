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
    aliases = {}
    by_name = {}
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
                name = node.get('Name', '')
                variable = '.'.join((*variable_path, name))
                candidates = [v for v in by_name.get(variable.split('.')[0], [])
                              if (str(v.get('scope', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold() == str(program).casefold() if program
                                   else str(v.get('scope', '')).casefold() in {'', 'global', '@global'})]
                if len(candidates) == 1:
                    suffix = variable.partition('.')[2]
                    resolved = candidates[0]['id'] + ('.' + suffix if suffix else '')
                    alias = '.'.join((datasource, *names, name))
                    aliases[alias] = resolved
                    if datasource.casefold() == 'local': aliases['.'.join((*names, name))] = resolved
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
                alarms.append({'name': doc.get('Name', Path(source).stem), 'source': source, 'binding': image, 'items': items,
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
            layer_state = {'id': layer['id'], 'name': layer['name'], 'properties': layer_props,
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
                    props['Resolved VirtualKey source'] = key_source
                for index, operation in enumerate(virtual_key.get('actions', []), 1):
                    for name, value in operation.items(): props[f'VirtualKey action {index} / {name}'] = value
                key_actions = virtual_key.get('actions', [])
                if completion and props.get('CompletionValue') is not None:
                    completion_action = {'kind': 'write', 'variable': completion, 'value': props['CompletionValue']}
                else:
                    completion_action = None
                for operation in key_actions:
                    operation_binding = resolve_binding(operation.get('ValueDatapoint'))
                    class_id = str(operation.get('ClassId', '')).upper()
                    if class_id in {'0X00000161', '0X0000016A', '0X0000016B'} and operation_binding:
                        actions.append({'kind': {'0X00000161': 'write', '0X0000016A': 'toggle', '0X0000016B': 'momentary'}[class_id],
                                        'variable': operation_binding, 'value': operation.get('SetValue', operation.get('Value', '1')),
                                        'resetValue': operation.get('ResetValue', '0'), 'classId': class_id})
                    page = re.search(r'Page\[([^\]]+)\]', operation.get('Page', ''), re.I)
                    if operation.get('Type') == 'Change' and page:
                        actions.append({'kind': 'navigate', 'page': page[1]})
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
                       'textIndexBinding': resolve_binding(props.get('IndexDatapoint')),
                       'textGroup': group_path(props.get('TextGroup'), source),
                       'lockingBinding': resolve_binding(props.get('LockingDatapoint')),
                       'passwordLevelBinding': resolve_binding(props.get('LevelDatapoint')),
                       'bitmaps': control.get('bitmaps', {}),
                       'bitmapIndexBinding': resolve_binding(props.get('IndexDatapoint') or props.get('BitmapIndex')),
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
                    obj['limitation'] = 'No supported command or navigation action was resolved; interaction is disabled.'
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
        pages.append({'id': source, 'name': layout['name'], 'source': source,
                      'width': layout['width'], 'height': layout['height'], 'objects': objects, 'layers': layers,
                      'properties': layout.get('properties', {}), 'palette': layout.get('palette', {}),
                      'warnings': layout.get('warnings', [])})
        diagnostics.extend({'severity': 'warning', 'code': 'hmi-resource-unresolved', 'source': source,
                            'message': message} for message in layout.get('warnings', []))
    return {'pages': pages, 'textGroups': groups, 'textSnippets': snippets,
            'bitmapAssets': assets, 'alarmGroups': alarms, 'adapterVersion': 5}
