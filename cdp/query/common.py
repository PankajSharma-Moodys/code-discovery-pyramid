"""Helpers shared by the query kinds."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .budget import Budget
from .store import Store


def _as_of(store: Store) -> Dict:
    """The commit and state generation an answer was computed from.

    `state_version` is the number of patches folded into `state.json`. It is a
    generation counter, not a semantic version: patch 0000 is the derived
    structural layer, and each agent wave appends more. Two answers carrying
    different `state_version` were computed from different knowledge, even at
    one commit.
    """
    inventory = store.inventory
    provenance = (store.state or {}).get("provenance", {})
    result = {
        "repo": inventory.get("repo_name"),
        "commit": inventory.get("head", "unpinned"),
        "state_version": provenance.get("patch_count", 0),
        "fold_hash": provenance.get("fold_hash"),
    }
    # M3.7 `--as-of`: the claim log was replayed only up to a past run, but
    # `xref`/`graph` (and so `inventory.head` above) are still the current
    # structural view -- naming that explicitly rather than letting `commit`
    # imply the whole answer is historical when only the claims are.
    choice = getattr(store, "choice", None)
    if choice is not None:
        result.update(choice.as_dict())
    as_of_run_id = getattr(store, "as_of_run_id", None)
    if as_of_run_id:
        result["patch_log_as_of"] = as_of_run_id
    return result


def flag_changed(result: Any, changed: Sequence[str]) -> List[str]:
    """Mark every citation of a file that changed since the answering snapshot
    (`changed_since: true`) and return the changed files the answer cites."""
    wanted, cited = set(changed), set()

    def walk(node):
        if isinstance(node, dict):
            at = node.get("file") if isinstance(node.get("line"), int) else None
            at = at or (str(node["at"]).rsplit(":", 1)[0] if isinstance(node.get("at"), str) else None)
            if isinstance(at, str) and at in wanted:
                node["changed_since"] = True
                cited.add(at)
            for key, value in list(node.items()):
                if key != "as_of":
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, str) and ":" in item and item.rsplit(":", 1)[0] in wanted:
                    cited.add(item.rsplit(":", 1)[0])
                else:
                    walk(item)

    walk(result)
    return sorted(cited)


def _finish(result: Dict, store: Store, budget: Optional[Budget]) -> Dict:
    """Attach the two fields every response must carry."""
    result["as_of"] = _as_of(store)
    choice = getattr(store, "choice", None)
    if choice is not None and choice.changed_files:
        result["as_of"]["changed_since"] = flag_changed(result, choice.changed_files)
    if budget is None:
        result["elided"] = 0
        result["budget"] = None
        result["budget_note"] = (
            "%s is never budgeted: it is the check that detects a compromised "
            "answer, so it must not be able to be compromised the same way."
            % result.get("query")
        )
        return result
    result["elided"] = budget.elided
    result["budget"] = budget.limit
    note = budget.note()
    if note:
        result["budget_note"] = note
    return result


def cite(anchor: Dict) -> str:
    return "%s:%s" % (anchor.get("file"), anchor.get("line"))


def ann_at(file: str, row: Dict) -> str:
    """`file:line` or `file:line-end` for an annotation row."""
    line, end = row.get("line"), row.get("end_line")
    if not line:
        return file
    return "%s:%d" % (file, line) + ("-%d" % end if end and end != line else "")


def ann_view(file: str, rows: Sequence[Dict]) -> List[Dict]:
    """Annotation rows as the query shows them: verbatim text, where it sits and its parsed `args`."""
    return [{"text": r["text"], "at": ann_at(file, r), **({"args": r["args"]} if r.get("args") else {})}
            for r in rows]


def annotations_of(store: Store, fqn: str) -> Dict:
    """What decorates a symbol: its own annotations and parameters, and its owner class's.
    One entry per definition site (overloads differ); empty keys are left out."""
    syms = store.xref["symbols"]
    out: Dict[str, List] = {"annotations": [], "params": [], "class_annotations": []}
    for site in syms.get(fqn, {}).get("sites", []):
        out["annotations"] += ann_view(site["file"], site.get("annotations", []))
        for p in site.get("params", []):
            if p.get("annotations"):
                out["params"].append({"name": p["name"], "type": p.get("type"),
                                      "annotations": ann_view(site["file"], p["annotations"])})
    owner = fqn.partition("#")[0]
    if "#" not in fqn:
        head = fqn.rpartition(".")[0]
        owner = head if syms.get(head, {}).get("kind") in ("class", "interface", "enum", "record") else ""
    if owner and owner != fqn:
        for site in syms.get(owner, {}).get("sites", []):
            out["class_annotations"] += ann_view(site["file"], site.get("annotations", []))
    return {k: v for k, v in out.items() if v}


#: Parameter annotations that name a request input: kind -> annotation fqns (simple names when the
#: fqn is unresolved, as for every rule match).
INPUT_ANNOTATIONS = {
    "path": ("org.springframework.web.bind.annotation.PathVariable", "javax.ws.rs.PathParam", "jakarta.ws.rs.PathParam"),
    "query": ("org.springframework.web.bind.annotation.RequestParam", "javax.ws.rs.QueryParam", "jakarta.ws.rs.QueryParam"),
    "header": ("org.springframework.web.bind.annotation.RequestHeader", "javax.ws.rs.HeaderParam", "jakarta.ws.rs.HeaderParam"),
    "body": ("org.springframework.web.bind.annotation.RequestBody",),
}
INPUT_SIMPLE = frozenset(f.rsplit(".", 1)[-1] for fqns in INPUT_ANNOTATIONS.values() for f in fqns) | {"DefaultValue"}


def _input_kind(ann: Dict) -> Optional[str]:
    from ..rules import ann_matches
    for kind, fqns in INPUT_ANNOTATIONS.items():
        if ann_matches(ann, fqns, [f.rsplit(".", 1)[-1] for f in fqns]):
            return kind
    return None


def route_inputs(store: Store, handler: str, evidence: Sequence[Dict]) -> List[Dict]:
    """What a route's handler reads from the request: one row per annotated parameter,
    `{name, kind, type, [required], [default]}`, from `@PathVariable`/`@RequestParam`/`@RequestHeader`/
    `@RequestBody` and the JAX-RS `*Param` annotations. `required`/`default` appear only when the
    annotation's arguments (or a JAX-RS `@DefaultValue`) state them; the row's `at` is the
    annotation's `file:line`."""
    sites = store.xref["symbols"].get(handler, {}).get("sites", [])
    if not sites:
        return []
    ev = evidence[0] if evidence else {}
    same = [s for s in sites if s["file"] == ev.get("file")] or sites
    after = [s for s in same if s["anchor"]["line"] >= (ev.get("line") or 0)]
    site = min(after or same, key=lambda s: s["anchor"]["line"] if after else -s["anchor"]["line"])
    out: List[Dict] = []
    for p in site.get("params", []):
        anns = p.get("annotations") or []
        for a in anns:
            kind = _input_kind(a)
            if kind is None:
                continue
            args = a.get("args") or {}
            name = args.get("value") if isinstance(args.get("value"), str) else args.get("name")
            row = {"name": name if isinstance(name, str) else (None if kind == "body" else p["name"]),
                   "kind": kind, "type": p.get("type"), "param": p["name"], "at": ann_at(site["file"], a)}
            if isinstance(args.get("required"), bool):
                row["required"] = args["required"]
            default = args.get("defaultValue")
            for d in anns:
                if (d.get("name") or "") == "DefaultValue" and isinstance((d.get("args") or {}).get("value"), str):
                    default = d["args"]["value"]
            if isinstance(default, str):
                row["default"] = default
            out.append(row)
            break
    return out


