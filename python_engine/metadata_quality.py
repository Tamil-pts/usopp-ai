"""Read-only metadata quality checks. No workbook values or schema are changed."""
from collections import defaultdict
import importlib.util
import math
from pathlib import Path
import re
import sys

# The established engine filename contains a version dot, so load it with the
# same file-based import mechanism used by the engine regression checks.
_engine_path=Path(__file__).with_name('packet_validation_report_uSOPp_v1.71_final.py')
if not _engine_path.is_file():_engine_path=_engine_path.with_suffix('.pyc')
_spec=importlib.util.spec_from_file_location('usopp_metadata_quality_packet_types',_engine_path)
_engine=importlib.util.module_from_spec(_spec)
sys.modules[_spec.name]=_engine
_spec.loader.exec_module(_engine)
BASE_TYPE_SIZES=_engine.BASE_TYPE_SIZES
metadata_output_type=_engine.metadata_output_type
metadata_type_compatibility=_engine.metadata_type_compatibility
normalize_type_name=_engine.normalize_type_name
parse_type_expr=_engine.parse_type_expr


def header(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').casefold())


def clean(value):
    text = str(value if value is not None else '').strip()
    return '' if text.casefold() in {'<null>', 'null', 'none'} else text


def integer(value):
    if isinstance(value, bool) or not clean(value):
        return None
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def identity(value):
    number = integer(value)
    return str(number) if number is not None else clean(value).casefold()


def machine_variant(value):
    normalized=identity(value)
    return 'both' if normalized in {'', 'both', 'all', 'all variants', 'allvariants', '*'} else normalized


def wire_size(datatype):
    """Use the packet engine's type parser and its 50-byte STRING contract."""
    raw = clean(datatype).upper()
    if not raw:
        return None
    normalized = metadata_output_type(raw)
    if normalized == 'STRING':
        return 50
    parsed = parse_type_expr(raw)
    if parsed.kind == 'array' and parsed.array_range:
        count = parsed.array_range[1] - parsed.array_range[0] + 1
        element = wire_size(parsed.base)
        return count * element if count > 0 and element else None
    return BASE_TYPE_SIZES.get(normalize_type_name(normalized))


def source_fields(data, kind):
    """Offsets in these engine records already exclude the five-byte header."""
    output = []
    if kind == 'generated':
        for index, row in enumerate(data.get('records', []), 2):
            output.append({'sheet': data.get('sheetName', ''), 'row': index,
                           'groupCode': row.get('group_code'), 'tagCode': row.get('tag_code'),
                           'parameter': row.get('parameter'), 'offset': row.get('offset'),
                           'size': row.get('size'), 'dataType': row.get('datatype'),
                           'plcTag': row.get('plc_tag', '')})
    else:
        for row in data.get('metadataComparison', {}).get('results', []):
            if row.get('plcOffset') is None or not row.get('metadataSheet') or not row.get('metadataRow'):
                continue
            output.append({'sheet': row['metadataSheet'], 'row': row['metadataRow'],
                           'groupCode': row.get('groupCode'), 'tagCode': row.get('metadataTagCode'),
                           'parameter': row.get('metadataParameterName'), 'offset': row['plcOffset'],
                           'size': row.get('plcSize'), 'dataType': row.get('plcType'),
                           'plcTag': row.get('plcTag', ''), 'sourceFile': row.get('logicSourceFile', ''),
                           'lineNumber': row.get('logicLineNumber')})
    return output


def _stage(name, issues, checked, detail):
    status = 'FAIL' if any(issue['status'] == 'FAIL' for issue in issues) else 'REVIEW' if issues else 'PASS'
    return {'id': name, 'status': status, 'checked': checked, 'issues': issues, 'detail': detail}


def inspect_workbook(sheets, reference=None):
    if not isinstance(sheets, list) or len(sheets) > 100:
        raise ValueError('Supply the metadata workbook worksheets.')
    metadata = []
    mappings = []
    byte_issues = []
    mapping_issues = []
    duplicate_issues = []
    reference = reference or []
    source_by_position = {(row.get('sheet'), integer(row.get('row'))): row for row in reference}

    def issue(target, row, check, expected, actual, status='FAIL'):
        item = {'sheet': row.get('sheet', ''), 'row': row.get('row'),
                'groupCode': row.get('groupCode'), 'tagCode': row.get('tagCode'), 'parameter': row.get('parameter', ''),
                'check': check, 'expected': expected, 'actual': actual, 'status': status}
        if item not in target:
            target.append(item)

    for sheet in sheets:
        if not isinstance(sheet, dict) or not isinstance(sheet.get('rows'), list):
            raise ValueError('Each worksheet must contain its existing rows.')
        if not isinstance(sheet.get('headers'),list) or any(not isinstance(key,str) for key in sheet['headers']) or any(not isinstance(record,dict) for record in sheet['rows']):
            raise ValueError('Keep worksheet headers as text and rows as cell records.')
        if len(sheet['rows']) > 50000:
            raise ValueError('A worksheet can contain at most 50,000 metadata rows.')
        headers = {header(key): key for key in sheet.get('headers', [])}
        column = lambda *names: next((headers[name] for name in names if name in headers), '')
        if header(sheet.get('name')) == 'sheet2':
            tag = column('tagcode'); plc = column('plcval', 'plcvalue'); shown = column('shownval', 'shownvalue')
            variant = column('machinevariant', 'machinevariants', 'machinevarients')
            for index, record in enumerate(sheet['rows'], 2):
                if not any(clean(value) for value in record.values()):
                    continue
                row = {'sheet': sheet['name'], 'row': index, 'tagCode': identity(record.get(tag)),
                       'plcValue': identity(record.get(plc)), 'shownValue': clean(record.get(shown)),
                       'variant': machine_variant(record.get(variant))}
                mappings.append(row)
                if not tag or not plc or not shown or not row['tagCode'] or not row['plcValue'] or not row['shownValue']:
                    issue(mapping_issues, row, 'Incomplete Sheet2 mapping', 'TAG_CODE, PLCVAL and SHOWNVAL', 'Missing column or value')
            continue
        group = column('groupcode', 'group', 'groupid'); parameter = column('parameters', 'parameter', 'parametername')
        if not group or not parameter:
            continue
        offset = column('offsetfromthestartofthegroupinbytes', 'offset', 'byteoffset', 'offsetinbytes')
        dtype = column('tagdatatype', 'datatype', 'type')
        variant = column('machinevariants', 'machinevariant', 'machinevarients')
        tag = column('tagcode'); shown = column('isshownvaluedifferent', 'shownvaluedifferent')
        lower = column('fromversion'); upper = column('toversion')
        for index, record in enumerate(sheet['rows'], 2):
            if not any(clean(value) for value in record.values()):
                continue
            row = {'sheet': sheet['name'], 'row': index, 'groupCode': integer(record.get(group)),
                   'parameter': clean(record.get(parameter)), 'dataType': clean(record.get(dtype)),
                   'offset': integer(record.get(offset)), 'offsetValue': record.get(offset),
                   'variant': machine_variant(record.get(variant)), 'tagCode': identity(record.get(tag)),
                   'shownDifferent': clean(record.get(shown)).casefold() in {'yes', 'true', '1'},
                   'version': (clean(record.get(lower)), clean(record.get(upper))),
                   'size': wire_size(record.get(dtype)), 'expectedOffsets': [], 'sourceOffset': None}
            metadata.append(row)
            if row['groupCode'] is None or row['groupCode'] < 0:
                issue(byte_issues, row, 'Invalid Group Code', 'A non-negative integer', record.get(group))
            if not row['parameter']:
                issue(byte_issues, row, 'Missing parameter', 'A parameter name', record.get(parameter))
            if row['offset'] is None or row['offset'] < 0:
                issue(byte_issues, row, 'Invalid byte offset', 'A non-negative whole number of bytes', record.get(offset))
            if not row['size']:
                issue(byte_issues, row, 'Unresolved datatype size', 'A supported PLC wire datatype', row['dataType'] or 'Missing', 'REVIEW')
            source = source_by_position.get((row['sheet'], index))
            if source:
                row['sourceOffset'] = integer(source.get('offset'))
                row['sourceFile'] = source.get('sourceFile', '')
                row['lineNumber'] = source.get('lineNumber')
                if row['groupCode'] != integer(source.get('groupCode')):
                    issue(byte_issues, row, 'PLC Group Code mismatch', source.get('groupCode'), row['groupCode'])
                if row['offset'] != row['sourceOffset']:
                    issue(byte_issues, row, 'PLC byte offset mismatch', row['sourceOffset'], row['offsetValue'])
                source_size = integer(source.get('size'))
                if source_size and row['size'] and source_size != row['size']:
                    issue(byte_issues, row, 'PLC field size mismatch', source_size, row['size'])
                if not row['size'] and source_size:
                    row['size'] = source_size
                if source.get('dataType') and row['dataType']:
                    match = metadata_type_compatibility(source['dataType'], row['dataType'], row['groupCode'], source_size)
                    if match != 'EXACT':
                        issue(byte_issues, row, 'PLC datatype mismatch', source['dataType'], row['dataType'], 'REVIEW' if match == 'WARNING' else 'FAIL')
            elif reference:
                issue(byte_issues, row, 'PLC source row unavailable', 'A matching source row from this workbook validation', 'Not checked', 'REVIEW')

    buckets = defaultdict(list)
    for row in metadata:
        buckets[(row['sheet'], row['groupCode'], row['version'])].append(row)
    for rows in buckets.values():
        variants = {row['variant'] for row in rows if row['variant'] not in {'both', 'all'}} or {'both'}
        for variant in sorted(variants):
            cursor = 0
            for row in rows:
                if row['variant'] not in {'both', 'all', variant}:
                    continue
                if cursor is not None and cursor not in row['expectedOffsets']:
                    row['expectedOffsets'].append(cursor)
                if cursor is not None and row['offset'] is not None and cursor != row['offset']:
                    issue(byte_issues, row, 'Offset gap' if row['offset'] > cursor else 'Offset overlap', cursor, row['offset'])
                cursor = cursor + row['size'] if cursor is not None and row['size'] else None

    duplicate_buckets = defaultdict(list)
    tags = defaultdict(list)
    for row in metadata:
        name = re.sub(r'\s+', ' ', row['parameter']).casefold()
        if row['groupCode'] is not None and name:
            duplicate_buckets[(row['sheet'], row['groupCode'], name)].append(row)
        if row['tagCode']:
            tags[row['tagCode']].append(row)
    for rows in duplicate_buckets.values():
        if len(rows) > 1:
            for row in rows:
                issue(duplicate_issues, row, 'Duplicate parameter', 'One parameter per Group Code', f'{len(rows)} matching rows')
    mapped = defaultdict(list)
    for row in mappings:
        if row['tagCode'] not in tags:
            issue(mapping_issues, row, 'Orphan Sheet2 tag', 'TAG_CODE present in metadata', row['tagCode'])
        key = (row['tagCode'], row['plcValue'], row['variant'])
        mapped[key].append(row)
    for rows in mapped.values():
        if len(rows) > 1:
            for row in rows:
                issue(mapping_issues, row, 'Duplicate Sheet2 mapping', 'One mapping per tag, PLC value and variant', len(rows))
    for row in metadata:
        if row['shownDifferent'] and not any(mapping['tagCode'] == row['tagCode'] and mapping['plcValue'] and mapping['shownValue'] and
                (row['variant'] in {'both', 'all'} or mapping['variant'] in {'both', 'all', row['variant']}) for mapping in mappings):
            issue(mapping_issues, row, 'Missing Sheet2 mapping', f"Mapping for TAG_CODE {row['tagCode']}", 'Not found')

    if not metadata:
        issue(byte_issues, {}, 'Metadata rows unavailable', 'A metadata worksheet with Group Code and Parameters', 'Not found', 'REVIEW')
    structural = _stage('bytes', byte_issues, len(metadata), 'Offsets are payload-relative; the five-byte packet header is excluded.')
    structural['workbookStatus'] = structural['status']
    structural['sourceCompared'] = bool(reference)
    if not reference and structural['status'] == 'PASS':
        structural['status'] = 'REVIEW'
        structural['detail'] += ' Workbook layout passed; run project validation to verify it against PLC source.'
    sheet2 = _stage('sheet2', mapping_issues, len(mappings), 'Mappings are checked by TAG_CODE, PLCVAL and machine variant.')
    if not mappings and not any(row['shownDifferent'] for row in metadata):
        sheet2['status'] = 'NOT_APPLICABLE'
        sheet2['detail'] = 'No displayed-value mappings are required by this workbook.'
    duplicates = _stage('duplicates', duplicate_issues, len(metadata), 'Duplicate names are checked within each worksheet and Group Code.')
    for row in metadata:
        row['issues'] = [issue for issue in byte_issues if issue['sheet'] == row['sheet'] and issue['row'] == row['row']]
        row['status'] = 'FAIL' if any(issue['status'] == 'FAIL' for issue in row['issues']) else 'REVIEW' if row['issues'] else 'PASS'
    return {'stages': [structural, sheet2, duplicates], 'offsetRows': metadata,
            'metadata': [{'parameter': row['parameter'], 'groupCode': row['groupCode'], 'dataType': row['dataType'], 'tagCode': row['tagCode']} for row in metadata]}
