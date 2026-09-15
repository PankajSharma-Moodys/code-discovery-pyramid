"""Phase 7b — the deterministic merge operator (§5.5).

SKILL.state explicitly leaves multi-agent merge conflict resolution unsolved:
its merge is single-agent, so a patch never contends with a concurrent patch.
CDP is inherently multi-agent, so this operator is a contribution rather than an
implementation detail.

**Detection comes first, and it is the harder half.** Both obvious definitions
are wrong. Matching on claim `id` fires almost never, since ids are agent-coined.
Matching on "these statements read differently" fires constantly on claims
written from different vantage points — `sql-pool-api` calling `DServer` an
API-facing domain type and `sql-pool-common` calling it a shared internal model
do not contradict each other, and a detector that flags that pair flags most of
the corpus.

A conflict therefore requires all three of: same resolved subject, same `kind`,
and a differing value in a **closed-vocabulary field**. Prose difference is not
conflict; two differently-worded statements agreeing on every enum are two
descriptions of one fact, and both are kept with both evidence sets.

**Resolution order: ownership, then evidence count, then escalate.** An earlier
draft had the first two reversed. Evidence count rewards verbosity — an agent
citing five incidental use-sites would defeat an agent citing the one definition
site — and a conflict about what a symbol *means* turns on authority, not volume.

**Reduction is set-wise, not pairwise.** Evaluating the whole claim set for a
subject at once makes order-independence structural rather than something to be
proved again every time the policy changes, and it makes escalation correct by
construction: `contested` is a set-valued outcome, and pairwise folding is
exactly where an n-way tie degrades into an arbitrary pair.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .util import stable_hash

# The closed-vocabulary fields conflict detection is defined over. Deliberately
# excludes `confidence`: that is a claim's own hedge, not an assertion about the
# subject, and treating it as one would make every cautious agent a conflict.
ENUM_FIELDS = ("channel", "visibility", "side_effect_type")
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2, "contested": 3}


def merge_claims(claims: Sequence[Dict], symbols: Dict[str, Dict]) -> Dict:
    """Fold a flat list of verified claims into merged state.

    `symbols` is the global symbol table from the resolve phase; it is what
    makes rule 1 (ownership) answerable. This is the third argument the fold
    invariant in §3.4 insists on: a node's state is not a fold over its own
    patches alone.
    """
    groups: Dict[Tuple[str, str], List[Dict]] = {}
    for claim in claims:
        groups.setdefault((str(claim.get("subject")), str(claim.get("kind"))), []).append(claim)

    merged: List[Dict] = []
    conflicts: List[Dict] = []
    near_misses: List[Dict] = []
    stats = {"groups": 0, "unanimous": 0, "conflicts": 0, "near_misses": 0,
             "resolved_by_ownership": 0, "resolved_by_evidence": 0, "contested": 0}

    for key in sorted(groups):
        subject, kind = key
        members = sorted(groups[key], key=_claim_sort_key)
        stats["groups"] += 1

        by_signature: Dict[Tuple, List[Dict]] = {}
        for claim in members:
            by_signature.setdefault(_signature(claim), []).append(claim)

        if len(by_signature) == 1:
            stats["unanimous"] += 1
            merged.append(_union(subject, kind, members))
            # C4 instrumentation: same subject, same kind, same enums, different
            # prose. Free to collect, and it is the only number that separates
            # "the detection rule is well calibrated" from "it never fires".
            if len({str(c.get("statement", "")).strip() for c in members}) > 1:
                stats["near_misses"] += 1
                near_misses.append(
                    {
                        "subject": subject,
                        "kind": kind,
                        "statements": sorted(
                            {str(c.get("statement", "")) for c in members}
                        ),
                        "nodes": sorted({str(c.get("source_node", "")) for c in members}),
                    }
                )
            continue

        stats["conflicts"] += 1
        winner, reason = _resolve(subject, by_signature, symbols)
        if winner is not None:
            stats["resolved_by_" + reason] += 1
            merged.append(_union(subject, kind, by_signature[winner]))
            conflicts.append(
                _conflict_record(subject, kind, by_signature, resolved_by=reason, winner=winner)
            )
        else:
            stats["contested"] += 1
            claim = _union(subject, kind, members)
            claim["confidence"] = "contested"
            claim["contested_with"] = sorted(
                {str(c.get("source_node", "")) for c in members if c.get("source_node")}
            )
            merged.append(claim)
            conflicts.append(
                _conflict_record(subject, kind, by_signature, resolved_by=None, winner=None)
            )

    return {
        "claims": sorted(merged, key=lambda c: (c["kind"], c["subject"], c["id"])),
        "conflicts": conflicts,
        "near_misses": near_misses,
        "stats": stats,
    }


# ---------------------------------------------------------------- internals


def _signature(claim: Dict) -> Tuple:
    return tuple(claim.get(f) for f in ENUM_FIELDS)


def _claim_sort_key(claim: Dict) -> Tuple:
    """A total order on claims that does not depend on arrival order.

    Nothing downstream may use wave index, timestamp, or arrival position:
    all three encode *scheduling*, not authority, and letting them decide which
    module is right about `DServer` would make `--max-concurrent` an input to
    the architecture documentation. The failure would also be invisible to the
    determinism harness, which would score an order-dependent merge 1.0 and
    certify a systematically wrong pipeline as flawlessly stable.
    """
    return (
        str(claim.get("source_node", "")),
        str(claim.get("id", "")),
        stable_hash(claim.get("evidence") or []),
    )


def _distinct_anchors(claims: Iterable[Dict]) -> Set[Tuple[str, str]]:
    out: Set[Tuple[str, str]] = set()
    for claim in claims:
        for anchor in claim.get("evidence") or []:
            out.add((str(anchor.get("file")), str(anchor.get("anchor"))))
    return out


def _owning_modules(subject: str, symbols: Dict[str, Dict]) -> Set[str]:
    entry = symbols.get(subject)
    return set(entry["modules"]) if entry else set()


def _claim_modules(claims: Iterable[Dict]) -> Set[str]:
    out: Set[str] = set()
    for claim in claims:
        node = str(claim.get("source_node", ""))
        if node.startswith("root/"):
            out.add(node.split("/")[1])
        elif node:
            out.add(node)
    return out


def _resolve(
    subject: str, by_signature: Dict[Tuple, List[Dict]], symbols: Dict[str, Dict]
) -> Tuple[Optional[Tuple], str]:
    owners = _owning_modules(subject, symbols)

    if owners:
        owning = [sig for sig, group in by_signature.items() if _claim_modules(group) & owners]
        if len(owning) == 1:
            return owning[0], "ownership"

    counts = {sig: len(_distinct_anchors(group)) for sig, group in by_signature.items()}
    best = max(counts.values())
    leaders = sorted(sig for sig, n in counts.items() if n == best)
    if len(leaders) == 1:
        return leaders[0], "evidence"

    # Never silently pick. A merge operator that always produces an answer is a
    # merge operator that fabricates under contention, and contention is
    # precisely where the interesting knowledge lives.
    return None, "contested"


def _union(subject: str, kind: str, claims: Sequence[Dict]) -> Dict:
    claims = sorted(claims, key=_claim_sort_key)
    evidence: List[Dict] = []
    seen: Set[Tuple[str, str]] = set()
    for claim in claims:
        for anchor in claim.get("evidence") or []:
            key = (str(anchor.get("file")), str(anchor.get("anchor")))
            if key not in seen:
                seen.add(key)
                evidence.append(anchor)
    evidence.sort(key=lambda a: (str(a.get("file")), int(a.get("line") or 0)))

    statements = []
    for claim in claims:
        text = str(claim.get("statement", "")).strip()
        if text and text not in statements:
            statements.append(text)

    base = dict(claims[0])
    base.update(
        {
            "id": claims[0].get("id") or (kind + "." + subject),
            "kind": kind,
            "subject": subject,
            "statement": statements[0] if statements else "",
            "evidence": evidence,
            "confidence": max(
                (c.get("confidence", "low") for c in claims),
                key=lambda c: CONFIDENCE_ORDER.get(str(c), 0),
            ),
        }
    )
    if len(statements) > 1:
        base["statements"] = statements
    base["source_nodes"] = sorted({str(c.get("source_node", "")) for c in claims if c.get("source_node")})
    base.pop("source_node", None)
    return base


def _conflict_record(
    subject: str,
    kind: str,
    by_signature: Dict[Tuple, List[Dict]],
    resolved_by: Optional[str],
    winner: Optional[Tuple],
) -> Dict:
    positions = []
    for sig in sorted(by_signature, key=lambda s: tuple("" if v is None else str(v) for v in s)):
        group = by_signature[sig]
        positions.append(
            {
                "values": {f: v for f, v in zip(ENUM_FIELDS, sig) if v is not None},
                "nodes": sorted({str(c.get("source_node", "")) for c in group}),
                "statements": sorted({str(c.get("statement", "")) for c in group}),
                "evidence_count": len(_distinct_anchors(group)),
                "won": sig == winner,
            }
        )
    return {
        "subject": subject,
        "kind": kind,
        "resolved_by": resolved_by,
        "question": (
            "Which is correct for %s?" % subject
            if resolved_by is None
            else "Resolved by %s; recorded for audit." % resolved_by
        ),
        "positions": positions,
    }


def summarise(result: Dict) -> List[str]:
    s = result["stats"]
    return [
        "merge     %d subjects, %d unanimous, %d conflicts (%d ownership / %d evidence / %d contested)"
        % (s["groups"], s["unanimous"], s["conflicts"], s["resolved_by_ownership"],
           s["resolved_by_evidence"], s["contested"]),
        "          %d near-misses (same subject+kind+enums, differing prose)" % s["near_misses"],
    ]
