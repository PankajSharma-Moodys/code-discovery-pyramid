"""Scala member-level facts: type references, config reads, outbound HTTP, entry points.

The Scala twin of `java_flow` (+ `java_config`): the same rows, read from the Scala token stream.

  config_read     `System.getenv/getProperty` (via `java_config.emit_config`, the token shapes are
                  identical), `sys.env("K")`, `sys.env.get/getOrElse/apply("K")`, `sys.props(..)`,
                  and `configProvider.getValue(KEY)` (via `java_config.emit_provider_reads`)
  http_out        JAX-RS client `client.target(url)[.path(p)].request(..)[..].get/post/put/delete(..)`;
                  only when part of the URL is a literal or a constant (as for Java)
  process_boundary  `def main(args: Array[String])` in an object, and `extends App`
  uses            `extends`/`implements`/`type` rows for declared types
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .base import ExtractContext, FileFacts, anchor_at, mk_edge, mk_use
from .java_config import PROVIDER_TYPE, _args, _key, emit_config, emit_provider_reads
from .java_flow import _use, type_uses
from .scala_decl import ScMember, ScType, scala_type_text
from .scala_tokens import ScTokens, string_value

CLIENT_VERBS = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE", "patch": "PATCH",
                "head": "HEAD", "options": "OPTIONS", "method": "ANY"}
SYS_READERS = frozenset(["get", "getOrElse", "apply", "getOrElseUpdate"])
APP_SUPERS = frozenset(["App", "scala.App", "IOApp", "ZIOAppDefault", "ZIOApp"])
JOB_SUPERS = frozenset(["Job", "InterruptableJob", "AbstractJob"])


def scala_provider_names(tk: ScTokens) -> frozenset:
    """`name: ConfigProvider` (a parameter, field or local declared with a config-ish type)."""
    out = set()
    for i in range(2, tk.n):
        if tk.kind[i] != "id" or not tk.text[i][:1].isupper() or not PROVIDER_TYPE.search(tk.text[i]):
            continue
        if tk.at(i - 1) == ":" and tk.is_id(i - 2):
            out.add(tk.text[i - 2])
    return frozenset(out)


def _config_view(tk: ScTokens) -> ScTokens:
    """A copy of the token stream in which a string with interpolation holes (`s"A_${i}"`) is not a
    literal: `java_config` reads quoted text as a key, and `A_${i}` is not one."""
    import copy
    view = copy.copy(tk)
    view.text = [("<interp>" if tk.kind[i] == "str" and string_value(t) is None else t)
                 for i, t in enumerate(tk.text)]
    return view


def spans_of(types: List[ScType]):
    """(type, member, a, b, caller symbol) for every body and initialiser span."""
    for jt in types:
        for m in jt.members:
            for sp in (m.body, m.init):
                if sp and sp[1] > sp[0]:
                    yield jt, m, sp[0], sp[1], m.symbol


def _type_header(ctx: ExtractContext, facts: FileFacts, jt: ScType, resolver) -> None:
    anchor = anchor_at(ctx, jt.line)
    if anchor is None:
        return
    for idx, text in enumerate(jt.supertypes):
        base = scala_type_text(text).split("<", 1)[0].strip()
        if not base:
            continue
        target, state = resolver.resolve(base)
        if state == "third_party" and "." not in target:
            continue
        kind = "extends" if (idx == 0 and jt.kind != "interface") or jt.kind == "interface" else "implements"
        _use(facts, target, anchor, kind, jt.fqn, state, resolver)


def _sys_reads(ctx: ExtractContext, facts: FileFacts, tk: ScTokens, a: int, b: int, caller: str,
               constants: Dict[str, str], own: frozenset) -> None:
    for i in range(a, b):
        if tk.text[i] != "sys" or tk.kind[i] != "id" or tk.at(i + 1) != ".":
            continue
        if tk.at(i - 1) == "." and tk.at(i - 2) != "scala":
            continue
        if tk.at(i + 2) not in ("env", "props") or tk.kind[i + 2] != "id":
            continue
        j = i + 3
        line_i = i + 2
        if tk.at(j) == "(":
            open_i = j
        elif tk.at(j) == "." and tk.at(j + 1) in SYS_READERS and tk.at(j + 2) == "(":
            open_i, line_i = j + 2, j + 1
        else:
            continue
        args = _args(tk, open_i)
        if not args:
            continue
        anchor = anchor_at(ctx, tk.line[line_i])
        if anchor is None:
            continue
        key = _key(tk, args[0][0], args[0][1], constants, {}, own)
        facts.io_edges.append(mk_edge(caller, "config:" + key, "config_read", anchor))


def _interp_url(text: str, constants: Dict[str, str]) -> Optional[str]:
    """`s"$base/x/${id}"` -> `{}/x/{}`; a plain literal as is; None when it is not a string."""
    q = text.find('"')
    if q < 0:
        return None
    prefix = text[:q]
    val = string_value(text)
    if val is not None:
        return val
    body = text[q:]
    body = body[3:-3] if body.startswith('"""') else body[1:-1]
    if prefix not in ("s", "f"):
        return None

    def sub(m: "re.Match[str]") -> str:
        name = m.group(1) or m.group(2)
        return constants.get(name.strip(), "{}") if name and re.fullmatch(r"[A-Za-z_]\w*", name.strip()) else "{}"
    return re.sub(r"\$(?:\{([^{}]*)\}|([A-Za-z_]\w*))", sub, body.replace("$$", "$"))


