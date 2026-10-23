"""Virtual PLC routes added by the extension launcher; existing routes are reused."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from collections import Counter
import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.core.runtime import WORK, _local_path, locate_root, stage_project
from backend.core.access import require_session, owns_resource
from virtual_plc import __version__
from virtual_plc.core.service import VirtualPLCService, runtime_view, value_preview
from virtual_plc.core.storage import MAX_DOCUMENT, MAX_SOURCE, SOURCE_EXTENSIONS, bounded_json

router = APIRouter(prefix='/api/virtual-plc', tags=['Virtual PLC'])
service = VirtualPLCService(WORK / 'virtual_plc')


def owner(request):
    user = getattr(request.state, 'user', None)
    if not user or not user.get('id'):
        raise HTTPException(401, 'Sign in to uSOPp.ai before opening a Virtual PLC workspace.')
    return str(user['id'])


def opened(request, identity):
    try:
        return service.get(owner(request), identity)
    except (OSError, ValueError) as error:
        raise HTTPException(404, str(error)) from error


def fail(error):
    if isinstance(error, HTTPException):
        raise error
    raise HTTPException(400, str(error)) from error


@router.get('/health')
def module_health(request: Request):
    owner(request)
    return {'status': 'ready', 'moduleVersion': __version__, 'simulation': 'virtual-memory-only',
            'originalSourceWrites': False, 'maximumRunning': 2, 'maximumResident': 3}


@router.get('/sessions')
def sessions(request: Request):
    owner(request)
    records = []
    for folder in WORK.iterdir():
        if not folder.is_dir() or not owns_resource(folder):
            continue
        marker = folder / 'project_upload.json'
        manifest = folder / 'inputs.json'
        try:
            data = bounded_json(marker) if marker.is_file() else bounded_json(manifest) if manifest.is_file() else {}
            if marker.is_file() and not data.get('complete'):
                continue
            root = data.get('projectRoot') or data.get('project')
            if root and Path(root).is_dir():
                records.append({'sessionId': folder.name, 'projectPath': root,
                                'projectName': data.get('projectName') or Path(root).name})
        except (OSError, ValueError):
            continue
    return {'sessions': records[:100]}


@router.get('/projects')
def projects(request: Request):
    return {'projects': service.store.list(owner(request)), 'moduleVersion': __version__}


@router.get('/component-catalog')
def component_catalog(request: Request):
    owner(request)
    return {'catalog': service.component_catalog(), 'virtualOnly': True,
            'physicalConnections': False,
            'description': 'Generic virtual device signals; vendor drive protocols are not emulated.'}


@router.get('/library-support')
def library_support(request: Request):
    owner(request)
    from virtual_plc.core.vendor import support_catalog
    return support_catalog()


@router.get('/component-library')
def component_library_items(request:Request):
    return {'items':service.component_library(owner(request)).list(),'models':service.component_catalog()}


@router.get('/component-library/{identity}')
def component_library_item(identity:str,request:Request):
    try:return service.component_library(owner(request)).load(identity)
    except (ValueError,OSError) as error:fail(error)


@router.put('/component-library/{identity}')
def update_component_library_item(identity:str,payload:dict,request:Request):
    try:return service.component_library(owner(request)).update(identity,payload)
    except (ValueError,OSError) as error:fail(error)


@router.post('/projects/{identity}/component-library')
def save_component_library_item(identity:str,payload:dict,request:Request):
    try:return service.save_component_library(opened(request,identity),payload)
    except (ValueError,TypeError,KeyError,OSError) as error:fail(error)


@router.post('/projects/{identity}/component-library/{library_id}/apply')
def apply_component_library_item(identity:str,library_id:str,payload:dict,request:Request):
    try:return service.apply_component_library(opened(request,identity),library_id,payload)
    except (ValueError,TypeError,KeyError,OSError) as error:fail(error)


@router.post('/component-library/{identity}/references')
async def attach_component_reference(identity:str,request:Request,file:UploadFile=File(...)):
    from .core.component_library import MAX_REFERENCE
    try:return service.component_library(owner(request)).attach(identity,file.filename,await file.read(MAX_REFERENCE+1))
    except (ValueError,OSError) as error:fail(error)
    finally:await file.close()


@router.get('/component-library/{identity}/references/{reference_id}')
def component_reference(identity:str,reference_id:str,request:Request):
    try:
        path,name=service.component_library(owner(request)).reference(identity,reference_id)
        return FileResponse(path,filename=name,media_type='application/octet-stream',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})
    except (ValueError,OSError) as error:fail(error)


@router.get('/library-reference')
def library_reference(request:Request,name:str='',library:str=''):
    owner(request)
    from virtual_plc.core.catalog import load_catalog
    registry=load_catalog(Path(__file__).resolve().parents[1]/'knowledge/virtual_plc/br_catalog.json')
    entries=[e for e in registry['entries'] if (not name or name.casefold() in e['name'].casefold()) and (not library or library.casefold()==e['library'].casefold())]
    return {'schemaVersion':registry['schemaVersion'],'total':len(entries),'entries':entries[:200],'truncated':len(entries)>200}


@router.get('/module-help')
def hardware_help(request: Request, q: str = ''):
    owner(request)
    from virtual_plc.core.module_help import search
    return {'results': search(q[:80])}


@router.get('/module-help/document')
def hardware_help_document(request: Request, path: str):
    owner(request)
    from virtual_plc.core.module_help import document
    try: return document(path)
    except (ValueError, OSError) as error: fail(error)


@router.get('/module-help/image')
def hardware_help_image(request: Request, path: str):
    owner(request)
    from fastapi.responses import FileResponse
    from virtual_plc.core.module_help import safe_path
    try: return FileResponse(safe_path(path, images=True))
    except (ValueError, OSError) as error: fail(error)


@router.get('/projects/{identity}/components')
def components(identity: str, request: Request):
    try:
        return service.component_state(opened(request, identity))
    except (ValueError, TypeError, KeyError, OSError) as error:
        fail(error)


@router.put('/projects/{identity}/components')
def save_components(identity: str, payload: dict, request: Request):
    try:
        return service.configure_components(opened(request, identity), payload.get('components'))
    except (ValueError, TypeError, KeyError, OSError) as error:
        fail(error)


@router.put('/projects/{identity}/component-layout')
def component_layout(identity: str, payload: dict, request: Request):
    try:
        return service.move_components(opened(request, identity), payload.get('positions'))
    except (ValueError, TypeError, KeyError, OSError) as error:
        fail(error)


@router.post('/projects/{identity}/environment')
def build_environment(identity: str, payload: dict, request: Request):
    try:
        return service.build_environment(opened(request, identity), payload.get('apply') is True)
    except (ValueError, TypeError, KeyError, OSError) as error:
        fail(error)


@router.get('/projects/{identity}/environment')
def environment_status(identity: str, request: Request, query: str = '', offset: int = 0, target: str = '', view: str = 'alarms'):
    try:
        return service.environment_status(opened(request, identity), query, offset, target, view)
    except (ValueError, TypeError, KeyError, OSError) as error:
        fail(error)


@router.post('/projects/{identity}/environment/mappings/{mapping_id}/confirm')
def confirm_environment_mapping(identity:str,mapping_id:str,payload:dict,request:Request):
    try:return service.confirm_mapping(opened(request,identity),mapping_id,payload.get('bindings'),payload.get('config'))
    except (ValueError,TypeError,KeyError,OSError) as error:fail(error)


@router.put('/projects/{identity}/simulation-jig')
def simulation_jig(identity: str, payload: dict, request: Request):
    try:
        return service.configure_jig(opened(request,identity),payload.get('enabled'),payload.get('resetDefaults',False))
    except (ValueError,TypeError,KeyError,OSError) as error:
        fail(error)


@router.put('/projects/{identity}/components/{component_id}/fault')
def component_fault(identity: str, component_id: str, payload: dict, request: Request):
    try:
        return service.set_component_fault(opened(request, identity), component_id, payload.get('active'))
    except (ValueError, TypeError, KeyError, OSError) as error:
        fail(error)


@router.post('/projects/{identity}/interface-values')
def interface_values(identity: str, payload: dict, request: Request):
    from virtual_plc.core.service import value_preview
    workspace = opened(request, identity)
    names = payload.get('names')
    if not isinstance(names, list) or len(names) > 1024 or any(not isinstance(n, str) or len(n) > 400 for n in names):
        raise HTTPException(400, 'Request at most 1024 bounded PLC interface addresses.')
    values, errors, controls, texts, layers, passwords = {}, {}, {}, {}, {}, {}
    with workspace.lock:
        if not workspace.runtime:
            raise HTTPException(409, 'Complete project analysis first.')
        for name in set(names):
            try:
                value, complete = value_preview(workspace.runtime.get_value(name))
                if not complete: raise ValueError('Select a specific scalar array or structure member.')
                values[name] = value
            except (ValueError, TypeError, KeyError, IndexError) as error:
                errors[name] = str(error)[:300]
        if payload.get('pageId'):
            from virtual_plc.core.hmi_runtime import control_state
            page = next((p for p in workspace.model.get('hmi', {}).get('pages', []) if p['id'] == payload['pageId']), None)
            if page:
                controls = {item['id']: control_state(item, workspace.runtime) for item in page.get('objects', [])}
                layers = {item['id']: control_state({'layerState': item}, workspace.runtime) for item in page.get('layers', [])}
                from virtual_plc.core.hmi_text import display_text
                for item in page.get('objects',[]):
                    if item.get('kind') == 'password' and controls[item['id']]['visible']:
                        from virtual_plc.core.hmi_runtime import password_source_status
                        passwords[item['id']] = password_source_status(workspace.model, item, workspace.runtime)
                    if item.get('kind') not in {'text','listbox','datetime'} or not controls[item['id']]['visible']:continue
                    try:
                        rendered=display_text(workspace.model,item,workspace.runtime)
                        if rendered is not None:texts[item['id']]=rendered
                    except (ValueError,TypeError,KeyError,IndexError) as error:
                        errors[item['id']]=str(error)[:300]
    return {'values': values, 'errors': errors, 'controls': controls, 'texts': texts, 'layers': layers, 'passwordSources': passwords}


@router.post('/projects/{identity}/hmi-action')
def hmi_action(identity: str, payload: dict, request: Request):
    """Validate the source control and current status under the same scan lock."""
    from virtual_plc.core.hmi_runtime import require_input, input_value, write_value, control_state, navigation_page
    workspace = opened(request, identity)
    try:
        with workspace.lock:
            runtime = workspace.runtime
            if not runtime or workspace.document.get('status') != 'ready':
                raise ValueError('Wait for project analysis to finish.')
            page = next((p for p in workspace.model.get('hmi', {}).get('pages', []) if p['id'] == payload.get('pageId')), None)
            control = next((o for o in (page or {}).get('objects', []) if o['id'] == payload.get('objectId')), None)
            if not control: raise ValueError('Choose an analyzed HMI control.')
            phase, result = payload.get('phase'), {}
            if phase == 'release':
                # Releasing an already pressed button must work after its layer hides.
                for action in workspace.hmi_pressed.pop(control['id'], []):
                    write_value(runtime, action['variable'], action.get('resetValue', '0'))
            elif phase == 'input':
                if len(json.dumps(payload.get('value'))) > 16384: raise ValueError('HMI input is too large.')
                result = input_value(workspace.model, page, control, runtime, payload.get('value'))
            elif phase == 'press':
                require_input(page, control, runtime)
                if control.get('kind') not in {'button', 'hotspot'}: raise ValueError('This control is not a button.')
                actions = control.get('actions', [])
                if not actions: raise ValueError('No supported source key action was resolved.')
                if control['id'] in workspace.hmi_pressed: raise ValueError('Release this button before pressing again.')
                for action in actions:
                    if action['kind'] == 'navigate':
                        result['navigation'] = navigation_page(workspace.model.get('hmi',{}).get('pages',[]),page,action['page'])['id']
                        continue
                    value = action.get('value', '1')
                    if action['kind'] == 'toggle':
                        record, reference = runtime.value_reference(action['variable'])
                        spec = runtime.memory.reference_spec(reference)
                        expected = runtime.memory.coerce(value, spec)
                        if runtime.get_value(action['variable']) == expected: value = action.get('resetValue', '0')
                    write_value(runtime, action['variable'], value)
                    if action['kind'] == 'momentary':
                        workspace.hmi_pressed.setdefault(control['id'], []).append(action)
            else: raise ValueError('Choose press, release or input.')
            result['controls']={item['id']:control_state(item,runtime) for item in page.get('objects',[])}
            result['layers']={item['id']:control_state({'layerState':item},runtime) for item in page.get('layers',[])}
            return result
    except (ValueError, KeyError, TypeError, IndexError, OverflowError) as error:
        fail(error)


@router.put('/projects/{identity}/components/{component_id}/signal')
def component_signal(identity: str, component_id: str, payload: dict, request: Request):
    try:
        return service.set_component_signal(opened(request, identity), component_id, payload.get('value'))
    except (ValueError, TypeError, KeyError, OSError) as error:
        fail(error)


@router.put('/projects/{identity}/components/{component_id}/automatic')
def component_automatic(identity: str, component_id: str, request: Request):
    try:
        return service.set_component_automatic(opened(request,identity),component_id)
    except (ValueError,TypeError,KeyError,OSError) as error:
        fail(error)


@router.post('/projects')
def create_project(payload: dict, request: Request):
    account = owner(request)
    try:
        if payload.get('sessionId'):
            folder = require_session(str(payload['sessionId']))
            for filename in ('project_upload.json', 'inputs.json'):
                path = folder / filename
                if path.is_file():
                    data = bounded_json(path)
                    if filename == 'project_upload.json' and not data.get('complete'):
                        raise ValueError('Finish uploading the PLC project before analysis.')
                    root = data.get('projectRoot') or data.get('project')
                    if root:
                        break
            else:
                root = None
            if not root:
                raise ValueError('This session does not contain an uploaded PLC project.')
        else:
            root = payload.get('projectPath')
        path = locate_root(_local_path(str(root or ''), True, True))
        return service.create(account, path, str(payload.get('name') or ''), payload.get('configuration'))
    except (OSError, ValueError, TypeError) as error:
        fail(error)


@router.post('/examples/starter')
def starter_project(request: Request):
    """A separately named teaching project, never a substitute for PLC results."""
    account = owner(request)
    path = Path(__file__).parent / 'examples' / 'StarterPLC'
    try:
        return service.create(account, path, 'Starter PLC - training example', 'Example')
    except (ValueError, OSError, TypeError) as error:
        fail(error)


@router.get('/projects/{identity}/compatibility')
def compatibility_findings(identity: str, request: Request, offset: int = 0,
                           limit: int = 75, code: str = '', query: str = ''):
    workspace = opened(request, identity)
    with workspace.lock:
        if not workspace.runtime:
            raise HTTPException(409, 'Wait for project analysis to finish.')
        rows = [row for row in workspace.runtime.diagnostics
                if row.get('severity') == 'error' and not row.get('excluded')]
        counts = Counter(str(row.get('code') or 'OTHER') for row in rows)
        selected = [row for row in rows if (not code or row.get('code') == code)
                    and (not query or query.casefold() in
                         f'{row.get("message", "")} {row.get("source", "")}'.casefold())]
        offset, limit = max(0, offset), max(1, min(150, limit))
        return {'runAllowed': workspace.runtime.run_allowed, 'total': len(selected),
                'blockers': len(rows), 'byCode': dict(counts),
                'findings': selected[offset:offset + limit], 'offset': offset, 'limit': limit,
                'retainedFindings': len(workspace.runtime.diagnostics),
                'diagnosticCount': max(workspace.runtime.diagnostic_count, len(workspace.runtime.diagnostics)),
                'diagnosticsTruncated': workspace.runtime.diagnostic_count > len(workspace.runtime.diagnostics),
                'note': 'Conversion-support findings describe the virtual interpreter, not a verdict on the real PLC.'}


@router.post('/projects/{identity}/recheck')
def recheck_project(identity: str, request: Request):
    try:
        return service.recheck(opened(request, identity))
    except (ValueError, TypeError, OSError) as error:
        fail(error)


@router.put('/projects/{identity}/cpu-services')
def configure_cpu_services(identity: str,payload: dict,request: Request):
    try:
        return service.configure_cpu(opened(request,identity),payload)
    except (ValueError,TypeError,KeyError,OSError) as error:
        fail(error)


@router.post('/projects/{identity}/hmi-preview')
def create_hmi_preview(identity: str,payload: dict,request: Request):
    try:
        return service.create_hmi_preview(opened(request,identity),payload.get('pageId'))
    except (ValueError,TypeError,KeyError,OSError) as error:
        fail(error)


@router.post('/projects/{identity}/program-test')
def create_program_test(identity: str, payload: dict, request: Request):
    try:
        return service.create_program_test(opened(request, identity), payload.get('programId'), payload.get('intervalMs'))
    except (ValueError, TypeError, KeyError, OSError) as error:
        fail(error)


@router.post('/upload')
async def upload_project(request: Request, files: List[UploadFile] = File(...),
                         name: str = Form(''), configuration: str = Form('')):
    account = owner(request)
    try:
        from python_engine.project_paths import IGNORED_PROJECT_DIRS
        from backend.core.project_intelligence import RELEVANT
        selected = []
        total = 0
        for file in files:
            path = Path(str(file.filename or '').replace('\\', '/'))
            if any(part.casefold() in IGNORED_PROJECT_DIRS for part in path.parts[:-1]):
                continue
            if path.suffix.casefold() not in RELEVANT | SOURCE_EXTENSIONS:
                continue
            if file.size and file.size > MAX_SOURCE:
                raise ValueError('A source file exceeds the 8 MiB supported limit: ' + path.name)
            total += file.size or 0
            selected.append(file)
        if not selected or len(selected) > 15000 or total > 256 * 1024 * 1024:
            raise ValueError('Upload 1..15,000 relevant project resources, at most 256 MiB in total.')
        # Reuse the existing uploader and its traversal, ownership and generated-folder checks.
        session_id, root = await stage_project(selected, name or 'Virtual PLC project')
        result = await run_in_threadpool(service.create, account, root, name, configuration or None)
        result['uploadSessionId'] = session_id
        return result
    except (OSError, ValueError, TypeError) as error:
        fail(error)


@router.get('/projects/{identity}')
def project(identity: str, request: Request, runtimeOnly: bool = False):
    # The engineering model is already JSON data. Avoid FastAPI recursively
    # walking every cached Ladder cell and HMI property before serializing it.
    return JSONResponse(service.snapshot(opened(request, identity), runtime_only=runtimeOnly))


@router.post('/projects/{identity}/control')
def control(identity: str, payload: dict, request: Request):
    workspace = opened(request, identity)
    action = str(payload.get('action') or '')
    if action not in {'run', 'pause', 'stop', 'reset', 'scan', 'step'}:
        raise HTTPException(400, 'Choose run, pause, stop, reset, scan or step.')
    try:
        return service.command(workspace, action, payload.get('speed'))
    except (ValueError, TypeError, RuntimeError) as error:
        fail(error)


@router.post('/projects/{identity}/values')
def values(identity: str, payload: dict, request: Request):
    workspace = opened(request, identity)
    try:
        with workspace.lock:
            if not workspace.runtime or workspace.document['status'] != 'ready':
                raise ValueError('Wait for project analysis to finish.')
            name = payload.get('name') or payload.get('id')
            if not isinstance(name, str) or not name or len(name) > 400:
                raise ValueError('Select an analyzed variable name or identity.')
            if len(json.dumps(payload.get('value'))) > 65536:
                raise ValueError('A simulated value exceeds 64 KiB.')
            workspace.runtime.set_value(name, payload.get('value'), force=payload.get('force') is True,
                                        scope=payload.get('scope'), return_snapshot=False)
            return runtime_view(workspace.runtime, workspace.document.get('watchlist', []))
    except (ValueError, KeyError, TypeError, RuntimeError) as error:
        fail(error)


@router.delete('/projects/{identity}/forces')
def release_force(identity: str, request: Request, name: str):
    workspace = opened(request, identity)
    try:
        with workspace.lock:
            if not workspace.runtime:
                raise ValueError('Wait for analysis to finish.')
            workspace.runtime.release_force(name)
            return runtime_view(workspace.runtime, workspace.document.get('watchlist', []))
    except (ValueError, KeyError, TypeError) as error:
        fail(error)


@router.get('/projects/{identity}/source')
def source(identity: str, request: Request, path: str):
    opened(request, identity)
    try:
        return service.store.source(owner(request), identity, path)
    except (ValueError, OSError) as error:
        fail(error)


@router.get('/projects/{identity}/variables')
def variables(identity: str, request: Request, query: str = '', offset: int = 0, limit: int = 200,
              scope: str = '', watchlist: bool = False):
    workspace = opened(request, identity)
    if not 0 <= offset <= 100000 or not 1 <= limit <= 500 or len(query) > 200:
        raise HTTPException(400, 'Use a bounded variable search and page of 1..500 rows.')
    with workspace.lock:
        if not workspace.runtime:
            return {'variables': [], 'total': 0, 'offset': offset, 'limit': limit}
        rows = list(workspace.runtime.memory.records.values())
        if query:
            words = query.casefold()
            rows = [row for row in rows if words in (str(row.get('name', '')) + ' ' + str(row.get('scope', '')) + ' ' + str(row.get('type', ''))).casefold()]
        if scope:
            rows = [row for row in rows if str(row.get('scope', '')).casefold() == scope.casefold()]
        if watchlist:
            watched = set(workspace.document.get('watchlist', []))
            rows = [row for row in rows if row.get('id') in watched or row.get('name') in watched]
        selected = []
        for record in rows[offset:offset + limit]:
            row = {key: value for key, value in record.items() if not key.startswith('_')}
            for field in ('value', 'previous'):
                row[field], complete = value_preview(row.get(field))
                if not complete: row['valueTruncated'] = True
            selected.append(row)
        return {'variables': selected, 'total': len(rows), 'offset': offset, 'limit': limit}


@router.patch('/projects/{identity}')
def save(identity: str, payload: dict, request: Request):
    try:
        return JSONResponse(service.update(opened(request, identity), payload))
    except (ValueError, TypeError, KeyError) as error:
        fail(error)


@router.post('/projects/{identity}/duplicate')
def duplicate(identity: str, payload: dict, request: Request):
    workspace = opened(request, identity)
    try:
        with workspace.lock:
            service._persist(workspace)
            data = service.store.export(owner(request), identity)
        data['workspace']['settings'].pop('activeScenario', None)
        document = service.store.import_document(owner(request), data, payload.get('name') or workspace.document['name'] + ' copy')
        return service.snapshot(service.get(owner(request), document['id']))
    except (ValueError, OSError, TypeError) as error:
        fail(error)


@router.get('/projects/{identity}/export')
def export_project(identity: str, request: Request):
    workspace = opened(request, identity)
    try:
        with workspace.lock:
            service._persist(workspace)
            data = service.store.export(owner(request), identity)
        return JSONResponse(data, headers={'Content-Disposition': f'attachment; filename="Virtual_PLC_{identity[:8]}.json"'})
    except (ValueError, OSError, TypeError) as error:
        fail(error)


@router.post('/import')
async def import_project(request: Request, file: UploadFile = File(...)):
    try:
        raw = await file.read(MAX_DOCUMENT + 1)
        if len(raw) > MAX_DOCUMENT:
            raise ValueError('Workspace import exceeds 192 MiB.')
        data = json.loads(raw.decode('utf-8-sig'))
        document = await run_in_threadpool(service.store.import_document, owner(request), data)
        return await run_in_threadpool(lambda: service.snapshot(service.get(owner(request), document['id'])))
    except (ValueError, OSError, TypeError, KeyError) as error:
        fail(error)


@router.post('/projects/{identity}/cancel')
def cancel(identity: str, request: Request):
    workspace = opened(request, identity)
    workspace.cancel.set()
    return {'id': identity, 'cancelRequested': True}


@router.post('/projects/{identity}/refresh')
def refresh(identity: str, payload: dict, request: Request):
    workspace = opened(request, identity)
    if not workspace.document.get('projectRoot') or workspace.document.get('imported'):
        raise HTTPException(400, 'This is an imported snapshot. Select its original project to perform a new analysis.')
    service.analyze(workspace, rebuild=payload.get('rebuild') is True)
    return service.snapshot(workspace)


@router.get('/projects/{identity}/references')
def references(identity: str, request: Request, name: str):
    workspace = opened(request, identity)
    variable = next((row for row in workspace.model.get('variables', []) if row.get('id') == name), None)
    name = variable['name'] if variable else name
    try:
        from backend.core.project_intelligence import opened as open_index
        key = workspace.model.get('intelligenceProjectId')
        if key:
            return open_index(key, owner(request)).retrieve(name[:400], characters=9000, passes=3)
    except (ValueError, OSError, PermissionError):
        pass
    rows = [row for row in workspace.model.get('variables', []) if str(row.get('name', '')).casefold() == name.casefold()]
    return {'evidence': [ref for row in rows for ref in row.get('references', [])][:100],
            'notices': ['The original project index is unavailable. Showing saved declaration/reference evidence only.']}


@router.post('/projects/{identity}/breakpoints')
def breakpoint_control(identity: str, payload: dict, request: Request):
    workspace = opened(request, identity)
    try:
        with workspace.lock:
            if not workspace.runtime:
                raise ValueError('Wait for project analysis.')
            source = str(payload.get('source') or '')
            line = int(payload.get('line') or 0)
            if not source or line < 1:
                raise ValueError('Choose an original source path and positive line number.')
            if not hasattr(workspace.runtime, 'set_breakpoint'):
                raise ValueError('Source breakpoints are not supported for this execution model.')
            workspace.runtime.set_breakpoint(source, line, payload.get('enabled') is not False)
            workspace.document['settings']['breakpoints'] = workspace.runtime.snapshot().get('breakpoints', [])
            service._persist(workspace)
            return runtime_view(workspace.runtime, workspace.document.get('watchlist', []))
    except (ValueError, TypeError, KeyError) as error:
        fail(error)


@router.get('/templates')
def templates(request: Request):
    return {'templates': [row for row in service.store.list(owner(request))
                          if (row.get('settings') or {}).get('templateKind') in {'controller', 'io', 'simulation'}]}


@router.get('/projects/{identity}/signals')
def signals(identity: str, request: Request):
    workspace = opened(request, identity)
    with workspace.lock:
        if not workspace.runtime:
            return {'signals': [], 'timeMs': 0}
        snapshot = workspace.runtime.snapshot()
        return {'signals': snapshot.get('signals', []), 'timeMs': snapshot.get('timeMs'),
                'clock': 'deterministic-virtual', 'physicalPLC': False}


@router.post('/projects/{identity}/chopper')
def chopper(identity: str, payload: dict, request: Request):
    workspace = opened(request, identity)
    question = str(payload.get('question') or '').strip()
    if not question or len(question) > 6000:
        raise HTTPException(400, 'Ask a question of 1..6000 characters.')
    # Copy only bounded diagnostic state, then release the simulation lock.
    with workspace.lock:
        snapshot = runtime_view(workspace.runtime, workspace.document.get('watchlist', [])) if workspace.runtime else {}
        model = workspace.model
    from virtual_plc.core.chopper import answer
    history = payload.get('history')
    history = [{'role': row['role'], 'content': str(row.get('content', ''))[:2000]}
               for row in history[-6:] if isinstance(row, dict) and row.get('role') in {'user', 'assistant'}] if isinstance(history, list) else []
    return answer(model, snapshot, question, owner(request), history)
