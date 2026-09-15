#!/usr/bin/env python3
"""CDP entry point.

    python3 .claude/skills/cdp/run.py scan --repo .

Stdlib only, Python 3.9+. No install step: this file adds its own directory to
`sys.path` so the bundled `cdp` package imports whether or not the skill is on
`PYTHONPATH`, and whether or not the target repository has a virtualenv.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info < (3, 9):  # pragma: no cover
    sys.stderr.write("cdp needs Python 3.9 or newer (found %s)\n" % sys.version.split()[0])
    raise SystemExit(2)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cdp.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
