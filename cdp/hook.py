"""PreToolUse hook — turn "prefer the index over grep" from advice into a nudge.

`SKILL.md:50-54` already argues the case correctly and persuasively. The problem
is that it is prose, read once at session start, and the moment it matters is the
moment the model reaches for `Grep` without re-reading it.
`RESEARCH_GRAPHIFY.md §7.1` ranks closing that gap the single largest token lever
in the review, at the lowest cost.

**Why CDP's version can be better than the peer's.** Graphify's hook fires on any
read. `inventory.json` already classifies every file's `role`
(`lang/__init__.py:74-86`), so this one fires only on `role == "source"` — which
deletes the entire false-positive class in one line. *"Fix the typo in
README.md"* is `role == "docs"` and never triggers it.

**Three hard no-ops, all mandatory** (`PHASE/phase_1_plan.md` M1.6):

    1. no state resolvable for this repo   -- nothing to point at
    2. `inventory.head != git HEAD`        -- the index does not describe the
                                              working tree, and a hook nagging
                                              about a stale index is worse than
                                              no hook at all
    3. (retired by M2.6, see below)

The index is the one machine-level store (`CDP_HOME`, default `~/.cdp`). The
hook finds the scanned repo that contains the file being read -- the innermost
folder with a scan, so a scanned subfolder beats its parent -- and selects that
repo's snapshot **for the current HEAD**. Selecting "the oldest snapshot in the
file" is what once made the hook go silent after a repo's second scan.

**Strict mode (Phase 9, `--strict`)** turns the same one-shot trigger into a
block instead of a nudge, but only when blocking cannot backfire: coverage
(`state.json`'s `coverage.fraction`) is at or above `STRICT_MIN_COVERAGE`, and
the same freshness gate below (`inventory.head == git HEAD`) that already
guards the nudge also guards the block. Coverage is not freshness (R8, two
dates) — a 100%-coverage index at a stale HEAD is exactly the case that must
still degrade to a nudge, not block, since the index may no longer describe
the tree being read. Below the threshold, or when either gate fails, strict
mode degrades to the ordinary nudge rather than refusing silently or blocking
against ignorance — same "triggers at most once per session, never gets
stuck" one-shot marker as the nudge, so a block (or its degraded nudge) can
never repeat within a session and never leaves the model stuck: it fires once,
states why, and gets out of the way.

**Fails open, always.** Any exception, any unreadable state, any surprise in the
input shape exits 0 with no output. A hook is in the path of every file read in
the session; the worst outcome by a wide margin is one that can break it.

**Output shape (verified live on Claude Code 2.1.296).** `PreToolUse` and `PostToolUse`
`additionalContext` without a decision reaches the model; a `permissionDecision: deny`
reaches it as the reason (the harness labels any hook deny "hook error" in headless
output, with or without `systemMessage`, which the deny no longer sets). An empty grep is
a `PostToolUse` ("No matches found"), not a failure -- `--post-search` answers it.

**The gate (`--gate`, `install --harness --strict`).** It denies a call only when it can
replace it entirely: a pure search (no `;`/`&&`/pipes into non-limiters) whose every term
is a known identifier with recorded uses; a whole-file Read of a long file gets its
outline. A partial, empty or compound answer runs the call. Any MCP `cdp_query` (whatever
the server is named) marks the session as having asked the index, and the gate stops.
Each denial is once per session and subject (a search's terms, or a file for a Read). The gate stands
down for a file, or any file in a search's scope, with uncommitted changes (the index would be stale),
and for a search path outside the repo or outside a source dir. `CDP_LEAF_SESSION=1` (only `1`) stands all of
it down; markers in `$TMPDIR` are pruned by age and count.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#: Tools worth intercepting. Everything else is not a source read.
WATCHED = ("Read", "Grep", "Glob", "Bash")

#: A Bash command counts as a source search only when it runs one of these. Only
#: the gate (`--gate`) watches Bash; the plain nudge matcher never includes it.
SEARCH_COMMAND = re.compile(r"(?:^|[|;&(]\s*|\bxargs\s+)(?:grep|egrep|rg|ag|ack|find)\b")

#: The only role that gets a nudge. Editing a README, a CI file or a fixture is
#: not a question the index can answer better.
NUDGE_ROLE = "source"

#: Below this, a block would deny the model the source *and* leave the index
#: unable to answer (`RESEARCH_GRAPHIFY.md §7.8`) -- degrade to a nudge instead.
#: Deliberately high: blocking is a one-shot, session-shaping event, so the
#: bar for "the index can stand in for the source" is higher than the bar for
#: "the index is worth mentioning."
STRICT_MIN_COVERAGE = 0.95

#: Seconds each of refresh/status may take at session start.
SESSION_REFRESH_TIMEOUT = 60


def nudge_text(sha: str, path: str, dirty: bool) -> str:
    """`path` is the file being read, or empty/`.` when the call named no single
    file (a repo-wide grep or glob): then there is no file outline to suggest."""
    outline = ", `file` with term `%s` for this file's outline" % path if path not in ("", ".") else ""
    lines = [
        "CDP indexes this repository at %s." % sha[:12],
        "MCP `cdp_query` (kind `trace` for an entry point's reading list, `symbol` for "
        "definition + callers%s) gives cited locations and relationships; CLI form: "
        "`cdp query <kind> <term>`. It is a map, not the logic: Read only the cited line "
        "ranges (offset/limit), not whole files. `cdp_help` lists every kind, flag and "
        "recipe." % outline,
        "Check `query coverage` (cdp_query kind `coverage`) before concluding something is absent.",
    ]
    if dirty:
        # Stress test, and the decision it forced: HEAD matches but files are
        # edited, so the index is stale in a way the HEAD check structurally
        # cannot see. Suppressing the nudge would throw away a still-useful
        # index over a one-line edit; firing it silently would misrepresent
        # how fresh the index is. It fires, qualified. Phase 2's ephemeral
        # snapshots (0.6) make this precise rather than caveated.
        lines.append(
            "Note: the working tree is dirty. The index describes the commit, not "
            "your uncommitted edits, so verify anything it says about a file you "
            "have changed."
        )
    return " ".join(lines)


# -------------------------------------------------------------- resolution


def target_path(tool_name: str, tool_input: Dict) -> Optional[str]:
    """The path a watched tool is about to touch, if it names one."""
    if not isinstance(tool_input, dict):
        return None
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    if tool_name == "Glob":
        pattern = tool_input.get("pattern")
        if isinstance(pattern, str) and pattern:
            return pattern
    return None


def find_state(start: Path) -> Optional[Tuple[Path, str, Path]]:
    """`(home, repo_id, repo folder)` of the innermost scanned repo containing
    `start`, or None. Never creates or migrates the store."""
    from .store import SqliteStore, has_scanned
    from .store import registry

    home = registry.cdp_home()
    if not has_scanned(home):
        return None
    current = start if start.is_dir() else start.parent
    candidates = registry.candidate_identities(current)
    if not candidates:
        return None
    backend = SqliteStore(home / "index.db", readonly=True, busy_timeout_ms=1500)
    try:
        scanned = set(backend.repo_ids())
    finally:
        backend.close()
    for folder, repo_id in candidates:
        if repo_id in scanned:
            return home, repo_id, folder
    return None


def has_snapshot(home: Path, repo_id: str) -> bool:
    """Whether `repo_id` has been scanned into the store at `home`."""
    from .store import SqliteStore, has_scanned

    if not has_scanned(home):
        return False
    backend = SqliteStore(Path(home) / "index.db", readonly=True, busy_timeout_ms=1500)
    try:
        return repo_id in backend.repo_ids()
    finally:
        backend.close()


def git_head(repo: Path) -> Optional[str]:
    try:
        proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


#: Marker files this module leaves in the OS temp dir, and how many/how old they
#: may get. A session that ran hours ago will not fire again, so age is the
#: right key; the count bound covers a burst of short sessions.
MARKER_PREFIXES = ("cdp-hook-", "cdp-gate-")
MARKER_MAX_AGE = 24 * 3600
MARKER_MAX_COUNT = 200


def prune_markers(directory: Optional[Path] = None, max_age: float = MARKER_MAX_AGE,
                  max_count: int = MARKER_MAX_COUNT) -> int:
    """Delete markers older than `max_age` seconds, then the oldest beyond
    `max_count`. Returns how many went. Never raises."""
    import time

    directory = directory or Path(tempfile.gettempdir())
    cutoff = time.time() - max_age
    live: List[Tuple[float, str]] = []
    removed = 0
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.name.startswith(MARKER_PREFIXES):
                    continue
                try:
                    mtime = entry.stat(follow_symlinks=False).st_mtime
                except OSError:
                    continue
                if mtime < cutoff:
                    try:
                        os.unlink(entry.path)
                        removed += 1
                    except OSError:
                        pass
                else:
                    live.append((mtime, entry.path))
        for _mtime, path in sorted(live)[:max(0, len(live) - max_count)]:
            try:
                os.unlink(path)
                removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return removed


def _touch_once(marker: Path) -> bool:
    """True the first time `marker` is created. A marker that cannot be created
    reads as already fired: nagging on every call is worse than one missed hint."""
    try:
        marker.touch(exist_ok=False)
    except OSError:
        return False
    prune_markers()
    return True


def claim_session(state: Path, session_id: str) -> bool:
    """True the first time this session sees a source read, false thereafter.

    A nudge repeated on every read is nagging, and a model learns to ignore a
    channel that is always noisy. The marker lives under the OS temp directory
    rather than in the store: state is the fold of a scan, and a hook writing into
    it would make the scan's output a function of how many times someone opened
    a file.
    """
    key = hashlib.sha256(("%s|%s" % (state.resolve(), session_id)).encode()).hexdigest()[:16]
    return _touch_once(Path(tempfile.gettempdir()) / ("cdp-hook-%s" % key))


# ------------------------------------------------------------------ decide


def _gate(event: Dict) -> Optional[Dict]:
    """Everything both the nudge and the strict-mode block need in common:
    a reachable, fresh, source-role read. Returns `None` for any of the four
    silent no-ops (no state, unreadable state, stale index, wrong role);
    otherwise a dict with `state`/`inventory`/`repo`/`indexed`/`rel`. Does
    **not** claim the session marker -- callers decide what firing means.
    """
    if event.get("tool_name") not in WATCHED:
        return None

    is_search = event.get("tool_name") == "Bash"
    cwd = Path(str(event.get("cwd") or os.getcwd()))
    if is_search:
        tool_input = event.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str) or not SEARCH_COMMAND.search(command):
            return None
        raw = None
    else:
        raw = target_path(str(event.get("tool_name")), event.get("tool_input") or {})
    anchor = Path(raw) if raw and Path(raw).is_absolute() else cwd / (raw or ".")

    found = find_state(anchor) or find_state(cwd)
    if found is None:
        return None  # no-op 1: nothing scanned contains this path
    home, repo_id, repo = found
    state = home / "work" / repo_id  # session marker key only; never read or created

    from . import snapshot as snapshot_mod
    from .store import SqliteStore
    from .util import CdpError

    head = git_head(repo)
    try:
        backend = SqliteStore(home / "index.db", readonly=True, busy_timeout_ms=1500)
        choice = snapshot_mod.select(backend, repo, repo_id)
        if choice.scan_needed or choice.behind:
            backend.close()
            return None  # no-op 2: the index does not describe this working tree
        inventory = backend.read_artifact("inventory")
        folded = backend.read_artifact("state", {})
        # An exact match on an uncommitted tree already includes its edits; otherwise the
        # snapshot is of a commit and the files differing from HEAD are newer than it.
        edited = [] if (choice.row or {}).get("ephemeral") else list(choice.dirty_files)
        backend.close()
    except (OSError, ValueError, CdpError):
        return None

    indexed = str(inventory.get("head") or "")
    if not indexed or indexed == "unpinned" or head is None or indexed != head:
        return None

    rel = _relative(anchor, repo)
    if rel is None:
        return None
    if not is_search and _role_of(inventory, rel) != NUDGE_ROLE:
        return None

    is_file = any(f.get("path") == rel for f in inventory.get("files") or [])
    return {
        "search": is_search, "file": rel if is_file else "",
        "state": state, "inventory": inventory, "repo": repo,
        "indexed": indexed, "rel": rel, "edited": edited, "coverage_fraction": folded.get(
            "coverage", {}).get("fraction", 0.0),
    }


def _marker(state: Path, session_id: str, tag: str) -> Path:
    key = hashlib.sha256(("%s|%s|%s" % (state.resolve(), session_id, tag)).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / ("cdp-gate-%s" % key)


def _claim(state: Path, session_id: str, tag: str) -> bool:
    """True the first time this session sees `tag`."""
    return _touch_once(_marker(state, session_id, tag))


#: The MCP tool the model asks the index with. The server is registered as `cdp`
#: (`mcp__cdp__cdp_query`), but a user may have named it anything, or it may come
#: through a plugin (`mcp__plugin_x_cdp__cdp_query`): match the tool, not the server.
_MCP_QUERY = re.compile(r"^(?:mcp__.+__)?cdp_query$")


def is_index_query(tool_name: object) -> bool:
    return isinstance(tool_name, str) and bool(_MCP_QUERY.match(tool_name))


def _asked_marker(session_id: str) -> Path:
    key = hashlib.sha256(("asked|%s" % session_id).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / ("cdp-gate-asked-%s" % key)


def note_index_asked(session_id: str) -> None:
    """The model has asked the index this session: the gate has nothing left to teach."""
    marker = _asked_marker(session_id)
    if not marker.exists():
        _touch_once(marker)


def index_was_asked(session_id: str) -> bool:
    return _asked_marker(session_id).exists()


#: A whole-file Read of a source file longer than this gets the file's outline first.
READ_MIN_LOC = 250


def gate_decide(event: Dict) -> Optional[Dict]:
    """Answer from the index instead of running the call, where it can.

    * A recursive grep or a find by name on an identifier the index knows
      exactly: denied, with the definitions and uses inline.
    * A whole-file Read of a long source file: denied once per file, with its
      member outline, so the retry can be the range it needs.

    Everything else runs: single-file greps, string and regex searches, unknown
    names, and the retry of anything denied. Each denial is once per session
    and subject, so an index that falls short never traps the model.
    """
    from . import hook_rules

    sid = str(event.get("session_id") or "no-session")
    if is_index_query(event.get("tool_name")):
        note_index_asked(sid)  # E1: the model asked the index; nothing left to deny
        return None
    if index_was_asked(sid):
        return None
    gated = _gate(event)
    if gated is None:
        return None
    tool = str(event.get("tool_name"))
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    repo, state = gated["repo"], gated["state"]
    commit = gated["indexed"][:12]

    if tool == "Read":
        if "offset" in tool_input or "limit" in tool_input:
            return None
        if gated["rel"] in gated["edited"]:
            return None  # edited since the indexed commit: its outline would be stale
        entry = next((f for f in gated["inventory"].get("files", []) if f.get("path") == gated["rel"]), {})
        if int(entry.get("loc") or 0) <= READ_MIN_LOC:
            return None
        shape = hook_rules.outline(repo, gated["rel"])
        if shape is None or not _claim(state, sid, "read:" + gated["rel"]):
            return None
        shown = shape["lines"][:hook_rules.MAX_OUTLINE_LINES]
        more = "\n  (+%d more members)" % (len(shape["lines"]) - len(shown)) if len(shape["lines"]) > len(shown) else ""
        return {"block": True, "message": (
            "Not read yet: %s has %d lines. CDP's outline of it (commit %s):\n  %s%s\n"
            "Read just the member you need with offset/limit. To read the whole file anyway, "
            "repeat this call." % (gated["rel"], shape["loc"], commit, "\n  ".join(shown), more))}

    if tool == "Bash":
        command = str(tool_input.get("command") or "")
        # D2: only a command that is nothing but a search can be replaced by an answer.
        searches = hook_rules.shell_searches(command) if hook_rules.is_pure_search(command) else []
    else:
        searches = hook_rules.tool_searches(tool, tool_input)
    if not searches:
        return None
    scopes = _search_scopes(tool, searches, gated, event)
    if scopes is None or _edited_in(scopes, gated):
        return None  # outside the repo or a non-source dir, or edited since the indexed commit
    # D1/D3: answer only when every term is answered; otherwise the call runs untouched
    # and does not spend the once-per-subject denial.
    subject = "|".join(sorted(t for s in searches for t in s["terms"]))
    if _marker(state, sid, "search:" + subject).exists():
        return None  # the retry of a denied call: no second lookup
    answer = hook_rules.search_answer(repo, searches)
    if answer is None or not _claim(state, sid, "search:" + subject):
        return None
    return {"block": True, "message": (
        "Not run: the CDP index (commit %s) already answers this search:\n%s\n"
        "Read the cited ranges for the code. If this is not what you needed, repeat the same "
        "call and it will run." % (commit, answer))}


def _search_scopes(tool: str, searches: List[Dict], gated: Dict, event: Dict) -> Optional[List[str]]:
    """The repo-relative places a search reads, or None when the index cannot stand in for it:
    a path outside the repo, or one that holds no source (`src/main/resources`, `/var/log`).
    Grep/Glob name theirs in `path`, which `_gate` already resolved to `gated["rel"]`."""
    if tool != "Bash":
        return [gated["rel"]]
    cwd = Path(str(event.get("cwd") or os.getcwd()))
    scopes: List[str] = []
    for search in searches:
        for operand in search.get("paths") or ["."]:
            path = Path(operand)
            rel = _relative(path if path.is_absolute() else cwd / path, gated["repo"])
            if rel is None or _role_of(gated["inventory"], rel) != NUDGE_ROLE:
                return None
            scopes.append(rel)
    return scopes


def _in_scope(path: str, rel: str) -> bool:
    if rel in (".", ""):
        return True
    if "*" in rel:
        return path.startswith(rel.split("*", 1)[0])
    return path == rel or path.startswith(rel.rstrip("/") + "/")


def _edited_in(scopes: List[str], gated: Dict) -> bool:
    """Whether a source file under any of `scopes` differs from the indexed commit."""
    roles = {f.get("path"): f.get("role") for f in gated["inventory"].get("files") or []}
    return any(roles.get(path, NUDGE_ROLE) == NUDGE_ROLE and any(_in_scope(path, rel) for rel in scopes)
               for path in gated["edited"])


def post_search(event: Dict) -> Optional[str]:
    """PostToolUse: a grep/find/Grep/Glob that found nothing, for a name the index
    knows. An empty grep is a `PostToolUse` with "No matches found", not a failure
    (verified live), so this is the moment to point at `cdp_query`. Once per subject
    per session; silent when the index is stale or knows nothing of the terms."""
    from . import hook_rules

    tool = str(event.get("tool_name"))
    if tool not in ("Bash", "Grep", "Glob") or is_index_query(tool):
        return None
    if not hook_rules.is_empty_result(tool, event.get("tool_response"), event.get("tool_input")):
        return None
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    searches = (hook_rules.shell_searches(str(tool_input.get("command") or ""), targeted=True)
                if tool == "Bash" else hook_rules.tool_searches(tool, tool_input, targeted=True))
    if not searches:
        return None
    gated = _gate(event)
    if gated is None:
        return None
    sid = str(event.get("session_id") or "no-session")
    subject = "|".join(sorted(t for s in searches for t in s["terms"]))
    if _marker(gated["state"], sid, "empty:" + subject).exists():
        return None
    hint = hook_rules.empty_search_hint(gated["repo"], searches)
    if not hint or not _claim(gated["state"], sid, "empty:" + subject):
        return None
    return ("That search found nothing in the working tree, but the CDP index (commit %s) knows: %s."
            % (gated["indexed"][:12], hint))


def decide(event: Dict) -> Optional[str]:
    """The nudge to emit, or None for a silent no-op. Never raises."""
    gated = _gate(event)
    if gated is None:
        return None
    if not claim_session(gated["state"], str(event.get("session_id") or "no-session")):
        return None
    return nudge_text(gated["indexed"], gated["file"], bool(gated["edited"]))


def strict_decide(event: Dict) -> Optional[Dict]:
    """Strict mode's one-shot decision: block, or degrade to the nudge.

    Returns `None` for a silent no-op (same four gates `decide` uses), or a
    dict `{"block": bool, "message": str}` -- `block` is only ever `True` when
    coverage clears `STRICT_MIN_COVERAGE` *and* the freshness gate above
    already held (`_gate` checked it before this function is reached).
    """
    gated = _gate(event)
    if gated is None:
        return None
    if not claim_session(gated["state"], str(event.get("session_id") or "no-session")):
        return None
    message = nudge_text(gated["indexed"], gated["file"], bool(gated["edited"]))
    if gated["coverage_fraction"] < STRICT_MIN_COVERAGE:
        return {"block": False, "message": message}
    block_message = (
        "Blocked: the index covers %.0f%% of this repository at %s and can "
        "answer this without reading source. %s If the index truly cannot "
        "answer, override this once and read the file directly." %
        (gated["coverage_fraction"] * 100, gated["indexed"][:12], message)
    )
    return {"block": True, "message": block_message}


def _relative(path: Path, repo: Path) -> Optional[str]:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _role_of(inventory: Dict, rel: str) -> Optional[str]:
    """The role of `rel`, or of the first tracked file under it.

    `Grep`/`Glob` name a directory or a pattern rather than a file, so an exact
    match alone would make the hook fire on `Read` and never on the two tools
    that cost the most.
    """
    files = inventory.get("files") or []
    if rel in (".", ""):
        return NUDGE_ROLE if any(f.get("role") == NUDGE_ROLE for f in files) else None
    prefix = rel.rstrip("/") + "/"
    globbed = rel.split("*", 1)[0].rstrip("/")
    if "*" in rel and not globbed:  # `**/Name*.java`: anywhere in the repo
        return NUDGE_ROLE if any(f.get("role") == NUDGE_ROLE for f in files) else None
    for entry in files:
        if entry.get("path") == rel:
            return entry.get("role")
    for entry in files:
        path = entry.get("path", "")
        if (path.startswith(prefix) or (globbed and path.startswith(globbed + "/"))) \
                and entry.get("role") == NUDGE_ROLE:
            return NUDGE_ROLE
    return None


# -------------------------------------------------------------------- main


def payload(message: str, block: bool = False) -> Dict:
    if block:
        # `permissionDecision`/`permissionDecisionReason` is the documented
        # PreToolUse contract for actually deciding the call, unlike the plain
        # nudge above -- unverified against a live harness in this environment
        # (no interactive session to block for real in this repo's own test
        # suite), so `strict_decide` never blocks unless `_gate` already
        # confirmed a fresh, high-coverage index, per this module's docstring.
        # No `systemMessage`: it made the harness show the user a "hook error"
        # next to a deliberate block, and the reason reaches the model anyway.
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": message,
            },
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message,
        },
        "systemMessage": message,
    }


def session_start(event: Dict) -> Optional[str]:
    """SessionStart: refresh the index (no model calls), return a short status.

    Silent (None) when the repo was never scanned. A failure after that point
    is reported in the message instead of swallowed: a hook that silently does
    nothing is indistinguishable from one that never ran.
    """
    cwd = Path(event.get("cwd") or os.getcwd())
    found = find_state(cwd)
    if found is None:
        return None
    # The folder the scan is registered under, not the launch directory: a
    # session started in a subfolder (`repo/sql-pool`) would otherwise resolve
    # to a different, never-scanned identity and fail.
    repo = found[2]
    run_py = Path(__file__).resolve().parent.parent / "run.py"
    base = [sys.executable, str(run_py)]
    failure = None
    try:
        proc = subprocess.run(base + ["refresh", "--repo", str(repo), "--quiet"],
                              capture_output=True, text=True, timeout=SESSION_REFRESH_TIMEOUT, check=False)
        if proc.returncode != 0:
            failure = _first_line(proc.stderr or proc.stdout) or "exit %d" % proc.returncode
    except Exception as exc:  # noqa: BLE001 -- reported, never raised
        failure = "%s: %s" % (type(exc).__name__, exc)
    try:
        proc = subprocess.run(base + ["status", "--repo", str(repo), "--json"],
                              capture_output=True, text=True,
                              timeout=SESSION_REFRESH_TIMEOUT, check=False)
        status = json.loads(proc.stdout)
    except Exception as exc:  # noqa: BLE001 -- reported, never raised
        reason = _first_line(proc.stderr) if "proc" in locals() and proc.stderr else type(exc).__name__
        return "CDP index exists but cannot answer for this tree (%s); run `cdp scan`%s." % (
            reason, "; refresh failed: %s" % failure if failure else "")
    indexed = (status.get("head") or "unpinned")[:12]
    git_head_sha = (status.get("git_head") or "")[:12]
    behind = int(status.get("behind") or 0)
    if failure and (behind or "clean working tree" not in failure):
        return ("CDP refresh failed: %s; index at %s is %d commit(s) behind HEAD %s. Answers carry "
                "`as_of`/`behind`; `cdp refresh` (or MCP `cdp_refresh`) shows the error in full."
                % (failure, indexed, behind, git_head_sha or "?"))
    fresh = status.get("freshness") or {}
    coverage = status.get("coverage") or {}
    if "model_reviewed_fraction" in coverage:  # `status` computes it: None when no model review
        cov, reviewed = coverage["model_reviewed_fraction"], coverage["model_reviewed_fraction"] is not None
    else:  # an older status: a leaf patch accepted for some scope shows as a `complete` node
        cov = coverage.get("fraction")
        reviewed = any(node.get("status") == "complete" for wave in status.get("waves") or []
                       for node in wave.get("nodes") or [])
    if isinstance(cov, (int, float)) and cov > 0 and reviewed:
        depth = "model-reviewed coverage %d%%" % round(cov * 100)
    else:
        from .util import NO_REVIEW_NOTE

        depth = ("deterministic index (%s live claims), 0.0%% %s"
                 % (fresh.get("live", "?"), NO_REVIEW_NOTE))
    dirty = status.get("dirty_files") or []
    caveat = ((" The index includes uncommitted changes in %d file(s)." if status.get("snapshot_uncommitted")
               else " Uncommitted changes in %d file(s) are not in the index.") % len(dirty)) if dirty else ""
    return ("CDP index for this repo is ready: commit %s, %s.%s The MCP tool `cdp_query` "
            "returns cited file:line locations, so code can be located without grep/find and "
            "only the cited line ranges need reading: kind `trace` (term = route or symbol) is "
            "the reading list for an entry point, `symbol` gives definition and callers, `table`, "
            "`config`, `routes`, `paths`, `file`, `module` cover the rest. `cdp_help` gives flags "
            "and recipes; kind `coverage` says what the index did not examine."
            % (indexed, depth, caveat))


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip().removeprefix("cdp: ")[:200]
    return ""


def prompt_submit(event: Dict) -> Optional[str]:
    """UserPromptSubmit: the one hook that runs before the model's first move.

    Once per session, and only for a repo with a scan. No refresh here (the
    SessionStart hook did that); just the instruction, so it arrives with the
    prompt instead of after the model has already started grepping.
    """
    cwd = Path(event.get("cwd") or os.getcwd())
    found = find_state(cwd)
    if found is None:
        return None
    home, repo_id, _repo = found
    if not claim_session(home / "work" / repo_id, str(event.get("session_id") or "no-session") + ":prompt"):
        return None
    # Facts, not commands: the hooks docs warn that imperative "system
    # instruction" phrasing in additionalContext can trip the model's
    # prompt-injection defenses, which would explain it being ignored.
    return ("This repo has a CDP index: the MCP tool `cdp_query` (kinds: trace, symbol, table, "
            "config, routes, paths, file, module) returns cited file:line locations for the whole "
            "call chain in one call, so grep/find/Read are only needed afterwards, on the cited "
            "line ranges. Start with kind `trace` (term = route or symbol) or `symbol`; "
            "`cdp_help` gives flags and recipes.")


#: Set to `1` by `scripts/cdp-claude-leaf.sh` (only `1` counts: `0` or empty is off) so a leaf session -- which must read its
#: scope's files freely -- is not gated or nudged by the hooks of the repo it reads.
LEAF_ENV = "CDP_LEAF_SESSION"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get(LEAF_ENV) == "1" and "--explain" not in argv:
        return 0
    if "--gate" in argv:
        try:
            event = json.loads(sys.stdin.read() or "{}")
            result = gate_decide(event if isinstance(event, dict) else {})
        except Exception:
            return 0
        if result:
            print(json.dumps(payload(result["message"], block=True)))
        return 0
    if "--post-search" in argv:
        try:
            event = json.loads(sys.stdin.read() or "{}")
            message = post_search(event if isinstance(event, dict) else {})
        except Exception:
            return 0
        if message:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                     "additionalContext": message}}))
        return 0
    if "--prompt-submit" in argv:
        try:
            event = json.loads(sys.stdin.read() or "{}")
            message = prompt_submit(event if isinstance(event, dict) else {})
        except Exception:
            return 0
        if message:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                     "additionalContext": message}}))
        return 0
    if "--session-start" in argv:
        try:
            event = json.loads(sys.stdin.read() or "{}")
            message = session_start(event if isinstance(event, dict) else {})
        except Exception:
            return 0
        if message:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                     "additionalContext": message},
                              "systemMessage": message}))
        return 0
    if "--explain" in argv:
        print(__doc__.strip())
        print()
        print("Sample nudge:\n  %s" % nudge_text("0" * 40, "src/Example.java", False))
        return 0
    strict = "--strict" in argv
    try:
        event = json.loads(sys.stdin.read() or "{}")
        event = event if isinstance(event, dict) else {}
        if strict:
            result = strict_decide(event)
            message = result["message"] if result else None
            block = bool(result and result["block"])
        else:
            message = decide(event)
            block = False
    except Exception:
        # Fails open. See the module docstring: this runs before every file read
        # in the session, and breaking that is far worse than missing a nudge.
        return 0
    if message:
        print(json.dumps(payload(message, block=block)))
    return 0


if __name__ == "__main__":
    if not __package__:
        # Run as `python3 .../cdp/hook.py` (how install registers it): relative
        # imports need the package, so re-enter through it.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from cdp.hook import main as _package_main
        raise SystemExit(_package_main())
    raise SystemExit(main())
