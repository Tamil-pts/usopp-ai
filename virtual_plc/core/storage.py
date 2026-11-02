"""Per-account workspace snapshots. Never write into an imported PLC project."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import threading
import time
import uuid

SCHEMA = 1
MAX_DOCUMENT = 192 * 1024 * 1024
MAX_MODEL = 80 * 1024 * 1024
MAX_SOURCES = 64 * 1024 * 1024
MAX_SOURCE = 8 * 1024 * 1024
SOURCE_EXTENSIONS = {'.st', '.ab', '.src', '.ld', '.c', '.h', '.var', '.typ', '.fun',
                     '.page', '.txtgrp', '.algrp', '.alcfg', '.xml', '.sw', '.hw', '.hwl', '.iom',
                     '.apj', '.prg', '.pkg', '.set', '.dso', '.per', '.gdm', '.layer', '.pages',
                     '.vc', '.vcp', '.dob', '.dat', '.vcvk', '.vcr', '.vcs', '.fninfo', '.cfg', '.osl'}


def validate_configuration(data):
    if not isinstance(data, dict):
        raise ValueError('Workspace configuration must be an object.')
    if 'components' in data:
        from virtual_plc.core.components import validate_components
        validate_components(data['components'])
    settings = data.get('settings', {})
    if not isinstance(settings, dict) or len(json.dumps(settings)) > 65536:
        raise ValueError('Workspace settings must be an object of at most 64 KiB.')
    if 'backgroundLoad' in settings and settings['backgroundLoad'] not in {'responsive','balanced','fast'}:
        raise ValueError('Choose responsive, balanced or fast background simulation load.')
    if 'speed' in settings and (type(settings['speed']) not in {int, float}
                                or not math.isfinite(settings['speed']) or settings['speed'] not in {.25, .5, 1, 2, 5}):
        raise ValueError('Choose simulation speed 0.25, 0.5, 1, 2 or 5.')
    if 'autosave' in settings and type(settings['autosave']) is not bool:
        raise ValueError('Autosave must be enabled or disabled.')
    watched = data.get('watchlist', [])
    if not isinstance(watched, list) or len(watched) > 500 or any(not isinstance(item, str) or len(item) > 400 for item in watched):
        raise ValueError('Use at most 500 variable identities in a watchlist.')
    corrections = data.get('manualCorrections', {})
    if not isinstance(corrections, dict) or len(json.dumps(corrections)) > 65536:
        raise ValueError('Manual corrections must be an object of at most 64 KiB.')
    scenarios = data.get('scenarios', [])
    if not isinstance(scenarios, list) or len(scenarios) > 20:
        raise ValueError('Save at most 20 scenarios.')
    for scenario in scenarios:
        if not isinstance(scenario, dict) or not isinstance(scenario.get('events', []), list) or len(scenario.get('events', [])) > 1000:
            raise ValueError('A scenario must contain at most 1000 input events.')
        for event in scenario.get('events', []):
            if (not isinstance(event, dict) or not isinstance(event.get('name'), str)
                    or len(event['name']) > 400 or type(event.get('timeMs')) not in {int, float}
                    or not math.isfinite(event['timeMs']) or event['timeMs'] < 0
                    or len(json.dumps(event.get('value'))) > 65536):
                raise ValueError('Scenario events need a variable name, bounded value and finite nonnegative timeMs.')


def relative_path(value):
    text = str(value or '').replace('\\', '/')
    path = PurePosixPath(text)
    if (not text or path.is_absolute() or PureWindowsPath(text).drive
            or '..' in path.parts or '\x00' in text or ':' in text):
        raise ValueError('Use an original project-relative source path.')
    return path.as_posix()


def safe_source(root, name):
    relative = relative_path(name)
    root = Path(root).resolve()
    target = root.joinpath(*PurePosixPath(relative).parts)
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError('Source links cannot leave the imported project.')
    if target.suffix.casefold() not in SOURCE_EXTENSIONS:
        raise ValueError('This file type is not a Virtual PLC source resource.')
    if not target.is_file():
        raise FileNotFoundError(relative)
    if target.stat().st_size > MAX_SOURCE:
        raise ValueError('Source exceeds the 8 MiB view limit.')
    return target


def read_source(root, name):
    from python_engine.compare import decode_project_text
    path = safe_source(root, name)
    raw = path.read_bytes()
    return (raw.decode('latin-1') if path.suffix.casefold()=='.dat' else decode_project_text(path, raw)), hashlib.sha256(raw).hexdigest()


def atomic_json(path, value, maximum=MAX_DOCUMENT):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + uuid.uuid4().hex[:12] + '.tmp')
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(text.encode('utf-8')) > maximum:
            raise ValueError('Workspace document exceeds its supported size; reduce the project snapshot.')
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def bounded_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_DOCUMENT:
        raise ValueError('Workspace document exceeds 192 MiB.')
    return json.loads(path.read_text(encoding='utf-8-sig'))


class WorkspaceStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()

    def folder(self, owner, identity=None):
        # Keep paths within ordinary Windows limits in deeply nested workspaces.
        # This remains a per-account 128-bit namespace, not an access token.
        account = hashlib.sha256(str(owner).encode()).hexdigest()[:32]
        base = self.root / account
        if identity is None:
            return base
        if not re.fullmatch(r'[a-f0-9]{32}', str(identity)):
            raise ValueError('Invalid Virtual PLC workspace identity.')
        return base / identity

    def create(self, owner, name, project_root=None, identity=None):
        identity = identity or uuid.uuid4().hex
        document = {'schemaVersion': SCHEMA, 'id': identity, 'name': str(name)[:180],
                    'createdAt': time.time(), 'updatedAt': time.time(), 'projectRoot': str(project_root or ''),
                    'settings': {'speed': 1, 'theme': 'dark', 'autosave': True}, 'watchlist': [],
                    'manualCorrections': {}, 'scenarios': [], 'components': [], 'sourceCacheComplete': False,
                    'sourceCacheNotices': [], 'status': 'analyzing'}
        self.write(owner, identity, document)
        return document

    def write(self, owner, identity, document):
        with self.lock:
            document['updatedAt'] = time.time()
            atomic_json(self.folder(owner, identity) / 'workspace.json', document)

    def load(self, owner, identity):
        with self.lock:
            path = self.folder(owner, identity) / 'workspace.json'
            if not path.is_file():
                raise FileNotFoundError('Virtual PLC workspace was not found for this account.')
            return bounded_json(path)

    def list(self, owner):
        records = []
        folder = self.folder(owner)
        if not folder.exists():
            return records
        for path in folder.glob('*/workspace.json'):
            try:
                document = bounded_json(path)
                records.append({key: document.get(key) for key in (
                    'id', 'name', 'createdAt', 'updatedAt', 'status', 'moduleVersion', 'settings')})
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda row: row.get('updatedAt') or 0, reverse=True)

    def save_model(self, owner, identity, model):
        with self.lock:
            # Derived inspection graphs can be rebuilt from the source snapshot.
            # Keep canonical model/export budgets independent of their size.
            canonical={key:value for key,value in model.items() if key!='machineContext'}
            atomic_json(self.folder(owner, identity) / 'model.json', canonical, MAX_MODEL)

    def model(self, owner, identity):
        return bounded_json(self.folder(owner, identity) / 'model.json')

    def cache_sources(self, owner, identity, root, files):
        sources = {}
        total = 0
        notices = []
        if len(files) > 15000:
            notices.append('Source cache file limit reached; uncached paths remain in the manifest.')
        for resource in files[:15000]:
            name = resource.get('path') or resource.get('source')
            if not name or Path(name).suffix.casefold() not in SOURCE_EXTENSIONS:
                continue
            try:
                text, fingerprint = read_source(root, name)
                count = len(text.encode('utf-8'))
                if total + count > MAX_SOURCES:
                    notices.append('Source cache reached 64 MiB; original paths are retained for uncached files.')
                    break
                sources[relative_path(name)] = {'text': text, 'sha256': fingerprint}
                total += count
            except (OSError, ValueError) as error:
                notices.append(str(name) + ': ' + str(error))
        with self.lock:
            atomic_json(self.folder(owner, identity) / 'sources.json', sources)
        return not notices, notices[:100]

    def source(self, owner, identity, name):
        relative = relative_path(name)
        path = self.folder(owner, identity) / 'sources.json'
        sources = bounded_json(path) if path.is_file() else {}
        if relative in sources:
            return {**sources[relative], 'path': relative, 'snapshot': True,
                    'language': Path(relative).suffix.lstrip('.')}
        document = self.load(owner, identity)
        model = self.model(owner, identity)
        executable = next((row for row in model.get('programs', []) if row.get('source') == relative and isinstance(row.get('code'), str)), None)
        if executable:
            return {'path': relative, 'text': executable['code'], 'snapshot': True,
                    'language': executable.get('language', Path(relative).suffix.lstrip('.'))}
        allowed = {row.get('path') for row in model.get('files', [])}
        if relative not in allowed:
            raise FileNotFoundError('This source is not in the analyzed project manifest.')
        # Imported JSON never authorizes reading its alleged server-side root.
        if not document.get('projectRoot') or document.get('imported'):
            raise FileNotFoundError('Source was not embedded in this imported workspace.')
        text, fingerprint = read_source(document['projectRoot'], relative)
        original = next((row.get('sha256') for row in model.get('files', []) if row.get('path') == relative), None)
        if original and fingerprint != original:
            raise ValueError('This original source changed after analysis. Refresh the project before using it as simulation evidence.')
        return {'text': text, 'path': relative, 'sha256': fingerprint, 'snapshot': False,
                'language': Path(relative).suffix.lstrip('.')}

    def save_state(self, owner, identity, snapshot):
        with self.lock:
            atomic_json(self.folder(owner, identity) / 'state.json', snapshot)

    def export(self, owner, identity):
        document = self.load(owner, identity)
        folder = self.folder(owner, identity)
        if sum(path.stat().st_size for path in folder.glob('*.json') if path.name != 'imported_results.json') > MAX_DOCUMENT - 1024:
            raise ValueError('Workspace export exceeds 192 MiB; reduce the source snapshot or retained results before exporting.')
        sources = bounded_json(folder / 'sources.json') if (folder / 'sources.json').exists() else {}
        state = bounded_json(folder / 'state.json') if (folder / 'state.json').exists() else None
        # Absolute source roots and account identity are never trust grants in an import.
        return {'format': 'usopp-virtual-plc', 'schemaVersion': SCHEMA,
                'workspace': {key: value for key, value in document.items() if key != 'projectRoot'},
                'model': self.model(owner, identity), 'sources': sources, 'results': state}

    def import_document(self, owner, data, name=None):
        if (not isinstance(data, dict) or data.get('format') != 'usopp-virtual-plc'
                or data.get('schemaVersion') != SCHEMA or not isinstance(data.get('model'), dict)):
            raise ValueError('Import a schemaVersion 1 uSOPp Virtual PLC workspace.')
        model = deepcopy(data['model'])
        for key, maximum in (('variables', 100000), ('programs', 10000), ('tasks', 2048), ('files', 15000)):
            if not isinstance(model.get(key, []), list) or len(model.get(key, [])) > maximum:
                raise ValueError('Invalid or oversized ' + key + ' collection.')
            if any(not isinstance(row, dict) for row in model.get(key, [])):
                raise ValueError('Invalid ' + key + ' record.')
        if not isinstance(model.get('types', {}), dict) or len(model.get('types', {})) > 20000:
            raise ValueError('Invalid or oversized type definitions.')
        for resource in model.get('files', []):
            relative_path(resource.get('path'))
        functions = model.get('functions', [])
        if not isinstance(functions, list) or len(functions) > 10000 or any(not isinstance(row, dict) for row in functions):
            raise ValueError('Invalid function definition collection.')
        for program in [*model.get('programs', []), *functions]:
            program.pop('compiled', None)  # Recompile source, never trust imported executable IR.
            if not isinstance(program.get('code', ''), str) or len(program.get('code', '').encode()) > MAX_SOURCE:
                raise ValueError('Program source exceeds the supported size.')
        model['root'] = ''
        model.pop('intelligenceProjectId', None)  # Never mix imported code with an older server-side index.
        model.pop('indexStatus', None)
        sources = data.get('sources') or {}
        if not isinstance(sources, dict) or len(sources) > 15000:
            raise ValueError('Invalid source snapshot collection.')
        total = 0
        for path, source in sources.items():
            relative_path(path)
            if not isinstance(source, dict) or not isinstance(source.get('text'), str):
                raise ValueError('Invalid embedded source document.')
            count = len(source['text'].encode('utf-8'))
            if count > MAX_SOURCE:
                raise ValueError('Embedded source exceeds 8 MiB.')
            total += count
            if total > MAX_SOURCES:
                raise ValueError('Embedded sources exceed 64 MiB.')
        configuration = data.get('workspace') or {}
        validate_configuration(configuration)
        document = self.create(owner, name or configuration.get('name') or model.get('name') or 'Imported PLC')
        identity = document['id']
        for key in ('settings', 'watchlist', 'manualCorrections', 'scenarios', 'components', 'sourceCacheComplete', 'sourceCacheNotices'):
            if key in configuration:
                document[key] = configuration[key]
        # Imported output models require a fresh, explicit enable action.
        document['components'] = [{**item, 'enabled': False} for item in document.get('components', [])]
        document.update(imported=True, projectRoot='', status='ready')
        self.save_model(owner, identity, model)
        atomic_json(self.folder(owner, identity) / 'sources.json', sources)
        # Imported result evidence is kept as an archive, never treated as live PLC state.
        if isinstance(data.get('results'), dict):
            atomic_json(self.folder(owner, identity) / 'imported_results.json', data['results'])
        self.write(owner, identity, document)
        return document
