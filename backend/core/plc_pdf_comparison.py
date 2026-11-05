"""Printed PLC block/network comparison. Source evidence, never inferred execution."""
from __future__ import annotations

import io
import re
from collections import Counter, OrderedDict
from difflib import SequenceMatcher
from itertools import zip_longest

from fastapi import HTTPException

from backend.core import document_pdf_comparison as pdf

RUNNING = re.compile(r'^.+?\s+/\s+(.+?)\s+\(((?:OB|SBR|FB|FC|DB|INT)\s*\d+)\)\s*$', re.I)
NETWORK = re.compile(r'^Network\s+(\d+)\b(.*)$', re.I)


def extract(path, ignore_page_numbers=True):
    import pdfplumber
    blocks, pages, ignored, notices = [], [], [], []
    current, active = None, None
    characters = 0
    with pdfplumber.open(path) as document:
        if len(document.pages) > 250:
            raise HTTPException(422, 'PLC PDF comparison supports up to 250 pages per file.')
        for number, original in enumerate(document.pages, 1):
            bounds = original.bbox
            if original.cropbox:
                bounds = (max(bounds[0], original.cropbox[0]), max(bounds[1], original.cropbox[1]),
                          min(bounds[2], original.cropbox[2]), min(bounds[3], original.cropbox[3]))
            page = original.crop(bounds) if tuple(bounds) != tuple(original.bbox) else original
            width, height = page.width, page.height
            pages.append(dict(number=number, width=width, height=height))
            lines = page.extract_text_lines(return_chars=False)
            for line in lines:
                line['bbox'] = [line['x0']-bounds[0], line['top']-bounds[1], line['x1']-bounds[0], line['bottom']-bounds[1]]
            header = next((line for line in lines if RUNNING.fullmatch(line['text'].strip()) and line['bbox'][1] < height*.12), None)
            title = next((line for line in lines if re.match(r'^Block\s*:', line['text'], re.I)), None)
            match = RUNNING.fullmatch(header['text'].strip()) if header else None
            name = match[1].strip() if match else re.sub(r'^Block\s*:\s*', '', title['text'], flags=re.I).strip() if title else None
            address = match[2].upper().replace(' ', '') if match else ''
            identity = name.casefold() if name else None
            if identity and (current is None or current['key'] != identity or title):
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
            headings = [(line, NETWORK.fullmatch(line['text'].strip())) for line in body]
            headings = [(line, match) for line, match in headings if match]
            def append_region(unit, start, end, excluded=None):
                nonlocal characters
                if end <= start: return
                # Full width preserves parallel branches and wiring with no nearby text.
                unit['segments'].append(dict(page=number, bbox=[0, start, width, end]))
                content = [line['text'] for line in body if line is not excluded and start <= line['bbox'][1] < end]
                text = '\n'.join(content)
                if not content and page.images:unit['unknown']=True
                characters += len(text)
                unit['text'] += ('\n' if unit['text'] and text else '') + text
                if characters > 1000000:
                    raise HTTPException(422, 'PLC PDF text exceeds one million characters. Split the document.')
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
                end = headings[index+1][0]['bbox'][1]-2 if index+1 < len(headings) else bottom
                append_region(active, line['bbox'][3]+2, end)
            # A page counter is kept as separate evidence when explicitly requested.
            if not ignore_page_numbers and counters:
                current.setdefault('counters', []).extend(dict(number=None, title='Printed page counter', text=line['text'],
                    segments=[dict(page=number,bbox=line['bbox'])]) for line in counters)
            if sum(len(block['networks']) for block in blocks) > 3000:
                raise HTTPException(422, 'PLC PDF comparison supports up to 3,000 networks per file.')
            original.close()
    if not any(block['networks'] for block in blocks):
        raise HTTPException(422, 'No explicit PLC blocks and Network headings were found. Use a searchable PLC program PDF; scanned or other layouts need OCR/format review.')
    for block in blocks:
        if block['metadata'] and block['address']:
            block['metadata']['text']='Printed block reference: '+block['address']+'\n'+block['metadata']['text']
    return blocks, pages, ignored, notices


