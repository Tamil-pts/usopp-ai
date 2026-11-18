"""Printed instruction contracts, not runtime implementations or vendor guesses."""
import re

REGISTRY = {
    **{name: ('EN', 'ENO', 'IN1', 'IN2', 'OUT') for name in
       ('ADD_I', 'ADD_DI', 'ADD_R', 'SUB_I', 'SUB_DI', 'SUB_R',
        'MUL_I', 'MUL_DI', 'MUL_R', 'DIV_I', 'DIV_DI', 'DIV_R')},
    **{name: ('EN', 'ENO', 'IN', 'OUT') for name in ('MOV_B', 'MOV_W', 'MOV_DW')},
}
LITERAL = re.compile(r"(?:[A-Za-z_%][\w%.]*(?:\[\d+\])*|[+-]?\d+(?:\.\d+)?|(?:16|2)#[0-9A-Fa-f]+|'[^']*')\Z")


def recognize(rectangles, segments, words, used, used_words, symbols, unknown):
    """Associate each pin and operand with its own enclosing instruction box.

    EN/ENO require wires. Data pins require literal/source operands. Unsupported
    or ambiguous boxes stay opaque and block complete coverage.
    """
    for box, border in rectangles:
        if border & used:
            continue
        x0, y0, x1, y1 = box
        inside = [(i, w) for i, w in enumerate(words)
                  if x0-.2 <= w['box'][0] and w['box'][2] <= x1+.2 and
                  y0-.2 <= w['box'][1] and w['box'][3] <= y1+.2]
        titles = [(i, w) for i, w in inside if w['text'] in REGISTRY]
        if len(titles) != 1:
            labels = ' '.join(w['text'] for _, w in inside)
            unknown.append('Opaque instruction box: '+(labels[:100] or 'unlabelled')+'.')
            if inside:
                symbols.append(dict(kind='opaque',operand=inside[0][1]['text'],box=list(box),ports=[],port_names=[]))
            continue
        title_id, title = titles[0]; contract = REGISTRY[title['text']]
        pins = {}; bindings = {}; consumed = {title_id}; ports = []; names = []
        binding_boxes = {}
        valid = True
        for pin in contract:
            matches = [(i, w) for i, w in inside if w['text'] == pin]
            if len(matches) != 1: valid = False; break
            i, word = matches[0]; consumed.add(i)
            right = pin in {'OUT', 'ENO'}; edge = x1 if right else x0
            if (x1-word['box'][2] if right else word['box'][0]-x0) > max(12, (x1-x0)*.25):
                valid = False; break
            cy = (word['box'][1]+word['box'][3])/2
            stubs = [(j, s) for j, s in enumerate(segments) if j not in used and j not in border and
                     abs(s[0][1]-s[1][1]) < .01 and abs(s[0][1]-cy) <= 4 and
                     any(abs(p[0]-edge) <= .55 and (s[1-k][0]-edge)*(1 if right else -1) > .55
                         for k, p in enumerate(s))]
            if len(stubs) > 1: valid = False; break
            py = stubs[0][1][0][1] if stubs else cy
            operands = [(j, w) for j, w in enumerate(words) if j not in used_words and j not in consumed and
                        LITERAL.fullmatch(w['text']) and abs((w['box'][1]+w['box'][3])/2-py) <= 4 and
                        (0 <= w['box'][0]-x1 <= 65 if right else 0 <= x0-w['box'][2] <= 65)]
            if pin in {'EN', 'ENO'}:
                if not stubs or operands: valid = False; break
                _,stub=stubs[0]
                # Retain the observed wire endpoint. Small gaps on the printed
                # box edge or between conductors remain explicit open checks.
                point=min(stub,key=lambda p:abs(p[0]-edge))
                if abs(point[0]-edge)>.05:
                    unknown.append('A printed enable connection stops short of its instruction box.')
                ports.append(point); names.append(pin)
            else:
                if len(operands) != 1: valid = False; break
                j, value = operands[0]; consumed.add(j); bindings[pin] = value['text']
                binding_boxes[pin] = value['box']
                # These short pin stubs end at printed operands, not hidden nets.
                if stubs:
                    stub_id, stub = stubs[0]
                    if abs(stub[1][0]-stub[0][0]) > 18: valid = False; break
                    pins[pin] = stub_id
        if not valid or any(i not in consumed for i, _ in inside):
            unknown.append('Incomplete or ambiguous pins/operands for '+title['text']+'.')
            continue
        used.update(border); used.update(pins.values()); used_words.update(consumed)
        symbols.append(dict(kind='FB:'+title['text'], operand=title['text'], box=list(box),
                            ports=ports, port_names=names, bindings=bindings, binding_boxes=binding_boxes,
                            contract='Printed pin contract; execution semantics not evaluated'))
