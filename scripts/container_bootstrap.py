"""Initialize the persistent container account store without logging secrets."""
import os
from pathlib import Path
import sqlite3


def main():
    database = Path(os.environ['USOPP_DATA_ROOT']) / 'accounts.sqlite3'
    existing_admin = False
    if database.is_file():
        with sqlite3.connect(str(database), timeout=15) as connection:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
                existing_admin = bool(connection.execute("SELECT 1 FROM users WHERE username_key='admin'").fetchone())
    if not existing_admin:
        secret = os.getenv('USOPP_INITIAL_ADMIN_PASSWORD_FILE', '')
        if not secret:
            raise SystemExit('Provide an initial Admin password file for a new container installation.')
        password = Path(secret).read_text(encoding='utf-8-sig').rstrip('\r\n')
        if not 12 <= len(password) <= 128 or password == 'usopp.2026':
            raise SystemExit('Choose an initial Admin password of 12 to 128 characters.')
        os.environ['USOPP_INITIAL_ADMIN_PASSWORD'] = password
    from backend.core.accounts import store, password_matches
    try:
        store.initialize()
        with store.db() as connection:
            admin = connection.execute("SELECT password_hash FROM users WHERE username_key='admin'").fetchone()
        if not admin or password_matches('usopp.2026', admin['password_hash']):
            raise SystemExit('Change the existing local-demo Admin password before using this data in a container.')
    finally:
        os.environ.pop('USOPP_INITIAL_ADMIN_PASSWORD', None)


if __name__ == '__main__':
    main()