class Renderer:
    """Bounded page cache. Only cropped network evidence is retained in results."""
    def __init__(self, path, pages): self.path, self.pages, self.cache = path, pages, OrderedDict()
    def close(self):
        for image in self.cache.values(): image.close()
        self.cache.clear()
    def page(self, number):
        from PIL import Image
        if number not in self.cache:
            self.cache[number] = Image.open(io.BytesIO(pdf.render_png(self.path, number, width=1000))).convert('RGB')
            if len(self.cache) > 3: self.cache.popitem(last=False)[1].close()
        self.cache.move_to_end(number)
        return self.cache[number]
    def network(self, unit):
        from PIL import Image, ImageChops
        chunks = []
        try:
            for segment in unit['segments']:
                image = self.page(segment['page']); meta = self.pages[segment['page']-1]; box = segment['bbox']
                crop = image.crop((round(box[0]*image.width/meta['width']), round(box[1]*image.height/meta['height']),
                                   round(box[2]*image.width/meta['width']), round(box[3]*image.height/meta['height'])))
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
            result=merged.crop((max(0,bounds[0]-3),0,min(width,bounds[2]+3),height)) if bounds else merged.copy()
            merged.close(); return result
        finally:
            for chunk in chunks: chunk.close()


def pixel_diff(a, b):
    from PIL import Image, ImageChops
    size=(max(a.width,b.width),max(a.height,b.height))
    left,right=Image.new('RGB',size,'white'),Image.new('RGB',size,'white')
    left.paste(a,(0,0));right.paste(b,(0,0))
    delta=ImageChops.difference(left,right).convert('L').point(lambda v:255 if v>32 else 0)
    changed=delta.histogram()[255]
    # Red marks represent observed raster differences, including possible print/layout changes.
    overlay=right.copy();overlay.paste(Image.new('RGB',size,'#e44d61'),(0,0),delta)
    left.close();right.close();delta.close()
    return dict(changed_pixels=changed,total_pixels=size[0]*size[1],threshold=32),overlay


def aligned_networks(a, b):
    """Exact text anchors prevent one inserted network shifting all later networks."""
    keys=lambda units:[unit['text']+'\n'+unit['title'] for unit in units]
    for tag,i,j,k,l in SequenceMatcher(None,keys(a),keys(b),autojunk=False).get_opcodes():
        if tag=='equal': yield from zip(a[i:j],b[k:l]);continue
        # Exact network numbers are a second anchor when an entire text run changed.
        # Never pair network 1 with an unrelated network 20 merely by list position.
        unmatched_a,unmatched_b=a[i:j],b[k:l]
        right_numbers=Counter(unit['number'] for unit in unmatched_b)
        lookup={unit['number']:unit for unit in unmatched_b if right_numbers[unit['number']]==1}
        used=set()
        for left in unmatched_a:
            right=lookup.get(left['number'])
            if right:used.add(id(right))
            yield left,right
        for right in unmatched_b:
            if id(right) not in used:yield None,right


def compare(files, options):
    extracted=[extract(path,options.get('ignore_page_numbers',True)) for path in files]
    blocks=[item[0] for item in extracted];rows=[]
    renderers=[Renderer(path,item[1]) for path,item in zip(files,extracted)]
    pixels=options.get('pixel_compare',True)
    block_counts=[Counter(block['key'] for block in side) for side in blocks]
    blocks_info=[]
    def add(left,right,block_name,ambiguous=False):
        if not left and not right:return
        text_equal=bool(left and right and (left['text'],left['title'])==(right['text'],right['title']))
        state='unresolved' if ambiguous or any(unit and unit.get('unknown') for unit in (left,right)) else 'added' if left is None else 'removed' if right is None else 'unchanged' if text_equal else 'modified'
        visual=None
        if pixels and left and right and state!='unresolved':
            a,b=renderers[0].network(left),renderers[1].network(right)
            try:
                visual,overlay=pixel_diff(a,b);overlay.close()
                if visual['changed_pixels']:state='modified'
            finally:a.close();b.close()
        row=dict(id=len(rows)+1,status=state,block=block_name,unit='network' if (left or right)['number'] is not None else 'block',
                 text_changed=not text_equal,pixels=visual)
        for side,unit in zip(('base','compared'),(left,right)):
            row[side]=unit['text'] if unit else ''
            if unit and unit['number'] is not None and unit['title']:
                row[side]='Network title: '+unit['title']+'\n'+row[side]
            row[side+'_network']=unit['number'] if unit else None
            row[side+'_title']=unit['title'] if unit else ''
            segments=unit['segments'] if unit else []
            row[side+'_segments']=segments
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
                for a,b in aligned_networks(left['networks'] if left else [],right['networks'] if right else []):
                    # Duplicated network numbers in a block are never quietly certified as matches.
                    duplicate=any(unit and Counter(item['number'] for item in source['networks'])[unit['number']]>1 for unit,source in [(a,left),(b,right)] if source)
                    add(a,b,block['name'],ambiguous or duplicate)
                for a,b in zip_longest(left.get('counters',[]) if left else [],right.get('counters',[]) if right else []):add(a,b,block['name'],ambiguous)
                for a,b in zip_longest(left.get('unassigned',[]) if left else [],right.get('unassigned',[]) if right else []):add(a,b,block['name'],True)
                blocks_info.append(dict(name=block['name'],base_address=left['address'] if left else '',compared_address=right['address'] if right else '',rows=[r['id'] for r in rows[start:]]))
    finally:
        for renderer in renderers:renderer.close()
    pages={side:item[1] for side,item in zip(('base','compared'),extracted)}
    notes=['Networks are matched within explicit printed block headings. Exact network text anchors are followed by source-order pairing of unmatched runs.',
           'Printed project headers are identification only. Block information, network titles, operands and source pages remain in the result.',
           'Pixel comparison at 1000 px page width detects rendered wiring, symbols and text. Differences may include print/layout changes; no behavioural equivalence is asserted.' if pixels else 'Pixel comparison was disabled. Wiring and symbol geometry have not been compared.',
           'Page breaks and outside whitespace are removed from network crops; continued networks retain every source-page segment.']
    notes.extend(f'{side}: {notice}' for side,item in zip(('Base','Compared'),extracted) for notice in item[3])
    ignored={side:item[2] for side,item in zip(('base','compared'),extracted)}
    return rows,[],notes,dict(mode='plc_networks',pixel_compare=pixels,blocks=blocks_info,pages=pages,
        pairs=pdf.align_pages(rows,pages['base'],pages['compared']),ignore_page_numbers=options.get('ignore_page_numbers',True),ignored_page_numbers=ignored)


