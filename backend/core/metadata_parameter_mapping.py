"""Resolve a workbook rename to an exact PLC identity before sharing it."""
from __future__ import annotations

import json
import hashlib
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException


def name_key(value):
    # Use the same identity normalization as the metadata generator.
    return re.sub(r'[^A-Z0-9]+', '', str(value or '').upper())


def header_key(value):
    return name_key(value).lower()


def number_key(value):
    try:
        number = Decimal(str(value).strip())
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


IDENTITY_HEADERS = (
    ('groupcode', 'group', 'groupid'), ('tagcode',),
    ('offsetfromthestartofthegroupinbytes', 'offset', 'byteoffset', 'offsetinbytes'),
    ('tagdatatype', 'datatype'),
)


def row_identity(row):
    fields = {header_key(key): value for key, value in row.items()}
    values = [next((fields[key] for key in keys if key in fields), None) for keys in IDENTITY_HEADERS]
    return tuple(number_key(value) for value in values[:3]) + (name_key(values[3]),)


def row_variant(row):
    return next((str(value or '').strip().casefold() for key, value in row.items()
                 if header_key(key) in {'machinevariant', 'machinevariants', 'machinevarients'}), '')


def source_revision(mapping):
    return hashlib.sha256(json.dumps(mapping, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def department_key(value):
    return str(value or 'All').strip().casefold()


def mapping_matches(row, mapping):
    return (all(name_key(row.get(key)) == name_key(mapping[key]) for key in ('plc_parameter', 'plc_tag'))
            and department_key(row.get('machine_department')) == department_key(mapping['machine_department']))


def resolve_parameter(payload, path, sheets, folder):
    """Do not infer a PLC tag from a metadata label or from row order alone."""
    sheet_name = str(payload.get('sheetName') or '')
    row_number = payload.get('rowNumber')
    if header_key(sheet_name) == 'sheet2':
        raise HTTPException(400, 'Sheet2 labels are not PLC parameter-name mappings.')
    sheet = next((item for item in sheets if item['name'] == sheet_name), None)
    if not sheet or type(row_number) is not int or not 2 <= row_number <= len(sheet['rows']) + 1:
        raise HTTPException(400, 'Select an existing metadata parameter row.')
    original = sheet['rows'][row_number - 2]
    parameter_header = next((key for key in sheet['headers'] if header_key(key) in {'parameters', 'parameter', 'parametername'}), None)
    if not parameter_header:
        raise HTTPException(400, 'This worksheet has no parameter-name column.')
    identity = row_identity(original)
    edited = payload.get('row')
    if not isinstance(edited, dict) or row_identity(edited) != identity or row_variant(edited) != row_variant(original):
        raise HTTPException(409, 'Group Code, TAG_CODE, datatype, offset or machine variant changed. Save and validate this workbook before creating a master mapping.')
    if any(value is None for value in identity[:3]) or not identity[3]:
        raise HTTPException(400, 'The row needs a Group Code, TAG_CODE, datatype and byte offset to identify its PLC parameter.')

    manifest_file = folder / 'inputs.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8-sig')) if manifest_file.is_file() else {}
    generated = payload.get('source') == 'generated'
    original_path = manifest.get('generated' if generated else 'uploaded')
    if not original_path or Path(original_path).resolve() != path.resolve():
        raise HTTPException(409, 'This PLC result belongs to a different workbook. Validate the selected workbook first.')
    result_file = folder / ('generated_metadata.json' if generated else 'validation_results.json')
    if not result_file.is_file():
        raise HTTPException(400, 'Generate metadata or validate this workbook with its PLC project first to fill the PLC tag and comment.')
    result = json.loads(result_file.read_text(encoding='utf-8-sig'))
    department = str(manifest.get('machineDepartment') or result.get('machineDepartment') or '').strip()
    if not department or department.casefold() == 'all':
        raise HTTPException(400, 'Choose a department and run generation or validation before sharing this mapping.')

    candidates = []
    if generated:
        if result.get('sheetName') != sheet_name:
            raise HTTPException(409, 'The generated PLC result belongs to a different worksheet.')
        for record in result.get('records', []):
            key = tuple(number_key(record.get(field)) for field in ('group_code', 'tag_code', 'offset')) + (name_key(record.get('datatype')),)
            if key == identity:
                candidates.append({'plc_tag': record.get('plc_tag'), 'plc_parameter': record.get('plc_parameter'),
                                   'sourceFile': record.get('source_file', ''), 'lineNumber': record.get('line_number')})
    else:
        for record in result.get('metadataComparison', {}).get('results', []):
            if record.get('metadataSheet') != sheet_name or record.get('metadataRow') != row_number:
                continue
            key = tuple(number_key(record.get(field)) for field in ('metadataGroupCode', 'metadataTagCode', 'metadataOffset')) + (name_key(record.get('metadataType')),)
            if (key == identity and number_key(record.get('groupCode')) == identity[0]
                    and number_key(record.get('plcOffset')) == identity[2]
                    and record.get('datatypeCompatibility') == 'EXACT'):
                tag = str(record.get('plcTag') or '').strip()
                comment = str(record.get('logicComment') or record.get('logicDescription') or '').strip()
                if name_key(comment) in {'', 'NODESCRIPTION', 'NOTAVAILABLE', 'NONE'}:
                    comment = tag
                candidates.append({'plc_tag': tag, 'plc_parameter': comment,
                                   'sourceFile': record.get('logicSourceFile', ''), 'lineNumber': record.get('logicLineNumber')})
    identities = {(name_key(item['plc_parameter']), name_key(item['plc_tag'])) for item in candidates}
    if len(identities) != 1 or any(not value for value in next(iter(identities), ('', ''))):
        raise HTTPException(409, 'No unique PLC tag and comment match this row. Check its PLC group, datatype and byte offset in validation first. Your workbook edit is kept.')
    return {**candidates[0], 'machine_department': department, 'groupCode': str(identity[0]),
            'tagCode': str(identity[1]), 'originalName': str(original[parameter_header] or '')}


def upsert_rename(document, mapping, new_name):
    """Update just the approved name, preserving limits, factors and other rules."""
    mappings = document.setdefault('mappings', [])
    matches = [row for row in mappings if mapping_matches(row, mapping)]
    if len(matches) > 1:
        raise HTTPException(409, 'Multiple master mappings use this PLC tag and comment in this department. Resolve them in KnowHub before saving.')
    if matches:
        matches[0].update(metadata_parameter=new_name, status='configured')
    else:
        # A department rename must retain settings inherited from an All rule.
        inherited = [row for row in mappings if mapping_matches(row, {**mapping, 'machine_department': 'All'})]
        if len(inherited) > 1:
            raise HTTPException(409, 'Multiple shared master mappings use this PLC identity. Resolve them in KnowHub before saving.')
        mappings.append({**(inherited[0] if inherited else {}),
                         **{key: mapping[key] for key in ('plc_parameter', 'plc_tag', 'machine_department')},
                         'metadata_parameter': new_name, 'status': 'configured'})
