"""Derive write-service packet layouts from the outgoing mms_nw_r groups.

The existing writer supplies setting policies, not the external field order.
An internal adapter feeds those policies their original frame without changing
the PLC project or making a monitoring value writable.
"""
import copy
import re
import textwrap

from python_engine.project_analysis import _mask


def identity(value):
    return re.sub(r'\s+', '', value).casefold()


def catalog(study):
    from python_engine.spinconnect_edit_map import read_variants
    from python_engine.spinconnect_write import array_capacity, SEND

    legacy = {g['code']: g for g in study.groups}
    branches = {}
    for case in study.rcases:
        if case.function == 1:
            for branch in case.branches:
                branches.setdefault(branch.code, []).append(branch)
    result = []
    for code, matches in branches.items():
        branch = matches[0]
        original = legacy.get(code)
        group = copy.deepcopy(original) if original else {
            'code': code, 'fields': [], 'issues': [], 'warnings': [],
            'machineConditions': [], 'readDifferences': [], 'writeLine': None,
        }
        group.update(description=branch.description, layoutBasis='mms_nw_r',
                     readSourceLine=study.rt.count('\n', 0, branch.start) + 1,
                     readLine=study.rt.count('\n', 0, branch.start) + 1,
                     legacyPayloadVariants=list(group.get('payloadVariants', [])))
        if len(matches) != 1:
            group['issues'].append('The read routine repeats this group code; select an unambiguous read handler.')
        body = study.rt[branch.body_start:branch.end]
        clean = _mask(body, strings=True)
        issues = group['issues']
        if not original:
            issues.append('No setting-write policy exists for this read group. Its monitoring fields are read-only until a write mapping and interlocks are defined.')
        try:
            if re.search(r'\b(?:FOR|WHILE|REPEAT|CASE)\b', clean, re.I):
                raise ValueError('Loop or nested CASE packet fields require a reviewed read layout.')
            assignments = [m[1].strip() for m in re.finditer(r'\bnw_i\s*:=\s*([^;]+);', clean, re.I)]
            if assignments and (assignments[0] != '5' or any(not re.fullmatch(r'nw_i\s*\+\s*\d+', v, re.I) for v in assignments[1:])):
                raise ValueError('The read cursor must start at byte 5 and advance by explicit field widths.')
            reads = read_variants(body)
        except ValueError as error:
            reads = []
            issues.append(str(error))
        sizes = sorted({r['payloadBytes'] for r in reads})
        group['payloadVariants'] = sizes
        group['readPayloadVariants'] = sizes
        group['sourceReadVariants'] = reads
        group['wireLayouts'] = []
        group['adapters'] = []
        fields = {}
        for ri, read in enumerate(reads):
            for fi, slot in enumerate(read['fields']):
                if slot['span'] <= 0 or slot['size'] > slot['span']:
                    issues.append(f"Read field {slot['variable']} at payload byte {slot['offset']}: copies {slot['size']} bytes but advances {slot['span']}. Correct the mms_nw_r byte layout before generating.")
                key = (identity(slot['variable']), slot['offset'], slot['span'])
                if key not in fields:
                    reference=next((m.start() for m in SEND.finditer(clean) if identity(m[1])==identity(slot['variable']) and int(m[2])==slot['size']),0)
                    fields[key] = {
                        'id': f'{code}:read:{len(fields)+1}', 'index': len(fields)+1,
                        'size': slot['span'], 'copiedBytes': slot['size'], 'type': 'Context bytes',
                        'readVariable': slot['variable'], 'destinations': [],
                        'sourceAssignments': [], 'writable': False, 'temporary': '',
                        'description': slot['variable'], 'line': study.rt.count('\n',0,branch.body_start+reference)+1,
                        'writeOffsets': [slot['offset']+7], 'errorPositions': [],
                        'paths': [], 'hmiOptions': [], 'hmiId': '', 'min': None, 'max': None,
                        'sourceChecks': [], 'legacyIds': [],
                    }
                fields[key]['paths'].append({'offset': slot['offset']+7, 'errorPosition': 0, 'when': read['when']})
            if not original:
                continue
            for wi, layout in enumerate(original['wireLayouts']):
                copies, failures = [], []
                for old in original['fields']:
                    paths = [p for p in old['paths'] if not p['when'] or p['when'] in layout['when']]
                    if not paths:
                        continue
                    if len(paths) != 1:
                        failures.append(f"{old['id']}: ambiguous original write position.")
                        continue
                    names = {identity(v) for v in old['destinations']}
                    fallback = {identity(v) for v in old['readVariable'].split(' / ')}
                    slots = [s for s in read['fields'] if identity(s['variable']) in names and s['size'] == old['size'] and s['span'] >= old['size']]
                    if not slots:
                        slots = [s for s in read['fields'] if identity(s['variable']) in fallback and s['size'] == old['size'] and s['span'] >= old['size']]
                    if not slots:
                        if old['writable']:
                            failures.append(f"{old['id']} ({old['readVariable']}): no matching {old['size']}-byte mms_nw_r field for its setting assignment.")
                        # Old context-only fields have no assignment. The adapter
                        # initializes their unused slots to zero.
                        continue
                    names_found = {identity(s['variable']) for s in slots}
                    if len(names_found) != 1:
                        failures.append(f"{old['id']}: more than one read variable matches its setting policy.")
                        continue
                    slot = min(slots, key=lambda s: s['offset'])
                    copies.append({'sourceOffset': slot['offset']+7, 'targetOffset': paths[0]['offset'], 'size': old['size'], 'legacyId': old['id']})
                    field = fields[(identity(slot['variable']), slot['offset'], slot['span'])]
                    if old['writable']:
                        for name in ('type', 'temporary', 'description', 'hmiOptions', 'hmiId', 'min', 'max'):
                            field[name] = copy.deepcopy(old[name])
                        field['writable'] = True
                        field['destinations'] = sorted(set(field['destinations'] + old['destinations']))
                        field['sourceAssignments'] = sorted(set(field['sourceAssignments'] + old['sourceAssignments']))
                        field['sourceChecks'] = list(dict.fromkeys(field['sourceChecks'] + old['sourceChecks']))
                        field['legacyIds'] = sorted(set(field['legacyIds'] + [old['id']]))
                        field['errorPositions'] = sorted(set(field['errorPositions'] + old['errorPositions']))
                # A read variant that cannot feed this writer path is not used.
                group['adapters'].append({'readVariant': ri, 'writerVariant': wi,
                    'payloadBytes': read['payloadBytes'], 'legacyPayloadBytes': layout['payloadBytes'],
                    'when': ' AND '.join('('+x+')' for x in (read['when'], layout['when']) if x),
                    'copies': copies, 'issues': failures})
        if original:
            usable = [a for a in group['adapters'] if not a['issues']]
            for wi in range(len(original['wireLayouts'])):
                if not any(a['writerVariant'] == wi for a in usable):
                    failures = [e for a in group['adapters'] if a['writerVariant'] == wi for e in a['issues']]
                    issues.extend(failures or ['No read layout can supply this original write variant.'])
            # Each outgoing layout must have a usable corresponding write path.
            for ri in range(len(reads)):
                if not any(a['readVariant'] == ri for a in usable):
                    issues.append(f'Read variant {ri+1} has no complete setting-policy mapping.')
            for i, adapter in enumerate(usable):
                group['wireLayouts'].append({'payloadBytes': adapter['payloadBytes'], 'requestBytes': adapter['payloadBytes']+9,
                    'fieldCount': len(reads[adapter['readVariant']]['fields']), 'when': adapter['when']})
        group['fields'] = list(fields.values())
        if original:
            for name, addition in [('nw_rcv_buffer', 9), ('nw_snd_buffer', 7)]:
                capacity = array_capacity(study.vars.get(name, {}))
                if capacity is None or max(sizes or [0])+addition > capacity:
                    issues.append(f'The mms_nw_r packet exceeds the declared {name} capacity or its bounds are unresolved.')
            group['warnings'].append('Group and field bytes come from mms_nw_r. Existing mms_nw_w setting assignments and checks run through an internal frame adapter; context-only read fields remain read-only.')
        group['issues'] = list(dict.fromkeys(issues))
        result.append(group)
    return result


