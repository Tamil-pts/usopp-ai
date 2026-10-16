"""Portable, admin-only export/import of shared engineering knowledge."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend.core import accounts
from backend.core.runtime import BASE, EXPORTS, KNOWLEDGE, WORK

router = APIRouter(prefix='/api/admin/knowledge', tags=['Admin knowledge transfer'])
BUNDLE_FORMAT = 'usopp-engineering-knowledge'
MAX_UPLOAD = 6 * 1024 * 1024 * 1024
MAX_EXPANDED = 12 * 1024 * 1024 * 1024
MAX_ENTRIES = 200_000
EXCLUDED_NAMES = {'br_help.sqlite3', 'help_index.sqlite3'}


def require_admin(request: Request):
    if getattr(request.state, 'user', {}).get('role') != 'admin':
        raise HTTPException(403, 'Only an administrator can export or import shared knowledge.')


def _data_files(root: Path, prefix: str, include_br_help: bool):
    if not root.is_dir():
        return []
    paths = []
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink() or path.name in EXCLUDED_NAMES:
            continue
        rel = path.relative_to(root).as_posix()
        if prefix == 'knowledge' and rel.startswith('dashboard_layouts/users/'):
            continue
        if prefix == 'knowledge' and rel.startswith('br_help/') and not include_br_help:
            continue
        if prefix == 'knowledge' and rel.startswith('help_index/') and path.suffix.casefold() in {'.sqlite', '.sqlite3'}:
            continue
        if prefix == 'rules' and 'archive' in path.relative_to(root).parts:
            continue
        if path.suffix.casefold() in {'.pem', '.key', '.p12', '.pfx', '.gguf', '.safetensors', '.sqlite', '.sqlite3', '.db'} or path.name.endswith(('-wal', '-shm')):
            continue
        paths.append((path, f'{prefix}/{rel}'))
    return paths


def _user_model_files():
    files = []
    for user in accounts.store.list_users():
        identity = user.get('id') or user.get('username')
        key = hashlib.sha256(str(identity).encode()).hexdigest()
        directory = WORK / 'data_models' / key
        if not directory.is_dir():
            continue
        for path in directory.glob('*.json'):
            if path.is_file() and not path.is_symlink():
                files.append((path, f'user_data_models/{user["username"]}/{path.name}'))
    return files


@router.get('/export')
def export_knowledge(request: Request, include_br_help: bool = False):
    require_admin(request)
    target_dir = EXPORTS / 'knowledge-transfer'
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f'usopp-knowledge-{time.strftime("%Y%m%d-%H%M%S")}-{uuid4().hex[:8]}.zip'
    files = _data_files(KNOWLEDGE, 'knowledge', include_br_help) + _data_files(BASE / 'rules', 'rules', include_br_help) + _user_model_files()
    manifest = {
        'format': BUNDLE_FORMAT, 'version': 1, 'createdAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'contains': ['shared knowledge', 'rules', 'learning and feedback records', 'per-user imported DataInspect models'],
        'includesBRHelpSources': bool(include_br_help),
        'note': 'Model weights, accounts, user settings, PLC project uploads, reports and run history are excluded.',
    }
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        for path, arcname in files:
            archive.write(path, arcname)
    return FileResponse(target, media_type='application/zip', filename=target.name,
                        background=BackgroundTask(lambda: target.unlink(missing_ok=True)))


def _safe_name(name: str) -> PurePosixPath:
    normalized = name.replace('\\', '/')
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or any(part in {'', '.', '..'} for part in path.parts):
        raise ValueError('The knowledge archive contains an unsafe path.')
    return path


def _destination(rel: PurePosixPath, usernames: dict[str, int]) -> Path | None:
    parts = rel.parts
    if len(parts) >= 2 and parts[0] in {'knowledge', 'rules'}:
        if parts[:3] == ('knowledge','dashboard_layouts','users'):
            return None
        if parts[0] == 'rules' and 'archive' in parts:
            return None
        return BASE.joinpath(*parts)
    if len(parts) == 3 and parts[0] == 'user_data_models' and parts[2].lower().endswith('.json'):
        user_id = usernames.get(parts[1].casefold())
        if user_id is None:
            return None
        key = hashlib.sha256(str(user_id).encode()).hexdigest()
        return WORK / 'data_models' / key / Path(parts[2]).name
    return None


def _record_key(value):
    if isinstance(value, dict):
        for key in ('id', 'prefix', 'parameter_id', 'plc_tag'):
            if value.get(key) not in (None, ''):
                if key == 'plc_tag':
                    return key + ':' + '|'.join(str(value.get(field) or '').strip().casefold() for field in
                        ('plc_parameter', 'plc_tag', 'metadata_parameter', 'machine_department'))
                return key + ':' + str(value[key]).strip().casefold()
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def _merge_json(existing, incoming):
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return incoming
    result = dict(existing)
    for key, value in incoming.items():
        old = result.get(key)
        if isinstance(old, list) and isinstance(value, list) and key in {'rules', 'mappings', 'pipelines', 'models', 'departments', 'prefixes'}:
            merged = {_record_key(item): item for item in old}
            merged.update({_record_key(item): item for item in value})
            result[key] = list(merged.values())
        else:
            result[key] = value
    return result


def _merge_jsonl(current: bytes, incoming: bytes) -> bytes:
    records = {}
    order = []
    for data in (current, incoming):
        for line in data.decode('utf-8', errors='replace').splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except ValueError:
                parsed = line
            key = str(parsed.get('id') or _record_key(parsed)) if isinstance(parsed, dict) else _record_key(parsed)
            if key not in records:
                order.append(key)
            records[key] = line
    return ('\n'.join(records[key] for key in order) + ('\n' if order else '')).encode('utf-8')


@router.post('/import')
async def import_knowledge(request: Request, file: UploadFile = File(...)):
    require_admin(request)
    temporary = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix='usopp-knowledge-import-', suffix='.zip', dir=EXPORTS)
        temporary = Path(temp_name)
        size = 0
        with os.fdopen(fd, 'wb') as output:
            while chunk := await file.read(4 * 1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, 'Knowledge archive is larger than the 6 GiB import limit.')
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, 'Choose a uSOPp knowledge archive.')
        with zipfile.ZipFile(temporary, 'r') as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise HTTPException(413, 'The archive contains too many files.')
            manifest_info = next((item for item in infos if item.filename == 'manifest.json'), None)
            if not manifest_info:
                raise HTTPException(400, 'This archive has no uSOPp knowledge manifest.')
            if manifest_info.file_size > 1024 * 1024:
                raise HTTPException(400, 'The knowledge archive manifest is too large.')
            manifest = json.loads(archive.read(manifest_info).decode('utf-8'))
            if manifest.get('format') != BUNDLE_FORMAT or manifest.get('version') != 1:
                raise HTTPException(400, 'This uSOPp knowledge archive version is not supported.')
            usernames = {user['username'].casefold(): user['id'] for user in accounts.store.list_users()}
            selected = []
            total = 0
            names = set()
            missing_model_owners = 0
            for info in infos:
                if info.is_dir() or info.filename == 'manifest.json':
                    continue
                if info.flag_bits & 0x1:
                    raise HTTPException(400, 'Encrypted ZIP entries are not supported.')
                rel = _safe_name(info.filename)
                if len(rel.parts) == 3 and rel.parts[0] == 'user_data_models' and rel.parts[1].casefold() not in usernames:
                    missing_model_owners += 1
                    continue
                destination = _destination(rel, usernames)
                if destination is None:
                    continue
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode and (mode & 0o170000) == 0o120000:
                    raise HTTPException(400, 'Symbolic links are not allowed in knowledge archives.')
                total += info.file_size
                if total > MAX_EXPANDED:
                    raise HTTPException(413, 'Expanded knowledge archive exceeds the 12 GiB limit.')
                key = str(destination.resolve()).casefold()
                if key in names:
                    raise HTTPException(400, 'The archive contains duplicate destination files.')
                names.add(key)
                selected.append((info, destination))
            backup_dir = EXPORTS / 'knowledge-import-backups' / time.strftime('%Y%m%d-%H%M%S')
            changed = 0
            imported_br_help = False
            for info, destination in selected:
                imported_br_help = imported_br_help or info.filename.startswith('knowledge/br_help/')
                if destination.exists() and destination.is_file():
                    backup = backup_dir / destination.relative_to(BASE)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, backup)
                destination.parent.mkdir(parents=True, exist_ok=True)
                staging = destination.with_name(destination.name + f'.import-{uuid4().hex}.tmp')
                try:
                    if destination.is_file() and destination.suffix.casefold() == '.jsonl':
                        incoming = archive.read(info)
                        staging.write_bytes(_merge_jsonl(destination.read_bytes(), incoming))
                    elif destination.is_file() and destination.suffix.casefold() == '.json':
                        try:
                            current_json = json.loads(destination.read_text(encoding='utf-8'))
                            incoming_json = json.loads(archive.read(info).decode('utf-8'))
                            merged_json = _merge_json(current_json, incoming_json)
                            staging.write_text(json.dumps(merged_json, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                        except (UnicodeError, ValueError):
                            with archive.open(info) as source, staging.open('wb') as output:
                                shutil.copyfileobj(source, output, 4 * 1024 * 1024)
                    else:
                        with archive.open(info) as source, staging.open('wb') as output:
                            shutil.copyfileobj(source, output, 4 * 1024 * 1024)
                    os.replace(staging, destination)
                finally:
                    staging.unlink(missing_ok=True)
                changed += 1
        if imported_br_help:
            from backend.core import br_help
            br_help.STATE.update(phase='idle', stage='Imported manual sources; rebuild the help index', current=0, total=0, error='')
        return {'importedFiles': changed, 'missingUserModels': missing_model_owners,
                'backupDirectory': str(backup_dir) if backup_dir.exists() else None,
                'message': 'Knowledge files were merged. Rule, mapping, pipeline and model catalog entries are combined by identity; learning and feedback JSONL records are deduplicated. Other matching files were backed up before replacement. Files absent from the archive were left unchanged.'}
    except zipfile.BadZipFile:
        raise HTTPException(400, 'The selected file is not a valid ZIP archive.')
    except (OSError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(400, f'Knowledge import failed: {error}')
    finally:
        await file.close()
        if temporary:
            temporary.unlink(missing_ok=True)
