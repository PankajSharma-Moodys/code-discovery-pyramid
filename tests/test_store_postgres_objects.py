"""PostgresStore's object store against a real server: the objects advisory lock defers a sweep
while a writer is mid-build, and a sweep frees exactly the objects no manifest reaches."""
import os
import tempfile
import unittest
from pathlib import Path

POSTGRES_DSN = os.environ.get("CDP_TEST_POSTGRES_DSN")


@unittest.skipUnless(POSTGRES_DSN, "set CDP_TEST_POSTGRES_DSN to run the Postgres object-store tests")
class PostgresObjectStoreTest(unittest.TestCase):
    def setUp(self):
        from cdp.store.postgres_backend import PostgresStore

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        schema = "cdp_test_obj_%d" % os.getpid()
        self.a = PostgresStore(POSTGRES_DSN, schema, inbox_root=Path(tmp.name) / "a")
        self.b = PostgresStore(POSTGRES_DSN, schema, inbox_root=Path(tmp.name) / "b")
        self.addCleanup(self._teardown)

    def _teardown(self):
        self.a.close()
        self.b.drop_schema()
        self.b.close()

    def test_sweep_defers_to_a_writer_then_frees_only_orphans(self):
        a, b = self.a, self.b
        a.begin_snapshot("probe", "c1")
        a.write_artifact("inventory", {"files": [{"path": "x.py", "module": "x", "role": "src",
                                                  "language": "python", "bytes": 3, "loc": 1, "binary": False}]})
        a.write_artifact("misc", {"k": [1, 2, 3]})
        a._hold_objects_lock()
        self.assertIsNone(b.sweep_objects(), "a sweep must not run while a writer holds the objects lock")
        a._commit_build()
        self.assertFalse(any(b.sweep_objects(dry_run=True).values()))
        b._x("INSERT INTO doc (h, z) VALUES (%s, %s)", (b._bin(b"orphan-doc"), b._bin(b"z")))
        b._x("INSERT INTO seg (h, z) VALUES (%s, %s)", (b._bin(b"orphan-seg"), b._bin(b"z")))
        b._db_commit()
        freed = b.sweep_objects()
        self.assertEqual((freed["doc"], freed["seg"]), (1, 1))
        self.assertFalse(any(b.sweep_objects().values()))
        self.assertEqual(b.dangling_references(), [])
        b.use_snapshot("probe", "c1")
        self.assertEqual(b.read_artifact("misc"), {"k": [1, 2, 3]})


if __name__ == "__main__":
    unittest.main()
