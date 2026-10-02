"""Parse common Sieve filters without depending on their generating client.

Only understood filters become editable objects. Other script text is retained
byte-for-byte in the document until a filter is explicitly changed.
"""

import re
from dataclasses import dataclass, field


_Q = r'"((?:[^"\\]|\\.)*)"'
_NAME = re.compile(r'# rule:\[([^\]\r\n]*)\]\r?\n', re.I)
_START = re.compile(r'(?m)^(?:# rule:\[[^\]\r\n]*\]\r?\n)?if\s+')


def _unquote(value):
    return re.sub(r'\\([\\"])', r'\1', value)


def _quote(value):
    if any(ord(char) < 32 for char in value):
        raise ValueError("Texten innehåller en radbrytning eller ett kontrolltecken")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


@dataclass
class Condition:
    kind: str
    field: str = ""
    operator: str = "contains"
    value: str = ""
    negate: bool = False


@dataclass
class Action:
    kind: str
    target: str = ""
    copy: bool = False


@dataclass
class Filter:
    name: str
    join: str = "allof"
    conditions: list[Condition] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    enabled: bool = True
    original: str = ""
    dirty: bool = False


@dataclass
class Document:
    parts: list[str | Filter]
    opaque: bool = False

    @property
    def filters(self):
        return [part for part in self.parts if isinstance(part, Filter)]

    def render(self):
        text = "".join(render_filter(part) if isinstance(part, Filter) and part.dirty
                       else part.original if isinstance(part, Filter) else part for part in self.parts)
        required = set(re.findall(r'"([A-Za-z0-9-]+)"', "\n".join(re.findall(r'(?im)^\s*require\s+[^;]+;', text))))
        needed = set()
        for item in self.filters:
            if not item.dirty:
                continue
            if any(condition.kind == 'body' for condition in item.conditions):
                needed.add('body')
            if any(condition.kind == 'envelope' for condition in item.conditions):
                needed.add('envelope')
            for action in item.actions:
                needed.update({"fileinto"} if action.kind == "fileinto" else set())
                needed.update({"copy"} if action.copy else set())
                needed.update({"reject"} if action.kind == "reject" else set())
                needed.update({"ereject"} if action.kind == "ereject" else set())
                needed.update({"imap4flags"} if action.kind in ("addflag", "setflag", "removeflag") else set())
                needed.update({"vacation"} if action.kind == "vacation" else set())
        missing = needed - required
        if missing:
            declaration = 'require [' + ', '.join(_quote(name) for name in sorted(missing)) + '];\r\n'
            text = declaration + text
        return text


def _scan_block(text, start):
    """Find a top-level brace pair while ignoring quoted text and comments."""
    quote = escaped = comment = False
    depth = 0
    opened = None
    for pos in range(start, len(text)):
        char = text[pos]
        if comment:
            if char == '\n':
                comment = False
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quote = False
            continue
        if char == '#':
            comment = True
        elif char == '"':
            quote = True
        elif char == '{':
            depth += 1
            if opened is None:
                opened = pos
        elif char == '}':
            depth -= 1
            if opened is not None and depth == 0:
                return opened, pos + 1
    return None


def _split_top_level(text, separator):
    pieces = []
    start = depth = 0
    quote = escaped = False
    for pos, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quote = False
        elif char == '"':
            quote = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == separator and depth == 0:
            pieces.append(text[start:pos].strip())
            start = pos + 1
    pieces.append(text[start:].strip())
    return pieces


_HEADER = re.compile(r'^(header|address|envelope)\s+:(contains|is|matches)\s+' + _Q + r'\s+' + _Q + r'$', re.I | re.S)
_EXISTS = re.compile(r'^exists\s+' + _Q + r'$', re.I | re.S)
_SIZE = re.compile(r'^size\s+:(over|under)\s+([0-9]+[KMG]?)$', re.I)
_BODY = re.compile(r'^body\s+:(contains|is|matches)\s+' + _Q + r'$', re.I | re.S)
_ACTION_TARGET = re.compile(r'^(fileinto|redirect)\s+(:copy\s+)?' + _Q + r'$', re.I | re.S)
_ACTION_PLAIN = re.compile(r'^(reject|ereject|addflag|setflag|removeflag)\s+' + _Q + r'$', re.I | re.S)


def parse_condition(text):
    text = text.strip()
    negate = bool(re.match(r'^not\s+', text, re.I))
    if negate:
        text = re.sub(r'^not\s+', '', text, count=1, flags=re.I)
    match = _HEADER.fullmatch(text)
    if match:
        kind, op, header, value = match.groups()
        return Condition(kind.lower(), _unquote(header), op.lower(), _unquote(value), negate)
    match = _EXISTS.fullmatch(text)
    if match:
        return Condition('exists', _unquote(match.group(1)), 'exists', '', negate)
    match = _SIZE.fullmatch(text)
    if match:
        return Condition('size', '', match.group(1).lower(), match.group(2), negate)
    match = _BODY.fullmatch(text)
    if match:
        return Condition('body', '', match.group(1).lower(), _unquote(match.group(2)), negate)
    if text.lower() == 'true':
        return Condition('true', '', 'is', '', negate)
    return None


