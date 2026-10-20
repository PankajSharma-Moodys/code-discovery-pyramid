"""Grounded-diagram checker: parse a Mermaid `flowchart`/`stateDiagram`, pull each edge's
`file:line` citation off its label, and check it against the repo (`cdp verify-diagram`).

Stdlib only, no store read. A citation resolves by repo-unique path suffix over `git ls-files`
(module hints such as `scheduler-core` and file names spelled out elsewhere in the diagram narrow
it). The cited line must exist, and the cited line +-3 must hold one of the edge's claimed tokens
(callee, state name, label words) on a line that is neither a comment nor that token's own
declaration. Per edge:

- correct: every cited site shows a claimed token.
- wrong_citation: the file/line does not exist, or the token is in the file but not at the site
  (a declaration, a doc comment, a generic line); `hint` names the nearest real site.
- unsupported: no claimed token anywhere in the cited file.
- ambiguous: the path matches several files.
- uncited: no citation on the edge (a citation on a node does not count).
- inferred: a dashed (`-.->`) or `?`-labelled edge with no citation; honest, not a failure.

Generalised from the hand grader used in RESEARCH_DIAGRAM_TEST.md.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Dict, List, Optional, Sequence, Tuple

EXTS = ("scala", "sc", "java", "kts", "kt", "cs", "py", "go", "tsx", "ts", "jsx", "js", "mjs",
        "sql", "rb", "rs", "php", "cpp", "hpp", "cc", "c", "h", "swift", "m", "groovy", "gradle",
        "xml", "yml", "yaml", "conf", "json", "properties", "proto", "tf", "sh", "toml", "ini",
        "fs", "vb", "lua", "dart", "ex", "exs", "erl", "clj", "hs", "ml", "r", "pl", "cshtml", "razor")
_EXT = "|".join(sorted(EXTS, key=len, reverse=True))
CITE = re.compile(
    r"(?:(?P<file>(?<![\w/.-])[A-Za-z_][\w./-]*\.(?:%s))|(?<![\w:/]))"
    r":(?P<a>\d+)(?:\s*-\s*(?P<b>\d+))?(?P<more>(?:\s*,\s*:?\d+(?:\s*-\s*\d+)?(?![\w.]))*)" % _EXT)
WINDOW = 3
STATUSES = ("correct", "wrong_citation", "unsupported", "ambiguous", "uncited", "inferred")
FAILING = frozenset(("wrong_citation", "unsupported", "ambiguous", "uncited"))

STOP = frozenset("""
a an the and or of to in on at by for with from into via as is are be if else then than this that
not no only found traced verified unverified inferred documented further shown call calls called
return returns new set get per each all any one two when while after before also both same
true false null none path flow edge edges node state states start end initial ok success
""".split())

_HEADER = re.compile(r"^(flowchart|graph)\b|^stateDiagram(-v2)?\b")
_SKIP_FLOW = re.compile(r"^(%%|classDef\b|class\b|style\b|linkStyle\b|subgraph\b|end\b|click\b|direction\b)")
_SHAPE = (r'\(\[.*?\]\)|\[\(.*?\)\]|\(\(.*?\)\)|\[\[.*?\]\]|\{\{.*?\}\}|\[/.*?/\]|\[\\.*?\\\]'
          r'|\["(?:[^"\\]|\\.)*"\]|\("(?:[^"\\]|\\.)*"\)|\{"(?:[^"\\]|\\.)*"\}'
          r'|\[[^\]]*\]|\((?:[^()]|\([^()]*\))*\)|\{[^}]*\}|>[^\]]*\]')
_NODE = re.compile(r"\s*(?P<id>\w+)\s*(?P<shape>%s)?\s*(?=$|&|-|=|~|\.|<|o\b|x\b)" % _SHAPE)
_LINK = re.compile(
    r'\s*(?:(?P<op1>--|==|-\.)\s*(?P<txt>"[^"]*"|[^"|>\-=.][^>|]*?)\s*(?P<op2>-->|==>|\.->|---|-\.-|\.-)'
    r'|(?P<op><?-{2,}>|<?={2,}>|<?-\.+->|-{3,}|-\.+-|~~~|--[ox]|==[ox])'
    r'(?:\s*\|(?P<pipe>[^|]*)\|)?)')
_STATE_EDGE = re.compile(r"^(?P<a>\[\*\]|[\w.]+)\s*-->\s*(?P<b>\[\*\]|[\w.]+)\s*(?::\s*(?P<lab>.*))?$")
_COMMENT = re.compile(r"^\s*(//|/\*|\*|#(?!region|endregion|if|else|elif|endif|define|pragma)|--|<!--|\"\"\"|''')")


class DiagramError(ValueError):
    """The text is not a Mermaid flowchart or stateDiagram this checker understands."""


# ---------------------------------------------------------------------------- parsing


def split_fences(text: str) -> List[str]:
    """Each ```mermaid fence of a markdown answer, or the whole text when it has none."""
    fences = re.findall(r"```\s*mermaid[^\n]*\n(.*?)```", text, re.S)
    return fences or [text]


def _clean_label(text: str) -> str:
    text = (text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1]
    return re.sub(r"<br\s*/?>|<[^>]+>|&\w+;", " ", text).strip()


def _shape_text(shape: Optional[str]) -> str:
    if not shape:
        return ""
    return _clean_label(shape.strip("[](){}<>/\\"))


def parse(text: str) -> Dict:
    """`{"kind", "edges": [{from, to, label, dashed, line}], "nodes": {id: label}, "errors"}`.
    Raises `DiagramError` when there is no recognisable header."""
    lines = text.splitlines()
    body = [(i + 1, ln.strip()) for i, ln in enumerate(lines)]
    body = [(n, s) for n, s in body if s and not s.startswith("%%") and not s.startswith("---")]
    if body and body[0][1].startswith("title"):
        body = body[1:]
    if not body or not _HEADER.match(body[0][1]):
        raise DiagramError("not a Mermaid flowchart/stateDiagram: first line is %r"
                           % (body[0][1][:60] if body else ""))
    kind = "state" if body[0][1].startswith("stateDiagram") else "flowchart"
    out = {"kind": kind, "edges": [], "nodes": {}, "errors": []}
    (_parse_state if kind == "state" else _parse_flow)(body[1:], out)
    return out


def _parse_state(body, out) -> None:
    in_note = False
    for n, s in body:
        if in_note:
            in_note = not s.startswith("end note")
            continue
        if s.startswith("note "):
            head, sep, rest = s.partition(":")
            if not sep:
                in_note = True
            elif ":" in rest:
                out["errors"].append("line %d: one-line note with a second ':' breaks the Mermaid "
                                     "parser; use block form (note ... end note)" % n)
            continue
        m = _STATE_EDGE.match(s)
        if m:
            out["edges"].append({"from": m["a"], "to": m["b"], "label": _clean_label(m["lab"]),
                                 "dashed": False, "line": n})
            continue
        m = re.match(r'state\s+"([^"]*)"\s+as\s+(\w+)', s) or re.match(r"(\w+)\s*:\s*(.*)$", s)
        if m:
            sid, desc = (m[2], m[1]) if s.startswith("state") else (m[1], m[2])
            out["nodes"][sid] = _clean_label(desc)


def _parse_flow(body, out) -> None:
    for n, s in body:
        if _SKIP_FLOW.match(s):
            continue
        _parse_flow_stmt(s.rstrip(";").strip(), n, out)


def _parse_flow_stmt(s: str, n: int, out) -> None:
    pos, prev, nodes = 0, None, out["nodes"]
    while pos < len(s):
        m = _NODE.match(s, pos)
        if not m or not m["id"]:
            return
        nid = m["id"]
        if m["shape"]:
            nodes[nid] = _shape_text(m["shape"])
        else:
            nodes.setdefault(nid, "")
        if prev is not None:
            out["edges"].append(dict(prev, to=nid))
        pos = m.end()
        while pos < len(s) and s[pos] in " &":   # `A & B --> C`: keep the last source only
            pos += 1
        lm = _LINK.match(s, pos)
        if not lm:
            return
        op = lm["op"] or (lm["op1"] + lm["op2"])
        label = lm["pipe"] if lm["op"] else lm["txt"]
        prev = {"from": nid, "label": _clean_label(label), "dashed": "." in op, "line": n}
        pos = lm.end()


# ---------------------------------------------------------------------------- citations


def find_cites(label: str, last: Optional[str]) -> Tuple[List[Dict], Optional[str]]:
    """Every `file:line[-line][, line]` in an edge label. A bare `:123` reuses the last file
    named in the diagram. Words with a `-` just before a cite are path hints (`scheduler-core`)."""
    cites = []
    for m in CITE.finditer(label):
        path = m["file"] or last
        if not path:
            continue
        last = path
        a = int(m["a"])
        spans = [(a, int(m["b"]) if m["b"] else a)]
        for part in re.findall(r"\d+(?:\s*-\s*\d+)?", m["more"] or ""):
            lo, _, hi = part.partition("-")
            spans.append((int(lo), int(hi or lo)))
        hints = [t for t in re.findall(r"[\w-]+", label[max(0, m.start() - 40):m.start()])
                 if "-" in t.strip("-")]
        cites.append({"text": m.group(0).strip(), "path": path, "spans": spans, "hints": hints})
    return cites, last


def strip_cites(label: str) -> str:
    return CITE.sub(" ", label)


def repo_files(repo: str) -> List[str]:
    try:
        r = subprocess.run(["git", "-C", repo, "ls-files", "--cached", "--others", "--exclude-standard"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return r.stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        pass
    found = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        found.extend(os.path.relpath(os.path.join(root, f), repo) for f in names)
    return found


def _is_test(f: str) -> bool:
    b = os.path.basename(f)
    return bool(re.search(r"(^|/)(test|tests|spec|__tests__)/", f) or re.search(
        r"(Tests?|Spec)\.\w+$|^test_|_test\.\w+$|\.(test|spec)\.\w+$", b))


def resolve(path: str, hints: Sequence[str], files: Sequence[str], context: str) -> List[str]:
    """Candidates for a cited path: exact path suffix first, then basename suffix (an
    abbreviation such as `Handler.cs`), narrowed by module hints, non-test files and file
    stems the diagram spells out elsewhere."""
    p = path.lstrip("./")
    if "/.../" in p:   # `scheduler-core/.../Foo.scala`: head dirs, then any depth, then the tail
        head, _, tail = p.partition("/.../")
        c = [f for f in files if (f == tail or f.endswith("/" + tail))
             and re.search(r"(^|/)%s/" % re.escape(head), f[:len(f) - len(tail)])]
    else:
        c = [f for f in files if f == p or f.endswith("/" + p)]
    if not c and "/" not in p and "..." not in p:
        c = [f for f in files if os.path.basename(f).endswith(p)]
    if len(c) > 1 and hints:
        c = [f for f in c if all(h in f for h in hints)] or c
    if len(c) > 1:
        c = [f for f in c if not _is_test(f)] or c
    if len(c) > 1:
        named = [f for f in c if re.search(r"(?<![\w.])%s(?![\w])" % re.escape(
            os.path.splitext(os.path.basename(f))[0]), context)]
        c = named or c
    return c


# ---------------------------------------------------------------------------- tokens


def _words(text: str):
    """(identifier-like, plain) words of a label: camelCase, snake_case, dotted, ALLCAPS vs. rest.
    Hyphenated module hints (`scheduler-core`) are not claims."""
    strong, weak = [], []
    text = re.sub(r"[\w]+(?:-[\w]+)+", " ", strip_cites(text))
    text = re.sub(r"[\w./-]*[\w-]\.(?:%s)\b(?::\d+)?" % _EXT, " ", text)   # a path is not an identifier
    text = re.sub(r"\b\w+(?:/\w+)+/?", " ", text)
    for raw in re.findall(r"[A-Za-z_][\w.#]*", text):
        parts = [x for x in re.split(r"[.#]", raw) if x]
        for w in parts:
            if w.lower() in STOP or len(w) < 3:
                continue
            ident = len(parts) > 1 or "_" in w or any(ch.isdigit() for ch in w) or \
                (w[0].islower() and any(ch.isupper() for ch in w)) or sum(ch.isupper() for ch in w) >= 2
            if ident:
                strong.append(w)
            elif len(w) >= 4:
                weak.append(w)
    return strong, weak


def claimed_tokens(edge: Dict, nodes: Dict[str, str], kind: str) -> List[str]:
    """What the cited site must show (any one of). Flowchart: every label word, plus the
    target node's identifiers (its plain words only when nothing else). State diagram: the
    target state (the source for `X --> [*]`) and the label's identifiers -- a plain word such
    as `reconcile` names a mechanism, not the transition."""
    strong, weak = _words(edge["label"])
    calls = re.findall(r"([A-Za-z_][\w.#]*)\s*\(", strip_cites(edge["label"]))
    if calls and kind != "state":   # `ship(order) · f:1`: the callee is the claim, `order` is an argument
        strong, weak = _words(" ".join(calls))
    if kind == "state":
        sid = edge["to"] if edge["to"] != "[*]" else edge["from"]
        toks = strong + ([sid] if sid != "[*]" else [])
        if "_" in sid and not sid.isupper():
            toks.extend(p for p in sid.split("_") if len(p) >= 3)
    else:
        toks = strong + weak
        n_strong, n_weak = _words(nodes.get(edge["to"], ""))
        toks += n_strong or ([] if toks else n_weak)
        tgt = edge["to"]
        if not nodes.get(tgt) and len(tgt) >= 3 and (tgt.isupper() or tgt[:1].isupper()):
            toks.append(tgt)   # a bare-id lifecycle edge (`QUEUED --> PENDING`): the target state is the claim
    seen, out = set(), []
    for w in toks:
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


def _core(tok: str) -> str:
    """Regex for one token. ALLCAPS matches whole; a lowercase word by stem (`registered` ~
    `register`); a mixed-case identifier as a prefix (`GetEdmByName` ~ `GetEdmByNameAsync`),
    an interface name also as its field (`IEdmRepository` ~ `_edmRepository`)."""
    if tok.isupper():
        return r"%s(?![A-Za-z0-9_])" % re.escape(tok)
    if tok.islower():
        return re.escape(re.sub(r"(ing|ed|es|s)$", "", tok) if len(tok) > 5 else tok) + r"\w*"
    alts = [re.escape(tok)]
    if re.match(r"I[A-Z][a-z]", tok):
        alts.append(re.escape(tok[1:]))
    return r"(?:%s)\w*" % "|".join(alts)


def _hit(code: str, tok: str) -> bool:
    """`tok` on this code line; a Capitalised token also as a camelCase hump
    (`Passive` in `MakePassiveAsync`, `PendingDelete` in `ListInstancesPendingDeleteAsync`)."""
    if re.search(r"(?<![A-Za-z0-9])_?" + _core(tok), code, re.I):
        return True
    return tok[:1].isupper() and not tok.isupper() and \
        bool(re.search(r"(?<=[a-z0-9])%s(?![a-z])" % re.escape(tok), code))


_MODS = (r"(?:public|private|protected|internal|static|async|override|final|virtual|abstract|sealed|"
         r"synchronized|partial|extern|unsafe|open|suspend|inline|implicit|lazy)")
_SIGNATURE = re.compile(
    r"\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:%s\s+)+[\w<>\[\],.?\s]*?\b\w+\s*(?:<[^>]*>)?\s*\("
    r"|(?:%s\s+)*(?:def|fun|func|function)\s+\w+)" % (_MODS, _MODS))


def _decl(line: str, tok: str) -> bool:
    """Is `tok` declared (not used) on this line: a def/class/enum keyword before it, a
    modifier-led method signature, or a bare enum member line."""
    t = _core(tok)
    return bool(
        re.search(r"\b(def|fun|func|function|class|object|trait|interface|enum|struct|record|"
                  r"type|module|case\s+object|case\s+class|procedure|table)\s+%s" % t, line, re.I)
        or re.match(r"\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|private|protected|internal|static|"
                    r"async|override|final|virtual|abstract|sealed|synchronized|partial|extern|"
                    r"unsafe|open|suspend|inline)\s+)+[\w<>\[\],.?\s]*?\b%s\s*[(<]" % t, line)
        or re.search(r"\b(val|var|let|const|lazy\s+val)\s+%s\b" % t, line)
        or re.match(r"\s*(?:%s\s+)+[\w<>\[\],.?\s]*?\b%s\s*(?:=(?!=)|;)" % (_MODS, t), line)
        or (tok[:1].isupper() and re.match(
            r"\s*%s\s*(?:\([^)]*\))?\s*(?:=\s*[^,;=]+)?\s*[,;]?\s*(?://.*)?$" % t, line)))


def _code(line: str) -> str:
    """The line with a trailing `//` or `--` comment removed; "" for a comment line."""
    if _COMMENT.match(line):
        return ""
    return re.sub(r"(?<![:\"'\w])\s(//|--\s).*$", "", line)


