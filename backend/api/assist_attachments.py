"""Transient, bounded attachment previews for Chopper. Uploaded files are never executed."""
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile, BadZipFile

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

router = APIRouter(tags=['Chopper attachments'])
MAX_FILE = 20 * 1024 * 1024
MAX_TEXT = 60000

def unpack_project(archive_path:Path, source:Path):
    from backend.core.runtime import locate_root, IGNORED_PROJECT_DIRS
    import shutil, stat
    with ZipFile(archive_path) as archive:
        files=[entry for entry in archive.infolist() if not entry.is_dir()]
        if len(files)>100000 or sum(entry.file_size for entry in files)>600*1024*1024:
            raise HTTPException(413,'Project ZIP exceeds 100,000 files or 600 MB of extracted data.')
        targets=[]; seen=set(); base=source.resolve()
        for entry in files:
            name=entry.filename.replace('\\','/'); rel=Path(name)
            if not name or rel.is_absolute() or rel.drive or '..' in rel.parts or ':' in name or stat.S_ISLNK(entry.external_attr >> 16):
                raise HTTPException(400,'Project ZIP contains an unsafe path or link.')
            if any(part.casefold() in IGNORED_PROJECT_DIRS|{'.git','node_modules','__macosx'} for part in rel.parts[:-1]): continue
            target=(source/rel).resolve()
            if base not in target.parents or str(target).casefold() in seen:
                raise HTTPException(400,'Project ZIP contains unsafe or duplicate paths.')
            seen.add(str(target).casefold());targets.append((entry,target))
        for entry,target in targets:
            if entry.flag_bits & 1: raise HTTPException(422,'Attach an unencrypted project ZIP.')
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(entry) as incoming,target.open('wb') as output: shutil.copyfileobj(incoming,output)
    root=locate_root(source)
    if not any((root/name).is_dir() for name in ('Logical','pgm')):
        raise HTTPException(422,'The ZIP contains only a project descriptor. Include the complete project folder with Logical or pgm source files.')
    return root,len(targets)

@router.post('/api/assist/project-attachment')
async def project_attachment(file:UploadFile=File(...)):
    from backend.core.runtime import WORK, json
    from backend.core.run_history import current_user
    import uuid
    if Path(file.filename or '').suffix.casefold()!='.zip':
        raise HTTPException(400,'Attach a complete project ZIP, or choose Project folder from the attachment button.')
    work=WORK/('chopper_'+uuid.uuid4().hex);source=work/'source';source.mkdir(parents=True)
    from backend.core.access import claim_resource
    claim_resource(work)
    archive_path=work/'project.zip';size=0
    try:
        with archive_path.open('wb') as output:
            while data:=await file.read(1024*1024):
                size+=len(data)
                if size>200*1024*1024: raise HTTPException(413,'Choose a project ZIP smaller than 200 MB.')
                output.write(data)
        try:root,count=await run_in_threadpool(unpack_project,archive_path,source)
        except (BadZipFile,OSError,RuntimeError): raise HTTPException(422,'Project ZIP could not be read. Attach a complete, unencrypted ZIP.')
        descriptor=next((p.name for p in root.iterdir() if p.suffix.casefold() in {'.apj','.pgp'}),root.name)
        (work/'inputs.json').write_text(json.dumps({'project':str(root),'owner':(current_user.get() or {}).get('id')}),encoding='utf-8')
        return {'projectPath':str(root),'projectName':descriptor,'sessionId':work.name,'uploadedFiles':count}
    finally:
        await file.close()
        archive_path.unlink(missing_ok=True)