def inputs_line(inputs: Sequence[Dict], cap: int = 8) -> str:
    """`inputs: path id:Long, query q:String?=x, body Foo` (`?` = not required, `=x` = default)."""
    parts = []
    for i in inputs[:cap]:
        typ = (i.get("type") or "").rsplit(".", 1)[-1]
        mark = ("?" if i.get("required") is False else "") + ("=" + i["default"] if "default" in i else "")
        head = i["kind"] + (" " + i["name"] + ":" if i.get("name") else " ")
        parts.append(head + typ + mark)
    more = ", ... +%d" % (len(inputs) - cap) if len(inputs) > cap else ""
    return "inputs: " + ", ".join(parts) + more


def squash(text: str) -> str:
    """Lower-case with all whitespace removed, so `value = "60s"` finds `value="60s"`."""
    return "".join(str(text).split()).lower()


def _claim_lines(claim: Dict, indent: str = "  ") -> List[str]:
    out = ["%s%s" % (indent, claim.get("statement", ""))]
    for text in claim.get("statements", [])[1:]:
        out.append("%s  (also stated as) %s" % (indent, text))
    marks = [claim.get("confidence", "")]
    if claim.get("channel"):
        marks.append(claim["channel"])
    out.append(
        "%s  [%s] %s"
        % (indent, "/".join(m for m in marks if m), " ".join(cite(a) for a in claim.get("evidence", [])))
    )
    return out


def _matches(text: str, needle: str) -> bool:
    return needle.lower() in str(text).lower()


_SEARCH_SEGMENT_SPLIT = re.compile(r"[.#:/_]+")


