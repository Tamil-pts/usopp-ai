"""Bounded offline module documentation; never loads vendor scripts or drivers."""
from functools import lru_cache
from pathlib import Path
import re
from urllib.parse import unquote

from python_engine.br_help_index import HelpText, read_text

ROOT = Path(__file__).resolve().parents[2] / 'knowledge/br_help'
HARDWARE = ROOT / 'AS12/Help-en/Data/hardware'
IMAGE_TYPES = {'.png', '.gif', '.jpg', '.jpeg', '.webp', '.bmp'}


def safe_path(relative, images=False):
    path = (ROOT / unquote(str(relative))).resolve()
    if not path.is_relative_to(HARDWARE.resolve()) or not path.is_file():
        raise ValueError('Local hardware help resource was not found.')
    if path.suffix.lower() not in (IMAGE_TYPES if images else {'.html', '.htm'}):
        raise ValueError('Unsupported help resource type.')
    if path.stat().st_size > 8*1024*1024: raise ValueError('Help resource exceeds 8 MiB.')
    return path


@lru_cache(maxsize=256)
def document(relative):
    path = safe_path(relative)
    parser = HelpText()
    parser.feed(read_text(path.read_bytes()))
    lines = [' '.join(line.split()) for line in ''.join(parser.text).splitlines() if line.strip()]
    images = []
    for entry in parser.images[:32]:
        source = entry['src'].split('#', 1)[0].split('?', 1)[0]
        if re.match(r'^[a-z]+:', source, re.I): continue
        candidate = (path.parent / unquote(source.replace('\\', '/'))).resolve()
        if candidate.is_relative_to(HARDWARE.resolve()) and candidate.is_file() and candidate.suffix.lower() in IMAGE_TYPES:
            images.append({'path': candidate.relative_to(ROOT).as_posix(), 'caption': entry['caption']})
    body = '\n'.join(lines)
    return {'path': path.relative_to(ROOT).as_posix(), 'title': ''.join(parser.title).strip(),
            'text': body[:100000], 'truncated': len(body) > 100000, 'images': images,
            'referenceOnly': True}


@lru_cache(maxsize=1)
def folders():
    return sorted((p for p in HARDWARE.iterdir() if p.is_dir()), key=lambda p: p.name) if HARDWARE.is_dir() else []


@lru_cache(maxsize=256)
def module_details(model):
    model = str(model).strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{2,80}', model):
        return {'model': model[:80], 'available': False, 'topics': []}
    key = model.casefold()
    exact = [p for p in folders() if p.name.casefold() == key]
    candidates = exact
    if not candidates:
        # B&R explicitly names shared data sheets AP31x1, CP04xx, etc. Keep
        # these marked as family references; do not claim an exact model match.
        candidates = [p for p in folders() if 'x' in p.name[3:].lower() and any(re.fullmatch(
            re.escape(p.name[:3]) + ''.join(r'\d' if c.lower() == 'x' else re.escape(c) for c in p.name[3:]), variant, re.I)
            for variant in {key, key.rsplit('-', 1)[0]})]
    if not candidates and '-' in key:
        candidates = [p for p in folders() if p.name.lower() == key.rsplit('-', 1)[0]]
    if len(candidates) > 1:
        verified = []
        for folder in candidates:
            files = list(folder.glob('bestelldaten*.html')) + list(folder.glob(folder.name+'.html'))
            content = '\n'.join(document(p.relative_to(ROOT).as_posix())['text'] for p in files)
            if re.search(r'(?<![A-Za-z0-9])'+re.escape(model)+r'(?![A-Za-z0-9-])', content, re.I): verified.append(folder)
        if len(verified) == 1: candidates = verified
    if len(candidates) != 1: return {'model': model, 'available': False, 'topics': []}
    folder = candidates[0]
    topics = []
    for path in sorted(folder.rglob('*.htm*'))[:350]:
        if path.stat().st_size > 8*1024*1024: continue
        # Titles are enough for the module index. Topic bodies are read on demand.
        raw = read_text(path.read_bytes()[:16384])
        title = re.search(r'<title[^>]*>(.*?)</title>', raw, re.I | re.S)
        parser = HelpText(); parser.feed(title[0] if title else path.stem)
        topics.append({'title': ''.join(parser.title).strip() or path.stem,
                       'path': path.relative_to(ROOT).as_posix()})
    priority = lambda t: (0 if Path(t['path']).stem == folder.name else
                          1 if 'technical data' in t['title'].lower() else
                          2 if 'general information' in t['title'].lower() else 3, t['path'])
    topics.sort(key=priority)
    summaries = []
    for topic in topics:
        if 'general information' in topic['title'].lower() or 'technical data' in topic['title'].lower():
            summaries.append(document(topic['path']))
        if len(summaries) >= 3: break
    text = '\n'.join(d['text'] for d in summaries)
    family = None
    for term, label in [('bus receiver', 'Bus receiver'), ('bus transmitter', 'Bus transmitter'),
                        ('serial interface', 'Serial interface'), ('power measurement', 'Power measurement'),
                        ('power supply', 'Power supply'), ('cpu base', 'CPU base')]:
        if term in text.lower(): family = label; break
    if key.startswith('x20cs') and re.search(r'RS(?:232|422|485)', text): family = 'Serial interface'
    if key.startswith('x20bb'): family = 'CPU base'
    # General data sheets also mention their supply. Use the documented module
    # family for the device label instead of classifying every device as a PSU.
    family_prefixes = {'x20cp': 'CPU', 'x20di': 'Digital input', 'x20do': 'Digital output',
                       'x20ai': 'Analog input', 'x20ao': 'Analog output',
                       'x20br': 'Bus receiver', 'x20bt': 'Bus transmitter',
                       'x20ps': 'Power supply'}
    family = family_prefixes.get(key[:5], family)
    channel_count = None
    for line in text.splitlines():
        if re.search(r'number of (?:digital|analog) (?:inputs|outputs)\b', line, re.I):
            numbers = re.findall(r'\|\s*(\d+)\s*(?=\||$)', line)
            if numbers and len(set(numbers)) == 1: channel_count = int(numbers[0])
    kind = {'x20di': 'digital inputs', 'x20do': 'digital outputs', 'x20ai': 'analog inputs', 'x20ao': 'analog outputs'}.get(key[:5])
    if kind:
        numbers = re.findall(r'\b(\d+)\s+'+kind, text, re.I)
        if numbers and len(set(numbers)) == 1: channel_count = int(numbers[0])
    return {'model': model, 'available': True, 'scope': 'exact' if exact else 'family',
            'family': folder.name, 'type': family, 'channelCount': channel_count,
            'topics': topics, 'summary': '\n'.join(d['text'] for d in summaries)[:3000],
            'images': [image for doc in summaries for image in doc['images']][:6]}


def search(query):
    query = str(query).strip()
    exact = module_details(query)
    if exact['available']: return [exact]
    terms = query.casefold()
    return [{'model': p.name.upper(), 'available': True, 'scope': 'directory'}
            for p in folders() if terms and terms in p.name.casefold()][:40]
