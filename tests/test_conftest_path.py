"""F3: test modules import `helpers`; that must not depend on the caller's PYTHONPATH or
pytest's import mode (importlib mode does not put `tests/` on sys.path by itself)."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from helpers import SKILL_ROOT


class ConftestPathTest(unittest.TestCase):
    def test_helpers_importable_without_pythonpath_in_importlib_mode(self):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_home.py", "-q", "--import-mode=importlib",
             "-p", "no:cacheprovider"],
            cwd=str(SKILL_ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout[-800:] + proc.stderr[-400:])


if __name__ == "__main__":
    unittest.main()