def _uses(line: str, toks: Sequence[str], decl_ok: bool = False,
          states: Sequence[str] = ()) -> List[str]:
    """The tokens this line uses: not in a comment, not a token's own declaration (unless
    `decl_ok`: a cited range that spans the definition the edge names), not a bare method
    signature, and not a generic line naming 3+ of the diagram's states (`Set(A, B, C)`)."""
    code = _code(line)
    if code and not decl_ok and _SIGNATURE.match(code):
        body = re.search(r"\)[^{=]*(?:\{|=>|=)(.*)$", code)
        code = body.group(1) if body else ""   # a signature shows where a call lands, not the call
    if not code.strip():
        return []
    if states and sum(1 for st in states if re.search(r"\b%s\b" % re.escape(st), code)) >= 3:
        return []
    return [t for t in toks if _hit(code, t) and (decl_ok or not _decl(code, t))]


# ---------------------------------------------------------------------------- grading


class Repo:
    def __init__(self, root: str) -> None:
        self.root = root
        self.files = repo_files(root)
        self._cache: Dict[str, List[str]] = {}

    def lines(self, rel: str) -> List[str]:
        if rel not in self._cache:
            try:
                with open(os.path.join(self.root, rel), encoding="utf-8", errors="replace") as fh:
                    self._cache[rel] = fh.read().splitlines()
            except OSError:
                self._cache[rel] = []
        return self._cache[rel]


