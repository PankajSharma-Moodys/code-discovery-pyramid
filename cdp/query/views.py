"""How much of an answer to send, and in what form: `view`, `format`, `max_tokens`, `offset`.

`query.dispatch` computes the full result; this module projects it. Four views, each a projection of
the next, so no fact becomes unreachable -- a smaller view says how to ask for the larger one:

- `count`:   the true number of rows per bucket, and how to list them.
- `list`:    one line per row: name, `file:line`, and a short note.
- `compact`: every fact, repetition removed (`compact.py`).
- `detail`:  the full result, unchanged.

Rows are the unit of paging and of the size cap. When a cap cuts rows the answer says so with the true
`count`, a `shown` range and a `next` line with the exact call; `offset` continues from there over the
same row order, so pages never overlap or skip a row. `stats` and `coverage` are never projected.

`format=text` writes the same projection as grep-like lines (`list`/`count`) or indented `key: value`
lines (`compact`/`detail`); `format=json` is the structured dict. They carry the same facts.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..guide_kinds import FORMATS, VIEWS
from . import compact as compact_mod
from .common import REGEX_MAX_LINE, compile_regex

#: The built-in per-answer cap, in tokens (CONTEXT_PLAN.md): small enough that one answer grows context the
#: way one grep does, far under Claude Code's 10k-token MCP warning. A cut answer says what it cut and gives the
#: next `offset`; a repo sets its own `max_tokens` in `.cdp.toml` `[query]` (0 = no cap).
DEFAULT_MAX_TOKENS = 3000
CHARS_PER_TOKEN = 4
#: Row allowance for `count`/`list` when the caller gave no `budget`: those views are cut by the size
#: cap and paged by `offset`, so the underlying query must not pre-cut them.
UNLIMITED_ROWS = 10 ** 9

#: Kinds that are never projected: the census the "there is no X" check relies on.
UNPROJECTED = frozenset(("stats", "coverage"))
BROAD = ("routes", "claims", "table", "config", "search", "module", "unknowns")

#: kind -> the result keys holding its rows, in answer order. `by_node` is a dict of lists.
PRIMARY: Dict[str, Tuple[str, ...]] = {
    "routes": ("routes",),
    "claims": ("claims",),
    "table": ("tables",),
    "config": ("keys",),
    "module": ("found",),
    "symbol": ("found",),
    "file": ("found",),
    "trace": ("files",),
    "unknowns": ("by_node",),
    "paths": ("paths",),
    "conflicts": ("conflicts", "near_misses"),
    "search": ("claims", "symbols", "unknowns", "files", "constants", "annotations", "code"),
}
#: bucket -> the result field holding its true total, where the result states one.
_TOTAL = {"routes": "count", "claims": "count", "tables": "count", "keys": "count", "by_node": "count",
          "files": "file_count", "conflicts": "count", "near_misses": "near_miss_count"}
#: Fields kept in a `count`/`list` answer's header besides scalars.
_HEADER_KEEP = ("not_found", "not_searched", "default_filters", "budget_note", "dropped_fields")
_HEADER_DROP = frozenset(("caveat", "searched", "trail", "budget", "count", "counts", "file_count",
                          "near_miss_count"))


def default_view(kind: str) -> str:
    return "list" if kind in BROAD else "compact"


def resolve(kind: str, view: Optional[str], fmt: Optional[str], max_tokens: Optional[int],
            cfg: Optional[Dict]) -> Tuple[str, str, int]:
    """`(view, format, max_tokens)`: a call's own value, else the repo's `[query]`, else the built-in."""
    cfg = cfg or {}
    for name, value, allowed in (("view", view, VIEWS), ("format", fmt, FORMATS)):
        if value is not None and value not in allowed:
            raise ValueError("%s must be one of %s, got %r" % (name, ", ".join(allowed), value))
    view = view or (cfg.get("view") or {}).get(kind) or cfg.get("default_view") or default_view(kind)
    fmt = fmt or (cfg.get("format") or {}).get(view) or ("text" if view in ("count", "list") else "json")
    if max_tokens is None:
        max_tokens = cfg.get("max_tokens", DEFAULT_MAX_TOKENS)
    return view, fmt, max_tokens


# --------------------------------------------------------------------------- rows

Row = Tuple[str, Any]  # (bucket, raw row)


def _rows_of(kind: str, result: Dict) -> List[Row]:
    rows: List[Row] = []
    for key in PRIMARY[kind]:
        value = result.get(key)
        if key == "by_node" and isinstance(value, dict):
            rows += [(key, r) for node in sorted(value) for r in value[node]]
        elif isinstance(value, list):
            rows += [(key, r) for r in value]
    return rows


def _with_rows(kind: str, result: Dict, rows: List[Row]) -> Dict:
    """`result` with its primary buckets holding only `rows`."""
    out = {k: v for k, v in result.items() if k not in PRIMARY[kind]}
    for key in PRIMARY[kind]:
        if key not in result:
            continue
        mine = [r for b, r in rows if b == key]
        if key == "by_node":
            grouped: Dict[str, List] = {}
            for r in mine:
                grouped.setdefault(str(r.get("source_node", "(unattributed)")), []).append(r)
            out[key] = {n: grouped[n] for n in sorted(grouped)}
        else:
            out[key] = mine
    return out


def _totals(kind: str, result: Dict, rows: List[Row]) -> Dict[str, int]:
    have: Dict[str, int] = {}
    for bucket, _ in rows:
        have[bucket] = have.get(bucket, 0) + 1
    counts = result.get("counts") if kind == "search" else None
    out = {}
    for key in PRIMARY[kind]:
        if key not in result:
            continue
        field = _TOTAL.get(key)
        stated = (counts or {}).get(key) if counts else (result.get(field) if field else None)
        out[key] = stated if isinstance(stated, int) else have.get(key, 0)
    return out


def _drop_fields(kind: str, rows: List[Row], cfg: Optional[Dict]) -> Tuple[List[Row], List[str]]:
    names = ((cfg or {}).get("drop_fields") or {}).get(kind) or []
    if not names:
        return rows, []
    gone = set()
    out = []
    for bucket, row in rows:
        if isinstance(row, dict):
            gone.update(n for n in names if n in row)
            row = {k: v for k, v in row.items() if k not in names}
        out.append((bucket, row))
    return out, sorted(gone)


# --------------------------------------------------------------------------- list rows

def _short(fqn: str) -> str:
    owner, sep, member = str(fqn).partition("#")
    return owner.rsplit(".", 1)[-1] + sep + member


def _cite(value: Any) -> str:
    if isinstance(value, dict):
        if "file" in value:
            return "%s:%s" % (value["file"], value["line"]) if value.get("line") else str(value["file"])
        return str(value.get("at") or "")
    return str(value or "")


def _first(rows: Any) -> str:
    return _cite(rows[0]) if isinstance(rows, list) and rows else ""


def _note(text: Any, width: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[:width - 3] + "..."


def _claim_row(c: Dict) -> Dict:
    return {"name": c.get("subject") or c.get("id"), "at": _first(c.get("evidence")), "kind": c.get("kind"),
            "note": _note(c.get("statement"), 72)}


def _names(groups: List[Dict], limit: int = 3) -> str:
    names = [g.get("by", "?") for g in groups]
    return ", ".join(names[:limit]) + (" +%d" % (len(names) - limit) if len(names) > limit else "") if names else "-"


def _unknown_row(u: Dict) -> Dict:
    return {"name": _note(u.get("question"), 120), "at": _cite(u.get("anchor")), "note": u.get("source_node")}


def _generic_row(r: Any) -> Dict:
    if not isinstance(r, dict):
        return {"name": str(r)}
    name = next((r[k] for k in ("name", "subject", "fqn", "key", "path", "route", "table", "question", "id")
                 if isinstance(r.get(k), str)), "")
    at = r.get("at") or r.get("anchor") or r.get("evidence")
    return {"name": name, "at": _first(at) if isinstance(at, list) else _cite(at)}


_LIST_ROWS: Dict[Tuple[str, str], Callable[[Any], Dict]] = {
    ("routes", "routes"): lambda r: {"name": "%s %s" % (r.get("verb"), r.get("route")), "to": _short(r.get("handler", "")),
                                     "at": _first(r.get("evidence"))},
    ("claims", "claims"): _claim_row,
    ("search", "claims"): _claim_row,
    ("table", "tables"): lambda r: {"name": r.get("table"), "at": _first(r.get("evidence")) or _first(r.get("migrations")),
                                    "note": "written by %s; read by %s" % (_names(r.get("writers", [])),
                                                                          _names(r.get("readers", [])))},
    ("config", "keys"): lambda r: {"name": r.get("key"), "at": _first(r.get("declared")) or _first(r.get("read")),
                                   "note": "%s read site(s)" % r.get("read_count", len(r.get("read", [])))},
    ("module", "found"): lambda r: {"name": r.get("name"), "note": "%s files, %s loc, %s claims; depends on %s" % (
        r.get("files"), r.get("loc"), r.get("claims_count"),
        ", ".join(d["module"] for d in r.get("depends_on", [])) or "-")},
    ("symbol", "found"): lambda r: {"name": r.get("fqn"), "to": r.get("kind"), "at": _first(r.get("defined_at")),
                                    "note": "used by %s, %s claim(s)" % (r.get("used_by_count"), r.get("claims_count"))},
    ("file", "found"): lambda r: {"name": r.get("path"), "to": r.get("role"), "at": r.get("path"),
                                  "note": "%s loc, %s definitions" % (r.get("loc"), r.get("defines_count"))},
    ("trace", "files"): lambda r: {"name": r.get("why"), "at": r.get("at"),
                                   "note": r.get("confidence") if r.get("confidence") != "high" else None},
    ("unknowns", "by_node"): _unknown_row,
    ("search", "unknowns"): _unknown_row,
    ("search", "symbols"): lambda r: {"name": r},
    ("search", "files"): lambda r: {"name": r, "at": r},
    ("search", "constants"): lambda r: {"name": r},
    ("search", "annotations"): lambda r: {"name": r.get("text"), "to": r.get("owner"), "at": r.get("at")},
    ("search", "code"): lambda r: {"name": r.get("text"), "to": r.get("owner"), "at": r.get("at")},
}


def _list_row(kind: str, bucket: str, row: Any) -> Dict:
    made = _LIST_ROWS.get((kind, bucket), _generic_row)(row)
    return {k: v for k, v in made.items() if v not in (None, "", [], {})}


_FQN = re.compile(r"^[\w$]+(?:\.[\w$]+)+(?:#[\w$<>]+)?$")


def _short_names(rows: List[Dict]) -> Dict[str, str]:
    """A dotted name -> its last segment (`a.b.C#m` -> `C#m`), unless two names in the answer would collide."""
    by_short: Dict[str, set] = {}
    for r in rows:
        name = r.get("name") or ""
        if _FQN.match(name):
            owner, sep, member = name.partition("#")
            by_short.setdefault(owner.rsplit(".", 1)[-1] + sep + member, set()).add(name)
    return {next(iter(names)): short for short, names in by_short.items() if len(names) == 1}


def _row_lines(rows: List[Dict], short: bool = True) -> List[str]:
    """Text lines for list rows: short names, `[kind]` only where kinds differ, and the full repo-relative
    `file:line` exactly as grep prints it -- a cite must open directly in Read, and a shortened one
    (`ApiConstants.java`) can name two files (CONTEXT_PLAN `format`). `short=False` keeps full names: the
    line `filter` matches (FILTER_PLAN.md)."""
    names = _short_names(rows) if short else {}
    mixed = len({r.get("kind") for r in rows}) > 1
    lines = []
    for row in rows:
        name = names.get(row.get("name"), row.get("name", ""))
        label = name
        if row.get("to"):
            label += " → %s" % row["to"]
        at = row.get("at")
        note = row.get("note")
        lead = name.rsplit(".", 1)[-1] + " "
        if note and note.startswith(lead):
            note = note[len(lead):]  # the statement opens with the name already shown
        kind = "[%s]" % row["kind"] if mixed and row.get("kind") else None
        lines.append("  ".join(p for p in (label, at, kind, note) if p))
    return lines


# --------------------------------------------------------------------------- filter

def _filter_rows(kind: str, rows: List[Row], pattern: str) -> Tuple[List[Row], List[str]]:
    """The rows whose `list` line (`name → to  path:line  note`) `re.search`es `pattern`, like `grep -E` over
    `--max-tokens 0 --view list`. A row matches on its full-name line or the short-name line the answer
    displays, so a pattern written from either (`^SqlPoolApplication`, `^com\\.acme\\.`) works. Also returns
    a note for rows skipped as too long to search."""
    rx = compile_regex(pattern)
    lines: Dict[int, Tuple[str, str]] = {}
    for bucket in dict.fromkeys(b for b, _ in rows):
        idx = [i for i, (b, _) in enumerate(rows) if b == bucket]
        made = [_list_row(kind, bucket, rows[i][1]) for i in idx]
        lines.update(zip(idx, zip(_row_lines(made, short=False), _row_lines(made))))
    kept, long = [], 0
    for i, row in enumerate(rows):
        full, shown = lines[i]
        if len(full) > REGEX_MAX_LINE:
            long += 1
        elif rx.search(full) or rx.search(shown):
            kept.append(row)
    return kept, (["%d row line(s) over %d characters were not matched by filter" % (long, REGEX_MAX_LINE)]
                  if long else [])


def _quote(pattern: str) -> str:
    """The pattern as one unambiguous token: bare when it is plain, else JSON-quoted (newlines escaped)."""
    return pattern if re.fullmatch(r"[^\s\"'\\]+", pattern) else json.dumps(pattern, ensure_ascii=False)


# --------------------------------------------------------------------------- text

def _dump(value: Any, indent: int = 0) -> List[str]:
    """Indented `key: value` lines for any JSON value; nothing is abbreviated."""
    pad = "  " * indent
    if isinstance(value, dict):
        lines: List[str] = []
        for k, v in value.items():
            if isinstance(v, (dict, list)) and v:
                inline = isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v)
                if inline:
                    lines.append("%s%s: %s" % (pad, k, ", ".join(str(x) for x in v)))
                else:
                    lines.append("%s%s:" % (pad, k))
                    lines += _dump(v, indent + 1)
            else:
                lines.append("%s%s: %s" % (pad, k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v))
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                body = _dump(item, indent + 1)
                lines.append("%s- %s" % (pad, body[0].lstrip()) if body else "%s-" % pad)
                lines += body[1:]
            elif isinstance(item, list):  # a `[line, anchor]` pair
                lines.append("%s- %s" % (pad, ", ".join(str(x) for x in item)))
            else:
                lines.append("%s- %s" % (pad, item))
        return lines
    return [pad + str(value)]


def _as_of_json(as_of: Dict) -> Dict:
    """The provenance a `count`/`list` answer keeps: the commit and state it came from, and any reason to
    doubt it. `detail`/`compact` carry the full `as_of`."""
    keep = {"commit": as_of.get("commit"), "state_version": as_of.get("state_version")}
    for k in ("behind", "dirty_files", "changed_since", "snapshot_uncommitted", "routed", "code_note"):
        if as_of.get(k):
            keep[k] = as_of[k]
    return keep


def _as_of_brief(as_of: Dict) -> str:
    bits = ["@%s" % str(as_of.get("commit", "?"))[:10], "state %s" % as_of.get("state_version")]
    if as_of.get("behind"):
        bits.append("%s commit(s) behind HEAD" % as_of["behind"])
    if as_of.get("dirty_files"):
        bits.append("%d dirty file(s)" % len(as_of["dirty_files"]))
    if as_of.get("changed_since"):
        bits.append("changed since scan: %s" % json.dumps(as_of["changed_since"]))
    for k in ("routed", "code_note"):
        if as_of.get(k):
            bits.append("%s: %s" % (k, as_of[k]))
    return " ".join(bits)


def _size(payload: Dict) -> int:
    if payload.get("format") == "text":
        return len(payload["text"])
    return len(json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False))


# --------------------------------------------------------------------------- apply

def apply(kind: str, result: Dict, *, view: str, fmt: str, max_tokens: int, offset: int = 0,
          cfg: Optional[Dict] = None, explicit_budget: bool = True, filter: Optional[str] = None,
          carry: Optional[Dict[str, str]] = None) -> Dict:
    """Project `result` (the full answer for `kind`) to `view`/`fmt`, under the cap, from row `offset`.
    `filter` narrows the rows first, so totals, the cap and paging all work over matched rows only. `carry` is
    the call's `term`/`match`, which `next` repeats so following it returns the same rows."""
    carry = dict(carry or {})
    if fmt == "json" and view in ("count", "list"):
        carry["format"] = "json"  # the text default needs no mention
    if kind in UNPROJECTED:
        return result
    all_rows = _rows_of(kind, result)
    all_rows, gone = _drop_fields(kind, all_rows, cfg)
    totals = _totals(kind, result, all_rows)
    total = sum(totals.values())
    unsearched: List[str] = []
    before = total
    if filter:
        all_rows, unsearched = _filter_rows(kind, all_rows, filter)
        totals = {k: sum(1 for b, _ in all_rows if b == k) for k in totals}  # matched, not the stated totals
        total = sum(totals.values())
    if offset > len(all_rows):
        raise ValueError("offset %d is past the last row (%d row(s) in this answer)" % (offset, len(all_rows)))
    window = all_rows[offset:]
    cap = max_tokens * CHARS_PER_TOKEN if max_tokens else 0
    base = dict(result)
    if gone:
        base["dropped_fields"] = "dropped by .cdp.toml [query] drop_fields: %s" % ", ".join(gone)
    if not explicit_budget:
        base.pop("budget", None)
    if filter:
        base["filter"] = filter
        base["matched"] = "%d of %d rows" % (total, before)
        if unsearched:
            base["not_searched"] = "; ".join(x for x in [base.get("not_searched")] + unsearched if x)

    def emit(k: int) -> Dict:
        cut = k < len(window) or offset > 0
        paging = {"count": total, "shown": ("%d-%d" % (offset + 1, offset + k)) if k else "none",
                  "next": _next(view, offset + k, filter, carry) if offset + k < len(all_rows) else None} if cut else None
        note = ("cut at about %d tokens (max_tokens; 0 lifts); view=compact term=<name> gives one row's facts"
                % max_tokens) if k < len(window) and cap else None
        return _emit(kind, base, window[:k], totals, view, fmt, paging, note, carry)

    keep = len(window)
    if cap and _size(emit(keep)) > cap:
        lo, hi = 1, keep  # the largest k whose answer fits; at least one row, so progress is always made
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _size(emit(mid)) <= cap:
                lo = mid
            else:
                hi = mid - 1
        keep = lo
    out = emit(keep)
    if cap and keep == 1 and window and _size(out) > cap and view in ("compact", "detail"):
        out = _fit_one_row(kind, base, window[0], offset, totals, view, fmt, cap, max_tokens,
                           paging_next=_next(view, offset + 1, filter, carry) if offset + 1 < len(all_rows) else None, carry=carry,
                           total=total)
    return out


