"""Generate the offline B&R reference index; no model or PLC execution."""
import argparse
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python_engine.br_help_index import build_index


def main():
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path(os.getenv('USOPP_DATA_ROOT') or ROOT))
    args = parser.parse_args()
    database = args.data_root / 'knowledge/help_index/br_help.sqlite3'
    last = 0
    def progress(stage, current, total):
        nonlocal last
        if current == 0 or current == total or time.monotonic() - last > 15:
            print(f'{stage}: {current:,}/{total:,}', flush=True)
            last = time.monotonic()
    temporary, meta = build_index(args.data_root / 'knowledge/br_help',
                                  ROOT / 'knowledge/help_index/project_guide.json', database, progress)
    os.replace(temporary, database)
    print(f'Published: {database}\nCounts: {meta["counts"]}\nSize: {database.stat().st_size / 1024**2:.1f} MiB', flush=True)


if __name__ == '__main__': main()
