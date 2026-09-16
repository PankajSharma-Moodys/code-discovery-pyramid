"""Phase 4 (M4.4) -- `cdp answer`, end to end: the same pipeline a leaf
agent's patch goes through (validate -> verify anchor -> entail -> fold), no
bypass, reproducing the `ARCHITECTURE.md` RetryPolicy.execute scenario shape:
a human answers an unknown, the claim is discharged with attribution, and a
later edit to the anchored file invalidates the review (R9, via `refresh`)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from helpers import SKILL_ROOT, make_repo

from cdp.store.sqlite_backend import SqliteStore

import unittest

RUN_PY = SKILL_ROOT / "run.py"
ANCHOR_FILE = "core/src/main/java/COM/Example/mini/core/WidgetRepository.java"


def _run(*args, cwd=None, check=True):
    return subprocess.run(
        [sys.executable, str(RUN_PY)] + list(args),
        check=check, capture_output=True, text=True, cwd=cwd,
    )


class AnswerEndToEndTest(unittest.TestCase):
    def _scan(self, tmp: Path) -> tuple[Path, Path]:
        repo = make_repo(Path(tmp))
        state = Path(tmp) / "state"
        _run("scan", "--repo", str(repo), "--state-dir", str(state), "--quiet")
        return repo, state

    def _node_for(self, state: Path, suffix: str) -> str:
        backend = SqliteStore(state / "index.db")
        backend.use_latest_snapshot()
        partition = backend.read_artifact("partition")
        backend.close()
        return next(s["node"] for s in partition["scopes"] if s["node"].endswith(suffix))

    def test_answer_is_kept_and_discharges_a_matching_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, state = self._scan(tmp)
            node = self._node_for(state, "core")

            backend = SqliteStore(state / "index.db")
            backend.use_latest_snapshot()
            manifest = backend.read_artifact("manifest")
            backend.ensure_inbox()
            backend.close()
            patch = {
                "schema_version": "1.0.0",
                "node": node,
                "run_id": manifest.get("run_id", "test-run"),
                "status": "complete",
                "claims": [],
                "unknowns": [{
                    "question": "why does WidgetRepository extend JpaRepository directly?",
                    "why_unresolved": "no rationale found in the module",
                    "subject": "com.example.mini.core.WidgetRepository",
                    "needs": "needs_human",
                }],
            }
            (state / "patches" / "inbox" / "core.json").write_text(json.dumps(patch))
            _run("collect", "--repo", str(repo), "--state-dir", str(state))

            proc = _run(
                "answer", node,
                "--subject", "com.example.mini.core.WidgetRepository",
                "--kind", "naming",
                "--claim", "Extends JpaRepository directly; no custom queries needed yet",
                "--anchor", "%s:7" % ANCHOR_FILE,
                "--author", "jdoe <jdoe@example.invalid>",
                "--repo", str(repo), "--state-dir", str(state),
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("verdict=", proc.stdout)

            backend = SqliteStore(state / "index.db")
            backend.use_latest_snapshot()
            live_state = backend.read_artifact("state")
            backend.close()

            claim = next(c for c in live_state["claims"] if c.get("author_kind") == "human")
            self.assertEqual(claim["author"], "jdoe <jdoe@example.invalid>")

            discharged = [u for u in live_state["unknowns"]
                          if u.get("subject") == "com.example.mini.core.WidgetRepository"]
            self.assertEqual(len(discharged), 1)
            self.assertEqual(discharged[0]["status"], "resolved")
            self.assertEqual(discharged[0]["resolved_by"]["claim_id"], claim["id"])
            self.assertEqual(discharged[0]["resolved_by"]["author_kind"], "human")

    def test_fabricated_anchor_is_rejected_humans_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, state = self._scan(tmp)
            node = self._node_for(state, "core")
            proc = _run(
                "answer", node,
                "--subject", "com.example.mini.core.Nothing",
                "--kind", "naming", "--claim", "this anchor does not exist",
                "--anchor", "%s:9999" % ANCHOR_FILE,
                "--repo", str(repo), "--state-dir", str(state), check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("no citable anchor", proc.stdout + proc.stderr)

    def test_review_invalidated_after_the_anchored_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, state = self._scan(tmp)
            node = self._node_for(state, "core")
            _run(
                "answer", node,
                "--subject", "com.example.mini.core.WidgetRepository",
                "--kind", "naming", "--claim", "Extends JpaRepository directly",
                "--anchor", "%s:7" % ANCHOR_FILE,
                "--repo", str(repo), "--state-dir", str(state),
            )
            backend = SqliteStore(state / "index.db")
            backend.use_latest_snapshot()
            before = backend.read_artifact("state")
            backend.close()
            claim_before = next(c for c in before["claims"] if c.get("author_kind") == "human")
            self.assertIsNotNone(claim_before["claim_reviewed_at"])

            target = repo / ANCHOR_FILE
            target.write_text("// a leading comment shifts every line down\n" + target.read_text())
            subprocess.run(["git", "-C", str(repo), "commit", "-aqm", "shift"], check=True,
                            env={"GIT_AUTHOR_NAME": "cdp", "GIT_AUTHOR_EMAIL": "cdp@example.invalid",
                                 "GIT_COMMITTER_NAME": "cdp", "GIT_COMMITTER_EMAIL": "cdp@example.invalid",
                                 "PATH": "/usr/bin:/bin:/usr/local/bin"})

            _run("refresh", "--repo", str(repo), "--state-dir", str(state), "--quiet")
            backend = SqliteStore(state / "index.db")
            backend.use_latest_snapshot()
            after = backend.read_artifact("state")
            backend.close()
            claim_after = next(c for c in after["claims"] if c.get("author_kind") == "human")
            # R9: the anchor relocated (the inserted line shifted it down), so
            # its review is invalidated -- the claim survives the edit, but
            # `claim_reviewed_at` is cleared, landing it in "anchored but
            # unreviewed" rather than quietly staying LIVE against stale trust.
            self.assertIsNone(claim_after["claim_reviewed_at"])
            self.assertEqual(claim_after["evidence"][0]["line"], 8)


if __name__ == "__main__":
    unittest.main()
