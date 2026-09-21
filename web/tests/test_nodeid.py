"""`nodeid` against this repo's real scanned shapes, not hand-built fixtures --
same "verify against ground truth" posture as `WEB_RESEARCH.md`'s own probe."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MINIREPO = REPO_ROOT / "tests" / "fixtures" / "minirepo"


class NodeIdConstructorsTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        from web.api import nodeid

        cases = {
            nodeid.module_id("core"): ("module", "core"),
            nodeid.scope_id("root/core"): ("scope", "root/core"),
            nodeid.file_id("root/core/a.py"): ("file", "root/core/a.py"),
            nodeid.sym_id("pkg.Foo.bar"): ("sym", "pkg.Foo.bar"),
            nodeid.route_id("GET /orders"): ("route", "GET /orders"),
            nodeid.table_id("orders"): ("table", "orders"),
        }
        for node_id, expected in cases.items():
            self.assertEqual(nodeid.parse(node_id), expected)

    def test_parse_rejects_unnamespaced_and_unknown(self) -> None:
        from web.api import nodeid

        with self.assertRaises(ValueError):
            nodeid.parse("no-colon-here")
        with self.assertRaises(ValueError):
            nodeid.parse("bogus:thing")


class SubjectIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.state_dir, ignore_errors=True)
        subprocess.run(
            [sys.executable, "-m", "cdp", "scan", "--repo", str(MINIREPO),
             "--state-dir", str(self.state_dir)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )
        from web.api.store_reader import ReadOnlyConnection

        conn = ReadOnlyConnection(self.state_dir / "index.db")
        snapshot_id = conn.latest_pinned_snapshot()
        self.xref = conn.read_artifact(snapshot_id, "xref")
        self.partition = conn.read_artifact(snapshot_id, "partition")
        self.dataflow = conn.read_artifact(snapshot_id, "dataflow")
        conn.close()

    def test_every_real_symbol_classifies_as_sym(self) -> None:
        from web.api import nodeid

        index = nodeid.SubjectIndex(self.xref, self.partition, self.dataflow)
        symbols = list(self.xref.get("symbols", {}).keys())
        self.assertTrue(symbols, "fixture scan produced no symbols")
        for fqn in symbols:
            self.assertEqual(index.classify(fqn), nodeid.sym_id(fqn))

    def test_every_real_scope_node_classifies_as_scope(self) -> None:
        from web.api import nodeid

        index = nodeid.SubjectIndex(self.xref, self.partition, self.dataflow)
        scopes = [s["node"] for s in self.partition.get("scopes", [])]
        self.assertTrue(scopes, "fixture scan produced no scopes")
        for node in scopes:
            self.assertEqual(index.classify(node), nodeid.scope_id(node))

    def test_unresolved_subject_returns_none(self) -> None:
        from web.api import nodeid

        index = nodeid.SubjectIndex(self.xref, self.partition, self.dataflow)
        self.assertIsNone(index.classify("definitely_not_a_real_subject_xyz"))


if __name__ == "__main__":
    unittest.main()
