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

Through Phase 1, condition 1 was `--in-repo` only: CDP writes state to
`./.cdp` *outside* the analysed repository by deliberate design (`cli.py:14-17`:
"a tool that leaves a directory behind in someone else's checkout has made a
decision that was not its to make"), and a directory walk from a file being
read could never reach a `.cdp/` outside the repo. `PHASE/phase_2_plan.md`
M2.6's store registry (`store.registry`) dissolves this: `find_state` walks up
for an in-repo `.cdp/` first, and failing that, resolves the repo's identity
and looks it up in the registry that a default-location `scan` populated.

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

**Output shape, and what is verified about it.** The harness documents that for
`PreToolUse` plain stdout goes to the debug log and is *not* shown to the model,
so structured JSON is the only route; that `additionalContext` is among the
fields honoured when JSON validates; and that exit 0 with no `permissionDecision`
reports no decision, leaving the call to the normal permission flow — which is
exactly what a nudge should do. What the published reference does **not** state
verbatim is whether `additionalContext` is accepted for `PreToolUse`
specifically. So the payload also carries `systemMessage`, a universal field, and
carries no `permissionDecision` at all. If `additionalContext` turns out to be
rejected the result is a non-blocking notice, never a blocked read.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

#: Tools worth intercepting. Everything else is not a source read.
WATCHED = ("Read", "Grep", "Glob")

#: The only role that gets a nudge. Editing a README, a CI file or a fixture is
#: not a question the index can answer better.
NUDGE_ROLE = "source"

STATE_DIRNAME = ".cdp"

#: Below this, a block would deny the model the source *and* leave the index
#: unable to answer (`RESEARCH_GRAPHIFY.md §7.8`) -- degrade to a nudge instead.
#: Deliberately high: blocking is a one-shot, session-shaping event, so the
#: bar for "the index can stand in for the source" is higher than the bar for
#: "the index is worth mentioning."
STRICT_MIN_COVERAGE = 0.95


def nudge_text(sha: str, path: str, dirty: bool) -> str:
    lines = [
        "`.cdp/` indexes this repository at %s." % sha[:12],
        "`cdp query symbol <name>` and `cdp query file %s` return the same facts "
        "with file:line citations at a fraction of the cost, and "
        "`cdp query trace <entrypoint>` returns the whole reading list for a "
        "question. If you still need the source, Read only the cited lines." % path,
        "Check `cdp query coverage` before concluding something is absent.",
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


def find_state(start: Path) -> Optional[Path]:
    """Walk up from `start` looking for an in-repo `.cdp/`; failing that,
    resolve the enclosing repo's identity and consult the registry.

    Before M2.6 (`PHASE/phase_2_plan.md` 2.3) this was in-repo only: CDP's
    default state location is *outside* the repo, so a directory walk from a
    file being read could never reach it, and `cdp install --hook` refused
    outside `--in-repo` rather than installing a hook that would silently
    never fire. The registry (`store.registry`, keyed by repo identity, not
    path) dissolves that: `scan`'s default run registers where it wrote state,
    and this looks it up the same way.
    """
    from .store import has_scanned
    from .store import registry

    current = start if start.is_dir() else start.parent
    for candidate in [current] + list(current.parents):
        state = candidate / STATE_DIRNAME
        if has_scanned(state):
            return state

    for candidate in [current] + list(current.parents):
        if (candidate / ".git").exists():
            registered = registry.lookup(registry.repo_identity(candidate))
            if registered is not None and has_scanned(registered):
                return registered
            break
    return None


def git_head(repo: Path) -> Optional[str]:
    try:
        proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def is_dirty(repo: Path) -> bool:
    """Tracked modifications only — `--untracked-files=no`.

    The inventory is built from `git ls-files`, so an untracked file is not in
    the index and cannot make it stale. Counting untracked files would make the
    qualifier fire permanently after `cdp scan --in-repo`, which writes an
    untracked `.gitignore` entry of its own: a warning that is always on is a
    warning nobody reads.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def claim_session(state: Path, session_id: str) -> bool:
    """True the first time this session sees a source read, false thereafter.

    A nudge repeated on every read is nagging, and a model learns to ignore a
    channel that is always noisy. The marker lives under the OS temp directory
    rather than in `.cdp/`: state is the fold of a scan, and a hook writing into
    it would make the scan's output a function of how many times someone opened
    a file.
    """
    key = hashlib.sha256(("%s|%s" % (state.resolve(), session_id)).encode()).hexdigest()[:16]
    marker = Path(tempfile.gettempdir()) / ("cdp-hook-%s" % key)
    try:
        marker.touch(exist_ok=False)
        return True
    except FileExistsError:
        return False
    except OSError:
        # Cannot tell whether it already fired. Say nothing rather than risk
        # nagging on every read.
        return False


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

    raw = target_path(str(event.get("tool_name")), event.get("tool_input") or {})
    cwd = Path(str(event.get("cwd") or os.getcwd()))
    anchor = Path(raw) if raw and Path(raw).is_absolute() else cwd / (raw or ".")

    state = find_state(anchor) or find_state(cwd)
    if state is None:
        return None  # no-op 1 and 3: no `.cdp/` reachable from here

    from .store import SqliteStore
    from .util import CdpError

    try:
        # `find_state` already confirmed `has_scanned(state)`, i.e. `index.db`
        # exists -- opening it here never creates it as a side effect.
        backend = SqliteStore(state / "index.db")
        inventory = backend.read_artifact("inventory")
        # `state.parent` is the repo only under the in-repo layout
        # (`<repo>/.cdp`); once state can live anywhere (M2.6's registry), the
        # manifest's own `repo` field is the only reliable source.
        manifest_repo = backend.read_artifact("manifest", {}).get("repo")
        repo = Path(manifest_repo) if manifest_repo else state.parent
        folded = backend.read_artifact("state", {})
        backend.close()
    except (OSError, ValueError, CdpError):
        return None

    indexed = str(inventory.get("head") or "")
    head = git_head(repo)
    if not indexed or indexed == "unpinned" or head is None or indexed != head:
        return None  # no-op 2: the index does not describe this working tree

    rel = _relative(anchor, repo)
    if rel is None:
        return None
    if _role_of(inventory, rel) != NUDGE_ROLE:
        return None

    return {
        "state": state, "inventory": inventory, "repo": repo,
        "indexed": indexed, "rel": rel, "coverage_fraction": folded.get(
            "coverage", {}).get("fraction", 0.0),
    }


def decide(event: Dict) -> Optional[str]:
    """The nudge to emit, or None for a silent no-op. Never raises."""
    gated = _gate(event)
    if gated is None:
        return None
    if not claim_session(gated["state"], str(event.get("session_id") or "no-session")):
        return None
    return nudge_text(gated["indexed"], gated["rel"], is_dirty(gated["repo"]))


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
    message = nudge_text(gated["indexed"], gated["rel"], is_dirty(gated["repo"]))
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
    prefix = rel.rstrip("/") + "/"
    globbed = rel.split("*", 1)[0].rstrip("/")
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
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": message,
            },
            "systemMessage": message,
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message,
        },
        "systemMessage": message,
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
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
    raise SystemExit(main())
