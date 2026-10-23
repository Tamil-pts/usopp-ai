"""Bounded report query plans. All calculations use owned worksheet records.

The planner chooses columns and operations; it never supplies result numbers or
executable code. Source families are aggregated separately before alignment.
"""
from collections import defaultdict
from hashlib import sha256
import json
import math
import re
from statistics import mean, median, pstdev

from python_engine.mill_reports import (
    _markdown_table, aggregate, filter_records, format_duration, format_number, letter,
    machine_key, normalized_question, number, parse_date, query_scope, words,
)

OPS = {'default', 'sum', 'mean', 'min', 'max', 'median', 'stddev', 'count', 'distinct_count', 'distinct'}
PREDICATES = {'eq', 'ne', 'in', 'gt', 'gte', 'lt', 'lte', 'contains'}
DIMENSIONS = {'machine', 'date', 'shift', 'lot', 'count', 'tpi', 'tm', 'stop_reason', 'category', 'user_reason'}


def catalog(reports):
    result, seen = {}, set()
    for report in reports:
        if report['digest'] in seen:
            continue
        seen.add(report['digest'])
        for index, table in enumerate(report['tables']):
            identifier = f'T{len(result)}'
            columns = {c['key']: c for c in table['columns']}
            for key, column in list(columns.items()):
                if key.startswith('extra_'):
                    values = [r['values'][key] for r in table['records'][:128] if r['values'].get(key) is not None]
                    if values and all(isinstance(v, str) for v in values):
                        columns[key] = {**column, 'aggregation': 'identity'}
            result[identifier] = {'report': report, 'table': table, 'columns': columns}
    return result


def catalog_id(sources):
    return sha256(json.dumps([(key, item['report']['digest'], item['table']['sheet'], list(item['columns']))
                             for key, item in sources.items()], separators=(',', ':')).encode()).hexdigest()


def describe_catalog(reports):
    """Column schema only: workbook cell text is never interpreted as instructions."""
    sources = catalog(reports)
    return [{'source': key, 'type': item['table']['kind'],
             'columns': [{'key': c['key'], 'label': c['label'][:100], 'unit': c['unit'], 'default': c['aggregation']}
                         for c in item['columns'].values() if not c['key'].startswith('extra_s_no')],
             'dates': sorted({r['values']['date'] for r in item['table']['records'] if r['values'].get('date')})[::max(1, len({r['values'].get('date') for r in item['table']['records']})-1)]}
            for key, item in sources.items()]


def _strings(value, maximum=50):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError('The comparison contains too many filter values.')
    if any(isinstance(v, (dict, list, bool)) or v is None or len(str(v)) > 300 or isinstance(v, (int, float)) and not math.isfinite(v) for v in value):
        raise ValueError('The comparison contains an invalid filter value.')
    return value


