"""Shared offline reference retrieval. Project evidence remains separate."""
import hashlib
import os
import re
import sqlite3
import threading
from backend.core.runtime import KNOWLEDGE, RESOURCE_ROOT, log
from python_engine import br_help_index as engine

GUIDE = RESOURCE_ROOT / 'knowledge/help_index/project_guide.json'
MANUAL = RESOURCE_ROOT / 'knowledge/help_index/BR_PROJECT_HELP.md'
ROOT = KNOWLEDGE / 'br_help'
DATABASE = KNOWLEDGE / 'help_index/br_help.sqlite3'
LOCK = threading.RLock()
STATE = {'phase': 'idle', 'stage': '', 'current': 0, 'total': 0, 'error': ''}
_meta_cache = (None, None)


def topics():
    return engine.load_guide(GUIDE)


def _guide_document(topic):
    text = engine.topic_text(topic)
    return {'id': 'guide-' + topic['id'], 'kind': 'guide', 'title': topic['title'],
            'category': topic['category'], 'library': '', 'helpSet': 'uSOPp project guide',
            'file': 'help_index/project_guide.json#' + topic['id'], 'text': text,
            'excerpt': text[:500], 'headings': topic.get('keywords', []), 'images': [],
            'digest': hashlib.sha256(text.encode()).hexdigest(), 'truncated': False}


def _metadata():
    global _meta_cache
    stamp = DATABASE.stat().st_mtime_ns if DATABASE.exists() else None
    if stamp != _meta_cache[0]:
        try: _meta_cache = (stamp, engine.metadata(DATABASE))
        except (sqlite3.DatabaseError, OSError, ValueError):
            log.exception('BR_HELP_INDEX_READ_ERROR; compact guide remains available')
            _meta_cache = (stamp, None)
            STATE.update(error='The reference index could not be read. Rebuild it to restore manual search.')
    return _meta_cache[1]


def status():
    with LOCK:
        meta = _metadata()
        guide = topics()
        return {**STATE, 'index': meta, 'vendorHelpAvailable': ROOT.is_dir(),
                'guideOutdated': bool(meta and meta.get('guideDigest') != hashlib.sha256(GUIDE.read_bytes()).hexdigest()),
                'topics': [{'id': 'guide-' + t['id'], 'title': t['title'], 'category': t['category']} for t in guide],
                'categories': sorted({t['category'] for t in guide} | set((meta or {}).get('categories', {}))),
                'notice': 'Reference retrieval does not train model weights. Check documentation against the installed library and runtime version.'}


def search(query='', category='', limit=12):
    with LOCK:
        if _metadata(): return engine.search(DATABASE, query, category, limit)
        terms = set(engine.tokenize(query))
        records = [_guide_document(t) for t in topics() if not category or t['category'] == category]
        if terms: records = [d for d in records if terms & set(engine.tokenize(d['title'] + ' ' + d['text']))]
        ranked = sorted(records, key=lambda d: -len(terms & set(engine.tokenize(d['title'] + ' ' + d['text']))))
        return [{k: v for k, v in d.items() if k not in {'text', 'images', 'headings', 'digest'}} for d in ranked[:limit]]


def document(identifier):
    with LOCK:
        if identifier.startswith('guide-'):
            return next((_guide_document(t) for t in topics() if 'guide-' + t['id'] == identifier), None)
        return engine.document(DATABASE, identifier) if _metadata() else None


def rebuild():
    with LOCK:
        if STATE['phase'] == 'building': return status()
        STATE.update(phase='building', stage='Discovering supplied B&R documentation', current=0, total=0, error='')
    def worker():
        temporary = None
        def progress(stage, current, total):
            with LOCK: STATE.update(stage=stage, current=current, total=total)
        try:
            temporary, meta = engine.build_index(ROOT, GUIDE, DATABASE, progress)
            with LOCK:
                os.replace(temporary, DATABASE)
                STATE.update(phase='ready', stage='Reference index ready')
            log.info('BR_HELP_INDEX_READY counts=%s', meta['counts'])
        except Exception as error:
            if temporary: temporary.unlink(missing_ok=True)
            with LOCK: STATE.update(phase='error', error=str(error), stage='Index rebuild failed; previous index retained')
            log.exception('BR_HELP_INDEX_BUILD_ERROR')
    threading.Thread(target=worker, name='br-help-index', daemon=True).start()
    return status()


