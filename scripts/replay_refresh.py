#!/usr/bin/env python3
"""Replay the last N commits of a repo under the refresh == scan invariant (F2 check (a)).

    scripts/replay_refresh.py REPO [N=26] [SUBFOLDER]

REPO is cloned into a temp dir (never modified); it is scanned at HEAD~N and refreshed one
commit at a time, each step compared with a fresh scan. Exit 1 if any step differs."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import repo_layouts as L  # noqa: E402


def main(argv) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    src, n = Path(argv[1]).resolve(), int(argv[2]) if len(argv) > 2 else 26
    sub = argv[3] if len(argv) > 3 else ""
    with tempfile.TemporaryDirectory() as tmp:
        clone = L.Repo(Path(tmp) / "clone")
        subprocess.run(["git", "clone", "-q", "--no-local", str(src), str(clone.path)], check=True)
        shas = clone.git("rev-list", "--first-parent", "--reverse", "HEAD~%d..HEAD" % n).split()
        clone.git("checkout", "-q", clone.git("rev-parse", shas[0] + "~1"))
        cdp = L.Cdp(tmp, clone.path / sub if sub else clone.path)
        cdp.scan()
        bad = 0
        for sha in shas:
            clone.git("checkout", "-q", sha)
            cdp.refresh()
            problems = L.check_refresh_equals_scan(cdp)
            bad += bool(problems)
            print("%s  %s" % (sha[:9], "ok" if not problems else "DIFFERS: " + "; ".join(problems[:2])))
        print("%d/%d commits differ from a fresh scan" % (bad, len(shas)))
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
