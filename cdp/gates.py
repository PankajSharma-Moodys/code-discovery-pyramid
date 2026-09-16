"""Phase 4 (M4.2) -- the four unknown gates.

`CDP_CLI_SCOPE.md`'s asymmetry: claims are falsifiable, unknowns are not. You
cannot validate an unknown's *content*, only everything around it. Four gates,
all deterministic, all free (no model call), run against a patch's
`unknowns[]` before it is appended to the log -- the same point schema
validation already runs at (`cli.py` `cmd_collect`), and for the same reason:
a rejection here needs to be attached to a specific, cited reason, not a
silent drop.

Gate 1 (subject exists) and gate 2 (negative entailment) require an unknown to
*name* a subject to be checked at all. An unknown with no `subject` field is
the pre-M4.2 shape (a scope-level gap, e.g. "what does this module contain")
and passes both gates unconditionally -- this keeps every existing unknown
producer (derived patches, `_structural_unknowns`, demoted claims) working
without a migration. `subject` is optional in the schema for exactly this
reason.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from .util import normalise_ws, stable_hash

UNEXAMINED = "unexamined"
UNKNOWN = "unknown"
ABANDONED = "abandoned"

NEEDS_VALUES = {
    "needs_runtime", "needs_external_doc", "needs_human",
    "needs_wider_scope", "needs_other_repo",
}
OPEN = "open"
RESOLVED = "resolved"
MOOT = "moot"


def build_extraction_index(extraction: Optional[Dict]) -> Tuple[set, set, Dict[Tuple[str, str], Dict]]:
    """`(defined fqns, io_edge subjects, {(subject, channel): edge})` --
    the same structural index `entail.py` builds for claims, reused here so
    "subject exists" and "already answered" mean the same thing for an
    unknown as `entailed`/`contradicted` mean for a claim."""
    io_edges = (extraction or {}).get("io_edges") or []
    defines = (extraction or {}).get("defines") or []
    def_fqns = {d.get("fqn") for d in defines if d.get("fqn")}
    edge_subjects = {e.get("source") for e in io_edges if e.get("source")}
    edge_subjects |= {e.get("target") for e in io_edges if e.get("target")}
    edges_by_key: Dict[Tuple[str, str], Dict] = {}
    for e in io_edges:
        edges_by_key.setdefault((e.get("source"), e.get("channel")), e)
    return def_fqns, edge_subjects, edges_by_key


def gate_subject_exists(unknown: Dict, node: str, def_fqns: set, edge_subjects: set,
                         scope_nodes: set) -> Optional[str]:
    """Gate 1. `None` means "passes". A subject naming nothing CDP already
    knows about is, per the plan, "about nothing" -- except a subject equal to
    a real scope node, which is the legitimate "why is there no retry *here*"
    case the plan's stress-test table asks to allow."""
    subject = unknown.get("subject")
    if subject is None:
        return None
    if subject in def_fqns or subject in edge_subjects or subject in scope_nodes:
        return None
    return "subject %r names nothing in defines[]/io_edges and is not a scope" % subject


def gate_negative_entailment(unknown: Dict, edges_by_key: Dict[Tuple[str, str], Dict]) -> Optional[str]:
    """Gate 2 (6.1b). Requires both `subject` and `channel` -- without a
    stated channel there is nothing structural to check the question against.
    Matches on structure only (subject, channel), never on `question`'s
    wording, the same discipline `entail.py` enforces for claims."""
    subject = unknown.get("subject")
    channel = unknown.get("channel")
    if not subject or not channel:
        return None
    edge = edges_by_key.get((subject, channel))
    if edge is None:
        return None
    anchor = edge.get("anchor") or {}
    return "already answered by io_edge %s -> %s (%s) at %s:%s" % (
        edge.get("source"), edge.get("target"), channel,
        anchor.get("file", "?"), anchor.get("line", "?"),
    )


def provenance_state(node: str, task_rows: Optional[Dict[str, Dict]]) -> str:
    """Gate 3. Reads `snapshot_task` (0.12), written since M5.2 by
    `supervisor.dispatch_scope` -- `task_rows` is `{}` only for a node no run
    has touched yet, or for any store predating a real writer. A `folded` row
    means the scope was actively, successfully examined and this question
    still stands -- genuinely `unknown`. An `abandoned` row (M5.2's own
    terminal failure state, after `supervisor.MAX_ATTEMPTS`) means CDP tried
    and could not resolve it."""
    row = (task_rows or {}).get(node)
    if row is None:
        return UNEXAMINED
    state = row.get("state")
    if state == "folded":
        return UNKNOWN
    if state == "abandoned":
        return ABANDONED
    return UNEXAMINED


def gate_needs_valid(unknown: Dict) -> Optional[str]:
    """M4.3 (R12): an unknown must state what would resolve it, from a closed
    vocabulary -- the countermeasure to "cheap to emit, impossible to
    falsify." A missing or unrecognised value is malformed and rejected here,
    at `collect` time, for newly authored unknowns only -- an unknown already
    in the log before this gate existed is grandfathered by `fold`
    (`grandfather_needs`), never rejected retroactively."""
    needs = unknown.get("needs")
    if needs in NEEDS_VALUES:
        return None
    return "needs %r is not one of %s" % (needs, sorted(NEEDS_VALUES))


