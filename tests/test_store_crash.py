"""Crash safety of the schema-12 object store (PLAN_DB_ARCH.md §6, gate 5).

A `cdp scan` runs in a real subprocess and is SIGKILLed by its own process at an exact point:
the driver below wraps one store method and, on its Nth call, sends itself SIGKILL (or pauses on
a file handshake, for the concurrency tests). No product code is changed and nothing is timed, so
every kill lands at the same place on every run.

After a kill the store must still answer from the previous complete snapshot only, `verify --full`
(which includes the dangling-reference check) must pass, and a rerun scan must succeed.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from helpers import SKILL_ROOT, have_git, make_repo

pytestmark = pytest.mark.skipif(not have_git(), reason="needs git")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "cdp", "GIT_AUTHOR_EMAIL": "cdp@example.invalid",
    "GIT_COMMITTER_NAME": "cdp", "GIT_COMMITTER_EMAIL": "cdp@example.invalid",
    "GIT_AUTHOR_DATE": "2025-01-02T00:00:00+00:00", "GIT_COMMITTER_DATE": "2025-01-02T00:00:00+00:00",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
}

# Runs `cdp.cli.main(argv)` with one store method wrapped. T4_POINT is `cls:method:before|after`
# (`obj` = ObjectStoreMixin, `sql` = SqliteStore); on call T4_NTH the action T4_ACTION fires:
# `kill` = SIGKILL self, `pause` = write T4_READY then wait for T4_GO to exist. With T4_MATCH set,
# only calls whose first argument contains that text count.
DRIVER = r'''
import os, signal, sys, time
from pathlib import Path
from cdp.store import objects, sqlite_backend
point = os.environ.get("T4_POINT")
if point:
    cls_name, meth, when = point.split(":")
    cls = {"obj": objects.ObjectStoreMixin, "sql": sqlite_backend.SqliteStore}[cls_name]
    nth, action, seen = int(os.environ.get("T4_NTH", "1")), os.environ.get("T4_ACTION", "kill"), [0]
    orig = getattr(cls, meth)
    def fire():
        seen[0] += 1
        if seen[0] != nth:
            return
        if action == "kill":
            os.kill(os.getpid(), signal.SIGKILL)
        Path(os.environ["T4_READY"]).write_text("ready")
        deadline = time.monotonic() + 30
        while not Path(os.environ["T4_GO"]).exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    match = os.environ.get("T4_MATCH")
    def wrapped(self, *a, **k):
        if match and not (a and match in str(a[0])):
            return orig(self, *a, **k)
        if when == "before":
            fire()
        out = orig(self, *a, **k)
        if when == "after":
            fire()
        return out
    setattr(cls, meth, wrapped)
from cdp.cli import main
sys.exit(main(sys.argv[1:]))
'''


def env_for(home: Path, **extra: str) -> Dict[str, str]:
    env = dict(os.environ)
    env.update({"CDP_HOME": str(home), "PYTHONPATH": str(SKILL_ROOT)})
    for k in ("T4_POINT", "T4_NTH", "T4_ACTION", "T4_READY", "T4_GO", "T4_MATCH"):
        env.pop(k, None)
    env.update(extra)
    return env


def cdp(home: Path, *argv: str, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", DRIVER] + list(argv), cwd=str(SKILL_ROOT),
                          env=env_for(home, **extra), capture_output=True, text=True, timeout=60)


def cdp_bg(home: Path, *argv: str, **extra: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", DRIVER] + list(argv), cwd=str(SKILL_ROOT),
                            env=env_for(home, **extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)


def wait_file(path: Path, proc: Optional[subprocess.Popen] = None, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if proc is not None and proc.poll() is not None:
            raise AssertionError("process exited (%s) before %s: %s" % (proc.returncode, path.name,
                                                                         proc.stderr.read()[-2000:]))
        assert time.monotonic() < deadline, "timed out waiting for %s" % path
        time.sleep(0.01)


def scan(home: Path, repo: Path, *flags: str, **extra: str) -> subprocess.CompletedProcess:
    return cdp(home, "scan", "--repo", str(repo), "--quiet", "--no-docs", *flags, **extra)


def ok(proc: subprocess.CompletedProcess) -> subprocess.CompletedProcess:
    assert proc.returncode == 0, "rc=%s\nstdout=%s\nstderr=%s" % (proc.returncode, proc.stdout[-2000:],
                                                                   proc.stderr[-2000:])
    return proc


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo)] + list(args), check=True, capture_output=True,
                          text=True, env=GIT_ENV).stdout.strip()


def new_commit(repo: Path, tag: str = "2") -> str:
    """Change one source file and commit it (pinned dates: the same sha on every run)."""
    src = sorted(p for p in repo.rglob("*.java") if ".git" not in p.parts)[0]
    src.write_text(src.read_text() + "\nclass Added%s { void added%s() {} }\n" % (tag, tag))
    git(repo, "add", "-A")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "change " + tag)
    return git(repo, "rev-parse", "HEAD")


def snapshot_rows(home: Path) -> List[Dict]:
    from cdp.store import SqliteStore

    s = SqliteStore(home / "index.db", readonly=True)
    try:
        return s.list_snapshots()
    finally:
        s.close()


def answers(home: Path, repo: Path) -> Dict:
    """Everything the snapshot `choose_snapshot` selects for `repo` answers from: its commit, every
    artifact, its patch log, its reports, plus two CLI answers."""
    from cdp import snapshot as snapshot_mod
    from cdp.store import SqliteStore, registry

    s = SqliteStore(home / "index.db", readonly=True)
    try:
        choice = snapshot_mod.select(s, repo, registry.repo_identity(repo))
        if choice.row is None:
            return {"selected": None}
        sid = s.snapshot_id()
        names = [n for (n,) in s._rows("SELECT name FROM snapshot_doc WHERE snapshot_id=? ORDER BY name", (sid,))]
        reports = s._rows("SELECT name, payload FROM snapshot_report WHERE snapshot_id=? ORDER BY name", (sid,))
        out = {"selected": choice.row["commit_sha"], "artifacts": {n: s.read_artifact(n) for n in names},
               "patches": s.load_patches(), "reports": [tuple(r) for r in reports]}
    finally:
        s.close()
    # `as_of` reports freshness against the working tree (HEAD moved on), not the snapshot's answer.
    out["stats"] = _answer(ok(cdp(home, "query", "stats", "--repo", str(repo), "--json")))
    found = cdp(home, "query", "search", "Added", "--repo", str(repo), "--json", "--include-tests")
    out["search"] = (found.returncode, _answer(found))       # rc 1 = not found, still an answer
    return out


def _answer(proc: subprocess.CompletedProcess) -> Dict:
    data = json.loads(proc.stdout)
    data.pop("as_of", None)
    return data


def verify_full(home: Path, repo: Path) -> subprocess.CompletedProcess:
    return cdp(home, "verify", "--full", "--repo", str(repo))


@pytest.fixture
def world(tmp_path):
    repo = make_repo(tmp_path)
    return tmp_path / "home", repo


# Kill points, in write order: before any object is written; between object batches (the second
# segment write has committed); after every object, before the manifest transaction; inside the
# manifest transaction after `complete=1` is set but before COMMIT.
KILL_POINTS = [
    pytest.param("obj:put_blobs:before", 1, id="before-objects"),
    pytest.param("obj:_put_segs:after", 2, id="mid-objects"),
    pytest.param("obj:_commit_build:before", 1, id="before-manifest-txn"),
    pytest.param("sql:_finish_snapshot:after", 1, id="inside-manifest-txn"),
]


@pytest.mark.parametrize("point,nth", KILL_POINTS)
def test_kill9_new_commit_scan_keeps_previous_snapshot(world, point, nth):
    home, repo = world
    ok(scan(home, repo))
    first = git(repo, "rev-parse", "HEAD")
    before = answers(home, repo)
    assert before["selected"] == first

    second = new_commit(repo)
    killed = scan(home, repo, T4_POINT=point, T4_NTH=str(nth))
    assert killed.returncode == -signal.SIGKILL, killed.stderr[-2000:]

    rows = {r["commit_sha"]: r for r in snapshot_rows(home)}
    assert rows[first]["complete"]
    assert second not in rows or not rows[second]["complete"], "a killed scan's snapshot became visible"
    after = answers(home, repo)
    assert after["selected"] == first                     # nearest clean ancestor, not the torn build
    assert after == before
    # `verify` re-anchors claims against the working tree, so it is run on the snapshot's own commit
    # (it fails the same way with no kill at all once HEAD has moved past the snapshot).
    git(repo, "checkout", "-q", first)
    ok(verify_full(home, repo))
    git(repo, "checkout", "-q", "main")

    ok(scan(home, repo))
    assert answers(home, repo)["selected"] == second
    assert {r["commit_sha"]: r["complete"] for r in snapshot_rows(home)}[second]
    ok(verify_full(home, repo))


def test_kill9_first_scan_leaves_nothing_visible(world):
    home, repo = world
    killed = scan(home, repo, T4_POINT="obj:_commit_build:before")
    assert killed.returncode == -signal.SIGKILL
    assert not any(r["complete"] for r in snapshot_rows(home))
    assert answers(home, repo) == {"selected": None}
    q = cdp(home, "query", "stats", "--repo", str(repo))
    assert q.returncode != 0 and "scan" in q.stderr
    ok(scan(home, repo))
    ok(verify_full(home, repo))


def test_kill9_same_commit_rescan_mid_objects_keeps_answers(world):
    """A rescan of the commit it already holds, with different budgets (so the new build differs),
    killed between object batches: the old answers are untouched."""
    home, repo = world
    ok(scan(home, repo))
    before = answers(home, repo)
    killed = scan(home, repo, "--max-leaf-files", "1", T4_POINT="obj:_put_segs:after", T4_NTH="2")
    assert killed.returncode == -signal.SIGKILL
    assert answers(home, repo) == before
    ok(verify_full(home, repo))
    ok(scan(home, repo, "--max-leaf-files", "1"))
    assert answers(home, repo)["artifacts"]["partition"] != before["artifacts"]["partition"]
    ok(verify_full(home, repo))


@pytest.mark.parametrize("point", [
    pytest.param("obj:_commit_build:before", id="before-manifest-txn"),
    pytest.param("sql:_finish_snapshot:after", id="inside-manifest-txn"),
])
def test_kill9_same_commit_rescan_late_keeps_patch_log(world, point):
    home, repo = world
    ok(scan(home, repo))
    before = answers(home, repo)
    killed = scan(home, repo, "--max-leaf-files", "1", T4_POINT=point)
    assert killed.returncode == -signal.SIGKILL
    ok(verify_full(home, repo))      # today: "fold_hash mismatch: the log has changed since state.json"
    after = answers(home, repo)
    assert after["artifacts"] == before["artifacts"]          # the manifest itself is untouched
    assert (after["patches"], after["reports"]) == (before["patches"], before["reports"])


def test_gc_after_killed_scan_keeps_last_complete_snapshot(world):
    home, repo = world
    ok(scan(home, repo))
    first = git(repo, "rev-parse", "HEAD")
    new_commit(repo)
    assert scan(home, repo, T4_POINT="obj:_commit_build:before").returncode == -signal.SIGKILL
    ok(cdp(home, "gc", "--repo", str(repo)))
    assert first in {r["commit_sha"] for r in snapshot_rows(home) if r["complete"]}
    ok(cdp(home, "query", "stats", "--repo", str(repo)))
