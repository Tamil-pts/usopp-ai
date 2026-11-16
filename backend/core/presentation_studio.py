"""Private local presentation drafts with immutable source snapshots and revision checks."""
import hashlib
import json
import re
import textwrap
import threading
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from pydantic import Field
from backend.core.runtime import WORK
from backend.core import visual_content as visual
from backend.core.workhub_intelligence import local_ai

LOCK = threading.RLock()

@contextmanager
def write_lock(user):
    root=home(user);root.mkdir(parents=True,exist_ok=True)
    # File publication is atomic; this short SQLite transaction serializes revision
    # checks across multiple backend processes as well as browser windows.
    with sqlite3.connect(root/'write-lock.sqlite3',timeout=10) as db:
        db.execute('BEGIN IMMEDIATE')
        yield

def fail(message, status=422):
    raise HTTPException(status, message)

def home(user):
    if not user or not isinstance(user.get('id'), int):
        fail('Sign in to use Presentation Studio.', 401)
    if user.get('role') != 'admin' and 'assistant' not in user.get('workspaceModules', []):
        fail('AI Assist is not enabled for this account.', 403)
    # Include account creation identity: deleted/recreated numeric IDs cannot inherit drafts.
    identity = hashlib.sha256(str((user['id'], user.get('username'), user.get('createdAt'))).encode()).hexdigest()[:24]
    return WORK/'presentation-studio'/identity

def path_for(user, key):
    if not re.fullmatch('[0-9a-f]{32}', key):
        fail('Invalid presentation reference.', 400)
    return home(user)/key

def publish(path, data):
    path.mkdir(parents=True, exist_ok=True)
    tmp = path/(uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path/'record.json')

def load(user, key):
    path = path_for(user, key)
    if not (path/'record.json').is_file():
        fail('Presentation not found for this account.', 404)
    return json.loads((path/'record.json').read_text(encoding='utf-8'))

class DraftCard(visual.Strict):
    title: str = Field(min_length=1,max_length=70)
    description: str = Field(default='',max_length=120)

class OutlineSlide(visual.Strict):
    title: str = Field(min_length=1, max_length=100)
    bullets: list[str] = Field(default_factory=list, max_length=4)
    source_ids: list[str] = Field(default_factory=list, max_length=4)
    layout: str = 'bullets'
    cards: list[DraftCard] = Field(default_factory=list,max_length=4)

class Plan(visual.Strict):
    slides: list[OutlineSlide] = Field(min_length=1, max_length=20)