def status_highlights(a, b, status):
    """Colour observed raster changes; preserve source ink and unchanged pixels."""
    from PIL import Image, ImageChops, ImageFilter
    color={'added':'#17a673','removed':'#e44d61','modified':'#efb52e','unresolved':'#8291a5'}.get(status)
    if not color:return a.copy(),b.copy() if b else None
    if b is None:
        tint=Image.new('RGB',a.size,color)
        try:return Image.blend(a,tint,.16),None
        finally:tint.close()
    size=(max(a.width,b.width),max(a.height,b.height))
    left,right=Image.new('RGB',size,'white'),Image.new('RGB',size,'white')
    left.paste(a,(0,0));right.paste(b,(0,0))
    delta=ImageChops.difference(left,right).convert('L')
    mask=delta.point(lambda value:255 if value>32 else 0).filter(ImageFilter.MaxFilter(7))
    delta.close()
    try:
        output=[]
        for image in (left,right):
            # A light coloured halo leaves black contacts, wires and labels legible.
            tint=Image.new('RGB',size,color);wash=Image.blend(image,tint,.28);tint.close()
            image.paste(wash,(0,0),mask);wash.close();output.append(image.copy())
        return tuple(output)
    finally:left.close();right.close();mask.close()


def network_image(user,key,row_id,side,overlay=False,highlight=False):
    from backend.core import document_comparison as core
    path,result,files=pdf.result_sources(user,key)
    if result['pdf'].get('mode')!='plc_networks' or side not in files or not 1<=row_id<=len(result['rows']):
        core.fail('Choose a valid PLC network and side.',400)
    if overlay and side!='compared':core.fail('Pixel overlay belongs to the Compared network.',400)
    row=result['rows'][row_id-1]
    if not row.get(side+'_segments'):core.fail('This network is absent from this side.',404)
    if overlay and (not result['pdf']['pixel_compare'] or not all(row.get(s+'_segments') for s in ('base','compared'))):
        core.fail('Pixel comparison is unavailable for this network.',400)
    cache=path/f'network-v2-{row_id}-{side}-{int(overlay)}-{int(highlight)}.png'
    if cache.is_file():return cache.read_bytes()
    renderers=[Renderer(files[s],result['pdf']['pages'][s]) for s in ('base','compared')]
    image=None
    try:
        if overlay:
            a,b=[r.network(dict(segments=row[s+'_segments'])) for r,s in zip(renderers,('base','compared'))]
            try:_,image=pixel_diff(a,b)
            finally:a.close();b.close()
        elif highlight and row['status']!='unchanged':
            if row['status']=='modified' and row.get('pixels'):
                a,b=[r.network(dict(segments=row[s+'_segments'])) for r,s in zip(renderers,('base','compared'))]
                try:
                    marked=status_highlights(a,b,'modified')
                    image=marked[0 if side=='base' else 1]
                    marked[1 if side=='base' else 0].close()
                finally:a.close();b.close()
            else:
                original=renderers[0 if side=='base' else 1].network(dict(segments=row[side+'_segments']))
                try:image,_=status_highlights(original,None,row['status'])
                finally:original.close()
        else:image=renderers[0 if side=='base' else 1].network(dict(segments=row[side+'_segments']))
        out=io.BytesIO();image.save(out,format='PNG');data=out.getvalue()
    finally:
        if image:image.close()
        for renderer in renderers:renderer.close()
    pdf.result_sources(user,key);pdf.save_cache(cache,data);return data


