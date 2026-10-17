"""T3 scan-speed changes to the object store keep its bytes and answers: worker-encoded cache
segments, threaded compression, the streamed cached extraction, and `preload_artifact`."""
import pickle
import tempfile
import unittest
import zlib
from pathlib import Path

from helpers import make_repo  # noqa: F401  (sets sys.path)

from cdp.extract import run_extract
from cdp.inventory import build_inventory
from cdp.store import objects
from cdp.store.sqlite_backend import SqliteStore
from cdp.util import stable_hash


class ScanPerfStoreTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def store(self, name: str) -> SqliteStore:
        s = SqliteStore(self.tmp / name / "index.db")
        self.addCleanup(s.close)
        return s

    def test_cached_extraction_matches_uncached_cold_and_warm(self):
        repo = make_repo(self.tmp / "repo")
        inventory = build_inventory(repo)
        want = stable_hash(run_extract(repo, inventory, workers=1))
        for workers in (1, 4):
            cache = self.store("w%d" % workers)
            for _ in ("cold", "warm"):
                self.assertEqual(stable_hash(run_extract(repo, inventory, workers=workers, cache=cache)), want)

    def test_worker_encoded_segment_is_byte_identical(self):
        body = {"facts": {"defines": [{"fqn": "a.B", "line": 3}], "loc": 7, "package": None}}
        enc = pickle.loads(pickle.dumps(objects.encode_seg(body)))     # as a worker hands it back
        self.assertIsInstance(enc, objects.Encoded)
        a, b = self.store("a"), self.store("b")
        ia = a._put_segs([(body, [])], None)
        ib = b._put_segs([(enc, [])], None)
        ra = a._rows("SELECT h, z FROM seg WHERE id=?", ia)[0]
        rb = b._rows("SELECT h, z FROM seg WHERE id=?", ib)[0]
        self.assertEqual(bytes(ra[0]), bytes(rb[0]))
        self.assertEqual(zlib.decompress(bytes(ra[1])), zlib.decompress(bytes(rb[1])))
        self.assertEqual(b._get_segs(ib)[ib[0]], body)

    def test_threaded_compression_matches_serial(self):
        raws = [(b"%d-" % i) * 40000 for i in range(16)]        # above the threading threshold
        self.assertGreater(sum(map(len, raws)), objects._THREAD_MIN_BYTES)
        self.assertEqual(objects._compress_many(raws), [zlib.compress(r, objects.ZLEVEL) for r in raws])

    def test_preload_hands_over_once_and_write_clears_it(self):
        s = self.store("p")
        s.begin_snapshot("probe", "c1")
        s.write_artifact("graph", {"nodes": [1, 2]})
        s.write_artifact("manifest", {"run_id": "r"})
        s.preload_artifact("graph")
        first = s.read_artifact("graph")
        second = s.read_artifact("graph")
        self.assertEqual(first, {"nodes": [1, 2]})
        self.assertEqual(second, first)
        self.assertIsNot(second, first)
        s.preload_artifact("graph")
        s.write_artifact("graph", {"nodes": [3]})
        self.assertEqual(s.read_artifact("graph"), {"nodes": [3]})
        s.preload_artifact("absent")            # nothing to preload: a no-op
        self.assertEqual(s.read_artifact("absent", {"d": 1}), {"d": 1})


if __name__ == "__main__":
    unittest.main()
