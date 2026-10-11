"""Every test runs against its own machine home.

CDP keeps one store per machine under `CDP_HOME` (default `~/.cdp`). A test
that forgot `--state-dir` would otherwise read and write the developer's real
index, so the home is pointed at a throwaway directory for the whole session.
"""

import os
import tempfile

_HOME = tempfile.TemporaryDirectory(prefix="cdp-test-home-")
os.environ["CDP_HOME"] = _HOME.name

# Test modules import the shared scaffolding as `from helpers import ...`.
import sys
from pathlib import Path

_TESTS = str(Path(__file__).resolve().parent / "tests")
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
