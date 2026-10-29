"""Replace the shared Database JSON Keys with an authoritative shortlisted CSV."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import uuid

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from backend.core.data_models import SERVICES, machine_key, parse_model

SCOPE_FIELDS = ('Service', 'Department', 'JSON collection')
BOOL_FIELDS = {'isRequired', 'IsRequired', 'isAutoCalc', 'isHost', 'isHours',
               'numericValueType', 'ignoreNameSeparators'}
NULLABLE_FIELDS = {'groupCode', 'tdEngineKey', 'mongoKey', 'formula', 'type'}
INDIA = timezone(timedelta(hours=5, minutes=30))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')


def parse_shortlist(raw):
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError('The CSV exceeds 20 MB.')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    headers = reader.fieldnames or []
    required = {*SCOPE_FIELDS, 'tagName', 'dataType'}
    if not required.issubset(headers) or any(not key for key in headers) or len(set(headers)) != len(headers):
        raise ValueError('CSV needs unique headers including Service, Department, JSON collection, tagName and dataType.')
    sources = {}
    count = 0
    for number, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f'CSV row {number}: the cell count does not match the header.')
        if not any(value.strip() for value in row.values()):
            continue
        service, department, collection = (row[key].strip() for key in SCOPE_FIELDS)
        service = service.upper()
        if service not in SERVICES:
            raise ValueError(f'CSV row {number}: choose PMS, QMS or CMS.')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', department):
            raise ValueError(f'CSV row {number}: use a department identifier without paths or punctuation.')
        prefix = f'{service}_{department}_'.casefold()
        if not collection.casefold().startswith(prefix):
            raise ValueError(f'CSV row {number}: collection must begin with {prefix}.')
        record = {}
        for field in headers:
            if field in SCOPE_FIELDS:
                continue
            value = row[field]
            if field in BOOL_FIELDS:
                if not value.strip():
                    continue  # Missing union-export fields stay absent, not false.
                if value.strip().casefold() not in {'true', 'false', '1', '0', 'yes', 'no'}:
                    raise ValueError(f'CSV row {number}: {field} must be true or false.')
                record[field] = value.strip().casefold() in {'true', '1', 'yes'}
            elif not value:
                if field in NULLABLE_FIELDS:
                    record[field] = None
            else:
                # IDs, H-suffixed groups, formulas, labels and database names
                # are kept verbatim; do not guess types or repair CSV wording.
                record[field] = value
        if not str(record.get('tagName') or '').strip() or not str(record.get('dataType') or '').strip():
            raise ValueError(f'CSV row {number}: tagName and dataType are required.')
        sources.setdefault((service, department), {}).setdefault(collection, []).append(record)
        count += 1
    if not count:
        raise ValueError('The shortlist contains no records; the existing dataset was not changed.')
    return sources, count


def build_plan(csv_path: Path, output: Path):
    raw = csv_path.read_bytes()
    sources, count = parse_shortlist(raw)
    previous = json.loads((output/'catalog.json').read_text(encoding='utf-8'))
    previous_manifest = json.loads((output/'source_manifest.json').read_text(encoding='utf-8'))
    previous_source_rows = 0
    for item in previous_manifest['fixedModels']:
        source = (output/'reference_sources'/item['originalSource']).resolve()
        if not source.is_relative_to((output/'reference_sources').resolve()):
            raise ValueError('An existing source escaped the data-model directory.')
        definition = json.loads(source.read_text(encoding='utf-8-sig'))
        prefix = (item['service']+'_'+item['department']+'_').casefold()
        previous_source_rows += sum(len(rows) for name, rows in definition['keysList'].items()
                                    if name.casefold().startswith(prefix))
    prior_models = {(model['service'], machine_key(model['machine'])): model for model in previous['models']}
    departments = {}
    for (service, department), collections in sources.items():
        master = departments.setdefault(department, {'controleCode': department, 'keysList': {}})
        master['keysList'].update(collections)
    files = {'reference_sources/'+csv_path.name: raw}
    models, fixed, archived_sources = [], [], []
    csv_sha = hashlib.sha256(raw).hexdigest()
    for department, master in departments.items():
        relative = 'CSV/'+department+'.json'
        body = json_bytes(master)
        files['reference_sources/'+relative] = body
        archived_sources.append({'source': relative, 'archive': 'reference_sources/'+relative,
                                 'sha256': hashlib.sha256(body).hexdigest()})
    for (service, department), collections in sources.items():
        database = {'controleCode': department, 'keysList': collections}
        original_source = 'CSV/'+department+'.json'
        model_file = service+'/'+department+'.json'
        model = parse_model(json_bytes(database), department+'.json', service, department)
        old = prior_models.get((service, machine_key(department)))
        model['id'] = old['id'] if old else hashlib.sha256(('fixed-csv:'+service+':'+machine_key(department)).encode()).hexdigest()
        for parameter in model['parameters']:
            parameter['dataTypeRole'] = 'wire' if parameter.get('plcDataType') else 'value'
        model.update(fixed=True, sourceType='shortlisted-csv', sourceRelativePath=model_file,
                     originalSource=original_source,
                     sourceSha256=hashlib.sha256(files['reference_sources/'+original_source]).hexdigest(),
                     sourceCsv=csv_path.name, sourceCsvSha256=csv_sha)
        # Build only from the supplied rows. In particular, do not carry over
        # old workbook supplements, datatype corrections or removed records.
        assert len(model['parameters']) == sum(len(rows) for rows in collections.values())
        models.append(model)
        files[model_file] = json_bytes(database)
        fixed.append({'service': service, 'department': department, 'file': model_file,
                      'originalSource': original_source, 'parameters': len(model['parameters'])})
    summary = {'sourceCsv': csv_path.name, 'sourceSha256': csv_sha, 'rows': count,
               'models': len(models), 'departments': len(departments),
               'collections': sum(len(value) for value in sources.values()),
               'previousSourceRows': previous_source_rows,
               'previousCatalogRows': sum(len(model['parameters']) for model in previous['models']),
               'serviceRows': {service: sum(len(rows) for (kind, _), collections in sources.items()
                                          if kind == service for rows in collections.values()) for service in SERVICES}}
    files['catalog.json'] = json_bytes({'schemaVersion': 1, 'fixedReferences': True,
                                       'selectionMode': 'curated-csv', 'sourceCsv': csv_path.name,
                                       'models': models, 'importIssues': []})
    files['source_manifest.json'] = json_bytes({
        'schemaVersion': 1, 'selectionMode': 'curated-csv',
        'selection': 'Authoritative shortlisted CSV only. No workbook-derived requirements.',
        'sourceCsv': csv_path.name, 'sourceCsvSha256': csv_sha,
        'sources': [{'source': csv_path.name, 'archive': 'reference_sources/'+csv_path.name,
                     'sha256': csv_sha}, *archived_sources], 'sourceIssues': [], 'fixedModels': fixed,
    })
    files['README.md'] = (f'''# Shared Database JSON Keys

The active dataset contains only the **{count:,} shortlisted records** from
`{csv_path.name}` ({len(models)} service/department groups and
{summary['collections']} collections). KnowHub, DataInspect and metadata
comparison use this same catalog. Existing fixed model IDs are retained.

The input CSV is retained byte-for-byte under `reference_sources`. The JSON
files are the server-compatible representation of its rows. Old workbook
supplements and legacy catalogs are outside the active dataset in the backup.
No missing parameters, aliases or corrected values are invented during import.
Explicit interpretation rules in `knowledge/master/data_model_rules.json`
remain separate from the source definitions.

To apply a new shortlist, first preview it and then apply it with a backup:

```powershell
python scripts/replace_data_model_json_keys.py --csv "C:/path/shortlist.csv"
python scripts/replace_data_model_json_keys.py --csv "C:/path/shortlist.csv" --apply
```

An administrator can edit an individual collection in KnowHub. Refresh the
source table to load edits from another session. Historical reports keep their
recorded definitions; they do not repopulate this active catalog.
''').encode('utf-8')
    return {'files': files, 'summary': summary}


def apply_plan(plan, output: Path, backup_root: Path):
    output, backup_root = output.absolute(), backup_root.absolute()
    if output.is_symlink() or output.resolve() != output or not (output/'source_manifest.json').is_file():
        raise ValueError('The target must be the resolved, existing data-model directory.')
    if backup_root.is_relative_to(output) or output.is_relative_to(backup_root):
        raise ValueError('Store the backup outside the active data-model directory.')
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(INDIA).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    backup = (backup_root/('data-models_'+stamp)).resolve()
    stage = (output.parent/('.'+output.name+'_stage_'+stamp)).resolve()
    previous = backup/'previous_data_models'
    # Check every absolute move target before moving either directory.
    if not backup.is_relative_to(backup_root.resolve()) or not stage.is_relative_to(output.parent.resolve()):
        raise ValueError('The staging/backup paths escaped their intended directories.')
    if backup.exists() or stage.exists() or previous.exists():
        raise ValueError('A staging or backup target already exists.')
    stage.mkdir()
    for relative, contents in plan['files'].items():
        parts = PurePosixPath(relative)
        target = (stage/Path(*parts.parts)).resolve()
        if parts.is_absolute() or '..' in parts.parts or not target.is_relative_to(stage):
            raise ValueError('An output file escaped the staging directory.')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
    catalog = json.loads((stage/'catalog.json').read_text(encoding='utf-8'))
    if sum(len(model['parameters']) for model in catalog['models']) != plan['summary']['rows']:
        raise ValueError('The staged catalog did not preserve every shortlisted row.')
    backup.mkdir()
    (backup/'replacement.json').write_bytes(json_bytes(plan['summary']))
    # Preserve the complete previous dataset, including its XLSX references,
    # outside the active lookup path. There is no recursive deletion.
    output.rename(previous)
    try:
        stage.rename(output)
    except Exception:
        previous.rename(output)
        raise
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=APP_ROOT/'knowledge/data_models')
    parser.add_argument('--backup-root', type=Path, default=APP_ROOT/'.usopp_exports/backups')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    plan = build_plan(args.csv.resolve(), args.output.resolve())
    summary = dict(plan['summary'], applied=False)
    if args.apply:
        summary.update(applied=True, backup=str(apply_plan(plan, args.output.resolve(), args.backup_root.resolve())))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