def autostart():
    state = status()
    if not state['index'] or state['guideOutdated']: rebuild()


def reference_question(question):
    value = str(question)
    return bool(re.search(r'\b(?:syntax|standards?|decode|formats?|documentation|manual|structured text|automation basic|how.*(?:ladder|\.st|\.var|\.typ|screen file))\b', value, re.I)) and not bool(re.search(r'\b(?:available|present|implemented)\b', value, re.I))


def reference_evidence(question, project_evidence=None):
    """Bounded excerpts, independent of the project reading budget."""
    question = str(question)[:800]
    general = reference_question(question)
    if not general and re.search(r'\b(?:WorkHub|ByteMap|MetaWorks|DataInspect|MatchView|LogicScan|KnowHub|ResultView)\b', question, re.I): return []
    terms = set(engine.tokenize(question))
    ranked = sorted(topics(), key=lambda t: -(2 * len(terms & set(engine.tokenize(t['title']))) + len(terms & set(engine.tokenize(' '.join(t.get('keywords', [])))))))
    candidates = []
    if ranked and terms & set(engine.tokenize(' '.join(ranked[0].get('keywords', [])) + ' ' + ranked[0]['title'])):
        candidates.append(_guide_document(ranked[0]))
        if general and len(ranked) > 1 and terms & set(engine.tokenize(' '.join(ranked[1].get('keywords', [])) + ' ' + ranked[1]['title'])):
            candidates.append(_guide_document(ranked[1]))
    if not general and not candidates and not project_evidence and len(terms) < 2: return []
    # Use actual referenced block names to improve library lookup.
    query = question
    for item in (project_evidence or [])[:4]:
        query += ' ' + ' '.join(re.findall(r'\b([A-Za-z_]\w+)\s*\(', item.get('excerpt', ''))[:3])
    try:
        vendor = search(query[:1000], 'libraries' if not general else '', 8)
        candidates.extend(d for d in vendor if d['kind'] == 'vendor')
        if not vendor and general: candidates.extend(_guide_document(t) for t in ranked[1:3])
    except Exception:
        log.exception('BR_HELP_RETRIEVAL_ERROR; compact guide retained')
    result, budget, seen = [], 4200, set()
    for candidate in candidates:
        if candidate['id'] in seen or budget < 200 or len(result) >= 3: continue
        seen.add(candidate['id'])
        doc = document(candidate['id'])
        if not doc: continue
        if candidate['kind'] == 'guide':
            paragraphs = doc['text'].split('\n\n')
            relevant = sorted(enumerate(paragraphs[1:], 1), key=lambda p: -len(terms & set(engine.tokenize(p[1]))))
            selected = {0, *(i for i, _ in relevant[:3])}
            body = '\n\n'.join(p for i, p in enumerate(paragraphs) if i in selected)
            excerpt = body[:min(1800, budget)]
        else:
            # Include title/start plus the full-text match vicinity for long manuals.
            match = candidate.get('excerpt', '')
            excerpt = (doc['text'][:650] + '\n...\n' + match)[:min(1600, budget)]
        budget -= len(excerpt)
        result.append({k: doc[k] for k in ('id', 'kind', 'title', 'category', 'library', 'helpSet', 'file', 'digest', 'truncated')} |
                      {'sourceId': f'H{len(result)+1}', 'excerpt': excerpt,
                       'excerptTruncated': len(doc['text']) > len(excerpt),
                       'coverage': 'Reference excerpt; not proof of project execution or runtime compatibility.'})
    return result


def local_answer(evidence):
    return '\n\n'.join(['B&R reference help (local excerpts):'] +
                       [f'[{d["sourceId"]}] {d["title"]}\n{d["excerpt"]}\nSource: {d["file"]}' for d in evidence] +
                       ['Examples illustrate syntax. Match vendor help to the project library/runtime version before applying an edit.'])