def validate_plan(plan, reports, question):
    sources = catalog(reports)
    if not isinstance(plan, dict) or not isinstance(plan.get('queries'), list) or len(plan['queries']) > 6:
        raise ValueError('Ask for at most six related report comparisons in one message.')
    if plan.get('catalog') and plan['catalog'] != catalog_id(sources):
        raise ValueError('The attached report columns changed. Ask the comparison again.')
    if plan.get('question') and plan['question'] != question:
        raise ValueError('The saved comparison belongs to a different question.')
    output = {'version': 1, 'question': question, 'catalog': catalog_id(sources), 'queries': [],
              'planner': 'model' if plan.get('planner') == 'model' else 'columns',
              'unavailable': [str(item)[:500] for item in _strings(plan.get('unavailable', []), 12)]}
    for raw in plan['queries']:
        if not isinstance(raw, dict) or not isinstance(raw.get('columns'), list) or not 1 <= len(raw['columns']) <= 12:
            raise ValueError('Each comparison needs between one and twelve source columns.')
        query = {'title': str(raw.get('title') or question)[:180], 'columns': [], 'groupBy': [], 'where': [], 'having': [], 'cohorts': [], 'calculations': []}
        for column in raw['columns']:
            if not isinstance(column, dict) or not isinstance(column.get('source'), str) or column['source'] not in sources:
                raise ValueError('A requested report source is unavailable.')
            source, key = column['source'], column.get('field')
            if not isinstance(key, str) or key not in sources[source]['columns']:
                raise ValueError('A requested field does not exist in the uploaded columns.')
            operation = column.get('operation', 'default')
            if not isinstance(operation, str) or operation not in OPS:
                raise ValueError('That calculation is not supported. Use total, mean, min, max, median, standard deviation or count.')
            query['columns'].append({'source': source, 'field': key, 'operation': operation})
        for key in _strings(raw.get('groupBy', ['machine']), 4):
            if not isinstance(key, str) or not any(key in sources[c['source']]['columns'] for c in query['columns']):
                raise ValueError('A grouping column does not exist in the selected reports.')
            if key not in query['groupBy']:
                query['groupBy'].append(key)
        predicates = raw.get('where', [])
        if not isinstance(predicates, list) or len(predicates) > 12:
            raise ValueError('Use at most twelve source filters per comparison.')
        for condition in predicates:
            if not isinstance(condition, dict) or not isinstance(condition.get('source'), str) or condition['source'] not in sources:
                raise ValueError('A filter source is unavailable.')
            if not isinstance(condition.get('field'), str) or condition['field'] not in sources[condition['source']]['columns'] or not isinstance(condition.get('operator'), str) or condition['operator'] not in PREDICATES:
                raise ValueError('A filter refers to an unavailable column or operation.')
            query['where'].append({k: condition[k] for k in ('source', 'field', 'operator')} | {'values': _strings(condition.get('values', []))})
        having = raw.get('having', [])
        if not isinstance(having, list) or len(having) > 12:
            raise ValueError('Use at most twelve aggregate filters.')
        for condition in having:
            if not isinstance(condition, dict) or type(condition.get('column')) is not int or not 0 <= condition['column'] < len(query['columns']) or not isinstance(condition.get('operator'), str) or condition['operator'] not in PREDICATES:
                raise ValueError('An aggregate filter refers to an unavailable result column.')
            query['having'].append({'column': condition['column'], 'operator': condition['operator'], 'values': _strings(condition.get('values', []))})
        cohorts = raw.get('cohorts', [])
        if not isinstance(cohorts, list) or len(cohorts) > 4:
            raise ValueError('Compare at most four date periods at a time.')
        for cohort in cohorts:
            if not isinstance(cohort, dict):
                raise ValueError('A comparison period needs a start and end date.')
            first, last = parse_date(cohort.get('from')), parse_date(cohort.get('to'))
            if not first or not last or first > last:
                raise ValueError('Each comparison period needs valid start and end dates.')
            query['cohorts'].append({'label': str(cohort.get('label') or f'{first} to {last}')[:100], 'from': first, 'to': last})
        formulas = raw.get('calculations', [])
        if not isinstance(formulas, list) or len(formulas) > 6:
            raise ValueError('Use at most six derived comparisons.')
        for calculation in formulas:
            if not isinstance(calculation, dict) or not isinstance(calculation.get('operation'), str) or calculation['operation'] not in {'difference', 'percent_change', 'ratio'} or any(type(calculation.get(k)) is not int or not 0 <= calculation[k] < len(query['columns']) for k in ('left', 'right')):
                raise ValueError('A derived comparison must reference existing numeric result columns.')
            query['calculations'].append({k: calculation[k] for k in ('operation', 'left', 'right')})
        sort_by = raw.get('sortBy')
        query['sortBy'] = sort_by if type(sort_by) is int and 0 <= sort_by < len(query['columns']) else None
        query['descending'] = raw.get('descending', True) is True
        limit = raw.get('limit', 500)
        query['limit'] = min(500, max(1, limit)) if type(limit) is int else 500
        compare_by = raw.get('compareBy', '')
        if not isinstance(compare_by, str):
            raise ValueError('The comparison dimension must be a column name.')
        if compare_by and compare_by not in [*query['groupBy'], 'period']:
            raise ValueError('The requested comparison dimension must also be a grouping column.')
        query.update(compareBy=compare_by, baseline=str(raw.get('baseline') or '')[:100], current=str(raw.get('current') or '')[:100])
        output['queries'].append(query)
    return output


