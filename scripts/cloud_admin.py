"""Set the first cloud Admin password offline; preserve existing accounts."""
from __future__ import annotations

import argparse
from contextlib import closing
import getpass
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check before starting the service; do not prompt or reset passwords.')
    args = parser.parse_args()
    configured = os.getenv('USOPP_DATA_ROOT', '')
    if not configured or not Path(configured).is_absolute():
        raise RuntimeError('Set USOPP_DATA_ROOT to an absolute persistent data directory first.')
    data_root = Path(configured).resolve()
    if data_root == ROOT:
        raise RuntimeError('Use a separate cloud data directory; the application folder is not a cloud data root.')
    db_path = data_root / 'accounts.sqlite3'
    if args.check and not db_path.is_file():
        raise RuntimeError('Initialize Admin offline with scripts/cloud_admin.py before starting the cloud service.')
    if db_path.is_file():
        # Read only: checks and updates never reset existing account passwords.
        with closing(sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)) as db:
            row = db.execute("SELECT password_hash,role,active FROM users WHERE username_key='admin'").fetchone()
        if not row or row[1] != 'admin' or not row[2]:
            raise RuntimeError('No enabled Admin account found. Preserve this database and restore a valid backup.')
        sys.path.insert(0, str(ROOT))
        from backend.core.accounts import password_matches
        if password_matches('usopp.2026', row[0]):
            raise RuntimeError('Admin still uses the local demo password. Change it through Account settings over an SSH tunnel before enabling cloud access.')
        print('Cloud Admin is configured. Existing accounts and passwords are unchanged.')
        return

    password = getpass.getpass('New cloud Admin password (12 to 128 characters): ')
    confirmation = getpass.getpass('Confirm cloud Admin password: ')
    if password != confirmation:
        raise RuntimeError('Passwords do not match; Admin was not initialized.')
    if not 12 <= len(password) <= 128 or password == 'usopp.2026':
        raise RuntimeError('Choose a new password containing 12 to 128 characters.')
    # The password is passed only within this process and is stored as a hash.
    os.environ['USOPP_INITIAL_ADMIN_PASSWORD'] = password
    sys.path.insert(0, str(ROOT))
    try:
        from backend.core.accounts import store
        store.initialize()
    finally:
        os.environ.pop('USOPP_INITIAL_ADMIN_PASSWORD', None)
    print('Cloud Admin initialized. Sign in as Admin using the password you entered.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, sqlite3.Error, EOFError) as error:
        print(f'uSOPp cloud: {error}', file=sys.stderr)
        raise SystemExit(1)
