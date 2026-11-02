"""Cross-module and same-file uses in a JS/TS/Vue file: what each imported binding is used for.

Syntactic, per file. An import binds a local name to `(module, exported name)`; every later
occurrence of that name is a `call` (`f(`, `X.f(`, `ns.f(`) or a `ref` (a callback, a JSX/Vue
tag, a type position). The module is emitted as written (`./x` made repo-relative, `@/x` kept),
and `cdp/webres.py` binds it to a declared symbol with the repo's file list in view.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .web_flow import Source

LOCAL_SPEC = re.compile(r"^(?:\.|@/|~/|#/)")
_IDENT = re.compile(r"^[A-Za-z_$][\w$]*$")
_IMPORT = re.compile(r"""\bimport\s+(?:type\s+)?([^'";]*?)\s*\bfrom\s+['"]([^'"]+)['"]""")
_DYN = re.compile(r"""(?:const|let|var)\s+(?:(\w+)|\{([^}]*)\})\s*=\s*(?:await\s+)?(?:import|require)\s*\(\s*['"]([^'"]+)['"]\s*\)""")
_REEXPORT = re.compile(r"""\bexport\s+(?:type\s+)?(?:\{([^}]*)\}|\*(?:\s+as\s+(\w+))?)\s*from\s*['"]([^'"]+)['"]""")
_STR = re.compile(r"""'[^'\n]*'|"[^"\n]*\"""")
_NOT_REF_BEFORE = frozenset(("function", "class", "new", "interface", "type", "enum", "const", "let", "var", "import", "export"))


def _parts(body: str) -> List[Tuple[str, str]]:
    """`a, b as c, type d` -> [(exported, local)]."""
    out = []
    for part in body.split(","):
        bits = re.split(r"\s+as\s+", re.sub(r"^\s*type\s+", "", part.strip()))
        if bits and _IDENT.match(bits[0]):
            out.append((bits[0], bits[-1]))
    return out


def bindings(text: str, mod_of) -> Tuple[Dict[str, Tuple[str, str]], List[Tuple[int, str, str, str]]]:
    """(local -> (module, exported | "default" | "*"), re-exports [(offset, exported-as, module, name | "*")])."""
    bound: Dict[str, Tuple[str, str]] = {}
    for m in _IMPORT.finditer(text):
        if not LOCAL_SPEC.match(m.group(2)):
            continue
        module, clause = mod_of(m.group(2)), m.group(1).strip()
        named = re.search(r"\{([^}]*)\}", clause)
        head = clause.split("{")[0].strip().rstrip(",").strip()
        if head.startswith("* as "):
            bound[head[5:].strip()] = (module, "*")
        elif head and _IDENT.match(head):
            bound[head] = (module, "default")
        if named:
            for exported, local in _parts(named.group(1)):
                bound[local] = (module, "default" if exported == "default" else exported)
    for m in _DYN.finditer(text):
        if not LOCAL_SPEC.match(m.group(3)):
            continue
        module = mod_of(m.group(3))
        if m.group(1):
            bound[m.group(1)] = (module, "*")
        else:
            for exported, local in _parts(m.group(2).replace(":", " as ")):
                bound[local] = (module, exported)
    reexports: List[Tuple[int, str, str, str]] = []
    for m in _REEXPORT.finditer(text):
        if not LOCAL_SPEC.match(m.group(3)):
            continue
        module = mod_of(m.group(3))
        if m.group(1) is not None:
            for name, alias in _parts(m.group(1)):
                reexports.append((m.start(), alias, module, name))
        else:
            reexports.append((m.start(), m.group(2) or "*", module, "*"))
    return bound, reexports


_REGEX = re.compile(r"""(^|[(,=:\[!&|?{};]\s*)(/(?![/*])(?:[^/\n\\\[]|\\.|\[(?:[^\]\n\\]|\\.)*\])+/[gimsuy]*)""", re.M)


def _blank(m: "re.Match") -> str:
    return m.group(0)[0] + " " * (len(m.group(0)) - 2) + m.group(0)[-1] if len(m.group(0)) > 1 else m.group(0)


def _masked(text: str) -> str:
    """`text` with string and regex-literal contents blanked (same length): neither is a use."""
    text = _STR.sub(_blank, text)
    return _REGEX.sub(lambda m: m.group(1) + " " * len(m.group(2)), text)


def _spans(text: str, pattern: "re.Pattern") -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


def _inside(pos: int, spans: Sequence[Tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


def module_uses(src: Source, decls: List[Dict], primary: str, mod_of, template: Optional[Source] = None) -> List[Dict]:
    """Rows {line, from, kind call|ref, webmod, webexp, webname, weblocal, [reexport_as], [fqn]}."""
    bound, reexports = bindings(src.text, mod_of)
    out: List[Dict] = []

    def owner(line: int) -> str:
        best = None
        for d in decls:
            if d["kind"] == "method" and d["line"] <= line <= d["end"] and \
                    (best is None or d["end"] - d["line"] < best["end"] - best["line"]):
                best = d
        return primary if best is None else (best.get("fqn") or primary + "." + (best["cls"] + "." if best["cls"] else "") + best["name"])

    for offset, alias, module, name in reexports:
        out.append({"line": src.line_of(offset), "from": primary, "kind": "ref", "webmod": module, "webexp": name,
                    "webname": None, "weblocal": alias, "reexport_as": alias})

    text = _masked(src.text)
    stmt = _spans(src.text, _IMPORT) + _spans(src.text, _REEXPORT) + _spans(src.text, _DYN)

    def emit(source: Source, offset: int, local: str, member: Optional[str], kind: str) -> None:
        module, exported = bound[local]
        line = source.line_of(offset)
        out.append({"line": line, "from": owner(line) if source is src else primary, "kind": kind, "webmod": module,
                    "webexp": exported, "webname": member, "weblocal": local})

    def scan(source: Source, body: str, in_template: bool) -> None:
        for local in bound:
            exported = bound[local][1]
            esc = re.escape(local)
            taken = set()
            for m in re.finditer(r"(?<![\w$.])%s\s*\.\s*([A-Za-z_$][\w$]*)\s*\(" % esc, body):
                if not in_template and _inside(m.start(), stmt):
                    continue
                emit(source, m.start(), local, m.group(1), "call")
                taken.add(m.start())
            if exported == "*":
                continue                                    # a namespace is only used through its members
            for m in re.finditer(r"(?<![\w$.])%s(?![\w$])" % esc, body):
                if m.start() in taken or (not in_template and _inside(m.start(), stmt)):
                    continue
                before = body[max(0, m.start() - 12):m.start()].rstrip().split(" ")[-1].split("\n")[-1]
                after = body[m.end():m.end() + 24].lstrip()
                if before in _NOT_REF_BEFORE or (after.startswith(":") and not after.startswith("::")
                                                 and body[:m.start()].rstrip()[-1:] in ("{", ",")):
                    continue
                emit(source, m.start(), local, None, "call" if after.startswith("(") else "ref")

    if bound:
        scan(src, text, False)
        if template is not None:
            # an expression: `:prop="e"`, `@ev="e"`, `v-dir="e"`, `{{ e }}`; a plain `hint="text"` is text
            attr = re.compile(r"""(?<![\w$-])(?:[:@#]|v-)[\w.:@#\[\]-]*\s*=\s*"([^"]*)"|(?<![\w$-])(?:[:@#]|v-)[\w.:@#\[\]-]*\s*=\s*'([^']*)'|\{\{(.*?)\}\}""", re.S)
            for m in attr.finditer(template.text):
                seg = m.group(m.lastindex or 0) if m.lastindex else ""
                base = m.start(m.lastindex) if m.lastindex else m.start()
                for local in bound:
                    for t in re.finditer(r"(?<![\w$.-])%s(?![\w$-])" % re.escape(local), seg):
                        if bound[local][1] == "*" and not re.match(r"\s*\.", seg[t.end():]):
                            continue
                        member = re.match(r"\s*\.\s*([A-Za-z_$][\w$]*)\s*\(", seg[t.end():])
                        emit(template, base + t.start(), local, member.group(1) if member else None,
                             "call" if member or re.match(r"\s*\(", seg[t.end():]) else "ref")
            for local, (_, exported) in bound.items():
                if exported == "*" or not local[:1].isupper():
                    continue
                kebab = re.sub(r"(?<!^)([A-Z])", r"-\1", local).lower()
                for t in re.finditer(r"</?(?:%s|%s)(?![\w-])" % (re.escape(local), re.escape(kebab)), template.text):
                    emit(template, t.start(), local, None, "ref")
    # a top-level function calling itself or a sibling in the same file
    for d in decls:
        if d["kind"] != "method" or d.get("cls") or not d.get("fqn") or not _IDENT.match(d["name"]):
            continue
        for m in re.finditer(r"(?<![\w$.])%s\s*\(" % re.escape(d["name"]), text):
            line = src.line_of(m.start())
            if line == d["line"] or text[max(0, m.start() - 9):m.start()].strip().endswith(("function", "new")):
                continue
            out.append({"line": line, "from": owner(line), "kind": "call", "fqn": d["fqn"], "local": True})
    return out