def _fit_one_row(kind: str, base: Dict, row: Row, offset: int, totals: Dict[str, int], view: str, fmt: str,
                 cap: int, max_tokens: int, paging_next: Optional[str], total: int,
                  carry: Optional[Dict[str, str]] = None) -> Dict:
    """One row larger than the cap on its own (a symbol with hundreds of callers): trim its inner lists from
    the end until it fits, and say exactly what was cut and the call that returns the whole row."""
    bucket, raw = row
    trimmed = json.loads(json.dumps(raw))
    cut: Dict[str, int] = {}

    def lists(value: Any, path: str) -> List[Tuple[str, List]]:
        found: List[Tuple[str, List]] = []
        if isinstance(value, dict):
            for k, v in value.items():
                found += lists(v, "%s.%s" % (path, k) if path else k)
        elif isinstance(value, list):
            if value:
                found.append((path, value))
            for v in value:
                found += lists(v, path)
        return found

    def build() -> Dict:
        note = ("row %d is larger than about %d tokens on its own: %s not shown; view=%s offset=%d max_tokens=0 "
                "returns the whole row" % (offset + 1, max_tokens,
                                           ", ".join("%d %s" % (n, k) for k, n in sorted(cut.items())),
                                           view, offset))
        paging = {"count": total, "shown": "%d-%d" % (offset + 1, offset + 1), "next": paging_next}
        return _emit(kind, base, [(bucket, trimmed)], totals, view, fmt, paging, note, carry)

    out = build()
    while _size(out) > cap:
        candidates = lists(trimmed, "")
        if not candidates:
            break
        path, biggest = max(candidates, key=lambda pv: len(json.dumps(pv[1])))
        biggest.pop()
        cut[path] = cut.get(path, 0) + 1
        out = build()
    return out


