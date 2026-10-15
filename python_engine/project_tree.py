"""Automation Studio object inventory from scoped files and project descriptors."""
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET


def build_project_tree(root: Path, files: dict, identity: dict) -> dict:
    # Only inventoried files are admitted. Package references cannot reintroduce
    # inactive visualizations/configurations, missing objects or external paths.
    nodes = {}

    def ensure(key, actual, is_file=False):
        if key in nodes:
            return nodes[key]
        name = PurePosixPath(actual).name
        node = {'key': key, 'name': name, 'relative_path': actual,
                'kind': 'file' if is_file else 'package', 'description': '',
                'children': [], 'descriptor': False, 'order': 100000}
        if is_file:
            node['extension'] = PurePosixPath(actual).suffix.lower()
            node['descriptor'] = node['extension'] in {'.pkg', '.prg', '.lby'}
        nodes[key] = node
        parent_key = str(PurePosixPath(key).parent)
        if parent_key != '.':
            parent = ensure(parent_key, str(PurePosixPath(actual).parent))
            parent['children'].append(node)
        return node

    for key, path in files.items():
        ensure(key, path.relative_to(root).as_posix(), True)
    by_casefold = {key.casefold(): node for key, node in nodes.items()}
    # Package/program descriptors are metadata, not comparison objects.
    # Read descriptors only beside already admitted, scoped directories.
    descriptors=dict(files)
    for key,node in list(nodes.items()):
        if node['kind']=='file':continue
        directory=root/node['relative_path']
        try:
            paths=[path for path in directory.iterdir() if path.is_file() and
                   (path.name.casefold()=='package.pkg' or path.suffix.casefold()=='.prg')]
        except OSError:continue
        for path in paths:
            if path.resolve().is_relative_to(root.resolve()):
                descriptors[str(PurePosixPath(key)/path.name)]=path

    def local(tag):
        return tag.rsplit('}', 1)[-1]

    # Package objects provide ordering, descriptions and program/library types.
    # Program and library Files lists preserve the displayed source file order.
    for key, path in descriptors.items():
        if path.suffix.lower() not in {'.pkg', '.prg', '.lby'}:
            continue
        try:
            doc = ET.fromstring(path.read_bytes())
        except (OSError, ET.ParseError):
            continue
        parent_key = str(PurePosixPath(key).parent)
        parent = nodes.get(parent_key)
        if parent and local(doc.tag) in {'Program', 'Library'}:
            parent['kind'] = local(doc.tag).lower()
            if not parent['description']:
                parent['description'] = doc.get('Description', '')
        for container in doc:
            if local(container.tag) not in {'Objects', 'Files'}:
                continue
            for order, obj in enumerate(container):
                if local(obj.tag) not in {'Object', 'File'}:
                    continue
                name = (obj.text or '').strip().replace('\\', '/')
                # The canonical parent already encodes the selected target.
                if not name or name.startswith('/') or ':' in name or '..' in name.split('/'):
                    continue
                child_key = str(PurePosixPath(parent_key) / name)
                child = by_casefold.get(child_key.casefold())
                if child is None:
                    continue
                child['order'] = order
                child['description'] = obj.get('Description', child['description'])
                child['language'] = obj.get('Language', '')
                if obj.get('Type'):
                    child['kind'] = obj.get('Type').lower()

    def finish(node):
        if node['key'] == 'Logical/Libraries':
            node['kind'] = 'libraries'
        if node['key'] == 'Physical/<ACTIVE>':
            node['kind'] = 'configuration'
        node['children'].sort(key=lambda item: (item['order'], item['name'].casefold()))
        for child in node['children']:
            finish(child)
        node.pop('order', None)

    for node in list(nodes.values()):
        if '/' not in node['key']:
            finish(node)
    # Logical objects sit directly below the project, as in AS Logical View.
    children = list(nodes.get('Logical', {}).get('children', []))
    if 'Physical' in nodes:
        children.append(nodes['Physical'])
    root_files = [node for key, node in nodes.items() if '/' not in key and key not in {'Logical', 'Physical'}]
    if root_files:
        children.append({'key': '$project-files', 'name': 'Project files', 'kind': 'package',
                         'description': '', 'relative_path': '', 'descriptor': True,
                         'children': sorted(root_files, key=lambda item: item['name'].casefold())})
    return {'schema_version': 1, 'name': identity.get('project_name') or root.name,
            'children': children, 'file_count': len(files)}