def _preferred(sources, key, question):
    explicit = re.search(r'(?:from|in|using)\s+(?:the\s+)?(production|stoppage|breakage|quality|power|air)(?:\s+\w+)?\s+report', question)
    candidates = [(name, item) for name, item in sources.items() if key in item['columns']]
    if not candidates:
        return None
    owners = {'production_kg': 'production', 'actual_kg': 'production', 'target_kg': 'production', 'lot': 'production', 'count': 'production', 'tpi': 'production', 'tm': 'production'}
    owners.update({key: 'power' for key in ('energy_kwh', 'energy_per_kg', 'voltage', 'current', 'frequency', 'ukg', 'power_factor')})
    owners.update({key: 'breakage' for key in ('breaks', 'startup_breaks', 'eb100sph', 'end_mending_min', 'idle_spindles', 'rogue_spindles', 'slip_spindles', 'worst_spindles', 'waste_kg', 'waste_percent')})
    owners.update({key: 'quality' for key in ('cvm', 'unevenness', 'thick_places')})
    owners.update({key: 'air' for key in ('air_m3', 'air_cfm')})
    return min(candidates, key=lambda pair: (0 if explicit and pair[1]['table']['kind'] == explicit[1] else 1,
                                           0 if pair[1]['table']['kind'] == owners.get(key) else 1,
                                           ['production', 'stoppage', 'breakage', 'quality', 'power', 'air'].index(pair[1]['table']['kind'])))[0]


def named_operation(key, question, column):
    from python_engine.report_questions import ALIASES
    text = normalized_question(question)
    positions = list(re.finditer(ALIASES.get(key, re.escape(words(column['label']))), text))
    prefix = text[max(0, positions[0].start()-35):positions[0].start()] if positions else ''
    prefix = re.split(r'\band\b|[,;?]', prefix)[-1]
    modifiers = list(re.finditer(r'\b(total|sum|average|avg|mean|median|standard deviation|stddev|minimum|maximum|min|max)\b', prefix))
    return {'total': 'sum', 'sum': 'sum', 'average': 'mean', 'avg': 'mean', 'mean': 'mean', 'median': 'median', 'standard deviation': 'stddev', 'stddev': 'stddev', 'minimum': 'min', 'maximum': 'max', 'min': 'min', 'max': 'max'}[modifiers[-1][1]] if modifiers else None


def unresolved_words(reports, question):
    """Unfamiliar wording must reach interpretation instead of a default metric."""
    from python_engine.report_questions import ALIASES
    text = normalized_question(question)
    for pattern in ALIASES.values():
        text = re.sub(pattern, ' ', text)
    vocabulary = set('show give list tell me please compare comparison comparision versus vs with and or the a an of for in on by to from between during over under is are was were has have had do does did which what how much many more less than their its this that those these same each every all per machine machines wise machinewise report reports data values value selected period periods date dates day days daily shift shifts lot lots total sum average avg mean median min max minimum maximum standard deviation stddev highest lowest most least top bottom first last rank ranking ranked ascending descending overall grand combined only now include add also output metric metrics measure measures production stoppage breakage quality power air energy consumption kg kilograms rpm percent percentage time times today yesterday latest entire whole full recorded using actual target running run used use name names can could should would you we i want need get it week month year jan feb mar apr may jun jul aug sep oct nov dec january february march april june july august september october november december'.split())
    for report in reports:
        for table in report['tables']:
            vocabulary.update(words(c['label']).split()[i] for c in table['columns'] for i in range(len(words(c['label']).split())))
            for row in table['records']:
                for key in ('machine', 'lot'):
                    vocabulary.update(words(row['values'].get(key)).split())
    return [token for token in words(text).split() if not token.isdigit() and token not in vocabulary and not re.fullmatch(r'(?:rf|df|sf|bf|cf|lf|cm|oe|rs|ac)\d+', token)]


