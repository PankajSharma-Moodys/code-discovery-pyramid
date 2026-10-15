"""Java member-level facts: typed references, call sites, outbound HTTP.

`java.py` reads what a file *declares*. This reads what its member bodies *do*,
which is what a "how does this behave" question needs: `OrderResource#place`
calls `OrderService#placeOrder`, which calls `OrderRepository#save`.

Declarations come from `java_decl`; the body walk (locals, fields, chained
calls, method references, constructors) is `java_body`. Everything is read from
declared types, never guessed from names. Receivers whose type the file does not
state are carried as a chain for the resolve phase to settle against the symbol
table; receivers nobody can type produce no edge rather than a wrong one.

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
from .java_body import FileInfo, Scan
from .java_config import emit_config, emit_provider_reads, provider_names
from .java_decl import JMember, JType, parse_type
from .java_types import split_type, wildcard_alts
from .java_tokens import Tokens

IDENT_RE = re.compile(r"[A-Z][\w$]*")
QUALIFIED_RE = re.compile(r"[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*")
VALUE_FIELD_RE = re.compile(r"@Value\s*\(\s*\"\$\{([^}:]+)(?::[^}]*)?\}\"\s*\)")
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
METHOD_HEAD_RE = re.compile(
    r"^(?:(?:public|protected|private|static|final|abstract|synchronized|default)\s+)*"
    r"(?:<[^>]*>\s+)?(?:([A-Za-z_$][\w$.]*(?:<[^()]*>)?(?:\[\])*)\s+)?([a-zA-Z_$][\w$]*)\s*\("
)
NOT_METHODS = frozenset(["if", "for", "while", "switch", "catch", "return", "new", "super", "this",
                         "synchronized", "throw", "else", "try", "assert"])


def emit_flow(ctx: ExtractContext, facts: FileFacts, code: List[str], tk: Tokens, types: List[JType],
              resolver, static_imports: Dict[str, str], static_wild: List[str]) -> None:
    """Append typed-reference, call and HTTP-out facts for one Java file."""
    constants: Dict[str, str] = {}
    feign: Dict[str, Dict] = {}
    constants_of: Dict[str, Dict[str, str]] = {}

    def http(line: int, caller: str, client: str, receiver: str, method: str) -> bool:
        _emit_http_call(ctx, facts, code, line, caller, client, receiver, method, constants)
        return True

    own = frozenset(jt.fqn.rsplit(".", 1)[-1] for jt in types)
    fi = FileInfo(ctx, facts, tk, resolver, types, static_imports, static_wild, http,
                  lambda scan, recv, name_i: _emit_event_post(ctx, facts, scan, recv, name_i))
    fi.http_types = HTTP_CLIENT_TYPES
    fi.constants, fi.own = constants, own
    providers = provider_names(tk)
    for jt in types:
        tv = jt.all_tparams()
        for m in jt.members:
            if m.kind in ("field", "enum_const"):
                fi.fields.setdefault(jt.fqn, {})[m.name] = fi.norm(m.ftype, tv)
                _note_constant(tk, m, constants)
        info = _feign_info("\n".join(text for _, text in jt.anns))
        if info:
            info["span"] = (jt.start_line, jt.end_line)
            feign[jt.fqn] = info
        _emit_type_header(ctx, facts, jt, resolver)

    for jt in types:
        tv = jt.all_tparams()
        for m in jt.members:
            anchor = anchor_at(ctx, m.line)
            if m.kind in ("field", "enum_const"):
                if anchor is not None and m.kind == "field":
                    type_uses(facts, m.ftype, anchor, jt.fqn, resolver)
                if m.kind == "enum_const" and anchor is not None:
                    row = mk_use(jt.fqn + "#<init>", anchor, via_import=False, resolved="external")
                    row.update({"kind": "call", "from_symbol": m.symbol, "speculative": False,
                                "how": "new"})
                    facts.uses.append(row)
                if m.init and m.init[1] > m.init[0]:
                    scan = Scan(fi, jt, m.symbol, tv, bounds=jt.all_bounds())
                    scan.run(*m.init)
                    emit_config(ctx, facts, tk, m.init[0], m.init[1], m.symbol, constants, static_imports, own)
                    emit_provider_reads(ctx, facts, tk, m.init[0], m.init[1], m.symbol, constants,
                                        static_imports, own, providers)
            elif m.kind in ("method", "ctor", "init"):
                mtv = tv | set(m.tparams)
                if m.kind == "method" and anchor is not None and m.params \
                        and any(n.rsplit(".", 1)[-1] == "Subscribe" for n, _ in m.anns):
                    event = split_type(fi.norm(m.params[0][0], mtv))[0]
                    if event and not event.startswith("~"):
                        facts.signals.append("event_subscriber")
                        facts.io_edges.append(mk_edge(m.symbol, "event:" + event, "event_subscribe", anchor))
                if anchor is not None:
                    for ptype, _ in m.params:
                        type_uses(facts, ptype, anchor, m.symbol, resolver)
                    if m.kind == "method" and m.ret:
                        type_uses(facts, m.ret, anchor, m.symbol, resolver)
                if m.body:
                    scan = Scan(fi, jt, m.symbol, mtv,
                                bounds=dict(jt.all_bounds(), **getattr(m.tparams, "bounds", {})))
                    scan.declare_params(m.params)
                    scan.caller_sig = m.sig
                    if m.kind == "ctor" and jt.extends and not _calls_ctor(tk, m.body[0]):
                        # javac's implicit `super();` at the top of a constructor
                        sup = fi.norm(jt.extends[0], tv)
                        scan.emit(sup.split("<", 1)[0], "<init>", tk.line[m.body[0] - 1], "ctor", (), argc=0)
                    scan.run(*m.body)
                    names = [n for _, n in m.params]
                    emit_config(ctx, facts, tk, m.body[0], m.body[1], m.symbol, constants, static_imports, own,
                                names)
                    emit_provider_reads(ctx, facts, tk, m.body[0], m.body[1], m.symbol, constants,
                                        static_imports, own, providers, names)

    _emit_feign(ctx, facts, code, feign, [], resolver)


EVENT_BUS_TYPES = frozenset(["EventBus", "AsyncEventBus"])


def _emit_event_post(ctx: ExtractContext, facts: FileFacts, scan: Scan, recv_type: str, name_i: int) -> None:
    """`eventBus.post(new X(...))` (or `post(x)` with `x` declared `X`) publishes event type
    `X`: an `event_publish` edge to `event:X`, which `dataflow` joins to the `@Subscribe`
    methods taking `X`. The receiver must be declared as a Guava `EventBus`/`AsyncEventBus`;
    any other `post` (an HTTP client, say) is not an event."""
    tk = scan.tk
    if split_type(recv_type)[0].rsplit(".", 1)[-1] not in EVENT_BUS_TYPES or tk.at(name_i + 1) != "(":
        return
    j = name_i + 2
    event = None
    if tk.at(j) == "new":
        r = parse_type(tk, j + 1)
        if r and tk.at(r[0]) == "(":
            event = split_type(scan.fi.norm(r[1], scan.tvars))[0]
    elif tk.is_id(j) and tk.at(j + 1) in (")", ","):
        found, val = scan.lookup(tk.text[j])
        if found and val and not val[1]:
            event = split_type(val[0])[0]
    anchor = anchor_at(ctx, tk.line[name_i])
    if event and not event.startswith("~") and anchor is not None:
        facts.signals.append("event_publisher")
        facts.io_edges.append(mk_edge(scan.caller, "event:" + event, "event_publish", anchor))


def _calls_ctor(tk: Tokens, i: int) -> bool:
    return tk.at(i) in ("this", "super") and tk.at(i + 1) == "("


def _note_constant(tk: Tokens, m: JMember, constants: Dict[str, str]) -> None:
    for name, text in m.anns:
        if name == "Value":
            vm = VALUE_FIELD_RE.search(text)
            if vm:
                constants[m.name] = "${%s}" % vm.group(1)
    if m.init and m.init[1] - m.init[0] == 1 and tk.kind[m.init[0]] == "str" \
            and ("static" in m.mods or "final" in m.mods):
        constants[m.name] = first_string_literal(tk.text[m.init[0]]) or ""


def _emit_type_header(ctx: ExtractContext, facts: FileFacts, jt: JType, resolver) -> None:
    """`class X extends B implements Y` -> `extends` and `implements` rows. An
    interface's `extends` list is a list of super-interfaces: `extends` rows."""
    anchor = anchor_at(ctx, jt.line)
    if anchor is None:
        return
    for name in jt.extends:
        target, state = resolver.resolve(name.split("<", 1)[0].strip())
        _use(facts, target, anchor, "extends", jt.fqn, state, resolver)
    kind = "extends" if jt.kind in ("interface", "annotation") else "implements"
    for name in jt.implements:
        base = name.split("<", 1)[0].strip()
        if base:
            target, state = resolver.resolve(base)
            _use(facts, target, anchor, kind, jt.fqn, state, resolver)


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
        alts = wildcard_alts(resolver, fqn, suffix)
        if alts:
            row["alts"] = alts
    facts.uses.append(row)


