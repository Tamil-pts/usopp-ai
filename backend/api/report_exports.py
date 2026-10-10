import json
import re
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend.core.runtime import WORK, EXPORTS, RESOURCE_ROOT
from backend.core.report_cover import ReportCover
from backend.core import rule_exports

router = APIRouter()


@router.post('/api/reports/rules/{sid}/{fmt}')
def export_rule_result(sid: str, fmt: str, cover: ReportCover):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
        raise HTTPException(400, 'Invalid report session')
    if fmt not in ('html', 'pdf'):
        raise HTTPException(400, 'Choose HTML or PDF')
    source = WORK / sid / 'rule_results.json'
    if not source.is_file():
        raise HTTPException(404, 'Rule results are unavailable. Run the pipeline again.')
    result = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(result, dict) or not isinstance(result.get('results'), list):
        raise HTTPException(409, 'This session does not contain a completed rule result.')
    inputs_path = WORK / sid / 'inputs.json'
    config_path = WORK / sid / 'rules.json'
    inputs = json.loads(inputs_path.read_text(encoding='utf-8')) if inputs_path.is_file() else {}
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.is_file() else {}
    result = {**result, 'reportContext': {
        'sessionId': sid, 'projectPath': inputs.get('project', ''),
        'pipelineName': config.get('pipelineName', '') if isinstance(config, dict) else '',
        'machineDepartment': config.get('machineDepartment', '') if isinstance(config, dict) else '',
        'resultRecordedAt': datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
    }}
    folder = EXPORTS / 'reports' / uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)
    from backend.core.access import claim_resource
    claim_resource(folder)
    from backend.core.identifiers import identify_result, filename_part
    identify_result(result,'rules',config.get('machineDepartment') if isinstance(config,dict) else None)
    path = folder / f'{filename_part(result["testId"])}_LogicScan_ResultView.{fmt}'
    details = cover.model_dump(mode='json')
    if fmt == 'html':
        rule_exports.export_html(result, path, details, RESOURCE_ROOT / 'src' / 'usopp_logo.png')
    else:
        rule_exports.export_pdf(result, path, details)
    if result.get('historyId'):
        from backend.core.run_history import add_run_artifact
        add_run_artifact(result['historyId'],path)
    return FileResponse(path, filename=path.name, media_type='text/html' if fmt == 'html' else 'application/pdf')