def _next(view: str, at: int, filter: Optional[str] = None, carry: Optional[Dict[str, str]] = None) -> str:
    bits = ["view=%s" % view]
    if filter:
        bits.append("filter=%s" % _quote(filter))
    bits += ["%s=%s" % (k, _quote(v)) for k, v in (carry or {}).items()]
    return " ".join(bits + ["offset=%d" % at])


def _emit(kind: str, result: Dict, rows: List[Row], totals: Dict[str, int], view: str, fmt: str,
          paging: Optional[Dict] = None, cap_note: Optional[str] = None,
          carry: Optional[Dict[str, str]] = None) -> Dict:
    shown = _with_rows(kind, result, rows)
    if view in ("count", "list"):
        payload = _brief(kind, shown, rows, totals, view, carry)
    elif view == "compact":
        payload = compact_mod.compact(shown)
    else:
        payload = dict(shown)
    if view != "detail" or fmt == "text":  # the JSON `detail` is the full result, unchanged
        payload["view"] = view
    if paging:
        payload["count"] = paging["count"]
        payload["shown"] = paging["shown"]
        if paging["next"]:
            payload["next"] = paging["next"]
        if cap_note:
            payload["capped"] = cap_note
    if fmt == "json":
        return payload
    return {"format": "text", "text": _text(kind, payload, view), "query": kind, "view": view,
            **{k: payload[k] for k in ("count", "shown", "next", "as_of", "not_found") if k in payload}}


