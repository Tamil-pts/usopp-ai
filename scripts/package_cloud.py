"""Create a fresh Linux source bundle without accounts, projects or credentials."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    'package.json', 'package-lock.json', 'backend_requirements.txt', 'server.py',
    'index.html', 'vite.config.ts', 'tsconfig.json', 'tsconfig.app.json',
    'usopp.sh', '.env.example', '.gitignore', 'README.md', 'CHANGELOG.md',
    'ARCHITECTURE.md', 'MULTI_USER.md', 'UBUNTU_DEMO.md', 'AZURE_DEPLOYMENT.md',
    'CHOPPER_LOCAL_AI.md', 'MCP_LOCAL_TOOLS.md', 'AS27_PROJECT_LAYOUT.md',
    'LADDER_REFERENCE_REVIEW.md', 'RTC_PROTOCOL.md',
}
TREES = ('backend', 'python_engine', 'assist', 'src', 'nami', 'scripts', 'deploy',
         'dist', 'knowledge/master', 'knowledge/data_models', 'knowledge/dashboard_layouts', 'knowledge/lapformer', 'rules')
SKIP_DIRS = {'node_modules', '__pycache__', '.git', '.venv', '.venv-ubuntu',
             '.usopp_workspaces', '.usopp_exports', '.usopp_server', 'logs',
             'archive', 'learning', 'feedback', 'projects', 'release', '.build'}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if relative.parts[:3]==('knowledge','dashboard_layouts','users'):
        return False
    if not path.is_file() or path.is_symlink():
        return False
    if any(part in SKIP_DIRS for part in relative.parts[:-1]):
        return False
    if path.suffix.lower() in {'.pyc', '.pyo', '.map', '.tsbuildinfo', '.sqlite3', '.db', '.pem', '.key', '.log', '.gguf', '.safetensors'}:
        return False
    if '.sqlite3' in path.name.lower():
        return False
    if path.name.startswith('.env') and path.name != '.env.example':
        return False
    return True


def main() -> None:
    version = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
    output = ROOT / 'release' / 'azure-source' / datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f'uSOPp_AI_{version}_Azure_Source.zip'
    files = {ROOT / name for name in ROOT_FILES}
    for tree in TREES:
        for source in (ROOT / tree).rglob('*'):
            if included(source):
                files.add(source)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(files):
            if source.is_file():
                archive.write(source, 'usopp_ai_2.0/' + source.relative_to(ROOT).as_posix())
    print(destination)
    print(f'{len(files)} files; {destination.stat().st_size / (1024 * 1024):.1f} MiB')
    print('Fresh installation: excludes accounts, private uploads/results, model settings and weights, and installed dependencies.')


if __name__ == '__main__':
    main()
