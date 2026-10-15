"""Offline B&R documentation indexing. No model, web request or PLC execution."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

SCHEMA = 1
DOCUMENT_EXTENSIONS = {'.html', '.htm', '.xml', '.txt', '.st', '.ab', '.c', '.h', '.var', '.typ', '.ld'}
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 100000


class HelpText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.title, self.headings, self.images = [], [], [], []
        self.hidden = 0
        self.in_title = False
        self.heading = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {'script', 'style', 'noscript'}: self.hidden += 1
        if tag == 'title': self.in_title = True
        if tag in {'h1', 'h2', 'h3'}: self.heading = []
        if tag in {'p', 'div', 'tr', 'li', 'br', 'pre', 'h1', 'h2', 'h3'}: self.text.append('\n')
        if tag in {'td', 'th'}: self.text.append(' | ')
        if tag == 'img' and attrs.get('src'):
            self.images.append({'src': attrs['src'], 'caption': attrs.get('alt', '')})

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript'}: self.hidden = max(0, self.hidden - 1)
        if tag == 'title': self.in_title = False
        if tag in {'h1', 'h2', 'h3'} and self.heading is not None:
            self.headings.append(' '.join(''.join(self.heading).split()))
            self.heading = None
        if tag in {'p', 'div', 'tr', 'li', 'pre'}: self.text.append('\n')

    def handle_data(self, data):
        if self.hidden: return
        if self.in_title: self.title.append(data)
        if self.heading is not None: self.heading.append(data)
        self.text.append(data)


def read_text(raw):
    charset = re.search(br'charset\s*=\s*["\']?([a-z0-9_-]+)', raw[:4096], re.I)
    for encoding in ([charset.group(1).decode('ascii')] if charset else []) + ['utf-8-sig', 'cp1252']:
        try: return raw.decode(encoding)
        except (UnicodeError, LookupError): pass
    return raw.decode('utf-8', errors='replace')


def load_guide(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return data['topics']


def tokenize(value):
    expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(value))
    return list(dict.fromkeys(re.findall(r'[A-Za-z_][A-Za-z0-9_]{1,}', expanded.casefold())))


def document_paths(root):
    if not root.is_dir(): return
    # A documentation directory called "temp" or "as" can contain genuine
    # manual topics; project exclusions do not apply to this separate corpus.
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in {'.git', '__pycache__', '.cache'} and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            path = Path(folder) / name
            if path.suffix.casefold() in DOCUMENT_EXTENSIONS and not path.is_symlink(): yield path


def build_index(root, guide_path, database, progress=None):
    root, database = Path(root).resolve(), Path(database).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    sources = list(document_paths(root))
    if progress: progress('Reading B&R help', 0, len(sources))
    fd, temporary = tempfile.mkstemp(prefix='br-help-', suffix='.sqlite3', dir=database.parent)
    os.close(fd)
    counts = {'guide': 0, 'vendor': 0, 'skipped': 0, 'truncated': 0}
    categories, skip_reasons = {}, {}
    fingerprint = hashlib.sha256()
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.executescript('''
                PRAGMA journal_mode=OFF;
                PRAGMA synchronous=OFF;
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE documents (id TEXT PRIMARY KEY, kind TEXT, title TEXT, category TEXT,
                    library TEXT, help_set TEXT, file TEXT, text TEXT, headings TEXT,
                    images TEXT, digest TEXT, truncated INTEGER, keywords TEXT);
                CREATE TABLE sources (file TEXT PRIMARY KEY, bytes INTEGER, digest TEXT, status TEXT, reason TEXT);
                CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED, title, keywords, text,
                    content='documents', content_rowid='rowid', tokenize='unicode61');
            ''')
            def add(record):
                record['keywords'] = ' '.join(tokenize(record['title'] + ' ' + record['file'] + ' ' + record.get('keywords', '')))
                row = db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', tuple(record[k] for k in
                    ('id', 'kind', 'title', 'category', 'library', 'helpSet', 'file', 'text', 'headings', 'images', 'digest', 'truncated', 'keywords')))
                db.execute('INSERT INTO search(rowid,id,title,keywords,text) VALUES (?,?,?,?,?)',
                           (row.lastrowid, record['id'], record['title'], record['keywords'], record['text']))

            guide_raw = Path(guide_path).read_bytes()
            fingerprint.update(guide_raw)
            for topic in load_guide(guide_path):
                body = topic_text(topic)
                add({'id': 'guide-' + topic['id'], 'kind': 'guide', 'title': topic['title'],
                     'category': topic['category'], 'library': '', 'helpSet': 'uSOPp project guide',
                     'file': 'help_index/project_guide.json#' + topic['id'], 'text': body,
                     'headings': json.dumps(topic.get('keywords', [])), 'images': '[]',
                     'digest': hashlib.sha256(body.encode()).hexdigest(), 'truncated': 0,
                     'keywords': ' '.join(topic.get('keywords', []))})
                counts['guide'] += 1
            for number, path in enumerate(sources, 1):
                relative = path.relative_to(root).as_posix()
                size, digest, source_status, reason = 0, '', 'skipped', ''
                try:
                    stat = path.stat()
                    size = stat.st_size
                    fingerprint.update(f'{relative}:{stat.st_size}:{stat.st_mtime_ns}\n'.encode())
                    if stat.st_size > MAX_FILE_BYTES:
                        counts['skipped'] += 1
                        reason = 'file-size-limit'
                        continue
                    raw = path.read_bytes()
                    digest = hashlib.sha256(raw).hexdigest()
                    text = read_text(raw)
                    parser = HelpText()
                    if path.suffix.casefold() in {'.html', '.htm', '.xml'}:
                        parser.feed(text)
                        text = '\n'.join(re.sub(r'[ \t\r\f\v]+', ' ', line).strip() for line in ''.join(parser.text).splitlines())
                        text = re.sub(r'\n{3,}', '\n\n', text).strip()
                    if not text.strip():
                        counts['skipped'] += 1
                        reason = 'no-extracted-text'
                        continue
                    title = ' '.join(''.join(parser.title).split()) or next(iter(parser.headings), path.stem)
                    parts = list(path.relative_to(root).parts)
                    lower = [p.casefold() for p in parts]
                    library = parts[lower.index('libraries') + 1] if 'libraries' in lower and lower.index('libraries') + 1 < len(parts) else ''
                    category = parts[lower.index('data') + 1] if 'data' in lower and lower.index('data') + 1 < len(parts) else 'Reference'
                    images = []
                    for image in parser.images:
                        src = image['src'].split('#')[0].split('?')[0]
                        if re.match(r'^(?:[a-z]+:|//)', src, re.I): continue
                        target = (path.parent / src.replace('\\', '/')).resolve()
                        if target.is_relative_to(root) and target.is_file() and target.suffix.casefold() in {'.png', '.gif', '.jpg', '.jpeg'}:
                            images.append({'file': target.relative_to(root).as_posix(), 'caption': image['caption']})
                        if len(images) >= 16: break
                    truncated = len(text) > MAX_TEXT_CHARS
                    add({'id': hashlib.sha256(relative.encode()).hexdigest(), 'kind': 'vendor',
                         'title': title[:500], 'category': category, 'library': library,
                         'helpSet': parts[0] if parts else 'B&R help', 'file': 'br_help/' + relative,
                         'text': text[:MAX_TEXT_CHARS], 'headings': json.dumps(parser.headings[:40]),
                         'images': json.dumps(images), 'digest': digest, 'truncated': int(truncated)})
                    counts['vendor'] += 1
                    counts['truncated'] += int(truncated)
                    categories[category] = categories.get(category, 0) + 1
                    source_status = 'truncated' if truncated else 'indexed'
                except (OSError, ValueError) as error:
                    counts['skipped'] += 1
                    reason = type(error).__name__
                finally:
                    db.execute('INSERT INTO sources VALUES (?,?,?,?,?)', (relative, size, digest, source_status, reason))
                    if source_status == 'skipped': skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                    if number % 250 == 0 or number == len(sources):
                        db.commit()
                        if progress: progress('Reading B&R help', number, len(sources))
            meta = {'schema': SCHEMA, 'builtAt': datetime.now(timezone.utc).isoformat(),
                    'counts': counts, 'sourceFiles': len(sources), 'fingerprint': fingerprint.hexdigest(),
                    'guideDigest': hashlib.sha256(guide_raw).hexdigest(), 'root': str(root),
                    'categories': categories, 'skipReasons': skip_reasons,
                    'coverage': 'Supplied local documentation; help-set labels are not proof of compatibility with a project runtime.',
                    'limits': {'maxFileBytes': MAX_FILE_BYTES, 'maxTextChars': MAX_TEXT_CHARS}}
            db.execute('INSERT INTO meta VALUES (?,?)', ('index', json.dumps(meta)))
            db.commit()
        with open(temporary, 'r+b') as stream: os.fsync(stream.fileno())
        return Path(temporary), meta
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def topic_text(topic):
    parts = [topic['summary'], *topic.get('details', [])]
    if topic.get('example'): parts.extend(['Illustrative example (not project source):', topic['example']])
    if topic.get('references'): parts.append('References: ' + ', '.join(topic['references']))
    return '\n\n'.join(parts)


def metadata(database):
    if not Path(database).is_file(): return None
    with closing(sqlite3.connect(f'file:{Path(database).resolve().as_posix()}?mode=ro', uri=True)) as db:
        row = db.execute('SELECT value FROM meta WHERE key=?', ('index',)).fetchone()
        return json.loads(row[0]) if row else None


def search(database, query, category='', limit=12):
    tokens = [t for t in tokenize(query) if t not in {'the', 'this', 'that', 'what', 'how', 'does', 'please', 'project', 'check', 'file', 'for', 'with', 'from', 'and', 'available', 'feature'}][:16]
    with closing(sqlite3.connect(f'file:{Path(database).resolve().as_posix()}?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        if tokens:
            expression = ' OR '.join('"' + token + '"*' for token in tokens)
            rows = db.execute('''SELECT d.id,d.kind,d.title,d.category,d.library,d.help_set AS helpSet,
                       d.file,d.truncated,snippet(search,3,'','',' ... ',42) AS excerpt
                       FROM search JOIN documents d ON d.id=search.id
                       WHERE search MATCH ? AND (?='' OR d.category=?)
                       ORDER BY bm25(search,0,15,8,1),d.file LIMIT ?''', (expression, category, category, limit)).fetchall()
        else:
            rows = db.execute('''SELECT id,kind,title,category,library,help_set AS helpSet,file,truncated,
                        substr(text,1,500) AS excerpt FROM documents WHERE (?='' OR category=?)
                        ORDER BY kind,title LIMIT ?''', (category, category, limit)).fetchall()
        return [dict(row) for row in rows]


def document(database, identifier):
    with closing(sqlite3.connect(f'file:{Path(database).resolve().as_posix()}?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT *,help_set AS helpSet FROM documents WHERE id=?', (identifier,)).fetchone()
        if not row: return None
        result = dict(row)
        result['headings'] = json.loads(result['headings'])
        result['images'] = json.loads(result['images'])
        return result
