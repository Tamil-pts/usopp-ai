"""Server-owned user settings and a rebuildable index of archived test results.

Rules/knowledge keep their existing JSON schemas. Reports and source snapshots
remain files under USOPP_DATA_ROOT. Never recreate either database on upgrades.
"""
from contextlib import contextmanager
import json
import re
import sqlite3
import threading
import time
from backend.core.runtime import BASE

DATABASE = BASE / 'application.sqlite3'
LOCK = threading.Lock()
READY = False
KEY = re.compile(r'^(?:usopp_|spinning_|spinconnect_|nami_)[A-Za-z0-9_.:%/ -]{1,180}$|^plc_configs$')
MAX_VALUE = 8 * 1024 * 1024


def initialize():
    global READY
    with LOCK:
        if READY:
            return
        DATABASE.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(DATABASE), timeout=30)
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS schema_versions (
                    component TEXT PRIMARY KEY, version INTEGER NOT NULL);
                INSERT OR IGNORE INTO schema_versions VALUES ('application', 1);
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT,
                    revision INTEGER NOT NULL, updated_at REAL NOT NULL,
                    PRIMARY KEY (user_id, key));
                CREATE TABLE IF NOT EXISTS run_archive (
                    id TEXT PRIMARY KEY, user_id INTEGER, test_id TEXT NOT NULL,
                    kind TEXT NOT NULL, created_at TEXT NOT NULL,
                    record_json TEXT NOT NULL, result_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS run_archive_owner
                    ON run_archive(user_id, created_at DESC);
            ''')
            connection.commit()
            version = connection.execute("SELECT version FROM schema_versions WHERE component='application'").fetchone()[0]
            if version > 1:
                raise RuntimeError('This data store needs a newer uSOPp release. Restore the matching backup before downgrading.')
            READY = True
        finally:
            connection.close()


@contextmanager
def db():
    initialize()
    connection = sqlite3.connect(str(DATABASE), timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def settings(user_id):
    with db() as connection:
        rows = connection.execute('SELECT key,value,revision FROM user_settings WHERE user_id=?', (user_id,)).fetchall()
    return {row['key']: {'value': row['value'], 'revision': row['revision']} for row in rows}


def validate_changes(changes):
    if not isinstance(changes, list) or len(changes) > 200:
        raise ValueError('Save at most 200 settings per request.')
    seen = set()
    size = 0
    for item in changes:
        if not isinstance(item, dict) or not isinstance(item.get('key'), str) or not KEY.fullmatch(item['key']):
            raise ValueError('Unsupported saved setting name.')
        if item['key'] in seen:
            raise ValueError('A setting occurs twice in the same request.')
        seen.add(item['key'])
        value = item.get('value')
        if value is not None and not isinstance(value, str):
            raise ValueError('Settings must contain text or null.')
        size += len((value or '').encode('utf-8'))
        if size > MAX_VALUE * 2 or len((value or '').encode('utf-8')) > MAX_VALUE:
            raise ValueError('Saved settings are too large. Use metadata uploads for larger files.')
        revision = item.get('revision', 0)
        if type(revision) is not int or revision < 0:
            raise ValueError('Invalid setting revision.')


class SettingsConflict(ValueError):
    pass


def save_settings(user_id, changes, import_missing=False):
    validate_changes(changes)
    with db() as connection:
        connection.execute('BEGIN IMMEDIATE')
        for item in changes:
            row = connection.execute('SELECT revision,value FROM user_settings WHERE user_id=? AND key=?', (user_id, item['key'])).fetchone()
            if import_missing and row is not None:
                continue
            # A no-op from another tab is safe; different stale writes conflict.
            if row is not None and row['value'] == item.get('value'):
                continue
            revision = row['revision'] if row else 0
            if not import_missing and item.get('revision', 0) != revision:
                raise SettingsConflict('This setting was changed in another window. Reload to use the server copy; your unsaved copy remains in this browser.')
            connection.execute('''INSERT INTO user_settings VALUES (?,?,?,?,?)
                ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value,
                revision=excluded.revision,updated_at=excluded.updated_at''',
                (user_id, item['key'], item.get('value'), revision + 1, time.time()))
    return settings(user_id)


def archive_run(record, result, only_missing=False):
    statement = 'INSERT OR IGNORE' if only_missing else 'INSERT OR REPLACE'
    with db() as connection:
        connection.execute(statement + ' INTO run_archive VALUES (?,?,?,?,?,?,?)',
            (record['id'], (record.get('user') or {}).get('id'), record.get('testId', ''),
             record['kind'], record['createdAt'], json.dumps(record, ensure_ascii=False),
             json.dumps(result, ensure_ascii=False)))


def archived_run(run_id):
    with db() as connection:
        row = connection.execute('SELECT record_json,result_json FROM run_archive WHERE id=?', (run_id,)).fetchone()
    return (json.loads(row[0]), json.loads(row[1])) if row else None


def archived_records():
    with db() as connection:
        rows = connection.execute('SELECT record_json FROM run_archive ORDER BY created_at DESC').fetchall()
    return [json.loads(row[0]) for row in rows]
