"""Command line interface.

Three commands do almost everything:

    cdp scan     # deterministic only. No LLM, no tokens. Writes queryable state.
    cdp query    # ask the state questions, with citations
    cdp docs     # render the markdown artifacts

The agent-driven phases (`prompts`, `collect`, `fold`) are separate because the
orchestration lives in `SKILL.md`, not here: Python owns every deterministic
phase and the session owns the wave loop. That split is what keeps the call
stack at depth 1 while the pyramid grows in the state directory.

**State is written outside the target repository by default** (PLAN.md C6). The
repository being analysed is not this tool's repository, and a tool that leaves
a directory behind in someone else's checkout has made a decision that was not
its to make. `--in-repo` opts into `.cdp/` inside the target.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shlex
import shutil
import sys
from contextlib import contextmanager as contextlib_contextmanager
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from . import anchor as anchor_mod
from . import dataflow as dataflow_mod
from . import diffs as diffs_mod
from . import docs as docs_mod
from . import freshness as freshness_mod
from . import gates as gates_mod
from . import githooks as githooks_mod
from . import golden as golden_mod
from . import graph as graph_mod
from . import helpdoc
from . import inventory as inventory_mod
from . import partition as partition_mod
from . import query as query_mod
from . import refresh as refresh_mod
from . import resolve as resolve_mod
from . import rollback as rollback_mod
from . import runner as runner_mod
from . import schedule as schedule_mod
from . import snapshot as snapshot_mod
from . import state as state_mod
from . import supervisor as supervisor_mod
from .store import ARTIFACTS, REPORTS, SqliteStore, WorkspaceStore, has_scanned
from .store import registry as registry_mod
from .derive import derive_claims
from .extract import run_extract
from . import prompts as prompts_mod
from .prompts import build_prompt
from .schema import Validator, schema_path, validate_patch
from .util import (
    CDP_VERSION,
    CdpError,
    read_json,
    run_git,
    stable_hash,
    write_json,
    write_text,
)
from .inventory import ROOT_MODULE as ROOT_MODULE_LABEL
from .verify import STRICT

SKILL_ROOT = Path(__file__).resolve().parent.parent

#: Floor on the bundled suite's size. `selftest` fails below it rather than
# reporting a green run over nothing. Raise it deliberately when tests are
# added; never lower it to make a red build green.
MIN_TESTS = 180


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args) or 0
    except CdpError as exc:
        print("cdp: %s" % exc, file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


def _parser() -> argparse.ArgumentParser:
    # The location flags are accepted on both sides of the subcommand. Typing
    # `cdp scan --repo X` is the natural order and `cdp --repo X scan` is the
    # one argparse makes natural; refusing either is a papercut on every call.
    # SUPPRESS keeps the subparser copy from overwriting a value already given
    # to the top-level parser with its own default.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=argparse.SUPPRESS,
                        help="repository to analyse (default: cwd)")
    common.add_argument("--state-dir", default=argparse.SUPPRESS,
                        help="where to write state (default: ./.cdp; never inside --repo "
                             "unless --in-repo)")
    common.add_argument("--in-repo", action="store_true", default=argparse.SUPPRESS,
                        help="write state into <repo>/.cdp and add a .gitignore entry")

    p = argparse.ArgumentParser(prog="cdp", parents=[common],
                                description="Code Discovery Pyramid v%s" % CDP_VERSION)
    sub = p.add_subparsers(dest="command")

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], help=help_text)

    s = add("scan", "run every deterministic phase and write queryable state")
    s.add_argument("--max-leaf-files", type=int, default=partition_mod.DEFAULT_MAX_FILES)
    s.add_argument("--max-leaf-loc", type=int, default=partition_mod.DEFAULT_MAX_LOC)
    s.add_argument("--max-concurrent", type=int, default=schedule_mod.DEFAULT_MAX_CONCURRENT)
    s.add_argument("--max-hops", type=int, default=dataflow_mod.DEFAULT_MAX_HOPS)
    s.add_argument("--no-docs", dest="docs", action="store_false", default=True,
                   help="skip rendering <state-dir>/docs/ at the end of the scan")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(func=cmd_scan)

    q = add("query", "ask the extracted state a question")
    q.add_argument("kind", choices=sorted(query_mod.QUERIES))
    q.add_argument("term", nargs="?", default=None)
    q.add_argument("--json", action="store_true", help="emit the full result as JSON")
    q.add_argument("--kind", dest="claim_kind", default=None, help="filter claims by kind")
    q.add_argument("--module", default=None)
    q.add_argument("--subject", default=None)
    q.add_argument("--from", dest="frm", default=None)
    q.add_argument("--to", dest="to", default=None)
    # One knob, not seven. `--limit` used to sit beside eleven unrelated
    # hard-coded caps inside `query.py`; both are now `--budget`, which is
    # counted and reported rather than applied silently.
    q.add_argument("--budget", type=int, default=None,
                   help="rows this answer may emit, across every list in it "
                        "(default %d; `stats` and `coverage` are never budgeted)"
                        % query_mod.DEFAULT_BUDGET)
    q.add_argument("--max-hops", type=int, default=dataflow_mod.DEFAULT_MAX_HOPS,
                   help="`query trace` only: how far to walk from the entry point")
    q.add_argument("--as-of", dest="as_of", default=None, metavar="COMMIT",
                   help="replay the claim log up to this commit's run, against "
                        "the current structural view (M3.7). A commit only -- "
                        "patches carry no timestamp (D8), so a wall-clock cut "
                        "is not supported")
    q.set_defaults(func=cmd_query)

    d = add("docs", "render the markdown artifacts")
    d.add_argument("--out", default=None, help="output directory (default: <state-dir>/docs)")
    d.set_defaults(func=cmd_docs)

    pr = add("prompts", "write one leaf prompt per scope, for the wave loop")
    pr.add_argument("--wave", type=int, default=None, help="only this wave")
    pr.add_argument("--node", default=None, help="only this node")
    pr.add_argument("--measure", action="store_true",
                     help="print a per-section token estimate (M5.6, 4.9) instead of "
                          "the usual per-scope summary -- chars/4, not a real tokenizer")
    pr.set_defaults(func=cmd_prompts)

    c = add("collect", "validate, verify and append leaf patches from the inbox")
    c.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    c.set_defaults(func=cmd_collect)

    f = add("fold", "recompute state.json from patches/ + xref.json")
    f.add_argument("--check", action="store_true", help="verify the invariant instead of writing")
    f.set_defaults(func=cmd_fold)

    r = add("refresh", "re-verify every live claim against HEAD, zero model calls")
    r.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(func=cmd_refresh)

    rn = add("run", "dispatch -> collect -> adjudicate -> fold, wave by wave")
    rn_target = rn.add_mutually_exclusive_group(required=True)
    rn_target.add_argument("--wave", type=int, help="dispatch only this wave")
    rn_target.add_argument("--wave-all", action="store_true", help="every wave, in order")
    rn_target.add_argument("--stale-only", action="store_true",
                            help="only scopes owning a stale/anchored-but-unreviewed "
                                 "claim (the M3.1 freshness bucket), across every wave")
    rn_target.add_argument("--scope", help="one node, by name (e.g. root/gateway)")
    rn.add_argument("--runner-cmd", default=None, metavar="CMD",
                     help="shell command for SubprocessRunner, given prompt and patch "
                          "paths as its last two arguments (default: FileRunner -- "
                          "wait for a human/external process to drop the patch file)")
    rn.add_argument("--timeout", type=float, default=300.0,
                     help="seconds before a task's runner call is treated as failed "
                          "(SubprocessRunner) or abandoned (FileRunner's poll deadline)")
    rn.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    rn.add_argument("--resume", action="store_true",
                     help="reclaim past-lease tasks and continue this run_id if the "
                          "partition is unchanged; otherwise open a new run inheriting "
                          "unchanged scopes (M5.5)")
    rn.add_argument("--max-attempts", type=int, default=supervisor_mod.MAX_ATTEMPTS,
                     help="retries per scope before it is abandoned (default %d)"
                          % supervisor_mod.MAX_ATTEMPTS)
    rn.set_defaults(func=cmd_run)

    st = add("status", "waves, node statuses and coverage")
    st.set_defaults(func=cmd_status)

    df = add("diff", "typed structural deltas between two scanned state directories")
    df.add_argument("old_state", help="state directory of the earlier snapshot")
    df.add_argument("new_state", help="state directory of the later snapshot")
    df.add_argument("--json", action="store_true")
    df.set_defaults(func=cmd_diff)

    gc = add("gc", "drop snapshots not kept by the retention rule")
    gc.add_argument("--db", default=None,
                     help="path to a SqliteStore index.db (default: the resolved store's)")
    gc.add_argument("--head-sha", default=None,
                    help="commit sha to treat as HEAD (default: `git -C --repo` HEAD)")
    gc.add_argument("--pin", action="append", default=[], metavar="SHA",
                    help="mark a commit's snapshot pinned before computing retention (repeatable)")
    gc.add_argument("--unpin", action="append", default=[], metavar="SHA")
    gc.add_argument("--dry-run", action="store_true", help="report what would be dropped, drop nothing")
    gc.set_defaults(func=cmd_gc)

    rb = add("rollback", "exclude a run's patches from the fold, without deleting them")
    rb_target = rb.add_mutually_exclusive_group(required=True)
    rb_target.add_argument("--to-run", metavar="RUN_OR_COMMIT",
                            help="exclude just this run's patches")
    rb_target.add_argument("--to-snapshot", metavar="COMMIT",
                            help="exclude this run and every run appended after it")
    rb.add_argument("--reason", default=None, help="why (recorded in the rollback ledger)")
    rb.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    rb.set_defaults(func=cmd_rollback)

    schema_defs = Validator.load(schema_path(SKILL_ROOT)).schema["$defs"]
    an = add("answer", "record a human claim against an unknown -- validate, "
                        "verify anchor, entail, fold, no bypass (M4.4)")
    an.add_argument("scope", help="the node this claim belongs to, e.g. root/gateway")
    an.add_argument("--subject", required=True, help="what the claim is about, e.g. a fqn")
    an.add_argument("--kind", required=True, choices=sorted(schema_defs["claim_kind"]["enum"]),
                    help="one of CDP's closed claim kinds -- R11: humans outrank "
                         "models on interpretation, never on structure")
    an.add_argument("--claim", required=True, dest="statement", help="the statement text")
    an.add_argument("--anchor", required=True, metavar="FILE:LINE",
                    help="where this is true; the citable text is read from the file itself")
    an.add_argument("--channel", default=None, choices=sorted(schema_defs["channel"]["enum"]))
    an.add_argument("--confidence", default="high", choices=["high", "medium", "low"])
    an.add_argument("--author", default=None, help="default: git config user.name <user.email>")
    an.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    an.set_defaults(func=cmd_answer)

    v = add("validate", "validate a patch file against the schema")
    v.add_argument("path")
    v.set_defaults(func=cmd_validate)

    gh = add("githook", "install/uninstall post-commit & post-checkout hooks "
                        "that auto-run `cdp refresh` (M3.8, opt-in, off by default)")
    gh.add_argument("action", choices=["install", "uninstall"])
    gh.set_defaults(func=cmd_githook)

    i = add("install", "copy this skill into another repository")
    i.add_argument("target", nargs="?", help="repository to install into")
    i.add_argument("--self", action="store_true",
                   help="refresh this repository's own vendored .claude/skills/cdp copy")
    i.add_argument("--hook", action="store_true",
                   help="also install the PreToolUse nudge (requires in-repo state)")
    i.set_defaults(func=cmd_install)

    stest = add("selftest", "run the bundled tests")
    stest.add_argument("--min-tests", type=int, default=MIN_TESTS,
                       help="fail if fewer than this many tests ran (default: %d)" % MIN_TESTS)
    stest.add_argument("--determinism", metavar="REPO",
                       help="instead of the suite, run the reproducibility gate "
                            "against an arbitrary repository")
    stest.add_argument("--golden", metavar="REPO",
                       help="instead of the suite, diff output against the stored "
                            "baseline for this repository")
    stest.add_argument("--bless", action="store_true",
                       help="with --golden: overwrite the baseline with current output")
    stest.add_argument("--golden-name", metavar="SLUG",
                       help="with --golden: baseline directory name, overriding <repo>@<sha>")
    stest.set_defaults(func=cmd_selftest)

    h = add("help", "when to use what, in what order, and what comes next")
    h.add_argument("topic", nargs="?",
                   help="'workflows' for the named recipes, or a command name")
    h.add_argument("--json", action="store_true",
                   help="emit the machine-readable command surface "
                        "(schema/help-1.0.0.json)")
    h.set_defaults(func=cmd_help)
    return p


# ------------------------------------------------------------------ paths


def _paths(args) -> "Paths":
    """`--in-repo` / `--state-dir` are an explicit override and win outright.
    Otherwise M2.6's order applies: `CDP_STORE` -> `.cdp.toml` walking up ->
    the registry (`~/.cdp/config.toml`, keyed by repo identity, not path) ->
    `cwd/.cdp` (today's default, unchanged for a repo scanned for the first
    time or from an environment with no registry entry yet).
    """
    repo = Path(getattr(args, "repo", ".")).expanduser().resolve()
    state_dir = getattr(args, "state_dir", None)
    if getattr(args, "in_repo", False):
        state = repo / ".cdp"
    elif state_dir:
        state = Path(state_dir).expanduser().resolve()
    else:
        state = registry_mod.resolve_store(repo, env=os.environ.get("CDP_STORE"))
    return Paths(repo=repo, state=state)


class Paths:
    def __init__(self, repo: Path, state: Path) -> None:
        self.repo = repo
        self.state = state

    def inside_repo(self) -> bool:
        try:
            self.state.relative_to(self.repo)
            return True
        except ValueError:
            return False


def _open_store(state_dir: Path) -> SqliteStore:
    """The CLI's actual default backend (D3, `PHASE/FINDINGS.md`): `SqliteStore`
    at `<state_dir>/index.db`, the path `CDP_CLI_SCOPE.md` 2.3 and
    `phase_2_plan.md` already name. `state_dir` itself stays a directory --
    `docs/`, `prompts/` and the inbox are filesystem handoffs regardless of
    backend (`store/__init__.py`'s module docstring)."""
    return SqliteStore(state_dir / "index.db")


def _run_id(head: str) -> str:
    """Derived from the commit, not the clock.

    Two scans of the same commit must produce byte-identical state, and a
    timestamp in the run id would leak into every patch and defeat the
    reproducibility gate at every phase.
    """
    return "cdp-" + (head[:12] if head and head != "unpinned" else stable_hash(head)[:12])


def _stamp_claims(claims: List[Dict], head: str) -> None:
    """First `claim_reviewed_at` for a freshly authored claim (0.8): the commit
    it was authored against, not a timestamp -- see `cdp/freshness.py` for why
    a wall-clock date here would break the determinism gate. `refresh`
    (`cdp/refresh.py`) is what carries this forward or clears it on later
    commits; scan/collect only ever set it once, at birth.
    """
    for claim in claims:
        claim.setdefault("claim_reviewed_at", head)


def _next_generation(existing_patches: Sequence[Dict], node: str) -> int:
    """1-based attempt count for `node` (M3.4). Stamped once at append time,
    onto data the patch carries forever, so `state.fold`'s per-node
    supersession reads a fact rather than a log position -- order-independent
    by construction, the same way `node_status` already is."""
    prior = [int(p.get("generation") or 1) for p in existing_patches if str(p.get("node")) == node]
    return (max(prior) + 1) if prior else 1


# ------------------------------------------------------------------- scan


def cmd_scan(args) -> int:
    paths = _paths(args)
    say = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    # M2.6: only the resolved-by-default case needs registering -- an explicit
    # `--in-repo`/`--state-dir` already tells every future command where to
    # look, and never touching the registry then keeps a test (or a user who
    # always passes `--state-dir`) from writing to `~/.cdp/config.toml` at all.
    if not getattr(args, "in_repo", False) and not getattr(args, "state_dir", None):
        registry_mod.register(registry_mod.repo_identity(paths.repo), paths.state)

    inventory = inventory_mod.build_inventory(paths.repo)
    say("\n".join(inventory_mod.summarise(inventory)))

    extraction = run_extract(paths.repo, inventory)
    say("extract   %d files parsed, %d symbols, %d edges, %d imports"
        % (extraction["totals"]["parsed_files"], extraction["totals"]["defines"],
           extraction["totals"]["io_edges"], extraction["totals"]["imports"]))

    graph = graph_mod.build_graph(inventory, extraction)
    say("\n".join(graph_mod.summarise(graph)))

    part = partition_mod.partition(inventory, args.max_leaf_files, args.max_leaf_loc)
    refresh_mod.annotate_scope_hashes(paths.repo, part)
    say("partition %d scopes (%d oversized)" % (part["totals"]["scopes"], part["totals"]["oversized"]))

    sched = schedule_mod.build_schedule(part, graph, args.max_concurrent)
    say("\n".join(schedule_mod.summarise(sched)))

    xref = resolve_mod.build_xref(inventory, extraction, graph)
    say("\n".join(resolve_mod.summarise(xref)))

    flow = dataflow_mod.build_dataflow(extraction, xref, graph, args.max_hops)
    say("\n".join(dataflow_mod.summarise(flow)))

    state_dir = paths.state
    store = _open_store(state_dir)
    store.begin_snapshot(*snapshot_mod.resolve_snapshot(paths.repo, inventory["head"]))
    store.write_artifact("inventory", inventory)
    store.write_artifact("extract", extraction)
    store.write_artifact("graph", graph)
    store.write_artifact("partition", part)
    store.write_artifact("schedule", sched)
    store.write_artifact("xref", xref)
    store.write_artifact("dataflow", flow)

    # The derived claims are appended as patch 0000. They enter state through
    # the same log every agent patch does, so the fold invariant holds from the
    # first commit rather than being retrofitted once agents exist.
    derived = derive_claims(paths.repo, inventory, extraction, graph, xref, part, flow)
    _stamp_claims(derived, inventory["head"])
    run_id = _run_id(inventory["head"])
    patch = {
        "schema_version": "1.0.0",
        "node": "root",
        "run_id": run_id,
        "author_kind": "python",
        "status": "complete",
        "generation": _next_generation(store.load_patches(), "root"),
        "claims": derived,
        "unknowns": _structural_unknowns(inventory, xref, graph),
    }
    validator = Validator.load(schema_path(SKILL_ROOT))
    errors = validate_patch(patch, validator)
    if errors:
        raise CdpError("derived claims failed their own schema:\n  " + "\n  ".join(errors[:10]))

    # M2.3: the log holds `patch` exactly as derived, unverified. Verification
    # runs inside `fold`, against `paths.repo`, so it is re-runnable at a
    # different commit without mutating the log (`cdp/state.py` `fold`).
    store.write_derived_patch(patch)
    store.ensure_inbox()

    st = _fold_and_write(store, xref, part, repo=paths.repo)
    verify_stats = st["verification"]
    say("verify    %d/%d derived claims anchored (%d demoted, rate %.3f)"
        % (verify_stats["claims_kept"], verify_stats["claims_in"],
           verify_stats["claims_demoted"], verify_stats["demotion_rate"]))
    say("merge     %d claims over %d subjects, %d conflicts, %d near-misses"
        % (len(st["claims"]), st["merge_stats"]["groups"],
           len(st["conflicts"]), len(st["near_misses"])))

    store.write_report("verify", verify_stats)
    store.write_report("conflicts", {"conflicts": st["conflicts"], "near_misses": st["near_misses"]})
    store.write_artifact(
        "manifest",
        {
            "cdp_version": CDP_VERSION,
            "run_id": run_id,
            "repo": str(paths.repo),
            "head": inventory["head"],
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "budgets": {
                "max_leaf_files": args.max_leaf_files,
                "max_leaf_loc": args.max_leaf_loc,
                "max_concurrent": args.max_concurrent,
                "max_hops": args.max_hops,
            },
            "module_level": sched["module_level"],
            "coverage": st["coverage"],
            "counts": inventory["counts"],
            # PLAN.md C2: tokens are not measurable under in-session execution.
            # This is: the exact source volume the run authorises agents to read.
            "source_loc_scheduled": sched["totals"]["source_loc_scheduled"],
            "note": (
                "manifest.json is the only state file containing a timestamp, and is excluded "
                "from the byte-identical reproducibility check for that reason."
            ),
        },
    )

    # §C item 1.2: docs were a separate command, so a rescan produced state and
    # no visible output, and the user-facing half of the module-detection bug
    # was invisible until someone remembered to run `cdp docs`. Rendering here
    # is the default; `--no-docs` opts out.
    if getattr(args, "docs", True):
        written = _render_docs(query_mod.Store(store), state_dir / "docs")
        say("docs      %d file(s) -> %s" % (len(written), state_dir / "docs"))

    if paths.inside_repo():
        _ensure_gitignore(paths.repo)
    say("\nstate     %s" % state_dir)
    say("next      cdp query stats | cdp query trace <entrypoint> | cdp prompts")
    store.close()
    return 0


def _structural_unknowns(inventory: Dict, xref: Dict, graph: Dict) -> List[Dict]:
    out: List[Dict] = []
    root = inventory.get("root_module") or {}
    if root.get("is_module") and not root.get("named"):
        out.append(
            {
                "question": "What is this module called?",
                "why_unresolved": (
                    "The scan root holds a build manifest (%s) and no sub-manifests, so the "
                    "repository is one module — but the manifest states no name, and the "
                    "directory name is an artifact of where the repository was cloned rather "
                    "than the module's identity. It is reported as %s rather than guessed."
                    % (root.get("manifest") or "unreadable", ROOT_MODULE_LABEL)
                ),
            }
        )
    for row in graph.get("declared_ambiguous", []):
        out.append(
            {
                "question": "Which module does %s's declared dependency on '%s' point at?"
                % (row["from"], row["dep"]),
                "why_unresolved": (
                    "%d modules share the basename '%s' (%s). A build manifest names a "
                    "dependency by its short name, and picking one of two equally-supported "
                    "candidates would assert an edge the repository does not state, so no "
                    "declared edge is drawn."
                    % (len(row["candidates"]), row["dep"], ", ".join(row["candidates"]))
                ),
            }
        )
    if inventory["source"] == "walk":
        out.append(
            {
                "question": "Which files in this repository are generated rather than authored?",
                "why_unresolved": (
                    "The target is not a git repository, so the inventory came from a filesystem "
                    "walk with a heuristic exclude list. Generated and build-output files may be "
                    "present in the census and described as if they were design."
                ),
            }
        )
    for module in inventory["modules"]:
        if module.get("generated_suspect"):
            out.append(
                {
                    "question": "What contract does %s actually publish?" % module["name"],
                    "why_unresolved": (
                        "%d of its %d files are untracked and generated at build time, so its "
                        "public surface cannot be read from the repository."
                        % (module.get("on_disk", 0) - module["files"], module.get("on_disk", 0))
                    ),
                }
            )
    for route in xref["unresolved_routes"]:
        out.append(
            {
                "question": "What literal path does %s serve?" % route["route"],
                "why_unresolved": "Constant(s) %s are not defined anywhere in the repository."
                % ", ".join(route.get("unresolved_constants", [])),
                "anchor": route["evidence"][0],
            }
        )
    return out


def _ensure_gitignore(repo: Path) -> None:
    path = repo / ".gitignore"
    entry = ".cdp/"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if entry in existing.split():
        return
    write_text(path, (existing.rstrip("\n") + "\n" if existing else "") + entry)


def _fold_and_write(
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


# ------------------------------------------------------------------ query


def _apply_as_of(store: "query_mod.Store", commit: str) -> None:
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


def cmd_query(args) -> int:
    store = query_mod.Store(_open_store(_paths(args).state))
    if getattr(args, "as_of", None):
        _apply_as_of(store, args.as_of)
    fn = query_mod.QUERIES[args.kind]
    # One `Budget` per response, shared by every list in it. `stats` and
    # `coverage` are constructed without one and take no `budget` argument, so
    # the exemption is enforced by their signatures rather than by a convention.
    unbudgeted = args.kind in query_mod.UNBUDGETED
    if unbudgeted and args.budget is not None:
        raise CdpError(
            "`query %s` is never budgeted: it is the check `SKILL.md` tells you to "
            "run before concluding that something is absent, and a budgeted "
            "guardrail cannot detect a budgeted answer." % args.kind
        )
    budget = None if unbudgeted else query_mod.Budget(args.budget)

    if args.kind in ("symbol", "file", "module", "search"):
        if not args.term:
            raise CdpError("`query %s` needs a term" % args.kind)
        result = fn(store, args.term, budget=budget)
    elif args.kind == "trace":
        if not args.term:
            raise CdpError("`query trace` needs an entry point")
        result = fn(store, args.term, max_hops=args.max_hops, budget=budget)
    elif args.kind in ("routes", "table", "config", "unknowns"):
        result = fn(store, args.term, budget=budget)
    elif args.kind == "paths":
        result = fn(store, args.frm, args.to, budget=budget)
    elif args.kind == "claims":
        result = fn(store, args.claim_kind or args.term, args.module, args.subject,
                    budget=budget)
    else:
        result = fn(store)

    if args.json:
        print(__import__("json").dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(query_mod.render(result))
    store.close()
    return 0


# ------------------------------------------------------------------- docs


def _render_docs(store: "query_mod.Store", out: Path) -> List[Path]:
    """The one call site for the renderer.

    `scan` and `docs` both render, and if they did it through two argument lists
    they could drift — at which point the golden baseline, which captures
    `cdp docs`, would stop describing what `cdp scan` writes.
    """
    return docs_mod.render_all(
        out, store.inventory, store.extraction, store.graph, store.partition,
        store.xref, store.dataflow, store.state, store.manifest,
    )


def cmd_docs(args) -> int:
    paths = _paths(args)
    store = query_mod.Store(_open_store(paths.state))
    out = Path(args.out).expanduser().resolve() if args.out else paths.state / "docs"
    for path in _render_docs(store, out):
        print(path)
    store.close()
    return 0


# ---------------------------------------------------------------- prompts


def cmd_prompts(args) -> int:
    paths = _paths(args)
    backend = _open_store(paths.state)
    store = query_mod.Store(backend)
    sched = store._load("schedule")
    run_id = store.manifest.get("run_id", "cdp")
    prior = list(store.state.get("claims", []))

    out_dir = paths.state / "prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    backend.ensure_inbox()

    written: List[Dict] = []
    for scope in store.partition["scopes"]:
        node = scope["node"]
        if args.node and node != args.node:
            continue
        if args.wave is not None and sched["node_wave"].get(node) != args.wave:
            continue
        text, stats = build_prompt(
            scope, store.inventory, store.extraction, store.xref, sched, prior, run_id
        )
        path = out_dir / (node.replace("/", "__") + ".md")
        write_text(path, text)
        stats["prompt"] = str(path)
        stats["wave"] = sched["node_wave"].get(node)
        written.append(stats)

    backend.write_report("prompts", {"prompts": written})
    if args.measure:
        _print_token_report(written)
        backend.close()
        return 0
    fired = [w for w in written if w["budget_fired"]]
    print("wrote %d prompt(s) to %s" % (len(written), out_dir))
    for row in written:
        print("  wave %-2s %-60s %2d files, sigma %d claim(s)%s"
              % (row["wave"], row["node"], row["files"], row["inherited_claims"],
                 "  BUDGET FIRED (%d elided)" % row["elided_claims"] if row["budget_fired"] else ""))
    if not fired:
        print("\ninherited-sigma budget never fired; the 200-claim default is not binding here.")
    backend.close()
    return 0


def _print_token_report(written: List[Dict]) -> None:
    """M5.6 (4.9): sum every leaf's per-section chars and report the
    fixed/variable split `CDP_CLI_SCOPE.md` says to measure before deciding on
    batching. `header`+`task` do not grow with scope size -- they are the
    part of the cost that scales with *scope count*, which is the shape a
    wrong cost curve would have."""
    if not written:
        print("no scopes matched -- nothing to measure")
        return
    section_totals: Dict[str, int] = {}
    for row in written:
        for name, chars in row["section_chars"].items():
            section_totals[name] = section_totals.get(name, 0) + chars
    total_tokens = sum(row["tokens_est"] for row in written)
    fixed_tokens = sum(row["fixed_tokens_est"] for row in written)
    n = len(written)
    print("measured  %d leaf prompt(s), chars/%d token estimate (not a real tokenizer)"
          % (n, prompts_mod.CHARS_PER_TOKEN_EST))
    for name, chars in sorted(section_totals.items(), key=lambda kv: -kv[1]):
        print("  %-10s %8d chars  (%d/leaf avg)" % (name, chars, chars // n))
    print("total     %d tokens_est (%d/leaf avg)" % (total_tokens, total_tokens // n))
    print("fixed     %d tokens_est (%d/leaf avg) -- header+task, independent of scope content"
          % (fixed_tokens, fixed_tokens // n))
    print("variable  %d tokens_est (%d/leaf avg) -- files/structure/inherited/gaps"
          % (total_tokens - fixed_tokens, (total_tokens - fixed_tokens) // n))


# ---------------------------------------------------------------- collect


def cmd_collect(args) -> int:
    """Validate, verify and append every patch an agent left in the inbox.

    §3.5's retry contract lives here in its terminal form: a patch that fails
    validation is recorded `invalid` with the specific violations attached, and
    no claim from it enters state. The three attempts happen in the session,
    which is the only place that can ask the agent to try again.
    """
    paths = _paths(args)
    backend = _open_store(paths.state)
    store = query_mod.Store(backend)
    inbox = backend.read_inbox()

    validator = Validator.load(schema_path(SKILL_ROOT))
    scope_nodes = {s["node"] for s in store.partition["scopes"]}
    accepted: List[Dict] = []
    rejected: List[Dict] = []

    for name, patch in inbox:
        if isinstance(patch, ValueError):
            rejected.append({"file": name, "errors": ["not valid JSON: %s" % patch]})
            continue
        errors = validate_patch(patch, validator)
        node = str(patch.get("node", ""))
        if node not in scope_nodes:
            errors.append("/node: %r is not a scope in partition.json" % node)
        if errors:
            rejected.append({"file": name, "node": node, "errors": errors[:12]})
            backend.append_patch(
                {
                    "schema_version": "1.0.0",
                    "node": node or Path(name).stem,
                    "run_id": str(patch.get("run_id", store.manifest.get("run_id", "cdp"))),
                    "status": "invalid",
                    "error": "; ".join(errors[:6]),
                },
                (node or Path(name).stem) + "-invalid",
            )
            continue
        accepted.append(patch)

    # M4.2: the four unknown gates. Subject/negative-entailment/provenance run
    # here, per-patch, before a patch's `unknowns[]` is appended to the log --
    # the same point schema validation already runs at. Clustering (gate 4)
    # runs inside `fold` instead (`cdp/gates.py` `cluster_unknowns`), since
    # cluster membership is a property of the whole current unknown set.
    def_fqns, edge_subjects, edges_by_key = gates_mod.build_extraction_index(store.extraction)
    node_to_hash = {s["node"]: s.get("scope_hash") for s in store.partition["scopes"]}
    task_states_cache: Dict[str, Dict[str, Dict]] = {}
    unknown_rejections: List[Dict] = []

    def _task_rows_for(run_id: str) -> Dict[str, Dict]:
        if run_id not in task_states_cache:
            getter = getattr(backend, "task_states", None)
            task_states_cache[run_id] = getter(run_id) if callable(getter) else {}
        return task_states_cache[run_id]

    # M2.3: append the raw, unverified patch. Verification runs inside
    # `fold`, against `paths.repo`, not here — see `cli.py` `cmd_scan`.
    log_so_far = backend.load_patches()
    for patch in accepted:
        patch.setdefault("author_kind", "llm")
        node = str(patch.get("node", "leaf"))
        patch["generation"] = _next_generation(log_so_far, node)
        log_so_far.append(patch)
        _stamp_claims(patch.get("claims") or [], store.inventory["head"])
        run_id = str(patch.get("run_id", store.manifest.get("run_id", "cdp")))
        task_rows = _task_rows_for(run_id).get(node_to_hash.get(node))
        kept_unknowns, patch_rejections = gates_mod.gate_patch_unknowns(
            patch.get("unknowns") or [], node, def_fqns, edge_subjects, edges_by_key,
            scope_nodes, {node: task_rows},
        )
        patch["unknowns"] = kept_unknowns
        unknown_rejections.extend(patch_rejections)
        backend.append_patch(patch, node)
        backend.clear_inbox(str(patch.get("node", "")))

    folded = _fold_and_write(backend, store.xref, store.partition, repo=paths.repo, mode=args.mode)
    stats = folded["verification"]
    backend.write_report("verify", stats)
    backend.write_report("rejected", {"rejected": rejected})
    backend.write_report("unknown_gates", {"rejected": unknown_rejections})

    print("accepted  %d patch(es), rejected %d" % (len(accepted), len(rejected)))
    if stats["claims_in"]:
        print("verify    %d/%d claims kept, demotion rate %.3f (%s)"
              % (stats["claims_kept"], stats["claims_in"], stats["demotion_rate"],
                 ", ".join("%s %d" % kv for kv in stats["reasons"].items()) or "no failures"))
        # PLAN.md C1: the number that decides whether the strict reading of
        # §5.4 is buying correctness or costing recall.
        print("          %d demoted claim(s) had at least one good anchor "
              "(would survive under --mode lenient)" % stats["would_survive_lenient"])
    for row in rejected:
        print("  REJECTED %s (%s)" % (row["file"], row.get("node", "?")))
        for err in row["errors"][:4]:
            print("    %s" % err)
    if unknown_rejections:
        print("gates     %d unknown(s) rejected" % len(unknown_rejections))
        for row in unknown_rejections[:8]:
            print("  REJECTED unknown (%s): %s" % (row["node"], row["reason"]))
    print("coverage  %.1f%%" % (100 * folded["coverage"]["fraction"]))
    backend.close()
    return 0


# ------------------------------------------------------------------- fold


def cmd_fold(args) -> int:
    paths = _paths(args)
    backend = _open_store(paths.state)
    store = query_mod.Store(backend)
    if args.check:
        problems = state_mod.check_fold(backend, store.xref, store.partition, repo=paths.repo)
        problems += state_mod.check_order_independence(
            backend.load_patches(), store.xref, store.partition
        )
        backend.close()
        if problems:
            for problem in problems:
                print("FAIL  %s" % problem)
            return 1
        print("ok    state.json = fold(merge, patches/, xref.json)")
        print("ok    merge is order-independent under reordering of the log")
        return 0
    folded = _fold_and_write(backend, store.xref, store.partition, repo=paths.repo)
    print("folded %d patch(es) -> %d claims, %d unknowns, coverage %.1f%%"
          % (folded["provenance"]["patch_count"], len(folded["claims"]),
             len(folded["unknowns"]), 100 * folded["coverage"]["fraction"]))
    backend.close()
    return 0


# --------------------------------------------------------------- refresh


def cmd_refresh(args) -> int:
    """M3.3: re-verify every live claim against HEAD, zero model calls.

    Re-derives nothing: the patch log is untouched (R5). What moves is the
    *view* -- incremental extraction (M3.2) for `xref`/`graph`/`dataflow`, and
    rename-aware re-verification for the claims already in the log, via the
    same `rename_map`/`edited_files` arguments `state.fold` now accepts.
    """
    paths = _paths(args)
    backend = _open_store(paths.state)
    store = query_mod.Store(backend)
    prior_snapshot_id = backend.snapshot_id()
    say = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    if snapshot_mod.is_dirty(paths.repo):
        raise CdpError("refresh requires a clean working tree (dirty trees are ephemeral, "
                       "never a refresh target)")
    prev_head = store.inventory.get("head")
    new_head = _git_head_or_raise(paths.repo)
    if prev_head in (None, "unpinned"):
        raise CdpError("no prior scan to refresh from -- run `cdp scan` first")
    if new_head == prev_head:
        say("refresh   HEAD unchanged (%s); nothing to do" % new_head[:12])
        backend.close()
        return 0

    history_ok = True
    try:
        rename_map, edited, added, deleted = refresh_mod.classify_changes(paths.repo, prev_head, new_head)
    except refresh_mod.HistoryUnavailable:
        history_ok = False
        rename_map, edited, added, deleted = {}, set(), set(), set()

    new_inventory = inventory_mod.build_inventory(paths.repo)
    if history_ok:
        changed = set(rename_map.values()) | edited | added
    else:
        changed = {e["path"] for e in new_inventory["files"]}
    new_extraction = refresh_mod.incremental_extract(paths.repo, new_inventory, store.extraction, changed)

    new_graph = graph_mod.build_graph(new_inventory, new_extraction)
    new_xref = resolve_mod.build_xref(new_inventory, new_extraction, new_graph)
    budgets = store.manifest.get("budgets", {})
    new_part = partition_mod.partition(
        new_inventory,
        budgets.get("max_leaf_files", partition_mod.DEFAULT_MAX_FILES),
        budgets.get("max_leaf_loc", partition_mod.DEFAULT_MAX_LOC),
    )
    refresh_mod.annotate_scope_hashes(paths.repo, new_part)
    dispatch = refresh_mod.changed_scopes(store.partition, new_part)
    new_flow = dataflow_mod.build_dataflow(
        new_extraction, new_xref, new_graph, budgets.get("max_hops", dataflow_mod.DEFAULT_MAX_HOPS)
    )

    # Read before `begin_snapshot` moves the backend's selection forward --
    # `store` wraps this same backend instance, and `state` is not read
    # anywhere above this line, so reading it after the snapshot switch would
    # silently return the new (not-yet-written) snapshot's empty default.
    before_demoted = len(store.state.get("unknowns", []))

    backend.begin_snapshot(*snapshot_mod.resolve_snapshot(paths.repo, new_inventory["head"]))
    # M2.4's per-snapshot patch isolation (`test_store_sqlite.py`) means the
    # snapshot just selected starts with an empty log. Carry the prior
    # snapshot's log forward verbatim -- refresh re-verifies the *existing*
    # log (D10), it never appends to it, so an empty one would fold to zero
    # claims regardless of how many were live a moment ago.
    if not backend.load_patches():
        backend.copy_patches_from(prior_snapshot_id)
    backend.write_artifact("inventory", new_inventory)
    backend.write_artifact("extract", new_extraction)
    backend.write_artifact("graph", new_graph)
    backend.write_artifact("partition", new_part)
    backend.write_artifact("xref", new_xref)
    backend.write_artifact("dataflow", new_flow)
    folded = state_mod.fold(
        backend.load_patches(), new_xref, new_part, repo=paths.repo, mode=args.mode,
        rename_map=rename_map, edited_files=frozenset(edited),
        excluded_run_ids=rollback_mod.load_excluded_run_ids(backend),
        extraction=new_extraction,
    )
    backend.write_artifact("state", folded)
    backend.write_artifact(
        "manifest",
        dict(store.manifest, head=new_inventory["head"],
             generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")),
    )

    buckets = freshness_mod.bucket_counts(folded["claims"], paths.repo, new_head)
    after_demoted = len(folded.get("unknowns", []))
    say("refresh   %s -> %s" % (prev_head[:12], new_head[:12]))
    if not history_ok:
        say("          history unavailable for that range (rebase/shallow) -- full "
            "re-extract, staleness reported as unknown rather than assumed live")
    say("extract   %d file(s) changed (renamed/edited/added), %d total parsed"
        % (len(changed), new_extraction["totals"]["parsed_files"]))
    say("rename    %d file(s) renamed, %d edited, %d added, %d deleted"
        % (len(rename_map), len(edited), len(added), len(deleted)))
    say("scopes    %d/%d changed (dispatch needed for %d, %d reuse the prior claim)"
        % (len(dispatch), len(new_part["scopes"]), len(dispatch),
           len(new_part["scopes"]) - len(dispatch)))
    say("verify    %d live, %d stale, %d anchored-but-unreviewed, %d unknown-churn "
        "(%d newly demoted), zero model calls"
        % (buckets[freshness_mod.LIVE], buckets[freshness_mod.STALE],
           buckets[freshness_mod.UNREVIEWED], buckets[freshness_mod.UNKNOWN_CHURN],
           after_demoted - before_demoted))
    backend.close()
    return 0


def _git_head_or_raise(repo: Path) -> str:
    from .util import git_head

    head = git_head(repo)
    if head is None:
        raise CdpError("`%s` is not a git repository HEAD could be read from" % repo)
    return head


# -------------------------------------------------------------------- run


def _build_runner(args):
    if args.runner_cmd:
        return runner_mod.SubprocessRunner(shlex.split(args.runner_cmd), timeout_s=args.timeout)
    return runner_mod.FileRunner(timeout_s=args.timeout)


def _stale_nodes(store: "query_mod.Store", repo: Path) -> List[str]:
    """Nodes owning at least one non-`live` claim (M3.1's freshness bucket) --
    the set `--stale-only` re-reviews, per `ARCHITECTURE.md`'s own worked
    example ('cdp run --stale-only re-reviews just those 11 scopes')."""
    head = store.inventory.get("head")
    if not head or head == "unpinned":
        return []
    cache: freshness_mod.ChurnCache = {}
    nodes = set()
    for claim in store.state.get("claims", []):
        if freshness_mod.claim_bucket(claim, repo, head, cache) != freshness_mod.LIVE:
            owners = claim.get("source_nodes") or ([claim["source_node"]] if claim.get("source_node") else [])
            nodes.update(owners)
    return sorted(nodes)


def _apply_wave_results(backend, store, results: List[Dict], run_id: str, mode: str, paths: "Paths") -> Dict:
    """The terminal outcome of one wave: append a `complete` patch for every
    scope that validated, a `status: failed` patch (no claims) for every one
    abandoned -- `state.fold`'s existing superseded-node handling turns the
    latter into an honest unknown (R6) with no further code here -- then one
    fold for the whole wave, and bump `validated` tasks to `folded`."""
    log_so_far = backend.load_patches()
    def_fqns, edge_subjects, edges_by_key = gates_mod.build_extraction_index(store.extraction)
    scope_nodes = {s["node"] for s in store.partition["scopes"]}
    node_to_hash = {s["node"]: s.get("scope_hash") for s in store.partition["scopes"]}
    task_rows = backend.task_states(run_id)
    for row in results:
        node = row["node"]
        if row["state"] == supervisor_mod.VALIDATED and row["patch"] is not None:
            patch = dict(row["patch"])
            patch["node"] = node
            patch["run_id"] = run_id
            patch["status"] = "complete"
            patch.setdefault("author_kind", "llm")
            patch["generation"] = _next_generation(log_so_far, node)
            log_so_far.append(patch)
            _stamp_claims(patch.get("claims") or [], store.inventory["head"])
            kept, _rejected = gates_mod.gate_patch_unknowns(
                patch.get("unknowns") or [], node, def_fqns, edge_subjects, edges_by_key,
                scope_nodes, {node: task_rows.get(node_to_hash.get(node))},
            )
            patch["unknowns"] = kept
            backend.append_patch(patch, node)
            backend.clear_inbox(node)
        elif row["state"] == supervisor_mod.ABANDONED:
            backend.append_patch(
                {"schema_version": "1.0.0", "node": node, "run_id": run_id, "status": "failed",
                 "error": row["last_error"] or "abandoned after %d attempts" % row["attempts"]},
                node + "-abandoned",
            )
    folded = _fold_and_write(backend, store.xref, store.partition, repo=paths.repo, mode=mode)
    supervisor_mod.mark_folded(backend, run_id, results)
    return folded


def _next_run_id(backend, base_run_id: str) -> str:
    """First `<base_run_id>-rN` (N starting at 2) not already a run in this
    store -- the new run `--resume` opens when the partition has drifted."""
    n = 2
    while backend.get_run("%s-r%d" % (base_run_id, n)) is not None:
        n += 1
    return "%s-r%d" % (base_run_id, n)


def cmd_run(args) -> int:
    """M5.3: `read schedule -> dispatch a wave -> collect -> adjudicate ->
    fold -> next wave`. `prompts`/`collect` still work standalone (M5.1's
    protocol doc); this drives them through `supervisor.py`'s state machine
    (M5.2) instead of a human running the loop from `SKILL.md`.

    `--resume` (M5.5, 4.6): `runs.partition_hash` (a `stable_hash` of every
    scope's `(node, scope_hash)`, computed fresh from *this* invocation's
    partition) decides which of two things happened since the run named by
    `manifest.run_id` last touched this store:

      unchanged  -- the same run continues. Any task still `dispatched` past
                    its lease is reclaimed as `expired` (the supervisor that
                    held it is presumed dead) and re-attempted; `folded` tasks
                    are left alone -- untouched and unpaid-for again.
      differs    -- a file changed the partition since this run started
                    (Phase 3's open interaction: a `refresh` landing mid-run).
                    Folding stale work against a changed partition is exactly
                    what R6/the merge operator must not do, so this opens a
                    *new* run (`<run_id>-rN`) rather than continuing the old
                    one, inheriting every scope whose own `scope_hash` did not
                    move (nothing to redo) and re-queuing the rest.

    Without `--resume`, a second invocation behaves as before M5.5: it
    reuses the existing run row (`begin_run` is idempotent) and redispatches
    everything asked for, from a fresh `--max-attempts` budget -- correct, but
    not resume-aware.
    """
    paths = _paths(args)
    backend = _open_store(paths.state)
    store = query_mod.Store(backend)
    sched = store._load("schedule")
    run_id = str(store.manifest.get("run_id", "cdp"))
    validator = Validator.load(schema_path(SKILL_ROOT))
    runner = _build_runner(args)

    partition_hash = stable_hash(
        sorted((s["node"], s.get("scope_hash")) for s in store.partition["scopes"])
    )
    skip_hashes: Set[str] = set()
    existing = backend.get_run(run_id)
    if existing is None:
        backend.begin_run(run_id, partition_hash)
    elif not args.resume:
        backend.begin_run(run_id, partition_hash)  # idempotent no-op; pre-M5.5 behaviour
    elif existing["partition_hash"] == partition_hash:
        reclaimed = backend.reclaim_expired(run_id)
        if reclaimed:
            print("resume    run %s: partition unchanged, reclaimed %d task(s) past lease"
                  % (run_id, len(reclaimed)))
        skip_hashes = {sh for sh, row in backend.task_states(run_id).items() if row["state"] == "folded"}
    else:
        old_run_id = run_id
        old_folded = {sh for sh, row in backend.task_states(old_run_id).items() if row["state"] == "folded"}
        new_hashes = {s.get("scope_hash") for s in store.partition["scopes"]}
        unchanged = old_folded & new_hashes
        run_id = _next_run_id(backend, old_run_id)
        backend.begin_run(run_id, partition_hash)
        backend.copy_folded_tasks(old_run_id, run_id, unchanged)
        skip_hashes = set(unchanged)
        print("resume    partition changed since run %s -- opened new run %s, "
              "inherited %d unchanged scope(s), %d re-queued"
              % (old_run_id, run_id, len(unchanged), len(new_hashes) - len(unchanged)))

    if args.stale_only:
        stale = _stale_nodes(store, paths.repo)
        if not stale:
            print("stale-only  zero scopes need review")
            backend.finish_run(run_id, "complete")
            backend.close()
            return 0
        wave_groups = [("stale", stale)]
    elif args.scope:
        if args.scope not in {s["node"] for s in store.partition["scopes"]}:
            raise CdpError("%r is not a scope in partition.json" % args.scope)
        wave_groups = [("scope", [args.scope])]
    elif args.wave is not None:
        wave = next((w for w in sched["waves"] if w["wave"] == args.wave), None)
        if wave is None:
            raise CdpError("no wave %d (schedule has %d)" % (args.wave, len(sched["waves"])))
        wave_groups = [(args.wave, wave["nodes"])]
    else:  # --wave-all
        wave_groups = [(w["wave"], w["nodes"]) for w in sched["waves"]]

    for label, nodes in wave_groups:
        results = supervisor_mod.run_wave(
            nodes, store, backend, runner, paths, run_id, validator, sched, args.mode,
            max_attempts=args.max_attempts, skip_hashes=skip_hashes,
        )
        _apply_wave_results(backend, store, results, run_id, args.mode, paths)
        counts: Dict[str, int] = {}
        for row in results:
            counts[row["state"]] = counts.get(row["state"], 0) + 1
        print("wave %-6s %2d scope(s)  %s" % (label, len(results),
              ", ".join("%s %d" % kv for kv in sorted(counts.items())) or "nothing to dispatch"))
        for row in results:
            if row["state"] != supervisor_mod.VALIDATED:
                print("  %-9s %-40s attempts %d  %s"
                      % (row["state"], row["node"], row["attempts"], row["last_error"] or ""))
        store = query_mod.Store(backend)  # re-read state.json: next wave inherits this wave's claims

    backend.finish_run(run_id, "complete")
    backend.close()
    return 0


# ----------------------------------------------------------------- status


def cmd_status(args) -> int:
    paths = _paths(args)
    store = query_mod.Store(_open_store(paths.state))
    sched = store._load("schedule")
    state = store.state
    statuses = state.get("nodes", {})
    print("run       %s @ %s" % (store.manifest.get("run_id", "?"), store.inventory["head"][:12]))
    print("coverage  %.1f%% (%d/%d tracked files)"
          % (100 * state["coverage"]["fraction"], state["coverage"]["files_complete"],
             state["coverage"]["files_total"]))
    head = store.inventory.get("head")
    if head and head != "unpinned" and state.get("claims"):
        # 0.9/3.6: three buckets over live claims, none a subset of the others --
        # "anchored but unreviewed" is what `run --stale-only` (Phase 5) targets.
        buckets = freshness_mod.bucket_counts(state["claims"], paths.repo, head)
        print("freshness %d live, %d stale, %d anchored-but-unreviewed, %d unknown-churn"
              % (buckets[freshness_mod.LIVE], buckets[freshness_mod.STALE],
                 buckets[freshness_mod.UNREVIEWED], buckets[freshness_mod.UNKNOWN_CHURN]))
    for wave in sched["waves"]:
        done = sum(1 for n in wave["nodes"] if statuses.get(n) == "complete")
        print("wave %-2d L%s  %d/%d complete  %d files, %d loc"
              % (wave["wave"], wave["level"], done, len(wave["nodes"]),
                 wave["file_count"], wave["loc"]))
        for node in wave["nodes"]:
            print("    %-9s %s" % (statuses.get(node, "pending"), node))

    # M5.2: `cdp run`'s per-run task table -- `snapshot_task`, not `nodes[]`
    # above (that is the patch log's own status; this is the supervisor's
    # dispatch bookkeeping for the run named on the first line).
    task_getter = getattr(store.backend, "task_rows", None)
    run_id = str(store.manifest.get("run_id", "cdp"))
    rows = task_getter(run_id) if callable(task_getter) else []
    if rows:
        node_of_hash = {s.get("scope_hash"): s["node"] for s in store.partition["scopes"]}
        print("\ntasks     run %s" % run_id)
        for row in rows:
            node = node_of_hash.get(row["scope_hash"], row["scope_hash"])
            print("    %-14s %-40s attempts %d%s"
                  % (row["state"] or "pending", node, row["attempts"] or 0,
                     "  %s" % row["last_error"] if row["last_error"] else ""))
    store.close()
    return 0


# ------------------------------------------------------------------- diff


def cmd_diff(args) -> int:
    old = query_mod.Store(Path(args.old_state).expanduser().resolve())
    new = query_mod.Store(Path(args.new_state).expanduser().resolve())
    result = diffs_mod.diff_snapshots(old.graph, old.xref, old.state, new.graph, new.xref, new.state)
    if args.json:
        print(__import__("json").dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(diffs_mod.summarise(result)))
    return 0


# --------------------------------------------------------------------- gc


def cmd_gc(args) -> int:
    """M3.6/0.10: a snapshot is kept iff HEAD, pinned, or cited by a live
    claim's `anchor_verified_at`/`claim_reviewed_at`.

    `--db` defaults to the same resolved store every other command writes
    (D3, `PHASE/FINDINGS.md`: `SqliteStore` is the CLI's actual default
    backend), so `gc` needs no separate setup step for the common case --
    only an override for retention against a store `_paths()` would not
    resolve to on its own.
    """
    paths = _paths(args)
    db_path = Path(args.db).expanduser().resolve() if args.db else (paths.state / "index.db")
    store = SqliteStore(db_path)
    try:
        repo = paths.repo
        repo_id = registry_mod.repo_identity(repo)
        for sha in args.pin:
            store.set_pinned(sha, True)
        for sha in args.unpin:
            store.set_pinned(sha, False)
        head_sha = args.head_sha or _git_head_or_raise(repo)
        snapshots = [s for s in store.list_snapshots() if s["repo_id"] == repo_id]
        if not any(s["commit_sha"] == head_sha for s in snapshots):
            raise CdpError("no snapshot for HEAD (%s) in %s -- run `cdp scan` against this store first"
                            % (head_sha[:12], db_path))
        store.begin_snapshot(repo_id, head_sha)
        head_claims = store.read_artifact("state", {}).get("claims", [])
        cited = {c.get("anchor_verified_at") for c in head_claims} | {c.get("claim_reviewed_at") for c in head_claims}
        cited.discard(None)
        keep_ids = snapshot_mod.snapshots_to_keep(snapshots, repo_id, head_sha, cited)
        drop = [s for s in snapshots if s["id"] not in keep_ids]
        print("gc        keeping %d/%d snapshot(s) (head + pinned + cited), dropping %d"
              % (len(snapshots) - len(drop), len(snapshots), len(drop)))
        for s in drop:
            print("          drop %s%s" % ((s["commit_sha"] or "?")[:12], " [dry-run]" if args.dry_run else ""))
            if not args.dry_run:
                store.delete_snapshot(s["id"])
    finally:
        store.close()
    return 0


# ---------------------------------------------------------------- rollback


def cmd_rollback(args) -> int:
    """M3.7: exclude a run's patches from the fold, without deleting them (R5).

    `--to-run` drops exactly one run, wherever it sits in the log. `--to-snapshot`
    drops that run and every run appended after it -- the log's own append
    order, since patches carry no timestamp by construction (D8). Either way
    the excluded run_ids are recorded in an append-only ledger
    (`cdp/rollback.py`) that every future fold (`scan`, `collect`, `fold`,
    `refresh`) reads, so the exclusion holds until a future rollback changes it.
    """
    paths = _paths(args)
    backend = _open_store(paths.state)
    store = query_mod.Store(backend)
    patches = backend.load_patches()

    if args.to_run:
        target = rollback_mod.resolve_run_id(args.to_run)
        kept, new_excluded = rollback_mod.patches_excluding_run(patches, target)
        if not new_excluded:
            raise CdpError("no patch in the log is stamped with run %s -- nothing to roll back" % target)
        kind = "to_run"
    else:
        target = rollback_mod.resolve_run_id(args.to_snapshot)
        kept, new_excluded, found = rollback_mod.patches_up_to_run(patches, target)
        if not found:
            raise CdpError("run %s never appended a patch -- nothing to roll back to" % target)
        if not new_excluded:
            print("rollback  --to-snapshot %s: already the most recent run, nothing to exclude" % target)
            backend.close()
            return 0
        kind = "to_snapshot"

    prior_excluded = rollback_mod.load_excluded_run_ids(backend)
    all_excluded = prior_excluded | new_excluded
    folded = state_mod.fold(
        patches, store.xref, store.partition, repo=paths.repo, mode=args.mode,
        excluded_run_ids=all_excluded,
        extraction=store.extraction,
    )
    backend.write_artifact("state", folded)
    reason = args.reason or ("rollback --%s %s" % (kind.replace("_", "-"), target))
    rollback_mod.record_rollback(backend, kind, target, new_excluded, reason)

    print("rollback  %s %s: excluded %d run(s) (%s)"
          % (("--to-run" if kind == "to_run" else "--to-snapshot"), target,
             len(new_excluded), ", ".join(sorted(new_excluded))))
    print("folded    %d claim(s), %d unknown(s), coverage %.1f%%"
          % (len(folded["claims"]), len(folded["unknowns"]), 100 * folded["coverage"]["fraction"]))
    backend.close()
    return 0


def _git_identity(repo: Path) -> str:
    name = run_git(repo, "config", "user.name")
    email = run_git(repo, "config", "user.email")
    name = (name or "").strip() or "unknown"
    email = (email or "").strip()
    return "%s <%s>" % (name, email) if email else name


def cmd_answer(args) -> int:
    """M4.4: a human claim against an unknown, through the *entire* pipeline
    -- validate, verify the anchor, entail, fold -- exactly like a leaf
    agent's patch (`cmd_collect`). `author_kind=human` changes merge
    precedence (R11) and, per `entail.py`, whether a contradiction is
    silently accepted -- it never changes the gate itself.
    """
    paths = _paths(args)
    backend = _open_store(paths.state)
    store = query_mod.Store(backend)

    scope_nodes = {s["node"] for s in store.partition["scopes"]}
    if args.scope not in scope_nodes:
        backend.close()
        raise CdpError("%r is not a scope in partition.json" % args.scope)

    file_part, sep, line_part = args.anchor.rpartition(":")
    if not sep or not line_part.isdigit():
        backend.close()
        raise CdpError("--anchor must be FILE:LINE, got %r" % args.anchor)
    abs_path = (paths.repo / file_part)
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        backend.close()
        raise CdpError("cannot read %s: %s" % (file_part, exc))
    anchor = anchor_mod.build_anchor(file_part, text.splitlines(), int(line_part) - 1)
    if anchor is None:
        backend.close()
        raise CdpError("no citable anchor at %s:%s -- humans are not exempt from anchor "
                        "verification either" % (file_part, line_part))

    claim = {
        "id": "human.%s" % stable_hash([args.scope, args.subject, args.statement])[:16],
        "kind": args.kind,
        "subject": args.subject,
        "statement": args.statement,
        "evidence": [anchor],
        "confidence": args.confidence,
        "author_kind": "human",
        "author": args.author or _git_identity(paths.repo),
    }
    if args.channel:
        claim["channel"] = args.channel

    log_so_far = backend.load_patches()
    patch = {
        "schema_version": "1.0.0",
        "node": args.scope,
        "run_id": "cdp-answer-%s" % claim["id"].split(".", 1)[1][:8],
        "status": "complete",
        "author_kind": "human",
        "generation": _next_generation(log_so_far, args.scope),
        "claims": [claim],
    }
    validator = Validator.load(schema_path(SKILL_ROOT))
    errors = validate_patch(patch, validator)
    if errors:
        backend.close()
        raise CdpError("schema-invalid claim:\n  " + "\n  ".join(errors[:10]))

    _stamp_claims(patch["claims"], store.inventory["head"])
    backend.append_patch(patch, args.scope)

    folded = _fold_and_write(backend, store.xref, store.partition, repo=paths.repo, mode=args.mode)
    kept = any(c["id"] == claim["id"] for c in folded["claims"])
    row = next((c for c in folded["claims"] if c["id"] == claim["id"]), None)
    if row is None:
        print("cdp: claim was NOT kept -- verification demoted it into unknowns[]", file=sys.stderr)
    else:
        print("answer    %s  verdict=%s  confidence=%s"
              % (claim["id"], row.get("verdict"), row.get("confidence")))
    discharged = [u for u in folded["unknowns"]
                  if u.get("status") == "resolved"
                  and (u.get("resolved_by") or {}).get("claim_id") == claim["id"]]
    for u in discharged:
        print("          discharged: %s" % u["question"])
    backend.close()
    return 0 if kept else 1


def cmd_help(args) -> int:
    """Guidance, derived from the live parser.

    `describe(_parser())` rather than a table: the command list cannot drift
    from the CLI, because it *is* the CLI. A hand-maintained help text that
    disagrees with the tool is a confident wrong answer about the tool itself.
    """
    surface = helpdoc.describe(_parser())
    if args.json:
        errors = Validator.load(schema_path_help()).validate(surface)
        if errors:
            raise CdpError(
                "`help --json` does not satisfy its own committed schema:\n  "
                + "\n  ".join(errors[:10])
            )
        print(__import__("json").dumps(surface, indent=2, sort_keys=True,
                                       ensure_ascii=False))
        return 0
    print(helpdoc.render(surface, args.topic))
    return 0


def schema_path_help() -> Path:
    from .schema import help_schema_path

    return help_schema_path(SKILL_ROOT)


def cmd_validate(args) -> int:
    validator = Validator.load(schema_path(SKILL_ROOT))
    errors = validate_patch(read_json(Path(args.path)), validator)
    if errors:
        for err in errors:
            print("FAIL  %s" % err)
        return 1
    print("ok    %s is a valid CDP patch" % args.path)
    return 0


# ---------------------------------------------------------------- install


#: Everything that constitutes the distributable skill, relative to SKILL_ROOT.
#
# This is an allow-list rather than a copy-everything-and-ignore, because
# SKILL_ROOT is now the repository root: a `copytree` with an ignore list would
# vendor `.git/`, `.venv/`, `PHASE/` and the design documents into every target
# repository, and would grow silently every time a file is added at the root.
# Naming the members means a new top-level file is *not* shipped until someone
# decides it should be.
DIST_MEMBERS = ("cdp", "tests", "schema", "agents", "run.py", "SKILL.md")

# `golden` is excluded deliberately: baselines are development artifacts of
# *this* repository, they are large, and `cdp selftest` inside a target repo has
# no use for another repository's blessed output.
_DIST_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".cdp", "runs", ".DS_Store", "golden",
)


def copy_distribution(dest: Path) -> None:
    """Materialise the skill tree at `dest`, replacing whatever was there.

    Deterministic and total: the destination afterwards contains exactly
    `DIST_MEMBERS` and nothing else, which is what makes the vendored copy
    comparable byte-for-byte against the source.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for member in DIST_MEMBERS:
        src = SKILL_ROOT / member
        if not src.exists():
            raise CdpError("distribution member missing from source tree: %s" % src)
        if src.is_dir():
            shutil.copytree(src, dest / member, ignore=_DIST_IGNORE)
        else:
            shutil.copy2(src, dest / member)


def cmd_githook(args) -> int:
    """M3.8. Distinct from `install --hook` above: that installs the
    PreToolUse nudge into `.claude/settings.json`; this installs real git
    `post-commit`/`post-checkout` hooks that call `cdp refresh`."""
    repo = _paths(args).repo
    fn = githooks_mod.install if args.action == "install" else githooks_mod.uninstall
    for line in fn(repo):
        print(line)
    return 0


def cmd_install(args) -> int:
    """Copy the skill into another repository. This is the portability story.

    One directory, no dependencies, no build step. `.claude/skills/cdp/` in the
    target is everything CDP is.

    `--self` refreshes this repository's own vendored copy. The vendored tree is
    *generated*, never hand-edited: `tests/test_distribution.py` asserts it is
    byte-identical to the source, so an edit made in the wrong place fails the
    build instead of silently diverging.
    """
    if getattr(args, "self", False):
        if args.target:
            raise CdpError("--self takes no target (it refreshes this repository)")
        target = SKILL_ROOT
    else:
        if not args.target:
            raise CdpError("install needs a target repository, or --self")
        target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        raise CdpError("not a directory: %s" % target)

    dest = target / ".claude" / "skills" / "cdp"
    copy_distribution(dest)

    agents = target / ".claude" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    source_agent = SKILL_ROOT / "agents" / "cdp-leaf.md"
    if source_agent.exists():
        shutil.copy2(source_agent, agents / "cdp-leaf.md")
    print("installed %s" % dest)
    if getattr(args, "hook", False):
        for line in install_hook(target, dest):
            print(line)
    print("try       python3 %s scan --repo %s"
          % (dest / "run.py", target))
    return 0


#: `matcher` is compared as an exact string when it contains only letters,
# digits and `|`, so this fires on exactly these three tools and nothing else.
HOOK_MATCHER = "Read|Grep|Glob"


def install_hook(target: Path, dest: Path) -> List[str]:
    """Register the PreToolUse nudge in `<target>/.claude/settings.json`.

    Before M2.6 (`PHASE/phase_2_plan.md` 2.3) this stated a hard constraint:
    the hook discovers state by walking up from the file being read
    (`hook.find_state`), so it could only ever see an *in-repo* `.cdp/`, and
    CDP's default writes state *outside* the repo (this module's docstring).
    `hook.find_state` now also consults the registry (`store.registry`), which
    `scan`'s default run populates, so a default-location scan is discoverable
    too. What is still true unconditionally: the hook cannot see a scan that
    has never happened, so that case is still named here rather than left to
    a silent no-op.
    """
    import json as json_mod

    notes: List[str] = []
    registered = registry_mod.lookup(registry_mod.repo_identity(target))
    has_state = has_scanned(target / ".cdp") or (
        registered is not None and has_scanned(registered)
    )
    if not has_state:
        notes.append(
            "note      no scan of %s yet, so the hook will no-op until you run:\n"
            "            python3 %s scan --repo %s"
            % (target, dest / "run.py", target)
        )

    settings_path = target / ".claude" / "settings.json"
    settings: Dict = {}
    if settings_path.exists():
        try:
            settings = read_json(settings_path)
        except ValueError:
            raise CdpError(
                "%s is not valid JSON; refusing to overwrite it. Fix or move it, "
                "then re-run with --hook." % settings_path
            )
    if not isinstance(settings, dict):
        raise CdpError("%s does not contain a JSON object" % settings_path)

    command = "python3 %s" % (dest / "cdp" / "hook.py")
    entry = {"type": "command", "command": command, "args": []}
    hooks = settings.setdefault("hooks", {})
    groups = hooks.setdefault("PreToolUse", [])
    for group in groups:
        if isinstance(group, dict) and group.get("matcher") == HOOK_MATCHER:
            handlers = group.setdefault("hooks", [])
            # Idempotent: re-running `install --hook` must not stack duplicates.
            if not any(h.get("command") == command for h in handlers
                       if isinstance(h, dict)):
                handlers.append(entry)
            break
    else:
        groups.append({"matcher": HOOK_MATCHER, "hooks": [entry]})

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(settings_path, settings)
    notes.insert(0, "hook      PreToolUse on %s -> %s" % (HOOK_MATCHER, settings_path))
    notes.insert(1, "          it fires only on files whose inventory role is 'source', "
                    "at most once\n          per session, and no-ops silently when "
                    "inventory.head != git HEAD.")
    notes.append("          python3 %s --explain   to see what it injects and why"
                 % (dest / "cdp" / "hook.py"))
    return notes


# ------------------------------------------------------- reproducibility gate


#: The one state file allowed to differ between two scans of one commit, and
# the one field in it allowed to do so. `cmd_scan` states this contract in
# `manifest.json`'s own `note`; until now nothing enforced it.
VOLATILE_FILE = "manifest.json"
VOLATILE_FIELDS = ("generated_at",)


def _state_files(root: Path) -> Dict[str, Path]:
    """Raw filesystem outputs under the state dir -- `docs/`, `prompts/`, and
    (for `check_determinism`'s test stubs, which write directly rather than
    through a store) anything else. Excludes `index.db`: two independent
    writes of identical content are not guaranteed byte-identical at the
    SQLite file level (page allocation, not just logical data), so its
    content is compared separately, through the store API (`_store_snapshot`).
    """
    return {
        str(p.relative_to(root)): p
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.name != "index.db"
    }


def _store_snapshot(root: Path) -> Dict[str, str]:
    """`<root>/index.db`'s content, canonically serialised through the store
    API -- comparable across two independently-written stores holding
    identical content, unlike the file's own bytes (see `_state_files`).
    `{}` vs `{}` (no differences) when no `index.db` exists at all, e.g. a
    `check_determinism` test stub that writes raw files directly."""
    backend = SqliteStore(root / "index.db")
    try:
        out = {
            "index.db:%s" % name: golden_mod.canonical(backend.read_artifact(name, {}))
            for name in ARTIFACTS
        }
        out.update({
            "index.db:reports/%s" % name: golden_mod.canonical(backend.read_report(name, {}))
            for name in REPORTS
        })
        out["index.db:patches"] = golden_mod.canonical(backend.load_patches())
        return out
    finally:
        backend.close()


def check_determinism(repo: Path, scan: Optional[Callable] = None) -> List[str]:
    """Scan `repo` twice into separate state directories and diff the results.

    Returns a list of problems; empty means the gate passed.

    Why this is not simply `diff -r`: an order-dependent merge is
    *deterministic but arbitrary*, so a harness that only compares two runs of
    the same code scores it 1.0 (`state.py:258-278` makes the same argument for
    `check_order_independence`, which is the complementary gate). This one
    catches non-determinism — `set()` iteration, dict ordering, clock and path
    leakage — and is run alongside the other, not instead of it.
    """
    import tempfile

    runner = scan or _scan_into
    problems: List[str] = []
    with tempfile.TemporaryDirectory(prefix="cdp-determinism-") as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        runner(repo, a)
        runner(repo, b)

        files_a, files_b = _state_files(a), _state_files(b)
        for rel in sorted(set(files_a) - set(files_b)):
            problems.append("%s: written by the first scan only" % rel)
        for rel in sorted(set(files_b) - set(files_a)):
            problems.append("%s: written by the second scan only" % rel)

        for rel in sorted(set(files_a) & set(files_b)):
            left, right = files_a[rel].read_bytes(), files_b[rel].read_bytes()
            if left == right:
                continue
            if rel != VOLATILE_FILE:
                problems.append(
                    "%s: differs between two scans of one commit%s"
                    % (rel, _first_difference(left, right))
                )
                continue
            problems.extend(_volatile_diff(rel, left, right))

        store_a, store_b = _store_snapshot(a), _store_snapshot(b)
        for rel in sorted(set(store_a) - set(store_b)):
            problems.append("%s: written by the first scan only" % rel)
        for rel in sorted(set(store_b) - set(store_a)):
            problems.append("%s: written by the second scan only" % rel)
        for rel in sorted(set(store_a) & set(store_b)):
            left_text, right_text = store_a[rel], store_b[rel]
            if left_text == right_text:
                continue
            left, right = left_text.encode("utf-8"), right_text.encode("utf-8")
            if rel != "index.db:manifest":
                problems.append(
                    "%s: differs between two scans of one commit%s"
                    % (rel, _first_difference(left, right))
                )
                continue
            problems.extend(_volatile_diff(rel, left, right))
    return problems


def _volatile_diff(rel: str, left: bytes, right: bytes) -> List[str]:
    """`manifest.json` may differ, but only in the fields declared volatile."""
    import json

    try:
        da, db = json.loads(left), json.loads(right)
    except ValueError as exc:
        return ["%s: not valid JSON (%s)" % (rel, exc)]
    changed = sorted(
        k for k in set(da) | set(db) if da.get(k, _MISSING) != db.get(k, _MISSING)
    )
    unexpected = [k for k in changed if k not in VOLATILE_FIELDS]
    if unexpected:
        return [
            "%s: differs in %s, which is not declared volatile (only %s may differ)"
            % (rel, ", ".join(unexpected), ", ".join(VOLATILE_FIELDS))
        ]
    return []


_MISSING = object()


def _first_difference(left: bytes, right: bytes) -> str:
    """Locate the first differing line, so the failure names a place.

    A reproducibility gate whose message is "the files differ" hands the reader
    a 400 KB diff to do by hand.
    """
    la = left.decode("utf-8", "replace").splitlines()
    lb = right.decode("utf-8", "replace").splitlines()
    for n, (x, y) in enumerate(zip(la, lb), 1):
        if x != y:
            return "\n      line %d: %.120r\n           vs: %.120r" % (n, x, y)
    return "\n      identical for %d lines, then one file ends (%d vs %d lines)" % (
        min(len(la), len(lb)), len(la), len(lb)
    )


def _scan_into(repo: Path, state: Path) -> None:
    """Run a real `cdp scan` in a subprocess.

    A subprocess rather than an in-process call on purpose: module-level caches
    and interning make a second in-process scan agree with the first for
    reasons that will not hold in production, which is exactly the false pass
    this gate exists to prevent.
    """
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "cdp.cli", "scan", "--quiet",
         "--repo", str(repo), "--state-dir", str(state)],
        cwd=str(SKILL_ROOT), capture_output=True, text=True,
        env=_deterministic_env(),
    )
    if proc.returncode != 0:
        raise CdpError("scan failed on %s:\n%s" % (repo, proc.stderr.strip()))


def _deterministic_env() -> Dict[str, str]:
    """`PYTHONHASHSEED=0` is deliberately *not* set.

    Setting it would hide precisely the bug this gate hunts: `set()` iteration
    order over strings varies with the hash seed, so pinning the seed makes a
    non-deterministic pipeline reproduce perfectly. Randomising it instead
    means two runs disagree whenever ordering leaked into the output.
    """
    import os
    import random

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(random.randint(1, 4294967295))
    env["PYTHONPATH"] = str(SKILL_ROOT)
    return env


# --------------------------------------------------------------- golden set


GOLDEN_ROOT = SKILL_ROOT / "tests" / "golden"


def _golden_terms(store) -> Dict[str, Optional[str]]:
    """Pick the arguments for the four queries that need one.

    Derived from the scanned state rather than hard-coded, so the baseline
    works against any target repository; recorded as an artifact of its own, so
    a reader of a diff can see what was actually asked. Deterministic by
    construction: first in sort order, never "most interesting".
    """
    def first(rows, key):
        names = sorted({r[key] for r in rows if r.get(key)})
        return names[0] if names else None

    symbols = getattr(store, "state", {}).get("claims", [])
    xref = getattr(store, "xref", {}) or {}
    symbol = first(xref.get("symbols", {}).values() if isinstance(
        xref.get("symbols"), dict) else xref.get("symbols", []), "fqn")
    return {
        "symbol": symbol,
        "file": first(xref.get("resolution", {}).get("files", []), "path")
        if isinstance(xref.get("resolution"), dict) else None,
        "module": first(symbols, "module"),
        "search": "config",
        # A route if the repository has one, since that is the entry point a
        # consumer actually traces; the first symbol otherwise, so the query is
        # still exercised on a repository with no HTTP surface.
        "trace": first(xref.get("routes", []), "route") or symbol,
    }


def collect_artifacts(repo: Path) -> Tuple[Dict[str, str], Optional[str]]:
    """Run `scan`, `docs` and every query; return `{name: text}` plus the head.

    In-process rather than by subprocess: unlike the determinism gate, which
    must not share a interpreter with the run it is checking, this one only
    needs the output, and thirteen subprocess scans are thirteen redundant
    scans.
    """
    import tempfile

    artifacts: Dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="cdp-golden-") as tmp:
        state = Path(tmp) / "state"
        _scan_into(repo, state)

        # Read back through the store API (D3, `PHASE/FINDINGS.md`), not a raw
        # filesystem walk: the default backend is `SqliteStore`, one binary
        # file, which a byte-diff cannot describe. `golden_mod.canonical`
        # re-serialises every artifact the same way regardless of backend, so
        # capture is a function of content, not of the storage format.
        backend = SqliteStore(state / "index.db")
        for name in ARTIFACTS:
            artifacts["scan/%s.json" % name] = golden_mod.canonical(
                backend.read_artifact(name, {})
            )
        for name in REPORTS:
            artifacts["scan/reports/%s.json" % name] = golden_mod.canonical(
                backend.read_report(name, {})
            )
        artifacts["scan/patches.json"] = golden_mod.canonical(backend.load_patches())
        head = backend.read_artifact("inventory").get("head")
        backend.close()

        # `docs` is driven through the CLI so the golden set covers the command
        # a user runs, not an internal function it happens to call today.
        docs_dir = Path(tmp) / "docs"
        _run_cli(["docs", "--repo", str(repo), "--state-dir", str(state),
                  "--out", str(docs_dir)])
        for path in sorted(docs_dir.rglob("*")):
            if path.is_file():
                artifacts["docs/%s" % path.relative_to(docs_dir).as_posix()] = (
                    path.read_text(encoding="utf-8", errors="replace")
                )

        store = query_mod.Store(state)
        terms = _golden_terms(store)
        artifacts["query/_terms.json"] = golden_mod.canonical(terms)
        for kind in sorted(query_mod.QUERIES):
            argv = ["query", kind, "--json", "--repo", str(repo),
                    "--state-dir", str(state)]
            term = terms.get(kind)
            if kind in ("symbol", "file", "module", "search", "trace"):
                if not term:
                    artifacts["query/%s.json" % kind] = (
                        '"no term available in this repository; query not run"\n'
                    )
                    continue
                argv.append(term)
            artifacts["query/%s.json" % kind] = _run_cli(argv)
        store.close()
    return artifacts, head


def _run_cli(argv: List[str]) -> str:
    """Invoke a CDP command and capture its stdout."""
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    if code:
        raise CdpError("`cdp %s` exited %d" % (" ".join(argv[:2]), code))
    return buf.getvalue()


def _git(repo: Path, *args: str) -> Optional[str]:
    import subprocess

    try:
        proc = subprocess.run(["git", "-C", str(repo)] + list(args),
                              capture_output=True, text=True)
    except OSError:
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


@contextlib_contextmanager
def pristine_checkout(repo: Path):
    """Yield a clean checkout of `repo`'s HEAD, or `repo` itself if not git.

    A golden baseline is pinned to a commit, so it must be a function of that
    commit. Scanning the working tree instead makes it a function of the
    working tree: `inventory["counts"]["on_disk"]` counts untracked files, so
    `.venv/`, `__pycache__/` and — self-referentially — the golden directory
    being written all move the numbers. Blessing a baseline from a dirty tree
    produces one that fails on its next run, in this repository by construction.

    A detached worktree at HEAD has none of that: tracked files only, no venv,
    no build output. It also settles the "two developers on different
    filesystems" case, since neither developer's untracked clutter is present.
    """
    import subprocess
    import tempfile

    if not (repo / ".git").exists() or _git(repo, "rev-parse", "HEAD") is None:
        yield repo, False
        return
    with tempfile.TemporaryDirectory(prefix="cdp-pristine-") as tmp:
        work = Path(tmp) / "tree"
        proc = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", "-q",
             str(work), "HEAD"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            # Degrade honestly rather than silently baselining the dirty tree.
            raise CdpError(
                "could not create a clean checkout of %s for the golden baseline:\n%s\n"
                "A baseline captured from a dirty working tree is not reproducible."
                % (repo, proc.stderr.strip())
            )
        try:
            yield work, True
        finally:
            subprocess.run(["git", "-C", str(repo), "worktree", "remove",
                            "--force", str(work)], capture_output=True)


def run_golden(repo: Path, bless: bool = False, name: Optional[str] = None) -> Tuple[int, str]:
    """Compare `repo`'s output against its baseline. Returns (exit code, report).

    `name` overrides the baseline directory. The fixture needs it: `make_repo`
    commits a fresh repository per run, so its SHA — and therefore its default
    slug — is different every time, and a baseline keyed on it would be written
    once and never read again.
    """
    with pristine_checkout(repo) as (target, pinned):
        artifacts, head = collect_artifacts(target)
        captured = golden_mod.capture(artifacts, target, head)
    golden_dir = GOLDEN_ROOT / (name or golden_mod.slug(repo.name, head))
    note = "" if pinned else (
        "\nnote  %s is not a git repository; the baseline was captured from the "
        "working tree and will churn with untracked files." % repo
    )

    if bless:
        golden_mod.write(golden_dir, captured)
        return 0, "blessed %d artifact(s) -> %s%s" % (len(captured), golden_dir, note)

    expected = golden_mod.read(golden_dir)
    if not expected:
        return 1, (
            "no golden baseline at %s.\n"
            "Capture one with `cdp selftest --golden %s --bless`." % (golden_dir, repo)
        )
    reports = golden_mod.compare(expected, captured)
    return (1 if reports else 0), golden_mod.summarise(reports) + note


def cmd_selftest(args) -> int:
    """Run the bundled tests.

    Spawned as a subprocess with `cwd` set to the tests directory rather than
    discovered in-process: the test modules import `helpers`, which needs to be
    importable, and in-process discovery silently found zero tests instead of
    saying so. A test runner that reports success having run nothing is the
    worst possible outcome for a self-test.

    The subprocess fixed the import, but `unittest discover` still exits 0 when
    it discovers nothing — so the original failure mode survived the fix. The
    floor below closes it: a suite that shrinks past `--min-tests` fails and
    says which number it saw, rather than reporting a green empty run.
    """
    import subprocess

    target = getattr(args, "determinism", None)
    if target:
        repo = Path(target).expanduser().resolve()
        if not repo.is_dir():
            raise CdpError("not a directory: %s" % repo)
        print("determinism  scanning %s twice" % repo)
        problems = check_determinism(repo)
        if problems:
            for problem in problems:
                print("  %s" % problem, file=sys.stderr)
            raise CdpError(
                "%d reproducibility problem(s) on %s: two scans of one commit "
                "must produce byte-identical state." % (len(problems), repo)
            )
        print("ok    two scans of %s agree byte-for-byte (%s excepted)"
              % (repo, VOLATILE_FILE))
        return 0

    golden_target = getattr(args, "golden", None)
    if golden_target:
        repo = Path(golden_target).expanduser().resolve()
        if not repo.is_dir():
            raise CdpError("not a directory: %s" % repo)
        code, report = run_golden(repo, bless=getattr(args, "bless", False),
                                  name=getattr(args, "golden_name", None))
        print(report, file=sys.stderr if code else sys.stdout)
        return code

    if getattr(args, "bless", False):
        raise CdpError("--bless is only meaningful with --golden")

    tests = SKILL_ROOT / "tests"
    if not tests.is_dir():
        raise CdpError("no tests bundled with this skill at %s" % tests)
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", ".", "-t", ".", "-v"],
        cwd=str(tests),
        stderr=subprocess.PIPE,
        text=True,
    )
    # unittest writes its report to stderr. Echo it verbatim; we only parse the
    # count line, and a parse failure must not swallow the report.
    sys.stderr.write(proc.stderr)
    ran = _tests_ran(proc.stderr)
    if ran is None:
        raise CdpError(
            "could not determine how many tests ran; refusing to report success. "
            "unittest output did not contain a 'Ran N test(s)' line."
        )
    floor = getattr(args, "min_tests", MIN_TESTS)
    if ran < floor:
        raise CdpError(
            "selftest ran %d test(s), below the floor of %d. Either tests were "
            "lost or --min-tests needs raising deliberately." % (ran, floor)
        )
    if proc.returncode == 0:
        print("ok    %d tests" % ran)
    return proc.returncode


_RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)


def _tests_ran(report: str) -> Optional[int]:
    """Extract the test count from a unittest report, or None if absent."""
    matches = _RAN_RE.findall(report or "")
    return int(matches[-1]) if matches else None


if __name__ == "__main__":  # `python3 -m cdp.cli ...`
    raise SystemExit(main())
