"""Offline backup/restore of the complete server data volume; no app imports."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile

MANIFEST = '_usopp_backup_manifest.json'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def backup(root, output, owner):
    if output.exists() or output.resolve().is_relative_to(root.resolve()):
        raise ValueError('Use a new backup file outside the data volume.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.part')
    package = Path('/opt/usopp/package.json')
    version = json.loads(package.read_text())['version'] if package.is_file() else 'unknown'
    manifest = json.dumps({'format': 1, 'createdAt': datetime.now(timezone.utc).isoformat(),
                          'dataRoot': str(root), 'toolVersion': version}).encode()
    try:
        with tarfile.open(temporary, 'w:gz', compresslevel=1, dereference=True) as archive:
            info = tarfile.TarInfo(MANIFEST); info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))
            for path in sorted(root.rglob('*')):
                if path.is_symlink():
                    raise ValueError('A data-volume symlink cannot be included. Store project inputs as uploaded files.')
                if not path.is_file() and not path.is_dir():
                    raise ValueError('A special file cannot be included in a server backup.')
                archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
        os.replace(temporary, output)
        checksum = output.with_name(output.name + '.sha256')
        checksum.write_text(f'{digest(output)}  {output.name}\n', encoding='ascii')
        for path in (output, checksum):
            os.chmod(path, 0o600)
            if owner is not None: os.chown(path, owner, -1)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Complete server backup: {output.name}')


def restore(root, source):
    if any(root.iterdir()):
        raise ValueError('Restore requires an empty new volume. Existing server data was not changed.')
    checksum = source.with_name(source.name + '.sha256')
    expected = checksum.read_text(encoding='ascii').split()[0]
    if len(expected) != 64 or digest(source) != expected:
        raise ValueError('Backup checksum does not match. Keep the original server data.')
    with tarfile.open(source, 'r:gz') as archive:
        members = archive.getmembers()
        manifest = archive.extractfile(MANIFEST)
        if manifest is None or json.load(manifest).get('format') != 1:
            raise ValueError('Unsupported server backup format.')
        for item in members:
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir()):
                raise ValueError('Backup contains an unsafe path or link.')
            if not (root / item.name).resolve().is_relative_to(root.resolve()):
                raise ValueError('Backup path is outside the target volume.')
        for item in members:
            if item.name == MANIFEST: continue
            archive.extract(item, path=root, filter='data')
    # Data is always owned by the app's fixed non-root UID in every image version.
    for path in [root, *root.rglob('*')]: os.chown(path, 10001, 10001)
    print('Restored complete server data to the new volume. Start the matching app release.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore'])
    parser.add_argument('archive', type=Path)
    parser.add_argument('--owner', type=int)
    args = parser.parse_args()
    data = Path(os.environ.get('USOPP_DATA_ROOT', '/data'))
    if args.action == 'backup': backup(data, args.archive, args.owner)
    else: restore(data, args.archive)