def _site_check(lines: List[str], spans, toks, states) -> List[Tuple[int, int]]:
    """The spans whose +-WINDOW lines show none of `toks` (empty: every span is supported)."""
    missing = []
    for lo, hi in spans:
        window = range(max(1, lo - WINDOW), min(len(lines), hi + WINDOW) + 1)
        if not any(_uses(lines[k - 1], toks, lo < hi and lo <= k <= hi, states) for k in window):
            missing.append((lo, hi))
    return missing


def _fits(lines: List[str], spans) -> bool:
    return all(1 <= lo <= hi <= len(lines) for lo, hi in spans)


def _check_cite(cite: Dict, toks: List[str], repo: Repo, context: str, states=()) -> Dict:
    """One citation: resolved file, then line range, then a claimed token at the site.
    A cite with several lines (`:431,498,519`) is supported when any of them is."""
    out = {"text": cite["text"], "path": cite["path"], "file": None, "status": "", "detail": ""}
    spans = cite["spans"]
    cands = resolve(cite["path"], cite["hints"], repo.files, context)
    if not cands:
        out.update(status="wrong_citation", detail="no file matches %s" % cite["path"])
        return out
    if len(cands) > 1:
        out.update(status="ambiguous", candidates=cands[:5],
                   detail="%d files match %s; use a repo-unique path" % (len(cands), cite["path"]))
        shows = [f for f in cands if toks and _fits(repo.lines(f), spans)
                 and len(_site_check(repo.lines(f), spans, toks, states)) < len(spans)]
        if len(shows) == 1:
            out["hint"] = "%s:%d" % (shows[0], spans[0][0])
            out["detail"] += " (only %s shows the edge there)" % shows[0]
        return out
    rel = out["file"] = cands[0]
    lines = repo.lines(rel)
    if not _fits(lines, spans):
        out.update(status="wrong_citation", detail="%s has %d lines, cited %s"
                   % (rel, len(lines), cite["text"].rpartition(":")[2]))
        return out
    if not toks:
        out.update(status="unsupported", detail="the edge names nothing checkable; label it with the call")
        return out
    missing = _site_check(lines, spans, toks, states)
    if len(missing) < len(spans):
        out["status"] = "correct"
        return out
    lo = missing[0][0]
    sites = [(len(_uses(ln, toks, False, states)), k + 1) for k, ln in enumerate(lines)]
    sites = [(n, k) for n, k in sites if n]
    if sites:
        best = max(sites, key=lambda nk: (nk[0], -abs(nk[1] - lo)))[1]
        out.update(status="wrong_citation", hint="%s:%d" % (rel, best),
                   detail="no %s at :%d+-%d (declaration, comment or generic line); nearest use :%d"
                   % ("/".join(toks[:3]), lo, WINDOW, best))
    else:
        out.update(status="unsupported", detail="no %s anywhere in %s outside comments/declarations"
                   % ("/".join(toks[:3]), rel))
    return out


