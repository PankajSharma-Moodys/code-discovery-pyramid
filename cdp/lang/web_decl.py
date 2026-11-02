"""Declarations of a JS/TS file: top level and members of top-level classes only.

Locals inside function bodies are not symbols (810 of the 1189 `const` lines in workflow-ui
were locals). Uses the nesting from `web_scan.scan`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

DECL_RE = re.compile(
    r"^\s*(export\s+(?:default\s+)?)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(class|interface|enum|type|function\*?|const|let|var)\s+(?:enum\s+)?"
    r"([A-Za-z_$][\w$]*)"
)
MEMBER_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|static|readonly|abstract|override|async|declare|get|set)\s+)*"
    r"\*?\s*(#?[A-Za-z_$][\w$]*)\s*[?!]?\s*(<[^>(]*>)?\s*(\(|=|:|;|$)"
)
_MODS = re.compile(r"\b(private|protected)\b")
_NOT_MEMBER = {"if", "for", "while", "switch", "return", "catch", "else", "do", "try", "import", "export"}
_CONT = ("+", ".", ")", "}", "]", "?", ":", "&&", "||", ",", "=", "*", "-", "/", "<", ">", "|", "??")
_ARROW = re.compile(
    r"=\s*(?:async\s+)?(?:\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)|[\w$]+)\s*(?::\s*[^=]+?)?=>|"
    r"=\s*(?:async\s+)?function\b|=\s*(?:React\.)?(?:memo|forwardRef|lazy)\s*\("
)
_STR_VALUE = re.compile(r"""=\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`([^`$\\]*)`)\s*;?\s*$""")


def _extent(code: Sequence[str], stacks: Sequence[Tuple[str, ...]], i: int, base: int) -> int:
    end = i
    for k in range(i + 1, len(code)):
        text = code[k].strip()
        if not text:
            continue
        if len(stacks[k]) < base or (len(stacks[k]) == base and not text.startswith(_CONT)):
            break
        end = k
    return end


def declarations(code: Sequence[str], stacks: Sequence[Tuple[str, ...]]) -> List[Dict]:
    out: List[Dict] = []
    cls_name: Optional[str] = None
    cls_end = -1
    for i, line in enumerate(code):
        depth = stacks[i]
        if cls_name is not None and i > cls_end:
            cls_name = None
        if not depth:
            m = DECL_RE.match(line)
            if not m:
                continue
            kw, name = m.group(2).rstrip("*"), m.group(3)
            end = _extent(code, stacks, i, 0)
            body = " ".join(code[i:min(end, i + 40) + 1])
            kind = {"function": "method", "const": "constant", "let": "field", "var": "field",
                    "type": "class"}.get(kw, kw)
            value = None
            if kw in ("const", "let", "var"):
                head = body[body.find(name) + len(name):]
                rhs = head[head.find("="):] if "=" in head else ""
                if _ARROW.match(rhs):
                    kind = "method"
                elif kw == "const":
                    sv = _STR_VALUE.match(rhs)
                    if sv:
                        value = next(g for g in sv.groups() if g is not None)
            out.append({"name": name, "kind": kind, "vis": "public" if m.group(1) else "internal",
                        "line": i, "end": end, "value": value, "cls": None,
                        "export": bool(m.group(1))})
            if kw == "class":
                cls_name, cls_end = name, end
        elif depth == ("c",) and cls_name is not None:
            text = line.strip()
            if not text or text.startswith(("@", "}", "//")):
                continue
            m = MEMBER_RE.match(line)
            if not m or m.group(1) in _NOT_MEMBER:
                continue
            name, follow = m.group(1), m.group(3)
            end = _extent(code, stacks, i, 1)
            kind = "method" if follow == "(" else "field"
            if follow == "=":
                body = " ".join(code[i:min(end, i + 40) + 1])
                if _ARROW.search(body[body.find("="):] if "=" in body else ""):
                    kind = "method"
            mod = _MODS.search(line.split(name, 1)[0])
            vis = "private" if name.startswith("#") or (mod and mod.group(1) == "private") else \
                "protected" if mod else "public"
            out.append({"name": name, "kind": kind, "vis": vis, "line": i, "end": end,
                        "value": None, "cls": cls_name, "export": False})
    return out


_ACCESSOR = re.compile(r"^\s*(?:(?:public|private|protected|static|readonly|override|declare)\s+)*accessor\s+(#?[\w$]+)")
_EXT_LANG = {"ts": "typescript", "mts": "typescript", "cts": "typescript", "tsx": "tsx"}


def tool_rows(ctx, language: str, primary: str) -> Optional[List[Dict]]:
    """Define rows from the tree-sitter rules (cdp.ts), or None to use the hand scanner (switch off, grammar missing,
    or a file that failed to parse at all). Free functions are `<module>#<name>` (D1)."""
    from cdp import ts
    if not ts.enabled(language):
        return None
    lang = _EXT_LANG.get(ctx.path.rsplit(".", 1)[-1].lower(), language)
    res = ts.extract_ex(lang, ctx.path, "\n".join(ctx.lines), primary)
    if res is None:
        return None
    rows, meta = res
    if (meta.get("has_error") and not rows) or "crash" in meta or "error" in meta:
        return None
    top = primary + "."
    for r in rows:
        if r["fqn"].endswith(".accessor"):             # grammar 0.23.2 reads `static accessor x` as a field named accessor
            m = _ACCESSOR.match(ctx.lines[r["anchor"]["line"] - 1])
            if m:
                r["fqn"] = r["fqn"][:-len("accessor")] + m.group(1)
        f = r["fqn"]
        if r["kind"] == "function" and f.startswith(top) and "#" not in f[len(top):] and "." not in f[len(top):]:
            r["fqn"] = primary + "#" + f[len(top):]
    return rows


def flow_decls(rows: List[Dict], primary: str) -> List[Dict]:
    """Rows -> the declaration dicts the flow code reads (name, cls, kind method|..., line, end, value, fqn)."""
    out = []
    for r in rows:
        f = r["fqn"]
        rest = f[len(primary) + 1:] if f.startswith(primary) else f
        head, sep, name = rest.replace("#", "\0").rpartition("\0") if "#" in rest else rest.rpartition(".")
        cls = head.replace("\0", "#") or None
        out.append({"name": name or rest, "kind": "method" if r["kind"] in ("function", "method") else r["kind"],
                    "line": r["anchor"]["line"] - 1, "end": r["end_line"] - 1, "value": r.get("value"), "cls": cls,
                    "export": r["visibility"] == "public", "fqn": f})
    return out
