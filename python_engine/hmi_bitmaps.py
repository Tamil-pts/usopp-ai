"""Resolve VC bitmap definitions within the selected visualization or VCShared."""
import base64
import hashlib
from io import BytesIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def tag(node):
    return node.tag.rsplit('}', 1)[-1].casefold()


def properties(node):
    return {child.get('Name'): child.get('Value', '') for child in node
            if tag(child) == 'property' and child.get('Name')}


class BitmapResolver:
    def __init__(self, target, cache, source_path=None):
        self.target = Path(target) if target else None
        self.cache = cache
        self.assets = {}
        self.source_path = Path(source_path) if source_path else None

    def reference(self, value, kind, folder, suffix=''):
        match = re.fullmatch(r'Source\[(local|global)\]\.' + kind + r'\[([^\]]+)\]', str(value or ''), re.I)
        if not match or self.target is None:
            return None
        home = self.target if match[1].casefold() == 'local' else self.target.parent / 'VCShared'
        directory = (home / folder).resolve()
        path = (directory / (match[2] + suffix)).resolve()
        if not path.is_relative_to(directory):
            return None
        if not path.exists() and path.parent.is_dir():
            path = next((p for p in path.parent.iterdir() if p.name.casefold() == path.name.casefold()), path)
        return path, home, match[2]

    def xml(self, path):
        key = 'bitmap_xml:' + str(path)
        if key not in self.cache:
            try:
                self.cache[key] = ET.fromstring(path.read_bytes())
            except (ET.ParseError, OSError):
                self.cache[key] = None
        return self.cache[key]

    def bitmap(self, value):
        record = {'reference': str(value or ''), 'status': 'unresolved', 'name': '', 'file': ''}
        resolved = self.reference(value, 'Bitmap', 'Bitmaps', '.bminfo')
        if resolved is None:
            record['message'] = 'Bitmap reference is missing or outside this visualization.'
            return record
        info_path, home, name = resolved
        record['name'] = name
        doc = self.xml(info_path)
        info = properties(doc) if doc is not None else {}
        filename = info.get('File', '').replace('\\', '/')
        directory = (home / 'Bitmaps').resolve()
        if filename:
            path = (directory / filename).resolve()
        else:
            path = next((p for p in directory.iterdir() if p.stem.casefold() == name.casefold()
                         and p.suffix.casefold() in {'.bmp', '.png', '.jpg', '.jpeg', '.gif'}), None) if directory.is_dir() else None
        if path is None or not path.is_relative_to(directory):
            record['message'] = 'Bitmap file definition is missing or leaves the Bitmaps directory.'
            return record
        if not path.is_file() and path.parent.is_dir():
            path = next((p for p in path.parent.iterdir() if p.name.casefold() == path.name.casefold()), path)
        record.update(file=path.name, path=path.relative_to(home).as_posix(),
                      transparent=info.get('Transparent', ''), definition=info_path.relative_to(home).as_posix())
        key = 'bitmap_image:' + str(path)
        if key not in self.cache:
            from PIL import Image
            try:
                if path.stat().st_size > 20 * 1024 * 1024:
                    raise ValueError('Bitmap file exceeds the preview size limit.')
                raw = path.read_bytes()
                with Image.open(BytesIO(raw)) as image:
                    if image.width * image.height > 8_000_000:
                        raise ValueError('Bitmap dimensions exceed the preview size limit.')
                    stream = BytesIO()
                    image.convert('RGBA').save(stream, format='PNG')
                    self.cache[key] = {'width': image.width, 'height': image.height,
                        'sha256': hashlib.sha256(raw).hexdigest(),
                        'data_uri': 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode('ascii')}
            except FileNotFoundError:
                self.cache[key] = {'error': f'{path.name} was not found in the Bitmaps folder.'}
            except OSError:
                self.cache[key] = {'error': f'{path.name} could not be read or decoded.'}
            except (ValueError, Image.DecompressionBombError) as error:
                self.cache[key] = {'error': str(error)}
        asset = self.cache[key]
        if asset.get('error'):
            record['message'] = 'Bitmap image unavailable: ' + asset['error']
            return record
        asset_id = hashlib.sha256(str(path).encode()).hexdigest()
        self.assets[asset_id] = {**asset, 'name': name, 'file': path.name, 'path': record['path']}
        record.update(status='resolved', asset_id=asset_id, sha256=asset['sha256'])
        return record

    def resolve(self, props, levels=1):
        states = {}
        for state, prefix in [('released', ''), ('pressed', 'Pressed')]:
            source = props.get(prefix + 'BitmapSource', '')
            if not source or source.casefold() in {'none', '<none>'}:
                continue
            group_ref = props.get(prefix + 'BitmapGroup', '')
            offset_value = props.get(prefix + 'BitmapOffset', props.get(prefix + 'BitmapIndexOffset', '0'))
            index_value = props.get(prefix + 'BitmapIndex', 'None')
            try:
                offset = int(offset_value)
            except (ValueError, TypeError):
                offset = None
            dynamic = index_value.casefold() not in {'none', '<none>', ''} and not index_value.isdigit()
            static_index = int(index_value) if index_value.isdigit() else 0
            variants = []
            metadata = {'source': source, 'group': group_ref, 'offset': offset_value,
                        'index_datapoint': index_value, 'dynamic': dynamic, 'variants': variants}
            if source.casefold() == 'singlebitmap':
                variants.append({'level': 0, 'language': 'neutral', **self.bitmap(props.get(prefix + 'Bitmap'))})
            else:
                group_path = self.reference(group_ref, 'BitmapGroup', 'BitmapGroups', '.bmgrp')
                group = self.xml(group_path[0]) if group_path else None
                if group_path:
                    metadata['group_name'] = group_path[2]
                    metadata['group_file'] = group_path[0].relative_to(group_path[1]).as_posix()
                indexes = {node.get('Value'): node.get('ID') for node in group.iter() if tag(node) == 'index'} if group is not None else {}
                for level in range(max(1, min(64, levels))):
                    index = offset + static_index + level if offset is not None else None
                    identity = indexes.get(str(index))
                    matches = [(layer.get('LanguageId', 'neutral'), bitmap.get('Value', ''))
                               for layer in group.iter() if tag(layer) == 'bitmaplayer'
                               for bitmap in layer if tag(bitmap) == 'bitmapref' and bitmap.get('ID') == identity] if group is not None and identity is not None else []
                    if not matches:
                        variants.append({'level': level, 'index': index, 'language': 'neutral', 'name': '',
                                         'reference': group_ref, 'status': 'unresolved',
                                         'message': f'Bitmap group/index could not be resolved: {group_ref} / {index}.'})
                    for language, value in matches:
                        # A group's local references are relative to the group owner,
                        # including when that owner is VCShared.
                        owner = BitmapResolver(group_path[1], self.cache)
                        variant = owner.bitmap(value)
                        self.assets.update(owner.assets)
                        variants.append({'level': level, 'index': index, 'language': language, **variant})
            states[state] = metadata
        return states

    @staticmethod
    def resolved_properties(states):
        result = {}
        for state, metadata in states.items():
            prefix = 'Resolved' + ('Pressed' if state == 'pressed' else '') + 'Bitmap'
            variants = metadata['variants']
            first = next((item for item in variants if item.get('level') == 0), {})
            for suffix, value in [('Name', first.get('name')), ('File', first.get('file')), ('Path', first.get('path')),
                                  ('Group', metadata.get('group_name')), ('Index', first.get('index')),
                                  ('Status', first.get('status')), ('SHA256', first.get('sha256'))]:
                if value is not None:
                    result[prefix + suffix] = str(value)
            if first.get('message'):
                result[prefix + 'Note'] = first['message']
            if metadata.get('dynamic'):
                result[prefix + 'IndexNote'] = 'Live index is not available; preview uses index 0 plus the configured offset.'
            for variant in variants:
                if len(variants) > 1:
                    result[prefix + f"Level{variant['level']} ({variant['language']})"] = f"{variant.get('index', '')}: {variant.get('name') or variant.get('reference')} ({variant['status']})"
                    if variant.get('sha256'):
                        result[prefix + f"SHA256Level{variant['level']} ({variant['language']})"] = variant['sha256']
        return result
