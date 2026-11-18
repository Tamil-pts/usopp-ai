"""Progressive PDF comparison orchestration; no model-written verdicts."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from uuid import uuid4

VERSION = 8


def cached_extract(path, options, extractor, cache_dir=None):
    """Reuse extraction only within an explicitly supplied account-owned cache.

    One cache slot per source content/profile; hashes and engine revision are
    checked on read. Atomic writes preserve a complete previous entry on failure.
    No source directory is modified and cache failure does not block comparison.
    """
    raw_hash = hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest() if False else None
    with Path(path).open('rb') as stream: raw_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    profile = {k: options.get(k, True) for k in ('ignore_page_numbers', 'compare_author',
        'compare_created', 'compare_modified', 'compare_comments', 'compare_references')}
    identity = dict(source=raw_hash, version=VERSION, profile=profile)
    cache = Path(cache_dir)/f'{raw_hash}.json' if cache_dir else None
    if cache and cache.is_file() and cache.stat().st_size <= 200*1024**2:
        try:
            record = json.loads(cache.read_text(encoding='utf8'))
            if record.get('identity') == identity:
                return record['data'], True
        except (OSError, ValueError, KeyError): pass
    data = extractor(path, profile['ignore_page_numbers'], options)
    if cache:
        temp = cache.with_suffix('.'+uuid4().hex+'.tmp')
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(dict(identity=identity, data=data), ensure_ascii=False), encoding='utf8')
            if temp.stat().st_size <= 200*1024**2: temp.replace(cache)
        except OSError: pass
        finally: temp.unlink(missing_ok=True)
    return data, False


def decision(structure, fallback, left, right):
    """Only covered incidence graphs can override source/raster uncertainty."""
    result = dict(fallback)
    result['checks'] = list(fallback['checks'])
    result['engineering_coverage'] = 'complete' if structure['supported'] else 'partial'
    result['classification'] = 'source_unchanged' if result['status']=='unchanged' else 'needs_review' if result['status']=='unresolved' else 'source_changed'
    if not structure['supported']: return result
    result['checks'].extend(['instance_bijection', 'named_terminal_incidence', 'full_primitive_coverage'])
    if structure['same']:
        result.update(status='unchanged', classification='verified_structure_unchanged',
            reason='Recognized element instances, operands, instruction pins and all terminal connections agree. Layout changes do not alter this covered printed structure.')
    else:
        details = [f"{c['operand']}: {c['before'] or 'absent'} -> {c['after'] or 'absent'}" for c in structure['changes']]
        # Binding changes are reported only where the instruction type occurs once
        # on each side. Repeated instructions retain their source-specific evidence.
        aa=[s for p in left.get('ladder_parts',[]) for s in p['symbols'] if s['kind'].startswith('FB:')]
        bb=[s for p in right.get('ladder_parts',[]) for s in p['symbols'] if s['kind'].startswith('FB:')]
        counts=[Counter(s['kind'] for s in side) for side in (aa,bb)]
        for a in aa:
            if counts[0][a['kind']] != 1 or counts[1][a['kind']] != 1: continue
            b=next(s for s in bb if s['kind']==a['kind'])
            for pin in sorted(a.get('bindings',{}).keys() | b.get('bindings',{}).keys()):
                av,bv=a.get('bindings',{}).get(pin),b.get('bindings',{}).get(pin)
                if av!=bv:details.append(f"{a['operand']}.{pin}: {av} -> {bv}")
        result.update(status='modified',classification='element_or_topology_modified',
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
