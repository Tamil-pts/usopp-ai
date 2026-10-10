from __future__ import annotations

import argparse
import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _clean(value: Any) -> str:
    return str(value or '').replace('\ufeff', '').strip()


def _field(row: dict[str, Any], prefix: str) -> str:
    for key, value in row.items():
        if _clean(key).casefold().startswith(prefix.casefold()):
            return _clean(value)
    return ''


def _group_codes(expression: str) -> tuple[list[int], bool]:
    text=re.sub(r'(?i)nw_group_code', '', expression or '').replace(':', ' ')
    codes=[]; ambiguous=False
    consumed=[]
    for match in re.finditer(r'(\d+)\s*\.\.\s*(\d+)', text):
        start,end=int(match.group(1)),int(match.group(2)); consumed.append(match.span())
        if start<=110 and end-start>=20 and start%10==0 and end%10==0:
            codes.extend(range(start,end+1,10))
        else:
            codes.extend(range(start,end+1)); ambiguous=True
    remaining=text
    for start,end in reversed(consumed): remaining=remaining[:start]+' '+remaining[end:]
    codes.extend(int(value) for value in re.findall(r'\d+',remaining))
    return sorted(set(codes)),ambiguous


def _source_file(explicit: str, note: str, group_expression: str, previous: str) -> str:
    if group_expression:
        return 'mms_nw_rCyclic.st'
    value=_clean(explicit)
    if value:
        low=value.casefold().replace('\\','/')
        if low=='mms_nw_r/cyclic.st': return 'mms_nw_rCyclic.st'
        if low=='mms_pms': return 'mms_pms/Cyclic.st'
        if low=='global declaration': return 'Global declaration files'
        return value
    note_file=re.search(r'([A-Za-z_][\w.-]*\.(?:var|typ|st|c|src))\b',note or '',re.I)
    if note_file: return note_file.group(1)
    return previous


def _memcpy_signatures(logic: str) -> list[dict[str, Any]]:
    pattern=re.compile(
        r'memcpy\s*\(\s*ADR\s*\(\s*nw_snd_buffer\s*\[\s*nw_i[^\]]*\]\s*\)\s*,'
        r'\s*ADR\s*\(\s*(.*?)\s*\)\s*,\s*(\d+)\s*\)\s*;', re.I|re.S)
    rows=[]; matches=list(pattern.finditer(logic))
    for index,match in enumerate(matches):
        tail_end=matches[index+1].start() if index+1<len(matches) else min(len(logic),match.end()+700)
        tail=logic[match.end():tail_end]
        increment=re.search(r'nw_i\s*:=\s*nw_i\s*\+\s*(\d+)\s*;',tail,re.I)
        comment=re.search(r'\(\*\s*(.*?)\s*\*\)',tail,re.S)
        rows.append({
            'parameter':re.sub(r'\s+',' ',match.group(1)).strip(),
            'size':int(match.group(2)),
            'increment':int(increment.group(1)) if increment else None,
            'description':re.sub(r'\s+',' ',comment.group(1)).strip() if comment else '',
        })
    return rows


def _required_snippets(logic: str) -> list[str]:
    clean=re.sub(r'\(\*.*?\*\)', ' ', logic or '', flags=re.S)
    clean=re.sub(r'//[^\r\n]*',' ',clean)
    snippets=[]
    for statement in clean.split(';'):
        value=re.sub(r'\s+',' ',statement).strip()
        if 6<=len(value)<=600 and (':=' in value or re.search(r'\b(?:FOR|IF|CASE)\b',value,re.I)):
            snippets.append(value)
    return snippets[:200]


def _required_declarations(logic: str) -> list[dict[str, Any]]:
    declarations=[]
    pattern=re.compile(r'\b([A-Za-z_]\w*)\s+(BOOL|USINT|SINT|UINT|INT|UDINT|DINT|REAL|LREAL)\s*\[\s*(\d+)\s*\.\.\s*(\d+)\s*\]',re.I)
    for match in pattern.finditer(logic or ''):
        declarations.append({'variable':match.group(1),'datatype':match.group(2).upper(),'lowerBound':int(match.group(3)),'upperBound':int(match.group(4))})
    return declarations


