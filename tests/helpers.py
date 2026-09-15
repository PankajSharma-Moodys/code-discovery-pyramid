"""Test scaffolding.

The fixture is checked in as plain files and turned into a real git repository
per test run. That is deliberate: §5.1 makes `git ls-files` the inventory source,
so a fixture that was never committed would exercise only the walk fallback and
leave the primary path untested. Where git is unavailable the tests still run
against the fallback and say so, rather than being skipped silently.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minirepo"

from cdp.dataflow import build_dataflow  # noqa: E402
from cdp.derive import derive_claims  # noqa: E402
from cdp.extract import run_extract  # noqa: E402
from cdp.graph import build_graph  # noqa: E402
from cdp.inventory import build_inventory  # noqa: E402
from cdp.partition import partition  # noqa: E402
from cdp.resolve import build_xref  # noqa: E402
from cdp.schedule import build_schedule  # noqa: E402


def have_git() -> bool:
    return shutil.which("git") is not None


def make_repo(tmp: Path) -> Path:
    """Copy the fixture into `tmp` and commit it, if git is available."""
    repo = Path(tmp) / "minirepo"
    shutil.copytree(FIXTURE, repo)
    if not have_git():
        return repo
    # Author and committer dates are pinned alongside the identities so that the
    # fixture commits to the *same SHA* on every run. Without this the fixture
    # has a fresh SHA per run, which leaks into `state.json`'s `fold_hash` (a
    # digest over patch content that carries the commit) and makes a golden
    # baseline for the fixture unusable: blessed once, different immediately.
    env = {
        "GIT_AUTHOR_NAME": "cdp", "GIT_AUTHOR_EMAIL": "cdp@example.invalid",
        "GIT_COMMITTER_NAME": "cdp", "GIT_COMMITTER_EMAIL": "cdp@example.invalid",
        "GIT_AUTHOR_DATE": "2025-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2025-01-01T00:00:00+00:00",
        "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp),
    }
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(["git", "-C", str(repo)] + args, check=True,
                       capture_output=True, env=env)
    return repo


class Pipeline:
    """Every deterministic phase, run once, for tests to assert against."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.inventory = build_inventory(repo)
        self.extraction = run_extract(repo, self.inventory)
        self.graph = build_graph(self.inventory, self.extraction)
        self.partition = partition(self.inventory)
        self.schedule = build_schedule(self.partition, self.graph)
        self.xref = build_xref(self.inventory, self.extraction, self.graph)
        self.dataflow = build_dataflow(self.extraction, self.xref, self.graph)
        self.claims = derive_claims(
            repo, self.inventory, self.extraction, self.graph,
            self.xref, self.partition, self.dataflow,
        )

    def defines(self, fqn: str):
        return [d for d in self.extraction["defines"] if d["fqn"] == fqn]

    def edges(self, channel: Optional[str] = None, target: Optional[str] = None):
        rows = self.extraction["io_edges"]
        if channel:
            rows = [r for r in rows if r["channel"] == channel]
        if target:
            rows = [r for r in rows if r["target"] == target]
        return rows

    def claims_of(self, kind: str):
        return [c for c in self.claims if c["kind"] == kind]


class MiniRepoTest(unittest.TestCase):
    """Base class that builds the fixture repo once per class."""

    tmp: Optional[tempfile.TemporaryDirectory] = None
    pipeline: Optional[Pipeline] = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls.tmp.name))
        cls.pipeline = Pipeline(cls.repo)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.tmp:
            cls.tmp.cleanup()
