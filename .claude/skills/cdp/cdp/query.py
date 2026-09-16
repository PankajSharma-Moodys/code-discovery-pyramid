"""The query layer.

RESEARCH.md §7.2 describes the knowledge graph as "the queryable substrate:
'what breaks if I change this table' is a graph query, not a grep." This module
is that substrate's interface, and it is the reason the whole pipeline is worth
running: documents go stale, a queryable index pinned to a commit does not.

Every answer carries `file:line` citations, and every answer is computed from
verified state — never from a model. `used-by` is the transpose of the import
table, `routes` come from constant-resolved annotations, `table` comes from
migration DDL. Asking a model "where is DServer used?" is asking a question it
answers confidently and wrongly; asking this module is asking for an inversion
of data that was checked.

The queries are deliberately the ones a joiner actually asks, in the order they
ask them: what are the entry points, who owns this table, where does this symbol
go, what is still unknown.

**Nothing here truncates silently.** Every list that can be cut is cut through
`Budget`, which counts the cut and reports it, and every response carries the
commit and state generation it was computed from. The reason is in
`SKILL.md:58-61`: *"Check coverage before saying 'there is no X'. If it is below
100%, absence of a fact means 'not examined', not 'not present'."* A renderer
that prints 6 of 47 config read-sites with no marker manufactures exactly the
false absence that rule exists to prevent — and unlike low coverage it is
invisible, because `coverage` still reads 100%.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .store import SqliteStore, WorkspaceStore
from .util import CdpError, truncate


class Store:
    """Lazily-loaded view over a workspace store.

    Accepts a `WorkspaceStore` directly, or a `Path`/`str` for convenience --
    a bare directory is wrapped as `SqliteStore(dir/index.db)`, the CLI's own
    default (D3, `PHASE/FINDINGS.md`). There is no `FileStore` fallback: every
    production write path constructs `SqliteStore`, so a directory with no
    `index.db` has no state to read, full stop. Reading and writing state
    itself is `store/`'s job (R1); this class only caches rows and exposes
    the properties every renderer and query reads.
    """

    def __init__(self, backend: Union["WorkspaceStore", Path, str]) -> None:
        if isinstance(backend, WorkspaceStore):
            self.backend = backend
        else:
            db = Path(backend) / "index.db"
            if not db.is_file():
                raise CdpError("no CDP state at %s — run `scan` first" % backend)
            self.backend = SqliteStore(db)
        # A view over the store reads the *current* state by default -- the
        # most recent snapshot, not whichever one `_snapshot_id()`'s lazy
        # `id=1` fallback happens to land on. See `use_latest_snapshot`'s
        # docstring for the bug this closes.
        use_latest = getattr(self.backend, "use_latest_snapshot", None)
        if callable(use_latest):
            use_latest()
        self._cache: Dict[str, Any] = {}

    def close(self) -> None:
        close = getattr(self.backend, "close", None)
        if close is not None:
            close()

    def _load(self, name: str, default: Any = None) -> Any:
        if name not in self._cache:
            self._cache[name] = self.backend.read_artifact(name, default)
        return self._cache[name]

    inventory = property(lambda self: self._load("inventory"))
    extraction = property(lambda self: self._load("extract"))
    graph = property(lambda self: self._load("graph"))
    partition = property(lambda self: self._load("partition"))
    xref = property(lambda self: self._load("xref"))
    state = property(lambda self: self._load("state", {"claims": [], "unknowns": [], "conflicts": []}))
    dataflow = property(lambda self: self._load("dataflow", {"edges": [], "paths": [], "process_boundaries": []}))
    manifest = property(lambda self: self._load("manifest", {}))

    def node_of(self, path: str) -> Optional[str]:
        for scope in self.partition["scopes"]:
            if path in scope["files"]:
                return scope["node"]
        return None


# ------------------------------------------------------------------- budget


#: Rows a single response may emit, across every list in it.
#
# A *row* rather than a token count because rows are what CDP can count exactly:
# a token estimate would be a second, softer number that disagrees with the
# first. 200 is chosen to bind on a real monorepo — on `PHASE/TARGET.md`'s
# target, `query table` and `query config` both exceed it — so the elision path
# is exercised by the default rather than only by an unusual flag.
DEFAULT_BUDGET = 200

#: Queries that are never budgeted. `RESEARCH_GRAPHIFY.md §7.3` item 3: these
# are the epistemic safety rails `SKILL.md:58-61` tells the model to check
# before saying "there is no X". Budgeting them would compromise the check that
# detects compromised answers.
UNBUDGETED = frozenset(["stats", "coverage"])


class Budget:
    """A whole-response row allowance, drawn down by every list in the result.

    Not a per-list constant: the eleven hard-coded caps this replaces
    (`[:40]`, `[:25]`, `[:12]`, `[:8]`, `[:6]`, `[:4]`) were unrelated to each
    other and to any budget, so a response could be cut in six places and report
    a total of nothing. One allowance, spent in construction order, means the
    count of what was dropped is a single honest number.

    **Ranked, not head-truncated.** When the allowance binds, the rows dropped
    are the lowest-evidence ones, using the policy `prompts.py:120` already
    applies to the inherited-sigma budget: `-len(evidence)`, then subject. Using
    CDP's own existing idiom means the ranking has one definition rather than
    two. Surviving rows are emitted in their original order — ranking decides
    *what* is dropped, never what the output looks like.
    """

    def __init__(self, rows: Optional[int] = None) -> None:
        self.limit = DEFAULT_BUDGET if rows is None else max(0, int(rows))
        self.spent = 0
        self.elided = 0

    @property
    def fired(self) -> bool:
        return self.elided > 0

    def take(self, rows: Sequence[Any]) -> List[Any]:
        """Return as many of `rows` as the remaining allowance admits."""
        rows = list(rows)
        room = self.limit - self.spent
        if room <= 0:
            self.elided += len(rows)
            return []
        if len(rows) <= room:
            self.spent += len(rows)
            return rows
        self.spent += room
        self.elided += len(rows) - room
        keep = sorted(sorted(range(len(rows)), key=lambda i: _rank(rows[i], i))[:room])
        return [rows[i] for i in keep]

    def note(self) -> Optional[str]:
        """The stated reason, when the allowance admitted nothing at all.

        A zero-row answer and a zero-budget answer look identical otherwise, and
        the difference between "there is no such thing" and "you asked for no
        rows" is the whole point of this module.
        """
        if self.limit == 0:
            return (
                "--budget 0 admits no rows. Every row of this answer was elided; "
                "this is not evidence that there are none."
            )
        if self.fired and self.spent == 0:
            return (
                "--budget %d was exhausted before this list. Every row of it was "
                "elided; this is not evidence that there are none." % self.limit
            )
        return None


def _rank(row: Any, index: int) -> Tuple:
    """`(-evidence, subject, id, index)` — total, deterministic, no ties.

    The stress test that forces the last two components: two rows with equal
    evidence and equal subject must still order the same way on every run, or
    the determinism gate fails intermittently — the worst failure mode to debug,
    because a re-run hides it.
    """
    return (-_evidence_count(row), _subject_of(row), _identity(row), index)


def _evidence_count(row: Any) -> int:
    if not isinstance(row, dict):
        return 0
    for key in ("evidence", "sites", "defined_at", "anchors", "hops", "candidates"):
        value = row.get(key)
        if isinstance(value, list):
            return len(value)
    if isinstance(row.get("used_by_count"), int):
        return row["used_by_count"]
    return 1 if (row.get("anchor") or row.get("at")) else 0


def _subject_of(row: Any) -> str:
    if not isinstance(row, dict):
        return str(row)
    for key in ("subject", "fqn", "table", "key", "path", "route", "name",
                "question", "trigger", "target", "shared", "at"):
        value = row.get(key)
        if isinstance(value, str):
            return value
    return ""


def _identity(row: Any) -> str:
    if not isinstance(row, dict):
        return str(row)
    for key in ("id", "file", "module", "channel", "verb"):
        value = row.get(key)
        if isinstance(value, str):
            return value
    return ""


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


# --------------------------------------------------------------- formatting


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


def _more(indent: str, total: int, shown: Sequence[Any]) -> List[str]:
    """The `"... N more"` marker, generalised from `q_symbol`'s `used_by`.

    That one site was the only honest truncation in the module
    (`RESEARCH_GRAPHIFY.md §10` marks it "the pattern to generalise"). Every
    list that can be cut now emits it, and a list that was not cut emits
    nothing, so the marker's presence means something.
    """
    missing = total - len(shown)
    return ["%s... %d more (elided by the budget)" % (indent, missing)] if missing > 0 else []


# ------------------------------------------------------------------ queries


def q_symbol(store: Store, name: str, budget: Optional[Budget] = None) -> Dict:
    """Definition sites, used-by, and collisions for a symbol.

    Accepts a fully-qualified name or a suffix — `DServer` finds
    `rms.unifiedstore.sqlpool.common.model.domain.DServer` — because nobody
    types the FQN.
    """
    budget = budget or Budget()
    xref = store.xref
    exact = xref["symbols"].get(name)
    keys = [name] if exact else [
        k for k in xref["symbols"] if k == name or k.rsplit(".", 1)[-1] == name or _matches(k, name)
    ]
    keys = sorted(keys, key=lambda k: (k.rsplit(".", 1)[-1] != name, len(k)))
    keys = budget.take(keys)
    if not keys:
        return _finish({"query": "symbol", "name": name, "found": []}, store, budget)

    out = []
    for key in keys:
        entry = xref["symbols"][key]
        users = xref["used_by"].get(key, [])
        claims = [c for c in store.state["claims"] if c.get("subject") == key or _matches(c.get("statement", ""), key.rsplit(".", 1)[-1])]
        out.append(
            {
                "fqn": key,
                "kind": entry["kind"],
                "visibility": entry["visibility"],
                "modules": entry["modules"],
                "value": entry.get("value"),
                "defined_at": [cite(s["anchor"]) for s in entry["sites"]],
                "collision": bool(entry.get("collision")),
                # The true total, kept alongside the budgeted list, so the
                # renderer states "used by 47 site(s)" even when it shows 12.
                "used_by_count": len(users),
                "used_by": [
                    {"module": u["module"], "at": cite(u["anchor"])}
                    for u in budget.take(users)
                ],
                "claims": budget.take(claims),
            }
        )
    return _finish({"query": "symbol", "name": name, "found": out}, store, budget)


def q_file(store: Store, path: str, budget: Optional[Budget] = None) -> Dict:
    budget = budget or Budget()
    files = [f for f in store.inventory["files"] if f["path"] == path or _matches(f["path"], path)]
    if not files:
        return _finish({"query": "file", "path": path, "found": []}, store, budget)
    out = []
    for entry in budget.take(sorted(files, key=lambda f: (f["path"] != path, len(f["path"])))):
        rel = entry["path"]
        info = store.extraction["files"].get(rel, {})
        defines = [d for d in store.extraction["defines"] if d["file"] == rel]
        edges = [e for e in store.extraction["io_edges"] if e["file"] == rel]
        claims = [
            c for c in store.state["claims"]
            if any(a.get("file") == rel for a in c.get("evidence", []))
        ]
        out.append(
            {
                "path": rel,
                "module": entry["module"],
                "node": store.node_of(rel),
                "language": entry["language"],
                "role": entry["role"],
                "loc": entry["loc"],
                "package": info.get("package"),
                "primary": info.get("primary"),
                "signals": info.get("signals", []),
                "defines_count": len(defines),
                "defines": [
                    {"fqn": d["fqn"], "kind": d["kind"], "at": cite(d["anchor"])}
                    for d in budget.take(defines)
                ],
                "io_edges_count": len(edges),
                "io_edges": [
                    {"channel": e["channel"], "target": e["target"], "at": cite(e["anchor"])}
                    for e in budget.take(edges)
                ],
                "claims": budget.take(claims),
            }
        )
    return _finish({"query": "file", "path": path, "found": out}, store, budget)


def q_module(store: Store, name: str, budget: Optional[Budget] = None) -> Dict:
    budget = budget or Budget()
    modules = [m for m in store.inventory["modules"] if m["name"] == name or _matches(m["name"], name)]
    if not modules:
        return _finish({"query": "module", "name": name, "found": []}, store, budget)
    graph = store.graph
    out = []
    for module in budget.take(modules):
        key = module["name"]
        claims = [c for c in store.state["claims"] if _claim_module(c, store) == key]
        out.append(
            {
                "name": key,
                "files": module["files"],
                "loc": module["loc"],
                "on_disk": module.get("on_disk"),
                "generated_suspect": module.get("generated_suspect", False),
                "by_language": module["by_language"],
                "by_role": module["by_role"],
                "level": store.manifest.get("module_level", {}).get(key),
                "depends_on": [
                    {"module": e["to"], "weight": e["weight"]}
                    for e in graph["observed"] if e["from"] == key
                ],
                "depended_on_by": [
                    {"module": e["from"], "weight": e["weight"]}
                    for e in graph["observed"] if e["to"] == key
                ],
                "declared_only": [
                    e["to"] for e in graph["divergence"]["declared_not_observed"] if e["from"] == key
                ],
                "observed_only": [
                    e["to"] for e in graph["divergence"]["observed_not_declared"] if e["from"] == key
                ],
                "scopes": [s["node"] for s in store.partition["scopes"] if s["module"] == key],
                # The tally is over *every* claim, not the budgeted list: a
                # count that shrinks with the budget would understate the module.
                "claims_count": len(claims),
                "claims_by_kind": _tally(c["kind"] for c in claims),
                "claims": budget.take(claims),
            }
        )
    return _finish({"query": "module", "name": name, "found": out}, store, budget)


def q_routes(store: Store, pattern: Optional[str] = None,
             budget: Optional[Budget] = None) -> Dict:
    budget = budget or Budget()
    routes = store.xref["routes"] + store.xref["unresolved_routes"]
    if pattern:
        routes = [r for r in routes if _matches(r["route"], pattern) or _matches(r["verb"], pattern)]
    return _finish(
        {
            "query": "routes",
            "count": len(routes),
            "routes": [
                {
                    "verb": r["verb"],
                    "route": r["route"],
                    "handler": r["handler"],
                    "module": r["module"],
                    "declared_via": r.get("symbolic"),
                    "unresolved_constants": r.get("unresolved_constants", []),
                    "evidence": [cite(a) for a in r["evidence"]],
                }
                for r in budget.take(routes)
            ],
        },
        store,
        budget,
    )


def q_table(store: Store, name: Optional[str] = None,
            budget: Optional[Budget] = None) -> Dict:
    """Who owns, writes and reads each table.

    "What breaks if I change this table" reduces to the union of the three
    lists below, and every entry carries the line that put it there.

    `RESEARCH_GRAPHIFY.md §10` calls this and `q_config` the worst of the silent
    truncations, and it is right: "who writes this table" is exactly the
    question where a partial list reads as a complete one and a wrong
    blast-radius conclusion follows directly from it.
    """
    budget = budget or Budget()
    buckets: Dict[str, Dict[str, List[Dict]]] = {}
    for edge in store.extraction["io_edges"]:
        if not edge["target"].startswith("table:"):
            continue
        table = edge["target"][len("table:") :]
        if name and not _matches(table, name):
            continue
        slot = buckets.setdefault(table, {"schema_own": [], "persist": [], "read": []})
        if edge["channel"] in slot:
            slot[edge["channel"]].append(edge)

    out = []
    for table in budget.take(sorted(buckets)):
        slot = buckets[table]
        evidence = slot["persist"] + slot["read"]
        out.append(
            {
                "table": table,
                "schema_owned_by": sorted({e["module"] for e in slot["schema_own"]}),
                "migration_count": len(slot["schema_own"]),
                "migrations": [cite(e["anchor"]) for e in budget.take(slot["schema_own"])],
                "written_by": sorted({e["source"] for e in slot["persist"]}),
                "read_by": sorted({e["source"] for e in slot["read"]}),
                "evidence_count": len(evidence),
                "evidence": [cite(e["anchor"]) for e in budget.take(evidence)],
            }
        )
    return _finish(
        {"query": "table", "name": name, "count": len(buckets), "tables": out},
        store, budget,
    )


def q_config(store: Store, key: Optional[str] = None,
             budget: Optional[Budget] = None) -> Dict:
    budget = budget or Budget()
    rows: Dict[str, Dict] = {}
    for row in store.extraction["defines"]:
        if row["kind"] != "config_key" or not row["fqn"].startswith("config:"):
            continue
        name = row["fqn"][len("config:") :]
        if key and not _matches(name, key):
            continue
        slot = rows.setdefault(name, {"key": name, "declared": [], "read": [], "values": []})
        slot["declared"].append(cite(row["anchor"]))
        if row.get("value"):
            slot["values"].append(row["value"])
    for edge in store.extraction["io_edges"]:
        if edge["channel"] != "config_read" or not edge["target"].startswith("config:"):
            continue
        name = edge["target"][len("config:") :]
        if key and not _matches(name, key):
            continue
        if edge["source"].startswith("config-file:"):
            continue
        rows.setdefault(name, {"key": name, "declared": [], "read": [], "values": []})["read"].append(
            {"by": edge["source"], "at": cite(edge["anchor"])}
        )

    out = []
    for name in budget.take(sorted(rows)):
        slot = rows[name]
        out.append(
            {
                "key": name,
                "values": slot["values"],
                "declared_count": len(slot["declared"]),
                "declared": budget.take(slot["declared"]),
                "read_count": len(slot["read"]),
                "read": budget.take(slot["read"]),
            }
        )
    return _finish({"query": "config", "count": len(rows), "keys": out}, store, budget)


def q_paths(
    store: Store,
    frm: Optional[str] = None,
    to: Optional[str] = None,
    budget: Optional[Budget] = None,
) -> Dict:
    budget = budget or Budget()
    paths = store.dataflow["paths"]
    if frm:
        paths = [p for p in paths if _matches(p["source"], frm) or _matches(p["trigger"], frm)]
    if to:
        paths = [p for p in paths if _matches(p["sink"], to)]
    return _finish(
        {
            "query": "paths",
            "count": len(paths),
            "paths": [
                {
                    "trigger": p["trigger"],
                    "modules": p["modules"],
                    "representation_chain": p["representation_chain"],
                    "confidence": p["min_confidence"],
                    "hops": [
                        {
                            "from": h["from"].rsplit(".", 1)[-1],
                            "to": h["to"].rsplit(".", 1)[-1],
                            "channel": h["channel"],
                            "at": cite(h["anchor"]),
                        }
                        for h in p["hops"]
                    ],
                }
                for p in budget.take(paths)
            ],
        },
        store,
        budget,
    )


def q_search(store: Store, text: str, budget: Optional[Budget] = None) -> Dict:
    budget = budget or Budget()
    claims = [
        c for c in store.state["claims"]
        if _matches(c.get("subject", ""), text) or _matches(c.get("statement", ""), text)
    ]
    symbols = [k for k in store.xref["symbols"] if _matches(k, text)]
    unknowns = [u for u in store.state["unknowns"] if _matches(u.get("question", ""), text)]
    files = [f["path"] for f in store.inventory["files"] if _matches(f["path"], text)]
    return _finish(
        {
            "query": "search",
            "text": text,
            "counts": {
                "claims": len(claims), "symbols": len(symbols),
                "unknowns": len(unknowns), "files": len(files),
            },
            "claims": budget.take(claims),
            "symbols": budget.take(sorted(symbols, key=len)),
            "unknowns": budget.take(unknowns),
            "files": budget.take(sorted(files, key=len)),
        },
        store,
        budget,
    )


def q_claims(
    store: Store,
    kind: Optional[str] = None,
    module: Optional[str] = None,
    subject: Optional[str] = None,
    budget: Optional[Budget] = None,
) -> Dict:
    budget = budget or Budget()
    claims = store.state["claims"]
    if kind:
        claims = [c for c in claims if c.get("kind") == kind]
    if subject:
        claims = [c for c in claims if _matches(c.get("subject", ""), subject)]
    if module:
        claims = [c for c in claims if _matches(_claim_module(c, store) or "", module)]
    return _finish(
        {"query": "claims", "count": len(claims), "claims": budget.take(claims)},
        store, budget,
    )


def q_unknowns(store: Store, module: Optional[str] = None,
               budget: Optional[Budget] = None) -> Dict:
    budget = budget or Budget()
    unknowns = store.state["unknowns"]
    if module:
        unknowns = [u for u in unknowns if _matches(str(u.get("source_node", "")), module)]
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


# -------------------------------------------------------------------- trace


#: What `trace` promises and, more importantly, what it does not.
TRACE_CAVEAT = (
    "This is a reading list, not an answer. CDP has no parameter or branch model: "
    "it collapses a wide grep into a small cited read whose completeness is stated "
    "by the `elided` count below — zero means the list is complete, anything else "
    "means it is qualified. Hops marked `medium` come from the import table: an "
    "import proves that a file *can* reach a symbol, not that it does."
)


def q_trace(
    store: Store,
    entry: str,
    max_hops: int = 8,
    budget: Optional[Budget] = None,
) -> Dict:
    """The minimal cited file set needed to answer a question about an entry point.

    Composes three things CDP already has and never joined: the `dataflow.py`
    traversal, `resolve.py`'s `used_by` transpose, and the budget above. The
    join is the product: today a consumer answers "what do I read to understand
    `POST /v1/settle`?" by running `routes`, then `symbol`, then `paths`, and
    doing the set union by hand.

    Every file carries the edge that put it there. A file with no justifying
    edge is not in the list, which is the only reason the list can be called
    minimal.
    """
    budget = budget or Budget()
    resolved = _resolve_entry(store, entry)
    if not resolved:
        return _finish(
            {
                "query": "trace",
                "entry": entry,
                "found": False,
                "why": (
                    "No route, dataflow source or defined symbol matches %r. It may be "
                    "in a scope this run did not cover — check `query coverage` before "
                    "concluding it does not exist." % entry
                ),
                "caveat": TRACE_CAVEAT,
                "files": [],
                "unknowns": [],
            },
            store, budget,
        )

    adjacency: Dict[str, List[Dict]] = {}
    for edge in store.dataflow["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge)

    # Entry points are named by whatever recorded them — a route as
    # `Class#method`, a dataflow source as its own node — while the edge graph
    # is keyed on the file's primary symbol. Left unnormalised, a real endpoint
    # on the validation target traced to exactly one file, which reads as "this
    # endpoint touches nothing" rather than "the key did not match".
    _pivot(store, resolved, adjacency)
    reached, exhausted = _walk(resolved["node"], adjacency, max_hops)
    callers = store.xref["used_by"].get(resolved["node"], [])

    rows = _trace_files(store, resolved, reached, callers)
    # The entry point itself is never budgeted away. `--budget 0` must return the
    # entry and a count of what it dropped; an empty set with no explanation
    # reads as "nothing here", which is the one thing trace must never say.
    head, rest = rows[:1], rows[1:]
    files = head + budget.take(rest)
    paths_shown = {row["file"] for row in files}

    unknowns = budget.take([
        u for u in store.state.get("unknowns", [])
        if (u.get("anchor") or {}).get("file") in paths_shown
        or any(_matches(u.get("question", ""), n.rsplit(".", 1)[-1]) for n in reached)
    ])

    return _finish(
        {
            "query": "trace",
            "entry": entry,
            "found": True,
            "resolved_as": resolved,
            "max_hops": max_hops,
            # A walk that ran out of hops has not finished. Reporting it as
            # completion is how a cycle turns into a confident wrong answer.
            "hops_exhausted": exhausted,
            # Why the trail stops, stated. An entry point with no outgoing edge
            # renders as a one-file list, and a one-file list with no
            # explanation reads as "this touches nothing" rather than as
            # "CDP found no edge leaving here".
            "trail": (
                "%d node(s) reachable from %s" % (len(reached), resolved["node"])
                if reached
                else "No dataflow edge leaves %s, so the trail stops at its "
                     "defining file. That is an absence of an extracted edge, not "
                     "evidence that nothing is called: check `query coverage`, and "
                     "note that runtime wiring (DI, reflection, framework "
                     "registration) produces no import to follow."
                     % resolved["node"]
            ),
            "file_count": len(rows),
            "files": files,
            "unknowns": unknowns,
            "caveat": TRACE_CAVEAT,
        },
        store, budget,
    )


def _pivot(store: Store, resolved: Dict, adjacency: Dict[str, List[Dict]]) -> None:
    """Move `resolved["node"]` onto a key the edge graph actually has.

    Tries the member's owning class, then the primary symbol of the file the
    entry point was cited in. Records what it did in `resolved["pivoted_from"]`
    rather than silently substituting a different subject.
    """
    node = resolved["node"]
    if node in adjacency:
        return
    candidates: List[str] = []
    if "#" in node:
        candidates.append(node.split("#", 1)[0])
    at = resolved.get("at") or ""
    primary = store.extraction["files"].get(at.rsplit(":", 1)[0], {}).get("primary")
    if primary:
        candidates.append(primary)
    for candidate in candidates:
        if candidate in adjacency:
            resolved["pivoted_from"] = node
            resolved["node"] = candidate
            return


def _resolve_entry(store: Store, entry: str) -> Optional[Dict]:
    """Route path, dataflow source, or symbol — in that order of specificity."""
    for route in store.xref["routes"] + store.xref["unresolved_routes"]:
        if route["route"] == entry or _matches(route["route"], entry):
            # A route handler is recorded as `Class#method`, while the dataflow
            # graph is keyed on the file's primary symbol. Walking from the raw
            # handler string finds no adjacency and silently returns a one-file
            # trace, which reads as "this endpoint touches nothing".
            info = store.extraction["files"].get(route["file"], {})
            node = info.get("primary") or route["handler"].split("#", 1)[0]
            return {
                "kind": "route",
                "node": node,
                "handler": route["handler"],
                "label": "%s %s" % (route["verb"], route["route"]),
                "channel": "http_in",
                "module": route["module"],
                "at": cite(route["evidence"][0]) if route["evidence"] else None,
            }
    for source in store.dataflow.get("sources", []):
        if source["node"] == entry or source["trigger"] == entry or _matches(source["node"], entry):
            return {
                "kind": "source",
                "node": source["node"],
                "label": source["trigger"],
                "channel": source["channel"],
                "module": source["module"],
                "at": cite(source["anchor"]),
            }
    symbols = store.xref["symbols"]
    keys = [k for k in symbols if k == entry or k.rsplit(".", 1)[-1] == entry]
    keys = keys or [k for k in symbols if _matches(k, entry)]
    if keys:
        key = sorted(keys, key=lambda k: (len(k), k))[0]
        sites = symbols[key]["sites"]
        return {
            "kind": "symbol",
            "node": key,
            "label": key,
            "channel": "defines",
            "module": sites[0]["module"] if sites else None,
            "at": cite(sites[0]["anchor"]) if sites else None,
        }
    return None


def _walk(
    start: str, adjacency: Dict[str, List[Dict]], max_hops: int
) -> Tuple[Dict[str, Dict], bool]:
    """Breadth-first from `start`, keeping the first edge that reached each node.

    First-reaching rather than shortest-overall because the question is *why is
    this file in my reading list*, and the answer should be the shortest
    justification. Deterministic: the frontier is sorted at every level.
    """
    reached: Dict[str, Dict] = {}
    frontier = [start]
    seen = {start}
    hops = 0
    while frontier and hops < max_hops:
        hops += 1
        nxt: List[str] = []
        for node in frontier:
            for edge in sorted(
                adjacency.get(node, ()),
                key=lambda e: (e["channel"], e["target"], e["anchor"]["file"], e["anchor"]["line"]),
            ):
                target = edge["target"]
                if target in seen:
                    continue
                seen.add(target)
                reached[target] = edge
                nxt.append(target)
        frontier = nxt
    return reached, bool(frontier)


def _trace_files(
    store: Store, resolved: Dict, reached: Dict[str, Dict], callers: Sequence[Dict]
) -> List[Dict]:
    """One row per file, each with the single edge that justified including it.

    Deduplicated on the file, because a reading list that names the same file
    three times for three edges is longer than the grep it replaced.
    """
    rows: List[Dict] = []
    seen: Set[str] = set()

    def add(path: Optional[str], module: Optional[str], why: str,
            at: Optional[str], confidence: str) -> None:
        if not path or path in seen:
            return
        seen.add(path)
        rows.append({"file": path, "module": module, "why": why, "at": at,
                     "confidence": confidence})

    entry_file = (resolved.get("at") or "").rsplit(":", 1)[0] or None
    add(entry_file, resolved.get("module"),
        "entry point (%s) %s" % (resolved["channel"], resolved["label"]),
        resolved.get("at"), "high")

    for target in sorted(reached):
        edge = reached[target]
        add(edge["anchor"]["file"], edge.get("module"),
            "%s --%s--> %s" % (edge["source"].rsplit(".", 1)[-1], edge["channel"],
                               target.rsplit(".", 1)[-1]),
            cite(edge["anchor"]), edge.get("confidence", "medium"))
        for site in store.xref["symbols"].get(target, {}).get("sites", []):
            add(site["file"], site["module"], "defines %s" % target,
                cite(site["anchor"]), "high")

    for caller in callers:
        add(caller["file"], caller["module"],
            "references %s" % resolved["node"].rsplit(".", 1)[-1],
            cite(caller["anchor"]), "high")
    return rows


def q_stats(store: Store) -> Dict:
    """Never budgeted (`UNBUDGETED`). Takes no `budget` argument at all, so a
    future edit cannot quietly start honouring one."""
    inv = store.inventory
    state = store.state
    # The build's own name for itself, when it differs from the directory. On
    # the validation target `settings.gradle` says `rootProject.name = 'spm'`
    # while every directory is `sql-pool-*`, and that mismatch is the first
    # thing a newcomer trips over -- so it belongs in the first thing they run.
    build_name = None
    for row in store.extraction["defines"]:
        if row["fqn"] == "build:rootProject.name":
            build_name = row.get("value")
            break
    return _finish({
        "query": "stats",
        "repo": inv["repo_name"],
        "build_name": build_name if build_name and build_name != inv["repo_name"] else None,
        "head": inv["head"],
        "census": inv["counts"],
        "inventory_source": inv["source"],
        "languages": inv["by_language"],
        "roles": inv["by_role"],
        "modules": len(inv["modules"]),
        "scopes": len(store.partition["scopes"]),
        "symbols": len(store.xref["symbols"]),
        "routes": len(store.xref["routes"]),
        "claims": len(state.get("claims", [])),
        "claims_by_kind": _tally(c["kind"] for c in state.get("claims", [])),
        "claims_by_confidence": _tally(c.get("confidence", "?") for c in state.get("claims", [])),
        "unknowns": len(state.get("unknowns", [])),
        "conflicts": len(state.get("conflicts", [])),
        "coverage": state.get("coverage", {}),
        "resolution": store.xref["resolution"],
        "divergence": {
            "declared": store.graph["divergence"]["declared_edges"],
            "observed": store.graph["divergence"]["observed_edges"],
            "declared_not_observed": store.graph["divergence"]["declared_not_observed"],
            "observed_not_declared": store.graph["divergence"]["observed_not_declared"],
        },
        "declared_ambiguous": store.graph.get("declared_ambiguous", []),
    }, store, None)


def q_coverage(store: Store) -> Dict:
    """Never budgeted (`UNBUDGETED`). See `q_stats`."""
    state = store.state
    coverage = state.get("coverage", {})
    return _finish({
        "query": "coverage",
        "coverage": coverage,
        "nodes": state.get("nodes", {}),
        "node_errors": state.get("node_errors", {}),
        "warning": (
            None
            if coverage.get("fraction", 0) >= 0.999
            else "This run covers %.1f%% of tracked files. Treat every absent fact as unexamined, "
            "not as absent from the codebase." % (100 * coverage.get("fraction", 0))
        ),
    }, store, None)


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


# ------------------------------------------------------------------ rendering


def render(result: Dict) -> str:
    """Text rendering of a result that has *already* been budgeted.

    Truncation happens in exactly one place — `Budget.take`, inside the query —
    so this function renders every row it is handed. An earlier version also cut
    here, with smaller and unrelated constants (`defines[:40]` in the JSON,
    `[:20]` on screen), which meant `--json` and the text output disagreed about
    what the answer was and neither said so.
    """
    kind = result.get("query")
    lines: List[str] = []

    if kind == "symbol":
        if not result["found"]:
            lines.append("No symbol matching %r. Try `search %s`."
                         % (result["name"], result["name"]))
        for entry in result["found"]:
            lines.append("%s  [%s %s]" % (entry["fqn"], entry["visibility"], entry["kind"]))
            if entry.get("value") is not None:
                lines.append("  value: %r" % entry["value"])
            lines.append("  defined in %s at %s" % (", ".join(entry["modules"]), ", ".join(entry["defined_at"])))
            if entry["collision"]:
                lines.append("  ! declared at more than one site; no winner is picked (§6.4)")
            lines.append("  used by %d site(s)" % entry["used_by_count"])
            for use in entry["used_by"]:
                lines.append("    %-24s %s" % (use["module"], use["at"]))
            if entry["used_by_count"] > len(entry["used_by"]):
                lines.append("    ... %d more (elided by the budget)"
                             % (entry["used_by_count"] - len(entry["used_by"])))
            for claim in entry["claims"]:
                lines.extend(_claim_lines(claim))
            lines.append("")

    elif kind == "file":
        if not result["found"]:
            lines.append("No file matching %r." % result["path"])
        for entry in result["found"]:
            lines.append("%s" % entry["path"])
            lines.append(
                "  module %s | node %s | %s | %s | %d loc"
                % (entry["module"], entry["node"], entry["language"], entry["role"], entry["loc"])
            )
            if entry.get("package"):
                lines.append("  package %s" % entry["package"])
            if entry["signals"]:
                lines.append("  signals: %s" % ", ".join(entry["signals"]))
            if entry["defines"]:
                lines.append("  defines:")
                for d in entry["defines"]:
                    lines.append("    %-9s %-60s %s" % (d["kind"], truncate(d["fqn"], 60), d["at"]))
                lines.extend(_more("    ", entry["defines_count"], entry["defines"]))
            if entry["io_edges"]:
                lines.append("  edges:")
                for e in entry["io_edges"]:
                    lines.append("    %-16s %-50s %s" % (e["channel"], truncate(e["target"], 50), e["at"]))
                lines.extend(_more("    ", entry["io_edges_count"], entry["io_edges"]))
            for claim in entry["claims"]:
                lines.extend(_claim_lines(claim))
            lines.append("")

    elif kind == "module":
        if not result["found"]:
            lines.append("No module matching %r." % result["name"])
        for entry in result["found"]:
            lines.append("%s  (%d files, %d loc%s)" % (
                entry["name"], entry["files"], entry["loc"],
                ", %d on disk" % entry["on_disk"] if entry.get("on_disk") else ""))
            if entry["generated_suspect"]:
                lines.append("  ! generated at build time; described by contract, not read (§6.7)")
            lines.append("  languages: %s" % ", ".join("%s %d" % kv for kv in entry["by_language"].items()))
            lines.append("  depends on:   %s" % (", ".join(
                "%s(%d)" % (d["module"], d["weight"]) for d in entry["depends_on"]) or "-"))
            lines.append("  depended on:  %s" % (", ".join(
                "%s(%d)" % (d["module"], d["weight"]) for d in entry["depended_on_by"]) or "-"))
            if entry["declared_only"]:
                lines.append("  ! declared but never imported: %s" % ", ".join(entry["declared_only"]))
            if entry["observed_only"]:
                lines.append("  ! imported but not declared: %s" % ", ".join(entry["observed_only"]))
            lines.append("  scopes: %s" % ", ".join(entry["scopes"]))
            lines.append("  claims: %s" % ", ".join("%s %d" % kv for kv in entry["claims_by_kind"].items()))
            for claim in entry["claims"]:
                lines.extend(_claim_lines(claim))
            lines.extend(_more("  ", entry["claims_count"], entry["claims"]))
            lines.append("")

    elif kind == "routes":
        lines.append("%d route(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["routes"]))
        for r in result["routes"]:
            note = ""
            if r["unresolved_constants"]:
                note = "  ! constant unresolved: " + ", ".join(r["unresolved_constants"])
            elif r["declared_via"]:
                note = "  (declared as %s)" % r["declared_via"]
            lines.append("  %-7s %-40s %s" % (r["verb"], r["route"], r["handler"].rsplit(".", 1)[-1]))
            lines.append("          %s%s" % (" ".join(r["evidence"]), note))

    elif kind == "table":
        lines.append("%d table(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["tables"]))
        for t in result["tables"]:
            lines.append("  %s" % t["table"])
            lines.append("    schema owned by: %s" % (", ".join(t["schema_owned_by"]) or "(no migration found)"))
            if t["migrations"]:
                lines.append("    migrations: %s" % " ".join(t["migrations"]))
                lines.extend(_more("    ", t["migration_count"], t["migrations"]))
            if t["written_by"]:
                lines.append("    written by: %s" % ", ".join(s.rsplit(".", 1)[-1] for s in t["written_by"]))
            if t["read_by"]:
                lines.append("    read by:    %s" % ", ".join(s.rsplit(".", 1)[-1] for s in t["read_by"]))
            if t["evidence"]:
                lines.append("    %s" % " ".join(t["evidence"]))
                lines.extend(_more("    ", t["evidence_count"], t["evidence"]))

    elif kind == "config":
        lines.append("%d config key(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["keys"]))
        for c in result["keys"]:
            lines.append("  %s%s" % (c["key"], "  = %r" % c["values"][0] if c["values"] else ""))
            if c["declared"]:
                lines.append("    declared: %s" % " ".join(c["declared"]))
                lines.extend(_more("    ", c["declared_count"], c["declared"]))
            for r in c["read"]:
                lines.append("    read by %-50s %s" % (truncate(r["by"], 50), r["at"]))
            lines.extend(_more("    ", c["read_count"], c["read"]))

    elif kind == "paths":
        lines.append("%d traced path(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["paths"]))
        for p in result["paths"]:
            lines.append("  %s   [%s]" % (p["trigger"], p["confidence"]))
            for h in p["hops"]:
                lines.append("    --%s--> %-40s %s" % (h["channel"], h["to"], h["at"]))
            if p["representation_chain"]:
                lines.append("    representations: %s" % " -> ".join(
                    r.rsplit(".", 1)[-1] for r in p["representation_chain"]))

    elif kind == "trace":
        if not result["found"]:
            lines.append("No trace for %r." % result["entry"])
            lines.append("  %s" % result["why"])
        else:
            r = result["resolved_as"]
            lines.append("entry  %s   [%s]" % (r["label"], r["channel"]))
            lines.append("       %s  %s" % (r["node"], r.get("at") or "-"))
            lines.append("")
            lines.append("read %d of %d cited file(s):" % (len(result["files"]), result["file_count"]))
            for row in result["files"]:
                lines.append("  %s" % row["at"] or row["file"])
                lines.append("      %s  [%s]" % (row["why"], row["confidence"]))
            lines.extend(_more("  ", result["file_count"], result["files"]))
            lines.append("")
            lines.append("  %s" % result["trail"])
            if result["hops_exhausted"]:
                lines.append("")
                lines.append("  ! the walk stopped at --max-hops %d with the frontier still "
                             "open; the trail continues beyond this list."
                             % result["max_hops"])
            if result["unknowns"]:
                lines.append("")
                lines.append("unknowns on this path:")
                for u in result["unknowns"]:
                    lines.append("  %s" % u["question"])
            lines.append("")
            lines.append(result["caveat"])

    elif kind == "search":
        counts = result["counts"]
        if result["symbols"]:
            lines.append("symbols:")
            lines += ["  " + s for s in result["symbols"]]
            lines.extend(_more("  ", counts["symbols"], result["symbols"]))
        if result["files"]:
            lines.append("files:")
            lines += ["  " + f for f in result["files"]]
            lines.extend(_more("  ", counts["files"], result["files"]))
        if result["claims"]:
            lines.append("claims:")
            for claim in result["claims"]:
                lines.extend(_claim_lines(claim))
            lines.extend(_more("  ", counts["claims"], result["claims"]))
        if result["unknowns"]:
            lines.append("unknowns:")
            for u in result["unknowns"]:
                lines.append("  %s" % u["question"])
            lines.extend(_more("  ", counts["unknowns"], result["unknowns"]))
        if not lines:
            lines.append("Nothing matched %r." % result["text"])

    elif kind == "claims":
        lines.append("%d claim(s)" % result["count"])
        lines.extend(_more("  ", result["count"], result["claims"]))
        for claim in result["claims"]:
            lines.append("  %-12s %s" % (claim["kind"], truncate(claim["subject"], 70)))
            lines.extend(_claim_lines(claim, indent="    "))

    elif kind == "unknowns":
        lines.append("%d unknown(s) — the tribal-knowledge inventory" % result["count"])
        lines.extend(_more("  ", result["count"],
                           [r for rows in result["by_node"].values() for r in rows]))
        for node, rows in result["by_node"].items():
            lines.append("  %s" % node)
            for row in rows:
                lines.append("    %s" % row["question"])
                lines.append("      why: %s" % row["why_unresolved"])
                if row.get("needs"):
                    lines.append("      needs: %s%s" % (
                        row["needs"], " (migrated)" if row.get("needs_migrated") else ""))
                status = row.get("status", "open")
                if status != "open":
                    rb = row.get("resolved_by") or {}
                    detail = ("  resolved_by=%s (%s @ %s)" % (
                        rb.get("claim_id"), rb.get("author_kind"), rb.get("at_snapshot"))
                        if status == "resolved" else "")
                    lines.append("      status: %s%s" % (status, detail))
                if row.get("anchor"):
                    lines.append("      %s" % cite(row["anchor"]))

    elif kind == "conflicts":
        lines.append("%d conflict(s), %d near-miss(es)" % (result["count"], result["near_miss_count"]))
        lines.extend(_more("  ", result["count"], result["conflicts"]))
        lines.extend(_more("  ", result["near_miss_count"], result["near_misses"]))
        for c in result["conflicts"]:
            lines.append("  %s (%s) — %s" % (c["subject"], c["kind"], c["resolved_by"] or "CONTESTED"))
            for pos in c["positions"]:
                lines.append("    %s%s  by %s  (%d anchors)" % (
                    pos["values"], "  <-- kept" if pos["won"] else "",
                    ", ".join(pos["nodes"]), pos["evidence_count"]))
        for n in result["near_misses"]:
            lines.append("  ~ %s: %d wordings, same enums" % (n["subject"], len(n["statements"])))

    elif kind == "stats":
        c = result["census"]
        lines += [
            "repo        %s @ %s%s" % (
                result["repo"], result["head"][:12],
                "   (the build calls itself '%s')" % result["build_name"]
                if result.get("build_name") else ""),
            "census      %d tracked / %d on disk (%.1fx) [%s]"
            % (c["tracked"], c["on_disk"], c["ratio"], result["inventory_source"]),
            "modules     %d in %d scopes" % (result["modules"], result["scopes"]),
            "symbols     %d" % result["symbols"],
            "routes      %d" % result["routes"],
            "claims      %d  (%s)" % (result["claims"], ", ".join("%s %d" % kv for kv in result["claims_by_kind"].items())),
            "confidence  %s" % ", ".join("%s %d" % kv for kv in result["claims_by_confidence"].items()),
            "unknowns    %d" % result["unknowns"],
            "conflicts   %d" % result["conflicts"],
            "coverage    %.1f%% of tracked files in complete scopes"
            % (100 * result["coverage"].get("fraction", 0)),
            "graph       declared %d / observed %d inter-module edges"
            % (result["divergence"]["declared"], result["divergence"]["observed"]),
        ]
        for e in result["divergence"]["declared_not_observed"]:
            lines.append("  declared but never imported: %s -> %s" % (e["from"], e["to"]))
        for e in result["divergence"]["observed_not_declared"]:
            lines.append("  imported but not declared:   %s -> %s" % (e["from"], e["to"]))
        for row in result.get("declared_ambiguous", []):
            lines.append("  ambiguous declared dep:      %s -> '%s' (%s); no edge drawn"
                         % (row["from"], row["dep"], ", ".join(row["candidates"])))

    elif kind == "coverage":
        cov = result["coverage"]
        lines.append("coverage %d/%d tracked files (%.1f%%)"
                     % (cov.get("files_complete", 0), cov.get("files_total", 0),
                        100 * cov.get("fraction", 0)))
        if result["warning"]:
            lines.append(result["warning"])
        for node in cov.get("incomplete_nodes", []):
            lines.append("  incomplete: %s (%s)" % (node, result["nodes"].get(node, "not run")))

    else:
        lines.append(str(result))

    return "\n".join(lines).rstrip() + _footer(result)


def _footer(result: Dict) -> str:
    """`elided: N` and `as of commit X, state vY` — on every response.

    Both are mandatory (`CDP_CLI_SCOPE.md §C` item 1.3). The provenance line
    matters as much as the count: an answer with no commit attached cannot be
    checked against the tree it describes, and two answers from different
    snapshots are indistinguishable once pasted into a ticket.
    """
    parts: List[str] = [""]
    if result.get("budget_note"):
        parts.append(result["budget_note"])
    as_of = result.get("as_of") or {}
    parts.append(
        "elided: %d%s" % (
            result.get("elided", 0),
            "" if result.get("budget") is None else " (budget %d rows)" % result["budget"],
        )
    )
    parts.append(
        "as of %s@%s, state v%s"
        % (as_of.get("repo", "?"), str(as_of.get("commit", "unpinned"))[:12],
           as_of.get("state_version", 0))
    )
    return "\n" + "\n".join(parts)


QUERIES: Dict[str, Callable] = {
    "symbol": q_symbol,
    "file": q_file,
    "module": q_module,
    "routes": q_routes,
    "table": q_table,
    "config": q_config,
    "paths": q_paths,
    "trace": q_trace,
    "search": q_search,
    "claims": q_claims,
    "unknowns": q_unknowns,
    "conflicts": q_conflicts,
    "stats": q_stats,
    "coverage": q_coverage,
}
