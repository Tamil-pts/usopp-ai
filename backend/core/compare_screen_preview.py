"""Portable static HMI previews for comparison reports (no live PLC simulation)."""
from io import BytesIO
from pathlib import Path
import re
from functools import lru_cache
from contextvars import ContextVar
import hashlib
import json
import os
import tempfile
import base64

preview_cache = ContextVar('compare_preview_cache', default=None)
preview_progress = ContextVar('compare_preview_progress', default=None)


@lru_cache(maxsize=128)
def _font(path, size):
    from PIL import ImageFont
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def preview_png(layout):
    if not layout or not layout.get('layers'):
        return None
    from PIL import Image, ImageDraw, ImageFont
    width=max(1,int(layout.get('width') or 640)); height=max(1,int(layout.get('height') or 480))
    scale=min(2,2400/max(width,height))
    palette=layout.get('palette') or {}
    def color(value,fallback):
        value=str(palette.get(str(value),value) or '')
        return value if re.fullmatch(r'#[0-9a-fA-F]{6}',value) else fallback
    image=Image.new('RGB',(max(1,int(width*scale)),max(1,int(height*scale))),color((layout.get('properties') or {}).get('BackColor'),'#f5f8fb'))
    def bitmap(states):
        variants = ((states or {}).get('released') or {}).get('variants') or []
        candidates = [item for item in variants if item.get('level', 0) == 0]
        variant = next((item for item in candidates if item.get('language') == 'en'), None)
        variant = variant or next((item for item in candidates if item.get('language') == 'neutral'), None) or next(iter(candidates), None)
        return variant, (layout.get('bitmap_assets') or {}).get((variant or {}).get('asset_id'))
    def paste_bitmap(panel, asset):
        if not asset or not str(asset.get('data_uri', '')).startswith('data:image/png;base64,'):
            return False
        try:
            with Image.open(BytesIO(base64.b64decode(asset['data_uri'].split(',', 1)[1]))) as source:
                if source.width * source.height > 8_000_000:
                    return False
                resized = source.convert('RGBA').resize(panel.size, Image.Resampling.LANCZOS)
                panel.paste(resized, (0, 0), resized)
            return True
        except (OSError, ValueError, Image.DecompressionBombError):
            return False
    background, background_asset = bitmap(layout.get('bitmaps'))
    if not paste_bitmap(image, background_asset) and background:
        ImageDraw.Draw(image).text((8, 8), 'Bitmap unavailable: ' + str(background.get('file') or background.get('name') or background.get('reference') or ''), fill='#975719')
    font_path=next((str(p) for p in [Path('C:/Windows/Fonts/arial.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.exists()),None)
    for layer in layout['layers']:
        if layer.get('hidden'): continue
        for control in layer.get('controls') or []:
            props=control.get('effective_properties') or control.get('properties') or {}
            x=int((float(layer.get('left') or 0)+float(control.get('left') or 0))*scale)
            y=int((float(layer.get('top') or 0)+float(control.get('top') or 0))*scale)
            w=max(1,int(float(control.get('width') or 1)*scale)); h=max(1,int(float(control.get('height') or 1)*scale))
            if x>=image.width or y>=image.height or x+w<0 or y+h<0: continue
            w=min(w,4800);h=min(h,4800)
            transparent=control.get('class') in {'HotSpot','TouchPadGrid'} or props.get('FillStyle')=='Transparent' or (control.get('class')=='Text' and not props.get('BackColor'))
            panel=Image.new('RGBA',(w,h),(0,0,0,0) if transparent else color(props.get('BackColor'),'#edf3f7'))
            variant, asset = bitmap(control.get('bitmaps'))
            rendered_bitmap = paste_bitmap(panel, asset)
            draw=ImageDraw.Draw(panel)
            border={'added':'#16975f','removed':'#d34b55','modified':'#d18b16'}.get(control.get('status'),'#7b8b9b')
            if control.get('class') != 'TouchPadGrid' or control.get('status') in {'added','removed','modified'}:
                draw.rectangle((0,0,w-1,h-1),outline=border,width=max(1,int(scale*2)))
            texts=control.get('texts') or {}
            bound=control.get('class') in {'Numeric','String','TouchPadEdit'}
            label=(control.get('datapoint') or props.get('SimulationValue') or '') if bound else texts.get('en') or next(iter(texts.values()),'')
            if variant and not rendered_bitmap: label=variant.get('file') or variant.get('name') or variant.get('reference') or '[Bitmap unavailable]'
            configured=(control.get('fonts') or {}).get('en') or {}
            try: size=float(configured.get('Size') or 0)*4/3
            except (TypeError,ValueError): size=0
            size=size or (9 if width<=320 else 12)
            if bound and label: size=min(size,max(4,(w/scale-4)/max(1,len(str(label))*.55)))
            font=_font(font_path,max(4,min(150,int(size*scale))))
            lines=[]
            for line in str(label).splitlines():
                if bound or props.get('Multiline')=='Disable': lines.append(line);continue
                current=''
                for word in line.split(' '):
                    candidate=(current+' '+word).strip()
                    if current and draw.textlength(candidate,font=font)>w-8: lines.append(current);current=word
                    else: current=candidate
                lines.append(current)
            y_text=3
            if control.get('class') == 'TouchPadEdit':
                y_text=max(0,(h-max(6,int(size*scale*1.2))*len(lines))/2)
            for line in lines:
                length=draw.textlength(line,font=font)
                centered=props.get('AlignmentHorizontal')=='Center' or (not props.get('AlignmentHorizontal') and control.get('class')=='TouchPadEdit')
                x_text=(w-length)/2 if centered else w-length-4 if props.get('AlignmentHorizontal')=='Right' else 4
                draw.text((max(2,x_text),y_text),line,font=font,fill=color(props.get('ForeColor'),'#182738'))
                y_text+=max(6,int(size*scale*1.2))
            image.paste(panel,(x,y),panel)
    stream=BytesIO();image.save(stream,format='PNG');return stream.getvalue()


def screen_previews(diff):
    layouts=(diff.get('parsed_screen') or {}).get('layouts') or {}
    result = {}
    for side,key in [('base','base'),('developed','new')]:
        layout = layouts.get(key)
        if not layout or not layout.get('layers'):
            result[side] = None
            continue
        directory = preview_cache.get()
        path = None
        if directory:
            # Captions, dimensions, colors and filtered change states all affect
            # the image. Cover edits can safely reuse the same rendered screen.
            digest = hashlib.sha256(json.dumps(['preview-v3',layout],sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
            path = Path(directory) / (digest + '.png')
            if path.is_file():
                result[side] = path.read_bytes()
                continue
        callback = preview_progress.get()
        if callback: callback(f"Rendering {side} screen preview: {diff.get('file_name') or diff.get('path','HMI')}")
        data = preview_png(layout)
        if path and data:
            path.parent.mkdir(parents=True,exist_ok=True)
            descriptor,temporary = tempfile.mkstemp(dir=path.parent,suffix='.tmp')
            try:
                with os.fdopen(descriptor,'wb') as stream: stream.write(data)
                os.replace(temporary,path)
            finally:
                if Path(temporary).exists(): Path(temporary).unlink()
        result[side] = data
    return result
