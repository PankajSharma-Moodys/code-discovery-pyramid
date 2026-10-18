"""The object store's public per-file reads (`segments`, `extract_heads`, `call_owners`) answer
exactly what the whole artifacts say, on SQLite and Postgres; `FileStore` has none."""

from __future__ import annotations

import difflib
import json
import os
import random
import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline, make_repo

from cdp.query.store import Store
from cdp.query.suggest import _close_matches
from cdp.store import FileStore, SqliteStore

POSTGRES_DSN = os.environ.get("CDP_TEST_POSTGRES_DSN")


def _fqns(row):
    """Every string under a `fqn` key in `row`, at any depth."""
    if isinstance(row, dict):
        for k, v in row.items():
            if k == "fqn" and isinstance(v, str):
                yield v
            else:
                yield from _fqns(v)
    elif isinstance(row, list):
        for v in row:
            yield from _fqns(v)


class ReadsMixin:
    pipeline: Pipeline

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pipeline = Pipeline(make_repo(Path(cls._tmp.name) / "repo"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        p = self.pipeline
        self.store = self.make_store()
        self.store.begin_snapshot("probe", "c1")
        for name, data in (("inventory", p.inventory), ("extract", p.extraction), ("xref", p.xref),
                           ("manifest", {"run_id": "r"})):
            self.store.write_artifact(name, data)
        self.store.use_snapshot("probe", "c1")
        self.assertIsNotNone(self.store.parts_skeleton("extract"), "extract must be decomposed")
        self.assertIsNotNone(self.store.parts_skeleton("xref"), "xref must be decomposed")
        self.files = sorted(self.store.current_files())
        self.extract = json.loads(json.dumps(p.extraction, sort_keys=True))
        self.uses = json.loads(json.dumps(p.xref, sort_keys=True))["uses"]

    def rows_of(self, path, key="defines"):
        return [r for r in self.extract[key] if r.get("file") == path]

    def test_segments_match_file_part_and_whole_xref(self):
        got = self.store.segments("xref", self.files + ["no/such/file"])
        self.assertTrue(got)
        self.assertNotIn("no/such/file", got)
        for path, seg in got.items():
            self.assertEqual(seg, self.store.file_part("xref", path))
            self.assertEqual(sorted(map(json.dumps, seg["uses"])),
                             sorted(json.dumps(u) for u in self.uses if u["from_file"] == path))
        self.assertEqual(self.store.segments("extract", []), {})

    def test_extract_heads_hold_every_list_but_uses(self):
        for _ in ("cold", "cached"):
            heads = self.store.extract_heads()
            self.assertTrue(heads)
            for path, head in heads.items():
                self.assertNotIn("uses", head)
                whole = self.store.file_part("extract", path)
                self.assertEqual(head, {k: v for k, v in whole.items() if k != "uses"})
                self.assertEqual(sorted(map(json.dumps, head.get("defines", []))),
                                 sorted(map(json.dumps, self.rows_of(path))))

    def test_extract_heads_keep_only_files_naming_a_needle(self):
        fqn = next(d["fqn"] for d in self.extract["defines"])
        needle = fqn[:max(1, len(fqn) - 2)]          # a prefix: any string starting with it counts
        heads = self.store.extract_heads([needle])
        for path in self.files:
            whole = self.store.file_part("extract", path) or {}
            text = json.dumps({k: v for k, v in whole.items() if k != "uses"}, sort_keys=True)
            self.assertEqual(path in heads, json.dumps(needle)[:-1] in text, path)
        self.assertEqual(self.store.extract_heads(["\x01never"]), {})
        one = next(iter(heads))
        self.assertEqual(list(self.store.extract_heads(paths=[one])), [one])

    def test_call_owners_match_the_whole_xref_uses(self):
        owners = self.store.call_owners()
        self.assertEqual(set(owners), {p for p in self.files if self.store.current_files()[p].get("xseg")})
        for path, (got, binding) in owners.items():
            rows = [u for u in self.uses if u["from_file"] == path]
            self.assertEqual(got, frozenset(f.partition("#")[0].encode() for r in rows for f in _fqns(r)), path)
            self.assertEqual(binding, '"kind": "binding"' in json.dumps(rows, sort_keys=True), path)
        self.assertIs(self.store.call_owners(), owners, "kept per snapshot view")

    def test_query_store_reads_agree_with_whole_artifacts(self):
        q = Store(self.store)
        self.assertEqual(q.defines_in(self.files), {p: self.rows_of(p) for p in self.files})
        self.assertEqual(q.xref_uses_in(self.files), self.uses)
        self.assertEqual(q.extract_where([""])["defines"], self.extract["defines"])


class SqliteReads(ReadsMixin, unittest.TestCase):
    def make_store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = SqliteStore(Path(tmp.name) / "index.db")
        self.addCleanup(store.close)
        return store


@unittest.skipUnless(POSTGRES_DSN, "set CDP_TEST_POSTGRES_DSN to run the Postgres read tests")
class PostgresReads(ReadsMixin, unittest.TestCase):
    def make_store(self):
        from cdp.store.postgres_backend import PostgresStore

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = PostgresStore(POSTGRES_DSN, "cdp_test_reads_%d" % os.getpid(), inbox_root=Path(tmp.name) / "in")
        self.addCleanup(lambda: (store.drop_schema(), store.close()))
        return store


class FileStoreHasNoSegments(unittest.TestCase):
    def test_defaults_are_empty(self):
        with tempfile.TemporaryDirectory() as d:
            store = FileStore(Path(d))
            self.assertEqual(store.segments("xref", ["a.py"]), {})
            self.assertEqual(store.extract_heads(["x"]), {})
            self.assertEqual(store.call_owners(), {})


class CloseMatchesAreDifflibs(unittest.TestCase):
    def test_same_list_as_get_close_matches(self):
        rnd, alpha = random.Random(7), "abcab.#_XyZ"
        word = lambda k: "".join(rnd.choice(alpha) for _ in range(rnd.randint(0, k)))   # noqa: E731
        for _ in range(3000):
            pool = list(dict.fromkeys(word(9) for _ in range(rnd.randint(0, 40))))
            w, n, cutoff = word(8), rnd.randint(1, 6), rnd.choice([0.0, 0.3, 0.6, 0.8])
            self.assertEqual(_close_matches(w, pool, n, cutoff), difflib.get_close_matches(w, pool, n, cutoff))


if __name__ == "__main__":
    unittest.main()