_RANK = {"wrong_citation": 4, "unsupported": 3, "ambiguous": 2, "correct": 0}


def grade(text: str, repo: Repo) -> List[Dict]:
    """Grade every diagram in `text` (a .mmd or a markdown answer with mermaid fences)."""
    results = []
    for src in split_fences(text):
        d = parse(src)
        last, edges = None, []
        states = sorted({x for e in d["edges"] for x in (e["from"], e["to"]) if x != "[*]"}) \
            if d["kind"] == "state" else []
        for e in d["edges"]:
            if not e["label"] and "[*]" in (e["from"], e["to"]):
                continue   # bare start/end marker claims nothing
            cites, last = find_cites(e["label"], last)
            toks = claimed_tokens(e, d["nodes"], d["kind"])
            inferred = e["dashed"] or e["label"].lstrip().startswith("?")
            row = {"id": "E%d" % (len(edges) + 1), "from": e["from"], "to": e["to"],
                   "label": e["label"], "line": e["line"], "dashed": e["dashed"],
                   "inferred": inferred, "tokens": toks, "cites": []}
            if not cites:
                row["status"] = "inferred" if inferred else "uncited"
            else:
                row["cites"] = [_check_cite(c, toks, repo, src, states) for c in cites]
                sts = [c["status"] for c in row["cites"]]
                broken = any(c["status"] == "wrong_citation" and not c.get("hint") for c in row["cites"])
                row["status"] = "correct" if "correct" in sts and not broken else \
                    max(sts, key=lambda s: _RANK[s])
            edges.append(row)
        counts = {s: sum(1 for e in edges if e["status"] == s) for s in STATUSES}
        results.append({"kind": d["kind"], "errors": d["errors"], "edges": edges, "counts": counts})
    return results


def summarize(results: List[Dict]) -> Dict[str, int]:
    return {s: sum(r["counts"][s] for r in results) for s in STATUSES}


def exit_code(results: List[Dict]) -> int:
    if any(r["errors"] for r in results):
        return 1
    return 3 if any(e["status"] in FAILING for r in results for e in r["edges"]) else 0
