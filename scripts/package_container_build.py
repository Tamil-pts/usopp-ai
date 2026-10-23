"""Create a small private source bundle for building the Linux container on Ubuntu."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    '.dockerignore', 'Dockerfile', 'backend_requirements.txt', 'index.html',
    'package.json', 'package-lock.json', 'vite.config.ts',
}
DIRECTORIES = (
    'backend', 'python_engine', 'src', 'nami', 'virtual_plc', 'knowledge/virtual_plc', 'knowledge/master',
    'knowledge/data_models', 'knowledge/dashboard_layouts', 'knowledge/lapformer', 'knowledge/chopper', 'knowledge/help_index',
    'rules',
)
EXTRA_FILES = (
    'REPORT_ANALYSIS.md', 'YBS_DATAINSPECT.md', 'SPINCONNECT_WRITE_ST.md', 'scripts/audit_ybs.py',
    'deploy/container/entrypoint.sh',
    'distribution/usopp-container.sh',
    'distribution/compose.yaml',
    'distribution/PRIVATE_UBUNTU_BUILD.md',
    'scripts/build_nami.mjs',
    'scripts/package_container.py',
    'scripts/container_bootstrap.py',
    'scripts/container_maintenance.py',
    'local_ai/MODEL_LICENSE.txt',
    'local_ai/MODEL_CARD.md',
)
EXCLUDED_PARTS = {
    'node_modules', '__pycache__', 'archive', 'learning', 'feedback',
    'projects', 'br_help', 'training', 'models', '.git',
}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.sqlite', '.sqlite3', '.gguf', '.safetensors', '.pem', '.key', '.p12', '.pfx'}


def allowed_file(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if relative.parts[:2] in {('virtual_plc','tests'),('virtual_plc','dist')}:return False
    if relative.parts[:3]==('knowledge','dashboard_layouts','users'):
        return False
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.suffix.casefold() in EXCLUDED_SUFFIXES or path.name.startswith('.env'):
        return False
    if path.name.endswith(('-wal', '-shm')):
        return False
    return path.is_file()


def files_to_pack() -> list[Path]:
    files = {ROOT / name for name in ROOT_FILES | set(EXTRA_FILES)}
    files.update(ROOT.glob('tsconfig*.json'))
    for directory in DIRECTORIES:
        base = ROOT / directory
        if not base.is_dir():
            raise FileNotFoundError(f'Required container build input is missing: {base.relative_to(ROOT)}')
        files.update(path for path in base.rglob('*') if allowed_file(path))
    missing = sorted(path.relative_to(ROOT).as_posix() for path in files if not path.is_file())
    if missing:
        raise FileNotFoundError('Required build files are missing: ' + ', '.join(missing))
    return sorted((path for path in files if allowed_file(path)), key=lambda p: p.relative_to(ROOT).as_posix().casefold())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
    files = files_to_pack()
    with tarfile.open(output, 'w:gz', compresslevel=6) as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    checksum = output.with_name(output.name + '.sha256')
    checksum.write_text(f'{digest}  {output.name}\n', encoding='ascii', newline='\n')
    print(f'uSOPp {version} private container build bundle: {output}')
    print(f'{len(files)} files, {output.stat().st_size / 1048576:.1f} MiB')
    print(f'SHA256: {checksum}')
    print('This bundle contains private source files. Transfer it only to the trusted build server.')


if __name__ == '__main__':
    main()
