"""Active hardware and interface routes; presence never establishes a drive identity."""
from pathlib import PurePosixPath
import re
import xml.etree.ElementTree as ET


def routes(model, sources, resolve, ref):
    selected = model.get('projectInfo', {}).get('activeConfiguration')
    hardware, interfaces = [], []
    for path, text in sources.items():
        parts = PurePosixPath(path).parts
        if len(parts) < 3 or parts[0].lower() != 'physical' or not selected or parts[1] != selected:
            continue
        if path.lower().endswith('.iom'):
            for m in re.finditer(r'(?m)^\s*([\w.#]+)\s+AT\s+(%[^;\r\n]+)', text):
                name = re.sub(r'^Cyclic#\d+\.', '', m[1])
                signal = resolve(name)
                hardware.append({'signal': signal, 'name': name, 'address': m[2].strip(),
                                 'configuration': selected, 'direction': 'output' if m[2].startswith('%Q') else 'input',
                                 'sources': [ref(path, text.count('\n', 0, m.start()) + 1)]})
        if not path.lower().endswith(('.hw', '.hwl')):
            continue
        try:
            tree = ET.fromstring(text)
        except ET.ParseError:
            continue
        tag = lambda e: e.tag.rsplit('}', 1)[-1].lower()
        for module in tree.iter():
            if tag(module) != 'module':
                continue
            connection = next((c for c in module if tag(c) == 'connection' and c.get('TargetConnector')), None)
            for connector in module:
                if tag(connector) != 'connector':
                    continue
                params = {p.get('ID'): p.get('Value') for p in connector.iter() if tag(p) == 'parameter'}
                mode = str(params.get('DeviceType') or params.get('Mode') or '')
                if not re.search(r'RS232|RS422|RS485|CAN|MODBUS|POWERLINK|ETHERNET', mode, re.I):
                    continue
                alias = connection.get('TargetConnector') + '.' + connector.get('Name', '') if connection is not None else None
                name = connector.get('Name', '')
                position = text.find('Name="' + name + '"', text.find('Name="' + module.get('Name', '') + '"'))
                interfaces.append({'module': module.get('Name'), 'model': module.get('Type'), 'connector': name,
                                   'device': alias, 'mode': mode, 'parameters': params,
                                   'configuration': selected, 'sources': [ref(path, text.count('\n', 0, position) + 1)],
                                   'meaning': 'Configured interface; connected drive and protocol payload require call/data tracing.'})
    return hardware, interfaces
