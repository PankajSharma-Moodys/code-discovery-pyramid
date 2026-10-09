"""Phase 1 / A: CDP follows a flow from its entry point to storage and to the
next service, with a citation on every hop.

Three fixtures, each a case from PLAN.md's acceptance list:
`orderrepo` (route -> service -> repository -> entity -> table), `callerrepo` +
`calleerepo` (an outbound HTTP call and the route that serves it), and
`wiredrepo` (one-implementation interface, URL held in a config key).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import Pipeline, make_repo

from cdp.link import scan_links


def _pipeline(name: str):
    tmp = tempfile.TemporaryDirectory()
    return tmp, Pipeline(make_repo(Path(tmp.name), name))


class OrderFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.p = _pipeline("orderrepo")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_route_reaches_the_table_with_a_citation_on_every_hop(self):
        paths = [x for x in self.p.dataflow["paths"]
                 if x["source"].endswith("OrderResource#place") and x["sink"] == "table:orders"]
        self.assertEqual(len(paths), 1)
        path = paths[0]
        self.assertEqual(path["trigger"], "route:POST /orders")
        self.assertEqual(
            [h["to"].rsplit(".", 1)[-1] for h in path["hops"]],
            ["OrderService#placeOrder", "OrderRepository#save", "OrderEntity", "table:orders"],
        )
        self.assertTrue(path["fully_anchored"])
        for hop in path["hops"]:
            self.assertTrue(hop["anchor"]["file"] and hop["anchor"]["line"])
        # The call is cited at the line that makes it, not at an import.
        first = path["hops"][0]["anchor"]
        self.assertIn("service.placeOrder", first["anchor"])

    def test_symbol_lists_the_same_package_caller(self):
        users = self.p.xref["used_by"]["com.acme.orders.OrderService"]
        self.assertIn("OrderResource.java", {u["file"].rsplit("/", 1)[-1] for u in users})

    def test_repository_is_linked_to_its_entity(self):
        rows = [u for u in self.p.xref["uses"]
                if u.get("kind") == "binding" and u["fqn"] == "com.acme.orders.OrderEntity"]
        self.assertEqual([r["from_symbol"] for r in rows], ["com.acme.orders.OrderRepository"])

    def test_unknown_types_do_not_become_unresolved_references(self):
        # `String`, `Long`, `Id` ... name nothing in the repo; they are dropped,
        # not counted against the scan.
        self.assertEqual(self.p.xref["resolution"].get("unresolved", 0), 0)


class HttpLinkTest(unittest.TestCase):
    def test_outbound_call_links_to_the_route_that_serves_it(self):
        t1, caller = _pipeline("callerrepo")
        t2, callee = _pipeline("calleerepo")
        self.addCleanup(t1.cleanup)
        self.addCleanup(t2.cleanup)
        out = [e for e in caller.dataflow["edges"] if e["channel"] == "http_out"
               and not e["target"].startswith("library:")]
        self.assertEqual([e["target"] for e in out], ["http:POST http://billing/v1/charges"])
        report = scan_links([
            {"repo": "orders", "head": "a", "dataflow": caller.dataflow},
            {"repo": "billing", "head": "b", "dataflow": callee.dataflow},
        ])
        self.assertEqual(len(report["links"]), 1)
        link = report["links"][0]
        self.assertEqual(link["caller"]["repo"], "orders")
        self.assertEqual(link["callee"]["repo"], "billing")
        self.assertEqual(link["match_kind"], "exact")


class WiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.p = _pipeline("wiredrepo")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_interface_with_one_implementation_resolves_to_it(self):
        path = [x for x in self.p.dataflow["paths"] if x["trigger"] == "route:GET /greet"][0]
        hops = [h["to"].rsplit(".", 1)[-1] for h in path["hops"]]
        self.assertEqual(hops[:3], ["Greeter#greet", "GreeterImpl#greet", "RemoteClient#send"])
        self.assertEqual(path["hops"][1]["confidence"], "medium")

    def test_call_through_a_wildcard_import_lands_on_the_imported_class(self):
        # `import com.acme.wired.store.*;` -- AuditStore is not in GreeterImpl's
        # own package, and must not be guessed to be.
        targets = {e["target"] for e in self.p.dataflow["edges"]
                   if e["source"] == "com.acme.wired.GreeterImpl#greet"}
        self.assertIn("com.acme.wired.store.AuditStore#record", targets)
        self.assertNotIn("com.acme.wired.AuditStore#record", targets)

    def test_url_held_in_a_config_key_is_the_target(self):
        out = [e["target"] for e in self.p.dataflow["edges"]
               if e["channel"] == "http_out" and not e["target"].startswith("library:")]
        self.assertEqual(out, ["http:POST ${billing.url}/v1/charges"])

    def test_a_second_implementation_stops_the_guess(self):
        # Two implementers: the interface hop must not pick one.
        from cdp.dataflow import build_dataflow
        x = self.p.xref
        extra = dict(x["uses"][0])
        extra.update({"kind": "implements", "fqn": "com.acme.wired.Greeter",
                      "from_symbol": "com.acme.wired.Other", "resolved": "local",
                      "from_module": extra["from_module"]})
        x2 = dict(x, uses=x["uses"] + [extra])
        flow = build_dataflow(self.p.extraction, x2, self.p.graph)
        self.assertFalse([e for e in flow["edges"] if e["source"] == "com.acme.wired.Greeter#greet"])


if __name__ == "__main__":
    unittest.main()
