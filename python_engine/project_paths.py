"""Common exclusions for engineering projects, not vendor documentation."""
import os
from pathlib import Path

IGNORED_PROJECT_DIRS = frozenset({
    'temp', 'tmp', 'as', 'binaries', 'compiledbinaries', 'diagnosis', 'bin', 'obj',
    'build', '.git', '.svn', '.hg', '__pycache__', 'node_modules', '.cache',
    '.venv', '.venv-ubuntu', '.usopp_workspaces', '.usopp_exports', '__macosx',
})


def project_files(root, excluded=IGNORED_PROJECT_DIRS):
    """Prune generated directories before walking; never follow linked sources."""
    root = Path(root)
    resolved_root = root.resolve()
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories
                                if name.casefold() not in excluded and not (Path(folder) / name).is_symlink()
                                and (Path(folder) / name).resolve().is_relative_to(resolved_root))
        for name in sorted(files):
            path = Path(folder) / name
            if not path.is_symlink() and path.resolve().is_relative_to(resolved_root): yield path
