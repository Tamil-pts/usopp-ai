"""Bounded instance matching and combinational checks for covered PDF networks.

Instance IDs locate source objects; they are never inferred PLC instance names.
This module does not execute instructions, timers, retained coils or scan cycles.
"""
from collections import Counter, defaultdict
from itertools import product

REVISION = 1
MAX_SEARCH = 4096


def graph(part):
    elements = {s.get('instance_id', s['operand']): s for s in part['symbols']}
    labels = {key: (s['kind'], s.get('canonical_operand', s['operand']),
                    tuple(sorted(s.get('bindings', {}).items()))) for key, s in elements.items()}
    nets = [tuple(sorted(map(tuple, net))) for net in part['nets']]
    power = set(part.get('power_nets', []))
    return labels, nets, power


def match(a, b):
    """Exact labelled incidence isomorphism with a hard search bound.

    Identically labelled contacts remain separate vertices. Colour refinement
    prunes candidates; equality requires a complete terminal/net bijection.
    """
    la, na, pa = graph(a); lb, nb, pb = graph(b)
    if Counter(la.values()) != Counter(lb.values()) or len(na) != len(nb):
        return dict(same=False, exhausted=False, mapping={}, attempts=0)
    def refine(labels, nets, power):
        # Common nested signatures, with deterministic integer compression below.
        incidence = defaultdict(list)
        for i, net in enumerate(nets):
            for element, port in net: incidence[element].append((port, i))
        return incidence
    ia, ib = refine(la, na, pa), refine(lb, nb, pb)
    ca, cb = la.copy(), lb.copy()
    for _ in range(min(len(la)+1, 20)):
        def signatures(labels, colors, incidence, nets, power):
            return {e: (labels[e], tuple(sorted((port, i in power,
                tuple(sorted((p, colors[n]) for n, p in nets[i])))
                for port, i in incidence[e]))) for e in labels}
        sa, sb = signatures(la, ca, ia, na, pa), signatures(lb, cb, ib, nb, pb)
        values = {value: i for i, value in enumerate(sorted(set(sa.values()) | set(sb.values()), key=repr))}
        xa, xb = {e: values[s] for e, s in sa.items()}, {e: values[s] for e, s in sb.items()}
        if Counter(xa.values()) != Counter(xb.values()):
            return dict(same=False, exhausted=False, mapping={}, attempts=0)
        if xa == ca and xb == cb: break
        ca, cb = xa, xb
    candidates = {e: [f for f in lb if cb[f] == ca[e]] for e in la}
    order = sorted(la, key=lambda e: (len(candidates[e]), -len(ia[e]), e))
    target = Counter((i in pb, net) for i, net in enumerate(nb))
    mapping = {}; used = set(); attempts = 0; exhausted = False
    def search(index):
        nonlocal attempts, exhausted
        attempts += 1
        if attempts > MAX_SEARCH:
            exhausted = True; return False
        if index == len(order):
            return Counter((i in pa, tuple(sorted((mapping[e], p) for e, p in net)))
                           for i, net in enumerate(na)) == target
        e = order[index]
        for f in candidates[e]:
            if f in used: continue
            mapping[e] = f; used.add(f)
            # Every fully mapped net must already exist on the other side.
            complete = Counter((i in pa, tuple(sorted((mapping[n], p) for n, p in net)))
                               for i, net in enumerate(na) if all(n in mapping for n, _ in net))
            if not (complete-target) and search(index+1): return True
            used.remove(f); del mapping[e]
            if exhausted: return False
        return False
    same = search(0)
    return dict(same=same, exhausted=exhausted, mapping=dict(mapping) if same else {}, attempts=attempts)


def functional(a, b):
    """Exhaustive truth table for ordinary NO/NC contacts and unique coils only."""
    def prepare(part):
        if not part.get('complete') or len(part['symbols']) > 100: return None
        symbols = part['symbols']
        if any(s['kind'] not in {'NO', 'NC', 'coil'} for s in symbols): return None
        coils = [s for s in symbols if s['kind'] == 'coil']
        names = [s.get('canonical_operand', s['operand']) for s in coils]
        inputs = {s.get('canonical_operand', s['operand']) for s in symbols if s['kind'] != 'coil'}
        # Self-feedback needs scan/state semantics, not a Boolean truth table.
        if not coils or len(set(names)) != len(names) or inputs & set(names): return None
        ports = {tuple(port): i for i, net in enumerate(part['nets']) for port in net}
        if not part.get('power_nets'): return None
        return symbols, inputs, ports
    aa, bb = prepare(a), prepare(b)
    if aa is None or bb is None: return dict(supported=False, reason='Requires a fully covered, stateless contact/ordinary-coil network.')
    inputs = sorted(aa[1] | bb[1])
    if len(inputs) > 10: return dict(supported=False, reason='Truth-table input bound exceeded (10 inputs).')
    def evaluate(part, prepared, values):
        symbols, _, ports = prepared; parents = list(range(len(part['nets'])))
        def root(i):
            while parents[i] != i: i = parents[i]
            return i
        for s in symbols:
            key = s.get('instance_id', s['operand']); name = s.get('canonical_operand', s['operand'])
            if s['kind'] in {'NO', 'NC'} and values[name] == (s['kind'] == 'NO'):
                parents[root(ports[(key, 'in')])] = root(ports[(key, 'out')])
        supply = {root(i) for i in part['power_nets']}
        return {s.get('canonical_operand', s['operand']): root(ports[(s.get('instance_id', s['operand']), 'in')]) in supply
                for s in symbols if s['kind'] == 'coil'}
    for combination in product((False, True), repeat=len(inputs)):
        values = dict(zip(inputs, combination)); av, bv = evaluate(a, aa, values), evaluate(b, bb, values)
        if av != bv:
            return dict(supported=True, equivalent=False, inputs=values, before=av, after=bv,
                        scope='Ordinary combinational contact/coil truth table only')
    return dict(supported=True, equivalent=True, combinations=2**len(inputs),
                scope='Ordinary combinational contact/coil truth table only')
