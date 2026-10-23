"""Bounded per-account engineering sessions and background simulation workers."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import threading
import time

from virtual_plc import __version__
from virtual_plc.core.components import DeviceComponents, component_catalog, validate_components
from virtual_plc.core.storage import WorkspaceStore, validate_configuration
from virtual_plc.core.preview import value_preview

MAX_RESIDENT = 3
MAX_RUNNING = 2


def runtime_view(runtime, watchlist=()):
    snapshot = runtime.snapshot(compact=True, watchlist=watchlist)
    variables = snapshot.get('variables', [])
    if len(variables) > 1000:
        selected = variables[:1000]
        known = {row['id'] for row in selected}
        watched = set(watchlist)
        selected.extend(row for row in variables if row['id'] not in known
                        and (row['id'] in watched or row.get('name') in watched))
        snapshot['variables'] = selected
    snapshot['variablesTotal'] = len(runtime.memory.records)
    snapshot['variableRowsLimited'] = len(snapshot.get('variables', [])) < len(runtime.memory.records)
    snapshot['traceTotalRetained'] = len(snapshot.get('trace', []))
    snapshot['trace'] = snapshot.get('trace', [])[-1000:]
    snapshot['diagnosticsTotal'] = len(snapshot.get('diagnostics', []))
    snapshot['diagnostics'] = snapshot.get('diagnostics', [])[:500]
    # The UI reads other variable pages lazily. Poll only displayed/watch rows
    # and resolved interface bindings, rather than every large PLC array.
    memory = {}
    truncated = []
    for row in snapshot.get('variables', []):
        for field in ('value', 'previous'):
            row[field], complete = value_preview(row.get(field))
            if not complete:
                row['valueTruncated'] = True
                truncated.append(row['id'])
        memory[row['id']] = row.get('value')
    if not hasattr(runtime, '_interface_bindings'):
        bindings = set()
        for page in runtime.project.get('hmi', {}).get('pages', []):
            for item in page.get('objects', []):
                fields = ('binding', 'visibilityBinding', 'statusBinding', 'lockingBinding',
                          'passwordLevelBinding', 'textBinding', 'textIndexBinding',
                          'bitmapIndexBinding', 'minBinding', 'maxBinding')
                actions = [item.get('action') or {}, item.get('completion') or {}, *item.get('actions', [])]
                for value in [*(item.get(key) for key in fields),
                              (item.get('layerState') or {}).get('statusBinding'),
                              *(action.get('variable') for action in actions)]:
                    if isinstance(value, str) and len(value) <= 400:
                        bindings.add(value)
        for channel in runtime.project.get('hardware', {}).get('channels', []):
            value = channel.get('variableId') or channel.get('variable')
            if isinstance(value, str): bindings.add(value)
        runtime._interface_bindings = sorted(bindings)
    if not hasattr(runtime, '_interface_readers'):
        runtime._interface_readers = []
        for name in runtime._interface_bindings[:2000]:
            try:
                record, reference = runtime.value_reference(name)
                runtime._interface_readers.append((name, record, reference.get('path', [])))
            except (ValueError, TypeError, KeyError, IndexError):
                continue
    for name, record, path in runtime._interface_readers:
        try:
            raw, _ = runtime.memory.member(record['value'], record['_spec'], path, lambda index: index['value'])
            value, complete = value_preview(raw)
            memory[name] = value
            if not complete: truncated.append(name)
        except (ValueError, TypeError, KeyError, IndexError):
            continue
    snapshot['memory'] = memory
    snapshot['memoryLimited'] = True
    snapshot['truncatedValues'] = list(set(truncated))
    snapshot['interfaceBindingsLimited'] = len(runtime._interface_bindings) > 2000
    return snapshot


@dataclass
class Workspace:
    owner: str
    identity: str
    document: dict
    model: dict = field(default_factory=dict)
    runtime: object = None
    public_model: dict = field(default_factory=dict)
    progress: dict = field(default_factory=dict)
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)
    thread: object = None
    accessed: float = field(default_factory=time.monotonic)
    saved_at: float = 0
    scenario_cursor: int = 0
    devices: object = None
    device_error: str = ''
    hmi_pressed: dict = field(default_factory=dict)
    environment_cache: object = None


def public_model(model, runtime=None):
    """Source is fetched by path; avoid retransmitting code/IR with every poll."""
    view = {key: value for key, value in model.items() if key not in {'programs', 'functions', 'sources'}}
    for key in ('programs', 'functions'):
        collection = model.get(key, [])
        if isinstance(collection, list):
            view[key] = [{field: value for field, value in row.items() if field not in {'code','originalCode', 'compiled', 'ir'}}
                         for row in collection if isinstance(row, dict)]
            if runtime:
                for row in view[key]:
                    unit = runtime.units.get(row.get('id'))
                    if not unit:
                        continue
                    errors = [item for item in runtime.diagnostics if item.get('severity') == 'error' and item.get('source') == unit.get('source')]
                    unsupported = [item for item in unit.get('compiled', {}).get('diagnostics', []) if item.get('severity') == 'error']
                    active = row.get('id') in runtime.active_units
                    status = ('excluded' if not active else 'unsupported' if unsupported
                              else 'partially supported' if errors else 'supported')
                    row['compatibility'] = {'status': status, 'active': active,
                                            'diagnostics': (unsupported + errors)[:10]}
    return view


def corrections(model, options):
    """Apply explicit virtual-only overrides, preserving original source evidence."""
    model = deepcopy(model)
    from .project import upgrade_lifecycle
    upgrade_lifecycle(model)
    if not isinstance(options, dict):
        raise ValueError('Manual corrections must be an object.')
    if 'cpuServices' in options:
        from .cpu import configuration
        model['cpuServices']=configuration(options['cpuServices'])
    if options.get('simulationProfile'):
        model['simulationProfile']=deepcopy(options['simulationProfile'])
    if options.get('sourceCorrections'):
        from .source_corrections import apply_corrections
        apply_corrections(model,options['sourceCorrections'])
    intervals = options.get('taskIntervals') or {}
    assignments = options.get('programAssignments') or {}
    enabled = options.get('taskEnabled') or {}
    programs = {row['id'] for row in model.get('programs', [])}
    for task in model.get('tasks', []):
        identity = task['id']
        if identity in intervals:
            interval = float(intervals[identity])
            if not 0.1 <= interval <= 60000:
                raise ValueError('Virtual task intervals must be 0.1..60000 ms.')
            task.update(intervalMs=interval, timingSource='Explicit virtual workspace override')
        if identity in assignments:
            selected = assignments[identity]
            if not isinstance(selected, list) or not set(selected).issubset(programs):
                raise ValueError('Assign only analyzed program IDs to virtual tasks.')
            task.update(programs=selected, assignmentSource='Explicit virtual workspace override')
        if identity in enabled:
            if type(enabled[identity]) is not bool:
                raise ValueError('Virtual task enabled overrides must be boolean.')
            task.update(enabled=enabled[identity], enabledSource='Explicit virtual workspace override')
    mappings = options.get('ioMappings') or {}
    variables = {row['id'] for row in model.get('variables', [])}
    for channel in model.get('hardware', {}).get('channels', []):
        if channel.get('id') in mappings:
            target = mappings[channel['id']]
            if target not in variables:
                raise ValueError('Choose an analyzed PLC variable for a virtual I/O binding.')
            channel.update(variable=target, bindingSource='Explicit virtual workspace override')
    return model


class VirtualPLCService:
    def __init__(self, root):
        self.store = WorkspaceStore(root)
        self.guard = threading.RLock()
        self.workspaces = {}
        self.stop_event = threading.Event()
        self.worker = None
        self.component_libraries={}

    def component_library(self,owner):
        from .component_library import ComponentLibrary
        with self.guard:
            key=str(owner)
            if key not in self.component_libraries:self.component_libraries[key]=ComponentLibrary(self.store.folder(key)/'component-library')
            return self.component_libraries[key]

    def save_component_library(self,workspace,payload):
        with workspace.lock:
            selected=payload.get('componentIds')
            if not isinstance(selected,list) or not selected or len(selected)>2048 or any(not isinstance(value,str) for value in selected):
                raise ValueError('Select one or more configured components for the library item.')
            components=[item for item in workspace.document.get('components',[]) if item['id'] in selected]
            if len(components)!=len(set(selected)):raise ValueError('The selected components have changed. Refresh and select them again.')
            return self.component_library(workspace.owner).save(payload,components,workspace.document.get('name',''))

    def apply_component_library(self,workspace,identity,payload):
        with workspace.lock:
            if not workspace.runtime or workspace.document.get('status')!='ready':raise ValueError('Complete project analysis first.')
            components=self.component_library(workspace.owner).instantiate(identity,workspace.runtime,payload.get('matchExact',False),payload.get('offsetX',0),payload.get('offsetY',0))
            self.configure_components(workspace,workspace.document.get('components',[])+components)
            return {**self.component_state(workspace),'message':'Library models and layout added as disabled drafts. Review PLC tags, enable the required devices and save connections.'}

    def _start_worker(self):
        with self.guard:
            if self.worker and self.worker.is_alive():
                return
            self.stop_event.clear()
            self.worker = threading.Thread(target=self._run, name='virtual-plc-scans', daemon=True)
            self.worker.start()

    def _room(self):
        with self.guard:
            while len(self.workspaces) >= MAX_RESIDENT:
                candidates = [row for row in self.workspaces.values()
                              if not (row.thread and row.thread.is_alive())
                              and (not row.runtime or row.runtime.status != 'running')]
                if not candidates:
                    raise ValueError('Three Virtual PLC workspaces are active. Pause or close one first.')
                oldest = min(candidates, key=lambda row: row.accessed)
                self._persist(oldest)
                self.workspaces.pop((oldest.owner, oldest.identity), None)

    def get(self, owner, identity):
        key = (str(owner), identity)
        with self.guard:
            workspace = self.workspaces.get(key)
            if workspace:
                workspace.accessed = time.monotonic()
                return workspace
            document = self.store.load(owner, identity)
            self._room()
            workspace = Workspace(str(owner), identity, document)
            if (self.store.folder(owner, identity) / 'model.json').is_file():
                from virtual_plc.core.runtime import VirtualRuntime
                base = self.store.model(owner, identity)
                self._upgrade_views(workspace, base)
                workspace.model = corrections(base, document.get('manualCorrections') or {})
                workspace.runtime = VirtualRuntime(workspace.model)
                workspace.public_model = public_model(workspace.model, workspace.runtime)
                workspace.document['status'] = 'ready'
                workspace.progress = {'stage': 'Saved engineering snapshot opened', 'percentage': 100}
                # Reopen starts stopped. Saved trace/results are archival evidence.
                self._restore_retention(workspace)
            elif document.get('status') in {'analyzing', 'interrupted'}:
                workspace.document['status'] = 'interrupted'
                workspace.progress = {'stage': 'Analysis interrupted by server restart', 'percentage': None,
                                      'message': 'No analysis is running. Choose Retry analysis to continue from the saved project.'}
                self.store.write(workspace.owner, workspace.identity, workspace.document)
            elif document.get('status') in {'cancelled', 'error', 'failed'}:
                workspace.progress = {'stage': document.get('analysisMessage') or 'Project analysis needs attention',
                                      'message': 'No analysis is running. Retry analysis or select the original project folder.',
                                      'percentage': None}
            self.workspaces[key] = workspace
            return workspace

    def _upgrade_views(self, workspace, model):
        from .io_bindings import connect_io
        binding_upgrade = model.get('hardware', {}).get('bindingAdapterVersion', 0) < 1
        connect_io(model.setdefault('hardware', {}), model.get('variables', []), model.get('tasks', []))
        if binding_upgrade:
            self.store.save_model(workspace.owner, workspace.identity, model)
        from virtual_plc.core.hardware import order_hardware, read_hardware
        from virtual_plc.core.project import upgrade_task_slots
        task_upgrade = model.get('taskAdapterVersion', 0) < 2
        declaration_upgrade=model.get('declarationAdapterVersion',0)<4
        upgrade_task_slots(model)
        model['variables'] = [v for v in model.get('variables', []) if not str(v.get('source', '')).lower().endswith('.fun')]
        model.setdefault('statistics', {})['variables'] = len(model['variables'])
        order_hardware(model.setdefault('hardware', {}))
        cache = self.store.folder(workspace.owner, workspace.identity) / 'sources.json'
        if workspace.document.get('imported'):
            if declaration_upgrade and cache.is_file():
                from .c_declarations import merge
                from .storage import bounded_json
                cached={k:v['text'] for k,v in bounded_json(cache).items()}
                merge(model,cached)
                self.store.save_model(workspace.owner,workspace.identity,model)
            return
        if (model.get('hmi', {}).get('adapterVersion', 0) >= 5 and model.get('symbolCaseSensitive') is True and model.get('hardware', {}).get('adapterVersion', 0) >= 2 and not task_upgrade and not declaration_upgrade):
            return
        root = Path(workspace.document.get('projectRoot') or '')
        def require_refresh():
            if model.get('symbolCaseSensitive') is not True and not any(d.get('code') == 'B&R_REFRESH_REQUIRED' for d in model.get('diagnostics', [])):
                model.setdefault('diagnostics', []).append({'severity': 'error', 'code': 'B&R_REFRESH_REQUIRED',
                    'message': 'Refresh the original project to restore complete, case-sensitive B&R declarations. Source inspection remains available.'})
        if not workspace.document.get('projectRoot') or not root.is_dir() or not cache.is_file():
            require_refresh()
            return
        from virtual_plc.core.storage import bounded_json
        from virtual_plc.core.hmi import read_hmi
        cached = {name: item['text'] for name, item in bounded_json(cache).items()}
        if model.get('symbolCaseSensitive') is not True:
            if not workspace.document.get('sourceCacheComplete'):
                require_refresh()
                return
            from virtual_plc.core.project import upgrade_symbol_model
            remap = upgrade_symbol_model(model, cached)
            def migrate(value):
                if isinstance(value, str): return remap.get(value, value)
                if isinstance(value, list): return [migrate(item) for item in value]
                if isinstance(value, dict): return {key: migrate(item) for key, item in value.items()}
                return value
            workspace.document = migrate(workspace.document)
            workspace.document['symbolIdentityMigration'] = remap
            workspace.document['modelRevision'] = str(time.time_ns())
        from .c_declarations import merge as merge_c_declarations
        merge_c_declarations(model,cached)
        original = self.store.model(workspace.owner, workspace.identity)
        upgrade_task_slots(original)
        if original.get('symbolCaseSensitive') is not True:
            from virtual_plc.core.project import upgrade_symbol_model
            upgrade_symbol_model(original, cached)
        original['variables'] = [v for v in original.get('variables', []) if not str(v.get('source', '')).lower().endswith('.fun')]
        original.setdefault('statistics', {})['variables'] = len(original['variables'])
        merge_c_declarations(original,cached)
        if model.get('hardware', {}).get('adapterVersion', 0) < 2:
            from virtual_plc.core.project import _configuration_path
            configuration = model.get('projectInfo', {}).get('activeConfiguration')
            physical = {name: text for name, text in cached.items() if Path(name).suffix.lower() in {'.hw','.hwl','.iom'} and _configuration_path(name, configuration)}
            hardware = read_hardware(physical, configuration, [])
            lookup = {v['name']: v for v in model.get('variables', []) if v.get('scope') == '@global'}
            for channel in hardware['channels']:
                variable = lookup.get(channel.get('variable','').split('.',1)[0])
                if variable: channel.update(variableId=variable['id'], type=variable['type'])
            model['hardware'] = hardware
            original['hardware'] = hardware
        if model.get('hmi', {}).get('adapterVersion', 0) < 5:
            sources = {name: text for name, text in cached.items() if Path(name).suffix.lower() in {'.page', '.layer', '.vcvk', '.algrp', '.txtgrp', '.dso'}}
            diagnostics = []
            model['hmi'] = read_hmi(root, sources, diagnostics, variables=model.get('variables', []))
            model['hmi']['upgradeNotices'] = diagnostics[:100]
            original['hmi'] = model['hmi']
        for target in (model, original):
            connect_io(target.setdefault('hardware', {}), target.get('variables', []), target.get('tasks', []))
            target['diagnostics'] = [d for d in target.get('diagnostics', []) if d.get('code') != 'hmi-status-unresolved']
        self.store.save_model(workspace.owner, workspace.identity, original)
        # Keep the old archival trace intact; only live identities and current diagnostics are upgraded.
        self.store.write(workspace.owner, workspace.identity, workspace.document)

    def create(self, owner, project_root, name='', configuration=None):
        self._room()
        document = self.store.create(owner, name or Path(project_root).name, project_root)
        document['moduleVersion'] = __version__
        document['configuration'] = configuration
        workspace = Workspace(str(owner), document['id'], document)
        with self.guard:
            self.workspaces[(str(owner), document['id'])] = workspace
        self.analyze(workspace)
        return self.snapshot(workspace)

    def analyze(self, workspace, rebuild=False):
        with workspace.lock:
            if workspace.thread and workspace.thread.is_alive():
                return
            if workspace.runtime:
                workspace.runtime.command('pause', return_snapshot=False)
            workspace.cancel = threading.Event()
            workspace.document['status'] = 'analyzing'
            workspace.document.pop('analysisMessage', None)
            workspace.progress = {'stage': 'Preparing local project analysis', 'percentage': 0}
            self.store.write(workspace.owner, workspace.identity, workspace.document)
        def worker():
            started = time.monotonic()
            from backend.core.run_history import current_user
            token = current_user.set({'id': workspace.owner})
            def report(data, offset=0, scale=1):
                with workspace.lock:
                    value = data.get('percentage')
                    workspace.progress = {**workspace.progress, **data,
                                          'percentage': None if value is None else round(offset + value * scale, 1),
                                          'elapsedSeconds': round(time.monotonic() - started, 2)}
            try:
                from backend.core.project_intelligence import Index
                from virtual_plc.core.project import analyze_project
                from virtual_plc.core.runtime import VirtualRuntime
                root = Path(workspace.document['projectRoot']).resolve()
                index = Index(root, workspace.owner)
                state = index.build(workspace.cancel, lambda data: report(data, 0, .35), 'rebuild' if rebuild else 'refresh')
                if workspace.cancel.is_set():
                    raise InterruptedError('Project analysis cancelled; original sources are unchanged.')
                report({'stage': 'Resolving controller, tasks, types, logic and HMI', 'percentage': 0}, 35, .5)
                model = analyze_project(root, progress=lambda data: report(data, 35, .5),
                                        cancel=workspace.cancel, configuration=workspace.document.get('configuration'))
                model['intelligenceProjectId'] = index.key
                model['indexStatus'] = state
                if workspace.cancel.is_set():
                    raise InterruptedError('Project analysis cancelled.')
                report({'stage': 'Compiling supported logic and checking dependencies', 'percentage': 87})
                executable = corrections(model, workspace.document.get('manualCorrections') or {})
                runtime = VirtualRuntime(executable)
                if workspace.cancel.is_set():
                    raise InterruptedError('Project analysis cancelled.')
                report({'stage': 'Saving source evidence and engineering snapshot', 'percentage': 96})
                complete, notices = self.store.cache_sources(workspace.owner, workspace.identity, root, model.get('files', []))
                if workspace.cancel.is_set():
                    raise InterruptedError('Project analysis cancelled before snapshot activation.')
                self.store.save_model(workspace.owner, workspace.identity, model)
                with workspace.lock:
                    workspace.model = executable
                    workspace.public_model = public_model(executable, runtime)
                    workspace.runtime = runtime
                    workspace.devices = None
                    workspace.device_error = ''
                    workspace.document.update(status='ready', moduleVersion=__version__, sourceCacheComplete=complete,
                                              sourceCacheNotices=notices, modelRevision=str(time.time_ns()))
                    workspace.progress = {'stage': 'Project analyzed; review simulation compatibility', 'percentage': 100,
                                          'elapsedSeconds': round(time.monotonic() - started, 2), 'index': state}
                    self.store.write(workspace.owner, workspace.identity, workspace.document)
            except InterruptedError as error:
                with workspace.lock:
                    workspace.document['status'] = 'cancelled'
                    workspace.document['analysisMessage'] = str(error)[:1000]
                    workspace.progress.update(stage=str(error), percentage=None)
                    self.store.write(workspace.owner, workspace.identity, workspace.document)
            except Exception as error:
                from backend.core.runtime import log
                log.exception('VIRTUAL_PLC_ANALYSIS_ERROR workspace=%s', workspace.identity)
                with workspace.lock:
                    workspace.document['status'] = 'error'
                    workspace.document['analysisMessage'] = str(error)[:1000]
                    workspace.progress.update(stage=str(error)[:1000], percentage=None)
                    self.store.write(workspace.owner, workspace.identity, workspace.document)
            finally:
                current_user.reset(token)
        workspace.thread = threading.Thread(target=worker, name='virtual-plc-analysis', daemon=True)
        workspace.thread.start()

    def snapshot(self, workspace, runtime_only=False):
        with workspace.lock:
            workspace.accessed = time.monotonic()
            result = {**workspace.document, 'moduleVersion': __version__, 'progress': dict(workspace.progress),
                      'runtime': runtime_view(workspace.runtime, workspace.document.get('watchlist', [])) if workspace.runtime else None}
            result.pop('projectRoot', None)
            result.pop('symbolIdentityMigration', None)
            if not runtime_only:
                result['components'] = self.component_state(workspace)['components']
            else:
                result.pop('components', None)
            if not runtime_only:
                result['model'] = workspace.public_model
            return result

    def component_catalog(self):
        return component_catalog()

    def configure_cpu(self,workspace,payload):
        from .cpu import configuration
        prepared=configuration(payload)
        with workspace.lock:
            if not workspace.runtime or workspace.document.get('status')!='ready':raise ValueError('Complete project analysis first.')
            if workspace.runtime.status=='running' or workspace.runtime._pending is not None:raise ValueError('Pause or reset before configuring CPU services.')
            workspace.runtime.cpu.configure(prepared)
            workspace.runtime.cpu.publish_io()
            workspace.document.setdefault('manualCorrections',{})['cpuServices']=prepared
            workspace.model['cpuServices']=prepared
            self._persist(workspace)
            return workspace.runtime.cpu.summary()

    def create_program_test(self, workspace, identity, interval_ms=None):
        from .program_test import program_model
        with workspace.lock:
            if not workspace.model or workspace.document.get('status') != 'ready':
                raise ValueError('Complete project analysis first.')
            model = program_model(workspace.model, identity, workspace.identity, interval_ms)
            bundle = self.store.export(workspace.owner, workspace.identity)
            bundle.update(model=model, results=None)
            bundle['workspace'] = {'name': model['name'], 'settings': {'autosave': True, 'speed': 1},
                                   'components': [], 'watchlist': [], 'manualCorrections': {},
                                   'sourceCacheComplete': bool(workspace.document.get('sourceCacheComplete')),
                                   'sourceCacheNotices': deepcopy(workspace.document.get('sourceCacheNotices', []))}
            document = self.store.import_document(workspace.owner, bundle, name=model['name'])
            document.update(executionScope=model['executionScope'], moduleVersion=__version__, status='ready')
            self.store.write(workspace.owner, document['id'], document)
        return self.snapshot(self.get(workspace.owner, document['id']))

    def create_hmi_preview(self,workspace,page_id):
        from .hmi_preview import preview_model
        with workspace.lock:
            if not workspace.runtime or workspace.document.get('status')!='ready':raise ValueError('Complete project analysis first.')
            model=preview_model(workspace.model,workspace.runtime,page_id,workspace.identity)
            bundle=self.store.export(workspace.owner,workspace.identity)
            bundle.update(model=model,results=None)
            bundle['workspace']={'name':model['name'],'settings':{'autosave':True,'speed':1},'components':[],
                'watchlist':[],'manualCorrections':{},'sourceCacheComplete':bool(workspace.document.get('sourceCacheComplete')),
                'sourceCacheNotices':deepcopy(workspace.document.get('sourceCacheNotices',[]))}
            document=self.store.import_document(workspace.owner,bundle,name=model['name'])
            document.update(executionScope=model['executionScope'],moduleVersion=__version__,status='ready')
            self.store.write(workspace.owner,document['id'],document)
        return self.snapshot(self.get(workspace.owner,document['id']))

    def _devices(self, workspace):
        if workspace.runtime is None:
            return None
        if workspace.devices is None and not workspace.device_error:
            try:
                workspace.devices = DeviceComponents(workspace.document.get('components', []), workspace.runtime)
            except (ValueError, TypeError, KeyError, IndexError) as error:
                # A changed project can invalidate old bindings. Keep the
                # workspace accessible so the user can repair its device draft.
                workspace.device_error = str(error)[:1000]
        if workspace.devices:
            workspace.devices.active = workspace.document.get('settings',{}).get('simulationJigEnabled', False)
            if workspace.devices.active and not workspace.devices.started:
                workspace.devices.prepare()
        return workspace.devices

    def component_state(self, workspace):
        with workspace.lock:
            devices = self._devices(workspace)
            components = devices.snapshot() if devices else [
                {**deepcopy(item), 'status': {'state': 'error' if workspace.device_error else 'blocked',
                 'message': workspace.device_error or 'Complete project analysis before connecting components.'}}
                for item in workspace.document.get('components', [])]
            machine={}
            for name,address in (workspace.document.get('simulationJig',{}).get('profile') or {}).get('statusSignals',{}).items():
                try:machine[name]=workspace.runtime.get_value(address)
                except (ValueError,KeyError,TypeError):machine[name]=None
            return {'components': components, 'catalog': component_catalog(), 'virtualOnly': True, 'maximumComponents':2048,
                    'environment':workspace.document.get('environment'),
                    'jig':{**workspace.document.get('simulationJig',{}),
                           'enabled':bool(devices and devices.active),
                           'plcStatus':workspace.runtime.status if workspace.runtime else 'unavailable',
                           'machine':machine,
                           'automaticSensors':sum(c.get('kind') in {'digital_input','analog_input'} and bool(c.get('config',{}).get('automatic')) for c in workspace.document.get('components',[]))}}

    def configure_jig(self, workspace, enabled, reset_defaults=False):
        """Physical simulation is an explicit mode, separate from PLC execution."""
        if type(enabled) is not bool or type(reset_defaults) is not bool:
            raise ValueError('Jig enabled/resetDefaults must be true or false.')
        from .environment import bench_profile, build_plan, initialize_bench
        with workspace.lock:
            if not workspace.runtime or workspace.document.get('status')!='ready':
                raise ValueError('Complete project analysis before enabling the simulation jig.')
            prepared=workspace.document.get('simulationJig',{}).get('prepared',False)
            if enabled and workspace.runtime._pending is not None:
                raise ValueError('Finish the pending PLC scan before changing the simulation jig.')
            if enabled and (reset_defaults or not prepared):
                from .runtime import VirtualRuntime
                base=self.store.model(workspace.owner,workspace.identity)
                profile=bench_profile(workspace.runtime)
                options=deepcopy(workspace.document.get('manualCorrections',{}))
                if reset_defaults and profile and profile.get('sourceCorrections') and 'sourceCorrections' not in options:
                    directory=Path(__file__).resolve().parents[1]/'examples'
                    path=(directory/profile['sourceCorrections']).resolve()
                    if not path.is_relative_to(directory.resolve()):raise ValueError('Invalid jig correction resource.')
                    document=json.loads(path.read_text(encoding='utf-8'))
                    import hashlib
                    sources={p['source']:p.get('code','') for p in base.get('programs',[])}
                    if all(hashlib.sha256(sources.get(c['source'],'').encode()).hexdigest()==c['codeSha256'] for c in document['corrections']):
                        options['sourceCorrections']=document
                if reset_defaults:
                    model=corrections(base,options)
                    runtime=VirtualRuntime(model)
                    for identity,record in workspace.runtime.memory.records.items():
                        if record.get('retain') and identity in runtime.memory.records:
                            runtime.set_value(identity,deepcopy(record['value']),return_snapshot=False)
                else:
                    # Enabling field feedback must not reset task state or stop a running PLC.
                    model,runtime=workspace.model,workspace.runtime
                plan=build_plan(runtime,workspace.document.get('components',[]))
                components=plan['components']
                initialization=(initialize_bench(runtime,components) if reset_defaults
                                else plan.get('initializationProfile'))
                for component in components:
                    if reset_defaults and 'faultInjected' in component['config']:component['config']['faultInjected']=0
                devices=DeviceComponents(components,runtime)
                if reset_defaults:workspace.runtime.command('pause',return_snapshot=False)
                workspace.model,workspace.runtime=model,runtime
                workspace.public_model=public_model(model,runtime)
                workspace.devices,workspace.device_error=devices,''
                workspace.environment_cache=None
                if reset_defaults:
                    workspace.hmi_pressed.clear()
                    workspace.scenario_cursor=0
                workspace.document.update(manualCorrections=options,components=devices.components,modelRevision=str(time.time_ns()))
                workspace.document['environment']={k:v for k,v in plan.items() if k!='components'}
                workspace.document['environment']['initializationProfile']=initialization
                workspace.document['simulationJig']={'prepared':True,'profile':initialization,
                    'message':('Jig defaults restored; PLC reset and stopped. Press Run PLC, then use the operator controls.' if reset_defaults
                               else 'Jig connected. PLC task state is preserved; feedback follows actual output commands. Use START or a configured scenario when required.')}
            workspace.document.setdefault('settings',{})['simulationJigEnabled']=enabled
            if enabled:workspace.document['settings'].setdefault('backgroundLoad','fast')
            devices=self._devices(workspace)
            if enabled and devices:devices.prepare()
            self._persist(workspace)
            return {**self.component_state(workspace),'runtime':runtime_view(workspace.runtime,workspace.document.get('watchlist',[])),
                    'settings':deepcopy(workspace.document['settings']),
                    'modelRevision':workspace.document.get('modelRevision'),
                    'manualCorrections':deepcopy(workspace.document.get('manualCorrections',{}))}

    def build_environment(self, workspace, apply=False):
        from .environment import build_plan
        with workspace.lock:
            if not workspace.runtime or workspace.document.get('status')!='ready':
                raise ValueError('Complete project analysis before building the simulation environment.')
            if workspace.runtime.status=='running':
                raise ValueError('Pause the simulation before building or changing field connections.')
            plan=build_plan(workspace.runtime,workspace.document.get('components',[]))
            if apply:
                workspace.document.setdefault('settings',{}).setdefault('simulationJigEnabled',False)
                workspace.document['environment']={k:v for k,v in plan.items() if k!='components'}
                self.configure_components(workspace,plan['components'])
                return {**self.component_state(workspace),'plan':workspace.document['environment']}
            return plan

    def confirm_mapping(self,workspace,mapping_id,bindings=None,config=None):
        from .environment import build_plan
        with workspace.lock:
            if not workspace.runtime or workspace.document.get('status')!='ready':raise ValueError('Complete project analysis first.')
            if workspace.runtime.status=='running' or workspace.runtime._pending is not None:
                raise ValueError('Pause the PLC and finish its scan before confirming connections.')
            plan=build_plan(workspace.runtime,workspace.document.get('components',[]))
            proposal=next((item for item in plan['pendingMappings'] if item['id']==mapping_id),None)
            if not proposal:raise ValueError('This proposal is stale. Analyze the current project connections again.')
            if proposal.get('candidates') and bindings is None:raise ValueError('Several exact tags match. Choose the required PLC tags in Configure component.')
            if bindings is not None:proposal['bindings']=bindings
            if config is not None:proposal['config']=config
            proposal=validate_components([proposal],workspace.runtime)[0]
            selected=set(proposal['bindings'].values())
            kept=[]
            for item in workspace.document.get('components',[]):
                if selected.intersection(item.get('bindings',{}).values()):
                    if item.get('evidence',{}).get('method')!='Exact selected-configuration I/O mapping':
                        raise ValueError('An existing configured device owns this signal. Review its connections before replacing it.')
                else:kept.append(item)
            proposal['evidence'].update(confidence='confirmed',mappingSource='operator-confirmed')
            configured=validate_components(kept+[proposal],workspace.runtime)
            self.configure_components(workspace,configured)
            updated=build_plan(workspace.runtime,configured)
            # A confirmed device already owns its ports and needs no repeated proposal.
            workspace.document['environment']={key:value for key,value in updated.items() if key!='components'}
            workspace.document['environment']['pendingMappings']=[item for item in updated['pendingMappings'] if item['id']!=mapping_id]
            self._persist(workspace)
            return self.component_state(workspace)

    def environment_status(self, workspace, query='', offset=0, target='', view='alarms'):
        from .environment import LogicIndex, alarm_rows
        with workspace.lock:
            runtime=workspace.runtime
            if not runtime: raise ValueError('Complete project analysis first.')
            if not workspace.environment_cache or workspace.environment_cache['runtime'] is not runtime:
                workspace.environment_cache={'runtime':runtime,'index':LogicIndex(runtime),'alarms':alarm_rows(runtime)}
            cached=workspace.environment_cache
            physical={c['bindings']['value']:c['id'] for c in workspace.document.get('components',[])
                      if c['kind'] in {'digital_input','analog_input','pushbutton'} and c.get('bindings',{}).get('value')}
            query=str(query)[:200].casefold(); offset=max(0,min(int(offset),100000))
            if target:
                from .environment import scoped
                identity = scoped(runtime, str(target)[:400])
                if not identity: raise ValueError('Choose an exact declared PLC signal.')
                inputs, locations, limited = cached['index'].dependencies(identity, physical)
                return {'variable':identity, 'value':runtime.get_value(identity), 'inputs':inputs,
                        'logicSources':locations, 'dependencyLimitReached':limited, 'timeMs':runtime.time_ms}
            if view == 'timers':
                timers = [record for record in runtime.memory.records.values()
                          if record.get('_spec',{}).get('kind') == 'block'
                          and record.get('_spec',{}).get('type','').upper() in {'TON','TOF','TP'}
                          and query in (record['id']+' '+str(record.get('source',''))).casefold()]
                return {'timers':[{'variable':record['id'],'name':record['name'],
                                  'type':record['_spec']['type'],'source':record.get('source'),
                                  'line':record.get('line'),'value':{key:record['value'].get(key) for key in ('IN','PT','ET','Q')}}
                                 for record in timers[offset:offset+25]],
                        'total':len(timers),'timeMs':runtime.time_ms}
            selected=[r for r in cached['alarms'] if query in str(r).casefold()]
            rows=[]
            for original in selected[offset:offset+25]:
                row=dict(original)
                try: row.update(value=bool(runtime.get_value(row['variable'])),quality='simulated') if row['variable'] else row.update(value=None,quality='unresolved')
                except (ValueError,TypeError,KeyError): row.update(value=None,quality='unresolved')
                row['inputs'],row['logicSources'],row['dependencyLimitReached']=cached['index'].dependencies(row.get('variable'),physical) if row.get('variable') else ([],[],False)
                rows.append(row)
            return {'alarms':rows,'total':len(selected),'offset':offset,'limit':25,'timeMs':runtime.time_ms,
                    'summary':workspace.document.get('environment',{}).get('summary',{}),
                    'unresolved':workspace.document.get('environment',{}).get('unresolved',[])[:50]}

    def move_components(self, workspace, positions):
        """Save presentation coordinates without resetting the running field model."""
        if not isinstance(positions, dict) or len(positions) > 2048:
            raise ValueError('Provide at most 2048 device positions.')
        with workspace.lock:
            configured = {c['id']: c for c in workspace.document.get('components', [])}
            for identity, position in positions.items():
                if identity not in configured:
                    raise ValueError('Choose a configured device to move.')
                if (not isinstance(position, dict) or set(position) != {'x', 'y'} or
                    any(type(position[k]) not in {int, float} or not math.isfinite(position[k])
                        or not 0 <= position[k] <= 12000 for k in ('x', 'y'))):
                    raise ValueError('Device coordinates must be finite numbers within 0..12000.')
            devices = self._devices(workspace)
            for identity, position in positions.items():
                configured[identity]['position'] = dict(position)
                if devices:
                    next(c for c in devices.components if c['id'] == identity)['position'] = dict(position)
            self.store.write(workspace.owner, workspace.identity, workspace.document)
            return {'positions': positions, 'saved': True}

    def configure_components(self, workspace, components):
        with workspace.lock:
            runtime = workspace.runtime
            if runtime is None or workspace.document.get('status') != 'ready':
                raise ValueError('Complete project analysis before connecting components.')
            if runtime.status == 'running':
                raise ValueError('Pause the simulation before changing device connections.')
            if runtime._pending is not None:
                raise ValueError('Finish the pending scan or reset before changing device connections.')
            configured = validate_components(components, runtime)
            devices = DeviceComponents(configured, runtime)
            workspace.document['components'] = configured
            workspace.devices, workspace.device_error = devices, ''
            self._persist(workspace)
            return self.component_state(workspace)

    def set_component_signal(self, workspace, identity, value):
        with workspace.lock:
            devices = self._devices(workspace)
            if workspace.document.get('status') != 'ready' or not devices:
                raise ValueError('Complete project analysis and save valid component connections first.')
            if not devices.active:raise ValueError('Switch Simulation jig ON before operating field devices.')
            configured = deepcopy(workspace.document.get('components', []))
            component = next((item for item in configured if item['id'] == identity), None)
            if not component or component['kind'] not in {'digital_input', 'analog_input', 'pushbutton'}:
                raise ValueError('Choose a configured pushbutton, DI or AI input.')
            if component['kind'] == 'pushbutton':
                if value not in (0,1,2,False,True): raise ValueError('Pushbuttons accept pulse (1), hold (2) or release (0).')
                devices.states[identity]['pressedUntilMs'] = None if value == 2 else workspace.runtime.time_ms + component['config']['pulseMs'] if value else 0
            else:
                component['config']['value'] = int(value) if type(value) is bool else value
                if component['kind'] in {'digital_input','analog_input'}:component['config']['automatic']=0
            configured = validate_components(configured, workspace.runtime)
            workspace.document['components'] = configured
            target = next(item for item in devices.components if item['id'] == identity)
            target['config'] = next(item['config'] for item in configured if item['id'] == identity)
            devices.pending_signals.add(identity)
            devices.prepare()
            self.store.write(workspace.owner, workspace.identity, workspace.document)
            # Persist the small device configuration without copying PLC arrays.
            return self.component_state(workspace)

    def set_component_automatic(self, workspace, identity):
        with workspace.lock:
            devices=self._devices(workspace)
            if not devices or not devices.active:raise ValueError('Switch Simulation jig ON first.')
            target=next((c for c in devices.components if c['id']==identity),None)
            if not target or target['kind'] not in {'digital_input','analog_input'} or not any(target['bindings'].get(k) or target.get('links',{}).get(k) for k in ('command','enable')):
                raise ValueError('This sensor has no configured automatic feedback command.')
            target['config']['automatic']=1
            devices.states[identity].pop('desiredValue',None)
            original=next(c for c in workspace.document['components'] if c['id']==identity)
            original['config']['automatic']=1
            self.store.write(workspace.owner,workspace.identity,workspace.document)
            return self.component_state(workspace)

    def set_component_fault(self, workspace, identity, active):
        with workspace.lock:
            if type(active) is not bool: raise ValueError('Fault injection requires true or false.')
            devices = self._devices(workspace)
            target = next((c for c in devices.components if c['id'] == identity), None) if devices else None
            if not target or target['kind'] not in {'servo','vfd','velocity_servo','motor','cylinder'}: raise ValueError('Choose a motor, cylinder, servo or VFD component.')
            target['config']['faultInjected'] = int(active)
            devices.states[identity]['current']['fault'] = active
            if active and devices.states[identity].get('faultSinceMs') is None:
                devices.states[identity]['faultSinceMs'] = workspace.runtime.time_ms
            elif not active:
                devices.states[identity]['faultSinceMs'] = None
            original = next(c for c in workspace.document['components'] if c['id'] == identity)
            original['config']['faultInjected'] = int(active)
            devices.pending_signals.add(identity)
            devices.prepare()
            self.store.write(workspace.owner, workspace.identity, workspace.document)
            return self.component_state(workspace)

    def command(self, workspace, action, speed=None):
        if speed is not None and float(speed) not in {.25, .5, 1, 2, 5}:
            raise ValueError('Choose simulation speed 0.25, 0.5, 1, 2 or 5.')
        with self.guard, workspace.lock:
            if not workspace.runtime or workspace.document['status'] != 'ready':
                raise ValueError('Complete project analysis before controlling simulation.')
            if action == 'run':
                with self.guard:
                    count = sum(bool(row is not workspace and row.runtime and row.runtime.status == 'running')
                                for row in self.workspaces.values())
                    if count >= MAX_RUNNING:
                        raise ValueError('At most two Virtual PLC simulations can run at the same time on this server.')
            devices = self._devices(workspace)
            if action in {'run', 'scan', 'step'}:
                if workspace.device_error:
                    raise ValueError('Repair or remove invalid device connections: ' + workspace.device_error)
                if workspace.runtime.status != 'faulted' and devices:
                    devices.prepare()
            workspace.runtime.command(action, speed=speed, return_snapshot=False)
            if action in {'scan', 'step'} and devices:
                devices.after_scan()
            if speed is not None:
                workspace.document['settings']['speed'] = float(speed)
            if action in {'reset', 'cold-reset'}:
                workspace.scenario_cursor = 0
                workspace.devices, workspace.device_error = None, ''
            self._persist(workspace)
        if action == 'run':
            self._start_worker()
        return runtime_view(workspace.runtime, workspace.document.get('watchlist', []))

    def update(self, workspace, payload):
        validate_configuration(payload)
        if 'components' in payload:
            raise ValueError('Use Save connections in Components to update device bindings.')
        with workspace.lock:
            if 'name' in payload:
                name = str(payload['name']).strip()
                if not name or len(name) > 180:
                    raise ValueError('Give the workspace a name of 1..180 characters.')
                workspace.document['name'] = name
            if 'settings' in payload:
                settings = payload['settings']
                if not isinstance(settings, dict) or len(json.dumps(settings)) > 65536:
                    raise ValueError('Invalid workspace settings.')
                allowed = {'theme', 'autosave', 'speed', 'panels', 'zoom', 'selectedTab', 'selectedSource',
                           'breakpoints', 'templateKind', 'activeScenario', 'backgroundLoad'}
                if 'activeScenario' in settings and settings['activeScenario'] != workspace.document['settings'].get('activeScenario'):
                    workspace.scenario_cursor = 0
                workspace.document['settings'].update({key: value for key, value in settings.items() if key in allowed})
            if 'watchlist' in payload:
                watchlist = payload['watchlist']
                if not isinstance(watchlist, list) or len(watchlist) > 500 or any(not isinstance(item, str) for item in watchlist):
                    raise ValueError('Use at most 500 variable names in a watchlist.')
                workspace.document['watchlist'] = watchlist
            if 'manualCorrections' in payload and payload['manualCorrections'] != workspace.document.get('manualCorrections', {}):
                if workspace.runtime and workspace.runtime.status == 'running':
                    raise ValueError('Pause the simulation before changing virtual task or I/O configuration.')
                options = payload['manualCorrections']
                if len(json.dumps(options)) > 65536:
                    raise ValueError('Manual virtual corrections exceed 64 KiB.')
                from virtual_plc.core.runtime import VirtualRuntime
                model = corrections(self.store.model(workspace.owner, workspace.identity), options)
                runtime = VirtualRuntime(model)
                workspace.document['manualCorrections'] = options
                workspace.document['modelRevision'] = str(time.time_ns())
                workspace.model = model
                workspace.public_model = public_model(model, runtime)
                workspace.runtime = runtime
                workspace.devices, workspace.device_error = None, ''
                workspace.scenario_cursor = 0
            if 'scenarios' in payload:
                scenarios = payload['scenarios']
                if not isinstance(scenarios, list) or len(scenarios) > 20:
                    raise ValueError('Save at most 20 simulation scenarios.')
                for scenario in scenarios:
                    events = scenario.get('events', [])
                    if len(events) > 1000 or any(not isinstance(event.get('name'), str) or not isinstance(event.get('timeMs'), (int, float)) or event['timeMs'] < 0 for event in events):
                        raise ValueError('Scenario events need a name, value and nonnegative timeMs; maximum 1000 events.')
                    scenario['events'] = sorted(events, key=lambda event: event['timeMs'])
                workspace.document['scenarios'] = scenarios
                workspace.scenario_cursor = 0
            self._persist(workspace)
        return self.snapshot(workspace, runtime_only='manualCorrections' not in payload)

    def recheck(self, workspace):
        """Apply updated interpreter support to the saved model without reindexing."""
        from virtual_plc.core.runtime import VirtualRuntime
        with workspace.lock:
            if workspace.document.get('status') != 'ready' or not workspace.model:
                raise ValueError('Wait for project analysis to finish.')
            if workspace.runtime and workspace.runtime.status == 'running':
                raise ValueError('Pause the simulation before rechecking compatibility.')
            self._upgrade_views(workspace, workspace.model)
            runtime = VirtualRuntime(workspace.model)
            for point in workspace.document.get('settings', {}).get('breakpoints', [])[:500]:
                if isinstance(point, dict) and point.get('source') and type(point.get('line')) is int:
                    runtime.set_breakpoint(point['source'], point['line'], point.get('enabled') is not False, return_snapshot=False)
            workspace.runtime = runtime
            workspace.devices, workspace.device_error = None, ''
            workspace.public_model = public_model(workspace.model, runtime)
            workspace.scenario_cursor = 0
            workspace.document.update(moduleVersion=__version__, modelRevision=str(time.time_ns()))
            workspace.progress = {'stage': 'Compatibility updated; virtual memory reset', 'percentage': 100}
            self._persist(workspace)
        return self.snapshot(workspace)

    def _persist(self, workspace):
        self.store.write(workspace.owner, workspace.identity, workspace.document)
        if workspace.runtime:
            state = workspace.runtime.snapshot(state_only=True)
            state.pop('variables', None)  # Declarations already live in the immutable model.
            state['trace'] = state.get('trace', [])[-1000:]
            self.store.save_state(workspace.owner, workspace.identity, state)
        workspace.saved_at = time.monotonic()

    def _restore_retention(self, workspace):
        state_file = self.store.folder(workspace.owner, workspace.identity) / 'state.json'
        if not state_file.is_file():
            return
        from virtual_plc.core.storage import bounded_json
        previous = bounded_json(state_file).get('memory', {})
        remap = workspace.document.get('symbolIdentityMigration', {})
        previous = {remap.get(key, key): value for key, value in previous.items()}
        for variable in workspace.model.get('variables', []):
            if variable.get('retain') and variable.get('id') in previous:
                try:
                    workspace.runtime.set_value(variable['id'], previous[variable['id']], return_snapshot=False)
                except (KeyError, ValueError, TypeError):
                    continue
        for point in workspace.document.get('settings', {}).get('breakpoints', [])[:500]:
            if isinstance(point, dict) and point.get('source') and type(point.get('line')) is int:
                workspace.runtime.set_breakpoint(point['source'], point['line'], point.get('enabled') is not False, return_snapshot=False)

    def _scenario_event(self,workspace,event):
        """Explicit scenario contacts must reach the same device inputs as manual controls."""
        from .environment import scoped
        runtime=workspace.runtime
        devices=self._devices(workspace)
        identity=scoped(runtime,event['name'])
        runtime.set_value(event['name'],event.get('value'),force=event.get('force') is True,return_snapshot=False)
        if not devices or not devices.active or not identity:return
        for component in devices.components:
            if component.get('bindings',{}).get('value')!=identity:continue
            if component['kind']=='pushbutton':
                pressed=bool(event.get('value'))!=bool(component['config']['releasedValue'])
                devices.states[component['id']]['pressedUntilMs']=None if pressed else 0
            elif component['kind'] in {'digital_input','analog_input'}:
                component['config'].update(value=event.get('value'),automatic=0)
                original=next(item for item in workspace.document['components'] if item['id']==component['id'])
                original['config'].update(value=event.get('value'),automatic=0)
                devices.pending_signals.add(component['id'])

    def _run(self):
        next_tick = {}
        while not self.stop_event.wait(.002):
            with self.guard:
                workspaces = list(self.workspaces.values())
            now = time.monotonic()
            for workspace in workspaces:
                with workspace.lock:
                    runtime = workspace.runtime
                    if not runtime or runtime.status != 'running':
                        continue
                    key = (workspace.owner, workspace.identity)
                    if now < next_tick.get(key, 0):
                        continue
                    try:
                        tick_started = time.monotonic()
                        before = runtime.time_ms
                        batch_start=runtime.scan_count
                        # Batch cheap scheduler quanta with a short wall-time budget.
                        # A 0.4 ms PLC task must not incur a 10 ms host sleep per scan.
                        while runtime.status=='running':
                            scenario = workspace.document['settings'].get('activeScenario')
                            sequence = next((row for row in workspace.document.get('scenarios', []) if row.get('id') == scenario), None)
                            if sequence:
                                events = sequence.get('events', [])
                                while workspace.scenario_cursor < len(events) and events[workspace.scenario_cursor]['timeMs'] <= runtime.time_ms:
                                    event = events[workspace.scenario_cursor]
                                    self._scenario_event(workspace,event)
                                    workspace.scenario_cursor += 1
                            devices = self._devices(workspace)
                            if devices:
                                devices.prepare()
                            runtime.tick()
                            if devices:
                                devices.after_scan()
                            if runtime.scan_count-batch_start>=32 or time.monotonic()-tick_started>=.008:
                                break
                        after = runtime.time_ms
                        speed = float(workspace.document['settings'].get('speed') or 1)
                        finished = time.monotonic()
                        share = {'responsive': .1, 'balanced': .25, 'fast': .75}.get(workspace.document['settings'].get('backgroundLoad'), .25)
                        duration = max(.001, finished-tick_started)
                        next_tick[key] = finished + max(.002, duration*(1-share)/share, (after-before)/1000/max(.25,min(5,speed)))
                        runtime.performance = {'lastScanWallMs': round(duration*1000, 2), 'backgroundLoad': workspace.document['settings'].get('backgroundLoad', 'balanced'), 'cpuShare': share, 'scansPerBatch':runtime.scan_count-batch_start, 'scanBatchBudgetMs':8}
                        if workspace.document['settings'].get('autosave', True) and finished - workspace.saved_at >= 30:
                            self._persist(workspace)
                    except Exception as error:
                        from backend.core.runtime import log
                        log.exception('VIRTUAL_PLC_SCAN_ERROR workspace=%s', workspace.identity)
                        try:
                            runtime.command('pause', return_snapshot=False)
                        except Exception:
                            pass
                        workspace.progress['runtimeError'] = str(error)[:1000]

    def close(self):
        self.stop_event.set()
        with self.guard:
            workspaces = list(self.workspaces.values())
        for workspace in workspaces:
            workspace.cancel.set()
            with workspace.lock:
                if workspace.runtime:
                    workspace.runtime.command('pause', return_snapshot=False)
                self._persist(workspace)
        if self.worker:
            self.worker.join(timeout=2)
        # Let cancellable index readers release their SQLite handles before
        # shutdown returns. Never join while holding a workspace lock.
        deadline = time.monotonic() + 3
        for workspace in workspaces:
            if workspace.thread and workspace.thread.is_alive():
                workspace.thread.join(timeout=max(0, deadline - time.monotonic()))
