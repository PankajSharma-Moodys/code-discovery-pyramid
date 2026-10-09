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
    as_of_run_id = getattr(store, "as_of_run_id", None)
    if as_of_run_id:
        result["patch_log_as_of"] = as_of_run_id
    return result


def _finish(result: Dict, store: Store, budget: Optional[Budget]) -> Dict:
    """Attach the two fields every response must carry."""
    result["as_of"] = _as_of(store)
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
