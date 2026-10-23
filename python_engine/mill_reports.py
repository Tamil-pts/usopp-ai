"""Read mill report records and calculate source-backed answers without an LLM.

Workbook cells are data. Formulas, macros and text instructions are never run.
Summary rows are retained for reconciliation and excluded from detail totals.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from io import BytesIO, StringIO
import csv
import hashlib
import math
import re
from statistics import mean
from zipfile import ZipFile

MAX_ROWS = 100_000
MAX_COLUMNS = 128
MAX_CELLS = 2_000_000
MAX_SHEETS = 16
LABELS = {'production': 'Production', 'quality': 'Quality', 'stoppage': 'Stoppage',
          'breakage': 'Breakage', 'air': 'Air consumption', 'power': 'Power'}


def words(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').casefold()).strip()


@dataclass(frozen=True)
class Field:
    key: str
    pattern: str
    aggregation: str = 'mean'
    unit: str = ''


FIELDS = (
    Field('machine', r'^(?:m c(?: name| no)?|mc name|machine(?: name| no| number| id)?|equipment(?: name| id)?)$', 'identity'),
    Field('date', r'^(?:shift date|production date|report date|date)\b', 'identity'),
    Field('shift', r'^shift(?: no| number)?$', 'identity'),
    Field('lot', r'^(?:lot|batch)(?: name| no| number| id)?$', 'identity'),
    Field('count', r'^(?:count|yarn count|hank ne)$', 'dimension'),
    Field('tpi', r'^(?:tpi|twists? per inch)$', 'dimension', 'TPI'),
    Field('tm', r'^(?:tm|twist multiplier)$', 'dimension'),
    Field('target_kg', r'^target production\b', 'sum', 'kg'),
    Field('actual_kg', r'^actual production\b', 'sum', 'kg'),
    Field('ybs_kg', r'^ybs production\b', 'sum', 'kg'),
    Field('production_kg', r'^(?:production|produced|output)(?: kgs?| kilograms?)?$', 'sum', 'kg'),
    Field('efficiency', r'^(?:prod eff|production eff|production efficiency|efficiency)$', 'mean', '%'),
    Field('utilization', r'^(?:m c|machine|mc)?\s*utili[sz]ation\b', 'mean', '%'),
    Field('spindle_speed', r'^(?:avg |average )?spindle speed\b', 'mean', 'rpm'),
    Field('delivery_speed', r'^(?:avg |average )?delivery speed\b', 'mean', 'm/min'),
    Field('gpss_40s', r'^40s gpss?\b', 'mean', 'g'),
    Field('gpss', r'^gpss?\b', 'mean', 'g'),
    Field('speed_percent', r'^(?:machine )?speed(?: percent)?$', 'mean', '%'),
    Field('spindles', r'^allotted spindle', 'mean', 'spindles'),
    Field('worked_spindles', r'^worked spindle', 'mean', 'spindles'),
    Field('doffs', r'^(?:total )?doffs?(?: nos?)?$', 'sum', 'doffs'),
    Field('avg_doff_seconds', r'^(?:avg|average) doff time\b', 'mean', 'seconds'),
    Field('runtime_seconds', r'^(?:total )?run(?:ning)? time\b', 'sum', 'seconds'),
    Field('idle_seconds', r'^idle time\b', 'sum', 'seconds'),
    Field('doff_seconds', r'^doff time\b', 'sum', 'seconds'),
    Field('powerfail_seconds', r'^power\s*fail(?:ure)? time\b', 'sum', 'seconds'),
    Field('stop_reason', r'^(?:machine display stoppage reason|stoppage reason|stop reason|reason)$', 'identity'),
    Field('user_reason', r'^(?:user entered reason|operator reason)$', 'identity'),
    Field('start_time', r'^start time\b', 'identity'),
    Field('end_time', r'^end time\b', 'identity'),
    Field('stop_seconds', r'^(?:stoppage )?duration\b|^stop(?:page)? time\b', 'sum', 'seconds'),
    Field('category', r'^category$', 'identity'),
    Field('breaks', r'^(?:total )?(?:break|breaks|breakage)(?: nos?| count)?$', 'sum', 'breaks'),
    Field('startup_breaks', r'^startup breaks\b', 'mean', '%'),
    Field('eb100sph', r'^eb 100sph\b', 'mean', '%'),
    Field('waste_kg', r'^(?:p waste|pneumafil waste|waste)(?: kgs?)?$', 'sum', 'kg'),
    Field('waste_percent', r'^(?:p waste|pneumafil waste|waste) (?:percent|percentage)$', 'mean', '%'),
    Field('idle_spindles', r'^idle(?: spindles?)?(?: nos?| count)?$', 'mean', 'spindles/record'),
    Field('slip_spindles', r'^slip(?: spindles?)?(?: nos?| count)?$', 'mean', 'spindles/record'),
    Field('rogue_spindles', r'^(?:rogue|rouge)(?: spindles?)?(?: nos?| count)?$', 'mean', 'spindles/record'),
    Field('worst_spindles', r'^worst(?: spindles?)?(?: nos?| count)?$', 'mean', 'spindles/record'),
    Field('end_mending_min', r'^(?:avg|average) (?:em|end mending)(?: time)?(?: min| minutes)?$', 'mean', 'min'),
    Field('cvm', r'^cvm$', 'mean', '%'),
    Field('unevenness', r'^u$', 'mean', '%'),
    Field('a_percent', r'^a$', 'mean', '%'),
    Field('thick_places', r'^thick places?\b', 'mean', '/hr'),
    Field('air_m3', r'^air consumption (?:cu m|m3|cubic meters?|cubic metres?)$', 'sum', 'm³'),
    Field('air_cfm', r'^air consumption cfm$', 'mean', 'CFM'),
    Field('energy_kwh', r'^(?:total )?kwh(?: kwh)?$|^energy(?: consumption)? kwh$', 'sum', 'kWh'),
    Field('power_factor', r'^power factor$', 'mean'),
    Field('voltage', r'^(?:avg |average )?voltage\b', 'mean', 'V'),
    Field('current', r'^(?:avg |average )?current\b', 'mean', 'A'),
    Field('ukg', r'^ukg$', 'mean', 'kWh/kg'),
    Field('frequency', r'^frequency\b', 'mean', 'Hz'),
)


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace(',', '').replace('%', '')
            if value in {'', '-', '--', 'N/A', 'NA'}:
                return None
            if value.startswith('(') and value.endswith(')'):
                value = '-' + value[1:-1]
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def parse_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    value = str(value or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d %b %Y', '%d %B %Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(value[:10] if fmt == '%Y-%m-%d' else value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def duration(value, label=''):
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, datetime):
        return (value - datetime(1899, 12, 30)).total_seconds()
    if isinstance(value, time):
        return value.hour * 3600 + value.minute * 60 + value.second
    if isinstance(value, (int, float)):
        return float(value) * 86400  # numeric Excel time serial
    match = re.fullmatch(r'\s*(?:(\d+)\s+days?,?\s*)?(\d+):(\d{2})(?::(\d{2}(?:\.\d+)?))?\s*', str(value or ''))
    if not match:
        return None
    days, first, second, third = match.groups()
    if third is not None:
        result = int(first) * 3600 + int(second) * 60 + float(third)
    elif 'mm:ss' in label.casefold():
        result = int(first) * 60 + int(second)
    else:
        result = int(first) * 3600 + int(second) * 60
    return int(days or 0) * 86400 + result


def field(label, column):
    normalized = words(label)
    if normalized in {'waste', 'p waste', 'pneumafil waste'} and '%' in str(label):
        return {'key': 'waste_percent', 'label': str(label).strip(), 'column': column,
                'aggregation': 'mean', 'unit': '%'}
    for candidate in FIELDS:
        if re.search(candidate.pattern, normalized):
            return {'key': candidate.key, 'label': str(label).strip(), 'column': column,
                    'aggregation': candidate.aggregation, 'unit': candidate.unit}
    cv = re.fullmatch(r'cv\s*(\d+\s*(?:cm|m))', normalized)
    if cv:
        return {'key': 'cv_' + cv[1].replace(' ', ''), 'label': str(label).strip(),
                'column': column, 'aggregation': 'mean', 'unit': '%'}
    return {'key': f'extra_{column}', 'label': str(label).strip(), 'column': column,
            'aggregation': 'mean', 'unit': ''}


def report_kind(columns):
    keys = {item['key'] for item in columns}
    if 'stop_reason' in keys and 'stop_seconds' in keys:
        return 'stoppage'
    if 'cvm' in keys or 'unevenness' in keys:
        return 'quality'
    if 'breaks' in keys:
        return 'breakage'
    if 'air_m3' in keys or 'air_cfm' in keys:
        return 'air'
    if 'energy_kwh' in keys and keys & {'voltage', 'current', 'power_factor'}:
        return 'power'
    if 'production_kg' in keys:
        return 'production'
    return None


def letter(column):
    result = ''
    while column:
        column, remainder = divmod(column - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheets(name, content):
    suffix = name.rsplit('.', 1)[-1].casefold()
    if suffix == 'xlsx':
        from openpyxl import load_workbook
        with ZipFile(BytesIO(content)) as archive:
            if len(archive.infolist()) > 5000 or sum(item.file_size for item in archive.infolist()) > 60 * 1024**2:
                raise ValueError('Workbook exceeds the 60 MB expanded attachment limit.')
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            for sheet in book.worksheets:
                if sheet.sheet_state != 'visible':
                    continue
                yield sheet.title, sheet.max_row or 0, sheet.max_column or 0, (
                    [(cell.value, cell.number_format or '') for cell in row]
                    for row in sheet.iter_rows(max_row=min(sheet.max_row or MAX_ROWS, MAX_ROWS + 1),
                                               max_col=min(sheet.max_column or MAX_COLUMNS, MAX_COLUMNS)))
        finally:
            book.close()
    elif suffix == 'xls':
        import xlrd
        book = xlrd.open_workbook(file_contents=content, on_demand=True)
        try:
            for sheet in book.sheets():
                if getattr(sheet, 'visibility', 0) != 0:
                    continue
                def read_rows(sheet=sheet):
                    for i in range(min(sheet.nrows, MAX_ROWS + 1)):
                        values = []
                        for j in range(min(sheet.ncols, MAX_COLUMNS)):
                            cell = sheet.cell(i, j)
                            item = cell.value
                            fmt = f'xlrd-date:{book.datemode}' if cell.ctype == xlrd.XL_CELL_DATE else ''
                            values.append((item, fmt))
                        yield values
                yield sheet.name, sheet.nrows, sheet.ncols, read_rows()
        finally:
            book.release_resources()
    elif suffix == 'csv':
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = content.decode('cp1252')
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        rows = csv.reader(StringIO(text), dialect)
        yield 'CSV', 0, 0, ([(value, '') for value in row[:MAX_COLUMNS]] for row in rows)


def parse_report(name, content):
    """Recognize headers from their columns, not the supplied filename."""
    tables, metadata, warnings = [], {}, []
    cells_read, rows_read = 0, 0
    bounded = False
    for sheet_number, (sheet, declared_rows, declared_columns, incoming) in enumerate(_sheets(name, content), 1):
        if sheet_number > MAX_SHEETS:
            bounded = True
            break
        table = None
        seen_keys = set()
        for row_number, cells in enumerate(incoming, 1):
            cells_read += len(cells)
            rows_read += 1
            if row_number > MAX_ROWS or cells_read > MAX_CELLS:
                bounded = True
                break
            raw = [value for value, _ in cells]
            if table is None:
                if row_number > 60:
                    break
                for index in range(0, min(len(raw) - 1, 8), 2):
                    key = words(raw[index])
                    if key in {'department', 'from date', 'to date', 'reportname', 'report name', 'report type', 'shed', 'shift', 'lot', 'count'}:
                        metadata[key] = str(raw[index + 1] or '')[:1000]
                candidate = [field(value, index) for index, value in enumerate(raw, 1) if value is not None]
                kind = report_kind(candidate)
                if not kind or not any(item['key'] == 'machine' for item in candidate):
                    continue
                columns = []
                for item in candidate:
                    if item['key'] in seen_keys:
                        warnings.append(f'{sheet}: duplicate column {item["label"]}; first occurrence used.')
                        continue
                    columns.append(item)
                    seen_keys.add(item['key'])
                table = {'sheet': sheet, 'kind': kind, 'headerRow': row_number,
                         'columns': columns, 'records': [], 'summaries': [], 'skippedRows': 0,
                         'declaredRows': declared_rows, 'declaredColumns': declared_columns}
                if declared_columns > MAX_COLUMNS:
                    bounded = True
                tables.append(table)
                continue
            values = {}
            for column in table['columns']:
                index = column['column'] - 1
                value, fmt = cells[index] if index < len(cells) else (None, '')
                key = column['key']
                if key == 'date':
                    if fmt.startswith('xlrd-date:') and isinstance(value, (int, float)):
                        import xlrd
                        value = xlrd.xldate_as_datetime(value, int(fmt.rsplit(':', 1)[1]))
                    value = parse_date(value)
                elif column['aggregation'] == 'identity':
                    if key in {'start_time', 'end_time'} and fmt.startswith('xlrd-date:'):
                        value = format_duration(float(value) * 86400)
                    elif isinstance(value, (time, datetime)):
                        value = value.isoformat()
                    elif isinstance(value, timedelta):
                        value = format_duration(value.total_seconds())
                    elif value is not None:
                        value = str(value).strip()[:2000]
                elif column['unit'] == 'seconds':
                    value = duration(value, column['label'])
                else:
                    original = value
                    value = number(value)
                    if value is None and column['key'].startswith('extra_') and original is not None:
                        value = str(original).strip()[:2000] or None
                    if value is not None and column['unit'] == '%' and '%' in re.sub(r'"[^"]*"|\\.', '', fmt):
                        value *= 100
                values[key] = value
            machine = values.get('machine')
            label = ' '.join(str(value) for value in raw[:4] if value is not None)
            is_summary = bool(re.search(r'\b(?:summary|sub\s*total|subtotal|grand total|total)\b', label, re.I))
            if is_summary or not machine or words(machine) in {'m c name', 'machine name', 'machine'}:
                if is_summary:
                    table['summaries'].append({'row': row_number, 'label': label[:200], 'values': values})
                table['skippedRows'] += 1
                continue
            # A machine record must have its own date when a date column exists.
            # This excludes units, repeated headers and machine subtotal blocks.
            if 'date' in seen_keys and not values.get('date'):
                table['skippedRows'] += 1
                continue
            table['records'].append({'row': row_number, 'values': values})
        if bounded:
            break
    tables = [table for table in tables if table['records']]
    if not tables:
        return None
    if bounded:
        warnings.append('Reading limit reached. Results cover the parsed records only; upload a smaller date range for complete totals.')
    return {'schema': 3, 'name': name, 'digest': hashlib.sha256(content).hexdigest(),
            'metadata': metadata, 'tables': tables, 'complete': not bounded,
            'warnings': warnings, 'rowsRead': rows_read}


def report_summary(report):
    records = [row for table in report['tables'] for row in table['records']]
    dates = sorted({row['values']['date'] for row in records if row['values'].get('date')})
    kinds = list(dict.fromkeys(table['kind'] for table in report['tables']))
    return {'name': report['name'], 'kinds': kinds, 'kind': kinds[0],
            'label': ' / '.join(LABELS[kind] for kind in kinds), 'records': len(records),
            'machines': len({row['values']['machine'] for row in records}),
            'dateFrom': dates[0] if dates else None, 'dateTo': dates[-1] if dates else None,
            'complete': report['complete'], 'sheets': len(report['tables']),
            'summaryRowsExcluded': sum(len(table['summaries']) for table in report['tables']),
            'warnings': report['warnings']}


def format_number(value, decimals=2):
    return 'Unavailable' if value is None else f'{value:,.{decimals}f}'


def format_duration(value):
    if value is None:
        return 'Unavailable'
    total = round(value)
    hours, remainder = divmod(abs(total), 3600)
    minutes, seconds = divmod(remainder, 60)
    return ('-' if total < 0 else '') + f'{hours}:{minutes:02}:{seconds:02}'


def aggregate(rows, key, mode='mean'):
    if key == 'event_count':
        return len(rows)
    if key == 'energy_per_kg':
        paired = [row for row in rows if all(isinstance(row['values'].get(field), (int, float))
                  and math.isfinite(row['values'][field]) for field in ('energy_kwh', 'production_kg'))]
        energy, production = aggregate(paired, 'energy_kwh', 'sum'), aggregate(paired, 'production_kg', 'sum')
        return energy / production if energy is not None and production and production > 0 else None
    values = [row['values'].get(key) for row in rows]
    values = [value for value in values if isinstance(value, (int, float)) and math.isfinite(value)]
    if not values:
        return None
    return math.fsum(values) if mode == 'sum' else mean(values)


def normalized_question(question):
    text = str(question).casefold()
    for wrong, correct in {'peoduction': 'production', 'prodution': 'production', 'producton': 'production',
                           'qualti': 'quality', 'qualty': 'quality', 'stopage': 'stoppage',
                           'analysi': 'analysis', 'analize': 'analyze', 'higest': 'highest',
                           'highst': 'highest', 'whehic': 'which', 'wich': 'which',
                           'spindel': 'spindle', 'spindels': 'spindles',
                           'delivary': 'delivery', 'avarage': 'average'}.items():
        text = re.sub(r'\b' + wrong + r'\b', correct, text)
    return text


def query_scope(question, all_dates, today=None, previous=None):
    text = normalized_question(question)
    today = parse_date(today) or date.today().isoformat()
    current = date.fromisoformat(today)
    previous = previous if isinstance(previous, dict) else {}
    scope = {}
    for key in ('from', 'to'):
        if parse_date(previous.get(key)):
            scope[key] = parse_date(previous[key])
    if re.fullmatch(r'\d{1,3}', str(previous.get('shift') or '')):
        scope['shift'] = str(previous['shift'])
    if isinstance(previous.get('machines'), list):
        scope['machines'] = [machine_key(value) for value in previous['machines'][:50] if isinstance(value, str)]
    if re.search(r'\b(?:all dates|whole|entire|overall|full (?:report|period))\b', text):
        scope = {}
    explicit = []
    patterns = (r'\b\d{4}-\d{2}-\d{2}\b', r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b',
                r'\b\d{1,2}\s+(?:jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)\s+\d{4}\b')
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            parsed = parse_date(match.group())
            if parsed:
                explicit.append((match.start(), parsed))
    explicit.sort()
    if explicit:
        last = explicit[1][1] if len(explicit) >= 4 and re.search(r'compar|versus|\bvs\b', text) else explicit[-1][1]
        scope['from'], scope['to'] = explicit[0][1], last
    elif re.search(r'\btoday\b', text):
        scope['from'] = scope['to'] = today
    elif re.search(r'\byesterday\b', text):
        scope['from'] = scope['to'] = (current - timedelta(days=1)).isoformat()
    elif re.search(r'\b(?:latest|last) (?:day|date)\b', text) and all_dates:
        scope['from'] = scope['to'] = max(all_dates)
    elif match := re.search(r'\b(?:last|past)\s+(\d{1,3})\s+days?\b', text):
        scope['from'] = (current - timedelta(days=max(1, int(match[1])) - 1)).isoformat()
        scope['to'] = today
    elif 'this month' in text:
        scope['from'] = current.replace(day=1).isoformat()
        scope['to'] = today
    shifts = re.findall(r'\bshift\s*(?:no\.?\s*)?[#:]?\s*(\d+)\b', text)
    if shifts:
        scope['shift'] = shifts[-1]
    if 'all shifts' in text:
        scope.pop('shift', None)
    machines = list(dict.fromkeys(machine_key(item) for item in re.findall(r'\b(?:RF|DF|SF|BF|CF|LF|CM|OE|RS|AC)\s*[-_]?\s*\d+\b', question, re.I)))
    if machines:
        scope['machines'] = machines
    if re.search(r'\ball (?:the )?machines\b', text):
        scope.pop('machines', None)
    if not machines and re.search(r'\bmachine\s*[- ]?\s*wise\b|\b(?:per|by|each|every) machine\b|\bwhich machine\b.*\b(?:highest|lowest|most|least)\b', text) and not re.search(r'\b(?:this|that|selected|same) machine\b(?!\s*[- ]?\s*wise)', text):
        scope.pop('machines', None)
    return {key: value for key, value in scope.items() if key in {'from', 'to', 'shift', 'machines'} and value}


def machine_key(value):
    key = re.sub(r'[^A-Z0-9]', '', value.upper())
    match = re.fullmatch(r'([A-Z]+)(\d+)', key)
    return match[1] + str(int(match[2])) if match else key


def filter_records(rows, scope):
    result = []
    for row in rows:
        value = row['values']
        day = value.get('date')
        if scope.get('from') and (not day or day < scope['from']):
            continue
        if scope.get('to') and (not day or day > scope['to']):
            continue
        if scope.get('shift') and str(value.get('shift')) != str(scope['shift']):
            continue
        machine = machine_key(value['machine'])
        if scope.get('machines') and machine not in scope['machines']:
            continue
        result.append(row)
    return result


def _metric(table, question):
    text = normalized_question(question)
    keys = {column['key']: column for column in table['columns']}
    if table['kind'] == 'stoppage' and re.search(r'number of|event count|most (?:stoppage )?(?:stoppages|stops|events)|frequen|highest.*(?:count|events)', text):
        return {**keys['machine'], 'key': 'event_count', 'label': 'Stoppage events', 'aggregation': 'sum', 'unit': 'events'}
    if 'energy_kwh' in keys and 'production_kg' in keys and re.search(r'kwh\s*/\s*kg|(?:power|energy) per|energy intens', text):
        return {**keys['energy_kwh'], 'key': 'energy_per_kg', 'label': 'Energy per production kg', 'aggregation': 'ratio', 'unit': 'kWh/kg',
                'sourceColumns': [keys['energy_kwh']['column'], keys['production_kg']['column']]}
    if 'production_kg' in keys and re.search(r'running machines.*production|production.*running machines', text):
        return keys['production_kg']
    requested = (
        ('actual_kg', r'actual production'), ('target_kg', r'target production'),
        ('waste_kg', r'waste'), ('eb100sph', r'eb.?100|100.?sph'),
        ('startup_breaks', r'startup break'), ('breaks', r'breakage|total break|breaks'),
        ('end_mending_min', r'end mending|mending time|\bemt\b'),
        ('idle_spindles', r'idle spindle'), ('rogue_spindles', r'rogue spindle|rouge spindle'),
        ('slip_spindles', r'slip spindle'), ('worst_spindles', r'worst spindle'),
        ('gpss_40s', r'40s gps'), ('gpss', r'\bgpss?\b'),
        ('stop_seconds', r'stop|down.?time|duration'), ('idle_seconds', r'idle'),
        ('avg_doff_seconds', r'average doff|avg\.? doff'), ('doff_seconds', r'doff time'),
        ('doffs', r'doffs'), ('runtime_seconds', r'run.?time|run time|running machines'),
        ('air_cfm', r'cfm'), ('air_m3', r'air consumption|cubic|cu\.?\s*m'),
        ('ukg', r'ukg|kwh\s*/\s*kg|energy per|power per'),
        ('energy_kwh', r'kwh|energy|power consumption'), ('power_factor', r'power factor'),
        ('voltage', r'voltage'), ('current', r'current'), ('frequency', r'frequency'),
        ('cvm', r'cvm'), ('a_percent', r'\ba\s*(?:%|percent)'), ('unevenness', r'unevenness|\bu\s*%'),
        ('thick_places', r'thick place'), ('efficiency', r'efficien'),
        ('utilization', r'utili[sz]'), ('spindle_speed', r'spindle speed'),
        ('delivery_speed', r'delivery speed'), ('production_kg', r'production|output|\bkg\b'),
    )
    for key, pattern in requested:
        if key in keys and re.search(pattern, text):
            return keys[key]
    for key, column in keys.items():
        if key.startswith('cv_') and key[3:] in words(text).replace(' ', ''):
            return column
    defaults = {'production': 'production_kg', 'quality': 'cvm', 'stoppage': 'stop_seconds',
                'breakage': 'breaks', 'air': 'air_m3', 'power': 'energy_kwh'}
    return keys.get(defaults[table['kind']]) or next(column for column in table['columns'] if column['aggregation'] == 'sum')


def _markdown_table(headers, rows):
    def clean(value):
        return str(value).replace('|', '/').replace('\r', ' ').replace('\n', ' ')[:800]
    return '\n'.join(['| ' + ' | '.join(map(clean, headers)) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |',
                      *['| ' + ' | '.join(map(clean, row)) + ' |' for row in rows]])


def _scope_label(rows, scope):
    dates = sorted({row['values']['date'] for row in rows if row['values'].get('date')})
    first, last = scope.get('from') or (dates[0] if dates else None), scope.get('to') or (dates[-1] if dates else None)
    label = first if first == last else f'{first} to {last}'
    if not first:
        label = 'Uploaded records'
    if scope.get('shift'):
        label += f' · Shift {scope["shift"]}'
    if scope.get('machines'):
        label += ' · ' + ', '.join(sorted({row['values']['machine'] for row in rows}) or scope['machines'])
    return label


def _source(report, table, rows, metric):
    relevant = {
        'production': {'production_kg', 'actual_kg', 'target_kg', 'efficiency', 'runtime_seconds'},
        'stoppage': {'stop_reason', 'stop_seconds', 'user_reason', 'machine'},
        'quality': {'cvm', 'unevenness', 'thick_places'},
        'power': {'energy_kwh', 'production_kg'},
    }.get(table['kind'], set()) | {metric['key']}
    columns = list(dict.fromkeys([metric['column'], *metric.get('sourceColumns', []),
                                 *[column['column'] for column in table['columns'] if column['key'] in relevant]]))
    return {'file': report['name'], 'reportId': report.get('id'), 'sheet': table['sheet'],
            'headerRow': table['headerRow'], 'metric': metric.get('sourceLabel', metric['label']),
            'column': letter(metric['column']), 'rows': [row['row'] for row in rows],
            'columns': [letter(column) for column in columns],
            'records': len(rows), 'summaryRowsExcluded': len(table['summaries']),
            'complete': report['complete'], 'digest': report['digest']}


def analyze_reports(reports, question, *, today=None, previous=None, scope_override=None):
    """Answer common report questions from complete parsed numeric records."""
    text = normalized_question(question)
    selected = [(report, table) for report in reports for table in report['tables']]
    topics = {'quality': r'quality|cvm|unevenness|thick place|\bcv\b',
              'breakage': r'breakage|breaks|eb.?100|waste|(?:idle|rogue|rouge|slip|worst) spindle|end mending|\bemt\b', 'stoppage': r'stoppage|stop reason|stopped|downtime|down time|most stops',
              'air': r'\bair\b|\bcfm\b', 'power': r'\bpower\b|\benergy\b|\bkwh\b|\bukg\b|voltage|current consumption',
              'production': r'production|output|efficien|utili[sz]|running machines'}
    wanted = [kind for kind, pattern in topics.items() if re.search(pattern, text)]
    if wanted:
        matching = [(report, table) for report, table in selected if table['kind'] in wanted]
        if matching:
            selected = matching
        elif len(wanted) == 1:
            names = ', '.join(LABELS[kind] for kind in dict.fromkeys(table['kind'] for _, table in selected))
            return {'answer': f'Attach a {LABELS[wanted[0]].lower()} report for this question. The current attachments contain {names.lower()} data.',
                    'cards': [], 'sources': [], 'scope': {}, 'kinds': []}
    elif previous and previous.get('kind'):
        matching = [(report, table) for report, table in selected if table['kind'] == previous['kind']]
        if matching:
            selected = matching
    all_dates = sorted({row['values']['date'] for _, table in selected for row in table['records'] if row['values'].get('date')})
    scope = query_scope('', [], today, scope_override) if isinstance(scope_override, dict) else query_scope(question, all_dates, today, (previous or {}).get('scope'))
    if isinstance((previous or {}).get('focusMachine'), str) and re.search(r'\b(?:that|this|same) machine\b|\bits (?:reason|stop)', text) and not scope.get('machines'):
        scope['machines'] = [machine_key(previous['focusMachine'])]
    cards, sources, sections, warnings, table_results = [], [], [], [], []
    focus_machine = None
    limit_match = re.search(r'\b(?:top|bottom|first|last)\s+(\d+)\b', text)
    limit = max(1, min(50, int(limit_match[1]))) if limit_match else 5
    if re.search(r'\b(?:all machines|every machine)\b', text):
        limit = 50
    if re.search(r'\b(?:which|what)\s+(?:m/?c|machine)\b', text) and not limit_match and not re.search(r'compare', text):
        limit = 1
    group_key, group_label = 'machine', 'Machine'
    if re.search(r'\b(?:daily|daywise|datewise|trend|by day|by date|which day|which date|highest day|lowest day)\b', text):
        group_key, group_label = 'date', 'Date'
    elif re.search(r'\b(?:shiftwise|by shift|compare shifts|which shift|highest shift|lowest shift)\b', text):
        group_key, group_label = 'shift', 'Shift'
    elif re.search(r'\b(?:lotwise|by lot|which lot|compare lots)\b', text):
        group_key, group_label = 'lot', 'Lot'
    if group_key != 'machine' and not limit_match:
        limit = 50
    if re.search(r'\b(?:maintenance ticket|create (?:a )?ticket)\b', text):
        return {'answer': 'A maintenance ticket can be drafted from these recorded stoppages. No maintenance ticket service is connected here, so no ticket has been created. Ask for the machine’s stoppage reasons and use the cited records in your maintenance system.',
                'cards': [], 'sources': [], 'scope': scope, 'kinds': []}
    for report, table in selected:
        rows = filter_records(table['records'], scope)
        metric = dict(_metric(table, question))
        if metric['unit'] == 'seconds':
            metric['sourceLabel'] = metric['label']
            metric['label'] = re.sub(r'\((?:HH:MM|MM:SS)\)', '(H:MM:SS)', metric['label'], flags=re.I)
        heading = f'{LABELS[table["kind"]]} · {_scope_label(rows, scope)}'
        if len(selected) > 1:
            heading += f' · {report["name"]}'
        sections.append('### ' + heading)
        if not rows:
            sections.append('No machine records match this date, shift or machine selection. '
                            f'The uploaded report covers {all_dates[0] if all_dates else "an unspecified start"} to {all_dates[-1] if all_dates else "an unspecified end"}.')
            continue
        source = _source(report, table, rows, metric)
        sources.append(source)
        warnings.extend(report['warnings'])
        missing = 0 if metric['key'] in {'event_count', 'energy_per_kg'} else sum(row['values'].get(metric['key']) is None for row in rows)
        if missing:
            warnings.append(f'{report["name"]}: {missing} of {len(rows)} selected records have no numeric {metric["label"]}; those cells are excluded from this calculation.')
        if metric['key'] == 'energy_per_kg' or table['kind'] == 'power':
            missing_pairs = sum(any(row['values'].get(key) is None for key in ('energy_kwh', 'production_kg')) for row in rows)
            if missing_pairs:
                warnings.append(f'{report["name"]}: {missing_pairs} selected records lack paired energy/production values. Calculated kWh/kg uses only records containing both values.')
        grouped = defaultdict(list)
        for row in rows:
            grouped[str(row['values'].get(group_key) or 'Unspecified')].append(row)
        machines_count = len({row['values']['machine'] for row in rows})
        total = aggregate(rows, metric['key'], metric['aggregation'])
        display = lambda value: format_duration(value) if metric['unit'] == 'seconds' else format_number(value, 0 if metric['key'] in {'breaks', 'doffs', 'event_count'} else 2)
        aggregation_label = 'Total' if metric['aggregation'] == 'sum' else 'Calculated' if metric['aggregation'] == 'ratio' else 'Mean reported'
        summary_label = metric['label'] if metric['label'].casefold().startswith(aggregation_label.casefold() + ' ') else aggregation_label + ' ' + metric['label']
        cards.extend([{'label': f'{LABELS[table["kind"]]} · {summary_label}', 'value': display(total),
                       'unit': '' if metric['unit'] == 'seconds' else metric['unit'], 'detail': _scope_label(rows, scope)},
                      {'label': 'Machines / detail records', 'value': f'{machines_count} / {len(rows):,}', 'unit': '', 'detail': report['name']}])
        sections.append(f'**{summary_label}: {display(total)}**'
                        f' · {machines_count} machines · {len(rows):,} machine records.')
        default_low = table['kind'] == 'quality'
        ascending = bool(re.search(r'lowest|least|minimum|bottom|smallest|best.*quality', text)) or (default_low and not re.search(r'highest|most|maximum|worst|poorest|poor quality|bad quality|descending', text))
        ranked = []
        for machine, machine_rows in grouped.items():
            value = aggregate(machine_rows, metric['key'], metric['aggregation'])
            if value is not None:
                ranked.append((machine, value, machine_rows))
        ranked.sort(key=lambda item: (item[1] if ascending else -item[1], item[0]))
        chronological = group_key == 'date' and not re.search(r'highest|lowest|top|bottom|most|least|maximum|minimum', text)
        if chronological:
            ranked.sort(key=lambda item: item[0])
        if re.search(r'\brunning machines\b', text):
            ranked = [item for item in ranked if (aggregate(item[2], 'runtime_seconds', 'sum') or 0) > 0]
        if ranked:
            order = 'date order' if chronological else 'lowest first' if ascending else 'highest first'
            sections.append(f'{group_label} ranking by **{metric["label"]} ({order})**. '
                            + ('Values are summed across the selected records.' if metric['aggregation'] == 'sum' else 'Values use summed kWh divided by summed production kg.' if metric['aggregation'] == 'ratio' else 'Values are arithmetic means of the reported machine records.'))
            headers = [group_label, metric['label'], 'Records']
            extra = []
            if table['kind'] == 'production':
                extra = [('efficiency', 'Mean prod. eff. (%)', 'mean'), ('runtime_seconds', 'Recorded run time', 'sum')]
            elif table['kind'] == 'quality':
                extra = [('unevenness', 'Mean U (%)', 'mean'), ('thick_places', 'Mean thick places (/hr)', 'mean')]
            elif table['kind'] == 'stoppage':
                headers.append('Largest recorded reason by duration')
            elif table['kind'] == 'power':
                extra = [('production_kg', 'Production (kg)', 'sum')]
                headers.append('Calculated kWh/kg')
            extra = [item for item in extra if item[0] != metric['key'] and any(column['key'] == item[0] for column in table['columns'])]
            headers.extend(item[1] for item in extra)
            output_rows = []
            for machine, value, machine_rows in ranked[:limit]:
                cells = [machine, display(value), str(len(machine_rows))]
                if table['kind'] == 'stoppage':
                    reasons = defaultdict(float)
                    for row in machine_rows:
                        reasons[row['values'].get('stop_reason') or 'Unspecified'] += row['values'].get('stop_seconds') or 0
                    cells.append(max(reasons, key=reasons.get))
                elif table['kind'] == 'power':
                    cells.append(format_number(aggregate(machine_rows, 'energy_per_kg')))
                for key, label, mode in extra:
                    value = aggregate(machine_rows, key, mode)
                    cells.append(format_duration(value) if key.endswith('_seconds') else format_number(value))
                output_rows.append(cells)
            sections.append(_markdown_table(headers, output_rows))
            table_results.append({'title': heading, 'headers': headers, 'rows': output_rows})
            if len(ranked) > limit and limit > 1:
                sections.append(f'Showing {limit} of {len(ranked)} {group_label.lower()} groups. Ask for all machines or a specific machine to expand.')
            if limit == 1 and len(selected) == 1 and group_key == 'machine':
                focus_machine = ranked[0][0]
        if table['kind'] == 'production':
            production, actual = aggregate(rows, 'production_kg', 'sum'), aggregate(rows, 'actual_kg', 'sum')
            if actual is not None and metric['key'] != 'actual_kg':
                sections.append(f'The separate **Actual Production (Kgs)** column totals **{format_number(actual)} kg**. Machine production ranking uses the requested column, without adding these two production measures together.')
            if any(column['key'] == 'target_kg' for column in table['columns']):
                no_target = sum(not row['values'].get('target_kg') or row['values']['target_kg'] <= 0 for row in rows)
                target = aggregate(rows, 'target_kg', 'sum')
                if not no_target and target and production is not None:
                    sections.append(f'Target production: **{format_number(target)} kg** · achievement: **{format_number(100 * production / target)}%**.')
                elif no_target:
                    sections.append(f'Target achievement is unavailable: {no_target} selected records have a zero or missing target.')
        if table['kind'] == 'stoppage':
            reason_records = ranked[0][2] if ranked and limit == 1 else rows
            reason_heading = f'Recorded reasons for {ranked[0][0]}' if ranked and limit == 1 else 'Recorded stoppage reasons across selected machines'
            if ranked and limit == 1:
                machine, value, machine_rows = ranked[0]
                sections.append(f'**{machine}** ranks first by {metric["label"].lower()}: **{display(value)}** '
                                f'across **{len(machine_rows)} recorded events**. Its total recorded downtime is '
                                f'**{format_duration(aggregate(machine_rows, "stop_seconds", "sum"))}** (H:MM:SS).')
            reasons = defaultdict(list)
            for row in reason_records:
                reasons[row['values'].get('stop_reason') or 'Unspecified'].append(row)
            reasons = sorted(reasons.items(), key=lambda item: -(aggregate(item[1], 'stop_seconds', 'sum') or 0))
            reason_limit = 50 if re.search(r'\ball (?:the )?(?:stoppage )?reasons\b', text) else max(5, limit)
            reason_rows = [[reason, str(len(events)), format_duration(aggregate(events, 'stop_seconds', 'sum'))] for reason, events in reasons[:reason_limit]]
            sections.extend(['**' + reason_heading + '**', _markdown_table(['Reason', 'Events', 'Total duration (H:MM:SS)'], reason_rows)])
            table_results.append({'title': reason_heading, 'headers': ['Reason', 'Events', 'Total duration (H:MM:SS)'], 'rows': reason_rows})
            if len(reasons) > reason_limit:
                sections.append(f'Showing {reason_limit} of {len(reasons)} recorded reasons, ranked by duration.')
            if reasons:
                leading_reason, events = reasons[0]
                sections.append(f'Largest recorded reason by duration: **{leading_reason}**, '
                                f'**{format_duration(aggregate(events, "stop_seconds", "sum"))}**, **{len(events)} events**. '
                                'This is the recorded reason text; it does not independently prove a physical root cause.')
        if table['kind'] == 'quality':
            sections.append('Quality values are reported measurements. Accept/reject limits and a live machine status are not present in this workbook. CV and quality averages are unweighted record means.')
        if table['kind'] in {'production', 'stoppage'}:
            sections.append('These are historical report records. Current running/stopped state and an active fault cannot be established from this upload.')
        if table['kind'] == 'power':
            sections.append('Calculated kWh/kg uses summed kWh divided by summed production kg for the selected machine records. Reported UKG values remain a separate metric.')
        # Reconcile only an unfiltered, complete table against its own overall summary.
        if not scope and report['complete'] and total is not None and metric['aggregation'] == 'sum':
            overall = next((row for row in reversed(table['summaries']) if 'overall summary' in row['label'].casefold() or 'grand total' in row['label'].casefold()), None)
            reported = overall['values'].get(metric['key']) if overall else None
            if reported is not None and abs(total - reported) > (0.5 if metric['unit'] == 'seconds' else 0.005):
                warnings.append(f'{report["name"]}, {table["sheet"]}!{letter(metric["column"])}{overall["row"]}: '
                                f'workbook summary {display(reported)} differs from the detail-record result {display(total)} '
                                f'by {display(abs(total - reported))}. This answer uses the displayed machine records.')
        row_refs = ', '.join(f'{source["column"]}{row}' for row in source['rows'][:8])
        if len(source['rows']) > 8:
            row_refs += f' (+{len(source["rows"]) - 8} detail cells)'
        sections.append(f'Source: **{report["name"]} → {table["sheet"]}**, header row {table["headerRow"]}; '
                        f'{metric["label"]}: {row_refs}. Summary rows are excluded.')
    if warnings:
        sections.extend(['### Data notes', *['- ' + warning for warning in dict.fromkeys(warnings)]])
    kinds = list(dict.fromkeys(table['kind'] for _, table in selected))
    return {'answer': '\n\n'.join(sections), 'cards': cards[:12], 'tables': table_results,
            'sources': sources, 'scope': scope, 'kinds': kinds,
            'kind': kinds[0] if len(kinds) == 1 else None,
            'warnings': list(dict.fromkeys(warnings)), 'calculated': True,
            'focusMachine': focus_machine,
            'groupBy': group_key,
            'complete': all(report['complete'] for report, _ in selected)}
