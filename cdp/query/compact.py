"""The default answer shape: the same facts as the full result, with the repetition taken out.

The full result (`view=detail`) repeats a lot: every annotation carries its verbatim `text` *and*
a parsed `args` tree whose nested annotations repeat their own text; every `at` spells out a file
path the row already names; a class's annotations are copied onto each of its members; route
`params` restate `inputs`; every claim restates that it was verified at HEAD. On sql-pool that made
`routes` 106k characters for 25 rows -- past the MCP limit, so the agent saw nothing at all.

`compact` removes only what can be read back from what it keeps:

- an annotation keeps `text` and `line`. The constant values it uses (`ApiConstants.POST` -> `POST`),
  which the text alone cannot give, are listed once for the whole answer under `resolved` (inline only
  if one name resolved to two values). When `text` was truncated the parsed `args` tree is the one full
  copy, so the annotation keeps `args` (CONTEXT_PLAN rule 1): every argument past the cut, plain or nested;
- when every annotation of a row sits in one file, the row says so once (`annotations_in`) and each
  annotation keeps just its line;
- class annotations move to one top-level `classes` entry per class;
- a route param annotation already stated by an `inputs` row is dropped;
- claim timestamps equal to `as_of.commit` are dropped (a different or empty one is kept: that is the
  staleness signal), and claim evidence is grouped by file;
- empty fields inside rows are omitted.

`tests/test_query_views.py` extracts every fact (citations, annotation texts, resolved values,
claims, inputs) from both shapes and fails if they differ. The size cap (`views.py`) is the one place
rows can leave the answer, and it says how many and how to get them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..lang.base import ANNOTATION_TEXT_MAX
from .common import INPUT_SIMPLE

NOTE = ("compact form: empty fields omitted; an annotation's `line` is in the row's `annotations_in` file; "
        "class annotations are listed once under `classes`; `resolved` gives constant values; claim "
        "timestamps are omitted where they equal as_of.commit; claim evidence is grouped by file. "
        "view=detail returns the full form.")

_ANN_KEYS = frozenset(("text", "at", "args"))
_OWNER_KEYS = ("handler", "fqn", "symbol", "node", "by")


class _Ctx:
    """What one `compact` call shares across rows: HEAD, the hoisted classes and the hoisted constants."""

    def __init__(self, head: Optional[str]) -> None:
        self.head = head
        self.classes: Dict[str, Dict] = {}
        self.resolved: Dict[str, Any] = {}
        self.clashes: set = set()


def compact(result: Dict) -> Dict:
    ctx = _Ctx((result.get("as_of") or {}).get("commit"))
    out = {k: (v if k == "as_of" else _walk(v, ctx, top=True)) for k, v in result.items()}
    if ctx.classes:
        out["classes"] = ctx.classes
    if ctx.resolved:
        out["resolved"] = ctx.resolved
    out["compact"] = NOTE
    return out


# --------------------------------------------------------------------------- walk

def _walk(value: Any, ctx: _Ctx, top: bool = False) -> Any:
    if isinstance(value, list):
        return [_walk(v, ctx) for v in value]
    if not isinstance(value, dict):
        return value
    if _is_claim(value):
        return _claim(value, ctx.head)
    row = dict(value)
    if "class_annotations" in row:
        _hoist_class(row, ctx)
    if "params" in row and "inputs" in row:
        row["params"] = _params_minus_inputs(row["params"], row["inputs"])
    _localise_annotations(row, ctx)
    done = {k: _walk(v, ctx) for k, v in row.items()}
    return done if top else {k: v for k, v in done.items() if v not in (None, [], {}, "")}


def _is_ann(d: Any) -> bool:
    return (isinstance(d, dict) and isinstance(d.get("text"), str) and d["text"].startswith("@")
            and "at" in d and set(d) <= _ANN_KEYS)


def _ann(a: Dict, file: Optional[str], ctx: _Ctx) -> Dict:
    row: Dict[str, Any] = {}
    at = a["at"]
    if file and at.startswith(file + ":"):
        line = at[len(file) + 1:]
        row["line"] = int(line) if line.isdigit() else line
    else:
        row["at"] = at
    row["text"] = a["text"]
    inline = {}
    for ref, value in _resolved(a.get("args"), {}).items():
        if ctx.resolved.setdefault(ref, value) != value:  # one name, two values: say so where it differs
            ctx.clashes.add(ref)
            inline[ref] = value
    if inline:
        row["resolved"] = inline
    if a.get("args") and _truncated(a["text"]):
        row["args"] = a["args"]  # the one full copy: a plain argument past the cut lives only here
    return row


def _truncated(text: str) -> bool:
    return text.endswith("...") and len(text) >= ANNOTATION_TEXT_MAX


def _resolved(value: Any, acc: Dict) -> Dict:
    if isinstance(value, dict):
        if "ref" in value and "resolved" in value:
            acc[value["ref"]] = value["resolved"]
        for v in value.values():
            _resolved(v, acc)
    elif isinstance(value, list):
        for v in value:
            _resolved(v, acc)
    return acc


def _ann_lists(row: Dict) -> List[List[Dict]]:
    """Every annotation list a row holds: its own, and each param's."""
    lists = [row["annotations"]] if isinstance(row.get("annotations"), list) else []
    for p in row.get("params") or []:
        if isinstance(p, dict) and isinstance(p.get("annotations"), list):
            lists.append(p["annotations"])
    return [lst for lst in lists if lst and all(_is_ann(a) for a in lst)]


