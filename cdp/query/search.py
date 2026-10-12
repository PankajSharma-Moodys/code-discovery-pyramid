"""Search, claims, unknowns and conflicts."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .. import codeindex
from ..util import truncate
from .budget import Budget
from .common import ann_at, cite, squash, _claim_module, _fair_split_budget, _finish, _matches, _role_index, _search_rank_key
from .store import Store


SEARCHED = ("claim subjects and statements, symbol names, constant values, annotations (name, fqn, text), "
            "unknown questions, file paths, source text of source-role files (code: case-insensitive "
            "substring, one line at a time, cited to the enclosing member)")


def q_search(store: Store, text: str, budget: Optional[Budget] = None,
             exclude_role: Optional[Sequence[str]] = None) -> Dict:
    budget = budget or Budget()
    claims = [
        c for c in store.state["claims"]
        if _matches(c.get("subject", ""), text) or _matches(c.get("statement", ""), text)
    ]
    symbols = sorted(
        (k for k in store.xref["symbols"] if _matches(k, text)),
        key=lambda s: _search_rank_key(s, text),
    )
    unknowns = [u for u in store.state["unknowns"] if _matches(u.get("question", ""), text)]
    # A constant is found by its value too (`"X-Request-Id"`), not only its name.
    named = set(symbols)
    constants = sorted(
        ("%s = %s  %s" % (k, e["value"], cite(e["sites"][0]["anchor"]) if e["sites"] else "-")
         for k, e in store.xref["symbols"].items()
         if k not in named and e.get("value") is not None and _matches(e["value"], text)),
    )
    annotations = _annotation_hits(store, text, exclude_role)
    code = _code_hits(store, text, exclude_role)
    files = sorted(
        (
            f["path"] for f in store.inventory["files"]
            if _matches(f["path"], text) and not (exclude_role and f["role"] in exclude_role)
        ),
        key=lambda f: _search_rank_key(f, text),
    )
    # Fair-split, not a single shared budget spent in construction order --
    # see `_fair_split_budget`'s docstring for the real-repo failure mode
    # this replaced.
    (claims_room, symbols_room, unknowns_room, files_room, constants_room, annotations_room,
     code_room) = _fair_split_budget(
        budget.limit,
        [len(claims), len(symbols), len(unknowns), len(files), len(constants), len(annotations), len(code)]
    )
    code_budget = Budget(code_room)
    kept_code = code_budget.take(code)
    annotations_budget = Budget(annotations_room)
    kept_annotations = annotations_budget.take(annotations)
    constants_budget = Budget(constants_room)
    kept_constants = constants_budget.take(constants)
    claims_budget = Budget(claims_room)
    symbols_budget = Budget(symbols_room)
    unknowns_budget = Budget(unknowns_room)
    files_budget = Budget(files_room)
    kept_claims = claims_budget.take(claims)
    kept_symbols = symbols_budget.take(symbols)
    kept_unknowns = unknowns_budget.take(unknowns)
    kept_files = files_budget.take(files)
    budget.spent = (
        claims_budget.spent + symbols_budget.spent
        + unknowns_budget.spent + files_budget.spent + constants_budget.spent + annotations_budget.spent + code_budget.spent
    )
    budget.elided = (
        claims_budget.elided + symbols_budget.elided
        + unknowns_budget.elided + files_budget.elided + constants_budget.elided + annotations_budget.elided + code_budget.elided
    )
    result = _finish(
        {
            "query": "search",
            "text": text,
            "counts": {
                "claims": len(claims), "symbols": len(symbols),
                "unknowns": len(unknowns), "files": len(files),
                "constants": len(constants), "annotations": len(annotations), "code": len(code),
            },
            "searched": SEARCHED,
            "not_searched": ("source text of files that are not source-role (tests, config, docs, assets), "
                             "binary, over-size or generated files, and anything that spans two lines"),
            "claims": kept_claims,
            "symbols": kept_symbols,
            "unknowns": kept_unknowns,
            "files": kept_files,
            "constants": kept_constants,
            "annotations": kept_annotations,
            "code": kept_code,
        },
        store,
        budget,
    )
    note = _code_note(result["as_of"])
    if note:
        result["as_of"]["code_note"] = note
    return result


def _code_note(as_of: Dict) -> str:
    """Said when code text may differ from the tree on disk: a dirty scan indexed working files, and
    edits since the scan are not in the `code` artifact."""
    if as_of.get("snapshot_uncommitted"):
        return "code text is from the working files at scan time (uncommitted edits included)"
    if as_of.get("dirty_files"):
        return "code text is as indexed; uncommitted edits since the scan are not searched"
    return ""


def _window(line: str, needle: str, width: int = 160) -> str:
    """The line trimmed, cut to `width` around the first match so the match stays visible."""
    line = line.strip()
    if len(line) <= width:
        return line
    at = max(0, line.lower().find(needle) - width // 3)
    return ("..." if at else "") + line[at:at + width] + ("..." if at + width < len(line) else "")


def _code_hits(store: Store, text: str, exclude_role: Optional[Sequence[str]]) -> List[Dict]:
    """Lines of source text containing `text` (case-insensitive substring, one line at a time).
    Row: the enclosing member (or type, or the file), `file:line`, the trimmed line. The `code`
    artifact holds source-role files only, so a role filter on it is a no-op unless it names `source`."""
    files = (getattr(store, "code", None) or {}).get("files") or {}
    needle = text.lower()
    if not files or not needle.strip() or (exclude_role and "source" in exclude_role):
        return []
    members = codeindex.member_index(store.xref["symbols"])
    hits = []
    for path in sorted(files):
        rows = members.get(path, [])
        for line, content in codeindex.scan_lines(files[path], needle):
            hits.append({"owner": codeindex.owner_of(rows, line) or path, "at": "%s:%d" % (path, line),
                         "text": _window(content, needle)})
    return hits


def _annotation_hits(store: Store, text: str, exclude_role: Optional[Sequence[str]]) -> List[Dict]:
    """Annotations (on declarations and on parameters) whose name, fqn or source text contains
    `text`, whitespace ignored on both sides. Row: owner, verbatim text, `file:line-end`."""
    needle = squash(text)
    if not needle:
        return []
    roles = _role_index(store) if exclude_role else {}
    hits = []
    for fqn, entry in store.xref["symbols"].items():
        for site in entry.get("sites", []):
            if exclude_role and roles.get(site["file"]) in exclude_role:
                continue
            groups = [(fqn, site.get("annotations", []))]
            groups += [("%s(%s)" % (fqn, p["name"]), p.get("annotations", [])) for p in site.get("params", [])]
            for owner, rows in groups:
                for r in rows:
                    if needle in squash(r["name"]) or needle in squash(r.get("fqn", "")) or needle in squash(r["text"]):
                        hits.append({"owner": owner, "text": r["text"], "at": ann_at(site["file"], r)})
    hits.sort(key=lambda h: (_search_rank_key(h["text"], text), h["owner"], h["at"]))
    return hits


def q_claims(
    store: Store,
    kind: Optional[str] = None,
    module: Optional[str] = None,
    subject: Optional[str] = None,
    budget: Optional[Budget] = None,
    exclude_role: Optional[Sequence[str]] = None,
) -> Dict:
    budget = budget or Budget()
    claims = store.state["claims"]
    if kind:
        claims = [c for c in claims if c.get("kind") == kind]
    if subject:
        claims = [c for c in claims if _matches(c.get("subject", ""), subject)]
    if module:
        claims = [c for c in claims if _matches(_claim_module(c, store) or "", module)]
    if exclude_role:
        roles = _role_index(store)
        # Dropped only if every evidence anchor is excluded-role.
        claims = [
            c for c in claims
            if any(roles.get(a.get("file")) not in exclude_role for a in c.get("evidence", []))
        ]
    return _finish(
        {"query": "claims", "count": len(claims), "claims": budget.take(claims)},
        store, budget,
    )


def q_unknowns(store: Store, module: Optional[str] = None,
               budget: Optional[Budget] = None,
               exclude_role: Optional[Sequence[str]] = None) -> Dict:
    budget = budget or Budget()
    unknowns = store.state["unknowns"]
    if module:
        unknowns = [u for u in unknowns if _matches(str(u.get("source_node", "")), module)]
    if exclude_role:
        roles = _role_index(store)
        unknowns = [
            u for u in unknowns
            if roles.get((u.get("anchor") or {}).get("file")) not in exclude_role
        ]
    grouped: Dict[str, List[Dict]] = {}
    for row in budget.take(unknowns):
        grouped.setdefault(str(row.get("source_node", "(unattributed)")), []).append(row)
    return _finish(
        {
            "query": "unknowns",
            "count": len(unknowns),
            "by_node": {k: grouped[k] for k in sorted(grouped)},
        },
        store, budget,
    )


def q_conflicts(store: Store, budget: Optional[Budget] = None) -> Dict:
    budget = budget or Budget()
    state = store.state
    return _finish(
        {
            "query": "conflicts",
            "count": len(state.get("conflicts", [])),
            "near_miss_count": len(state.get("near_misses", [])),
            "conflicts": budget.take(state.get("conflicts", [])),
            "near_misses": budget.take(state.get("near_misses", [])),
        },
        store, budget,
    )
