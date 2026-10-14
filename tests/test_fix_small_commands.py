"""diff with no args, collect exit code / junk markers, export on an empty store."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo

from cdp.cli import main
from cdp.query import Store


def _run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = main(argv)
    return rc, out.getvalue()


class SmallCommandsTest(unittest.TestCase):
    def _scanned(self, tmp):
        repo = make_repo(Path(tmp))
        state = Path(tmp) / "state"
        main(["scan", "--repo", str(repo), "--state-dir", str(state), "--quiet"])
        return repo, state

    def test_diff_without_arguments_compares_current_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, state = self._scanned(tmp)
            rc, out = _run(["diff", "--repo", str(repo), "--state-dir", str(state)])
            self.assertEqual(rc, 0, out)
            self.assertIn("module(s) added", out)

    def test_collect_all_rejected_exits_1_leaves_no_junk_and_keeps_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, state = self._scanned(tmp)
            inbox = next(state.glob("work/*/patches/inbox"))
            (inbox / "empty.json").write_text(json.dumps(
                {"schema_version": "1.0.0", "node": "", "run_id": "x", "status": "complete"}))
            (inbox / "bad.json").write_text("{bad")
            (inbox / "arr.json").write_text("[]")
            store = Store(state)
            before = len(store.backend.load_patches())
            store.close()
            rc, out = _run(["collect", "--repo", str(repo), "--state-dir", str(state)])
            self.assertEqual(rc, 1, out)
            self.assertIn("rejected", out)
            store = Store(state)
            self.assertEqual(len(store.backend.load_patches()), before)
            self.assertFalse([u for u in store.state["unknowns"] if u.get("source_node") == "empty"])
            store.close()

    def test_collect_empty_inbox_exits_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, state = self._scanned(tmp)
            rc, _ = _run(["collect", "--repo", str(repo), "--state-dir", str(state)])
            self.assertEqual(rc, 0)

    def test_export_on_empty_store_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            out = Path(tmp) / "o"
            rc, _ = _run(["export", "--repo", str(repo), "--state-dir", str(Path(tmp) / "none"),
                          "--out", str(out)])
            self.assertNotEqual(rc, 0)
            self.assertFalse(out.exists() and any(out.iterdir()))


if __name__ == "__main__":
    unittest.main()
