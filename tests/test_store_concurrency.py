"""Concurrency of the schema-12 object store (PLAN_DB_ARCH.md §6-7, gate 4).

Real `cdp` subprocesses share one CDP_HOME. Overlap is forced, not timed: the driver in
`test_store_crash.py` pauses a process at an exact store call (a READY/GO file handshake) while
the other process runs, so each interleaving is the same on every run.
"""

from __future__ import annotations

import signal
import time
from pathlib import Path

import pytest

from helpers import have_git
from test_store_crash import (answers, cdp, cdp_bg, git, make_repo, new_commit, ok, scan,
                              snapshot_rows, verify_full, wait_file)

pytestmark = pytest.mark.skipif(not have_git(), reason="needs git")


def _repo_b(tmp: Path) -> Path:
    """A second repo with its own identity (a different fixture, so no shared root commit)."""
    return make_repo(tmp / "b", "pyrepo")


def _pause(tmp: Path, point: str, nth: int = 1, match: str = "") -> dict:
    ready, go = tmp / ("ready-%d" % len(list(tmp.glob("ready-*")))), tmp / "go"
    env = {"T4_POINT": point, "T4_NTH": str(nth), "T4_ACTION": "pause", "T4_READY": str(ready), "T4_GO": str(go)}
    if match:
        env["T4_MATCH"] = match
    return env


def _finish(proc, timeout: float = 30.0):
    out, err = proc.communicate(timeout=timeout)
    assert proc.returncode == 0, "rc=%s\n%s\n%s" % (proc.returncode, out[-1500:], err[-1500:])
    return out


def _still_waiting(proc, seconds: float = 1.0) -> bool:
    """A scan of these fixtures takes ~0.6 s; one still running after `seconds` is blocked."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        time.sleep(0.05)
    return True


@pytest.fixture
def two_repos(tmp_path):
    """Repo A with a superseded snapshot (gc drops it and its objects die); repo B unscanned."""
    home = tmp_path / "home"
    a = make_repo(tmp_path / "a")
    ok(scan(home, a))
    new_commit(a)
    ok(scan(home, a))
    return home, a, _repo_b(tmp_path), tmp_path


def _check_b(home: Path, b: Path) -> None:
    sha = git(b, "rev-parse", "HEAD")
    assert {r["commit_sha"]: r["complete"] for r in snapshot_rows(home)}[sha]
    got = answers(home, b)
    assert got["selected"] == sha and got["artifacts"]["inventory"]
    ok(verify_full(home, b))


def test_gc_of_a_defers_sweep_while_scan_of_b_writes_objects(two_repos):
    """B is paused holding the objects lock shared, with objects written that no manifest cites yet:
    a sweep now would free them. gc of A must defer its sweep; both stores stay whole."""
    home, a, b, tmp = two_repos
    env = _pause(tmp, "obj:_put_segs:after")
    proc = cdp_bg(home, "scan", "--repo", str(b), "--quiet", "--no-docs", **env)
    wait_file(Path(env["T4_READY"]), proc)

    gc = ok(cdp(home, "gc", "--repo", str(a)))
    assert "dropping 1" in gc.stdout and "sweep     deferred" in gc.stdout, gc.stdout
    Path(env["T4_GO"]).write_text("go")
    _finish(proc)
    _check_b(home, b)
    ok(verify_full(home, a))

    gc = ok(cdp(home, "gc", "--repo", str(a)))      # nothing writing: now the sweep runs
    assert "sweep     freed" in gc.stdout, gc.stdout
    _check_b(home, b)
    ok(verify_full(home, a))


def test_scan_of_b_waits_for_running_sweep_of_a(two_repos):
    """The other order: gc of A is paused inside its sweep (objects lock held exclusive, mark not
    yet taken). B's scan must block before writing any object, then complete after the sweep."""
    home, a, b, tmp = two_repos
    env = _pause(tmp, "obj:_q:after", match="live_doc")
    gc = cdp_bg(home, "gc", "--repo", str(a), **env)
    wait_file(Path(env["T4_READY"]), gc)

    proc = cdp_bg(home, "scan", "--repo", str(b), "--quiet", "--no-docs")
    assert _still_waiting(proc), "scan of B wrote objects while a sweep held the objects lock"
    Path(env["T4_GO"]).write_text("go")
    assert "sweep     freed" in _finish(gc)
    _finish(proc)
    _check_b(home, b)
    ok(verify_full(home, a))


