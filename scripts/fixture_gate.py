#!/usr/bin/env python3
"""Run a Phase 0 gate against the `minirepo` fixture.

The fixture is checked in as plain files and only becomes a git repository when
`tests/helpers.make_repo` copies and commits it (see that module for why: the
inventory reads `git ls-files`, so an uncommitted fixture would exercise only
the walk fallback). That means the fixture gates cannot be a plain CLI call on a
path — something has to build the repository first. This script is that
something, so the Makefile stays a list of gates rather than a shell program.

    scripts/fixture_gate.py determinism | fold | golden | bless
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from helpers import make_repo  # noqa: E402
from cdp.cli import check_determinism, main, run_golden  # noqa: E402

FIXTURE_SLUG = "minirepo@fixture"


def gate_determinism(repo: Path) -> int:
    problems = check_determinism(repo)
    if problems:
        for problem in problems:
            print("  %s" % problem, file=sys.stderr)
        print("FAIL  fixture is not reproducible", file=sys.stderr)
        return 1
    print("ok    two scans of the fixture agree byte-for-byte")
    return 0


def gate_fold(repo: Path, tmp: Path) -> int:
    state = tmp / "state"
    code = main(["scan", "--repo", str(repo), "--state-dir", str(state), "--quiet"])
    if code:
        return code
    # M2.3: verification now runs inside `fold`, against `--repo` -- omitting
    # it here used to be harmless (fold never touched the filesystem) and is
    # now a real bug: without it, `--repo` defaults to cwd and every claim's
    # anchor is checked against the wrong tree and demoted.
    return main(["fold", "--check", "--repo", str(repo), "--state-dir", str(state)])


def gate_golden(repo: Path, bless: bool) -> int:
    code, report = run_golden(repo, bless=bless, name=FIXTURE_SLUG)
    print(report, file=sys.stderr if code else sys.stdout)
    return code


def main_(argv):
    if len(argv) != 2 or argv[1] not in ("determinism", "fold", "golden", "bless"):
        print(__doc__, file=sys.stderr)
        return 2
    gate = argv[1]
    with tempfile.TemporaryDirectory(prefix="cdp-fixture-") as tmp:
        repo = make_repo(Path(tmp))
        if gate == "determinism":
            return gate_determinism(repo)
        if gate == "fold":
            return gate_fold(repo, Path(tmp))
        return gate_golden(repo, bless=(gate == "bless"))


if __name__ == "__main__":
    raise SystemExit(main_(sys.argv))
