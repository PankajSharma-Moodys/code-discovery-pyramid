"""Phase 7, M7.5 (0.19) -- `cdp export`: canonical JSON, reviewable patches,
archive dump, anonymised corpus."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo

from cdp.cli import main
from cdp.export import export_anonymized, export_archive, export_json, export_patches
from cdp.golden import canonical
from cdp.query import Store
from cdp.store.file_backend import FileStore
from cdp.store.sqlite_backend import SqliteStore

_REAL_ANCHOR = [{"file": "Dockerfile", "line": 3, "anchor": "ENV MINI_DB_URL=jdbc:postgresql://localhost/mini"}]
_DISTINCTIVE_SUBJECT = "AcmeWidgetFactory.build"
_DISTINCTIVE_STATEMENT = "AcmeWidgetFactory builds a WidgetGizmo for the checkout pipeline"


def _patch(node: str, run_id: str, claim_id: str, subject: str, statement: str) -> dict:
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
                "subject": subject,
                "statement": statement,
                "evidence": _REAL_ANCHOR,
                "confidence": "high",
            }
        ],
        "unknowns": [],
    }


class ExportJsonTest(unittest.TestCase):
    def test_json_export_round_trips_into_a_file_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            main(["scan", "--repo", str(repo), "--state-dir", str(state), "--quiet"])

            src = Store(state)
            out = Path(tmp) / "export-json"
            written = export_json(src.backend, out)
            self.assertIn("state", written)
            self.assertIn("graph", written)

            roundtripped = FileStore(out)
            self.assertTrue(roundtripped.exists())
            self.assertEqual(
                canonical(src.backend.read_artifact("state")),
                canonical(roundtripped.read_artifact("state")),
            )
            self.assertEqual(
                canonical(src.backend.read_artifact("graph")),
                canonical(roundtripped.read_artifact("graph")),
            )
            src.close()


class ExportPatchesTest(unittest.TestCase):
    def test_one_reviewable_file_per_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            main(["scan", "--repo", str(repo), "--state-dir", str(state), "--quiet"])

            store = Store(state)
            n_patches = len(store.backend.load_patches())
            out = Path(tmp) / "export-patches"
            n = export_patches(store.backend, out)
            self.assertEqual(n, n_patches)
            files = sorted(out.glob("*.json"))
            self.assertEqual(len(files), n_patches)
            # Each file is the patch, reviewable as plain JSON.
            first = json.loads(files[0].read_text())
            self.assertIn("node", first)
            store.close()


class ExportArchiveTest(unittest.TestCase):
    def test_archive_dump_matches_the_compacted_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            main(["scan", "--repo", str(repo), "--state-dir", str(state), "--quiet"])

            store = SqliteStore(state / "index.db")
            node = store.read_artifact("partition")["scopes"][0]["node"]
            for i in range(3):
                store.append_patch(
                    _patch(node, "cdp-run%d" % i, "synthetic.%d" % i, "Synthetic%d" % i, "x" * 20),
                    "run-%d" % i,
                )
            result = store.compact(keep_generations=1, threshold=0.0)
            self.assertGreater(result["moved"], 0)

            out = Path(tmp) / "export-archive"
            n = export_archive(store, out)
            self.assertEqual(n, result["moved"])
            dumped = json.loads((out / "archive.json").read_text())
            self.assertEqual(len(dumped), result["moved"])
            self.assertTrue(all("content_hash" in row for row in dumped))
            store.close()

    def test_archive_export_refused_on_a_backend_with_no_cold_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileStore(Path(tmp) / "filestore")
            self.assertFalse(store.supports_compaction())
            with self.assertRaises(Exception):
                export_archive(store, Path(tmp) / "export-archive-fail")


class ExportAnonymizedTest(unittest.TestCase):
    def test_symbol_names_paths_and_claim_text_do_not_survive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp))
            state = Path(tmp) / "state"
            main(["scan", "--repo", str(repo), "--state-dir", str(state), "--quiet"])

            store = SqliteStore(state / "index.db")
            node = store.read_artifact("partition")["scopes"][0]["node"]
            store.append_patch(
                _patch(node, "cdp-distinctive0", "distinctive.claim",
                       _DISTINCTIVE_SUBJECT, _DISTINCTIVE_STATEMENT),
                "distinctive-run",
            )
            from cdp.state import fold
            folded = fold(store.load_patches(), store.read_artifact("xref"),
                          store.read_artifact("partition"), repo=repo)
            store.write_artifact("state", folded)
            self.assertIn(_DISTINCTIVE_SUBJECT, {c["subject"] for c in folded["claims"]})

            out = Path(tmp) / "export-anon"
            counts = export_anonymized(store, out)
            self.assertGreater(counts["claims"], 0)
            corpus_text = (out / "corpus.json").read_text()

            self.assertNotIn(_DISTINCTIVE_SUBJECT, corpus_text)
            self.assertNotIn("AcmeWidgetFactory", corpus_text)
            self.assertNotIn(_DISTINCTIVE_STATEMENT, corpus_text)
            self.assertNotIn("Dockerfile", corpus_text)
            self.assertNotIn(node, corpus_text)
            store.close()


if __name__ == "__main__":
    unittest.main()
