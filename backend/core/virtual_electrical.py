"""PDF source inventory and legacy layout compatibility for native circuit reconstruction."""
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math
import os
import threading
import time

from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter, Transformation
from PIL import Image
from python_engine.circuit_compare import extract_pdf

LOCK = threading.RLock()


def write(path, value):
    with LOCK:
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        os.replace(temporary,path)


def read(path):
    # Windows can deny a read while another thread publishes an atomic rename.
    with LOCK:return json.loads(path.read_text(encoding='utf-8'))


def layout(pages, mode='grid'):
    columns=1 if mode=='vertical' else len(pages) if mode=='horizontal' else max(1,math.ceil(math.sqrt(len(pages)*1.3)))
    width=max(p['width'] for p in pages)+60
    height=max(p['height'] for p in pages)+90
    return [{'page':p['number'],'x':round((i%columns)*width,2),'y':round((i//columns)*height+34,2)} for i,p in enumerate(pages)]


def decode(folder, progress=lambda *_:None):
    digest=hashlib.sha256((folder/'source.pdf').read_bytes()).hexdigest()
    decoded=extract_pdf(folder/'source.pdf','drawing',folder,progress)
    pages=[];references=defaultdict(list)
    for p in decoded:
        with Image.open(folder/p['image']) as preview:
            preview.thumbnail((480,480));preview.save(folder/f"thumb-{p['number']}.png")
        pages.append({k:p[k] for k in ('number','width','height','title','image','notices','textWords') }|
                     {'searchText':p['text'][:18000],'coverage':p['scene']['coverage']})
        seen=set()
        for node in p['scene']['components']+p['scene']['terminals']:
            key=(node['reference'],tuple(node['bbox']))
            if key in seen:continue
            seen.add(key)
            references[node['reference']].append({'page':p['number'],'bbox':node['bbox'],'kind':node['kind'],'id':node['id']})
    data={'pages':pages,'references':[{'reference':k,'occurrences':v[:300]} for k,v in sorted(references.items())],
          'sourceSha256':digest,'pageCount':len(pages),'netlistVerified':False,
          'meaning':'All source sheets share one artboard. Repeated references link printed labels; they do not establish electrical continuity.'}
    write(folder/'drawing.json',data)
    write(folder/'layout.json',{'version':1,'mode':'grid','positions':layout(pages),'updated':time.time()})
    from .electrical_native import build
    progress('Redrawing native circuit objects',len(pages),len(pages))
    build(folder)
    if hashlib.sha256((folder/'source.pdf').read_bytes()).hexdigest()!=digest:raise ValueError('Source drawing changed during extraction.')
    return data


def update_layout(folder,payload):
    with LOCK:
        original=json.loads((folder/'layout.json').read_text(encoding='utf-8'))
        if type(payload.get('version'))is not int or payload['version']!=original['version']:raise HTTPException(409,'Layout changed in another window. Reopen before saving.')
        data=json.loads((folder/'drawing.json').read_text(encoding='utf-8'));pages=data['pages']
        mode=payload.get('mode','custom')
        if mode in {'grid','horizontal','vertical'}:positions=layout(pages,mode)
        elif mode=='custom':
            positions=payload.get('positions')
            if not isinstance(positions,list) or len(positions)!=len(pages):raise HTTPException(400,'Keep exactly one position for every sheet.')
            expected={p['number'] for p in pages};seen=set();clean=[]
            for p in positions:
                if not isinstance(p,dict) or type(p.get('page'))is not int or p['page'] not in expected or p['page'] in seen:raise HTTPException(400,'Keep each source sheet once on the canvas.')
                if any(type(p.get(k))not in (int,float) or not math.isfinite(p[k]) or abs(p[k])>100000 for k in ('x','y')):raise HTTPException(400,'Keep sheet positions within the workspace.')
                seen.add(p['page']);clean.append({k:p[k] for k in ('page','x','y')})
            positions=clean
        else:raise HTTPException(400,'Choose Grid, Horizontal, Vertical or a custom layout.')
        result={'version':original['version']+1,'mode':mode,'positions':positions,'updated':time.time()}
        write(folder/'layout.json',result)
        return result


def export_pdf(folder, output):
    """Compose every original PDF page on one sheet, with the saved relative positions."""
    with LOCK:
        data=json.loads((folder/'drawing.json').read_text(encoding='utf-8'))
        positions={p['page']:p for p in json.loads((folder/'layout.json').read_text(encoding='utf-8'))['positions']}
    left=min(p['x'] for p in positions.values());top=min(p['y'] for p in positions.values())
    right=max(positions[p['number']]['x']+p['width'] for p in data['pages']);bottom=max(positions[p['number']]['y']+p['height'] for p in data['pages'])
    width,height=right-left+40,bottom-top+40;scale=min(1,14000/max(width,height))
    source=PdfWriter(clone_from=folder/'source.pdf');writer=PdfWriter();canvas=writer.add_blank_page(width*scale,height*scale)
    for info in data['pages']:
        page=source.pages[info['number']-1];page.transfer_rotation_to_content()
        pos=positions[info['number']]
        # Account for the source crop origin, including rotated PDF pages.
        crop=page.cropbox;px=(pos['x']-left+20)*scale;py=(bottom-pos['y']-info['height']+20)*scale
        transform=Transformation().translate(-float(crop.left),-float(crop.bottom)).scale(scale).translate(px,py)
        canvas.merge_transformed_page(page,transform,over=True,expand=False)
    writer.add_metadata({'/Title':'Unified electrical drawing workspace','/Subject':'Source sheets arranged on one artboard; electrical continuity is not certified.'})
    with output.open('wb') as stream:writer.write(stream)
