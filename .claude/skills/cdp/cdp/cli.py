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
import functools
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
from . import doctor as doctor_mod
from . import docs as docs_mod
from . import entail as entail_mod
from . import export as export_mod
from . import freshness as freshness_mod
from . import gates as gates_mod
from . import githooks as githooks_mod
from . import hook as hook_mod
from . import golden as golden_mod
from . import graph as graph_mod
from . import helpdoc
from . import inventory as inventory_mod
from . import link as link_mod
from . import partition as partition_mod
from . import query as query_mod
from . import reflect as reflect_mod
from . import refresh as refresh_mod
from . import resolve as resolve_mod
from . import rollback as rollback_mod
from . import lock as lock_mod
from . import runner as runner_mod
from . import schedule as schedule_mod
from . import snapshot as snapshot_mod
from . import state as state_mod
from . import supervisor as supervisor_mod
from . import tiering as tiering_mod
from . import trajectory as trajectory_mod
from .store import ARTIFACTS, REPORTS, FileStore, SqliteStore, WorkspaceStore, has_scanned
from .store import registry as registry_mod
from .derive import derive_claims
from . import extract as extract_mod
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
import json
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
    s.add_argument("--workers", type=int, default=None,
                   help="parallel extraction workers (F9: default auto -- "
                        "sequential under %d parseable files, else cpu_count; "
                        "1 forces sequential)" % extract_mod.PARALLEL_MIN_FILES)
    s.add_argument("--exclude", action="append", default=None, metavar="NAME",
                   help="directory-name segment to exclude from the scan, in "
                        "addition to the built-in AI-tool/editor defaults "
                        "(.claude, .cursor, ...) and any .cdp.toml `exclude` "
                        "list -- repeatable")
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
    pr.add_argument("--digest", action="store_true",
                     help="M6.3 (4.2): digest-first mode -- the leaf's input is full file "
                          "text inlined in the prompt, not a Read/Grep tool. Behind a flag "
                          "until doctor/benchmark evidence promotes it to default.")
    pr_lessons = pr.add_mutually_exclusive_group()
    pr_lessons.add_argument("--lessons", type=int, default=None, metavar="N",
                             help="pin lesson-set cut vN (M9.3, 6.7/6.8); default: the "
                                  "latest *promoted* cut, or none if none is promoted yet")
    pr_lessons.add_argument("--no-lessons", action="store_true",
                             help="never use a lesson-set, even if one is promoted")
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
    rn_lessons = rn.add_mutually_exclusive_group()
    rn_lessons.add_argument("--lessons", type=int, default=None, metavar="N",
                             help="pin lesson-set cut vN (M9.3, 6.7); default: the latest "
                                  "cut if one exists, otherwise none")
    rn_lessons.add_argument("--no-lessons", action="store_true",
                             help="never use a lesson-set, even if a cut exists")
    rn.set_defaults(func=cmd_run)

    dr = add("doctor", "model conformance harness (M6.1, 4.10) -- schema "
                        "validity, anchor survival, entailment, recall and "
                        "false-unknown rate against a hand-authored golden set")
    dr.add_argument("--runner-cmd", required=True, metavar="CMD",
                     help="shell command for SubprocessRunner, given prompt and patch "
                          "paths as its last two arguments")
    dr.add_argument("--model", required=True, metavar="LABEL",
                     help="label for this runner in the compatibility table "
                          "(e.g. a model name) -- not passed to the runner itself")
    dr.add_argument("--timeout", type=float, default=300.0)
    dr.add_argument("--node", default=None, help="only this scope")
    dr.set_defaults(func=cmd_doctor)

    rf = add("reflect", "M9.3 (6.6): one real model call per outlier scope from a "
                         "run's own trajectory corpus, cashed out as a deterministic "
                         "promotion or discarded")
    rf.add_argument("--run-id", default=None, help="default: this store's own manifest run_id")
    rf.add_argument("--runner-cmd", required=True, metavar="CMD",
                     help="shell command for SubprocessRunner, given prompt and output "
                          "paths as its last two arguments")
    rf.add_argument("--limit", type=int, default=reflect_mod.DEFAULT_LIMIT,
                     help="max outlier scopes to reflect on (default %d)" % reflect_mod.DEFAULT_LIMIT)
    rf.add_argument("--timeout", type=float, default=300.0)
    rf.set_defaults(func=cmd_reflect)

    ls = add("lessons", "M9.3 (6.7): cut and inspect numbered, pinned lesson-sets")
    ls.add_argument("lessons_action", choices=["cut", "show", "unpromote"])
    ls.add_argument("--version", type=int, default=None,
                     help="show: which cut (default: latest); unpromote: required")
    ls.add_argument("--reason", default=None, help="unpromote: audit note, why this cut is being reverted")
    ls.set_defaults(func=cmd_lessons)

    ho = add("holdout", "M9.3 (6.8): A/B a lesson-set cut against a repo outside its own "
                         "learning corpus; promotes it to `latest` only if it passes")
    ho.add_argument("--lessons", type=int, required=True, metavar="N", help="the cut to A/B")
    ho.set_defaults(func=cmd_holdout)

    st = add("status", "waves, node statuses and coverage")
    st.set_defaults(func=cmd_status)

    df = add("diff", "typed structural deltas between two scanned snapshots")
    df.add_argument("old_state", nargs="?", default=None,
                     help="state directory of the earlier snapshot (pass together with "
                          "new_state); omit and use --old-sha/--new-sha instead")
    df.add_argument("new_state", nargs="?", default=None,
                     help="state directory of the later snapshot")
    df.add_argument("--old-sha", default=None, metavar="SHA",
                     help="diff --repo's earlier snapshot by commit sha instead of a "
                          "directory (default: --repo's current/latest scanned snapshot)")
    df.add_argument("--new-sha", default=None, metavar="SHA",
                     help="diff --repo's later snapshot by commit sha instead of a "
                          "directory (default: --repo's current/latest scanned snapshot)")
    df.add_argument("--json", action="store_true")
    df.set_defaults(func=cmd_diff)

    lk = add("link", "who calls this service / what publishes to this topic, "
                      "across modules and across snapshots (Phase 8, M8.1-M8.2)")
    lk_sub = lk.add_subparsers(dest="link_command")
    lks = lk_sub.add_parser("scan", help="match channel edges within and across scanned "
                                          "state directories -- read-only, writes no snapshot")
    lks.add_argument("state_dirs", nargs="+", metavar="STATE_DIR",
                      help="one or more scanned state directories. Each is exploded by its "
                           "edges' own `module` tag before matching, so one whole-monorepo "
                           "scan already surfaces cross-module links; passing several state "
                           "dirs additionally matches across snapshots (5.5: a link is "
                           "between snapshots, not repos)")
    lks.add_argument("--json", action="store_true")
    lks.add_argument("--db", default=None,
                      help="also persist this scan's links/unmatched calls into the "
                           "link.* namespace of the store resolved the same way every "
                           "other command's does (`.cdp.toml` -> registry -> cwd/.cdp, "
                           "default sqlite, D3) -- replaces prior contents, since link "
                           "data is fully derived (R3). Pass an explicit path to persist "
                           "into a store other than the one this invocation resolves to")
    lks.set_defaults(func=cmd_link_scan)

    lkq = lk_sub.add_parser("query", help="who calls a service / what it calls that "
                                           "is not registered anywhere -- from the last "
                                           "persisted `link scan --db`")
    lkq.add_argument("--db", default=None,
                      help="read from this SqliteStore's link.* namespace instead of "
                           "the one this invocation resolves to (same default-resolution "
                           "rule as every other command, `.cdp.toml`/registry/cwd, D3)")
    lkq.add_argument("--service", required=True, help="repo name/identifier to query, "
                                                        "as it appears in a scanned manifest's `repo` field")
    lkq.add_argument("--json", action="store_true")
    lkq.set_defaults(func=cmd_link_query)

    lkp = lk_sub.add_parser("prompts", help="write one prompt per ambiguous (heuristic) "
                                             "link, from a prior `link scan --db` (M8.3, 5.2)")
    lkp.add_argument("--db", default=None,
                      help="read from / write back into this SqliteStore's link.* "
                           "namespace instead of the one this invocation resolves to")
    lkp.add_argument("--out", required=True, help="directory to write tasks/, tasks.json, "
                                                    "inbox/ into")
    lkp.add_argument("--runner-cmd", default=None,
                      help="if set, immediately run each task's prompt through this "
                           "command via runner.SubprocessRunner (same protocol `cdp run` "
                           "uses) and write its patch into --out/inbox/")
    lkp.set_defaults(func=cmd_link_prompts)

    lkc = lk_sub.add_parser("collect", help="validate+verify+entail+fold every patch "
                                             "left in a `link prompts --out`'s inbox/ (M8.3)")
    lkc.add_argument("--db", default=None,
                      help="read from / write back into this SqliteStore's link.* "
                           "namespace instead of the one this invocation resolves to")
    lkc.add_argument("--in", dest="in_dir", required=True,
                      help="the directory a prior `link prompts --out` wrote")
    lkc.set_defaults(func=cmd_link_collect)

    lkr2 = lk_sub.add_parser("run", help="dispatch every ambiguous link task through the "
                                          "same lease/retry machinery `cdp run` uses for "
                                          "scopes, and record it to the trajectory store "
                                          "as dim_task_kind=link (post-Phase-9 item 5)")
    lkr2.add_argument("--db", default=None,
                       help="read from / write back into this SqliteStore's link.* "
                            "namespace instead of the one this invocation resolves to")
    lkr2.add_argument("--run-id", default=None, help="defaults to \"cdp-link\"")
    lkr2.add_argument("--out", default=None,
                       help="directory to write task prompts into (defaults to "
                            "<state>/link-tasks)")
    lkr2.add_argument("--runner-cmd", default=None, metavar="CMD",
                       help="run each task's prompt through this command via "
                            "runner.SubprocessRunner; without it, waits for a human/"
                            "external process to drop the patch file (FileRunner)")
    lkr2.add_argument("--timeout", type=float, default=300.0)
    lkr2.add_argument("--max-attempts", type=int, default=supervisor_mod.MAX_ATTEMPTS)
    lkr2.set_defaults(func=cmd_link_run)

    lkr = lk_sub.add_parser("refresh", help="re-verify a prior `link scan --db`'s contracts "
                                             "against freshly scanned state directories (M8.4, 5.3)")
    lkr.add_argument("state_dirs", nargs="+", metavar="STATE_DIR",
                      help="freshly scanned state directories for the repo(s) being refreshed "
                           "-- a repo not named here is left byte-identical in the persisted report")
    lkr.add_argument("--json", action="store_true")
    lkr.add_argument("--db", default=None,
                      help="the store holding the prior `link scan --db` to refresh, resolved "
                           "the same way every other command's is if omitted")
    lkr.set_defaults(func=cmd_link_refresh)

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

    cp = add("compact", "move superseded patch generations to the cold archive")
    cp.add_argument("--db", default=None,
                     help="path to a SqliteStore index.db (default: the resolved store's)")
    cp.add_argument("--compact-threshold", type=float, default=0.30,
                     help="minimum fraction of superseded rows required to act (default 0.30)")
    cp.add_argument("--keep-generations", type=int, default=1,
                     help="generations kept hot per (snapshot, node) -- a performance knob, "
                          "not a retention decision: nothing is lost, only archived (default 1)")
    cp.add_argument("--dry-run", action="store_true", help="report what would move, move nothing")
    cp.set_defaults(func=cmd_compact)

    vf = add("verify", "recompute the fold from the log and compare to state.json; "
                        "--full also proves the archive, not just the hot table")
    vf.add_argument("--full", action="store_true",
                     help="re-fold from the cold archive too (M7.4, 2.5) -- "
                          "what makes compaction provably lossless rather than asserted")
    vf.add_argument("--mode", choices=["strict", "lenient"], default=STRICT)
    vf.set_defaults(func=cmd_verify)

    ex = add("export", "canonical JSON / reviewable patches / archive dump / anonymised corpus")
    ex.add_argument("--format", choices=["json", "patches", "archive", "anonymized"],
                     default="json")
    ex.add_argument("--out", required=True, metavar="DIR", help="destination directory")
    ex.add_argument("--db", default=None,
                     help="path to a SqliteStore index.db (default: the resolved store's)")
    ex.set_defaults(func=cmd_export)

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
    i.add_argument("--framework", choices=["claude-code", "langgraph", "adk", "none"],
                   default="claude-code",
                   help="which agent framework will drive the leaf wave loop "
                        "(default claude-code); langgraph/adk print pip-install "
                        "and import guidance instead of writing .claude/agents/, "
                        "none skips agent registration entirely")
    i.add_argument("--hook", action="store_true",
                   help="also install the PreToolUse nudge (requires in-repo state; "
                        "claude-code only)")
    i.add_argument("--strict", action="store_true",
                   help="with --hook, block the first source read of a session "
                        "instead of nudging, when the index is fresh and its "
                        "coverage fraction is at least %.2f" % hook_mod.STRICT_MIN_COVERAGE)
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