def generate(user, payload):
    home(user)
    prompt = str(payload.get('prompt') or '').strip()
    if not 4 <= len(prompt) <= 4000:
        fail('Describe the presentation in 4 to 4,000 characters.')
    count = payload.get('count', 6)
    if type(count) is not int or not 2 <= count <= 12:
        fail('Choose between 2 and 12 slides.')
    palette, font = payload.get('palette', 'Ocean'), payload.get('font', 'Arial')
    if palette not in visual.PALETTES or font not in visual.FONTS:
        fail('Choose a supported palette and font.')
    sources = payload.get('sources', [])
    if not isinstance(sources, list) or len(sources) > 4:
        fail('Attach up to four source documents.')
    evidence, notices, snapshots = [], [], []
    budget = max(1200, min(10000, local_ai.source_budget()))
    for source in sources:
        if not isinstance(source, dict):
            fail('Invalid source reference.')
        key = str(source.get('id', ''))
        path = path_for(user, key)
        if not (path/'source.json').is_file():
            fail('An attached source is unavailable for this account.', 404)
        saved = json.loads((path/'source.json').read_text(encoding='utf-8'))
        snapshots.append({k: saved[k] for k in ('id', 'name', 'sha256', 'notice')})
        for part in re.split(r'\n+|(?<=[.!?])\s+', saved['text']):
            part = part.strip()
            if not part:
                continue
            # Bounded exact excerpts. Original extraction remains available in the source snapshot.
            for chunk in textwrap.wrap(part, width=120, break_long_words=False, break_on_hyphens=False):
                if budget < len(chunk):
                    notices.append('Source text was shortened to fit the local model. Review attached originals; this deck is not an exhaustive summary.')
                    break
                evidence.append({'id': f'S{len(evidence)+1}', 'text': chunk, 'source': saved['name']})
                budget -= len(chunk)+30
            if budget < 120:
                break
    manual = payload.get('mode') == 'manual'
    if manual:
        content = evidence or [{'id': 'P1', 'text': prompt[:120], 'source': 'Your prompt'}]
        outline = [{'title': prompt[:80] if i == 0 else f'Section {i+1}',
                    'bullets': [v['text'] for v in content[i*4:i*4+4]],
                    'source_ids': [v['id'] for v in content[i*4:i*4+4]] if evidence else [],
                    'layout': ('bullets', 'cards', 'timeline')[i % 3]} for i in range(count)]
        notices.append('Manual starter: content is copied from your inputs; no AI inference was used.')
    else:
        instruction = ('Return a compact presentation outline as JSON only. The slides array must have exactly slide_count entries. '
                       'Titles must be short editorial headings of at most six words. layout must be one of bullets, cards, timeline. '
                       'No extra keys, explanations or markdown. ')
        if evidence:
            instruction += ('Use this exact schema: {"slides":[{"title":"Review","layout":"cards","source_ids":["S1"]}]}. '
                            'Select one to four existing evidence IDs for each slide. Do NOT write bullet text or summaries. '
                            'Do NOT add a bullets field. Output only titles, layout names and source_ids.')
        else:
            instruction += ('Use this exact schema: {"slides":[{"title":"Introduction","layout":"bullets",'
                            '"bullets":["A short draft point"],"source_ids":[]}]}. '
                            'Write two or three brief points per slide, at most 90 characters each. '
                            'No invented numbers, people, dates, approvals or project results. These are draft general ideas.')
        try:
            raw = local_ai.llm_json(instruction, {'topic': prompt, 'slide_count': count, 'evidence': evidence})
            if evidence and isinstance(raw, dict) and isinstance(raw.get('slides'), list):
                # Models sometimes write prose despite the selection-only request. None of that
                # prose enters a source-grounded slide; only separately validated source IDs do.
                for row in raw['slides']:
                    if isinstance(row, dict) and (row.get('bullets') or row.get('cards')):
                        notices.append('Model-written body text was discarded. Slide bodies contain the selected source excerpts only; titles remain draft editorial labels.')
                        row['bullets'] = []
                        row.pop('cards',None)
            plan = Plan.model_validate(raw)
        except local_ai.ServiceUnavailable as error:
            fail(str(error), 503)
        except (local_ai.ModelOutputError, ValueError) as error:
            fail('Local model returned an invalid outline. Retry or choose the manual starter.', 422)
        if len(plan.slides) != count:
            fail('The local model did not return the requested number of slides. Retry or use the manual starter.')
        by_id = {v['id']: v for v in evidence}
        outline = []
        for slide in plan.slides:
            item = slide.model_dump()
            cards=item.pop('cards')
            if cards:
                if item['bullets']:fail('The model returned ambiguous card content. Retry the outline.')
                item['bullets']=[card['title']+(': '+card['description'] if card['description'] else '') for card in cards]
            if item['layout'] not in {'bullets', 'cards', 'timeline'}:
                fail('The model selected an unsupported layout. Retry.')
            if evidence:
                if not item['source_ids'] or any(key not in by_id for key in item['source_ids']) or item['bullets']:
                    fail('The model returned unsupported source claims. No presentation was published.')
                item['bullets'] = [by_id[key]['text'] for key in item['source_ids']]
                item['notes'] = '\n'.join(f"[{key}] {by_id[key]['source']}: {by_id[key]['text']}" for key in item['source_ids'])
            elif any(len(text)>120 or not text.strip() for text in item['bullets']) or item['source_ids']:
                fail('The model returned invalid draft paragraphs. Retry.')
            outline.append(item)
    if not evidence:
        notices.append('Prompt-only draft: content is not verified project evidence. Review all factual claims before use.')
    else:
        notices.append('This deck contains selected source excerpts. Review the originals for context and any omitted material.')
    for item in outline:
        if evidence and not item.get('notes'):
            by_id = {v['id']: v for v in evidence}
            item['notes'] = '\n'.join(f"[{key}] {by_id[key]['source']}: {by_id[key]['text']}" for key in item['source_ids'])
    try:deck = visual.layout(prompt[:100], outline, palette, font)
    except (ValueError,TypeError):fail('The generated slide content is invalid. Review the source text or retry the outline.')
    value = {'id': uuid4().hex, 'revision': 1, 'deck': deck, 'sources': snapshots,
             'evidence': evidence, 'notices': list(dict.fromkeys(notices)), 'generation': 'manual' if manual else 'local_llm',
             'warnings': visual.diagnostics(deck)}
    with LOCK,write_lock(user):
        publish(path_for(user, value['id'])/'revisions'/'1', value)
        publish(path_for(user, value['id']), value)
    return value

def upload(user, name, content):
    home(user)
    if len(content) > 20*1024**2:
        fail('Choose a source smaller than 20 MB.', 413)
    name = Path(name.replace('\\', '/')).name[:180]
    if Path(name).suffix.lower() not in {'.pdf', '.docx', '.csv', '.xls', '.xlsx', '.txt'}:
        fail('Attach PDF, DOCX, CSV, XLS, XLSX or TXT.')
    from backend.api.assist_attachments import preview
    result = preview(name, content)
    if not result['readable']:
        fail(result['notice'] or 'No readable text found.')
    key = uuid4().hex
    clean=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',result['text'])
    notice=result['notice']+(' Unsupported text control characters were omitted.' if clean!=result['text'] else '')
    value = {'id': key, 'name': name, 'sha256': hashlib.sha256(content).hexdigest(),
             'text': clean, 'notice': notice}
    path = path_for(user, key)
    path.mkdir(parents=True)
    (path/'source.json').write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    (path/'original').write_bytes(content)
    return {k: value[k] for k in ('id', 'name', 'sha256', 'notice')}

def save(user, key, payload):
    with LOCK,write_lock(user):
        old = load(user, key)
        if type(payload.get('revision')) is not int or payload['revision'] != old['revision']:
            fail('This presentation changed in another window. Reopen it before saving.', 409)
        try:
            deck = visual.validate_deck(payload.get('deck'))
        except (ValueError, TypeError):
            fail('Invalid slide geometry, text, font or colors. Keep elements inside the slide.')
        evidence = {v['id'] for v in old['evidence']}
        if any(set(slide['source_ids'])-evidence for slide in deck['slides']):
            fail('Unknown source reference. Reopen the saved presentation.')
        value = {**old, 'deck': deck, 'revision': old['revision']+1, 'warnings': visual.diagnostics(deck)}
        publish(path_for(user, key)/'revisions'/str(value['revision']), value)
        publish(path_for(user, key), value)
        return value
