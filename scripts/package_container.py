"""Compile the application into a fresh Docker runtime directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import py_compile
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {'.py', '.pyw', '.ts', '.tsx', '.map'}


def stage(destination: Path) -> None:
    destination = destination.resolve()
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise ValueError('Runtime staging must not be the application or its parent.')
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError('Choose an empty runtime staging directory.')
    for name in ('backend', 'python_engine'):
        for source in sorted((ROOT / name).rglob('*.py')):
            relative = source.relative_to(ROOT)
            target = (destination / relative).with_suffix('.pyc')
            target.parent.mkdir(parents=True, exist_ok=True)
            py_compile.compile(str(source), cfile=str(target),
                               dfile=relative.as_posix(), doraise=True)
    py_compile.compile(str(ROOT / 'scripts/container_bootstrap.py'),
                       cfile=str(destination / 'container_bootstrap.pyc'),
                       dfile='container_bootstrap.py', doraise=True)
    py_compile.compile(str(ROOT / 'scripts/container_maintenance.py'),
                       cfile=str(destination / 'container_maintenance.pyc'),
                       dfile='container_maintenance.py', doraise=True)
    for page in ('index.html', 'nami/index.html'):
        if not (ROOT / 'dist' / page).is_file():
            raise ValueError(f'Build the frontend first: dist/{page} is missing.')
    shutil.copytree(ROOT / 'dist', destination / 'dist')
    shutil.copytree(ROOT / 'rules', destination / 'rules',
                    ignore=shutil.ignore_patterns('archive', 'learning', 'feedback', '__pycache__'))
    for name in ('master', 'data_models', 'chopper'):
        shutil.copytree(ROOT / 'knowledge' / name, destination / 'knowledge' / name)
    help_target = destination / 'knowledge' / 'help_index'
    help_target.mkdir()
    for name in ('project_guide.json', 'BR_PROJECT_HELP.md'):
        shutil.copy2(ROOT / 'knowledge' / 'help_index' / name, help_target / name)
    (destination / 'src').mkdir()
    for name in ('usopp_logo.png', 'petrus_logo.png'):
        shutil.copy2(ROOT / 'src' / name, destination / 'src' / name)
    (destination / 'local_ai').mkdir()
    for name in ('MODEL_LICENSE.txt', 'MODEL_CARD.md'):
        shutil.copy2(ROOT / 'local_ai' / name, destination / 'local_ai' / name)
    # Runtime needs only the version, not developer build commands/dependencies.
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    (destination / 'package.json').write_text(
        json.dumps({'name': package['name'], 'version': package['version']}), encoding='utf-8')
    raw = [p.relative_to(destination).as_posix() for p in destination.rglob('*')
           if p.is_file() and p.suffix.casefold() in SOURCE_SUFFIXES]
    if raw:
        raise ValueError('Raw application source found: ' + ', '.join(raw[:10]))
    print(f'Compiled runtime staged: {destination}; raw application source audit passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    stage(parser.parse_args().output)