def write_adapter(group, original_body, capacity):
    """Translate the reviewed read-layout request before existing policy code."""
    lines = ['(* Incoming settings use the mms_nw_r field layout. *)',
        'scw_request_length := nw_rcv_buffer_length;',
        'memcpy(ADR(scw_request_buffer), ADR(nw_rcv_buffer), SIZEOF(nw_rcv_buffer));',
        'nw_snd_buffer[2] := 13;', 'nw_snd_buffer[3] := 0;', 'nw_snd_buffer[4] := 0;',
        'nw_snd_buffer_length := 5;', 'nw_snd_response := TRUE;']
    lines += ['IF NOT HMI_EN_Write THEN', '    nw_snd_buffer[2] := 18;']
    if group['machineConditions']:
        lines += ['ELSIF NOT ('+group['machineConditions'][0]+') THEN', '    nw_snd_buffer[2] := 18;']
    lines.append('ELSE')
    adapters = [a for a in group['adapters'] if not a['issues']]
    for i, adapter in enumerate(adapters):
        condition = f"(scw_request_length = {adapter['payloadBytes']+9})"
        if adapter['when']:
            condition += ' AND ('+adapter['when']+')'
        lines.append(('IF ' if i == 0 else 'ELSIF ')+condition+' THEN')
        body = [f'nxt_adr := memset(ADR(nw_rcv_buffer[7]), 0, {capacity-7});']
        for item in adapter['copies']:
            body.append(f"memcpy(ADR(nw_rcv_buffer[{item['targetOffset']}]), ADR(scw_request_buffer[{item['sourceOffset']}]), {item['size']});")
        body += [f"nw_rcv_buffer_length := {adapter['legacyPayloadBytes']+9};",
                 f"nw_rcv_buffer[3] := {((adapter['legacyPayloadBytes']+2) >> 8)};",
                 f"nw_rcv_buffer[4] := {(adapter['legacyPayloadBytes']+2) % 256};", original_body]
        lines.append(textwrap.indent('\n'.join(body), '    '))
    if adapters:
        lines.append('END_IF;')
    lines.append('END_IF;')
    lines += ['memcpy(ADR(nw_rcv_buffer), ADR(scw_request_buffer), SIZEOF(nw_rcv_buffer));',
              'nw_rcv_buffer_length := scw_request_length;']
    return '\n'.join(lines)