def normalize_checklist(text: str, filename: str, module_id: str='SC-FIN-CHECKLIST',
                        name: str='Spin Connect 2.0 Finisher Checklist', version: str='1.0',
                        machine: str='Finisher') -> dict[str, Any]:
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    rules=[]; blank_rows=[]; last_source='mms_nw_rCyclic.st'; total=0
    for row_number,row in enumerate(reader,start=1):
        total=row_number
        explicit=_field(row,'subroutine /file')
        note=_field(row,'note/instruction')
        group_expression=_field(row,'group code')
        logic=_field(row,'check the logican presence')
        if not any((explicit,note,group_expression,logic)):
            blank_rows.append(row_number); continue
        source=_source_file(explicit,note,group_expression,last_source)
        if explicit and not group_expression: last_source=source
        groups,ambiguous_range=_group_codes(group_expression)
        signatures=_memcpy_signatures(logic)
        snippets=_required_snippets(logic)
        declarations=_required_declarations(logic)
        kind='checklist_packet_signatures' if groups and signatures else 'checklist_source_signatures'
        template_mismatch=(len(groups)>1 and any(re.search(r'(?:PREVIOUS_SHIFT_1|DOFF_REPORT1)',item['parameter'],re.I) for item in signatures))
        ready=kind=='checklist_packet_signatures' and not ambiguous_range and not template_mismatch
        first_names=', '.join(item['parameter'] for item in signatures[:3])
        title=(f'Group {group_expression}: {first_names}' if group_expression else f'{source}: checklist row {row_number}')
        rule={
            'id':f'{module_id}-ROW-{row_number:03d}',
            'name':title[:160],
            'version':version,
            'enabled':False,
            'reviewStatus':'Ready for engineer review' if ready else 'Needs engineer review',
            'kind':kind,
            'sourceRow':row_number,
            'sourceFile':source,
            'groupExpression':group_expression,
            'groupCodes':groups,
            'requiredParameters':signatures,
            'requiredSnippets':snippets,
            'requiredDeclarations':declarations,
            'note':note,
            'expected':f'Checklist row {row_number} logic shall be present in {source}.',
        }
        if ambiguous_range: rule['reviewReason']='Confirm how the Group Code range must expand.'
        elif template_mismatch: rule['reviewReason']='Confirm the per-group shift/report variable substitutions.'
        elif kind=='checklist_source_signatures': rule['reviewReason']='Confirm the source file and exact executable statements.'
        rules.append(rule)
    ready_count=sum(rule['reviewStatus'].startswith('Ready') for rule in rules)
    return {
        'schemaVersion':'1.0',
        'id':module_id,
        'name':name,
        'version':version,
        'enabled':False,
        'kind':'rule_collection',
        'machineScope':[machine],
        'source':{'filename':filename,'format':'csv','importedAt':datetime.now(timezone.utc).isoformat()},
        'importSummary':{
            'totalRows':total,
            'definedRows':len(rules),
            'blankRows':len(blank_rows),
            'blankRowNumbers':blank_rows,
            'readyForReview':ready_count,
            'needsReview':len(rules)-ready_count,
        },
        'rules':rules,
    }


def normalize_checklist_bytes(data: bytes, filename: str, **kwargs) -> dict[str, Any]:
    if len(data)>2*1024*1024:
        raise ValueError('Checklist file must be 2 MB or smaller.')
    for encoding in ('utf-8-sig','utf-8','cp1252'):
        try: return normalize_checklist(data.decode(encoding),filename,**kwargs)
        except UnicodeDecodeError: continue
    raise ValueError('Checklist file encoding is not supported.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True); parser.add_argument('--output',required=True)
    parser.add_argument('--module-id',default='SC-FIN-CHECKLIST'); parser.add_argument('--name',default='Spin Connect 2.0 Finisher Checklist')
    parser.add_argument('--version',default='1.0'); parser.add_argument('--machine',default='Finisher')
    args=parser.parse_args(); source=Path(args.input); output=Path(args.output)
    module=normalize_checklist_bytes(source.read_bytes(),source.name,module_id=args.module_id,name=args.name,version=args.version,machine=args.machine)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(module,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(module['importSummary']))


if __name__=='__main__': main()
