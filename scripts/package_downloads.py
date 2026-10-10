"""Create Windows and container-launcher download ZIPs with SHA256 companions."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def checksum(path: Path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    path.with_name(path.name + '.sha256').write_text(f'{digest}  {path.name}\n', encoding='ascii')


def write_zip(destination: Path, sources: list[tuple[Path, str]]):
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for source, name in sources:
            if source.suffix.casefold() in {'.py', '.pyw', '.ts', '.tsx', '.map'}:
                raise ValueError(f'Raw application source is not a download asset: {source.name}')
            archive.write(source, name)
    checksum(destination)
    print(f'{destination} ({destination.stat().st_size / 1048576:.1f} MiB)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--windows-dir', type=Path)
    parser.add_argument('--latest-windows', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    version = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
    output = args.output or ROOT / 'release/downloads' / datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True, exist_ok=True)
    windows = args.windows_dir
    if args.latest_windows:
        candidates = list((ROOT / 'release/windows-source-free').glob('*/uSOPp_AI/uSOPp_AI.exe'))
        if not candidates:
            raise ValueError('Build the portable Windows EXE first.')
        windows = max(candidates, key=lambda p: p.stat().st_mtime).parent
    if windows:
        windows = windows.resolve()
        if not (windows / 'uSOPp_AI.exe').is_file():
            raise ValueError('Choose the complete portable uSOPp_AI folder.')
        bundled_version = json.loads((windows / 'package.json').read_text(encoding='utf-8'))['version']
        if bundled_version != version:
            raise ValueError(f'Rebuild the Windows EXE: bundled {bundled_version}, requested {version}.')
        files = [(p, 'uSOPp_AI/' + p.relative_to(windows).as_posix())
                 for p in sorted(windows.rglob('*')) if p.is_file()]
        files.append((ROOT / 'distribution/README.md', 'uSOPp_AI/INSTALL.md'))
        files.extend((p, 'uSOPp_AI/' + p.name)
                     for p in sorted((ROOT / 'distribution/windows').iterdir()) if p.is_file())
        write_zip(output / f'uSOPp_AI_{version}_Windows_x64.zip', files)
    launchers = [(p, p.name) for p in sorted((ROOT / 'distribution').iterdir())
                 if p.is_file() and p.name in {'README.md', 'compose.yaml', 'usopp-container.ps1', 'usopp-container.sh'}]
    write_zip(output / f'uSOPp_AI_{version}_Container_Launchers.zip', launchers)


if __name__ == '__main__':
    main()