def use_row(facts: FileFacts, fqn: str, anchor: Dict, kind: str, from_symbol: str, state: str,
            resolver=None) -> None:
    """Public alias for `java.py`, which records repository bindings."""
    _use(facts, fqn, anchor, kind, from_symbol, state, resolver)


def type_uses(facts: FileFacts, type_text: str, anchor: Dict, from_symbol: str, resolver) -> None:
    seen = set()
    for name in QUALIFIED_RE.findall(type_text.replace("[]", "")):
        name = re.sub(r"\s+", "", name)
        # `a.b.Type` is one reference (by its full path), `Outer.Inner` a reference to
        # Inner and to Outer; a lone lowercase word is a keyword or a package.
        parts = name.split(".")
        names = [name] + [".".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)
                          if parts[i - 1][:1].isupper()]
        for one in names:
            if one in seen or not one.rsplit(".", 1)[-1][:1].isupper():
                continue
            seen.add(one)
            target, state = resolver.resolve(one)
            if state == "third_party" and "." not in target:
                continue
            _use(facts, target, anchor, "type", from_symbol, state, resolver)


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
    m = re.search(r"(?<![\w$])(?:this\.)?%s\.%s\s*\(" % (re.escape(receiver), re.escape(method)), text)
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
    """The `@FeignClient` type whose lines contain `idx`; a mapping anywhere else in the
    file (a controller beside the client) is not a client call."""
    for fqn, info in feign.items():
        lo, hi = info["span"]
        if lo <= idx <= hi:
            return fqn
    return None


def _named_or_first(args: str, keys) -> Optional[str]:
    for key in keys:
        m = re.search(r"\b%s\s*=\s*\"([^\"]*)\"" % key, args)
        if m:
            return m.group(1)
    return first_string_literal(args)
