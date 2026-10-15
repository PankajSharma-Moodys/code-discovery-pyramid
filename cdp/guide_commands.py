"""The command guide: ONE source for what every `cdp` command does (the kinds are in
`guide_kinds.py`). Each command has **what** (does / writes / does not), **how**
(flags that matter, defaults, side effects), examples, and **where** (when to use it,
what next). `guide.py` renders every surface from this; `tests/test_guide.py` and
`tests/test_guide_examples.py` hold them to it.

Examples are `(command, mode)`: mode `run` is executed against a fixture repo by the
tests, `parse` is only checked against the real parser (needs a model, a second repo,
or is destructive). `<placeholders>` are bound by the tests.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

Example = Tuple[str, str]


def ex(cmd: str, parse: bool = False) -> Example:
    return (cmd, "parse" if parse else "run")


STORE = ("State lives in ONE machine store, `CDP_HOME` (default `~/.cdp`), never in the repo: "
         "index in `index.db`, files under `work/<repo-slug>/` (`docs/`, `prompts/`, `patches/inbox/`).")

COMMANDS: Dict[str, Dict] = {
    "scan": {
        "what": "Deterministic extraction of the whole repo (symbols, call edges, routes, tables, "
                "config, dataflow, claims). No model calls. Writes the machine store and, unless "
                "`--no-docs`, the markdown docs. " + STORE,
        "how": "Re-running is safe (new snapshot at the current commit). Indexes the working tree as is: "
               "with uncommitted edits the snapshot is labelled `+uncommitted`. `--max-leaf-files`/`--max-leaf-loc` "
               "size the scopes `prompts` hands to leaf agents; `--max-concurrent` caps scopes per wave; "
               "`--max-hops` caps dataflow path length; `--workers 1` forces sequential extraction.",
        "examples": [ex("scan"), ex("scan --exclude vendor --workers 4"), ex("scan --no-docs --quiet")],
        "where": "First command on any repo, or after structural changes. Then `query stats`.",
    },
    "query": {
        "what": "Ask the index a typed question; every answer is cited `file:line` and carries "
                "`as_of`. 14 kinds, see `help <kind>`. Read-only.",
        "how": "`query <kind> [term]`. Parameters apply per kind; passing one a kind does not use is "
               "an error. `--budget` caps rows (default 200; `elided: N` reports the cut); `stats` and "
               "`coverage` are never budgeted. `--json` prints the full result. Exit 1 when a term, filter or "
               "narrowing parameter matched nothing (as grep), else 0; topics: `help views|filter|paging|match`.",
        "examples": [ex("query stats --json"), ex("query symbol <symbol> --as-of <sha>")],
        "where": "Everything about the code. Pick the kind with `help recipes` or the table in `help`.",
    },
    "docs": {
        "what": "Renders `00-overview.md`, `modules/<module>.md`, `dataflow.md`, `unknowns.md`, "
                "`CLAUDE.md` from the index. Read-only on the index.",
        "how": "Default output `<CDP_HOME>/work/<repo-slug>/docs/` (printed). `--out DIR` writes elsewhere.",
        "examples": [ex("docs"), ex("docs --out <out>")],
        "where": "Onboarding or a CLAUDE.md draft. For a specific question use `query`.",
    },
    "status": {
        "what": "Index head vs git HEAD (behind/dirty), coverage, freshness buckets, waves, per-node "
                "status and the current run's task table.",
        "how": "`--json` is what the SessionStart hook and MCP `cdp_status` read. Answers come from the "
               "snapshot of HEAD, else the nearest clean ancestor, never another branch (else `scan`); "
               "`N uncommitted file(s) included in this index` = a `+uncommitted` snapshot.",
        "examples": [ex("status"), ex("status --json")],
        "where": "Before trusting an answer as current. Behind -> `refresh`; stale -> `run --stale-only`.",
    },
    "diff": {
        "what": "Typed structural deltas (files added/removed/changed, symbols added/removed/changed, "
                "routes, module edges, claims) between two scanned snapshots of the same repo. A file "
                "counts as changed when its size, line count or a definition's extent differs (no "
                "content hash is kept).",
        "how": "Two forms: `diff <old_state> <new_state>` (two state directories) or `diff --old-sha A "
               "--new-sha B` (snapshots of `--repo`; needs the sqlite/postgres store). An omitted "
               "side defaults to the current/latest scanned snapshot; both omitted compares a "
               "snapshot with itself. Git file changes without a re-scan do not appear.",
        "examples": [ex("diff --old-sha <sha> --new-sha <sha>"), ex("diff <old_state> <new_state>", True)],
        "where": "'What changed structurally between releases'. Then `query symbol`/`table` on an item.",
    },
    "prompts": {
        "what": "Writes one leaf prompt per scope for the optional model-review layer.",
        "how": "Output `<CDP_HOME>/work/<repo-slug>/prompts/<node>.md` (printed). `--wave N`/`--node X` "
               "limit it; `--digest` builds full-file prompts instead of citation prompts; `--measure` "
               "prints token estimates and writes nothing; `--lessons N`/`--no-lessons` choose the "
               "lesson-set.",
        "examples": [ex("prompts"), ex("prompts --wave 0 --digest"), ex("prompts --measure")],
        "where": "Only for model review. Hand each prompt to a leaf, drop its patch in "
                 "`<CDP_HOME>/work/<repo-slug>/patches/inbox/`, then `collect`.",
    },
    "collect": {
        "what": "Validates, verifies (anchors exist), entails and appends the leaf patches in the inbox.",
        "how": "Reads `<CDP_HOME>/work/<repo-slug>/patches/inbox/`. `--mode strict` (default) demotes "
               "unverifiable claims to unknowns; `lenient` keeps more. Exit 0 when every patch was accepted "
               "(or the inbox is empty), 3 when some were rejected, 1 when all were (rejections are listed).",
        "examples": [ex("collect")],
        "where": "After leaves wrote patches. Then `fold --check`.",
    },
    "fold": {
        "what": "Recomputes `state.json` (claims, unknowns, coverage) from the patch log + xref.",
        "how": "`--check` verifies the invariant and writes nothing.",
        "examples": [ex("fold"), ex("fold --check")],
        "where": "After `collect`/`rollback`/`compact`. Failure of `--check` -> `rollback` the run, then `fold`.",
    },
    "refresh": {
        "what": "Incremental update: re-extracts changed files, re-verifies every live claim against "
                "HEAD, no model calls. No-op when HEAD is unchanged.",
        "how": "`--quiet` for hooks. Run automatically at session start; `githook install` runs it on "
               "commit. Refuses a dirty tree (`refresh requires a clean working tree`, exit 2): commit, "
               "stash, or `scan` (which indexes it as `+uncommitted`).",
        "examples": [ex("refresh"), ex("refresh --quiet")],
        "where": "Index is behind HEAD. Then `status`.",
    },
    "run": {
        "what": "The wave loop for model review: dispatch leaves -> collect -> adjudicate -> fold, "
                "supervised (leases, retries, resume). Costs model calls via `--runner-cmd`.",
        "how": "Target: `--wave N`, `--wave-all`, `--stale-only` or `--scope NODE`. Without "
               "`--runner-cmd` it waits for patches dropped by hand. `--parallel N` runs N scopes of a "
               "wave at once; `--timeout` (default 900s) and `--max-attempts` (3) bound a scope; "
               "`--resume` continues an interrupted run.",
        "examples": [ex('run --wave-all --runner-cmd "<cmd>" --parallel 4', True),
                     ex("run --stale-only --runner-cmd \"<cmd>\"", True), ex("run --resume --wave-all", True)],
        "where": "Optional: adds meaning on top of `scan`. `status` shows task state.",
    },
    "verify": {
        "what": "Recomputes the fold from the log and diffs it with `state.json`; `--full` also proves "
                "the cold archive.",
        "how": "Read-only. `--mode` as in `collect`.",
        "examples": [ex("verify"), ex("verify --full")],
        "where": "Integrity check. FAIL -> `rollback --to-run <run>`, then `fold`.",
    },
    "answer": {
        "what": "Records a human claim against an unknown through the same validate/verify/entail/fold "
                "pipeline as a leaf patch (`author_kind=human`).",
        "how": "`answer <scope> --subject S --kind K --claim TEXT --anchor FILE:LINE`; the scope is the "
               "node (`root/web`, see `query unknowns`). Exit 1 if verification demoted the claim. "
               "`--channel`, `--confidence`, `--author`, `--mode` are optional.",
        "examples": [ex('answer root --subject <symbol> --kind ownership --claim "Owned by orders team" '
                        '--anchor <file>:1', True)],
        "where": "After `query unknowns` lists something a human knows. Then `query unknowns` again.",
    },
    "reflect": {
        "what": "One model call per outlier scope from a run's trajectory corpus; keeps well-formed promotions.",
        "how": "`--runner-cmd` required; `--limit` scopes (default 5); `--run-id` defaults to the store's run.",
        "examples": [ex('reflect --runner-cmd "<cmd>" --limit 3', True)],
        "where": "After a `run`. Then `lessons cut`.",
    },
    "lessons": {
        "what": "Cut and inspect numbered, pinned lesson-sets.",
        "how": "`lessons cut`; `lessons show [--version N]`; `lessons unpromote --version N --reason TEXT`.",
        "examples": [ex("lessons cut", True), ex("lessons show", True)],
        "where": "After `reflect`. Then `holdout --lessons N` before trusting a cut.",
    },
    "holdout": {
        "what": "A/B a lesson-set cut on a repo outside its own learning corpus; promotes it to latest "
                "only if tiering does not regress.",
        "how": "`holdout --lessons N --repo <holdout-repo>`: the holdout repo is `--repo`, not a "
               "positional. Exit 1 on reject.",
        "examples": [ex("holdout --lessons 1 --repo <repo>", True)],
        "where": "After `lessons cut`. On promote: `run` uses it by default.",
    },
    "gc": {
        "what": "Drops snapshots not kept by retention (HEAD, pinned, cited by a live claim).",
        "how": "`--dry-run` reports only; `--pin SHA`/`--unpin SHA` mark snapshots before computing; "
               "`--head-sha` overrides HEAD; `--db PATH` targets another existing store. SHAs may be "
               "unique prefixes; an ambiguous one lists the candidates.",
        "examples": [ex("gc --dry-run"), ex("gc --pin <sha> --dry-run")],
        "where": "Disk pressure. Then `compact` for superseded patches.",
    },
    "compact": {
        "what": "Moves superseded patch generations to the cold archive.",
        "how": "`--keep-generations N` (default 1; keep >= 1), `--compact-threshold F` (default 0.30), "
               "`--dry-run`. Run `fold` and `verify` afterwards.",
        "examples": [ex("compact --dry-run"), ex("compact --keep-generations 2", True)],
        "where": "Large patch logs. `export --format archive` inspects what moved.",
    },
    "export": {
        "what": "Dumps the store: canonical `json`, reviewable `patches`, cold `archive`, or an "
                "`anonymized` corpus.",
        "how": "`--out DIR` (required). `--format` default `json`. `--db PATH` exports another store.",
        "examples": [ex("export --format json --out <out>"), ex("export --format patches --out <out>")],
        "where": "Backup, review, or sharing a corpus.",
    },
    "rollback": {
        "what": "Excludes a run's patches from the fold without deleting them (append-only ledger); "
                "`--undo` reverses the latest.",
        "how": "`--to-run RUN` excludes one run; `--to-snapshot SHA` that run and every later one; "
               "`--reason` is recorded.",
        "examples": [ex('rollback --to-run <run> --reason "bad batch"', True), ex("rollback --undo", True)],
        "where": "`verify`/`fold --check` fails, or a bad batch of claims. Then `query stats`.",
    },
    "doctor": {
        "what": "Conformance harness for a model: schema validity, anchor survival, entailment, "
                "recall against a golden set. Writes `<CDP_HOME>/doctor/<model>.json`.",
        "how": "`--runner-cmd` and `--model` required; `--node` limits scopes; `--timeout` 300s.",
        "examples": [ex('doctor --runner-cmd "<cmd>" --model my-model', True)],
        "where": "Before trusting a new model as a leaf.",
    },
    "validate": {
        "what": "Validates a patch file against the patch schema.",
        "how": "Read-only. A non-JSON file is an error.",
        "examples": [ex("validate <patch.json>", True)],
        "where": "Debugging a leaf's output before `collect`.",
    },
    "githook": {
        "what": "Installs/removes git `post-commit`, `post-checkout`, `post-merge` and `post-rewrite` hooks "
                "running `cdp refresh` (commit, branch switch, pull, rebase).",
        "how": "Writes only into the repo's hooks directory, all four or none (a foreign hook of the same "
               "name refuses the whole install); one install serves every worktree; `uninstall` removes "
               "only CDP's hooks. Works from a checkout of CDP (no PYTHONPATH needed).",
        "examples": [ex("githook install"), ex("githook uninstall")],
        "where": "Keep the index fresh on every commit, pull and rebase. (`install --harness` is the Claude Code "
                 "session setup, not this.)",
    },
    "install": {
        "what": "Copies the skill into another repo (`.claude/skills/cdp`, plus the `cdp-leaf` agent; runtime "
                "files only, no `tests/`, ~0.5 MB). Nothing else is written by default; `--harness` adds Claude Code hooks and `.mcp.json`.",
        "how": "`install <target>`; `--framework {claude-code,langgraph,adk,none}`; `--hook` adds the "
               "PreToolUse nudge; `--harness` = the nudge (never blocks; it names the exact `cdp_query` for the "
               "Grep/Glob/Read the model reached for, once per subject, quiet after the first `cdp_query`) + "
               "UserPromptSubmit (names the kind for the question) + SessionStart refresh/status + a PostToolUse "
               "hint after empty searches + MCP server; `--strict` swaps the nudge for the gate (a repo-wide "
               "grep/find or whole-file Read the index fully answers is denied once with the answer, everything "
               "else runs; any `cdp_query` switches it off for the session); `--claude-md` writes a marked "
               "`MUST use cdp_query first` block (generated from this guide) into the target's CLAUDE.md, "
               "creating the file, never touching text outside the markers; `--allow-mcp` adds `mcp__cdp__*` to "
               "`permissions.allow` (the cdp tools run without a prompt; they edit no repository files); "
               "`--priority` = `--harness --strict --claude-md --allow-mcp`, the CDP-first preset; `--agents-md` "
               "also writes AGENTS.md; headless `claude -p` refuses MCP tools unless allowed (`--allowedTools "
               "\"mcp__cdp__*\"` or `--allow-mcp`); `--remove-harness` undoes hooks, the MCP entry, the CLAUDE.md "
               "block and the permission (only what install added) and deletes settings files it leaves empty; "
               "`--self` refreshes this repo's vendored copy (for CDP developers).",
        "examples": [ex("install <target>"), ex("install <target> --harness", True), ex("install <target> --priority", True),
                     ex("install <target> --remove-harness", True)],
        "where": "Once per repo you want Claude to use CDP in. Then `scan --repo <target>`.",
    },
    "selftest": {
        "what": "Runs the bundled tests, or the reproducibility (`--determinism REPO`) / golden "
                "(`--golden`) gates.",
        "how": "`--min-tests N` fails if fewer ran; `--bless` with `--golden` overwrites the baseline.",
        "examples": [ex("selftest --min-tests 100", True)],
        "where": "From a CDP checkout, to prove it works (an installed copy has no `tests/`: use "
                 "`selftest --determinism REPO` there).",
    },
    "help": {
        "what": "This guide: every command and query kind with What / How / Where, generated from one source.",
        "how": "`help` overview; `help <command>`; `help <kind>`; `help recipes`; `help reference` "
               "(the full reference); `--json` machine-readable. MCP: `cdp_help`.",
        "examples": [ex("help"), ex("help query"), ex("help trace"), ex("help recipes")],
        "where": "Whenever you are unsure which command or flag to use.",
    },
    "link": {
        "what": "Cross-repo/module edges: which service calls which, what publishes to a topic, matched "
                "across scanned repos. Subcommands: `scan`, `query`, `prompts`, `collect`, `run`, `refresh`.",
        "how": "`link scan` (no args: every repo in the machine store at its latest snapshot; or "
               "stand-alone state dirs) matches channel edges -- HTTP client calls (Refit, HttpClient, "
               "requests, fetch, Feign, RestTemplate) to server routes -- and does not modify the index (it "
               "takes the one empty `locks/links-*.lock` file, reused, and SQLite may touch `index.db-shm`); "
               "`link scan --db` saves the links. `link query "
               "--service NAME` (repo directory name, path, identity or unique prefix) lists callers and "
               "unmatched calls (unknown name: error listing the known ones). Over MCP: `cdp_link`. "
               "Ambiguous matches go through "
               "`link prompts --out DIR` -> leaf -> `link collect --in DIR`, or `link run --runner-cmd` "
               "(one step). `link refresh` re-verifies after a re-scan.",
        "examples": [ex("link scan"), ex("link scan --db"), ex("link scan --db <db>", True), ex("link query --service <repo-name> --db <db>", True),
                     ex("link prompts --out <out> --db <db>", True), ex("link collect --in <out> --db <db>", True),
                     ex("link run --db <db>", True), ex("link refresh --db <db>", True)],
        "where": "'Who calls this service / what breaks in other repos'. Scan every repo first.",
    },
}

#: Help text for flags the parser leaves bare or states wrongly; applied to the parser
#: itself (`guide.apply_flag_help`), so `--help`, `help <cmd>` and `help --json` agree.
#: Key: "<command> <flag-or-dest>" (nested: "link scan --json"); `*` is any command.
FLAG_HELP: Dict[str, str] = {
    "* --json": "print the full result as JSON",
    "gc --db": "path to an existing index.db (default: the machine store); a missing path is an error, never a new empty store",
    "compact --db": "path to an existing index.db (default: the machine store); a missing path is an error, never a new empty store",
    "export --db": "path to an existing index.db (default: the machine store); a missing path is an error, never a new empty store",
    "link scan --db": "save the links: bare `--db` into the machine store, or `--db PATH` into an existing index.db (a missing path is an error). Without it the scan does not modify the index",
    "link query --db": "path to an existing index.db (default: the machine store); a missing path is an error, never a new empty store",
    "link prompts --db": "path to an existing index.db (default: the machine store); a missing path is an error, never a new empty store",
    "link collect --db": "path to an existing index.db (default: the machine store); a missing path is an error, never a new empty store",
    "link run --db": "path to an existing index.db (default: the machine store); a missing path is an error, never a new empty store",
    "link refresh --db": "path to an existing index.db (default: the machine store); a missing path is an error, never a new empty store",
    "* --mode": "strict (default) demotes unverifiable claims to unknowns; lenient keeps more",
    "* --quiet": "print nothing except errors (for hooks)",
    "* --timeout": "seconds before one runner call is treated as failed",
    "answer --channel": "the edge channel this claim is about (optional)",
    "answer --confidence": "claim confidence (default high)",
    "docs --out": "output directory (default: <CDP_HOME>/work/<repo-slug>/docs)",
    "scan --max-leaf-files": "max files per leaf scope (default 40)",
    "scan --max-leaf-loc": "max lines of code per leaf scope (default 6000)",
    "scan --max-concurrent": "max scopes per wave (default 12)",
    "scan --max-hops": "max edges walked per dataflow path (default 8)",
    "scan --no-docs": "skip rendering the markdown docs (default: rendered to <CDP_HOME>/work/<repo-slug>/docs)",
    "diff --old-sha": "earlier snapshot of --repo by commit sha or unique sha prefix (default: the current/latest scanned snapshot)",
    "diff --new-sha": "later snapshot of --repo by commit sha or unique sha prefix (default: the current/latest scanned snapshot)",
    "gc --head-sha": "commit sha (or unique prefix) to treat as HEAD (default: `git -C --repo` HEAD)",
    "gc --pin": "keep this commit's snapshot (sha or unique prefix; repeatable)",
    "query --as-of": "replay the claim log up to this commit's run (sha or unique prefix); a commit only, no wall-clock cuts",
    "rollback --to-run": "exclude just this run's patches (run id, commit sha, or unique prefix)",
    "rollback --to-snapshot": "exclude this run and every run appended after it (run id, commit sha, or unique prefix)",
    "export --format": "json (canonical), patches (reviewable), archive (cold archive), anonymized (corpus); default json",
    "gc --unpin": "remove the pin on this commit's snapshot (repeatable)",
    "githook action": "install or uninstall the post-commit/post-checkout/post-merge/post-rewrite hooks",
    "install --agents-md": "also write AGENTS.md at the repository root (never overwrites; off by default)",
    "install --claude-md": "write a marked CDP rule block into the target's CLAUDE.md (idempotent; off by default)",
    "install --allow-mcp": "add mcp__cdp__* to permissions.allow so the cdp MCP tools run without a prompt (off by default)",
    "install --priority": "CDP-first preset: --harness --strict --claude-md --allow-mcp",
    "install --hook": "also install the Claude Code PreToolUse nudge (not git hooks; for those use `githook install`)",
    "lessons lessons_action": "cut a new lesson-set, show one, or unpromote a cut",
    "link link_command": "scan, query, prompts, collect, run or refresh (see `help link`)",
    "link scan --json": "print the full result as JSON",
    "link query --json": "print the full result as JSON",
    "link refresh --json": "print the full result as JSON",
    "link run --timeout": "seconds before one task's runner call is treated as failed",
    "link run --max-attempts": "retries per ambiguous task before it is abandoned",
    "query kind": "which question to ask; see `help <kind>` for each (stats, coverage, symbol, file, "
                  "module, routes, table, config, paths, trace, search, claims, unknowns, conflicts)",
    "query term": "the name to look up; meaning depends on kind (required for symbol/file/module/trace/"
                  "search; optional filter for routes/table/config/unknowns/claims; unused for paths/"
                  "stats/coverage/conflicts)",
    "query --kind": "`claims` only: filter by claim kind (entrypoint, public_api, data_model, ...)",
    "query --module": "`claims` only: claims whose module contains this text",
    "query --subject": "`claims` only: claims whose subject contains this text",
    "query --from": "`paths` only: source or trigger contains this text",
    "query --to": "`paths` only: sink contains this text",
    "query --max-hops": "`trace` only: how many edges to walk (default 8)",
    "query --exclude-role": "drop rows whose file has this role (test, build, ci, config, docs, asset, "
                            "schema, source); repeatable; not for module/paths/conflicts/stats/coverage",
    "query --budget": "rows this answer may emit across every list in it (default 200); not for stats/coverage",
    "refresh --mode": "strict (default) demotes unverifiable claims to unknowns; lenient keeps more",
    "run --mode": "strict (default) demotes unverifiable claims to unknowns; lenient keeps more",
    "status --json": "print the status as JSON (what the SessionStart hook reads)",
    "validate path": "path to the patch JSON file",
}

#: Named recipes (`help recipes`): short worked sequences. Steps are examples too.
RECIPES: List[Dict] = [
    {"name": "who-calls", "title": "Who calls X",
     "when": "You need the callers of a class or method.",
     "steps": [ex("query symbol <symbol>"), ex("query trace <method>")],
     "why": "`symbol` lists definition sites and every `used_by` site, cited. `trace` shows what X reaches."},
    {"name": "blast-radius", "title": "What breaks if I change Y",
     "when": "Before editing a method, route or table.",
     "steps": [ex("query trace <route> --exclude-role test"), ex("query symbol <method>"),
               ex("query table <table>")],
     "why": "`trace` is the reading list downstream; `symbol` the callers upstream; `table` every "
            "writer/reader. Read only the cited ranges."},
    {"name": "route-tables", "title": "Which tables does a route touch",
     "when": "Mapping an endpoint to its storage.",
     "steps": [ex("query routes <route>"), ex("query paths --from <route>"), ex("query table")],
     "why": "`paths` shows route -> service -> repository -> table when the path closes; if it "
            "reports 0 paths use `trace <route>`."},
    {"name": "config-reads", "title": "Where is a config key read",
     "when": "Finding the code behind a setting or env var.",
     "steps": [ex("query config <config-key>"), ex("query file <file>")],
     "why": "`config` gives declarations and every read site; `file` outlines the reader."},
    {"name": "onboard", "title": "Onboard onto an unfamiliar repository",
     "when": "First contact with a repo.",
     "steps": [ex("scan"), ex("query stats"), ex("query routes"), ex("query unknowns"), ex("docs")],
     "why": "`stats` is the shape, `routes` the outside edge, `unknowns` what to ask a human; `docs` "
            "writes `00-overview.md` under `<CDP_HOME>/work/<repo-slug>/docs/`."},
    {"name": "two-repos", "title": "How two repos connect",
     "when": "Service A calls service B; both are scanned.",
     "steps": [ex("scan"), ex("link scan --db"), ex("link query --service <repo-name>", True)],
     "why": "`link scan --db` matches channel edges across every scanned repo in the machine store and saves them; "
            "`link query` lists a service's callers and unmatched calls."},
    {"name": "refresh", "title": "Refresh after commits",
     "when": "The branch moved since the last scan.",
     "steps": [ex("status"), ex("refresh"), ex("query coverage")],
     "why": "`refresh` re-verifies claims and re-extracts changed files with no model calls (use `scan` "
            "after large restructures); `status` shows behind/dirty; answers list uncommitted files they may not reflect."},
    {"name": "review", "title": "Review a change",
     "when": "You need the blast radius of a diff.",
     "steps": [ex("query file <file>"), ex("query symbol <symbol>"), ex("diff --old-sha <sha> --new-sha <sha>")],
     "why": "`file` + `symbol` give the touched definitions and their callers; `diff` shows structural "
            "deltas between two scanned snapshots."},
]
