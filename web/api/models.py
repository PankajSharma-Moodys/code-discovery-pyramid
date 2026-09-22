"""Pydantic response models -- the CLI-parity contract (`WEB_RESEARCH.md` §6.1).

`StatusResponse` mirrors `cdp.cli.status()`'s dict shape field-for-field.
`web/tests/test_status_contract.py` validates both `cdp status --json`'s
stdout and `GET /api/status`'s body against this same model, so the two
surfaces diverging fails CI instead of surfacing as a trust bug in a demo.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class CoverageResponse(BaseModel):
    fraction: float
    files_complete: int
    files_total: int


class FreshnessResponse(BaseModel):
    live: int
    stale: int
    unreviewed: int
    unknown_churn: int


class WaveNodeResponse(BaseModel):
    node: str
    status: str


class WaveResponse(BaseModel):
    wave: int
    level: int
    done: int
    total: int
    file_count: int
    loc: int
    nodes: List[WaveNodeResponse]


class TaskResponse(BaseModel):
    node: str
    state: str
    attempts: int
    last_error: Optional[str] = None


class StatusResponse(BaseModel):
    run_id: str
    head: Optional[str] = None
    coverage: CoverageResponse
    freshness: Optional[FreshnessResponse] = None
    waves: List[WaveResponse]
    tasks: List[TaskResponse]


# --------------------------------------------------------------- /api/node/:id
#
# `GET /api/node/:id` (`PLAN.md` item 3, `WEB_RESEARCH.md` §7.1/§7.3). Mirrors
# `state.claims[]`/`dataflow.edges[]`/`partition.scopes[]` field-for-field --
# see `web/api/app.py`'s `_build_node` for the assembly and `web/api/nodeid.py`
# for the namespace classification this response is keyed on.


class EvidenceResponse(BaseModel):
    file: str
    line: int
    anchor: Optional[str] = None


class ClaimResponse(BaseModel):
    subject: str
    kind: str
    confidence: str
    evidence: List[EvidenceResponse]
    anchor_verified_at: Optional[str] = None
    claim_reviewed_at: Optional[str] = None
    author_kind: Optional[str] = None


class DataflowAnchorResponse(BaseModel):
    file: str
    line: int
    anchor: Optional[str] = None


class DataflowEdgeResponse(BaseModel):
    source: str
    target: str
    channel: str
    confidence: str
    module: Optional[str] = None
    anchor: Optional[DataflowAnchorResponse] = None


class SourceEntryResponse(BaseModel):
    node: str
    channel: str
    trigger: str
    module: Optional[str] = None
    anchor: Optional[DataflowAnchorResponse] = None


class SourcesResponse(BaseModel):
    count: int
    sources: List[SourceEntryResponse]


class ScopeSummaryResponse(BaseModel):
    node: str
    module: str
    file_count: int
    loc: int


class NodeResponse(BaseModel):
    node_id: str
    namespace: str
    claims: List[ClaimResponse]
    unknowns_count: int
    edges_in: List[DataflowEdgeResponse]
    edges_out: List[DataflowEdgeResponse]
    scope: Optional[ScopeSummaryResponse] = None


class RepoInfoResponse(BaseModel):
    """One `cdp.store.registry` entry, per `GET /api/repos`. `head` is the
    *current* HEAD of the repo's working tree (`git rev-parse HEAD`, run at
    request time); `as_of_commit` is the commit the pinned snapshot's
    `inventory` was built against (same source `cdp.query._as_of` reads).
    `behind` is `0` when the two match, an exact `git rev-list --count`
    when cheaply derivable, or `None` (never a fabricated number) when the
    working tree moved, isn't a git repo, or the git call otherwise failed.
    `error` is set (and every other field but `repo_id`/`state_dir` left
    `None`) when this one registry entry couldn't be resolved at all --
    a broken entry never fails the whole list."""

    repo_id: str
    state_dir: str
    repo_path: Optional[str] = None
    head: Optional[str] = None
    as_of_commit: Optional[str] = None
    behind: Optional[int] = None
    error: Optional[str] = None


class ReposResponse(BaseModel):
    repos: List[RepoInfoResponse]


class GraphNodeResponse(BaseModel):
    """One node per package (L3) or typed `dataflow` node (L2). Fields that
    don't apply at a given level are left `None`/empty rather than the model
    forking in two.

    `type`/`family`/`degree` are `ATLAS_REDESIGN.md` §3's visual-encoding
    channels, computed server-side so both canvases and the legend read the
    same source of truth. `node_id` is the *namespaced* (`web/api/nodeid.py`)
    form the inspector can hand straight to `/api/node/{id}` -- `None` for a
    synthetic L3 package super-node, which has no single underlying subject.
    `members` is only populated at L3 (the raw L2 ids rolled into this one)."""

    id: str
    label: str
    level: Optional[int] = None
    file_count: Optional[int] = None
    by_role: Optional[dict] = None
    by_language: Optional[dict] = None
    oversized: Optional[bool] = None
    type: Optional[str] = None
    family: Optional[str] = None
    degree: Optional[int] = None
    node_id: Optional[str] = None
    members: Optional[List[str]] = None


class GraphEdgeResponse(BaseModel):
    """`kind` carries the channel the edge was extracted from -- `call`,
    `persist`, `process_boundary`, `http_in`, `read`, `config_read`,
    `schema_own` at L2/L3 (`dataflow.edges[].channel`), `import` at L1, and
    the divergence signal `declared` / `observed` / `both` wherever the
    `graph` artifact is the source. `count` is how many underlying edges a
    rolled-up L3 edge stands for (always 1 at L2)."""

    source: str
    target: str
    kind: str
    weight: Optional[int] = None
    confidence: Optional[str] = None
    count: Optional[int] = None


class GraphLegendEntry(BaseModel):
    """One row of the canvas legend, computed from the same tables that drive
    the encoding so the legend can never drift from what is drawn."""

    type: str
    label: str
    family: str
    count: int


class GraphResponse(BaseModel):
    level: str
    scope: Optional[str] = None
    nodes: List[GraphNodeResponse]
    edges: List[GraphEdgeResponse]
    levels: List[List[str]] = []
    cycles: List[List[str]] = []
    divergence: Optional[dict] = None
    legend: List[GraphLegendEntry] = []


class ConfidenceResponse(BaseModel):
    """`GET /api/confidence` -- one bulk `{raw graph id -> bucket}` map for a
    whole altitude, replacing the per-node `/api/node` fan-out the confidence
    lens used to do (353 requests at L2 after `ATLAS_REDESIGN.md` P0). Buckets
    are the `theme/confidence.ts` vocabulary: `high` / `medium` / `low` /
    `contested` / `unreviewed`."""

    level: str
    buckets: dict


class DoctorResponse(BaseModel):
    """`GET /api/doctor` -- reads `<state>/doctor/*.json` straight off disk
    (`cdp/cli.py:1885`'s write side), no `index.db` involved. `models` keys on
    the model name each report was written under; `table` is
    `doctor.compatibility_table`'s same text rendering, included for parity
    with the CLI's own printed output when >1 model is present."""

    models: dict
    table: Optional[str] = None


class LinkSideResponse(BaseModel):
    repo: str
    anchor: Optional[dict] = None


class LinkResponse(BaseModel):
    """One matched or unmatched entry from `link.query_service`
    (`cdp/link.py:217`). Deliberately loose (`dict`-typed `caller`/`callee`/
    `outbound`) -- these are link/unmatched records straight from
    `link.scan_links`'s own output shape, not re-modeled here."""

    protocol: Optional[str] = None
    caller: Optional[dict] = None
    callee: Optional[dict] = None
    outbound: Optional[dict] = None
    match_kind: Optional[str] = None


class LinkQueryResponse(BaseModel):
    service: str
    links: List[dict]
    unmatched: List[dict]


class LinksResponse(BaseModel):
    """All persisted `link_edge` rows (`ReadOnlyConnection.read_link_edges`),
    unfiltered by service -- the constellation view's data source. Same
    loose `dict`-typed shape as `LinkQueryResponse` (straight from
    `link.scan_links`'s own output), split by `kind` ("link" vs
    "unmatched")."""

    links: List[dict]
    unmatched: List[dict]


class TrajectoryRunResponse(BaseModel):
    run_id: str
    node: str
    repo_id: str
    model: str
    scope_shape: str
    tier: str
    task_kind: str
    state: Optional[str] = None
    attempts: Optional[int] = None
    wall_ms: Optional[int] = None
    claims_emitted: Optional[int] = None
    unknowns_emitted: Optional[int] = None
    elision_regret: Optional[int] = None
    entailed: Optional[int] = None
    consistent: Optional[int] = None
    contradicted: Optional[int] = None
    created_at: str


class TrajectoryResponse(BaseModel):
    shape: Optional[str] = None
    runs: List[TrajectoryRunResponse]


class DiffResponse(BaseModel):
    """`cdp.diffs.diff_snapshots`'s return value, passed through as-is
    (`WEB_RESEARCH.md` §7.1's `/api/diff` -- a typed structural delta, not a
    text diff). Left loose/`dict`-typed like `/api/query`'s response: the
    shape is `cdp/diffs.py`'s own, not re-modeled field-for-field here."""

    old_sha: str
    new_sha: str
    diff: dict


class SnapshotMetaResponse(BaseModel):
    commit_sha: str
    created_at: str


class SnapshotsResponse(BaseModel):
    """Ordered (oldest-first) list of this repo's scanned commits
    (`snapshot_meta`, via `ReadOnlyConnection.known_shas`/`snapshot_history`)
    -- the time scrubber's timeline, and the set of shas valid as `/api/diff`
    `old`/`new` params."""

    repo_id: str
    snapshots: List[SnapshotMetaResponse]


class JobResponse(BaseModel):
    """`POST /api/run`/`POST /api/refresh` (`WEB_RESEARCH.md` §7.2.4) --
    `status` is `"started"` for a freshly spawned subprocess or `"joined"`
    when a job for this `(repo, state_dir)` was already in flight and this
    call returned that same job's handle instead of racing a second process
    (single-flight, not a queue -- see `web/api/jobs.py`)."""

    job_id: str
    status: str
    pid: int
    kind: str


class JobStatusResponse(BaseModel):
    """`GET /api/job/:id` -- lets a caller that already holds a `job_id` (from
    a `JobResponse`) poll for completion without a task table to watch, which
    is what `/api/status`'s poll gives `/api/run`/`/api/refresh` but `POST
    /api/hookup/liveness`'s `cdp doctor` subprocess has none of."""

    job_id: str
    kind: str
    repo: str
    state_dir: str
    running: bool
    returncode: Optional[int] = None


class InstallPreviewResponse(BaseModel):
    """`GET /api/hookup/preview` -- read-only description of what `cdp
    install --framework <framework> <target>` would do, without running it
    (`WEB_RESEARCH.md` §4 item 1: "shows the exact files it will copy")."""

    skill_dest: str
    skill_members: List[str]
    leaf_agent_file: Optional[str] = None
    framework_note: Optional[str] = None
    agents_md_path: str
    agents_md_action: str


class InstallResultResponse(BaseModel):
    """`POST /api/hookup/install` -- `cdp install` is a fast, idempotent
    file-copy, so unlike `/api/run`/`/api/refresh` this runs synchronously
    and returns the finished result rather than a `JobResponse` to poll."""

    returncode: int
    stdout: str
    stderr: str


class McpToolResponse(BaseModel):
    name: str
    description: str
    input_schema: dict


class McpToolsResponse(BaseModel):
    """`GET /api/hookup/mcp-tools` -- read straight from
    `mcp_server.schemas.TOOL_SCHEMAS`, never restated (§7.2's "client of the
    CLI's semantics, not a second implementation")."""

    tools: List[McpToolResponse]
    client_config: str


class SourceResponse(BaseModel):
    """`GET /api/source` -- file bytes for the code-peek pane
    (`WEB_RESEARCH.md` §7.1, net-new: no other endpoint serves raw file
    content). `path` is the repo-relative POSIX string as requested (same
    format `cdp/inventory.py` stores in the `inventory` artifact, so it's
    consistent with what claims/anchors already reference)."""

    path: str
    start_line: int
    end_line: int
    total_lines: int
    lines: List[str]
