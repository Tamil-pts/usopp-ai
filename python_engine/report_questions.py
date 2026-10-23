"""Resolve report questions against column headers before calculating an answer.

An unrecognized request never becomes a workbook's default measure. Distinct
TPI/count/lot combinations retain their relationships in the original records.
"""
from collections import defaultdict
import re

from python_engine.mill_reports import (
    _markdown_table, _scope_label, aggregate, analyze_reports, filter_records,
    format_duration, format_number, letter, machine_key, normalized_question,
    query_scope, words,
)

ALIASES = {
    'tpi': r'\btpi\b|twists? per inch', 'tm': r'\btm\b|twist multiplier',
    'count': r'\byarn count\b|\bcounts?\b|\bhank\b',
    'lot': r'\blots?\b|\bbatch(?:es)?\b',
    'production_kg': r'\bproduction\b|\boutput\b|produced',
    'actual_kg': r'actual production', 'target_kg': r'target production',
    'runtime_seconds': r'\brun\s*time\b|\bruntime\b|running hours',
    'idle_seconds': r'idle time', 'doff_seconds': r'doff time',
    'avg_doff_seconds': r'(?:average|avg)\.? doff', 'doffs': r'\bdoffs?\b',
    'utilization': r'utili[sz]ation|\buti\b', 'efficiency': r'efficien',
    'spindle_speed': r'spindles?\s+speeds?|\brpm\b', 'delivery_speed': r'delivery\s+speeds?',
    'gpss_40s': r'40s gpss?', 'gpss': r'\bgpss?\b',
    'breaks': r'breakage|total break|end breaks|\bbreaks?\b',
    'startup_breaks': r'startup (?:end )?break', 'eb100sph': r'eb.?100|100.?sph|\bebhsh\b',
    'end_mending_min': r'end mending|mending time|\bemt\b',
    'idle_spindles': r'idle spindle', 'slip_spindles': r'slip spindle',
    'rogue_spindles': r'rogue spindle|rouge spindle', 'worst_spindles': r'worst spindle',
    'waste_kg': r'\bwaste\b|\bwastage\b', 'waste_percent': r'waste\s*(?:%|percent)',
    'cvm': r'\bcvm\b|\bquality\b', 'unevenness': r'unevenness|\bu\s*%',
    'thick_places': r'thick place', 'air_m3': r'\bair\b', 'air_cfm': r'\bcfm\b',
    'energy_kwh': r'\bkwh\b|energy|power consumption',
    'energy_per_kg': r'kwh\s*/\s*kg|energy per|power per|energy intens',
    'power_factor': r'power factor', 'voltage': r'voltage', 'current': r'\bcurrent\b',
    'frequency': r'frequency|\bhz\b', 'spindles': r'allotted spindle', 'worked_spindles': r'worked spindle',
    'stop_seconds': r'stoppage|stopped|downtime|down time|stop reason|\bstops?\b',
    'stop_reason': r'\breasons?\b',
    'event_count': r'number of.*stop|event count|most.*(?:stops|events)|stoppage (?:count|events)|count.*(?:stops|events)',
}
IDENTITIES = {'machine', 'date', 'shift', 'lot'}
DIMENSIONS = {'count', 'tpi', 'tm'}
PRIORITY = {'production': 0, 'stoppage': 1, 'breakage': 2, 'air': 3, 'power': 4, 'quality': 5}
LABELS = {'tpi': 'TPI', 'count': 'Yarn count', 'lot': 'Lot', 'tm': 'Twist multiplier',
          'spindle_speed': 'Spindle speed (RPM)', 'delivery_speed': 'Delivery speed (M/Min)'}


def requested_fields(question, reports):
    text = normalized_question(question)
    selected = [key for key, pattern in ALIASES.items() if re.search(pattern, text)]
    if 'count' in selected and re.search(r'event count|stoppage count|count.*(?:stops|events)|number of|how many', text) and not re.search(r'yarn count', text):
        selected.remove('count')
    if 'current' in selected and re.search(r'current (?:lot|batch|week|day|month|period|machine|report|shift)', text):
        selected.remove('current')
    normalized = words(text)
    # Match unanticipated headers by their full descriptive name. Avoid short
    # one-letter columns and generic identity words as accidental matches.
    for report in reports:
        for table in report['tables']:
            for column in table['columns']:
                label = re.sub(r'\([^)]*\)', '', column['label']).strip()
                label = words(label)
                if len(label) >= 4 and column['key'] not in IDENTITIES and re.search(r'\b' + re.escape(label) + r'\b', normalized):
                    if column['key'] not in selected:
                        selected.append(column['key'])
    # Suppress a broad alias only when every occurrence belongs to a specific
    # phrase. "Production and target production" requests both columns.
    broader = {'production_kg': ['actual_kg', 'target_kg'], 'doff_seconds': ['avg_doff_seconds'],
               'gpss': ['gpss_40s'], 'air_m3': ['air_cfm'], 'energy_kwh': ['energy_per_kg'],
               'waste_kg': ['waste_percent'], 'breaks': ['startup_breaks'], 'stop_seconds': ['event_count']}
    for broad, specifics in broader.items():
        remainder = text
        for specific in specifics:
            if specific in selected:
                remainder = re.sub(ALIASES[specific], ' ', remainder)
        if broad in selected and not re.search(ALIASES[broad], remainder):
            selected.remove(broad)
    return selected


