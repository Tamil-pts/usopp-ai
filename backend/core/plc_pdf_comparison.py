"""Printed PLC block/network comparison. Source evidence, never inferred execution."""
from __future__ import annotations

import io
import re
from collections import Counter, OrderedDict
from bisect import bisect_left
from difflib import SequenceMatcher
from itertools import zip_longest

from fastapi import HTTPException

from backend.core import document_pdf_comparison as pdf
from backend.core import plc_comparison_evidence as evidence
from backend.core import plc_ladder_structure as ladder
from backend.core import plc_pdf_engineering as engineering

RUNNING = re.compile(r'^.+?\s+/\s+(.+?)(?:\s+\(((?:OB|SBR|FB|FC|DB|INT)\s*\d+)\))?\s*$', re.I)
NETWORK = re.compile(r'^Network\s+(\d+)\b(.*)$', re.I)


def extract(path, ignore_page_numbers=True, options=None):
    import pdfplumber
    options = options or {}
    blocks, pages, ignored, notices = [], [], [], []
    current, active = None, None
    characters = 0
    network_count = 0
    with pdfplumber.open(path) as document:
        if len(document.pages) > evidence.MAX_PAGES:
            raise HTTPException(422, 'PLC PDF comparison supports up to 2,000 pages per file.')
        for number, original in enumerate(document.pages, 1):
            bounds = original.bbox
            if original.cropbox:
                bounds = (max(bounds[0], original.cropbox[0]), max(bounds[1], original.cropbox[1]),
                          min(bounds[2], original.cropbox[2]), min(bounds[3], original.cropbox[3]))
            page = original.crop(bounds) if tuple(bounds) != tuple(original.bbox) else original
            width, height = page.width, page.height
            pages.append(dict(number=number, width=width, height=height))
            lines = page.extract_text_lines(return_chars=True)
            for line in lines:
                line['bbox'] = [line['x0']-bounds[0], line['top']-bounds[1], line['x1']-bounds[0], line['bottom']-bounds[1]]
            header = next((line for line in lines if RUNNING.fullmatch(line['text'].strip()) and line['bbox'][1] < height*.12), None)
            title = next((line for line in lines if re.match(r'^Block\s*:', line['text'], re.I)), None)
            match = RUNNING.fullmatch(header['text'].strip()) if header else None
            name = match[1].strip() if match else re.sub(r'^Block\s*:\s*', '', title['text'], flags=re.I).strip() if title else None
            address = (match[2] or '').upper().replace(' ', '') if match else ''
            identity = name.casefold() if name else None
            if identity and (current is None or current['key'] != identity or title or
                             address and current['address'] and address != current['address']):
                current = dict(key=identity, name=name, address=address, networks=[], metadata=None)
                if title and match and re.sub(r'^Block\s*:\s*','',title['text'],flags=re.I).strip().casefold()!=identity:
                    current['ambiguous']=True
                    notices.append(f'Page {number}: running block heading and Block label disagree; review the block identity.')
                blocks.append(current); active = None
            if not current or not identity:
                # No inherited block assignment across an unrecognised/scanned page.
                notices.append(f'Page {number}: no explicit block heading; content is unresolved.')
                blocks.append(dict(key=f'__unresolved_{number}', name=f'Unidentified page {number}', address='',
                                   networks=[], metadata=dict(number=None, title='', text='[Block heading unavailable]',
                                                             segments=[dict(page=number, bbox=[0,0,width,height])], unknown=True)))
                current, active = None, None
                original.close(); continue
            counters = [line for line in lines if pdf.page_counter(line['text'], line['bbox'], width, height, number, len(document.pages))]
            if ignore_page_numbers:
                ignored.extend(dict(page=number, text=line['text']) for line in counters)
            bottom = min((line['bbox'][1]-4 for line in counters if line['bbox'][1] > height*.9), default=height-8)
            top = header['bbox'][3]+4 if header else 8
            body = [line for line in lines if line is not header and line not in counters and line['bbox'][1] >= top and line['bbox'][3] <= bottom]
            # Positively identified print metadata and green comment glyphs only.
            masks=[]
            retained=[]
            for line in body:
                field=next((key for key,pattern in [('author',r'^Author\s*:'),('created',r'^Created\s*:'),('modified',r'^(?:Last\s+)?Modified\s*:')] if re.match(pattern,line['text'],re.I)),None)
                if field and not options.get('compare_'+field,True):
                    # Cover glyph antialiasing and small rasterization offsets too.
                    # The same padded mask is applied to both sides before pixel
                    # comparison and when a cached preview/export is rendered.
                    x0,y0,x1,y1=line['bbox']
                    masks.append([max(0,x0-3),max(0,y0-3),min(width,x1+3),min(height,y1+3)])
                    ignored.append(dict(page=number,text=line['text'],kind=field));continue
                if not options.get('compare_comments',True):
                    chars=line.get('chars',[])
                    def is_comment(char):
                        color=char.get('non_stroking_color')
                        return isinstance(color,(tuple,list)) and len(color)==3 and color[1]>.25 and color[1]>color[0]*1.5 and color[1]>color[2]*1.5
                    removed=[char for char in chars if is_comment(char)]
                    if removed:
                        masks.extend([char['x0']-bounds[0],char['top']-bounds[1],char['x1']-bounds[0],char['bottom']-bounds[1]] for char in removed)
                        ignored.append(dict(page=number,text=''.join(c['text'] for c in removed),kind='comment'))
                        # PDF spaces are often geometric gaps, not character objects.
                        # Preserve those gaps so "Network 3" never becomes "Network3".
                        remaining=[c for c in chars if not is_comment(c)]
                        compact=[c for c in chars if not c['text'].isspace()]
                        if ''.join(c['text'] for c in compact)==re.sub(r'\s','',line['text']):
                            glyphs=iter(compact)
                            kept=''.join(char for char in line['text'] if char.isspace() or not is_comment(next(glyphs)))
                        else:
                            kept=pdfplumber.utils.extract_text(remaining,x_tolerance_ratio=.1) or ''
                        line={**line,'text':kept.strip()}
                        if not line['text']:continue
                retained.append(line)
            body=retained
            headings = [(line, NETWORK.fullmatch(line['text'].strip())) for line in body]
            headings = [(line, match) for line, match in headings if match]
            def append_region(unit, start, end, excluded=None):
                nonlocal characters
                if end <= start: return
                # Full width preserves parallel branches and wiring with no nearby text.
                unit['segments'].append(dict(page=number, bbox=[0, start, width, end], masks=[box for box in masks if box[1]<end and box[3]>start]))
                region=[line for line in body if line is not excluded and start <= line['bbox'][1] < end]
                drawing_end=end
                drawing_lines=region
                references=next((line for line in region if re.fullmatch(r'(?:Symbol|Address|Comment)(?:\s+(?:Symbol|Address|Comment)){2}',line['text'].strip(),re.I) and all(re.search(r'\b'+word+r'\b',line['text'],re.I) for word in ('Symbol','Address','Comment'))),None)
                if references and unit.get('number') is not None:
                    table_start=references['bbox'][1]-2
                    table=[line for line in region if line['bbox'][1]>=table_start]
                    unit.setdefault('references',[]).append(dict(page=number,text='\n'.join(line['text'] for line in table)))
                    unit.setdefault('symbol_references',[]).extend(engineering.symbol_references(references,table[1:],number))
                    drawing_end=max(start,table_start)
                    drawing_lines=[line for line in region if line['bbox'][1]<table_start]
                    if not options.get('compare_references',True):
                        unit['segments'][-1]['bbox'][3]=drawing_end
                        region=drawing_lines
                unit.setdefault('source_evidence', []).append(evidence.fingerprint(page, unit['segments'][-1]['bbox'], region, masks))
                if unit.get('number') is not None:
                    drawing_box=[0,start,width,drawing_end]
                    try:part=ladder.recognize(page,drawing_box,drawing_lines,masks)
                    except (KeyError,TypeError,ValueError,OverflowError):
                        part=dict(complete=False,symbols=[],nets=[],open_checks=['Unsupported structural drawing format; source/raster comparison retained.'])
                    if part.get('empty') and not region and unit.get('ladder_parts'):
                        unit['segments'].pop()
                        unit['source_evidence'].pop()
                        return
                    part.update(page=number,bbox=drawing_box)
                    unit.setdefault('ladder_parts',[]).append(part)
                    unit['drawing_text']=unit.get('drawing_text',[])+[line['text'] for line in drawing_lines]
                content = [line['text'] for line in region]
                text = '\n'.join(content)
                if not content and page.images:unit['unknown']=True
                characters += len(text)
                unit['text'] += ('\n' if unit['text'] and text else '') + text
                if characters > 20000000:
                    raise HTTPException(422, 'PLC PDF text exceeds twenty million characters. Split the document.')
            first = headings[0][0]['bbox'][1] if headings else bottom
            if title:
                active = dict(number=None, title='Block information', text='', segments=[])
                current['metadata'] = active
            if active:
                append_region(active, top, first-2)
            elif first > top+8 and any(line['bbox'][1] < first-2 for line in body):
                notices.append(f'Page {number}: content before the first network needs review.')
                unknown=dict(number=None,title='Unassigned content',text='',segments=[],unknown=True)
                append_region(unknown,top,first-2)
                current.setdefault('unassigned',[]).append(unknown)
            for index, (line, match) in enumerate(headings):
                active = dict(number=int(match[1]), title=match[2].strip(), text='', segments=[])
                current['networks'].append(active)
                network_count += 1
                end = headings[index+1][0]['bbox'][1]-2 if index+1 < len(headings) else bottom
                append_region(active, line['bbox'][3]+2, end)
            # A page counter is kept as separate evidence when explicitly requested.
            if not ignore_page_numbers and counters:
                current.setdefault('counters', []).extend(dict(number=None, title='Printed page counter', text=line['text'],
                    segments=[dict(page=number,bbox=line['bbox'])]) for line in counters)
            if network_count > 50000:
                raise HTTPException(422, 'PLC PDF comparison supports up to 50,000 networks per file.')
            original.close()
    if not any(block['networks'] for block in blocks):
        raise HTTPException(422, 'No explicit PLC blocks and Network headings were found. Use a searchable PLC program PDF; scanned or other layouts need OCR/format review.')
    for block in blocks:
        if block['metadata'] and block['address']:
            block['metadata']['text']='Printed block reference: '+block['address']+'\n'+block['metadata']['text']
    return blocks, pages, ignored, notices