def export_report(user,key,format):
    """Matched network crops and explicit before/after evidence in every report."""
    import base64
    from html import escape
    path,result,_=pdf.result_sources(user,key)
    if result['pdf'].get('mode')!='plc_networks':
        raise HTTPException(400,'Choose a PLC network comparison.')
    cache=path/f'plc-network-report-v2.{format}'
    if cache.is_file():return cache.read_bytes()
    rows=[row for row in result['rows'] if row['status']!='unchanged']
    heading=result['base']['name']+' -> '+result['compared']['name']
    notes=[*result['notices'],'Compared network crops mark observed changed pixels in red when pixel comparison is enabled.',
           *(f"{side.title()} SHA256: {result[side]['sha256']}" for side in ('base','compared'))]
    def description(row):
        return f"{row['block']} | {'Network' if row['unit']=='network' else 'Block information'} {row['base_network'] if row['base_network'] is not None else ''} -> {row['compared_network'] if row['compared_network'] is not None else ''} | {row['status']}"
    def evidence(row):
        metric=row.get('pixels')
        return ('Text changed. ' if row['text_changed'] else 'Extracted text unchanged. ')+(
            f"{metric['changed_pixels']} of {metric['total_pixels']} rendered pixels differ (threshold {metric['threshold']}/255). Review wiring and print layout." if metric else 'Pixel comparison not available for this pair.')
    def png(row,side):
        overlay=side=='compared' and bool(row.get('pixels',{}).get('changed_pixels') if row.get('pixels') else False)
        return network_image(user,key,row['id'],side,overlay=overlay) if row.get(side+'_segments') else None
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
        sections=[]
        for row in rows:
            columns=[]
            for side,label in [('base','Before'),('compared','After')]:
                image=png(row,side)
                picture=f'<img alt="{label} source network" src="data:image/png;base64,{base64.b64encode(image).decode()}"/>' if image else '<p>Network absent on this side.</p>'
                columns.append(f'<div><h3>{label}</h3><p>{escape(row[side+"_ref"])}</p>{picture}<pre>{escape(row[side])}</pre></div>')
            sections.append(f'<section><h2>{escape(description(row))}</h2><p>{escape(evidence(row))}</p><div class="pair">{"".join(columns)}</div></section>')
        data=('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
              '<title>PLC PDF network comparison</title><style>body{font:14px system-ui;margin:24px;color:#182b37}section{border-top:1px solid #ccd4db;margin-top:24px}.pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}p{overflow-wrap:anywhere}@media(max-width:650px){.pair{grid-template-columns:1fr}}</style>'
              f'<h1>PLC PDF network comparison</h1><h2>{escape(heading)}</h2>'+''.join(f'<p>{escape(note)}</p>' for note in notes)+
              (''.join(sections) or '<p>No differences in the compared networks.</p>')+'</html>').encode('utf8')
    elif format=='docx':
        from docx import Document
        from docx.shared import Inches
        from PIL import Image
        document=Document();document.add_heading('PLC PDF network comparison',0);document.add_paragraph(heading)
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
            for side,label in [('base','Before'),('compared','After')]:
                document.add_heading(label+' extracted text',2);document.add_paragraph(row[side] or '(Network absent)')
        if not rows:document.add_paragraph('No differences in the compared networks.')
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
        story=[Paragraph('PLC PDF network comparison',styles['Title']),Paragraph(escape(heading),styles['Heading2'])]
        for note in notes:story.append(Paragraph(escape(note),styles['BodyText']))
        for row in rows:
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
            for side,label in [('base','Before'),('compared','After')]:
                story.append(Paragraph(label+' extracted text',styles['Heading3']))
                # Separate source lines can paginate without a single oversized table row.
                story.extend(Paragraph(escape(line) or '(blank)',styles['Code']) for line in row[side].splitlines())
        if not rows:story.append(Paragraph('No differences in the compared networks.',styles['BodyText']))
        SimpleDocTemplate(output,pagesize=landscape(A4),leftMargin=35,rightMargin=35,topMargin=30,bottomMargin=30).build(story)
        data=output.getvalue()
    pdf.result_sources(user,key);pdf.save_cache(cache,data);return data
