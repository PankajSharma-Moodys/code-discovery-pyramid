#!/usr/bin/env python3
"""Regenerate SKILL.md and docs/CDP_REFERENCE.md from `cdp/guide_*.py`.

    python3 scripts/gen_guide.py           # rewrite both
    python3 scripts/gen_guide.py --check   # exit 1 if either is stale
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cdp import guide  # noqa: E402

TARGETS = {ROOT / "SKILL.md": guide.skill_md, ROOT / "docs" / "CDP_REFERENCE.md": guide.reference_md}


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="Regenerate SKILL.md and docs/CDP_REFERENCE.md from cdp/guide_*.py.")
    parser.add_argument("--check", action="store_true", help="exit 1 if either file is stale; write nothing")
    args = parser.parse_args(argv)
    stale = []
    for path, render in TARGETS.items():
        new = render()
        if args.check:
            if not path.exists() or path.read_text() != new:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(new)
    if stale:
        print("stale (run python3 scripts/gen_guide.py): " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
