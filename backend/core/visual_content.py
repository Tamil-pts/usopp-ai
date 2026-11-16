"""Shared visual tokens and bounded, editable slide geometry. No remote assets."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

import json
from backend.core.runtime import RESOURCE_ROOT
TOKENS = json.loads((RESOURCE_ROOT/'knowledge/master/visual_tokens.json').read_text(encoding='utf-8'))
FONTS = TOKENS['fonts']
PALETTES = TOKENS['palettes']
COLOR = r'^#[0-9a-fA-F]{6}$'

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Element(Strict):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,60}$')
    kind: Literal['text', 'box'] = 'text'
    text: str = Field(default='', max_length=1200)
    x: float = Field(ge=0, le=1260)
    y: float = Field(ge=0, le=700)
    w: float = Field(ge=20, le=1280)
    h: float = Field(ge=20, le=720)
    size: int = Field(default=28, ge=12, le=72)
    color: str = Field(default='#17344b', pattern=COLOR)
    fill: str = Field(default='#ffffff', pattern=COLOR)
    bold: bool = False

class Slide(Strict):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,60}$')
    title: str = Field(max_length=160)
    background: str = Field(default='#ffffff', pattern=COLOR)
    elements: list[Element] = Field(min_length=1, max_length=40)
    notes: str = Field(default='', max_length=12000)
    source_ids: list[str] = Field(default_factory=list, max_length=20)

class Deck(Strict):
    title: str = Field(min_length=1, max_length=160)
    font: str = 'Arial'
    palette: str = 'Ocean'
    slides: list[Slide] = Field(min_length=1, max_length=20)

def validate_deck(data):
    deck = Deck.model_validate(data)
    if deck.font not in FONTS or deck.palette not in PALETTES:
        raise ValueError('Choose a supported font and palette.')
    if any(ord(c)<32 for c in deck.title):
        raise ValueError('Presentation title contains unsupported control characters.')
    if len({s.id for s in deck.slides}) != len(deck.slides):
        raise ValueError('Slide identities must be unique.')
    for slide in deck.slides:
        if len({e.id for e in slide.elements}) != len(slide.elements):
            raise ValueError('Element identities must be unique within a slide.')
        for e in slide.elements:
            if e.x + e.w > 1280.01 or e.y + e.h > 720.01:
                raise ValueError('Move or resize elements to stay inside the slide.')
        if any(ord(c)<32 and c not in '\r\n\t' for c in slide.notes+slide.title+''.join(e.text for e in slide.elements)):
            raise ValueError('Text contains unsupported control characters.')
    return deck.model_dump()

def layout(title, outline, palette='Ocean', font='Arial'):
    colors = PALETTES[palette]
    slides = []
    for i, item in enumerate(outline):
        elements = [dict(id='heading', text=item['title'], x=64, y=64, w=1152, h=110,
                         size=44 if len(item['title'])<=42 else 36, color='#17344b', bold=True)]
        elements[0]['h']=124
        bullets = item.get('bullets', [])
        # Each paragraph has its own editable object. Cards and timelines use varied layouts.
        mode = item.get('layout', 'bullets')
        for j, text in enumerate(bullets):
            if mode == 'cards':
                x, y, w, h = 64+(j % 2)*584, 205+(j//2)*176, 560, 152
            elif mode == 'timeline':
                x, y, w, h = 64+j*292, 245, 268, 270
            else:
                x, y, w, h = 64, 205+j*91, 1152, 82
            elements.append(dict(id=f'point-{j}', kind='box', text=text, x=x, y=y, w=w,
                                 h=h, size=24 if mode!='bullets' else 27,
                                 fill=colors[j % len(colors)], color='#17344b'))
        elements.append(dict(id='footer', text=f'{i+1:02d} / {len(outline):02d}  |  Review draft',
                             x=64, y=650, w=1100, h=38, size=14, color='#526575'))
        slides.append(dict(id=f'slide-{i+1}', title=item['title'], elements=elements,
                           notes=item.get('notes', ''), source_ids=item.get('source_ids', []),
                           background='#f8fafc' if i % 2 else '#ffffff'))
    return validate_deck(dict(title=title, palette=palette, font=font, slides=slides))

def diagnostics(deck):
    """Conservative warnings; font metrics/render review is still necessary."""
    import math
    result = []
    def luminance(color):
        values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))
    for i, slide in enumerate(deck['slides']):
        elements = slide['elements']
        for e in elements:
            capacity = max(1, int((e['w']-24)/(e['size']*.57)))
            lines = sum(max(1, math.ceil(len(line)/capacity)) for line in e['text'].split('\n'))
            if lines*e['size']*1.25 > e['h']-12:
                result.append(f"Slide {i+1}: '{e['id']}' may overflow. Shorten text or enlarge the object.")
            a,b=sorted((luminance(e['color']),luminance(e['fill'] if e['kind']=='box' else slide['background'])))
            if (b+.05)/(a+.05)<3:
                result.append(f"Slide {i+1}: '{e['id']}' has low text contrast. Choose a darker text or lighter fill.")
        for j, a in enumerate(elements):
            for b in elements[j+1:]:
                if min(a['x']+a['w'], b['x']+b['w']) > max(a['x'], b['x'])+2 and min(a['y']+a['h'], b['y']+b['h']) > max(a['y'], b['y'])+2:
                    result.append(f"Slide {i+1}: '{a['id']}' overlaps '{b['id']}'.")
    return result
