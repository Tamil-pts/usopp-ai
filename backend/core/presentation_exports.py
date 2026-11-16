"""Render one shared slide schema to editable PPTX, vector PDF, SVG or PNG ZIP."""
import io
import html
import textwrap
import zipfile

def lines(element):
    width = max(1, int((element['w']-28)/(element['size']*.57)))
    return [part for line in element['text'].split('\n') for part in textwrap.wrap(line, width, replace_whitespace=False) or ['']]

def svg(slide, font):
    esc = html.escape
    result = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="{slide["background"]}"/>']
    for e in slide['elements']:
        x,y,w,h = (e[key] for key in ('x','y','w','h'))
        if e['kind']=='box':
            result.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{e["fill"]}"/>')
        result.append(f'<text x="{x+14}" y="{y+e["size"]+8}" fill="{e["color"]}" font-family="{esc(font,quote=True)}" font-size="{e["size"]}" font-weight="{700 if e["bold"] else 400}">')
        for i,line in enumerate(lines(e)):
            result.append(f'<tspan x="{x+14}" dy="{e["size"]*1.25 if i else 0}">{esc(line)}</tspan>')
        result.append('</text>')
    return ''.join(result)+'</svg>'

def pptx(deck):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Emu, Pt
    prs = Presentation()
    px=lambda value:Emu(round(value*9525))
    prs.slide_width,prs.slide_height=px(1280),px(720)
    prs.core_properties.title=deck['title']
    prs.core_properties.subject='Reviewable Chopper presentation draft'
    for row in deck['slides']:
        slide=prs.slides.add_slide(prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb=RGBColor.from_string(row['background'][1:])
        for e in row['elements']:
            shape=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,px(e['x']),px(e['y']),px(e['w']),px(e['h'])) if e['kind']=='box' else slide.shapes.add_textbox(px(e['x']),px(e['y']),px(e['w']),px(e['h']))
            shape.name=e['id']
            if e['kind']=='box':
                shape.fill.solid();shape.fill.fore_color.rgb=RGBColor.from_string(e['fill'][1:]);shape.line.fill.background()
            frame=shape.text_frame;frame.word_wrap=True
            frame.margin_left=frame.margin_right=px(14);frame.margin_top=frame.margin_bottom=px(8)
            # Explicit common wrapping improves consistency with SVG/PDF, while text remains editable.
            frame.text='\n'.join(lines(e))
            for paragraph in frame.paragraphs:
                paragraph.font.name=deck['font'];paragraph.font.size=Pt(e['size']*.75)
                paragraph.font.bold=e['bold'];paragraph.font.color.rgb=RGBColor.from_string(e['color'][1:])
                paragraph.space_after=Pt(0);paragraph.line_spacing=1.25
        slide.notes_slide.notes_text_frame.text=row['notes']
    output=io.BytesIO();prs.save(output);return output.getvalue()

def pdf(deck):
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.colors import HexColor
    import os
    from pathlib import Path
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from fontTools.ttLib import TTFont as FontInfo
    from fastapi import HTTPException
    font='Times-Roman' if deck['font'] in {'Georgia','Cambria','Times New Roman'} else 'Courier' if deck['font'] in {'Courier New','Consolas'} else 'Helvetica'
    bold_font={'Times-Roman':'Times-Bold','Courier':'Courier-Bold','Helvetica':'Helvetica-Bold'}[font]
    names={'Arial':'arial.ttf','Calibri':'calibri.ttf','Aptos':'aptos.ttf','Segoe UI':'segoeui.ttf','Verdana':'verdana.ttf','Tahoma':'tahoma.ttf','Trebuchet MS':'trebuc.ttf','Georgia':'georgia.ttf','Cambria':'cambria.ttf','Times New Roman':'times.ttf','Courier New':'cour.ttf','Consolas':'consola.ttf'}
    candidates=[Path(os.getenv('WINDIR','C:/Windows'))/'Fonts'/names.get(deck['font'],'missing.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    chosen=next((p for p in candidates if p.is_file()),None)
    characters=set(''.join(e['text'] for s in deck['slides'] for e in s['elements']))-set('\n\r\t')
    if chosen:
        with FontInfo(chosen) as info:available=set(info.getBestCmap() or {})
        if any(ord(c) not in available for c in characters):
            raise HTTPException(422,'The server font cannot render some characters in this presentation. Export editable PPTX/SVG, or choose a supported installed font.')
        font='Chopper-'+chosen.stem
        if font not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(font,str(chosen)))
        bold_font=font
        bold_names={'arial':'arialbd.ttf','calibri':'calibrib.ttf','aptos':'aptos-bold.ttf','segoeui':'segoeuib.ttf','verdana':'verdanab.ttf','tahoma':'tahomabd.ttf','trebuc':'trebucbd.ttf','georgia':'georgiab.ttf','cambria':'cambriab.ttf','times':'timesbd.ttf','cour':'courbd.ttf','consola':'consolab.ttf','DejaVuSans':'DejaVuSans-Bold.ttf'}
        bold_path=chosen.with_name(bold_names.get(chosen.stem,'missing-bold.ttf'))
        if bold_path.is_file():
            bold_font=font+'-bold'
            if bold_font not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(bold_font,str(bold_path)))
    elif any(ord(c)>255 for c in characters):
        raise HTTPException(422,'A suitable server font is unavailable for some characters. Use editable PPTX or SVG export.')
    output=io.BytesIO();canvas=Canvas(output,pagesize=(960,540));canvas.setTitle(deck['title'])
    for slide in deck['slides']:
        canvas.saveState();canvas.scale(.75,.75)
        canvas.setFillColor(HexColor(slide['background']));canvas.rect(0,0,1280,720,fill=1,stroke=0)
        for e in slide['elements']:
            if e['kind']=='box':
                canvas.setFillColor(HexColor(e['fill']));canvas.roundRect(e['x'],720-e['y']-e['h'],e['w'],e['h'],14,fill=1,stroke=0)
            variant = bold_font if e['bold'] else font
            canvas.setFont(variant,e['size']);canvas.setFillColor(HexColor(e['color']))
            for i,line in enumerate(lines(e)):
                canvas.drawString(e['x']+14,720-e['y']-e['size']-8-i*e['size']*1.25,line)
        canvas.restoreState();canvas.showPage()
    canvas.save();return output.getvalue()

def export(deck, kind):
    if kind=='pptx':return pptx(deck)
    if kind=='pdf':return pdf(deck)
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        if kind=='svg':
            for i,slide in enumerate(deck['slides']):archive.writestr(f'slide-{i+1:02d}.svg',svg(slide,deck['font']))
        else:
            import pypdfium2
            document=pypdfium2.PdfDocument(pdf(deck))
            try:
                for i in range(len(document)):
                    page=document[i];bitmap=page.render(scale=1.5)
                    try:
                        data=io.BytesIO();bitmap.to_pil().save(data,format='PNG');archive.writestr(f'slide-{i+1:02d}.png',data.getvalue())
                    finally:bitmap.close();page.close()
            finally:document.close()
    return output.getvalue()