def local_plan(reports, question, previous=None):
    """Compile familiar requests from actual headers; return None for model planning."""
    from python_engine.report_questions import ALIASES, requested_fields, unmatched_parts
    text = normalized_question(question)
    sources = catalog(reports)
    if unresolved_words(reports, question) or re.search(r'weighted|normaliz|forecast|predict|correlat|relationship|variance|percentile|quartile|standard error', text):
        return None
    if re.search(r'compar.*\breports\b|across (?:the )?reports|between (?:the )?reports', text):
        return None
    if re.search(r'\b(?:ratio|per kg|per kilogram|correlat|relationship|percent.*(?:change|difference)|percentage.*(?:change|difference))\b', text):
        return None
    pieces = [piece.strip() for piece in re.split(r'[;?\n]+|\band\s+(?=(?:which|what|show|give|rank|compare)\b)', question) if piece.strip()]
    if len(pieces) > 6:
        return None
    queries = []
    for piece in pieces:
        part = normalized_question(piece)
        fields = requested_fields(piece, reports)
        inherited = not fields and previous and re.search(r'compare|versus|\bvs\b|same|also|those|these|^only\b|^for\b|^now for\b', part)
        if inherited:
            fields = previous.get('fields', [])
        if not fields or unmatched_parts(piece, reports):
            return None
        if re.search(r'\b(?:also|add|include those)\b', part) and previous:
            fields = list(dict.fromkeys([*previous.get('fields', []), *fields]))[:12]
        # Preserve the existing overview/catalog/reason workflows.
        if set(fields) <= {'stop_seconds', 'event_count', 'stop_reason'} or 'event_count' in fields or 'energy_per_kg' in fields:
            return None
        if re.search(r'highest|most|maximum|\btop\b', part) and re.search(r'lowest|least|minimum|\bbottom\b', part):
            return None
        columns, groups = [], []
        for key in fields:
            source = _preferred(sources, key, part)
            if source is None:
                return None
            column = sources[source]['columns'][key]
            operation = 'default'
            if inherited:
                prior_plan = previous.get('plan') if isinstance(previous.get('plan'), dict) else {}
                prior_columns = [c for q in prior_plan.get('queries', [])[:6] if isinstance(q, dict) for c in q.get('columns', [])[:12] if isinstance(c, dict)] if isinstance(prior_plan.get('queries', []), list) else []
                operation = next((c.get('operation', 'default') for c in prior_columns if c.get('field') == key), 'default')
            operation = named_operation(key, piece, column) or operation
            if key in DIMENSIONS and column['aggregation'] in {'identity', 'dimension'} and operation == 'default':
                if key not in groups:
                    groups.append(key)
                continue
            columns.append({'source': source, 'field': key, 'operation': operation})
        if not columns:
            return None
        for dimension, pattern in [('date', r'\bdaily\b|\btrend\b|date\s*wise|day\s*wise|by (?:date|day)|per day'), ('shift', r'shift\s*wise|by shift|per shift|compare.*shifts'), ('lot', r'lot\s*wise|by lot|per lot'), ('count', r'count\s*wise|by (?:yarn )?count')]:
            if re.search(pattern, part):
                groups.append(dimension)
        machine_group = re.search(r'\b(?:by|per|each|every|which) machine|machine\s*[- ]?\s*wise|compare.*machine|\b(?:RF|DF)\s*\d', part)
        if machine_group or not groups and not re.search(r'\b(?:overall|grand total|all machines combined)\b', part):
            groups.insert(0, 'machine')
        # Lot names accompanying a numeric metric are grouping identities.
        if 'lot' in fields and 'lot' not in groups:
            groups.append('lot')
            columns = [c for c in columns if c['field'] != 'lot']
        for key in groups:
            if any(key not in sources[c['source']]['columns'] for c in columns):
                return None
        query = {'title': piece, 'columns': columns, 'groupBy': list(dict.fromkeys(groups))[:4], 'where': [], 'cohorts': []}
        for source in dict.fromkeys(c['source'] for c in columns):
            for dimension, pattern in [('lot', r'lot\s*wise|by lot|per lot'), ('shift', r'shift\s*wise|by shift|per shift')]:
                if re.search(pattern, part) and dimension not in sources[source]['columns']:
                    return None
        # Select actual lot identifiers from the uploaded records, including
        # machine naming conventions beyond the earlier RF/DF patterns.
        for source in dict.fromkeys(c['source'] for c in columns):
            for key in ('lot', 'machine'):
                values = {str(r['values'][key]) for r in sources[source]['table']['records'] if r['values'].get(key) is not None}
                matches = [v for v in values if re.search(r'(?<![a-z0-9])'+re.escape(v.casefold()).replace(r'\ ', r'\s*')+r'(?![a-z0-9])', part)]
                if matches:
                    query['where'].append({'source': source, 'field': key, 'operator': 'in', 'values': sorted(matches)[:50]})
        dates = [parse_date(m[0]) for m in re.finditer(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b', part)]
        if len(dates) in {2, 4} and re.search(r'compar|versus|\bvs\b', part):
            ranges = [(d, d) for d in dates] if len(dates) == 2 and not re.search(r'\bfrom\b|\bbetween\b', part) else list(zip(dates[::2], dates[1::2]))
            if len(ranges) == 2:
                query['cohorts'] = [{'label': f'{a} to {b}' if a != b else a, 'from': a, 'to': b} for a, b in ranges]
                query['compareBy'] = 'period'
        shifts = list(dict.fromkeys(re.findall(r'\bshift\s*(?:no\.?\s*)?(\d+)', part)))
        if len(shifts) > 1:
            if 'shift' not in query['groupBy']:
                query['groupBy'].append('shift')
            for source in dict.fromkeys(c['source'] for c in columns):
                query['where'].append({'source': source, 'field': 'shift', 'operator': 'in', 'values': shifts})
        rank = bool(re.search(r'highest|lowest|most|least|maximum|minimum|\btop\b|\bbottom\b|\brank\b', part))
        if rank:
            query.update(sortBy=0, descending=not bool(re.search(r'lowest|least|minimum|\bbottom\b', part)))
            limit = re.search(r'\b(?:top|bottom)\s*(\d+)\b', part)
            query['limit'] = int(limit[1]) if limit else 1 if re.search(r'which machine', part) else 5
        if re.search(r'\b(?:above|below|greater|less|over|under|exceed|at least|at most)\b|[<>]=?', part):
            return None
        # Explicit metric/machine differences use the generic comparison result.
        if re.search(r'differen|how much more|how much less', part) and not query.get('compareBy'):
            return None
        queries.append(query)
    return validate_plan({'queries': queries, 'unavailable': []}, reports, question)


def _match(value, operator, expected, key=''):
    if value is None or not expected:
        return False
    if key == 'machine':
        value, expected = machine_key(str(value)), [machine_key(str(v)) for v in expected]
    if operator in {'eq', 'ne', 'in'}:
        matched = any(str(value).casefold() == str(v).casefold() or number(value) is not None and number(value) == number(v) for v in expected)
        return not matched if operator == 'ne' else matched
    if operator == 'contains':
        return any(str(v).casefold() in str(value).casefold() for v in expected)
    a, b = number(value), number(expected[0])
    if a is None or b is None:
        a, b = str(value).casefold(), str(expected[0]).casefold()
    return {'gt': lambda: a > b, 'gte': lambda: a >= b, 'lt': lambda: a < b, 'lte': lambda: a <= b}[operator]()


def _aggregate(records, key, operation, column):
    values = [r['values'][key] for r in records if r['values'].get(key) is not None]
    operation = operation if operation != 'default' else column['aggregation']
    if operation in {'identity', 'dimension', 'distinct'}:
        return ', '.join(map(str, sorted(set(values), key=lambda v: str(v)))) if values else None
    if operation == 'distinct_count':
        return len(set(values)) if records else None
    if operation == 'count':
        return len(values) if records else None
    numbers = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)]
    if not numbers:
        return None
    return {'sum': sum, 'mean': mean, 'min': min, 'max': max, 'median': median, 'stddev': pstdev}[operation](numbers)


