"""Source snapshots and readable differences for configured logic rules."""
import difflib
import re
from pathlib import Path

LOGIC_KINDS = {'checkpoint_1', 'checkpoint_2', 'checkpoint_3', 'checkpoint_4',
               'condition_assignment', 'indexed_assignment_range', 'machine_status_packet',
               'product_code_all_groups', 'lot_name_packet_hmi', 'exact_logic_declaration',
               'cross_domain_traceability', 'group_code_exact_logic'}


def expected_logic(rule):
    values = rule.get('logicAlternatives')
    if not values:
        # Read older rules which stored alternatives in one OR-delimited text field.
        # New configurations use one array item per accepted ST block.
        legacy = str(rule.get('exactLogic', '') or '')
        values = re.split(r'(?im)^\s*OR\s*$', legacy) if legacy else []
    if isinstance(values, str): values = [values]
    return [value for value in values if isinstance(value, str) and value.strip()]


def cross_function_configuration_error(rule):
    if rule.get('crossFunctionMode','all') not in {'all','any'}:
        return 'Cross references must use AND (all) or OR (any).'
    checks = rule.get('crossFunctionChecks') or []
    if not isinstance(checks, list):
        return 'Cross-function checks must be a list.'
    for index, check in enumerate(checks):
        label = str(check.get('name') or f'Cross-function check {index + 1}') if isinstance(check, dict) else f'Cross-function check {index + 1}'
        if not isinstance(check, dict):
            return f'{label} must be an object.'
        if not expected_logic(check):
            return f'Add at least one accepted logic block to {label}.'
        files = check.get('sourceFiles') or []
        if isinstance(files, str):
            files = [item.strip() for item in re.split(r'[\r\n,;]+', files) if item.strip()]
        if not check.get('searchAllSubroutines') and not files and not (check.get('subroutine') or check.get('sourceFile')):
            return f'Choose “Search all other subroutines” or enter a source file for {label}.'
    return None


def enrich_result(root, rule, result, engine):
    result['ruleDefinition'] = dict(rule)
    result['expectedLogic'] = expected_logic(rule)
    result['failureReasons'] = [] if result['status'] == 'PASS' else [result['actual'], *result.get('recommendations', [])]
    result['logicComparisons'] = []
    if rule.get('kind')=='module_serial_mapping':
        result['logicConfiguration']='Physical configurations are checked separately: hardware module -> SerialNumber I/O binding -> declared scalar/array element -> each GC 420 packet path and payload size.'
        return result
    if rule.get('kind') in {'structured_requirements','structured_checks'}:
        result['logicConfiguration']='Every main requirement must pass. Cross references use their configured AND / OR mode; each accepted alternative must match completely in its own file.'
        return result
    if not result['expectedLogic']:
        result['logicConfiguration'] = 'Expected source logic is not configured.'
        return result
    requested = rule.get('sourceFiles') or [rule.get('subroutine') or rule.get('sourceFile') or '']
    requested = [str(x).replace('\\', '/').casefold() for x in requested if x]
    paths = []
    referenced=[]
    for name in result.get('sourceFiles',[]):
        path=(root/str(name).replace('\\','/')).resolve()
        if path.is_relative_to(root.resolve()) and path.is_file(): referenced.append(path)
    for path in referenced or engine.all_files(root):
        relative = path.relative_to(root).as_posix().casefold()
        if path.suffix.lower() not in {'.st','.ab','.src','.c','.ld','.var','.typ','.page','.pages','.txtgrp','.algrp','.tpr','.hw','.hwl','.iom','.sw','.set','.xml','.cfg','.pkg','.lby','.vcvk','.apj','.gdm','.osl','.layer'}:
            continue
        if any(relative == name if '/' in name else path.name.casefold() == name or (name in {'mms_nw_rcyclic.st','mms_nw_r.src'} and path.name.casefold() in {'mms_nw_rcyclic.st','mms_nw_r.src'}) for name in requested):
            paths.append(path)
    token_pattern = r"'(?:[^']|'')*'|[A-Za-z_]\w*|\d+(?:\.\d+)?|:=|<=|>=|<>|\S"
    def tokens(text):
        return list(re.finditer(token_pattern, engine._strip_plc_comments(text)))
    def key(value):
        return value if value.startswith("'") else value.casefold()
    def line_key(line):
        return tuple(key(m.group()) for m in tokens(line))
    candidates = []
    for path in paths:
        text = engine.read_text(path)
        clean = engine._strip_plc_comments(text) if path.suffix.casefold() in {'.st','.ab','.src','.c','.ld','.var','.typ'} else text
        offset = 0
        if rule.get('groupCode') is not None:
            branch = engine._branch_with_location(text, int(rule['groupCode']))
            if not branch:
                continue
            clean, offset = branch
        base_line = engine._line_number(engine._strip_plc_comments(text), offset)
        candidates.append((path, text, clean, base_line))
    for alternative, expected in enumerate(result['expectedLogic']):
        wanted = [key(m.group()) for m in tokens(expected)]
        best = None
        for path, original, segment, base_line in candidates:
            hit = engine._logic_match(segment, expected)
            found = bool(hit)
            if hit:
                start, end = hit
                score = 1.0
            else:
                source = tokens(segment)
                values = [key(m.group()) for m in source]
                if not values or not wanted:
                    continue
                # A bounded source preview is an approximation, never proof of a match.
                anchors = {value for value in wanted[:20] if re.match(r'[a-z_]\w+', value)}
                starts = [i for i, value in enumerate(values) if value in anchors][:80] or [0]
                score, index = max((difflib.SequenceMatcher(None, wanted, values[i:i+len(wanted)], autojunk=False).ratio(), i) for i in starts)
                start, end = source[index].start(), source[min(len(source)-1, index+len(wanted)-1)].end()
            first = base_line + segment.count('\n', 0, start)
            last = base_line + segment.count('\n', 0, end)
            if best is None or score > best[0]:
                best = (score, path, original, first, last, found)
        comparison = {'alternative': alternative+1, 'expected': expected, 'actual': '', 'file': '', 'line': 1, 'matched': False, 'approximate': False, 'differences': []}
        if best:
            _, path, original, first, last, found = best
            lines = original.splitlines()
            actual = '\n'.join(lines[first-1:last])
            comparison.update(actual=actual, file=path.relative_to(root).as_posix(), line=first, endLine=last, matched=found, approximate=not found)
        else:
            comparison['note'] = 'Configured source file or Group Code section was not found.'
        if not comparison['matched']:
            left, right = expected.splitlines(), comparison['actual'].splitlines()
            matcher = difflib.SequenceMatcher(None, [line_key(x) for x in left], [line_key(x) for x in right], autojunk=False)
            comparison['differences'] = [{'kind': kind, 'expectedLine': i+1, 'actualLine': comparison['line']+j,
                                         'expected': '\n'.join(left[i:ii]), 'actual': '\n'.join(right[j:jj])}
                                        for kind, i, ii, j, jj in matcher.get_opcodes() if kind != 'equal']
        result['logicComparisons'].append(comparison)
    result['logicConfiguration'] = 'Configured code; comparison ignores comments, whitespace and identifier case, and preserves string values.'
    result['sourceFiles'] = sorted(set(result.get('sourceFiles', [])) | {p.relative_to(root).as_posix() for p in paths} | {x['file'] for x in result['logicComparisons'] if x['file']})
    return result
