"""`query symbol <Enum>`: the `states` section built from D4a's state evidence.

The evidence (`access`/`value`/`from` on a use of an enum value) must survive the store's read-back
-- both the segment path (`used_by_entries`) and the whole-artifact path (`_user`) -- on SQLite and
Postgres, and `q_symbol` turns it into per-value write/guard sites, transitions and the values no
code outside tests writes.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline
from test_java_resolution import inline_repo

from cdp.query import Store, render
from cdp.query.compact import compact
from cdp.query.lookup import q_symbol
from cdp.store import SqliteStore

POSTGRES_DSN = os.environ.get("CDP_TEST_POSTGRES_DSN")

FILES = {
    "build.sbt": "name := \"m\"\n",
    "src/main/scala/p/St.scala": "package p\nobject St extends Enumeration {\n  val QUEUED, RUNNING, DONE, GONE = Value\n}\n",
    "src/main/scala/p/Ev.scala": "package p\ncase class Ev(id: Int, newStatus: St.Value, oldStatus: St.Value)\n",
    "src/main/scala/p/Svc.scala": (
        "package p\nclass Svc {\n  def go(s: St.Value): Unit = {\n"
        "    if (s == St.QUEUED) post(Ev(1, St.RUNNING, St.QUEUED))\n"    # 4
        "    post(Ev(2, St.DONE, s))\n"                                   # 5
        "  }\n  def post(e: Ev): Unit = ()\n}\n"),
    "src/test/scala/p/SvcTest.scala": (
        "package p\nclass SvcTest {\n  def t(): Unit = {\n    val e = Ev(3, St.DONE, St.RUNNING)\n  }\n}\n"),
    "src/main/scala/p/Plain.scala": "package p\nobject Plain {\n  def f(e: Ev): Int = e.id\n}\n",
}


class StateViewMixin:
    pipeline: Pipeline

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pipeline = Pipeline(inline_repo(Path(cls._tmp.name) / "repo", FILES))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        p = self.pipeline
        self.backend = self.make_store()
        self.backend.begin_snapshot("probe", "c1")
        for name, data in (("inventory", p.inventory), ("extract", p.extraction), ("xref", p.xref),
                           ("manifest", {"run_id": "r"})):
            self.backend.write_artifact(name, data)
        self.backend.use_snapshot("probe", "c1")
        self.store = Store(self.backend)

    def test_read_back_keeps_state_evidence(self):
        want = self.pipeline.xref["used_by"]["p.St"]
        self.assertTrue([u for u in want if u.get("from")], "fixture must carry a transition")
        self.assertEqual(self.store.used_by["p.St"], want)                         # segment path
        self.assertEqual(self.backend.read_artifact("xref")["used_by"]["p.St"], want)   # whole artifact

    def test_states_section(self):
        e = q_symbol(self.store, "p.St", exact=True)["found"][0]
        st = e["states"]
        self.assertEqual(list(st), ["DONE", "GONE", "QUEUED", "RUNNING"])   # by declaration line, then name
        self.assertEqual([(r["at"], r["in"], r.get("from")) for r in st["RUNNING"]["write"]],
                         [("src/main/scala/p/Svc.scala:4", "p.Svc#go", "QUEUED")])
        self.assertEqual([r["at"] for r in st["DONE"]["write"]], ["src/main/scala/p/Svc.scala:5"])
        self.assertEqual([r["at"] for r in st["QUEUED"]["guard"]], ["src/main/scala/p/Svc.scala:4"])
        self.assertEqual(st["QUEUED"].get("read"), 1)
        # the test file's write (DONE) is counted, not listed; its old-value arg (RUNNING) is a read
        self.assertEqual((st["DONE"].get("test"), st["RUNNING"].get("read")), (1, 1))
        self.assertEqual(e["transitions"], [{"from": "QUEUED", "to": "RUNNING", "at": "src/main/scala/p/Svc.scala:4"}])
        self.assertEqual(e["no_writer"], ["GONE", "QUEUED"])
        self.assertEqual(st["GONE"], {})
        # compact shortens `in`; text names every part
        self.assertEqual(compact({"found": [e]})["found"][0]["states"]["RUNNING"]["write"][0]["in"], "Svc#go")
        text = render(q_symbol(self.store, "p.St", exact=True))
        self.assertIn("write src/main/scala/p/Svc.scala:4  in p.Svc#go  from QUEUED", text)
        self.assertIn("transition QUEUED -> RUNNING  src/main/scala/p/Svc.scala:4", text)
        self.assertIn("no writer found: GONE, QUEUED", text)

    def test_budget_counts_state_rows(self):
        from cdp.query.budget import Budget
        b = Budget(2)
        e = q_symbol(self.store, "p.St", exact=True, budget=b)["found"][0]
        listed = sum(len(s.get(a, [])) for s in e["states"].values() for a in ("write", "guard"))
        self.assertEqual(listed + len(e["used_by"]), 1)    # one row for the match itself
        self.assertEqual(e["states_cut"], 2)
        self.assertEqual(e["no_writer"], ["GONE", "QUEUED"])   # from every row, not the shown ones
        self.assertTrue(e["see_all"])

    def test_non_enum_symbol_has_no_states(self):
        e = q_symbol(self.store, "p.Ev", exact=True)["found"][0]
        self.assertTrue(e["used_by"])
        self.assertFalse({"states", "transitions", "no_writer"} & set(e))


class SqliteStateView(StateViewMixin, unittest.TestCase):
    def make_store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = SqliteStore(Path(tmp.name) / "index.db")
        self.addCleanup(store.close)
        return store


@unittest.skipUnless(POSTGRES_DSN, "set CDP_TEST_POSTGRES_DSN to run the Postgres read-back")
class PostgresStateView(StateViewMixin, unittest.TestCase):
    def make_store(self):
        from cdp.store.postgres_backend import PostgresStore

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = PostgresStore(POSTGRES_DSN, "cdp_test_state_view_%d" % os.getpid(), inbox_root=Path(tmp.name) / "in")
        self.addCleanup(lambda: (store.drop_schema(), store.close()))
        return store


if __name__ == "__main__":
    unittest.main()
