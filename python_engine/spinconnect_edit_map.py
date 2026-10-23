"""Portable DataInspect layouts derived from the two project services."""
import re


def read_variants(body):
    from python_engine.spinconnect_write import layout_tree, SEND, RECV
    # These source constructs serialize a Boolean as an explicit zero/one byte.
    pattern = (r'IF\s*\(\s*([A-Za-z_]\w*(?:\.\w+)*)\s*=\s*0\s*\)\s*THEN\s*;?\s*'
               r'nw_snd_buffer\[nw_i\]\s*:=\s*0\s*;\s*ELSE\s*'
               r'nw_snd_buffer\[nw_i\]\s*:=\s*1\s*;\s*END_IF\s*;?')
    from python_engine.project_analysis import _mask
    clean = _mask(body, strings=True)
    clean = re.sub(pattern, lambda m: 'memcpy(ADR(nw_snd_buffer[nw_i]),ADR('+m[1]+'),1);', clean, flags=re.I)
    adapted = re.sub(SEND.pattern, lambda m: 'memcpy(ADR('+m[1]+'),ADR(nw_rcv_buffer[nw_i]),'+m[2]+');', clean, flags=re.I)
    tree = layout_tree(adapted)

    def walk(nodes, states):
        for node in nodes:
            if node['kind'] == 'copy':
                match = RECV.fullmatch(node['text'])
                for state in states:
                    state['fields'].append({'offset':state['payloadBytes'], 'size':int(match[2]), 'variable':match[1].strip()})
            elif node['kind'] == 'increment':
                size = int(re.search(r'\+\s*(\d+)', node['text'])[1])
                for state in states: state['payloadBytes'] += size
            else:
                import copy
                yes, no = copy.deepcopy(states), copy.deepcopy(states)
                for state in yes: state['conditions'].append(node['condition'])
                for state in no: state['conditions'].append('NOT ('+node['condition']+')')
                states = walk(node['yes'], yes) + walk(node['no'], no)
            if len(states) > 128: raise ValueError('Too many read layout variants.')
        return states

    result = []
    for state in walk(tree, [{'payloadBytes':0,'conditions':[],'fields':[]}]):
        if not state['payloadBytes']: continue
        fields = state['fields']
        for index, field in enumerate(fields):
            field['span'] = (fields[index+1]['offset'] if index+1<len(fields) else state['payloadBytes'])-field['offset']
        state['when'] = ' AND '.join('('+x+')' for x in state.pop('conditions'))
        result.append(state)
    return result


def build_edit_map(study, groups, reviewed):
    reviewed = {f['id']:f for f in reviewed}
    result = {'schema':1,'groups':[]}
    for group in groups:
        code = group['code']
        wb = next(b for b in study.wread.branches if b.code==code)
        reads = read_variants(study.wt[wb.body_start:wb.end])
        rb = next((b for case in study.rcases for b in case.branches if b.code==code), None)
        sources = read_variants(study.rt[rb.body_start:rb.end]) if rb else []
        variants = []
        for index, layout in enumerate(group['wireLayouts']):
            slots, issues = [], []
            for field in group['fields']:
                paths = [p for p in field['paths'] if not p['when'] or p['when'] in layout['when']]
                if not paths: continue
                if len(paths)!=1:
                    issues.append('Ambiguous write position: '+field['id']); continue
                # Destination identity takes priority over a coincident read offset.
                names = [x.casefold() for x in field['destinations']]
                fallback = [x.strip().casefold() for x in field['readVariable'].split(' / ')]
                candidates = [(r, f) for r in reads for f in r['fields'] if f['variable'].casefold() in names and f['span']>=field['size']]
                if not candidates:
                    candidates = [(r, f) for r in reads for f in r['fields'] if f['variable'].casefold() in fallback and f['span']>=field['size']]
                unique = {(r['payloadBytes'], f['offset'], f['variable']) for r,f in candidates}
                at_position = {row for row in unique if row[1]==paths[0]['offset']-7}
                if len(at_position)==1: unique=at_position
                elif len({(row[0],row[2]) for row in unique})==1:
                    unique={min(unique)}  # The same variable is serialized more than once.
                if len(unique)!=1:
                    issues.append('No unique write-port read field: '+field['id']); continue
                read_size, read_offset, variable = next(iter(unique))
                source_slots = {(r['payloadBytes'], f['offset'], f['size']) for r in sources for f in r['fields'] if f['variable'].casefold()==variable.casefold()}
                review = reviewed.get(field['id'], {})
                slots.append({'id':field['id'],'writeOffset':paths[0]['offset']-7,'readOffset':read_offset,
                              'readPayloadBytes':read_size,'size':field['size'],'type':field['type'],
                              'variable':variable,'writable':field['writable'],
                              'sourceSlots':[{'payloadBytes':s,'offset':o,'size':w} for s,o,w in sorted(source_slots)],
                              'min':review.get('appliedMin'),'max':review.get('appliedMax')})
            if len({f['readPayloadBytes'] for f in slots})!=1: issues.append('Read layout selection is ambiguous.')
            variants.append({'id':str(index),'when':layout['when'],'payloadBytes':layout['payloadBytes'],
                             'readPayloadBytes':slots[0]['readPayloadBytes'] if slots else 0,'fields':slots,'issues':issues})
        result['groups'].append({'code':code,'variants':variants})
    return result
