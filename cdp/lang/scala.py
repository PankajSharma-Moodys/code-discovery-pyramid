"""Scala extractor.

Reads a `.scala` file the way `java.py` reads a `.java` one: a token stream (`scala_tokens`), declarations
at any visibility with extents (`scala_decl`), annotations as structured args (`scala_annotations`), and
member-level facts (`scala_flow`, `scala_body`). JVM annotations are Java's, so a Scala row has the same
shape as a Java one and the rule engine, `resolve.py`, dataflow and link read both alike.

Kinds: `trait` -> `interface`; `object` -> `class` with `object: true` (a companion object is merged into
its class: one define row, `companion: true`); `case class` -> `class` with `case: true`.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .. import sigs
from .java_types import norm_type, resolve_name
from .base import (
    ExtractContext,
    Extractor,
    FileFacts,
    anchor_at,
    channel_for_import,
    count_loc,
    mk_edge,
)
from .scala_decl import ScalaDeclParser
from .scala_emit import ScResolver, declarations, di_signals, read_imports
from .scala_body import scan_file
from .scala_flow import emit_flow
from .scala_tokens import ScTokens, string_value


class ScalaExtractor(Extractor):
    language = "scala"
    extensions = (".scala",)

    def extract(self, ctx: ExtractContext) -> FileFacts:
        lines = ctx.lines
        facts = FileFacts(path=ctx.path, language=self.language, loc=count_loc(lines))
        tk = ScTokens(lines)
        parser = ScalaDeclParser(tk, lines)
        parser.parse()
        types = parser.types
        facts.package = parser.package or None
        pkg = parser.package
        imports, simple_to_fqn, wildcards = read_imports(ctx, tk, facts)
        resolver = ScResolver(pkg, simple_to_fqn, wildcards)
        resolver.local_types = {t.name: t.fqn for t in types}
        sigs.assign(types, lambda t, tv: norm_type(t, lambda n: resolve_name(resolver, n), tv) or t)
        decls = declarations(ctx, facts, tk, types, resolver)

        # Mirror Java: primary is the first top-level type. A companion object has no define row of its
        # own (it merges into the class, same fqn), so its members must not win by line order.
        tops = sorted((t for t in types if t.outer is None), key=lambda t: (t.line, t.fqn))
        primary = tops[0].fqn if tops else (decls[0]["fqn"] if decls else (pkg + "." + _stem(ctx.path) if pkg else _stem(ctx.path)))
        facts.primary = primary

        _emit_import_edges(facts, imports, primary)
        di_signals(facts, types)
        constants = {d["fqn"].rsplit(".", 1)[-1]: d["value"] for d in facts.defines
                     if d["kind"] == "constant" and isinstance(d.get("value"), str)}
        emit_flow(ctx, facts, tk, types, resolver, constants)
        scan_file(ctx, facts, tk, types, resolver, lines, constants)

        facts.signals = sorted(set(facts.signals))
        return facts


def _stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _emit_import_edges(facts: FileFacts, imports: List[Dict], primary: str) -> None:
    seen = set()
    for row in imports:
        channel = channel_for_import(row["fqn"])
        if channel is None or channel in seen:
            continue
        seen.add(channel)
        parts = row["fqn"].split(".")
        root = ".".join(parts[:3]) if len(parts) >= 3 else row["fqn"]
        facts.io_edges.append(mk_edge(primary, "library:" + root, channel, row["anchor"]))
