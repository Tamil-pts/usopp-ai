"""Admin editing for the original PMS/QMS/CMS database JSON Key sources."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath

from backend.core.runtime import KNOWLEDGE, RESOURCE_ROOT
from backend.core.data_models import machine_key, name_key, parse_model

_lock = threading.RLock()
_SERVICES = {'PMS', 'QMS', 'CMS'}
_PRESERVED_PARAMETER_FIELDS = (
    'excelReferences', 'referenceIssues', 'suggestedPlcType', 'dataTypeRole',
    'numericValueType', 'aliases', 'canonicalName', 'mappingSource',
    'referenceCorrections', 'ignoreNameSeparators', 'configuredPlcDataType',
    'resolvedReferenceIssues',
)
_PRESERVED_RECORD_FIELDS = (
    'excelReference', 'dataTypeRole', 'numericValueType', 'aliases',
    'canonicalName', 'mappingSource', 'referenceCorrections',
    'ignoreNameSeparators', 'originalDataType', 'plcDataType',
)


def _data_root() -> Path:
    root = KNOWLEDGE / 'data_models'
    if (root / 'source_manifest.json').is_file():
        return root
    return RESOURCE_ROOT / 'knowledge' / 'data_models'


def _manifest() -> dict:
    path = _data_root() / 'source_manifest.json'
    if not path.is_file():
        raise FileNotFoundError('The fixed data-model source manifest is not installed.')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data.get('fixedModels'), list):
        raise ValueError('The fixed data-model source manifest is invalid.')
    return data


def _entry(model_id: str) -> dict:
    try:
        service, department = model_id.split(':', 1)
    except ValueError as error:
        raise KeyError(model_id) from error
    for item in _manifest()['fixedModels']:
        if (str(item.get('service', '')).upper() == service.upper()
                and machine_key(item.get('department', '')) == machine_key(department)):
            return item
    raise KeyError(model_id)


def _source_path(item: dict) -> Path:
    relative = PurePosixPath(str(item.get('originalSource', '')).replace('\\', '/'))
    if not relative.parts or relative.is_absolute() or any(part in {'', '.', '..'} for part in relative.parts):
        raise ValueError('The model manifest contains an unsafe source path.')
    base = (_data_root() / 'reference_sources').resolve()
    path = (base / Path(*relative.parts)).resolve()
    if base not in path.parents or path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f'Original JSON Key source was not found: {relative.as_posix()}')
    return path


def _collection_prefix(item: dict) -> str:
    department = re.sub(r'[^a-z0-9]+', '_', str(item.get('department', '')).casefold()).strip('_')
    return f"{str(item.get('service', '')).casefold()}_{department}_"


def _scoped_collections(data: dict, item: dict) -> dict[str, list]:
    collections = data.get('keysList')
    if not isinstance(collections, dict):
        raise ValueError('The source JSON must contain a keysList object.')
    prefix = _collection_prefix(item)
    return {key: value for key, value in collections.items()
            if isinstance(key, str) and key.casefold().startswith(prefix)}


def _revision(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def list_sources() -> list[dict]:
    result = []
    for item in _manifest()['fixedModels']:
        path = _source_path(item)
        raw = path.read_bytes()
        data = json.loads(raw.decode('utf-8-sig'))
        collections = _scoped_collections(data, item)
        result.append({
            'id': f"{item['service']}:{item['department']}",
            'service': item['service'], 'department': item['department'],
            'originalSource': item['originalSource'], 'modelFile': item['file'],
            'parameterCount': sum(len(rows) for rows in collections.values()),
            'collectionCount': len(collections), 'revision': _revision(raw),
        })
    return result


def get_source(model_id: str) -> dict:
    item = _entry(model_id)
    path = _source_path(item)
    raw = path.read_bytes()
    data = json.loads(raw.decode('utf-8-sig'))
    collections = _scoped_collections(data, item)
    return {
        'id': f"{item['service']}:{item['department']}",
        'service': item['service'], 'department': item['department'],
        'originalSource': item['originalSource'], 'modelFile': item['file'],
        'revision': _revision(raw), 'collections': collections,
        'parameterCount': sum(len(rows) for rows in collections.values()),
        'collectionCount': len(collections),
    }


def _identity(record: dict) -> tuple:
    group = record.get('groupCode')
    if group is None:
        group = ''
    return (name_key(record.get('tagName')), str(group).strip().casefold(),
            str(record.get('formula') or '').strip().casefold())


def _parameter_identity(record: dict) -> tuple:
    return (str(record.get('sheet', '')).casefold(), name_key(record.get('name')),
            tuple(record.get('groupCodes') or []), record.get('kind'))


def _preserve_parameter_metadata(fresh: list[dict], previous: list[dict]) -> list[dict]:
    prior = defaultdict(deque)
    for row in previous:
        prior[_parameter_identity(row)].append(row)
    result = []
    for row in fresh:
        old_rows = prior[_parameter_identity(row)]
        if old_rows:
            old = old_rows.popleft()
            same_type = str(row.get('dataType', '')).casefold() == str(old.get('dataType', '')).casefold()
            for key in _PRESERVED_PARAMETER_FIELDS:
                if key in old and (same_type or key not in {'referenceIssues', 'suggestedPlcType', 'referenceCorrections', 'resolvedReferenceIssues'}):
                    row[key] = copy.deepcopy(old[key])
        result.append(row)
    result.extend(copy.deepcopy(row) for row in previous if row.get('referenceOrigin') == 'workbook-supplement')
    return result


def _preserve_database_metadata(collections: dict, previous: dict, source_names: set[str]) -> dict:
    prior_collections = previous.get('keysList') if isinstance(previous, dict) else {}
    prior_collections = prior_collections if isinstance(prior_collections, dict) else {}
    result = {}
    for name, rows in collections.items():
        old_rows = prior_collections.get(name, [])
        matches = defaultdict(deque)
        for row in old_rows if isinstance(old_rows, list) else []:
            if isinstance(row, dict):
                matches[_identity(row)].append(row)
        updated = []
        seen = defaultdict(int)
        for row in rows:
            value = copy.deepcopy(row)
            same = matches[_identity(row)]
            if same:
                old = same.popleft()
                seen[_identity(row)] += 1
                same_type = str(row.get('dataType', '')).casefold() == str(old.get('dataType', '')).casefold()
                for key in _PRESERVED_RECORD_FIELDS:
                    if key in old and (same_type or key not in {'referenceCorrections', 'originalDataType', 'plcDataType'}):
                        value[key] = copy.deepcopy(old[key])
            updated.append(value)
        # Workbook-only definitions were added to the generated schema, not the
        # original JSON Key file. Keep those definitions attached to the model.
        for old_rows in [old_rows] if isinstance(old_rows, list) else []:
            for row in old_rows:
                if not isinstance(row, dict) or not isinstance(row.get('excelReference'), dict):
                    continue
                key = _identity(row)
                if seen[key] < sum(1 for source_row in rows if _identity(source_row) == key):
                    continue
                updated.append(copy.deepcopy(row))
                seen[key] += 1
        result[name] = updated
    for name, rows in prior_collections.items():
        if name in result or name in source_names or not isinstance(rows, list):
            continue
        supplements = [copy.deepcopy(row) for row in rows if isinstance(row, dict) and isinstance(row.get('excelReference'), dict)]
        if supplements:
            result[name] = supplements
    return result


def _updated_documents(item: dict, updated_source: dict, source_bytes: bytes) -> dict[Path, object]:
    root = _data_root()
    catalog_path = root / 'catalog.json'
    manifest_path = root / 'source_manifest.json'
    if not catalog_path.is_file():
        raise FileNotFoundError('The DataInspect fixed-model catalog is missing; no changes were saved.')
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    manifest = _manifest()
    target_source = str(item['originalSource']).replace('\\', '/')
    matching_entries = [entry for entry in manifest['fixedModels']
                        if str(entry.get('originalSource', '')).replace('\\', '/') == target_source]
    source_collections = updated_source['keysList']
    prefix_for = _collection_prefix
    manifest_by_id = {(str(entry['service']).upper(), machine_key(entry['department'])): entry for entry in matching_entries}
    updated_model_ids = set()
    for model in catalog.get('models', []):
        model_id = (str(model.get('service', '')).upper(), machine_key(model.get('machine', '')))
        fixed_entry = manifest_by_id.get(model_id)
        if not fixed_entry:
            continue
        updated_model_ids.add(model_id)
        stable_id = model.get('id')
        prefix = prefix_for(fixed_entry)
        fresh = parse_model(source_bytes, Path(target_source).name, fixed_entry['service'], fixed_entry['department'])
        fresh['parameters'] = [row for row in fresh['parameters']
                               if str(row.get('sheet', '')).casefold().startswith(prefix)]
        for row in fresh['parameters']:
            row.setdefault('dataTypeRole', 'wire' if row.get('plcDataType') else 'value')
        previous_parameters = model.get('parameters', [])
        fresh['parameters'] = _preserve_parameter_metadata(fresh['parameters'], previous_parameters)
        old_database = model.get('databaseModel') if isinstance(model.get('databaseModel'), dict) else {}
        old_keys = old_database.get('keysList') if isinstance(old_database.get('keysList'), dict) else {}
        scoped = {name: rows for name, rows in source_collections.items()
                  if isinstance(name, str) and name.casefold().startswith(prefix)}
        model_database = copy.deepcopy(updated_source)
        model_database['keysList'] = _preserve_database_metadata(scoped, old_database, set(scoped))
        model.update(fresh)
        model.update(
            id=stable_id, source=Path(target_source).name,
            service=fixed_entry['service'], machine=fixed_entry['department'],
            fixed=True, sourceType=model.get('sourceType', 'json'),
            sourceRelativePath=fixed_entry.get('file', model.get('sourceRelativePath')),
            originalSource=target_source, databaseModel=model_database,
            sourceSha256=_revision(source_bytes),
        )
        manifest_entry = next((entry for entry in manifest['fixedModels']
                               if entry.get('service') == fixed_entry['service']
                               and machine_key(entry.get('department', '')) == machine_key(fixed_entry['department'])), None)
        if manifest_entry is not None:
            manifest_entry['parameters'] = len(fresh['parameters'])
    if not updated_model_ids:
        raise FileNotFoundError('No DataInspect model refers to this original JSON Key source; no changes were saved.')
    for source in manifest.get('sources', []):
        if str(source.get('source', '')).replace('\\', '/') == target_source:
            source['sha256'] = _revision(source_bytes)
    original_path = _source_path(item)
    output: dict[Path, object] = {original_path: updated_source, catalog_path: catalog, manifest_path: manifest}
    # Keep each generated server JSON in sync with the source collections that
    # its DataInspect service/department model exposes.
    for fixed_entry in matching_entries:
        model = next((candidate for candidate in catalog.get('models', [])
                      if str(candidate.get('service', '')).upper() == str(fixed_entry['service']).upper()
                      and machine_key(candidate.get('machine', '')) == machine_key(fixed_entry['department'])), None)
        if model and isinstance(model.get('databaseModel'), dict):
            output[root / fixed_entry['file']] = model['databaseModel']
    return output


def save_source(model_id: str, payload: dict) -> dict:
    item = _entry(model_id)
    if not isinstance(payload, dict) or not isinstance(payload.get('collections'), dict):
        raise ValueError('Provide the edited JSON Key collections.')
    path = _source_path(item)
    with _lock:
        before = path.read_bytes()
        if payload.get('revision') != _revision(before):
            raise RuntimeError('This JSON Key file changed elsewhere. Reload it before saving.')
        original = json.loads(before.decode('utf-8-sig'))
        old_collections = original.get('keysList')
        if not isinstance(old_collections, dict):
            raise ValueError('The source JSON does not contain a keysList object.')
        incoming = payload['collections']
        if len(incoming) > 1000:
            raise ValueError('A JSON Key source can contain at most 1,000 collections.')
        prefix = _collection_prefix(item)
        for collection, rows in incoming.items():
            if not isinstance(collection, str) or not collection.casefold().startswith(prefix):
                raise ValueError(f'Collection names for this source must begin with {prefix}.')
            if not isinstance(rows, list) or len(rows) > 30000:
                raise ValueError(f'{collection} must be a list with at most 30,000 records.')
            for index, row in enumerate(rows, 1):
                if not isinstance(row, dict) or len(row) > 100:
                    raise ValueError(f'{collection}, row {index}: expected an object with at most 100 fields.')
                if not str(row.get('tagName') or '').strip():
                    raise ValueError(f'{collection}, row {index}: tagName is required.')
        updated = copy.deepcopy(original)
        updated_keys = {}
        inserted = set()
        for collection, rows in old_collections.items():
            if isinstance(collection, str) and collection.casefold().startswith(prefix):
                if collection in incoming:
                    updated_keys[collection] = incoming[collection]
                    inserted.add(collection)
            else:
                updated_keys[collection] = rows
        for collection, rows in incoming.items():
            if collection not in inserted:
                updated_keys[collection] = rows
        updated['keysList'] = updated_keys
        serialized = json.dumps(updated, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if b'\r\n' in before:
            serialized = serialized.replace('\n', '\r\n')
        new_source_bytes = serialized.encode('utf-8')
        if len(new_source_bytes) > 20 * 1024 * 1024:
            raise ValueError('The edited JSON Key file exceeds 20 MB.')
        documents = _updated_documents(item, updated, new_source_bytes)
        # Reject malformed generated data before placing any write on disk.
        json.loads(new_source_bytes.decode('utf-8'))
        old_bytes = {target: target.read_bytes() if target.is_file() else None for target in documents}
        written = []
        try:
            from backend.core.run_history import write_json
            for target, data in documents.items():
                write_json(target, data)
                written.append(target)
        except Exception:
            for target in reversed(written):
                previous = old_bytes[target]
                if previous is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(previous)
            raise
    return get_source(model_id)
