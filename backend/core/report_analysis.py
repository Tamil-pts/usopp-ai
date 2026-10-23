"""Owned, opaque references to full report records used by Chopper calculations."""
from pathlib import Path
import json
import re
from uuid import uuid4

from fastapi import HTTPException
from backend.core.access import claim_resource, require_resource
from backend.core.assist_progress import report as progress
from backend.core.runtime import WORK
from python_engine.mill_reports import parse_report, report_summary, analyze_reports


def attach_report(name: str, content: bytes):
    if Path(name).suffix.casefold() not in {'.xlsx', '.xls', '.csv'}:
        return None
    parsed = parse_report(name, content)
    if parsed is None:
        return None
    identifier = uuid4().hex
    directory = WORK / ('chopper_report_' + identifier)
    directory.mkdir(parents=True)
    claim_resource(directory)
    parsed['id'] = identifier
    parsed['name'] = Path(name.replace('\\', '/')).name
    suffix = Path(parsed['name']).suffix.casefold()
    (directory / ('source' + suffix)).write_bytes(content)
    (directory / 'report.json').write_text(json.dumps(parsed, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    summary = {**report_summary(parsed), 'id': identifier}
    coverage = 'Complete records read' if summary['complete'] else 'Partial records; reading limit reached'
    notice = (f'{summary["label"]} report: {summary["records"]:,} machine records, '
              f'{summary["machines"]} machines; {summary["dateFrom"] or "date unspecified"} to {summary["dateTo"] or "date unspecified"}. '
              f'{coverage}. {summary["summaryRowsExcluded"]} summary rows excluded from calculations.')
    return {'readable': True, 'text': notice, 'notice': notice, 'report': summary}


def load_report(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise HTTPException(400, 'Invalid report attachment reference. Attach the workbook again.')
    directory = WORK / ('chopper_report_' + identifier)
    require_resource(directory)
    path = directory / 'report.json'
    if not path.is_file():
        raise HTTPException(404, 'The report attachment has expired or was cleared. Attach the workbook again.')
    document = json.loads(path.read_text(encoding='utf-8'))
    if document.get('schema', 0) < 3:
        source = directory / ('source' + Path(document['name']).suffix.casefold())
        if source.is_file():
            refreshed = parse_report(document['name'], source.read_bytes())
            if refreshed:
                document = {**refreshed, 'id': identifier}
                temporary = directory / ('report_' + uuid4().hex + '.json')
                temporary.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False), encoding='utf-8')
                temporary.replace(path)
    return document, directory


def dashboard_request(payload):
    from python_engine.mill_dashboard import build_dashboard
    identifiers = payload.get('reportIds')
    if not isinstance(identifiers, list) or not identifiers or len(identifiers) > 10 or any(not isinstance(item, str) for item in identifiers):
        raise HTTPException(400, 'Attach between one and ten report files.')
    reports = [load_report(item)[0] for item in dict.fromkeys(identifiers)]
    try:
        question = str(payload.get('question') or '')[:20000]
        analysis = None
        if question:
            from backend.core.report_planner import resolve_question
            analysis = resolve_question(reports, question, today=payload.get('today'), scope_override=payload.get('scope'), saved_plan=payload.get('plan'),
                                        previous={'fields': payload.get('fields'), 'groupBy': payload.get('groupBy')})
        dashboard = build_dashboard(reports, question='', kinds=dashboard_kinds(reports, analysis, payload.get('kinds')),
                               scope=analysis['scope'] if analysis else payload.get('scope'), comparison=payload.get('comparison', True),
                               targets=payload.get('targets'), today=payload.get('today'))
        if analysis:
            bind_query(dashboard, analysis, reports)
        return dashboard
    except ValueError as error:
        raise HTTPException(422, str(error))


def reply_if_report(payload):
    context = payload.get('context') if isinstance(payload.get('context'), dict) else {}
    attachments = context.get('attachments') or []
    if not isinstance(attachments, list):
        return None
    identifiers = list(dict.fromkeys(item.get('reportId') for item in attachments[:10]
                                    if isinstance(item, dict) and isinstance(item.get('reportId'), str)))
    if not identifiers:
        return None
    question = str(payload.get('question') or 'Analyze my reports.')
    report_terms = r'report|production|quality|breakage|stoppage|consumption|kwh|cvm|downtime|machine|shift|ranking|highest|lowest|dashboard|performance|utili[sz]|efficien|compliance|spindle|mending|doff|\bkpi\b|\btpi\b|\btm\b|\blots?\b|yarn count'
    if re.search(r'\b(?:WorkHub|ByteMap|MetaWorks|DataInspect|MatchView|LogicScan|KnowHub|ResultView)\b', question, re.I):
        return None
    if re.search(r'\b(?:settings|password|login)\b', question, re.I) and not re.search(report_terms, question, re.I):
        return None
    if re.fullmatch(r'\s*(?:hello|hi|hey|thanks|thank you|good morning|good evening)[!.\s]*', question, re.I):
        return None
    # Explicit project/source questions retain their established assistant path.
    if re.search(r'\b(?:PLC code|source code|ladder|subroutine|function block|variable declaration|packet|group code)\b', question, re.I) and not re.search(r'\b(?:report|spreadsheet|workbook)\b', question, re.I):
        return None
    if re.search(r'\b(?:selected project|Automation Studio|machine functions|operating sequence|function flow|motor interlock|SpinConnect)\b', question, re.I) and not re.search(r'\b(?:report|production|quality|stoppage|tpi|lots?|yarn count)\b', question, re.I):
        return None
    progress('Calculating results from the uploaded report records')
    reports = [load_report(identifier)[0] for identifier in identifiers]
    previous = context.get('reportQuery') if isinstance(context.get('reportQuery'), dict) else None
    controls = context.get('reportDashboard') if isinstance(context.get('reportDashboard'), dict) else {}
    if isinstance(controls.get('scope'), dict):
        previous = {**(previous or {}), 'scope': controls['scope']}
    from backend.core.report_planner import resolve_question
    analysis = resolve_question(reports, question, today=context.get('reportToday'), previous=previous)
    from python_engine.mill_dashboard import build_dashboard
    try:
        dashboard = build_dashboard(reports, question='' if analysis.get('plan') else question, scope=analysis['scope'], kinds=dashboard_kinds(reports, analysis, controls.get('kinds')),
                                    comparison=controls.get('comparison', True), targets=controls.get('targets'), today=context.get('reportToday'))
    except ValueError as error:
        raise HTTPException(422, str(error))
    if dashboard['scope'] != analysis['scope']:
        analysis = resolve_question(reports, question, today=context.get('reportToday'), previous=previous, scope_override=dashboard['scope'], saved_plan=analysis.get('plan'))
    bind_query(dashboard, analysis, reports)
    analysis['dashboard'] = dashboard
    analysis['summary'] = analysis.get('summary') or conversation_summary(analysis, dashboard, question)
    choices = [{'label': 'All machines for this question', 'action': 'suggest:Show all machines for '+question},
               {'label': 'Show lots and yarn counts', 'action': 'suggest:Show machine-wise lot names and yarn counts.'}]
    if analysis.get('intent') == 'unmatched':
        choices = [{'label': 'Available report columns', 'action': 'suggest:List the available report columns.'}]
    return {'answer': analysis.pop('answer'), 'source': 'local-mill-report', 'model': None,
            'evidence': [], 'reportAnalysis': analysis, 'choices': choices,
            'semanticReviewRequired': False}


def dashboard_kinds(reports, analysis=None, requested=None):
    """The question selects its source families; the initial view is production."""
    if analysis and analysis.get('kinds'):
        return analysis['kinds']
    question = (analysis or {}).get('question', '')
    if re.search(r'\ball (?:attached )?reports?\b|\ball report (?:types|families)\b|\bcombined dashboard\b', question, re.I):
        return sorted({table['kind'] for report in reports for table in report['tables']})
    return requested if isinstance(requested, list) else None


def bind_query(dashboard, analysis, reports):
    from python_engine.mill_reports import filter_records, machine_key
    query = analysis['query']
    matched = {(source['file'], source['sheet']) for source in analysis.get('sources', [])}
    rows = [row for report in reports for table in report['tables']
            if (report['name'], table['sheet']) in matched
            for row in filter_records(table['records'], dashboard['scope'])]
    query.setdefault('machineCount', len({machine_key(row['values']['machine']) for row in rows}))
    query.setdefault('recordCount', sum(source['records'] for source in analysis.get('sources', [])))
    dashboard['query'] = query


def conversation_summary(analysis, dashboard, question):
    from python_engine.mill_reports import _markdown_table, format_number
    period = dashboard['period']
    heading = f'**{period["from"] or "Uploaded records"} to {period["to"] or "latest record"}**'
    if re.search(r'\b(?:performance|dashboard|executive|weekly|overview|summary|summarize)\b', question, re.I):
        metrics = [m for m in dashboard['metrics'] if m['key'] in {'production', 'daily_output', 'utilization', 'stoppage', 'cvm'} and m['value'] is not None]
        rows = [[m['label'], format_number(m['value'])+' '+m['unit']] for m in metrics]
        findings = ['- '+item['title']+'. '+item['detail'] for item in dashboard['findings'][:3]]
        return '\n\n'.join([heading, _markdown_table(['Measure', 'Selected period'], rows), *findings, 'Explore the dashboard sections for trends, KPI compliance and suggested actions.'])
    if analysis.get('kind') == 'stoppage':
        table = (analysis.get('tables') or [None])[0]
        ranking = _markdown_table(table['headers'], table['rows']) if table else ''
        reason_block = re.search(r'(\*\*Recorded (?:reasons|stoppage reasons)[\s\S]*?)(?=\n\n(?:Showing|Largest recorded|These are|Source:)|$)', analysis['answer'])
        return '\n\n'.join(part for part in [heading, ranking, reason_block[1] if reason_block else '', 'Reasons are the recorded machine messages. The dashboard shows their duration and event counts.'] if part)
    tables = analysis.get('tables') or []
    if tables:
        return '\n\n'.join([heading, *[_markdown_table(table['headers'], table['rows']) for table in tables[:2]], 'Open the dashboard for the full period summary, trends and source coverage.'])
    return analysis['answer']
