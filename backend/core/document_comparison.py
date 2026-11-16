"""Account-owned file comparisons. Inputs are read-only; no macros/formulas run."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from datetime import date, datetime, time, timezone
from decimal import Decimal
from collections import Counter
from difflib import SequenceMatcher
from itertools import zip_longest
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from backend.core.runtime import WORK

TABLES={'.csv','.xls','.xlsx'}
SUPPORTED=TABLES|{'.pdf','.docx','.txt'}
MAX_BYTES=25*1024**2
MAX_ROWS=50000
MAX_COLUMNS=256
MAX_CELLS=1000000


def fail(message,status=422):raise HTTPException(status,message)


def folder(user):
    if not user or not isinstance(user.get('id'),int):fail('Sign in to compare documents.',403)
    return WORK/'document-comparisons'/str(user['id'])


def record(user,key,kind='uploads'):
    if not re.fullmatch(r'[0-9a-f]{32}',str(key)):fail('Invalid document comparison reference.',400)
    path=folder(user)/kind/key
    if not (path/'record.json').is_file():fail('This comparison file is unavailable for this account.',404)
    data=json.loads((path/'record.json').read_text(encoding='utf8'))
    return path,data


def publish(path,value):
    path.mkdir(parents=True,exist_ok=True)
    tmp=path/'record.tmp'
    tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf8')
    tmp.replace(path/'record.json')


def office_check(path):
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist())>20000 or sum(i.file_size for i in archive.infolist())>120*1024**2:
            fail('The expanded Office document exceeds the comparison limit.')


def csv_rows(path):
    raw=path.read_bytes()
    try:
        text=raw.decode('utf-16') if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode('utf-8-sig')
    except UnicodeDecodeError:fail('Save this CSV using UTF-8 or UTF-16 encoding and upload it again.')
    if '\x00' in text:fail('This is not a readable CSV file.')
    try:dialect=csv.Sniffer().sniff(text[:65536],delimiters=',;\t|')
    except csv.Error:dialect=csv.excel
    result=[];cells=0
    try:
        for row in csv.reader(io.StringIO(text,newline=''),dialect):
            if len(row)>MAX_COLUMNS or len(result)>=MAX_ROWS:fail('CSV comparison supports up to 50,000 rows and 256 columns.')
            cells+=len(row)
            if cells>MAX_CELLS:fail('This CSV exceeds the one-million-cell comparison limit.')
            result.append(row)
    except csv.Error:fail('This CSV contains invalid quoting or an oversized field.')
    return result


def upload(user,name,content):
    name=Path(str(name).replace('\\','/')).name[:180]
    ext=Path(name).suffix.lower()
    if ext not in SUPPORTED:fail('Choose CSV, XLS, XLSX, PDF, DOCX or TXT. Save legacy Word DOC files as DOCX first.',400)
    if not content:fail('The selected file is empty.',400)
    if len(content)>MAX_BYTES:fail('Choose a file up to 25 MB.',413)
    key=uuid4().hex;path=folder(user)/'uploads'/key
    path.mkdir(parents=True,exist_ok=False);source=path/('source'+ext);source.write_bytes(content)
    try:
        sheets=[]
        if ext=='.xlsx':
            office_check(source)
            from openpyxl import load_workbook
            book=load_workbook(source,read_only=True,data_only=True,keep_links=False)
            try:sheets=[{'name':s.title,'rows':s.max_row or 0,'columns':s.max_column or 0} for s in book]
            finally:book.close()
        elif ext=='.xls':
            import xlrd
            book=xlrd.open_workbook(str(source),on_demand=True)
            try:sheets=[{'name':s.name,'rows':s.nrows,'columns':s.ncols} for s in book.sheets()]
            finally:book.release_resources()
        elif ext=='.csv':
            rows=csv_rows(source);sheets=[{'name':'CSV','rows':len(rows),'columns':max(map(len,rows),default=0)}]
        else:
            # Fail unreadable/encrypted inputs before accepting them into the UI.
            text_units(source)
        if len(sheets)>100:fail('Choose a workbook with up to 100 sheets.')
        info={'id':key,'name':name,'extension':ext,'kind':'table' if ext in TABLES else 'text',
              'sha256':hashlib.sha256(content).hexdigest(),'size':len(content),'sheets':sheets}
        publish(path,info)
        return info
    except Exception as error:
        source.unlink(missing_ok=True)
        if isinstance(error,HTTPException):raise
        fail('This file could not be read. Check its format and upload an unlocked, complete copy.')


def source(user,key):
    path,info=record(user,key)
    file=path/('source'+info['extension'])
    if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=info['sha256']:
        fail('The uploaded source changed. Upload the original again.',409)
    return file,info


def number(value):
    if isinstance(value,bool) or not isinstance(value,int):fail('Choose valid sheet, header and column indices.',400)
    return value


def settings(info,config):
    sheet=config.get('sheet')
    header=number(config.get('header_row',1))
    if not any(s['name']==sheet for s in info['sheets']):fail('Choose a sheet from the selected file.',400)
    if not 0<=header<=100:fail('Header row must be 0 (no header) through 100.',400)
    if header>next(s['rows'] for s in info['sheets'] if s['name']==sheet):fail('The header row is outside the selected sheet.',400)
    return sheet,header


def cell(value,kind=None,unknown=False):
    if value is None or value=='':return {'value':'','type':'blank','unknown':unknown}
    if isinstance(value,bool):return {'value':'TRUE' if value else 'FALSE','type':'boolean','unknown':unknown}
    if isinstance(value,(datetime,date,time)):return {'value':value.isoformat(),'type':'date','unknown':unknown}
    if isinstance(value,(int,float,Decimal)):
        if isinstance(value,float) and not math.isfinite(value):return {'value':str(value),'type':'error','unknown':unknown}
        value=format(Decimal(str(value)).normalize(),'f')
        return {'value':value,'type':'number','unknown':unknown}
    value=str(value)
    if len(value)>32768:fail('A cell exceeds the 32,768-character comparison limit.')
    return {'value':value,'type':kind or 'text','unknown':unknown}


def read_table(path,info,sheet,mode='values',limit=None,max_col=None):
    desc=next(s for s in info['sheets'] if s['name']==sheet)
    rows=desc['rows'];cols=min(desc['columns'],max_col or MAX_COLUMNS)
    if limit:rows=min(rows,limit)
    elif rows>MAX_ROWS or rows*cols>MAX_CELLS:fail('The selected sheet exceeds 50,000 rows or one million cells. Split it into smaller files.')
    if info['extension']=='.csv':
        # CSV values remain text: leading zeroes and literal formula-like strings matter.
        return [[cell(v) for v in row[:cols]] for row in csv_rows(path)[:rows]]
    if info['extension']=='.xls':
        if mode=='formulas':fail('Formula-text comparison requires XLSX on both sides. Use stored values for XLS or CSV.',400)
        import xlrd
        book=xlrd.open_workbook(str(path),on_demand=True)
        try:
            s=book.sheet_by_name(sheet);result=[]
            for i in range(rows):
                values=[]
                for j in range(cols):
                    c=s.cell(i,j);value=c.value;kind=None
                    if c.ctype==xlrd.XL_CELL_DATE:
                        value=xlrd.xldate_as_datetime(value,book.datemode)
                        if c.value<1:value=value.time()
                    elif c.ctype==xlrd.XL_CELL_BOOLEAN:value=bool(value)
                    elif c.ctype==xlrd.XL_CELL_ERROR:value=xlrd.error_text_from_code.get(value,'Excel error');kind='error'
                    values.append(cell(value,kind))
                result.append(values)
            return result
        finally:book.release_resources()
    from openpyxl import load_workbook
    formulas=load_workbook(path,read_only=True,data_only=False,keep_links=False)
    values=load_workbook(path,read_only=True,data_only=True,keep_links=False) if mode=='values' else None
    try:
        f=formulas[sheet].iter_rows(max_row=rows,max_col=cols)
        v=values[sheet].iter_rows(max_row=rows,max_col=cols) if values else iter(())
        result=[]
        for row in f:
            cache=next(v,None);items=[]
            for j,c in enumerate(row):
                value=cache[j].value if cache else c.value
                missing=c.data_type=='f' and mode=='values' and value is None
                items.append(cell('[No stored formula result]' if missing else value,'formula' if c.data_type=='f' and mode=='formulas' else 'error' if c.data_type=='e' else None,missing))
            result.append(items)
        return result
    finally:
        formulas.close()
        if values:values.close()


def letter(index):
    from openpyxl.utils import get_column_letter
    return get_column_letter(index+1)


def at(row,index):return row[index] if index<len(row) else cell(None)


def columns(user,key,sheet,header=1):
    path,info=source(user,key)
    if info['kind']!='table':fail('Column selection is available for CSV, XLS and XLSX.',400)
    sheet,header=settings(info,{'sheet':sheet,'header_row':header})
    rows=read_table(path,info,sheet,limit=header+10)
    names=rows[header-1] if header and header<=len(rows) else []
    used=list(range(min(MAX_COLUMNS,next(s['columns'] for s in info['sheets'] if s['name']==sheet))))
    cols=[{'index':i,'letter':letter(i),'name':at(names,i)['value'] or 'Column '+letter(i),'has_data':bool(at(names,i)['value'] or any(at(r,i)['value'] for r in rows[header:]))} for i in used]
    return {'columns':cols,'preview':[{'row':n,'values':[at(r,i)['value'] for i in used[:32]]} for n,r in enumerate(rows[header:header+5],header+1)],
            'notice':'Select the header row (0 means no header). Preview shows the first 32 columns; all available columns through IV can be selected. CSV cells are text.'}


def normalized(c,options):
    value=c['value']
    if options.get('ignore_whitespace'):value=' '.join(value.split())
    if options.get('ignore_case'):value=value.casefold()
    return c['type'] if options.get('compare_types') else '',value


def table_diff(files,infos,configs,options):
    mappings=options.get('columns')
    if not isinstance(mappings,list) or not 1<=len(mappings)<=MAX_COLUMNS:fail('Select at least one column pair to compare.',400)
    pairs=[]
    for m in mappings:
        if not isinstance(m,dict):fail('Choose valid column pairs.',400)
        pair=(number(m.get('base')),number(m.get('compared')))
        if min(pair)<0 or max(pair)>=MAX_COLUMNS:fail('Select columns A through IV.',400)
        pairs.append(pair)
    if len(set(a for a,b in pairs))!=len(pairs) or len(set(b for a,b in pairs))!=len(pairs):fail('Map each selected column only once.',400)
    schemas=[columns_for(path,info,config) for path,info,config in zip(files,infos,configs)]
    for a,b in pairs:
        if a not in schemas[0] or b not in schemas[1]:fail('A mapped column is no longer available. Reload the column selection.',400)
    mode=options.get('value_mode','values')
    if mode not in {'values','formulas'}:fail('Choose stored values or formula text.',400)
    if mode=='formulas' and any(i['extension']!='.xlsx' for i in infos):fail('Formula-text comparison requires XLSX on both sides. Use stored values for XLS or CSV.',400)
    rows=[read_table(path,info,config['sheet'],mode,max_col=max(pair[side] for pair in pairs)+1) for side,(path,info,config) in enumerate(zip(files,infos,configs))]
    data=[[(n,r) for n,r in enumerate(values,1) if n>config['header_row'] and any(at(r,p[side])['value'] for p in pairs)] for side,(values,config) in enumerate(zip(rows,configs))]
    keys=options.get('keys',[])
    if not isinstance(keys,list) or len(keys)>len(pairs) or any(not isinstance(k,int) or isinstance(k,bool) or not 0<=k<len(pairs) for k in keys):fail('Choose valid row-key column pairs.',400)
    if options.get('match_by','row') not in {'row','key'}:fail('Choose row order or key columns.',400)
    if len(set(keys))!=len(keys):fail('Select each row-key column pair once.',400)
    matched=[]
    if options.get('match_by')=='key':
        if not keys:fail('Select at least one row-key column pair.',400)
        lookup=[]
        for side,values in enumerate(data):
            indexed={}
            for n,row in values:
                values_key=[at(row,pairs[k][side]) for k in keys]
                if any(c['type']=='blank' or c['unknown'] for c in values_key):fail(f"{infos[side]['name']}: row {n} has a blank or unavailable key. Choose complete key columns.")
                key=tuple(normalized(c,options) for c in values_key)
                if key in indexed:fail(f"{infos[side]['name']}: duplicate key at rows {indexed[key][0]} and {n}. Add another key column.")
                indexed[key]=(n,row)
            lookup.append(indexed)
        for key in dict.fromkeys([*lookup[0],*lookup[1]]):matched.append((lookup[0].get(key),lookup[1].get(key)))
    else:matched=list(zip_longest(*data))
    if len(matched)*len(pairs)>300000:fail('The result would exceed 300,000 compared cells. Select fewer columns or split the sheet.')
    labels=[{'base':{'index':a,'letter':letter(a),'name':schemas[0][a]},'compared':{'index':b,'letter':letter(b),'name':schemas[1][b]}} for a,b in pairs]
    result=[]
    for index,(left,right) in enumerate(matched,1):
        changes=[]
        for j,(a,b) in enumerate(pairs):
            lc=at(left[1],a) if left else None;rc=at(right[1],b) if right else None
            state='unresolved' if (lc and lc['unknown']) or (rc and rc['unknown']) else 'added' if lc is None else 'removed' if rc is None else 'unchanged' if normalized(lc,options)==normalized(rc,options) else 'modified'
            changes.append({'column':j,'status':state,'base':{**lc,'ref':f"{configs[0]['sheet']}!{letter(a)}{left[0]}"} if lc else None,'compared':{**rc,'ref':f"{configs[1]['sheet']}!{letter(b)}{right[0]}"} if rc else None})
        state='unresolved' if any(c['status']=='unresolved' for c in changes) else 'added' if not left else 'removed' if not right else 'modified' if any(c['status']!='unchanged' for c in changes) else 'unchanged'
        result.append({'id':index,'status':state,'base_ref':f"{configs[0]['sheet']} / row {left[0]}" if left else '', 'compared_ref':f"{configs[1]['sheet']} / row {right[0]}" if right else '',
                       'key':' / '.join(at((left or right)[1],pairs[k][0 if left else 1])['value'] for k in keys) if options.get('match_by')=='key' else '', 'cells':changes})
    notices=['Only selected columns are compared. Empty selected rows are omitted. Formatting and macros are not compared; formulas are never executed.']
    if mode=='values':notices.append('Excel uses stored values, including cached formula results. CSV values remain text. Formula cells without stored results are marked Needs review.')
    if any(s['columns']>MAX_COLUMNS for info in infos for s in info['sheets'] if s['name'] in {c['sheet'] for c in configs}):notices.append('Column selection is limited to A through IV (256 columns).')
    return result,labels,notices


def columns_for(path,info,config):
    sheet,header=settings(info,config);rows=read_table(path,info,sheet,limit=header+10)
    names=rows[header-1] if header and header<=len(rows) else []
    return {i:at(names,i)['value'] or 'Column '+letter(i) for i in range(min(MAX_COLUMNS,next(s['columns'] for s in info['sheets'] if s['name']==sheet)))}


def text_units(path):
    ext=path.suffix.lower();units=[];notices=[];characters=0
    def emit(text,ref,unknown=False):
        nonlocal characters
        characters+=len(text)
        if len(units)>=10000 or characters>1000000:fail('Extracted text exceeds 10,000 lines or one million characters. Split the document.')
        units.append({'value':text,'ref':ref,**({'unknown':True} if unknown else {})})
    def add(text,ref):
        for n,line in enumerate(str(text).splitlines(),1):
            if line.strip():emit(line,ref+f' / line {n}')
    if ext=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(path)
        if reader.is_encrypted:fail('Upload an unlocked PDF for comparison.')
        if len(reader.pages)>250:fail('PDF comparison supports up to 250 pages per file.')
        for n,page in enumerate(reader.pages,1):
            stream=page.get_contents()
            if stream and len(stream.get_data())>10*1024**2:fail(f'PDF page {n} exceeds the text-extraction limit.')
            text=page.extract_text() or ''
            resources=page.get('/Resources')
            resources=resources.get_object() if resources else {}
            if not text.strip() and resources.get('/XObject'):
                emit('[No extractable text; OCR required]',f'Page {n}',True)
                notices.append(f'Page {n} has no extractable text. Upload an OCR/text PDF to compare its content.')
            else:add(text,f'Page {n}')
    elif ext=='.docx':
        office_check(path)
        from docx import Document
        from docx.table import Table
        document=Document(path)
        for n,block in enumerate(document.iter_inner_content(),1):
            if isinstance(block,Table):
                for r,row in enumerate(block.rows,1):add(' | '.join(c.text for c in row.cells),f'Block {n} / table row {r}')
            else:add(block.text,f'Paragraph {n}')
        for label,section in enumerate(document.sections,1):
            for kind,part in [('header',section.header),('footer',section.footer)]:
                for n,p in enumerate(part.paragraphs,1):add(p.text,f'Section {label} / {kind} {n}')
    else:
        raw=path.read_bytes()
        try:text=raw.decode('utf-16') if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode('utf-8-sig')
        except UnicodeDecodeError:fail('Upload a UTF-8 or UTF-16 text file.')
        if '\x00' in text:fail('This is not a readable text document.')
        for n,line in enumerate(text.splitlines(),1):
            if line.strip():emit(line,f'Line {n}')
    if not units or all(u.get('unknown') for u in units):fail('No comparable text was found. For scanned PDFs, upload an OCR/text copy.')
    if len(units)>10000 or sum(len(u['value']) for u in units)>1000000:fail('Extracted text exceeds 10,000 lines or one million characters. Split the document.')
    return units,notices


def text_diff(files,options):
    a,an=text_units(files[0]);b,bn=text_units(files[1]);result=[]
    def norm(units,side):return [f'__unreadable_{side}_{i}__' if u.get('unknown') else normalized({'type':'text','value':u['value']},options)[1] for i,u in enumerate(units)]
    for tag,i,j,k,l in SequenceMatcher(None,norm(a,'base'),norm(b,'compared'),autojunk=True).get_opcodes():
        for left,right in zip_longest(a[i:j],b[k:l]):
            state='unresolved' if (left and left.get('unknown')) or (right and right.get('unknown')) else 'added' if left is None else 'removed' if right is None else 'unchanged' if tag=='equal' else 'modified'
            result.append({'id':len(result)+1,'status':state,'base_ref':left['ref'] if left else '', 'compared_ref':right['ref'] if right else '', 'base':left['value'] if left else '', 'compared':right['value'] if right else ''})
    return result,[],['Text comparison covers extracted text and tables, not page geometry, images, typography or tracked-change history. Blank lines are omitted.']+['Base: '+n for n in an]+['Compared: '+n for n in bn]


def run(user,payload):
    configs=[payload.get('base'),payload.get('compared')]
    if not all(isinstance(c,dict) for c in configs):fail('Select two files to compare.',400)
    configs=[{'id':c.get('id'),'sheet':c.get('sheet',''),'header_row':c.get('header_row',1)} for c in configs]
    inputs=[source(user,c.get('id')) for c in configs];files=[i[0] for i in inputs];infos=[i[1] for i in inputs]
    if infos[0]['kind']!=infos[1]['kind']:fail('Compare two spreadsheets, or compare two text documents (PDF, DOCX or TXT).',400)
    options={k:payload.get(k) for k in ('columns','keys','match_by','value_mode','ignore_case','ignore_whitespace','compare_types','ignore_page_numbers','plc_networks','pixel_compare','compare_author','compare_created','compare_modified','compare_comments','compare_references') if k in payload}
    for k in ('ignore_case','ignore_whitespace','compare_types','ignore_page_numbers','plc_networks','pixel_compare','compare_author','compare_created','compare_modified','compare_comments','compare_references'):
        if k in options and not isinstance(options[k],bool):fail('Choose valid text comparison options.',400)
    pdf=None
    if options.get('plc_networks') and not all(info['extension']=='.pdf' for info in infos):fail('PLC network comparison requires two PDF files.',400)
    try:
        if all(info['extension']=='.pdf' for info in infos):
            if options.get('plc_networks'):
                from backend.core.plc_pdf_comparison import compare
            else:
                from backend.core.document_pdf_comparison import compare
            options.setdefault('ignore_page_numbers',True)
            rows,labels,notices,pdf=compare(files,options)
        else:
            rows,labels,notices=table_diff(files,infos,configs,options) if infos[0]['kind']=='table' else text_diff(files,options)
    except HTTPException:raise
    except Exception:fail('The comparison could not read these files. Upload complete, unlocked copies and check the selection.')
    # Recheck the immutable snapshots before publishing any results.
    for info in infos:source(user,info['id'])
    key=uuid4().hex
    result={'id':key,'kind':infos[0]['kind'],'base':infos[0],'compared':infos[1],'selection':{'base':configs[0],'compared':configs[1],**options},
            'columns':labels,'created_at':datetime.now(timezone.utc).isoformat(),'notices':notices,'rows':rows,
            'summary':{s:sum(r['status']==s for r in rows) for s in ('added','removed','modified','unchanged','unresolved')}}
    if pdf:result['pdf']=pdf
    publish(folder(user)/'results'/key,result)
    return page(user,key)


def filtered(result,status):
    if not isinstance(status,str) or status not in {'all','differences','added','removed','modified','unchanged','unresolved'}:fail('Choose a valid difference filter.',400)
    if result['kind']=='text' and result.get('pdf',{}).get('mode')!='plc_networks' and status=='differences':
        positions=set()
        for i,row in enumerate(result['rows']):
            if row['status']!='unchanged':positions.update(range(max(0,i-5),min(len(result['rows']),i+6)))
        return [r for i,r in enumerate(result['rows']) if i in positions]
    return [r for r in result['rows'] if status=='all' or status=='differences' and r['status']!='unchanged' or status==r['status']]


def column_choice(result,side,column):
    if result['kind']!='table':fail('Header filters are available for spreadsheet comparisons.',400)
    column=number(column)
    if not isinstance(side,str) or side not in {'base','compared'} or not 0<=column<len(result['columns']):fail('Choose a selected spreadsheet column.',400)
    return side,column


def view_settings(result,column_filters=None,sort=None):
    rules=[];seen=set();characters=0;values_count=0
    if column_filters is None:column_filters=[]
    if not isinstance(column_filters,list) or len(column_filters)>64:fail('Use up to 64 column filters.',400)
    for rule in column_filters:
        if not isinstance(rule,dict):fail('Choose valid column filters.',400)
        side,column=column_choice(result,rule.get('side'),rule.get('column'));mode=rule.get('mode');values=rule.get('values')
        if (side,column) in seen or not isinstance(mode,str) or mode not in {'include','exclude'} or not isinstance(values,list):fail('Choose one valid filter per column.',400)
        seen.add((side,column))
        if any(v is not None and (not isinstance(v,str) or len(v)>32768) for v in values):fail('Choose valid filter values.',400)
        characters+=sum(len(v) for v in values if v is not None);values_count+=len(values)
        if characters>200000 or values_count>2000:fail('This filter selection is too large. Select fewer values or exclude the unwanted values.',400)
        rules.append({'side':side,'column':column,'mode':mode,'values':list(dict.fromkeys(values))})
    sorting=None
    if sort is not None:
        if not isinstance(sort,dict):fail('Choose valid column sorting.',400)
        side,column=column_choice(result,sort.get('side'),sort.get('column'));direction=sort.get('direction')
        if not isinstance(direction,str) or direction not in {'asc','desc'}:fail('Choose ascending or descending sorting.',400)
        sorting={'side':side,'column':column,'direction':direction}
    return rules,sorting


def row_value(row,side,column):
    value=row['cells'][column].get(side)
    return None if value is None else value['value']


def sort_value(value):
    if value is not None and len(value)<=256 and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',value.strip()):
        try:return 0,Decimal(value.strip())
        except ArithmeticError:pass
    return 1,str(value).casefold()


def view_rows(result,status,column_filters=None,sort=None):
    rules,sorting=view_settings(result,column_filters,sort);rows=filtered(result,status);status_total=len(rows)
    for rule in rules:
        values=set(rule['values']);include=rule['mode']=='include'
        rows=[row for row in rows if (row_value(row,rule['side'],rule['column']) in values)==include]
    if sorting:
        side=sorting['side'];column=sorting['column']
        present=[r for r in rows if row_value(r,side,column) not in (None,'')]
        empty=[r for r in rows if row_value(r,side,column) in (None,'')]
        rows=sorted(present,key=lambda r:sort_value(row_value(r,side,column)),reverse=sorting['direction']=='desc')+empty
    return rows,rules,sorting,status_total


def page(user,key,status='differences',offset=0,limit=100,column_filters=None,sort=None):
    if offset<0 or not 1<=limit<=200:fail('Use a nonnegative offset and a page size from 1 to 200.',400)
    _,result=record(user,key,'results')
    for side in ('base','compared'):source(user,result[side]['id'])
    rows,rules,sorting,status_total=view_rows(result,status,column_filters,sort)
    return {**result,'rows':rows[offset:offset+limit],'total':len(rows),'offset':offset,'limit':limit,'filter':status,'column_filters':rules,'sort':sorting,'status_total':status_total}


def column_values(user,key,payload):
    _,result=record(user,key,'results');side,column=column_choice(result,payload.get('side'),payload.get('column'))
    rules,_=view_settings(result,payload.get('column_filters'));rules=[r for r in rules if (r['side'],r['column'])!=(side,column)]
    rows,_,_,_=view_rows(result,payload.get('status','differences'),rules)
    query=payload.get('search','');offset=number(payload.get('offset',0));limit=number(payload.get('limit',100))
    if not isinstance(query,str) or len(query)>200 or offset<0 or not 1<=limit<=200:fail('Use a search up to 200 characters and a valid values page.',400)
    counts=Counter(row_value(row,side,column) for row in rows)
    label=lambda value:'(No row)' if value is None else '(Blanks)' if value=='' else value
    values=[v for v in counts if query.casefold() in label(v).casefold()]
    values.sort(key=lambda v:(v is None or v=='',sort_value(v)))
    return {'items':[{'value':v,'label':label(v),'count':counts[v]} for v in values[offset:offset+limit]],'total':len(values),'offset':offset,'limit':limit}


def export_csv(user,key,status='differences',column_filters=None,sort=None):
    _,result=record(user,key,'results')
    for side in ('base','compared'):source(user,result[side]['id'])
    rows,rules,sorting,_=view_rows(result,status,column_filters,sort)
    out=io.StringIO(newline='');writer=csv.writer(out)
    def safe(value):
        value=str(value)
        return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r')) else value
    writer.writerow(['Comparison',result['id'],result['created_at']]);writer.writerow(['Base',safe(result['base']['name']),result['base']['sha256']]);writer.writerow(['Compared',safe(result['compared']['name']),result['compared']['sha256']])
    writer.writerow(['Selection',json.dumps(result['selection'],ensure_ascii=False)]);writer.writerow(['Filter',status])
    if rules or sorting:
        writer.writerow(['Column filters',json.dumps(rules,ensure_ascii=False)]);writer.writerow(['Sort',json.dumps(sorting,ensure_ascii=False)])
    for note in result['notices']:writer.writerow(['Scope',safe(note)])
    writer.writerow(['Status','Row key','Column pair','Base source','Base value','Base type','Compared source','Compared value','Compared type'])
    for row in rows:
        if result['kind']=='table':
            for c in row['cells']:
                label=result['columns'][c['column']];a=c['base'] or {};b=c['compared'] or {}
                writer.writerow([c['status'],safe(row['key']),safe(label['base']['name']+' -> '+label['compared']['name']),safe(a.get('ref','')),safe(a.get('value','')),a.get('type',''),safe(b.get('ref','')),safe(b.get('value','')),b.get('type','')])
        else:writer.writerow([row['status'],'','Text',safe(row['base_ref']),safe(row['base']),'text',safe(row['compared_ref']),safe(row['compared']),'text'])
    return ('\ufeff'+out.getvalue()).encode('utf8')
