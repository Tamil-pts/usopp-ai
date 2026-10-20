"""Physical graph from B&R hardware connections and saved topology coordinates."""
from pathlib import Path
import math
import re
import xml.etree.ElementTree as ET

from .module_help import module_details


def tag(node):
    return node.tag.rsplit('}', 1)[-1].lower()


def enrich_hardware(hardware, sources, configuration):
    raw, positions, links = {}, {}, []
    prefix = str(configuration or 'unresolved') + ':'
    for source, text in sources.items():
        if Path(source).suffix.lower() not in {'.hw', '.hwl'} or not text.strip(): continue
        try: doc = ET.fromstring(text)
        except ET.ParseError: continue
        for node in doc.iter():
            if tag(node) == 'module' and node.get('Name'):
                if node.get('X') is not None and node.get('Y') is not None:
                    try:
                        x, y = float(node.get('X')), float(node.get('Y'))
                        if math.isfinite(x) and math.isfinite(y): positions[node.get('Name')] = {'x': x, 'y': y, 'source': source}
                    except ValueError: pass
                elif Path(source).suffix.lower() == '.hw':
                    raw[node.get('Name')] = (node, source)
            if tag(node) == 'link':
                links.append({'from': node.get('From'), 'to': node.get('To'), 'fromPort': node.get('FromPort'),
                              'toPort': node.get('ToPort'), 'source': source,
                              'points': [dict(p.attrib) for p in node if tag(p) == 'point']})
    units = hardware.get('controllers', []) + hardware.get('modules', [])
    by_name = {unit['name']: unit for unit in units}
    owners, terminals = {}, {}
    for name, (node, source) in raw.items():
        if name not in by_name: continue
        for connection in node:
            if tag(connection) != 'connection': continue
            port, target = connection.get('Connector', ''), connection.get('TargetModule')
            if port == 'SL' and connection.get('TargetConnector') == 'SL1': owners[target] = name
            if port.startswith('SS'): terminals[target] = name
    edges, seen, raw_edges = [], set(), []
    for name, (node, source) in raw.items():
        for connection in node:
            if tag(connection) != 'connection': continue
            target, port, target_port = connection.get('TargetModule', ''), connection.get('Connector', ''), connection.get('TargetConnector', '')
            raw_edges.append({'from': prefix+name, 'to': prefix+target, 'source': source, **dict(connection.attrib)})
            child, parent = owners.get(name, name), owners.get(target, target)
            if child == parent or child not in by_name or parent not in by_name: continue
            if name in terminals or target in terminals or port.startswith('SS'): continue
            bus = ('X2X' if 'X2X' in port.upper()+target_port.upper() else 'USB' if 'USB' in port.upper()+target_port.upper()
                   else 'POWERLINK' if 'PLK' in port.upper()+target_port.upper() else 'Ethernet' if 'ETH' in port.upper()+target_port.upper()
                   else 'Local slot' if port == 'SL' else 'Configured link')
            key = tuple(sorted((child, parent)))
            if key in seen: continue
            seen.add(key)
            matching = next((link for link in links if {link['from'], link['to']} == {child, parent}), None)
            edges.append({'from': prefix+parent, 'to': prefix+child, 'bus': bus,
                          'fromPort': target_port, 'toPort': port, 'source': source,
                          'external': any(tag(n) == 'cable' for n in connection) or bool(matching),
                          'layoutLink': matching, 'via': [prefix+n for n in (target, name) if n not in {parent, child}]})
    accessories = []
    for name, (node, source) in raw.items():
        if name in by_name: continue
        accessories.append({'id': prefix+name, 'name': name, 'model': node.get('Type'), 'source': source,
                            'hostId': prefix+owners.get(name, terminals.get(name)) if name in owners or name in terminals else None,
                            'role': 'Terminal block' if name in terminals else 'Bus/base module',
                            'position': positions.get(name)})
    children = {}
    for edge in edges: children.setdefault(edge['from'], []).append(edge)
    def natural(node):
        return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', node)]
    counters, visited = {}, set()
    def visit(identity, group=None):
        if identity in visited: return
        visited.add(identity)
        for edge in sorted(children.get(identity, []), key=lambda e: natural(e['to'])):
            row = by_name[edge['to'][len(prefix):]]
            selected_group = group
            if group is None or edge['external'] or edge['fromPort'].startswith('IF'):
                selected_group = edge['from'] + '/' + edge['fromPort']
            if edge['bus'] != 'Local slot':
                counters[selected_group] = counters.get(selected_group, 0) + 1
                row.update(station='ST'+str(counters[selected_group]), interfacePath=selected_group, parentId=edge['from'], bus=edge['bus'])
            else:
                row.update(station=edge['fromPort'], parentId=edge['from'], bus=edge['bus'])
            visit(row['id'], selected_group)
    for controller in hardware.get('controllers', []): visit(controller['id'])
    for row in units:
        row['position'] = positions.get(row['name'])
        reference = module_details(row.get('model') or '')
        row['documentation'] = {key: reference.get(key) for key in ('available', 'scope', 'family', 'topics', 'images', 'summary')}
        if row.get('type') == 'Unresolved module type':
            row['type'] = reference.get('type') or ('CPU base' if str(row.get('model', '')).startswith('X20BB') else
                          'USB mass storage' if str(row.get('model', '')).lower() == 'usbms01' else 'Unresolved module type')
        row['channelCount'] = reference.get('channelCount')
        row['capacitySource'] = 'B&R '+str(reference.get('scope'))+' reference' if reference.get('channelCount') is not None else None
    for row in units:
        if row.get('type') == 'CPU base':
            accessories.append({**row, 'hostId': prefix+owners[row['name']] if row['name'] in owners else None, 'role': 'CPU base'})
    hardware['accessories'] = accessories
    hardware['connections'] = raw_edges
    hardware['topology'] = {'nodes': [dict(row) for row in units if row.get('type') != 'CPU base'], 'edges': edges, 'layoutLinks': links,
                            'positionSource': 'Hardware.hwl' if positions else 'Connections only; no saved layout',
                            'adapterVersion': 2}
    hardware['adapterVersion'] = 2
    return hardware