def _file_of(at: str) -> str:
    head, _, tail = at.rpartition(":")
    return head if head and tail.replace("-", "").isdigit() else at


def _localise_annotations(row: Dict, ctx: _Ctx) -> None:
    lists = _ann_lists(row)
    if not lists:
        return
    files = {_file_of(a["at"]) for lst in lists for a in lst}
    file = files.pop() if len(files) == 1 else None
    if file:
        row["annotations_in"] = file
    if isinstance(row.get("annotations"), list) and row["annotations"] in lists:
        row["annotations"] = [_ann(a, file, ctx) for a in row["annotations"]]
    if row.get("params"):
        row["params"] = [dict(p, annotations=[_ann(a, file, ctx) for a in p["annotations"]])
                         if isinstance(p, dict) and p.get("annotations") in lists else p
                         for p in row["params"]]


def _hoist_class(row: Dict, ctx: _Ctx) -> None:
    anns = row["class_annotations"]
    if not (isinstance(anns, list) and anns and all(_is_ann(a) for a in anns)):
        return
    owner = next((row[k] for k in _OWNER_KEYS if isinstance(row.get(k), str) and row[k]), None)
    if not owner:
        return
    owner = owner.partition("#")[0] if "#" in owner else owner.rpartition(".")[0] or owner
    files = {_file_of(a["at"]) for a in anns}
    file = files.pop() if len(files) == 1 else None
    entry = {**({"file": file} if file else {}), "annotations": [_ann(a, file, ctx) for a in anns]}
    if ctx.classes.setdefault(owner, entry) != entry:  # two blocks under one name: keep this one inline
        return
    del row["class_annotations"]
    row.setdefault("class", owner)


def _params_minus_inputs(params: Any, inputs: Any) -> Any:
    """Drop the param annotations an `inputs` row already states (`@QueryParam("x")` is input x)."""
    if not (isinstance(params, list) and isinstance(inputs, list)):
        return params
    named = {i.get("param"): i for i in inputs if isinstance(i, dict)}
    kept = []
    for p in params:
        if not (isinstance(p, dict) and p.get("name") in named and isinstance(p.get("annotations"), list)):
            kept.append(p)
            continue
        row = named[p["name"]]

        def stated(a: Dict) -> bool:
            """Only an annotation whose content the input row carries may go: `@DefaultValue` needs the
            row's `default` (a constant default the row could not read must stay)."""
            simple = a["text"][1:].split("(", 1)[0].rsplit(".", 1)[-1]
            if simple not in INPUT_SIMPLE:
                return False
            return simple != "DefaultValue" or "default" in row or "default_ref" in row

        rest = [a for a in p["annotations"] if not (_is_ann(a) and stated(a))]
        if rest:
            kept.append(dict(p, annotations=rest))
    return kept


# --------------------------------------------------------------------------- claims

def _is_claim(d: Dict) -> bool:
    ev = d.get("evidence")
    return ("statement" in d and isinstance(ev, list)
            and all(isinstance(e, dict) and "file" in e for e in ev))


def _claim(c: Dict, head: Optional[str]) -> Dict:
    out = {}
    for k, v in c.items():
        if k in ("anchor_verified_at", "claim_reviewed_at") and head and v == head:
            continue
        if k == "evidence":
            grouped: Dict[str, List] = {}
            for e in v:
                grouped.setdefault(e["file"], []).append([e.get("line"), e.get("anchor")])
            out["evidence"] = grouped
            continue
        out[k] = v
    return {k: v for k, v in out.items() if v not in ([], {}, "")}
