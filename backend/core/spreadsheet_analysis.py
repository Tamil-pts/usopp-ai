"""Account-owned spreadsheet exploration. All displayed statistics use saved cells."""
from __future__ import annotations
import csv
import io
import json
import math
import re
from collections import Counter,OrderedDict
from decimal import Decimal
from pathlib import Path

from backend.core import document_comparison as store


def upload(user,name,content):
    if Path(name or '').suffix.lower() not in store.TABLES:store.fail('Choose CSV, XLS or XLSX.',400)
    if len(content)>20*1024**2:store.fail('Choose a spreadsheet up to 20 MB.',413)
    return store.upload(user,name,content)


def numeric(cell):
    if cell.get('unknown') or cell['type'] in {'date','boolean','error','blank'}:return None
    value=cell['value'].strip()
    # Identifiers such as 001, locale-dependent numbers and percentages remain text.
    if not re.fullmatch(r'[+-]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?',value):return None
    number=Decimal(value)
    if not number.is_finite():return None
    value=float(number)
    if not math.isfinite(value) or value==0 and number!=0:return None
    if number==number.to_integral_value() and abs(number)>9007199254740991:return None
    return number


def finite(value):
    if value is None:return None
    output=float(value)
    if not math.isfinite(output):store.fail('This aggregation exceeds finite numeric limits. Choose another measure.',422)
    return output


def read(user,payload):
    path,info=store.source(user,payload.get('id'))
    if info['kind']!='table':store.fail('Choose a spreadsheet.',400)
    sheet,header=store.settings(info,{'sheet':payload.get('sheet'),'header_row':payload.get('header_row',1)})
    desc=next(s for s in info['sheets'] if s['name']==sheet)
    if desc['columns']>256:store.fail('This workspace supports up to 256 columns per sheet. Select a smaller worksheet.',422)
    raw=store.read_table(path,info,sheet)
    names=raw[header-1] if header else []
    columns=[dict(index=i,letter=store.letter(i),name=store.at(names,i)['value'] or 'Column '+store.letter(i)) for i in range(desc['columns'])]
    rows=[(number,[store.at(row,i) for i in range(len(columns))]) for number,row in enumerate(raw[header:],header+1) if any(c['value'] for c in row)]
    return path,info,sheet,header,columns,rows,len(raw[header:])-len(rows)


def selected(payload,key,columns):
    value=payload.get(key)
    if value is None:return None
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<len(columns):store.fail('Choose a valid '+key.replace('_',' ')+'.',400)
    return value


def quantile(values,fraction):
    position=(len(values)-1)*fraction;index=int(position);weight=Decimal(str(position-index))
    return values[index]+(values[min(index+1,len(values)-1)]-values[index])*weight


def aggregate(rows,metric,operation):
    if operation=='count':return len(rows)
    values=[value for _,row in rows if (value:=numeric(row[metric])) is not None]
    if not values:return None
    total=sum(values,Decimal(0))
    return finite(total if operation=='sum' else total/len(values) if operation=='mean' else min(values) if operation=='min' else max(values))


