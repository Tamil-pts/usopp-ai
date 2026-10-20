"""Bounded PLC language parsers producing data-only, source-addressed IR.

There is deliberately no Python evaluation, source translation, or native code
execution here. Unsupported syntax is a blocking diagnostic, not a no-op.
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

MAX_SOURCE_BYTES = 2_000_000
MAX_TOKENS = 150_000
MAX_PARSE_DEPTH = 80
IEC_BLOCKS = {"TON", "TON_10MS", "TOF", "TP", "CTU", "CTD", "R_TRIG", "F_TRIG"}
# These B&R operators own hidden state at each lexical invocation. They must
# never enter the stateless builtin dispatcher.
STATEFUL_CALLS = {"EDGEPOS", "EDGENEG"}
BUILTINS = {"ABS", "MIN", "MAX", "LIMIT", "SEL", "MUX", "SQRT", "SIN", "COS",
            "TAN", "EXP", "LN", "LOG", "TRUNC", "ROUND", "MOD", "MOVE", "SHL", "SHR",
            "ROL", "ROR", "BIT_SET", "BIT_CLR", "BIT_TST", "BOOL", "BYTE", "WORD", "DWORD",
            "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT", "REAL", "LREAL",
            "TIME", "STRING", "LEN", "CONCAT", "TO_BOOL", "TO_INT", "TO_REAL", "TO_DINT", "TO_UINT", "TO_UDINT"}
TOKEN = re.compile(
    r"(?P<space>\s+)|(?P<comment>//[^\n]*|/\*[\s\S]*?\*/|\(\*[\s\S]*?\*\))|"
    r"(?P<string>'(?:[^']|'')*'|\"(?:[^\"\\]|\\.)*\")|"
    r"(?P<typed>(?:2|8|16)\#[0-9A-Fa-f_]+|(?:T|TIME|LTIME)\#[0-9][\w.]*(?:_[\w.]+)*|"
    r"[A-Za-z_]\w*\#(?:[A-Za-z_]\w*|[0-9][\w.]*(?:\#[0-9A-Fa-f_]+)?))|"
    r"(?P<number>0[xX][0-9A-Fa-f]+[uUlL]*|(?:\d+\.\d+(?!\.)|\d+)(?:[Ee][+-]?\d+)?[uUlLfF]*)|"
    r"(?P<id>[A-Za-z_]\w*)|(?P<op>:=|=>|<=|>=|<>|==|!=|&&|\|\||\+\+|--|\+=|-=|\*=|/=|->|\.\.|<<|>>|\*\*|[+\-*/%=<>()\[\],;:.{}!&|^~?])"
)


class CompileError(ValueError):
    def __init__(self, message: str, line: int = 1):
        super().__init__(message)
        self.line = line


@dataclass(frozen=True)
class Token:
    text: str
    line: int
    kind: str


def literal(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    value = text.strip()
    if re.fullmatch(r'0[xX][0-9A-Fa-f]+[uUlL]*', value):
        return int(re.sub(r'[uUlL]+$', '', value), 16)
    if re.fullmatch(r'(?:\d+\.\d*|\d+)(?:[Ee][+-]?\d+)?[uUlLfF]+', value):
        value = re.sub(r'[uUlLfF]+$', '', value)
    if value.upper() in {"TRUE", "FALSE"}:
        return value.upper() == "TRUE"
    if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0]:
        return iec_string(value[1:-1].replace("''", "'"))
    if re.fullmatch(r"(?i)(T|TIME|LTIME)\#.+", value):
        body = value.split("#", 1)[1].replace("_", "")
        parts = list(re.finditer(r"(?i)(\d+(?:\.\d+)?)(ms|us|ns|d|h|m|s)", body))
        if not parts or "".join(p.group(0) for p in parts) != body:
            raise ValueError("Unsupported TIME literal: " + value)
        scale = {"d": 86400000, "h": 3600000, "m": 60000, "s": 1000,
                 "ms": 1, "us": .001, "ns": .000001}
        return sum(float(p.group(1)) * scale[p.group(2).lower()] for p in parts)
    if "#" in value:
        prefix, tail = value.split("#", 1)
        if prefix in {"2", "8", "16"}:
            return int(tail.replace("_", ""), int(prefix))
        return literal(tail)
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\d+)(?:[Ee][+-]?\d+)?", value):
        return float(value)
    raise ValueError("Not an IEC literal: " + value)


def iec_string(value):
    escapes = {'L': '\n', 'N': '\n', 'R': '\r', 'T': '\t', '$': '$', "'": "'", '"': '"'}
    return re.sub(r'\$([0-9A-Fa-f]{2}|[LlNnRrTt$\'\"])',
                  lambda m: escapes.get(m[1].upper(), chr(int(m[1], 16)) if len(m[1]) == 2 else m[1]), value)


def lex(text: str, pragmas: bool = False) -> list[Token]:
    if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise CompileError("Source exceeds the 2 MB execution limit")
    tokens, pos, line = [], 0, 1
    while pos < len(text):
        if pragmas and text[pos] == "{":
            end = text.find("}", pos+1)
            if end < 0:
                raise CompileError("Incomplete B&R declaration attribute", line)
            line += text[pos:end+1].count("\n")
            pos = end+1
            continue
        match = TOKEN.match(text, pos)
        if not match:
            raise CompileError("Unsupported character or incomplete comment: " + repr(text[pos:pos+24]), line)
        kind = match.lastgroup
        if kind not in {"space", "comment"}:
            tokens.append(Token(match.group(), line, kind))
            if len(tokens) > MAX_TOKENS:
                raise CompileError("Source exceeds token limit", line)
        line += match.group().count("\n")
        pos = match.end()
    tokens.append(Token("<EOF>", line, "eof"))
    return tokens


class Parser:
    PRECEDENCE = {"OR": 1, "||": 1, "XOR": 2, "^": 2, "AND": 3, "&&": 3, "&": 3,
                  "=": 4, "==": 4, "<>": 4, "!=": 4, "<": 4, ">": 4, "<=": 4, ">=": 4,
                  "|": 2, "<<": 5, ">>": 5, "+": 6, "-": 6, "*": 7, "/": 7, "MOD": 7, "%": 7,
                  "**": 8}
    UNARY_PRECEDENCE = 8

    def __init__(self, text: str, source: str, language: str = "st"):
        self.tokens = lex(text, pragmas=language != "c")
        self.i, self.source, self.language = 0, source, language
        self.declarations: list[dict] = []
        self.depth = 0

    @property
    def token(self) -> Token:
        return self.tokens[self.i]

    @property
    def up(self) -> str:
        return self.token.text.upper()

    def pop(self) -> Token:
        token = self.token
        if token.kind != "eof":
            self.i += 1
        return token

    def accept(self, value: str) -> bool:
        if self.up == value.upper():
            self.pop()
            return True
        return False

    def require(self, value: str) -> Token:
        if self.up != value.upper():
            raise CompileError(f"Expected {value}, found {self.token.text}", self.token.line)
        return self.pop()

    def identifier(self) -> str:
        if self.token.kind != "id":
            raise CompileError("Expected identifier, found " + self.token.text, self.token.line)
        return self.pop().text

    def expression(self, minimum: int = 0, depth: int = 0) -> dict:
        if depth > MAX_PARSE_DEPTH:
            raise CompileError("Expression nesting limit exceeded", self.token.line)
        site = self.i
        token = self.pop()
        upper = token.text.upper()
        if upper in {"NOT", "!", "~", "+", "-"}:
            left = {"op": "unary", "operator": upper, "value": self.expression(self.UNARY_PRECEDENCE, depth+1)}
        elif token.text == "(":
            cast = self.c_cast_type() if self.language == 'c' else None
            if cast:
                left = {'op': 'cast', **cast, 'value': self.expression(self.UNARY_PRECEDENCE, depth+1)}
            else:
                left = self.expression(depth=depth+1)
                self.require(")")
        elif self.language == 'c' and token.text == '&':
            value = self.expression(self.UNARY_PRECEDENCE, depth+1)
            if value.get('op') != 'ref':
                raise CompileError('C address-of requires a variable', token.line)
            left = {'op': 'call', 'name': 'ADR', 'args': [{'name': None, 'output': False, 'value': value}],
                    'line': token.line, 'source': self.source, 'site': site}
        elif self.language == 'c' and upper == 'SIZEOF' and self.accept('('):
            typename = self.c_cast_type()
            if typename:
                left = {'op': 'sizeof_type', **typename}
            else:
                value = self.expression(depth=depth+1)
                self.require(')')
                left = {'op': 'call', 'name': 'SIZEOF', 'args': [{'name': None, 'output': False, 'value': value}],
                        'line': token.line, 'source': self.source, 'site': site}
        elif token.kind in {"number", "string", "typed"} or upper in {"TRUE", "FALSE"}:
            try:
                left = {"op": "literal", "value": literal(token.text)}
            except ValueError as error:
                if token.kind == "typed" and re.fullmatch(r"[A-Za-z_]\w*#[A-Za-z_]\w*", token.text):
                    left = {"op": "ref", "name": token.text, "path": []}
                else:
                    raise CompileError(str(error), token.line) from error
        elif token.kind == "id":
            left = {"op": "ref", "name": token.text, "path": []}
        else:
            raise CompileError("Expected expression, found " + token.text, token.line)
        while True:
            if self.accept("["):
                indexes = [self.expression(depth=depth+1)]
                while self.accept(","):
                    indexes.append(self.expression(depth=depth+1))
                self.require("]")
                if left["op"] != "ref":
                    raise CompileError("Index requires a variable", self.token.line)
                left["path"].extend({"index": index} for index in indexes)
            elif self.up == "." or (self.language == 'c' and self.up == '->'):
                dereference = self.pop().text == '->'
                if left["op"] != "ref":
                    raise CompileError("Member requires a variable", self.token.line)
                if dereference:
                    left['path'].append({'dereference': True})
                if self.token.kind=='number' and self.token.text.isdigit():left['path'].append({'bit':int(self.pop().text)})
                else:left["path"].append({"member": self.identifier()})
            elif self.accept("("):
                if left["op"] != "ref":
                    raise CompileError("Unsupported callable expression", self.token.line)
                args = []
                if not self.accept(")"):
                    while True:
                        name, output = None, False
                        if self.token.kind == "id" and self.tokens[self.i+1].text in {":=", "=>"}:
                            name = self.pop().text
                            output = self.pop().text == "=>"
                        args.append({"name": name, "output": output, "value": self.expression(depth=depth+1)})
                        if self.accept(")"):
                            break
                        self.require(",")
                        if self.accept(')'):break
                instance=left if left.get('path') else None
                left = {"op": "call", "name": left["name"], "args": args, "line": token.line,
                        "source": self.source, "site": site}
                if instance:left['instance']=instance
            else:
                operator = self.up
                precedence = self.PRECEDENCE.get(operator, -1)
                if precedence < minimum:
                    break
                self.pop()
                right = self.expression(precedence if operator == "**" else precedence+1, depth+1)
                left = {"op": "binary", "operator": operator, "left": left, "right": right}
        if self.language == 'c' and minimum == 0 and self.accept('?'):
            yes = self.expression(depth=depth+1)
            self.require(':')
            no = self.expression(depth=depth+1)
            left = {'op': 'conditional', 'condition': left, 'yes': yes, 'no': no}
        return left

    def declarations_block(self, scope: str) -> None:
        mode = self.pop().text.upper()
        retain, constant = False, False
        while self.up in {"RETAIN", "NON_RETAIN", "CONSTANT", "PERSISTENT"}:
            qualifier = self.pop().text.upper()
            retain = retain or qualifier in {"RETAIN", "PERSISTENT"}
            constant = constant or qualifier == "CONSTANT"
        while self.up not in {"END_VAR", "<EOF>"}:
            line = self.token.line
            names = [self.identifier()]
            while self.accept(","):
                names.append(self.identifier())
            self.require(":")
            typename = []
            while self.up not in {":=", ";", "<EOF>"}:
                typename.append(self.pop().text)
            initial = None
            if self.accept(":="):
                initial = self.expression()
            self.require(";")
            for name in names:
                self.declarations.append({"name": name, "type": " ".join(typename), "scope": scope,
                                          "initialExpression": initial, "retain": retain,
                                          "constant": constant, "mode": mode, "source": self.source, "line": line})
        self.require("END_VAR")
        self.accept(";")

    def block(self, stop: set[str], scope: str = "", depth: int = 0) -> list[dict]:
        if depth > MAX_PARSE_DEPTH:
            raise CompileError("Statement nesting limit exceeded", self.token.line)
        statements = []
        while self.up not in stop and self.up != "<EOF>":
            if self.accept(";"):
                continue
            if self.up.startswith("VAR") and self.up in {"VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_GLOBAL", "VAR_TEMP"}:
                self.declarations_block(scope)
                continue
            statements.append(self.statement(scope, depth+1))
        return statements

    def statement(self, scope: str, depth: int) -> dict:
        line = self.token.line
        node = {"line": line, "source": self.source}
        if self.language == "ab" and self.accept("GOTO"):
            label = self.identifier()
            self.require(";")
            return {**node, "op": "goto", "label": label}
        if (self.language == "ab" and self.token.kind == "id"
                and self.tokens[self.i+1].text == ":"):
            name = self.identifier()
            self.require(":")
            self.accept(";")
            return {**node, "op": "label", "name": name}
        if self.accept("IF"):
            cases = []
            condition = self.expression()
            self.require("THEN")
            cases.append({"condition": condition, "body": self.block({"ELSIF", "ELSE", "END_IF"}, scope, depth)})
            while self.accept("ELSIF"):
                condition = self.expression()
                self.require("THEN")
                cases.append({"condition": condition, "body": self.block({"ELSIF", "ELSE", "END_IF"}, scope, depth)})
            other = self.block({"END_IF"}, scope, depth) if self.accept("ELSE") else []
            self.require("END_IF")
            self.accept(";")
            return {**node, "op": "if", "cases": cases, "else": other}
        if self.accept("CASE"):
            expression = self.expression()
            self.require("OF")
            cases = []
            while self.up not in {"ELSE", "END_CASE", "<EOF>"}:
                labels = []
                while True:
                    first = self.expression()
                    last = self.expression() if self.accept("..") else None
                    labels.append({"first": first, "last": last})
                    if not self.accept(","):
                        break
                self.require(":")
                body = []
                while self.up not in {"ELSE", "END_CASE", "<EOF>"}:
                    # Label tokens have a colon before any assignment or statement boundary.
                    look = self.i
                    while self.tokens[look].text not in {":", ":=", ";", "<EOF>"}:
                        look += 1
                    if self.up not in {'CASE','IF','FOR','WHILE','REPEAT'} and self.tokens[look].text == ":":
                        break
                    if self.accept(";"):
                        continue
                    body.append(self.statement(scope, depth+1))
                if self.language == "ab" and cases and not cases[-1]["body"]:
                    # Automation Basic permits consecutive ACTION labels with
                    # one shared ENDACTION/body. ST empty arms remain distinct.
                    cases[-1]["labels"].extend(labels)
                    cases[-1]["body"] = body
                else:
                    cases.append({"labels": labels, "body": body})
            other = self.block({"END_CASE"}, scope, depth) if self.accept("ELSE") else []
            self.require("END_CASE")
            self.accept(";")
            return {**node, "op": "case", "value": expression, "cases": cases, "else": other}
        if self.accept("FOR"):
            target = {"op": "ref", "name": self.identifier(), "path": []}
            self.require(":=")
            start = self.expression()
            self.require("TO")
            end = self.expression()
            step = self.expression() if self.accept("BY") else {"op": "literal", "value": 1}
            self.require("DO")
            body = self.block({"END_FOR"}, scope, depth)
            self.require("END_FOR")
            self.accept(";")
            return {**node, "op": "for", "target": target, "start": start, "end": end, "step": step, "body": body,'basicLoop':self.language=='ab'}
        if self.accept("WHILE"):
            condition = self.expression()
            self.require("DO")
            body = self.block({"END_WHILE"}, scope, depth)
            self.require("END_WHILE")
            self.accept(";")
            return {**node, "op": "while", "condition": condition, "body": body}
        if self.accept("REPEAT"):
            body = self.block({"UNTIL"}, scope, depth)
            self.require("UNTIL")
            condition = self.expression()
            self.require("END_REPEAT")
            self.accept(";")
            return {**node, "op": "repeat", "condition": condition, "body": body}
        if self.accept("EXIT"):
            self.accept(";")
            return {**node, "op": "exit"}
        if self.accept("RETURN"):
            self.accept(";")
            return {**node, "op": "return"}
        # Parse lvalue before := using a minimum binding power above all binary ops.
        expression = self.expression(9)
        if self.language=='ab' and self.accept('ACCESS'):
            if expression.get('op')!='ref' or expression.get('path'):raise CompileError('ACCESS target must be a declared variable',line)
            value=self.expression();self.require(';')
            return {**node,'op':'access','target':expression,'value':value}
        if self.accept(":="):
            if expression["op"] != "ref":
                raise CompileError("Assignment requires a variable", line)
            value = self.expression()
            self.require(";")
            return {**node, "op": "assign", "target": expression, "value": value}
        if expression["op"] == "call":
            self.require(";")
            return {**node, "op": "call", "expression": expression}
        if expression["op"] == "ref" and self.accept(";"):
            # B&R permits a parameterless function-block invocation without
            # parentheses. Some generated sources also contain scalar reads.
            # Keep the reference explicit: semantic linking decides between
            # invoking a declared instance and evaluating a scalar reference.
            return {**node, "op": "reference_statement", "expression": expression}
        raise CompileError("Unsupported statement starting at " + str(expression.get("name", expression["op"])), line)

    def parse(self) -> list[dict]:
        sections = []
        while self.up != "<EOF>":
            if self.accept(";"):
                continue
            if self.up in {"PROGRAM", "FUNCTION", "FUNCTION_BLOCK", "ACTION"}:
                kind = self.pop().text.upper()
                line, name = self.token.line, self.identifier()
                return_type = None
                if kind == "ACTION":
                    self.require(":")
                elif self.accept(":"):
                    return_type = self.identifier()
                end = {"PROGRAM": "END_PROGRAM", "FUNCTION": "END_FUNCTION", "FUNCTION_BLOCK": "END_FUNCTION_BLOCK", "ACTION": "END_ACTION"}[kind]
                body = self.block({end}, name)
                self.require(end)
                self.accept(";")
                sections.append({"name": name, "kind": kind.lower(), "line": line,
                                 "returnType": return_type, "instructions": body})
            else:
                line = self.token.line
                sections.append({"name": "_CYCLIC", "kind": "program", "line": line,
                                 "instructions": self.block(set())})
        return sections


def automation_basic(text: str) -> str:
    """Explicit AS Basic control-flow subset; every unhandled statement is rejected."""
    # A leading semicolon is a whole-line comment in B&R Basic, not an ST
    # statement separator. Mask block comments before recognizing THEN/DO.
    text = '\n'.join(text.splitlines())
    text = re.sub(r'\(\*[\s\S]*?\*\)', lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)
    result = []
    loops = []
    for raw in text.splitlines():
        # Strip trailing // comments before adding ST statement terminators.
        # Quoted strings may themselves contain slashes.
        raw = re.sub(r'''('(?:[^']|'')*'|"(?:[^"\\]|\\.)*")|//.*|;.*''',lambda m:m[1] or '',raw)
        line = raw.strip()
        if line.startswith(';'):
            result.append('')
            continue
        if not line:
            result.append("")
            continue
        line = re.sub(r"(?i)\bELSEIF\b", "ELSIF", line)
        line = re.sub(r"(?i)^ELSE\s+IF\b", "ELSIF", line)
        line = re.sub(r"(?i)\bENDIF\b", "END_IF", line)
        line = re.sub(r"(?i)^NEXT(?:\s+\w+)?\s*;?$", "END_FOR", line)
        line = re.sub(r"(?i)^WEND\s*;?$", "END_WHILE", line)
        if re.fullmatch(r'(?i)LOOP\s*;?', line):
            loops.append('END_WHILE')
            line = 'WHILE TRUE DO'
        elif re.match(r'(?i)^LOOP\s+\w+\s*=', line):
            loops.append('END_FOR')
            line = re.sub(r'(?i)^LOOP\s+(\w+)\s*=',r'FOR \1 :=',line)
            if re.search(r'(?i)\bDOWNTO\b', line):
                line = re.sub(r'(?i)\bDOWNTO\b', 'TO', line)
                line = re.sub(r'(?i)\s+DO\s*$', ' BY -1 DO', line)
        elif re.fullmatch(r'(?i)ENDLOOP\s*;?', line):
            if not loops:
                raise CompileError('ENDLOOP without matching LOOP', len(result)+1)
            line = loops.pop()
        line = re.sub(r'(?i)^EXITIF\s+(.+?)\s*;?$',r'IF \1 THEN EXIT; END_IF;',line)
        line = re.sub(r'(?i)^EXITIF\s*\((.*)\)\s*;?$',r'IF \1 THEN EXIT; END_IF;',line)
        line = re.sub(r'(?i)^ACTION\s+(.+):\s*$', r'\1:', line)
        line = re.sub(r'(?i)^ELSEACTION\s*:\s*$', 'ELSE', line)
        if re.fullmatch(r'(?i)ENDACTION\s*;?', line):
            result.append('')
            continue
        line = re.sub(r'(?i)^ENDCASE\s*;?$', 'END_CASE', line)
        line = re.sub(r"(?i)\bENDFUNCTION\b", "END_FUNCTION", line)
        line = re.sub(r"(?i)\bENDPROGRAM\b", "END_PROGRAM", line)
        line = re.sub(r"(?i)^FOR\s+(\w+)\s*=", r"FOR \1 :=", line)
        if re.match(r'(?i)^FOR\b',line):line = re.sub(r"(?i)\bSTEP\b", "BY", line)
        if re.match(r"(?i)^FOR\b", line) and not re.search(r"(?i)\bDO\s*$", line):
            line += " DO"
        if re.match(r"(?i)^WHILE\b", line) and not re.search(r"(?i)\bDO\s*$", line):
            line += " DO"
        if not re.match(r"(?i)^(IF|ELSIF|WHILE|FOR|CASE)\b", line):
            line = re.sub(r"^(\w+(?:\[[^]]+\]|\.\w+)*)\s*=(?!=)", r"\1 :=", line)
        line = re.sub(r'(?i)^([A-Za-z_]\w*)\s+FUB\s+([A-Za-z_]\w*)\s*\(\s*\)\s*;?$', r'\1()', line)
        if not line.endswith((";", ":")) and not re.match(r"(?i)^(PROGRAM|FUNCTION|FUNCTION_BLOCK|VAR|VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR_GLOBAL|VAR_TEMP|ELSE)\b", line) and not re.search(r"(?i)\b(THEN|DO|OF)$", line):
            line += ";"
        result.append(line)
    if loops:
        raise CompileError('LOOP without matching ENDLOOP', len(result))
    return "\n".join(result)


class CParser(Parser):
    """Explicit C syntax lowered to the same bounded virtual-memory IR.

    Address/cast nodes never carry a native address. Object macros are expanded
    as bounded token substitutions; includes only identify external interfaces.
    """
    C_TYPES = {"BOOL": "BOOL", "BOOL_T": "BOOL", "CHAR": "SINT", "SHORT": "INT", "INT": "DINT",
               "LONG": "DINT", "FLOAT": "REAL", "DOUBLE": "LREAL", "UINT": "UINT", "UDINT": "UDINT",
               "DINT": "DINT", "USINT": "USINT", "REAL": "REAL", "LREAL": "LREAL", "VOID": "VOID",
               "SINT": "SINT", "WORD": "WORD", "DWORD": "DWORD", "BYTE": "BYTE", "STRING": "STRING",
               "UINT8_T": "USINT", "UINT16_T": "UINT", "UINT32_T": "UDINT", "INT8_T": "SINT", "INT16_T": "INT", "INT32_T": "DINT"}
    PRECEDENCE = {'||': 1, '&&': 2, '|': 3, '^': 4, '&': 5, '==': 6, '!=': 6,
                  '<': 7, '>': 7, '<=': 7, '>=': 7, '<<': 8, '>>': 8,
                  '+': 9, '-': 9, '*': 10, '/': 10, '%': 10}
    UNARY_PRECEDENCE = 11

    def __init__(self, text: str, source: str):
        self.type_names = {m[1].upper(): m[1] for m in re.finditer(
            r'\btypedef\s+struct\s*(?:\w+\s*)?\{[^{}]*\}\s*(\w+)\s*;', text, re.S)}
        self.type_names.update({m[1].upper(): m[1] for m in re.finditer(
            r'\b([A-Za-z_]\w*_typ)\b', text)})
        # Includes name interfaces only. Conditional preprocessor evaluation is
        # limited to defined object macros and the B&R default-include guard.
        stripped = []
        macros, conditionals = {}, []
        for line in text.splitlines():
            directive = re.sub(r'/\*.*?\*/|//.*', '', line).strip()
            if match := re.fullmatch(r'#\s*(ifdef|ifndef)\s+(\w+)', directive):
                enabled = match[2] == '_DEFAULT_INCLUDES' or match[2] in macros
                enabled = enabled if match[1] == 'ifdef' else not enabled
                conditionals.append((all(item[0] for item in conditionals), enabled, False))
                stripped.append('')
            elif re.fullmatch(r'#\s*else', directive):
                if not conditionals or conditionals[-1][2]:
                    raise CompileError('Unmatched or duplicate C #else', len(stripped)+1)
                parent, enabled, _ = conditionals[-1]
                conditionals[-1] = (parent, not enabled, True)
                stripped.append('')
            elif re.fullmatch(r'#\s*endif', directive):
                if not conditionals:
                    raise CompileError('Unmatched C #endif', len(stripped)+1)
                conditionals.pop()
                stripped.append('')
            elif conditionals and not all(parent and enabled for parent, enabled, _ in conditionals):
                stripped.append('')
            elif re.fullmatch(r'#\s*include\s+[<"][\w./-]+[>"]', directive):
                stripped.append("")
            elif match := re.fullmatch(r'#\s*define\s+(\w+)\s+(.+)', directive):
                if re.match(r'^\s*#\s*define\s+\w+\(', line):
                    raise CompileError('Function-like C macros require explicit expansion', len(stripped)+1)
                macros[match[1]] = match[2]
                stripped.append('')
            elif line.lstrip().startswith("#"):
                raise CompileError("Unsupported C preprocessor directive", len(stripped)+1)
            else:
                expanded, seen = line, set()
                for _ in range(32):
                    if expanded in seen:
                        raise CompileError('Recursive C object macro expansion', len(stripped)+1)
                    seen.add(expanded)
                    updated = re.sub(r'''('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|//.*)|\b[A-Za-z_]\w*\b''',
                                     lambda m: m[1] or macros.get(m[0], m[0]), expanded)
                    if updated == expanded:
                        break
                    expanded = updated
                else:
                    raise CompileError('C object macro expansion limit exceeded', len(stripped)+1)
                stripped.append(expanded)
        if conditionals:
            raise CompileError('Unclosed C preprocessor conditional', len(stripped))
        super().__init__("\n".join(stripped), source, "c")

    def c_type(self):
        unsigned = self.accept('UNSIGNED')
        signed = self.accept('SIGNED') if not unsigned else False
        if unsigned or signed:
            token = self.pop().text.upper() if self.up in {'CHAR', 'SHORT', 'INT', 'LONG'} else 'INT'
            if token == 'LONG':
                self.accept('INT')
            return ({'CHAR': 'USINT', 'SHORT': 'UINT', 'INT': 'UDINT', 'LONG': 'UDINT'} if unsigned else
                    {'CHAR': 'SINT', 'SHORT': 'INT', 'INT': 'DINT', 'LONG': 'DINT'})[token]
        if self.up in self.C_TYPES:
            return self.C_TYPES[self.pop().text.upper()]
        if self.up in self.type_names:
            return self.type_names[self.pop().text.upper()]
        return None

    def c_cast_type(self):
        """Read TYPE [* ...] ')' after an opening parenthesis, or rewind."""
        start = self.i
        self.accept('CONST')
        typename = self.c_type()
        pointers = 0
        while typename and self.up in {'*', '**'}:
            pointers += len(self.pop().text)
        if typename and self.accept(')'):
            if pointers > 2:
                raise CompileError('C pointer nesting exceeds the virtual-memory subset', self.token.line)
            return {'type': typename, 'pointers': pointers}
        self.i = start
        return None

    def expression(self, minimum: int = 0, depth: int = 0) -> dict:
        return super().expression(minimum, depth)

    def c_block(self, scope: str, depth: int = 0) -> list[dict]:
        if depth > MAX_PARSE_DEPTH:
            raise CompileError("C statement nesting limit exceeded", self.token.line)
        if not self.accept("{"):
            return [self.c_statement(scope, depth+1)]
        body = []
        while self.up not in {"}", "<EOF>"}:
            if self.accept(";"):
                continue
            body.append(self.c_statement(scope, depth+1))
        self.require("}")
        return body

    def c_statement(self, scope: str, depth: int = 0) -> dict:
        line = self.token.line
        node = {"line": line, "source": self.source}
        if self.accept('SWITCH'):
            self.require('(')
            value = self.expression()
            self.require(')')
            self.require('{')
            cases, default, default_seen = [], [], False
            current = None
            while self.up not in {'}', '<EOF>'}:
                if self.accept('CASE'):
                    if default_seen:
                        raise CompileError('C default labels preceding later case labels require ordered switch arms', self.token.line)
                    label = self.expression()
                    self.require(':')
                    if current is not None and not current['body']:
                        current['labels'].append(label)
                    else:
                        current = {'labels': [label], 'body': []}
                        cases.append(current)
                elif self.accept('DEFAULT'):
                    if default_seen:
                        raise CompileError('Duplicate C default label', self.token.line)
                    default_seen = True
                    self.require(':')
                    current = {'labels': [], 'body': []}
                    default = current['body']
                elif current is None:
                    raise CompileError('C switch statement precedes a case label', self.token.line)
                else:
                    current['body'].append(self.c_statement(scope, depth+1))
            self.require('}')
            return {**node, 'op': 'switch', 'value': value, 'cases': cases, 'default': default}
        if self.accept("IF"):
            self.require("(")
            condition = self.expression()
            self.require(")")
            body = self.c_block(scope, depth+1)
            other = self.c_block(scope, depth+1) if self.accept("ELSE") else []
            return {**node, "op": "if", "cases": [{"condition": condition, "body": body}], "else": other}
        if self.accept("WHILE"):
            self.require("(")
            condition = self.expression()
            self.require(")")
            return {**node, "op": "while", "condition": condition, "body": self.c_block(scope, depth+1)}
        if self.accept("FOR"):
            self.require("(")
            initialize = self.c_statement(scope, depth+1)
            condition = self.expression()
            self.require(";")
            increment = self.c_assignment(scope, terminator=False)
            self.require(")")
            return {**node, "op": "sequence", "body": [initialize, {**node, "op": "while", "condition": condition,
                    "body": self.c_block(scope, depth+1) + [increment]}]}
        if self.accept("BREAK"):
            self.require(";")
            return {**node, "op": "exit"}
        if self.accept("RETURN"):
            expression = None if self.up == ";" else self.expression()
            self.require(";")
            return {**node, "op": "return", "value": expression}
        if self.up in self.C_TYPES:
            typename = self.C_TYPES[self.pop().text.upper()]
            name = self.identifier()
            if self.up in {"*", "[", ","}:
                raise CompileError("Only scalar C local declarations are executable", line)
            initial = self.expression() if self.accept("=") else None
            self.require(";")
            self.declarations.append({"name": name, "type": typename, "scope": scope, "mode": "VAR",
                                      "source": self.source, "line": line, "initialExpression": None})
            if initial is not None:
                return {**node, "op": "assign", "target": {"op": "ref", "name": name, "path": []}, "value": initial}
            return {**node, "op": "sequence", "body": []}
        return self.c_assignment(scope)

    def c_assignment(self, scope: str, terminator: bool = True) -> dict:
        line = self.token.line
        expression = self.expression(self.UNARY_PRECEDENCE)
        node = {"line": line, "source": self.source}
        if self.up in {"=", "+=", "-=", "*=", "/=", "++", "--"}:
            operator = self.pop().text
            if expression["op"] != "ref":
                raise CompileError("C assignment requires a variable", line)
            value = {"op": "literal", "value": 1} if operator in {"++", "--"} else self.expression()
            if operator != "=":
                value = {"op": "binary", "operator": operator[0], "left": expression, "right": value}
            result = {**node, "op": "assign", "target": expression, "value": value}
        elif expression["op"] == "call":
            result = {**node, "op": "call", "expression": expression}
        else:
            raise CompileError("Unsupported C statement", line)
        if terminator:
            self.require(";")
        return result

    def parse(self) -> list[dict]:
        sections = []
        while self.up != "<EOF>":
            if self.accept('TYPEDEF'):
                # Declarations are extracted independently into the typed PLC
                # memory model. Consume the exact balanced declaration here.
                balance = 0
                while self.up != '<EOF>':
                    token = self.pop().text
                    balance += int(token == '{') - int(token == '}')
                    if token == ';' and balance == 0:
                        break
                if balance:
                    raise CompileError('Unclosed C typedef declaration', self.token.line)
                continue
            storage = None
            if self.up in {'_LOCAL', '_GLOBAL', '_GLOBAL_RETAIN'}:
                storage = self.pop().text
            self.accept("STATIC")
            self.accept('CONST')
            typename = self.c_type()
            if not typename:
                raise CompileError("Unsupported C type/declaration: " + self.token.text, self.token.line)
            if self.up in {'_LOCAL', '_GLOBAL', '_GLOBAL_RETAIN'}:
                storage = self.pop().text
            pointers = 0
            while self.accept('*'):
                pointers += 1
            # B&R uses `void _CYCLIC ProgramCyclic(void)` markers.
            marker = self.pop().text if self.up in {"_INIT", "_CYCLIC", "_EXIT"} else None
            line, name = self.token.line, self.identifier()
            if self.up != '(':
                # File-scope C objects are supplied by the declaration adapter;
                # never turn a definition into cyclic executable instructions.
                while self.up not in {';', '<EOF>'}:
                    self.pop()
                self.require(';')
                continue
            self.require("(")
            parameters = []
            if not self.accept(")"):
                if self.up == "VOID" and self.tokens[self.i+1].text == ")":
                    self.pop()
                else:
                    while True:
                        param_type = self.c_type()
                        if not param_type or param_type == "VOID":
                            raise CompileError("Unsupported C parameter type", self.token.line)
                        pointer_depth = 0
                        while self.accept('*'):
                            pointer_depth += 1
                        param = self.identifier()
                        parameters.append({"name": param, "type": param_type, "scope": name, "mode": "VAR_INPUT",
                                           "source": self.source, "line": line, 'pointers': pointer_depth})
                        if not self.accept(","):
                            break
                self.require(")")
            if self.accept(";"):
                # Prototype declarations have no executable body.
                continue
            self.declarations.extend(parameters)
            body = self.c_block(name)
            sections.append({"name": marker or name, "callName": name, "kind": "program" if marker else "function",
                             "line": line, "returnType": None if typename == "VOID" else typename, "instructions": body})
        return sections


def compile_source(text: str, language: str = "st", source: str = "<source>") -> dict:
    language = language.lower().lstrip(".")
    result = {"language": language, "source": source, "sections": [], "declarations": [], "diagnostics": []}
    try:
        if language == "h":
            result["diagnostics"].append({"severity": "warning", "code": "INTERFACE_ONLY", "source": source,
                                           "line": 1, "message": "C headers supply declarations only and are never executed."})
        elif language in {"st", "ab", "c"}:
            parser = CParser(text, source) if language == "c" else Parser(automation_basic(text) if language == "ab" else text, source, language)
            result["sections"] = parser.parse()
            result["declarations"] = parser.declarations
            for section in result['sections']:
                labels = {}
                jumps = []
                for node in walk_ir(section.get('instructions', [])):
                    if node.get('op') == 'label':
                        key = node['name'].casefold()
                        if key in labels:
                            raise CompileError('Duplicate GOTO label: ' + node['name'], node.get('line', 1))
                        labels[key] = node
                    elif node.get('op') == 'goto':
                        jumps.append(node)
                for jump in jumps:
                    if jump['label'].casefold() not in labels:
                        raise CompileError('Unresolved GOTO label: ' + jump['label'], jump.get('line', 1))
            if language == 'ab':
                aliases = {i: match[2] for i, line in enumerate(text.splitlines(), 1)
                           if (match := re.match(r'\s*([A-Za-z_]\w*)\s+FUB\s+([A-Za-z_]\w*)\s*\(\s*\)', line, re.I))}
                for node in walk_ir(result['sections']):
                    if node.get('op') == 'call' and node.get('name') and node.get('line') in aliases:
                        node['expectedType'] = aliases[node['line']]
        else:
            raise CompileError("Unsupported executable language: " + language)
    except (CompileError, RecursionError) as error:
        result["diagnostics"].append({"severity": "error", "code": "UNSUPPORTED_SYNTAX", "source": source,
                                       "line": getattr(error, "line", 1), "message": str(error)})
        result["sections"] = []
    blocked = any(item["severity"] == "error" for item in result["diagnostics"])
    result["compatibility"] = {"runAllowed": not blocked, "status": "blocked" if blocked else "supported",
                               "supported": len(result["sections"]), "blocked": int(blocked)}
    return result


def ladder_expression(text: str, source: str, target: bool = False) -> dict:
    """Parse one complete PLC binding; never accept a truncated expression."""
    parser = Parser(str(text).strip(), source)
    expression = parser.expression()
    if parser.up != "<EOF>" or (target and expression.get("op") != "ref"):
        raise CompileError("Expected one complete " + ("variable binding" if target else "expression"))
    if any(node.get("op") == "call" for node in walk_ir(expression)):
        raise CompileError("Calls inside Ladder pin/contact expressions are not supported")
    return expression


def _ladder_block(model: dict, source: str) -> dict | None:
    """Resolve a single IEC FB only from explicit B&R pin/series geometry.

    Multi-block data-flow ordering and proprietary blocks remain unavailable.
    An empty output stub is valid; an unexplained analog wire is not.
    """
    from .libraries import BLOCK_INPUTS, BLOCK_OUTPUTS, block_member
    cells = model.get("cells", [])
    members = [cell for cell in cells if cell.get("kind") == "functionblock"]
    analogs = [cell for cell in cells if cell.get("kind") == "analog"]
    if not members:
        if analogs:
            raise CompileError("Analog wires require a resolved standard IEC function block")
        return None
    groups = {cell.get("blockId") for cell in members}
    if len(groups) != 1 or None in groups:
        raise CompileError("Multiple or ungrouped function blocks require explicit data-flow scheduling")
    types = {str(cell.get("type", "")).upper() for cell in members}
    if len(types) != 1 or next(iter(types)) not in IEC_BLOCKS:
        raise CompileError("Unsupported function-block implementation: " + ", ".join(sorted(types)))
    kind = next(iter(types))
    block_columns = {cell["column"] for cell in members}
    if len(block_columns) != 1:
        raise CompileError("Block segments do not share one logical column")
    column = next(iter(block_columns))
    if any(cell.get("kind") in {"contact", "coil"} and column <= cell["column"] < column+2 for cell in cells):
        raise CompileError("Overlapping contact/block column requires explicit execution ordering")
    if any(cell.get("kind") == "coil" and cell["column"] < column+2 for cell in cells):
        raise CompileError("A coil before the block requires explicit execution ordering")
    names = {cell.get("instance") or cell.get("name") for cell in members} - {"", None}
    if len(names) != 1 or not re.fullmatch(r"[A-Za-z_]\w*", next(iter(names), "")):
        raise CompileError("Function-block instance is not one resolved declaration")
    by_id = {cell["id"]: cell for cell in cells}
    incoming, outgoing = {}, {}
    for edge in model.get("connections", []):
        if edge.get("kind") == "series":
            incoming.setdefault(edge["to"], []).append(by_id[edge["from"]])
            outgoing.setdefault(edge["from"], []).append(by_id[edge["to"]])
    seen_in, seen_out, consumed = set(), set(), set()
    inputs, outputs, bool_outputs = [], [], {}
    boolean_pins = {"IN", "CU", "CD", "R", "LD", "CLK"}
    for cell in members:
        if cell.get("position") == "header":
            if cell.get("inputs") or cell.get("outputs"):
                raise CompileError("Header pins do not have executable wire geometry")
            continue
        if len(cell.get("inputs", [])) > 1 or len(cell.get("outputs", [])) > 1:
            raise CompileError("Only one input and output per Ladder block row is resolved")
        for raw in cell.get("inputs", []):
            pin = block_member(kind, raw)
            if pin not in BLOCK_INPUTS[kind] or pin in seen_in:
                raise CompileError("Unknown or duplicate " + kind + " input: " + str(raw))
            seen_in.add(pin)
            predecessors = incoming.get(cell["id"], [])
            if len(predecessors) == 1 and predecessors[0].get("kind") == "analog" and predecessors[0].get("type", "").lower() == "input":
                value = predecessors[0]
                if value.get("or") or len(outgoing.get(value["id"], [])) != 1:
                    raise CompileError("Analog input branches are not resolved")
                consumed.add(value["id"])
                inputs.append({"pin": pin, "expression": ladder_expression(value["name"], source), "cell": cell["id"]})
            elif pin in boolean_pins and (cell["column"] == 0 or (len(predecessors) == 1 and predecessors[0].get("kind") in {"contact", "line"})):
                inputs.append({"pin": pin, "wire": cell["id"], "cell": cell["id"]})
            else:
                raise CompileError("Input " + kind + "." + pin + " has no unambiguous " + ("Boolean wire" if pin in boolean_pins else "analog expression"))
        for raw in cell.get("outputs", []):
            pin = block_member(kind, raw)
            if pin not in BLOCK_OUTPUTS[kind] or pin in seen_out:
                raise CompileError("Unknown or duplicate " + kind + " output: " + str(raw))
            seen_out.add(pin)
            destinations = outgoing.get(cell["id"], [])
            if destinations and destinations[0].get("kind") == "analog":
                target = destinations[0]
                if len(destinations) != 1 or target.get("type", "").lower() != "output" or target.get("or"):
                    raise CompileError("Analog output branches are not resolved")
                consumed.add(target["id"])
                outputs.append({"pin": pin, "target": ladder_expression(target["name"], source, target=True), "cell": cell["id"]})
            elif pin != "Q" and destinations:
                raise CompileError("Numeric output " + kind + "." + pin + " requires an analog destination")
            if pin == "Q":
                bool_outputs[cell["id"]] = pin
    if consumed != {cell["id"] for cell in analogs}:
        raise CompileError("Unresolved analog wire outside the IEC block pins")
    if seen_in != BLOCK_INPUTS[kind]:
        raise CompileError("Missing explicit " + kind + " input pins: " + ", ".join(sorted(BLOCK_INPUTS[kind]-seen_in)))
    return {"instance": next(iter(names)), "type": kind, "inputs": inputs, "outputs": outputs, "booleanOutputs": bool_outputs, "column": column,
            "line": min((cell.get("sourceLine", 1) for cell in members), default=1)}


def _ladder_conversion(model,source):
    cells=model.get('cells',[])
    meaningful=[c for c in cells if c.get('kind')!='empty']
    functions=[c for c in meaningful if c.get('kind')=='function']
    if len(functions)!=1 or len(meaningful)!=3:return None
    function=functions[0];kind=function.get('type','').upper()
    if not re.fullmatch(r'(?:BOOL|S?INT|USINT|UINT|DINT|UDINT|REAL|LREAL|TIME|BYTE|WORD|DWORD)_TO_(?:BOOL|S?INT|USINT|UINT|DINT|UDINT|REAL|LREAL|TIME|BYTE|WORD|DWORD|STRING)',kind):return None
    inputs=[c for c in meaningful if c.get('kind')=='analog' and c.get('type')=='input']
    outputs=[c for c in meaningful if c.get('kind')=='analog' and c.get('type')=='output']
    if len(inputs)!=1 or len(outputs)!=1 or any(c.get('or') for c in meaningful):return None
    if len(function.get('inputs',[]))!=1 or len(function.get('outputs',[]))!=1:return None
    edges={(e['from'],e['to']) for e in model.get('connections',[]) if e.get('kind')=='series'}
    if len(model.get('connections',[]))!=2 or edges!={(inputs[0]['id'],function['id']),(function['id'],outputs[0]['id'])}:return None
    return {'op':'assign','source':source,'line':function.get('sourceLine',1),
        'target':ladder_expression(outputs[0]['name'],source,target=True),
        'value':{'op':'call','name':kind,'line':function.get('sourceLine',1),'source':source,
                 'args':[{'name':None,'output':False,'value':ladder_expression(inputs[0]['name'],source)}]}}


def compile_ladder(networks: list[dict] | str, source: str = "<ladder>", source_text: str | None = None) -> dict:
    """Use the existing B&R geometry and preserve OR junctions in a Boolean graph.

    Contact/coil networks and one explicitly wired standard IEC block per
    network are supported. Unknown geometry blocks the whole active program.
    """
    result = {"language": "ld", "source": source, "sections": [], "declarations": [], "diagnostics": []}
    if isinstance(networks, str):
        source_text = networks
        try:
            import xml.etree.ElementTree as ET
            from python_engine.ladder_model import network_model
            # Automation Studio .ld resources contain a PROGRAM wrapper around
            # the XML document. Extract exactly its networks element.
            start = re.search(r"<(?:\w+:)?networks\b", networks, re.I)
            end = re.search(r"</(?:\w+:)?networks\s*>", networks, re.I)
            empty=re.search(r'<(?:\w+:)?networks\s*/>',networks,re.I)
            xml = networks[start.start():end.end()] if start and end else empty[0] if empty else networks
            root = ET.fromstring(xml)
            networks = [network_model(node, i+1) for i, node in enumerate(root.iter())
                        if node.tag.rsplit("}", 1)[-1].lower() == "network"]
        except (ValueError, ImportError, ET.ParseError) as error:
            result["diagnostics"].append({"severity": "error", "code": "LADDER_PARSE", "source": source,
                                           "line": 1, "message": str(error)})
            networks = []
    network_locations = list(re.finditer(r"<(?:\w+:)?network\b[^>]*>[\s\S]*?</(?:\w+:)?network\s*>", source_text or "", re.I))
    instructions = []
    for number, network in enumerate(networks, 1):
        model = deepcopy(network.get("diagram", network))
        if re.search(r'<(?:\w+:)?networks\s*/>',source_text or '',re.I):continue
        location = network_locations[number-1] if number <= len(network_locations) else None
        source_line = (source_text or "").count("\n", 0, location.start())+1 if location else number
        if location:
            row_matches = list(re.finditer(r"<(?:\w+:)?row\b[^>]*>[\s\S]*?</(?:\w+:)?row\s*>", location.group(), re.I))
            cell_lines = {}
            for row_number, row_match in enumerate(row_matches):
                children = re.finditer(r"<(?:\w+:)?(?:empty|line|contact|coil|analog|functionblock|function)\b", row_match.group(), re.I)
                for column, child in enumerate(children):
                    offset = location.start()+row_match.start()+child.start()
                    cell_lines[(row_number, column)] = (source_text or "").count("\n", 0, offset)+1
            for cell in model.get("cells", []):
                cell["sourceLine"] = cell_lines.get((cell["row"], cell.get("xmlColumn", cell["column"])), source_line)
        if model.get("commented"):
            continue
        cells = model.get("cells", [])
        warnings = model.get("warnings", [])
        unsupported = {cell.get("kind", "unknown") for cell in cells
                       if cell.get("kind") not in {"empty", "line", "contact", "coil", "analog", "function", "functionblock"}}
        if unsupported:
            warnings = [*warnings, "Unsupported elements: " + ", ".join(sorted(unsupported))]
        if warnings:
            result["diagnostics"].append({"severity": "error", "code": "LADDER_UNSUPPORTED_NETWORK", "source": source,
                "line": source_line, "network": number, "message": f"Network {number}: " + ", ".join(warnings)})
            continue
        if not any(cell.get("kind") not in {"empty", "line"} for cell in cells):
            # Keep labeled empty networks as valid jump destinations.
            if model.get("label"):
                instructions.append({"op": "sequence", "source": source, "line": source_line, "networkNumber": number,
                                     "network": model, "body": []})
            continue
        needs_plan = any(cell.get("kind") in {"function", "functionblock", "analog"}
                         or (cell.get("kind") == "coil" and cell.get("type", "").upper() in {"JUMP", "RETURN"}) for cell in cells)
        if needs_plan:
            try:
                from .ladder_dataflow import compile_plan
                plan = compile_plan(model, source, ladder_expression)
                instructions.append({"op": "ladder", "source": source, "line": source_line, "networkNumber": number,
                                     "network": model, "plan": plan, "block": None})
            except (ValueError, KeyError, TypeError) as error:
                result["diagnostics"].append({"severity": "error", "code": "LADDER_BLOCK_WIRING", "source": source,
                    "line": source_line, "network": number, "message": f"Network {number}: {error}"})
            continue
        block = None
        coils = [cell for cell in cells if cell.get("kind") == "coil"]
        for cell in cells:
            if cell.get("kind") in {"coil", "contact"}:
                if cell['kind'] == 'coil' and cell.get('type', '').upper() == 'RETURN' and not cell.get('name'):
                    cell['expression'] = {'op': 'literal', 'value': False}
                    continue
                try:
                    expression = ladder_expression(cell.get("name", ""), source, target=cell["kind"] == "coil")
                    if expression.get("op") not in {"ref", "literal"} or (expression.get("op") == "literal" and not isinstance(expression.get("value"), bool)):
                        raise CompileError("A Ladder contact needs a BOOL variable or BOOL literal")
                    cell["expression"] = expression
                except ValueError as error:
                    result["diagnostics"].append({"severity": "error", "code": "LADDER_EXPRESSION", "source": source,
                        "line": cell.get("sourceLine", source_line), "network": number, "message": f"Network {number}: {cell.get('name')!r}: {error}"})
                allowed = {"", "NORMAL", "OPEN", "CLOSED", "NEGATED", "SET", "RESET", "NC", "NO"}
                if cell["kind"] == "contact":
                    allowed = {"", "NORMAL", "OPEN", "CLOSED", "NEGATED", "NC", "NO", "TRANSITION", "POSITIVE TRANSITION", "NEGATIVE TRANSITION"}
                if cell.get("type", "").upper() not in allowed:
                    result["diagnostics"].append({"severity": "error", "code": "LADDER_ELEMENT_TYPE", "source": source,
                        "line": cell.get("sourceLine", source_line), "network": number, "message": f"Network {number}: unsupported {cell['kind']} type {cell.get('type')}"})
        if not coils and block is None:
            result["diagnostics"].append({"severity": "error", "code": "LADDER_NO_COIL", "source": source,
                                           "line": source_line, "network": number, "message": f"Network {number} has no executable coil."})
        instructions.append({"op": "ladder", "source": source, "line": source_line, "networkNumber": number, "network": model, "block": block})
    if not result["diagnostics"]:
        jumps = [operation for instruction in instructions for operation in instruction.get("plan", {}).get("operations", {}).values()
                 if operation.get("kind") == "coil" and operation.get("type") == "JUMP"]
        if jumps:
            labels = {}
            for index, instruction in enumerate(instructions):
                label = instruction.get("network", {}).get("label", "")
                if not label: continue
                if label.casefold() in labels:
                    result["diagnostics"].append({"severity": "error", "code": "LADDER_LABEL", "source": source,
                        "line": instruction["line"], "message": "Duplicate Ladder label: " + label})
                labels[label.casefold()] = index
            for jump in jumps:
                if jump["label"].casefold() not in labels:
                    result["diagnostics"].append({"severity": "error", "code": "LADDER_LABEL", "source": source,
                        "line": jump["line"], "message": "Unresolved Ladder jump label: " + jump["label"]})
            instructions = [{"op": "ladder_program", "source": source, "line": 1, "body": instructions, "labels": labels}]
        if not result["diagnostics"]:
            result["sections"] = [{"name": "_CYCLIC", "kind": "program", "line": 1, "instructions": instructions}]
    result["compatibility"] = {"runAllowed": not result["diagnostics"], "status": "blocked" if result["diagnostics"] else "supported",
                               "supported": len(instructions), "blocked": len(result["diagnostics"])}
    return result


def walk_ir(value: Any):
    if isinstance(value, dict):
        if "op" in value:
            yield value
        for key, child in value.items():
            if key not in {"network"}:
                yield from walk_ir(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_ir(child)