def test_two_scans_of_one_repo_serialise(tmp_path):
    """Scan 1 is paused just before its manifest transaction (repo lock held); scan 2 of the same
    repo waits on the repo lock, then rebuilds the same commit. One complete snapshot, verify ok,
    answers equal a single clean scan's."""
    home = tmp_path / "home"
    repo = make_repo(tmp_path)
    ok(scan(home, repo))
    expected = answers(home, repo)

    env = _pause(tmp_path, "obj:_commit_build:before")
    first = cdp_bg(home, "scan", "--repo", str(repo), "--quiet", "--no-docs", **env)
    wait_file(Path(env["T4_READY"]), first)
    second = cdp_bg(home, "scan", "--repo", str(repo), "--quiet", "--no-docs")
    assert _still_waiting(second), "second scan of the same repo did not wait for the first"
    Path(env["T4_GO"]).write_text("go")
    _finish(first)
    _finish(second)

    rows = [r for r in snapshot_rows(home) if r["commit_sha"] == git(repo, "rev-parse", "HEAD")]
    assert len(rows) == 1 and rows[0]["complete"]
    got = answers(home, repo)
    assert got["artifacts"].pop("manifest")["run_id"] == expected["artifacts"].pop("manifest")["run_id"]
    assert got == expected
    ok(verify_full(home, repo))


def test_waiting_scan_proceeds_after_holder_is_killed(tmp_path):
    """Scan 1 holds the repo lock with a half-built new-commit snapshot and is SIGKILLed; the
    waiting scan 2 gets the lock (flock dies with its process) and completes the snapshot."""
    home = tmp_path / "home"
    repo = make_repo(tmp_path)
    ok(scan(home, repo))
    new_commit(repo)

    env = _pause(tmp_path, "obj:_put_segs:after", nth=2)
    first = cdp_bg(home, "scan", "--repo", str(repo), "--quiet", "--no-docs", **env)
    wait_file(Path(env["T4_READY"]), first)
    second = cdp_bg(home, "scan", "--repo", str(repo), "--quiet", "--no-docs")
    assert _still_waiting(second)
    first.send_signal(signal.SIGKILL)
    first.communicate(timeout=10)
    assert first.returncode == -signal.SIGKILL
    _finish(second)
    head = git(repo, "rev-parse", "HEAD")
    assert {r["commit_sha"]: r["complete"] for r in snapshot_rows(home)}[head]
    assert answers(home, repo)["selected"] == head
    ok(verify_full(home, repo))


# ------------------------------------------------------------------ MCP staleness


@pytest.fixture
def mcp_home(tmp_path, monkeypatch):
    from mcp_server import tools

    home = tmp_path / "home"
    monkeypatch.setenv("CDP_HOME", str(home))
    before = set(tools._OPEN)
    yield home, tools
    for key in set(tools._OPEN) - before:
        tools._OPEN.pop(key)[0].backend.close()


def _strip(answer: dict) -> dict:
    answer = dict(answer)
    answer.pop("as_of", None)
    return answer


def _uncached(tools, repo: Path, kind: str, term=None, **kw) -> dict:
    """The same question from a fresh store, as a newly started server would answer it."""
    saved = dict(tools._OPEN)
    tools._OPEN.clear()
    try:
        return tools.cdp_query(str(repo), kind, term, **kw)
    finally:
        for key, (store, _) in tools._OPEN.items():
            store.backend.close()
        tools._OPEN.clear()
        tools._OPEN.update(saved)


QUESTIONS = [("stats", None, {}), ("coverage", None, {}),
             ("search", "Added", {"include_tests": True}), ("module", "core", {})]


def _ask_all(tools, repo: Path, cached: bool) -> list:
    ask = tools.cdp_query if cached else (lambda *a, **k: _uncached(tools, *a, **k))
    return [_strip(ask(str(repo), kind, term, **kw)) for kind, term, kw in QUESTIONS]


def test_mcp_cached_store_sees_new_commit_scanned_by_another_process(mcp_home):
    home, tools = mcp_home
    repo = make_repo(home.parent / "r")
    ok(scan(home, repo))
    first = _ask_all(tools, repo, cached=True)
    assert len(tools._OPEN) >= 1                    # the server now holds a cached store

    new_commit(repo)
    ok(scan(home, repo))                            # another process
    now = _ask_all(tools, repo, cached=True)
    assert now == _ask_all(tools, repo, cached=False)
    assert now != first
    assert now[2]["count"] > 0                      # the new commit's class is found


def test_mcp_cached_store_sees_same_commit_rescan_by_another_process(mcp_home):
    """Same snapshot id, recommitted manifest: only `touch_seq`/docs change in the fingerprint."""
    home, tools = mcp_home
    repo = make_repo(home.parent / "r")
    ok(scan(home, repo))
    first = _ask_all(tools, repo, cached=True)
    ok(scan(home, repo, "--max-leaf-files", "1"))    # another process, same commit
    now = _ask_all(tools, repo, cached=True)
    assert now == _ask_all(tools, repo, cached=False)
    assert now != first


def test_mcp_cached_store_ignores_killed_scan(mcp_home):
    """A scan killed inside its manifest transaction must not disturb the cached answers."""
    home, tools = mcp_home
    repo = make_repo(home.parent / "r")
    ok(scan(home, repo))
    first = _ask_all(tools, repo, cached=True)
    new_commit(repo)
    killed = scan(home, repo, T4_POINT="sql:_finish_snapshot:after")
    assert killed.returncode == -signal.SIGKILL
    git(repo, "checkout", "-q", "HEAD~1")            # answer for the commit the store holds
    assert _ask_all(tools, repo, cached=True) == first
