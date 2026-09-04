"""Renders ScanResult to JSON. Reads the ScanResult only — rule 2."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from code_scanner.model import ScanResult


def write(result: ScanResult, out: str) -> None:
    payload = json.dumps(result.to_dict(), indent=2, sort_keys=False)
    if out == "-":
        sys.stdout.write(payload + "\n")
    else:
        Path(out).write_text(payload + "\n", encoding="utf-8")
