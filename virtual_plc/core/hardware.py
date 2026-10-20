"""Adapt the existing B&R hardware and I/O readers without vendor guesses."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from python_engine.compare import parse_hardware_modules, parse_io_mappings


def module_key(module):
    """Natural station order within its configured rack/path (ST2 before ST10)."""
    name = str(module.get('name', ''))
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r'(\d+)', name))


def order_hardware(hardware):
    for collection in ('controllers', 'modules'):
        hardware[collection] = sorted(hardware.get(collection, []), key=module_key)
        for index, module in enumerate(hardware[collection]): module['order'] = index
    order = {module['id']: i for i, module in enumerate(hardware.get('controllers', []) + hardware.get('modules', []))}
    hardware['channels'] = sorted(hardware.get('channels', []), key=lambda c: (
        order.get(c.get('moduleId'), 99999), module_key({'name': c.get('name', '')})))
    return hardware


def tag(node):
    return node.tag.rsplit('}', 1)[-1].casefold()


def read_hardware(sources, configuration, diagnostics):
    result = {'controllers': [], 'modules': [], 'connections': [], 'channels': [],
              'unresolved': [], 'taskIntervals': {}, 'taskIntervalsByController': {}}
    modules = {}
    # Nonempty Hardware.hw is authoritative when .hwl is only an empty editor sidecar.
    hardware = [(path, text) for path, text in sources.items()
                if Path(path).suffix.casefold() in {'.hw', '.hwl'} and text.strip()]
    hardware.sort(key=lambda item: (Path(item[0]).suffix.casefold() != '.hw', item[0]))
    for path, text in hardware:
        try:
            root = ET.fromstring(text)
        except ET.ParseError as error:
            result['unresolved'].append({'source': path, 'message': f'Hardware XML: {error}'})
            continue
        decoded = parse_hardware_modules(text)
        allowed = {record['properties']['Object name']: record['properties'] for record in decoded.values()}
        for node in root.iter():
            if tag(node) != 'module' or node.get('Name') not in allowed:
                continue
            name = node.get('Name')
            identity = f'{configuration or "unresolved"}:{name}'
            if identity in modules:
                continue
            properties = allowed[name]
            model = properties.get('Module type') or None
            controller = name.casefold() in {'plc1', 'cpu'} or bool(re.match(r'^(?:X20CP\d|4PP\d+\.\d|PP\d+\.\d)', model or '', re.I))
            # Model prefixes establish a family, never a physical channel count.
            family = ('CPU' if controller else
                      'Digital input' if re.match(r'X20DI', model or '', re.I) else
                      'Digital output' if re.match(r'X20DO', model or '', re.I) else
                      'Analog input' if re.match(r'X20AI', model or '', re.I) else
                      'Analog output' if re.match(r'X20AO', model or '', re.I) else 'Unresolved module type')
            module = {'id': identity, 'name': name, 'model': model, 'type': family,
                      'order': len(modules), 'source': path, 'configuration': configuration,
                      'channelCount': None, 'mappedChannelCount': 0, 'channels': [],
                      'properties': dict(node.attrib), 'parameters': {}}
            for child in node:
                if tag(child) == 'parameter':
                    module['parameters'][child.get('ID', '')] = child.get('Value', '')
                elif tag(child) == 'connection':
                    result['connections'].append({'from': identity, 'to': f'{configuration or "unresolved"}:{child.get("TargetModule", "")}',
                                                   'source': path, **dict(child.attrib)})
            if controller:
                controller_intervals = result['taskIntervalsByController'].setdefault(name.casefold(), {})
                for key, value in module['parameters'].items():
                    match = re.fullmatch(r'Cyclic(\d+)Duration', key, re.I)
                    if match:
                        try:
                            duration = float(value) / 1000
                            if duration > 0:
                                controller_intervals[f'Cyclic#{int(match[1])}'.casefold()] = duration
                        except (TypeError, ValueError):
                            pass
            modules[identity] = module
            result['controllers' if controller else 'modules'].append(module)
    if len(result['controllers']) == 1:
        result['taskIntervals'] = result['taskIntervalsByController'].get(result['controllers'][0]['name'].casefold(), {})
    for path, text in sources.items():
        if Path(path).suffix.casefold() != '.iom':
            continue
        for record in parse_io_mappings(text).values():
            props = record['properties']
            identity = f'{configuration or "unresolved"}:{props["Module"]}'
            variable = props['PLC tag'].removeprefix('::')
            channel = {'id': f'{identity}:{props["Channel"]}', 'signalId': f'{identity}:{props["Channel"]}',
                       'name': props['Channel'], 'moduleId': identity, 'module': props['Module'],
                       'address': props['Address'], 'variable': variable,
                       'direction': props['Direction'].casefold(), 'type': None, 'source': path,
                       'quality': 'not-running', 'status': 'not-running', 'value': None,
                       'timestamp': None, 'unit': None}
            channel['line'] = next((index for index, line in enumerate(text.splitlines(), 1)
                                    if props['Address'] in line and props['PLC tag'] in line), 1)
            result['channels'].append(channel)
            if identity in modules:
                modules[identity]['channels'].append(channel['id'])
                modules[identity]['mappedChannelCount'] += 1
            else:
                result['unresolved'].append({'source': path, 'message': f'I/O mapping {props["Address"]} references unknown module {props["Module"]}.'})
    if not result['controllers']:
        result['unresolved'].append({'message': 'No CPU module could be established from the selected hardware configuration.'})
    diagnostics.extend({'severity': 'warning', 'code': 'hardware-unresolved', **item} for item in result['unresolved'])
    from .hardware_topology import enrich_hardware
    return order_hardware(enrich_hardware(result, sources, configuration))
