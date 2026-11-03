"""Bundle Playwright's runtime without development typings or source maps."""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('playwright', excludes=[
    '**/*.ts', '**/*.tsx', '**/*.map', '**/*.py', '**/*.pyw',
])
