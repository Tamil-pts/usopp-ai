"""Persistent local accounts and revocable browser sessions."""
import hashlib
import json
import hmac
import secrets
import sqlite3
import threading
import time
import os
import re
from contextlib import contextmanager, closing
from functools import lru_cache
from backend.core.runtime import BASE

COOKIE = 'usopp_session'
SESSION_SECONDS = 12 * 60 * 60
DEMO_SESSION_SECONDS = 30 * 60
ITERATIONS = 600000
WORKSPACE_MODULES = ('workhub','bytemap','datainspect','matchview','logicscan','virtual_plc','edesign','assistant')

def validate_workspace_modules(value):
    if value is None:return None
    if not isinstance(value,list) or any(not isinstance(v,str) or v not in WORKSPACE_MODULES for v in value):
        raise ValueError('Choose valid workspace modules.')
    return [v for v in WORKSPACE_MODULES if v in value]

def visible_modules(row):
    if row['role']=='admin' or not row['workspace_modules']:return list(WORKSPACE_MODULES)
    try:
        value=json.loads(row['workspace_modules'])
        return validate_workspace_modules(value) if isinstance(value,list) else list(WORKSPACE_MODULES)
    except (ValueError,TypeError):return list(WORKSPACE_MODULES)
def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS)
    return f'{ITERATIONS}${salt.hex()}${digest.hex()}'

def password_matches(password, encoded):
    count, salt, digest = encoded.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count)).hex()
    return hmac.compare_digest(actual, digest)

@lru_cache(maxsize=64)
def factory_password(encoded):
    try:return password_matches('usopp.2026',encoded)
    except (ValueError,TypeError):return False