def _key(value, key):
    return machine_key(str(value)) if key == 'machine' and value is not None else str(value) if value is not None else None


def _coverage(rows):
    if not rows or any(any(r['values'].get(key) is None for key in ('machine', 'date', 'shift')) for r in rows):
        return None
    return {tuple(_key(r['values'][key], key) for key in ('machine', 'date', 'shift')) for r in rows}


def _cell(value, unit='', operation=''):
    if value is None:
        return 'Unavailable'
    if isinstance(value, str):
        return value
    if not math.isfinite(value):
        return 'Unavailable'
    return format_duration(value) if unit == 'seconds' and operation not in {'count', 'distinct_count'} else format_number(value, 0 if operation in {'count', 'distinct_count'} else 2)


def execute_plan(reports, plan, *, scope=None, today=None, previous=None):
    question = plan['question']
    plan = validate_plan(plan, reports, question)
    sources = catalog(reports)
    dates = [r['values']['date'] for item in sources.values() for r in item['table']['records'] if r['values'].get('date')]
    selected_scope = query_scope('', [], today, scope) if isinstance(scope, dict) else query_scope(question, dates, today, (previous or {}).get('scope'))
    all_periods = [cohort for query in plan['queries'] for cohort in query['cohorts']]
    if all_periods and not isinstance(scope, dict):
        selected_scope.update({'from': min(c['from'] for c in all_periods), 'to': max(c['to'] for c in all_periods)})
    tables, notes, evidence, methods = [], list(plan['unavailable']), {}, []
    for query in plan['queries']:
        source_names = list(dict.fromkeys(c['source'] for c in query['columns']))
        methods.append('Group by: '+(', '.join(query['groupBy']) or 'overall')+'.')
        methods.extend('Filter '+p['field']+' '+p['operator']+' '+', '.join(map(str, p['values']))+'.' for p in query['where'])
        if len({str(v) for p in query['where'] if p['field'] == 'shift' for v in p['values']}) > 1 and not isinstance(scope, dict):
            selected_scope.pop('shift', None)
        groups = query['groupBy']
        compatible = all(all(key in sources[name]['columns'] for key in groups) for name in source_names)
        blocks = [list(range(len(query['columns'])))] if compatible else [[i for i, c in enumerate(query['columns']) if c['source'] == name] for name in source_names]
        if not compatible:
            notes.append('The selected reports do not share every grouping column. Their results are displayed separately.')
        for indexes in blocks:
            selected_columns = [query['columns'][i] for i in indexes]
            block_sources = list(dict.fromkeys(c['source'] for c in selected_columns))
            grouping = [key for key in groups if all(key in sources[name]['columns'] for name in block_sources)]
            matrix, row_groups, headers, units = {}, {}, [], []
            cohorts = query['cohorts'] or [{'label': '', 'from': None, 'to': None}]
            for column in selected_columns:
                info = sources[column['source']]['columns'][column['field']]
                operation = column['operation'] if column['operation'] != 'default' else info['aggregation']
                label = {'mean': 'Mean ', 'sum': 'Total ', 'min': 'Minimum ', 'max': 'Maximum ', 'median': 'Median ', 'stddev': 'Standard deviation ', 'count': 'Count of ', 'distinct_count': 'Distinct count of '}.get(operation, '') + info['label']
                if len(block_sources) > 1:
                    label += ' ['+sources[column['source']]['table']['kind']+']'
                headers.append(label)
                units.append('count' if operation in {'count', 'distinct_count'} else info['unit'])
                methods.append(label+'; '+operation+'; '+sources[column['source']]['report']['name']+'!'+letter(info['column']))
            for cohort in cohorts:
                active_scope = dict(selected_scope)
                if cohort['from']:
                    active_scope.update({'from': max(cohort['from'], selected_scope.get('from') or cohort['from']), 'to': min(cohort['to'], selected_scope.get('to') or cohort['to'])})
                for name in block_sources:
                    item = sources[name]
                    rows = filter_records(item['table']['records'], active_scope)
                    conditions = [p for p in query['where'] if p['source'] == name]
                    rows = [r for r in rows if all(_match(r['values'].get(p['field']), p['operator'], p['values'], p['field']) for p in conditions)]
                    used_columns = {c['field'] for c in selected_columns if c['source'] == name} | set(grouping) | {p['field'] for p in conditions}
                    record = evidence.setdefault(name, {'rows': {}, 'columns': set()})
                    record['rows'].update({r['row']: r for r in rows})
                    record['columns'].update(used_columns)
                    grouped = defaultdict(list)
                    for row in rows:
                        identity = tuple([*([cohort['label']] if query['cohorts'] else []), *[_key(row['values'].get(key), key) for key in grouping]])
                        grouped[identity].append(row)
                    if not grouping and not query['cohorts'] and not rows:
                        grouped[()] = []
                    for identity, records in grouped.items():
                        entry = matrix.setdefault(identity, {'values': [None]*len(selected_columns), 'counts': {}, 'labels': [*([cohort['label']] if query['cohorts'] else []), *[records[0]['values'].get(key) if records else None for key in grouping]]})
                        entry['counts'][name] = len(records)
                        row_groups[identity, name] = records
                        for i, column in enumerate(selected_columns):
                            if column['source'] == name:
                                info = item['columns'][column['field']]
                                entry['values'][i] = _aggregate(records, column['field'], column['operation'], info)
                                missing = sum(r['values'].get(column['field']) is None for r in records)
                                if missing:
                                    notes.append(f'{info["label"]}: {missing} missing selected cells excluded in {cohort["label"] or "this selection"}.')
            derived_headers = []
            for calculation in query['calculations']:
                if calculation['left'] not in indexes or calculation['right'] not in indexes:
                    notes.append('A derived calculation spans incompatible grouping columns and is unavailable.')
                    continue
                left, right = indexes.index(calculation['left']), indexes.index(calculation['right'])
                operation = calculation['operation']
                if operation != 'ratio' and (units[left].casefold() != units[right].casefold() or not units[left] and selected_columns[left]['field'] != selected_columns[right]['field']):
                    notes.append(f'Cannot subtract or calculate percent change between {headers[left]} and {headers[right]} because their units differ.')
                    continue
                derived_headers.append(f'{headers[left]} / {headers[right]}' if operation == 'ratio' else f'{headers[left]} − {headers[right]}' + (' (%)' if operation == 'percent_change' else ''))
                for identity, entry in matrix.items():
                    a, b = entry['values'][left], entry['values'][right]
                    name_a, name_b = selected_columns[left]['source'], selected_columns[right]['source']
                    same_coverage = name_a == name_b or (_coverage(row_groups.get((identity, name_a), [])) is not None and _coverage(row_groups.get((identity, name_a), [])) == _coverage(row_groups.get((identity, name_b), [])))
                    paired_values = all(isinstance(r['values'].get(selected_columns[i]['field']), (int, float)) for i, name in [(left, name_a), (right, name_b)] for r in row_groups.get((identity, name), []))
                    value = None
                    if same_coverage and paired_values and isinstance(a, (int, float)) and isinstance(b, (int, float)):
                        value = a-b if operation == 'difference' else a/b if operation == 'ratio' and b else (a-b)/abs(b)*100 if operation == 'percent_change' and b else None
                    entry.setdefault('derived', []).append(value)
                    if not same_coverage:
                        notes.append('A cross-report calculation was withheld where machine/date/shift coverage did not match.')
                    if not paired_values:
                        notes.append('A derived calculation was withheld where the paired source measurements were missing or nonnumeric.')
                    if b == 0 and operation != 'difference':
                        notes.append('Ratios and percentage changes with a zero denominator are unavailable.')
            entries = list(matrix.items())
            conditions = [p for p in query['having'] if p['column'] in indexes]
            entries = [(identity, entry) for identity, entry in entries if all(_match(entry['values'][indexes.index(p['column'])], p['operator'], p['values']) for p in conditions)]
            entries.sort(key=lambda pair: tuple(re.sub(r'\d+', lambda match: match[0].zfill(20), '' if value is None else str(value)) for value in pair[0]))
            if query['sortBy'] in indexes:
                position = indexes.index(query['sortBy'])
                entries.sort(key=lambda pair: (not isinstance(pair[1]['values'][position], (int, float)), -(pair[1]['values'][position] or 0) if query['descending'] and isinstance(pair[1]['values'][position], (int, float)) else pair[1]['values'][position] if isinstance(pair[1]['values'][position], (int, float)) else 0))
            count_headers = ['Records' if len(block_sources) == 1 else sources[name]['table']['kind'].title()+' records' for name in block_sources]
            result_headers = [*(['Period'] if query['cohorts'] else []), *[key.replace('_', ' ').title() for key in grouping], *headers, *derived_headers, *count_headers]
            output = [[*['Unavailable' if value is None else str(value) for value in entry['labels']], *[_cell(value, units[i], selected_columns[i]['operation']) for i, value in enumerate(entry['values'])], *[_cell(value) for value in entry.get('derived', [])], *[str(entry['counts'].get(name, 0)) for name in block_sources]] for _, entry in entries[:query['limit']]]
            tables.append({'title': query['title'], 'headers': result_headers, 'rows': output, 'totalRows': len(entries), 'fields': [*grouping, *[c['field'] for c in selected_columns]], 'kind': sources[block_sources[0]]['table']['kind'] if len(block_sources) == 1 else 'comparison'})
            if len(entries) > query['limit']:
                notes.append(f'Showing {query["limit"]} of {len(entries)} result groups. Narrow the filters to see other rows.')
            compare_by = query['compareBy']
            identity_keys = [*(['period'] if query['cohorts'] else []), *grouping]
            if compare_by in identity_keys and len(entries) > 1:
                position = identity_keys.index(compare_by)
                buckets = defaultdict(list)
                for identity, entry in entries:
                    buckets[tuple(v for i, v in enumerate(identity) if i != position)].append((identity[position], entry))
                comparisons = []
                for other, items in buckets.items():
                    candidates = sorted(items, key=lambda pair: str(pair[0]))
                    baseline = next((p for p in candidates if _key(p[0], compare_by) == _key(query['baseline'], compare_by)), None) if query['baseline'] else candidates[0]
                    if baseline is None:
                        notes.append('The requested baseline has no matching records in this selection.')
                        continue
                    for current in candidates:
                        if current is baseline or query['current'] and _key(current[0], compare_by) != _key(query['current'], compare_by):
                            continue
                        for i, label in enumerate(headers):
                            a, b = current[1]['values'][i], baseline[1]['values'][i]
                            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                                comparisons.append([*map(str, other), label, str(baseline[0]), str(current[0]), _cell(b, units[i]), _cell(a, units[i]), _cell(a-b, units[i]), _cell((a-b)/abs(b)*100 if b else None)+'%' if b else 'Unavailable'])
                if comparisons:
                    tables.append({'title': query['title']+' · comparison', 'headers': [*[key.title() for key in identity_keys if key != compare_by], 'Measure', 'Baseline', 'Compared', 'Baseline value', 'Compared value', 'Difference', 'Change (%)'], 'rows': comparisons[:500], 'totalRows': len(comparisons)})
                    notes.append('Change is (compared − baseline) / |baseline| × 100. Different measurement units keep separate scales. Observed totals are not normalized for unequal coverage.')
            if len(block_sources) > 1:
                notes.append('Report families were aggregated independently, then aligned by the displayed identities. Missing values remain unavailable; detail rows were not multiplied by a raw cross-report join.')
    provenance = []
    for name, used in evidence.items():
        item = sources[name]
        cols = sorted((item['columns'][key] for key in used['columns'] if key in item['columns']), key=lambda c: c['column'])
        provenance.append({'file': item['report']['name'], 'reportId': item['report'].get('id'), 'sheet': item['table']['sheet'], 'headerRow': item['table']['headerRow'],
                           'metric': ', '.join(c['label'] for c in cols), 'column': letter(cols[0]['column']) if cols else '', 'columns': [letter(c['column']) for c in cols],
                           'rows': sorted(used['rows']), 'records': len(used['rows']), 'summaryRowsExcluded': len(item['table']['summaries']), 'complete': item['report']['complete'], 'digest': item['report']['digest']})
        notes.extend(item['report'].get('warnings', []))
        overall = next((row for row in reversed(item['table']['summaries']) if re.search(r'overall summary|grand total', row['label'], re.I)), None)
        for key in ('production_kg', 'energy_kwh'):
            stated = overall['values'].get(key) if overall else None
            total = aggregate(item['table']['records'], key, 'sum')
            if stated is not None and total is not None and abs(stated-total) > .005:
                notes.append(f'{item["report"]["name"]}: overall summary {format_number(stated)} differs from detail sum {format_number(total)} by {format_number(abs(stated-total))}. Detail records are used.')
    kinds = list(dict.fromkeys(sources[name]['table']['kind'] for name in evidence))
    if not tables:
        message = 'I need a supported column or a clearer comparison. '+(' '.join(plan['unavailable']) if plan['unavailable'] else 'Choose the measures, machines, dates, shifts or lots to compare.')
    else:
        notes.extend(['Means are arithmetic means of the selected nonempty machine-record cells. Summary rows are excluded.', 'Historical uploads do not establish a live machine state.'])
        message = '\n\n'.join([*['### '+t['title']+'\n\n'+_markdown_table(t['headers'], t['rows']) for t in tables], *['- '+note for note in dict.fromkeys(notes)]])
    fields = list(dict.fromkeys(c['field'] for q in plan['queries'] for c in q['columns']))
    query = {'question': question, 'title': question[:200], 'fields': fields, 'section': 'question', 'intent': 'comparison', 'tables': tables, 'notes': list(dict.fromkeys(notes)), 'message': message, 'sources': provenance, 'plan': plan, 'methods': list(dict.fromkeys(methods)), 'planner': plan['planner'],
             'machineCount': len({machine_key(row['values']['machine']) for used in evidence.values() for row in used['rows'].values()}),
             'recordCount': sum(len(used['rows']) for used in evidence.values())}
    return {'answer': message, 'summary': message, 'query': query, 'plan': plan, 'scope': selected_scope, 'fields': fields, 'groupBy': plan['queries'][0]['groupBy'][0] if plan['queries'] and plan['queries'][0]['groupBy'] else None,
            'intent': 'comparison' if tables else 'unmatched', 'tables': tables, 'sources': provenance, 'warnings': query['notes'], 'cards': [], 'kinds': kinds, 'kind': kinds[0] if len(kinds) == 1 else None, 'complete': all(sources[name]['report']['complete'] for name in evidence)}