def _brief(kind: str, shown: Dict, rows: List[Row], totals: Dict[str, int], view: str,
           carry: Optional[Dict[str, str]] = None) -> Dict:
    out: Dict[str, Any] = {"query": kind, "as_of": _as_of_json(shown.get("as_of") or {})}
    for k, v in shown.items():
        if k in PRIMARY[kind] or k in out or k in _HEADER_DROP:
            continue
        if v is not None and (not isinstance(v, (dict, list)) or k in _HEADER_KEEP):
            out[k] = v
    if view == "count":
        out["counts"] = {("unknowns" if k == "by_node" else k): n for k, n in totals.items()}
        out["next"] = (_next("list", 0, shown.get("filter"), carry).replace(" offset=0", "") + " (one line per row)"
                       if shown.get("filter") or carry else "view=list (one line per row) or view=compact (full facts)")
        return out
    for key in PRIMARY[kind]:
        if key in shown:
            bucket = "unknowns" if key == "by_node" else key
            out[bucket] = [_list_row(kind, key, r) for b, r in rows if b == key]
    out["count"] = sum(totals.values())
    return out


def _text(kind: str, payload: Dict, view: str) -> str:
    lines = []
    count = payload.get("count") if view != "count" else None
    head = "%s %s" % (kind, view)
    if view == "count":
        head += ": " + ", ".join("%s %s" % (b, n) for b, n in payload["counts"].items())
    elif count is not None:
        head += ": %s row(s)" % count
        if payload.get("shown") and payload["shown"] != "1-%s" % count:
            head += ", shown %s" % payload["shown"]
    if payload.get("match") and payload["match"] != "all":
        head += "  [%s match]" % payload["match"]
    lines.append(head + "  " + _as_of_brief(payload.get("as_of") or {}))
    for k, v in payload.items():
        if k in ("query", "view", "as_of", "count", "counts", "shown", "next", "match", "capped") or k in _bucket_keys(kind):
            continue
        lines += _dump({k: _quote(v) if k == "filter" else v})
    if view == "list":
        for key in PRIMARY[kind]:
            bucket = "unknowns" if key == "by_node" else key
            rows = payload.get(bucket)
            if not rows:
                continue
            if len(PRIMARY[kind]) > 1:
                lines.append("%s (%d):" % (bucket, len(rows)))
            indent = "  " if len(PRIMARY[kind]) > 1 else ""
            lines += [indent + line for line in _row_lines(rows)]
    elif view != "count":
        for key in PRIMARY[kind]:
            if key in payload and payload[key] not in ([], {}):
                lines += _dump({key: payload[key]})
    for k in ("capped", "next"):
        if payload.get(k):
            lines.append("%s: %s" % (k, payload[k]))
    return "\n".join(lines)


def _bucket_keys(kind: str) -> Tuple[str, ...]:
    return PRIMARY[kind] + (("unknowns",) if kind == "unknowns" else ())
