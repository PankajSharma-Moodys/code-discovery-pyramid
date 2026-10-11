#!/usr/bin/env python3
"""Stress `cdp run --parallel N` outside pytest (F1: a crash in libsqlite3 killed the
process, which pytest cannot report as a failure).

    scripts/parallel_stress.py [RUNS=50] [PARALLEL=4]    # exit 1 on any failed run
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from helpers import make_repo  # noqa: E402

RUNNER = """import json, sys
from pathlib import Path
p = Path(sys.argv[3]); node = p.stem.replace('__', '/')
p.write_text(json.dumps({'schema_version': '1.0.0', 'node': node, 'run_id': 'x',
    'status': 'complete', 'claims': [],
    'unknowns': [{'question': 'what is here?', 'why_unresolved': 'fake', 'needs': 'needs_human'}]}))
"""


def one_run(tmp: Path, parallel: str) -> subprocess.CompletedProcess:
    repo, state = make_repo(tmp), tmp / "state"
    env = dict(os.environ, CDP_HOME=str(tmp / "home"))
    run_py = str(ROOT / "run.py")
    subprocess.run([sys.executable, run_py, "scan", "--repo", str(repo), "--state-dir", str(state),
                    "--quiet"], check=True, capture_output=True, env=env)
    (tmp / "runner.py").write_text(RUNNER)
    return subprocess.run(
        [sys.executable, run_py, "run", "--repo", str(repo), "--state-dir", str(state), "--wave-all",
         "--parallel", parallel, "--runner-cmd", "%s %s" % (sys.executable, tmp / "runner.py")],
        capture_output=True, text=True, env=env)


def main(argv) -> int:
    runs = int(argv[1]) if len(argv) > 1 else 50
    parallel = argv[2] if len(argv) > 2 else "4"
    failures = 0
    for i in range(runs):
        with tempfile.TemporaryDirectory() as tmp:
            proc = one_run(Path(tmp), parallel)
        if proc.returncode != 0:
            failures += 1
            print("run %d: rc=%s %s" % (i, proc.returncode, (proc.stderr or proc.stdout)[-400:]))
    print("%d/%d runs failed (--parallel %s)" % (failures, runs, parallel))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
