"""Read-only routine selection and source-backed flows for Chopper chat."""
from pathlib import Path
import json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.core.assist_progress import report
from backend.core.runtime import _local_path, _local_session, locate_root
from python_engine.function_flow import SUPPORTED_EXTENSIONS, build_function_flow, flow_html
from python_engine.project_analysis import normalize_question

router = APIRouter(tags=['Chopper function flow'])
MAX_SOURCE_BYTES = 5 * 1024 * 1024
LANGUAGES = {'.st': 'Structured Text', '.ab': 'Automation Basic', '.ld': 'Ladder', '.src': 'AS 2.7 source'}
FLOW_WORDS = {'a', 'an', 'and', 'all', 'as', 'at', 'by', 'can', 'create', 'draw', 'explain',
              'file', 'flow', 'flowchart', 'for', 'from', 'function', 'generate', 'give', 'in',
              'ladder', 'logic', 'me', 'my', 'of', 'one', 'operating', 'please', 'plc', 'project',
              'routine', 'selected', 'sequence', 'show', 'source', 'step', 'steps', 'subroutine',
              'that', 'the', 'this', 'to', 'view', 'want', 'with', 'working', 'wise'}


def is_flow_question(question):
    text = normalize_question(question)
    if re.search(r'\b(?:function\s+flow|logic\s+flow|flow\s*chart|step[\s-]*wise|step[\s-]*by[\s-]*step)\b', text, re.I):
        return True
    if re.search(r'\b(?:in words|in sentences|written explanation|working explanation|describe how|explain how)\b', text, re.I) and \
            re.search(r'\b(?:routine|subroutine|ladder)\b|[\w.-]+\.(?:st|ab|ld|src)\b', text, re.I):
        return True
    return bool(re.search(r'\bflow\b', text, re.I) and
                re.search(r'\b(?:routine|subroutine|ladder|logic)\b|[\w.-]+\.(?:st|ab|ld|src)\b', text, re.I))


def _request(context):
    comparison_id = str(context.get('comparisonSessionId') or '')
    project_path = str(context.get('projectPath') or '')
    if comparison_id and (context.get('comparisonFocus') or not project_path):
        return {'comparisonSessionId': comparison_id}
    return {'projectPath': project_path} if project_path else {}


def _sources(request):
    """Catalogued paths are the only files that can be opened by this feature."""
    comparison_id = str(request.get('comparisonSessionId') or '')
    if comparison_id:
        from backend.api.comparison import _comparison_result_for_export
        result, work = _comparison_result_for_export(comparison_id)
        projects = result.get('projects') or {}
        base = result.get('baseName') or (projects.get('base') or {}).get('project_name') or 'Base'
        developed = result.get('newName') or (projects.get('developed') or {}).get('project_name') or 'Developed'
        candidates = {}
        for group in ('diffs', 'same_logic_files', 'same_project_files'):
            for entry in result.get(group, []):
                path = str(entry.get('path') or '')
                if entry.get('category') == 'logic' and Path(path).suffix.casefold() in SUPPORTED_EXTENSIONS:
                    candidates[path] = entry
        return {'kind': 'comparison', 'projectLabel': f'{base} / {developed}', 'baseLabel': base,
                'newLabel': developed, 'candidates': candidates, 'result': result, 'work': work}
    project_path = str(request.get('projectPath') or '')
    if not project_path:
        raise HTTPException(400, 'Select a project in ByteMap or attach a complete project folder / ZIP in Chopper first.')
    allowed = _local_path(project_path, True, True)
    root = locate_root(allowed)
    from backend.core.access import require_resource
    require_resource(root)
    from python_engine.project_knowledge import source_files
    identity, files, _ = source_files(root)
    candidates = {path.relative_to(root).as_posix(): path for path in files
                  if path.suffix.casefold() in SUPPORTED_EXTENSIONS and not path.is_symlink()
                  and path.resolve().is_relative_to(root.resolve())}
    name = identity.get('project_name') or root.name
    return {'kind': 'project', 'projectLabel': name, 'baseLabel': 'Base', 'newLabel': name,
            'root': root, 'identity': identity, 'candidates': candidates,
            'explanationFiles': {path.relative_to(root).as_posix(): path for path in files
                                 if not path.is_symlink() and path.resolve().is_relative_to(root.resolve())}}


