# CDP — Functionality Guides

One folder per functional area. Each contains three docs:

- `KNOW_ABOUT.md` — concepts, invariants, gotchas (source: `PHASE/FINDINGS.md`)
- `HOW_TO.md` — commands to use the functionality
- `WHERE_TO.md` — file/test/doc navigation map

Governing rules referenced throughout (`CDP_CLI_SCOPE.md`): R1 provenance is a
column not a directory; R2 structure is disposable, claims are precious; R3
`scan` writes, `link` reads; R4 trajectory corpus is write-always; R5 archive
never destroys; R6 a failed scope becomes an `unknown`, never a silent gap;
R7 config is a file, data is a table; R8 an anchor surviving ≠ a claim being
fresh; R9 never assume, diff; R10 learning steers routing, never claim
content; R11 humans outrank models on interpretation, never structure; R12
unknowns are sticky.

## Areas

- [scanning-extraction](scanning-extraction/) — language extractors, anchoring, inventory excludes
- [graph-building-resolution](graph-building-resolution/) — declared/observed graph, dataflow pivoting
- [merge-conflict-handling](merge-conflict-handling/) — cross-agent patch merge
- [verification-entailment](verification-entailment/) — anchor verification, entailment, unknown gates
- [anchoring-diffs](anchoring-diffs/) — anchor building, structural diffs between scans
- [state-snapshots](state-snapshots/) — fold, generations, freshness, snapshots
- [golden-regression-testing](golden-regression-testing/) — fixture and target-repo golden baselines
- [doctor-model-conformance](doctor-model-conformance/) — cross-model conformance scoring
- [runner-protocol-leaf-dispatch](runner-protocol-leaf-dispatch/) — wave dispatch, leases, leaf agent contract
- [digest-tiering](digest-tiering/) — digest-mode prompts, T2/T3 tiering
- [digest-gates-escalation](digest-gates-escalation/) — leaf self-reported escalation
- [cross-repo-link](cross-repo-link/) — Phase 8 cross-repo service link discovery
- [trajectory-learning-distribution](trajectory-learning-distribution/) — lessons, promotions, holdout gating
- [benchmarking](benchmarking/) — graded coverage and live-holdout benchmarks
- [mcp-server](mcp-server/) — 3-tool MCP server
- [agent-adapters](agent-adapters/) — ADK / LangGraph tool adapters
- [export-postgres](export-postgres/) — export formats, Postgres backend
- [rollback-recovery](rollback-recovery/) — run/snapshot rollback ledger
- [backend-selection](backend-selection/) — sqlite/file/postgres store selection, git hooks
- [scheduling-cli-cross-cutting](scheduling-cli-cross-cutting/) — help/status/install, `--repo` guard
- [cross-cutting-infra](cross-cutting-infra/) — schema, distribution, core-purity enforcement
- [locking](locking/) — per-repo mutual exclusion around every store-touching command