def analyze(user,payload):
    _,info,sheet,header,columns,rows,empty=read(user,payload)
    group=selected(payload,'group',columns);metric=selected(payload,'metric',columns);pivot=selected(payload,'pivot',columns)
    operation=payload.get('operation','count')
    if operation not in {'count','sum','mean','min','max'}:store.fail('Choose Count, Sum, Mean, Minimum or Maximum.',400)
    if operation!='count' and metric is None:store.fail('Choose a numeric measure for this aggregation.',400)
    profiles=[];issues=[]
    for column in columns:
        i=column['index'];values=[(number,numeric(row[i])) for number,row in rows];valid=[v for _,v in values if v is not None]
        blanks=[number for number,row in rows if row[i]['value']==''];errors=[number for number,row in rows if row[i]['type']=='error' or row[i].get('unknown')]
        profile={**column,'numeric':len(valid),'missing':len(blanks),'errors':len(errors),'distinct':len({(row[i]['type'],row[i]['value']) for _,row in rows}),
                 'sum':finite(sum(valid,Decimal(0))) if valid else None,'mean':finite(sum(valid,Decimal(0))/len(valid)) if valid else None,
                 'min':finite(min(valid)) if valid else None,'max':finite(max(valid)) if valid else None}
        profiles.append(profile)
        if blanks:issues.append(dict(kind='missing',column=i,count=len(blanks),cells=[f'{column["letter"]}{n}' for n in blanks[:12]]))
        if errors:issues.append(dict(kind='error',column=i,count=len(errors),cells=[f'{column["letter"]}{n}' for n in errors[:12]]))
    if metric is not None and operation!='count' and not profiles[metric]['numeric']:store.fail('This measure has no finite numeric cells. Numbers with units, IDs with leading zeroes and ambiguous locale formats remain text.',422)
    def key(row,index):return ('all','All rows') if index is None else (row[index]['type'],row[index]['value'])
    buckets=OrderedDict();matrix=OrderedDict();pivot_keys=OrderedDict()
    for number,row in rows:
        identity=key(row,group);buckets.setdefault(identity,[]).append((number,row))
        if pivot is not None:
            pk=key(row,pivot);pivot_keys[pk]=None;matrix.setdefault((identity,pk),[]).append((number,row))
    order=payload.get('order','source')
    if order not in {'source','label','value_desc','value_asc'}:store.fail('Choose a valid chart order.',400)
    categories=[dict(id=json.dumps(identity),label=identity[1] or '(blank)',type=identity[0],value=aggregate(items,metric,operation),rows=len(items),source_rows=[n for n,_ in items]) for identity,items in buckets.items()]
    if order=='label':categories.sort(key=lambda item:item['label'])
    if order.startswith('value_'):categories.sort(key=lambda item:(item['value'] is None,(-1 if order=='value_desc' else 1)*(item['value'] or 0)))
    outliers=[];outlier_count=0;bounds=None
    if metric is not None:
        pairs=[(number,value) for number,row in rows if (value:=numeric(row[metric])) is not None]
        if len(pairs)>=4:
            values=sorted(v for _,v in pairs);q1,q3=quantile(values,.25),quantile(values,.75);spread=q3-q1;low,high=q1-spread*Decimal('1.5'),q3+spread*Decimal('1.5')
            marked=[dict(row=number,cell=f'{columns[metric]["letter"]}{number}',value=finite(value)) for number,value in pairs if value<low or value>high]
            outlier_count=len(marked);outliers=marked[:100];bounds=dict(q1=finite(q1),q3=finite(q3),lower=finite(low),upper=finite(high))
    duplicates=len(rows)-len({tuple((c['type'],c['value']) for c in row) for _,row in rows})
    pivots=list(pivot_keys)[:30];group_keys=list(buckets)[:100]
    pivot_table=dict(columns=[dict(id=json.dumps(k),label=k[1] or '(blank)') for k in pivots],rows=[dict(label=k[1] or '(blank)',values=[aggregate(matrix.get((k,p),[]),metric,operation) for p in pivots]) for k in group_keys]) if pivot is not None else None
    notes=['Values are read from the selected saved worksheet. Formulas are not executed; missing cached results remain errors.',
           'Empty rows are excluded. Source row numbers and column letters retain their original positions.',
           'Count counts rows. Other aggregations exclude blank, error, date, boolean and nonnumeric cells. No locale or engineering unit is inferred.',
           'Numbers beyond finite chart precision and integers above 9,007,199,254,740,991 remain source text. Numeric charts use floating-point values; original cells remain downloadable.',
           'IQR outliers are statistical review candidates, not proven defects or causes. No engineering risk threshold is assumed.']
    if len(categories)>500:notes.append(f'Charts show 500 of {len(categories)} groups; KPI and profile calculations still cover all {len(rows)} rows. Download the worksheet for all cells.')
    if pivot is not None and (len(pivot_keys)>30 or len(buckets)>100):notes.append('Pivot preview is limited to 100 row groups and 30 column groups. Empty intersections remain blank except Count, which is zero.')
    if outlier_count>100:notes.append(f'The first 100 of {outlier_count} IQR outliers are displayed.')
    recommendations=[]
    for issue in issues[:8]:recommendations.append(f'Review {issue["count"]} {"missing cells" if issue["kind"]=="missing" else "unreadable or error cells"} in {columns[issue["column"]]["name"]} ({columns[issue["column"]]["letter"]}); for example {", ".join(issue["cells"][:4])}.')
    if duplicates:recommendations.append(f'Review {duplicates} repeated complete rows before deciding whether deduplication is appropriate. No rows were removed.')
    if outlier_count:recommendations.append(f'Check {outlier_count} IQR candidates against their source rows and an approved limit before treating them as defects.')
    if not recommendations:recommendations.append('No missing cells, spreadsheet errors or duplicate complete rows were found by these checks. '+('No selected-measure IQR candidates were found. ' if bounds else 'IQR outliers were not assessed; select a numeric measure with at least four finite values. ')+'Confirm units and acceptance criteria before making an engineering decision.')
    source=dict(file=info['name'],id=info['id'],sheet=sheet,header_row=header,sha256=info['sha256'])
    store.source(user,info['id'])
    return dict(source=source,columns=profiles,rows=len(rows),empty_rows=empty,blank_cells=sum(p['missing'] for p in profiles),error_cells=sum(p['errors'] for p in profiles),duplicates=duplicates,
                value=aggregate(rows,metric,operation),metric=metric,group=group,pivot=pivot,operation=operation,order=order,categories=categories[:500],group_count=len(categories),
                outliers=outliers,outlier_count=outlier_count,outlier_bounds=bounds,pivot_table=pivot_table,issues=issues,recommendations=recommendations,notes=notes,
                preview=[dict(row=n,cells=[c['value'] for c in row]) for n,row in rows[:100]],preview_total=len(rows))


