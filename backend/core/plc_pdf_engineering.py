"""Progressive PDF comparison orchestration; no model-written verdicts."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

VERSION = 8
MAX_CACHE_ENTRY = 100 * 1024**2
MAX_CACHE_BYTES = 256 * 1024**2
ALIAS = re.compile(r'[A-Z_][\w.]*\Z', re.I)
ADDRESS = re.compile(r'%?(?:SM|S|AI|AQ|I|Q|M|V|L|T|C|HC)[BWD]?\d+(?:\.\d+)?\Z', re.I)


def symbol_references(header, lines, page):
    """Read explicit Symbol/Address columns, leaving prose and unknown forms alone."""
    from pdfplumber.utils import extract_words

    headings = {w['text'].casefold(): w['x0'] for w in extract_words(header['chars'])}
    if not {'symbol', 'address', 'comment'} <= headings.keys():
        return []
    columns = sorted((x, name) for name, x in headings.items())
    records = []
    for line in lines:
        values = {}
        for word in extract_words(line['chars'], x_tolerance=1):
            column = next((name for x, name in reversed(columns) if word['x0'] >= x - 1), None)
            if column:
                values.setdefault(column, []).append(word['text'])
        name = ' '.join(values.get('symbol', []))
        address = ' '.join(values.get('address', []))
        if ALIAS.fullmatch(name) and ADDRESS.fullmatch(address):
            records.append(dict(name=name, address=address, page=page, bbox=line['bbox']))
    return records


def normalize_operands(unit):
    mapping = {}
    for item in unit.get('symbol_references', []):
        mapping.setdefault(item['name'], set()).add(item['address'])
    parts = []
    for part in unit.get('ladder_parts', []):
        conflicts = set()

        def canonical(value):
            if ADDRESS.fullmatch(value):
                return value
            addresses = mapping.get(value, set())
            if len(addresses) > 1:
                conflicts.add(value)
            return next(iter(addresses)) if len(addresses) == 1 else value

        symbols = [dict(s, canonical_operand=canonical(s['operand']),
                        canonical_bindings={pin:canonical(value) for pin,value in s.get('bindings',{}).items()})
                   for s in part['symbols']]
        checks = part['open_checks'] + [f'Conflicting address references for {name}.' for name in sorted(conflicts)]
        parts.append(dict(part, symbols=symbols, complete=part['complete'] and not conflicts, open_checks=checks))
    return parts


def network_key(unit):
    """Use engineering elements as a pairing hint only when extraction covers the network."""
    parts = normalize_operands(unit)
    if parts and all(p['complete'] for p in parts):
        elements = tuple(sorted((s['kind'], s['canonical_operand'], tuple(sorted(s.get('canonical_bindings',{}).items())))
                                for p in parts for s in p['symbols']))
        return ('elements',elements)
    # Preserve whitespace inside strings, identifiers and printable literals.
    content = '\n'.join(unit.get('drawing_text', [])) or unit['text']
    return ('text',unit['title'],content) if content.strip() else None


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cached_extract(path, options, extractor, cache_dir=None):
    """Reuse extraction only within an explicitly supplied account-owned cache.

    One cache slot per source content/profile; hashes and engine revision are
    checked on read. Atomic writes preserve a complete previous entry on failure.
    No source directory is modified and cache failure does not block comparison.
    """
    if cache_dir is None:
        return extractor(path, options.get('ignore_page_numbers', True), options), False
    raw_hash = _digest(path)
    profile = {k: options.get(k, True) for k in ('ignore_page_numbers', 'compare_author',
        'compare_created', 'compare_modified', 'compare_comments', 'compare_references')}
    identity = dict(source=raw_hash, version=VERSION, profile=profile)
    slot = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = Path(cache_dir)/f'{slot}.json'
    try:
        if cache.stat().st_size <= MAX_CACHE_ENTRY:
            record = json.loads(cache.read_text(encoding='utf8'))
            if record.get('identity') == identity:
                cache.touch(exist_ok=True)
                return record['data'], True
    except (OSError, ValueError, KeyError):
        pass
    data = extractor(path, profile['ignore_page_numbers'], options)
    if _digest(path) == raw_hash:
        temp = cache.with_suffix('.'+uuid4().hex+'.tmp')
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(dict(identity=identity, data=data), ensure_ascii=False), encoding='utf8')
            if temp.stat().st_size <= MAX_CACHE_ENTRY:
                temp.replace(cache)
                remaining = MAX_CACHE_BYTES
                entries = sorted(((entry.stat(),entry) for entry in cache.parent.glob('*.json')),
                                 key=lambda pair:pair[0].st_mtime, reverse=True)
                for stat,entry in entries:
                    remaining -= stat.st_size
                    if remaining < 0:
                        entry.unlink(missing_ok=True)
        except OSError: pass
        finally:
            try:temp.unlink(missing_ok=True)
            except OSError:pass
    return data, False


def binding_changes(structure):
    """Pair instruction instances using unique unchanged bindings as context."""
    result = []
    for kind in sorted({s['kind'] for s in structure['base_elements'] if s.get('bindings')}):
        aa, bb = [[s for s in structure[side+'_elements'] if s['kind']==kind] for side in ('base','compared')]
        key = lambda s: (s['canonical_operand'],tuple(sorted(s['canonical_bindings'].items())))
        common = Counter(map(key, aa)) & Counter(map(key, bb))
        # Repeated identical bindings could conceal an instance swap or a
        # rewired enable, so only consume unambiguous instances.
        unique = {signature for signature,count in common.items() if count==1
                  and sum(key(s)==signature for s in aa)==sum(key(s)==signature for s in bb)==1}
        pending_a = [s for s in aa if key(s) not in unique]
        pending_b = [s for s in bb if key(s) not in unique]
        if len(pending_a)!=1 or len(pending_b)!=1:
            continue
        before,after = pending_a[0],pending_b[0]
        ap,bp = before['canonical_bindings'],after['canonical_bindings']
        if len(aa)>1 and not any(ap[pin]==bp.get(pin) for pin in ap):
            continue
        for pin in sorted(ap.keys() & bp.keys()):
            if ap[pin] != bp[pin]:
                result.append(dict(instruction=before['operand'], pin=pin, before=before['bindings'][pin],
                    after=after['bindings'][pin], base_page=before['page'], compared_page=after['page'],
                    base_bbox=before['binding_boxes'][pin], compared_bbox=after['binding_boxes'][pin]))
    return result


def describe(row):
    """Share engineering change details across the existing export formats."""
    structure = row.get('structure') or {}
    evidence = [row['assessment']['reason']]
    for change in structure.get('binding_changes', []):
        evidence.append(f"{change['instruction']}.{change['pin']} on Base page {change['base_page']} "
                        f"and Compared page {change['compared_page']}: {change['before']} -> {change['after']}.")
    for change in structure.get('alias_changes', []):
        evidence.append(f"Name: {change['before']} -> {change['after']}.")
    return '\n'.join(evidence)


def decision(structure, fallback, left, right, options):
    """Only covered incidence graphs can override source/raster uncertainty."""
    result = dict(fallback)
    result['checks'] = list(fallback['checks'])
    result['engineering_coverage'] = 'complete' if structure['supported'] else 'partial'
    result['classification'] = {'unchanged':'source_unchanged','unresolved':'needs_review'}.get(result['status'],'source_changed')
    if left['number'] is None or not options.get('pixel_compare',True):
        result['engineering_coverage']='not_evaluated'
        if (options.get('pixel_compare',True) and left['title']==right['title']=='Block information'
                and left['text']==right['text'] and result['status']!='unchanged'
                and all(s['complete'] and s['margin_rule_only'] for u in (left,right) for s in u.get('source_evidence',[]))):
            result.update(status='unchanged',classification='visual_only',
                reason='Block information text agrees. The printed table spacing or margin rule changed.')
        return result
    details = binding_changes(structure)
    structure['binding_changes'] = details
    inputs = lambda unit: '\n'.join(unit.get('drawing_text', []))
    references_changed = [r['text'] for r in left.get('references',[])] != [r['text'] for r in right.get('references',[])]
    if not structure['supported']:
        if result['status']=='unchanged' and not result['source_corroborated'] and (
                structure['review_required'] or any(s['primitives'] for u in (left,right) for s in u['source_evidence'])):
            result.update(status='unresolved',classification='needs_review',
                reason='Available elements and drawing evidence do not establish complete wiring. Review the unresolved connections or instructions.')
        if details and result['status'] in {'modified','unresolved'}:
            result.update(status='modified',classification='operand_modified',
                reason='Printed instruction operands changed. Remaining network connectivity needs review.')
        return result
    result['checks'].extend(['instance_bijection', 'named_terminal_incidence', 'full_primitive_coverage'])
    if structure['same']:
        title_changed=left['title']!=right['title']
        if structure['printed_order_changed']:
            result.update(status='modified',classification='instruction_order_changed',
                reason='The printed order of instructions or retained coils changed. Review execution order and dependencies.')
        elif structure['alias_changes']:
            result.update(status='modified',classification='alias_changed',
                reason='Printed operand names changed. Their explicit address references and covered terminal connections agree.')
        elif title_changed or (options.get('compare_references',True) and references_changed):
            result.update(status='modified',classification='source_changed',
                reason='Network title or selected symbol references changed. The covered Ladder structure agrees.')
        elif inputs(left)!=inputs(right):
            # Slide positions can alter text reading order. Check the actual
            # token coverage before clearing a source text change.
            if Counter(inputs(left).split())!=Counter(inputs(right).split()):
                result.update(status='modified',classification='source_changed',
                    reason='Extracted text changed outside the matched structure. Review the printed content.')
            else:
                result.update(status='unchanged',classification='visual_only',
                    reason='Recognized elements, operands and terminal connections agree after layout changes.')
        else:
            result.update(status='unchanged',
                classification='visual_only' if not fallback['source_corroborated'] else 'verified_structure_unchanged',
                reason='Recognized element instances, operands, instruction pins and all covered terminal connections agree.')
    else:
        details = [f"{c['operand']}: {c['before'] or 'absent'} -> {c['after'] or 'absent'}" for c in structure['changes']]
        result.update(status='modified',
            classification='operand_modified' if structure['binding_changes'] else
                           'element_modified' if details else 'topology_modified',
            reason='Covered printed network changed: '+('; '.join(details) or 'element multiplicity or terminal connectivity changed')+'.')
        functional=structure.get('functional',{})
        if functional.get('supported'):
            result['checks'].append('bounded_combinational_truth_table')
            if functional['equivalent']:
                result['classification']='equivalent_combinational_restructure'
                result['reason']+=' The bounded contact/ordinary-coil truth table agrees; the structural change remains reported.'
            else:
                result['classification']='functional_difference'
                result['reason']+=' Counterexample: '+json.dumps(functional['inputs'],sort_keys=True)+'; outputs '+json.dumps(functional['before'],sort_keys=True)+' -> '+json.dumps(functional['after'],sort_keys=True)+'.'
    return result
