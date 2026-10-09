"""Determinism, golden and bundled-test checks."""

from __future__ import annotations

import re
import sys

from . import golden as golden_mod, query as query_mod
from .session import Paths, open_store
from .store import ARTIFACTS, REPORTS
from .util import CdpError, SKILL_ROOT
from contextlib import contextmanager as contextlib_contextmanager
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


#: Floor on the bundled suite's size. `selftest` fails below it rather than
# reporting a green run over nothing. Raise it deliberately when tests are
# added; never lower it to make a red build green.
MIN_TESTS = 180


def state_files(root: Path) -> Dict[str, Path]:
    """Raw filesystem outputs under the state dir -- `docs/`, `prompts/`, and
    (for `check_determinism`'s test stubs, which write directly rather than
    through a store) anything else. Excludes `index.db` and its WAL files: two independent
    writes of identical content are not guaranteed byte-identical at the
    SQLite file level (page allocation, not just logical data), so its
    content is compared separately, through the store API (`store_snapshot`).
    """
    return {
        str(p.relative_to(root)): p
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith("index.db")
    }


def store_snapshot(repo: Path, root: Path) -> Dict[str, str]:
    """`root`'s store content, canonically serialised through the store API
    -- comparable across two independently-written stores holding identical
    content, unlike the file's own bytes (see `state_files`). Resolved via
    `open_store` (`repo`'s `.cdp.toml`, same as the scan that wrote `root`
    used), not a hardcoded `SqliteStore` -- otherwise this would silently
    read (or create) the wrong backend for any repo configured to use `file`
    or `postgres`. `{}` vs `{}` (no differences) when nothing was scanned at
    all, e.g. a `check_determinism` test stub that writes raw files
    directly."""
    backend = open_store(Paths(repo=repo, state=root))
    try:
        if not backend.exists():
            return {}
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


#: The one state file allowed to differ between two scans of one commit, and
# the one field in it allowed to do so. `cmd_scan` states this contract in
# `manifest.json`'s own `note`; until now nothing enforced it.
VOLATILE_FILE = "manifest.json"


VOLATILE_FIELDS = ("generated_at",)


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

    runner = scan or scan_into
    problems: List[str] = []
    with tempfile.TemporaryDirectory(prefix="cdp-determinism-") as tmp:
        a, b = Path(tmp) / "a", Path(tmp) / "b"
        runner(repo, a)
        runner(repo, b)

        files_a, files_b = state_files(a), state_files(b)
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
                    % (rel, first_difference(left, right))
                )
                continue
            problems.extend(volatile_diff(rel, left, right))

        store_a, store_b = store_snapshot(repo, a), store_snapshot(repo, b)
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
                    % (rel, first_difference(left, right))
                )
                continue
            problems.extend(volatile_diff(rel, left, right))
    return problems


MISSING = object()


def volatile_diff(rel: str, left: bytes, right: bytes) -> List[str]:
    """`manifest.json` may differ, but only in the fields declared volatile."""
    import json

    try:
        da, db = json.loads(left), json.loads(right)
    except ValueError as exc:
        return ["%s: not valid JSON (%s)" % (rel, exc)]
    changed = sorted(
        k for k in set(da) | set(db) if da.get(k, MISSING) != db.get(k, MISSING)
    )
    unexpected = [k for k in changed if k not in VOLATILE_FIELDS]
    if unexpected:
        return [
            "%s: differs in %s, which is not declared volatile (only %s may differ)"
            % (rel, ", ".join(unexpected), ", ".join(VOLATILE_FIELDS))
        ]
    return []


def first_difference(left: bytes, right: bytes) -> str:
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


def scan_into(repo: Path, state: Path) -> None:
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
        env=deterministic_env(),
    )
    if proc.returncode != 0:
        raise CdpError("scan failed on %s:\n%s" % (repo, proc.stderr.strip()))


def deterministic_env() -> Dict[str, str]:
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


GOLDEN_ROOT = SKILL_ROOT / "tests" / "golden"


def golden_terms(store) -> Dict[str, Optional[str]]:
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
        scan_into(repo, state)

        # Read back through the store API (D3, `PHASE/FINDINGS.md`) via
        # `open_store` -- not a hardcoded `SqliteStore`, and not a raw
        # filesystem walk: golden capture must resolve the same backend the
        # scan above actually used (`repo`'s `.cdp.toml`), or this would
        # silently read the wrong store the moment a repo configures `file`
        # or `postgres`. `golden_mod.canonical` re-serialises every artifact
        # the same way regardless of backend, so capture is a function of
        # content, not of the storage format.
        backend = open_store(Paths(repo=repo, state=state))
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
        run_cli(["docs", "--repo", str(repo), "--state-dir", str(state),
                  "--out", str(docs_dir)])
        for path in sorted(docs_dir.rglob("*")):
            if path.is_file():
                artifacts["docs/%s" % path.relative_to(docs_dir).as_posix()] = (
                    path.read_text(encoding="utf-8", errors="replace")
                )

        store = query_mod.Store(state)
        terms = golden_terms(store)
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
            artifacts["query/%s.json" % kind] = run_cli(argv)
        store.close()
    return artifacts, head


def run_cli(argv: List[str]) -> str:
    """Invoke a CDP command and capture its stdout."""
    import contextlib
    import io

    from .cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    if code:
        raise CdpError("`cdp %s` exited %d" % (" ".join(argv[:2]), code))
    return buf.getvalue()


def git(repo: Path, *args: str) -> Optional[str]:
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

    if not (repo / ".git").exists() or git(repo, "rev-parse", "HEAD") is None:
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


RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)


def tests_ran(report: str) -> Optional[int]:
    """Extract the test count from a unittest report, or None if absent."""
    matches = RAN_RE.findall(report or "")
    return int(matches[-1]) if matches else None