_CAMEL_BOUNDARY_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _search_rank_key(text: str, needle: str) -> Tuple[int, int, str]:
    """Ranks a `q_search` match by how meaningfully `needle` relates to
    `text`, not just by `text`'s raw length.

    A pure length sort (the prior behaviour) ranks a short, coincidental
    substring match above a longer, semantically-real one -- e.g. against
    this repo's own real vocabulary, `q="id"` ranked the dataflow node
    `table:widget` (an accidental "id" inside "widget") ahead of
    `cdp.derive#claim_id`/`web.api.nodeid#sym_id` (where "id" is a whole,
    real token), purely because `table:widget` is a shorter string overall.

    Tiers, tightest first: (0) exact case-insensitive match, (1) `needle` is
    a whole segment once `text` is split on the same separators query
    vocabulary already uses (`.`, `#`, `:`, `/`, `_`), (2) `needle` is a whole
    camelCase/PascalCase sub-token of one of those segments -- e.g. `"id"`
    against `AddImportJobId` -- since delimiter-splitting alone never
    separates identifiers that only vary by case, (3) `text` or one of its
    delimiter segments starts with `needle`, (4) everything else (`_matches`'s
    plain substring test). Length, then the text itself, break ties within a
    tier -- shorter still reads as more relevant, and the final `text` key
    makes tied output deterministic rather than depending on scan order.
    """
    lower = str(text).lower()
    lower_needle = needle.lower()
    if lower == lower_needle:
        tier = 0
    else:
        segments = _SEARCH_SEGMENT_SPLIT.split(str(text))
        lower_segments = [s.lower() for s in segments]
        if lower_needle in lower_segments:
            tier = 1
        else:
            camel_tokens = [
                tok.lower()
                for seg in segments
                for tok in _CAMEL_BOUNDARY_SPLIT.split(seg)
                if tok
            ]
            if lower_needle in camel_tokens:
                tier = 2
            elif lower.startswith(lower_needle) or any(s.startswith(lower_needle) for s in lower_segments):
                tier = 3
            else:
                tier = 4
    return (tier, len(text), text)


def _fair_split_budget(limit: int, demands: Sequence[int]) -> List[int]:
    """Water-filling allocation of `limit` rows across `demands` buckets.

    `q_search` used to spend one shared `Budget` across `claims`, `symbols`,
    `unknowns`, `files` in that construction order -- so a term with more
    claim matches than the whole budget could exhaust it before `symbols`/
    `files` (the only two categories `/api/search` actually returns) got a
    turn. Passing `q_search`'s own default budget (200) through, instead of
    the UI's small `limit`, was tried first and fixed the reported case
    (`q="app"`, 26 claims) -- but measured live against the real
    `unified-store` index, ordinary vocabulary (`service`, `id`, `sql`,
    `table`, `route`, `schema`, `store`) has *more than 200* matching claims
    each, so `/api/search` still silently returned zero results for common,
    real words. Splitting the allowance fairly across buckets, with any
    share a smaller bucket doesn't need redistributed to the buckets that
    do, closes the actual failure mode rather than just raising the same
    single shared number again.
    """
    n = len(demands)
    alloc = [0] * n
    remaining = max(0, int(limit))
    active = [i for i in range(n) if demands[i] > 0]
    while remaining > 0 and active:
        share = max(1, remaining // len(active))
        still_active = []
        for i in active:
            want = demands[i] - alloc[i]
            take = min(want, share, remaining)
            alloc[i] += take
            remaining -= take
            if alloc[i] < demands[i]:
                still_active.append(i)
        active = still_active
    return alloc


def _more(indent: str, total: int, shown: Sequence[Any]) -> List[str]:
    """The `"... N more"` marker, generalised from `q_symbol`'s `used_by`.

    That one site was the only honest truncation in the module
    (`RESEARCH_GRAPHIFY.md §10` marks it "the pattern to generalise"). Every
    list that can be cut now emits it, and a list that was not cut emits
    nothing, so the marker's presence means something.
    """
    missing = total - len(shown)
    return ["%s... %d more (elided by the budget)" % (indent, missing)] if missing > 0 else []


def _role_index(store: Store) -> Dict[str, str]:
    """`path -> role`, built once per query rather than re-scanned per row."""
    return {f["path"]: f["role"] for f in store.inventory["files"]}


def _claim_module(claim: Dict, store: Store) -> Optional[str]:
    nodes = claim.get("source_nodes") or ([claim["source_node"]] if claim.get("source_node") else [])
    for node in nodes:
        if node.startswith("root/"):
            return node.split("/")[1]
    for anchor in claim.get("evidence", []):
        for entry in store.inventory["files"]:
            if entry["path"] == anchor.get("file"):
                return entry["module"]
    return None


def _tally(values: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
