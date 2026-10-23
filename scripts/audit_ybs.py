"""Audit YBS decimal-buffer logs against their sequential Excel metadata.

Usage: python scripts/audit_ybs.py --metadata workbook.xlsx --log capture.txt --output report_folder
No network traffic is sent. Wire assumptions are capture-derived, not a firmware specification.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook, load_workbook
from python_engine.ybs import metadata_rows, parse_frame, decode_values, WIRE_TYPES


def audit(metadata_path, log_path, output):
    book = load_workbook(metadata_path, read_only=True, data_only=True)
    sheet = book.worksheets[0]
    metadata = metadata_rows(sheet.iter_rows(values_only=True), sheet.title)
    book.close()
    groups = defaultdict(list)
    for item in metadata: groups[item['groupCode']].append(item)
    widths = {canonical: width for canonical, width, _ in WIRE_TYPES.values()}
    expected = {gc: max(item['offset']+widths[item['dataType']] for item in items) for gc, items in groups.items()}
    frames, samples, first = [], [], set()
    for line_no, line in enumerate(log_path.read_text(encoding='utf-8-sig').splitlines(), 1):
        match = re.search(r'\b(writeBuffer|buffer):\s*\[([^\]]*)\]\s*for groupCode\s+(\d+)', line, re.I)
        if not match: continue
        tokens = re.split(r'[\s,]+', match[2].strip())
        if any(not token.isdigit() or not 0 <= int(token) <= 255 for token in tokens):
            raise ValueError(f'Log line {line_no}: invalid decimal bytes.')
        raw = bytes(map(int, tokens)); gc = int(match[3]); request = match[1].lower() == 'writebuffer'
        parsed = parse_frame(raw, group=gc)
        logged = re.search(r'\blength\s+(\d+)', line, re.I)
        logged_length = int(logged[1]) if logged else None
        row = dict(line=line_no, direction='request' if request else 'response', groupCode=gc,
                   frameBytes=len(raw), declaredFrameBytes=parsed['frameLength'], loggedLength=logged_length,
                   loggedLengthMatch=logged_length is None or logged_length==len(raw), valid=parsed['success'],
                   payloadBytes=parsed['dataLength'], metadataBytes=expected.get(gc),
                   metadataLengthMatch=None if request else parsed['dataLength']==expected.get(gc),
                   error=parsed['error'], endByte=raw[-1], checksumByte=raw[-2])
        frames.append(row)
        if not request and parsed['success'] and gc not in first:
            first.add(gc)
            samples.extend(dict(logLine=line_no, **item) for item in decode_values(parsed['payload'], groups.get(gc, [])))
    counts = Counter((f['direction'], f['valid']) for f in frames)
    layouts = []
    for gc, items in sorted(groups.items()):
        received = [f for f in frames if f['direction']=='response' and f['groupCode']==gc]
        layouts.append(dict(groupCode=gc, metadataFields=len(items), metadataBytes=expected[gc],
                            receivedDataBytes=sorted(set(f['payloadBytes'] for f in received)), responses=len(received),
                            invalidFrames=sum(not f['valid'] for f in received),
                            firstResponseLine=received[0]['line'] if received else None,
                            layout='mismatch' if any(not f['metadataLengthMatch'] for f in received) else 'length matches; invalid frames cannot verify values' if any(not f['valid'] for f in received) else 'length matches'))
    summary = dict(metadataFile=metadata_path.name, metadataSHA256=hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
                   logSHA256=hashlib.sha256(log_path.read_bytes()).hexdigest(), metadataRows=len(metadata), groups=len(groups),
                   frameLines=len(frames), requests=counts['request',True]+counts['request',False],
                   responses=counts['response',True]+counts['response',False], validResponses=counts['response',True],
                   invalidResponses=counts['response',False], invalidRequests=counts['request',False],
                   assumptions=['F1/F0; header total length; embedded GC; XOR seed FF; big-endian.',
                                'User-confirmed sequential offsets and embedded C widths: UCHAR=1, USINT=2, UINT=4, FLOAT=4 bytes.',
                                'Actual = raw / division factor * multiplication factor; status labels only from explicit bit columns.',
                                'Workbook/device version not independently confirmed. No firmware/source specification supplied.'])
    output.mkdir(parents=True, exist_ok=True)
    (output/'YBS_audit.json').write_text(json.dumps(dict(summary=summary, groups=layouts, frames=frames), indent=2, allow_nan=False), encoding='utf-8')
    workbook = Workbook(); workbook.remove(workbook.active)
    def table(name, rows):
        ws=workbook.create_sheet(name)
        if not rows: return
        keys=list(rows[0]); ws.append(keys)
        for row in rows:
            ws.append([json.dumps(row.get(key),ensure_ascii=False) if isinstance(row.get(key),(dict,list)) else row.get(key) for key in keys])
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    table('Summary', [dict(key=key,value=value) for key,value in summary.items()])
    table('Group layouts', layouts); table('Frame checks', frames)
    keys=('logLine','sourceSheet','sourceRow','groupCode','parameter','wireDataType','dataType','offset','rawHex','rawValue','divideFactor','multiplyFactor','actualValue','units','min','max','qualityIssue','dropdownText')
    table('First valid group samples', [{key:sample.get(key) for key in keys} for sample in samples])
    workbook.save(output/'YBS_audit.xlsx')
    print(json.dumps(summary, indent=2))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata',required=True,type=Path);parser.add_argument('--log',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();audit(args.metadata,args.log,args.output)