class Renderer:
    """Bounded page cache. Only cropped network evidence is retained in results."""
    def __init__(self, path, pages): self.path, self.pages, self.cache, self.document = path, pages, OrderedDict(), None
    def close(self):
        for image in self.cache.values(): image.close()
        self.cache.clear()
        if self.document is not None:
            with pdf.RENDER_LOCK:self.document.close()
            self.document=None
    def page(self, number):
        if number not in self.cache:
            # Keep the PDF document open for this bounded renderer; avoid PNG
            # encoding/decoding and font reinitialisation for every source page.
            import pypdfium2 as pdfium
            with pdf.RENDER_LOCK:
                if self.document is None:self.document=pdfium.PdfDocument(str(self.path))
                page=self.document[number-1]
                try:
                    w,h=page.get_size();bitmap=page.render(scale=min(1000/w,(4000000/(w*h))**.5,3))
                    try:self.cache[number]=bitmap.to_pil().convert('RGB')
                    finally:bitmap.close()
                finally:page.close()
            if len(self.cache) > 3: self.cache.popitem(last=False)[1].close()
        self.cache.move_to_end(number)
        return self.cache[number]
    def network(self, unit, highlights=()):
        from PIL import Image, ImageChops
        chunks = []
        try:
            for segment in unit['segments']:
                image = self.page(segment['page']); meta = self.pages[segment['page']-1]; box = segment['bbox']
                boxes=[box for page,box in highlights if page==segment['page']]
                if segment.get('masks') or boxes:
                    from PIL import ImageDraw
                    image=image.copy();draw=ImageDraw.Draw(image)
                    for mask in segment.get('masks',[]):
                        draw.rectangle((int(mask[0]*image.width/meta['width'])-1,int(mask[1]*image.height/meta['height'])-1,
                            int(mask[2]*image.width/meta['width'])+1,int(mask[3]*image.height/meta['height'])+1),fill='white')
                    mark=ImageDraw.Draw(image,'RGBA')
                    for x0,y0,x1,y1 in boxes:
                        mark.rectangle((int(x0*image.width/meta['width'])-2,int(y0*image.height/meta['height'])-2,
                            int(x1*image.width/meta['width'])+2,int(y1*image.height/meta['height'])+2),fill=(245,181,35,75))
                crop = image.crop((round(box[0]*image.width/meta['width']), round(box[1]*image.height/meta['height']),
                                   round(box[2]*image.width/meta['width']), round(box[3]*image.height/meta['height'])))
                if segment.get('masks') or boxes:image.close()
                ink = ImageChops.difference(crop.convert('L'), Image.new('L', crop.size, 255)).point(lambda value:255 if value>70 else 0)
                bounds = ink.getbbox(); ink.close()
                if bounds:
                    trimmed = crop.crop((0,max(0,bounds[1]-3),crop.width,min(crop.height,bounds[3]+3)))
                    if sum(chunk.width*chunk.height for chunk in chunks)+trimmed.width*trimmed.height>12000000:
                        trimmed.close();crop.close()
                        raise HTTPException(422, 'A network exceeds the 12 megapixel review limit. Split this PDF network into a smaller document.')
                    chunks.append(trimmed)
                crop.close()
            width, height = max((chunk.width for chunk in chunks),default=1), sum(chunk.height for chunk in chunks) or 1
            if width*height > 12000000:
                raise HTTPException(422, 'A network exceeds the 12 megapixel review limit. Split this PDF network into a smaller document.')
            merged = Image.new('RGB',(width,height),'white'); y=0
            for chunk in chunks: merged.paste(chunk,(0,y)); y+=chunk.height
            ink = ImageChops.difference(merged.convert('L'), Image.new('L',merged.size,255)).point(lambda value:255 if value>70 else 0)
            bounds=ink.getbbox(); ink.close()
            top,bottom=0,height
            if bounds and unit.get('number') is not None:
                # A printed left power rail can extend through blank space or a symbol
                # table. Fit to the connected drawing, not that decorative extension.
                import numpy as np
                pixels=np.asarray(merged.convert('L'))<180
                rail=any(pixels[:,x].sum()>height*.75 for x in range(bounds[0],min(width,bounds[0]+5)))
                if rail:
                    pixels[:,:min(width,bounds[0]+7)]=False
                    occupied=np.flatnonzero(pixels.any(axis=1))
                    if len(occupied):top=max(0,int(occupied[0])-8);bottom=min(height,int(occupied[-1])+9)
            result=merged.crop((max(0,bounds[0]-3),top,min(width,bounds[2]+3),bottom)) if bounds else merged.copy()
            merged.close(); return result
        finally:
            for chunk in chunks: chunk.close()