def _resolve_backend(repo: Path) -> Tuple[str, Optional[Dict[str, str]]]:
    """`.cdp.toml`'s `backend` key decides which `WorkspaceStore` `_open_store`
    constructs -- default `"sqlite"` (D3's default, unchanged for a repo with
    no `.cdp.toml`, or one that doesn't name a backend)."""
    kind = registry_mod.team_backend(repo)
    if kind not in ("sqlite", "file", "postgres"):
        raise CdpError('unknown backend %r in .cdp.toml (must be "sqlite", "file" or "postgres")' % kind)
    pg = registry_mod.team_postgres_config(repo) if kind == "postgres" else None
    if kind == "postgres" and not (pg and pg.get("dsn")):
        raise CdpError('backend = "postgres" in .cdp.toml needs a [postgres] dsn')
    return kind, pg


def _default_postgres_schema(repo: Path) -> str:
    """A stable, valid Postgres schema name derived from repo identity, so
    two repos sharing one Postgres server without an explicit `schema =`
    in `.cdp.toml` don't collide."""
    raw = registry_mod.repo_identity(repo)
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
    if not sanitized or not sanitized[0].isalpha():
        sanitized = "r_" + sanitized
    return ("cdp_" + sanitized)[:63]


def _open_store(paths: "Paths") -> WorkspaceStore:
    """No backend is hardcoded here: which `WorkspaceStore` implementation
    this constructs is `.cdp.toml`'s `backend` key (`_resolve_backend`),
    defaulting to `SqliteStore` (D3, `PHASE/FINDINGS.md`) at
    `<state>/index.db` -- the path `CDP_CLI_SCOPE.md` 2.3 and
    `phase_2_plan.md` already name. `paths.state` itself stays a directory
    regardless of backend -- `docs/`, `prompts/` and the inbox are filesystem
    handoffs every backend shares (`store/__init__.py`'s module docstring)."""
    kind, pg = _resolve_backend(paths.repo)
    if kind == "file":
        return FileStore(paths.state)
    if kind == "postgres":
        from .store.postgres_backend import PostgresStore

        schema = pg.get("schema") or _default_postgres_schema(paths.repo)
        return PostgresStore(pg["dsn"], schema, inbox_root=paths.state)
    return SqliteStore(paths.state / "index.db")