def is_overview(question):
    text = normalized_question(question)
    return bool(re.search(r'\b(?:performance|dashboard|executive|overview|summary|summarize|analyse|analyze|analysis|review)\b', text))


def unmatched_parts(question, reports):
    """Disclose unsupported extra requests instead of silently dropping them."""
    parts = re.split(r'\band\b|\balso\b|[;?\n]', normalized_question(question))
    if len(parts) < 2:
        return []
    missing = []
    for part in parts:
        if requested_fields(part, reports) or is_overview(part):
            continue
        remainder = re.sub(r'\b(?:RF|DF)\s*0*\d+\b|\d{4}-\d{2}-\d{2}|\d+', ' ', part, flags=re.I)
        remainder = re.sub(r'\b(?:show|give|list|compare|the|a|an|of|for|in|on|by|to|from|with|all|each|machine|machines|wise|machinewise|date|dates|day|days|shift|shifts|selected|period|today|yesterday|this|that|same|last|week|month|why|please|highest|lowest|average|avg|mean|total)\b', ' ', remainder)
        if re.search(r'[a-z]{3}', remainder):
            missing.append(part.strip(' ,.:'))
    return missing


def _scope(reports, question, today, previous):
    dates = [r['values']['date'] for report in reports for table in report['tables'] for r in table['records'] if r['values'].get('date')]
    scope = query_scope(question, dates, today, (previous or {}).get('scope'))
    if isinstance((previous or {}).get('focusMachine'), str) and re.search(r'\b(?:that|this|same) machine\b(?!\s*[- ]?\s*wise)|\bits\b', question, re.I) and not scope.get('machines'):
        scope['machines'] = [machine_key(previous['focusMachine'])]
    return scope


def _finish(analysis, question, fields, section='question'):
    if section == 'question' and re.search(r'\bdashboard\b|\bexecutive summary\b|\boverview\b', normalized_question(question)) and analysis.get('intent') != 'unmatched':
        section = 'overview'
    analysis['fields'] = fields
    analysis['question'] = question
    analysis['intent'] = analysis.get('intent', 'calculation')
    analysis['query'] = {'question': question, 'title': question.strip()[:200],
                         'fields': fields, 'section': section, 'intent': analysis['intent'],
                         'groupBy': analysis.get('groupBy'),
                         'tables': analysis.get('tables', []), 'notes': analysis.get('warnings', []),
                         'message': analysis.get('summary') or analysis['answer'], 'sources': analysis.get('sources', [])}
    return analysis


def _missing(reports, question, fields, scope):
    columns = list(dict.fromkeys(c['label'] for report in reports for table in report['tables'] for c in table['columns'] if c['key'] not in IDENTITIES))
    wanted = ', '.join(LABELS.get(key, key.replace('_', ' ')) for key in fields)
    answer = ('I could not find ' + wanted + ' in the attached report columns.' if fields else 'I could not match this question to a report column or supported calculation.')
    answer += '\n\nAvailable columns include: ' + ', '.join(columns[:30]) + '.\n\nAsk for a named column, machine/lot list, total, average, ranking or date/shift breakdown.'
    return _finish({'answer': answer, 'summary': answer, 'tables': [], 'cards': [], 'sources': [],
                    'scope': scope, 'kind': None, 'kinds': [], 'complete': all(r['complete'] for r in reports),
                    'intent': 'unmatched', 'warnings': []}, question, fields)


