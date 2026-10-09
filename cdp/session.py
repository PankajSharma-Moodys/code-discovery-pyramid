"""Opening a repo's store and the small helpers every command shares."""

from __future__ import annotations

import os
import shlex

from . import docs as docs_mod, rollback as rollback_mod, runner as runner_mod, state as state_mod
from .store import FileStore, SqliteStore, WorkspaceStore, registry as registry_mod
from .util import CdpError, run_git, stable_hash
from .verify import STRICT
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


class Paths:
    """`state` is the machine home (`CDP_HOME`); `work` is this repo's own
    hand-over directory under it."""

    def __init__(self, repo: Path, state: Path) -> None:
        self.repo = repo
        self.state = state
        self.repo_id = registry_mod.repo_identity(repo)
        self.work = registry_mod.work_dir(state, self.repo_id)


def paths_for(repo, state_dir=None) -> "Paths":
    """One store per machine: `state_dir` (an alias for `CDP_HOME`), else
    `CDP_HOME`, else `~/.cdp`. The repo only decides *which rows* of that store
    a command reads (`Paths.repo_id`)."""
    repo = Path(repo).expanduser().resolve()
    if os.environ.get("CDP_STORE"):
        raise CdpError("CDP_STORE is no longer read: CDP keeps one store per machine. "
                       "Use CDP_HOME (default ~/.cdp) to move it.")
    home = Path(state_dir).expanduser().resolve() if state_dir else registry_mod.cdp_home()
    registry_mod.check_team_config(repo)
    return Paths(repo=repo, state=home)


def resolve_backend(home: Path) -> Tuple[str, Optional[Dict[str, str]]]:
    """`CDP_HOME/config.toml`'s `backend` key decides which `WorkspaceStore`
    `open_store` constructs -- default `"sqlite"`. One choice per machine."""
    kind = registry_mod.machine_backend(home)
    config = home / registry_mod.CONFIG_FILE
    if kind not in ("sqlite", "file", "postgres"):
        raise CdpError('unknown backend %r in %s (must be "sqlite", "file" or "postgres")' % (kind, config))
    pg = registry_mod.machine_postgres_config(home) if kind == "postgres" else None
    if kind == "postgres" and not (pg and pg.get("dsn")):
        raise CdpError('backend = "postgres" in %s needs a [postgres] dsn' % config)
    return kind, pg


def open_store(paths: "Paths") -> WorkspaceStore:
    """No backend is hardcoded here: `CDP_HOME/config.toml` picks the
    `WorkspaceStore` (`resolve_backend`), defaulting to `SqliteStore` at
    `<home>/index.db`. The store is then pointed at *this repo's* snapshot for
    HEAD (else its latest), so a read never answers from another repo.
    Commands that scan or refresh move the selection themselves afterwards."""
    kind, pg = resolve_backend(paths.state)
    if kind == "file":
        return FileStore(paths.state)
    if kind == "postgres":
        from .store.postgres_backend import PostgresStore

        return PostgresStore(pg["dsn"], pg.get("schema") or "cdp", inbox_root=paths.work)
    backend = SqliteStore(paths.state / "index.db", inbox_root=paths.work)
    backend.use_current_snapshot(paths.repo_id, run_git_head(paths.repo))
    return backend


def run_git_head(repo: Path) -> Optional[str]:
    out = run_git(repo, "rev-parse", "HEAD")
    return out.strip() if out and out.strip() else None


def check_repo_matches_manifest(paths: "Paths", manifest: Dict) -> None:
    """Fail loudly rather than silently verifying every anchor against the
    wrong tree -- found live: `cdp run` defaulted `--repo` to cwd when
    omitted, verified every claim against this tool's own repo instead of
    the actual target, and every anchor failed, indistinguishable at a
    glance from a genuinely bad leaf run. `manifest["repo"]` is already
    written by `cmd_scan`; this is a runtime cross-check of two
    already-recorded values, nothing new to serialize."""
    recorded = manifest.get("repo")
    if not recorded or str(paths.repo) == recorded:
        return
    raise CdpError(
        "--repo %s does not match the repo this state was scanned from "
        "(%s, from manifest.json). Anchor verification would silently run "
        "against the wrong tree. Pass the matching --repo, or --state-dir "
        "if you meant a different repo's state." % (paths.repo, recorded)
    )


def new_run_id(head: str) -> str:
    """Derived from the commit, not the clock.

    Two scans of the same commit must produce byte-identical state, and a
    timestamp in the run id would leak into every patch and defeat the
    reproducibility gate at every phase.
    """
    return "cdp-" + (head[:12] if head and head != "unpinned" else stable_hash(head)[:12])


