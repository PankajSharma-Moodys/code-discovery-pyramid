"""Phase 3, M3.2/M3.3 -- incremental extract equivalence and rename-awareness.

The equivalence test is M3.2's whole acceptance criterion: without it,
incremental extract is a silent divergence generator. The rename test is the
"landmine" `PHASE/phase_3_plan.md` calls out by name: a `git mv` must not
mass-demote a correct corpus.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import MiniRepoTest, make_repo

from cdp.extract import run_extract
from cdp.refresh import classify_changes, incremental_extract
from cdp.state import fold
from cdp.verify import FileCache, verify_all


def _commit_all(repo: Path, message: str) -> str:
    env_args = ["-c", "user.name=cdp", "-c", "user.email=cdp@example.invalid"]
    subprocess.run(["git", "-C", str(repo)] + env_args + ["add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo)] + env_args + ["-c", "commit.gpgsign=false", "commit", "-q", "-m", message],
        check=True,
    )
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


class IncrementalExtractEquivalenceTest(MiniRepoTest):
    def test_reextracting_one_module_equals_a_full_rescan(self) -> None:
        prior = self.pipeline.extraction
        inventory = self.pipeline.inventory
        one_file = inventory["files"][0]["path"]

        incremental = incremental_extract(self.repo, inventory, prior, {one_file})
        full = run_extract(self.repo, inventory)

        self.assertEqual(incremental, full)

    def test_empty_changed_set_carries_everything_forward(self) -> None:
        prior = self.pipeline.extraction
        inventory = self.pipeline.inventory
        incremental = incremental_extract(self.repo, inventory, prior, set())
        self.assertEqual(incremental, prior)


@unittest.skipUnless(subprocess.run(["git", "--version"], capture_output=True).returncode == 0, "git required")
class RenameAwarenessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(Path(self.tmp.name))
        self.prev_sha = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _patches_citing(self, rel_path: str, claim_id: str = "widget.claim") -> list:
        return [{
            "schema_version": "1.0.0", "node": "root", "run_id": "r1", "status": "complete",
            "claims": [{
                "id": claim_id, "kind": "structure", "subject": "widget", "confidence": "high",
                "claim_reviewed_at": self.prev_sha,
                "statement": "Widget carries the fixture's core entity shape.",
                "evidence": [{"file": rel_path, "line": 1, "anchor": "package com.example.mini.core;"}],
            }],
        }]

    def test_pure_rename_relocates_and_review_stands(self) -> None:
        old_rel = "core/src/main/java/COM/Example/mini/core/Widget.java"
        new_rel = "core/src/main/java/COM/Example/mini/core/WidgetMoved.java"
        subprocess.run(["git", "-C", str(self.repo), "mv", old_rel, new_rel], check=True)
        new_sha = _commit_all(self.repo, "pure rename")

        rename_map, edited, added, deleted = classify_changes(self.repo, self.prev_sha, new_sha)
        self.assertEqual(rename_map, {old_rel: new_rel})
        self.assertEqual(edited, set())

        patches = self._patches_citing(old_rel)
        verified, stats = verify_all(self.repo, patches, head_sha=new_sha, rename_map=rename_map,
                                     edited_files=frozenset(edited))
        self.assertEqual(stats["claims_demoted"], 0, "the landmine: a git mv must not demote a live claim")
        kept = verified[0]["claims"][0]
        self.assertEqual(kept["evidence"][0]["file"], new_rel)
        self.assertEqual(kept["claim_reviewed_at"], self.prev_sha, "R9: pure rename carries review forward")
        self.assertEqual(kept["anchor_verified_at"], new_sha)

    def test_real_edit_invalidates_review_without_demoting(self) -> None:
        rel = "core/src/main/java/COM/Example/mini/core/WidgetEntity.java"
        path = self.repo / rel
        path.write_text(path.read_text() + "\n// a genuinely new line\n")
        new_sha = _commit_all(self.repo, "real edit")

        rename_map, edited, added, deleted = classify_changes(self.repo, self.prev_sha, new_sha)
        self.assertIn(rel, edited)

        patches = self._patches_citing(rel)
        # WidgetEntity.java's package line (line 1) is untouched by the appended
        # trailing line, so the anchor still resolves -- this asserts R9's
        # invalidation fires from the file being edited, not from the anchor
        # itself failing to verify.
        verified, stats = verify_all(self.repo, patches, head_sha=new_sha, rename_map=rename_map,
                                     edited_files=frozenset(edited))
        self.assertEqual(stats["claims_demoted"], 0)
        kept = verified[0]["claims"][0]
        self.assertIsNone(kept["claim_reviewed_at"], "R9: a real edit invalidates review")

    def test_reformat_only_carries_review_forward(self) -> None:
        rel = "core/src/main/java/COM/Example/mini/core/WidgetEntity.java"
        path = self.repo / rel
        # Reindent every line -- normalise_ws-identical, not a real edit.
        reindented = "\n".join("    " + line if line.strip() else line for line in path.read_text().splitlines())
        path.write_text(reindented + "\n")
        new_sha = _commit_all(self.repo, "reformat only")

        rename_map, edited, added, deleted = classify_changes(self.repo, self.prev_sha, new_sha)
        self.assertNotIn(rel, edited, "whitespace-only reindent must not count as an edit")

    def test_git_mv_of_a_whole_package_causes_zero_mass_demotion(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "mv", "core", "core2"], check=True)
        new_sha = _commit_all(self.repo, "move whole package")

        rename_map, edited, added, deleted = classify_changes(self.repo, self.prev_sha, new_sha)
        self.assertTrue(rename_map, "expected every file under core/ to appear as a rename")

        patches = []
        for old_rel, new_rel in rename_map.items():
            first_line = (self.repo / new_rel).read_text().splitlines()[0]
            if len(first_line.strip()) < 12:
                continue  # too short to qualify as an anchor on its own
            patches.append({
                "schema_version": "1.0.0", "node": "root", "run_id": "r1", "status": "complete",
                "claims": [{
                    "id": "claim.%d" % len(patches), "kind": "structure", "subject": "x",
                    "confidence": "high", "claim_reviewed_at": self.prev_sha,
                    "statement": "A claim anchored somewhere under the moved package.",
                    "evidence": [{"file": old_rel, "line": 1, "anchor": first_line}],
                }],
            })
        verified, stats = verify_all(self.repo, patches, head_sha=new_sha, rename_map=rename_map,
                                     edited_files=frozenset(edited))
        self.assertEqual(stats["claims_demoted"], 0, "git mv of a whole package must not mass-demote")


if __name__ == "__main__":
    unittest.main()