def parse_action(text):
    text = text.strip()
    if text.lower() in ('keep', 'discard', 'stop'):
        return Action(text.lower())
    match = re.fullmatch(r'vacation\s+' + _Q, text, re.I | re.S)
    if match:
        return Action('vacation', _unquote(match.group(1)))
    match = _ACTION_TARGET.fullmatch(text)
    if match:
        kind, copy, target = match.groups()
        return Action(kind.lower(), _unquote(target), bool(copy))
    match = _ACTION_PLAIN.fullmatch(text)
    if match:
        kind, target = match.groups()
        return Action(kind.lower(), _unquote(target))
    return None


def parse_filter(text):
    original = text
    match = _NAME.match(text)
    name = match.group(1) if match else ""
    if match:
        text = text[match.end():]
    block = _scan_block(text, 0)
    if not block or text[block[1]:].strip():
        return None
    opened, closed = block
    header = text[:opened].strip()
    if not header.lower().startswith('if '):
        return None
    header = header[3:].strip()
    enabled = True
    disabled = re.fullmatch(r'false\s*#\s*(.*)', header, re.I | re.S)
    if disabled:
        enabled = False
        header = disabled.group(1).strip()
    join = 'allof'
    group = re.fullmatch(r'(allof|anyof)\s*\((.*)\)', header, re.I | re.S)
    if group:
        join = group.group(1).lower()
        tests = _split_top_level(group.group(2), ',')
    else:
        tests = [header]
    conditions = [parse_condition(test) for test in tests]
    if not conditions or any(item is None for item in conditions):
        return None
    body = text[opened + 1:closed - 1]
    statements = _split_top_level(body, ';')
    if statements and not statements[-1]:
        statements.pop()
    actions = [parse_action(statement) for statement in statements]
    if not actions or any(item is None for item in actions):
        return None
    return Filter(name, join, conditions, actions, enabled, original)


def parse_document(script):
    # A text: literal can contain lines starting with "if" or braces.
    # Keep such scripts intact until the scanner understands text literals.
    if re.search(r'(?im)\btext:\s*\r?\n', script):
        return Document([script], opaque=True)
    parts = []
    position = 0
    cursor = 0
    while True:
        match = _START.search(script, cursor)
        if not match:
            parts.append(script[position:])
            break
        block = _scan_block(script, match.start())
        if not block:
            parts.append(script[position:])
            break
        _, end = block
        # Keep an entire else/elsif chain opaque, including nested conditions.
        if re.match(r'\s*(?:else|elsif)\b', script[end:], re.I):
            cursor = end
            while re.match(r'\s*(?:else|elsif)\b', script[cursor:], re.I):
                branch = _scan_block(script, cursor)
                if not branch:
                    cursor = len(script)
                    break
                cursor = branch[1]
            continue
        parts.append(script[position:match.start()])
        original = script[match.start():end]
        parts.append(parse_filter(original) or original)
        position = end
        cursor = end
    return Document(parts)


def render_filter(item):
    if any(char in '\r\n]' for char in item.name):
        raise ValueError('Ogiltigt regelnamn')
    if item.join not in ('allof', 'anyof'):
        raise ValueError('Ogiltig villkorskombination')
    if not item.conditions or not item.actions:
        raise ValueError('En regel behöver minst ett villkor och en åtgärd')
    tests = []
    for cond in item.conditions:
        prefix = 'not ' if cond.negate else ''
        if cond.kind in ('header', 'address', 'envelope') and cond.operator in ('contains', 'is', 'matches'):
            if not cond.field:
                raise ValueError('Ange ett fält för villkoret')
            tests.append(prefix + f'{cond.kind} :{cond.operator} {_quote(cond.field)} {_quote(cond.value)}')
        elif cond.kind == 'exists':
            if not cond.field:
                raise ValueError('Ange en rubrik för villkoret')
            tests.append(prefix + f'exists {_quote(cond.field)}')
        elif cond.kind == 'size' and cond.operator in ('over', 'under') and re.fullmatch(r'[0-9]+[KMG]?', cond.value):
            tests.append(prefix + f'size :{cond.operator} {cond.value}')
        elif cond.kind == 'body' and cond.operator in ('contains', 'is', 'matches'):
            tests.append(prefix + f'body :{cond.operator} {_quote(cond.value)}')
        elif cond.kind == 'true':
            tests.append(prefix + 'true')
        else:
            raise ValueError('Villkoret stöds inte')
    test = f'{item.join} (' + ', '.join(tests) + ')' if len(tests) > 1 or item.join == 'anyof' else tests[0]
    header = 'if ' + (('false # ' + test) if not item.enabled else test)
    lines = []
    if item.name:
        lines.append(f'# rule:[{item.name}]')
    lines.extend([header, '{'])
    for action in item.actions:
        if action.kind in ('keep', 'discard', 'stop'):
            lines.append(f'    {action.kind};')
        elif action.kind in ('fileinto', 'redirect', 'reject', 'ereject', 'addflag', 'setflag', 'removeflag'):
            if action.copy and action.kind not in ('fileinto', 'redirect'):
                raise ValueError('Kopia stöds bara för mapp och vidarebefordran')
            if action.kind in ('fileinto', 'redirect') and not action.target:
                raise ValueError('Åtgärden behöver en mapp eller adress')
            lines.append(f'    {action.kind} ' + (':copy ' if action.copy else '') + _quote(action.target) + ';')
        elif action.kind == 'vacation':
            lines.append(f'    vacation {_quote(action.target)};')
        else:
            raise ValueError('Åtgärden stöds inte')
    lines.append('}')
    return '\r\n'.join(lines)
