"""Java member-level facts: typed references, call sites, outbound HTTP.

`java.py` reads what a file *declares*. This reads what its method bodies *do*,
which is what a "how does this behave" question needs: `OrderResource#place`
calls `OrderService#placeOrder`, which calls `OrderRepository#save`.

Everything is read from declared types, never guessed from names. A call
`service.placeOrder(...)` becomes an edge only because `service` was declared
as an `OrderService` in this same file (field, constructor/method parameter or
local). Receivers whose type this file does not state (lambda parameters,
chained results) produce no edge rather than a wrong one.

Rows are emitted as `uses[]` with extra keys (`kind`, `from_symbol`,
`speculative`) so the resolve phase, which owns the symbol table this file
lacks, decides whether the target exists. `speculative` marks a type name
assumed to live in the file's own package; if no such symbol exists the row is
dropped rather than counted as an unresolved reference.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .base import ExtractContext, FileFacts, anchor_at, first_string_literal, mk_edge, mk_use

MODS = r"(?:(?:public|protected|private|static|final|abstract|synchronized|transient|volatile|default|native)\s+)*"
FIELD_RE = re.compile(r"^" + MODS + r"([A-Za-z_$][\w$.]*(?:<[^()=;]*>)?(?:\[\])*)\s+([a-zA-Z_$][\w$]*)\s*(?:=|;)")
METHOD_HEAD_RE = re.compile(
    r"^" + MODS + r"(?:<[^>]*>\s+)?(?:([A-Za-z_$][\w$.]*(?:<[^()]*>)?(?:\[\])*)\s+)?([a-zA-Z_$][\w$]*)\s*\("
)
TYPE_HEAD_RE = re.compile(
    r"^\s*(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed|strictfp)\s+)*"
    r"(class|interface|enum|record)\s+([A-Za-z_$][\w$]*)"
)
LOCAL_RE = re.compile(
    r"(?<![\w$.])([A-Z][\w$.]*(?:<[^;=()]*>)?(?:\[\])*)\s+([a-z_$][\w$]*)\s*(?==|;|:|\))"
)
VAR_NEW_RE = re.compile(r"(?<![\w$.])var\s+([a-z_$][\w$]*)\s*=\s*new\s+([A-Z][\w$.]*)")
RECEIVER_CALL_RE = re.compile(r"(?<![\w$.])(this\.)?([A-Za-z_$][\w$]*)\.([a-zA-Z_$][\w$]*)\s*\(")
BARE_CALL_RE = re.compile(r"(?<![\w$.])([a-zA-Z_$][\w$]*)\s*\(")
IMPLEMENTS_RE = re.compile(r"\bimplements\s+([^{]+)")
EXTENDS_RE = re.compile(r"\bextends\s+([A-Za-z_$][\w$.]*(?:<[^{]*?>)?)(?=\s+implements\b|\s*\{|\s*$)")
IDENT_RE = re.compile(r"[A-Z][\w$]*")
VALUE_FIELD_RE = re.compile(r"@Value\s*\(\s*\"\$\{([^}:]+)(?::[^}]*)?\}\"\s*\)")

NOT_METHODS = frozenset(["if", "for", "while", "switch", "catch", "return", "new", "super", "this",
                         "synchronized", "throw", "else", "try", "assert"])
HTTP_CLIENT_TYPES = frozenset(["RestTemplate", "TestRestTemplate", "WebClient", "RestClient"])
REST_TEMPLATE_VERBS = {
    "getForObject": "GET", "getForEntity": "GET", "postForObject": "POST", "postForEntity": "POST",
    "postForLocation": "POST", "put": "PUT", "delete": "DELETE", "patchForObject": "PATCH",
    "headForHeaders": "HEAD",
}
CLIENT_VERB_CALLS = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE",
                     "patch": "PATCH", "head": "HEAD", "options": "OPTIONS"}
SPRING_VERBS = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
                "DeleteMapping": "DELETE", "PatchMapping": "PATCH", "RequestMapping": "ANY"}


class _Member:
    __slots__ = ("cls", "simple", "name", "start", "end", "sig_end", "has_body", "params", "ctor")

    def __init__(self, cls, simple, name, start, params, ctor):
        self.cls, self.simple, self.name = cls, simple, name
        self.start, self.end, self.params, self.ctor = start, start, params, ctor
        self.sig_end, self.has_body = start, False

    @property
    def symbol(self) -> str:
        return "%s#%s" % (self.cls, "<init>" if self.ctor else self.name)


def emit_flow(ctx: ExtractContext, facts: FileFacts, code: List[str], masked: List[str],
              pkg: str, resolver, primary: str) -> None:
    """Append typed-reference, call and HTTP-out facts for one Java file."""
    types: List[Tuple[str, str, int]] = []  # (fqn, simple, body depth)
    fields: Dict[str, Dict[str, str]] = {}
    constants: Dict[str, str] = {}
    members: List[_Member] = []
    open_member: Optional[_Member] = None
    feign: Dict[str, Dict] = {}
    depth = 0
    pending_annotations: List[str] = []

    for idx, line in enumerate(code):
        while types and depth < types[-1][2]:
            types.pop()
        if open_member and depth <= types[-1][2] and idx > open_member.sig_end:
            open_member.end = idx - 1
            open_member = None

        stripped = line.strip()
        tm = TYPE_HEAD_RE.match(line)
        if tm:
            simple = tm.group(2)
            outer = types[-1][0] if types else None
            fqn = (outer + "." + simple) if outer else ((pkg + "." + simple) if pkg else simple)
            _emit_type_header(ctx, facts, code, idx, fqn, resolver)
            if pending_annotations:
                feign_info = _feign_info("\n".join(pending_annotations))
                if feign_info:
                    feign[fqn] = feign_info
            types.append((fqn, simple, depth + 1))
            pending_annotations = []
        elif types and depth == types[-1][2] and open_member is None and stripped:
            if stripped.startswith("@"):
                pending_annotations.append(stripped)
                # `@Autowired private Foo foo;` carries the declaration on the same line.
                rest = re.sub(r"^(?:@[\w$.]+(?:\([^)]*\))?\s*)+", "", stripped)
                if rest:
                    opened = _member_line(ctx, facts, code, idx, rest, types[-1], resolver,
                                          fields, constants, members, pending_annotations)
                    pending_annotations = []
                    if opened and opened.has_body:
                        open_member = opened
            else:
                opened = _member_line(ctx, facts, code, idx, stripped, types[-1], resolver, fields,
                                      constants, members, pending_annotations)
                pending_annotations = []
                if opened and opened.has_body:
                    open_member = opened
        depth += masked[idx].count("{") - masked[idx].count("}")

    if open_member:
        open_member.end = len(code) - 1

    own_methods: Dict[str, set] = {}
    for m in members:
        if not m.ctor:
            own_methods.setdefault(m.cls, set()).add(m.name)

    for m in members:
        _emit_body(ctx, facts, code, m, fields.get(m.cls, {}), constants,
                   own_methods.get(m.cls, set()), resolver)

    _emit_feign(ctx, facts, code, feign, members, resolver)


def _emit_type_header(ctx, facts, code, idx, fqn, resolver) -> None:
    """`class X extends B implements Y` -> `extends` and `implements` rows, read
    across wrapped lines."""
    if not re.match(r"^\s*(?:\w+\s+)*class\s", code[idx]):
        return
    text = " ".join(code[idx: idx + 4])
    text = text.split("{", 1)[0]
    anchor = anchor_at(ctx, idx)
    if anchor is None:
        return
    em = EXTENDS_RE.search(text)
    if em:
        target, state = resolver.resolve(em.group(1).split("<", 1)[0].strip())
        _use(facts, target, anchor, "extends", fqn, state, resolver)
    m = IMPLEMENTS_RE.search(text)
    if not m:
        return
    for name in _split_top_level(m.group(1)):
        base = name.strip().split("<", 1)[0].strip()
        if not base:
            continue
        target, state = resolver.resolve(base)
        _use(facts, target, anchor, "implements", fqn, state, resolver)


def _member_line(ctx, facts, code, idx, stripped, type_info, resolver, fields, constants,
                 members, pending_annotations) -> Optional[_Member]:
    cls, simple, _ = type_info
    # Join a signature that wraps until its parameter list closes.
    text = stripped
    j = idx
    while text.count("(") > text.count(")") and j + 1 < len(code) and j - idx < 12:
        j += 1
        text += " " + code[j].strip()

    fm = FIELD_RE.match(text)
    if fm and "(" not in fm.group(1):
        type_text, name = fm.group(1), fm.group(2)
        fields.setdefault(cls, {})[name] = type_text
        anchor = anchor_at(ctx, idx)
        if anchor is not None:
            _type_uses(facts, type_text, anchor, cls, resolver)
        for annotation in pending_annotations:
            vm = VALUE_FIELD_RE.search(annotation)
            if vm:
                constants[name] = "${%s}" % vm.group(1)
        sm = re.search(r"=\s*(\"(?:[^\"\\]|\\.)*\")\s*;", text)
        if sm and re.search(r"\bstatic\b|\bfinal\b", text.split("=", 1)[0]):
            constants[name] = first_string_literal(sm.group(1)) or ""
        return None

    mm = METHOD_HEAD_RE.match(text)
    if not mm or mm.group(2) in NOT_METHODS or "=" in text.split("(", 1)[0]:
        return None
    ret, name = mm.group(1), mm.group(2)
    ctor = ret is None
    if ctor and name != simple:
        return None
    params = _params(text)
    member = _Member(cls, simple, name, idx, params, ctor)
    member.sig_end, member.has_body = j, "{" in text
    members.append(member)
    anchor = anchor_at(ctx, idx)
    if anchor is not None:
        for type_text, _ in params:
            _type_uses(facts, type_text, anchor, member.symbol, resolver)
    return member


def _params(text: str) -> List[Tuple[str, str]]:
    start = text.index("(")
    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    out = []
    for chunk in _split_top_level(text[start + 1:end]):
        chunk = re.sub(r"@[\w$.]+(?:\([^)]*\))?\s*", "", chunk).replace("final ", "").strip()
        parts = chunk.rsplit(None, 1)
        if len(parts) == 2:
            out.append((parts[0].strip(), parts[1].strip()))
    return out


def _split_top_level(text: str) -> List[str]:
    out, depth, cur = [], 0, []
    for ch in text:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def _use(facts: FileFacts, fqn: str, anchor: Dict, kind: str, from_symbol: str, state: str,
         resolver=None, suffix: str = "") -> None:
    row = mk_use(fqn, anchor, via_import=False, resolved="external")
    row["kind"] = kind
    row["from_symbol"] = from_symbol
    # A name the file does not import is either in its own package or behind a
    # wildcard import. The resolve phase holds the symbol table, so it picks the
    # candidate that exists and drops the row if none does.
    row["speculative"] = state in ("local", "unresolved")
    if row["speculative"] and resolver is not None:
        simple = fqn.split("#", 1)[0].rsplit(".", 1)[-1]
        alts = [w + "." + simple + suffix for w in resolver.wildcards]
        if alts:
            row["alts"] = alts
    facts.uses.append(row)


def use_row(facts: FileFacts, fqn: str, anchor: Dict, kind: str, from_symbol: str, state: str,
            resolver=None) -> None:
    """Public alias for `java.py`, which records repository bindings."""
    _use(facts, fqn, anchor, kind, from_symbol, state, resolver)


def _type_uses(facts: FileFacts, type_text: str, anchor: Dict, from_symbol: str, resolver) -> None:
    seen = set()
    for name in IDENT_RE.findall(type_text.replace("[]", "")):
        if name in seen:
            continue
        seen.add(name)
        target, state = resolver.resolve(name)
        if state == "third_party" and "." not in target:
            continue
        _use(facts, target, anchor, "type", from_symbol, state, resolver)


def _emit_body(ctx, facts, code, member: _Member, fields: Dict[str, str], constants: Dict[str, str],
               own_methods: set, resolver) -> None:
    scope: Dict[str, str] = dict(fields)
    scope.update({n: t for t, n in member.params})
    caller = member.symbol

    in_body = False
    for idx in range(member.start, member.end + 1):
        line = code[idx]
        if not in_body:
            if "{" not in line:
                continue
            in_body = True
            line = line.split("{", 1)[1]
        for lm in LOCAL_RE.finditer(line):
            scope[lm.group(2)] = lm.group(1)
            anchor = anchor_at(ctx, idx)
            if anchor is not None:
                _type_uses(facts, lm.group(1), anchor, caller, resolver)
        for vm in VAR_NEW_RE.finditer(line):
            scope[vm.group(1)] = vm.group(2)

        for cm in RECEIVER_CALL_RE.finditer(line):
            this_prefix, receiver, method = cm.group(1), cm.group(2), cm.group(3)
            if receiver == "this" and not this_prefix:
                # `this.validate(x)`: a call to one of the class's own methods.
                _own_call(ctx, facts, idx, member, method, own_methods)
                continue
            type_text = fields.get(receiver) if this_prefix else scope.get(receiver)
            if type_text is None and not this_prefix and receiver[:1].isupper():
                type_text = receiver  # static call on a type name
            if type_text is None:
                continue
            base = type_text.split("<", 1)[0].replace("[]", "").strip()
            if base in HTTP_CLIENT_TYPES:
                _emit_http_call(ctx, facts, code, idx, caller, base, receiver, method, constants)
                continue
            target, state = resolver.resolve(base)
            anchor = anchor_at(ctx, idx)
            if anchor is not None and target:
                _use(facts, "%s#%s" % (target, method), anchor, "call", caller, state,
                     resolver, "#" + method)
        for bm in BARE_CALL_RE.finditer(line):
            name = bm.group(1)
            if name not in NOT_METHODS:
                _own_call(ctx, facts, idx, member, name, own_methods)


def _own_call(ctx, facts, idx: int, member: _Member, name: str, own_methods: set) -> None:
    if name in own_methods and name != member.name:
        anchor = anchor_at(ctx, idx)
        if anchor is not None:
            row = mk_use("%s#%s" % (member.cls, name), anchor, via_import=False, resolved="external")
            row.update({"kind": "call", "from_symbol": member.symbol, "speculative": False})
            facts.uses.append(row)


# --------------------------------------------------------------- HTTP out


def _statement(code: List[str], idx: int, span: int = 6) -> str:
    """The call expression starting at `idx`, joined across wrapped lines."""
    text = code[idx]
    j = idx
    while text.count("(") > text.count(")") and j + 1 < len(code) and j - idx < span:
        j += 1
        text += " " + code[j].strip()
    return text


def _url_expr(expr: str, constants: Dict[str, str]) -> Optional[str]:
    """Evaluate `"http://x" + PATH + id` into `http://x/path{}`; None if no part is known."""
    out: List[str] = []
    known = False
    for part in _split_plus(expr):
        part = part.strip()
        lit = first_string_literal(part) if part.startswith('"') else None
        if lit is not None:
            out.append(lit)
            known = True
        elif part in constants:
            out.append(constants[part])
            known = True
        elif part:
            out.append("{}")
    return "".join(out) if known else None


def _split_plus(expr: str) -> List[str]:
    out, cur, quote, depth = [], [], False, 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and i + 1 < len(expr):
                cur.append(expr[i + 1])
                i += 1
            elif ch == '"':
                quote = False
        elif ch == '"':
            quote = True
            cur.append(ch)
        elif ch in "([":
            depth += 1
            cur.append(ch)
        elif ch in ")]":
            depth -= 1
            cur.append(ch)
        elif ch == "+" and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur))
    return out


def _first_arg(text: str, open_at: int) -> str:
    depth, quote, i = 0, False, open_at
    start = open_at + 1
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == '"':
                quote = False
        elif ch == '"':
            quote = True
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
            if depth == 0:
                return text[start:i]
        elif ch == "," and depth == 1:
            return text[start:i]
        i += 1
    return text[start:]


def _emit_http_call(ctx, facts, code, idx, caller, client, receiver, method, constants) -> None:
    text = _statement(code, idx)
    m = re.search(r"(?<![\w$.])%s\.%s\s*\(" % (re.escape(receiver), re.escape(method)), text)
    if not m:
        return
    verb: Optional[str] = None
    url_arg: Optional[str] = None
    if client in ("RestTemplate", "TestRestTemplate"):
        verb = REST_TEMPLATE_VERBS.get(method)
        if method in ("exchange", "execute"):
            hm = re.search(r"HttpMethod\.([A-Z]+)", text)
            verb = hm.group(1) if hm else None
            if method == "execute" and verb is None:
                return
        elif verb is None:
            return
        url_arg = _first_arg(text, m.end() - 1)
    else:
        verb = CLIENT_VERB_CALLS.get(method)
        if method == "method":
            hm = re.search(r"HttpMethod\.([A-Z]+)", text)
            verb = hm.group(1) if hm else None
        if verb is None:
            return
        # `webClient.post().uri("...")`: the URI is set on the same statement.
        full = _statement(code, idx, span=10)
        um = re.search(r"\.(?:uri|url)\s*\(", full[m.start():])
        if not um:
            return
        url_arg = _first_arg(full, m.start() + um.end() - 1)
    url = _url_expr(url_arg, constants)
    anchor = anchor_at(ctx, idx)
    if not url or anchor is None:
        return
    facts.signals.append("http_client")
    facts.io_edges.append(mk_edge(caller, "http:%s %s" % (verb or "ANY", url), "http_out", anchor))


def _feign_info(annotation_text: str) -> Optional[Dict]:
    m = re.search(r"@FeignClient\s*(\(.*)", annotation_text, re.S)
    if not m:
        return None
    args = m.group(1)
    info = {"url": None, "name": None, "path": ""}
    for key in ("url", "name", "value", "path"):
        km = re.search(r"\b%s\s*=\s*\"([^\"]*)\"" % key, args)
        if km:
            info["name" if key == "value" else key] = km.group(1)
    if info["name"] is None:
        lit = first_string_literal(args)
        info["name"] = lit
    return info


def _emit_feign(ctx, facts, code, feign: Dict[str, Dict], members, resolver) -> None:
    """`@FeignClient` interfaces: one `http_out` per mapped method."""
    if not feign:
        return
    for idx, line in enumerate(code):
        am = re.match(r"^\s*@(Get|Post|Put|Delete|Patch|Request)Mapping\s*(\(.*)?$", line)
        if not am:
            continue
        args = am.group(2) or ""
        path = _named_or_first(args, ("value", "path")) or ""
        verb = SPRING_VERBS.get(am.group(1) + "Mapping", "ANY")
        if verb == "ANY":
            rm = re.search(r"RequestMethod\.([A-Z]+)", args)
            verb = rm.group(1) if rm else "ANY"
        method_name = None
        for j in range(idx + 1, min(idx + 8, len(code))):
            mm = METHOD_HEAD_RE.match(code[j].strip())
            if mm and mm.group(2) not in NOT_METHODS:
                method_name = mm.group(2)
                break
        owner = _feign_owner(code, idx, feign)
        if owner is None:
            continue
        info = feign[owner]
        base = info["url"] or ("http://%s" % info["name"] if info["name"] else "")
        url = (base.rstrip("/") + "/" + (info["path"] or "").strip("/") + "/" + path.lstrip("/")).replace("//", "/")
        url = url.replace(":/", "://").rstrip("/") if url else url
        if not base:
            continue
        anchor = anchor_at(ctx, idx)
        if anchor is None:
            continue
        facts.signals.append("http_client")
        source = "%s#%s" % (owner, method_name) if method_name else owner
        facts.io_edges.append(mk_edge(source, "http:%s %s" % (verb, url), "http_out", anchor))


def _feign_owner(code: List[str], idx: int, feign: Dict[str, Dict]) -> Optional[str]:
    # Feign clients are single-level interfaces; the owner is the one declared
    # above this line, which for a flat file is the last (only) entry.
    return list(feign)[-1] if feign else None


def _named_or_first(args: str, keys) -> Optional[str]:
    for key in keys:
        m = re.search(r"\b%s\s*=\s*\"([^\"]*)\"" % key, args)
        if m:
            return m.group(1)
    return first_string_literal(args)