def email_address(value):
    if value is None: return ''
    if not isinstance(value,str): raise ValueError('Enter a valid email address.')
    value=value.strip()
    if value and (len(value)>254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",value)):
        raise ValueError('Enter a valid email address.')
    return value

def public_user(row):
    return {key:row[key] for key in ('id','username','designation','company','role','email')} | {'active':bool(row['active']), 'approved':bool(row['approved']), 'createdAt':row['created_at'], 'isDemo':bool(row['is_demo']),
        'avatarUrl':f'/api/auth/profile-image/{row["id"]}?v={row["profile_image_version"]}' if row['profile_image'] else None,'workspaceModules':visible_modules(row),
        'passwordChangeRequired':row['role']=='admin' and factory_password(row['password_hash'])}

def session_seconds(user):
    return DEMO_SESSION_SECONDS if user.get('isDemo') else SESSION_SECONDS

class AccountStore:
    def __init__(self, path):
        self.path = path
        self._ready = False
        self._lock = threading.Lock()

    @contextmanager
    def db(self):
        self.initialize()
        connection = sqlite3.connect(str(self.path), timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        with self._lock:
            if self._ready:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(str(self.path), timeout=15)) as connection:
                connection.execute('PRAGMA journal_mode=WAL')
                connection.executescript('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY, username TEXT NOT NULL,
                        username_key TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                        designation TEXT NOT NULL, company TEXT NOT NULL, role TEXT NOT NULL,
                        created_at REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS sessions (
                        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS login_attempts (key TEXT NOT NULL, at REAL NOT NULL);
                    CREATE INDEX IF NOT EXISTS attempts_lookup ON login_attempts(key, at);
                    CREATE TABLE IF NOT EXISTS resource_owners (
                        path TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at REAL NOT NULL);
                ''')
                if 'active' not in {column[1] for column in connection.execute('PRAGMA table_info(users)')}:
                    connection.execute('ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
                columns = {column[1] for column in connection.execute('PRAGMA table_info(users)')}
                if 'email' not in columns:
                    connection.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
                if 'is_demo' not in columns:
                    connection.execute('ALTER TABLE users ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0')
                if 'approved' not in columns:
                    connection.execute('ALTER TABLE users ADD COLUMN approved INTEGER NOT NULL DEFAULT 1')
                if 'profile_image' not in columns:
                    connection.execute('ALTER TABLE users ADD COLUMN profile_image BLOB')
                if 'profile_image_version' not in columns:
                    connection.execute('ALTER TABLE users ADD COLUMN profile_image_version INTEGER NOT NULL DEFAULT 0')
                if 'workspace_modules' not in columns:
                    connection.execute('ALTER TABLE users ADD COLUMN workspace_modules TEXT')
                # Seed only once. A password change is never overwritten on restart.
                if not connection.execute("SELECT 1 FROM users WHERE username_key='admin'").fetchone():
                    initial_password = os.getenv('USOPP_INITIAL_ADMIN_PASSWORD', 'usopp.2026')
                    if not 8 <= len(initial_password) <= 128:
                        raise ValueError('The initial Admin password must contain 8 to 128 characters.')
                    connection.execute('INSERT INTO users (username,username_key,password_hash,designation,company,role,created_at) VALUES (?,?,?,?,?,?,?)',
                        ('Admin','admin',password_hash(initial_password),'Administrator','uSOPp.ai','admin',time.time()))
                # Preserve existing accounts; keep the demonstration login
                # separate from real account listings and workspaces.
                if not connection.execute("SELECT 1 FROM users WHERE username_key='demo'").fetchone():
                    connection.execute('INSERT INTO users (username,username_key,password_hash,designation,company,role,created_at,is_demo) VALUES (?,?,?,?,?,?,?,1)',
                        ('demo','demo',password_hash('demo'),'Demo user','uSOPp.ai','user',time.time()))
                connection.commit()
            self._ready = True

    def register(self, username, password, designation, company, role='user', email='', workspace_modules=None):
        email=email_address(email)
        workspace_modules=validate_workspace_modules(workspace_modules)
        if role not in ('admin','user'): raise ValueError('Choose Admin or User.')
        encoded = password_hash(password)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users WHERE username_key=?', (username.casefold(),)).fetchone():
                raise sqlite3.IntegrityError('Username already exists')
            result = db.execute('INSERT INTO users (username,username_key,password_hash,designation,company,role,created_at) VALUES (?,?,?,?,?,?,?)',
                (username,username.casefold(),encoded,designation,company,role,time.time()))
            db.execute('UPDATE users SET email=? WHERE id=?',(email,result.lastrowid))
            if workspace_modules is not None:db.execute('UPDATE users SET workspace_modules=? WHERE id=?',(json.dumps(workspace_modules),result.lastrowid))
            return public_user(db.execute('SELECT * FROM users WHERE id=?',(result.lastrowid,)).fetchone())

    def request_account(self, username, password, designation, company, email=''):
        email=email_address(email)
        encoded = password_hash(password)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users WHERE username_key=?', (username.casefold(),)).fetchone():
                raise sqlite3.IntegrityError('Username already exists')
            result = db.execute('INSERT INTO users (username,username_key,password_hash,designation,company,role,created_at,active,approved) VALUES (?,?,?,?,?,?,?,?,?)',
                (username,username.casefold(),encoded,designation,company,'user',time.time(),0,0))
            db.execute('UPDATE users SET email=? WHERE id=?',(email,result.lastrowid))
            return public_user(db.execute('SELECT * FROM users WHERE id=?',(result.lastrowid,)).fetchone())

    def login(self, username, password, client):
        key = hashlib.sha256(f'{client}:{username.casefold()}'.encode()).hexdigest()
        with self.db() as db:
            db.execute('DELETE FROM login_attempts WHERE at<?',(time.time()-300,))
            if db.execute('SELECT COUNT(*) FROM login_attempts WHERE key=?',(key,)).fetchone()[0] >= 10:
                return None, 'throttled'
            row = db.execute('SELECT * FROM users WHERE username_key=?',(username.casefold(),)).fetchone()
            valid = password_matches(password, row['password_hash'] if row else '600000$'+'0'*32+'$'+'0'*64)
            if row and valid and not row['approved']:
                db.execute('DELETE FROM login_attempts WHERE key=?',(key,))
                return None, 'pending'
            if not row or not valid or not row['active']:
                db.execute('INSERT INTO login_attempts VALUES (?,?)',(key,time.time()))
                return None, 'invalid'
            db.execute('DELETE FROM login_attempts WHERE key=?',(key,))
            return public_user(row), None

    def new_session(self, user_id):
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            user = db.execute('SELECT * FROM users WHERE id=? AND active=1',(user_id,)).fetchone()
            if not user:
                raise ValueError('Account is unavailable.')
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user_id,time.time()+session_seconds(public_user(user))))
        return token

    def user_for_token(self, token):
        if not token or len(token)>256:
            return None
        with self.db() as db:
            row = db.execute('SELECT u.*,s.expires AS session_expires FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?',
                (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
            if not row or not row['active']:
                return None
            user = public_user(row)
            if user['isDemo']:
                # Negative, JavaScript-safe IDs keep visitor settings, uploaded
                # projects and history separate for every demo login. Reloading
                # the same cookie retains the namespace and original deadline.
                user['id'] = -(int.from_bytes(hashlib.sha256(token.encode()).digest()[:6],'big') + 1)
                user['sessionExpiresAt'] = row['session_expires']
            return user

    def list_users(self):
        with self.db() as db:
            return [public_user(row) for row in db.execute('SELECT * FROM users WHERE is_demo=0 ORDER BY role,username_key')]

    def capacity(self):
        with self.db() as db:
            count = db.execute('SELECT COUNT(*) FROM users WHERE active=1 AND is_demo=0').fetchone()[0]
        return {'maxActiveUsers': None, 'activeUsers': count,
                'availableSlots': None, 'includesAdmin': True, 'unlimited': True}

    def manage_user(self, user_id, username, designation, company, active, password=None, role=None, actor_id=None, email=None, workspace_modules=None):
        workspace_modules=validate_workspace_modules(workspace_modules)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
            if not row: raise ValueError('Account not found.')
            if row['is_demo']: raise ValueError('The demo account uses fixed demonstration credentials.')
            role=row['role'] if role is None else role
            if role not in ('admin','user'): raise ValueError('Choose Admin or User.')
            if row['username_key']=='admin' and (username.casefold()!='admin' or not active or role!='admin'):
                raise ValueError('The primary Admin account must keep its username, Admin role and enabled access.')
            if user_id==actor_id and (not active or role!='admin'):
                raise ValueError('You cannot remove your own administrator access.')
            if row['role']=='admin' and row['active'] and (not active or role!='admin'):
                others=db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND is_demo=0 AND id!=?",(user_id,)).fetchone()[0]
                if not others: raise ValueError('Keep at least one enabled administrator.')
            db.execute('UPDATE users SET username=?,username_key=?,designation=?,company=?,role=?,active=?,approved=CASE WHEN ?=1 THEN 1 ELSE approved END WHERE id=?',
                       (username,username.casefold(),designation,company,role,int(active),int(active),user_id))
            if email is not None: db.execute('UPDATE users SET email=? WHERE id=?',(email_address(email),user_id))
            if workspace_modules is not None:db.execute('UPDATE users SET workspace_modules=? WHERE id=?',(json.dumps(workspace_modules),user_id))
            if password:
                db.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(password),user_id))
            if password or not active or row['username']!=username or row['role']!=role:
                db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            return public_user(db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone())

    def set_email(self, user_id, email):
        email=email_address(email)
        with self.db() as db:
            row=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
            if not row or row['is_demo']: raise ValueError('Use a personal account to set an email address.')
            db.execute('UPDATE users SET email=? WHERE id=?',(email,user_id))
            return public_user(db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone())

    def set_profile_image(self, user_id, image):
        with self.db() as db:
            row=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
            if not row or row['is_demo']: raise ValueError('Use a personal account to set a profile photo.')
            db.execute('UPDATE users SET profile_image=?,profile_image_version=profile_image_version+1 WHERE id=?',(image,user_id))
            return public_user(db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone())

    def profile_image(self, user_id):
        with self.db() as db:
            row=db.execute('SELECT profile_image FROM users WHERE id=?',(user_id,)).fetchone()
            return row['profile_image'] if row else None

    def delete_user(self, user_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not row:
                raise ValueError('Account not found.')
            if row['role'] == 'admin' or row['is_demo']:
                raise ValueError('The Admin and fixed demo accounts cannot be deleted.')
            paths = [item['path'] for item in db.execute('SELECT path FROM resource_owners WHERE user_id=?', (user_id,))]
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            db.execute('DELETE FROM resource_owners WHERE user_id=?', (user_id,))
            db.execute('DELETE FROM users WHERE id=?', (user_id,))
            return {'username': row['username'], 'paths': paths}

    def logout(self, token):
        if token:
            with self.db() as db:
                db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def change_password(self, user_id, current, replacement):
        with self.db() as db:
            row = db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
            if not row or row['is_demo'] or not password_matches(current,row['password_hash']):
                return False
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(replacement),user_id))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
        return True

store = AccountStore(BASE/'accounts.sqlite3')