def preview(name: str, content: bytes) -> dict:
    suffix = Path(name).suffix.lower()
    notice = ''
    try:
        if suffix in ('.xlsx', '.docx'):
            with ZipFile(BytesIO(content)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 60 * 1024 * 1024 or len(archive.infolist()) > 5000:
                    raise HTTPException(413, 'The document expands beyond the attachment reading limit.')
        if suffix == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                return {'readable': False, 'text': '', 'notice': 'This PDF is encrypted. Attach an unlocked copy.'}
            parts, size = [], 0
            for page in reader.pages[:50]:
                stream = page.get_contents()
                if stream and len(stream.get_data()) > 5 * 1024 * 1024:
                    notice = 'Some large PDF pages were skipped.'
                    continue
                part = page.extract_text() or ''
                parts.append(part); size += len(part)
                if size >= MAX_TEXT:
                    break
            text = '\n'.join(parts)
            if len(reader.pages) > 50:
                notice += ' Only the first 50 PDF pages were considered.'
            if not text.strip():
                return {'readable': False, 'text': '', 'notice': 'No readable PDF text found. For a scanned document, attach its text or an OCR copy.'}
        elif suffix == '.docx':
            from docx import Document
            document = Document(BytesIO(content))
            parts = [p.text for p in document.paragraphs]
            parts.extend(' | '.join(c.text for c in row.cells) for table in document.tables for row in table.rows)
            text = '\n'.join(parts)
        elif suffix == '.xlsx':
            from openpyxl import load_workbook
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
            parts, size = [], 0
            try:
                for sheet in workbook.worksheets[:10]:
                    parts.append(f'Worksheet: {sheet.title}')
                    for row in sheet.iter_rows(max_row=1000, max_col=40, values_only=True):
                        part = ' | '.join(str(v) if v is not None else '' for v in row)
                        parts.append(part); size += len(part)
                        if size >= MAX_TEXT:
                            break
                    if size >= MAX_TEXT:
                        break
            finally:
                workbook.close()
            text = '\n'.join(parts); notice = 'Spreadsheet preview: up to 10 sheets, 1000 rows and 40 columns per sheet.'
        elif suffix == '.xls':
            import xlrd
            workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
            parts, size = [], 0
            try:
                for sheet in workbook.sheets()[:10]:
                    parts.append(f'Worksheet: {sheet.name}')
                    for i in range(min(sheet.nrows, 1000)):
                        part = ' | '.join(str(v) for v in sheet.row_values(i, 0, min(sheet.ncols, 40)))
                        parts.append(part); size += len(part)
                        if size >= MAX_TEXT:
                            break
                    if size >= MAX_TEXT:
                        break
            finally:
                workbook.release_resources()
            text = '\n'.join(parts); notice = 'Spreadsheet preview: up to 10 sheets, 1000 rows and 40 columns per sheet.'
        else:
            if content.startswith((b'\xff\xfe', b'\xfe\xff')):
                text = content.decode('utf-16')
            elif b'\x00' in content[:8192]:
                return {'readable': False, 'text': '', 'notice': 'Binary attachment cannot be read as chat text. Attach an exported text/source file instead.'}
            else:
                try:
                    text = content.decode('utf-8-sig')
                except UnicodeDecodeError:
                    if suffix not in {'.txt', '.log', '.csv', '.st', '.ab', '.ld', '.var', '.typ', '.src', '.xml', '.iom', '.page', '.algrp', '.txtgrp', '.c', '.h', '.md'}:
                        return {'readable': False, 'text': '', 'notice': 'This attachment format is not readable text. Attach a text export.'}
                    text = content.decode('cp1252', errors='replace')
                    notice = 'Read using Windows text encoding; review any replacement characters.'
        is_log = bool(re.search(r'\b(?:writeBuffer|buffer):\s*\[[^\]]*\]\s*for groupCode\s+\d+', text, re.I))
        truncated = not is_log and len(text) > MAX_TEXT
        return {'readable': bool(text.strip()), 'text': text if is_log else text[:MAX_TEXT],
                'notice': (notice + (' Preview truncated to 60,000 characters.' if truncated else '')).strip()}
    except HTTPException:
        raise
    except (ValueError, OSError, BadZipFile):
        raise HTTPException(422, 'The attachment could not be read. Check its format and attach an unlocked, complete file.')
    except Exception:
        raise HTTPException(422, 'The document could not be read. Attach a text export or check that its reader package is installed.')


@router.post('/api/assist/attachment')
async def read_attachment(file: UploadFile = File(...)):
    try:
        content = await file.read(MAX_FILE + 1)
        if len(content) > MAX_FILE:
            raise HTTPException(413, 'Choose a file smaller than 20 MB.')
        return await run_in_threadpool(preview, file.filename or 'Attachment', content)
    finally:
        await file.close()
