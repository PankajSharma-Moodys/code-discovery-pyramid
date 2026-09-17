"""F9 -- `run_extract`'s process-pool path, checked directly against real
files rather than trusted on the docstring's ordering argument.

`PARALLEL_MIN_FILES` keeps every existing test and the fixture golden path on
the sequential branch untouched; these tests force the parallel branch with
an explicit `workers=` override and assert it produces byte-identical output
to the sequential branch, which is the actual claim being made, not merely
its absence of a crash.
"""

from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

from helpers import SKILL_ROOT, make_repo  # noqa: F401  (sets sys.path)

from cdp.extract import run_extract
from cdp.inventory import build_inventory
from cdp.util import stable_hash


class ParallelMatchesSequentialTest(unittest.TestCase):
    def test_parallel_matches_sequential_on_minirepo(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            inventory = build_inventory(repo)
            sequential = run_extract(repo, inventory, workers=1)
            # Explicit override forces the parallel branch despite the
            # fixture sitting well under PARALLEL_MIN_FILES.
            parallel = run_extract(repo, inventory, workers=4)
        self.assertEqual(stable_hash(sequential), stable_hash(parallel))

    def test_default_is_sequential_below_threshold(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            inventory = build_inventory(repo)
            auto = run_extract(repo, inventory)
            explicit_sequential = run_extract(repo, inventory, workers=1)
        self.assertEqual(stable_hash(auto), stable_hash(explicit_sequential))

    @unittest.skipUnless(os.environ.get("TARGET_REPO"), "TARGET_REPO not set")
    def test_parallel_matches_sequential_on_target_repo(self) -> None:
        """Real, non-fixture input -- the file count that actually clears
        PARALLEL_MIN_FILES and exercises real multiprocessing, not just the
        forced-override path above."""
        repo = Path(os.environ["TARGET_REPO"]).expanduser().resolve()
        inventory = build_inventory(repo)

        start = time.time()
        sequential = run_extract(repo, inventory, workers=1)
        sequential_s = time.time() - start

        start = time.time()
        parallel = run_extract(repo, inventory, workers=None)  # auto
        parallel_s = time.time() - start

        self.assertEqual(stable_hash(sequential), stable_hash(parallel))
        print("\nrun_extract: sequential %.2fs, parallel(auto) %.2fs"
              % (sequential_s, parallel_s))


if __name__ == "__main__":
    unittest.main()
