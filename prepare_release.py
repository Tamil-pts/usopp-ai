"""Stage engine bytecode without copying source into the distributable."""
from pathlib import Path
import py_compile
import tempfile
import shutil


def prepare() -> Path:
    root = Path(__file__).resolve().parent
    staging = root / '.build' / 'staging'
    staging.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='release_', dir=staging))
    target = stage / 'python_engine'
    target.mkdir()
    for source in (root / 'python_engine').glob('*.py'):
        py_compile.compile(str(source), cfile=str(target / (source.stem + '.pyc')),
                           dfile='python_engine/' + source.name, doraise=True)
    if list((root / 'dist').rglob('*.map')):
        raise RuntimeError('Frontend source maps found; rebuild with sourcemap disabled.')
    # Ship active defaults, not historical rules, local learning, project caches
    # or the developer's large Automation Studio help installation.
    shutil.copytree(root / 'rules', stage / 'rules',
                    ignore=shutil.ignore_patterns('archive', 'learning', 'feedback', '__pycache__'))
    (stage / 'knowledge').mkdir()
    shutil.copytree(root / 'knowledge' / 'master', stage / 'knowledge' / 'master')
    shutil.copytree(root / 'knowledge' / 'data_models', stage / 'knowledge' / 'data_models')
    shutil.copytree(root / 'knowledge' / 'chopper', stage / 'knowledge' / 'chopper')
    help_target = stage / 'knowledge' / 'help_index'
    help_target.mkdir()
    for name in ('project_guide.json', 'BR_PROJECT_HELP.md'):
        shutil.copy2(root / 'knowledge' / 'help_index' / name, help_target / name)
    return stage


if __name__ == '__main__':
    print(prepare())
