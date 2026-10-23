"""Performance views calculated from owned mill-report records.

Reference dashboards define presentation only. Targets must be supplied by the
user; recorded reason text does not establish a mechanical diagnosis.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import math
import re

from python_engine.mill_reports import (
    aggregate, filter_records, format_duration, format_number, letter,
    machine_key, normalized_question, parse_date, query_scope,
)


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    kind: str
    field: str
    mode: str
    unit: str
    direction: str = 'lower'
    scale: float = 1


METRICS = (
    Metric('production', 'Total production', 'production', 'production_kg', 'sum', 'kg', 'higher'),
    Metric('daily_output', 'Average daily output', 'production', 'production_kg', 'daily', 'kg/day', 'higher'),
    Metric('utilization', 'Mean utilization', 'production', 'utilization', 'mean', '%', 'higher'),
    Metric('efficiency', 'Mean production efficiency', 'production', 'efficiency', 'mean', '%', 'higher'),
    Metric('spindle_speed', 'Mean spindle speed', 'production', 'spindle_speed', 'mean', 'RPM', 'higher'),
    Metric('delivery_speed', 'Mean delivery speed', 'production', 'delivery_speed', 'mean', 'm/min', 'higher'),
    Metric('gpss_40s', 'Mean 40s GPSS', 'production', 'gpss_40s', 'mean', 'g', 'higher'),
    Metric('doff_time', 'Mean doff time', 'production', 'avg_doff_seconds', 'mean', 'min', 'lower', 1 / 60),
    Metric('stoppage', 'Recorded stoppage', 'stoppage', 'stop_seconds', 'sum', 'min', 'lower', 1 / 60),
    Metric('stop_events', 'Stoppage events', 'stoppage', 'event_count', 'sum', 'events'),
    Metric('breaks', 'Total end breaks', 'breakage', 'breaks', 'sum', 'breaks'),
    Metric('eb100sph', 'Mean EB/100SPH', 'breakage', 'eb100sph', 'mean', 'source %'),
    Metric('end_mending', 'Mean end mending time', 'breakage', 'end_mending_min', 'mean', 'min'),
    Metric('idle_spindles', 'Mean idle spindles', 'breakage', 'idle_spindles', 'mean', 'spindles/record'),
    Metric('rogue_spindles', 'Mean rogue spindles', 'breakage', 'rogue_spindles', 'mean', 'spindles/record'),
    Metric('worst_spindles', 'Mean worst spindles', 'breakage', 'worst_spindles', 'mean', 'spindles/record'),
    Metric('startup_breaks', 'Mean startup breaks', 'breakage', 'startup_breaks', 'mean', '%'),
    Metric('slip_spindles', 'Mean slip spindles', 'breakage', 'slip_spindles', 'mean', 'spindles/record'),
    Metric('waste_kg', 'Recorded pneumafil waste', 'breakage', 'waste_kg', 'sum', 'kg'),
    Metric('waste_percent', 'Mean waste', 'breakage', 'waste_percent', 'mean', '%'),
    Metric('cvm', 'Mean CVM', 'quality', 'cvm', 'mean', '%'),
    Metric('air', 'Air consumption', 'air', 'air_m3', 'sum', 'm³'),
    Metric('energy', 'Energy consumption', 'power', 'energy_kwh', 'sum', 'kWh'),
    Metric('energy_intensity', 'Calculated energy intensity', 'power', 'energy_per_kg', 'ratio', 'kWh/kg'),
)
BY_KEY = {metric.key: metric for metric in METRICS}


def clean_scope(value):
    return query_scope('', [], previous=value if isinstance(value, dict) else {})


def clean_targets(value):
    result = {}
    if not isinstance(value, dict):
        return result
    for key, target in value.items():
        if key not in BY_KEY or not isinstance(target, dict):
            continue
        limit = target.get('value')
        if isinstance(limit, bool) or not isinstance(limit, (int, float)) or not math.isfinite(limit) or limit < 0:
            continue
        op = target.get('operator', 'gte' if BY_KEY[key].direction == 'higher' else 'lte')
        if op in {'lte', 'gte'}:
            result[key] = {'value': float(limit), 'operator': op}
    return result


def value_for(rows, metric):
    if not rows:
        return None
    if metric.mode == 'daily':
        days = len({row['values'].get('date') for row in rows if row['values'].get('date')})
        total = aggregate(rows, metric.field, 'sum')
        return total / days if total is not None and days else None
    value = aggregate(rows, metric.field, metric.mode)
    return value * metric.scale if value is not None else None


def _difference(current, previous, metric, comparable=True):
    if current is None or previous is None or not comparable:
        return None
    delta = current - previous
    return {'absolute': delta, 'percent': delta / abs(previous) * 100 if previous else None,
            'unit': 'percentage points' if metric.unit in {'%', 'source %'} else metric.unit,
            'favorable': None if abs(delta) < 1e-10 else (delta > 0 if metric.direction == 'higher' else delta < 0)}


def _period(scope, available):
    first = scope.get('from') or (min(available) if available else None)
    last = scope.get('to') or (max(available) if available else None)
    return {'from': first, 'to': last,
            'days': (date.fromisoformat(last) - date.fromisoformat(first)).days + 1 if first and last else 0}


def _previous(period, comparison):
    if isinstance(comparison, dict):
        first, last = parse_date(comparison.get('from')), parse_date(comparison.get('to'))
        if first and last and first <= last:
            return _period({'from': first, 'to': last}, [])
        raise ValueError('Choose valid comparison dates with the start on or before the end.')
    if comparison is False or not period['from'] or not period['days']:
        return None
    end = date.fromisoformat(period['from']) - timedelta(days=1)
    return _period({'from': (end - timedelta(days=period['days'] - 1)).isoformat(), 'to': end.isoformat()}, [])


def _weekly_scope(question, dates, today, scope):
    text = normalized_question(question)
    current = date.fromisoformat(parse_date(today) or date.today().isoformat())
    if re.search(r'\b(?:this|current) week\b', text):
        start = current - timedelta(days=current.weekday())
        scope.update({'from': start.isoformat(), 'to': (start + timedelta(days=6)).isoformat()})
    elif re.search(r'\blast week\b', text):
        start = current - timedelta(days=current.weekday() + 7)
        scope.update({'from': start.isoformat(), 'to': (start + timedelta(days=6)).isoformat()})
    elif re.search(r'\b(?:latest|last) (?:available )?7 days\b|\blatest week\b', text) and dates:
        end = date.fromisoformat(max(dates))
        scope.update({'from': (end - timedelta(days=6)).isoformat(), 'to': end.isoformat()})
    return scope


def build_dashboard(reports, *, question='', scope=None, comparison=True, targets=None, today=None, kinds=None):
    """Keep each report family independent; align machine names only for display."""
    available_kinds = sorted({table['kind'] for report in reports for table in report['tables']})
    if isinstance(kinds, list):
        kinds = list(dict.fromkeys(kind for kind in kinds if isinstance(kind, str) and kind in available_kinds))
        if not kinds:
            raise ValueError('Choose a report type present in the attached workbooks.')
    else:
        kinds = ['production'] if 'production' in available_kinds else available_kinds
    notes, selected, fingerprints = [], {}, set()
    for report in reports:
        if report['digest'] in fingerprints:
            continue
        fingerprints.add(report['digest'])
        for table in report['tables']:
            kind = table['kind']
            if kind not in kinds:
                continue
            if kind in selected:
                notes.append(f'{report["name"]} / {table["sheet"]}: another {kind} table is attached. The dashboard uses {selected[kind][0]["name"]} / {selected[kind][1]["sheet"]}; remove it to choose this source. Tables are not added together.')
            else:
                selected[kind] = report, table
    all_dates = sorted({r['values']['date'] for _, table in selected.values() for r in table['records'] if r['values'].get('date')})
    scope = query_scope(question, all_dates, today, clean_scope(scope))
    scope = _weekly_scope(question, all_dates, today, scope)
    if re.search(r'compar|versus|\bvs\b', question, re.I):
        dates = [parse_date(match[0]) for match in re.finditer(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})\b', question)]
        dates = [value for value in dates if value]
        if len(dates) >= 4:
            comparison = {'from': dates[2], 'to': dates[3]}
    period = _period(scope, all_dates)
    if period['from'] and period['to'] and period['from'] > period['to']:
        raise ValueError('The start date must be on or before the end date.')
    if period['days'] > 3660:
        raise ValueError('Choose a report period of ten years or less.')
    baseline = _previous(period, comparison)
    if baseline and baseline['from'] <= period['to'] and baseline['to'] >= period['from']:
        raise ValueError('The comparison period must not overlap the report period.')
    targets = {key: target for key, target in clean_targets(targets).items() if BY_KEY[key].kind in kinds}
    current, prior, sources, daily, machines = {}, {}, [], defaultdict(dict), {}
    for kind, (report, table) in selected.items():
        rows = filter_records(table['records'], scope)
        past = filter_records(table['records'], {**scope, **({'from': baseline['from'], 'to': baseline['to']} if baseline else {})}) if baseline else []
        current[kind], prior[kind] = rows, past
        for row in rows:
            label = row['values']['machine']
            machines.setdefault(machine_key(label), {'machine': label, 'values': {}, 'records': {}, 'violations': []})
        days = sorted({row['values']['date'] for row in rows if row['values'].get('date')})
        past_days = sorted({row['values']['date'] for row in past if row['values'].get('date')})
        sources.append({'kind': kind, 'file': report['name'], 'sheet': table['sheet'], 'reportId': report.get('id'),
                        'headerRow': table['headerRow'], 'columns': [{'key': c['key'], 'label': c['label'], 'column': letter(c['column'])} for c in table['columns']],
                        'rows': [r['row'] for r in rows], 'records': len(rows), 'days': len(days),
                        'previousRecords': len(past), 'previousRows': [r['row'] for r in past], 'previousDays': len(past_days),
                        'summaryRowsExcluded': len(table['summaries']), 'complete': report['complete'], 'digest': report['digest']})
        notes.extend(report.get('warnings', []))
        if rows and period['days'] and len(days) < period['days']:
            notes.append(f'{kind.title()}: records on {len(days)} of {period["days"]} selected calendar days. Missing days are not treated as zero.')
        if baseline and len(past_days) < baseline['days']:
            notes.append(f'{kind.title()} comparison: {len(past_days)} of {baseline["days"]} calendar days have records. Full-period change is unavailable for incomplete coverage.')
        # A summary discrepancy remains visible in the visual report.
        overall = next((r for r in reversed(table['summaries']) if 'overall summary' in r['label'].casefold() or 'grand total' in r['label'].casefold()), None)
        for key in ('production_kg', 'energy_kwh'):
            stated = overall['values'].get(key) if overall else None
            computed = aggregate(table['records'], key, 'sum')
            if stated is not None and computed is not None and abs(stated - computed) > .005:
                col = next((letter(c['column']) for c in table['columns'] if c['key'] == key), '')
                notes.append(f'{report["name"]}!{col}{overall["row"]}: summary {format_number(stated)} differs from detail sum {format_number(computed)} by {format_number(abs(stated-computed))}. Detail records are used.')
    cards, compliance = [], []
    for metric in METRICS:
        if metric.kind not in kinds:
            continue
        table_info = selected.get(metric.kind)
        keys = {c['key'] for c in table_info[1]['columns']} if table_info else set()
        available = metric.field in keys or metric.field == 'event_count' and bool(table_info) or metric.field == 'energy_per_kg' and {'energy_kwh', 'production_kg'} <= keys
        rows, past = current.get(metric.kind, []), prior.get(metric.kind, [])
        value = value_for(rows, metric) if available else None
        previous = value_for(past, metric) if available else None
        day_groups, old_groups, machine_groups = defaultdict(list), defaultdict(list), defaultdict(list)
        for row in rows:
            if row['values'].get('date'):
                day_groups[row['values']['date']].append(row)
            machine_groups[machine_key(row['values']['machine'])].append(row)
        for row in past:
            if row['values'].get('date'):
                old_groups[row['values']['date']].append(row)
        source = next((s for s in sources if s['kind'] == metric.kind), None)
        # A partial final shift or changed fleet invalidates whole-period deltas.
        full_days = bool(source and baseline and source['days'] == period['days'] and source['previousDays'] == baseline['days'])
        def coverage_signature(records):
            result = defaultdict(set)
            for record in records:
                v = record['values']
                result[machine_key(v['machine'])].add((v.get('date'), v.get('shift')))
            return {key: dict(Counter(str(shift) for _, shift in values)) for key, values in result.items()}
        matched = full_days and coverage_signature(rows) == coverage_signature(past)
        change = _difference(value, previous, metric, bool(matched))
        status = 'unavailable' if value is None else 'unconfigured'
        target = targets.get(metric.key)
        daily_values = []
        for day, records in sorted(day_groups.items()):
            measured = value_for(records, metric) if available else None
            if measured is not None:
                daily[day][metric.key] = measured
                daily_values.append((day, measured))
        for name, records in machine_groups.items():
            if available:
                machines[name]['values'][metric.key] = value_for(records, metric)
                machines[name]['records'][metric.kind] = len(records)
        if value is not None and target:
            passes = lambda measured: measured <= target['value'] if target['operator'] == 'lte' else measured >= target['value']
            status = 'pass' if passes(value) else 'breach'
            compliant = sum(passes(v) for _, v in daily_values)
            for name, records in machine_groups.items():
                measured = value_for(records, metric)
                if measured is not None and not passes(measured):
                    machines[name]['violations'].append(metric.key)
        else:
            compliant = None
        missing = sum(row['values'].get(metric.field) is None for row in rows) if available and metric.field not in {'event_count', 'energy_per_kg'} else 0
        if missing:
            notes.append(f'{metric.label}: {missing} selected cells are missing; excluded from the calculation.')
        if metric.field == 'energy_per_kg':
            missing_pairs = sum(any(row['values'].get(key) is None for key in ('energy_kwh', 'production_kg')) for row in rows)
            if missing_pairs:
                notes.append(f'Energy intensity: {missing_pairs} records lack paired energy/production cells and are excluded from the ratio.')
        entry = {'key': metric.key, 'label': metric.label, 'kind': metric.kind, 'unit': metric.unit,
                 'value': value, 'previous': previous, 'change': change, 'direction': metric.direction,
                 'status': status, 'target': target, 'available': bool(available), 'records': len(rows),
                 'basis': 'sum / days with records' if metric.mode == 'daily' else 'sum' if metric.mode == 'sum' else 'summed paired kWh / summed paired kg' if metric.mode == 'ratio' else 'arithmetic mean of machine records',
                 'comparisonNote': 'Matched calendar-day and machine/shift coverage' if matched else 'Missing or unequal date, machine or shift coverage; change not calculated.'}
        cards.append(entry)
        if metric.key not in {'production', 'daily_output', 'stop_events', 'breaks', 'waste_kg', 'air', 'energy'}:
            compliance.append({**entry, 'daysPassing': compliant, 'daysMeasured': len(daily_values), 'flaggedMachines': sum(metric.key in m['violations'] for m in machines.values())})
    for machine in machines.values():
        for kind, rows in current.items():
            own = [r for r in rows if machine_key(r['values']['machine']) == machine_key(machine['machine'])]
            if kind == 'production':
                machine['runtimeSeconds'] = aggregate(own, 'runtime_seconds', 'sum')
                machine['speedRPM'] = aggregate(own, 'spindle_speed', 'mean')
                machine['lots'] = sorted({r['values']['lot'] for r in own if r['values'].get('lot')})
            if kind == 'stoppage' and own:
                by_reason = defaultdict(float)
                for row in own:
                    by_reason[row['values'].get('stop_reason') or 'Unspecified'] += row['values'].get('stop_seconds') or 0
                machine['leadingReason'] = max(by_reason, key=by_reason.get)
    reason_groups = defaultdict(list)
    for row in current.get('stoppage', []):
        reason_groups[row['values'].get('stop_reason') or 'Unspecified'].append(row)
    stop_total = aggregate(current.get('stoppage', []), 'stop_seconds', 'sum') or 0
    reasons = []
    for reason, rows in reason_groups.items():
        seconds = aggregate(rows, 'stop_seconds', 'sum')
        reasons.append({'reason': reason, 'events': len(rows), 'seconds': seconds,
                        'minutes': seconds / 60 if seconds is not None else None,
                        'share': seconds / stop_total * 100 if seconds is not None and stop_total else None,
                        'machines': sorted({r['values']['machine'] for r in rows})})
    reasons.sort(key=lambda r: -(r['seconds'] or 0))
    production_machines = sorted([m for m in machines.values() if m['values'].get('production') is not None], key=lambda m: -m['values']['production'])
    stop_machines = sorted([m for m in machines.values() if m['values'].get('stoppage') is not None], key=lambda m: -m['values']['stoppage'])
    findings, actions = [], []
    def finding(title, detail, severity='info', metric=None, machine=None):
        findings.append({'title': title, 'detail': detail, 'severity': severity, 'metric': metric, 'machine': machine})
    if production_machines:
        top, low = production_machines[0], production_machines[-1]
        finding(f'{top["machine"]} leads recorded production', f'{format_number(top["values"]["production"])} kg across the selected period. Compare count mix, runtime and coverage before judging machine efficiency.', 'positive', 'production', top['machine'])
        prod_days = [(day, values['production']) for day, values in daily.items() if values.get('production') is not None]
        if len(prod_days) > 1:
            worst = min(prod_days, key=lambda item: item[1])
            finding('Lowest recorded production day', f'{worst[0]}: {format_number(worst[1])} kg. Check shift and machine coverage; a low total alone does not establish a production fault.', 'attention', 'production')
        if top != low:
            finding(f'{low["machine"]} has the lowest recorded output', f'{format_number(low["values"]["production"])} kg. Different yarn counts and run hours can explain part of this difference.', 'info', 'production', low['machine'])
    if stop_machines:
        top = stop_machines[0]
        finding(f'{top["machine"]} has the most downtime', f'{format_duration(top["values"]["stoppage"]*60)} across {top["records"].get("stoppage", 0)} events. Largest recorded reason: {top.get("leadingReason", "Unspecified")}.', 'attention', 'stoppage', top['machine'])
    for item in compliance:
        if item['status'] == 'breach':
            finding(item['label'] + ' exceeds its configured limit' if item['target']['operator'] == 'lte' else item['label'] + ' is below its configured target',
                    f'{format_number(item["value"])} {item["unit"]}; {item["daysPassing"]}/{item["daysMeasured"]} measured daily aggregates meet the user target.', 'attention', item['key'])
    for i, reason in enumerate(reasons[:3]):
        actions.append({'priority': 'High' if i == 0 else 'Medium', 'action': 'Review the events and confirm the recorded condition: ' + reason['reason'],
                        'evidence': f'{format_duration(reason["seconds"])} / {reason["events"]} events; {", ".join(reason["machines"][:6])}',
                        'owner': 'Assign owner', 'due': 'Set due date', 'status': 'Suggested', 'metric': 'stoppage'})
    for item in compliance:
        if item['status'] == 'breach':
            actions.append({'priority': 'High', 'action': 'Review ' + item['label'].lower() + ' by machine and shift; verify settings and operating conditions against your mill procedure.',
                            'evidence': f'{format_number(item["value"])} {item["unit"]}; user target {"≤" if item["target"]["operator"]=="lte" else "≥"} {item["target"]["value"]}',
                            'owner': 'Assign owner', 'due': 'Set due date', 'status': 'Suggested', 'metric': item['key']})
    if not targets:
        notes.append('No KPI limits are configured. Set your mill targets to calculate compliance and machine violations. Reference-report thresholds are not applied automatically.')
    if current.get('quality') and current.get('production'):
        p_names = {machine_key(r['values']['machine']) for r in current['production']}
        q_names = {machine_key(r['values']['machine']) for r in current['quality']}
        if p_names != q_names:
            notes.append('Quality and production reports cover different machine sets. Their values remain separate; no cross-machine quality/production correlation is inferred.')
    notes.extend(['Means are unweighted machine-record averages. Spindle counts are counts per record, not counts of flagged machines.',
                  'These uploads are historical records and do not establish current machine running/stopped status.'])
    if 'stoppage' in kinds:
        notes.append('Stoppage reasons are recorded messages. Suggested actions require engineering review; no maintenance ticket or completed work is inferred.')
    for metric in cards:
        if metric['available'] and metric['previous'] is not None and metric['change'] is None:
            # One compact explanation covers all affected cards.
            notes.append('Comparison values may be shown, but percentage changes are withheld when date or machine/shift coverage differs. Daily output divides by observed days; holidays are not inferred.')
            break
    daily_list = [{'date': day, **values} for day, values in sorted(daily.items())]
    if len(daily_list) > 366:
        notes.append('Trend display is limited to the latest 366 dates. KPI totals still use all selected records.')
        daily_list = daily_list[-366:]
    return {'schema': 1, 'title': 'Chopper performance analysis', 'scope': scope, 'period': period, 'kinds': kinds,
            'comparison': baseline, 'targets': targets, 'metrics': cards, 'daily': daily_list,
            'machines': sorted(machines.values(), key=lambda m: m['machine']), 'topMachines': [m['machine'] for m in production_machines[:5]],
            'bottomMachines': [m['machine'] for m in reversed(production_machines[-5:])], 'reasons': reasons,
            'compliance': compliance, 'findings': findings, 'actions': actions[:20], 'notes': list(dict.fromkeys(notes)),
            'sources': sources, 'complete': all(report['complete'] for report, _ in selected.values()),
            'available': {'kinds': available_kinds, 'from': all_dates[0] if all_dates else None, 'to': all_dates[-1] if all_dates else None,
                          'machines': sorted({r['values']['machine'] for _, t in selected.values() for r in t['records']}),
                          'shifts': sorted({str(r['values']['shift']) for _, t in selected.values() for r in t['records'] if r['values'].get('shift')})},
            'machineCount': len(machines), 'recordCount': sum(len(rows) for rows in current.values())}