def gate_patch_unknowns(
    unknowns: Sequence[Dict], node: str, def_fqns: set, edge_subjects: set,
    edges_by_key: Dict[Tuple[str, str], Dict], scope_nodes: set,
    task_rows: Optional[Dict[str, Dict]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """Gates 1-3 (plus M4.3's needs-vocabulary gate) over one patch's
    `unknowns[]`. Returns `(kept, rejected)`; `rejected` entries carry the
    original unknown plus `reason`, for the `collect` report (mirrors how
    schema-invalid patches are reported)."""
    kept: List[Dict] = []
    rejected: List[Dict] = []
    for unknown in unknowns:
        reason = gate_subject_exists(unknown, node, def_fqns, edge_subjects, scope_nodes)
        if reason is None:
            reason = gate_negative_entailment(unknown, edges_by_key)
        if reason is None:
            reason = gate_needs_valid(unknown)
        if reason is not None:
            rejected.append({"node": node, "unknown": unknown, "reason": reason})
            continue
        row = dict(unknown)
        row["provenance_state"] = provenance_state(node, task_rows)
        kept.append(row)
    return kept, rejected


def grandfather_needs(unknowns: List[Dict]) -> List[Dict]:
    """M4.3's migration decision, taken explicitly rather than improvised:
    an unknown with no `needs` -- because it was logged before this gate
    existed, or because it is one of `fold`'s own internally-generated
    unknowns (the superseded-node gap below), which never passes through
    `gate_patch_unknowns` -- is grandfathered as `needs_human` with a marker.
    This is the honest option named in the plan: silently backfilling a
    specific category no one chose would misrepresent old data as if it had
    always answered the question."""
    for row in unknowns:
        if row.get("needs") not in NEEDS_VALUES:
            row["needs"] = "needs_human"
            row["needs_migrated"] = True
    return unknowns


def discharge_unknowns(
    unknowns: List[Dict], claims: Sequence[Dict],
    def_fqns: Set[str], edge_subjects: Set[str], scope_nodes: Set[str],
) -> List[Dict]:
    """R12, the ratchet. Recomputed fresh on every fold, from the *current*
    claim set and structural index -- never from whether some later patch
    happened to restate the question -- which is what makes "silence never
    discharges" true by construction rather than convention:

    - No `subject` (a scope-level gap): always stays `open`. There is
      nothing structural to check it against.
    - `subject` no longer resolves to anything in `defines[]`/`io_edges`/a
      scope: `moot` -- a different outcome from `resolved`, per the plan,
      because nothing answered it; its subject just stopped existing.
    - `subject` (and `channel`, if the unknown names one) matches a claim
      among the currently-folded claims, and that claim is not itself
      `contradicted`: `resolved`, attributed via `resolved_by`. A claim's
      mere presence here already means it survived validate -> verify ->
      entail -> fold (an "adjudicated claim" is exactly what reaches this
      list) -- matching against `contradicted` claims is not "someone
      answered it" only through a discipline that structurally already agrees.
    - Otherwise: `open`.
    """
    by_key: Dict[Tuple[Optional[str], Optional[str]], Dict] = {}
    for claim in claims:
        by_key.setdefault((claim.get("subject"), claim.get("channel")), claim)
    for row in unknowns:
        subject = row.get("subject")
        if not subject:
            row.setdefault("status", OPEN)
            continue
        if subject not in def_fqns and subject not in edge_subjects and subject not in scope_nodes:
            row["status"] = MOOT
            continue
        claim = by_key.get((subject, row.get("channel")))
        if claim is not None and claim.get("verdict") != "contradicted":
            row["status"] = RESOLVED
            row["resolved_by"] = {
                "claim_id": claim.get("id", "?"),
                "author_kind": claim.get("author_kind", "llm"),
                "at_snapshot": claim.get("anchor_verified_at") or claim.get("claim_reviewed_at") or "?",
            }
        else:
            row.setdefault("status", OPEN)
    return unknowns


def cluster_unknowns(unknowns: List[Dict]) -> List[Dict]:
    """Gate 4. Annotates (never removes or merges) `cluster_id`/`cluster_size`
    on unknowns whose `question` *and* `why_unresolved` both normalise
    identically -- requiring both, not just the question, is what keeps this
    from collapsing 40 genuinely distinct unknowns that happen to share
    phrasing (e.g. "why is there no retry here", asked about 40 unrelated call
    sites, each with its own `why_unresolved`) into one cluster: a real
    systemic gap (the same extractor limitation hit in 40 scopes) produces
    identical text for *both* fields, because it is emitted from the same
    template against the same missing signal.

    Operates on the fully-assembled, deduped unknown list at fold time (not
    per-patch in `collect`), because cluster membership is a property of the
    whole current set and must stay current as unknowns come and go across
    folds -- unlike gates 1-3, it never rejects, so it needs no ledger entry.
    """
    groups: Dict[Tuple[str, str], List[Dict]] = {}
    for row in unknowns:
        key = (
            normalise_ws(str(row.get("question", ""))),
            normalise_ws(str(row.get("why_unresolved", ""))),
        )
        groups.setdefault(key, []).append(row)
    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        cluster_id = stable_hash(list(key))
        for row in rows:
            row["cluster_id"] = cluster_id
            row["cluster_size"] = len(rows)
    return unknowns
