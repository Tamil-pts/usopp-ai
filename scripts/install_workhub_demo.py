"""Install a checked demo stage offline, preserving a complete rollback backup."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3

ROOT=Path(__file__).resolve().parents[1]


def copy_db(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(source) as src,sqlite3.connect(target) as dst:src.backup(dst)


def install(folder,backup,replace_local,ports=(8200,8391)):
    if not replace_local:raise RuntimeError('Explicit --replace-local is required to replace local demo records.')
    for path in (folder,backup):
        if not path.is_relative_to(ROOT/'.build'):raise RuntimeError('Use a stage and backup inside this checkout .build directory.')
    if backup.exists():raise RuntimeError('Use a new backup directory.')
    for port in ports:
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex(('127.0.0.1',port))==0:raise RuntimeError(f'Stop the checked local/test server on port {port} before installation.')
    result=json.loads((folder/'result.json').read_text());stage=folder/'stage'
    if not result.get('complete') or result['project_count']!=53 or result.get('dates_shifted') is not False:
        raise RuntimeError('Expected a completed 53-project stage preserving original dates.')
    with sqlite3.connect(ROOT/'accounts.sqlite3') as live,sqlite3.connect(stage/'accounts.sqlite3') as staged:
        admin=live.execute("SELECT id,password_hash FROM users WHERE username_key='admin'").fetchone()
        if admin!=staged.execute("SELECT id,password_hash FROM users WHERE username_key='admin'").fetchone():
            raise RuntimeError('The Admin identity or password changed. Reconcile the stage before installation.')
        old_users=live.execute("SELECT id,username FROM users WHERE username_key!='admin' AND is_demo=0").fetchall()
    for path in (ROOT/'.usopp_workhub/projects.sqlite3',stage/'.usopp_workhub/projects.sqlite3',ROOT/'accounts.sqlite3',stage/'accounts.sqlite3'):
        with sqlite3.connect(path) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Database integrity check failed.')
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    with sqlite3.connect(stage/'accounts.sqlite3') as db:db.execute('DELETE FROM sessions')
    with sqlite3.connect(stage/'.usopp_workhub/projects.sqlite3') as db:
        assert db.execute("SELECT count(*) FROM items WHERE type='project' AND is_sample=1").fetchone()[0]==53
        assert db.execute("SELECT count(*) FROM pi_jobs WHERE status IN ('running','queued')").fetchone()[0]==0
    backup.mkdir(parents=True)
    copy_db(ROOT/'accounts.sqlite3',backup/'accounts.sqlite3')
    if (ROOT/'application.sqlite3').exists():copy_db(ROOT/'application.sqlite3',backup/'application.sqlite3')
    mappings=ROOT/'knowledge/master/parameter_mappings.json';mapping_hash=hashlib.sha256(mappings.read_bytes()).hexdigest()
    live_hub=ROOT/'.usopp_workhub';saved_hub=backup/'.usopp_workhub'
    # Check both absolute endpoints before moving the complete directory.
    assert live_hub.resolve().is_relative_to(ROOT) and saved_hub.resolve().is_relative_to(backup)
    live_hub.rename(saved_hub)
    try:
        shutil.copytree(stage/'.usopp_workhub',live_hub,ignore=shutil.ignore_patterns('*-wal','*-shm'))
        copy_db(stage/'accounts.sqlite3',ROOT/'accounts.sqlite3')
        assert hashlib.sha256(mappings.read_bytes()).hexdigest()==mapping_hash
        with sqlite3.connect(ROOT/'accounts.sqlite3') as db:
            assert db.execute("SELECT id,password_hash FROM users WHERE username_key='admin'").fetchone()==admin
        with sqlite3.connect(live_hub/'projects.sqlite3') as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    except Exception:
        # Keep any partial output for diagnosis, and restore the original data.
        if live_hub.exists():live_hub.rename(backup/'failed-demo-install')
        saved_hub.rename(live_hub);copy_db(backup/'accounts.sqlite3',ROOT/'accounts.sqlite3')
        raise
    manifest={'installed':True,'stage':str(stage),'backup':str(backup),'removed_old_users':old_users,
              'projects':53,'admin_password_preserved':True,'master_mapping_sha256_unchanged':mapping_hash}
    (backup/'installation.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    print(json.dumps({'installed':True,'projects':53,'removed_old_users':len(old_users),'backup':str(backup)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--replace-local',action='store_true');args=parser.parse_args()
    install(args.folder.resolve(),args.backup.resolve(),args.replace_local)