def safe(value):return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r')) else value


def preview_rows(user,payload):
    _,info,_,_,columns,rows,_=read(user,payload)
    group=selected(payload,'group',columns);identity=payload.get('category_id')
    if not isinstance(identity,str) or len(identity)>33000:store.fail('Choose a chart category.',400)
    selected_rows=[(n,row) for n,row in rows if json.dumps(('all','All rows') if group is None else (row[group]['type'],row[group]['value']))==identity]
    store.source(user,info['id'])
    return dict(rows=[dict(row=n,cells=[c['value'] for c in row]) for n,row in selected_rows[:100]],total=len(selected_rows))


def export(user,payload,format):
    if format=='json':return json.dumps(analyze(user,payload),ensure_ascii=False,allow_nan=False).encode('utf8')
    _,info,sheet,_,columns,rows,_=read(user,payload)
    headers=[c['name'] for c in columns]
    if format=='csv':
        out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow([safe(h) for h in headers])
        writer.writerows([c['value'] if numeric(c) is not None else safe(c['value']) for c in row] for _,row in rows)
        data=b'\xef\xbb\xbf'+out.getvalue().encode('utf8')
    elif format=='xlsx':
        from openpyxl import Workbook
        book=Workbook();ws=book.active;ws.title=sheet[:31];ws.append([safe(h) for h in headers]);ws.freeze_panes='A2'
        for _,row in rows:ws.append([finite(numeric(c)) if c['type']=='number' and numeric(c) is not None else safe(c['value']) for c in row])
        ws.auto_filter.ref=ws.dimensions;out=io.BytesIO();book.save(out);book.close();data=out.getvalue()
    else:store.fail('Choose CSV, XLSX or JSON.',400)
    store.source(user,info['id']);return data