def _rows(sources, query='', offset=0, limit=150):
    tokens = str(query).casefold().split()
    paths = sorted(sources['candidates'], key=str.casefold)
    matched = [path for path in paths if all(token in path.casefold() for token in tokens)]
    rows = [{'path': path, 'name': Path(path).name, 'language': LANGUAGES[Path(path).suffix.casefold()]}
            for path in matched[offset:offset + limit]]
    return {'projectLabel': sources['projectLabel'], 'baseLabel': sources['baseLabel'],
            'newLabel': sources['newLabel'], 'sourceKind': sources['kind'], 'candidates': rows,
            'total': len(paths), 'matched': len(matched), 'offset': offset, 'limit': limit, 'query': query}


@router.post('/api/assist/flow/catalog')
def flow_catalog(payload: dict):
    sources = _sources(payload)
    try:
        offset = max(0, int(payload.get('offset', 0)))
        limit = max(1, min(250, int(payload.get('limit', 150))))
    except (TypeError, ValueError):
        raise HTTPException(400, 'Choose valid routine list page numbers.')
    return _rows(sources, str(payload.get('query') or '')[:200], offset, limit)


def _read_flow(path, relative):
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise HTTPException(413, 'Function flow supports source files up to 5 MB.')
    raw = path.read_bytes()
    if len(raw) > MAX_SOURCE_BYTES:
        raise HTTPException(413, 'Function flow supports source files up to 5 MB.')
    legacy = path.suffix.casefold() in {'.src', '.ld'} and raw.startswith(b'B&R') and b'\x00' in raw
    if legacy:
        from python_engine.compare import decode_project_text
        text = decode_project_text(path, raw)
    elif raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = raw.decode('utf-16')
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('cp1252')
    if '\x00' in text:
        raise HTTPException(422, 'This routine contains unsupported binary records. Select a readable source export.')
    flow = build_function_flow(text, relative)
    flow['lineBasis'] = 'Decoded source view' if legacy else 'Source file snapshot'
    return flow


def _open_flow(sources, relative):
    entry = sources['candidates'].get(relative)
    if entry is None:
        raise HTTPException(404, 'Select a routine from this project’s source list.')
    report('Decoding routine and building numbered working steps')
    if sources['kind'] == 'comparison':
        from backend.api.comparison import _function_flow_detail
        view = _function_flow_detail(sources['result'], sources['work'], relative)
    else:
        root = sources['root'].resolve()
        if entry.is_symlink() or not entry.resolve().is_relative_to(root):
            raise HTTPException(403, 'Linked sources outside this project cannot be opened.')
        view = {'base': None, 'developed': _read_flow(entry, relative)}
        report('Explaining function calls from project declarations and local B&R help')
        from backend.core import br_help
        from python_engine.flow_explanations import FlowExplainer
        files = sources['explanationFiles']
        def implementation_flow(name):
            try:
                return _read_flow(files[name], name)
            except HTTPException as error:
                raise ValueError(str(error.detail)) from error
        explainer = FlowExplainer(files, implementation_flow, br_help.DATABASE, br_help.KNOWLEDGE)
        view['developed'] = explainer.enrich(view['developed'])
    if sources['kind'] == 'comparison':
        # Only saved comparison evidence is available here. Do not reopen the
        # original projects or invent a target binding for missing declarations.
        from backend.core import br_help
        from python_engine.flow_explanations import FlowExplainer
        for value in view.values():
            if value:
                value = FlowExplainer({}, lambda name: None, br_help.DATABASE, br_help.KNOWLEDGE).enrich(value)
                value['notices'].append('This comparison flow uses saved evidence. Open the complete project to resolve local instance types and expand its called routines.')
    # Exports read this snapshot, so later edits to a project do not change an
    # earlier answer. The ordinary workspace owner checks apply to downloads.
    sid, work = _local_session()
    snapshot = {'view': view, 'baseLabel': sources['baseLabel'], 'newLabel': sources['newLabel']}
    (work / 'chopper_function_flow.json').write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
    return {**snapshot, 'snapshotId': sid, 'selectedPath': relative}


