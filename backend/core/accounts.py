"""Persistent local accounts and revocable browser sessions."""
import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
import os
from contextlib import contextmanager, closing
from backend.core.runtime import BASE

COOKIE = 'usopp_session'
SESSION_SECONDS = 12 * 60 * 60
DEMO_SESSION_SECONDS = 30 * 60
ITERATIONS = 600000
# Keep USOPP_MAX_USERS as the total account limit for existing deployments.
# Six enabled accounts allow five regular users plus the seeded Admin.
MAX_ACTIVE_USERS = max(1, int(os.getenv('USOPP_MAX_USERS', '6')))

class AccountCapacityError(ValueError):
    pass

def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS)
    return f'{ITERATIONS}${salt.hex()}${digest.hex()}'

def password_matches(password, encoded):
    count, salt, digest = encoded.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count)).hex()
    return hmac.compare_digest(actual, digest)

def public_user(row):
    return {key:row[key] for key in ('id','username','designation','company','role')} | {'active':bool(row['active']), 'approved':bool(row['approved']), 'createdAt':row['created_at'], 'isDemo':bool(row['is_demo'])}

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
                if 'is_demo' not in columns:
                    connection.execute('ALTER TABLE users ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0')
                if 'approved' not in columns:
                    connection.execute('ALTER TABLE users ADD COLUMN approved INTEGER NOT NULL DEFAULT 1')
                # Seed only once. A password change is never overwritten on restart.
                if not connection.execute("SELECT 1 FROM users WHERE username_key='admin'").fetchone():
                    initial_password = os.getenv('USOPP_INITIAL_ADMIN_PASSWORD', 'usopp.2026')
                    if not 8 <= len(initial_password) <= 128:
                        raise ValueError('The initial Admin password must contain 8 to 128 characters.')
                    connection.execute('INSERT INTO users (username,username_key,password_hash,designation,company,role,created_at) VALUES (?,?,?,?,?,?,?)',
                        ('Admin','admin',password_hash(initial_password),'Administrator','uSOPp.ai','admin',time.time()))
                # Preserve existing accounts; reserve a separate demonstration
                # account without using any regular-user capacity.
                if not connection.execute("SELECT 1 FROM users WHERE username_key='demo'").fetchone():
                    connection.execute('INSERT INTO users (username,username_key,password_hash,designation,company,role,created_at,is_demo) VALUES (?,?,?,?,?,?,?,1)',
                        ('demo','demo',password_hash('demo'),'Demo user','uSOPp.ai','user',time.time()))
                connection.commit()
            self._ready = True

    def register(self, username, password, designation, company):
        encoded = password_hash(password)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users WHERE username_key=?', (username.casefold(),)).fetchone():
                raise sqlite3.IntegrityError('Username already exists')
            self._check_capacity(db)
            result = db.execute('INSERT INTO users (username,username_key,password_hash,designation,company,role,created_at) VALUES (?,?,?,?,?,?,?)',
                (username,username.casefold(),encoded,designation,company,'user',time.time()))
            return public_user(db.execute('SELECT * FROM users WHERE id=?',(result.lastrowid,)).fetchone())

    def request_account(self, username, password, designation, company):
        encoded = password_hash(password)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users WHERE username_key=?', (username.casefold(),)).fetchone():
                raise sqlite3.IntegrityError('Username already exists')
            result = db.execute('INSERT INTO users (username,username_key,password_hash,designation,company,role,created_at,active,approved) VALUES (?,?,?,?,?,?,?,?,?)',
                (username,username.casefold(),encoded,designation,company,'user',time.time(),0,0))
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
        return {'maxActiveUsers': MAX_ACTIVE_USERS, 'activeUsers': count,
                'availableSlots': max(0, MAX_ACTIVE_USERS-count), 'includesAdmin': True}

    def _check_capacity(self, db):
        if db.execute('SELECT COUNT(*) FROM users WHERE active=1 AND is_demo=0').fetchone()[0] >= MAX_ACTIVE_USERS:
            raise AccountCapacityError(f'The {MAX_ACTIVE_USERS}-account limit is reached, including Admin. Disable an unused account or increase USOPP_MAX_USERS on the server.')

    def manage_user(self, user_id, username, designation, company, active, password=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
            if not row: raise ValueError('Account not found.')
            if row['is_demo']: raise ValueError('The demo account uses fixed demonstration credentials.')
            if row['role']=='admin': raise ValueError('Use your account settings to change the administrator password. The administrator account cannot be disabled or renamed here.')
            if active and not row['active']:
                self._check_capacity(db)
            db.execute('UPDATE users SET username=?,username_key=?,designation=?,company=?,active=?,approved=CASE WHEN ?=1 THEN 1 ELSE approved END WHERE id=?',
                       (username,username.casefold(),designation,company,int(active),int(active),user_id))
            if password:
                db.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(password),user_id))
            if password or not active or row['username']!=username:
                db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            return public_user(db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone())

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