def _locked(shared: bool, timeout_s: float = lock_mod.DEFAULT_TIMEOUT_S):
    """Decorator: take the per-repo lock (`cdp/lock.py`) for this command's
    entire body before it touches the store, release it on any exit path.

    Resolves `paths`/backend kind itself, independently of whatever the
    wrapped `cmd_*` does with `_paths(args)`/`_open_store(paths)` -- both are
    pure functions of `args`, so computing them twice is cheap and keeps this
    decorator a pure wrapper that never has to reach into the function body.
    `shared=True` (read-consistency only: query/docs/status/diff/export/
    verify/doctor) lets concurrent readers proceed; `shared=False` (anything
    that appends a patch, writes an artifact, moves the snapshot pointer, or
    touches task/rollback state) blocks every other locked command, reader
    or writer alike, for as long as this one runs.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(args):
            paths = _paths(args)
            kind, pg = _resolve_backend(paths.repo)
            with lock_mod.repo_lock(paths, kind, pg, shared=shared, timeout_s=timeout_s):
                return func(args)

        return wrapper

    return decorator


def _check_repo_matches_manifest(paths: "Paths", manifest: Dict) -> None:
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


def _extra_excludes(args, repo: Path) -> List[str]:
    """`.cdp.toml`'s `exclude` list plus this invocation's `--exclude`
    (where the command's own parser has one) -- additive on top of
    `inventory.DEFAULT_EXCLUDES`, never a replacement for it."""
    return registry_mod.team_excludes(repo) + list(getattr(args, "exclude", None) or [])


@_locked(shared=False)
def cmd_scan(args) -> int:
    paths = _paths(args)
    say = (lambda *a: None) if args.quiet else (lambda *a: print(*a))

    # M2.6: only the resolved-by-default case needs registering -- an explicit
    # `--in-repo`/`--state-dir` already tells every future command where to
    # look, and never touching the registry then keeps a test (or a user who
    # always passes `--state-dir`) from writing to `~/.cdp/config.toml` at all.
    if not getattr(args, "in_repo", False) and not getattr(args, "state_dir", None):
        registry_mod.register(registry_mod.repo_identity(paths.repo), paths.state)

    inventory = inventory_mod.build_inventory(paths.repo, extra_excludes=_extra_excludes(args, paths.repo))
    say("\n".join(inventory_mod.summarise(inventory)))

    extraction = run_extract(paths.repo, inventory, workers=args.workers)
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
    store = _open_store(paths)
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


@_locked(shared=True)
def cmd_query(args) -> int:
    store = query_mod.Store(_open_store(_paths(args)))
    if getattr(args, "as_of", None):
        _apply_as_of(store, args.as_of)
    # Dispatch itself lives in `query.dispatch` -- shared with `mcp_server`'s
    # `cdp_query` tool (Phase 9, 7.1) so both answer from one `if` ladder.
    try:
        result = query_mod.dispatch(
            store, args.kind, args.term, budget=args.budget,
            claim_kind=args.claim_kind, module=args.module, subject=args.subject,
            frm=args.frm, to=args.to, max_hops=args.max_hops,
        )
    except ValueError as exc:
        raise CdpError(str(exc))

    if args.json:
        print(__import__("json").dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(query_mod.render(result))
        if result.get("elided", 0) > 0 and not result.get("budget_note"):
            print("tip       --budget <bigger N> to see the rest (%d row(s) elided)"
                  % result["elided"])
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


@_locked(shared=True)
def cmd_docs(args) -> int:
    paths = _paths(args)
    store = query_mod.Store(_open_store(paths))
    out = Path(args.out).expanduser().resolve() if args.out else paths.state / "docs"
    for path in _render_docs(store, out):
        print(path)
    print("next      open %s/00-overview.md, or cdp query stats" % out)
    store.close()
    return 0


# ---------------------------------------------------------------- prompts


@_locked(shared=False)
def cmd_prompts(args) -> int:
    paths = _paths(args)
    backend = _open_store(paths)
    store = query_mod.Store(backend)
    if args.digest:
        # M6.3: digest mode reads --repo's file content, unlike the default
        # prompt build -- the same silent-wrong-repo failure mode as F16.
        _check_repo_matches_manifest(paths, store.manifest)
    sched = store._load("schedule")
    run_id = store.manifest.get("run_id", "cdp")
    prior = list(store.state.get("claims", []))

    out_dir = paths.state / "prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    backend.ensure_inbox()

    # M6.4 (4.8): built once, not per scope -- `build_symbol_index` scans all
    # of `extraction`, so per-scope re-building would be quadratic in scope count.
    symbol_index = tiering_mod.build_symbol_index_for_tiering(store.extraction)

    # M9.3 (6.8): the same lesson resolution `cmd_run` uses, so `cdp prompts
    # --lessons vN` reproduces exactly what a real run would have applied --
    # this is `cdp holdout`'s own A/B lever, no live model call required.
    with trajectory_mod.TrajectoryStore() as trajectory:
        if args.no_lessons:
            lessons_version = None
        elif args.lessons is not None:
            lessons_version = args.lessons
        else:
            lessons_version = trajectory.latest_lesson_version()
        lesson_hints: Dict = {}
        if lessons_version is not None:
            lesson_hints = reflect_mod.apply_lessons(trajectory.load_lessons(lessons_version))
    prompt_kwargs: Dict = {}
    if lesson_hints.get("max_inherited") is not None:
        prompt_kwargs["max_inherited"] = lesson_hints["max_inherited"]

    written: List[Dict] = []
    for scope in store.partition["scopes"]:
        node = scope["node"]
        if args.node and node != args.node:
            continue
        if args.wave is not None and sched["node_wave"].get(node) != args.wave:
            continue
        text, stats = build_prompt(
            scope, store.inventory, store.extraction, store.xref, sched, prior, run_id,
            digest_mode=args.digest, repo_root=paths.repo, symbol_index=symbol_index,
            extra_third_party=lesson_hints.get("third_party_patterns", frozenset()),
            prompt_fixes=lesson_hints.get("prompt_fixes", ()),
            **prompt_kwargs
        )
        path = out_dir / (node.replace("/", "__") + ".md")
        write_text(path, text)
        stats["prompt"] = str(path)
        stats["wave"] = sched["node_wave"].get(node)
        written.append(stats)

    backend.write_report("prompts", {"prompts": written})
    tiering_report = {row["node"]: row["tiering"] for row in written if "tiering" in row}
    backend.write_report("tiering", {"tiering": tiering_report})
    if tiering_report:
        t3 = {n: r for n, r in tiering_report.items() if r["tier"] == tiering_mod.T3}
        print("tiering   %d/%d scope(s) T3 (%s)" % (
            len(t3), len(tiering_report),
            ", ".join(sorted({r["reason"] for r in t3.values()})) or "none",
        ))
    if args.measure:
        _print_token_report(written)
        backend.close()
        return 0
    fired = [w for w in written if w["budget_fired"]]
    tightened = [w for w in written if w.get("prompt_tightened")]
    exhausted = [w for w in written if w.get("prompt_budget_exhausted")]
    print("wrote %d prompt(s) to %s" % (len(written), out_dir))
    for row in written:
        flags = []
        if row["budget_fired"]:
            flags.append("BUDGET FIRED (%d elided)" % row["elided_claims"])
        if row.get("prompt_tightened"):
            flags.append("TIGHTENED (%s)" % ", ".join(row["prompt_tightened"]))
        if row.get("prompt_budget_exhausted"):
            flags.append("OVER max_prompt_tokens=%s EVEN AT FLOOR" % row.get("max_prompt_tokens"))
        print("  wave %-2s %-60s %2d files, sigma %d claim(s)%s"
              % (row["wave"], row["node"], row["files"], row["inherited_claims"],
                 "  " + "; ".join(flags) if flags else ""))
    if not fired:
        print("\ninherited-sigma budget never fired; the 200-claim default is not binding here.")
    if tightened:
        print("%d scope(s) exceeded max_prompt_tokens and were auto-tightened." % len(tightened))
    if exhausted:
        print("%d scope(s) still exceed max_prompt_tokens after every lever was floored -- "
              "raise --max-leaf-files/--max-leaf-loc down, or accept the overrun." % len(exhausted))
    if written:
        print("next      hand each prompt in %s to a leaf, then cdp collect" % out_dir)
        if not args.digest:
            print("tip       --digest builds full-file prompts instead of citations")
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


@_locked(shared=False)
def cmd_collect(args) -> int:
    """Validate, verify and append every patch an agent left in the inbox.

    §3.5's retry contract lives here in its terminal form: a patch that fails
    validation is recorded `invalid` with the specific violations attached, and
    no claim from it enters state. The three attempts happen in the session,
    which is the only place that can ask the agent to try again.
    """
    paths = _paths(args)
    backend = _open_store(paths)
    store = query_mod.Store(backend)
    _check_repo_matches_manifest(paths, store.manifest)
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
            task_states_cache[run_id] = backend.task_states(run_id)
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
    stats["escalation_rate"] = _escalation_rate(accepted)
    backend.write_report("verify", stats)
    backend.write_report("rejected", {"rejected": rejected})
    backend.write_report("unknown_gates", {"rejected": unknown_rejections})

    # M6.4 (4.8): the rule's post-dispatch half. A T2 leaf's own claims may
    # self-report `escalated: true` (M6.3) -- upgrade that scope's logged
    # tier in place, reason `leaf_escalated`, rather than only ever deciding
    # tier before the leaf ran.
    tiering_report = dict(backend.read_report("tiering", {}).get("tiering", {}))
    tiering_upgrades = []
    for patch in accepted:
        node = str(patch.get("node", "leaf"))
        if tiering_mod.apply_leaf_escalation(tiering_report, node, patch.get("claims") or []):
            tiering_upgrades.append(node)
    if tiering_upgrades:
        backend.write_report("tiering", {"tiering": tiering_report})
        print("tiering   %d scope(s) upgraded to T3 (leaf_escalated): %s"
              % (len(tiering_upgrades), ", ".join(sorted(tiering_upgrades))))

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
    if stats["escalation_rate"] is not None:
        print("escalation %.3f (M6.3: fraction of claims that needed source beyond the digest)"
              % stats["escalation_rate"])
    if accepted:
        print("next      cdp fold --check")
    backend.close()
    return 0


def _escalation_rate(patches: List[Dict]) -> Optional[float]:
    """M6.3 (4.2): fraction of claims across this batch self-reporting
    `escalated: true` -- `None`, not `0.0`, when nothing in the batch used
    digest mode, so a real 0% escalation run is never confused with "the
    question doesn't apply here"."""
    claims = [c for patch in patches for c in (patch.get("claims") or [])]
    if not claims:
        return None
    return sum(1 for c in claims if c.get("escalated")) / len(claims)


# ------------------------------------------------------------------- fold


@_locked(shared=False)
def cmd_fold(args) -> int:
    paths = _paths(args)
    backend = _open_store(paths)
    store = query_mod.Store(backend)
    _check_repo_matches_manifest(paths, store.manifest)
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
    print("next      cdp query stats")
    backend.close()
    return 0


@_locked(shared=True)
def cmd_verify(args) -> int:
    """M7.4 (2.5): same mechanism as `fold --check`, extended over the cold
    archive when `--full` is given -- the audit story that makes `compact`
    provably lossless rather than merely asserted."""
    paths = _paths(args)
    backend = _open_store(paths)
    store = query_mod.Store(backend)
    _check_repo_matches_manifest(paths, store.manifest)
    problems = state_mod.check_fold(
        backend, store.xref, store.partition, repo=paths.repo, mode=args.mode, full=args.full
    )
    backend.close()
    if problems:
        for problem in problems:
            print("FAIL  %s" % problem)
        print("next      cdp rollback --to-run <the offending run> to exclude it, "
              "or cdp fold to recompute and re-check")
        return 1
    if args.full:
        print("ok    state.json = fold(merge, patches/ + archive/, xref.json)")
        print("ok    archive rows match their recorded content hash")
    else:
        print("ok    state.json = fold(merge, patches/, xref.json)")
        print("tip       cdp verify --full to also audit the cold archive "
              "(needs cdp compact to have run first)")
    return 0


# --------------------------------------------------------------- refresh


@_locked(shared=False)
def cmd_refresh(args) -> int:
    """M3.3: re-verify every live claim against HEAD, zero model calls.

    Re-derives nothing: the patch log is untouched (R5). What moves is the
    *view* -- incremental extraction (M3.2) for `xref`/`graph`/`dataflow`, and
    rename-aware re-verification for the claims already in the log, via the
    same `rename_map`/`edited_files` arguments `state.fold` now accepts.
    """
    paths = _paths(args)
    backend = _open_store(paths)
    store = query_mod.Store(backend)
    _check_repo_matches_manifest(paths, store.manifest)
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

    new_inventory = inventory_mod.build_inventory(paths.repo, extra_excludes=_extra_excludes(args, paths.repo))
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
    say("next      cdp query stats")
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


def _apply_wave_results(backend, store, results: List[Dict], run_id: str, mode: str, paths: "Paths",
                         trajectory: Optional["trajectory_mod.TrajectoryStore"] = None,
                         repo_id: Optional[str] = None, model: Optional[str] = None) -> Dict:
    """The terminal outcome of one wave: append a `complete` patch for every
    scope that validated, a `status: failed` patch (no claims) for every one
    abandoned -- `state.fold`'s existing superseded-node handling turns the
    latter into an honest unknown (R6) with no further code here -- then one
    fold for the whole wave, and bump `validated` tasks to `folded`."""
    log_so_far = backend.load_patches()
    def_fqns, edge_subjects, edges_by_key = gates_mod.build_extraction_index(store.extraction)
    scope_nodes = {s["node"] for s in store.partition["scopes"]}
    node_to_hash = {s["node"]: s.get("scope_hash") for s in store.partition["scopes"]}
    node_to_scope = {s["node"]: s for s in store.partition["scopes"]}
    task_rows = backend.task_states(run_id)
    tiering_report = backend.read_report("tiering", {}).get("tiering", {})
    for row in results:
        node = row["node"]
        claims_emitted = unknowns_emitted = None
        entailed = consistent = contradicted = elision_regret = None
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
            claims_emitted = len(patch.get("claims") or [])
            unknowns_emitted = len(kept)
            # M9.2 (6.3): output scorecard -- entailment split on this leaf's
            # own emitted claims, against the same extraction the leaf saw.
            verdicts = [c.get("verdict") for c in entail_mod.entail_claims(patch.get("claims") or [], store.extraction)]
            entailed = verdicts.count(entail_mod.ENTAILED)
            consistent = verdicts.count(entail_mod.CONSISTENT)
            contradicted = verdicts.count(entail_mod.CONTRADICTED)
            # M9.2 (6.4): elision regret -- did this leaf emit an unknown
            # about a subject the digest budget had already elided as a
            # prior claim? That is the concrete "was the answer in a row the
            # budget elided" question `prompts.py`'s ranking function needs
            # graded against.
            elided_subjects = (row.get("prompt_stats") or {}).get("elided_subjects") or []
            unknown_subjects = [str(u.get("subject", "")) for u in kept]
            elision_regret = trajectory_mod.elision_regret(elided_subjects, unknown_subjects)
        elif row["state"] == supervisor_mod.ABANDONED:
            backend.append_patch(
                {"schema_version": "1.0.0", "node": node, "run_id": run_id, "status": "failed",
                 "error": row["last_error"] or "abandoned after %d attempts" % row["attempts"]},
                node + "-abandoned",
            )
        if trajectory is not None and repo_id is not None:
            scope = node_to_scope.get(node, {})
            prompt_stats = row.get("prompt_stats") or {}
            trajectory.record_leaf_run(
                run_id=run_id, node=node, scope_hash=node_to_hash.get(node), repo_id=repo_id,
                model=model, scope_shape_key=trajectory_mod.scope_shape_key(scope),
                template_version=None, tier=tiering_report.get(node, {}).get("tier"),
                task_kind="scope", state=row["state"], attempts=row.get("attempts"),
                claims_emitted=claims_emitted, unknowns_emitted=unknowns_emitted,
                rows_elided=prompt_stats.get("elided_claims"), tokens_est=prompt_stats.get("tokens_est"),
                digest_mode=prompt_stats.get("digest_mode"), entailed=entailed,
                consistent=consistent, contradicted=contradicted, elision_regret=elision_regret,
                sigma_claims=prompt_stats.get("sigma_claims"),
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


@_locked(shared=False)
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
    backend = _open_store(paths)
    if not backend.supports_run_tracking():
        raise CdpError(
            "%s has no run/task tracking -- `cdp run` needs the sqlite or "
            "postgres backend" % type(backend).__name__
        )
    store = query_mod.Store(backend)
    _check_repo_matches_manifest(paths, store.manifest)
    sched = store._load("schedule")
    run_id = str(store.manifest.get("run_id", "cdp"))
    validator = Validator.load(schema_path(SKILL_ROOT))
    runner = _build_runner(args)
    if not args.runner_cmd:
        print("run       no --runner-cmd given -- waiting for a human/external "
              "process to drop the patch file (FileRunner, timeout %ss)" % args.timeout)

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

    repo_id = registry_mod.repo_identity(paths.repo)
    model = (args.runner_cmd.split()[0] if args.runner_cmd else "human")
    trajectory = trajectory_mod.TrajectoryStore()
    trajectory.record_run_event(run_id=run_id, repo_id=repo_id, event="started")

    if args.no_lessons:
        lessons_version = None
    elif args.lessons is not None:
        lessons_version = args.lessons
    else:
        lessons_version = trajectory.latest_lesson_version()  # None until the first cut (6.7)
    backend.set_run_lessons_version(run_id, lessons_version)
    lesson_hints: Dict = {}
    if lessons_version is not None:
        lesson_hints = reflect_mod.apply_lessons(trajectory.load_lessons(lessons_version))
        print("lessons   pinned v%d" % lessons_version)

    if args.stale_only:
        stale = _stale_nodes(store, paths.repo)
        if not stale:
            print("stale-only  zero scopes need review")
            backend.finish_run(run_id, "complete")
            trajectory.record_run_event(run_id=run_id, repo_id=repo_id, event="finished", reason="complete")
            _maybe_print_lessons_hint(trajectory)
            trajectory.close()
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

    any_incomplete = False
    for label, nodes in wave_groups:
        results = supervisor_mod.run_wave(
            nodes, store, backend, runner, paths, run_id, validator, sched, args.mode,
            max_attempts=args.max_attempts, skip_hashes=skip_hashes, lesson_hints=lesson_hints,
        )
        _apply_wave_results(backend, store, results, run_id, args.mode, paths,
                             trajectory=trajectory, repo_id=repo_id, model=model)
        counts: Dict[str, int] = {}
        for row in results:
            counts[row["state"]] = counts.get(row["state"], 0) + 1
        print("wave %-6s %2d scope(s)  %s" % (label, len(results),
              ", ".join("%s %d" % kv for kv in sorted(counts.items())) or "nothing to dispatch"))
        for row in results:
            if row["state"] != supervisor_mod.VALIDATED:
                print("  %-9s %-40s attempts %d  %s"
                      % (row["state"], row["node"], row["attempts"], row["last_error"] or ""))
                any_incomplete = True
        store = query_mod.Store(backend)  # re-read state.json: next wave inherits this wave's claims

    backend.finish_run(run_id, "complete")
    trajectory.record_run_event(run_id=run_id, repo_id=repo_id, event="finished", reason="complete")
    print("next      cdp query stats, or cdp fold --check")
    if any_incomplete:
        print("tip       cdp run --resume --run-id %s to retry the incomplete/failed scope(s)" % run_id)
    _maybe_print_lessons_hint(trajectory)
    trajectory.close()
    backend.close()
    return 0


def _maybe_print_lessons_hint(trajectory: "trajectory_mod.TrajectoryStore") -> None:
    """Every `LESSONS_HINT_EVERY` finished runs (global, cross-repo cadence,
    per the user's own decision -- cutting itself stays manual), nudge that
    pending promotions exist and name the exact command to freeze them.
    Silent otherwise: off-cadence, or nothing pending."""
    count = trajectory.finished_run_count()
    if count % trajectory_mod.LESSONS_HINT_EVERY != 0:
        return
    pending = trajectory.pending_promotion_count()
    if pending == 0:
        return
    print("lessons   %d promotion(s) pending after %d runs -- `cdp lessons cut` to freeze them"
          % (pending, count))


@_locked(shared=False)
def cmd_reflect(args) -> int:
    """M9.3 (6.6): select this run's own outlier scopes from the trajectory
    corpus (deterministic, M9.2's own columns), spend one real model call per
    outlier, and keep only what comes back as a well-formed, deterministic
    promotion (`reflect.validate_promotion`) -- everything else is discarded
    and named, never stored as a vague lesson (R10)."""
    paths = _paths(args)
    backend = _open_store(paths)
    store = query_mod.Store(backend)
    run_id = args.run_id or str(store.manifest.get("run_id", "cdp"))
    with trajectory_mod.TrajectoryStore() as trajectory:
        leaf_rows = trajectory.leaf_runs_for(run_id)
    outliers = reflect_mod.select_outliers(leaf_rows, limit=args.limit)
    if not outliers:
        print("reflect   0 outlier scope(s) in run %s -- nothing to reflect on" % run_id)
        backend.write_report("reflections", {"accepted": [], "discarded": []})
        backend.close()
        return 0
    runner = runner_mod.SubprocessRunner(shlex.split(args.runner_cmd), timeout_s=args.timeout)
    prompts_dir = paths.state / "reflections"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    accepted, discarded = reflect_mod.reflect(outliers, runner, prompts_dir)
    for d in discarded:
        print("reflect   DISCARDED (%s): %s" % (d["node"], d["reason"]))
    for a in accepted:
        print("reflect   PROMOTED  (%s): %s" % (a["node"], a["promotion"]["promotion"]))
    print("reflect   %d accepted, %d discarded" % (len(accepted), len(discarded)))
    backend.write_report("reflections", {"accepted": accepted, "discarded": discarded})
    backend.close()
    if accepted:
        with trajectory_mod.TrajectoryStore() as trajectory:
            for a in accepted:
                trajectory.record_promotion(run_id=run_id, node=a["node"], promotion=a["promotion"])
        print("next      cdp lessons cut to freeze %d pending promotion(s), then "
              "cdp holdout --lessons vN <held-out-repo> to A/B before trusting it" % len(accepted))
    return 0


def cmd_lessons(args) -> int:
    """M9.3 (6.7): cut and inspect lesson-sets. A cut is a numbered,
    immutable snapshot of every promotion `cdp reflect` has accepted since the
    last cut -- `cdp run --lessons vN` pins one; the default (no flag) is
    always the *latest* cut, never the live, still-growing corpus (6.7:
    "default is latest cut, never live corpus -- a live corpus makes every
    run unreproducible")."""
    with trajectory_mod.TrajectoryStore() as trajectory:
        if args.lessons_action == "cut":
            version = trajectory.cut_lessons()
            if version is None:
                print("lessons   nothing pending to cut")
            else:
                n = len(trajectory.load_lessons(version))
                print("lessons   cut v%d (%d promotion(s))" % (version, n))
                print("next      cdp run --lessons v%d to pin it, or cdp holdout --lessons v%d "
                      "<held-out-repo> to A/B it first" % (version, version))
        elif args.lessons_action == "unpromote":
            if args.version is None:
                raise CdpError("`cdp lessons unpromote` needs --version")
            if not trajectory.unpromote_cut(args.version, reason=args.reason):
                raise CdpError("v%d is not currently promoted -- nothing to unpromote" % args.version)
            fallback = trajectory.latest_lesson_version()
            print("lessons   v%d unpromoted -- default `cdp run` resolution now falls back to %s"
                  % (args.version, ("v%d" % fallback) if fallback is not None else "no lesson-set"))
            print("next      cdp run --lessons vN uses the new fallback automatically; "
                  "pass --no-lessons to opt out entirely")
        else:  # show
            version = args.version if args.version is not None else trajectory.latest_lesson_version()
            if version is None:
                print("lessons   no cut exists yet")
                return 0
            lessons = trajectory.load_lessons(version)
            print("lessons   v%d (%d promotion(s))" % (version, len(lessons)))
            for row in lessons:
                print("  %-30s %-20s %s" % (row["node"], row["kind"], row["payload"]))
            print("tip       cdp lessons cut freezes new promotions since this cut; "
                  "cdp lessons unpromote --version N reverts one")
    return 0


@_locked(shared=False)
def cmd_holdout(args) -> int:
    """M9.3 (6.8): "A/B on a pinned snapshot, `--lessons none` vs `--lessons
    vN`. Learn on repos A-E, benchmark on F, or you are measuring
    memorisation." The A here is the deterministic tiering rule (M6.4) with
    and without the cut's `import_channel_hint` patterns applied -- no live
    model call, since T3 escalation is exactly the routing signal a lesson
    can move (`graph._looks_third_party`), and it is reproducible by
    construction. The split-is-real check (this milestone's own stress test)
    runs first and refuses outright if it fails."""
    paths = _paths(args)
    backend = _open_store(paths)
    store = query_mod.Store(backend)
    repo_id = registry_mod.repo_identity(paths.repo)

    with trajectory_mod.TrajectoryStore() as trajectory:
        learned = trajectory.learned_repos_for_cut(args.lessons)
        if repo_id in learned:
            store.close()
            raise CdpError(
                "holdout repo %r is in v%d's own learning corpus %s -- this would "
                "measure memorisation, not a real holdout (6.8)" % (repo_id, args.lessons, sorted(learned))
            )
        lessons = trajectory.load_lessons(args.lessons)
        if not lessons:
            store.close()
            raise CdpError("lesson-set v%d has no rows to A/B" % args.lessons)
        hints = reflect_mod.apply_lessons(lessons)

    symbol_owner, namespace_owner = tiering_mod.build_symbol_index_for_tiering(store.extraction)
    module_set = {m["name"] for m in store.inventory["modules"]}
    scopes = store.partition["scopes"]

    def t3_rate(extra_third_party) -> float:
        if not scopes:
            return 0.0
        t3 = sum(
            1 for s in scopes
            if tiering_mod.compute_tier(
                s, store.extraction, module_set, symbol_owner, namespace_owner, extra_third_party
            )["tier"] == tiering_mod.T3
        )
        return t3 / len(scopes)

    before = t3_rate(frozenset())
    after = t3_rate(hints["third_party_patterns"])
    metric = {"t3_rate_none": before, "t3_rate_lessons": after, "scopes": len(scopes)}

    # Promotion bar (6.8's own open decision, settled here): a lesson-set
    # must not *increase* T3 escalation on a repo it never learned from --
    # an increase means its import_channel_hint patterns overfit the
    # learning corpus rather than naming a real third-party root.
    passed = after <= before
    print("holdout   v%d on %s: T3 rate %.3f (none) -> %.3f (lessons) -- %s"
          % (args.lessons, repo_id, before, after, "PROMOTE" if passed else "REJECT"))
    backend.write_report("holdout", metric)
    store.close()
    if passed:
        with trajectory_mod.TrajectoryStore() as trajectory:
            trajectory.promote_cut(args.lessons, repo_id, metric)
        print("holdout   v%d promoted to latest" % args.lessons)
        print("next      cdp run --lessons v%d (or omit --lessons; v%d is now the latest cut)"
              % (args.lessons, args.lessons))
    else:
        print("holdout   v%d NOT promoted -- regression on a repo outside its learning corpus" % args.lessons)
    return 0 if passed else 1


# ----------------------------------------------------------------- doctor


@_locked(shared=True)
def cmd_doctor(args) -> int:
    """M6.1 (4.10): dispatch one runner over every scope of an already-scanned
    repo, score each patch against the hand-authored golden set (currently
    only defined for `tests/fixtures/minirepo` -- doctor on any other repo
    reports the other four metrics with `recall`/`false_unknown_rate` at
    `None`, rather than silently fabricating a golden set from CDP's own
    output).  Writes `<state>/doctor/<model>.json` and prints the
    compatibility table across every model report already on disk.
    """
    paths = _paths(args)
    backend = _open_store(paths)
    store = query_mod.Store(backend)
    sched = store._load("schedule")
    run_id = str(store.manifest.get("run_id", "cdp"))
    validator = Validator.load(schema_path(SKILL_ROOT))
    runner = runner_mod.SubprocessRunner(shlex.split(args.runner_cmd), timeout_s=args.timeout)

    golden_by_module = doctor_mod.GOLDEN_MINIREPO if paths.repo.name == "minirepo" else {}

    out_dir = paths.state / "doctor"
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "_scratch_prompt.md"
    patch_path = out_dir / "_scratch_patch.json"

    reports: List[Dict] = []
    for scope in store.partition["scopes"]:
        node = scope["node"]
        if args.node and node != args.node:
            continue
        golden = golden_by_module.get(scope["module"], [])
        report = doctor_mod.doctor_scope(
            scope, store.inventory, store.extraction, store.xref, sched,
            store.state.get("claims", []), run_id, runner, paths.repo,
            prompt_path, patch_path, validator, golden,
        )
        reports.append(report)
        print("  %-40s schema_valid=%-5s empty=%-5s recall=%s false_unknown=%s"
              % (node, report.get("schema_valid"), report.get("empty"),
                 report.get("recall"), report.get("false_unknown_rate")))

    for p in (prompt_path, patch_path):
        if p.exists():
            p.unlink()

    agg = doctor_mod.aggregate(reports)
    agg["model"] = args.model
    agg["scope_reports"] = reports
    write_json(out_dir / ("%s.json" % args.model), agg)
    print("doctor    %s: schema_valid=%s%% yield_collapse=%s%% recall=%s%% false_unknown=%s%% (n=%d scope(s), %d golden fact(s))"
          % (args.model, doctor_mod._pct(agg["schema_validity_rate"]),
             doctor_mod._pct(agg["yield_collapse_rate"]), doctor_mod._pct(agg["recall"]),
             doctor_mod._pct(agg["false_unknown_rate"]), agg["scopes"], agg["golden_total"]))

    models = {}
    for f in out_dir.glob("*.json"):
        data = read_json(f)
        if isinstance(data, dict) and "model" in data:
            models[data["model"]] = data
    if len(models) > 1:
        print("\n" + doctor_mod.compatibility_table(models))
    else:
        print("next      cdp doctor --model <other> to compare, once more than one "
              "model has a report here")

    backend.close()
    return 0


# ----------------------------------------------------------------- status


@_locked(shared=True)
def cmd_status(args) -> int:
    paths = _paths(args)
    store = query_mod.Store(_open_store(paths))
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
        if buckets[freshness_mod.STALE] + buckets[freshness_mod.UNREVIEWED] > 0:
            print("tip       cdp run --stale-only to re-dispatch just the stale/anchored-but-unreviewed scope(s)")
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
    run_id = str(store.manifest.get("run_id", "cdp"))
    rows = store.backend.task_rows(run_id)
    if rows:
        node_of_hash = {s.get("scope_hash"): s["node"] for s in store.partition["scopes"]}
        print("\ntasks     run %s" % run_id)
        incomplete = False
        for row in rows:
            node = node_of_hash.get(row["scope_hash"], row["scope_hash"])
            print("    %-14s %-40s attempts %d%s"
                  % (row["state"] or "pending", node, row["attempts"] or 0,
                     "  %s" % row["last_error"] if row["last_error"] else ""))
            if row["state"] not in (supervisor_mod.FOLDED,):
                incomplete = True
        if incomplete:
            print("next      cdp run --resume --run-id %s to continue the incomplete task(s) above" % run_id)
    store.close()
    return 0


# ------------------------------------------------------------------- diff


def _open_diff_side(state_dir: Path) -> "query_mod.Store":
    """Directory-pair mode: detect which directory-shaped backend is
    actually present instead of assuming `SqliteStore` -- `FileStore`'s
    loose-JSON layout is just as diffable, it was simply never tried.
    Postgres has no per-snapshot directory at all, so it can't be reached
    this way; that's what `--repo`/`--old-sha`/`--new-sha` is for."""
    state_dir = state_dir.expanduser().resolve()
    if (state_dir / "index.db").is_file():
        return query_mod.Store(state_dir)
    if (state_dir / "graph.json").is_file():
        return query_mod.Store(FileStore(state_dir))
    raise CdpError(
        "no CDP state at %s -- run `scan` first. If this is postgres-backed "
        "state, `cdp diff <dir> <dir>` can't read it (postgres has no "
        "per-snapshot directory) -- use `cdp diff --repo ... --old-sha ... "
        "--new-sha ...` instead." % state_dir
    )


def _current_snapshot_sha(backend: WorkspaceStore, repo_id: str) -> str:
    backend.use_latest_snapshot()
    sid = backend.snapshot_id()
    row = next((r for r in backend.list_snapshots() if r["id"] == sid), None)
    if row is None:
        raise CdpError("no scanned snapshot for %s -- run `cdp scan` first" % repo_id)
    return row["commit_sha"]


@_locked(shared=True)
def cmd_diff(args) -> int:
    dir_mode = args.old_state is not None or args.new_state is not None
    sha_mode = args.old_sha is not None or args.new_sha is not None
    if dir_mode and sha_mode:
        raise CdpError("pass either two state directories or --old-sha/--new-sha, not both")

    if dir_mode:
        if args.old_state is None or args.new_state is None:
            raise CdpError("directory mode needs both old_state and new_state")
        old = _open_diff_side(Path(args.old_state))
        new = _open_diff_side(Path(args.new_state))
        try:
            old_graph, old_xref, old_state = old.graph, old.xref, old.state
            new_graph, new_xref, new_state = new.graph, new.xref, new.state
        finally:
            old.close()
            new.close()
    else:
        if not sha_mode:
            raise CdpError("need either two state directories, or --old-sha/--new-sha")
        paths = _paths(args)
        backend = _open_store(paths)
        try:
            if not backend.supports_snapshot_history():
                raise CdpError(
                    "%s can't back `cdp diff --old-sha/--new-sha` -- it holds "
                    "exactly one snapshot per directory, with no commit-sha "
                    "lineage to select from. Use `cdp diff <old_dir> <new_dir>` "
                    "instead, or switch this repo's backend to sqlite/postgres."
                    % type(backend).__name__
                )
            repo_id = registry_mod.repo_identity(paths.repo)
            old_sha = args.old_sha or _current_snapshot_sha(backend, repo_id)
            new_sha = args.new_sha or _current_snapshot_sha(backend, repo_id)

            backend.use_snapshot(repo_id, old_sha)
            old_store = query_mod.Store(backend, use_latest=False)
            old_graph, old_xref, old_state = old_store.graph, old_store.xref, old_store.state

            backend.use_snapshot(repo_id, new_sha)
            new_store = query_mod.Store(backend, use_latest=False)
            new_graph, new_xref, new_state = new_store.graph, new_store.xref, new_store.state
        finally:
            backend.close()

    result = diffs_mod.diff_snapshots(old_graph, old_xref, old_state, new_graph, new_xref, new_state)
    if args.json:
        print(__import__("json").dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(diffs_mod.summarise(result)))
        print("tip       cdp query symbol/table <name> for full context on a changed item above")
    return 0


# -------------------------------------------------------------------- link


@_locked(shared=False)
def cmd_link_scan(args) -> int:
    """M8.1: read-only across N already-scanned state directories -- N may be
    1, since `link.scan_links` explodes each state dir's pooled edges by
    their own `module` tag before matching, so a single whole-monorepo scan
    already yields cross-module links. R3 -- `link scan` never opens a store
    for writing and never touches `snapshot.*`/`claim.*`; it only reads each
    store's `dataflow.json` and `manifest.json` (for the `(repo, head)`
    identity 5.5 requires).
    """
    snapshots = []
    stores = []
    try:
        for d in args.state_dirs:
            store = query_mod.Store(Path(d).expanduser().resolve())
            stores.append(store)
            snapshots.append(
                {
                    "repo": store.manifest.get("repo", d),
                    "head": store.manifest.get("head", "?"),
                    "dataflow": store.dataflow,
                }
            )
        report = link_mod.scan_links(snapshots)
    finally:
        for store in stores:
            store.close()
    paths = _paths(args)
    db_store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else _open_store(paths)
    try:
        if not db_store.supports_link_edges():
            raise CdpError(
                "%s cannot back `cdp link scan --db` -- needs the sqlite backend "
                "(pass --db, or set `backend = \"sqlite\"` in .cdp.toml)" % type(db_store).__name__
            )
        db_store.write_link_edges(report)
    finally:
        db_store.close()
    if args.json:
        print(__import__("json").dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(link_mod.summarise(report)))
        print("next      cdp link query --service <name>")
        heuristic = report.get("totals", {}).get("heuristic", 0)
        if heuristic:
            print("tip       cdp link prompts --out <dir> to resolve the %d ambiguous match(es)"
                  % heuristic)
    return 0


def _read_link_report(store) -> Dict:
    edges = store.read_link_edges()
    return {
        "links": [e["data"] for e in edges if e["kind"] == "link"],
        "unmatched": [e["data"] for e in edges if e["kind"] == "unmatched"],
    }


@_locked(shared=False)
def cmd_link_prompts(args) -> int:
    """M8.3 (5.2): the LLM tier fires only on ambiguous (`heuristic`) matches
    a prior `link scan --db` already persisted. Writes one prompt per
    distinct ambiguous caller target (`link.build_tasks` groups candidates so
    "three concatenations" become one question), plus `tasks.json` --
    `link collect`'s own validation reference for what each task actually
    showed the model, so a resolution's citation can be checked against it.

    Reuses `runner.py`'s protocol wholesale (5.2, "mirrors the core loop
    exactly"): with `--runner-cmd`, each task's prompt/patch pair is run
    through the exact same `SubprocessRunner` `cdp run` uses, no
    link-specific dispatch code.
    """
    paths = _paths(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else _open_store(paths)
    try:
        if not store.supports_link_edges():
            raise CdpError(
                "%s cannot back `cdp link prompts` -- needs the sqlite backend "
                "(pass --db, or set `backend = \"sqlite\"` in .cdp.toml)" % type(store).__name__
            )
        report = _read_link_report(store)
    finally:
        store.close()

    tasks = link_mod.build_tasks(report)
    out_dir = Path(args.out).expanduser().resolve()
    (out_dir / "tasks").mkdir(parents=True, exist_ok=True)
    (out_dir / "inbox").mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "tasks.json", tasks)

    runner = runner_mod.SubprocessRunner(args.runner_cmd.split()) if args.runner_cmd else None
    ran = 0
    for task in tasks:
        prompt_path = out_dir / "tasks" / (task["task_id"] + ".md")
        write_text(prompt_path, link_mod.render_task_prompt(task))
        if runner is not None:
            patch_path = out_dir / "inbox" / (task["task_id"] + ".json")
            result = runner.run(prompt_path, patch_path)
            print("  %-20s %s%s" % (task["task_id"], "ok" if result.ok else "FAILED",
                                     "" if result.ok else ": %s" % result.error))
            ran += 1
    print("link prompts  %d ambiguous task(s) -> %s%s"
          % (len(tasks), out_dir, "  (ran %d via --runner-cmd)" % ran if runner else ""))
    if tasks and runner is None:
        print("next      hand each prompt in %s/tasks to a leaf, drop its patch in "
              "%s/inbox, then cdp link collect --in %s" % (out_dir, out_dir, out_dir))
    return 0


@_locked(shared=False)
def cmd_link_collect(args) -> int:
    """M8.3 (5.2): validate -> verify -> entail -> fold, for link-task
    patches only -- `link.validate_task_patch` is the validate+verify+entail
    step (closed verdict vocabulary, no fabricated citation), matching
    `cmd_collect`'s own shape for the single-repo case one function up, not
    the same function, since a link task's patch is a handful of fields
    against a cross-repo candidate set rather than a scope's full claim
    schema. Accepted resolutions attribute onto their link by `link_id`
    (never touching `match_kind`, M8.1's own closed vocabulary) and are
    persisted back the same way `link scan --db` writes -- R3 still holds,
    nothing here touches `snapshot.*`/`claim.*`.
    """
    in_dir = Path(args.in_dir).expanduser().resolve()
    tasks = {t["task_id"]: t for t in read_json(in_dir / "tasks.json")}

    paths = _paths(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else _open_store(paths)
    try:
        if not store.supports_link_edges():
            raise CdpError(
                "%s cannot back `cdp link collect` -- needs the sqlite backend "
                "(pass --db, or set \"backend = \\\"sqlite\\\"\" in .cdp.toml)" % type(store).__name__
            )
        report = _read_link_report(store)
        run_id = "cdp-link"
        accepted = 0
        rejected = []
        folded = 0
        for patch_path in sorted((in_dir / "inbox").glob("*.json")):
            try:
                patch = json.loads(patch_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                rejected.append((patch_path.name, ["not valid JSON: %s" % exc]))
                continue
            task = tasks.get(patch.get("task_id"))
            if task is None:
                rejected.append((patch_path.name, ["/task_id: %r is not a known task" % patch.get("task_id")]))
                continue
            errors = link_mod.validate_task_patch(patch, task)
            if errors:
                rejected.append((patch_path.name, errors))
                continue
            accepted += 1
            folded += link_mod.fold_resolutions(report, task, patch, run_id)
        store.write_link_edges(report)
    finally:
        store.close()

    print("link collect  accepted %d, rejected %d, %d resolution(s) folded"
          % (accepted, len(rejected), folded))
    for name, errors in rejected:
        print("  REJECTED %s: %s" % (name, "; ".join(errors[:4])))
    if folded:
        print("next      cdp link query --service <name>")
    return 0


@_locked(shared=False)
def cmd_link_run(args) -> int:
    """Post-Phase-9 item 5: `link prompts`/`link collect` are a manual,
    file-handoff pair (M8.3) with no leases, no `link_task` rows, and no
    trajectory row -- link work was invisible to `dim_task_kind=link`'s
    routing prior/elision regret even though both already support it by
    construction. This dispatches every ambiguous task through
    `link.dispatch_link_task` (the same lease/retry state machine `cdp run`
    uses for scopes, against `link_task` rather than `snapshot_task` -- R3's
    non-entanglement holds), folds validated resolutions immediately, and
    records one `fact_leaf_run` row per task with `task_kind="link"`.
    """
    paths = _paths(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else _open_store(paths)
    try:
        if not store.supports_link_edges():
            raise CdpError(
                "%s cannot back `cdp link run` -- needs the sqlite backend "
                "(pass --db, or set `backend = \"sqlite\"` in .cdp.toml)" % type(store).__name__
            )
        report = _read_link_report(store)
        tasks = link_mod.build_tasks(report)
        run_id = args.run_id or "cdp-link"
        prompts_dir = Path(args.out).expanduser().resolve() if args.out else (paths.state / "link-tasks")
        prompts_dir.mkdir(parents=True, exist_ok=True)
        runner = _build_runner(args)
        model = args.runner_cmd.split()[0] if args.runner_cmd else "human"
        folded = 0
        counts: Dict[str, int] = {}
        with trajectory_mod.TrajectoryStore() as trajectory:
            for task in tasks:
                row = link_mod.dispatch_link_task(
                    task, run_id, runner, store, prompts_dir, max_attempts=args.max_attempts,
                )
                if row is None:
                    continue
                counts[row["state"]] = counts.get(row["state"], 0) + 1
                if row["state"] == supervisor_mod.VALIDATED:
                    folded += link_mod.fold_resolutions(report, task, row["patch"], run_id)
                repo_id = task["candidates"][0]["caller"]["repo"]
                trajectory.record_leaf_run(
                    run_id=run_id, node=task["task_id"], scope_hash=task["task_id"], repo_id=repo_id,
                    model=model, scope_shape_key=link_mod.link_task_shape_key(task),
                    template_version=None, tier=None, task_kind="link",
                    state=row["state"], attempts=row["attempts"],
                )
        store.write_link_edges(report)
    finally:
        store.close()
    print("link run  %d task(s)  %s  %d resolution(s) folded"
          % (len(tasks), ", ".join("%s %d" % kv for kv in sorted(counts.items())) or "nothing to dispatch", folded))
    if folded:
        print("next      cdp link query --service <name>")
    return 0


@_locked(shared=False)
def cmd_link_refresh(args) -> int:
    """M8.4 (5.3): re-verify a prior `link scan --db`'s contracts against
    freshly scanned state directories for the repo(s) named here, mirroring
    Phase 3's refresh semantics (D10) -- an endpoint that still exists
    carries forward re-anchored; one that vanished decays with a stated
    reason. R3 still holds: nothing here touches `snapshot.*`/`claim.*`, and
    a repo not named in `state_dirs` is left byte-identical in the persisted
    report (5.5).
    """
    snapshots = []
    stores = []
    try:
        for d in args.state_dirs:
            store = query_mod.Store(Path(d).expanduser().resolve())
            stores.append(store)
            snapshots.append(
                {
                    "repo": store.manifest.get("repo", d),
                    "head": store.manifest.get("head", "?"),
                    "dataflow": store.dataflow,
                }
            )
    finally:
        for store in stores:
            store.close()

    paths = _paths(args)
    db_store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else _open_store(paths)
    try:
        if not db_store.supports_link_edges():
            raise CdpError(
                "%s cannot back `cdp link refresh` -- needs the sqlite backend "
                "(pass --db, or set `backend = \"sqlite\"` in .cdp.toml)" % type(db_store).__name__
            )
        old_report = _read_link_report(db_store)
        report = link_mod.refresh_links(old_report, snapshots)
        db_store.write_link_edges(report)
    finally:
        db_store.close()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(link_mod.summarise_refresh(report)))
        print("next      cdp link query --service <name>")
    return 0


@_locked(shared=True)
def cmd_link_query(args) -> int:
    """M8.2 (5.6): reads back the `link.*` rows a prior `link scan --db`
    persisted and renders what touches one service -- links either direction,
    and that service's own unmatched outbound calls as a named deliverable
    rather than an absence.
    """
    paths = _paths(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else _open_store(paths)
    try:
        if not store.supports_link_edges():
            raise CdpError(
                "%s cannot back `cdp link query` -- needs the sqlite backend "
                "(pass --db, or set `backend = \"sqlite\"` in .cdp.toml)" % type(store).__name__
            )
        edges = store.read_link_edges()
    finally:
        store.close()
    result = link_mod.query_service(edges, args.service)
    if args.json:
        print(__import__("json").dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(link_mod.summarise_query(result)))
    return 0


# --------------------------------------------------------------------- gc


@_locked(shared=False)
def cmd_gc(args) -> int:
    """M3.6/0.10: a snapshot is kept iff HEAD, pinned, or cited by a live
    claim's `anchor_verified_at`/`claim_reviewed_at`.

    `--db` is an explicit escape hatch straight to a `SqliteStore` file --
    for retention against a store `_paths()`/`.cdp.toml` would not resolve to
    on its own. Without it, `gc` resolves the backend the same way every
    other command does (`_open_store`), so it now genuinely works against a
    `.cdp.toml`-configured Postgres backend too, not just the sqlite default.
    """
    paths = _paths(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else _open_store(paths)
    if not store.supports_run_tracking():
        raise CdpError(
            "%s has no run/task tracking -- `cdp gc` needs the sqlite or "
            "postgres backend" % type(store).__name__
        )
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
            raise CdpError("no snapshot for HEAD (%s) in this store -- run `cdp scan` against it first"
                            % head_sha[:12])
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
        if drop and not args.dry_run:
            print("tip       cdp compact to also fold superseded patches into the cold archive")
    finally:
        store.close()
    return 0


@_locked(shared=False)
def cmd_compact(args) -> int:
    """M7.3/2.4: move superseded `complete` generations to the cold archive.
    `--keep-generations` is a performance knob, never a retention decision --
    the archive is read by `verify --full` and `export --archive`, never
    silently dropped."""
    paths = _paths(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else _open_store(paths)
    if not store.supports_compaction():
        raise CdpError(
            "%s cannot back `cdp compact` -- needs the sqlite backend" % type(store).__name__
        )
    try:
        result = store.compact(
            keep_generations=args.keep_generations,
            threshold=args.compact_threshold,
            dry_run=args.dry_run,
        )
        if not result["threshold_met"]:
            print("compact   %.0f%% superseded (< --compact-threshold %.0f%%) -- nothing moved"
                  % (result["eligible_ratio"] * 100, args.compact_threshold * 100))
        else:
            print("compact   moved %d superseded patch(es) to the archive, kept %d%s"
                  % (result["moved"], result["kept"], " [dry-run]" if args.dry_run else ""))
            if result["moved"] and not args.dry_run:
                print("tip       cdp export --format archive to inspect the cold archive")
    finally:
        store.close()
    return 0


# ---------------------------------------------------------------- export


@_locked(shared=True)
def cmd_export(args) -> int:
    """M7.5 (0.19): four fixed output shapes -- `cdp/export.py` has the full
    account of each."""
    paths = _paths(args)
    store = SqliteStore(Path(args.db).expanduser().resolve()) if args.db else _open_store(paths)
    dest = Path(args.out).expanduser().resolve()
    try:
        if args.format == "json":
            written = export_mod.export_json(store, dest)
            print("export    json      %d artifact(s)/report(s) -> %s" % (len(written), dest))
            print("tip       --format patches for a reviewable dump, "
                  "--format archive to include the cold archive")
        elif args.format == "patches":
            n = export_mod.export_patches(store, dest)
            print("export    patches   %d patch(es) -> %s" % (n, dest))
        elif args.format == "archive":
            if not store.supports_compaction():
                raise CdpError(
                    "%s has no cold archive -- `cdp export --format archive` needs "
                    "the sqlite backend" % type(store).__name__
                )
            n = export_mod.export_archive(store, dest)
            print("export    archive   %d row(s) -> %s" % (n, dest))
        else:
            counts = export_mod.export_anonymized(store, dest)
            print("export    anonymized  %d claim(s), %d unknown(s), %d conflict(s) -> %s"
                  % (counts["claims"], counts["unknowns"], counts["conflicts"], dest))
    finally:
        store.close()
    return 0


# ---------------------------------------------------------------- rollback


@_locked(shared=False)
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
    backend = _open_store(paths)
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

    repo_id = registry_mod.repo_identity(paths.repo)
    with trajectory_mod.TrajectoryStore() as trajectory:
        for excluded_run_id in sorted(new_excluded):
            trajectory.record_run_event(run_id=excluded_run_id, repo_id=repo_id,
                                         event="rolled_back", reason=reason)

    print("rollback  %s %s: excluded %d run(s) (%s)"
          % (("--to-run" if kind == "to_run" else "--to-snapshot"), target,
             len(new_excluded), ", ".join(sorted(new_excluded))))
    print("folded    %d claim(s), %d unknown(s), coverage %.1f%%"
          % (len(folded["claims"]), len(folded["unknowns"]), 100 * folded["coverage"]["fraction"]))
    print("next      cdp query stats to confirm the exclusion took effect")
    if not args.reason:
        print("tip       --reason \"...\" records why, in the rollback ledger, for whoever reads it later")
    backend.close()
    return 0


def _git_identity(repo: Path) -> str:
    name = run_git(repo, "config", "user.name")
    email = run_git(repo, "config", "user.email")
    name = (name or "").strip() or "unknown"
    email = (email or "").strip()
    return "%s <%s>" % (name, email) if email else name


@_locked(shared=False)
def cmd_answer(args) -> int:
    """M4.4: a human claim against an unknown, through the *entire* pipeline
    -- validate, verify the anchor, entail, fold -- exactly like a leaf
    agent's patch (`cmd_collect`). `author_kind=human` changes merge
    precedence (R11) and, per `entail.py`, whether a contradiction is
    silently accepted -- it never changes the gate itself.
    """
    paths = _paths(args)
    backend = _open_store(paths)
    store = query_mod.Store(backend)
    _check_repo_matches_manifest(paths, store.manifest)

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
    if kept:
        print("next      cdp query unknowns to see what's still open")
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
#
# `mcp_server/`, `litellm_adapter/`, `agent_adapter/` (Phase 9, 7.1/7.2/7.4)
# are deliberately absent -- they are consumed via `pip install cdp[mcp]` /
# an MCP client config / a LangGraph or ADK agent importing `agent_adapter`,
# never by copying into a target repo's `.claude/skills/`. Not an oversight.
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


def register_leaf_agent(target: Path, framework: str) -> None:
    """Point `target` at whatever produces leaf patches for `framework`.

    `claude-code` is the only framework with a file to copy: `.claude/agents/`
    is a Claude Code discovery convention, and `cdp-leaf.md` is meaningless to
    anything else. `langgraph`/`adk` leaves are Python the target repo's own
    graph/agent code imports (`agent_adapter.langgraph_leaf`/`adk_leaf`), so
    -- like `agent_adapter/` itself, which `DIST_MEMBERS` deliberately never
    vendors -- there is nothing to copy; printing the install/import guidance
    is the entire "installation". `none` registers nothing, for repos driving
    leaves purely through `cdp run --wave-all --runner-cmd`.
    """
    if framework == "claude-code":
        agents = target / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        source_agent = SKILL_ROOT / "agents" / "cdp-leaf.md"
        if source_agent.exists():
            shutil.copy2(source_agent, agents / "cdp-leaf.md")
            print("installed %s" % (agents / "cdp-leaf.md"))
    elif framework in ("langgraph", "adk"):
        module = "agent_adapter.%s_leaf" % framework
        print("no files copied for --framework %s -- in %s, run:" % (framework, target))
        print("  pip install cdp[agent]")
        print("  from %s import run_leaf" % module)
    elif framework == "none":
        pass


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

    framework = getattr(args, "framework", "claude-code")
    if getattr(args, "hook", False) and framework != "claude-code":
        raise CdpError("--hook installs a Claude Code PreToolUse nudge; "
                        "it does not apply to --framework %s" % framework)

    dest = target / ".claude" / "skills" / "cdp"
    copy_distribution(dest)
    print("installed %s" % dest)

    register_leaf_agent(target, framework)

    # Tier-0 (7.9): a root-level AGENTS.md works for any assistant, hook-less
    # or not — Cursor, Codex, Copilot, Aider all read it. Placed at the
    # target's root, not inside dest, since that is where those tools look.
    # Never overwritten: a repo's own AGENTS.md is the operator's file.
    agents_md = target / "AGENTS.md"
    source_agents_md = SKILL_ROOT / "AGENTS.md"
    if agents_md.exists():
        print("kept      %s (already present, not overwritten)" % agents_md)
    elif source_agents_md.exists():
        shutil.copy2(source_agents_md, agents_md)
        print("wrote     %s" % agents_md)
    if getattr(args, "hook", False):
        for line in install_hook(target, dest, strict=getattr(args, "strict", False)):
            print(line)
    print("try       python3 %s scan --repo %s"
          % (dest / "run.py", target))
    print("tip       --hook to auto-refresh state on every commit, "
          "--framework {langgraph,adk} for non-Claude-Code leaves")
    return 0


#: `matcher` is compared as an exact string when it contains only letters,
# digits and `|`, so this fires on exactly these three tools and nothing else.
HOOK_MATCHER = "Read|Grep|Glob"


def install_hook(target: Path, dest: Path, strict: bool = False) -> List[str]:
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
    entry = {"type": "command", "command": command, "args": ["--strict"] if strict else []}
    hooks = settings.setdefault("hooks", {})
    groups = hooks.setdefault("PreToolUse", [])
    for group in groups:
        if isinstance(group, dict) and group.get("matcher") == HOOK_MATCHER:
            handlers = group.setdefault("hooks", [])
            # Idempotent: re-running `install --hook` must not stack duplicates,
            # and re-running with a different `--strict` choice updates the
            # existing entry's args in place rather than leaving the old choice.
            existing = next((h for h in handlers
                              if isinstance(h, dict) and h.get("command") == command), None)
            if existing is None:
                handlers.append(entry)
            else:
                existing["args"] = entry["args"]
            break
    else:
        groups.append({"matcher": HOOK_MATCHER, "hooks": [entry]})

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(settings_path, settings)
    notes.insert(0, "hook      PreToolUse on %s -> %s" % (HOOK_MATCHER, settings_path))
    if strict:
        notes.insert(1, "          strict mode: blocks the first source read of a session "
                        "when the index is fresh\n          and covers at least %d%% of the "
                        "repo; degrades to the nudge otherwise, and never\n          blocks "
                        "(or nudges) twice in one session."
                        % int(hook_mod.STRICT_MIN_COVERAGE * 100))
    else:
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


def _store_snapshot(repo: Path, root: Path) -> Dict[str, str]:
    """`root`'s store content, canonically serialised through the store API
    -- comparable across two independently-written stores holding identical
    content, unlike the file's own bytes (see `_state_files`). Resolved via
    `_open_store` (`repo`'s `.cdp.toml`, same as the scan that wrote `root`
    used), not a hardcoded `SqliteStore` -- otherwise this would silently
    read (or create) the wrong backend for any repo configured to use `file`
    or `postgres`. `{}` vs `{}` (no differences) when nothing was scanned at
    all, e.g. a `check_determinism` test stub that writes raw files
    directly."""
    backend = _open_store(Paths(repo=repo, state=root))
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

        store_a, store_b = _store_snapshot(repo, a), _store_snapshot(repo, b)
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

        # Read back through the store API (D3, `PHASE/FINDINGS.md`) via
        # `_open_store` -- not a hardcoded `SqliteStore`, and not a raw
        # filesystem walk: golden capture must resolve the same backend the
        # scan above actually used (`repo`'s `.cdp.toml`), or this would
        # silently read the wrong store the moment a repo configures `file`
        # or `postgres`. `golden_mod.canonical` re-serialises every artifact
        # the same way regardless of backend, so capture is a function of
        # content, not of the storage format.
        backend = _open_store(Paths(repo=repo, state=state))
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