def answer_question(reports, question, *, today=None, previous=None, scope_override=None):
    """Answer the named columns or explain why no supported column matched."""
    previous = previous if isinstance(previous, dict) else {}
    if isinstance(previous.get('fields'), list):
        previous = {**previous, 'fields': [key for key in previous['fields'] if isinstance(key, str)][:16]}
    fields = requested_fields(question, reports)
    text = normalized_question(question)
    if re.search(r'\b(?:also|add|include that|include those)\b', text) and fields and isinstance(previous.get('fields'), list):
        fields = list(dict.fromkeys([*previous['fields'], *fields]))[:16]
    scope = query_scope('', [], today, scope_override) if isinstance(scope_override, dict) else _scope(reports, question, today, previous)
    if re.search(r'(?:available|list|show|which|what).*\b(?:columns|headers|fields|parameters)\b', text):
        headers = ['Report', 'Worksheet', 'Column', 'Field', 'Unit']
        rows = [[report['name'], table['sheet'], letter(column['column']), column['label'], column['unit']]
                for report in reports for table in report['tables'] for column in table['columns']]
        answer = _markdown_table(headers, rows)
        return _finish({'answer': answer, 'summary': answer, 'tables': [{'title': 'Available report columns', 'headers': headers, 'rows': rows}],
                        'scope': scope, 'cards': [], 'sources': [], 'kind': None, 'kinds': [], 'intent': 'catalog',
                        'warnings': [], 'complete': all(report['complete'] for report in reports)}, question, [])
    if not fields and re.search(r'\b(?:that|its|their|same|all machines|all shifts)\b', text) and isinstance(previous.get('fields'), list):
        fields = previous['fields'][:16]
    if not fields and is_overview(question):
        overview_reports = reports
        if not re.search(r'\ball (?:attached )?reports?\b|\bcombined dashboard\b|\ball report (?:types|families)\b', text):
            production = [{**report, 'tables': [table for table in report['tables'] if table['kind'] == 'production']} for report in reports]
            production = [report for report in production if report['tables']]
            if production:
                overview_reports = production
        result = analyze_reports(overview_reports, question, today=today, previous={'scope': scope}, scope_override=scope)
        return _finish(result, question, [], 'overview')
    if not fields:
        # An explicit column-independent machine listing is still meaningful.
        if re.search(r'\b(?:which|what|list|show|how many|number of)\b.*\bmachines?\b', text):
            fields = ['machine']
        else:
            return _missing(reports, question, fields, scope)
    # Preserve the full recorded-reason analysis for stoppage-only requests.
    if set(fields) <= {'stop_seconds', 'event_count', 'stop_reason'}:
        stop_reports = [{**r, 'tables': [t for t in r['tables'] if t['kind'] == 'stoppage']} for r in reports]
        stop_reports = [r for r in stop_reports if r['tables']]
        if stop_reports:
            result = analyze_reports(stop_reports, question, today=today, previous={**previous, 'scope': scope}, scope_override=scope)
            return _finish(result, question, fields, 'stoppage')
        return _missing(reports, question, fields, scope)
    return _tabular(reports, question, fields, scope, today, previous)