def url_expr(tk: ScTokens, a: int, b: int, constants: Dict[str, str]) -> Optional[str]:
    """`"http://x" + PATH + id` / `s"..."` -> `http://x/path{}`; None if no part is known."""
    out: List[str] = []
    known = False
    i = a
    while i < b:
        k, t = tk.kind[i], tk.text[i]
        if k == "str":
            v = _interp_url(t, constants)
            if v is not None:
                out.append(v)
                known = known or bool(v.replace("{}", ""))
            else:
                out.append("{}")
        elif k == "id" and t in constants and tk.at(i + 1) not in ("(", "."):
            out.append(constants[t])
            known = True
        elif k == "op" and t == "+":
            pass
        else:
            out.append("{}")
            if tk.kind[i] == "op" and t in "([{":
                i = tk.close(i)
            else:
                while tk.at(i + 1) == "." and tk.is_id(i + 2):
                    i += 2
                    if tk.at(i + 1) == "(":
                        i = tk.close(i + 1)
        i += 1
    s = "".join(out)
    s = re.sub(r"(\{\})+", "{}", s)
    return s if known else None


def _http_out(ctx: ExtractContext, facts: FileFacts, tk: ScTokens, a: int, b: int, caller: str,
              constants: Dict[str, str]) -> int:
    """JAX-RS client chains; returns the number of `.target(` sites seen (emitted or not)."""
    sites = 0
    for i in range(a, b):
        if tk.text[i] != "target" or tk.at(i - 1) != "." or tk.at(i + 1) != "(" or not tk.is_id(i):
            continue
        sites += 1
        c = tk.close(i + 1)
        base = url_expr(tk, i + 2, c, constants)
        j = c + 1
        path = ""
        seen_request = False
        verb = None
        while tk.at(j) == "." and tk.is_id(j + 1) and tk.at(j + 2) == "(":
            name = tk.text[j + 1]
            cc = tk.close(j + 2)
            if name == "path":
                seg = url_expr(tk, j + 3, cc, constants)
                path += "/" + (seg or "{}").lstrip("/")
            elif name == "request":
                seen_request = True
            elif seen_request and name in CLIENT_VERBS:
                verb = CLIENT_VERBS[name]
                break
            j = cc + 1
        if not seen_request or verb is None:
            continue
        anchor = anchor_at(ctx, tk.line[i])
        if anchor is None:
            continue
        url = base
        if url is None:
            continue
        url = url.rstrip("/") + path if path else url
        facts.signals.append("http_client")
        facts.io_edges.append(mk_edge(caller, "http:%s %s" % (verb, url), "http_out", anchor))
    return sites


def emit_flow(ctx: ExtractContext, facts: FileFacts, tk: ScTokens, types: List[ScType], resolver,
              constants: Dict[str, str]) -> Dict[str, int]:
    """Append type uses, config reads, HTTP-out and entry-point facts for one Scala file."""
    own = frozenset(jt.name for jt in types)
    providers = scala_provider_names(tk)
    stats = {"target_sites": 0}
    for jt in types:
        tv = jt.all_tparams()
        _type_header(ctx, facts, jt, resolver)
        if any(s.split("[", 1)[0].split(".")[-1] in APP_SUPERS for s in jt.supertypes) and jt.is_object:
            anchor = anchor_at(ctx, jt.line)
            if anchor is not None:
                facts.signals.append("main")
                facts.io_edges.append(mk_edge(jt.fqn, "process:" + jt.fqn, "process_boundary", anchor))
        if any(s.split("[", 1)[0].split(".")[-1] in JOB_SUPERS for s in jt.supertypes):
            anchor = anchor_at(ctx, jt.line)
            if anchor is not None:
                facts.signals.append("quartz_job")
                facts.io_edges.append(mk_edge(jt.fqn, "scheduler", "schedule", anchor))
        for m in jt.members:
            anchor = anchor_at(ctx, m.line)
            if anchor is None:
                continue
            if m.kind == "field":
                if m.ftype:
                    type_uses(facts, m.ftype, anchor, jt.fqn, resolver)
            elif m.kind in ("method", "ctor"):
                for ptype, _ in m.params:
                    type_uses(facts, ptype, anchor, m.symbol, resolver)
                if m.kind == "method" and m.ret:
                    type_uses(facts, m.ret, anchor, m.symbol, resolver)
                if m.kind == "method" and m.name == "main" and jt.is_object and len(m.params) == 1 \
                        and m.params[0][0].replace(" ", "") in ("Array<String>", "String[]"):
                    facts.signals.append("main")
                    facts.io_edges.append(mk_edge(jt.fqn, "process:" + jt.fqn, "process_boundary", anchor))
                if m.kind == "method" and m.params and any(n == "Subscribe" for n, _ in m.anns):
                    event = scala_type_text(m.params[0][0]).split("<", 1)[0]
                    target, state = resolver.resolve(event)
                    if event and state != "third_party":
                        facts.signals.append("event_subscriber")
                        facts.io_edges.append(mk_edge(m.symbol, "event:" + target, "event_subscribe", anchor))
    cfg = _config_view(tk)
    for jt, m, a, b, caller in spans_of(types):
        names = [n for _, n in m.params]
        emit_config(ctx, facts, cfg, a, b, caller, constants, {}, own, names)
        _sys_reads(ctx, facts, cfg, a, b, caller, constants, own)
        emit_provider_reads(ctx, facts, cfg, a, b, caller, constants, {}, own, providers, names)
        stats["target_sites"] += _http_out(ctx, facts, tk, a, b, caller, constants)
    return stats