def registered_pixels(a, b):
    """Rigid network registration only: never warp branches or individual operands."""
    import numpy as np
    from PIL import Image, ImageChops, ImageFilter
    if a.size==b.size and a.tobytes()==b.tobytes():
        return [a.copy(),b.copy()],[Image.new('L',a.size),Image.new('L',a.size)],[(0,0),(0,0)],dict(x=0,y=0,confidence=1.0)
    scale=min(1., 1024/max(a.size+b.size))
    arrays=[]
    for image in (a,b):
        small=image.convert('L').resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))))
        arrays.append(np.asarray(small)<180)
        small.close()
    aa,bb=arrays
    shape=[1 << (int(n)-1).bit_length() for n in np.add(aa.shape,bb.shape)-1]
    correlation=np.fft.irfft2(np.fft.rfft2(aa,s=shape)*np.conj(np.fft.rfft2(bb,s=shape)),s=shape)
    y,x=np.unravel_index(correlation.argmax(),correlation.shape)
    y=int(y if y<=shape[0]//2 else y-shape[0]);x=int(x if x<=shape[1]//2 else x-shape[1])
    # A strong common-ink anchor is required; unrelated networks stay unregistered.
    confidence=float(correlation.max())/max(1,min(int(aa.sum()),int(bb.sum())))
    dx,dy=(round(x/scale),round(y/scale)) if confidence>=.55 else (0,0)
    offsets=[(max(0,-dx),max(0,-dy)),(max(0,dx),max(0,dy))]
    size=(max(a.width+offsets[0][0],b.width+offsets[1][0]),max(a.height+offsets[0][1],b.height+offsets[1][1]))
    images=[];ink=[]
    for original,offset in zip((a,b),offsets):
        canvas=Image.new('RGB',size,'white');canvas.paste(original,offset);images.append(canvas)
        ink.append(canvas.convert('L').point(lambda v:255 if v<180 else 0))
    masks=[]
    for own,other in ((ink[0],ink[1]),(ink[1],ink[0])):
        nearby=other.filter(ImageFilter.MaxFilter(3))
        masks.append(ImageChops.subtract(own,nearby));nearby.close()
    for item in ink:item.close()
    return images,masks,offsets,dict(x=dx,y=dy,confidence=round(confidence,4))


def pixel_diff(a, b, aligned=False):
    from PIL import Image, ImageChops
    images,masks,offsets,registration=registered_pixels(a,b)
    union=ImageChops.lighter(*masks)
    changed=union.histogram()[255]
    overlay=images[1].copy();tint=Image.new('RGB',overlay.size,'#e44d61');overlay.paste(tint,(0,0),union);tint.close()
    box=(*offsets[1],offsets[1][0]+b.width,offsets[1][1]+b.height)
    result=overlay.copy() if aligned else overlay.crop(box);overlay.close()
    total=union.width*union.height
    for item in images+masks+[union]:item.close()
    return dict(changed_pixels=changed,total_pixels=total,difference_ratio=round(changed/max(1,total),8),threshold=180,registration=registration,tolerance_pixels=1),result


def aligned_networks(a, b):
    """Use unique content anchors and network IDs inside the intervening spans."""
    keys=[list(map(engineering.network_key,units)) for units in (a,b)]
    counts=[Counter(side) for side in keys]
    indexes={key:i for i,key in enumerate(keys[1]) if key and counts[1][key]==1}
    candidates=[(i,indexes[key]) for i,key in enumerate(keys[0]) if counts[0][key]==1 and key in indexes]
    # Longest increasing subsequence keeps stable source-order anchors, even
    # when some signatures repeat hundreds of times or a network is relocated.
    tails,tail_indices,previous=[],[],[]
    for index,(_,right) in enumerate(candidates):
        slot=bisect_left(tails,right)
        previous.append(tail_indices[slot-1] if slot else -1)
        if slot==len(tails):
            tails.append(right)
            tail_indices.append(index)
        else:
            tails[slot]=right
            tail_indices[slot]=index
    anchors=[]
    index=tail_indices[-1] if tail_indices else -1
    while index!=-1:
        anchors.append(candidates[index])
        index=previous[index]
    ordered=set(anchors)
    moved={}
    for i,k in candidates:
        if (i,k) not in ordered and (evidence.exact_match(a[i],b[k]) or ladder.compare(a[i],b[k])['same']):
            moved[i]=k
    moved_targets=set(moved.values())
    i=k=0
    for j,l in [*reversed(anchors),(len(a),len(b))]:
        unmatched_b=[b[index] for index in range(k,l) if index not in moved_targets]
        right_numbers=Counter(unit['number'] for unit in unmatched_b)
        lookup={unit['number']:unit for unit in unmatched_b if right_numbers[unit['number']]==1}
        for index in range(i,j):
            left=a[index]
            yield left,b[moved[index]] if index in moved else lookup.pop(left['number'],None)
        for right in unmatched_b:
            if right_numbers[right['number']]!=1 or right['number'] in lookup:yield None,right
        if j<len(a):
            yield a[j],b[l]
        i,k=j+1,l+1


def compare(files, options, cache_dir=None):
    cached=[engineering.cached_extract(path,options,extract,cache_dir) for path in files]
    extracted=[item[0] for item in cached]
    blocks=[item[0] for item in extracted];rows=[]
    renderers=[Renderer(path,item[1]) for path,item in zip(files,extracted)]
    pixels=options.get('pixel_compare',True)
    block_counts=[Counter(block['key'] for block in side) for side in blocks]
    blocks_info=[]
    def add(left,right,block_name,ambiguous=False):
        if not left and not right:return
        text_equal=bool(left and right and (left['text'],left['title'])==(right['text'],right['title']))
        state='unresolved' if ambiguous or any(unit and unit.get('unknown') for unit in (left,right)) else 'added' if left is None else 'removed' if right is None else 'unchanged' if text_equal else 'modified'
        structure=ladder.compare(left or {},right or {}) if pixels and not ambiguous else ladder.compare({}, {})
        visual=None
        if (pixels and left and right and state!='unresolved' and not structure['same']
                and not (text_equal and evidence.exact_match(left,right))):
            a,b=renderers[0].network(left),renderers[1].network(right)
            try:
                visual,overlay=pixel_diff(a,b);overlay.close()
                if visual['changed_pixels']:state='modified'
            finally:a.close();b.close()
        assessment=None
        if left and right and state!='unresolved':
            assessment=evidence.judge(left,right,text_equal,visual)
            assessment=engineering.decision(structure,assessment,left,right,options)
            state=assessment['status']
            if left['number'] is not None and left['number']!=right['number']:
                assessment['reason']+=f" Printed network number changed from {left['number']} to {right['number']}."
        row=dict(structure=structure,assessment=assessment,id=len(rows)+1,status=state,block=block_name,unit='network' if (left or right)['number'] is not None else 'block',
                 text_changed=not text_equal,pixels=visual)
        for side,unit in zip(('base','compared'),(left,right)):
            row[side]=unit['text'] if unit else ''
            if unit and unit['number'] is not None and unit['title']:
                row[side]='Network title: '+unit['title']+'\n'+row[side]
            row[side+'_network']=unit['number'] if unit else None
            row[side+'_title']=unit['title'] if unit else ''
            segments=unit['segments'] if unit else []
            row[side+'_segments']=segments
            row[side+'_references']=unit.get('references',[]) if unit else []
            row[side+'_symbol_references']=unit.get('symbol_references',[]) if unit else []
            page_numbers=list(dict.fromkeys(segment['page'] for segment in segments))
            label=f"Network {unit['number']}" if unit and unit['number'] is not None else unit['title'] if unit else ''
            row[side+'_ref']=f"{block_name} / {label} / Pages {', '.join(map(str,page_numbers))}" if unit else ''
            row[side+'_location']=dict(page=segments[0]['page'],bbox=segments[0]['bbox'],highlights=[segments[0]['bbox']] if state!='unchanged' else []) if segments else None
        rows.append(row)
    try:
        right_by_key={block['key']:block for block in blocks[1] if block_counts[1][block['key']]==1}
        used=set()
        for left in blocks[0]+[None]:
            candidates=[right_by_key.get(left['key'])] if left else [block for block in blocks[1] if id(block) not in used]
            for right in candidates:
                if right:used.add(id(right))
                block=left or right
                if not block:continue
                ambiguous=any(counts[block['key']]>1 for counts in block_counts) or block['key'].startswith('__unresolved') or bool((left or {}).get('ambiguous') or (right or {}).get('ambiguous'))
                start=len(rows)
                add(left.get('metadata') if left else None,right.get('metadata') if right else None,block['name'],ambiguous)
                network_counts={id(source):Counter(unit['number'] for unit in source['networks']) for source in (left,right) if source}
                for a,b in aligned_networks(left['networks'] if left else [],right['networks'] if right else []):
                    # Duplicated network numbers in a block are never quietly certified as matches.
                    duplicate=any(unit and network_counts[id(source)][unit['number']]>1 for unit,source in [(a,left),(b,right)] if source)
                    add(a,b,block['name'],ambiguous or duplicate)
                for a,b in zip_longest(left.get('counters',[]) if left else [],right.get('counters',[]) if right else []):add(a,b,block['name'],ambiguous)
                for a,b in zip_longest(left.get('unassigned',[]) if left else [],right.get('unassigned',[]) if right else []):add(a,b,block['name'],True)
                blocks_info.append(dict(name=block['name'],base_address=left['address'] if left else '',compared_address=right['address'] if right else '',rows=[r['id'] for r in rows[start:]]))
    finally:
        for renderer in renderers:renderer.close()
    pages={side:item[1] for side,item in zip(('base','compared'),extracted)}
    notes=['Networks are matched within explicit printed block headings using unique content anchors and unambiguous network numbers.',
           'Printed project headers are identification only. Block information, network titles, operands and source pages remain in the result.',
           'Pixel comparison at 1000 px page width detects rendered wiring, symbols and text. Rigid network alignment removes page translation; a one-pixel raster tolerance retains changed ink. No behavioural equivalence is asserted.' if pixels else 'Pixel comparison was disabled. Wiring and symbol geometry have not been compared.',
           'Source text, drawing primitives and raster evidence are checked in two bounded passes. Matching source geometry corroborates rendering noise; unexplained visual changes require review.',
           'Page breaks and outside whitespace are removed from network crops; continued networks retain every source-page segment.']
    notes.extend(f'{side}: {notice}' for side,item in zip(('Base','Compared'),extracted) for notice in item[3])
    ignored={side:item[2] for side,item in zip(('base','compared'),extracted)}
    omitted=[name for name in ('author','created','modified','comments','references') if not options.get('compare_'+name,True)]
    if omitted:notes.append('Excluded from text and rendered pixel comparison: '+', '.join(omitted)+'. Masked preview areas are omitted from exports too. Comment exclusion recognizes green printed comment text; other comment styles remain compared for review.')
    return rows,[],notes,dict(mode='plc_networks',comparison_version=engineering.VERSION,pixel_compare=pixels,blocks=blocks_info,pages=pages,
        extraction_cache_hits=sum(hit for _,hit in cached),
        comparison_fields={name:options.get('compare_'+name,True) for name in ('author','created','modified','comments','references')},
        pairs=pdf.align_pages(rows,pages['base'],pages['compared']),ignore_page_numbers=options.get('ignore_page_numbers',True),ignored_page_numbers=ignored)


def status_highlights(a, b, status, aligned=False):
    """Colour observed raster changes; preserve source ink and unchanged pixels."""
    from PIL import Image, ImageChops, ImageFilter
    color={'added':'#17a673','removed':'#e44d61','modified':'#efb52e','unresolved':'#8291a5'}.get(status)
    if not color:return a.copy(),b.copy() if b else None
    if b is None:
        tint=Image.new('RGB',a.size,color)
        try:return Image.blend(a,tint,.16),None
        finally:tint.close()
    images,masks,offsets,_=registered_pixels(a,b)
    union=ImageChops.lighter(*masks)
    try:
        output=[]
        for image,mask,offset,original in zip(images,masks,offsets,(a,b)):
            halo=union.filter(ImageFilter.MaxFilter(3))
            tint=Image.new('RGB',image.size,color);wash=Image.blend(image,tint,.28);tint.close()
            image.paste(wash,(0,0),halo);wash.close();halo.close()
            output.append(image.copy() if aligned else image.crop((*offset,offset[0]+original.width,offset[1]+original.height)))
        return tuple(output)
    finally:
        for item in images+masks+[union]:item.close()


def network_image(user,key,row_id,side,overlay=False,highlight=False):
    from backend.core import document_comparison as core
    path,result,files=pdf.result_sources(user,key)
    if result['pdf'].get('mode')!='plc_networks' or side not in files or not 1<=row_id<=len(result['rows']):
        core.fail('Choose a valid PLC network and side.',400)
    if overlay and side!='compared':core.fail('Pixel overlay belongs to the Compared network.',400)
    if result['pdf'].get('comparison_version',0)!=engineering.VERSION:core.fail('Run Compare PLC PDFs again to apply source evidence checks.',409)
    row=result['rows'][row_id-1]
    if not row.get(side+'_segments'):core.fail('This network is absent from this side.',404)
    if overlay and (not result['pdf']['pixel_compare'] or not all(row.get(s+'_segments') for s in ('base','compared'))):
        core.fail('Pixel comparison is unavailable for this network.',400)
    # Registration and raster tolerance must also apply to regenerated exports.
    cache=path/f'network-v{engineering.VERSION}-{row_id}-{side}-{int(overlay)}-{int(highlight)}.png'
    if cache.is_file():return cache.read_bytes()
    image=None
    if not overlay:
        renderer=ExportNetworkImages((path,result,files))
        try:data=renderer.png(row,side,highlight=highlight and row['status']!='unchanged')
        finally:renderer.close()
    else:
        renderers=[Renderer(files[s],result['pdf']['pages'][s]) for s in ('base','compared')]
        try:
            a,b=[r.network(dict(segments=row[s+'_segments'],number=row.get(s+'_network'))) for r,s in zip(renderers,('base','compared'))]
            try:
                if row['status']=='unchanged' and ((row.get('assessment') or {}).get('source_corroborated') or (row.get('structure') or {}).get('same')):
                    pair,masks,_,_=registered_pixels(a,b)
                    image=pair[1];pair[0].close()
                    for mask in masks:mask.close()
                else:_,image=pixel_diff(a,b,aligned=True)
            finally:a.close();b.close()
            out=io.BytesIO();image.save(out,format='PNG');data=out.getvalue()
        finally:
            if image:image.close()
            for renderer in renderers:renderer.close()
    pdf.result_sources(user,key);pdf.save_cache(cache,data)
    return data


class ExportNetworkImages:
    """One bounded page cache per source and one registration per network pair."""
    def __init__(self,sources):
        self.path,self.result,files=sources
        self.renderers={side:Renderer(files[side],self.result['pdf']['pages'][side]) for side in ('base','compared')}
    def close(self):
        for renderer in self.renderers.values():renderer.close()
    def png(self,row,side,highlight=None):
        if not row.get(side+'_segments'):return None
        highlight=(row['status']!='unchanged') if highlight is None else highlight
        cache=lambda name:self.path/f"network-v{engineering.VERSION}-{row['id']}-{name}-0-{int(highlight)}.png"
        if cache(side).is_file():return cache(side).read_bytes()
        images={};marked=[]
        try:
            local_marks=(row.get('structure') or {}).get('binding_changes',[]) if highlight else []
            for name in ('base','compared'):
                if row.get(name+'_segments'):
                    boxes=[(change[name+'_page'],change[name+'_bbox']) for change in local_marks]
                    images[name]=self.renderers[name].network(dict(segments=row[name+'_segments'],number=row.get(name+'_network')),boxes)
            if local_marks:
                selected=images
            elif highlight and row['status'] in {'modified','unresolved'} and (row.get('pixels') or {}).get('changed_pixels') and len(images)==2:
                marked=list(status_highlights(images['base'],images['compared'],row['status'],aligned=True))
                selected=dict(zip(('base','compared'),marked))
            elif highlight:
                selected={name:status_highlights(original,None,row['status'])[0] for name,original in images.items()}
                marked=list(selected.values())
            else:selected=images
            if len(images)==2 and not marked:
                if row.get('pixels') and not local_marks:
                    pair,masks,_,_=registered_pixels(images['base'],images['compared'])
                    for mask in masks:mask.close()
                else:
                    from PIL import Image
                    size=(max(i.width for i in images.values()),max(i.height for i in images.values()))
                    pair=[]
                    for original in images.values():
                        canvas=Image.new('RGB',size,'white');canvas.paste(original,(0,0));pair.append(canvas)
                selected=dict(zip(('base','compared'),pair));marked=pair
            for name,image in selected.items():
                stream=io.BytesIO();image.save(stream,format='PNG');pdf.save_cache(cache(name),stream.getvalue())
            return cache(side).read_bytes()
        finally:
            for image in [*images.values(),*marked]:image.close()


def export_report(user,key,format,status='differences',metadata=None,progress=None):
    sources=pdf.result_sources(user,key)
    if sources[1]['pdf'].get('mode')!='plc_networks':raise HTTPException(400,'Choose a PLC network comparison.')
    if sources[1]['pdf'].get('comparison_version',0)!=engineering.VERSION:raise HTTPException(409,'Run Compare PLC PDFs again before exporting this older result.')
    renderer=ExportNetworkImages(sources)
    try:return _export_report(user,key,format,status,metadata,sources,renderer,progress)
    finally:renderer.close()


def _export_report(user,key,format,status,metadata,sources,renderer,progress):
    """Matched network crops and explicit before/after evidence in every report."""
    import base64
    from html import escape
    from backend.core import document_comparison as core
    path,result,_=sources
    if result['pdf'].get('mode')!='plc_networks':
        raise HTTPException(400,'Choose a PLC network comparison.')
    status=core.plc_status_filter(status)
    metadata=metadata or {}
    metadata_fields=('project_name','project_id','department','base','description','approved_by','objective_scope','developed','reviewed_by')
    metadata={name:str(metadata.get(name,'') or '').strip() for name in metadata_fields}
    if any(len(value)>(2000 if name in {'description','objective_scope'} else 500) or any(ord(c)<32 and c not in '\n\r\t' for c in value) for name,value in metadata.items()):
        raise HTTPException(400,'Keep report details within their text limits and remove unsupported control characters.')
    detail_labels=(('project_name','Project name'),('project_id','Project ID'),('department','Department'),('base','Base / reference'),('developed','Developed / compare'),('description','Description'),('objective_scope','Objective / scope'),('reviewed_by','Reviewed by'),('approved_by','Approved by'))
    import hashlib,json
    metadata_hash=hashlib.sha256(json.dumps(metadata,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()[:12]
    cache=path/f'plc-network-report-v11-{status}-{metadata_hash}.{format}'
    if cache.is_file():
        if progress:progress(0,0,'complete')
        return cache.read_bytes()
    rows=core.filtered(result,status)
    heading=result['base']['name']+' -> '+result['compared']['name']
    notes=[*result['notices'],f'Export selection: {status}. Reports show Before and After side by side; both sides mark detected changes when highlighting is available.',
           *(f"{side.title()} SHA256: {result[side]['sha256']}" for side in ('base','compared'))]
    def description(row):
        return f"{row['block']} | {'Network' if row['unit']=='network' else 'Block information'} {row['base_network'] if row['base_network'] is not None else ''} -> {row['compared_network'] if row['compared_network'] is not None else ''} | {row['status']}"
    def evidence(row):
        metric=row.get('pixels')
        if row.get('assessment'):return engineering.describe(row)
        return ('Text changed. ' if row['text_changed'] else 'Extracted text unchanged. ')+(
            f"{metric['changed_pixels']} changed ink pixels after rigid network alignment (one-pixel raster tolerance). Review highlighted operands, symbols and wiring." if metric else 'Pixel comparison not available for this pair.')
    def text_changes(row):
        """Return literal line changes, with compared-side additions and base-side removals."""
        added=[];removed=[]
        before=row['base'].splitlines();after=row['compared'].splitlines()
        for operation,left_start,left_end,right_start,right_end in SequenceMatcher(None,before,after,autojunk=False).get_opcodes():
            if operation in {'replace','delete'}:removed.extend(before[left_start:left_end])
            if operation in {'replace','insert'}:added.extend(after[right_start:right_end])
        return added,removed
    completed=set()
    if progress:progress(0,len(rows),'rendering')
    def png(row,side):
        value=renderer.png(row,side)
        if row['id'] not in completed:
            completed.add(row['id'])
            if progress:progress(len(completed),len(rows),'rendering')
        return value
    def tiles(row):
        from PIL import Image
        images={side:Image.open(io.BytesIO(data)).convert('RGB') for side in ('base','compared') if (data:=png(row,side))}
        try:
            width=max((image.width for image in images.values()),default=1)
            height=max((image.height for image in images.values()),default=1)
            step=max(1,int(width*1.03))
            for top in range(0,height,step):
                part={}
                for side,image in images.items():
                    if top>=image.height:continue
                    crop=image.crop((0,top,image.width,min(image.height,top+step)))
                    data=io.BytesIO();crop.save(data,format='PNG');crop.close();part[side]=data.getvalue()
                yield part
        finally:
            for image in images.values():image.close()
    output=io.BytesIO()
    if format=='html':
        cover_rows=''.join(f'<dt>{label}</dt><dd>{escape(metadata[name])}</dd>' for name,label in detail_labels if metadata[name])
        cover_html=('<section class="cover"><h1>Project and review details</h1><dl>'+cover_rows+'</dl></section>') if cover_rows else ''
        sections=[]
        for row in rows:
            columns=[]
            for side,label in [('base','Before'),('compared','After')]:
                image=png(row,side)
                picture=f'<img alt="{label} source network" src="data:image/png;base64,{base64.b64encode(image).decode()}"/>' if image else '<p>Network absent on this side.</p>'
                columns.append(f'<div><h3>{label}</h3><p>{escape(row[side+"_ref"])}</p>{picture}<pre>{escape(row[side])}</pre></div>')
            added,removed=text_changes(row)
            change_summary=''.join((f'<h3>Added content · Compared</h3><pre class="added">{escape(chr(10).join(added))}</pre>' if added else '',f'<h3>Removed content · Base</h3><pre class="removed">{escape(chr(10).join(removed))}</pre>' if removed else '')) or '<p>No extracted text additions or removals. Review the side-by-side images for visual or wiring changes.</p>'
            sections.append(f'<section><h2>{escape(description(row))}</h2><p>{escape(evidence(row))}</p><div class="pair">{"".join(columns)}</div><h2>Text changes</h2>{change_summary}</section>')
        data=('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
              '<title>PLC PDF network comparison</title><style>body{font:14px system-ui;margin:24px;color:#182b37}section{border-top:1px solid #ccd4db;margin-top:24px}.cover{page-break-after:always;padding-bottom:30px}.cover dt{font-weight:600;margin-top:14px}.cover dd{margin:5px 0;white-space:pre-wrap}.pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;padding:8px}.added{background:#e3f7eb;border-left:4px solid #159447}.removed{background:#fde8e8;border-left:4px solid #d43f4d}p{overflow-wrap:anywhere}@media(max-width:650px){.pair{grid-template-columns:1fr}}</style>'
              +cover_html+f'<h1>PLC PDF network comparison</h1><h2>{escape(heading)}</h2>'+''.join(f'<p>{escape(note)}</p>' for note in notes)+
              (''.join(sections) or '<p>No differences in the compared networks.</p>')+'</html>').encode('utf8')
    elif format=='docx':
        from docx import Document
        from docx.shared import Inches
        from docx.shared import RGBColor
        from PIL import Image
        document=Document()
        selected_details=[(label,metadata[name]) for name,label in detail_labels if metadata[name]]
        if selected_details:
            document.add_heading('Project and review details',0)
            table=document.add_table(rows=len(selected_details),cols=2)
            for row,(label,value) in zip(table.rows,selected_details):row.cells[0].text=label;row.cells[1].text=value
            document.add_page_break()
        document.add_heading('PLC PDF network comparison',0);document.add_paragraph(heading)
        for note in notes:document.add_paragraph(note)
        for row in rows:
            document.add_heading(description(row),1);document.add_paragraph(evidence(row))
            for number,part in enumerate(tiles(row),1):
                document.add_paragraph(f'Network crop part {number}')
                table=document.add_table(rows=1,cols=2)
                for cell,(side,label) in zip(table.rows[0].cells,[('base','Before'),('compared','After')]):
                    cell.text=label+'\n'+row[side+'_ref']
                    image=part.get(side)
                    if image:
                        with Image.open(io.BytesIO(image)) as im: width,height=im.size
                        scale=min(2.9/width,3.5/height)
                        cell.add_paragraph().add_run().add_picture(io.BytesIO(image),width=Inches(width*scale),height=Inches(height*scale))
            added,removed=text_changes(row)
            document.add_heading('Text changes',2)
            for title,lines,color in [('Added content · Compared',added,'00843D'),('Removed content · Base',removed,'C62828')]:
                if lines:
                    document.add_heading(title,3)
                    for line in lines:
                        paragraph=document.add_paragraph(line)
                        for run in paragraph.runs:run.font.color.rgb=RGBColor.from_string(color)
            if not added and not removed:document.add_paragraph('No extracted text additions or removals. Review the side-by-side images for visual or wiring changes.')
        if not rows:document.add_paragraph('No differences in the compared networks.')
        if progress:progress(len(rows),len(rows),'formatting')
        document.save(output);data=output.getvalue()
    else:
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,Table,TableStyle,PageBreak
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4,landscape
        from backend.core.workhub_quality.packages import _pdf_font
        from reportlab.pdfbase import pdfmetrics
        styles=getSampleStyleSheet()
        font=_pdf_font('\n'.join([heading,*notes,*(row[side] for row in rows for side in ('base','compared'))]))
        if font!='Helvetica':pdfmetrics.registerFontFamily(font,normal=font,bold=font,italic=font,boldItalic=font)
        for style in styles.byName.values():style.fontName=font
        story=[Paragraph('PLC PDF network comparison',styles['Title']),Paragraph(escape(heading),styles['Heading2']),Paragraph(f'Included: {escape(status)}',styles['BodyText'])]
        detail_rows=[[Paragraph(f'<b>{label}</b>',styles['BodyText']),Paragraph(escape(metadata[key]) or '—',styles['BodyText'])] for key,label in detail_labels if metadata[key]]
        if detail_rows:
            story.extend([Spacer(1,10),Paragraph('Project and approval details',styles['Heading2'])])
            details=Table(detail_rows,colWidths=[135,605],repeatRows=0)
            details.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(0,-1),'#edf3f8'),('GRID',(0,0),(-1,-1),0.4,'#c8d3dd'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
            story.append(details)
        for row in rows:
            added,removed=text_changes(row)
            for number,part in enumerate(tiles(row),1):
                story.extend([PageBreak(),Paragraph(escape(description(row))+f' | Crop part {number}',styles['Heading2']),Paragraph(escape(evidence(row)),styles['BodyText']),Spacer(1,10)])
                cells=[]
                for side,label in [('base','Before'),('compared','After')]:
                    items=[Paragraph(label,styles['Heading3']),Paragraph(escape(row[side+'_ref']) or '(Network absent)',styles['BodyText'])]
                    image=part.get(side)
                    if image:
                        obj=Image(io.BytesIO(image));scale=min(350/obj.imageWidth,370/obj.imageHeight)
                        obj.drawWidth=obj.imageWidth*scale;obj.drawHeight=obj.imageHeight*scale;items.append(obj)
                    cells.append(items)
                table=Table([cells],colWidths=[370,370]);table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
                story.append(table)
            story.append(Paragraph('Text changes',styles['Heading2']))
            change_rows=[]
            for label,lines,background in [('Added content · Compared',added,'#e3f7eb'),('Removed content · Base',removed,'#fde8e8')]:
                if lines:
                    change_rows.append([Paragraph(f'<b>{escape(label)}</b>',styles['BodyText'])])
                    change_rows.extend([Paragraph(escape(line) or '(blank)',styles['Code'])] for line in lines)
            if change_rows:
                changes=Table(change_rows,colWidths=[740],repeatRows=0)
                table_style=[('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]
                for index,row_cells in enumerate(change_rows):
                    if len(row_cells)==1 and isinstance(row_cells[0],Paragraph) and row_cells[0].getPlainText().startswith('Added content'):
                        table_style.append(('BACKGROUND',(0,index),(-1,index),'#e3f7eb'))
                    elif len(row_cells)==1 and isinstance(row_cells[0],Paragraph) and row_cells[0].getPlainText().startswith('Removed content'):
                        table_style.append(('BACKGROUND',(0,index),(-1,index),'#fde8e8'))
                changes.setStyle(TableStyle(table_style));story.append(changes)
            else:story.append(Paragraph('No extracted text additions or removals. Review the side-by-side images for visual or wiring changes.',styles['BodyText']))
        if not rows:story.append(Paragraph('No differences in the compared networks.',styles['BodyText']))
        if progress:progress(len(rows),len(rows),'formatting')
        SimpleDocTemplate(output,pagesize=landscape(A4),leftMargin=35,rightMargin=35,topMargin=30,bottomMargin=30).build(story)
        data=output.getvalue()
    pdf.result_sources(user,key);pdf.save_cache(cache,data)
    if progress:progress(len(rows),len(rows),'complete')
    return data
