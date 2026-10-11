"""C# member-level facts: base types, configuration reads, typed references and call sites.

`csharp.py` reads what a file declares; this reads what its member bodies do. Declarations come
from `csharp_decl`; the body walk (locals, fields, chained calls, `new`, method groups) is
`csharp_body`, configuration reads are `csharp_config`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .base import ExtractContext, FileFacts, anchor_at, is_third_party
from .csharp_config import config_names, emit_config, key_of
from .csharp_decl import CMember, CType, DeclParser
from .csharp_tokens import CsTokens
from .java_flow import use_row


def member_spans(m: CMember) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    if m.ctor_init:
        spans.append((m.ctor_init[0], m.ctor_init[1]))
    if m.body:
        spans.append(m.body)
    spans.extend(m.bodies)
    if m.init and m.init[1] > m.init[0]:
        spans.append(m.init)
    return spans


def _header(ctx: ExtractContext, facts: FileFacts, jt: CType, resolver) -> None:
    anchor = anchor_at(ctx, jt.line)
    if anchor is None:
        return
    for name in jt.extends:
        target, state = resolver.resolve(name.split("<", 1)[0].strip())
        use_row(facts, target, anchor, "extends", jt.fqn, state, resolver)
    kind = "extends" if jt.kind == "interface" else "implements"
    for name in jt.implements:
        base = name.split("<", 1)[0].strip()
        if base:
            target, state = resolver.resolve(base)
            use_row(facts, target, anchor, kind, jt.fqn, state, resolver)


def owner_resolver(jt: CType, statics: List[Dict]):
    """The class a bare identifier (a constant used as `Key`) belongs to: this class, an enclosing
    one, or -- when none declares it -- the type of the file's `using static`."""
    chain = []
    t = jt
    while t is not None:
        chain.append(t)
        t = t.outer
    members = {id(c): {m.name for m in c.members} | {m.name for m in c.types} for c in chain}
    members = {c.name: members[id(c)] for c in chain}
    statics_ = [s["fqn"].rsplit(".", 1)[-1] for s in statics if not is_third_party(s["fqn"])]

    def owner(name: str) -> str:
        for c in chain:
            if name in members[c.name]:
                return c.name
        return statics_[0] if statics_ else jt.name
    return owner


def emit_flow(ctx: ExtractContext, facts: FileFacts, tk: CsTokens, parser: DeclParser, types: List[CType],
              resolver, statics: List[Dict], ns: str) -> None:
    cfg = config_names(tk)
    constants: Dict[str, Dict[str, str]] = {}
    for jt in types:
        _header(ctx, facts, jt, resolver)
        for m in jt.members:
            if m.kind == "field" and m.init and "static" in m.mods and ("const" in m.mods or "readonly" in m.mods) \
                    and not m.prop:
                v = key_of(tk, m.init[0], m.init[1], constants.get(jt.fqn, {}), owner_resolver(jt, statics))
                if v != "(dynamic)":
                    constants.setdefault(jt.fqn, {})[m.name] = v
    for jt in types:
        local = constants.get(jt.fqn, {})
        for m in jt.members:
            for a, b in member_spans(m):
                emit_config(ctx, facts, tk, a, b, m.symbol, local, owner_resolver(jt, statics), cfg)
    if parser.top_spans:
        owner = (ns + "." if ns else "") + "Program#<Main>"
        for a, b in parser.top_spans:
            emit_config(ctx, facts, tk, a, b, owner, {}, "Program", cfg)
    from .csharp_body import emit_bodies
    emit_bodies(ctx, facts, tk, parser, types, resolver, statics, ns)