def edit_map(groups, reviewed):
    """External settings read and write frames now share the outgoing layout."""
    reviewed = {f['id']: f for f in reviewed}
    result = {'schema': 1, 'layoutBasis': 'mms_nw_r', 'groups': []}
    for group in groups:
        variants = []
        for index, adapter in enumerate(a for a in group['adapters'] if not a['issues']):
            read = group['sourceReadVariants'][adapter['readVariant']]
            slots = []
            for slot in read['fields']:
                field = next(f for f in group['fields'] if identity(f['readVariable']) == identity(slot['variable']) and slot['offset']+7 in f['writeOffsets'] and slot['span'] == f['size'])
                policy = next((reviewed[id] for id in field['legacyIds'] if id in reviewed), {})
                slots.append({'id': field['id'], 'writeOffset': slot['offset'], 'readOffset': slot['offset'],
                    'readPayloadBytes': read['payloadBytes'], 'size': slot['span'], 'type': field['type'],
                    'variable': slot['variable'], 'writable': field['writable'],
                    'sourceSlots': [{'payloadBytes': read['payloadBytes'], 'offset': slot['offset'], 'size': slot['span']}],
                    'min': policy.get('appliedMin'), 'max': policy.get('appliedMax')})
            variants.append({'id': str(index), 'when': adapter['when'], 'payloadBytes': read['payloadBytes'],
                'readPayloadBytes': read['payloadBytes'], 'fields': slots, 'issues': []})
        result['groups'].append({'code': group['code'], 'variants': variants})
    return result
