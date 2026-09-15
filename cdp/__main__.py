"""`python3 -m cdp ...` — the form that works without the console script.

`run.py` remains the zero-install entry point for a vendored skill copy; this
one is for a checkout or an installed package, where `cdp` is already importable.
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