@router.post('/api/assist/flow/open')
def flow_open(payload: dict):
    return _open_flow(_sources(payload), str(payload.get('routinePath') or ''))


@router.get('/api/assist/flow/export/{sid}')
def flow_export(sid: str, side: str = 'developed'):
    if side not in {'base', 'developed'}:
        raise HTTPException(400, 'Choose Base or Developed for the flow export.')
    from backend.core.access import require_session
    path = require_session(sid) / 'chopper_function_flow.json'
    if not path.is_file():
        raise HTTPException(404, 'This function flow was cleared. Open the routine again in Chopper.')
    flow = json.loads(path.read_text(encoding='utf-8'))['view'].get(side)
    if not flow:
        raise HTTPException(404, 'This routine is absent from the selected side.')
    filename = re.sub(r'[^A-Za-z0-9_.-]', '_', Path(flow['sourceFile']).stem) + '_Function_Flow.html'
    return PlainTextResponse(flow_html(flow, show_source=False), media_type='text/html', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def _question_query(question, paths):
    text = normalize_question(question).replace('\\', '/')
    folded = text.casefold()
    exact = [path for path in paths if path.casefold() in folded]
    if len(exact) == 1:
        return Path(exact[0]).name, exact[0]
    named_files = re.findall(r'\b[\w.-]+\.(?:st|ab|ld|src)\b', text, re.I)
    if named_files:
        matching = [path for path in paths if Path(path).name.casefold() == named_files[0].casefold()]
        return named_files[0], matching[0] if len(matching) == 1 else None
    # Match actual routine identifiers in this question, rather than guessing a
    # routine from a machine-purpose label or silently choosing a target.
    tokens = [token for token in re.findall(r'\b[\w-]+\b', text) if token.casefold() not in FLOW_WORDS]
    tokens = [token for token in tokens if any(token.casefold() in path.casefold().split('/') for path in paths) or
              any(re.sub(r'(?:cyclic|init|exit)$', '', Path(path).stem, flags=re.I).casefold() == token.casefold() for path in paths)]
    return ' '.join(tokens[:3]), None


def flow_reply(question, context):
    request = _request(context)
    if not request:
        return {'answer': 'Select a project in ByteMap or attach its complete folder / ZIP, then choose Routine function flow.',
                'source': 'local-function-flow', 'choices': [{'label': 'Attach project ZIP', 'action': 'attach'}, {'label': 'Open ByteMap', 'action': 'open:validation'}]}
    report('Finding PLC routines for the function flow')
    sources = _sources(request)
    query, selected = _question_query(question, sources['candidates'])
    browser = {**_rows(sources, query), 'request': request}
    if selected:
        browser.update(_open_flow(sources, selected))
        flow = browser['view'].get('developed') or browser['view']['base']
        headings = [lane['title'] + ': ' + ' → '.join(step['title'] for step in lane['steps'])
                    for section in flow['sections'] for lane in section['sequences']]
        answer = f'Working sequence for {flow["sourceFile"]}:\n' + '\n'.join(headings)
    else:
        answer = 'Choose a PLC routine below to see its numbered working steps, conditions, results and explained function calls.'
    return {'answer': answer, 'source': 'local-function-flow', 'functionFlow': browser, 'model': None}
