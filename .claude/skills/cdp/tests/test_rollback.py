"""Phase 3, M3.7 -- rollback and `--as-of`.

Two properties, each with its own acceptance line in `phase_3_plan.md`:
rollback restores the prior state exactly, and it does so by excluding a run
via a ledger rather than deleting or rewriting a patch (R5). `--as-of` is the
same "up to a run" cut, read-only.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from helpers import make_repo

from cdp.rollback import (
    load_excluded_run_ids,
    patches_excluding_run,
    patches_up_to_run,
    record_rollback,
    resolve_run_id,
)
from cdp.state import check_fold, fold
from cdp.store.file_backend import FileStore
from cdp.store.sqlite_backend import SqliteStore

import unittest

SKILL_ROOT = Path(__file__).resolve().parent.parent
RUN_PY = SKILL_ROOT / "run.py"


def _patch(node: str, run_id: str, claim_id: str, evidence=None) -> dict:
    return {
        "schema_version": "1.0.0",
        "node": node,
        "run_id": run_id,
        "status": "complete",
        "generation": 1,
        "claims": [
            {
                "id": claim_id,
                "kind": "defines",
                "subject": claim_id,
                "statement": "x",
                "evidence": evidence if evidence is not None else [],
                "confidence": "high",
            }
        ],
        "unknowns": [],
    }


# A real anchor from `tests/fixtures/minirepo`, reused so a synthetic "bad
# run" claim survives `verify_all` (empty evidence gets demoted immediately,
# which would make the CLI-level tests below pass for the wrong reason).
_REAL_ANCHOR = [{"file": "Dockerfile", "line": 3, "anchor": "ENV MINI_DB_URL=jdbc:postgresql://localhost/mini"}]


class HelperFunctionTest(unittest.TestCase):
    def test_resolve_run_id_passes_through_a_run_id_and_hashes_a_commit(self) -> None:
        self.assertEqual(resolve_run_id("cdp-abc123456789"), "cdp-abc123456789")
        self.assertEqual(resolve_run_id("deadbeef" * 5), resolve_run_id("deadbeef" * 5))
        self.assertTrue(resolve_run_id("deadbeefcafe").startswith("cdp-"))

    def test_patches_excluding_run_drops_only_that_run(self) -> None:
        patches = [_patch("root/a", "cdp-r1", "a.1"), _patch("root/b", "cdp-r2", "b.1")]
        kept, excluded = patches_excluding_run(patches, "cdp-r1")
        self.assertEqual(excluded, {"cdp-r1"})
        self.assertEqual([p["node"] for p in kept], ["root/b"])

    def test_patches_excluding_run_not_found_excludes_nothing(self) -> None:
        patches = [_patch("root/a", "cdp-r1", "a.1")]
        kept, excluded = patches_excluding_run(patches, "cdp-missing")
        self.assertEqual(excluded, set())
        self.assertEqual(kept, patches)

    def test_patches_up_to_run_cuts_after_the_runs_last_occurrence(self) -> None:
        patches = [
            _patch("root/a", "cdp-r1", "a.1"),
            _patch("root/b", "cdp-r1", "b.1"),  # same run, two patches
            _patch("root/c", "cdp-r2", "c.1"),
        ]
        kept, excluded, found = patches_up_to_run(patches, "cdp-r1")
        self.assertTrue(found)
        self.assertEqual([p["node"] for p in kept], ["root/a", "root/b"])
        self.assertEqual(excluded, {"cdp-r2"})

    def test_patches_up_to_run_distinguishes_not_found_from_already_latest(self) -> None:
        patches = [_patch("root/a", "cdp-r1", "a.1")]
        _, excluded_latest, found_latest = patches_up_to_run(patches, "cdp-r1")
        self.assertTrue(found_latest)
        self.assertEqual(excluded_latest, set())
        _, excluded_missing, found_missing = patches_up_to_run(patches, "cdp-missing")
        self.assertFalse(found_missing)
        self.assertEqual(excluded_missing, set())


class FoldExclusionTest(unittest.TestCase):
    def test_excluding_a_run_restores_the_prior_fold_exactly(self) -> None:
        """The acceptance line, literally: rollback of a bad run restores the
        prior state -- i.e. folding with the run appended-then-excluded must
        equal folding as if it had never been appended."""
        before = [_patch("root/a", "cdp-r1", "a.1")]
        bad_run = [_patch("root/b", "cdp-bad", "b.1")]

        prior = fold(before, {"symbols": {}}, None)
        after_bad_run = fold(before + bad_run, {"symbols": {}}, None)
        rolled_back = fold(before + bad_run, {"symbols": {}}, None, excluded_run_ids=frozenset({"cdp-bad"}))

        self.assertNotEqual(
            {c["subject"] for c in after_bad_run["claims"]},
            {c["subject"] for c in prior["claims"]},
        )
        self.assertEqual(
            {c["subject"] for c in rolled_back["claims"]},
            {c["subject"] for c in prior["claims"]},
        )
        self.assertEqual(rolled_back["provenance"]["fold_hash"], prior["provenance"]["fold_hash"])
        self.assertEqual(rolled_back["rollback"], {"excluded_run_ids": ["cdp-bad"]})
        self.assertIsNone(prior["rollback"])

    def test_check_fold_reads_the_ledger_so_a_rolled_back_state_still_verifies(self) -> None:
        """Without threading the ledger through, `check_fold` recomputes over
        the raw log and finds a mismatch against the rolled-back state.json --
        the same class of false positive D11 already named for rename_map."""
        with tempfile.TemporaryDirectory() as tmp:
            store = FileStore(Path(tmp))
            patches = [_patch("root/a", "cdp-r1", "a.1"), _patch("root/bad", "cdp-bad", "b.1")]
            for i, p in enumerate(patches):
                store.append_patch(p, "patch-%d" % i)

            folded = fold(store.load_patches(), {"symbols": {}}, None, excluded_run_ids=frozenset({"cdp-bad"}))
            store.write_artifact("state", folded)

            # Without recording the rollback, check_fold must see drift.
            problems_before_ledger = check_fold(store, {"symbols": {}}, None)
            self.assertTrue(problems_before_ledger)

            record_rollback(store, "to_run", "cdp-bad", {"cdp-bad"}, "test")
            self.assertEqual(load_excluded_run_ids(store), frozenset({"cdp-bad"}))
            problems_after_ledger = check_fold(store, {"symbols": {}}, None)
            self.assertEqual(problems_after_ledger, [])


class RollbackCliTest(unittest.TestCase):
    def _scan(self, repo: Path, state: Path) -> None:
        subprocess.run(
            [sys.executable, str(RUN_PY), "scan", "--repo", str(repo),
             "--state-dir", str(state), "--quiet"], check=True, capture_output=True)

    def test_rollback_to_run_excludes_an_injected_bad_run_and_fold_check_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            self._scan(repo, state)

            store = SqliteStore(state / "index.db")
            before_claims = {c["id"] for c in store.read_artifact("state")["claims"]}

            # Simulate a bad run: a leaf patch asserting a claim that should
            # never have existed, appended under its own run_id.
            bad_patch = _patch("root/bogus", "cdp-bad000000", "bogus.claim", evidence=_REAL_ANCHOR)
            store.append_patch(bad_patch, "bad-run")
            state_mod_folded = fold(
                store.load_patches(), store.read_artifact("xref"), store.read_artifact("partition"),
                repo=repo,
            )
            store.write_artifact("state", state_mod_folded)
            self.assertIn("bogus.claim", {c["id"] for c in state_mod_folded["claims"]})

            proc = subprocess.run(
                [sys.executable, str(RUN_PY), "rollback", "--to-run", "cdp-bad000000",
                 "--repo", str(repo), "--state-dir", str(state)],
                capture_output=True, text=True, check=True,
            )
            self.assertIn("excluded 1 run(s)", proc.stdout)

            after_claims = {c["id"] for c in store.read_artifact("state")["claims"]}
            self.assertEqual(after_claims, before_claims)
            self.assertNotIn("bogus.claim", after_claims)

            check = subprocess.run(
                [sys.executable, str(RUN_PY), "fold", "--check", "--repo", str(repo),
                 "--state-dir", str(state)],
                capture_output=True, text=True,
            )
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_as_of_replays_the_log_without_mutating_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            self._scan(repo, state)

            store = SqliteStore(state / "index.db")
            patches = store.load_patches()
            root_run_id = patches[0]["run_id"]

            store.append_patch(
                _patch("root/bogus", "cdp-later0000", "bogus.claim", evidence=_REAL_ANCHOR), "later-run"
            )
            subprocess.run(
                [sys.executable, str(RUN_PY), "fold", "--repo", str(repo), "--state-dir", str(state)],
                check=True, capture_output=True,
            )
            state_before = store.read_artifact("state")
            live = subprocess.run(
                [sys.executable, str(RUN_PY), "query", "claims", "--json",
                 "--repo", str(repo), "--state-dir", str(state)],
                capture_output=True, text=True, check=True,
            )
            self.assertIn("bogus.claim", live.stdout)

            past = subprocess.run(
                [sys.executable, str(RUN_PY), "query", "claims", "--json",
                 "--as-of", root_run_id, "--repo", str(repo), "--state-dir", str(state)],
                capture_output=True, text=True, check=True,
            )
            self.assertNotIn("bogus.claim", past.stdout)
            self.assertIn(root_run_id, past.stdout)  # patch_log_as_of marker

            # Read-only: state.json on disk is untouched by --as-of.
            self.assertEqual(store.read_artifact("state")["provenance"], state_before["provenance"])


if __name__ == "__main__":
    unittest.main()
