"""Java call extraction must beat grep: the flow reads like the code does.

`reservrepo` is the shape that broke on a real repo: a resource calling a service
whose real work happens through `this.method()` calls to private methods and
through an injected abstract helper with several implementations.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline, make_repo

S = "com.acme.res.ReservationService"


class JavaCallsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Pipeline(make_repo(Path(cls.tmp.name), "reservrepo"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def targets_from(self, method: str):
        return {e["target"] for e in self.p.dataflow["edges"]
                if e["source"] == "%s#%s" % (S, method) and e["channel"] == "call"}

    def test_this_dot_calls_to_own_methods_are_edges(self):
        t = self.targets_from("makeReservations")
        self.assertIn(S + "#validateMakeReservation", t)
        self.assertIn(S + "#getReservationCapacity", t)
        self.assertIn(S + "#initializeUserAndPassword", t)

    def test_bare_calls_to_own_methods_are_edges(self):
        self.assertIn(S + "#checkIdempotency", self.targets_from("makeReservations"))

    def test_this_dot_call_from_a_loop_body(self):
        self.assertIn(S + "#initializeUserAndPassword", self.targets_from("processPendingReservations"))

    def test_private_and_protected_methods_are_symbols(self):
        for name, vis in (("validateMakeReservation", "private"),
                          ("checkIdempotency", "private"),
                          ("initializeUserAndPassword", "protected")):
            rows = self.p.defines("%s#%s" % (S, name))
            self.assertEqual([r["visibility"] for r in rows], [vis], name)

    def test_symbol_table_has_callers_of_a_private_method(self):
        users = self.p.xref["used_by"].get(S + "#validateMakeReservation", [])
        self.assertEqual({u["file"].rsplit("/", 1)[-1] for u in users}, {"ReservationService.java"})

    def test_job_reaches_the_service_through_this_field_call(self):
        callers = {u["file"].rsplit("/", 1)[-1]
                   for u in self.p.xref["used_by"].get(S + "#processPendingReservations", [])}
        self.assertIn("ProcessPendingJob.java", callers)

    def test_abstract_call_reaches_every_implementation(self):
        t = self.targets_from("initializeUserAndPassword")
        base = "com.acme.res.ServerHelper#createReservationCredentials"
        self.assertIn(base, t)
        impls = {e["target"] for e in self.p.dataflow["edges"]
                 if e["source"] == base and e["channel"] == "call"}
        self.assertEqual(impls, {"com.acme.res.PostgresServerHelper#createReservationCredentials",
                                 "com.acme.res.MssqlServerHelper#createReservationCredentials"})

    def test_members_carry_their_extent(self):
        row = self.p.defines(S + "#makeReservations")[0]
        self.assertEqual((row["anchor"]["line"], row["end_line"]), (15, 24))


if __name__ == "__main__":
    unittest.main()