def stamp_claims(claims: List[Dict], head: str) -> None:
    """First `claim_reviewed_at` for a freshly authored claim (0.8): the commit
    it was authored against, not a timestamp -- see `cdp/freshness.py` for why
    a wall-clock date here would break the determinism gate. `refresh`
    (`cdp/refresh.py`) is what carries this forward or clears it on later
    commits; scan/collect only ever set it once, at birth.
    """
    for claim in claims:
        claim.setdefault("claim_reviewed_at", head)


def next_generation(existing_patches: Sequence[Dict], node: str) -> int:
    """1-based attempt count for `node` (M3.4). Stamped once at append time,
    onto data the patch carries forever, so `state.fold`'s per-node
    supersession reads a fact rather than a log position -- order-independent
    by construction, the same way `node_status` already is."""
    prior = [int(p.get("generation") or 1) for p in existing_patches if str(p.get("node")) == node]
    return (max(prior) + 1) if prior else 1


def git_head_or_raise(repo: Path) -> str:
    from .util import git_head

    head = git_head(repo)
    if head is None:
        raise CdpError("`%s` is not a git repository HEAD could be read from" % repo)
    return head


def build_runner(runner_cmd: Optional[str], timeout: float):
    if runner_cmd:
        return runner_mod.SubprocessRunner(shlex.split(runner_cmd), timeout_s=timeout)
    return runner_mod.FileRunner(timeout_s=timeout)


def next_run_id(backend, base_run_id: str) -> str:
    """First `<base_run_id>-rN` (N starting at 2) not already a run in this
    store -- the new run `--resume` opens when the partition has drifted."""
    n = 2
    while backend.get_run("%s-r%d" % (base_run_id, n)) is not None:
        n += 1
    return "%s-r%d" % (base_run_id, n)


def fold_and_write(
    store: "WorkspaceStore", xref: Dict, part: Dict, repo: Optional[Path] = None, mode: str = STRICT
) -> Dict:
    patches = store.load_patches()
    folded = state_mod.fold(
        patches, xref, part, repo=repo, mode=mode,
        excluded_run_ids=rollback_mod.load_excluded_run_ids(store),
        extraction=store.read_artifact("extract") if store.has_artifact("extract") else None,
    )
    store.write_artifact("state", folded)
    return folded


def render_docs(store: "query_mod.Store", out: Path) -> List[Path]:
    """The one call site for the renderer.

    `scan` and `docs` both render, and if they did it through two argument lists
    they could drift — at which point the golden baseline, which captures
    `cdp docs`, would stop describing what `cdp scan` writes.
    """
    return docs_mod.render_all(
        out, store.inventory, store.extraction, store.graph, store.partition,
        store.xref, store.dataflow, store.state, store.manifest,
    )


def git_identity(repo: Path) -> str:
    name = run_git(repo, "config", "user.name")
    email = run_git(repo, "config", "user.email")
    name = (name or "").strip() or "unknown"
    email = (email or "").strip()
    return "%s <%s>" % (name, email) if email else name

def apply_as_of(store: "query_mod.Store", commit: str) -> None:
    """M3.7: replay the claim log up to `commit`'s run, against the *current*
    structural view (`xref`/`partition` are not rebuilt at the old commit --
    that is `refresh`'s job, not a query's). This is what keeps it "nearly
    free" per `phase_3_plan.md`: one extra `fold` over an already-loaded patch
    list, no re-extraction, no repo checkout.

    Anchors are not re-verified against `repo` here (`fold(..., repo=None)`):
    verifying an old claim's anchor against the *current* tree would report
    drift that `refresh` already has a home for, and verifying against the old
    tree would need a checkout this operation is explicitly meant to avoid
    paying for. The claims returned are exactly what the log asserted as of
    that run, unverified against any tree.
    """
    run_id = rollback_mod.resolve_run_id(commit)
    kept, _excluded, found = rollback_mod.patches_up_to_run(store.backend.load_patches(), run_id)
    if not found:
        raise CdpError(
            "commit %s never appears in this store's patch log -- `--as-of` "
            "only replays history this store actually recorded" % commit
        )
    folded = state_mod.fold(kept, store.xref, store.partition, extraction=store.extraction)
    store._cache["state"] = folded
    store.as_of_run_id = run_id


def extra_excludes(repo: Path, exclude: Optional[Sequence[str]] = None) -> List[str]:
    """`.cdp.toml`'s `exclude` list plus this invocation's `--exclude` --
    additive on top of `inventory.DEFAULT_EXCLUDES`, never a replacement for it."""
    return registry_mod.team_excludes(repo) + list(exclude or [])