def _tabular(reports, question, fields, scope, today, previous=None):
    text = normalized_question(question)
    candidates, digests = [], set()
    for report in reports:
        if report['digest'] in digests:
            continue
        digests.add(report['digest'])
        for table in report['tables']:
            columns = {c['key']: c for c in table['columns']}
            if 'energy_per_kg' in fields and {'energy_kwh', 'production_kg'} <= columns.keys():
                columns['energy_per_kg'] = {**columns['energy_kwh'], 'key': 'energy_per_kg', 'label': 'Energy per production kg', 'unit': 'kWh/kg', 'aggregation': 'ratio'}
            matching = [key for key in fields if key in columns]
            if matching:
                candidates.append((report, table, columns, matching))
    remaining, chosen = set(fields), []
    while remaining:
        options = [item for item in candidates if remaining.intersection(item[3])]
        if not options:
            break
        best = min(options, key=lambda item: (-len(remaining.intersection(item[3])), PRIORITY.get(item[1]['kind'], 9)))
        matched = [key for key in fields if key in remaining and key in best[2]]
        chosen.append((*best[:3], matched))
        remaining.difference_update(matched)
    if not chosen:
        return _missing(reports, question, fields, scope)
    sections, sources, tables, notes = [], [], [], []
    for part in unmatched_parts(question, reports):
        notes.append(f'Could not match this additional request to a report column: "{part}". No substitute measure was used.')
    if remaining:
        notes.append('Not present in the attached columns: ' + ', '.join(LABELS.get(key, key.replace('_', ' ')) for key in fields if key in remaining) + '.')
    if len(chosen) > 1:
        notes.append('Requested columns occur in different source tables. Results remain separate; records from different report families are not added together.')
    rank = bool(re.search(r'highest|lowest|most|least|maximum|minimum|\btop\b|\bbottom\b|\brank\b', text))
    ascending = bool(re.search(r'lowest|least|minimum|\bbottom\b', text))
    if rank and 'cvm' in fields and not re.search(r'highest|most|maximum|worst|descending', text):
        ascending = True
    explicit_mean = bool(re.search(r'average|\bavg\b|\bmean\b', text))
    explicit_total = bool(re.search(r'\btotal\b|\bsum\b', text))
    list_only = all(key in IDENTITIES | DIMENSIONS for key in fields)
    count_distinct = bool(re.search(r'how many|number of|distinct count', text)) and list_only
    group_by = 'machine'
    if re.search(r'\b(?:also|same|that|its|those)\b', text) and (previous or {}).get('groupBy') in {'machine', 'date', 'shift', 'lot', 'count'}:
        group_by = previous['groupBy']
    if re.search(r'\b(?:daily|datewise|daywise|by date|per day|by day|trend)\b', text):
        group_by = 'date'
    elif re.search(r'\b(?:shiftwise|shift wise|by shift|per shift)\b', text):
        group_by = 'shift'
    elif re.search(r'\b(?:lotwise|lot wise|by lot|per lot)\b', text):
        group_by = 'lot'
    if re.search(r'\b(?:countwise|count wise|by (?:yarn )?count|per count)\b', text):
        group_by = 'count'
    for report, table, columns, requested in chosen:
        if table['kind'] == 'stoppage' and 'stop_reason' in requested:
            stop_result = analyze_reports([{**report, 'tables': [table]}], 'Show all recorded stoppage reasons. '+question, today=today, previous={'scope': scope}, scope_override=scope)
            sections.append(stop_result['answer'])
            tables.extend(stop_result.get('tables', []))
            sources.extend(stop_result.get('sources', []))
            notes.extend(stop_result.get('warnings', []))
            continue
        rows = filter_records(table['records'], scope)
        heading = f'{report["name"]} / {table["sheet"]} · {_scope_label(rows, scope)}'
        sections.append('### ' + heading)
        if not rows:
            sections.append('No records match the selected date, shift or machine filters.')
            continue
        values = defaultdict(list)
        dimensions = [key for key in requested if key in IDENTITIES | DIMENSIONS and key != group_by]
        # Keep actual TPI/count/lot combinations together instead of averaging
        # different yarn settings into a setting that never occurred.
        # Lot identifies which settings and speed measurements belong together,
        # including when numeric averages are requested in the same question.
        dimension_keys = [key for key in dimensions if key == 'lot' or
                          list_only and not (explicit_mean or explicit_total or rank or count_distinct)]
        for row in rows:
            identity = tuple(row['values'].get(key) for key in [group_by, *dimension_keys])
            values[identity].append(row)
        measures = [key for key in requested if key != group_by and key not in dimension_keys]
        headers = [LABELS.get(group_by, group_by.title()), *[LABELS.get(key, columns[key]['label']) for key in dimension_keys]]
        measure_headers, modes = [], {}
        for key in measures:
            column = columns[key]
            text_values = any(isinstance(row['values'].get(key), str) for row in rows)
            if count_distinct:
                mode = 'distinct_count'
            elif text_values or key in IDENTITIES or key in DIMENSIONS and not (explicit_mean or rank):
                mode = 'distinct'
            elif key in DIMENSIONS and rank:
                mode = 'min' if ascending else 'max'
            else:
                mode = 'mean' if explicit_mean else 'sum' if explicit_total and key not in DIMENSIONS else column['aggregation']
            modes[key] = mode
            label = LABELS.get(key, column['label'])
            if mode in {'mean', 'sum', 'max', 'min', 'distinct_count'}:
                label = {'mean': 'Mean ', 'sum': 'Total ', 'max': 'Maximum ', 'min': 'Minimum ', 'distinct_count': 'Distinct '}[mode] + label
            if column['unit'] == 'seconds':
                label = re.sub(r'\([^)]*\)', '(H:MM:SS)', label)
            measure_headers.append(label)
        lot_dates = 'lot' in requested and not rank
        headers.extend([*measure_headers, 'Records', *(['First recorded date', 'Last recorded date'] if lot_dates else [])])
        grouped = []
        for identities, records in values.items():
            cells = ['—' if value is None else format_number(value, 2).rstrip('0').rstrip('.') if isinstance(value, (int, float)) else str(value) for value in identities]
            sort_value = None
            for key in measures:
                column, mode = columns[key], modes[key]
                distinct = sorted({row['values'][key] for row in records if row['values'].get(key) is not None}, key=lambda v: (isinstance(v, str), v))
                if mode == 'distinct':
                    value = None
                    cell = ', '.join(format_number(v).rstrip('0').rstrip('.') if isinstance(v, (int, float)) else str(v) for v in distinct) or 'Unavailable'
                elif mode == 'distinct_count':
                    value, cell = len(distinct), str(len(distinct))
                elif mode in {'min', 'max'}:
                    numeric = [v for v in distinct if isinstance(v, (int, float))]
                    value = (min(numeric) if mode == 'min' else max(numeric)) if numeric else None
                    cell = format_number(value)
                else:
                    value = aggregate(records, key, mode)
                    cell = format_duration(value) if column['unit'] == 'seconds' else format_number(value, 0 if key in {'breaks', 'event_count', 'doffs'} else 2)
                if sort_value is None and value is not None:
                    sort_value = value
                cells.append(cell)
            dates = sorted({r['values']['date'] for r in records if r['values'].get('date')})
            grouped.append((cells + [str(len(records)), *([dates[0] if dates else 'Unavailable', dates[-1] if dates else 'Unavailable'] if lot_dates else [])], sort_value))
        grouped.sort(key=lambda item: _natural(item[0][0]))
        if rank:
            grouped.sort(key=lambda item: (item[1] is None, item[1] if ascending and item[1] is not None else -(item[1] or 0)))
        limit_match = re.search(r'\b(?:top|bottom|first)\s+(\d+)\b', text)
        limit = min(500, max(1, int(limit_match[1]))) if limit_match else 1 if rank and re.search(r'\bwhich machine\b', text) else 5 if rank else 500
        output = [item[0] for item in grouped[:limit]]
        tables.append({'title': heading, 'headers': headers, 'rows': output, 'totalRows': len(grouped), 'groupBy': group_by,
                       'fields': [group_by, *dimension_keys, *measures], 'kind': table['kind']})
        sections.append(_markdown_table(headers, output))
        if len(grouped) > limit:
            notes.append(f'Showing {limit} of {len(grouped)} grouped rows. Narrow the date or machine filters for the remaining combinations.')
        if dimensions and not explicit_mean:
            notes.append('Yarn count, TPI and lot values are actual settings found in the selected records. Mixed settings are listed as distinct values/combinations, not averaged.')
        source_columns = list(dict.fromkeys(columns[key]['column'] for key in [group_by, *requested] if key in columns))
        sources.append({'file': report['name'], 'reportId': report.get('id'), 'sheet': table['sheet'], 'headerRow': table['headerRow'],
                        'metric': ', '.join(columns[key]['label'] for key in requested), 'column': letter(source_columns[0]),
                        'columns': [letter(c) for c in source_columns], 'rows': [r['row'] for r in rows], 'records': len(rows),
                        'summaryRowsExcluded': len(table['summaries']), 'complete': report['complete'], 'digest': report['digest']})
        notes.extend(report.get('warnings', []))
        sections.append(f'Source: {report["name"]} → {table["sheet"]}; header row {table["headerRow"]}; columns {", ".join(letter(c) for c in source_columns)}. Summary rows excluded.')
    if 'lot' in fields:
        notes.append('These lots were recorded during the selected report period. Historical uploads do not identify the lot running live now.')
    if notes:
        sections.extend(['### Data notes', *['- '+note for note in dict.fromkeys(notes)]])
    answer = '\n\n'.join(sections)
    summary = '\n\n'.join([f'**{_scope_label([r for _, table, _, _ in chosen for r in filter_records(table["records"], scope)], scope)}**',
                             *[_markdown_table(table['headers'], table['rows']) for table in tables],
                             *['- '+note for note in dict.fromkeys(notes)]]) if tables else answer
    kinds = list(dict.fromkeys(item[1]['kind'] for item in chosen))
    result = {'answer': answer, 'summary': summary, 'cards': [], 'tables': tables, 'sources': sources, 'scope': scope,
              'kind': kinds[0] if len(kinds) == 1 else None, 'kinds': kinds, 'intent': 'ranking' if rank else 'projection',
              'warnings': list(dict.fromkeys(notes)), 'complete': all(report['complete'] for report, _, _, _ in chosen),
              'focusMachine': scope['machines'][0] if len(scope.get('machines', [])) == 1 else tables[0]['rows'][0][0] if rank and group_by == 'machine' and tables and len(tables[0]['rows']) == 1 else None, 'groupBy': group_by}
    return _finish(result, question, fields)


def _natural(value):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r'(\d+)', str(value))]
