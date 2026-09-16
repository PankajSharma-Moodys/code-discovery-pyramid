"""Phase 4 (M4.1) -- entailment validation (6.1).

`verify.py:14-20` states the boundary honestly: anchor verification confirms
cited text exists, never that it supports the statement. This module narrows
that gap as far as determinism can: a claim is checked against the same
`io_edges`/`defines` the extractor already produced for this commit, matching
on **structure** (subject + channel, or subject + a discrete field like
visibility) and never on the claim's own wording -- "occurs near the cited
line" was already rejected as a text-matching rule for anchors, and paraphrase
matching for entailment is the same mistake one level up.

Three verdicts, in order of how much they tell you:

- `entailed`   -- an `io_edge` already states this subject+channel fact.
  Not a failure: it is a cost signal (a claim that only restates structure
  did not need a model to say it).
- `contradicted` -- a `definition` for this subject exists and disagrees with
  the claim on a discrete field. Gold: every entry is an agent error or an
  extractor gap.
- `consistent`  -- no structural opinion either way. The default for intent
  claims, which is most of them.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

ENTAILED = "entailed"
CONSISTENT = "consistent"
CONTRADICTED = "contradicted"


def entail_claims(claims: Sequence[Dict], extraction: Optional[Dict]) -> List[Dict]:
    """Return `claims` with a `verdict` field added to each, verdict never
    read back into anything else -- it is an annotation, not a rewrite of the
    claim's own asserted fields."""
    io_edges = (extraction or {}).get("io_edges") or []
    defines = (extraction or {}).get("defines") or []
    edge_keys = {(e.get("source"), e.get("channel")) for e in io_edges}
    def_by_fqn: Dict[str, Dict] = {}
    for d in defines:
        def_by_fqn.setdefault(d.get("fqn"), d)

    out: List[Dict] = []
    for claim in claims:
        row = dict(claim)
        subject = row.get("subject")
        channel = row.get("channel")
        definition = def_by_fqn.get(subject)
        if channel and (subject, channel) in edge_keys:
            row["verdict"] = ENTAILED
        elif (
            definition is not None
            and row.get("visibility")
            and definition.get("visibility") != row["visibility"]
        ):
            row["verdict"] = CONTRADICTED
        else:
            row["verdict"] = CONSISTENT
        # R11 (Phase 4, M4.4): humans outrank models on interpretation, never
        # on structure. A human claim contradicted by extraction is not
        # silently accepted -- its confidence is downgraded to `contested`,
        # the same value merge.py already uses for a claim two agents
        # disagree on, reused here for a claim and the deterministic layer
        # disagreeing instead.
        if row["verdict"] == CONTRADICTED and row.get("author_kind") == "human":
            row["confidence"] = "contested"
        out.append(row)
    return out


def summarize(claims: Sequence[Dict]) -> Dict:
    """Overall verdict counts, plus the per-scope entailed ratio
    `CDP_CLI_SCOPE.md`'s tiering question needs: a scope whose claims are all
    `entailed` did not need an expensive model to produce them."""
    counts = {ENTAILED: 0, CONSISTENT: 0, CONTRADICTED: 0}
    by_node: Dict[str, Dict[str, int]] = {}
    for claim in claims:
        verdict = claim.get("verdict", CONSISTENT)
        counts[verdict] = counts.get(verdict, 0) + 1
        # Post-merge, a claim carries `source_nodes` (plural, `merge.py:225-226`
        # -- one claim can be attributed to several converging leaves);
        # pre-merge callers (e.g. a single patch's own claims) still have the
        # singular `source_node`. A claim counts toward every node it names.
        nodes = claim.get("source_nodes")
        if nodes is None:
            nodes = [claim.get("source_node", "?")]
        for node in (nodes or ["?"]):
            node_counts = by_node.setdefault(str(node), {ENTAILED: 0, CONSISTENT: 0, CONTRADICTED: 0})
            node_counts[verdict] = node_counts.get(verdict, 0) + 1

    total = len(claims)
    by_node_ratio = {}
    for node, node_counts in sorted(by_node.items()):
        node_total = sum(node_counts.values())
        by_node_ratio[node] = {
            **node_counts,
            "entailed_ratio": round(node_counts[ENTAILED] / node_total, 4) if node_total else 0.0,
        }
    return {
        "counts": counts,
        "rate_contradicted": round(counts[CONTRADICTED] / total, 4) if total else 0.0,
        "by_node": by_node_ratio,
    }
